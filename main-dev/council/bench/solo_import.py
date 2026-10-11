"""Tolerant loader for solo-model benchmark results (one model answering alone).

The file format from the benchmarking laptop is not fixed, so this takes .json, .jsonl and .csv,
several JSON shapes, and many field-name spellings. Rows with no model or no task are skipped and
counted. Pure apart from reading the one file it is given.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Optional

from council.core.schemas_v15 import SoloScore

_MODEL = ("model_id", "model", "name", "tag")
_TASK = ("task_id", "task", "id", "question_id", "qid")
_CORRECT = ("correct", "is_correct", "passed", "ok")
_SCORE = ("score", "accuracy", "grade")
_ANSWER = ("answer", "output", "response", "prediction")
_CATEGORY = ("category", "subject", "type")
_LAT_S = ("latency_s", "latency", "seconds", "time_s")
_LAT_MS = ("latency_ms", "ms")
_TOKENS = ("tokens_out", "completion_tokens", "tokens")
_LIST_KEYS = ("results", "rows", "data", "scores", "items")

_TRUE = {"true", "t", "1", "yes", "y", "pass", "passed", "correct", "ok"}
_FALSE = {"false", "f", "0", "no", "n", "fail", "failed", "incorrect", "wrong"}


def normalize_model(name: str, known: dict[str, str] | None = None) -> str:
    """Map an Ollama tag like "qwen3:14b" to a council model id. Unknown names pass through lower-cased."""
    raw = str(name or "").strip()
    if not known:
        return raw.lower()
    tries = [raw]
    low = raw.lower()
    for prefix in ("ollama/", "ollama:"):
        if low.startswith(prefix):
            tries.append(raw[len(prefix):])
    for t in list(tries):
        if t.lower().endswith(":latest"):
            tries.append(t[: -len(":latest")])
    for t in tries:
        if t in known:
            return known[t]
    lowered = {str(k).lower(): v for k, v in known.items()}
    for t in tries:
        if t.lower() in lowered:
            return lowered[t.lower()]
    return low


def _lower_keys(d: dict) -> dict:
    return {str(k).strip().lower(): v for k, v in d.items()}


def _pick(d: dict, aliases: tuple[str, ...]) -> Any:
    for a in aliases:
        v = d.get(a)
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        return v
    return None


def _to_bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        s = v.strip().lower()
        if s in _TRUE:
            return True
        if s in _FALSE:
            return False
    return None


def _to_float(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        if isinstance(v, str):
            s = v.strip()
            if s.endswith("%"):
                return float(s[:-1]) / 100.0
            return float(s)
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> Optional[int]:
    f = _to_float(v)
    return None if f is None else int(f)


def _to_solo(raw: dict, model: str = "", task: str = "", known: dict[str, str] | None = None) -> Optional[SoloScore]:
    row = _lower_keys(raw)
    m = _pick(row, _MODEL)
    t = _pick(row, _TASK)
    m = str(m).strip() if m is not None else model
    t = str(t).strip() if t is not None else task
    if not m or not t:
        return None
    score = _to_float(_pick(row, _SCORE))
    correct = _to_bool(_pick(row, _CORRECT))
    if correct is None and score is not None:
        correct = score >= 0.5
    lat = _to_float(_pick(row, _LAT_S))
    if lat is None:
        ms = _to_float(_pick(row, _LAT_MS))
        lat = None if ms is None else ms / 1000.0
    ans = _pick(row, _ANSWER)
    cat = _pick(row, _CATEGORY)
    return SoloScore(
        model_id=normalize_model(m, known),
        task_id=t,
        correct=correct,
        score=score,
        answer="" if ans is None else str(ans),
        category="" if cat is None else str(cat),
        latency_s=lat,
        tokens_out=_to_int(_pick(row, _TOKENS)),
    )


def _is_row(d: dict) -> bool:
    low = _lower_keys(d)
    return _pick(low, _MODEL) is not None and _pick(low, _TASK) is not None


def _cell(value: Any, model: str, task: str) -> Optional[tuple]:
    """One entry of a {task: row-or-bool} map."""
    if isinstance(value, dict):
        return (value, model, task)
    if isinstance(value, bool) or isinstance(value, str):
        return ({"correct": value}, model, task)
    if isinstance(value, (int, float)):
        return ({"score": value}, model, task)
    return None


def _walk(data: Any) -> tuple[list, int, str]:
    """Flatten any supported JSON shape to (row, default_model, default_task) tuples.

    Returns (entries, junk_count, format_name). Junk is entries that are not rows at all.
    """
    entries: list = []
    junk = 0
    if isinstance(data, list):
        for r in data:
            if isinstance(r, dict):
                entries.append((r, "", ""))
            else:
                junk += 1
        return entries, junk, "list"
    if not isinstance(data, dict):
        return [], 1, "unknown"
    if _is_row(data):
        return [(data, "", "")], 0, "single"
    low = _lower_keys(data)
    for key in _LIST_KEYS:
        if key in low and isinstance(low[key], (list, dict)):
            sub, j, fmt = _walk(low[key])
            return sub, j, "results" if fmt == "list" else fmt
    for model, val in data.items():
        model = str(model)
        if isinstance(val, dict) and any(k.lower() in _LIST_KEYS for k in val):
            val = next(v for k, v in val.items() if k.lower() in _LIST_KEYS)
        if isinstance(val, list):
            for r in val:
                if isinstance(r, dict):
                    entries.append((r, model, ""))
                else:
                    junk += 1
        elif isinstance(val, dict):
            for task, cell in val.items():
                e = _cell(cell, model, str(task))
                if e is None:
                    junk += 1
                else:
                    entries.append(e)
        else:
            junk += 1
    return entries, junk, "by_model"


def _read_jsonl(text: str) -> tuple[list, int]:
    entries, junk = [], 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            junk += 1
            continue
        if isinstance(obj, dict):
            entries.append((obj, "", ""))
        else:
            junk += 1
    return entries, junk


def _read_csv(text: str) -> list:
    return [(dict(r), "", "") for r in csv.DictReader(io.StringIO(text)) if any(v for v in r.values() if v)]


def load_solo_report(path, known: dict[str, str] | None = None) -> tuple[list[SoloScore], dict]:
    """Return (scores, info). info has rows (seen), kept, skipped, models, tasks, format."""
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig")
    ext = p.suffix.lower()
    junk = 0
    if ext == ".csv":
        entries, fmt = _read_csv(text), "csv"
    elif ext == ".jsonl":
        entries, junk = _read_jsonl(text)
        fmt = "jsonl"
    else:
        try:
            entries, junk, fmt = _walk(json.loads(text))
            fmt = "json:" + fmt
        except ValueError:
            if ext == ".json":
                raise
            entries, junk = _read_jsonl(text)
            fmt = "jsonl"
    scores: list[SoloScore] = []
    skipped = junk
    for raw, model, task in entries:
        s = _to_solo(raw, model, task, known)
        if s is None:
            skipped += 1
        else:
            scores.append(s)
    info = {
        "rows": len(entries) + junk,
        "kept": len(scores),
        "skipped": skipped,
        "models": sorted({s.model_id for s in scores}),
        "tasks": len({s.task_id for s in scores}),
        "format": fmt,
    }
    return scores, info


def load_solo(path, known: dict[str, str] | None = None) -> list[SoloScore]:
    return load_solo_report(path, known)[0]


__all__ = ["load_solo", "load_solo_report", "normalize_model"]
