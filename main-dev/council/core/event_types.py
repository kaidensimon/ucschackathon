"""Event contract (spec 16.3). One string constant and one payload model per event type.

FROZEN after the first fan-out, like schemas.py. Do not edit without telling every consumer.

Conventions
- Constant name: the type upper-cased with "." -> "_"   (RUN_CREATED = "run.created").
- Payload name:  the type in CamelCase + "Payload"      (RunCreatedPayload).
- Every payload ignores unknown keys. Every field has a default, except the ids that name
  the subject of the event: `call_id` on turn.*, `task_id` on task.*, `model_id` on model.*.
- A payload carries everything a UI needs to draw that moment without another request.
  `run_id`, `seq` and `ts` live on the envelope (schemas.Event), not in the payload.
- Two payloads are flat schemas.py types, as schemas.py documents them:
  telemetry.tick IS a TelemetrySnapshot, user.input_requested IS a UserQuestion.
- No logic lives here beyond validate_payload / make_payload.
- Added 2026-10-10, appended after telemetry.tick: tribunal.* and correction.recorded,
  probe.* (28), bench.* (18).
- Added 2026-10-11, appended after bench.completed: effort.planned, round.extended,
  review.debate, review.final_say.
- Added 2026-10-11 (1.5), appended after review.final_say: lie.report, steer.applied,
  steer.trained, memory.planned. Their `report` / `plan` are dumps of schemas_v15 types.
- Added 2026-10-11 (open council protocol), appended after memory.planned: msg.started,
  msg.delta, msg.thinking, msg.ended, msg.card, msg.lie, table.tally. Emitted by
  chamber/open_debate.py; the payloads are exactly the dicts it emits.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from council.core.schemas import (
    BenchResult,
    BenchRunRequest,
    BenchSummaryRow,
    ClaimScore,
    Correction,
    DefenseVerdict,
    Probe,
    TribunalAnswer,
    TribunalOutcome,
    TribunalQuestion,
    AttemptRecord,
    Ballot,
    Check,
    CheckKind,
    CheckResult,
    ChronicleEntry,
    Crux,
    Decision,
    Deliverable_,
    Difficulty,
    DiffStats,
    EvidenceResult,
    InspectLevel,
    LensName,
    LineupRecord,
    LineupScore,
    MemoryCandidate,
    MemoryVerdict,
    Mode,
    Option,
    Outcome,
    Plan,
    ReasoningLevel,
    RejectedLineup,
    ReviewBallot,
    ReviewFix,
    ReviewVerdict,
    RouterTier,
    RunCounters,
    RunState,
    TaskKind,
    TaskProfile,
    TaskStatus,
    TaskTier,
    TelemetrySnapshot,
    UserQuestion,
    WorkReport,
)

# --------------------------------------------------------------------------------------
# Type strings, in the order of 16.3
# --------------------------------------------------------------------------------------

# Run
RUN_CREATED = "run.created"
RUN_STATE_CHANGED = "run.state_changed"
RUN_COMPLETED = "run.completed"
RUN_FAILED = "run.failed"
RUN_CANCELLED = "run.cancelled"
# Setup
BRIEF_READY = "brief.ready"
RECALL_READY = "recall.ready"
PROFILE_READY = "profile.ready"
# Router
ROUTER_CANDIDATES_SCORED = "router.candidates_scored"
ROUTER_LINEUP_SELECTED = "router.lineup_selected"
# Models
MODEL_LOADING = "model.loading"
MODEL_LOADED = "model.loaded"
MODEL_UNLOADED = "model.unloaded"
MODEL_EVICTED = "model.evicted"
MODEL_FAILED = "model.failed"
# Deliberation
SEAT_ASSIGNED = "seat.assigned"
ROUND_STARTED = "round.started"
TURN_STARTED = "turn.started"
TURN_DELTA = "turn.delta"
TURN_REASONING_DELTA = "turn.reasoning_delta"
TURN_COMPLETED = "turn.completed"
TURN_INVALID = "turn.invalid"
TURN_TIMEOUT = "turn.timeout"
OPTIONS_CLUSTERED = "options.clustered"
CRUXES_EXTRACTED = "cruxes.extracted"
EVIDENCE_REQUESTED = "evidence.requested"
EVIDENCE_RESULT = "evidence.result"
BALLOT_CAST = "ballot.cast"
ROUND_COMPLETED = "round.completed"
# Decision
CONSENSUS_REACHED = "consensus.reached"
CONSENSUS_FAILED = "consensus.failed"
CHAIR_STARTED = "chair.started"
CHAIR_DELTA = "chair.delta"
RATIFY_RESULT = "ratify.result"
DECISION_FINAL = "decision.final"
# User
USER_INPUT_REQUESTED = "user.input_requested"
USER_INPUT_RECEIVED = "user.input_received"
# Plan
PLAN_DRAFTED = "plan.drafted"
PLAN_LINTED = "plan.linted"
PLAN_REVIEWED = "plan.reviewed"
PLAN_READY = "plan.ready"
# Work
DELEGATION_STARTED = "delegation.started"
TASK_QUEUED = "task.queued"
TASK_STARTED = "task.started"
TASK_DELTA = "task.delta"
TASK_ATTEMPT_COMPLETED = "task.attempt_completed"
CHECK_STARTED = "check.started"
CHECK_RESULT = "check.result"
TASK_PASSED = "task.passed"
TASK_FAILED = "task.failed"
TASK_BLOCKED = "task.blocked"
TASK_SKIPPED = "task.skipped"
TASK_ESCALATED = "task.escalated"
INTEGRATION_RESULT = "integration.result"
# Review
REVIEW_STARTED = "review.started"
REVIEW_BALLOT = "review.ballot"
REVIEW_VERDICT = "review.verdict"
# Chronicle
MEMORY_CANDIDATE = "memory.candidate"
MEMORY_VERDICT = "memory.verdict"
MEMORY_COMMITTED = "memory.committed"
MEMORY_CONTESTED = "memory.contested"
MEMORY_RETRACTED = "memory.retracted"
# Telemetry
TELEMETRY_TICK = "telemetry.tick"
# Tribunal (27)
TRIBUNAL_STARTED = "tribunal.started"
TRIBUNAL_QUESTION = "tribunal.question"
TRIBUNAL_ANSWER = "tribunal.answer"
TRIBUNAL_VERDICT = "tribunal.verdict"
TRIBUNAL_OUTCOME = "tribunal.outcome"
# Corrections (27.6)
CORRECTION_RECORDED = "correction.recorded"
# Probe (28)
PROBE_SCORES = "probe.scores"
PROBE_TRAINED = "probe.trained"
# Bench (18)
BENCH_STARTED = "bench.started"
BENCH_PROGRESS = "bench.progress"
BENCH_COMPLETED = "bench.completed"
# Adaptive effort and review debate (added 2026-10-11)
EFFORT_PLANNED = "effort.planned"
ROUND_EXTENDED = "round.extended"
REVIEW_DEBATE = "review.debate"
REVIEW_FINAL_SAY = "review.final_say"
# 1.5: lie detector, steering vectors, memory plan (added 2026-10-11)
LIE_REPORT = "lie.report"
STEER_APPLIED = "steer.applied"
STEER_TRAINED = "steer.trained"
MEMORY_PLANNED = "memory.planned"
# Open council protocol: one free-text message + card per turn (added 2026-10-11)
MSG_STARTED = "msg.started"
MSG_DELTA = "msg.delta"
MSG_THINKING = "msg.thinking"
MSG_ENDED = "msg.ended"
MSG_CARD = "msg.card"
MSG_LIE = "msg.lie"
TABLE_TALLY = "table.tally"

EVENT_TYPES: tuple[str, ...] = (
    RUN_CREATED, RUN_STATE_CHANGED, RUN_COMPLETED, RUN_FAILED, RUN_CANCELLED,
    BRIEF_READY, RECALL_READY, PROFILE_READY,
    ROUTER_CANDIDATES_SCORED, ROUTER_LINEUP_SELECTED,
    MODEL_LOADING, MODEL_LOADED, MODEL_UNLOADED, MODEL_EVICTED, MODEL_FAILED,
    SEAT_ASSIGNED, ROUND_STARTED, TURN_STARTED, TURN_DELTA, TURN_REASONING_DELTA,
    TURN_COMPLETED, TURN_INVALID, TURN_TIMEOUT, OPTIONS_CLUSTERED, CRUXES_EXTRACTED,
    EVIDENCE_REQUESTED, EVIDENCE_RESULT, BALLOT_CAST, ROUND_COMPLETED,
    CONSENSUS_REACHED, CONSENSUS_FAILED, CHAIR_STARTED, CHAIR_DELTA, RATIFY_RESULT,
    DECISION_FINAL,
    USER_INPUT_REQUESTED, USER_INPUT_RECEIVED,
    PLAN_DRAFTED, PLAN_LINTED, PLAN_REVIEWED, PLAN_READY,
    DELEGATION_STARTED, TASK_QUEUED, TASK_STARTED, TASK_DELTA, TASK_ATTEMPT_COMPLETED,
    CHECK_STARTED, CHECK_RESULT, TASK_PASSED, TASK_FAILED, TASK_BLOCKED, TASK_SKIPPED,
    TASK_ESCALATED, INTEGRATION_RESULT,
    REVIEW_STARTED, REVIEW_BALLOT, REVIEW_VERDICT,
    MEMORY_CANDIDATE, MEMORY_VERDICT, MEMORY_COMMITTED, MEMORY_CONTESTED, MEMORY_RETRACTED,
    TELEMETRY_TICK,
    TRIBUNAL_STARTED, TRIBUNAL_QUESTION, TRIBUNAL_ANSWER, TRIBUNAL_VERDICT, TRIBUNAL_OUTCOME,
    CORRECTION_RECORDED,
    PROBE_SCORES, PROBE_TRAINED,
    BENCH_STARTED, BENCH_PROGRESS, BENCH_COMPLETED,
    EFFORT_PLANNED, ROUND_EXTENDED, REVIEW_DEBATE, REVIEW_FINAL_SAY,
    LIE_REPORT, STEER_APPLIED, STEER_TRAINED, MEMORY_PLANNED,
    MSG_STARTED, MSG_DELTA, MSG_THINKING, MSG_ENDED, MSG_CARD, MSG_LIE, TABLE_TALLY,
)

TERMINAL_EVENTS: tuple[str, ...] = (RUN_COMPLETED, RUN_FAILED, RUN_CANCELLED)

# Streamed token events: delivered live, never stored (16.3). Includes turn.reasoning_delta.
EPHEMERAL_EVENTS: tuple[str, ...] = tuple(
    t for t in EVENT_TYPES if t.endswith(".delta") or t.endswith("_delta")
)

# --------------------------------------------------------------------------------------
# Shared payload parts
# --------------------------------------------------------------------------------------


class _Payload(BaseModel):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())


class ModelInfo(_Payload):
    """What a UI needs to draw one model chip."""

    model_id: str
    display: str = ""
    lab: str = ""
    lineage: str = ""
    params_b: Optional[float] = None
    quant: str = ""
    footprint_gib: float = 0.0
    resident: bool = False


class ScoredCandidate(_Payload):
    """One model as the Router scored it for this task (9.2 - 9.4)."""

    model_id: str
    display: str = ""
    lab: str = ""
    q: float = 0.0  # competence estimate, 0..1
    eligible: bool = True
    reason: str = ""  # why it was excluded, when eligible is False


# --------------------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------------------


class RunCreatedPayload(_Payload):
    task: str = ""
    workspace: Optional[str] = None
    mode: Mode = "standard"
    deliverable: Optional[Deliverable_] = None
    lineup_override: Optional[list[str]] = None
    options: dict[str, Any] = Field(default_factory=dict)
    state: RunState = RunState.INTAKE
    created_at: Optional[float] = None


class RunStateChangedPayload(_Payload):
    from_state: Optional[RunState] = None  # None on the first transition
    to_state: RunState = RunState.INTAKE
    reason: str = ""
    round: int = 0
    review_cycle: int = 0
    phase_ms: Optional[float] = None  # wall-clock spent in from_state


class RunCompletedPayload(_Payload):
    state: RunState = RunState.DONE
    outcome: Optional[Outcome] = None
    final_text: str = ""
    decision: Optional[Decision] = None
    counters: RunCounters = Field(default_factory=RunCounters)
    files_written: list[str] = Field(default_factory=list)
    finished_at: Optional[float] = None


class RunFailedPayload(_Payload):
    state: RunState = RunState.FAILED
    from_state: Optional[RunState] = None
    error: str = ""
    detail: str = ""
    counters: RunCounters = Field(default_factory=RunCounters)
    finished_at: Optional[float] = None


class RunCancelledPayload(_Payload):
    state: RunState = RunState.CANCELLED
    from_state: Optional[RunState] = None
    reason: str = ""
    counters: RunCounters = Field(default_factory=RunCounters)
    finished_at: Optional[float] = None


# --------------------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------------------


class BriefReadyPayload(_Payload):
    workspace: Optional[str] = None
    summary: str = ""
    file_count: int = 0
    languages: list[str] = Field(default_factory=list)
    key_files: list[str] = Field(default_factory=list)
    tree: str = ""
    cached: bool = False
    ms: float = 0.0


class RecallReadyPayload(_Payload):
    entries: list[ChronicleEntry] = Field(default_factory=list)
    count: int = 0
    record_block: str = ""  # the "council record" text every seat receives
    ms: float = 0.0


class ProfileReadyPayload(_Payload):
    profile: Optional[TaskProfile] = None
    model_id: Optional[str] = None
    ms: float = 0.0


# --------------------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------------------


class RouterCandidatesScoredPayload(_Payload):
    candidates: list[ScoredCandidate] = Field(default_factory=list)
    lineups_considered: int = 0
    top: list[RejectedLineup] = Field(default_factory=list)  # best lineups, best first
    tier: RouterTier = "A"
    k: int = 0


class RouterLineupSelectedPayload(_Payload):
    lineup: Optional[LineupRecord] = None
    models: list[ModelInfo] = Field(default_factory=list)  # one per seat, plus the chair
    chair_model_id: Optional[str] = None
    wildcard_seat_no: Optional[int] = None
    score: LineupScore = Field(default_factory=LineupScore)
    mode: Mode = "standard"
    k: int = 0
    labs: int = 0  # distinct labs in the lineup
    overridden: bool = False  # lineup_override was used


# --------------------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------------------


class _ModelEvent(_Payload):
    model_id: str
    display: str = ""
    lab: str = ""
    footprint_gib: float = 0.0
    serve_profile: Optional[str] = None  # "live" | "batch"
    mem_available_gib: Optional[float] = None


class ModelLoadingPayload(_ModelEvent):
    reason: str = ""
    expected_load_s: Optional[float] = None


class ModelLoadedPayload(_ModelEvent):
    load_ms: float = 0.0
    ctx: Optional[int] = None
    parallel: Optional[int] = None
    endpoint: Optional[str] = None


class ModelUnloadedPayload(_ModelEvent):
    reason: str = ""
    freed_gib: float = 0.0


class ModelEvictedPayload(_ModelEvent):
    reason: str = ""
    freed_gib: float = 0.0
    for_model_id: Optional[str] = None  # the model that needed the room


class ModelFailedPayload(_ModelEvent):
    error: str = ""
    stage: str = ""  # "load" | "health" | "serve"
    replaced_by: Optional[str] = None  # alternate model id, if one took the seat


# --------------------------------------------------------------------------------------
# Deliberation
# --------------------------------------------------------------------------------------


class SeatAssignedPayload(_Payload):
    seat_no: int = 0
    model_id: str = ""
    display: str = ""
    lab: str = ""
    lens: Optional[LensName] = None
    is_wildcard: bool = False
    is_chair: bool = False
    q: float = 0.0
    label: Optional[str] = None  # anonymous label other seats see: "A", "B", ...
    replaces_model_id: Optional[str] = None  # set when an alternate took the seat


class RoundStartedPayload(_Payload):
    round: int = 0
    purpose: str = ""
    seats: list[int] = Field(default_factory=list)
    deadline_s: Optional[float] = None
    focus_crux_ids: list[str] = Field(default_factory=list)
    is_review: bool = False


class TurnStartedPayload(_Payload):
    call_id: str
    purpose: str = ""
    model_id: str = ""
    seat_no: Optional[int] = None  # None for clerk, foreman and other non-seat calls
    round: int = 0
    reasoning: ReasoningLevel = "off"
    max_output_tokens: Optional[int] = None
    attempt: int = 1


class TurnDeltaPayload(_Payload):
    call_id: str
    seat_no: Optional[int] = None
    text: str = ""


class TurnReasoningDeltaPayload(_Payload):
    call_id: str
    seat_no: Optional[int] = None
    text: str = ""


class TurnCompletedPayload(_Payload):
    call_id: str
    seat_no: Optional[int] = None
    round: int = 0
    purpose: str = ""
    model_id: str = ""
    tokens: int = 0  # tokens_out, the headline number
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_reasoning: int = 0
    tps: float = 0.0
    ms: float = 0.0
    parsed: Optional[dict[str, Any]] = None  # the Draft / Critique / Ballot / ... as a dict
    content: str = ""
    finish_reason: Optional[str] = None
    attempts: int = 1
    cached: bool = False


class TurnInvalidPayload(_Payload):
    call_id: str
    seat_no: Optional[int] = None
    round: int = 0
    purpose: str = ""
    model_id: str = ""
    error: str = ""
    attempts: int = 1
    will_retry: bool = False
    content_tail: str = ""


class TurnTimeoutPayload(_Payload):
    call_id: str
    seat_no: Optional[int] = None
    round: int = 0
    purpose: str = ""
    model_id: str = ""
    timeout_s: float = 0.0
    ms: float = 0.0
    will_retry: bool = False


class OptionsClusteredPayload(_Payload):
    round: int = 0
    options: list[Option] = Field(default_factory=list)
    tally: dict[str, int] = Field(default_factory=dict)  # option id -> holders
    agreement: float = 0.0  # share held by the largest option
    leading_option_id: Optional[str] = None


class CruxesExtractedPayload(_Payload):
    round: int = 0
    cruxes: list[Crux] = Field(default_factory=list)


class EvidenceRequestedPayload(_Payload):
    round: int = 0
    check_id: str = ""
    kind: Optional[CheckKind] = None
    spec: str = ""
    settles: Optional[str] = None
    crux_id: Optional[str] = None
    requested_by: list[int] = Field(default_factory=list)  # seat_no values; empty = engine


class EvidenceResultPayload(_Payload):
    round: int = 0
    check_id: str = ""
    result: Optional[EvidenceResult] = None
    crux_id: Optional[str] = None
    crux_resolved: bool = False


class BallotCastPayload(_Payload):
    seat_no: int = 0
    round: int = 0
    ballot: Optional[Ballot] = None
    model_id: str = ""
    call_id: Optional[str] = None
    changed: bool = False  # the seat moved since its last position


class RoundCompletedPayload(_Payload):
    round: int = 0
    options: list[Option] = Field(default_factory=list)
    tally: dict[str, int] = Field(default_factory=dict)
    agreement: float = 0.0
    leading_option_id: Optional[str] = None
    valid_turns: int = 0
    failed_seats: list[int] = Field(default_factory=list)
    converged: bool = False
    ms: float = 0.0


# --------------------------------------------------------------------------------------
# Decision
# --------------------------------------------------------------------------------------


class ConsensusReachedPayload(_Payload):
    round: int = 0
    option_id: Optional[str] = None
    agreement: float = 0.0
    threshold: float = 0.8
    tally: dict[str, int] = Field(default_factory=dict)
    outcome: Outcome = "consensus"
    early: bool = False  # reached at round 0, debate skipped


class ConsensusFailedPayload(_Payload):
    round: int = 0
    agreement: float = 0.0
    threshold: float = 0.8
    tally: dict[str, int] = Field(default_factory=dict)
    leading_option_id: Optional[str] = None
    open_cruxes: list[Crux] = Field(default_factory=list)
    reason: str = ""
    next_step: str = ""  # "round" | "majority" | "chair" | "user" | "deadlock"


class ChairStartedPayload(_Payload):
    call_id: Optional[str] = None
    model_id: str = ""
    seat_no: Optional[int] = None
    reason: str = ""


class ChairDeltaPayload(_Payload):
    call_id: Optional[str] = None
    seat_no: Optional[int] = None
    text: str = ""


class RatifyResultPayload(_Payload):
    ratified: bool = False
    votes_for: int = 0
    votes_against: int = 0
    votes: dict[str, bool] = Field(default_factory=dict)  # seat_no (as text) -> approve
    objections: list[str] = Field(default_factory=list)
    option_id: Optional[str] = None


class DecisionFinalPayload(_Payload):
    decision: Optional[Decision] = None
    options: list[Option] = Field(default_factory=list)
    ms: float = 0.0  # wall-clock of the whole deliberation


# --------------------------------------------------------------------------------------
# User
# --------------------------------------------------------------------------------------


class UserInputRequestedPayload(UserQuestion):
    """Flat UserQuestion (question, options, request_id, crux_id, context) plus the paused state."""

    question: str = ""
    from_state: Optional[RunState] = None
    source: str = ""  # "decision" | "review" | "plan"


class UserInputReceivedPayload(_Payload):
    request_id: Optional[str] = None
    choice: Optional[str] = None
    text: Optional[str] = None
    resume_state: Optional[RunState] = None


# --------------------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------------------


class PlanDraftedPayload(_Payload):
    plan: Optional[Plan] = None
    version: int = 1
    task_count: int = 0
    model_id: Optional[str] = None
    call_id: Optional[str] = None


class PlanLintedPayload(_Payload):
    ok: bool = False
    version: int = 1
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    task_count: int = 0
    will_retry: bool = False


class PlanReviewedPayload(_Payload):
    ok: bool = False
    version: int = 1
    reviewer_seat_no: Optional[int] = None
    reviewer_model_id: Optional[str] = None
    issues: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)


class PlanReadyPayload(_Payload):
    plan: Optional[Plan] = None
    version: int = 1
    task_count: int = 0
    micro_count: int = 0
    senior_count: int = 0
    edited_by_user: bool = False


# --------------------------------------------------------------------------------------
# Work
# --------------------------------------------------------------------------------------


class DelegationStartedPayload(_Payload):
    task_count: int = 0
    task_ids: list[str] = Field(default_factory=list)
    workers: list[ModelInfo] = Field(default_factory=list)
    max_parallel: int = 0
    cycle: int = 0  # 0 = first pass, n = nth fix cycle
    plan_version: int = 1


class _TaskEvent(_Payload):
    task_id: str
    title: str = ""
    attempt: int = 0  # 1-based; 0 = no attempt yet
    model_id: Optional[str] = None
    tier: TaskTier = "micro"


class TaskQueuedPayload(_TaskEvent):
    status: TaskStatus = TaskStatus.queued
    kind: Optional[TaskKind] = None
    deps: list[str] = Field(default_factory=list)
    write_set: list[str] = Field(default_factory=list)
    cycle: int = 0


class TaskStartedPayload(_TaskEvent):
    status: TaskStatus = TaskStatus.running
    call_id: Optional[str] = None
    max_attempts: int = 0
    temperature: Optional[float] = None


class TaskDeltaPayload(_Payload):
    task_id: str
    attempt: int = 0
    call_id: Optional[str] = None
    text: str = ""


class TaskAttemptCompletedPayload(_TaskEvent):
    status: TaskStatus = TaskStatus.running
    ok: bool = False
    record: Optional[AttemptRecord] = None
    blocked: Optional[str] = None
    failing_check: Optional[str] = None
    error_tail: str = ""
    files_changed: list[str] = Field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    tps: float = 0.0
    ms: float = 0.0
    will_retry: bool = False


class CheckStartedPayload(_Payload):
    task_id: Optional[str] = None  # None for global acceptance / integration
    attempt: Optional[int] = None
    check_id: Optional[str] = None
    check: Optional[Check] = None
    level: Optional[InspectLevel] = None


class CheckResultPayload(_Payload):
    result: Optional[CheckResult] = None
    task_id: Optional[str] = None
    attempt: Optional[int] = None
    check_id: Optional[str] = None
    level: Optional[InspectLevel] = None
    ok: bool = False


class _TaskEnded(_TaskEvent):
    attempts: int = 0
    checks: list[CheckResult] = Field(default_factory=list)
    failing_check: Optional[str] = None
    error_tail: str = ""
    reason: str = ""
    files_changed: list[str] = Field(default_factory=list)
    ms: float = 0.0


class TaskPassedPayload(_TaskEnded):
    status: TaskStatus = TaskStatus.passed


class TaskFailedPayload(_TaskEnded):
    status: TaskStatus = TaskStatus.failed


class TaskBlockedPayload(_TaskEnded):
    status: TaskStatus = TaskStatus.blocked


class TaskSkippedPayload(_TaskEnded):
    status: TaskStatus = TaskStatus.skipped
    blocked_by: list[str] = Field(default_factory=list)  # failed dependency task ids


class TaskEscalatedPayload(_TaskEvent):
    status: TaskStatus = TaskStatus.queued
    to: str = "senior"  # "senior" | "council"
    from_tier: TaskTier = "micro"
    to_tier: Optional[TaskTier] = "senior"
    from_model_id: Optional[str] = None
    to_model_id: Optional[str] = None
    failing_check: Optional[str] = None
    reason: str = ""


class IntegrationResultPayload(_Payload):
    ok: bool = False
    stage: str = ""  # "checks" (L3 on the staged copy) | "copy" (into the real workspace)
    checks: list[CheckResult] = Field(default_factory=list)
    files_written: list[str] = Field(default_factory=list)
    diff_stats: DiffStats = Field(default_factory=DiffStats)
    error: Optional[str] = None


# --------------------------------------------------------------------------------------
# Review
# --------------------------------------------------------------------------------------


class ReviewStartedPayload(_Payload):
    cycle: int = 0
    report: Optional[WorkReport] = None
    seats: list[int] = Field(default_factory=list)
    max_cycles: int = 0


class ReviewBallotPayload(_Payload):
    seat_no: int = 0
    model_id: str = ""
    cycle: int = 0
    ballot: Optional[ReviewBallot] = None
    call_id: Optional[str] = None


class ReviewVerdictPayload(_Payload):
    verdict: Optional[ReviewVerdict] = None
    tally: dict[str, int] = Field(default_factory=dict)  # verdict -> votes
    fixes: list[ReviewFix] = Field(default_factory=list)
    cycle: int = 0
    reason: str = ""
    next_state: Optional[RunState] = None


# --------------------------------------------------------------------------------------
# Chronicle
# --------------------------------------------------------------------------------------


class MemoryCandidatePayload(_Payload):
    candidate: Optional[MemoryCandidate] = None
    index: int = 0
    total: int = 0


class MemoryVerdictPayload(_Payload):
    candidate_id: str = ""
    seat_no: Optional[int] = None
    model_id: str = ""
    verdict: Optional[MemoryVerdict] = None


class MemoryCommittedPayload(_Payload):
    entry: Optional[ChronicleEntry] = None
    candidate_id: str = ""
    action: str = ""  # MemoryAction: adopt | provisional | merge:<id> | supersede:<id>
    superseded_id: Optional[str] = None
    merged_into_id: Optional[str] = None


class MemoryContestedPayload(_Payload):
    entry_id: str = ""
    entry: Optional[ChronicleEntry] = None
    candidate_id: str = ""
    reason: str = ""


class MemoryRetractedPayload(_Payload):
    entry_id: str = ""
    entry: Optional[ChronicleEntry] = None
    reason: str = ""
    by: str = ""  # "panel" | "user" | "aging"


# --------------------------------------------------------------------------------------
# Telemetry
# --------------------------------------------------------------------------------------


class TelemetryTickPayload(TelemetrySnapshot):
    """Flat TelemetrySnapshot, as schemas.py documents it."""


# --------------------------------------------------------------------------------------
# Tribunal (27). The schema object sits in the field named after the last word of the type.
# --------------------------------------------------------------------------------------


class TribunalStartedPayload(_Payload):
    outlier_seat: Optional[int] = None
    outlier_model_id: str = ""
    distance: float = 0.0  # 27.3
    option_id: Optional[str] = None  # the decided option
    outlier_option_id: Optional[str] = None  # what the outlier held
    examiners: list[int] = Field(default_factory=list)  # seat_no values, in asking order
    judges: list[int] = Field(default_factory=list)  # seat_no values
    questions: int = 0  # how many will be asked


class TribunalQuestionPayload(_Payload):
    seat_no: Optional[int] = None  # the examiner
    model_id: str = ""
    index: int = 0  # 0-based question number
    question: Optional[TribunalQuestion] = None
    outlier_seat: Optional[int] = None
    call_id: Optional[str] = None


class TribunalAnswerPayload(_Payload):
    seat_no: Optional[int] = None  # the outlier
    model_id: str = ""
    index: int = 0  # the question it answers
    answer: Optional[TribunalAnswer] = None
    call_id: Optional[str] = None


class TribunalVerdictPayload(_Payload):
    seat_no: Optional[int] = None  # the judge
    model_id: str = ""
    verdict: Optional[DefenseVerdict] = None
    call_id: Optional[str] = None


class TribunalOutcomePayload(_Payload):
    outcome: Optional[TribunalOutcome] = None
    seat_no: Optional[int] = None  # the outlier
    model_id: str = ""
    contested_after_review: bool = False
    correction_eligible: bool = False
    reason: str = ""  # why skipped, or why no correction
    ms: float = 0.0


# --------------------------------------------------------------------------------------
# Corrections (27.6)
# --------------------------------------------------------------------------------------


class CorrectionRecordedPayload(_Payload):
    correction: Optional[Correction] = None
    seat_no: Optional[int] = None
    model_id: str = ""
    project: str = ""
    dataset_size: int = 0  # examples in dataset.jsonl after the append


# --------------------------------------------------------------------------------------
# Probe (28)
# --------------------------------------------------------------------------------------


class ProbeScoresPayload(_Payload):
    seat_no: Optional[int] = None
    model_id: str = ""
    round: int = 0
    scores: list[ClaimScore] = Field(default_factory=list)
    probe_status: Optional[str] = None  # ProbeStatus of the probe used, None if none
    shown_to_council: bool = False


class ProbeTrainedPayload(_Payload):
    probe: Optional[Probe] = None
    model_id: str = ""
    validated: bool = False
    layers_tried: list[int] = Field(default_factory=list)
    auroc_by_layer: dict[str, float] = Field(default_factory=dict)  # layer (as text) -> AUROC
    top_dims: list[int] = Field(default_factory=list)  # top-weighted dimensions of the direction
    ms: float = 0.0


# --------------------------------------------------------------------------------------
# Bench (18)
# --------------------------------------------------------------------------------------


class BenchStartedPayload(_Payload):
    request: Optional[BenchRunRequest] = None
    bench_id: str = ""
    modes: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    tasks: int = 0
    total: int = 0  # task x mode units of work


class BenchProgressPayload(_Payload):
    bench_id: str = ""
    mode: str = ""
    model_id: Optional[str] = None  # the model being run (model-major scheduling)
    done: int = 0
    total: int = 0
    correct: int = 0
    result: Optional[BenchResult] = None  # the result just finished, if any


class BenchCompletedPayload(_Payload):
    bench_id: str = ""
    summary: list[BenchSummaryRow] = Field(default_factory=list)
    results_path: str = ""
    ms: float = 0.0
    error: Optional[str] = None


# --------------------------------------------------------------------------------------
# Adaptive effort and review debate (added 2026-10-11)
# --------------------------------------------------------------------------------------


class EffortPlannedPayload(_Payload):
    """Flat EffortPlan fields plus the difficulty it was planned from."""

    level: Literal["light", "normal", "heavy"] = "normal"
    rounds: list[str] = Field(default_factory=list)
    deadline_s: float = 0.0
    reasoning: ReasoningLevel = "council"
    max_extra_rounds: int = 0
    difficulty: Optional[Difficulty] = None
    rationale: str = ""


class RoundExtendedPayload(_Payload):
    round: int = 0  # the round that was added
    agreement: float = 0.0  # agreement that made the extension worth it
    extra_used: int = 0
    extra_max: int = 0
    reason: str = ""


class ReviewDebatePayload(_Payload):
    cycle: int = 0
    tally_before: dict[str, int] = Field(default_factory=dict)  # verdict -> votes
    tally_after: dict[str, int] = Field(default_factory=dict)


class ReviewFinalSayPayload(_Payload):
    cycle: int = 0
    seat_no: Optional[int] = None  # the randomly picked seat
    model_id: str = ""
    verdict: Optional[ReviewVerdict] = None
    reason: str = ""


# --------------------------------------------------------------------------------------
# 1.5: lie detector, steering vectors, memory plan (added 2026-10-11)
# --------------------------------------------------------------------------------------


class LieReportPayload(_Payload):
    report: dict[str, Any] = Field(default_factory=dict)  # a schemas_v15.LieReport dump
    flagged: int = 0
    watched: int = 0


class SteerAppliedPayload(_Payload):
    project: str = ""
    model_id: str = ""
    scale: float = 0.0
    layers: list[int] = Field(default_factory=list)
    source: str = ""  # where the vector came from, e.g. its file


class SteerTrainedPayload(_Payload):
    project: str = ""
    model_id: str = ""
    examples: int = 0
    scale: Optional[float] = None  # None = no strength passed the sanity check
    active: bool = False
    reason: str = ""


class MemoryPlannedPayload(_Payload):
    plan: dict[str, Any] = Field(default_factory=dict)  # a schemas_v15.MemoryPlan dump


# --------------------------------------------------------------------------------------
# Open council protocol (added 2026-10-11). turn_id = call_id of the message call.
# --------------------------------------------------------------------------------------


class MsgStartedPayload(_Payload):
    turn_id: str
    call_id: str  # gateway call id of the message call: its "turn.delta" events carry it
    seat_no: int = 0
    model_id: str = ""
    name: str = ""
    round: int = 0
    kind: str = "reply"  # "position" | "reply"
    to: Any = "all"  # "all" or a list of seat ids ("s2")


class MsgDeltaPayload(_Payload):
    turn_id: str
    seat_no: Optional[int] = None
    text: str = ""


class MsgThinkingPayload(_Payload):
    turn_id: str
    seat_no: Optional[int] = None


class MsgEndedPayload(_Payload):
    turn_id: str
    seat_no: int = 0
    text: str = ""
    error: Optional[str] = None


class MsgCardPayload(_Payload):
    turn_id: str
    seat_no: int = 0
    card: Optional[dict[str, Any]] = None  # a chamber.messages.Card dump
    fallback: bool = False  # the engine made the card, the card call failed


class MsgLiePayload(_Payload):
    turn_id: str
    seat_no: int = 0
    score: Optional[float] = None  # 0 = likely false .. 1 = likely true
    level: str = "ok"  # "ok" | "watch" | "flag"
    reasons: list[str] = Field(default_factory=list)


class TableTallyPayload(_Payload):
    round: int = 0
    groups: list[dict[str, Any]] = Field(default_factory=list)  # {answer_id, statement, seat_ids}
    leading: str = ""
    agree: int = 0
    seats: int = 0
    needed: int = 0
    reached: bool = False  # true only when the debate ends on this tally
    valid: int = 0
    quorum: int = 0
    unconfirmed: bool = False  # round-0 agreement that still goes to round 1
    basis: str = "round-vote"


# --------------------------------------------------------------------------------------
# Lookup and validation
# --------------------------------------------------------------------------------------


def payload_class_name(type: str) -> str:
    """"run.state_changed" -> "RunStateChangedPayload"."""
    words = type.replace(".", "_").split("_")
    return "".join(w[:1].upper() + w[1:] for w in words) + "Payload"


def constant_name(type: str) -> str:
    """"run.state_changed" -> "RUN_STATE_CHANGED"."""
    return type.replace(".", "_").upper()


PAYLOADS: dict[str, type[BaseModel]] = {t: globals()[payload_class_name(t)] for t in EVENT_TYPES}


def validate_payload(type: str, payload: dict) -> BaseModel:
    """Return the payload model for `type`. ValueError on an unknown type or an invalid payload."""
    cls = PAYLOADS.get(type) if isinstance(type, str) else None
    if cls is None:
        raise ValueError(f"unknown event type: {type!r}")
    if isinstance(payload, cls):
        return payload
    if isinstance(payload, BaseModel):
        payload = payload.model_dump()
    if not isinstance(payload, dict):
        raise ValueError(f"payload of {type} must be a dict, got {payload.__class__.__name__}")
    try:
        return cls.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid payload for {type}: {exc}") from exc


def make_payload(type: str, **fields: Any) -> dict:
    """Validated, JSON-ready payload dict for `type`. Unknown fields are dropped."""
    return validate_payload(type, fields).model_dump(mode="json")


__all__ = (
    [constant_name(t) for t in EVENT_TYPES]
    + [payload_class_name(t) for t in EVENT_TYPES]
    + [
        "EVENT_TYPES", "PAYLOADS", "TERMINAL_EVENTS", "EPHEMERAL_EVENTS",
        "ModelInfo", "ScoredCandidate",
        "validate_payload", "make_payload", "payload_class_name", "constant_name",
    ]
)
