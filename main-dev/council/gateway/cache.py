"""Gateway call cache (spec 7.5).

Key: sha256 over the canonical JSON of the fields that decide a model's output.
Only cacheable calls with a fixed seed are read or stored. Only ok results are stored.
Storage is any object with cache_get(key) -> CallResult | None and cache_put(key, result).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional, Protocol

from council.core.schemas import CallResult, CallSpec


class CacheStore(Protocol):
    def cache_get(self, key: str) -> Optional[CallResult]: ...

    def cache_put(self, key: str, result: CallResult) -> None: ...


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def cache_key(spec: CallSpec, quant: str = "") -> str:
    """sha256 hex digest over the output-determining fields of `spec`."""
    material = {
        "model_id": spec.model_id,
        "quant": quant,
        "messages": spec.messages,
        "json_schema": spec.json_schema,
        "reasoning": spec.reasoning,
        "temperature": spec.temperature,
        "top_p": spec.top_p,
        "seed": spec.seed,
        "max_output_tokens": spec.max_output_tokens,
        "max_reasoning_tokens": spec.max_reasoning_tokens,
    }
    return hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()


def _eligible(spec: CallSpec) -> bool:
    return bool(spec.cacheable) and spec.seed is not None


class CallCache:
    """Read-through and write-through cache over a CacheStore."""

    def __init__(self, store: CacheStore) -> None:
        self.store = store
        self.hits = 0
        self.misses = 0

    def get(self, spec: CallSpec, quant: str = "") -> Optional[CallResult]:
        """Cached result for `spec`, or None. Returns None without a lookup unless the call is eligible."""
        if not _eligible(spec):
            self.misses += 1
            return None
        found = self.store.cache_get(cache_key(spec, quant))
        if found is None:
            self.misses += 1
            return None
        self.hits += 1
        return found.model_copy(update={"cached": True})

    def put(self, spec: CallSpec, quant: str, result: CallResult) -> bool:
        """Store `result` if the call is eligible and the result is ok. Returns True when stored."""
        if not _eligible(spec) or not result.ok:
            return False
        self.store.cache_put(cache_key(spec, quant), result)
        return True
