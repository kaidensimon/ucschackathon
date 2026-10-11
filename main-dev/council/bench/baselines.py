"""Solo baselines for the council comparison.

Pure: no I/O, no clock, no randomness. Every function takes SoloScore rows
(from council.core.schemas_v15) and returns plain values.

Duplicate rows: a (task_id, model_id) pair may appear more than once. per_task()
keeps the last one, and every function that works per task or per model goes
through per_task() so a re-run replaces the earlier answer. accuracy() alone
takes the rows as given.

A row counts as right when correct is True. When correct is None, score >= 0.5
counts as right. When both are None, the row counts as wrong.
"""

from __future__ import annotations

from council.core.schemas_v15 import SoloScore


def _hit(row: SoloScore) -> bool:
    if row.correct is not None:
        return bool(row.correct)
    if row.score is not None:
        return row.score >= 0.5
    return False


def _filter(solo: list[SoloScore], models: list[str] | None) -> list[SoloScore]:
    if models is None:
        return list(solo)
    keep = set(models)
    return [row for row in solo if row.model_id in keep]


def _all_models(solo: list[SoloScore]) -> set[str]:
    return {row.model_id for row in solo}


def per_task(solo: list[SoloScore]) -> dict[str, dict[str, SoloScore]]:
    """task_id -> model_id -> score. Last row wins for a repeated pair."""
    table: dict[str, dict[str, SoloScore]] = {}
    for row in solo:
        table.setdefault(row.task_id, {})[row.model_id] = row
    return table


def accuracy(rows: list[SoloScore]) -> float:
    """Share of rows that are right. 0.0 on an empty list."""
    if not rows:
        return 0.0
    return sum(1 for row in rows if _hit(row)) / len(rows)


def by_model(solo: list[SoloScore]) -> dict[str, float]:
    """model_id -> accuracy over that model's tasks (last row wins per task)."""
    per_model: dict[str, list[SoloScore]] = {}
    for answers in per_task(solo).values():
        for model_id, row in answers.items():
            per_model.setdefault(model_id, []).append(row)
    return {model_id: accuracy(rows) for model_id, rows in per_model.items()}


def best_k(solo: list[SoloScore], k: int) -> list[str]:
    """Top k models by accuracy. Ties go to the lower model id. k <= 0 gives []."""
    if k <= 0:
        return []
    scores = by_model(solo)
    ranked = sorted(scores, key=lambda model_id: (-scores[model_id], model_id))
    return ranked[:k]


def oracle(solo: list[SoloScore], models: list[str] | None = None) -> dict[str, bool]:
    """task_id -> True when at least one listed model answered it right.

    Only tasks that at least one listed model answered appear in the result.
    models=None means every model in solo.
    """
    table = per_task(_filter(solo, models))
    return {
        task_id: any(_hit(row) for row in answers.values())
        for task_id, answers in table.items()
    }


def vote(solo: list[SoloScore], models: list[str] | None = None) -> dict[str, bool]:
    """task_id -> True when more than half of the voters were right.

    Voters are the listed models (all models in solo when models=None). A voter
    who did not answer a task counts as wrong for that task. A tie is not a
    majority, so it gives False.
    """
    voters = set(models) if models is not None else _all_models(solo)
    table = per_task(_filter(solo, models))
    result: dict[str, bool] = {}
    for task_id, answers in table.items():
        right = sum(1 for row in answers.values() if _hit(row))
        result[task_id] = right * 2 > len(voters)
    return result


def common_tasks(solo: list[SoloScore], models: list[str] | None = None) -> list[str]:
    """Sorted task ids that every listed model answered.

    models=None means every model in solo. An empty models list gives [].
    """
    voters = set(models) if models is not None else _all_models(solo)
    if not voters:
        return []
    table = per_task(solo)
    return sorted(
        task_id for task_id, answers in table.items() if voters.issubset(answers.keys())
    )


__all__ = [
    "per_task",
    "accuracy",
    "by_model",
    "best_k",
    "oracle",
    "vote",
    "common_tasks",
]
