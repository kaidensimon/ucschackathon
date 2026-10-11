"""Pure-Python logistic regression for activation probes (ARCHITECTURE 28.4)."""
from __future__ import annotations

import math
import random


def standardize(X: list[list[float]]) -> tuple[list[list[float]], list[float], list[float]]:
    """Return (X2, means, stds). Zero-variance columns get std 1.0."""
    if not X:
        return [], [], []
    n = len(X)
    d = len(X[0])
    means = [sum(row[j] for row in X) / n for j in range(d)]
    stds = []
    for j in range(d):
        var = sum((row[j] - means[j]) ** 2 for row in X) / n
        s = math.sqrt(var)
        stds.append(s if s > 1e-12 else 1.0)
    X2 = [[(row[j] - means[j]) / stds[j] for j in range(d)] for row in X]
    return X2, means, stds


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def predict_proba(weights: list[float], bias: float, x: list[float]) -> float:
    z = bias + sum(w * v for w, v in zip(weights, x))
    return _sigmoid(z)


def train_logreg(
    X: list[list[float]],
    y: list[int],
    l2: float = 0.01,
    lr: float = 0.1,
    epochs: int = 200,
    seed: int = 0,
) -> tuple[list[float], float]:
    """Batch gradient descent with L2 on weights. Deterministic with seed."""
    if not X:
        return [], 0.0
    n = len(X)
    d = len(X[0])
    rng = random.Random(seed)
    weights = [rng.uniform(-0.01, 0.01) for _ in range(d)]
    bias = 0.0
    for _ in range(epochs):
        gw = [0.0] * d
        gb = 0.0
        for row, label in zip(X, y):
            err = predict_proba(weights, bias, row) - label
            gb += err
            for j in range(d):
                gw[j] += err * row[j]
        for j in range(d):
            weights[j] -= lr * (gw[j] / n + l2 * weights[j])
        bias -= lr * gb / n
    return weights, bias


def auroc(scores: list[float], labels: list[int]) -> float:
    """Rank-based AUROC with average ranks for ties. 0.5 if one class missing."""
    pos = sum(1 for l in labels if l == 1)
    neg = len(labels) - pos
    if pos == 0 or neg == 0:
        return 0.5
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    rank_sum = sum(r for r, l in zip(ranks, labels) if l == 1)
    return (rank_sum - pos * (pos + 1) / 2.0) / (pos * neg)


def split(X, y, test_fraction: float = 0.3, seed: int = 0):
    """Shuffle deterministically. Returns (X_train, y_train, X_test, y_test)."""
    n = len(X)
    idx = list(range(n))
    random.Random(seed).shuffle(idx)
    n_test = int(round(n * test_fraction))
    if n >= 2:
        n_test = min(max(n_test, 1), n - 1)
    test_idx = idx[:n_test]
    train_idx = idx[n_test:]
    return (
        [X[i] for i in train_idx],
        [y[i] for i in train_idx],
        [X[i] for i in test_idx],
        [y[i] for i in test_idx],
    )


def top_dimensions(weights: list[float], n: int = 10) -> list[tuple[int, float]]:
    """Dimensions with largest |weight|, as (index, weight)."""
    ranked = sorted(range(len(weights)), key=lambda i: (-abs(weights[i]), i))
    return [(i, weights[i]) for i in ranked[:n]]
