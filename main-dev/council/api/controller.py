"""RunController (spec 2, 16.4, 17): owns the life of a run.

Two paths behind start():
  demo  - options["demo"] true. Replays council.api.demo_script through the bus, delays divided
          by `speed`, pausing at the delegate marker until delegate() (or options.auto_delegate).
  real  - INTAKE here, then council.api.run_pipeline.RunPipeline walks every later state. The
          controller is the pipeline's RunControl: it emits the state changes, waits for the
          delegate click and for user answers, and reports cancellation.

build_mock() wires every component in mock mode. build_from_config() reads config.gateway.mock
and builds the mock or the real stack (driver from host.build_driver: llamacpp, ollama or mock;
real gateway, which asks the host for each model's URL and, where the driver knows it, for the
context the model was loaded with).
1.5 services, all under data_home: probe_files (ProbeFiles), steer_store (SteerStore) and steer
(SteerService on the probe's activation source; no source, no service). The service renders with
host.render (a driver without a chat template gets the plain text of the chat) and generates by
putting the vector on the model (host.set_steering, reload) and asking the gateway at batch
priority. steer_live {model id: (path, scale) | None} is what each model runs with; the pipeline
shares it.
Data that lives on disk (corrections/, runs/, bench/) goes under `data_home`. With an in-memory
database and no data_home given, that is a temp folder removed at shutdown.

failed_models {model id: error} lists the models that could not be loaded in this process. The
pipeline never seats them again, and their entry in `registry` has status "failed".

Every state change emits run.state_changed and persists the folded snapshot. A failure emits
run.failed and never escapes the run task.

Action methods (start, delegate, cancel, submit_input, wait, shutdown) are coroutines.
start_bench and train_probe are coroutines too. Everything else is a plain call.
Unknown run or bench -> RunNotFound (a KeyError). Wrong state -> InvalidState (a ValueError).
A user plan edit that fails lint -> PlanRejected (an InvalidState with .issues).
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import shutil
import tempfile
import time
import traceback
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from council.api.demo_script import BUILTIN_MODELS, WAIT_DELEGATE, demo_events
from council.api.run_pipeline import RunDeps, RunPipeline, apply_steering
from council.bench import sample_tasks
from council.bench.runner import BenchRunner
from council.chamber.evidence import EvidenceRunner
from council.chronicle.corrections import CorrectionBook
from council.chronicle.reflect import Reflector
from council.chronicle.service import Chronicle
from council.core import config as config_mod
from council.core import event_types as ET
from council.core.events import EventBus
from council.core.schemas import (
    BenchRunRequest,
    BenchTask,
    CallSpec,
    ClaimScore,
    Correction,
    Crux,
    Decision,
    Event,
    EvidenceResult,
    LineupRecord,
    MeasuredStats,
    ModelEntry,
    Option,
    Plan,
    Probe,
    ResidentModel,
    RunCounters,
    RunRequest,
    RunSnapshot,
    RunState,
    TaskProfile,
    TaskStatus,
    TelemetrySnapshot,
    TribunalOutcome,
    UserInput,
    UserQuestion,
    WorkReport,
)
from council.core.store import Store
from council.core.util import new_id
from council.core.workspace import runs_dir
from council.gateway.embedder import MockEmbedder
from council.gateway.gateway import Gateway
from council.gateway.mock import MockResponder
from council.host import host as host_mod
from council.host import meminfo
from council.host.drivers import MockDriver
from council.host.host import Host
from council.host.ram import RamBudget
from council.probe import service as probe_service
from council.probe.activations import MockActivationSource
from council.probe.ledger import ClaimLedger
from council.probe.llamacpp_source import render_text
from council.probe.probe_files import ProbeFiles
from council.probe.service import ReliabilityService
from council.router import picker
from council.router.competence import SkillTable
from council.router.profiler import heuristic_profile
from council.steer.service import SteerService
from council.steer.store import SteerStore
from council.telemetry.sampler import FakeSampler, Sampler, default_gpu_reader
from council.works.foreman import Foreman

NEXT_PHASE_NOTE = (
    "Deliberation is complete. Planning and execution of this decision arrive in the next phase."
)
TERMINAL_STATES = (RunState.DONE, RunState.FAILED, RunState.CANCELLED)

_MOCK_TOTAL_GIB = 121.7
_MOCK_SYSTEM_GIB = 6.4
_FALLBACK_BUDGET_GIB = 64.0
_PAGE = 5000
_BENCH_ACTIVE = ("queued", "running")
_WEIGHTS_PREFIX = probe_service.WEIGHTS_KEY
_STEER_RUN = "steer"  # the host seat name of a steering sanity check

_TASK_STATUS = {
    ET.TASK_QUEUED: TaskStatus.queued,
    ET.TASK_STARTED: TaskStatus.running,
    ET.TASK_ESCALATED: TaskStatus.queued,
    ET.TASK_PASSED: TaskStatus.passed,
    ET.TASK_FAILED: TaskStatus.failed,
    ET.TASK_BLOCKED: TaskStatus.blocked,
    ET.TASK_SKIPPED: TaskStatus.skipped,
}


class RunNotFound(KeyError):
    pass


class InvalidState(ValueError):
    pass


class PlanRejected(InvalidState):
    """A user plan edit that still has lint errors. Nothing was stored."""

    def __init__(self, message: str, issues: Optional[list] = None) -> None:
        super().__init__(message)
        self.issues = list(issues or [])


def _quiet(type_: str, payload: Any = None) -> None:
    """Emit target of the shared services; the pipeline rebinds emit per run."""


class _MockProbeSource(MockActivationSource):
    """The mock activation source of the controller. The bootstrap lie prompt of 28.4 carries
    its own mark (activations.lie_messages), so the plain mock source already sees it."""


# --------------------------------------------------------------------------------------
# Snapshot fold (pure)
# --------------------------------------------------------------------------------------


def _state(value: Any) -> Optional[RunState]:
    try:
        return RunState(value) if value is not None else None
    except ValueError:
        return None


def _count_tasks(snap: RunSnapshot) -> None:
    c = snap.counters
    values = list(snap.task_statuses.values())
    c.tasks_total = len(values)
    c.tasks_passed = values.count(TaskStatus.passed)
    c.tasks_failed = values.count(TaskStatus.failed)
    c.tasks_blocked = values.count(TaskStatus.blocked)
    c.tasks_skipped = values.count(TaskStatus.skipped)


def _end(snap: RunSnapshot, ev: Event, p: dict, state: RunState) -> None:
    snap.state = state
    snap.pending_input = None
    snap.finished_at = p.get("finished_at") or ev.ts
    given = p.get("counters") or {}
    if given.get("calls") or given.get("tokens_out"):
        phase_ms = dict(snap.counters.phase_ms)
        snap.counters = RunCounters.model_validate(given)
        if phase_ms:
            snap.counters.phase_ms = phase_ms


def fold_event(snap: RunSnapshot, ev: Event) -> None:
    """Apply one stored event to a snapshot, in place."""
    t, p, c = ev.type, ev.payload or {}, snap.counters
    snap.last_seq = max(snap.last_seq, ev.seq)
    snap.updated_at = ev.ts

    if t == ET.RUN_CREATED:
        snap.task = p.get("task") or snap.task
        snap.workspace = p.get("workspace")
        snap.mode = p.get("mode") or snap.mode
        snap.deliverable = p.get("deliverable")
        snap.created_at = p.get("created_at") or ev.ts
    elif t == ET.RUN_STATE_CHANGED:
        to, frm = _state(p.get("to_state")), _state(p.get("from_state"))
        if to is None:
            return
        if to == RunState.AWAITING_USER:
            snap.prev_state = frm
        elif snap.state == RunState.AWAITING_USER:
            snap.prev_state = None
        snap.state = to
        snap.round = max(snap.round, int(p.get("round") or 0))
        c.review_cycles = max(c.review_cycles, int(p.get("review_cycle") or 0))
        ms = p.get("phase_ms")
        if frm is not None and isinstance(ms, (int, float)) and ms > 0:
            c.phase_ms[frm.value] = round(c.phase_ms.get(frm.value, 0.0) + float(ms), 1)
    elif t == ET.PROFILE_READY:
        if p.get("profile"):
            snap.profile = TaskProfile.model_validate(p["profile"])
            if snap.deliverable is None:
                snap.deliverable = snap.profile.deliverable
    elif t == ET.ROUTER_LINEUP_SELECTED:
        if p.get("lineup"):
            snap.lineup = LineupRecord.model_validate(p["lineup"])
    elif t == ET.SEAT_ASSIGNED:
        if snap.lineup is not None and p.get("replaces_model_id"):
            for seat in snap.lineup.seats:
                if seat.seat_no == p.get("seat_no"):
                    seat.model_id = p.get("model_id") or seat.model_id
    elif t == ET.ROUND_STARTED:
        snap.round = int(p.get("round") or 0)
    elif t in (ET.OPTIONS_CLUSTERED, ET.ROUND_COMPLETED):
        if p.get("options"):
            snap.options = [Option.model_validate(o) for o in p["options"]]
        if p.get("tally"):
            snap.tally = {str(k): int(v) for k, v in p["tally"].items()}
        if t == ET.ROUND_COMPLETED:
            c.rounds_run += 1
    elif t in (ET.CONSENSUS_REACHED, ET.CONSENSUS_FAILED):
        if p.get("tally"):
            snap.tally = {str(k): int(v) for k, v in p["tally"].items()}
    elif t == ET.CRUXES_EXTRACTED:
        snap.cruxes = [Crux.model_validate(x) for x in p.get("cruxes") or []]
    elif t == ET.EVIDENCE_RESULT:
        if p.get("result"):
            snap.evidence.append(EvidenceResult.model_validate(p["result"]))
        if p.get("crux_resolved"):
            for crux in snap.cruxes:
                if crux.id == p.get("crux_id"):
                    crux.resolved = True
                    crux.resolved_by = p.get("check_id") or crux.resolved_by
    elif t == ET.DECISION_FINAL:
        if p.get("decision"):
            snap.decision = Decision.model_validate(p["decision"])
            if snap.decision.tally:
                snap.tally = dict(snap.decision.tally)
            c.rounds_run = max(c.rounds_run, snap.decision.rounds_run)
        if p.get("options"):
            snap.options = [Option.model_validate(o) for o in p["options"]]
    elif t in (ET.TURN_COMPLETED, ET.TURN_INVALID, ET.TURN_TIMEOUT):
        c.calls += 1
        if t == ET.TURN_COMPLETED:
            c.tokens_in += int(p.get("tokens_in") or 0)
            c.tokens_out += int(p.get("tokens_out") or 0)
            c.tokens_reasoning += int(p.get("tokens_reasoning") or 0)
        else:
            c.calls_failed += 1
    elif t in (ET.PLAN_DRAFTED, ET.PLAN_READY):
        if p.get("plan"):
            snap.plan = Plan.model_validate(p["plan"])
            for task in snap.plan.tasks:
                snap.task_statuses.setdefault(task.id, TaskStatus.queued)
            _count_tasks(snap)
    elif t in _TASK_STATUS:
        if p.get("task_id"):
            snap.task_statuses[p["task_id"]] = _TASK_STATUS[t]
            _count_tasks(snap)
    elif t == ET.REVIEW_STARTED:
        if p.get("report"):
            snap.work_report = WorkReport.model_validate(p["report"])
        c.review_cycles = max(c.review_cycles, int(p.get("cycle") or 0))
    elif t == ET.TRIBUNAL_OUTCOME:
        if p.get("outcome"):
            snap.tribunal = TribunalOutcome.model_validate(p["outcome"])
    elif t == ET.CORRECTION_RECORDED:
        if p.get("correction"):
            fix = Correction.model_validate(p["correction"])
            snap.corrections = [x for x in snap.corrections if x.id != fix.id] + [fix]
            if snap.tribunal is not None and snap.tribunal.correction_id is None:
                snap.tribunal.correction_id = fix.id
    elif t == ET.PROBE_SCORES:
        scores = [ClaimScore.model_validate(x) for x in p.get("scores") or []]
        seat = p.get("seat_no")
        for score in scores:
            if score.seat_no is None:
                score.seat_no = seat
        seats = {x.seat_no for x in scores} | {seat}
        snap.claim_scores = [x for x in snap.claim_scores if x.seat_no not in seats] + scores
    elif t == ET.USER_INPUT_REQUESTED:
        snap.pending_input = UserQuestion.model_validate(p)
    elif t == ET.USER_INPUT_RECEIVED:
        snap.pending_input = None
    elif t == ET.RUN_COMPLETED:
        _end(snap, ev, p, RunState.DONE)
        if p.get("decision"):
            snap.decision = Decision.model_validate(p["decision"])
    elif t == ET.RUN_FAILED:
        _end(snap, ev, p, RunState.FAILED)
        snap.error = p.get("error") or "failed"
    elif t == ET.RUN_CANCELLED:
        _end(snap, ev, p, RunState.CANCELLED)


def fold(snap: RunSnapshot, events: list[Event]) -> RunSnapshot:
    for ev in events:
        if snap.finished_at is not None:
            # After the terminal event only the cursor moves: late events of cancelled calls.
            snap.last_seq = max(snap.last_seq, ev.seq)
            continue
        try:
            fold_event(snap, ev)
        except Exception:  # a bad payload must never break GET /runs/{id}
            continue
    end = snap.finished_at or snap.updated_at
    if snap.created_at and end:
        snap.counters.wall_ms = round(max(0.0, end - snap.created_at) * 1000.0, 1)
    return snap


# --------------------------------------------------------------------------------------
# Controller
# --------------------------------------------------------------------------------------


@dataclass
class _Run:
    run_id: str
    req: RunRequest
    demo: bool
    state: RunState = RunState.INTAKE
    entered: bool = False  # a run.state_changed has been emitted
    state_since: float = 0.0
    task: Optional[asyncio.Task] = None
    delegated: asyncio.Event = field(default_factory=asyncio.Event)
    input_wait: Optional[asyncio.Future] = None
    pending: Optional[UserQuestion] = None
    cancel_requested: bool = False
    terminal: bool = False


class _Control:
    """RunControl (run_pipeline) for one run, backed by the controller."""

    def __init__(self, ctrl: "RunController", run: _Run) -> None:
        self._ctrl, self._run = ctrl, run

    async def set_state(self, state: RunState, reason: str = "") -> None:
        self._ctrl._to(self._run, state, reason)

    async def wait_delegate(self) -> None:
        await self._run.delegated.wait()

    async def ask_user(self, question: UserQuestion) -> UserInput:
        return await self._ctrl._ask_user(self._run, question)

    def cancelled(self) -> bool:
        return self._run.cancel_requested


@dataclass
class _Bench:
    bench_id: str
    request: BenchRunRequest
    out_dir: Path
    state: str = "queued"  # queued | running | done | failed | cancelled
    started_at: float = 0.0
    finished_at: Optional[float] = None
    mode: str = ""
    model_id: Optional[str] = None
    done: int = 0
    total: int = 0
    correct: int = 0
    modes: list = field(default_factory=list)
    summary: list = field(default_factory=list)
    results_path: str = ""
    error: Optional[str] = None
    task: Optional[asyncio.Task] = None


class RunController:
    def __init__(
        self,
        config: Any,
        store: Any,
        bus: Any,
        gateway: Any,
        host: Any,
        registry: list[ModelEntry],
        sampler: Any = None,
        speed: float = 1.0,
        data_home: Path | None = None,
        chronicle: Any = None,
        reflector: Any = None,
        corrections: Any = None,
        reliability: Any = None,
        steer: Any = None,
        steer_store: Any = None,
        probe_files: Any = None,
    ) -> None:
        self.config = config
        self.store = store
        self.bus = bus
        self.gateway = gateway
        self.host = host
        self.registry = list(registry or [])
        self.mock = bool(getattr(getattr(config, "gateway", None), "mock", False))
        self.sampler = sampler if sampler is not None else (FakeSampler() if self.mock else None)
        self.speed = float(speed) if speed and speed > 0 else 1.0
        try:
            self.lens_texts = config_mod.load_lenses()
        except Exception:
            self.lens_texts = {}
        self._runs: dict[str, _Run] = {}
        self._tele_task: Optional[asyncio.Task] = None
        self._last_tick: Optional[TelemetrySnapshot] = None
        self._benches: dict[str, _Bench] = {}
        self._tmp_home: Optional[Path] = None
        if data_home is None:  # nothing on disk was asked for: a throwaway folder
            self._tmp_home = Path(tempfile.mkdtemp(prefix="council-"))
            weakref.finalize(self, shutil.rmtree, str(self._tmp_home), True)
        self.data_home = Path(data_home) if data_home is not None else self._tmp_home
        self.chronicle = chronicle
        self.reflector = reflector
        self.corrections_book = corrections
        self.reliability = reliability
        self.steer = steer
        self.steer_store = steer_store
        self.probe_files = probe_files
        self.steer_live: dict[str, Any] = {}  # model id -> (path, scale) | None, as served
        self.model_ctx: dict[str, int] = {}  # model id -> context it was loaded with
        self.evidence_runner = EvidenceRunner  # one is made per run, on the run's workspace
        # Models whose load failed in this process: {model id: error}. The pipeline fills it and
        # swaps their registry entry for one with status "failed" (what GET /models lists).
        self.failed_models: dict[str, str] = {}

    # ------------------------------------------------------------------ wiring

    @staticmethod
    def _data_home(base: Path, db_path: Any, data_home: Path | None) -> Optional[Path]:
        if data_home is not None:
            return Path(data_home)
        return None if str(db_path) == ":memory:" else base

    @staticmethod
    def _footprints(registry: list[ModelEntry]) -> dict[tuple[str, str], float]:
        out: dict[tuple[str, str], float] = {}
        for m in registry:
            live = m.measured.ram_gb_live
            if live is None:
                continue
            out[(m.id, "live")] = float(live)
            out[(m.id, "batch")] = float(m.measured.ram_gb_batch or live)
        return out

    def _wire(self, source: Any, embed: Any = None) -> "RunController":
        """Build the services of sections 15, 27 and 28 that were not passed in."""
        cfg, store, home = self.config, self.store, self.data_home
        embed = embed or self.gateway.embed
        if self.chronicle is None:
            self.chronicle = Chronicle(store, embed, cfg.chronicle)
        if self.reflector is None:
            self.reflector = Reflector(self.gateway, store, _quiet, embed, cfg.chronicle, time.time)
        if self.corrections_book is None:
            self.corrections_book = CorrectionBook(store, home)
        if self.reliability is None and bool(cfg.probe.enabled):
            self.reliability = ReliabilityService(
                ClaimLedger(store, time.time), store, source, cfg.probe, _quiet,
                home=home, lie_cfg=cfg.lie)
        if self.probe_files is None:
            self.probe_files = getattr(self.reliability, "files", None) or ProbeFiles(home)
        if self.steer_store is None:
            self.steer_store = SteerStore(home)
        if self.steer is None and source is not None:
            self.steer = SteerService(source, self.steer_store, self._steer_render,
                                      self._steer_generate, cfg.steer, _quiet, time.time)
        return self

    async def _steer_render(self, model_id: str, messages: list[dict]) -> str:
        """The prompt the model's own chat template makes. A driver with no template to ask
        (mock, Ollama) gets the plain text of the chat. A driver error is raised."""
        if getattr(self.host.driver, "render", None) is None:
            return render_text(messages, include_system=True)
        await self.host.ensure_resident([model_id], "live", _STEER_RUN)  # the template is the model's
        try:
            text = await self.host.render(model_id, messages)
        finally:
            self.host.release(_STEER_RUN)
        if not isinstance(text, str) or not text:
            raise RuntimeError(f"the chat template of {model_id} gave no text")
        return text

    async def _steer_generate(self, model_id: str, path: Optional[Path], scale: float,
                              prompts: list[str]) -> list[str]:
        """Answers of the model with the vector at this strength ("" for a failed call)."""
        await apply_steering(self.host, self.steer_live, model_id, path, scale)
        await self.host.ensure_resident([model_id], "live", _STEER_RUN)
        try:
            limit = int(getattr(self.config.steer, "max_tokens_probe", 80) or 80)
            specs = [CallSpec(
                model_id=model_id, purpose="steer.check", priority="batch", reasoning="off",
                messages=[{"role": "user", "content": p}], max_output_tokens=limit,
                temperature=0.0, meta={"scale": float(scale)}) for p in prompts]
            results = await asyncio.gather(*(self.gateway.call(s) for s in specs),
                                           return_exceptions=True)
        finally:
            self.host.release(_STEER_RUN)
        return [r.content if not isinstance(r, BaseException) and r.ok else "" for r in results]

    @classmethod
    def build_from_config(
        cls, home: Path | None = None, db_path: Any = None, speed: float = 1.0,
        data_home: Path | None = None,
    ) -> "RunController":
        """Mock or real, as config.gateway.mock says. Real: the configured host driver
        (Ollama when host.driver = "ollama") and the real gateway. Starts no model."""
        base = Path(home) if home is not None else config_mod.home()
        if db_path is None:
            (base / "db").mkdir(parents=True, exist_ok=True)
            db_path = base / "db" / "council.db"
        config = config_mod.load_config(base / "config" / "council.toml")
        if config.gateway.mock:
            return cls.build_mock(home=base, db_path=db_path, speed=speed, data_home=data_home)
        registry = config_mod.load_registry(base / "config" / "models.json")
        store = Store(db_path)
        bus = EventBus(store)
        footprints = cls._footprints(registry)
        core = {mid for mid in config.host.core_models if (mid, "live") in footprints}
        ram = RamBudget(lambda: meminfo.available_gib(meminfo.read_meminfo()),
                        float(config.host.headroom_gib), core, footprints)
        host = Host(host_mod.build_driver(config, registry), ram, registry, bus)
        ctx_of = getattr(host.driver, "ctx_of", None)  # the llama.cpp driver knows it per model
        gateway = Gateway(config, registry, store, bus, endpoint_for=host.endpoint_for,
                          ctx_for=ctx_of if callable(ctx_of) else None)
        sampler = Sampler(meminfo.read_meminfo, gateway.stats, host.status, default_gpu_reader,
                          float(config.telemetry.reference_price_per_million_tokens))
        ctrl = cls(config, store, bus, gateway, host, registry, sampler=sampler, speed=speed,
                   data_home=cls._data_home(base, db_path, data_home))
        ctrl.lens_texts = config_mod.load_lenses(base / "config" / "lenses.json")
        return ctrl._wire(probe_service.build_source(config, gateway))

    @classmethod
    def build_mock(
        cls, home: Path | None = None, db_path: Any = ":memory:", speed: float = 1.0,
        data_home: Path | None = None,
    ) -> "RunController":
        """Every real component, in mock mode: no GPU, no model server."""
        base = Path(home) if home is not None else config_mod.home()
        speed = float(speed) if speed and speed > 0 else 1.0
        config = config_mod.load_config(base / "config" / "council.toml")
        config.gateway.mock = True
        registry = config_mod.load_registry(base / "config" / "models.json")
        if not registry:
            registry = [
                m.model_copy(update={"measured": MeasuredStats(
                    ram_gb_live=round((m.params_b or 8.0) * 0.7 + 2.0, 1), load_s=6.0)})
                for m in BUILTIN_MODELS
            ]
        store = Store(db_path)
        bus = EventBus(store)

        footprints = cls._footprints(registry)
        core = {mid for mid in config.host.core_models if (mid, "live") in footprints}
        box: dict[str, Any] = {}

        def available() -> float:
            host = box.get("host")
            used = sum(r["footprint_gib"] for r in host.status()) if host is not None else 0.0
            return _MOCK_TOTAL_GIB - _MOCK_SYSTEM_GIB - used

        ram = RamBudget(available, float(config.host.headroom_gib), core, footprints)
        host = Host(MockDriver(load_delay_s=0.4 / speed), ram, registry, bus)
        box["host"] = host
        responder = MockResponder(seed=0, delay=(0.2 / speed, 0.9 / speed))
        embedder = MockEmbedder()
        gateway = Gateway(config, registry, store, bus, responder=responder,
                          endpoint_for=host.endpoint_for, embedder=embedder)
        ctrl = cls(config, store, bus, gateway, host, registry, sampler=FakeSampler(), speed=speed,
                   data_home=cls._data_home(base, db_path, data_home))
        ctrl.lens_texts = config_mod.load_lenses(base / "config" / "lenses.json")
        return ctrl._wire(_MockProbeSource(), embedder.embed)

    # ------------------------------------------------------------------ small helpers

    def _get(self, run_id: str) -> _Run:
        run = self._runs.get(run_id)
        if run is None:
            if self.store.get_run(run_id) is None:
                raise RunNotFound(run_id)
            raise InvalidState(f"run {run_id} is not active in this process")
        return run

    def _emit(self, type_: str, run_id: str, payload: Any = None) -> Optional[Event]:
        return self.bus.emit(type_, run_id, payload)

    def _persist(self, run: _Run, snap: Optional[RunSnapshot] = None) -> RunSnapshot:
        snap = snap or self.snapshot(run.run_id)
        fields: dict[str, Any] = dict(
            state=snap.state.value,
            counters=snap.counters.model_dump(mode="json"),
            snapshot=snap.model_dump(mode="json"),
        )
        if snap.state in TERMINAL_STATES:
            fields["finished"] = snap.finished_at
            fields["error"] = snap.error
            if snap.decision is not None:
                fields["outcome"] = snap.decision.outcome
        self.store.update_run(run.run_id, **fields)
        return snap

    def _to(self, run: _Run, state: RunState, reason: str = "", round_: int = 0) -> None:
        now = time.monotonic()
        self._emit(ET.RUN_STATE_CHANGED, run.run_id, dict(
            from_state=run.state if run.entered else None,
            to_state=state,
            reason=reason,
            round=round_,
            phase_ms=round((now - run.state_since) * 1000.0, 1) if run.entered else None,
        ))
        run.state, run.entered, run.state_since = state, True, now
        self._persist(run)

    def _finish(self, run: _Run) -> None:
        run.terminal = True
        if run.input_wait is not None and not run.input_wait.done():
            run.input_wait.cancel()
        try:
            self.host.release(run.run_id)
        except Exception:
            pass

    # ------------------------------------------------------------------ public: start

    async def start(self, req: RunRequest) -> str:
        opts = dict(req.options or {})
        demo = bool(opts.get("demo"))
        run_id = new_id("run")
        run = _Run(run_id=run_id, req=req, demo=demo, state_since=time.monotonic())
        self.store.create_run(run_id, req.task, req.workspace, req.mode, RunState.INTAKE)
        self._runs[run_id] = run
        self._emit(ET.RUN_CREATED, run_id, dict(
            task=req.task, workspace=req.workspace, mode=req.mode,
            deliverable=req.deliverable or ("plan" if demo else None),
            lineup_override=req.lineup_override, options=opts,
            state=RunState.INTAKE, created_at=time.time(),
        ))
        body = self._run_demo if demo else self._run_real
        run.task = asyncio.ensure_future(self._guard(run, body))
        if self.sampler is not None and (self._tele_task is None or self._tele_task.done()):
            self._tele_task = asyncio.ensure_future(self._telemetry_loop())
        return run_id

    async def _guard(self, run: _Run, body: Any) -> None:
        """Run one pipeline. Nothing but a cancellation leaves this coroutine."""
        try:
            await body(run)
        except asyncio.CancelledError:
            if not run.cancel_requested:
                raise
        except Exception as exc:  # noqa: BLE001 - a run must never crash the server
            try:
                from_state = run.state
                run.state = RunState.FAILED
                self._emit(ET.RUN_FAILED, run.run_id, dict(
                    from_state=from_state,
                    error=f"{exc.__class__.__name__}: {exc}"[:500],
                    detail=traceback.format_exc()[-2000:],
                    counters=self.snapshot(run.run_id).counters,
                    finished_at=time.time(),
                ))
                self._persist(run)
            except Exception:
                pass
        finally:
            if not run.cancel_requested:
                self._finish(run)

    # ------------------------------------------------------------------ demo path

    async def _run_demo(self, run: _Run) -> None:
        opts = run.req.options or {}
        seed = int(opts.get("seed") or 0)
        models = [m for m in self.registry if m.status == "active"] or None
        script = demo_events(run.req.task, run.run_id, models, seed)
        auto = bool(opts.get("auto_delegate")) or bool(self.config.foreman.auto_delegate)
        n = 0
        for delay, type_, payload in script:
            n += 1
            pause = max(0.0, float(delay)) / self.speed
            if pause >= 0.001:
                await asyncio.sleep(pause)
            elif n % 25 == 0:
                await asyncio.sleep(0)  # stay polite to the loop at high speed
            if type_ == WAIT_DELEGATE:
                if not auto:
                    await run.delegated.wait()
                continue
            if type_ == ET.RUN_CREATED:
                continue  # start() already emitted the real one
            if type_ == ET.RUN_STATE_CHANGED:
                # Wall-clock phase time, not story time: the wait for the user is real.
                now = time.monotonic()
                payload = dict(payload)
                payload["phase_ms"] = (
                    round((now - run.state_since) * 1000.0, 1) if run.entered else None
                )
                self._emit(type_, run.run_id, payload)
                run.state = _state(payload.get("to_state")) or run.state
                run.entered, run.state_since = True, now
                self._persist(run)
                continue
            if type_ == ET.RUN_COMPLETED:
                run.state = RunState.DONE
                payload = dict(payload)
                payload["finished_at"] = time.time()
            self._emit(type_, run.run_id, payload)
            if type_ == ET.RUN_COMPLETED:
                self._persist(run)
        if run.state != RunState.DONE:
            raise RuntimeError("demo script ended without run.completed")

    # ------------------------------------------------------------------ real path

    def _seat_budget(self) -> float:
        try:
            ram = self.host.ram
            resident = sum(float(r.get("footprint_gib") or 0.0) for r in self.host.status())
            return float(ram.seat_budget(float(ram.read_available_gib()) + resident))
        except Exception:
            return _FALLBACK_BUDGET_GIB

    def _resident_ids(self) -> set[str]:
        try:
            return {r["model_id"] for r in self.host.status()}
        except Exception:
            return set()

    def _table(self) -> SkillTable:
        try:
            stats = self.store.get_model_stats()
        except Exception:
            stats = {}
        return SkillTable({m.id: dict(m.priors) for m in self.registry}, stats=stats)

    def _pick(self, profile: TaskProfile, mode: Any, seed: int,
              override: Optional[list[str]], table: SkillTable) -> LineupRecord:
        try:
            total_runs = len(self.store.list_runs())
        except Exception:
            total_runs = 0
        return picker.pick(
            profile, int(mode.k), self.registry, table, self._seat_budget(), self.config.router,
            resident=self._resident_ids(), recent=self._recent_lineups(),
            deadline_s=float(mode.deadline_s), seed=seed, total_runs=total_runs,
            override=list(override) if override else None,
        )

    def _recent_lineups(self) -> list[list[str]]:
        try:
            return self.store.recent_lineups(max(1, int(self.config.router.repeat_window)))
        except Exception:
            return []

    def _deps(self) -> RunDeps:
        return RunDeps(
            config=self.config, store=self.store, bus=self.bus, gateway=self.gateway,
            host=self.host, registry=self.registry, chronicle=self.chronicle,
            reflector=self.reflector, corrections=self.corrections_book,
            reliability=self.reliability,
            home=self.data_home, now=time.time, lens_texts=dict(self.lens_texts),
            failed_models=self.failed_models, steer=self.steer, steer_store=self.steer_store,
            probe_files=self.probe_files, steer_live=self.steer_live, model_ctx=self.model_ctx,
        )

    async def _run_real(self, run: _Run) -> None:
        rid = run.run_id
        self._to(run, RunState.INTAKE, "run created")
        pipeline = RunPipeline(self._deps(), emit_completed=False)
        result = await pipeline.run(rid, run.req, _Control(self, run))
        if run.state != RunState.DONE:
            self._to(run, RunState.DONE, "run finished")
        counters = self.snapshot(rid).counters
        self._emit(ET.RUN_COMPLETED, rid, dict(
            state=RunState.DONE, outcome=result.decision.outcome, final_text=result.final_text,
            decision=result.decision, files_written=result.files_written, counters=counters,
            finished_at=time.time(),
        ))
        self._persist(run)

    async def _ask_user(self, run: _Run, question: UserQuestion, source: str = "council") -> UserInput:
        """AWAITING_USER and back. Resolved by submit_input()."""
        if not question.request_id:
            question = question.model_copy(update={"request_id": new_id("ask")})
        back = run.state
        run.pending = question
        run.input_wait = asyncio.get_running_loop().create_future()
        self._to(run, RunState.AWAITING_USER, "the council asks the user")
        self._emit(ET.USER_INPUT_REQUESTED, run.run_id, dict(
            question.model_dump(mode="json"), from_state=back, source=source))
        opts = getattr(run.req, "options", None) or {}
        unattended = (opts.get("auto_answer") or opts.get("auto_delegate") or opts.get("auto_input")
                      or bool(getattr(getattr(self.config, "foreman", None), "auto_delegate", False)))
        if unattended:  # the same flags the pipeline reads to skip the delegate wait
            # Nobody is watching (command line, benchmark, scripted run): do not wait forever.
            # The first option is the council's leading one.
            run.input_wait.set_result(UserInput(
                request_id=question.request_id,
                choice=question.options[0] if question.options else None,
                text="auto: no user present, the council's leading option stands",
            ))
        try:
            answer: UserInput = await run.input_wait
        finally:
            run.pending, run.input_wait = None, None
        self._emit(ET.USER_INPUT_RECEIVED, run.run_id, dict(
            request_id=answer.request_id, choice=answer.choice, text=answer.text, resume_state=back))
        self._to(run, back, "user answered")
        return answer

    # ------------------------------------------------------------------ public: actions

    async def delegate(self, run_id: str) -> bool:
        """The one-click delegate. Valid only in AWAITING_DELEGATION."""
        run = self._get(run_id)
        if run.terminal or run.state != RunState.AWAITING_DELEGATION:
            raise InvalidState(f"run is {run.state.value}, not AWAITING_DELEGATION")
        run.delegated.set()
        return True

    async def cancel(self, run_id: str) -> bool:
        """Stop a run. In-flight calls are cancelled. False when it had already ended."""
        run = self._runs.get(run_id)
        if run is None:
            if self.store.get_run(run_id) is None:
                raise RunNotFound(run_id)
            return False
        if run.terminal or run.cancel_requested:
            return False
        run.cancel_requested = True
        if run.task is not None and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        if run.state in TERMINAL_STATES:  # it finished on its own while we were stopping it
            self._finish(run)
            return False
        from_state = run.state
        run.state = RunState.CANCELLED
        try:
            self._emit(ET.RUN_CANCELLED, run_id, dict(
                from_state=from_state, reason="cancelled by user",
                counters=self.snapshot(run_id).counters, finished_at=time.time(),
            ))
            self._persist(run)
        finally:
            self._finish(run)
        return True

    async def submit_input(self, run_id: str, user_input: UserInput) -> bool:
        """Answer a user.input_requested."""
        run = self._get(run_id)
        if run.input_wait is None or run.input_wait.done() or run.pending is None:
            raise InvalidState("run is not waiting for user input")
        if not isinstance(user_input, UserInput):
            user_input = UserInput.model_validate(user_input)
        if run.pending.request_id and user_input.request_id != run.pending.request_id:
            raise InvalidState(f"unknown request_id: {user_input.request_id!r}")
        run.input_wait.set_result(user_input)
        return True

    async def wait(self, run_id: str, timeout: float | None = None) -> RunSnapshot:
        """Wait until the run task ends (or the timeout passes), then return the snapshot."""
        run = self._runs.get(run_id)
        if run is not None and run.task is not None and not run.task.done():
            await asyncio.wait([run.task], timeout=timeout)
        return self.snapshot(run_id)

    def models_busy(self) -> bool:
        """True while a real run or a bench is going: its models fill the memory."""
        if any(not r.terminal and not r.demo for r in self._runs.values()):
            return True
        return any(b.task is not None and not b.task.done() for b in self._benches.values())

    async def shutdown(self) -> None:
        """Stop every run task and the telemetry task, then the model servers. Emits nothing."""
        tasks = [r.task for r in self._runs.values() if r.task is not None and not r.task.done()]
        if self._tele_task is not None and not self._tele_task.done():
            tasks.append(self._tele_task)
        tasks += [b.task for b in self._benches.values() if b.task is not None and not b.task.done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for r in self._runs.values():
            r.terminal = True
        stop = getattr(self.host, "stop", None)
        if stop is not None:  # no llama-server is left behind on its port
            try:
                await stop()
            except Exception:
                pass
        if self._tmp_home is not None:
            shutil.rmtree(self._tmp_home, ignore_errors=True)

    # ------------------------------------------------------------------ public: reads

    def snapshot(self, run_id: str) -> RunSnapshot:
        """Fold the stored events of the run into a RunSnapshot."""
        row = self.store.get_run(run_id)
        if row is None:
            raise RunNotFound(run_id)
        snap = RunSnapshot(
            run_id=run_id, task=row.get("task") or "", workspace=row.get("workspace"),
            mode=row.get("mode") or "standard", created_at=row.get("created"),
        )
        since = 0
        while True:
            page = self.store.events_since(run_id, since, limit=_PAGE)
            fold(snap, page)
            if len(page) < _PAGE:
                break
            since = page[-1].seq
        return snap

    def list_runs(self) -> list[dict]:
        return self.store.list_runs()

    def is_active(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        return run is not None and not run.terminal

    def router_preview(self, task: str, mode: str = "standard") -> LineupRecord:
        """The lineup the Router would pick. Loads nothing, stores nothing."""
        profile = heuristic_profile(task)
        return self._pick(profile, self.config.mode(mode), 0, None, self._table())

    def telemetry(self) -> TelemetrySnapshot:
        """Latest telemetry snapshot (GET /telemetry)."""
        if self._last_tick is not None and any(not r.terminal for r in self._runs.values()):
            return self._last_tick
        return self._sample()

    # ------------------------------------------------------------------ public: plan edit

    def patch_plan(self, run_id: str, plan: Any) -> Plan:
        """A user edit of the plan (PATCH /runs/{id}/plan). Valid only in AWAITING_DELEGATION.

        `plan` is a Plan, or a dict of Plan fields laid over the current plan. It is re-linted
        by Foreman.apply_user_edit; with lint errors left, PlanRejected is raised and nothing
        changes. The stored plan gets a new version, which the pipeline picks up on delegate.
        """
        run = self._get(run_id)
        if run.terminal or run.state != RunState.AWAITING_DELEGATION:
            raise InvalidState(f"run is {run.state.value}, not AWAITING_DELEGATION")
        raw = self.store.get_json("plans", run_id)
        current = Plan.model_validate(raw) if raw else self.snapshot(run_id).plan
        if current is None:
            raise InvalidState("run has no plan yet")
        if isinstance(plan, Plan):
            edited = plan
        else:
            base = current.model_dump(mode="json")
            base.update(dict(plan or {}))
            try:
                edited = Plan.model_validate(base)
            except ValueError as exc:
                raise PlanRejected(f"not a valid plan: {str(exc)[:400]}") from None
        workspace = (Path(run.req.workspace) if run.req.workspace
                     else runs_dir(self.data_home, run_id) / "workspace")
        foreman = Foreman(self.gateway, _quiet, self.config.foreman, workspace)
        fixed, issues = foreman.apply_user_edit(current, edited)
        if issues:
            first = "; ".join(str(getattr(i, "message", i)) for i in issues[:3])
            raise PlanRejected(f"the edited plan has {len(issues)} lint error(s): {first}", issues)
        self.store.put_json("plans", run_id, fixed)
        self._emit(ET.PLAN_DRAFTED, run_id, dict(
            plan=fixed, version=self.store.plan_version(run_id), task_count=len(fixed.tasks)))
        self._persist(run)
        return fixed

    # ------------------------------------------------------------------ public: bench

    async def start_bench(self, req: BenchRunRequest) -> str:
        """Start one benchmark run in the background (POST /bench/run). Returns its id."""
        if not isinstance(req, BenchRunRequest):
            req = BenchRunRequest.model_validate(req)
        if not req.tasks_path:
            req = req.model_copy(update={"tasks_path": str(sample_tasks.default_path())})
        if any(b.state in _BENCH_ACTIVE for b in self._benches.values()):
            raise InvalidState("a bench run is already going")  # it loads models one at a time
        bench_id = new_id("bench")
        bench = _Bench(bench_id=bench_id, request=req, started_at=time.time(),
                       out_dir=self.data_home / "bench" / bench_id)
        self._benches[bench_id] = bench
        bench.task = asyncio.ensure_future(self._run_bench(bench))
        return bench_id

    def _bench_event(self, bench: _Bench, type_: str, payload: Any) -> None:
        p = dict(payload or {})
        p["bench_id"] = bench.bench_id
        if type_ == ET.BENCH_STARTED:
            bench.total = int(p.get("total") or 0)
            bench.modes = list(p.get("modes") or [])
        elif type_ == ET.BENCH_PROGRESS:
            bench.mode = str(p.get("mode") or bench.mode)
            bench.model_id = p.get("model_id")
            bench.done = int(p.get("done") or 0)
            bench.total = int(p.get("total") or bench.total)
            bench.correct = int(p.get("correct") or 0)
        elif type_ == ET.BENCH_COMPLETED:
            bench.summary = list(p.get("summary") or [])
            bench.results_path = str(p.get("results_path") or "")
            bench.error = p.get("error") or bench.error
        try:
            self.bus.emit(type_, bench.bench_id, p)
        except Exception:
            pass

    async def _run_bench(self, bench: _Bench) -> None:
        bench.state = "running"
        runner = BenchRunner(self.gateway, self.host, self.registry, self.store, self.config,
                             lambda type_, payload=None: self._bench_event(bench, type_, payload))
        try:
            rows = await runner.run(bench.request, bench.out_dir)
            bench.summary = [r.model_dump(mode="json") for r in rows]
            bench.state = "done"
        except asyncio.CancelledError:
            bench.state = "cancelled"
            raise
        except Exception as exc:  # noqa: BLE001 - a bench must never crash the server
            bench.state = "failed"
            bench.error = bench.error or f"{exc.__class__.__name__}: {exc}"[:400]
        finally:
            bench.finished_at = time.time()
            try:
                self.host.release("manual")  # Host.load seats its models under "manual"
            except Exception:
                pass

    def bench_status(self, bench_id: str) -> dict:
        bench = self._benches.get(bench_id)
        if bench is None:
            raise RunNotFound(bench_id)
        return dict(
            bench_id=bench.bench_id, state=bench.state, mode=bench.mode, model_id=bench.model_id,
            done=bench.done, total=bench.total, correct=bench.correct, modes=list(bench.modes),
            summary=list(bench.summary), results_path=bench.results_path,
            out_dir=str(bench.out_dir), error=bench.error, started_at=bench.started_at,
            finished_at=bench.finished_at, request=bench.request.model_dump(mode="json"),
        )

    # ------------------------------------------------------------------ public: 27 and 28

    def corrections(self, project: Optional[str] = None) -> list[Correction]:
        return self.store.corrections_list(project)

    async def train_probe(self, model_id: str) -> Probe:
        """Bootstrap and train the truth probe of one model (28.4) on the sample tasks."""
        if model_id not in {m.id for m in self.registry}:
            raise RunNotFound(model_id)
        if self.reliability is None or getattr(self.reliability, "source", None) is None:
            raise InvalidState("the probe is off, or this setup has no activation source")
        if str(getattr(getattr(self.config, "probe", None), "source", "mock")) == "llamacpp"                 and self.models_busy():
            # The real source loads its own full copy of the model, outside the Host RAM budget.
            raise InvalidState("a run is active: train the probe when the council is idle")
        service = copy.copy(self.reliability)

        def emit(type_: str, payload: Any = None) -> None:
            try:
                self.bus.emit(type_, None, payload)
            except Exception:
                pass

        service.emit = emit
        tasks = [BenchTask.model_validate(row) for row in sample_tasks.generate()]
        return await service.train_for(model_id, tasks, time.time())

    def probes(self) -> list[Probe]:
        out: list[Probe] = []
        for key, raw in sorted(self.store.kv_list(probe_service.NS).items()):
            if key.startswith(_WEIGHTS_PREFIX):
                continue
            try:
                out.append(Probe.model_validate(raw))
            except ValueError:
                continue
        return out

    def export_chronicle(self, project: Optional[str] = None) -> str:
        chronicle = self.chronicle or Chronicle(self.store, self.gateway.embed, self.config.chronicle)
        return chronicle.export_markdown(project)

    # ------------------------------------------------------------------ telemetry

    def _sample(self) -> TelemetrySnapshot:
        if self.sampler is None:
            return TelemetrySnapshot(ts=time.time())
        busy = any(not r.terminal for r in self._runs.values())
        if hasattr(self.sampler, "set_activity"):
            self.sampler.set_activity(0.8 if busy else 0.05)
        snap = self.sampler.sample()
        if isinstance(self.sampler, FakeSampler):
            snap = self._ground(snap)
        self._last_tick = snap
        return snap

    def _ground(self, snap: TelemetrySnapshot) -> TelemetrySnapshot:
        """Mock mode: keep the fake machine numbers, but show the models and calls that are real."""
        try:
            resident = [ResidentModel(model_id=r["model_id"], footprint_gib=r["footprint_gib"])
                        for r in self.host.status()]
            stats = self.gateway.stats()
        except Exception:
            return snap
        used = _MOCK_SYSTEM_GIB + sum(r.footprint_gib for r in resident)
        tokens = [int(stats.get(k) or 0) for k in ("tokens_in", "tokens_out", "tokens_reasoning")]
        price = float(self.config.telemetry.reference_price_per_million_tokens)
        in_flight = dict(stats.get("in_flight") or {})
        tps = dict(stats.get("tps_by_model") or {}) if in_flight else {}
        return snap.model_copy(update=dict(
            mem_total_gib=_MOCK_TOTAL_GIB, mem_used_gib=round(used, 2),
            mem_available_gib=round(_MOCK_TOTAL_GIB - used, 2), resident=resident,
            in_flight=in_flight, queue_depth=int(stats.get("queue_depth") or 0),
            tps_by_model=tps, tps_total=round(sum(tps.values()), 1),
            tokens_in=tokens[0], tokens_out=tokens[1], tokens_reasoning=tokens[2],
            cloud_equiv_usd=sum(tokens) / 1_000_000.0 * price,
        ))

    async def _telemetry_loop(self) -> None:
        """One telemetry.tick per tick_s on every active run. Demo runs carry scripted ticks."""
        tick = max(0.01, float(self.config.telemetry.tick_s))
        while any(not r.terminal for r in self._runs.values()):
            try:
                live = [r for r in self._runs.values() if not r.terminal and not r.demo]
                if live:
                    snap = self._sample()
                    for r in live:
                        if not r.terminal:
                            self._emit(ET.TELEMETRY_TICK, r.run_id, snap)
            except Exception:
                pass
            await asyncio.sleep(tick)


__all__ = ["RunController", "RunNotFound", "InvalidState", "PlanRejected", "fold", "fold_event",
           "NEXT_PHASE_NOTE", "TERMINAL_STATES"]
