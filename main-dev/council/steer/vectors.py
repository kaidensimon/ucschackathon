"""Steering-vector math. Pure python: no I/O, no clock, no randomness.

A steering vector for one layer is mean(activations of positive prompts) minus mean(activations
of negative prompts). It is then scaled to a small fraction of the layer's hidden-state size,
because the usable strength range is narrow (proven on the box by tools/box/steer_test.py).

Every function takes `{layer: vector}` rows (one dict per prompt) or `{layer: vector}` directions.
"""
from __future__ import annotations

import math

__all__ = ["mean_diff", "norm", "scale_to_fraction", "hidden_norms", "pick_layers", "separation"]

Rows = list[dict[int, list[float]]]
Direction = dict[int, list[float]]


def norm(v) -> float:
    """Euclidean length of a vector."""
    return math.sqrt(sum(x * x for x in v))


def _column(rows: Rows, layer: int) -> list[list[float]]:
    """The vectors of one layer, from the rows that have it."""
    return [r[layer] for r in rows if layer in r]


def _mean(vectors: list[list[float]]) -> list[float]:
    dim = len(vectors[0])
    if any(len(v) != dim for v in vectors):
        raise ValueError("vectors of one layer have different sizes")
    n = len(vectors)
    return [sum(col) / n for col in zip(*vectors)]


def mean_diff(pos: Rows, neg: Rows) -> Direction:
    """Per layer: mean(pos) - mean(neg). A layer missing on either side is dropped."""
    out: Direction = {}
    layers = {k for r in pos for k in r} & {k for r in neg for k in r}
    for layer in sorted(layers):
        mp, mn = _mean(_column(pos, layer)), _mean(_column(neg, layer))
        if len(mp) != len(mn):
            raise ValueError(f"layer {layer}: pos and neg vectors have different sizes")
        out[layer] = [a - b for a, b in zip(mp, mn)]
    return out


def hidden_norms(rows: Rows) -> dict[int, float]:
    """Mean vector norm per layer, over the rows that have the layer."""
    out: dict[int, float] = {}
    for layer in sorted({k for r in rows for k in r}):
        col = _column(rows, layer)
        out[layer] = sum(norm(v) for v in col) / len(col)
    return out


def scale_to_fraction(direction: Direction, hidden_norm: dict[int, float],
                      fraction: float = 0.06) -> Direction:
    """Rescale each layer vector so |v| = fraction * hidden_norm[layer].

    A layer with no hidden norm is dropped. A zero vector stays zero.
    """
    if fraction < 0:
        raise ValueError("fraction must not be negative")
    out: Direction = {}
    for layer, v in direction.items():
        if layer not in hidden_norm:
            continue
        n = norm(v)
        if n == 0.0:
            out[layer] = [0.0] * len(v)
            continue
        k = fraction * hidden_norm[layer] / n
        out[layer] = [x * k for x in v]
    return out


def pick_layers(n_layer: int, spec: str = "auto") -> list[int]:
    """Layers that get the vector.

    "auto": the middle band from 35% to 65% of depth, inclusive (40 layers -> 14..26).
    "a-b": explicit range, inclusive. A bare "a" is one layer.
    The result is clipped to 1..n_layer-1.
    """
    s = str(spec).strip().lower()
    if s in ("", "auto"):
        lo, hi = -(-35 * n_layer // 100), 65 * n_layer // 100  # integer ceil / floor: no float edge
    else:
        a, sep, b = s.partition("-")
        try:
            lo = int(a)
            hi = int(b) if sep else lo
        except ValueError:
            raise ValueError(f"bad layer spec {spec!r}: want 'auto' or 'a-b'") from None
        if lo > hi:
            raise ValueError(f"bad layer spec {spec!r}: start after end")
    return list(range(max(lo, 1), min(hi, n_layer - 1) + 1))


def separation(pos: Rows, neg: Rows, direction: Direction) -> dict[int, float]:
    """Per layer: how well the direction splits pos from neg.

    Project every row on the direction. The midpoint is halfway between the pos mean and the neg
    mean projection. Score = (share of pos above the midpoint + share of neg below it) / 2.
    0.5 = no signal, 1.0 = clean. A zero direction scores 0.5. A layer with no rows on one side
    is dropped.
    """
    out: dict[int, float] = {}
    for layer, d in direction.items():
        cp, cn = _column(pos, layer), _column(neg, layer)
        if not cp or not cn:
            continue
        n = norm(d)
        if n == 0.0:
            out[layer] = 0.5
            continue
        pp = [sum(x * y for x, y in zip(v, d)) / n for v in cp]
        pn = [sum(x * y for x, y in zip(v, d)) / n for v in cn]
        mid = (sum(pp) / len(pp) + sum(pn) / len(pn)) / 2
        up = sum(1 for p in pp if p > mid) / len(pp)
        down = sum(1 for p in pn if p < mid) / len(pn)
        out[layer] = (up + down) / 2
    return out
