"""Outlier choice for the tribunal (27.3). Pure functions, no I/O."""

from __future__ import annotations

from typing import Optional

from council.core.schemas import Ballot, SeatAssignment


def seat_distance(
    ballot: Optional[Ballot],
    r0_option: Optional[str],
    chosen: str,
    n_options: int,
) -> float:
    """How far a seat sits from the decision. 0 means it chose the decision."""
    if ballot is None:
        if r0_option is not None and r0_option != chosen:
            return 1.0
        return 0.0
    if ballot.choice == chosen:
        return 0.0
    denom = max(n_options - 1, 1)
    if chosen in ballot.ranking:
        rank = ballot.ranking.index(chosen)
    else:
        rank = denom  # not ranked at all: treat as last
    d = min(rank, denom) / denom
    if ballot.blocking_objection:
        d += 0.5
    d += 0.25 * float(ballot.confidence)
    return d


def find_outlier(
    final_ballots: dict[int, Optional[Ballot]],
    r0_options: dict[int, Optional[str]],
    chosen: str,
    n_options: int,
) -> Optional[int]:
    """Seat with the greatest distance > 0. Ties: higher confidence, then lower seat."""
    best: Optional[tuple[float, float, int]] = None
    for seat in sorted(set(final_ballots) | set(r0_options)):
        ballot = final_ballots.get(seat)
        d = seat_distance(ballot, r0_options.get(seat), chosen, n_options)
        if d <= 0:
            continue
        conf = float(ballot.confidence) if ballot is not None else 0.0
        key = (d, conf, -seat)
        if best is None or key > best:
            best = key
    return None if best is None else -best[2]


def examiners(
    seats: list[SeatAssignment],
    outlier_seat: int,
    final_ballots: dict[int, Optional[Ballot]],
    chosen: str,
    n: int,
) -> list[int]:
    """Majority seats by competence, best first, at most n. Falls back to any non-outlier."""
    if n <= 0:
        return []
    others = [s for s in seats if s.seat_no != outlier_seat]
    majority = [
        s for s in others
        if final_ballots.get(s.seat_no) is not None
        and final_ballots[s.seat_no].choice == chosen
    ]
    pool = majority if majority else others
    pool = sorted(pool, key=lambda s: (-s.q, s.seat_no))
    return [s.seat_no for s in pool[:n]]
