"""Probe calibration: Platt scaling and score quality metrics. Pure python, no I/O, no clock, no randomness."""

from __future__ import annotations

import math
from typing import Optional, Sequence

L2 = 1e-3


def _sigmoid(z: float) -> float:
    """Overflow-safe logistic function."""
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _check(a: Sequence, b: Sequence) -> None:
    if len(a) != len(b):
        raise ValueError(f"length mismatch: {len(a)} vs {len(b)}")


def fit_platt(
    scores: list[float], labels: list[int], iters: int = 200, lr: float = 0.1
) -> tuple[float, float]:
    """Fit p = sigmoid(a*s + b) by gradient descent on log loss with L2 on a.

    One-class or empty input returns the identity (1.0, 0.0).
    """
    _check(scores, labels)
    n = len(scores)
    if n == 0 or len(set(1 if y else 0 for y in labels)) < 2:
        return (1.0, 0.0)
    ys = [1 if y else 0 for y in labels]
    a, b = 1.0, 0.0
    for _ in range(max(0, iters)):
        ga = 0.0
        gb = 0.0
        for s, y in zip(scores, ys):
            err = _sigmoid(a * s + b) - y
            ga += err * s
            gb += err
        ga = ga / n + L2 * a
        gb = gb / n + L2 * b
        a -= lr * ga
        b -= lr * gb
    return (a, b)


def apply_platt(score: float, ab: tuple[float, float]) -> float:
    a, b = ab
    return _sigmoid(a * score + b)


def _bin_index(p: float, bins: int) -> int:
    i = int(p * bins)
    return min(max(i, 0), bins - 1)


def reliability_table(
    probs: list[float], labels: list[int], bins: int = 10
) -> list[dict]:
    """One row per bin: lo, hi, n, mean_p, frac_true. Empty bins have n=0 and None means."""
    _check(probs, labels)
    bins = max(1, int(bins))
    counts = [0] * bins
    sum_p = [0.0] * bins
    sum_y = [0.0] * bins
    for p, y in zip(probs, labels):
        i = _bin_index(p, bins)
        counts[i] += 1
        sum_p[i] += p
        sum_y[i] += 1 if y else 0
    rows: list[dict] = []
    for i in range(bins):
        n = counts[i]
        rows.append(
            {
                "lo": i / bins,
                "hi": (i + 1) / bins,
                "n": n,
                "mean_p": sum_p[i] / n if n else None,
                "frac_true": sum_y[i] / n if n else None,
            }
        )
    return rows


def ece(probs: list[float], labels: list[int], bins: int = 10) -> float:
    """Expected calibration error: bin-weighted mean |mean_p - frac_true|. Empty input gives 0.0."""
    total = len(probs)
    if total == 0:
        _check(probs, labels)
        return 0.0
    err = 0.0
    for row in reliability_table(probs, labels, bins):
        if row["n"]:
            err += row["n"] / total * abs(row["mean_p"] - row["frac_true"])
    return err


def brier(probs: list[float], labels: list[int]) -> float:
    """Mean squared error of probabilities against 0/1 labels. Empty input gives 0.0."""
    _check(probs, labels)
    if not probs:
        return 0.0
    return sum((p - (1 if y else 0)) ** 2 for p, y in zip(probs, labels)) / len(probs)


def auroc(scores: list[float], labels: list[int]) -> Optional[float]:
    """Rank-based AUROC (Mann-Whitney U), ties get the average rank. None when only one class."""
    _check(scores, labels)
    n = len(scores)
    n_pos = sum(1 for y in labels if y)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    order = sorted(range(n), key=lambda i: scores[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # ranks are 1-based
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    rank_sum_pos = sum(ranks[k] for k in range(n) if labels[k])
    u = rank_sum_pos - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


__all__ = ["fit_platt", "apply_platt", "ece", "brier", "auroc", "reliability_table"]
