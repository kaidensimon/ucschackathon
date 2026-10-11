"""Executors that drive a Deliberation (spec 10.12, 18.3).

LiveExecutor  - one deliberation, calls run in parallel as they are asked for. The debate is
                stopped when only the engine's Chair reserve (chair_reserve_s()) is left of the
                deadline; the engine is told the time really left, so the Chair gets it.
BatchExecutor - many deliberations, model-major: one model's calls for all tasks, then the next.

The Deliberation emits evidence.requested / evidence.result itself (it owns the check ids), so
these executors only forward the events it returns. They never emit those two a second time.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Awaitable, Callable, Optional

from council.core.schemas import CallResult, CallSpec, CheckRequest, Decision, EvidenceResult

NOT_RUN = "not run: no evidence runner"


async def _maybe(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _parse_call_id(call_id: str) -> tuple[Optional[int], Optional[int]]:
    """(seat_no, round) from "<run_id>:<round>:<seat_no>", else (None, None)."""
    parts = (call_id or "").split(":")
    if len(parts) < 3:
        return None, None
    seat_txt = parts[-1].split("#", 1)[0]
    try:
        return int(seat_txt), int(parts[-2])
    except ValueError:
        return None, None


def _failed(call_id: str, model_id: Optional[str], error: str) -> CallResult:
    return CallResult(call_id=call_id, ok=False, model_id=model_id, error=error)  # type: ignore[arg-type]


def _not_run(check: CheckRequest) -> EvidenceResult:
    return EvidenceResult(
        kind=check.kind, spec=check.spec, settles=check.settles, ok=False, error=NOT_RUN
    )


async def _emit_all(bus: Any, run_id: str, events: list) -> None:
    if bus is None:
        return
    for type_, payload in events:
        await _maybe(bus.emit(type_, run_id, payload))


def _chair_reserve(delib: Any) -> float:
    """Seconds the engine keeps back for the Chair. 0 for an engine that has no such reserve."""
    fn = getattr(delib, "chair_reserve_s", None)
    if not callable(fn):
        return 0.0
    try:
        return max(0.0, float(fn()))
    except Exception:
        return 0.0


def _on_deadline(delib: Any, remaining: float) -> list:
    """Tell the engine the debate is over. It is told the time really left when it takes it."""
    fn = delib.on_deadline
    try:
        takes_time = bool(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        takes_time = False
    return fn(max(0.0, remaining)) if takes_time else fn()


class LiveExecutor:
    def __init__(
        self,
        gateway: Any,
        bus: Any,
        clock: Callable[[], float] = time.monotonic,
        evidence_runner: Callable[[CheckRequest], Awaitable[EvidenceResult]] | None = None,
    ) -> None:
        self.gateway = gateway
        self.bus = bus
        self.clock = clock
        self.evidence_runner = evidence_runner

    async def _call(self, spec: CallSpec) -> CallResult:
        seat_no, round_ = _parse_call_id(spec.call_id)
        try:
            return await self.gateway.call(spec, seat_no=seat_no, round=round_)
        except asyncio.CancelledError:
            raise
        except Exception:
            return _failed(spec.call_id, spec.model_id, "server_error")

    async def _check(self, check: CheckRequest) -> EvidenceResult:
        if self.evidence_runner is None:
            return _not_run(check)
        try:
            return await self.evidence_runner(check)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            res = _not_run(check)
            return res.model_copy(update={"error": f"runner failed: {exc}"[:300]})

    async def run(self, delib: Any, run_id: str, deadline_s: float) -> Decision:
        start = self.clock()
        deadline_hit = False
        calls: dict[asyncio.Task, CallSpec] = {}
        checks: dict[asyncio.Task, Any] = {}
        stalled = False

        async def flush(events: list) -> None:
            await _emit_all(self.bus, run_id, events)

        try:
            await flush(delib.take_events())
            while not delib.is_done():
                remaining = deadline_s - (self.clock() - start)
                delib.set_remaining(remaining)
                for spec in delib.pending_calls():
                    calls[asyncio.ensure_future(self._call(spec))] = spec
                for check in delib.pending_checks():
                    checks[asyncio.ensure_future(self._check(check))] = check
                # events buffered by the engine (e.g. evidence.requested) go out now
                await flush(delib.take_events())
                if delib.is_done():
                    break

                # The debate ends when only the Chair reserve is left, so that a Chair that is
                # needed still has its time. In the Chair phase the reserve is 0.
                debate_left = remaining - _chair_reserve(delib)
                if not deadline_hit and debate_left <= 0:
                    deadline_hit = True
                    await flush(_on_deadline(delib, remaining))
                    await self._cancel_orphans(delib, calls)
                    continue

                inflight = set(calls) | set(checks)
                if not inflight:
                    # Nothing out and not done. Force progress once, then give up.
                    if stalled:
                        raise RuntimeError("deliberation stalled with no work in flight")
                    stalled = True
                    deadline_hit = True
                    await flush(_on_deadline(delib, remaining))
                    continue
                stalled = False

                timeout = None if deadline_hit else max(0.0, debate_left)
                done, _ = await asyncio.wait(
                    inflight, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    if task in calls:
                        calls.pop(task)
                        if task.cancelled():
                            continue
                        await flush(delib.on_result(task.result()))
                    else:
                        check = checks.pop(task)
                        if task.cancelled():
                            continue
                        pending_id = getattr(check, "check_id", "")
                        await flush(delib.on_evidence(pending_id, task.result()))
        finally:
            leftovers = list(calls) + list(checks)
            for task in leftovers:
                task.cancel()
            if leftovers:
                await asyncio.gather(*leftovers, return_exceptions=True)
        return delib.decision()

    async def _cancel_orphans(self, delib: Any, calls: dict) -> None:
        """Cancel calls the engine no longer waits on. A Chair or ratify call that is out stays."""
        waiting = getattr(delib, "_waiting", None)
        if waiting is None:
            return
        gone = [t for t, spec in calls.items() if spec.call_id not in waiting]
        for task in gone:
            task.cancel()
            calls.pop(task, None)
        if gone:
            await asyncio.gather(*gone, return_exceptions=True)


class BatchExecutor:
    """Model-major loop of 18.3. `host` may have load(model, profile) / unload(model), sync or async."""

    def __init__(
        self,
        gateway: Any,
        host: Any = None,
        bus: Any = None,
        evidence_runner: Callable[[CheckRequest], Awaitable[EvidenceResult]] | None = None,
    ) -> None:
        self.gateway = gateway
        self.host = host
        self.bus = bus
        self.evidence_runner = evidence_runner

    async def _host(self, name: str, *args: Any) -> None:
        fn = getattr(self.host, name, None) if self.host is not None else None
        if fn is not None:
            await _maybe(fn(*args))

    async def _run_group(self, specs: list[CallSpec]) -> list[CallResult]:
        try:
            if hasattr(self.gateway, "call_many"):
                results = list(await _maybe(self.gateway.call_many(specs)))
            else:
                results = list(await asyncio.gather(*[self.gateway.call(s) for s in specs]))
        except Exception:
            return [_failed(s.call_id, s.model_id, "server_error") for s in specs]
        by_id = {r.call_id: r for r in results}
        out = []
        for i, spec in enumerate(specs):
            res = by_id.get(spec.call_id)
            if res is None and len(results) == len(specs):
                res = results[i]
            out.append(res or _failed(spec.call_id, spec.model_id, "server_error"))
        return out

    async def _check(self, check: CheckRequest) -> EvidenceResult:
        if self.evidence_runner is None:
            return _not_run(check)
        try:
            return await self.evidence_runner(check)
        except Exception as exc:
            res = _not_run(check)
            return res.model_copy(update={"error": f"runner failed: {exc}"[:300]})

    async def run_many(self, delibs: list) -> list[Decision]:
        for d in delibs:
            await _emit_all(self.bus, d.run_id, d.take_events())
        stalled = False
        while any(not d.is_done() for d in delibs):
            owner: dict[str, Any] = {}
            groups: dict[str, list[CallSpec]] = {}
            for d in delibs:
                if d.is_done():
                    continue
                for spec in d.pending_calls():
                    owner[spec.call_id] = d
                    groups.setdefault(spec.model_id, []).append(spec)
            progressed = bool(groups)

            for model_id, specs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
                await self._host("load", model_id, "batch")
                results = await self._run_group(specs)
                for res in results:
                    d = owner[res.call_id]
                    await _emit_all(self.bus, d.run_id, d.on_result(res))
                await self._host("unload", model_id)

            for d in delibs:
                if d.is_done():
                    continue
                for check in d.pending_checks():
                    progressed = True
                    res = await self._check(check)
                    await _emit_all(
                        self.bus, d.run_id, d.on_evidence(getattr(check, "check_id", ""), res)
                    )
                await _emit_all(self.bus, d.run_id, d.take_events())

            if not progressed and any(not d.is_done() for d in delibs):
                if stalled:
                    raise RuntimeError("deliberations stalled with no work pending")
                stalled = True
                for d in delibs:
                    if not d.is_done():
                        await _emit_all(self.bus, d.run_id, d.on_deadline())
            else:
                stalled = False
        return [d.decision() for d in delibs]


__all__ = ["LiveExecutor", "BatchExecutor"]
