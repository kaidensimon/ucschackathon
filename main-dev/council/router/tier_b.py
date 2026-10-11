"""Tier B calibration index (spec 9.3, 9.5). Pure: reads a calibration matrix, no I/O."""

from __future__ import annotations

from council.core.schemas import CalibrationCell
from council.router.competence import q_tier_b
from council.router.distance import error_distance
from council.router.profiler import cosine


class CalibrationIndex:
    def __init__(
        self,
        matrix: dict[str, dict[str, CalibrationCell]],
        task_embeddings: dict[str, list[float]],
        truths: dict[str, str],
    ) -> None:
        self.matrix = matrix or {}
        self.task_embeddings = task_embeddings or {}
        self.truths = truths or {}

    @classmethod
    def from_store(cls, store, embeddings: dict[str, list[float]]) -> "CalibrationIndex":
        """Truth for a task is the answer key of any model that got it right."""
        matrix = store.calibration_matrix()
        truths: dict[str, str] = {}
        for task_id, row in matrix.items():
            for model_id in sorted(row):
                cell = row[model_id]
                if cell.correct and cell.answer_key is not None:
                    truths[task_id] = cell.answer_key
                    break
        return cls(matrix, dict(embeddings or {}), truths)

    def _usable_tasks(self) -> list[str]:
        return [t for t in self.matrix if t in self.task_embeddings]

    def ready(self, min_tasks: int = 20) -> bool:
        return len(self._usable_tasks()) >= min_tasks

    def _nearest(self, embedding: list[float], k: int) -> list[tuple[float, str]]:
        scored = [(max(0.0, cosine(embedding, self.task_embeddings[t])), t) for t in self._usable_tasks()]
        scored.sort(key=lambda p: (-p[0], p[1]))
        return scored[: max(0, k)]

    def neighbours(self, embedding: list[float], k: int = 30) -> list[dict]:
        near = self._nearest(embedding, k)
        total = sum(s for s, _ in near)
        out: list[dict] = []
        for s, t in near:
            answers = {
                m: c.answer_key
                for m, c in self.matrix[t].items()
                if c.answer_key is not None
            }
            out.append({
                "weight": (s / total) if total > 0 else 0.0,
                "truth": self.truths.get(t),
                "answers": answers,
            })
        return out

    def q_b(self, model_id: str, embedding: list[float], q_a: float, k: int = 30) -> float:
        pairs: list[tuple[float, bool]] = []
        for s, t in self._nearest(embedding, k):
            cell = self.matrix[t].get(model_id)
            if cell is not None:
                pairs.append((s, bool(cell.correct)))
        return q_tier_b(q_a, pairs)

    def error_distances(self, model_ids: list[str]) -> dict[tuple[str, str], float]:
        out: dict[tuple[str, str], float] = {}
        ids = list(model_ids)
        tasks = sorted(self.matrix)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                va: list[bool] = []
                vb: list[bool] = []
                for t in tasks:
                    row = self.matrix[t]
                    if a in row and b in row:
                        va.append(not row[a].correct)
                        vb.append(not row[b].correct)
                d = error_distance(va, vb)
                out[(a, b)] = d
                out[(b, a)] = d
        return out
