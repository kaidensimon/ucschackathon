"""Plain-sentence explanations for lie flags and probe cards.

Pure module: no I/O, no clock, no randomness. Takes LieFlag and ProbeCard from
the shared 1.5 contract and returns English text for the user.
"""

from __future__ import annotations

import math

from council.core.schemas_v15 import LieFlag, ProbeCard

_CAVEAT = (
    "This reads a statistical pattern in activations, trained on simple true/false "
    "statements; it is advisory, can be wrong, and is not proof of intent."
)


def _clamp01(x: float) -> float:
    return min(max(float(x), 0.0), 1.0)


def _pct(x: float) -> int:
    """0..1 score to a whole percent, halves rounded up. Out-of-range values are clamped."""
    return int(math.floor(_clamp01(x) * 100 + 0.5))


def _score(x: float) -> str:
    """0..1 score to two decimals, clamped."""
    return f"{_clamp01(x):.2f}"


def _subject(flag: LieFlag) -> str:
    return f"Seat {flag.seat_no}" if flag.seat_no > 0 else "This seat"


def explain_flag(flag: LieFlag) -> str:
    """One plain sentence on what the engine saw for one claim.

    Covers every combination of present and missing probe_score, stated_confidence
    and behaviour_score.
    """
    subj = _subject(flag)
    p = flag.probe_score
    s = flag.stated_confidence
    b = flag.behaviour_score

    if p is not None:
        if s is not None:
            lead = (
                f"{subj} said it was {_pct(s)}% sure, but its own activations "
                f"read this claim as {_pct(p)}% likely true"
            )
        else:
            lead = f"{subj}'s own activations read this claim as {_pct(p)}% likely true"
    else:
        if s is not None:
            lead = f"{subj} said it was {_pct(s)}% sure, but there is no probe for this model"
        else:
            lead = "No probe for this model"

    if b is not None:
        tail = f"; behaviour signals read {_score(b)}"
    elif p is None:
        tail = " and no behaviour signals"
    else:
        tail = ""

    return lead + tail + "."


def explain_card(card: ProbeCard) -> str:
    """One sentence on a trained probe: its score, its control, and whether it is active."""
    head = f"Probe v{card.version} for {card.model_id}: "

    if card.auroc is not None:
        body = f"{_score(card.auroc)} AUROC"
        if card.n_test > 0:
            body += f" on {card.n_test} held-out statements"
    else:
        body = "no AUROC recorded"

    if card.control_auroc is not None:
        body += f" (shuffled-label control {_score(card.control_auroc)})"

    if card.active:
        status = "Active."
    else:
        reason = card.reason.strip().rstrip(".").strip()
        status = f"Not active: {reason}." if reason else "Not active."

    return f"{head}{body}. {status}"


def caveat() -> str:
    """Fixed caveat shown next to any lie or probe output."""
    return _CAVEAT


__all__ = ["explain_flag", "explain_card", "caveat"]
