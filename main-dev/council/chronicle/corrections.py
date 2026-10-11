"""27.6 Corrections: build them from a tribunal outcome, keep them, feed notes and dataset."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from council.core.schemas import Correction, ModelEntry, TrainingExample, TribunalOutcome

try:
    from council.core.workspace import adapters_dir
except ImportError:  # workspace module not there yet: same layout as 27.6

    def adapters_dir(home: Path, project: str, model_id: str) -> Path:
        return Path(home) / "adapters" / project / model_id


TASK_LIMIT = 2000
_WORD = re.compile(r"[a-z0-9_]{3,}")


def _words(text: str) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


def _clip(text: str, n: int) -> str:
    text = text or ""
    return text if len(text) <= n else text[: n - 3] + "..."


def build_correction(
    outcome: TribunalOutcome,
    project: str,
    model: ModelEntry,
    run_id: str,
    task: str,
    wrong_position: str,
    council_position: str,
    verified_by: str,
    now: float,
) -> Correction:
    task = _clip(task, TASK_LIMIT)
    lesson = (outcome.lesson or "").strip()
    target_a = council_position
    if lesson:
        target_a = f"{council_position}\n\nLesson: {lesson}"
    explain = f"No. That is wrong"
    if outcome.error_kind and outcome.error_kind != "none":
        explain += f" ({outcome.error_kind} error)"
    explain += f". The correct position is: {council_position}"
    if lesson:
        explain += f"\n\n{lesson}"
    ex_a = TrainingExample(
        messages=[{"role": "user", "content": task}],
        target=target_a,
    )
    ex_b = TrainingExample(
        messages=[
            {
                "role": "user",
                "content": f"{task}\n\nA colleague proposes: {wrong_position}. Is that right?",
            }
        ],
        target=explain,
    )
    return Correction(
        id=uuid.uuid4().hex,
        project=project,
        model_id=model.id,
        lineage=model.lineage,
        run_id=run_id,
        created_at=now,
        task=task,
        wrong_position=wrong_position,
        council_position=council_position,
        error_kind=outcome.error_kind,
        lesson=lesson,
        verified_by=verified_by,  # type: ignore[arg-type]
        examples=[ex_a, ex_b],
    )


class CorrectionBook:
    def __init__(self, store: Any, home: Path):
        self.store = store
        self.home = Path(home)

    def _dataset(self, project: str, model_id: str) -> Path:
        return adapters_dir(self.home, project, model_id) / "dataset.jsonl"

    def record(self, c: Correction) -> Path:
        self.store.corrections_put(c)
        path = self._dataset(c.project, c.model_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            for ex in c.examples:
                f.write(json.dumps(ex.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return path

    def notes_for(self, project: str, model_id: str, query_text: str, k: int = 5) -> str:
        items = [c for c in self.store.corrections_list(project, model_id) if c.lesson.strip()]
        if not items or k <= 0:
            return ""
        q = _words(query_text)
        scored: list[tuple[int, int, Correction]] = []
        for i, c in enumerate(items):
            overlap = len(q & _words(f"{c.lesson} {c.task} {c.wrong_position} {c.council_position}"))
            if q and overlap == 0:
                continue
            scored.append((overlap, i, c))
        if not scored:
            return ""
        scored.sort(key=lambda t: (-t[0], -t[1]))  # most overlap, then newest
        lines = ["Corrections from earlier sessions in this project:"]
        seen: set[str] = set()
        for _, _, c in scored:
            lesson = " ".join(c.lesson.split())
            if lesson in seen:
                continue
            seen.add(lesson)
            lines.append(f"- {lesson}")
            if len(seen) >= k:
                break
        return "\n".join(lines)

    def dataset_size(self, project: str, model_id: str) -> int:
        path = self._dataset(project, model_id)
        if not path.exists():
            return 0
        with path.open("r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
