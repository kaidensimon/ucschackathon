"""RunPipeline: the full real run (spec 2 steps 2 to 15, plus 27 and 28) as one coordinator.

The controller owns the run record, the INTAKE state, cancellation and the wait for the user.
It hands this pipeline a RunControl and awaits run(). The pipeline walks the states

    PROFILING -> CONVENING -> DELIBERATING -> DECIDED -> [EXAMINING] -> [REFLECTING] -> DONE  (answer)
    ... -> PLANNING -> AWAITING_DELEGATION -> EXECUTING -> REVIEWING -> INTEGRATING
        -> REFLECTING -> DONE                                                           (plan, build)

Choices made here
- State changes go through ctl.set_state (the controller emits run.state_changed).
  user.input_requested / user.input_received belong to ctl.ask_user.
- run.completed is emitted here (no counters: the controller's fold keeps its own). Pass
  emit_completed=False to RunPipeline when the caller emits it.
- Brief text is cached in the store kv namespace "briefs" under brief_hash(workspace).
- Tier B is used when kv namespace "calibration_embeddings" ({task_id: {"embedding": [...]}})
  plus the calibration matrix make a ready CalibrationIndex. Otherwise Tier A.
- No workspace: the project id is "global"; a plan or build run works in runs/<run_id>/workspace.
- Claim scores (28.5) are computed between round 0 and round 1 by holding the round 1 calls back
  behind one engine-side pseudo check, so LiveExecutor is used unchanged.
- "An evidence check supports the council" (27.5) is read as: a python check exited 0 and it
  settles a claim of a seat that drafted the chosen option (EvidenceResult.supports, set by the
  Deliberation). A check that only ran, or whose side is unknown, does not count.
- Review: a fix majority with an empty fix list counts as accept. A split first vote gets one
  argument round (review.debate). The review ends with a FINAL SAY when review.deadline_s is
  over, the fix cycles are used up, the council has no usable verdict, or a second "fix" comes
  in although every current check passes (the first such "fix" is still done). Final say:
  review.final_say "random_seat" lets one randomly picked seat decide from the record; "user"
  asks the user ("accept" integrates, anything else discards). A council that votes ask_user in
  an attended run (no auto_input / auto_delegate) always gets the user.
- Adaptive effort (standard mode, chamber.adaptive, options.effort != "fixed"): the lineup is
  picked with the base mode, then rounds, deadline and reasoning are planned from the task and
  the measured seat speeds (effort.planned). options.effort light|normal|heavy forces a level.
  An explicit options.deadline_s still wins over the planned deadline.
- chamber.chair_pick "random": the chair (who breaks a failed consensus) is drawn with
  Random(f"{seed}:chair") over the seats; drawn again over the final seats when a seat changed.
  The Foreman's plan is then written by the best seat by q, not by the drawn chair.
- Cancellation (ctl.cancelled()) is checked between steps and raises asyncio.CancelledError.
- Any exception leaves run() after the host seats of the run are released.
- Convening loads the seats one at a time, resident models first. A seat whose model cannot be
  loaded (HostError, after the Host's own retry) gets a substitute: the next alternate of the
  lineup, then any other eligible model that fits the seat budget (one that keeps the lab rule
  first). model.failed is emitted with replaced_by. A seat with no substitute is dropped and the
  seats are renumbered. The run fails only below the quorum, ceil(quorum_fraction * k).
  When a seat changed, router.lineup_selected is emitted a second time with the final lineup,
  and the stored LineupRecord is the final one. seat.assigned carries replaces_model_id.
- A model whose load failed is out for this process: RunDeps.failed_models {id: error}, and its
  registry entry is swapped for a FailedModelEntry (status "failed"), so the picker, the role
  lookups and GET /models all see it. A refused admission (no room) is not a model fault: the
  seat is substituted but the model is not marked.
- Answer runs reflect too (REFLECTING, same collect + reflect path as build runs; the Reflector
  calls at batch priority), unless options.reflect is False or the mode is quick. A reflection
  error never fails an answer run: the answer is already delivered. accepted is None there.
- collect_candidates reads lessons from ballot.cast only. The lesson of a tribunal outcome and of
  a recorded correction is handed to it as an in-memory ballot.cast event (never emitted).

1.5 (each behind its config switch, none may fail a run)
- Memory plan ([memory]), before any seat is loaded: sizes come from the on-box check file, then
  the registry, then reported size x overhead. The total is MemTotal of the machine; in mock
  mode (and where /proc/meminfo is missing) it is what the Host's budget sees. The configured
  planner and clerk work while the seats are seated; they are kept when the plan says they fit
  beside the seats (share_roles "never": always kept; "always": never). The workers are not
  counted then: they load after the seats went idle. Otherwise every work role goes to a seated
  model (router.roles.assign_roles) for this run. Seats that still do not fit are dropped, lowest q
  first, never below 2: the council shrinks instead of failing. memory.planned carries the plan
  and says all of that in its notes.
- Context per model: only for a driver that takes one (ctx_for + ctx_of, the llama.cpp driver).
  Wanted = min(plan, ctx_policy for the model's roles), never above the configured context. A
  resident model keeps the context it was loaded with (RunDeps.model_ctx), so a run never
  reloads a model for its context. The Deliberation gets the smallest seat context.
- Steering ([steer]): before a seat loads, its active vector (the SteerStore card) goes to host.set_steering; no vector takes one off. A resident model
  whose steering changed is unloaded first, so the load restarts it (RunDeps.steer_live keeps
  what each model runs with). steer.applied is emitted once the seat is resident, and only when
  the driver can steer. After a run that recorded a correction, SteerService.train runs for
  that (project, model) once the reflection is over (steer.trained comes from the service).
- Lie detector ([lie]): the report of round 0 comes with the claim scores (the service emits
  lie.report and stores it). With show_to_council the flags go into round 1
  (Deliberation.set_lie_flags) and the examined seat's flags go to the Tribunal. The scoring
  step is cut off after lie.timeout_s per seat. With [probe] off and [lie] on, only the lie
  report is made. With [lie] off, no lie.report is emitted.
"""

from __future__ import annotations

import asyncio
import copy
import math
import random
import re
import time
import zlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from council.chamber.consensus import ConsensusConfig
from council.chamber.deliberation import Deliberation
from council.chamber.effort import apply_effort, plan_effort
from council.chamber.evidence import EvidenceRunner
from council.chamber.executors import LiveExecutor
from council.chamber.open_debate import OpenDebate
from council.chamber.outlier import examiners, find_outlier, seat_distance
from council.chamber.tribunal import Tribunal
from council.chronicle import recall
from council.chronicle.collect import collect_candidates
from council.chronicle.corrections import build_correction
from council.chronicle.reflect import Reflector, pick_judges
from council.core import event_types as ET
from council.core.schemas_v15 import ClaimSpan, MemoryPlan
from council.core.schemas import (
    CallResult,
    CallSpec,
    Correction,
    Decision,
    Event,
    EvidenceResult,
    LineupRecord,
    MinorityPosition,
    ModelEntry,
    Plan,
    ReviewBallot,
    RunRequest,
    RunState,
    SeatAssignment,
    TaskProfile,
    TribunalOutcome,
    UserInput,
    UserQuestion,
    WorkReport,
)
from council.api.ui_bridge import seat_names
from council.core.util import new_id
from council.core.workspace import project_id, runs_dir
from council.host import ctx_policy, memplan, meminfo, model_checks
from council.host.host import HostError
from council.probe.scorer import LiveScorer
from council.router import picker
from council.router import roles as roles_mod
from council.router import stats as router_stats
from council.router.competence import q_tier_a
from council.router.profiler import heuristic_profile
from council.router.tier_b import CalibrationIndex
from council.steer import contrast
from council.works import brief as brief_mod
from council.works import review as review_mod
from council.works.foreman import Foreman, PlanError, canonical_test_cmd
from council.works.pipeline import WorksPipeline
from council.works.report import report_text

NO_PROJECT = "global"
BRIEF_NS = "briefs"
CALIBRATION_NS = "calibration_embeddings"
BRIEF_CHARS = 3000
_FALLBACK_BUDGET_GIB = 64.0
_SCORE_CHECK = "__claim_scores__"
_TRIBUNAL_MODES = ("standard", "deep")
_TRIBUNAL_OUTCOMES = ("consensus", "majority", "chair")
_LESSON_OUTCOMES = ("conceded", "failed")
_NOT_A_MODEL_FAULT = ("cannot admit", "unknown model")
_EPS = 1e-9
_FORCED_EFFORT = {"light": "easy", "normal": "medium", "heavy": "hard"}
MIN_SEATS = 2  # the memory plan never shrinks a council below this
MEMORY_NS = "memory_plans"
_CTX_STEPS = (16384, 8192, 4096)
_BESIDE_SEATS = ("planner", "clerk")  # roles that work while the seats are seated
_MOCK_LAYERS = 24  # depth assumed for an activation source that cannot tell it (mock)
_LIE_SLACK_S = 5.0
_STANCE_CLAIM = "stance"  # claim id of a message's card stance, for the per-message lie reading
_STANCE_CLIP = 400
_NO_READING = {"score": None, "level": "ok", "reasons": ["no probe"]}
_WHY_NO_PROBE = "no probe"  # nothing was ever trained for the model (or no activation source)
_WHY_UNTRUSTED = "probe not trusted for this model"  # a probe exists and is not active
_WHY_TIMEOUT = "reading timed out"
_WHY_FAILED = "reading failed"
_WHY_NO_TEXT = "nothing to read"
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")


def _reading_text(msg: Any) -> str:
    """The statement the truth probe reads for a message: the card's stance, else the card's
    note, else the first sentence of the message."""
    card = getattr(msg, "card", None)
    for raw in (getattr(card, "stance", ""), getattr(card, "note", "")):
        text = str(raw or "").strip()
        if text:
            return text[:_STANCE_CLIP]
    body = str(getattr(msg, "text", "") or "").strip()
    first = next((part.strip() for part in _SENTENCE_END.split(body) if part.strip()), "")
    return first[:_STANCE_CLIP]


def _probe_state(reliability: Any, model_id: str) -> str:
    """"active", "untrusted" or "none" (see ReliabilityService.probe_state)."""
    try:
        if reliability.active_probes(model_id):
            return "active"
        state = getattr(reliability, "probe_state", None)
        return str(state(model_id)) if callable(state) else "none"
    except Exception:
        return "none"


async def apply_steering(host: Any, live: dict, model_id: str, path: Any, scale: float = 1.0) -> bool:
    """Tell the host which steering vector a model runs with (path None = none).

    `live` is {model id: (path, scale) or None}, what each model was last given. A resident
    model whose steering changes is unloaded, so its next load starts it with the new vector.
    False when the driver cannot steer. Driver errors are raised."""
    if getattr(getattr(host, "driver", None), "set_steering", None) is None:
        return False
    wanted = None if path is None else (str(path), float(scale))
    if live.get(model_id) != wanted:
        try:
            resident = any(r.get("model_id") == model_id for r in host.status())
        except Exception:
            resident = False
        if resident:
            await host.unload(model_id, "steer")
    ok = bool(await host.set_steering(model_id, None if path is None else Path(path), float(scale)))
    if ok:
        live[model_id] = wanted
    return ok


