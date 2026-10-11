"""Adaptive effort: scale rounds, deadline and reasoning to the task (like adaptive thinking).

Pure: no I/O, no clock, no randomness. The deadline comes from measured seat speed.
"""

from __future__ import annotations

from typing import get_args

from council.chamber import budget
from council.core.config import ChamberConfig
from council.core.schemas import EffortPlan, ModeConfig, ReasoningLevel, TaskProfile

_BALLOT_ROUND = "r2"
_EXTRA_ROUND = "r3"
_DEFAULT_SEATS = 6


def _level(profile: TaskProfile) -> str:
    contested = profile.contested is True
    if profile.difficulty == "hard" or contested:
        level = "heavy"
    elif profile.difficulty == "easy":
        level = "light"
    else:
        level = "normal"
    if level == "light" and profile.deliverable in ("build", "plan"):
        level = "normal"
    return level


def _light_rounds(rounds: list[str]) -> list[str]:
    if _BALLOT_ROUND in rounds:
        return list(rounds[: rounds.index(_BALLOT_ROUND) + 1])
    return list(rounds)


def _round_wall_s(round_name: str, seat_tps: list[float], reasoning: str) -> float:
    """Wall seconds for one round with all seats running at once on one GPU.

    budget.estimate_round_s sums the seats and divides by min(concurrent, 2). For equal
    seats that matches, but with mixed speeds it uses the MEAN seat, so it is too optimistic:
    a round ends when the SLOWEST seat ends. Each of N concurrent models runs at about
    tps / (N * 0.5) (see budget.turn_timeout_s), so the slowest takes
    tokens * N * 0.5 / min_tps. Use the larger of the two estimates.
    """
    n = len(seat_tps)
    base = budget.estimate_round_s(round_name, seat_tps, reasoning, concurrent=n)  # type: ignore[arg-type]
    tokens = budget.turn_tokens(round_name, reasoning)
    slowest = max(min(float(t) for t in seat_tps), 1.0)
    shared = tokens * max(1.0, n * 0.5) / slowest
    return max(base, shared)


def _deadline_s(
    rounds: list[str], extra: int, reasoning: str, seat_tps: list[float], chamber: ChamberConfig
) -> float:
    tps = [float(t) for t in seat_tps if t is not None and float(t) > 0]
    if not tps:
        tps = [budget.DEFAULT_TPS] * _DEFAULT_SEATS
    all_rounds = [r for r in rounds if r in budget.TURN_CAPS]
    all_rounds += [_EXTRA_ROUND] * max(0, extra)
    total = sum(_round_wall_s(r, tps, reasoning) for r in all_rounds)
    deadline = total * chamber.deadline_slack + budget.chair_reserve_s(max(tps), reasoning, total)
    return float(max(chamber.min_deadline_s, min(chamber.max_deadline_s, deadline)))


def plan_effort(
    profile: TaskProfile,
    mode: ModeConfig,
    mode_name: str,
    seat_tps: list[float],
    chamber: ChamberConfig,
) -> EffortPlan:
    """Choose rounds, deadline and reasoning for this task. Only "standard" mode adapts."""
    if mode_name != "standard" or not chamber.adaptive:
        return EffortPlan(
            level="normal",
            rounds=list(mode.rounds),
            deadline_s=mode.deadline_s,
            reasoning=mode.reasoning,
            max_extra_rounds=0,
            rationale="fixed mode",
        )

    level = _level(profile)
    if level == "light":
        rounds = _light_rounds(mode.rounds)
        reasoning: ReasoningLevel = "off"
        extra = min(1, chamber.max_extra_rounds)
    elif level == "heavy":
        rounds = list(mode.rounds)
        if _EXTRA_ROUND not in rounds:
            rounds.append(_EXTRA_ROUND)
        reasoning = "max" if "max" in get_args(ReasoningLevel) else mode.reasoning
        extra = chamber.max_extra_rounds
    else:
        rounds = list(mode.rounds)
        reasoning = mode.reasoning
        extra = min(1, chamber.max_extra_rounds)
    extra = max(0, extra)

    deadline = _deadline_s(rounds, extra, reasoning, seat_tps, chamber)
    flags = [profile.difficulty]
    if profile.contested is True:
        flags.append("contested")
    if profile.deliverable != "answer":
        flags.append(profile.deliverable)
    rationale = f"{', '.join(flags)}: {len(rounds)} rounds, reasoning {reasoning}, {round(deadline)} s"
    return EffortPlan(
        level=level,  # type: ignore[arg-type]
        rounds=rounds,
        deadline_s=deadline,
        reasoning=reasoning,
        max_extra_rounds=extra,
        rationale=rationale,
    )


def apply_effort(mode: ModeConfig, plan: EffortPlan) -> ModeConfig:
    """Copy of the mode with the plan's rounds, deadline and reasoning."""
    return mode.model_copy(
        update={
            "rounds": list(plan.rounds),
            "deadline_s": plan.deadline_s,
            "reasoning": plan.reasoning,
        },
        deep=True,
    )


__all__ = ["plan_effort", "apply_effort"]
