"""Router competence estimate (spec 9.3, 9.4, 9.7).

SkillTable holds Beta(alpha, beta) per (model_id, category). Prior mean comes from the
registry priors, worth `prior_strength` pseudo-observations.
"""

from __future__ import annotations

import math

from council.core.schemas import TaskProfile

DEFAULT_PRIOR = 0.5


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


class SkillTable:
    def __init__(
        self,
        priors: dict[str, dict[str, float]],
        prior_strength: float = 4.0,
        stats: dict[tuple[str, str], tuple[float, float]] | None = None,
    ) -> None:
        self.priors = {m: dict(c) for m, c in (priors or {}).items()}
        self.prior_strength = float(prior_strength)
        # (model_id, category) -> (alpha, beta), full posterior parameters.
        self.stats: dict[tuple[str, str], tuple[float, float]] = dict(stats or {})

    def _prior_mean(self, model_id: str, category: str) -> float:
        p = self.priors.get(model_id, {}).get(category, DEFAULT_PRIOR)
        return _clamp01(p)

    def _ab(self, model_id: str, category: str) -> tuple[float, float]:
        key = (model_id, category)
        if key in self.stats:
            return self.stats[key]
        p = self._prior_mean(model_id, category)
        return p * self.prior_strength, (1.0 - p) * self.prior_strength

    def mean(self, model_id: str, category: str) -> float:
        a, b = self._ab(model_id, category)
        total = a + b
        if total <= 0:
            return self._prior_mean(model_id, category)
        return a / total

    def update(self, model_id: str, category: str, reward: float, weight: float = 1.0) -> None:
        a, b = self._ab(model_id, category)
        r = _clamp01(reward)
        self.stats[(model_id, category)] = (a + weight * r, b + weight * (1.0 - r))

    def trials(self, model_id: str, category: str) -> float:
        """Observations beyond the prior."""
        a, b = self._ab(model_id, category)
        return max(0.0, a + b - self.prior_strength)

    def export(self) -> dict:
        return {
            "prior_strength": self.prior_strength,
            "priors": {m: dict(c) for m, c in self.priors.items()},
            "stats": [
                {"model_id": m, "category": c, "alpha": a, "beta": b}
                for (m, c), (a, b) in sorted(self.stats.items())
            ],
        }


def q_tier_a(model_id: str, profile: TaskProfile, table: SkillTable) -> float:
    """Sum of category weight * skill mean."""
    weights = {c: w for c, w in profile.categories.items() if w > 0}
    total = sum(weights.values())
    if total <= 0:
        return DEFAULT_PRIOR
    return sum(w * table.mean(model_id, c) for c, w in weights.items()) / total


def q_tier_b(q_a: float, neighbours: list[tuple[float, bool]], pseudo: float = 5.0) -> float:
    """Similarity-weighted correct fraction, shrunk toward q_a by `pseudo` pseudo-counts."""
    wsum = sum(max(0.0, s) for s, _ in neighbours)
    if wsum <= 0:
        return q_a
    correct = sum(max(0.0, s) for s, ok in neighbours if ok)
    return (correct + pseudo * q_a) / (wsum + pseudo)


def passes_floor(
    q: float,
    best_q: float,
    wildcard: bool,
    floor_delta: float = 0.10,
    wildcard_floor_delta: float = 0.20,
) -> bool:
    delta = wildcard_floor_delta if wildcard else floor_delta
    return q >= best_q - delta - 1e-12


def exploration_bonus(total_runs: int, model_runs: float) -> float:
    return math.sqrt(2.0 * math.log(max(total_runs, 1) + 1) / (model_runs + 1))