class FailedModelEntry(ModelEntry):
    """Registry entry of a model that could not be loaded in this process. Not "active", so the
    picker and every role lookup skip it; GET /models shows the status as it is."""

    status: str = "failed"  # type: ignore[assignment]


def evidence_supports(evidence: list[EvidenceResult], chosen: Optional[str]) -> bool:
    """27.5 "an evidence check supports the council's position".

    True only when a python check ran, exited 0, and the engine tied it to a claim of a seat
    that drafted the chosen option (EvidenceResult.supports). A check that merely ran, or whose
    side is not known, verifies nothing.
    """
    if not chosen:
        return False
    return any(e.ok and e.kind == "python" and e.exit_code == 0 and e.supports == chosen
               for e in evidence)


class RunControl(Protocol):
    async def set_state(self, state: RunState, reason: str = "") -> None: ...
    async def wait_delegate(self) -> None: ...
    async def ask_user(self, question: UserQuestion) -> UserInput: ...
    def cancelled(self) -> bool: ...


@dataclass
class RunDeps:
    config: Any
    store: Any
    bus: Any
    gateway: Any
    host: Any
    registry: list[ModelEntry]
    chronicle: Any = None  # chronicle.service.Chronicle
    reflector: Any = None  # chronicle.reflect.Reflector (its emit is rebound per run)
    reflector_factory: Optional[Callable[[Callable[[str, dict], None]], Any]] = None  # f(emit)
    corrections: Any = None  # CorrectionBook
    reliability: Any = None  # ReliabilityService | None
    home: Path = Path(".")
    now: Callable[[], float] = time.time
    lens_texts: dict[str, str] = field(default_factory=dict)
    failed_models: dict[str, str] = field(default_factory=dict)  # model id -> load error, this process
    steer: Any = None  # steer.service.SteerService (its emit is rebound per run)
    steer_store: Any = None  # steer.store.SteerStore
    probe_files: Any = None  # probe.probe_files.ProbeFiles
    steer_live: dict[str, Any] = field(default_factory=dict)  # model id -> (path, scale) | None
    model_ctx: dict[str, int] = field(default_factory=dict)  # model id -> context it was loaded with


@dataclass
class RunResult:
    decision: Decision
    final_text: str = ""
    files_written: list[str] = field(default_factory=list)
    tribunal: Optional[TribunalOutcome] = None
    correction: Optional[Correction] = None
    plan: Optional[Plan] = None
    report: Optional[WorkReport] = None
    accepted: Optional[bool] = None


class _ScoredDeliberation:
    """Deliberation proxy that scores the round 0 drafts before the round 1 calls go out."""

    def __init__(self, delib: Deliberation, score: Callable[..., Any]) -> None:
        self._d = delib
        self._score = score
        self.need = True
        self._hold = False
        self._sent = False
        self._r0_calls: dict[str, int] = {}
        self.specs: dict[int, CallSpec] = {}
        self.results: dict[int, CallResult] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._d, name)

    def pending_calls(self) -> list[CallSpec]:
        phase = self._d.phase
        if self.need and phase == "r1":
            self._hold = True
            return []
        # No round 1 (quick mode, early exit): `need` stays set and the caller scores afterwards.
        out = self._d.pending_calls()
        if phase == "r0":
            for spec in out:
                seat = (spec.meta or {}).get("seat_no")
                if isinstance(seat, int):
                    self._r0_calls[spec.call_id] = seat
                    self.specs[seat] = spec
        return out

    def pending_checks(self) -> list:
        out = list(self._d.pending_checks())
        if self._hold and not self._sent:
            self._sent = True
            out.append(_ScoreCheck())
        return out

    def on_result(self, result: CallResult) -> list:
        seat = self._r0_calls.get(result.call_id)
        if seat is not None:
            self.results[seat] = result
        return self._d.on_result(result)

    def on_evidence(self, check_id: str, result: EvidenceResult) -> list:
        if check_id == _SCORE_CHECK:
            self._hold, self.need = False, False
            return self._d.take_events()
        return self._d.on_evidence(check_id, result)

    def messages_for(self, seat: int) -> list[dict]:
        """What the probe source captures for a seat, in the framing the probe was trained on
        (probe/activations.py): the seat's system text, the task as the question, the answer.
        The long round 0 body (record, brief, format rules) is left out: no training row has it."""
        spec = self.specs.get(seat)
        msgs = [dict(m) for m in (spec.messages if spec is not None else []) if m.get("role") == "system"]
        msgs.append({"role": "user", "content": str(getattr(self._d, "task", "") or "")})
        draft = self._d.drafts().get(seat)
        if draft is not None:
            msgs.append({"role": "assistant", "content": draft.answer})
        return msgs

    async def score(self) -> None:
        self.need = False
        await self._score(self)


class _ScoreCheck:
    check_id = _SCORE_CHECK
    kind = "python"
    spec = ""
    settles = None


class _LieDebate:
    """OpenDebate proxy (open protocol): a lie-detector reading for every message.

    When a round's messages have their cards, the next round's calls (or the deciding vote)
    are held back, `read` gives one reading per new message, and set_lie_metrics puts them
    on the messages (it emits msg.lie and rebuilds the calls still waiting), then the calls
    go out. Same trick as _ScoredDeliberation: the wait is a pending check."""

    def __init__(self, debate: Any, read: Callable[[list], Any]) -> None:
        self._d = debate
        self._read = read
        self._seen: set[str] = set()
        self._hold = False
        self._sent = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._d, name)

    def unread(self, final: bool = False) -> list:
        """Messages with a card and no reading yet, of the rounds that are over."""
        phase = str(self._d.phase)
        if final or phase in ("chair", "done"):
            before: Optional[int] = None
        elif phase[:1] == "r" and phase[1:].isdigit():
            before = int(phase[1:])
        else:
            return []  # the round-0 merge: round 0 is not closed yet
        return [m for m in self._d.messages()
                if m.card is not None and m.text and m.turn_id not in self._seen
                and (before is None or m.round < before)]

    def pending_calls(self) -> list[CallSpec]:
        if self._hold:
            return []
        if self.unread():
            self._hold, self._sent = True, False
            return []
        return self._d.pending_calls()

    def pending_checks(self) -> list:
        out = list(self._d.pending_checks())
        if self._hold and not self._sent:
            self._sent = True
            out.append(_ScoreCheck())
        return out

    def on_evidence(self, check_id: str = "", result: Any = None) -> list:
        if check_id == _SCORE_CHECK:
            self._hold = False
            return self._d.take_events()
        return self._d.on_evidence(check_id, result)

    async def read(self, final: bool = False) -> None:
        msgs = self.unread(final)
        if not msgs:
            return
        self._seen.update(m.turn_id for m in msgs)
        self._d.set_lie_metrics(await self._read(msgs))


