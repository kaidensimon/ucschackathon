"""Host (spec 6): keeps models resident under the RAM budget."""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Callable

from council.core import event_types as ET
from council.core.schemas import ModelEntry
from council.host.ram import RamBudget, Resident


class HostError(Exception):
    pass


class Host:
    def __init__(
        self,
        driver: Any,
        ram: RamBudget,
        registry: list[ModelEntry],
        bus: Any,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.driver = driver
        self.ram = ram
        self.registry = {m.id: m for m in registry}
        self.bus = bus
        self.clock = clock
        self._resident: dict[str, Resident] = {}
        self._endpoints: dict[str, str] = {}
        self._seats: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()
        self._started = False

    async def _emit(self, type_: str, run_id: str, payload: dict) -> None:
        r = self.bus.emit(type_, run_id, payload)
        if inspect.isawaitable(r):
            await r

    async def start(self) -> None:
        await self.driver.start()
        self._started = True
        await self.adopt()

    async def adopt(self) -> None:
        """Take over models the server already has loaded (left by an earlier process).

        Without this a fresh process sees their memory as simply gone, plans a smaller
        council than fits, and never evicts them."""
        try:
            states = await self.driver.status()
        except Exception:  # noqa: BLE001
            return
        measured = await self._driver_footprints()
        for mid, state in (states or {}).items():
            if state != "loaded" or mid not in self.registry or mid in self._resident:
                continue
            footprint = measured.get(mid, 0.0)
            if footprint <= 0:
                try:
                    footprint = float(self.ram.footprint(mid, "live"))
                except Exception:  # noqa: BLE001
                    continue
            self._resident[mid] = Resident(mid, "live", footprint, True, self.clock())
            self._endpoints[mid] = self._driver_endpoint(mid)

    async def _driver_footprints(self) -> dict[str, float]:
        """GiB per loaded model as the driver measures it. {} when it cannot say."""
        fn = getattr(self.driver, "footprints", None)
        if fn is None:
            return {}
        try:
            res = fn()
            if inspect.isawaitable(res):
                res = await res
            return {str(k): float(v) for k, v in dict(res or {}).items()}
        except Exception:  # noqa: BLE001  measuring is best effort
            return {}

    async def _measure(self) -> None:
        """Replace table footprints of residents with what the driver measures."""
        for mid, gib in (await self._driver_footprints()).items():
            r = self._resident.get(mid)
            if r is not None and gib > 0:
                r.footprint_gib = gib

    def _driver_endpoint(self, mid: str) -> str:
        """Where an already loaded model answers: one URL per model (llama.cpp) or one for all."""
        for name in ("url_for", "endpoint_for"):
            fn = getattr(self.driver, name, None)
            if fn is None:
                continue
            try:
                url = fn(mid)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(url, str) and url:
                return url
        return str(getattr(self.driver, "base_url", "") or f"adopted://{mid}")

    async def stop(self) -> None:
        """Stop the driver (llama.cpp: every server process) and forget what was resident."""
        async with self._lock:
            try:
                await self.driver.stop()
            finally:
                self._resident.clear()
                self._endpoints.clear()
                self._started = False

    def is_seated(self, model_id: str) -> bool:
        """True when a run (or a bench) holds this model right now."""
        return any(model_id in seats for seats in self._seats.values())

    async def _drop_dead(self, run_id: str) -> None:
        """Forget residents whose server process died by itself (OOM, crash), so the next
        ensure_resident loads them again instead of handing out a dead URL."""
        fn = getattr(self.driver, "dead_models", None)
        if fn is None:
            return
        try:
            dead = fn()
            if inspect.isawaitable(dead):
                dead = await dead
        except Exception:  # noqa: BLE001
            return
        for mid in list(dead or []):
            if self._resident.pop(mid, None) is not None:
                self._endpoints.pop(mid, None)
                await self._emit(ET.MODEL_UNLOADED, run_id, {"model_id": mid})

    def _refresh_idle(self) -> None:
        seated = set().union(*self._seats.values()) if self._seats else set()
        for mid, r in self._resident.items():
            r.idle = mid not in seated

    async def ensure_resident(
        self,
        model_ids: list[str],
        profile: str,
        run_id: str,
        project: str | None = None,
    ) -> dict[str, str]:
        if not self._started:
            # First use in this process: learn what the server already holds, or every
            # load is judged against memory that looks full and cannot be reclaimed.
            await self.start()
        async with self._lock:
            out: dict[str, str] = {}
            wanted = list(dict.fromkeys(model_ids))
            admitted = False
            await self._drop_dead(run_id)
            # seat first so wanted models are never picked for eviction
            self._seats.setdefault(run_id, set()).update(wanted)
            self._refresh_idle()
            try:
                for mid in wanted:
                    cur = self._resident.get(mid)
                    if cur is not None and cur.profile == profile:
                        cur.last_used = self.clock()
                        out[mid] = self._endpoints[mid]
                        continue
                    if cur is not None:
                        await self._unload(mid, run_id, evicted=False)
                    out[mid] = await self._admit(mid, profile, run_id)
                    admitted = True
            except BaseException:
                self._seats[run_id] -= set(wanted)
                self._refresh_idle()
                raise
            self._refresh_idle()
            if admitted:
                await self._measure()
            return out

    async def load(self, model_id: str, profile: str, run_id: str = "manual") -> str:
        out = await self.ensure_resident([model_id], profile, run_id)
        return out[model_id]

    async def unload(self, model_id: str, run_id: str = "manual") -> None:
        async with self._lock:
            if model_id in self._resident:
                await self._unload(model_id, run_id, evicted=False)

    async def _unload(self, mid: str, run_id: str, evicted: bool) -> None:
        r = self._resident[mid]
        if evicted:
            await self._emit(
                ET.MODEL_EVICTED, run_id, {"model_id": mid, "footprint_gib": r.footprint_gib}
            )
        await self.driver.unload(mid)
        self._resident.pop(mid, None)
        self._endpoints.pop(mid, None)
        await self._emit(ET.MODEL_UNLOADED, run_id, {"model_id": mid})

    async def _admit(self, mid: str, profile: str, run_id: str) -> str:
        if mid not in self.registry:
            raise HostError(f"unknown model: {mid}")
        try:
            plan = self.ram.plan_admit(mid, profile, list(self._resident.values()))
        except KeyError as e:
            raise HostError(str(e)) from e
        if not plan.ok:
            await self._emit(
                ET.MODEL_FAILED, run_id, {"model_id": mid, "profile": profile, "error": plan.reason}
            )
            raise HostError(f"cannot admit {mid}: {plan.reason}")
        for ev in plan.evict:
            await self._unload(ev, run_id, evicted=True)
        footprint = self.ram.footprint(mid, profile)
        last_err: Exception | None = None
        for attempt in (1, 2):
            await self._emit(ET.MODEL_LOADING, run_id, {"model_id": mid, "profile": profile})
            try:
                endpoint = await self.driver.load(mid, profile)
            except Exception as e:  # noqa: BLE001
                last_err = e
                await self._emit(
                    ET.MODEL_FAILED,
                    run_id,
                    {"model_id": mid, "profile": profile, "error": str(e), "attempt": attempt},
                )
                continue
            self._resident[mid] = Resident(
                model_id=mid,
                profile=profile,
                footprint_gib=footprint,
                idle=False,
                last_used=self.clock(),
            )
            self._endpoints[mid] = endpoint
            await self._emit(
                ET.MODEL_LOADED,
                run_id,
                {"model_id": mid, "profile": profile, "endpoint": endpoint, "footprint_gib": footprint},
            )
            return endpoint
        raise HostError(f"load failed for {mid} after retry: {last_err}")

    def release(self, run_id: str) -> None:
        self._seats.pop(run_id, None)
        self._refresh_idle()

    def touch(self, model_id: str) -> None:
        r = self._resident.get(model_id)
        if r is not None:
            r.last_used = self.clock()

    def status(self) -> list[dict]:
        return [
            {
                "model_id": r.model_id,
                "profile": r.profile,
                "footprint_gib": r.footprint_gib,
                "idle": r.idle,
                "endpoint": self._endpoints.get(r.model_id),
            }
            for r in self._resident.values()
        ]

    def endpoint_for(self, model_id: str) -> str | None:
        """Base URL the driver returned for this model (the Gateway asks here), or None."""
        return self._endpoints.get(model_id)

    endpoint = endpoint_for

    def endpoints(self) -> dict[str, str]:
        return dict(self._endpoints)

    async def set_steering(self, model_id: str, path: Any, scale: float = 1.0) -> bool:
        """Put a steering vector on a model (path None = take it off).

        False when the driver cannot steer. A driver that restarts the server may hand
        back a new URL: it replaces the endpoint. Driver errors are raised."""
        fn = getattr(self.driver, "set_steering", None)
        if fn is None:
            return False
        async with self._lock:
            res = fn(model_id, path, scale)
            if inspect.isawaitable(res):
                res = await res
            if isinstance(res, str) and "://" in res and model_id in self._resident:
                self._endpoints[model_id] = res
        return True

    async def render(self, model_id: str, messages: list[dict]) -> str | None:
        """The prompt text the model's chat template makes of messages. None: driver cannot."""
        fn = getattr(self.driver, "render", None)
        if fn is None:
            return None
        res = fn(model_id, messages)
        if inspect.isawaitable(res):
            res = await res
        return res


def build_driver(config: Any, registry: list[ModelEntry]) -> Any:
    """Pick the host driver from config. Kept here for callers; lives in drivers.py."""
    from council.host.drivers import build_driver as _build

    return _build(config, registry)
