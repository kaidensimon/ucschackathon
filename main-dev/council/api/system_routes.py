"""HTTP routes for machine status: model cards, memory plan, spec-decoding pairs, measured models.

Mounted on the server by someone else; this file only builds the router.
A provider method that raises turns into 503 for that route only.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, TypeVar, runtime_checkable

from fastapi import APIRouter, HTTPException

from council.core.schemas_v15 import DraftPair, MeasuredModel, MemoryPlan

T = TypeVar("T")


@runtime_checkable
class SystemProvider(Protocol):
    def model_cards(self) -> list[dict]: ...

    def memory_plan(self) -> MemoryPlan: ...

    def draft_pairs(self) -> list[DraftPair]: ...

    def meminfo(self) -> dict: ...  # total_gib, available_gib, used_gib, swap_used_gib

    def measured(self) -> dict[str, MeasuredModel]: ...


def _call(what: str, fn: Callable[[], T]) -> T:
    """Run one provider method. Any failure becomes a 503 naming what failed."""
    try:
        return fn()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - provider is foreign code
        msg = str(exc)[:300]
        raise HTTPException(503, f"{what} failed: {type(exc).__name__}: {msg}" if msg else f"{what} failed: {type(exc).__name__}")


def _dump(obj: Any) -> Any:
    """Turn pydantic models (also inside lists and dicts) into plain JSON data."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _dump(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_dump(v) for v in obj]
    return obj


def make_router(provider: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/system/models")
    async def get_models() -> list:
        return _call("model_cards", lambda: _dump(list(provider.model_cards())))

    @router.get("/system/memory")
    async def get_memory() -> dict:
        def build() -> dict:
            return {"meminfo": _dump(provider.meminfo()), "plan": _dump(provider.memory_plan())}

        return _call("memory", build)

    @router.get("/system/specdec")
    async def get_specdec() -> list:
        return _call("draft_pairs", lambda: _dump(list(provider.draft_pairs())))

    @router.get("/system/measured")
    async def get_measured() -> dict:
        return _call("measured", lambda: _dump(dict(provider.measured())))

    return router


__all__ = ["SystemProvider", "make_router"]