class RunPipeline:
    def __init__(self, deps: RunDeps, emit_completed: bool = True) -> None:
        self.d = deps
        self.emit_completed = bool(emit_completed)
        self._state: dict[str, dict] = {}  # per run: roles, ctx, steered, steer_due

    # ------------------------------------------------------------------ small helpers

    def _emitter(self, run_id: str) -> Callable[[str, Any], None]:
        bus = self.d.bus

        def emit(type_: str, payload: Any = None) -> None:
            bus.emit(type_, run_id, payload)

        return emit

    @staticmethod
    def _check(ctl: RunControl) -> None:
        if ctl.cancelled():
            raise asyncio.CancelledError()

    async def _to(self, ctl: RunControl, state: RunState, reason: str = "") -> None:
        self._check(ctl)
        await ctl.set_state(state, reason)

    def _entry(self, model_id: Optional[str]) -> ModelEntry:
        return next((m for m in self.d.registry if m.id == model_id), None) or ModelEntry(id=model_id or "")

    def _role(self, role: str, run_id: Optional[str] = None) -> Optional[str]:
        """The model of a work role: the one the memory plan gave it for this run, else the
        registry's."""
        shared = (self._state.get(run_id) or {}).get("roles") if run_id else None
        if shared and shared.get(role):
            return shared[role]
        return next((m.id for m in self.d.registry if m.status == "active" and role in m.roles), None)

    def _run_state(self, run_id: str) -> dict:
        return self._state.setdefault(run_id, {})

    @staticmethod
    def _seed(run_id: str, opts: dict) -> int:
        seed = opts.get("seed")
        if isinstance(seed, int) and not isinstance(seed, bool):
            return seed
        return zlib.crc32(run_id.encode("utf-8")) & 0x7FFFFFFF

    def _mode(self, name: str, opts: dict) -> Any:
        mode = self.d.config.mode(name)
        update: dict[str, Any] = {}
        k = opts.get("k")
        if isinstance(k, int) and not isinstance(k, bool) and (2 <= k <= 6 or k in (mode.k_options or [mode.k])):  # the UI offers 2 to 6 seats
            update["k"] = k
        deadline = opts.get("deadline_s")
        if isinstance(deadline, (int, float)) and not isinstance(deadline, bool) and deadline > 0:
            update["deadline_s"] = float(deadline)
        return mode.model_copy(update=update) if update else mode

    def _resident_ids(self) -> set[str]:
        try:
            return {r["model_id"] for r in self.d.host.status()}
        except Exception:
            return set()

    def _seat_tps(self, lineup: LineupRecord) -> dict[int, float]:
        """Measured single-stream speed per seat, so turn timeouts fit each model."""
        by_id = {m.id: m for m in self.d.registry}
        out: dict[int, float] = {}
        for seat in lineup.seats:
            entry = by_id.get(seat.model_id)
            tps = getattr(getattr(entry, "measured", None), "tps_1", None) if entry else None
            if tps:
                out[int(seat.seat_no)] = float(tps)
        return out

    async def _adopt(self) -> None:
        try:
            await self.d.host.start()
        except Exception:  # noqa: BLE001  a server that is down fails later, at load
            pass

    def _seat_budget(self) -> float:
        try:
            ram = self.d.host.ram
            resident = sum(float(r.get("footprint_gib") or 0.0) for r in self.d.host.status())
            return float(ram.seat_budget(float(ram.read_available_gib()) + resident))
        except Exception:
            return _FALLBACK_BUDGET_GIB

    async def _call(self, spec: CallSpec) -> CallResult:
        try:
            return await self.d.gateway.call(spec, seat_no=(spec.meta or {}).get("seat_no"))
        except asyncio.CancelledError:
            raise
        except Exception:
            return CallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id, error="server_error")

    async def _seat(self, run_id: str, models: list, project: Optional[str] = None) -> None:
        """Seat exactly `models` for this run's next phase. Models of the last phase turn idle, so
        the Host may evict them when the new ones need the room (6.2)."""
        wanted = list(dict.fromkeys(m for m in models if m))
        self.d.host.release(run_id)
        if project:
            await self.d.host.ensure_resident(wanted, "live", run_id, project=project)
        else:
            await self.d.host.ensure_resident(wanted, "live", run_id)

    async def _seat_review(self, run_id: str, lineup: LineupRecord, extra: list,
                           project: Optional[str], emit: Callable) -> LineupRecord:
        """Seat the council again for the review. A seat whose model does not come back (the
        workers evicted it and it will not reload) is left out: the others still vote, and the
        built work is not lost. Returns the lineup of the seats that are resident."""
        try:
            await self._seat(run_id, [s.model_id for s in lineup.seats] + list(extra), project)
            return lineup
        except HostError:
            pass
        d = self.d
        d.host.release(run_id)
        kept = []
        for s in lineup.seats:
            try:
                await d.host.ensure_resident([s.model_id], "live", run_id, project=project or None)
                kept.append(s)
            except HostError as exc:
                emit(ET.MODEL_FAILED, self._model_event(
                    s.model_id, error=(str(exc) or exc.__class__.__name__)[:300], stage="load"))
        return lineup.model_copy(update={"seats": kept})

    async def _seat_ok(self, run_id: str, models: list) -> bool:
        """_seat that reports a model that will not load instead of raising."""
        try:
            await self._seat(run_id, models)
            return True
        except HostError:
            return False

    async def _ask(self, ctl: RunControl, question: UserQuestion) -> UserInput:
        self._check(ctl)
        if not question.request_id:
            question = question.model_copy(update={"request_id": new_id("ask")})
        return await ctl.ask_user(question)

    # ------------------------------------------------------------------ steps 2 to 4

    async def _brief(self, workspace: Optional[Path], emit: Callable) -> str:
        t0 = time.monotonic()
        if workspace is None or not workspace.is_dir():
            emit(ET.BRIEF_READY, dict(
                workspace=str(workspace) if workspace else None,
                summary="No workspace given." if workspace is None else "Workspace not found on this machine."))
            return ""
        key = await asyncio.to_thread(brief_mod.brief_hash, workspace)
        hit = None
        try:
            hit = self.d.store.kv_get(BRIEF_NS, key)
        except Exception:
            pass
        cached = isinstance(hit, dict) and isinstance(hit.get("text"), str)
        if cached:
            text = hit["text"]
        else:
            text = await asyncio.to_thread(brief_mod.build_brief, workspace, BRIEF_CHARS)
            try:
                self.d.store.kv_put(BRIEF_NS, key, {"text": text, "workspace": str(workspace)})
            except Exception:
                pass
        head, _, rest = text.partition("\n\n")
        files = [ln.strip() for ln in rest.split("\n\n", 1)[0].splitlines()[1:] if ln.startswith("  ")]
        langs = [p.split(" (")[0].strip() for p in head.removeprefix("Languages: ").split(",")
                 if head.startswith("Languages: ") and p.strip() and p.strip() != "unknown"]
        emit(ET.BRIEF_READY, dict(
            workspace=str(workspace),
            summary=f"{len(files)} files. Languages: {', '.join(langs[:4]) or 'none detected'}.",
            file_count=len(files), languages=langs,
            key_files=[f for f in files if brief_mod._is_key(f)][:8],
            tree="\n".join(files[:40]), cached=cached,
            ms=round((time.monotonic() - t0) * 1000.0, 1)))
        return "" if text == brief_mod.EMPTY else text

    async def _profile(self, req: RunRequest, emit: Callable) -> TaskProfile:
        t0 = time.monotonic()
        profile = heuristic_profile(req.task)
        update: dict[str, Any] = {}
        if req.deliverable:
            update["deliverable"] = req.deliverable
        if not profile.embedding:
            vec: list[float] = []
            try:
                got = await self.d.gateway.embed([req.task])
                vec = [float(x) for x in (got[0] if got else [])]
            except Exception:
                vec = []
            update["embedding"] = vec if any(vec) else recall.keyword_embedding(req.task)
        if update:
            profile = profile.model_copy(update=update)
        emit(ET.PROFILE_READY, dict(profile=profile, model_id=None,
                                    ms=round((time.monotonic() - t0) * 1000.0, 1)))
        return profile

    async def _recall(self, req: RunRequest, workspace: Optional[Path], profile: TaskProfile,
                      emit: Callable) -> str:
        t0 = time.monotonic()
        cats = list(profile.categories)
        if self.d.chronicle is not None and workspace is not None:
            block, found = await self.d.chronicle.record_for(req.task, workspace, cats)
        else:
            try:
                entries = self.d.store.chronicle_list()
            except Exception:
                entries = []
            found = recall.rank(entries, list(profile.embedding), None, cats,
                                k=int(self.d.config.chronicle.recall_k))
            block = recall.render_record(found)
        emit(ET.RECALL_READY, dict(entries=found, count=len(found), record_block=block,
                                   ms=round((time.monotonic() - t0) * 1000.0, 1)))
        return block

    # ------------------------------------------------------------------ step 5

    def _calibration(self) -> Optional[CalibrationIndex]:
        try:
            raw = self.d.store.kv_list(CALIBRATION_NS)
            emb = {k: list(v.get("embedding") or []) for k, v in raw.items() if isinstance(v, dict)}
            index = CalibrationIndex.from_store(self.d.store, {k: v for k, v in emb.items() if v})
            return index if index.ready() else None
        except Exception:
            return None

    async def _convene(self, run_id: str, req: RunRequest, profile: TaskProfile, mode: Any, seed: int,
                       project: str, emit: Callable) -> tuple[LineupRecord, Optional[str], Any]:
        d = self.d
        table = router_stats.load_table(d.registry, d.store)
        try:
            total_runs = len(d.store.list_runs())
            recent = d.store.recent_lineups(max(1, int(d.config.router.repeat_window)))
        except Exception:
            total_runs, recent = 0, []
        await self._adopt()
        resident = self._resident_ids()
        lineup = picker.pick(
            profile, int(mode.k), d.registry, table, self._seat_budget(), d.config.router,
            resident=resident, recent=recent, deadline_s=float(mode.deadline_s), seed=seed,
            total_runs=total_runs, override=list(req.lineup_override) if req.lineup_override else None,
            calibration=self._calibration(), embedding=list(profile.embedding) or None,
        )
        lineup = self._plan_memory(run_id, req, lineup, emit)  # may shrink the council
        lineup = self._pick_chair(lineup, seed)
        eligible = {m.id for m in picker.eligible_models(profile, d.registry)}
        candidates = []
        for m in d.registry:
            ok = m.id in eligible
            reason = "" if ok else (
                "failed to load" if m.id in d.failed_models else
                "not active" if m.status != "active" else
                "no seat role" if "seat" not in m.roles else
                "footprint not measured" if m.measured.ram_gb_live is None else
                "does not cover the task needs")
            candidates.append(dict(model_id=m.id, display=m.display or m.id, lab=m.lab,
                                   q=q_tier_a(m.id, profile, table), eligible=ok, reason=reason))
        emit(ET.ROUTER_CANDIDATES_SCORED, dict(
            candidates=candidates, lineups_considered=len(lineup.rejected) + 1,
            top=[dict(models=[s.model_id for s in lineup.seats if not s.is_wildcard],
                      score=lineup.chosen_score)] + list(lineup.rejected),
            tier=lineup.tier, k=lineup.k))
        self._emit_lineup(lineup, resident, req, emit)
        d.store.put_json("lineups", run_id, lineup)

        first = lineup
        lineup, replaced = await self._load_seats(run_id, lineup, profile, table, project, emit)
        if lineup is not first:  # a seat changed: the record everyone sees is the final one
            state = self._run_state(run_id)
            if state.get("roles"):  # roles were given to seats: give them to the final seats
                try:
                    state["roles"] = roles_mod.assign_roles(
                        [s.model_id for s in lineup.seats], {m.id: m for m in d.registry},
                        {}, False, None)
                except Exception:
                    state["roles"] = None
            lineup = self._pick_chair(lineup, seed)
            self._emit_lineup(lineup, self._resident_ids(), req, emit)
            d.store.put_json("lineups", run_id, lineup)
        clerk = await self._load_clerk(run_id, {s.model_id for s in lineup.seats}, project, emit)
        seated = {s.model_id for s in lineup.seats} | {clerk}
        for payload in self._run_state(run_id).pop("steered", {}).values():
            if payload["model_id"] in seated:
                emit(ET.STEER_APPLIED, payload)
        for s in lineup.seats:
            m = self._entry(s.model_id)
            emit(ET.SEAT_ASSIGNED, dict(
                seat_no=s.seat_no, model_id=s.model_id, display=m.display or m.id,
                lab=m.lab, lens=s.lens, is_wildcard=s.is_wildcard,
                is_chair=s.is_chair, q=s.q,
                label=chr(ord("A") + s.seat_no) if s.seat_no < 26 else None,
                replaces_model_id=replaced.get(s.seat_no)))
        return lineup, clerk, table

    def _pick_chair(self, lineup: LineupRecord, seed: int) -> LineupRecord:
        """chamber.chair_pick "random": one seat, drawn from the seed, is the chair. "router"
        (and a chair that is no seat) keeps what the router named."""
        if getattr(self.d.config.chamber, "chair_pick", "router") != "random" or not lineup.seats:
            return lineup
        seats = sorted(lineup.seats, key=lambda s: s.seat_no)
        if lineup.chair_model_id and lineup.chair_model_id not in {s.model_id for s in seats}:
            return lineup  # an external chair is not a seat: nothing to draw
        chair = random.Random(f"{seed}:chair").choice(seats)
        return lineup.model_copy(update=dict(
            chair_model_id=chair.model_id,
            seats=[s.model_copy(update={"is_chair": s.seat_no == chair.seat_no}) for s in lineup.seats]))

    def _effort(self, req: RunRequest, opts: dict, profile: TaskProfile, mode: Any,
                lineup: LineupRecord, emit: Callable) -> tuple[Any, int]:
        """Adaptive effort: (mode scaled to the task, extra voting rounds a close vote may add).
        The mode comes back unchanged outside standard mode, with chamber.adaptive off, or with
        options.effort == "fixed"."""
        chamber = self.d.config.chamber
        want = opts.get("effort")
        if req.mode != "standard" or not bool(getattr(chamber, "adaptive", False)) or want == "fixed":
            return mode, 0
        planned_from = profile
        if want in _FORCED_EFFORT:  # the user forces the level: the profile no longer decides
            planned_from = profile.model_copy(update=dict(
                difficulty=_FORCED_EFFORT[want], contested=False,
                deliverable="answer" if want == "light" else profile.deliverable))
        tps = self._seat_tps(lineup)
        plan = plan_effort(planned_from, mode, req.mode, [tps[n] for n in sorted(tps)], chamber)
        deadline = opts.get("deadline_s")
        if isinstance(deadline, (int, float)) and not isinstance(deadline, bool) and deadline > 0:
            plan = plan.model_copy(update={"deadline_s": float(deadline)})  # an explicit deadline wins
        emit(ET.EFFORT_PLANNED, dict(
            level=plan.level, rounds=list(plan.rounds), deadline_s=plan.deadline_s,
            reasoning=plan.reasoning, max_extra_rounds=plan.max_extra_rounds,
            difficulty=planned_from.difficulty, rationale=plan.rationale))
        return apply_effort(mode, plan), int(plan.max_extra_rounds)

    def _emit_lineup(self, lineup: LineupRecord, resident: set, req: RunRequest, emit: Callable) -> None:
        seat_ids = [s.model_id for s in lineup.seats]
        extra = [lineup.chair_model_id] if lineup.chair_model_id not in (None, *seat_ids) else []
        infos = []
        for mid in seat_ids + extra:
            m = self._entry(mid)
            infos.append(dict(
                model_id=m.id, display=m.display or m.id, lab=m.lab, lineage=m.lineage,
                params_b=m.params_b, quant=m.quant,
                footprint_gib=float(m.measured.ram_gb_live or 0.0), resident=m.id in resident))
        emit(ET.ROUTER_LINEUP_SELECTED, dict(
            lineup=lineup, models=infos, chair_model_id=lineup.chair_model_id,
            wildcard_seat_no=next((s.seat_no for s in lineup.seats if s.is_wildcard), None),
            score=lineup.chosen_score, mode=req.mode, k=lineup.k,
            labs=len({i["lab"] or i["model_id"] for i in infos}),
            overridden=bool(req.lineup_override)))

    # ------------------------------------------------------------------ step 5: loading

    def _mark_failed(self, model_id: str, error: str) -> None:
        """This model is out for the rest of the process (see the module notes)."""
        d = self.d
        d.failed_models[model_id] = str(error)[:300]
        try:
            for i, m in enumerate(d.registry):
                if m.id == model_id and not isinstance(m, FailedModelEntry):
                    d.registry[i] = FailedModelEntry.model_validate(
                        {**m.model_dump(), "status": "failed"})
        except Exception:
            pass  # failed_models alone still keeps it out of the seats

    async def _load_one(self, run_id: str, model_id: str, project: Optional[str]) -> Optional[str]:
        """Seat one model for this run. None when it is resident, else the error text."""
        d = self.d
        known = d.failed_models.get(model_id)
        if known is not None:
            return f"load failed earlier in this process: {known}"
        applied = await self._steer_seat(project, model_id)
        try:
            await d.host.ensure_resident([model_id], "live", run_id, project=project)
        except HostError as exc:
            error = str(exc) or exc.__class__.__name__
            if not any(mark in error for mark in _NOT_A_MODEL_FAULT):
                self._mark_failed(model_id, error)
            return error
        if applied is not None:
            self._run_state(run_id).setdefault("steered", {})[model_id] = applied
        return None

    def _model_event(self, model_id: str, **more: Any) -> dict:
        m = self._entry(model_id)
        return dict(model_id=m.id, display=m.display or m.id, lab=m.lab,
                    footprint_gib=float(m.measured.ram_gb_live or 0.0), serve_profile="live", **more)

    def _substitute(self, profile: TaskProfile, table: Any, taken: set, alternates: list,
                    tried: set, budget: float) -> Optional[str]:
        """The model that takes a seat whose model failed: the lineup's alternates in order, then
        any other eligible model, one that keeps the lab rule first, then by q."""
        d = self.d
        by_id: dict[str, ModelEntry] = {}
        for m in d.registry:
            by_id.setdefault(m.id, m)

        def size(mid: str) -> float:
            m = by_id.get(mid)
            return float(m.measured.ram_gb_live or 0.0) if m is not None else 0.0

        used = sum(size(x) for x in taken)

        def usable(mid: str) -> bool:
            m = by_id.get(mid)
            return (m is not None and m.status == "active" and mid not in taken and mid not in tried
                    and mid not in d.failed_models and used + size(mid) <= budget + _EPS)

        for mid in alternates:
            if usable(mid):
                return mid
        try:
            pool = [m for m in picker.eligible_models(profile, d.registry) if usable(m.id)]
        except Exception:
            return None
        max_lab = max(1, int(getattr(d.config.router, "max_per_lab", 1) or 1))
        labs = Counter((by_id[x].lab or x) for x in taken if x in by_id)

        def rank(m: ModelEntry) -> tuple:
            try:
                q = float(q_tier_a(m.id, profile, table))
            except Exception:
                q = 0.0
            return (labs[m.lab or m.id] >= max_lab, -q, m.id)

        pool.sort(key=rank)
        return pool[0].id if pool else None

    async def _load_seats(self, run_id: str, lineup: LineupRecord, profile: TaskProfile, table: Any,
                          project: str, emit: Callable) -> tuple[LineupRecord, dict[int, str]]:
        """Load the seats one at a time. Returns the final lineup (the same object when nothing
        changed) and {final seat_no: the model first picked for it} for the substituted seats."""
        d = self.d
        seats = list(lineup.seats)
        k = len(seats)
        fraction = float(getattr(d.config.chamber, "quorum_fraction", 0.6) or 0.6)
        need = max(1, math.ceil(fraction * k - _EPS))
        budget = self._seat_budget()
        resident = self._resident_ids()
        alternates = list(lineup.alternates)
        planned = {s.seat_no: s.model_id for s in seats}  # the models the seats hold, or will
        final: dict[int, SeatAssignment] = {}
        replaced: dict[int, str] = {}
        tried: set[str] = set()
        last_error = ""
        # Resident models first: seated at once, so no later load evicts them to make room.
        for seat in sorted(seats, key=lambda s: (s.model_id not in resident, s.seat_no)):
            mid: Optional[str] = seat.model_id
            while mid is not None:
                error = await self._load_one(run_id, mid, project)
                if error is None:
                    update: dict[str, Any] = {}
                    if mid != seat.model_id:
                        replaced[seat.seat_no] = seat.model_id
                        try:
                            q = float(q_tier_a(mid, profile, table))
                        except Exception:
                            q = 0.0
                        update = {"model_id": mid, "q": q}
                    final[seat.seat_no] = seat.model_copy(update=update) if update else seat
                    break
                last_error = error
                tried.add(mid)
                planned.pop(seat.seat_no, None)
                nxt = self._substitute(profile, table, set(planned.values()), alternates, tried, budget)
                emit(ET.MODEL_FAILED, self._model_event(mid, error=error[:300], stage="load",
                                                        replaced_by=nxt))
                if nxt is not None:
                    planned[seat.seat_no] = nxt
                mid = nxt
        if len(final) < need:
            raise HostError(f"only {len(final)} of {k} seats could be loaded "
                            f"(quorum {need}): {last_error}"[:400])
        if not replaced and len(final) == k:
            return lineup, {}

        kept = [final[n] for n in sorted(final)]
        ids = [s.model_id for s in kept]
        chair = lineup.chair_model_id
        if chair in {s.model_id for s in seats} and chair not in ids:  # the chair's model is gone
            best = 0
            for i, s in enumerate(kept):
                if s.q > kept[best].q:
                    best = i
            chair = ids[best]
        out_seats: list[SeatAssignment] = []
        out_replaced: dict[int, str] = {}
        for i, s in enumerate(kept):  # renumber: a dropped seat leaves no gap
            if s.seat_no in replaced:
                out_replaced[i] = replaced[s.seat_no]
            out_seats.append(s.model_copy(update={"seat_no": i, "is_chair": s.model_id == chair}))
        return lineup.model_copy(update=dict(
            seats=out_seats, k=len(out_seats), chair_model_id=chair,
            alternates=[a for a in alternates
                        if a not in ids and a not in tried and a not in d.failed_models],
        )), out_replaced

    async def _load_clerk(self, run_id: str, seat_ids: set, project: str, emit: Callable) -> Optional[str]:
        """The clerk, resident. A clerk that cannot be loaded gives way to the next model with the
        clerk role; with none left the council sits without a clerk."""
        tried: set[str] = set()
        shared = ((self._state.get(run_id) or {}).get("roles") or {}).get("clerk")
        if shared in seat_ids:
            return shared  # the memory plan gave the clerk's job to a seated model

        def pick_clerk() -> Optional[str]:
            return next((m.id for m in self.d.registry
                         if m.status == "active" and "clerk" in m.roles and m.id not in tried), None)

        while True:
            clerk = pick_clerk()
            if clerk is None or clerk in seat_ids:
                return clerk
            error = await self._load_one(run_id, clerk, project)
            if error is None:
                return clerk
            tried.add(clerk)
            emit(ET.MODEL_FAILED, self._model_event(clerk, error=error[:300], stage="load",
                                                    replaced_by=pick_clerk()))

    # ------------------------------------------------------------------ 1.5: memory plan

    def _is_mock(self) -> bool:
        return bool(getattr(getattr(self.d.config, "gateway", None), "mock", False))

    def _driver_name(self) -> str:
        return str(getattr(getattr(self.d.config, "host", None), "driver", "") or "")

    def _ctx_default(self) -> int:
        """The context window the driver loads a model with when nothing else is said."""
        cfg, name = self.d.config, self._driver_name()
        if not self._is_mock():
            if name == "llamacpp":
                return int(getattr(getattr(cfg, "llamacpp", None), "ctx", 0) or ctx_policy.DEFAULT_CTX)
            if name == "ollama":
                return int(getattr(getattr(cfg, "ollama", None), "num_ctx_live", 0) or 16384)
        return 16384

    def _per_model_ctx(self) -> bool:
        driver = getattr(self.d.host, "driver", None)
        return hasattr(driver, "ctx_for") and callable(getattr(driver, "ctx_of", None))

    def _sizes(self, ids: list[str]) -> dict[str, float]:
        """Real GiB per model: the on-box check, else the registry, else reported x overhead."""
        d = self.d
        mem = getattr(d.config, "memory", None)
        checks: dict = {}
        try:
            raw = str(getattr(mem, "measured_file", "") or "")
            path = Path(raw).expanduser() if raw else model_checks.default_path(Path(d.home))
            checks = model_checks.by_model_id(model_checks.load_checks(path), d.registry)
        except Exception:
            checks = {}
        overhead = float(getattr(mem, "overhead", 1.35) or 1.35)
        out: dict[str, float] = {}
        for mid in ids:
            check = checks.get(mid)
            live = self._entry(mid).measured.ram_gb_live
            if check is not None and check.ram_gib:
                out[mid] = float(check.ram_gib)
            elif live is not None:
                out[mid] = float(live)
            elif check is not None and check.reported_gib:
                out[mid] = float(check.reported_gib) * overhead
        return out

    def _total_gib(self) -> tuple[float, bool]:
        """(total memory, True when it was read from the machine)."""
        if not self._is_mock():
            try:
                total = meminfo.read_meminfo().get("MemTotal", 0) / meminfo.KB_PER_GIB
                if total > 0:
                    return float(total), True
            except Exception:
                pass
        try:
            ram = self.d.host.ram
            resident = sum(float(r.get("footprint_gib") or 0.0) for r in self.d.host.status())
            return float(ram.read_available_gib()) + resident, False
        except Exception:
            return _FALLBACK_BUDGET_GIB, False

    @staticmethod
    def _keep_seats(lineup: LineupRecord, keep: list[SeatAssignment]) -> LineupRecord:
        """The lineup with only `keep`, renumbered. A chair that left gives way to the best seat."""
        ids = [s.model_id for s in keep]
        chair = lineup.chair_model_id
        if chair in {s.model_id for s in lineup.seats} and chair not in ids:
            chair = max(keep, key=lambda s: (s.q, -s.seat_no)).model_id
        seats = [s.model_copy(update={"seat_no": i, "is_chair": s.model_id == chair})
                 for i, s in enumerate(keep)]
        return lineup.model_copy(update=dict(seats=seats, k=len(seats), chair_model_id=chair))

    def _plan_memory(self, run_id: str, req: RunRequest, lineup: LineupRecord,
                     emit: Callable) -> LineupRecord:
        """Plan roles, contexts and seats against the machine's memory, before anything loads.
        Returns the lineup, smaller when the seats did not fit. Never raises."""
        try:
            return self._plan_memory_inner(run_id, req, lineup, emit)
        except Exception:  # noqa: BLE001 - the plan is advice; the Host still guards every load
            return lineup

    def _plan_memory_inner(self, run_id: str, req: RunRequest, lineup: LineupRecord,
                           emit: Callable) -> LineupRecord:
        d = self.d
        mem = getattr(d.config, "memory", None)
        if mem is None or not lineup.seats:
            return lineup
        by_id: dict[str, ModelEntry] = {}
        for m in d.registry:
            by_id.setdefault(m.id, m)
        preferred = {r: self._role(r) for r in roles_mod.ROLE_NAMES}
        tps = {m.id: float(m.measured.tps_1) for m in d.registry if getattr(m.measured, "tps_1", None)}
        total, measured = self._total_gib()
        ctx_default = self._ctx_default()
        per_model = self._per_model_ctx()
        steps = tuple(s for s in _CTX_STEPS if s <= ctx_default) if per_model else ()
        share = str(getattr(mem, "share_roles", "auto") or "auto")

        def plan_for(seat_ids: list[str], roles: dict) -> MemoryPlan:
            ids = list(dict.fromkeys(seat_ids + [m for m in roles.values() if m]))
            return memplan.plan_memory(
                seat_ids, dict(roles), self._sizes(ids), total,
                reserve_gib=float(getattr(mem, "reserve_gib", 10.0)),
                overhead=float(getattr(mem, "overhead", 1.35)),
                ctx_default=ctx_default, ctx_steps=steps or (ctx_default,))

        def decide(seat_ids: list[str]) -> tuple[MemoryPlan, Optional[dict]]:
            """(plan, roles moved to seats for this run or None when the configured ones stay)."""
            configured = {r: m for r, m in preferred.items() if m and r in _BESIDE_SEATS}
            first = plan_for(seat_ids, configured)
            fits_extra = first.fits and not first.shared_roles and not first.dropped
            if share == "never" or (share == "auto" and fits_extra):
                return first, None
            roles = roles_mod.assign_roles(seat_ids, by_id, preferred, False, tps)
            return plan_for(seat_ids, roles), roles

        seats = sorted(lineup.seats, key=lambda s: s.seat_no)
        plan, shared = decide([s.model_id for s in seats])
        gone: list[str] = []
        while not plan.fits and len(seats) > MIN_SEATS:
            worst = min(seats, key=lambda s: (s.q, -s.seat_no))  # lowest q, the later seat on a tie
            seats = [s for s in seats if s.seat_no != worst.seat_no]
            gone.append(worst.model_id)
            plan, shared = decide([s.model_id for s in seats])
        notes = list(plan.notes)
        if shared is not None:
            notes.append("The work roles go to seated models for this run: "
                         + ", ".join(f"{r} = {m}" for r, m in sorted(shared.items())) + ".")
        if gone:
            lineup = self._keep_seats(lineup, seats)
            notes.append(f"The council shrank from {len(seats) + len(gone)} to {len(seats)} seats: "
                         f"{', '.join(gone)} (lowest scored) did not fit in memory.")
        if not plan.fits:
            notes.append(f"Still over the budget with {len(seats)} seats: the run goes on and the "
                         "host decides at load.")
        if shared is None:
            notes.append("The workers load once the seats are idle, so they are not counted here.")
        if not measured:
            notes.append("Total memory is what the host budget sees, not read from the machine.")
        if not per_model:
            notes.append("This driver loads every model with one context size.")
        plan = plan.model_copy(update=dict(
            notes=notes, dropped=list(plan.dropped) + [g for g in gone if g not in plan.dropped]))

        state = self._run_state(run_id)
        state["roles"] = shared
        if per_model:
            plan = plan.model_copy(update={"num_ctx": self._apply_ctx(
                plan, [s.model_id for s in seats], req.mode, ctx_default)})
            state["ctx"] = dict(plan.num_ctx)
        try:
            d.store.kv_put(MEMORY_NS, run_id, plan.model_dump(mode="json"))
        except Exception:
            pass
        emit(ET.MEMORY_PLANNED, dict(plan=plan.model_dump(mode="json")))
        return lineup

    def _apply_ctx(self, plan: MemoryPlan, seat_ids: list[str], mode: str, ctx_default: int) -> dict[str, int]:
        """Hand the driver one context per model. Returns what each model runs (or will run) with."""
        d = self.d
        resident = self._resident_ids()
        role_of: dict[str, list[str]] = {m: ["seat"] for m in seat_ids}
        for role, mid in plan.roles.items():
            role_of.setdefault(mid, []).append(role)
        for mid, ctx in plan.num_ctx.items():
            if mid in resident and mid in d.model_ctx:
                continue  # it runs already: no reload for a context
            policy = max(ctx_policy.ctx_for(r, mode) for r in role_of.get(mid, ["seat"]))
            d.model_ctx[mid] = max(1024, min(int(ctx), int(policy), int(ctx_default)))
        wanted = d.model_ctx
        d.host.driver.ctx_for = lambda model_id: wanted.get(model_id)
        return {mid: int(wanted.get(mid, ctx)) for mid, ctx in plan.num_ctx.items()}

    def _ctx_tokens(self, run_id: str, lineup: LineupRecord) -> Optional[int]:
        """The context window of the seats (the smallest one), None when nothing is known."""
        known = (self._state.get(run_id) or {}).get("ctx") or {}
        sizes = [int(known[s.model_id]) for s in lineup.seats if known.get(s.model_id)]
        if sizes:
            return min(sizes)
        if self._is_mock() or self._driver_name() not in ("llamacpp", "ollama"):
            return None
        return self._ctx_default()

    # ------------------------------------------------------------------ 1.5: steering

    def _steer_on(self) -> bool:
        return bool(getattr(getattr(self.d.config, "steer", None), "enabled", False))

    def _steering_of(self, project: Optional[str], model_id: str) -> Optional[tuple[Path, float, list]]:
        """(vector file, strength, layers) of the active steering vector of a seat, or None."""
        d = self.d
        if not project or not self._steer_on():
            return None
        try:
            card = d.steer_store.active(project, model_id) if d.steer_store is not None else None
            if card is not None and card.active and card.scale is not None and card.path \
                    and Path(card.path).is_file():
                return Path(card.path), float(card.scale), list(card.layers)
        except Exception:
            pass
        return None

    async def _steer_seat(self, project: Optional[str], model_id: str) -> Optional[dict]:
        """Before a model loads: put its steering vector on it, or make sure none is set.
        Returns the steer.applied payload, None when no vector is applied. Never raises."""
        d = self.d
        found = self._steering_of(project, model_id)
        try:
            if found is None:
                await apply_steering(d.host, d.steer_live, model_id, None)
                return None
            path, scale, layers = found
            if not await apply_steering(d.host, d.steer_live, model_id, path, scale):
                return None  # this driver cannot steer
            return dict(project=project, model_id=model_id, scale=scale, layers=layers, source=str(path))
        except asyncio.CancelledError:
            raise
        except Exception:
            return None

    async def _train_steering(self, run_id: str, emit: Callable) -> None:
        """After the reflection: one steering vector per (project, model) this run corrected.
        Never fails the run."""
        d = self.d
        due = list(dict.fromkeys((self._state.get(run_id) or {}).pop("steer_due", [])))
        if not due or d.steer is None or not self._steer_on():
            return
        need = int(getattr(d.config.steer, "min_examples", 0) or 0)
        for project, model_id in due:
            try:
                rows = [c for c in d.store.corrections_list(project) if c.model_id == model_id]
                pairs = contrast.from_corrections(rows)
                service = copy.copy(d.steer)
                service.emit = emit
                if contrast.enough(pairs, need):
                    await self._seat(run_id, [model_id])  # the template is asked of the loaded model
                source = getattr(service, "source", None)
                depth = None if hasattr(source, "info") else _MOCK_LAYERS
                await service.train(project, model_id, pairs, n_layer=depth)
            except asyncio.CancelledError:
                raise
            except Exception:
                continue

    # ------------------------------------------------------------------ steps 6 to 9

    def _protocol(self, opts: Optional[dict] = None) -> str:
        """The council protocol of a run: options["protocol"], else chamber.protocol."""
        said = str((opts or {}).get("protocol") or "").strip().lower()
        if said in ("structured", "open"):
            return said
        return str(getattr(self.d.config.chamber, "protocol", "structured") or "structured")

    def _new_deliberation(self, run_id: str, task: str, profile: TaskProfile, lineup: LineupRecord,
                          mode: Any, record: str, brief: str, clerk: Optional[str], opts: dict,
                          seed: int, project: str, max_extra_rounds: int = 0) -> Deliberation:
        chamber = self.d.config.chamber
        notes: dict[int, str] = {}
        if self.d.corrections is not None:
            for s in lineup.seats:
                try:
                    text = self.d.corrections.notes_for(project, s.model_id, task)
                except Exception:
                    text = ""
                if text:
                    notes[s.seat_no] = text
        more: dict[str, Any] = {}
        ctx = self._ctx_tokens(run_id, lineup)
        if ctx:
            more["ctx_tokens"] = int(ctx)
        maker: Any = Deliberation
        if self._protocol(opts) == "open":
            # Free text for all, by name, plus a card per message (chamber/open_debate.py).
            maker = OpenDebate
            more["seat_names"] = seat_names(
                {s.seat_no: self._entry(s.model_id).display or s.model_id for s in lineup.seats})
        return maker(
            run_id, task, profile, lineup, mode, record=record, brief=brief,
            lens_texts=self.d.lens_texts, clerk_model_id=clerk, answer_type=opts.get("answer_type"),
            cfg=ConsensusConfig(
                threshold=float(chamber.consensus_threshold),
                quorum_fraction=float(chamber.quorum_fraction),
                blocking_to_veto=int(chamber.blocking_objections_to_veto),
                early_exit_min_confidence=float(chamber.early_exit_min_confidence),
            ),
            seed=seed,
            plan_mode=profile.deliverable in ("plan", "build") and bool(chamber.ratify_in_plan_mode),
            seat_notes=notes,
            seat_tps=self._seat_tps(lineup),
            max_extra_rounds=max(0, int(max_extra_rounds)),
            extend_min_agreement=float(getattr(chamber, "extend_min_agreement", 0.5)),
            **more,
        )

    async def _deliberate(self, run_id: str, delib: Deliberation, lineup: LineupRecord, mode: Any,
                          workspace: Optional[Path], project: str, reliability: Any) -> Decision:
        if isinstance(delib, OpenDebate):  # no drafts and no claim scores: a reading per message
            return await self._deliberate_open(run_id, delib, lineup, mode, workspace, reliability)
        evidence = EvidenceRunner(workspace)
        probe_cfg = getattr(self.d.config, "probe", None)
        lie_cfg = getattr(self.d.config, "lie", None)
        probe_on = reliability is not None and bool(getattr(probe_cfg, "enabled", True))
        lie_on = reliability is not None and bool(getattr(lie_cfg, "enabled", False)) \
            and hasattr(reliability, "lie_report")
        scoring = probe_on or lie_on
        show = bool(getattr(probe_cfg, "show_to_council", True))
        show_lie = bool(getattr(lie_cfg, "show_to_council", True))
        # The whole step may hold round 1 back this long, no longer.
        limit = max(0.01, float(getattr(lie_cfg, "timeout_s", 20.0) or 20.0)) * max(1, len(lineup.seats)) \
            + _LIE_SLACK_S

        async def score(proxy: _ScoredDeliberation) -> None:
            try:
                report = None
                if probe_on:
                    job = reliability.score_round0(
                        run_id, project, list(lineup.seats), delib.drafts(), dict(proxy.results),
                        proxy.messages_for)
                    scores = await (asyncio.wait_for(job, limit) if lie_on else job)
                    if show and not delib.is_done():
                        delib.set_claim_scores(scores)
                    if lie_on:
                        report = reliability.last_report(run_id)
                else:
                    report = await asyncio.wait_for(reliability.lie_report(
                        run_id, str(getattr(delib, "task", "") or ""), list(lineup.seats),
                        delib.drafts()), limit)
                if report is not None and show_lie and not delib.is_done():
                    delib.set_lie_flags(list(report.flags))
            except asyncio.CancelledError:
                raise
            except Exception:
                pass  # scores and flags are advisory: a broken or slow probe never stops a council

        if not scoring:
            return await LiveExecutor(self.d.gateway, self.d.bus, evidence_runner=evidence.run).run(
                delib, run_id, float(mode.deadline_s))

        proxy = _ScoredDeliberation(delib, score)

        async def runner(check: Any) -> EvidenceResult:
            if getattr(check, "check_id", "") == _SCORE_CHECK:
                await proxy.score()
                return EvidenceResult(kind="python", id=_SCORE_CHECK, ok=True)
            return await evidence.run(check)

        decision = await LiveExecutor(self.d.gateway, self.d.bus, evidence_runner=runner).run(
            proxy, run_id, float(mode.deadline_s))
        if proxy.need:  # no round 1 (quick mode, early exit): the ledger still gets the drafts
            await proxy.score()
        try:
            reliability.ledger.label_from_evidence(run_id, delib.evidence(), delib.cruxes())
        except Exception:
            pass
        return decision

    async def _deliberate_open(self, run_id: str, delib: Any, lineup: LineupRecord, mode: Any,
                               workspace: Optional[Path], reliability: Any) -> Decision:
        """Run an OpenDebate. With the lie detector on, every message gets a reading before
        the next round reads it."""
        evidence = EvidenceRunner(workspace)
        lie_cfg = getattr(self.d.config, "lie", None)
        if reliability is None or not bool(getattr(lie_cfg, "enabled", False)):
            return await LiveExecutor(self.d.gateway, self.d.bus, evidence_runner=evidence.run).run(
                delib, run_id, float(mode.deadline_s))

        async def read(msgs: list) -> dict:
            return await self._message_readings(reliability, str(delib.task or ""), lineup, msgs)

        proxy = _LieDebate(delib, read)

        async def runner(check: Any) -> EvidenceResult:
            if getattr(check, "check_id", "") == _SCORE_CHECK:
                await proxy.read()
                return EvidenceResult(kind="python", id=_SCORE_CHECK, ok=True)
            return await evidence.run(check)

        decision = await LiveExecutor(self.d.gateway, self.d.bus, evidence_runner=runner).run(
            proxy, run_id, float(mode.deadline_s))
        try:  # the last round's messages: nobody reads them any more, the UI still shows them
            await proxy.read(final=True)
            emit = self._emitter(run_id)
            for type_, payload in delib.take_events():
                emit(type_, payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        return decision

    async def _message_readings(self, reliability: Any, task: str, lineup: LineupRecord,
                                msgs: list) -> dict[str, dict]:
        """{turn_id: lie-detector reading} of open-protocol messages. The statement scored is
        the stance on the message's card, else its note, else the message's first sentence, by
        the truth probe of the seat's model (LiveScorer on the reliability service's source and
        probes).

        Members are read in a fixed order (round, seat), one capture at a time when the source
        holds one model. [lie].timeout_s bounds each member's own load + capture, not its wait
        for the others; the batch is bounded by timeout_s * members to read, and whoever is not
        reached by then gets "reading timed out". Never raises. With no score the reading is
        score None, level "ok" and one reason: "no probe" (nothing trained, or no source),
        "probe not trusted for this model" (a probe exists and is not active),
        "reading timed out", "reading failed" or "nothing to read"."""
        out: dict[str, dict] = {m.turn_id: dict(_NO_READING, reasons=[_WHY_NO_PROBE]) for m in msgs}
        try:
            lie_cfg = getattr(self.d.config, "lie", None)
            timeout = max(0.01, float(getattr(lie_cfg, "timeout_s", 20.0) or 20.0))
            flag_below = float(getattr(lie_cfg, "flag_below", 0.30))
            watch_below = float(getattr(lie_cfg, "watch_below", 0.45))
            model = {s.seat_no: s.model_id for s in lineup.seats}
            if reliability is None or getattr(reliability, "source", None) is None:
                return out

            def why(turn_id: str, reason: str) -> None:
                out[turn_id] = dict(_NO_READING, reasons=[reason])

            items: list[tuple[str, str, str]] = []
            for m in sorted(msgs, key=lambda m: (int(m.round), int(m.seat_no), str(m.turn_id))):
                mid = model.get(m.seat_no)
                state = _probe_state(reliability, mid) if mid else "none"
                if state != "active":
                    why(m.turn_id, _WHY_UNTRUSTED if state == "untrusted" else _WHY_NO_PROBE)
                    continue
                text = _reading_text(m)
                if not text:
                    why(m.turn_id, _WHY_NO_TEXT)
                    continue
                why(m.turn_id, _WHY_TIMEOUT)  # what stays if the batch is cut off
                items.append((m.turn_id, mid, text))
            if not items:
                return out

            scorer = LiveScorer(reliability.source, reliability.active_probes,
                                platt_for=reliability.platt_for, timeout_s=timeout, max_claims=1)
            budget = timeout * len(items)
            try:
                # The outer limit only guards a source that ignores its own timeout.
                got = await asyncio.wait_for(
                    scorer.read_many(task, items, budget_s=budget), budget + _LIE_SLACK_S)
            except asyncio.TimeoutError:
                got = {}
            finally:
                release = getattr(reliability, "_release", None)
                if release is not None:
                    await release()
            for turn_id, (score, status) in got.items():
                if score is None or status != "ok":
                    why(turn_id, _WHY_TIMEOUT if status == "timeout"
                        else _WHY_UNTRUSTED if status == "no_probe" else _WHY_FAILED)
                    continue
                score = min(1.0, max(0.0, float(score)))
                level = "flag" if score < flag_below else "watch" if score < watch_below else "ok"
                out[turn_id] = {"score": score, "level": level,
                                "reasons": [f"truth probe reads the stance at {score:.2f}"]}
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        return out

    def _lie_flags(self, reliability: Any, run_id: str, seat_no: int) -> list:
        """The lie detector's flags on one seat (for the Tribunal). [] when there are none."""
        lie_cfg = getattr(self.d.config, "lie", None)
        if reliability is None or not bool(getattr(lie_cfg, "enabled", False)):
            return []
        try:
            report = reliability.last_report(run_id)
            return [f for f in (report.flags if report is not None else []) if f.seat_no == seat_no]
        except Exception:
            return []

    # ------------------------------------------------------------------ 27: tribunal

    def _tribunal_applies(self, req: RunRequest, opts: dict, decision: Decision) -> bool:
        cfg = getattr(self.d.config, "tribunal", None)
        if cfg is None or not bool(getattr(cfg, "enabled", True)):
            return False
        if opts.get("bench") and not bool(getattr(cfg, "in_bench", False)):
            return False
        return (req.mode in _TRIBUNAL_MODES and decision.outcome in _TRIBUNAL_OUTCOMES
                and decision.option_id is not None)

    async def _examine(self, run_id: str, req: RunRequest, delib: Deliberation, decision: Decision,
                       lineup: LineupRecord, project: str, seed: int, reliability: Any, ctl: RunControl,
                       emit: Callable) -> tuple[Decision, Optional[TribunalOutcome], Optional[Correction]]:
        chosen = decision.option_id
        ballots, r0, options = delib.final_ballots(), delib.r0_options(), delib.options()
        outlier = find_outlier(ballots, r0, chosen, len(options))
        if outlier is None:
            return decision, None, None  # unanimous: nothing to examine
        cfg = self.d.config.tribunal
        await self._to(ctl, RunState.EXAMINING, f"seat {outlier} is cross-examined")
        t0 = time.monotonic()
        ballot = ballots.get(outlier)
        held_id = ballot.choice if ballot is not None else r0.get(outlier)
        held = next((o for o in options if o.id == held_id), None)
        draft = delib.drafts().get(outlier)
        position = (ballot.final_answer if ballot is not None and ballot.final_answer else "") or (
            draft.answer if draft is not None else "") or (held.summary if held is not None else "")
        if held is not None and held.summary and held.summary not in position:
            position = f"{held.summary}\n\n{position}".strip()
        cruxes, evidence = delib.cruxes(), delib.evidence()
        by_evidence = evidence_supports(evidence, chosen)
        askers = examiners(list(lineup.seats), outlier, ballots, chosen, int(cfg.questions))
        seat_model = {s.seat_no: s.model_id for s in lineup.seats}
        emit(ET.TRIBUNAL_STARTED, dict(
            outlier_seat=outlier, outlier_model_id=seat_model.get(outlier, ""),
            distance=seat_distance(ballot, r0.get(outlier), chosen, len(options)),
            option_id=chosen, outlier_option_id=held_id, examiners=askers,
            judges=sorted(s for s in seat_model if s != outlier), questions=len(askers)))

        trib = Tribunal(run_id, req.task, decision, lineup, outlier, position, askers, cruxes, evidence,
                        cfg=cfg, verified_by_evidence=by_evidence, seed=seed,
                        lie_flags=self._lie_flags(reliability, run_id, outlier))
        for type_, payload in trib.take_events():
            emit(type_, payload)
        while not trib.is_done():
            self._check(ctl)
            specs = trib.pending_calls()
            events = []
            if not specs:
                events = trib.on_deadline()
            else:
                for result in await asyncio.gather(*(self._call(s) for s in specs)):
                    events += trib.on_result(result)
            for type_, payload in events:
                emit(type_, payload)
        outcome = trib.outcome()
        ok, why = trib.eligible()

        correction: Optional[Correction] = None
        model = self._entry(seat_model.get(outlier))
        if ok and self.d.corrections is not None and outcome.outcome in ("conceded", "failed"):
            correction = build_correction(outcome, project, model, run_id, req.task, position,
                                          decision.final_text, why, self.d.now())
            dataset = self.d.corrections.record(correction)
            outcome = outcome.model_copy(update={"correction_id": correction.id})
            size = int(self.d.corrections.dataset_size(project, model.id))
            emit(ET.CORRECTION_RECORDED, dict(correction=correction, seat_no=outlier, model_id=model.id,
                                              project=project, dataset_size=size))
            # The steering vector of this (project, model) is rebuilt once the run has reflected.
            self._run_state(run_id).setdefault("steer_due", []).append((project, model.id))
        if reliability is not None:
            try:
                reliability.ledger.label_from_tribunal(run_id, outcome)
            except Exception:
                pass

        if outcome.outcome == "vindicated":
            answers = [a.answer for a in outcome.answers if a.answer]
            decision = decision.model_copy(update=dict(
                contested_after_review=True,
                minority_report=[MinorityPosition(
                    seats=[outlier], position=position[:1200],
                    strongest_argument=(answers[0] if answers else position)[:600], option_id=held_id)],
            ))
            emit(ET.DECISION_FINAL, dict(decision=decision, options=options,
                                         ms=round((time.monotonic() - t0) * 1000.0, 1)))
        return decision, outcome, correction

    # ------------------------------------------------------------------ steps 10 to 13

    async def _plan(self, run_id: str, foreman: Foreman, goal: str, approach: str, brief: str,
                    lineup: LineupRecord) -> Plan:
        seats = sorted(lineup.seats, key=lambda s: (-s.q, s.seat_no))
        chair = lineup.chair_model_id or next((s.model_id for s in lineup.seats if s.is_chair), None) \
            or seats[0].model_id
        if getattr(self.d.config.chamber, "chair_pick", "router") == "random":
            chair = seats[0].model_id  # a drawn chair breaks ties; the best seat writes the plan
        second = next((s.model_id for s in seats if s.model_id != chair), None)
        # Writing a work plan is the hardest structured job in the run. A model marked "planner"
        # in the registry does it when there is one; the chair then becomes the second key.
        planner = self._role("planner", run_id)
        if planner and planner != chair:
            second, chair = chair, planner
        if chair not in {s.model_id for s in lineup.seats}:
            await self.d.host.ensure_resident([chair], "live", run_id)
        plan = await foreman.make_plan(run_id, goal, approach, brief, chair, second)
        self.d.store.put_json("plans", run_id, plan)
        return plan

    async def _review_ballots(self, seats: list, specs: list, cycle: int,
                              emit: Callable) -> dict[int, Optional[ReviewBallot]]:
        results = await asyncio.gather(*(self._call(s) for s in specs))
        ballots: dict[int, Optional[ReviewBallot]] = {}
        for seat, spec, res in zip(seats, specs, results):
            ballot = None
            if res.ok and isinstance(res.parsed, dict):
                try:
                    ballot = ReviewBallot.model_validate(res.parsed)
                except Exception:
                    ballot = None
            ballots[seat.seat_no] = ballot
            emit(ET.REVIEW_BALLOT, dict(seat_no=seat.seat_no, model_id=seat.model_id, cycle=cycle,
                                        ballot=ballot, call_id=spec.call_id))
        return ballots

    async def _review_vote(self, run_id: str, lineup: LineupRecord, plan: Plan, report: WorkReport,
                           cycle: int, max_cycles: int, emit: Callable) -> tuple[str, dict, list, dict]:
        """One review cycle: blind ballots, then one argument round when the vote is split.
        Returns (verdict, tally, fixes, final ballots)."""
        emit(ET.REVIEW_STARTED, dict(cycle=cycle, report=report,
                                     seats=[s.seat_no for s in lineup.seats], max_cycles=max_cycles))
        text = report_text(report)
        threshold = float(self.d.config.chamber.consensus_threshold)
        seats = list(lineup.seats)
        specs = [review_mod.build_review_call(run_id, s, text, plan.goal, cycle) for s in seats]
        ballots = await self._review_ballots(seats, specs, cycle, emit)
        verdict, counts = review_mod.decide_review(ballots, threshold)
        if bool(getattr(self.d.config.review, "debate", False)) and review_mod.needs_debate(ballots, threshold):
            specs = [review_mod.build_rebuttal_call(
                run_id, s, text, plan.goal, cycle, ballots.get(s.seat_no),
                [b for n, b in sorted(ballots.items()) if n != s.seat_no and b is not None])
                for s in seats]
            second = await self._review_ballots(seats, specs, cycle, emit)
            # A seat whose second call failed keeps its first vote.
            ballots = {n: second.get(n) or b for n, b in ballots.items()}
            before = counts
            verdict, counts = review_mod.decide_review(ballots, threshold)
            emit(ET.REVIEW_DEBATE, dict(cycle=cycle, tally_before=before, tally_after=counts))
        fixes = review_mod.merge_fixes(ballots) if verdict == "fix" else []
        return verdict, counts, fixes, ballots

    @staticmethod
    def _checks_pass(report: WorkReport) -> bool:
        """Every check that really ran on the current files passed, nothing deviates, and no
        work is missing (a failed task's files are rolled back, so its own check may have
        nothing left to fail on; a failed fix on files that were already right does not count)."""
        ran = [c for c in (report.final_checks or []) if not getattr(c, "invalid", False)]
        undone = int(getattr(report.summary, "unfinished", 0) or 0)
        return bool(ran) and all(c.ok for c in ran) and not report.deviations and not undone

    async def _final_say(self, run_id: str, lineup: LineupRecord, plan: Plan, report: WorkReport,
                         cycle: int, seed: int, history: list, emit: Callable) -> bool:
        """No agreement in time: one randomly picked seat decides from the record. True = accept."""
        seat = review_mod.pick_decider(list(lineup.seats), seed, cycle)
        spec = review_mod.build_final_call(run_id, seat, report_text(report), plan.goal, cycle, history)
        res = await self._call(spec)
        ballot: Optional[ReviewBallot] = None
        if res.ok and isinstance(res.parsed, dict):
            try:
                ballot = ReviewBallot.model_validate(res.parsed)
            except Exception:
                ballot = None
        accepted = review_mod.final_verdict(ballot)
        emit(ET.REVIEW_FINAL_SAY, dict(
            cycle=cycle, seat_no=seat.seat_no, model_id=seat.model_id,
            verdict="accept" if accepted else ballot.verdict,
            reason=ballot.reason if ballot is not None
            else "The deciding call failed: finished work is kept."))
        return accepted

    # ------------------------------------------------------------------ run

    async def run(self, run_id: str, req: RunRequest, ctl: RunControl) -> RunResult:
        try:
            return await self._run(run_id, req, ctl)
        finally:
            self._state.pop(run_id, None)
            try:
                self.d.host.release(run_id)
            except Exception:
                pass

    async def _run(self, run_id: str, req: RunRequest, ctl: RunControl) -> RunResult:
        d = self.d
        emit = self._emitter(run_id)
        opts = dict(req.options or {})
        seed = self._seed(run_id, opts)
        workspace = Path(req.workspace) if req.workspace else None
        project = project_id(workspace) if workspace is not None else NO_PROJECT
        reliability = None
        if d.reliability is not None:
            reliability = copy.copy(d.reliability)  # shared ledger and store, events on this run
            reliability.emit = emit
            if not bool(getattr(getattr(d.config, "lie", None), "enabled", False)):
                def no_lie(type_: str, payload: Any = None) -> None:  # [lie] is off
                    if type_ != ET.LIE_REPORT:
                        emit(type_, payload)

                reliability.emit = no_lie

        # 2 to 4: brief, profile, recall
        await self._to(ctl, RunState.PROFILING, "intake done")
        brief = await self._brief(workspace, emit)
        profile = await self._profile(req, emit)
        record = await self._recall(req, workspace, profile, emit)

        # 5: convene
        await self._to(ctl, RunState.CONVENING, "profile ready")
        mode = self._mode(req.mode, opts)
        lineup, clerk, table = await self._convene(run_id, req, profile, mode, seed, project, emit)
        mode, extra_rounds = self._effort(req, opts, profile, mode, lineup, emit)

        # 6 to 9: deliberate
        await self._to(ctl, RunState.DELIBERATING, "all seats resident")
        delib = self._new_deliberation(run_id, req.task, profile, lineup, mode, record, brief, clerk,
                                       opts, seed, project, max_extra_rounds=extra_rounds)
        decision = await self._deliberate(run_id, delib, lineup, mode, workspace, project, reliability)
        if decision.needs_user is not None and not opts.get("auto_input"):
            answer = await self._ask(ctl, decision.needs_user)
            said = answer.choice or answer.text or ""
            update: dict[str, Any] = {"needs_user": None}
            if said:
                update["final_text"] = (decision.final_text + f"\n\nUser decided: {said}").strip()
            decision = decision.model_copy(update=update)
        await self._to(ctl, RunState.DECIDED, f"decision: {decision.outcome}")
        d.store.put_json("decisions", run_id, decision)

        # 27: tribunal
        plan_like = profile.deliverable in ("plan", "build")
        outcome: Optional[TribunalOutcome] = None
        correction: Optional[Correction] = None
        proceed = True
        # The tribunal reads drafts, cruxes and claim flags of the structured protocol: it is
        # skipped for the open protocol for now.
        if not isinstance(delib, OpenDebate) and self._tribunal_applies(req, opts, decision):
            decision, outcome, correction = await self._examine(
                run_id, req, delib, decision, lineup, project, seed, reliability, ctl, emit)
            if outcome is not None:
                d.store.put_json("decisions", run_id, decision)
            if decision.contested_after_review and plan_like and not opts.get("auto_input"):
                answer = await self._ask(ctl, UserQuestion(
                    question="The dissenting seat defended its position under cross-examination. "
                             "Proceed with the council's decision?",
                    options=["proceed", "stop"],
                    context=(decision.minority_report[0].position if decision.minority_report else "")[:600]))
                proceed = (answer.choice or answer.text or "proceed").strip().lower() != "stop"

        result = RunResult(decision=decision, final_text=decision.final_text, tribunal=outcome,
                           correction=correction)
        if not plan_like or not proceed:
            events = None
            if not plan_like and opts.get("reflect") is not False and req.mode != "quick":
                self._check(ctl)
                try:  # the answer is already delivered: a reflection error never fails the run
                    events = await self._reflect(run_id, req, ctl, emit, lineup, clerk, project, profile)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    events = None
            try:
                router_stats.update_from_run(events or d.store.events_for_run(run_id), lineup, profile,
                                             decision, None, table, d.store)
            except Exception:
                pass
            await self._train_steering(run_id, emit)
            return await self._done(ctl, emit, result,
                                    "answer delivered" if not plan_like else "stopped by the user")

        # 10: plan
        if workspace is None:
            workspace = runs_dir(d.home, run_id) / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        foreman = Foreman(d.gateway, emit, d.config.foreman, workspace)
        await self._to(ctl, RunState.PLANNING, "the Foreman writes the plan")
        plan = await self._plan(run_id, foreman, req.task, decision.final_text, brief, lineup)

        # 11: delegate
        await self._to(ctl, RunState.AWAITING_DELEGATION, "plan ready")
        if not (opts.get("auto_delegate") or d.config.foreman.auto_delegate):
            version = d.store.plan_version(run_id)
            await ctl.wait_delegate()
            if d.store.plan_version(run_id) != version:  # the user edited the plan meanwhile
                edited = Plan.model_validate(d.store.get_json("plans", run_id))
                plan, issues = foreman.apply_user_edit(plan, edited)
                if issues:
                    raise PlanError(f"the edited plan has {len(issues)} lint error(s)", issues)
                emit(ET.PLAN_READY, ET.make_payload(
                    ET.PLAN_READY, plan=plan, version=d.store.plan_version(run_id),
                    task_count=len(plan.tasks), edited_by_user=True))

        # 11, 12: execute
        worker = self._role("worker", run_id) or clerk or lineup.seats[0].model_id
        senior = self._role("senior_worker", run_id)
        council_models = [s.model_id for s in lineup.seats] + [lineup.chair_model_id, clerk]
        work_models = [worker, senior, clerk]
        await self._seat(run_id, work_models)  # the seats go idle while the workers build
        works = WorksPipeline(d.gateway, emit, d.config, runs_dir(d.home, run_id), worker, senior, clerk)
        await self._to(ctl, RunState.EXECUTING, "delegated")
        report = await works.execute(run_id, plan, workspace)

        # 13: review
        max_cycles = max(0, int(d.config.review.max_cycles))
        review_deadline = float(getattr(d.config.review, "deadline_s", 0) or 0)
        final_say = str(getattr(d.config.review, "final_say", "user"))
        attended = not (opts.get("auto_input") or opts.get("auto_delegate") or d.config.foreman.auto_delegate)
        review_t0 = time.monotonic()
        history: list[dict] = []
        cycle, fix_cycles, replanned, clean_fix = 0, 0, False, False
        accepted: Optional[bool] = None
        while accepted is None:
            cycle += 1
            voters = await self._seat_review(run_id, lineup, council_models, project, emit)
            await self._to(ctl, RunState.REVIEWING, f"review cycle {cycle}")
            if not voters.seats:
                # No seat came back: nobody can vote. Finished work whose checks pass is kept.
                accepted = self._checks_pass(report)
                emit(ET.REVIEW_VERDICT, dict(
                    verdict="accept" if accepted else "ask_user", tally={}, fixes=[], cycle=cycle,
                    reason="no review seat could be loaded: decided on the checks",
                    next_state=RunState.INTEGRATING if accepted else RunState.REFLECTING))
                break
            verdict, counts, fixes, ballots = await self._review_vote(
                run_id, voters, plan, report, cycle, max_cycles, emit)
            history.append(review_mod.ballot_record(ballots, cycle, counts))
            if verdict == "fix" and not fixes:
                verdict = "accept"
            over = review_deadline > 0 and time.monotonic() - review_t0 > review_deadline
            # A "fix" on work whose current checks all pass is honoured once, not twice.
            pointless = verdict == "fix" and self._checks_pass(report)
            again = pointless and clean_fix
            can_fix = verdict == "fix" and fix_cycles < max_cycles and not over and not again
            can_replan = verdict == "replan" and not replanned and not over
            ends = verdict != "accept" and not can_fix and not can_replan
            ask = ends and (final_say != "random_seat" or (verdict == "ask_user" and attended))
            why = ("" if not ends else
                   "the review time limit is over" if over else
                   "a second fix was asked although every current check passes" if again else
                   "the fix cycles are used up" if verdict == "fix" else
                   "the council already replanned once" if verdict == "replan" else
                   "the council could not reach a verdict")
            nxt = (RunState.INTEGRATING if verdict == "accept" else
                   RunState.EXECUTING if can_fix else
                   RunState.DELIBERATING if can_replan else
                   RunState.AWAITING_USER if ask else RunState.REVIEWING)
            emit(ET.REVIEW_VERDICT, dict(verdict=verdict, tally=counts, fixes=fixes, cycle=cycle,
                                         reason=why, next_state=nxt))
            if verdict == "accept":
                accepted = True
            elif can_fix:
                fix_cycles += 1
                clean_fix = clean_fix or pointless
                tasks = review_mod.fixes_to_tasks(fixes, plan, fix_cycles,
                                                  test_cmd=canonical_test_cmd(plan))
                if not await self._seat_ok(run_id, work_models):
                    # The workers will not load, so no fix can be made: one seat decides on the
                    # work as it is, instead of the run failing with the work unintegrated.
                    voters = await self._seat_review(run_id, lineup, council_models, project, emit)
                    accepted = (await self._final_say(run_id, voters, plan, report, cycle, seed,
                                                      history, emit)
                                if voters.seats else self._checks_pass(report))
                    continue
                await self._to(ctl, RunState.EXECUTING, f"fix cycle {fix_cycles}")
                report = await works.execute_fixes(run_id, plan, tasks, workspace)
            elif can_replan:
                replanned = True
                await self._to(ctl, RunState.DELIBERATING, "the council replans")
                again_d = self._new_deliberation(
                    run_id, req.task, profile, lineup, mode.model_copy(update={"rounds": ["r0"]}), record,
                    (brief + "\n\nWORK REPORT OF THE FIRST PLAN (evidence):\n" + report_text(report)).strip(),
                    clerk, opts, seed + 1, project)
                redo = await LiveExecutor(d.gateway, d.bus, evidence_runner=EvidenceRunner(workspace).run
                                          ).run(again_d, run_id, float(mode.deadline_s))
                if redo.final_text:
                    decision = redo.model_copy(update={"needs_user": None})
                    d.store.put_json("decisions", run_id, decision)
                await self._to(ctl, RunState.PLANNING, "the Foreman writes a new plan")
                plan = await self._plan(run_id, foreman, req.task, decision.final_text, brief, lineup)
                await self._seat(run_id, work_models)
                await self._to(ctl, RunState.EXECUTING, "delegated again")
                report = await works.execute(run_id, plan, workspace)
                clean_fix = False  # a new plan: the first fix on it is honoured again
            elif ask:
                answer = await self._ask(ctl, UserQuestion(
                    question="The council could not accept the work. Accept it as it is, or discard it?",
                    options=["accept", "discard"], context=report_text(report, 1500)))
                accepted = (answer.choice or answer.text or "").strip().lower() == "accept"
            else:
                accepted = await self._final_say(run_id, voters, plan, report, cycle, seed, history, emit)

        # 14: integrate
        files: list[str] = []
        if accepted:
            await self._to(ctl, RunState.INTEGRATING, "work accepted")
            files = await works.integrate(run_id, workspace)

        # 15: reflect. The work is already decided (and written): an error here never fails the run.
        events = None
        self._check(ctl)
        try:
            events = await self._reflect(run_id, req, ctl, emit, lineup, clerk, project, profile)
        except asyncio.CancelledError:
            raise
        except Exception:
            events = None
        try:
            router_stats.update_from_run(events or d.store.events_for_run(run_id), lineup, profile,
                                         decision, accepted, table, d.store)
        except Exception:
            pass
        await self._train_steering(run_id, emit)

        s = report.summary
        note = (f"Work integrated: {len(files)} file(s) written." if accepted
                else "The work was discarded; nothing was written to the workspace.")
        result = RunResult(
            decision=decision, tribunal=outcome, correction=correction, plan=plan, report=report,
            accepted=accepted, files_written=files,
            final_text=f"{decision.final_text}\n\n[{note} Tasks passed {s.passed}, failed {s.failed}, "
                       f"blocked {s.blocked}, skipped {s.skipped}.]".strip())
        return await self._done(ctl, emit, result, "work accepted" if accepted else "work discarded")

    @staticmethod
    def _lesson_events(events: list) -> list:
        """Tribunal outcomes and corrections as lessons, in the one shape collect_candidates
        reads a lesson from (ballot.cast). In memory only: nothing here is emitted or stored."""
        out: list[Event] = []
        for e in events:
            p = e.payload or {}
            lesson: Any = ""
            if e.type == ET.TRIBUNAL_OUTCOME:
                o = p.get("outcome") or {}
                if isinstance(o, dict) and o.get("outcome") in _LESSON_OUTCOMES:
                    lesson = o.get("lesson")
            elif e.type == ET.CORRECTION_RECORDED:
                c = p.get("correction") or {}
                lesson = c.get("lesson") if isinstance(c, dict) else ""
            if isinstance(lesson, str) and lesson.strip():
                out.append(Event(type=ET.BALLOT_CAST, seq=e.seq, ts=e.ts, run_id=e.run_id,
                                 payload={"ballot": {"lesson": lesson.strip()}}))
        return out

    async def _reflect(self, run_id: str, req: RunRequest, ctl: RunControl, emit: Callable,
                       lineup: LineupRecord, clerk: Optional[str], project: str,
                       profile: TaskProfile) -> list:
        """Step 15, for build and answer runs alike. Returns the events of the run it read."""
        d = self.d
        await self._to(ctl, RunState.REFLECTING, "the council reflects")
        events = d.store.events_for_run(run_id)
        if d.reflector_factory is not None:
            reflector = d.reflector_factory(emit)
        elif d.reflector is not None:
            reflector = copy.copy(d.reflector)
            reflector.emit = emit
        else:
            reflector = Reflector(d.gateway, d.store, emit, d.gateway.embed, d.config.chronicle, d.now)
        judges = pick_judges(d.registry, lineup, int(d.config.chronicle.panel_size))
        await self._seat(run_id, list(judges) + [clerk])
        candidates = collect_candidates(list(events) + self._lesson_events(events), req.task)
        await reflector.reflect(run_id, candidates, judges,
                                "" if project == NO_PROJECT else project, list(profile.categories))
        return events

    async def _done(self, ctl: RunControl, emit: Callable, result: RunResult, reason: str) -> RunResult:
        await self._to(ctl, RunState.DONE, reason)
        if self.emit_completed:
            emit(ET.RUN_COMPLETED, dict(
                state=RunState.DONE, outcome=result.decision.outcome, final_text=result.final_text,
                decision=result.decision, files_written=result.files_written, finished_at=self.d.now()))
        return result


__all__ = ["RunPipeline", "RunDeps", "RunControl", "RunResult", "FailedModelEntry", "NO_PROJECT",
           "evidence_supports", "apply_steering", "MIN_SEATS", "MEMORY_NS"]
