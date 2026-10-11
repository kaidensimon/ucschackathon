"""Read the on-box model check into MeasuredModel rows.

The file is written by tools/box/check_models.py to ~/council/box/model_checks.json:
  {tag: {ok, error, size_gib, ram_gib, tps, json_ok, think_ok, checked_at}}

Field map (JSON -> MeasuredModel):
  tag        -> tag, model_id (until by_model_id sets the registry id)
  ok         -> ok (only a JSON true counts as ok)
  size_gib   -> reported_gib
  ram_gib    -> ram_gib
  tps        -> tps
  json_ok    -> json_ok
  think_ok   -> think_ok
  error      -> error ("" when null)
checked_at is not carried over.

This module reads a file. It never raises on a missing or bad file.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from council.core.schemas import ModelEntry
from council.core.schemas_v15 import MeasuredModel

FILE_NAME = "model_checks.json"


def default_path(home: Path) -> Path:
    """Where the check file lives, given the box home folder."""
    return home / FILE_NAME


def _opt_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    f = float(value)
    return f if math.isfinite(f) else None


def _opt_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _to_measured(tag: str, raw: dict[str, Any]) -> MeasuredModel:
    return MeasuredModel(
        model_id=tag,
        tag=tag,
        ok=raw.get("ok") is True,
        reported_gib=_opt_float(raw.get("size_gib")),
        ram_gib=_opt_float(raw.get("ram_gib")),
        tps=_opt_float(raw.get("tps")),
        json_ok=_opt_bool(raw.get("json_ok")),
        think_ok=_opt_bool(raw.get("think_ok")),
        error=_text(raw.get("error")),
    )


def load_checks(path: Path) -> dict[str, MeasuredModel]:
    """Rows of the check file keyed by Ollama tag. Missing or bad file gives {}."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, MeasuredModel] = {}
    for tag, raw in data.items():
        if not isinstance(tag, str) or not tag or not isinstance(raw, dict):
            continue
        try:
            out[tag] = _to_measured(tag, raw)
        except Exception:
            continue
    return out


def by_model_id(
    checks: dict[str, MeasuredModel], registry: list[ModelEntry]
) -> dict[str, MeasuredModel]:
    """Re-key checks by registry model id, matching ModelEntry.ollama_tag.

    Entries with no ollama_tag, or a tag with no check row, are left out.
    The input dict is not changed.
    """
    out: dict[str, MeasuredModel] = {}
    for entry in registry:
        tag = entry.ollama_tag
        if not tag or tag not in checks:
            continue
        out[entry.id] = checks[tag].model_copy(update={"model_id": entry.id})
    return out
