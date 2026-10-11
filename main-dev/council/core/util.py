"""Small shared helpers. No contract types are defined here.

Spec-facing API
- new_id(prefix)            -> "<prefix>_<12 hex chars>"
- SystemClock / FakeClock   -> clocks with now() -> float epoch seconds
- iso(ts)                   -> UTC ISO-8601 string
- stable_hash(obj)          -> sha256 hex of canonical JSON (sorted keys, no whitespace)
- chunk_words(text, n)      -> list of strings, each at most n whitespace-separated words
- est_tokens(text)          -> ceil(len(text) / 4)
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel


def new_id(prefix: str) -> str:
    """Return "<prefix>_" followed by 12 lowercase hex characters."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SystemClock:
    """Wall clock. now() returns epoch seconds."""

    def now(self) -> float:
        return time.time()


class FakeClock:
    """Deterministic clock for tests. Starts at `start`; advance() moves it forward."""

    def __init__(self, start: float = 0.0) -> None:
        self._t = float(start)

    def now(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += float(seconds)


def iso(ts: float) -> str:
    """Epoch seconds to a UTC ISO-8601 string, e.g. "1970-01-01T00:00:00+00:00"."""
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()


def _plain(obj: Any) -> Any:
    """Replace pydantic models with JSON-ready dicts, recursively through dicts and lists."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj


def stable_hash(obj: Any) -> str:
    """sha256 hex digest of the canonical JSON of obj. Same content, same hash, any key order."""
    canonical = json.dumps(
        _plain(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def chunk_words(text: str, n: int) -> list[str]:
    """Split text on whitespace into chunks of n words each. Empty text gives []."""
    if n < 1:
        raise ValueError("chunk_words: n must be >= 1")
    words = text.split()
    return [" ".join(words[i:i + n]) for i in range(0, len(words), n)]


def est_tokens(text: str) -> int:
    """Rough token estimate: one token per four characters, rounded up."""
    return math.ceil(len(text) / 4)


__all__ = [
    "new_id",
    "SystemClock",
    "FakeClock",
    "iso",
    "stable_hash",
    "chunk_words",
    "est_tokens",
]
