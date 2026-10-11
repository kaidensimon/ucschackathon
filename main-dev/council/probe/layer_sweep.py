"""Layer sweep. Pick which layers of a model carry the true/false signal.

Pure python. No I/O, no clock. Randomness only from the injected seed.
"""
from __future__ import annotations

import random


def _auroc(scores: list[float], labels: list[int]) -> float:
    """Rank-based AUROC, average ranks for ties. 0.5 if one class is missing."""
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


def _split_indices(n: int, groups: list[str] | None, seed: int,
                   test_fraction: float = 0.3) -> tuple[list[int], list[int]]:
    """Return (train_idx, test_idx). A group is never on both sides."""
    rng = random.Random(seed)
    if groups is None:
        idx = list(range(n))
        rng.shuffle(idx)
        n_test = int(round(n * test_fraction))
        if n >= 2:
            n_test = min(max(n_test, 1), n - 1)
        return sorted(idx[n_test:]), sorted(idx[:n_test])
    members: dict[str, list[int]] = {}
    for i, g in enumerate(groups):
        members.setdefault(g, []).append(i)
    names = sorted(members)
    rng.shuffle(names)
    target = int(round(n * test_fraction))
    test: list[int] = []
    train: list[int] = []
    for k, g in enumerate(names):
        left = len(names) - k - 1  # groups still unassigned after this one
        if len(test) < target and (left > 0 or train):
            test.extend(members[g])
        else:
            train.extend(members[g])
    if not test and len(names) >= 2:  # keep both sides non-empty
        g = names[0]
        test = members[g]
        train = [i for i in range(n) if i not in set(test)]
    return sorted(train), sorted(test)


def layer_scores(acts: dict[int, list[list[float]]], labels: list[int],
                 groups: list[str] | None = None, seed: int = 0) -> dict[int, float]:
    """Held-out AUROC of a difference-of-means direction, per layer.

    Direction = mean(true rows) - mean(false rows) on the train side.
    Score = AUROC of the projection on the test side. 0.5 means no signal.
    """
    n = len(labels)
    if groups is not None and len(groups) != n:
        raise ValueError("groups and labels differ in length")
    train, test = _split_indices(n, groups, seed)
    out: dict[int, float] = {}
    for layer, rows in acts.items():
        if len(rows) != n:
            raise ValueError(f"layer {layer}: {len(rows)} rows, {n} labels")
        pos = [rows[i] for i in train if labels[i] == 1]
        neg = [rows[i] for i in train if labels[i] != 1]
        if not pos or not neg or not test:
            out[layer] = 0.5
            continue
        d = len(rows[0])
        direction = [sum(r[j] for r in pos) / len(pos) - sum(r[j] for r in neg) / len(neg)
                     for j in range(d)]
        proj = [sum(a * b for a, b in zip(rows[i], direction)) for i in test]
        out[layer] = _auroc(proj, [1 if labels[i] == 1 else 0 for i in test])
    return out


def pick_layers(scores: dict[int, float], k: int = 4, min_gap: int = 2) -> list[int]:
    """Best k layers by score. No two closer than min_gap when possible. Ascending."""
    if k <= 0:
        return []
    ranked = sorted(scores, key=lambda l: (-scores[l], l))
    chosen: list[int] = []
    for l in ranked:
        if len(chosen) >= k:
            break
        if all(abs(l - c) >= min_gap for c in chosen):
            chosen.append(l)
    for l in ranked:  # gap rule left us short: fill with best remaining
        if len(chosen) >= k:
            break
        if l not in chosen:
            chosen.append(l)
    return sorted(chosen)


def candidate_layers(n_layer: int, n: int = 12) -> list[int]:
    """Layers evenly spread over the middle 20%..90% of depth. Unique, sorted."""
    if n_layer <= 0 or n <= 0:
        return []
    top = n_layer - 1
    lo = int(round(0.2 * top))
    hi = int(round(0.9 * top))
    if n == 1:
        return [(lo + hi) // 2]
    step = (hi - lo) / (n - 1)
    return sorted({int(round(lo + step * i)) for i in range(n)})


def sweep_text(scores: dict[int, float]) -> str:
    """Small table for the terminal."""
    if not scores:
        return "layer  auroc\n(no layers)"
    best = max(scores.values())
    lines = ["layer  auroc  bar"]
    for l in sorted(scores):
        s = scores[l]
        bar = "#" * int(round(max(0.0, min(1.0, s)) * 20))
        mark = " <- best" if s == best else ""
        lines.append(f"{l:>5}  {s:.3f}  {bar}{mark}")
    return "\n".join(lines)
