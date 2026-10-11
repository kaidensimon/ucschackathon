"""SSE helpers for GET /runs/{id}/events (spec 17): framing, cursor parsing, and the loop
that turns an event subscription into frames with keepalives."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from typing import Any, AsyncIterator, Callable, Iterable, Optional

from council.core.schemas import Event

_INT_RE = re.compile(r"^\d+$")


def format_sse(event: Event) -> str:
    """One event frame: id, event name, and the full envelope as JSON in data."""
    data = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
    return f"id: {event.seq}\nevent: {event.type}\ndata: {data}\n\n"


def keepalive() -> str:
    """SSE comment line that keeps the connection open."""
    return ": ping\n\n"


async def stream_frames(
    events: AsyncIterator[Event],
    keepalive_s: float = 15.0,
    poll_s: float = 0.25,
    should_stop: Optional[Callable[[], Any]] = None,
    terminal: Iterable[str] = (),
) -> AsyncIterator[str]:
    """SSE frames of an event subscription (EventBus.subscribe), with keepalive comments.

    Ends when the subscription ends or right after an event whose type is in `terminal`.
    Every `poll_s` without an event, `should_stop()` (plain or async) is asked; true ends the
    stream. After `keepalive_s` without an event one keepalive comment goes out.
    The pending read is never cancelled by a timeout, so no event is lost.
    """
    terminal = frozenset(terminal)
    it = events.__aiter__()
    pending: Optional[asyncio.Future] = None
    idle = 0.0
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(it.__anext__())
            wait_s = max(0.001, min(poll_s, keepalive_s - idle))
            done, _ = await asyncio.wait({pending}, timeout=wait_s)
            if not done:
                idle += wait_s
                if should_stop is not None:
                    stop = should_stop()
                    if inspect.isawaitable(stop):
                        stop = await stop
                    if stop and not pending.done():
                        return
                if idle >= keepalive_s:
                    idle = 0.0
                    yield keepalive()
                continue
            task, pending = pending, None
            try:
                ev = task.result()
            except StopAsyncIteration:
                return
            idle = 0.0
            yield format_sse(ev)
            if ev.type in terminal:
                return
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            try:
                await pending
            except (asyncio.CancelledError, StopAsyncIteration, Exception):
                pass
        close = getattr(it, "aclose", None)
        if close is not None:
            try:
                await close()
            except Exception:
                pass


def _as_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not _INT_RE.match(text):
        return None
    return int(text)


def parse_since(query_value: str | None, last_event_id: str | None) -> int:
    """The larger valid integer of ?since= and Last-Event-ID. 0 on garbage."""
    candidates = [v for v in (_as_int(query_value), _as_int(last_event_id)) if v is not None]
    return max(candidates, default=0)
