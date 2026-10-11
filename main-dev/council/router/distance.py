"""Pairwise model distance for lineup scoring (ARCHITECTURE.md 9.5). No logic beyond the spec."""

from __future__ import annotations

import math
from itertools import combinations

from council.core.schemas import ModelEntry


def lineage_distance(a: ModelEntry, b: ModelEntry) -> float:
    """1.0 different lab, 0.6 same lab different lineage, 0.3 same lineage different id, 0.0 same id."""
    if a.id == b.id:
        return 0.0
    if a.lab != b.lab:
        return 1.0
    if a.lineage and a.lineage == b.lineage:
        return 0.3
    return 0.6


def error_distance(vec_a: list[bool], vec_b: list[bool]) -> float:
    """(1 - Pearson correlation of wrong-indicator vectors) / 2. 0.5 if constant, empty, or mismatched."""
    n = len(vec_a)
    if n == 0 or n != len(vec_b):
        return 0.5
    xs = [1.0 if v else 0.0 for v in vec_a]
    ys = [1.0 if v else 0.0 for v in vec_b]
    mx = sum(xs) / n
    my = sum(ys) / n
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    sxx = sum(d * d for d in dx)
    syy = sum(d * d for d in dy)
    if sxx == 0.0 or syy == 0.0:
        return 0.5
    sxy = sum(p * q for p, q in zip(dx, dy))
    r = sxy / math.sqrt(sxx * syy)
    r = max(-1.0, min(1.0, r))
    return (1.0 - r) / 2.0


def _lookup_err(a: ModelEntry, b: ModelEntry, err: dict[tuple[str, str], float] | None) -> float | None:
    if not err:
        return None
    if (a.id, b.id) in err:
        return err[(a.id, b.id)]
    if (b.id, a.id) in err:
        return err[(b.id, a.id)]
    return None


def pair_distance(
    a: ModelEntry,
    b: ModelEntry,
    tier: str,
    err: dict[tuple[str, str], float] | None,
) -> float:
    """Tier A: lineage only. Tier B: 0.5 lineage + 0.5 error; lineage alone when no error data."""
    if tier == "A":
        return lineage_distance(a, b)
    if tier == "B":
        e = _lookup_err(a, b, err)
        if e is None:
            return lineage_distance(a, b)
        return 0.5 * lineage_distance(a, b) + 0.5 * e
    raise ValueError(f"unknown tier: {tier!r}")


def mean_pairwise(
    models: list[ModelEntry],
    tier: str,
    err: dict[tuple[str, str], float] | None = None,
) -> float:
    """Mean of pair_distance over all unordered pairs. 0.0 for fewer than 2 models."""
    if len(models) < 2:
        return 0.0
    pairs = list(combinations(models, 2))
    total = sum(pair_distance(a, b, tier, err) for a, b in pairs)
    return total / len(pairs)
