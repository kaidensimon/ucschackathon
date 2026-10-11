"""Structured output ladder (spec 7.3): grammar, prompted JSON, one repair call, give up."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Optional

from council.core.schemas import CallResult, CallSpec


def _balanced_end(text: str, start: int) -> int:
    """Index of the bracket closing the one at `start`, string-aware. -1 if none."""
    stack: list[str] = []
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if not stack or stack.pop() != ch:
                return -1
            if not stack:
                return i
    return -1


def extract_json(text: str) -> Any | None:
    """First balanced JSON object or array in text, or None. Tolerates fences and prose."""
    if not isinstance(text, str):
        return None
    pos = 0
    n = len(text)
    while pos < n:
        starts = [i for i in (text.find("{", pos), text.find("[", pos)) if i != -1]
        if not starts:
            return None
        s = min(starts)
        e = _balanced_end(text, s)
        if e != -1:
            try:
                return json.loads(text[s : e + 1])
            except (ValueError, TypeError):
                pass
        pos = s + 1
    return None


def _check(candidate: Any, schema: dict) -> bool:
    if candidate is None:
        return False
    try:
        from council.gateway.jsonschema_lite import validate

        return not validate(candidate, schema)
    except Exception:
        return False


def _good(result: Any, schema: dict) -> Optional[Any]:
    """A schema-valid parsed value from a result, or None."""
    if not isinstance(result, CallResult) or not result.ok:
        return None
    cands = [extract_json(result.content)]
    if result.parsed is not None:
        cands.insert(0, result.parsed)
    for c in cands:
        if _check(c, schema):
            return c
    return None


def _fail(base: Optional[CallResult], spec: CallSpec, attempts: int, error: str) -> CallResult:
    if base is None:
        return CallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id,
                          attempts=attempts, error=error)  # type: ignore[arg-type]
    return base.model_copy(update={"ok": False, "parsed": None, "attempts": attempts,
                                   "error": error})


async def run_ladder(
    spec: CallSpec,
    attempt: Callable[[CallSpec, str], Awaitable[CallResult]],
    repair: Callable[[str, dict], Awaitable[CallResult]] | None,
    structured_mode: str,
) -> CallResult:
    """Walk the ladder. Never raises."""
    schema = spec.json_schema
    attempts = 0
    last: Optional[CallResult] = None
    try:
        if schema is None:
            try:
                res = await attempt(spec, "prompt")
                return res.model_copy(update={"attempts": 1})
            except Exception:
                return _fail(None, spec, 1, "server_error")

        modes = (["grammar"] if structured_mode == "grammar" else []) + ["prompt"]
        for mode in modes:
            attempts += 1
            try:
                res = await attempt(spec, mode)
            except Exception:
                continue
            last = res
            if isinstance(res, CallResult) and res.error == "cancelled":
                return res.model_copy(update={"attempts": attempts})
            val = _good(res, schema)
            if val is not None:
                return res.model_copy(update={"parsed": val, "attempts": attempts})

        if repair is not None:
            attempts += 1
            text = last.content if last is not None else ""
            try:
                res = await repair(text, schema)
                val = _good(res, schema)
                if val is not None:
                    return res.model_copy(update={"parsed": val, "attempts": attempts})
                if isinstance(res, CallResult):
                    last = res
            except Exception:
                pass
        return _fail(last, spec, attempts, "invalid_output")
    except Exception:
        return _fail(None, spec, max(attempts, 1), "invalid_output")
