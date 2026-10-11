"""The partner UI's HTTP contract (/ui/...): chats, messages, runs as RunEvent and DebateEvent
streams. Thin: chats live in UiChats, runs in RunController. camelCase JSON as in the UI's
engine/contract.ts. Errors are {"code", "message"}.

make_router(controller, chats) -> APIRouter
RunTranslator: engine events of one run -> RunEvent dicts (pure, no I/O).

Seats of a run: the "seats" of POST /ui/chats/{id}/messages (2..6), DEFAULT_SEATS when it is left
out, never more than the models that can hold a seat. "Ask again" keeps the seats of the run it
replaces. GET /ui/health also says how many seats can be asked for (extra fields: "seats",
"models").

GET /ui/runs/{id}/debate always starts at the first event of the run: a finished run is replayed
whole and ends with answer.released; a run that is still going gives what happened so far and
then stays open for the rest, each event once.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Optional

from fastapi import APIRouter, Body, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute

from council.api.controller import RunNotFound
from council.api.sse import stream_frames
from council.api.ui_bridge import UiBridge
from council.core import event_types as ET
from council.core.schemas import RunRequest

NS_RUNS = "ui_runs"  # kv: run id -> {chatId, messageId}
ENGINE_VERSION = "council-1.5"
KEEPALIVE_S = 15.0
POLL_S = 0.25
DELTA_CHARS = 80
MAX_READING = 0.95
NO_ANSWER = "The council finished without a written answer."
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
SETTINGS_KEYS = ("modelAddress", "modelKey", "systemPrompt", "maxAnswerTokens")
DEFAULT_SEATS = 3  # what the UI shows when the user picked nothing
MIN_SEATS, MAX_SEATS = 2, 6
LOST_RUN = "The council stopped before it finished."


class UiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"code": code, "message": message}, status_code=status)


class _UiRoute(APIRoute):
    """Every error of a /ui route leaves as {"code", "message"}."""

    def get_route_handler(self) -> Callable:
        inner = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await inner(request)
            except UiError as exc:
                return _err(exc.status, exc.code, exc.message)
            except RunNotFound:
                return _err(404, "not_found", "That run does not exist.")
            except RequestValidationError:
                return _err(422, "bad_request", "The request was not understood.")

        return handler


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def seat_models(registry: Any) -> list:
    """The models that can hold a seat now: active, and tagged "seat" when the registry uses roles."""
    active = [m for m in registry or [] if getattr(m, "status", "active") == "active"]
    seated = [m for m in active if "seat" in (getattr(m, "roles", None) or [])]
    return seated or active


def seat_count(asked: Any, usable: int) -> int:
    """Seats for a run: what was asked (DEFAULT_SEATS if nothing), within 2..6 and the usable
    models. With fewer than two usable models the engine is left to say what is wrong."""
    want = asked if isinstance(asked, int) and not isinstance(asked, bool) else DEFAULT_SEATS
    want = max(MIN_SEATS, min(MAX_SEATS, want))
    return max(MIN_SEATS, min(want, usable)) if usable > 0 else want


def _pieces(text: str, size: int = DELTA_CHARS) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]


# --------------------------------------------------------------------------------------
# engine events -> RunEvent (pure)
# --------------------------------------------------------------------------------------


class RunTranslator:
    """Feed the engine events of one run (dicts with "type" and "payload"), get RunEvents.

    After the terminal event `end` is "done" | "failed" | "stopped"; the caller saves the
    message and closes with finish()."""

    def __init__(self, run_id: str, message_id: str) -> None:
        self.run_id, self.message_id = run_id, message_id
        self.seq = 0
        self.phase = "waiting"
        self.loading: set = set()
        self.loaded: set = set()
        self.seats = 0
        self.planned: Optional[int] = None
        self.round = 0
        self.end: Optional[str] = None
        self.final_text = ""
        self.error: Optional[str] = None
        self.tokens: Optional[int] = None
        self._last: Any = None

    def _ev(self, type_: str, **fields: Any) -> dict:
        self.seq += 1
        return dict(type=type_, runId=self.run_id, seq=self.seq, **fields)

    def _progress(self) -> Optional[float]:
        if self.phase == "waiting":
            total = max(self.seats, len(self.loading | self.loaded))
            if not total or not (self.loading or self.loaded):
                return None
            return round(min(1.0, len(self.loaded) / total), 3)
        if not self.planned:
            return None
        return round(min(MAX_READING, (self.round + 1) / (self.planned + 1)), 3)

    def _status(self) -> list[dict]:
        now = (self.phase, self._progress())
        if now == self._last:
            return []
        self._last = now
        return [self._ev("run.status", status=now[0], progress=now[1])]

    def start(self) -> list[dict]:
        first = dict(type="run.started", runId=self.run_id, messageId=self.message_id, seq=0)
        self.seq += 1
        first["seq"] = self.seq
        return [first] + self._status()

    def feed(self, event: dict) -> list[dict]:
        if self.end is not None:
            return []
        t, p = event.get("type"), event.get("payload") or {}
        if t == ET.ROUTER_LINEUP_SELECTED:
            self.seats = len(((p.get("lineup") or {}).get("seats")) or []) or self.seats
            for m in p.get("models") or []:  # already in memory: no model.loaded will come for it
                if isinstance(m, dict) and m.get("resident") is True and m.get("model_id"):
                    self.loaded.add(m["model_id"])
        elif t == ET.MODEL_LOADING:
            self.loading.add(p.get("model_id"))
        elif t == ET.MODEL_LOADED:
            self.loaded.add(p.get("model_id"))
        elif t == ET.EFFORT_PLANNED:
            rounds = p.get("rounds")
            self.planned = len(rounds) if isinstance(rounds, list) else self.planned
        elif t == ET.ROUND_STARTED:
            self.phase = "reading"
            self.round = int(p.get("round") or 0)
        elif t == ET.TURN_STARTED:
            self.phase = "reading"
        elif t == ET.RUN_COMPLETED:
            self.end = "done"
            self.final_text = str(p.get("final_text") or "").strip() or NO_ANSWER
            out = (p.get("counters") or {}).get("tokens_out")
            self.tokens = int(out) if isinstance(out, (int, float)) and out else None
            return [self._ev("delta", text=piece) for piece in _pieces(self.final_text)]
        elif t == ET.RUN_FAILED:
            self.end = "failed"
            self.error = "The council could not finish: " + str(p.get("error") or "unknown error")[:300]
            return []
        elif t == ET.RUN_CANCELLED:
            self.end = "stopped"
            self.error = "Stopped before the council finished."
            return []
        else:
            return []
        return self._status()

    def lost(self) -> None:
        """The stream ended with no terminal event (the server was restarted mid-run)."""
        if self.end is None:
            self.end = "failed"
            self.error = "The council stopped before it finished. Ask again."

    def fields(self) -> dict:
        """What to save on the assistant message once the run ended."""
        if self.end == "done":
            return dict(text=self.final_text, status="complete",
                        model=f"Council of {self.seats}" if self.seats else "Council",
                        answerTokens=self.tokens, error=None)
        return dict(status=self.end or "failed", error=self.error)

    def finish(self, message: dict) -> dict:
        return self._ev("run.done" if self.end == "done" else "run.error", message=message)


# --------------------------------------------------------------------------------------
# streams
# --------------------------------------------------------------------------------------


def _engine_frames(ctrl: Any, run_id: str, request: Request) -> AsyncIterator[str]:
    async def should_stop() -> bool:
        return not ctrl.is_active(run_id) or await request.is_disconnected()

    return stream_frames(ctrl.bus.subscribe(run_id, 0), keepalive_s=KEEPALIVE_S, poll_s=POLL_S,
                         should_stop=should_stop, terminal=ET.TERMINAL_EVENTS)


def _frame(obj: dict) -> str:
    return f"data: {json.dumps(obj, separators=(',', ':'))}\n\n"


def _ui_frame(ui: dict) -> str:
    return f"id: {ui['seq']}\ndata: {json.dumps(ui, separators=(',', ':'))}\n\n"


async def debate_frames(ctrl: Any, run_id: str, request: Request) -> AsyncIterator[str]:
    """The run as DebateEvent frames (same stream as GET /runs/{id}/ui-events).

    Always from the first engine event: what already happened, then the rest as it happens,
    every engine event through the one bridge exactly once (the bus hands out each seq once).
    A finished run ends with answer.released. If the run is over and its last events were not
    handed out (it ended between two reads, or the server was restarted mid-run), they are read
    from the store; a run that died with no end event is closed as "stopped"."""
    bridge = UiBridge(run_id)
    last = 0
    async for frame in _engine_frames(ctrl, run_id, request):
        if not frame.startswith("id:"):
            yield frame  # keepalive
            continue
        try:
            event = json.loads(frame.split("\ndata: ", 1)[1])
            last = max(last, int(event.get("seq") or 0))
            out = bridge.feed(event)
        except Exception:
            continue
        for ui in out:
            yield _ui_frame(ui)
    if bridge.released or ctrl.is_active(run_id):
        return  # complete, or the reader went away and the run goes on
    try:
        rest = [e.model_dump(mode="json") for e in ctrl.store.events_since(run_id, last)]
    except Exception:
        rest = []
    stamp = None
    for event in rest:
        stamp = event.get("ts") or stamp
        try:
            out = bridge.feed(event)
        except Exception:
            continue
        for ui in out:
            yield _ui_frame(ui)
    if not bridge.released:
        for ui in bridge.feed({"type": ET.RUN_FAILED, "ts": stamp, "payload": {"error": LOST_RUN}}):
            yield _ui_frame(ui)


# --------------------------------------------------------------------------------------
# router
# --------------------------------------------------------------------------------------


NL2 = "\n\n"  # a blank line between the question and the search results


def make_router(controller: Any, chats: Any) -> APIRouter:
    ctrl = controller
    router = APIRouter(prefix="/ui", route_class=_UiRoute)

    def need_chat(chat_id: str) -> dict:
        try:
            chat = chats.get(chat_id)
        except LookupError:
            chat = None
        if not chat:
            raise UiError(404, "not_found", "That chat does not exist.")
        return chat

    def summary(chat: dict) -> dict:
        msgs = chat.get("messages") or []
        out = {k: v for k, v in chat.items() if k != "messages"}
        out.setdefault("messageCount", len(msgs))
        out["preview"] = " ".join(str(msgs[-1].get("text") or "").split())[:120] if msgs else ""
        out["match"] = None
        return out

    def find_message(chat_id: str, message_id: str) -> Optional[dict]:
        try:
            chat = chats.get(chat_id) or {}
        except LookupError:
            return None
        return next((m for m in chat.get("messages") or [] if m.get("id") == message_id), None)

    def save(chat_id: str, message_id: str, **fields: Any) -> dict:
        """set_message, and always a Message back (also when a regenerate removed it)."""
        try:
            saved = chats.set_message(chat_id, message_id, **fields)
        except Exception:
            saved = None
        msg = saved if isinstance(saved, dict) and saved.get("id") else find_message(chat_id, message_id)
        if msg is None:
            msg = dict(id=message_id, chatId=chat_id, role="assistant", text="", status="failed",
                       createdAt=_now(), model=None, tokensPerSecond=None, answerTokens=None,
                       error=None, runId=None)
            msg.update(fields)
        return msg

    def seats_of_last_run(chat_id: str) -> Optional[int]:
        """The seats of the chat's newest run, so that "ask again" asks the same council."""
        try:
            messages = (chats.get(chat_id) or {}).get("messages") or []
        except LookupError:
            return None
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("runId"):
                seats = (ctrl.store.kv_get(NS_RUNS, msg["runId"]) or {}).get("seats")
                return seats if isinstance(seats, int) and not isinstance(seats, bool) else None
        return None

    def body_dict(body: Any) -> dict:
        if not isinstance(body, dict):
            raise UiError(422, "bad_request", "The request was not understood.")
        return body

    async def start_run(chat_id: str, text: str, seats: Any, history: str, user: Optional[dict]) -> dict:
        k = seat_count(seats, len(seat_models(ctrl.registry)))
        options: dict[str, Any] = {"auto_delegate": True, "auto_input": True, "k": k}
        assistant = chats.add_message(chat_id, "assistant", "", status="writing")
        task = f"{history}\n\n{text}" if history else text
        try:
            run_id = await ctrl.start(RunRequest(task=task, deliverable="answer", options=options))
        except Exception as exc:  # noqa: BLE001
            save(chat_id, assistant["id"], status="failed", error="The council could not start.")
            raise UiError(500, "run_failed", f"The council could not start: {str(exc)[:200]}")
        ctrl.store.kv_put(NS_RUNS, run_id, {"chatId": chat_id, "messageId": assistant["id"], "seats": k})
        assistant = save(chat_id, assistant["id"], runId=run_id)
        return dict(runId=run_id, userMessage=user, assistantMessage=assistant,
                    chat=summary(need_chat(chat_id)))

    # ------------------------------------------------------------------ health, settings

    @router.get("/health")
    async def health(request: Request) -> dict:
        registry = list(ctrl.registry or [])
        active = [m for m in registry if getattr(m, "status", "active") == "active"]
        n = len(active)  # quarantined / failed models are not counted
        usable = len(seat_models(registry))
        resting = len(registry) - n
        detail = f"{resting} of {len(registry)} models are resting after an error." if resting else None
        return dict(
            ok=True, engineVersion=ENGINE_VERSION,
            model=dict(state="ready", address=str(request.base_url).rstrip("/"),
                       name=f"Council ({n} models)", contextTokens=None, detail=detail, checkedAt=_now()),
            # extra to contract.ts Health: what a run can be asked for, and the models by name
            seats=dict(default=seat_count(None, usable), min=MIN_SEATS,
                       max=max(MIN_SEATS, min(MAX_SEATS, usable)) if usable else MAX_SEATS, usable=usable),
            models=[dict(id=getattr(m, "id", ""), name=getattr(m, "display", "") or getattr(m, "id", ""),
                         status=getattr(m, "status", "active"),
                         seat="seat" in (getattr(m, "roles", None) or [])) for m in registry])

    @router.get("/settings")
    async def get_settings() -> dict:
        return chats.settings()

    @router.patch("/settings")
    async def patch_settings(body: Any = Body(...)) -> dict:
        fields = {k: v for k, v in body_dict(body).items() if k in SETTINGS_KEYS}
        return chats.update_settings(**fields)

    # ------------------------------------------------------------------ chats

    @router.get("/chats")
    async def list_chats(query: Optional[str] = None) -> list:
        return chats.list((query or "").strip() or None)

    @router.post("/chats")
    async def create_chat(body: Any = Body(None)) -> dict:
        title = (body or {}).get("title") if isinstance(body, dict) else None
        return chats.create(title if isinstance(title, str) and title.strip() else None)

    @router.get("/chats/{chat_id}")
    async def get_chat(chat_id: str) -> dict:
        return need_chat(chat_id)

    @router.patch("/chats/{chat_id}")
    async def patch_chat(chat_id: str, body: Any = Body(...)) -> dict:
        need_chat(chat_id)
        b = body_dict(body)
        title, pinned = b.get("title"), b.get("pinned")
        return chats.update(chat_id, title=title if isinstance(title, str) else None,
                            pinned=pinned if isinstance(pinned, bool) else None)

    @router.delete("/chats/{chat_id}")
    async def delete_chat(chat_id: str) -> Response:
        need_chat(chat_id)
        chats.delete(chat_id)
        return Response(status_code=204)

    @router.get("/chats/{chat_id}/export")
    async def export_chat(chat_id: str, format: str = "markdown") -> dict:
        need_chat(chat_id)
        if format not in ("markdown", "json"):
            raise UiError(422, "bad_request", "The format must be markdown or json.")
        return chats.export(chat_id, format)

    @router.post("/chats/{chat_id}/messages")
    async def send_message(chat_id: str, body: Any = Body(...)) -> dict:
        need_chat(chat_id)
        b = body_dict(body)
        text = b.get("text")
        if not isinstance(text, str) or not text.strip():
            raise UiError(422, "bad_request", "Write a question first.")
        seats = b.get("seats")
        if seats is not None and (isinstance(seats, bool) or not isinstance(seats, int)
                                  or not MIN_SEATS <= seats <= MAX_SEATS):
            raise UiError(422, "bad_request", "The council takes 2 to 6 seats.")
        history = chats.history_block(chat_id) or ""
        user = chats.add_message(chat_id, "user", text.strip())
        asked = text.strip()
        given = b.get("searchResults")
        if isinstance(given, list) and given:
            # The desktop app ran the search in its own browser window and sent what it read.
            from council.web.search import results_block
            rows = [{"title": str(r.get("title") or "")[:160], "url": str(r.get("url") or "")[:300],
                     "snippet": str(r.get("snippet") or "")[:400]}
                    for r in given[:5] if isinstance(r, dict) and r.get("title")]
            block = results_block(rows)
            if block:
                asked = asked + NL2 + block
        elif b.get("search") is True:
            # No desktop shell (a plain browser tab): the engine tries one search itself. Search
            # sites often turn a program away; then there is no block and the council answers
            # from what it knows.
            from council.web.search import results_block, web_search
            block = results_block(await web_search(asked))
            if block:
                asked = asked + NL2 + block
        return await start_run(chat_id, asked, seats, history, user)

    @router.post("/chats/{chat_id}/regenerate")
    async def regenerate(chat_id: str) -> dict:
        need_chat(chat_id)
        last = chats.last_user_message(chat_id)
        if not last:
            raise UiError(409, "no_message", "There is no question to ask again.")
        seats = seats_of_last_run(chat_id)  # before the old answer is removed
        chats.remove_last_assistant(chat_id)
        text = str(last.get("text") or "")
        lines = (chats.history_block(chat_id) or "").split("\n")
        if lines and lines[-1].startswith("User: ") and text.strip().startswith(lines[-1][6:].rstrip(".")[:40]):
            lines.pop()  # the question itself follows the block
        history = "\n".join(lines) if len(lines) > 1 else ""
        return await start_run(chat_id, text, seats, history, None)

    # ------------------------------------------------------------------ runs

    def need_link(run_id: str) -> dict:
        link = ctrl.store.kv_get(NS_RUNS, run_id)
        if not link or ctrl.store.get_run(run_id) is None:
            raise UiError(404, "not_found", "That run does not exist.")
        return link

    @router.post("/runs/{run_id}/stop")
    async def stop_run(run_id: str) -> Response:
        link = need_link(run_id)
        if await ctrl.cancel(run_id):
            save(link["chatId"], link["messageId"], status="stopped",
                 error="Stopped before the council finished.")
        return Response(status_code=204)

    @router.get("/runs/{run_id}/events")
    async def run_events(run_id: str, request: Request) -> StreamingResponse:
        link = need_link(run_id)
        chat_id, message_id = link["chatId"], link["messageId"]

        async def frames() -> AsyncIterator[str]:
            tr = RunTranslator(run_id, message_id)
            for ev in tr.start():
                yield _frame(ev)
            async for frame in _engine_frames(ctrl, run_id, request):
                if not frame.startswith("id:"):
                    yield frame  # keepalive
                    continue
                try:
                    out = tr.feed(json.loads(frame.split("\ndata: ", 1)[1]))
                except Exception:
                    continue
                for ev in out:
                    yield _frame(ev)
            if tr.end is None:
                if ctrl.is_active(run_id):
                    return  # the reader went away; the run goes on
                tr.lost()
            yield _frame(tr.finish(save(chat_id, message_id, **tr.fields())))

        return StreamingResponse(frames(), media_type="text/event-stream", headers=SSE_HEADERS)

    @router.get("/runs/{run_id}/debate")
    async def run_debate(run_id: str, request: Request) -> StreamingResponse:
        if ctrl.store.get_run(run_id) is None:
            raise UiError(404, "not_found", "That run does not exist.")
        return StreamingResponse(debate_frames(ctrl, run_id, request),
                                 media_type="text/event-stream", headers=SSE_HEADERS)

    return router


__all__ = ["make_router", "RunTranslator", "UiError", "debate_frames", "seat_count", "seat_models",
           "NS_RUNS", "DEFAULT_SEATS"]
