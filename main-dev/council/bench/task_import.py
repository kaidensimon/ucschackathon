"""Load a teammate's custom benchmark file (.jsonl, .json, .csv) into BenchTask rows."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from council.core.schemas import BenchTask

_ID_KEYS = ("id", "task_id", "qid")
_PROMPT_KEYS = ("prompt", "question", "input", "text")
_ANSWER_KEYS = ("answer", "expected", "target", "gold", "label")
_CHOICE_KEYS = ("choices", "options")
_CATEGORY_KEYS = ("category", "subject", "topic")
_LETTER_COLUMNS = ("A", "B", "C", "D")

_CATEGORY_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("math", ("math", "algebra", "arithmetic", "calculus", "geometry")),
    ("logic", ("logic", "puzzle", "deduction", "reasoning")),
    ("code", ("code", "coding", "programming", "software")),
    ("science", ("science", "physics", "chemistry", "biology")),
    ("reading", ("reading", "comprehension")),
    ("writing", ("writing", "essay", "composition")),
    ("planning", ("planning", "plan", "schedule")),
)
_NUM_FULL = re.compile(r"^\s*[-+]?(?:\d[\d,]*(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?\s*%?\s*$")


def _pick(row: dict, keys: tuple[str, ...]) -> Any:
    lowered = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
    for key in keys:
        val = lowered.get(key)
        if val is not None and not (isinstance(val, str) and not val.strip()):
            return val
    return None


def _map_category(raw: Any) -> str:
    text = str(raw or "").lower()
    for cat, words in _CATEGORY_WORDS:
        if any(w in text for w in words):
            return cat
    return "knowledge"


def _map_difficulty(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    return text if text in ("easy", "medium", "hard") else "medium"


def _parse_choices(row: dict) -> list[str] | None:
    raw = _pick(row, _CHOICE_KEYS)
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("["):
            try:
                raw = json.loads(text)
            except ValueError:
                pass
        if isinstance(raw, str):
            raw = [p.strip() for p in text.split("|") if p.strip()]
    if isinstance(raw, dict):
        raw = [raw[k] for k in sorted(raw)]
    if isinstance(raw, (list, tuple)):
        out = [str(c).strip() for c in raw if str(c).strip()]
        return out or None
    lowered = {str(k).strip().upper(): v for k, v in row.items() if k is not None}
    cols = [str(lowered[c]).strip() for c in _LETTER_COLUMNS if lowered.get(c) not in (None, "")]
    return cols or None


def _mcq_answer(answer: str, choices: list[str], warnings: list[str], tid: str) -> str:
    a = answer.strip()
    if len(a) == 1 and a.isalpha():
        return a.upper()
    for i, c in enumerate(choices):
        if a.lower() == c.lower():
            return chr(ord("A") + i)
    if a.isdigit() and 0 <= int(a) < len(choices) and len(choices) <= 26:
        return chr(ord("A") + int(a))
    warnings.append(f"{tid}: answer {a!r} does not match a choice")
    return a


def _build(row: dict, line_no: int, warnings: list[str]) -> BenchTask | None:
    prompt = _pick(row, _PROMPT_KEYS)
    if prompt is None or not str(prompt).strip():
        return None
    tid_raw = _pick(row, _ID_KEYS)
    tid = str(tid_raw).strip() if tid_raw is not None else f"t{line_no}"
    answer_raw = _pick(row, _ANSWER_KEYS)
    answer = "" if answer_raw is None else str(answer_raw).strip()
    choices = _parse_choices(row)
    if answer_raw is None:
        warnings.append(f"{tid}: no answer")
    if choices:
        atype = "mcq"
        answer = _mcq_answer(answer, choices, warnings, tid) if answer else ""
        grader: dict[str, Any] = {"type": "mcq"}
    elif answer and _NUM_FULL.match(answer):
        atype = "numeric"
        answer = answer.replace(",", "").rstrip("% \t")
        grader = {"type": "numeric_tolerance", "tolerance": 1e-6}
    else:
        atype = "freeform"
        grader = {"type": "rubric"}
    return BenchTask(
        id=tid,
        prompt=str(prompt).strip(),
        source="custom",
        category=_map_category(_pick(row, _CATEGORY_KEYS)),
        difficulty=_map_difficulty(_pick(row, ("difficulty",))),
        choices=choices,
        answer_type=atype,
        answer=answer,
        grader=grader,
    )


def _read_rows(path: Path, warnings: list[str]) -> list[tuple[int, Any]]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8-sig")
    rows: list[tuple[int, Any]] = []
    if suffix == ".jsonl":
        for n, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append((n, json.loads(line)))
            except ValueError:
                warnings.append(f"line {n}: bad json")
    elif suffix == ".json":
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("tasks", data.get("questions", []))
        if not isinstance(data, list):
            raise ValueError("json file needs a list, or 'tasks'/'questions' list")
        rows = list(enumerate(data, start=1))
    elif suffix == ".csv":
        reader = csv.DictReader(text.splitlines())
        rows = [(n, r) for n, r in enumerate(reader, start=1)]
    else:
        raise ValueError(f"unsupported file type {suffix!r}")
    return rows


def load_tasks(path: Path) -> tuple[list[BenchTask], dict]:
    warnings: list[str] = []
    tasks: list[BenchTask] = []
    skipped = 0
    seen: set[str] = set()
    for n, row in _read_rows(Path(path), warnings):
        if not isinstance(row, dict):
            skipped += 1
            warnings.append(f"row {n}: not an object")
            continue
        task = _build(row, n, warnings)
        if task is None:
            skipped += 1
            continue
        if task.id in seen:
            warnings.append(f"{task.id}: duplicate id")
        seen.add(task.id)
        tasks.append(task)
    by_category: dict[str, int] = {}
    for t in tasks:
        by_category[t.category] = by_category.get(t.category, 0) + 1
    report = {"tasks": len(tasks), "skipped": skipped, "by_category": by_category, "warnings": warnings}
    return tasks, report
