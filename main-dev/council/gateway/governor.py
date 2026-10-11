"""Gateway governor (spec 7.2): per-model slots, distinct-model cap, priority."""
from __future__ import annotations

import asyncio
import itertools
from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal

Priority = Literal["interactive", "batch"]
_RANK = {"interactive": 0, "batch": 1}


class _Waiter:
    __slots__ = ("model_id", "rank", "seq", "fut")

    def __init__(self, model_id: str, rank: int, seq: int, fut: asyncio.Future):
        self.model_id = model_id
        self.rank = rank
        self.seq = seq
        self.fut = fut


class Governor:
    def __init__(self, slots: dict[str, int], max_concurrent_models: int, default_slots: int = 1):
        self._slots = dict(slots)
        self._max_models = max_concurrent_models
        self._default = default_slots
        self._in_flight: dict[str, int] = {}
        self._waiters: list[_Waiter] = []
        self._seq = itertools.count()

    def _limit(self, model_id: str) -> int:
        return self._slots.get(model_id, self._default)

    def _can_grant(self, model_id: str) -> bool:
        held = self._in_flight.get(model_id, 0)
        if held >= self._limit(model_id):
            return False
        if held == 0 and len(self._in_flight) >= self._max_models:
            return False
        return True

    def _dispatch(self) -> None:
        # Walk waiters by (priority, FIFO). A blocked waiter does not block others.
        for w in sorted(self._waiters, key=lambda x: (x.rank, x.seq)):
            if w.fut.done():
                self._waiters.remove(w)
                continue
            if self._can_grant(w.model_id):
                self._waiters.remove(w)
                self._in_flight[w.model_id] = self._in_flight.get(w.model_id, 0) + 1
                w.fut.set_result(None)

    def _release(self, model_id: str) -> None:
        n = self._in_flight.get(model_id, 0) - 1
        if n <= 0:
            self._in_flight.pop(model_id, None)
        else:
            self._in_flight[model_id] = n
        self._dispatch()

    @asynccontextmanager
    async def acquire(self, model_id: str, priority: Priority = "interactive") -> AsyncIterator[None]:
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        w = _Waiter(model_id, _RANK[priority], next(self._seq), fut)
        self._waiters.append(w)
        self._dispatch()
        try:
            await fut
        except BaseException:
            if fut.done() and not fut.cancelled():
                # Slot was granted before cancel landed; give it back.
                self._release(model_id)
            elif w in self._waiters:
                self._waiters.remove(w)
                self._dispatch()
            raise
        try:
            yield
        finally:
            self._release(model_id)

    def stats(self) -> dict:
        return {
            "in_flight": dict(self._in_flight),
            "queue_depth": sum(1 for w in self._waiters if not w.fut.done()),
            "active_models": list(self._in_flight),
        }

    def set_slots(self, model_id: str, n: int) -> None:
        self._slots[model_id] = n
        self._dispatch()
