"""Lineup scoring (spec 9.5). Pure: no I/O, no globals."""

from __future__ import annotations

import itertools
import math
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional

from council.core.schemas import LineupScore


@dataclass
class ScoringContext:
    q: dict[str, float]
    distance: Callable[[str, str], float]
    weights: dict[str, float]
    tier: str = "A"
    neighbours: Optional[list[dict]] = None
    resident: set[str] = field(default_factory=set)
    load_s: dict[str, float] = field(default_factory=dict)
    deadline_s: float = 300
    recent: list[list[str]] = field(default_factory=list)


def _vote_credit(models: list[str], nb: dict) -> float:
    answers = nb.get("answers", {})
    counts = Counter(answers[m] for m in models if m in answers)
    if not counts:
        return 0.0
    top = max(counts.values())
    tied = [a for a, c in counts.items() if c == top]
    return 1.0 / len(tied) if nb.get("truth") in tied else 0.0


def score_lineup(models: list[str], ctx: ScoringContext) -> LineupScore:
    n = len(models)
    if n == 0:
        return LineupScore()
    merit = sum(ctx.q.get(m, 0.0) for m in models) / n

    vote = cover = 0.0
    nbs = ctx.neighbours
    if ctx.tier != "A" and nbs:
        total_w = sum(nb.get("weight", 0.0) for nb in nbs)
        if total_w > 0:
            vote = sum(nb.get("weight", 0.0) * _vote_credit(models, nb) for nb in nbs) / total_w
            cover = sum(
                nb.get("weight", 0.0)
                for nb in nbs
                if any(nb.get("answers", {}).get(m) == nb.get("truth") and m in nb.get("answers", {}) for m in models)
            ) / total_w

    pairs = list(itertools.combinations(models, 2))
    div = sum(ctx.distance(a, b) for a, b in pairs) / len(pairs) if pairs else 0.0

    load = min(1.0, sum(ctx.load_s.get(m, 0.0) for m in models if m not in ctx.resident) / ctx.deadline_s) if ctx.deadline_s > 0 else 1.0
    load = max(0.0, load)

    last = ctx.recent[-5:]
    mset = set(models)
    repeat = sum(len(mset & set(r)) / n for r in last) / len(last) if last else 0.0

    w = ctx.weights
    total = (
        w.get("merit", 0.0) * merit
        + w.get("vote", 0.0) * vote
        + w.get("cover", 0.0) * cover
        + w.get("div", 0.0) * div
        - w.get("load", 0.0) * load
        - w.get("repeat", 0.0) * repeat
    )
    return LineupScore(merit=merit, vote=vote, cover=cover, div=div, load=load, repeat=repeat, total=total)


def softmax_sample(
    scored: list[tuple[list[str], float]], tau: float, top_n: int, rng: random.Random
) -> list[str]:
    if not scored:
        raise ValueError("no lineups to sample")
    top = sorted(scored, key=lambda t: t[1], reverse=True)[: max(1, top_n)]
    best = top[0][1]
    if tau <= 0:
        return list(top[0][0])
    weights = [math.exp((s - best) / tau) for _, s in top]
    pick = rng.choices(range(len(top)), weights=weights, k=1)[0]
    return list(top[pick][0])
