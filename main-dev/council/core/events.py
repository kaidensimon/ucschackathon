"""EventBus (spec 16.3): validate, persist, fan out.

emit() is called from the event loop thread. Each subscriber owns an asyncio.Queue.
Streamed token events (EPHEMERAL_EVENTS) are never stored; they carry the last persisted
seq of their run and reach live subscribers only.
"""

from __future__ import annotations

import inspect
import time
from typing import Any, AsyncIterator, Callable, Optional

import asyncio

from pydantic import BaseModel

from council.core.event_types import EPHEMERAL_EVENTS, TERMINAL_EVENTS, validate_payload
from council.core.schemas import Event

_PAGE = 5000


class EventBus:
    def __init__(self, store: Any) -> None:
        self.store = store
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._listeners: list[Callable[[Event], None]] = []
        self._last_seq: dict[str, int] = {}

    # ---------------------------------------------------------------- listeners

    def add_listener(self, fn: Callable[[Event], None]) -> Callable[[], None]:
        """Synchronous tap, called for every emitted event. Returns a remover."""
        self._listeners.append(fn)

        def remove() -> None:
            if fn in self._listeners:
                self._listeners.remove(fn)

        return remove

    # --------------------------------------------------------------------- emit

    def _known_last_seq(self, run_id: str) -> int:
        seq = self._last_seq.get(run_id)
        if seq is not None:
            return seq
        seq = 0
        try:
            while True:
                page = self.store.events_since(run_id, seq, limit=_PAGE)
                if inspect.isawaitable(page):
                    close = getattr(page, "close", None)
                    if close:
                        close()
                    break
                if not page:
                    break
                seq = max(seq, max(e.seq for e in page))
                if len(page) < _PAGE:
                    break
        except Exception:
            pass
        self._last_seq[run_id] = seq
        return seq

    def emit(self, type: str, run_id: str, payload: "dict | BaseModel | None" = None) -> Event:
        model = validate_payload(type, {} if payload is None else payload)
        data = model.model_dump(mode="json")
        if type in EPHEMERAL_EVENTS:
            event = Event(
                type=type,
                seq=self._known_last_seq(run_id),
                ts=time.time(),
                run_id=run_id,
                payload=data,
            )
        else:
            event = self.store.append_event(run_id, type, data)
            if event.seq > self._last_seq.get(run_id, 0):
                self._last_seq[run_id] = event.seq
        for fn in list(self._listeners):
            try:
                fn(event)
            except Exception:
                pass
        for q in list(self._subs.get(run_id, ())):
            q.put_nowait(event)
        return event

    # ---------------------------------------------------------------- subscribe

    async def subscribe(self, run_id: str, since: int = 0) -> AsyncIterator[Event]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subs.setdefault(run_id, []).append(queue)
        try:
            last = since
            while True:
                page = self.store.events_since(run_id, last, limit=_PAGE)
                if inspect.isawaitable(page):
                    page = await page
                for ev in page:
                    if ev.seq <= last:
                        continue
                    last = ev.seq
                    yield ev
                    if ev.type in TERMINAL_EVENTS:
                        return
                if len(page) < _PAGE:
                    break
            while True:
                ev = await queue.get()
                if ev.type not in EPHEMERAL_EVENTS:
                    if ev.seq <= last:
                        continue
                    last = ev.seq
                yield ev
                if ev.type in TERMINAL_EVENTS:
                    return
        finally:
            subs = self._subs.get(run_id)
            if subs and queue in subs:
                subs.remove(queue)
                if not subs:
                    del self._subs[run_id]


__all__ = ["EventBus"]
