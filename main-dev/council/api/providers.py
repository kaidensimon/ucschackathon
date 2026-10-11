"""Real providers for the 1.5 routes (lie_routes.LieProvider, system_routes.SystemProvider).

Thin glue: each method calls the module that owns the work and turns its answer into the
route's shape. Anything that is not there yet (a service method another module adds later)
is looked up with getattr and degrades to "nothing", never a crash.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import HTTPException

from council.bench import sample_tasks
from council.core import config as config_mod
from council.core import event_types as ET
from council.core.schemas import BenchTask, ModelEntry, Probe
from council.core.schemas_v15 import DraftPair, LieReport, MeasuredModel, MemoryPlan, ProbeCard
from council.host import meminfo, memplan, model_checks, specdec
from council.probe import lie_report as lie_report_mod
from council.probe import train_all as train_all_mod
from council.probe.probe_files import ProbeFiles
from council.router.roles import assign_roles
from council.telemetry import model_cards

_PAGE = 5000


def run_events(store: Any, run_id: str) -> list[Any]:
    """Every stored event of one run, oldest first (Event objects)."""
    out: list[Any] = []
    since = 0
    while True:
        page = store.events_since(run_id, since, limit=_PAGE)
        out.extend(page)
        if len(page) < _PAGE:
            return out
        since = page[-1].seq


def _as_report(raw: Any) -> Optional[LieReport]:
    if raw is None:
        return None
    if isinstance(raw, LieReport):
        return raw
    try:
        return LieReport.model_validate(raw)
    except Exception:  # noqa: BLE001 - a bad report is "no report"
        return None


def card_from_probe(probe: Probe, source: str = "mock", now: float = 0.0) -> ProbeCard:
    """A trained core Probe as a ProbeCard. Active means the trainer validated it."""
    active = probe.status == "validated"
    return ProbeCard(
        model_id=probe.model_id,
        source=source if source in ("mock", "ollama_embed", "llamacpp") else "mock",
        layers=[int(probe.layer)], auroc=float(probe.auroc), n_train=int(probe.n_train),
        trained_at=float(probe.trained_at or now), active=active,
        reason="validated" if active else f"status {probe.status}",
    )


class LieProviderImpl:
    """LieProvider over the reliability service, the probe files and the run events."""

    def __init__(
        self,
        service: Any,
        probe_files: Optional[ProbeFiles] = None,
        store: Any = None,
        registry: Optional[list[ModelEntry]] = None,
        source: str = "mock",
        now: Callable[[], float] = time.time,
        busy: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.busy = busy  # True while a council run or a bench holds models in memory
        self.service = service
        self.files = probe_files
        self.store = store
        self.registry = list(registry or [])
        self.source = source
        self.now = now
        self._lock = asyncio.Lock()  # each training holds a full model copy: one at a time

    # ------------------------------------------------------------------ reads

    def lie_report(self, run_id: str) -> Optional[LieReport]:
        fn = getattr(self.service, "last_report", None)
        if callable(fn):
            try:
                found = _as_report(fn(run_id))
            except Exception:  # noqa: BLE001
                found = None
            if found is not None:
                return found
        return self._report_from_events(run_id)

    def _report_from_events(self, run_id: str) -> Optional[LieReport]:
        """Fallback: the newest lie.report event of the run."""
        if self.store is None:
            return None
        try:
            events = run_events(self.store, run_id)
        except Exception:  # noqa: BLE001
            return None
        for ev in reversed(events):
            if ev.type == ET.LIE_REPORT:
                rep = _as_report((ev.payload or {}).get("report"))
                if rep is not None:
                    return rep
        return None

    def report_text(self, run_id: str) -> Optional[str]:
        rep = self.lie_report(run_id)
        return lie_report_mod.report_text(rep) if rep is not None else None

    def probe_cards(self) -> list[ProbeCard]:
        fn = getattr(self.service, "cards", None)
        if callable(fn):
            try:
                return list(fn())
            except Exception:  # noqa: BLE001
                pass
        return self.files.cards() if self.files is not None else []

    # ------------------------------------------------------------------ writes

    def _need_known(self, model_id: str) -> None:
        if self.registry and model_id not in {m.id for m in self.registry}:
            raise HTTPException(404, f"model not found: {model_id}")

    async def train(self, model_id: str) -> ProbeCard:
        self._need_known(model_id)
        train_for = getattr(self.service, "train_for", None)
        if train_for is None or getattr(self.service, "source", None) is None:
            raise HTTPException(409, "the probe is off, or this setup has no activation source")
        if self.source == "llamacpp" and self.busy is not None and self.busy():
            # The real source loads its own full copy of the model, outside the Host RAM budget.
            raise HTTPException(409, "a run is active: train the probe when the council is idle")
        tasks = [BenchTask.model_validate(row) for row in sample_tasks.generate()]
        async with self._lock:
            now = self.now()
            probe = await train_for(model_id, tasks, now)
        card = card_from_probe(probe, self.source, now)
        if self.files is not None:
            try:
                card = self.files.save(card, [probe])
            except Exception:  # noqa: BLE001 - the kv copy is already stored
                pass
        return card

    async def train_all(self) -> list[ProbeCard]:
        ids = [m.id for m in self.registry if m.status == "active" and "seat" in m.roles]
        return await train_all_mod.train_models(ids, self.train)

    def set_active(self, model_id: str, active: bool) -> Optional[ProbeCard]:
        if self.files is None:
            return None
        card = next((c for c in self.files.cards() if c.model_id == model_id), None)
        if card is None:
            return None
        if not self.files.set_active(model_id, card.version if active else None):
            return None
        return card.model_copy(update={"active": bool(active)})


class SystemProviderImpl:
    """SystemProvider over the host, the registry and the on-box check file.

    deps is the RunController (or anything with host, registry, config, data_home)."""

    def __init__(self, deps: Any, probe_cards: Optional[Callable[[], list[ProbeCard]]] = None) -> None:
        self.deps = deps
        self._probe_cards = probe_cards

    def _registry(self) -> list[ModelEntry]:
        return list(getattr(self.deps, "registry", None) or [])

    def _status(self) -> list[dict]:
        try:
            return list(self.deps.host.status())
        except Exception:  # noqa: BLE001
            return []

    def _home(self) -> Path:
        home = getattr(self.deps, "data_home", None)
        return Path(home) if home is not None else config_mod.home()

    def _cfg_memory(self) -> Any:
        return getattr(getattr(self.deps, "config", None), "memory", None)

    def measured(self) -> dict[str, MeasuredModel]:
        mem = self._cfg_memory()
        raw = str(getattr(mem, "measured_file", "") or "")
        path = Path(raw).expanduser() if raw else model_checks.default_path(self._home())
        return model_checks.by_model_id(model_checks.load_checks(path), self._registry())

    def _cards_of_probes(self) -> list[ProbeCard]:
        if self._probe_cards is not None:
            try:
                return list(self._probe_cards())
            except Exception:  # noqa: BLE001
                return []
        try:
            return ProbeFiles(self._home()).cards()
        except Exception:  # noqa: BLE001
            return []

    def model_cards(self) -> list[dict]:
        return model_cards.build_cards(
            self._registry(), self.measured(), None, self._cards_of_probes(),
            {r["model_id"] for r in self._status()},
        )

    def meminfo(self) -> dict:
        info = meminfo.read_meminfo()
        return {
            "total_gib": round(info.get("MemTotal", 0) / meminfo.KB_PER_GIB, 2),
            "available_gib": round(meminfo.available_gib(info), 2),
            "used_gib": round(meminfo.used_gib(info), 2),
            "swap_used_gib": round(meminfo.swap_used_gib(info), 2),
        }

    def memory_plan(self) -> MemoryPlan:
        registry = {m.id: m for m in self._registry()}
        status = self._status()
        seats = [r["model_id"] for r in status if r["model_id"] in registry]
        mem = self._cfg_memory()
        reserve = float(getattr(mem, "reserve_gib", 10.0))
        overhead = float(getattr(mem, "overhead", 1.35))
        ctx = int(getattr(getattr(self.deps.config, "ollama", None), "num_ctx_live", 16384) or 16384)
        measured = self.measured()
        gib: dict[str, float] = {}
        for r in status:
            if r.get("footprint_gib"):
                gib[r["model_id"]] = float(r["footprint_gib"])
        for mid in seats:
            m = measured.get(mid)
            if mid in gib or m is None:
                continue
            if m.ram_gib:
                gib[mid] = float(m.ram_gib)
            elif m.reported_gib:
                gib[mid] = float(m.reported_gib) * overhead
        roles = assign_roles(seats, registry, {}, False) if seats else {}
        total = self.meminfo()["total_gib"]
        plan = memplan.plan_memory(
            seats, dict(roles), gib, total, reserve_gib=reserve, overhead=overhead,
            ctx_default=ctx, ctx_steps=tuple(s for s in (16384, 8192, 4096) if s <= ctx) or (ctx,),
        )
        if not seats:
            plan.notes.append("No model is resident, so there is nothing to plan.")
        return plan

    def draft_pairs(self) -> list[DraftPair]:
        return specdec.propose_pairs([m for m in self._registry() if m.status == "active"])


def steer_cards(deps: Any) -> list[dict]:
    """Cards from council/steer/store.SteerStore when that module exists, else []."""
    try:
        from council.steer.store import SteerStore  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - module not written yet
        return []
    try:
        home = getattr(deps, "data_home", None) or config_mod.home()
        try:
            store = SteerStore(Path(home))
        except TypeError:
            store = SteerStore()
        fn = getattr(store, "cards", None) or getattr(store, "list_cards", None)
        rows = list(fn()) if callable(fn) else []
        return [r.model_dump(mode="json") if hasattr(r, "model_dump") else dict(r) for r in rows]
    except Exception:  # noqa: BLE001
        return []


__all__ = ["LieProviderImpl", "SystemProviderImpl", "card_from_probe", "run_events", "steer_cards"]
