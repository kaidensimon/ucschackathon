"""Per-turn token caps and round time budget (spec 10.9, 10.10)."""

from __future__ import annotations

from typing import Dict, List, Optional, TypedDict

from council.core.schemas import ReasoningLevel


class TurnCap(TypedDict):
    max_output: int
    max_reasoning: int
    temperature: Optional[float]


# Spec 10.9, standard mode. r0 temperature None means model default.
TURN_CAPS: Dict[str, TurnCap] = {
    "r0": {"max_output": 700, "max_reasoning": 1500, "temperature": None},
    "r1": {"max_output": 500, "max_reasoning": 800, "temperature": 0.4},
    "r2": {"max_output": 400, "max_reasoning": 600, "temperature": 0.3},
    "r3": {"max_output": 350, "max_reasoning": 400, "temperature": 0.3},
    "chair": {"max_output": 900, "max_reasoning": 1500, "temperature": 0.2},
    "ratify": {"max_output": 60, "max_reasoning": 0, "temperature": 0.0},
    "clerk": {"max_output": 400, "max_reasoning": 0, "temperature": 0.0},
}


def estimate_round_s(
    round_name: str,
    seat_tps: List[float],
    reasoning: ReasoningLevel,
    concurrent: int = 1,
) -> float:
    """Estimated wall seconds for one round, using caps from TURN_CAPS."""
    cap = TURN_CAPS[round_name]
    tokens_per_seat = cap["max_output"]
    if reasoning != "off":
        tokens_per_seat += cap["max_reasoning"]
    total = 0.0
    for tps in seat_tps:
        total += tokens_per_seat / max(float(tps), 1.0)
    return total / max(min(concurrent, 2), 1)


def can_start_round(
    round_name: str,
    seat_tps: List[float],
    reasoning: ReasoningLevel,
    remaining_s: float,
    concurrent: int = 1,
) -> bool:
    """True when the estimated round cost fits in the time left."""
    return estimate_round_s(round_name, seat_tps, reasoning, concurrent) <= remaining_s


DEFAULT_TPS = 15.0  # assumed speed of a model whose speed is not known
MIN_TURN_S = 45.0  # a turn is never given less than this, whatever time is left
CHAIR_RESERVE_SHARE = 0.4  # the Chair reserve is at most this share of the run deadline


def turn_tokens(round_name: str, reasoning: str) -> int:
    """Most tokens one turn of this round can generate (reasoning tokens only when it is on)."""
    cap = TURN_CAPS[round_name]
    tokens = cap["max_output"]
    if reasoning != "off":
        tokens += cap["max_reasoning"]
    return int(tokens)


def turn_timeout_s(
    round_name: str,
    tps: Optional[float],
    reasoning: str,
    concurrent: int,
    remaining_s: Optional[float],
    floor_s: float = 60,
    slack: float = 2.5,
    *,
    tokens: Optional[int] = None,
) -> float:
    """Wall seconds one turn may take before it is cut off.

    slack * tokens / (tps / max(1, concurrent * 0.5)), at least floor_s. `tps` is the model's
    speed alone (DEFAULT_TPS when unknown); `concurrent` models share one GPU. When
    `remaining_s` is given the result is capped by it, but never below MIN_TURN_S.
    `tokens` replaces the TURN_CAPS lookup (calls that are not in the table).
    """
    if tokens is None:
        tokens = turn_tokens(round_name, reasoning)
    speed = float(tps) if tps is not None and float(tps) > 0 else DEFAULT_TPS
    speed = speed / max(1.0, float(concurrent) * 0.5)
    out = max(float(floor_s), float(slack) * float(tokens) / speed)
    if remaining_s is not None:
        out = max(MIN_TURN_S, min(out, float(remaining_s)))
    return out


def chair_reserve_s(tps: Optional[float], reasoning: str, deadline_s: float) -> float:
    """Seconds of the run deadline kept back for the Chair.

    The Chair's own turn timeout (it generates alone), at most CHAIR_RESERVE_SHARE of the
    deadline so that the debate always keeps the larger part.
    """
    want = turn_timeout_s("chair", tps, reasoning, 1, None)
    return max(0.0, min(want, CHAIR_RESERVE_SHARE * max(0.0, float(deadline_s))))


def turn_timeout(cap_s: float, remaining_s: float) -> float:
    """Smaller of the turn's own cap and time left, floor 1 second."""
    return max(1.0, min(cap_s, remaining_s))
