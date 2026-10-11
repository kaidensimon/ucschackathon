"""Switch-on gate for a trained probe (1.5, lie detector). Pure: no I/O, no clock, no randomness.

A probe is active only when it clears every check below. The first failed check sets the reason.
  1. auroc known and >= min_auroc
  2. n_test >= min_test
  3. control_auroc (same probe on shuffled labels) known -> must be <= max_control, else it leaks
  4. baseline_auroc (surface features) known -> auroc must beat it by min_margin
"""
from __future__ import annotations

from typing import Any, Optional

from council.core.schemas_v15 import ProbeCard

# Float tolerance so that a margin of exactly min_margin is not lost to rounding.
_EPS = 1e-9


def decide_active(
    auroc: Optional[float],
    n_test: int,
    control_auroc: Optional[float],
    baseline_auroc: Optional[float],
    min_auroc: float = 0.80,
    min_test: int = 30,
    max_control: float = 0.62,
    min_margin: float = 0.03,
) -> tuple[bool, str]:
    """Return (active, reason). reason is short and says what decided it."""
    if auroc is None:
        return False, "no auroc yet"
    if auroc + _EPS < min_auroc:
        return False, f"auroc {auroc:.2f} below {min_auroc:.2f}"
    if n_test < min_test:
        return False, f"only {n_test} held-out, need {min_test}"
    if control_auroc is not None and control_auroc > max_control + _EPS:
        return False, "probe finds signal in shuffled labels: leak"
    if baseline_auroc is not None and auroc - baseline_auroc + _EPS < min_margin:
        return False, "no better than surface features"

    parts = [f"auroc {auroc:.2f} on {n_test} held-out"]
    parts.append(
        f"control {control_auroc:.2f}" if control_auroc is not None else "no control"
    )
    parts.append(
        f"baseline {baseline_auroc:.2f}" if baseline_auroc is not None else "no baseline"
    )
    return True, ", ".join(parts)


def card_with_gate(card: ProbeCard, **thresholds: Any) -> ProbeCard:
    """Return a copy of card with active and reason set by decide_active. The input is not changed."""
    active, reason = decide_active(
        card.auroc,
        card.n_test,
        card.control_auroc,
        card.baseline_auroc,
        **thresholds,
    )
    return card.model_copy(update={"active": active, "reason": reason})


__all__ = ["decide_active", "card_with_gate"]
