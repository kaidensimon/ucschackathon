"""Benchmark graders (spec 18.1). One normalize() shared by grader and Chamber clustering."""

from __future__ import annotations

import json
import re
import string
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from council.core.schemas import BenchResult, BenchTask

_NUM_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_MCQ_KEYWORD = re.compile(
    r"(?:answer|ans|choice|option)\s*(?:is|=|:|-)?\s*[:\-]?\s*\(?([A-Za-z])\)?(?![A-Za-z])",
    re.IGNORECASE,
)
_MCQ_LEAD = re.compile(r"^\(?([A-Za-z])(?:\)|\.|:)?(?:\s|$)")
_STRIP_CHARS = string.punctuation + string.whitespace


def _norm_mcq(answer: str) -> str:
    s = answer.strip()
    m = _MCQ_KEYWORD.search(s)
    if m:
        return m.group(1).upper()
    m = _MCQ_LEAD.match(s)
    if m:
        return m.group(1).upper()
    return s.strip(_STRIP_CHARS).upper()


def _parse_decimal(answer: str) -> Decimal | None:
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", answer.strip())
    m = _NUM_RE.search(s)
    if not m:
        return None
    try:
        return Decimal(m.group(0))
    except InvalidOperation:
        return None


def _norm_numeric(answer: str) -> str:
    d = _parse_decimal(answer)
    if d is None:
        return answer.strip().lower()
    if d == 0:
        return "0"
    return format(d.normalize(), "f")


def normalize(answer: str, answer_type: str) -> str:
    if answer is None:
        answer = ""
    if answer_type == "mcq":
        return _norm_mcq(answer)
    if answer_type == "numeric":
        return _norm_numeric(answer)
    if answer_type == "exact":
        return " ".join(answer.lower().split()).strip(_STRIP_CHARS)
    return answer.strip().lower()


def _grader_type(task: BenchTask) -> str:
    gtype = task.grader.get("type")
    if gtype:
        return str(gtype)
    return {"mcq": "mcq", "numeric": "numeric_tolerance", "exact": "exact"}.get(
        task.answer_type, "rubric"
    )


def grade(task: BenchTask, answer: str) -> bool:
    gtype = _grader_type(task)
    if gtype == "exact":
        return normalize(answer, "exact") == normalize(task.answer, "exact")
    if gtype == "mcq":
        return normalize(answer, "mcq") == normalize(task.answer, "mcq")
    if gtype == "numeric_tolerance":
        tol = float(task.grader.get("tolerance", 1e-6))
        got = _parse_decimal(answer)
        want = _parse_decimal(task.answer)
        if got is None or want is None:
            return False
        got_f, want_f = float(got), float(want)
        if want_f == 0:
            return abs(got_f) <= tol
        return abs(got_f - want_f) <= tol * abs(want_f)
    if gtype in ("unit_tests", "rubric"):
        raise NotImplementedError(f"grader type {gtype!r} not supported yet")
    raise ValueError(f"unknown grader type {gtype!r}")


def load_tasks(path) -> list[BenchTask]:
    tasks: list[BenchTask] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(BenchTask.model_validate(json.loads(line)))
    return tasks


def split(tasks: Iterable[BenchTask], name: str) -> list[BenchTask]:
    return [t for t in tasks if t.split == name]


def write_results(path, results: list[BenchResult]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        for r in results:
            f.write(r.model_dump_json() + "\n")
