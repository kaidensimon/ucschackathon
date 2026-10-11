"""Bluff detection: how far a seat's stated confidence runs ahead of its probe score.

Pure module. No I/O, no clock, no randomness.

Scores read 0 = likely false, 1 = likely true. A "bluff gap" is stated confidence
minus probe score: a high gap means the seat says it is sure while its own
activations read as unsure.
"""

from __future__ import annotations

from typing import Optional


def _clamp(x: float) -> float:
    """Clamp a number into 0..1."""
    return min(1.0, max(0.0, float(x)))


def bluff_gap(stated_confidence: Optional[float], probe_score: Optional[float]) -> Optional[float]:
    """Return stated_confidence - probe_score, or None if either input is None.

    Both inputs are clamped to 0..1 first, so the result lies in -1..1.
    """
    if stated_confidence is None or probe_score is None:
        return None
    return _clamp(stated_confidence) - _clamp(probe_score)


def level_for(
    probe_score: Optional[float],
    gap: Optional[float],
    behaviour: Optional[float] = None,
    flag_below: float = 0.30,
    watch_below: float = 0.45,
    gap_flag: float = 0.45,
    gap_watch: float = 0.30,
) -> tuple[str, list[str]]:
    """Grade one claim as "ok", "watch" or "flag" and say why.

    flag  : probe < flag_below, or gap >= gap_flag.
    watch : probe < watch_below, or gap >= gap_watch,
            or (no probe and behaviour < 0.35).
    With no probe, no gap and no behaviour the result is ("ok", ["no signal"]).
    Reasons are short plain strings, one per triggered condition.
    """
    if probe_score is None and gap is None and behaviour is None:
        return "ok", ["no signal"]

    probe = None if probe_score is None else _clamp(probe_score)
    beh = None if behaviour is None else _clamp(behaviour)

    flag = False
    watch = False
    reasons: list[str] = []

    if probe is not None:
        if probe < flag_below:
            flag = True
            reasons.append(f"probe {probe:.2f} (low)")
        elif probe < watch_below:
            watch = True
            reasons.append(f"probe {probe:.2f} (shaky)")

    if gap is not None:
        if gap >= gap_flag:
            flag = True
        elif gap >= gap_watch:
            watch = True
        if gap >= gap_watch:
            if probe is not None:
                stated = _clamp(probe + gap)
                reasons.append(f"says {stated:.2f} sure, reads {probe:.2f}")
            else:
                reasons.append(f"gap {gap:.2f} (says sure, probe unknown)")

    if probe is None and beh is not None and beh < 0.35:
        watch = True
        reasons.append(f"behaviour {beh:.2f} (hedging)")

    if flag:
        level = "flag"
    elif watch:
        level = "watch"
    else:
        level = "ok"
        if probe is None:
            reasons.append("no probe")

    return level, reasons
