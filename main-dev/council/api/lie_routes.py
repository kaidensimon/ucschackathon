"""HTTP routes for the lie detector. Mounted on the server by someone else; this file only builds the router.

The provider is any object with the LieProvider methods. The routes stay thin: they call the
provider, turn None into 404, and shape the JSON.
"""

from __future__ import annotations

import json
from typing import Any, Optional, Protocol, runtime_checkable

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import PlainTextResponse

from council.core.schemas_v15 import LieReport, ProbeCard

CAVEAT = (
    "Scores are hints, not proof. A probe reads a model's own activations and can be wrong; "
    "a flag means 'check this claim', not 'this claim is false'."
)


@runtime_checkable
class LieProvider(Protocol):
    def lie_report(self, run_id: str) -> Optional[LieReport]: ...

    def probe_cards(self) -> list[ProbeCard]: ...

    async def train(self, model_id: str) -> ProbeCard: ...

    async def train_all(self) -> list[ProbeCard]: ...

    def set_active(self, model_id: str, active: bool) -> Optional[ProbeCard]: ...


def _card(c: ProbeCard) -> dict:
    return c.model_dump(mode="json")


def _fallback_text(report: LieReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True)


def make_router(provider: Any) -> APIRouter:
    router = APIRouter()

    def need_report(run_id: str) -> LieReport:
        report = provider.lie_report(run_id)
        if report is None:
            raise HTTPException(404, f"lie report not found: {run_id}")
        return report

    @router.get("/lies/{run_id}")
    async def get_lies(run_id: str) -> dict:
        report = need_report(run_id)
        out = report.model_dump(mode="json")
        out["caveat"] = CAVEAT
        return out

    @router.get("/lies/{run_id}/text")
    async def get_lies_text(run_id: str) -> PlainTextResponse:
        report = need_report(run_id)
        fn = getattr(provider, "report_text", None)
        text = fn(run_id) if callable(fn) else None
        if not isinstance(text, str) or not text:
            text = _fallback_text(report)
        return PlainTextResponse(text, media_type="text/plain")

    @router.get("/probes/cards")
    async def get_cards() -> list:
        return [_card(c) for c in provider.probe_cards()]

    @router.post("/probes/train_all")
    async def post_train_all() -> list:
        return [_card(c) for c in await provider.train_all()]

    @router.post("/probes/cards/{model_id:path}/train")
    async def post_train(model_id: str) -> dict:
        return _card(await provider.train(model_id))

    @router.patch("/probes/cards/{model_id:path}")
    async def patch_card(model_id: str, body: dict[str, Any] = Body(...)) -> dict:
        active = body.get("active")
        if not isinstance(active, bool):
            raise HTTPException(422, "body must be {\"active\": bool}")
        card = provider.set_active(model_id, active)
        if card is None:
            raise HTTPException(404, f"probe card not found: {model_id}")
        return _card(card)

    return router


__all__ = ["LieProvider", "make_router", "CAVEAT"]
