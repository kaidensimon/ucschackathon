"""Lens assignment (spec 10.2).

A lens is a stance added to a seat's system prompt. Every lineup with at least
3 seats carries all REQUIRED lenses. The highest-q seat gets "specialist" when
there are at least 4 seats. The rest are dealt round-robin from a seed offset.
Deterministic: same inputs, same output.
"""

from __future__ import annotations

from council.core.schemas import LENSES

REQUIRED: tuple[str, ...] = ("builder", "skeptic", "first_principles")
SPECIALIST: str = "specialist"
# Lenses dealt to the non-specialist seats, in table order.
_DEALT: tuple[str, ...] = tuple(lens for lens in LENSES if lens != SPECIALIST)
_OPTIONAL: tuple[str, ...] = tuple(lens for lens in _DEALT if lens not in REQUIRED)
SPECIALIST_MIN_SEATS = 4
REQUIRED_MIN_SEATS = 3


def _deal_order(seed: int) -> list[str]:
    """Required lenses first (rotated by seed), then the optional ones (rotated by seed).

    Putting the required lenses at the front guarantees they are dealt first,
    so any lineup of 3 or more seats carries all of them.
    """
    req = list(REQUIRED)
    r = seed % len(req)
    req = req[r:] + req[:r]
    opt = list(_OPTIONAL)
    o = seed % len(opt)
    opt = opt[o:] + opt[:o]
    return req + opt


def assign_lenses(seat_models: list[str], q: dict[str, float], seed: int) -> dict[str, str]:
    """Map each seat's model_id to a lens.

    seat_models: model ids in seat order. Ties on q go to the earlier seat.
    q: model_id -> competence estimate (missing ids count as 0.0).
    seed: per-run offset. Any int is accepted; negative values are reduced modulo.
    Returns {model_id: lens}. Empty input gives {}.
    """
    n = len(seat_models)
    if n == 0:
        return {}

    specialist_idx: int | None = None
    if n >= SPECIALIST_MIN_SEATS:
        best = None
        for i, model_id in enumerate(seat_models):
            score = q.get(model_id, 0.0)
            if best is None or score > best:  # strict: earlier seat wins ties
                best = score
                specialist_idx = i

    order = _deal_order(seed)
    out: dict[str, str] = {}
    dealt = 0
    for i, model_id in enumerate(seat_models):
        if i == specialist_idx:
            out[model_id] = SPECIALIST
            continue
        out[model_id] = order[dealt % len(order)]
        dealt += 1
    return out
