"""Convergence and fallback rules (spec 10.7). Pure functions, no I/O.

    valid  = ballots that parsed and arrived before the deadline (None = invalid)
    quorum = ceil(0.6 * K)
    if count(valid) < quorum                              -> chair
    top    = option with the most first choices
    share  = count(top) / count(valid)
    if share >= 0.80 and fewer than 2 blocking objections -> consensus
    elif rounds remain and time remains                   -> continue
    elif share > 0.50                                     -> majority
    else                                                  -> chair

Rules that the pseudo-code leaves open, as implemented here:
- The 80% test is one seat, one vote. `ConsensusResult.share` is always that plain share.
- A blocking objection counts only when the seat's own choice is NOT the top option.
- A tie for the most first choices is broken by competence-weighted votes, then by a Borda
  count over the rankings, then by option id (so the result is deterministic).
- The majority test uses the competence-weighted share of `top` when weights are given,
  and the plain share when they are not.
- A seat missing from `weights` has weight 1.0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Optional

from council.core.schemas import Ballot, Option

_EPS = 1e-9

Status = Literal["consensus", "continue", "majority", "chair"]


@dataclass(frozen=True)
class ConsensusConfig:
    threshold: float = 0.80
    quorum_fraction: float = 0.60
    blocking_to_veto: int = 2
    early_exit_min_confidence: float = 0.70


@dataclass
class ConsensusResult:
    status: Status
    top: Optional[str]
    share: float
    tally: dict[str, int] = field(default_factory=dict)
    valid: int = 0
    quorum: int = 0
    blocked: bool = False


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def quorum_for(k: int, cfg: Optional[ConsensusConfig] = None) -> int:
    """ceil(quorum_fraction * k), safe against float noise (0.6 * 5 must be 3, not 4)."""
    cfg = cfg or ConsensusConfig()
    return max(0, math.ceil(cfg.quorum_fraction * k - _EPS))


def _valid(ballots: dict[int, Optional[Ballot]]) -> dict[int, Ballot]:
    return {seat: b for seat, b in ballots.items() if b is not None}


def _weight(weights: Optional[dict[int, float]], seat: int) -> float:
    if not weights:
        return 1.0
    return float(weights.get(seat, 1.0))


def _count_tally(valid: dict[int, Ballot]) -> dict[str, int]:
    tally: dict[str, int] = {}
    for seat in sorted(valid):
        choice = valid[seat].choice
        tally[choice] = tally.get(choice, 0) + 1
    return tally


def _rankings(valid: dict[int, Ballot]) -> list[list[str]]:
    """One ranking per valid ballot. A ballot with no ranking ranks only its choice."""
    out: list[list[str]] = []
    for seat in sorted(valid):
        b = valid[seat]
        out.append(list(b.ranking) if b.ranking else [b.choice])
    return out


def _ordered(valid: dict[int, Ballot], weights: Optional[dict[int, float]], by_weight_first: bool) -> list[str]:
    """Option ids, best first. Keys: count and weighted votes (order set by the flag), Borda, id."""
    counts = _count_tally(valid)
    wsum = weighted_tally(valid, weights)
    points = borda(_rankings(valid))

    def key(opt: str):
        c = -counts.get(opt, 0)
        w = -round(wsum.get(opt, 0.0), 9)
        first, second = (w, c) if by_weight_first else (c, w)
        return (first, second, -points.get(opt, 0), opt)

    return sorted(counts, key=key)


# --------------------------------------------------------------------------------------
# Public functions
# --------------------------------------------------------------------------------------


def borda(rankings: list[list[str]]) -> dict[str, int]:
    """Borda count. With m distinct options overall, place i (0-based) earns m - 1 - i points.

    An option a ranking leaves out earns 0 from it. A repeated id counts once, at its first place.
    """
    ids: list[str] = []
    seen: set[str] = set()
    cleaned: list[list[str]] = []
    for ranking in rankings:
        row: list[str] = []
        row_seen: set[str] = set()
        for opt in ranking:
            if opt in row_seen:
                continue
            row_seen.add(opt)
            row.append(opt)
            if opt not in seen:
                seen.add(opt)
                ids.append(opt)
        cleaned.append(row)
    m = len(ids)
    points: dict[str, int] = {opt: 0 for opt in ids}
    for row in cleaned:
        for i, opt in enumerate(row):
            points[opt] += m - 1 - i
    return points


def competence_weights(q: dict[int, float]) -> dict[int, float]:
    """Seat q values normalized to a mean of 1, then clipped to 0.5..1.5."""
    if not q:
        return {}
    mean = sum(float(v) for v in q.values()) / len(q)
    if mean <= 0:
        return {seat: 1.0 for seat in q}
    return {seat: min(1.5, max(0.5, float(v) / mean)) for seat, v in q.items()}


def weighted_tally(
    ballots: dict[int, Optional[Ballot]], weights: Optional[dict[int, float]] = None
) -> dict[str, float]:
    """Option id -> sum of the weights of the seats whose first choice it is. None ballots are skipped."""
    tally: dict[str, float] = {}
    for seat in sorted(ballots):
        b = ballots[seat]
        if b is None:
            continue
        tally[b.choice] = tally.get(b.choice, 0.0) + _weight(weights, seat)
    return tally


def top_two(
    ballots: dict[int, Optional[Ballot]], weights: Optional[dict[int, float]] = None
) -> list[str]:
    """The (up to) two leading option ids for Chair arbitration, best first.

    Ordered by weighted votes, then plain count, then Borda, then id.
    """
    return _ordered(_valid(ballots), weights, by_weight_first=True)[:2]


def evaluate(
    ballots: dict[int, Optional[Ballot]],
    k: int,
    cfg: Optional[ConsensusConfig] = None,
    rounds_remain: bool = False,
    time_remains: bool = False,
    weights: Optional[dict[int, float]] = None,
) -> ConsensusResult:
    cfg = cfg or ConsensusConfig()
    valid = _valid(ballots)
    n = len(valid)
    quorum = quorum_for(k, cfg)
    tally = _count_tally(valid)

    top: Optional[str] = None
    share = 0.0
    blocked = False
    if n:
        top = _ordered(valid, weights, by_weight_first=False)[0]
        share = tally[top] / n
        objections = sum(
            1
            for b in valid.values()
            if b.choice != top and b.blocking_objection and b.blocking_objection.strip()
        )
        blocked = objections >= cfg.blocking_to_veto

    def result(status: Status) -> ConsensusResult:
        return ConsensusResult(
            status=status, top=top, share=share, tally=tally, valid=n, quorum=quorum, blocked=blocked
        )

    if n < quorum or top is None:
        return result("chair")
    if share >= cfg.threshold - _EPS and not blocked:
        return result("consensus")
    if rounds_remain and time_remains:
        return result("continue")

    majority_share = share
    if weights:
        wsum = weighted_tally(valid, weights)
        total = sum(wsum.values())
        majority_share = wsum.get(top, 0.0) / total if total > 0 else 0.0
    if majority_share > 0.50 + _EPS:
        return result("majority")
    return result("chair")


def early_agreement(
    options: list[Option],
    confidences: dict[int, float],
    k: int,
    cfg: Optional[ConsensusConfig] = None,
) -> Optional[Option]:
    """Round-0 early exit. The agreed Option, or None when debate must go on.

    Valid seats are the seats that hold any option. Needs a quorum, a single largest option
    with share >= threshold, and a mean confidence of its holders >= early_exit_min_confidence.
    A holder with no recorded confidence is left out of the mean; no confidences at all = None.
    """
    cfg = cfg or ConsensusConfig()
    held: dict[str, set[int]] = {o.id: set(o.holders) for o in options}
    seats: set[int] = set()
    for holders in held.values():
        seats |= holders
    n = len(seats)
    if n == 0 or n < quorum_for(k, cfg):
        return None

    ranked = sorted(options, key=lambda o: (-len(held[o.id]), o.id))
    best = ranked[0]
    size = len(held[best.id])
    if len(ranked) > 1 and len(held[ranked[1].id]) == size:
        return None
    if size / n < cfg.threshold - _EPS:
        return None

    confs = [float(confidences[s]) for s in held[best.id] if s in confidences]
    if not confs:
        return None
    if sum(confs) / len(confs) < cfg.early_exit_min_confidence - _EPS:
        return None
    return best


__all__ = [
    "ConsensusConfig",
    "ConsensusResult",
    "evaluate",
    "early_agreement",
    "borda",
    "competence_weights",
    "weighted_tally",
    "top_two",
    "quorum_for",
]
