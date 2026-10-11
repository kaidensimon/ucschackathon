"""FastAPI app for the UI-agnostic API (spec 17). Thin: every route calls RunController."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from council.api.controller import InvalidState, PlanRejected, RunController, RunNotFound
from council.api import lie_routes, run_summary, system_routes
from council.api.providers import LieProviderImpl, SystemProviderImpl, steer_cards
from council.api.providers import run_events as stored_events
from council.api.sse import parse_since, stream_frames
from council.api.ui_bridge import UiBridge
from council.core import config as config_mod
from council.core import event_types as ET
from council.core.schemas import BenchRunRequest, RunRequest, UserInput
from council.probe.probe_files import ProbeFiles

KEEPALIVE_S = 15.0
API_LOAD_SEAT = "api-load"  # the seat id of POST /models/{id}/load ("manual" is the bench's)
POLL_S = 0.25
DEFAULT_PORT = 8765


def _default_controller() -> RunController:
    """config/council.toml decides: gateway.mock picks the mock or the real stack, and
    host.driver picks the model server of the real one."""
    db_dir = config_mod.home() / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return RunController.build_from_config(db_path=db_dir / "council.db")


def _driver_name(ctrl: RunController) -> str:
    """The host driver in use: "mock" in mock mode, else host.driver of the config."""
    if ctrl.mock:
        return "mock"
    return str(getattr(getattr(ctrl.config, "host", None), "driver", "") or "")


def _issue(issue: Any) -> dict:
    if isinstance(issue, dict):
        return issue
    return {
        "code": str(getattr(issue, "code", "") or ""),
        "task_id": getattr(issue, "task_id", None),
        "message": str(getattr(issue, "message", issue)),
    }


def _event_dict(ev: Any) -> dict:
    """A stored Event as the dict run_summary reads (ts as an ISO string)."""
    try:
        ts = datetime.fromtimestamp(float(ev.ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        ts = None
    return {"seq": ev.seq, "run_id": ev.run_id, "ts": ts, "type": ev.type, "payload": ev.payload}


def create_app(controller: Optional[RunController] = None) -> FastAPI:
    ctrl = controller if controller is not None else _default_controller()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await ctrl.host.start()
        except Exception:
            pass
        try:
            yield
        finally:
            await ctrl.shutdown()

    app = FastAPI(title="Council API", lifespan=lifespan)
    app.state.controller = ctrl
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Electron loads from file://, Vite from localhost
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # The partner UI's contract (/ui/...): chats in the store, one council run per message.
    from council.api import ui_api
    from council.api.ui_chats import UiChats
    app.include_router(ui_api.make_router(ctrl, getattr(ctrl, "ui_chats", None) or UiChats(ctrl.store)))

    @app.exception_handler(RunNotFound)
    async def _nf(_: Request, exc: RunNotFound):
        return JSONResponse({"detail": f"run not found: {exc}"}, status_code=404)

    @app.exception_handler(InvalidState)
    async def _bad(_: Request, exc: InvalidState):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(PlanRejected)
    async def _rejected(_: Request, exc: PlanRejected):
        return JSONResponse(
            {"ok": False, "detail": str(exc), "issues": [_issue(i) for i in exc.issues]},
            status_code=422,
        )

    # 1.5 routes. The lie router goes first: /probes/cards/... must not be taken by the
    # older /probes/{model_id:path}/train below.
    probe_files = ProbeFiles(ctrl.data_home)
    lie_provider = LieProviderImpl(
        getattr(ctrl, "reliability", None), probe_files=probe_files, store=ctrl.store,
        registry=ctrl.registry, source=str(getattr(getattr(ctrl.config, "probe", None), "source", "mock")),
        busy=getattr(ctrl, "models_busy", None),
    )
    app.include_router(lie_routes.make_router(lie_provider))
    app.include_router(system_routes.make_router(SystemProviderImpl(ctrl, lie_provider.probe_cards)))

    def need_run(run_id: str) -> None:
        if ctrl.store.get_run(run_id) is None:
            raise HTTPException(404, f"run not found: {run_id}")

    # ------------------------------------------------------------------ health

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True, "mock": bool(ctrl.mock), "driver": _driver_name(ctrl)}

    # ------------------------------------------------------------------ runs

    @app.post("/runs")
    async def start_run(req: RunRequest) -> dict:
        """Start a run. Free-form `options` also take "k" (council size, 2..6) and "effort"
        (the adaptive effort level)."""
        return {"run_id": await ctrl.start(req)}

    @app.get("/runs")
    async def list_runs() -> list:
        return ctrl.list_runs()

    @app.get("/runs/{run_id}")
    async def get_run(run_id: str):
        need_run(run_id)
        return ctrl.snapshot(run_id)

    @app.get("/runs/{run_id}/summary")
    async def run_summary_route(run_id: str) -> dict:
        """The run folded into one flat dict (lineup, rounds, decision, tasks, failures, tokens)."""
        need_run(run_id)
        return run_summary.summarize([_event_dict(e) for e in stored_events(ctrl.store, run_id)])

    @app.get("/runs/{run_id}/events")
    async def run_events(run_id: str, request: Request, since: Optional[str] = None):
        need_run(run_id)
        cursor = parse_since(since, request.headers.get("last-event-id"))

        async def should_stop() -> bool:
            # A run this process no longer drives gets no more events: replay, then close.
            return not ctrl.is_active(run_id) or await request.is_disconnected()

        frames = stream_frames(
            ctrl.bus.subscribe(run_id, cursor), keepalive_s=KEEPALIVE_S, poll_s=POLL_S,
            should_stop=should_stop, terminal=ET.TERMINAL_EVENTS,
        )
        return StreamingResponse(
            frames, media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/runs/{run_id}/ui-events")
    async def run_ui_events(run_id: str, request: Request):
        """The run as the partner UI's DebateEvent stream (docs/ui_ref/lib/events.ts): every
        engine event of the run goes through one UiBridge. Always from the start of the run
        (the bridge numbers its own events from 1), so a finished run is replayed whole.
        Frames carry no "event:" name: EventSource.onmessage gets every one."""
        need_run(run_id)

        async def should_stop() -> bool:
            return not ctrl.is_active(run_id) or await request.is_disconnected()

        frames = stream_frames(
            ctrl.bus.subscribe(run_id, 0), keepalive_s=KEEPALIVE_S, poll_s=POLL_S,
            should_stop=should_stop, terminal=ET.TERMINAL_EVENTS,
        )

        async def ui_frames():
            bridge = UiBridge(run_id)
            async for frame in frames:
                if not frame.startswith("id:"):
                    yield frame  # keepalive
                    continue
                try:
                    event = json.loads(frame.split("\ndata: ", 1)[1])
                    out = bridge.feed(event)
                except Exception:
                    continue  # one event the bridge cannot draw never ends the stream
                for ui in out:
                    yield f"id: {ui['seq']}\ndata: {json.dumps(ui, separators=(',', ':'))}\n\n"

        return StreamingResponse(
            ui_frames(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/runs/{run_id}/delegate")
    async def delegate(run_id: str) -> dict:
        return {"ok": await ctrl.delegate(run_id)}

    @app.post("/runs/{run_id}/input")
    async def submit_input(run_id: str, body: UserInput) -> dict:
        return {"ok": await ctrl.submit_input(run_id, body)}

    @app.patch("/runs/{run_id}/plan")
    async def patch_plan(run_id: str, body: dict[str, Any] = Body(...)):
        """Lay the body over the current plan and re-lint it. 200 {ok, plan, issues: []};
        422 {ok: false, detail, issues} when lint errors are left (nothing stored);
        409 outside AWAITING_DELEGATION; 404 for an unknown run."""
        plan = ctrl.patch_plan(run_id, body)
        return {"ok": True, "plan": plan, "issues": []}

    @app.post("/runs/{run_id}/cancel")
    async def cancel(run_id: str) -> dict:
        return {"ok": await ctrl.cancel(run_id)}

    # ------------------------------------------------------------------ router, models

    @app.get("/router/preview")
    async def router_preview(task: str, mode: str = "standard"):
        return ctrl.router_preview(task, mode)

    @app.get("/models")
    async def models() -> list:
        live = {r["model_id"]: r for r in ctrl.host.status()}
        rows = []
        for m in ctrl.registry:
            d = m.model_dump(mode="json")
            r = live.get(m.id)
            d["live"] = dict(resident=r is not None, **(r or {}))
            rows.append(d)
        return rows

    def need_model(model_id: str) -> None:
        if model_id not in {m.id for m in ctrl.registry}:
            raise HTTPException(404, f"model not found: {model_id}")

    @app.post("/models/{model_id}/load")
    async def load_model(model_id: str) -> dict:
        need_model(model_id)
        host = ctrl.host
        if any(r.get("model_id") == model_id for r in host.status()):
            # Resident already, in whatever profile a run or a bench loaded it: leave it alone.
            return {"ok": True, "model_id": model_id}
        try:
            # Its own seat id: "manual" is the bench's, and releasing that drops the bench's models.
            await host.load(model_id, "live", API_LOAD_SEAT)
        except Exception as exc:
            raise HTTPException(409, str(exc)[:300])
        finally:
            host.release(API_LOAD_SEAT)
        return {"ok": True, "model_id": model_id}

    @app.post("/models/{model_id}/unload")
    async def unload_model(model_id: str) -> dict:
        need_model(model_id)
        host = ctrl.host
        seated = getattr(host, "is_seated", None)
        if seated is not None and seated(model_id):
            raise HTTPException(409, f"model is in use by a run: {model_id}")
        await host.unload(model_id, "manual")
        return {"ok": True, "model_id": model_id}

    # ------------------------------------------------------------------ chronicle, telemetry

    @app.get("/chronicle")
    async def chronicle() -> list:
        return ctrl.store.chronicle_list()

    @app.patch("/chronicle/{entry_id}")
    async def chronicle_patch(entry_id: str, body: dict[str, Any] = Body(...)):
        entry = next((e for e in ctrl.store.chronicle_list() if e.id == entry_id), None)
        if entry is None:
            raise HTTPException(404, f"chronicle entry not found: {entry_id}")
        body.pop("id", None)
        try:
            new = type(entry).model_validate({**entry.model_dump(mode="json"), **body})
        except Exception as exc:
            raise HTTPException(422, str(exc)[:500])
        ctrl.store.chronicle_put(new)
        return new

    @app.delete("/chronicle/{entry_id}")
    async def chronicle_delete(entry_id: str) -> dict:
        if not any(e.id == entry_id for e in ctrl.store.chronicle_list()):
            raise HTTPException(404, f"chronicle entry not found: {entry_id}")
        ctrl.store.chronicle_delete(entry_id)
        return {"ok": True}

    @app.get("/telemetry")
    async def telemetry():
        return ctrl.telemetry()

    # ------------------------------------------------------------------ bench (17)

    @app.post("/bench/runs")
    async def bench_start(req: Optional[BenchRunRequest] = None) -> dict:
        return {"bench_id": await ctrl.start_bench(req or BenchRunRequest())}

    @app.get("/bench/runs/{bench_id}")
    async def bench_get(bench_id: str) -> dict:
        try:
            return ctrl.bench_status(bench_id)
        except RunNotFound:
            raise HTTPException(404, f"bench run not found: {bench_id}")

    # ------------------------------------------------------------------ 27, 28

    @app.get("/corrections")
    async def corrections(project: Optional[str] = None) -> list:
        return ctrl.corrections(project)

    @app.get("/probes")
    async def probes() -> list:
        return [p.model_dump(mode="json", exclude={"weights"}) for p in ctrl.probes()]

    @app.post("/probes/{model_id:path}/train")
    async def probe_train(model_id: str):
        need_model(model_id)
        probe = await ctrl.train_probe(model_id)
        return probe.model_dump(mode="json", exclude={"weights"})

    @app.get("/steer")
    async def steer() -> list:
        """Steering-vector cards from the steer store; [] while there is none."""
        return steer_cards(ctrl)

    @app.get("/chronicle/export")
    async def chronicle_export(project: Optional[str] = None) -> PlainTextResponse:
        return PlainTextResponse(ctrl.export_chronicle(project), media_type="text/markdown")

    @app.get("/config")
    async def get_config():
        return ctrl.config.model_dump(mode="json")

    return app


def main() -> None:
    import uvicorn

    port = int(os.environ.get("COUNCIL_PORT") or DEFAULT_PORT)
    uvicorn.run(create_app(), host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
