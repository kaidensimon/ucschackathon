"""Council shared contract (pydantic v2). Every cross-module value is a type from here.

FROZEN after the first fan-out. Do not edit without telling every consumer.

Conventions
- Every model ignores unknown keys (extra="ignore"), so partial or richer JSON loads.
- Every optional field has a default. Lists and dicts default to empty.
- Times: `ts`, `*_at` are float epoch seconds (UTC). Durations: `*_ms` milliseconds, `*_s` seconds.
- Seats are referred to by `seat_no` (int, 0-based). Models by `model_id` (registry id).
- Closed string sets are `typing.Literal` aliases. Open strings (Purpose, MemoryAction,
  Position, Scope) are plain `str` with the grammar documented next to the alias.
- LLM-facing schemas (Draft, Critique, Ballot, ReviewBallot, MemoryVerdict, WorkerOutput,
  TaskProfile) hold only what the model writes. The engine keys them by seat outside the model.
- No logic lives here.

Classes by spec section
  5.4  Registry      ModelSource, ServeProfile, ServeConfig, ReasoningControl, MeasuredStats, ModelEntry
  7.1  Gateway       CallSpec, CallResult
  8    Profiler      TaskProfile
  9.6  Router        SeatAssignment, LineupScore, RejectedLineup, LineupRecord
  10.4 Chamber       Claim, Draft, Flaw, Review, CheckRequest, Critique, CruxVote, Ballot,
                     MinorityPosition, Departure, UserQuestion, Decision
  10.5 Clerk         Option, Crux
  10.6 Evidence      EvidenceResult
  10.8 Modes         ModeConfig (+ MODE_DEFAULTS), EffortPlan
  11.1 Plan          InterfaceDef, Deliverable, Plan
  11.2 Micro-task    Check, ContextFile, TaskContext, TaskBudget, MicroTask
  12.1 Workers       WorkerOp, WorkerOutput
  13.1 Inspector     CheckResult, TaskStatus, AttemptRecord
  14.1 Work report   WorkSummary, DiffStats, WorkReportTask, WorkReport
  14.2 Review vote   ReviewFix, ReviewBallot
  15.3 Chronicle     EvidenceRef, ChronicleEntry
  15.4 Reflection    MemoryCandidate, MemoryVerdict
  16.3 Events        Event
  16.4 Run states    RunState
  17   API           RunRequest, RunCounters, RunSnapshot, UserInput
  18.1 Bench         BenchTask, BenchResult, BenchRunRequest, BenchSummaryRow, CalibrationCell
  19   Telemetry     ResidentModel, TelemetrySnapshot
  9.7  Router stats  BehaviourStats
  27.4 Tribunal      TribunalQuestion, TribunalAnswer, DefenseVerdict, TribunalOutcome
  27.6 Corrections   TrainingExample, Correction
  28   Reliability   ClaimRecord, BehaviourSignals, ClaimScore, Probe

Added 2026-10-10 (additive only): everything in sections 27 and 28, RunState.EXAMINING,
ModelEntry.ollama_tag, CallResult.logprobs, Decision.contested_after_review,
RunSnapshot.tribunal / corrections / claim_scores.

Added 2026-10-11 (additive only): EffortPlan, TaskProfile.contested, CheckResult.invalid,
WorkSummary.superseded, WorkReportTask.superseded_by, WorkReport.final_checks / files.

Literal aliases
  Purpose(str), ReasoningLevel, Priority, CallError, Category, Difficulty, Deliverable_, Need,
  Outcome, Severity, FlawKind, DraftVerdict, Position(str), Stance, CruxKind, CheckKind,
  LensName, Mode, RouterTier, InterfaceKind, TaskKind, TaskTier, CheckType, WorkerOpKind,
  InspectLevel, ReviewVerdict, EntryKind, EntryStatus, Scope(str), MemoryAction(str),
  ReasoningKind, StructuredMode, ModelRole, ModelStatus, ServeProfileName, AnswerType,
  Split, GraderType, ErrorKind, TribunalOutcomeKind, VerifiedBy, ClaimLabel,
  LabelledBy, ProbeStatus

Constants
  CATEGORIES, DIFFICULTIES, PURPOSES, LENSES, NEEDS, MEMORY_ACTIONS, MODE_DEFAULTS
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------------------
# Aliases and constants
# --------------------------------------------------------------------------------------

# 7.1. Open-ended because of "clerk.<step>"; PURPOSES lists the known ones.
Purpose = str
PURPOSES: tuple[str, ...] = (
    "seat.r0",
    "seat.r1",
    "seat.r2",
    "seat.r3",
    "chair",
    "ratify",
    "clerk.cluster_options",
    "clerk.extract_cruxes",
    "clerk.work_report",
    "foreman.decompose",
    "foreman.review",
    "worker",
    "inspect.review",
    "memory.judge",
    "bench.solo",
    "profile",
    "tribunal.question",
    "tribunal.answer",
    "tribunal.verdict",
)

ReasoningLevel = Literal["off", "council", "max"]
Priority = Literal["interactive", "batch"]
CallError = Literal["timeout", "invalid_output", "server_error", "cancelled"]

# 8 / 18.1
Category = Literal["math", "logic", "code", "science", "knowledge", "reading", "writing", "planning"]
CATEGORIES: tuple[str, ...] = (
    "math",
    "logic",
    "code",
    "science",
    "knowledge",
    "reading",
    "writing",
    "planning",
)
Difficulty = Literal["easy", "medium", "hard"]
DIFFICULTIES: tuple[str, ...] = ("easy", "medium", "hard")
Deliverable_ = Literal["answer", "plan", "build"]
Need = Literal["vision", "code_execution", "long_context", "multilingual"]
NEEDS: tuple[str, ...] = ("vision", "code_execution", "long_context", "multilingual")

# 10.4
Outcome = Literal["consensus", "majority", "chair", "user", "deadlock"]
Severity = Literal["minor", "major", "fatal"]
FlawKind = Literal["factual", "logic", "omission", "risk", "preference"]
DraftVerdict = Literal["better_than_mine", "equal", "worse_than_mine"]
Position = str  # "keep" | "revise" | "adopt:<label>"
Stance = Literal["agree", "disagree", "abstain"]

# 10.5 / 10.6
CruxKind = Literal["factual", "checkable", "value"]
CheckKind = Literal["python", "read_file", "grep"]  # evidence checks, not acceptance checks

# 10.2 / 10.8 / 9
LensName = Literal["builder", "skeptic", "first_principles", "risk", "user_advocate", "specialist"]
LENSES: tuple[str, ...] = (
    "builder",
    "skeptic",
    "first_principles",
    "risk",
    "user_advocate",
    "specialist",
)
Mode = Literal["quick", "standard", "deep"]
RouterTier = Literal["A", "B"]

# 11 / 12 / 13 / 14
InterfaceKind = Literal["function", "type", "file_format", "endpoint"]
TaskKind = Literal["create_file", "edit_file", "write_test", "write_doc", "transform", "research_note"]
TaskTier = Literal["micro", "senior"]
CheckType = Literal["command", "exists", "parses", "contains", "schema", "review"]
WorkerOpKind = Literal["write_file", "replace_block", "append"]
InspectLevel = Literal["L0", "L1", "L2", "L3"]
ReviewVerdict = Literal["accept", "fix", "replan", "ask_user"]

# 15
EntryKind = Literal["preference", "project_fact", "precedent", "lesson", "open_question"]
EntryStatus = Literal["provisional", "active", "contested", "superseded", "retracted"]
Scope = str  # "global" | "project:<workspace hash>" | "category:<task category>"
# "reject" | "provisional" | "adopt" | "merge:<id>" | "supersede:<id>" | "contest:<id>"
MemoryAction = str
MEMORY_ACTIONS: tuple[str, ...] = ("reject", "provisional", "adopt", "merge", "supersede", "contest")

# 5.4
ReasoningKind = Literal["none", "toggle", "effort", "always"]
StructuredMode = Literal["grammar", "prompt_only"]
ModelRole = Literal["seat", "chair", "clerk", "worker", "senior_worker", "embed", "baseline", "planner"]
ModelStatus = Literal["active", "quarantined", "disabled"]
ServeProfileName = Literal["live", "batch"]

# 18.1
AnswerType = Literal["mcq", "numeric", "exact", "code", "freeform"]
Split = Literal["calibration", "test"]
GraderType = Literal["exact", "numeric_tolerance", "unit_tests", "rubric"]

# 27 / 28
ErrorKind = Literal["factual", "logic", "misread_task", "ignored_evidence", "preference", "none"]
TribunalOutcomeKind = Literal["vindicated", "conceded", "failed", "skipped"]
VerifiedBy = Literal["evidence", "ground_truth", "conceded", "agreement"]
ClaimLabel = Literal["true", "false", "unknown"]  # strings, not bools
LabelledBy = Literal["evidence", "ground_truth", "tribunal", "user", "none"]
ProbeStatus = Literal["untrained", "candidate", "validated", "rejected"]

# A float from 0 to 1 as written by a model.
Unit = Annotated[float, Field(ge=0.0, le=1.0)]


def _new_id() -> str:
    return uuid.uuid4().hex


class _Model(BaseModel):
    """Base for every contract type: unknown keys are ignored, `model_*` field names are allowed."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())


# --------------------------------------------------------------------------------------
# 5.4 Registry
# --------------------------------------------------------------------------------------


class ModelSource(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    repo: str = ""
    file: str = ""
    sha256: Optional[str] = None
    license: Optional[str] = None


class ServeProfile(_Model):
    """One way to load a model. `live`: long context, few slots. `batch`: short context, many slots."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    ctx: int = 8192
    parallel: int = 1


class ServeConfig(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    live: ServeProfile = Field(default_factory=lambda: ServeProfile(ctx=32768, parallel=2))
    batch: ServeProfile = Field(default_factory=lambda: ServeProfile(ctx=8192, parallel=16))
    extra_args: list[str] = Field(default_factory=list)


class ReasoningControl(_Model):
    """`off`, `council`, `max` hold the exact request fields that produce that level for this model."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    kind: ReasoningKind = "none"
    off: dict[str, Any] = Field(default_factory=dict)
    council: dict[str, Any] = Field(default_factory=dict)
    max: dict[str, Any] = Field(default_factory=dict)


class MeasuredStats(_Model):
    """Filled in by probes. Null means not measured yet."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    ram_gb_live: Optional[float] = None
    ram_gb_batch: Optional[float] = None
    load_s: Optional[float] = None
    tps_1: Optional[float] = None
    tps_8: Optional[float] = None
    tps_32: Optional[float] = None
    structured_valid_rate: Optional[float] = None
    probe_date: Optional[str] = None


class ModelEntry(_Model):
    """One object of config/models.json."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    id: str
    display: str = ""
    lab: str = ""
    lineage: str = ""
    arch: str = "dense"
    params_b: Optional[float] = None
    active_params_b: Optional[float] = None
    quant: str = ""
    source: ModelSource = Field(default_factory=ModelSource)
    roles: list[ModelRole] = Field(default_factory=list)
    modalities: list[str] = Field(default_factory=lambda: ["text"])
    serve: ServeConfig = Field(default_factory=ServeConfig)
    reasoning: ReasoningControl = Field(default_factory=ReasoningControl)
    structured: StructuredMode = "grammar"
    sampling: dict[str, float] = Field(default_factory=dict)
    priors: dict[str, float] = Field(default_factory=dict)  # category -> 0..1
    measured: MeasuredStats = Field(default_factory=MeasuredStats)
    status: ModelStatus = "active"
    ollama_tag: Optional[str] = None  # name the Ollama driver loads, e.g. "gpt-oss:20b"
    # Extra Ollama request options, passed through untouched (e.g. {"draft_num_predict": 4}).
    ollama_options: dict[str, Any] = Field(default_factory=dict)
    # Label for UI and probes: built-in multi-token-prediction head, or a Modelfile DRAFT model.
    speculative: Literal["none", "mtp", "draft"] = "none"


# --------------------------------------------------------------------------------------
# 7.1 Gateway
# --------------------------------------------------------------------------------------


class CallSpec(_Model):
    """One model call. `json_schema` is the spec's `schema` field (renamed: BaseModel owns `schema`)."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    model_id: str
    call_id: str = Field(default_factory=_new_id)
    run_id: Optional[str] = None
    purpose: Purpose = ""
    messages: list[dict[str, Any]] = Field(default_factory=list)  # [{role, content}]
    json_schema: Optional[dict[str, Any]] = None
    reasoning: ReasoningLevel = "off"
    max_output_tokens: int = 1024
    max_reasoning_tokens: Optional[int] = None
    temperature: Optional[float] = None  # None: use the model card sampling
    top_p: Optional[float] = None
    seed: Optional[int] = None
    timeout_s: float = 120.0
    priority: Priority = "interactive"
    stream: bool = False
    cacheable: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)  # opaque caller tags (seat_no, round, task_id)


class CallResult(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    call_id: str
    ok: bool
    model_id: Optional[str] = None
    content: str = ""  # final text, reasoning block removed
    parsed: Optional[Any] = None  # object matching json_schema, or None
    reasoning_text: Optional[str] = None  # log and UI only, never shown to other models
    finish_reason: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_reasoning: int = 0
    prompt_ms: float = 0.0
    gen_ms: float = 0.0
    tps: float = 0.0
    attempts: int = 1
    cached: bool = False
    error: Optional[CallError] = None
    logprobs: Optional[list[float]] = None  # per output token, when the server returns them


# --------------------------------------------------------------------------------------
# 8 Profiler
# --------------------------------------------------------------------------------------


class TaskProfile(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    categories: dict[Category, float] = Field(default_factory=dict)  # weights sum to 1
    difficulty: Difficulty = "medium"
    needs: list[Need] = Field(default_factory=list)
    deliverable: Deliverable_ = "answer"
    embedding: list[float] = Field(default_factory=list)
    rationale: str = ""
    contested: Optional[bool] = None  # reasonable experts would disagree; None = not judged


# --------------------------------------------------------------------------------------
# 9.6 Router
# --------------------------------------------------------------------------------------


class SeatAssignment(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    seat_no: int
    model_id: str
    lens: Optional[LensName] = None  # assigned after the lineup is fixed
    is_wildcard: bool = False
    is_chair: bool = False
    q: float = 0.0  # competence estimate for this task, 0..1


class LineupScore(_Model):
    """Component scores of 9.5. total = a*merit + b*vote + c*cover + d*div - e*load - f*repeat."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    merit: float = 0.0
    vote: float = 0.0
    cover: float = 0.0
    div: float = 0.0
    load: float = 0.0
    repeat: float = 0.0
    total: float = 0.0


class RejectedLineup(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    models: list[str] = Field(default_factory=list)  # model ids
    score: LineupScore = Field(default_factory=LineupScore)


class LineupRecord(_Model):
    """Router output. The wildcard is the seat with is_wildcard = True."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    seats: list[SeatAssignment] = Field(default_factory=list)
    alternates: list[str] = Field(default_factory=list)  # model ids, best first
    chair_model_id: Optional[str] = None
    tier: RouterTier = "A"
    chosen_score: LineupScore = Field(default_factory=LineupScore)
    rejected: list[RejectedLineup] = Field(default_factory=list)  # top five not chosen
    seed: Optional[int] = None
    k: int = 0


# --------------------------------------------------------------------------------------
# 10.4 Chamber schemas (Draft, Critique, Ballot are written by models)
# --------------------------------------------------------------------------------------


class Claim(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    id: str  # "c1"
    text: str
    support: str = ""


class Draft(_Model):
    """Round 0. A seat's independent answer, produced blind."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    answer: str
    answer_key: Optional[str] = None  # closed-form tasks only: normalized final answer
    summary: str = ""  # 60 words or fewer
    claims: list[Claim] = Field(default_factory=list)  # up to 6
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: Unit = 0.5
    would_change_mind: str = ""
    user_questions: list[str] = Field(default_factory=list)


class Flaw(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    id: str  # "f1"
    text: str
    claim_ref: Optional[str] = None
    severity: Severity = "minor"
    kind: FlawKind = "logic"


class Review(_Model):
    """One seat's view of one other draft."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    target: str  # the anonymous label: "A", "B", ...
    strongest_point: str = ""
    flaws: list[Flaw] = Field(default_factory=list)
    verdict: DraftVerdict = "equal"


class CheckRequest(_Model):
    """An evidence check a seat asks for (10.6)."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    kind: CheckKind
    spec: str = ""  # script text, "path[:start-end]", or a pattern
    settles: Optional[str] = None  # claim_ref (or crux id) the result would settle


class Critique(_Model):
    """Round 1. `changed_because` must be non-empty unless position is "keep" (engine enforces)."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    reviews: list[Review] = Field(default_factory=list)
    checks_requested: list[CheckRequest] = Field(default_factory=list)
    position: Position = "keep"  # keep | revise | adopt:<label>
    changed_because: list[str] = Field(default_factory=list)  # flaw ids or claim ids


class CruxVote(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    crux_id: str
    stance: Stance = "abstain"


class Ballot(_Model):
    """Rounds 2 and 3."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    choice: str  # option id
    ranking: list[str] = Field(default_factory=list)  # all option ids, best first
    final_answer: str = ""
    answer_key: Optional[str] = None
    confidence: Unit = 0.5
    crux_votes: list[CruxVote] = Field(default_factory=list)
    blocking_objection: Optional[str] = None
    changed_because: list[str] = Field(default_factory=list)
    lesson: Optional[str] = None


# --------------------------------------------------------------------------------------
# 10.5 Clerk, 10.6 Evidence
# --------------------------------------------------------------------------------------


class Option(_Model):
    """A distinct candidate answer after near-identical positions are merged."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    id: str
    summary: str = ""
    holders: list[int] = Field(default_factory=list)  # seat_no values
    answer_key: Optional[str] = None


class Crux(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    id: str
    statement: str = ""
    between: list[str] = Field(default_factory=list)  # option ids
    kind: CruxKind = "factual"
    resolved: bool = False
    resolved_by: Optional[str] = None  # evidence check id, "vote", "user", ...


class EvidenceResult(_Model):
    """Engine output of one evidence check. Attached to R2 as fact, not as an opinion."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    kind: CheckKind
    id: str = ""
    spec: str = ""
    settles: Optional[str] = None
    crux_id: Optional[str] = None
    requested_by: list[int] = Field(default_factory=list)  # seat_no values; empty = engine
    ok: bool = False  # the check ran to completion
    output: str = ""
    truncated: bool = False
    exit_code: Optional[int] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    # Option id this result positively supports (27.5): set by the engine only when a python
    # check exits 0 and `settles` names a claim whose owner is known. None: side not known.
    supports: Optional[str] = None


class MinorityPosition(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    seats: list[int] = Field(default_factory=list)
    position: str = ""
    strongest_argument: str = ""
    option_id: Optional[str] = None


class Departure(_Model):
    """Where the council went against its own record."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    chronicle_entry_id: str
    why: str = ""


class UserQuestion(_Model):
    """Decision.needs_user, and the payload of user.input_requested."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    question: str
    options: list[str] = Field(default_factory=list)
    request_id: Optional[str] = None
    crux_id: Optional[str] = None
    context: str = ""


class Decision(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    outcome: Outcome
    option_id: Optional[str] = None
    final_text: str = ""
    answer_key: Optional[str] = None
    agreement: float = 0.0  # share of valid ballots for the chosen option
    tally: dict[str, int] = Field(default_factory=dict)  # option id -> count
    rounds_run: int = 0
    confidence: float = 0.0
    minority_report: list[MinorityPosition] = Field(default_factory=list)
    open_cruxes: list[Crux] = Field(default_factory=list)
    departures: list[Departure] = Field(default_factory=list)
    needs_user: Optional[UserQuestion] = None
    contested_after_review: bool = False  # 27.5: the outlier's defence held
    notes: list[str] = Field(default_factory=list)  # plain remarks, e.g. the Chair ran past the deadline


# --------------------------------------------------------------------------------------
# 10.8 Modes
# --------------------------------------------------------------------------------------


class ModeConfig(_Model):
    """`rounds` is the ordered list of rounds available, e.g. ["r0", "r1", "r2", "r3"]."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    name: Mode
    k: int = 5
    k_options: list[int] = Field(default_factory=list)  # allowed K values (the UI offers 2 to 6; deep also 7)
    rounds: list[str] = Field(default_factory=lambda: ["r0", "r1", "r2", "r3"])
    deadline_s: float = 300.0
    reasoning: ReasoningLevel = "council"
    use: str = ""


class EffortPlan(_Model):
    """How much deliberation one task gets: the mode's rounds, deadline and reasoning, scaled
    to the task. `max_extra_rounds` is how many more voting rounds a close vote may add."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    level: Literal["light", "normal", "heavy"] = "normal"
    rounds: list[str] = Field(default_factory=lambda: ["r0", "r1", "r2", "r3"])
    deadline_s: float = 300.0
    reasoning: ReasoningLevel = "council"
    max_extra_rounds: int = 0
    rationale: str = ""


MODE_DEFAULTS: dict[str, ModeConfig] = {
    "quick": ModeConfig(
        name="quick", k=3, k_options=[2, 3, 4, 5, 6], rounds=["r0"], deadline_s=60.0, reasoning="off",
        use="simple questions",
    ),
    "standard": ModeConfig(
        name="standard", k=6, k_options=[2, 3, 4, 5, 6], rounds=["r0", "r1", "r2", "r3"], deadline_s=300.0,
        reasoning="council", use="default",
    ),
    "deep": ModeConfig(
        name="deep", k=6, k_options=[2, 3, 4, 5, 6, 7], rounds=["r0", "r1", "r2", "r3", "r3"],
        deadline_s=1200.0, reasoning="max", use="hard problems, plans",
    ),
}


# --------------------------------------------------------------------------------------
# 11 Foreman: Plan and MicroTask
# --------------------------------------------------------------------------------------


class InterfaceDef(_Model):
    """A shared thing two tasks must agree on. Copied verbatim into every task that touches it."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    name: str
    kind: InterfaceKind = "function"
    definition: str = ""


class Deliverable(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    id: str
    description: str = ""
    paths: list[str] = Field(default_factory=list)


class Check(_Model):
    """One acceptance check. `type` selects which optional fields apply:

    command : cmd, expect_exit, timeout_s
    exists  : path
    parses  : path, language
    contains: path, pattern
    schema  : path, json_schema
    review  : rubric   (model review: only when nothing above can check it)
    """

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    type: CheckType
    id: Optional[str] = None
    cmd: Optional[str] = None
    expect_exit: int = 0
    timeout_s: float = 60.0
    path: Optional[str] = None
    language: Optional[str] = None
    pattern: Optional[str] = None
    json_schema: Optional[dict[str, Any]] = None
    rubric: Optional[str] = None


class ContextFile(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    path: str
    content: str = ""  # whole file or an excerpt
    is_excerpt: bool = False


class TaskContext(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    files: list[ContextFile] = Field(default_factory=list)
    interfaces: list[InterfaceDef] = Field(default_factory=list)  # verbatim from Plan.interfaces
    notes: str = ""


class TaskBudget(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    max_output_tokens: int = 1500
    max_attempts: int = 3


class MicroTask(_Model):
    """A unit of work a small model finishes in one generation. Needs at least one acceptance check (Foreman lint)."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    id: str
    title: str = ""
    kind: TaskKind = "create_file"
    goal: str = ""
    context: TaskContext = Field(default_factory=TaskContext)
    read_set: list[str] = Field(default_factory=list)
    write_set: list[str] = Field(default_factory=list)
    output_contract: str = ""
    acceptance: list[Check] = Field(default_factory=list)
    deps: list[str] = Field(default_factory=list)  # task ids that must pass first
    tier: TaskTier = "micro"
    budget: TaskBudget = Field(default_factory=TaskBudget)


class Plan(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    goal: str = ""
    approach: str = ""  # the Decision's final_text
    interfaces: list[InterfaceDef] = Field(default_factory=list)
    deliverables: list[Deliverable] = Field(default_factory=list)
    global_acceptance: list[Check] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    tasks: list[MicroTask] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# 12 Workers, 13 Inspector
# --------------------------------------------------------------------------------------


class WorkerOp(_Model):
    """write_file: path, content. replace_block: path, start_anchor, end_anchor, content. append: path, content."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    op: WorkerOpKind
    path: str
    content: str = ""
    start_anchor: Optional[str] = None
    end_anchor: Optional[str] = None


class WorkerOutput(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    ops: list[WorkerOp] = Field(default_factory=list)
    notes: str = ""
    blocked: Optional[str] = None  # the reason this task cannot be done as specified


class CheckResult(_Model):
    """Result of one Check (task acceptance, L0 structure, L2 review or L3 integration)."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    ok: bool
    type: Optional[CheckType] = None
    check: Optional[Check] = None
    check_id: Optional[str] = None
    task_id: Optional[str] = None  # None for global_acceptance
    attempt: Optional[int] = None
    level: Optional[InspectLevel] = None
    exit_code: Optional[int] = None
    output_tail: str = ""
    score: Optional[float] = None  # review checks
    error: Optional[str] = None
    duration_ms: float = 0.0
    # The check itself is broken (e.g. a test command that ran zero tests). Says nothing
    # about the work.
    invalid: bool = False


class TaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    passed = "passed"
    failed = "failed"
    blocked = "blocked"
    skipped = "skipped"
    # upper-case aliases of the same members
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class AttemptRecord(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    task_id: str
    attempt: int = 1  # 1-based
    model_id: Optional[str] = None
    temperature: Optional[float] = None
    ok: bool = False
    blocked: Optional[str] = None
    output: Optional[WorkerOutput] = None
    checks: list[CheckResult] = Field(default_factory=list)
    failing_check: Optional[str] = None
    error_tail: str = ""
    error: Optional[str] = None
    files_changed: list[str] = Field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    wall_ms: float = 0.0


# --------------------------------------------------------------------------------------
# 14 Review loop
# --------------------------------------------------------------------------------------


class WorkSummary(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    passed: int = 0
    failed: int = 0
    blocked: int = 0
    skipped: int = 0
    superseded: int = 0  # failed tasks whose files a later passed task rewrote
    # failed or blocked tasks whose files no passed task wrote: that work is missing. A failed
    # fix task on files an earlier task got right is not counted (the rollback restores them).
    unfinished: int = 0


class DiffStats(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    files_added: int = 0
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0


class WorkReportTask(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    id: str
    title: str = ""
    status: TaskStatus = TaskStatus.queued
    attempts: int = 0
    model: Optional[str] = None  # model id of the last attempt
    failing_check: Optional[str] = None
    error_tail: str = ""
    files_changed: list[str] = Field(default_factory=list)
    # id of a later passed task that rewrote all files of this task
    superseded_by: Optional[str] = None


class WorkReport(_Model):
    """Built by the Clerk from Inspector records. Seats read this, not raw output."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    summary: WorkSummary = Field(default_factory=WorkSummary)
    tasks: list[WorkReportTask] = Field(default_factory=list)
    integration: list[CheckResult] = Field(default_factory=list)
    diff_stats: DiffStats = Field(default_factory=DiffStats)
    deviations: list[str] = Field(default_factory=list)
    # every check re-run on the files as they are now
    final_checks: list[CheckResult] = Field(default_factory=list)
    files: dict[str, str] = Field(default_factory=dict)  # path -> current content, clipped


class ReviewFix(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    problem: str
    task_id: Optional[str] = None
    proposed_change: str = ""


class ReviewBallot(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    verdict: ReviewVerdict
    fixes: list[ReviewFix] = Field(default_factory=list)  # for "fix"
    reason: str = ""


# --------------------------------------------------------------------------------------
# 15 Chronicle
# --------------------------------------------------------------------------------------


class EvidenceRef(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    run_id: str
    event_seq: Optional[int] = None
    quote: str = ""


class MemoryVerdict(_Model):
    """One panel seat's blind verdict on a candidate. Written by a model."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    durable: bool
    kind: EntryKind = "lesson"
    scope: Scope = "global"
    statement_rewrite: str = ""
    action: MemoryAction = "reject"
    reason: str = ""


class MemoryCandidate(_Model):
    """An observation the Clerk extracted from a run, before the panel judges it."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    text: str
    id: str = ""
    run_id: Optional[str] = None
    source: str = ""  # user_statement | user_choice | plan_edit | override | lesson | review_failure | departure
    kind_hint: Optional[EntryKind] = None
    scope_hint: Optional[Scope] = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    related_entry_ids: list[str] = Field(default_factory=list)


class ChronicleEntry(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    id: str
    kind: EntryKind = "lesson"
    scope: Scope = "global"
    statement: str = ""
    rationale: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)
    status: EntryStatus = "provisional"
    confidence: float = 0.5
    support_count: int = 0
    contradict_count: int = 0
    created_at: Optional[float] = None
    last_confirmed_at: Optional[float] = None
    review_after: int = 20  # in-scope runs without confirmation before it is re-judged
    supersedes: Optional[str] = None
    votes: list[MemoryVerdict] = Field(default_factory=list)
    embedding: list[float] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# 27 Tribunal, corrections
# --------------------------------------------------------------------------------------


class TribunalQuestion(_Model):
    """Written by an examiner seat. `seat_no` is filled by the engine (the asker)."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    question: str
    targets_claim: Optional[str] = None  # claim id of the outlier's draft
    seat_no: Optional[int] = None


class TribunalAnswer(_Model):
    """Written by the outlier. Answers are in the order of the questions."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    answer: str
    concedes: bool = False
    new_evidence: str = ""
    seat_no: Optional[int] = None


class DefenseVerdict(_Model):
    """Written by a judge seat. `lesson` is one sentence addressed to the outlier model."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    held: bool
    score: Unit = 0.5
    decisive_point: str = ""
    error_kind: ErrorKind = "none"
    lesson: str = ""
    seat_no: Optional[int] = None


class TribunalOutcome(_Model):
    """27.5. `held_share` is the share of judges who said the defence held."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    outlier_seat: Optional[int] = None  # None when skipped
    outlier_model_id: Optional[str] = None
    outcome: TribunalOutcomeKind = "skipped"
    held_share: float = 0.0
    error_kind: ErrorKind = "none"  # the majority error_kind of the verdicts
    lesson: str = ""
    questions: list[TribunalQuestion] = Field(default_factory=list)
    answers: list[TribunalAnswer] = Field(default_factory=list)
    verdicts: list[DefenseVerdict] = Field(default_factory=list)
    correction_id: Optional[str] = None


class TrainingExample(_Model):
    """One chat-format training example: `messages` in, `target` is the assistant text wanted."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    messages: list[dict[str, Any]] = Field(default_factory=list)  # [{role, content}]
    target: str = ""


class Correction(_Model):
    """27.6. Project-scoped: `project` is the workspace hash."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    id: str = Field(default_factory=_new_id)
    project: str = ""
    model_id: str = ""
    lineage: str = ""
    run_id: Optional[str] = None
    created_at: Optional[float] = None
    task: str = ""  # truncated task text
    wrong_position: str = ""
    council_position: str = ""
    error_kind: ErrorKind = "none"
    lesson: str = ""
    verified_by: Optional[VerifiedBy] = None
    examples: list[TrainingExample] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# 28 Reliability and the probe
# --------------------------------------------------------------------------------------


class ClaimRecord(_Model):
    """28.2. One Draft claim in the ledger. `label` is the string "true", "false" or "unknown"."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    id: str = Field(default_factory=_new_id)
    run_id: Optional[str] = None
    project: str = ""
    model_id: str = ""
    seat_no: Optional[int] = None
    claim_id: str = ""  # Claim.id inside the draft: "c1"
    text: str = ""
    confidence: float = 0.5
    label: ClaimLabel = "unknown"
    labelled_by: LabelledBy = "none"
    created_at: Optional[float] = None


class BehaviourSignals(_Model):
    """28.3. Every signal is optional; a missing one is dropped and the weights renormalized."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    mean_logprob: Optional[float] = None
    entropy: Optional[float] = None
    self_agreement: Optional[float] = None
    stated_confidence: Optional[float] = None
    track_record: Optional[float] = None


class ClaimScore(_Model):
    """28.5. Advisory. `probe` and `probe_auroc` are None unless a validated probe exists.

    Both scores point the same way: 0 = likely wrong, 1 = likely right. `probe` is
    1 - P(deceptive) of the probe, not P(deceptive)."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    claim_ref: str = ""  # Claim.id
    reliability: float = 0.5
    probe: Optional[float] = None
    probe_auroc: Optional[float] = None
    seat_no: Optional[int] = None


class Probe(_Model):
    """28.4. A linear probe on one layer of one model."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    model_id: str = ""
    layer: int = 0
    weights: list[float] = Field(default_factory=list)
    bias: float = 0.0
    auroc: float = 0.0  # held-out
    n_train: int = 0
    trained_at: Optional[float] = None
    status: ProbeStatus = "untrained"


class BehaviourStats(_Model):
    """9.7. Per-model counters. Every field but `model_id` is a count; rates are count / runs."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    model_id: str
    flip_to_wrong: int = 0
    flip_to_right: int = 0
    persuaded: int = 0
    invalid: int = 0
    timeouts: int = 0
    runs: int = 0
    agree_with_decision: int = 0  # runs where its final position was the decision


# --------------------------------------------------------------------------------------
# 16 Events and run states
# --------------------------------------------------------------------------------------


class Event(_Model):
    """Envelope. `seq` is strictly increasing per database; 0 means not yet stored."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    type: str
    seq: int = 0
    ts: float = 0.0
    run_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RunState(str, Enum):
    INTAKE = "INTAKE"
    PROFILING = "PROFILING"
    CONVENING = "CONVENING"
    DELIBERATING = "DELIBERATING"
    DECIDED = "DECIDED"
    EXAMINING = "EXAMINING"  # 27.2: the tribunal, between DECIDED and whatever follows
    PLANNING = "PLANNING"
    AWAITING_DELEGATION = "AWAITING_DELEGATION"
    EXECUTING = "EXECUTING"
    REVIEWING = "REVIEWING"
    INTEGRATING = "INTEGRATING"
    REFLECTING = "REFLECTING"
    DONE = "DONE"
    AWAITING_USER = "AWAITING_USER"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


# --------------------------------------------------------------------------------------
# 17 API
# --------------------------------------------------------------------------------------


class RunRequest(_Model):
    """Body of POST /runs."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    task: str
    workspace: Optional[str] = None
    mode: Mode = "standard"
    deliverable: Optional[Deliverable_] = None  # None: the Profiler decides
    lineup_override: Optional[list[str]] = None  # model ids
    options: dict[str, Any] = Field(default_factory=dict)


class RunCounters(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    calls: int = 0
    calls_failed: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_reasoning: int = 0
    wall_ms: float = 0.0
    rounds_run: int = 0
    review_cycles: int = 0
    tasks_total: int = 0
    tasks_passed: int = 0
    tasks_failed: int = 0
    tasks_blocked: int = 0
    tasks_skipped: int = 0
    phase_ms: dict[str, float] = Field(default_factory=dict)  # RunState name -> wall-clock ms
    cloud_equiv_usd: float = 0.0


class RunSnapshot(_Model):
    """What GET /runs/{id} returns. Also what the controller persists after every transition."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    run_id: str
    state: RunState = RunState.INTAKE
    prev_state: Optional[RunState] = None  # the state to return to from AWAITING_USER
    task: str = ""
    workspace: Optional[str] = None
    mode: Mode = "standard"
    deliverable: Optional[Deliverable_] = None
    profile: Optional[TaskProfile] = None
    lineup: Optional[LineupRecord] = None
    round: int = 0
    options: list[Option] = Field(default_factory=list)
    cruxes: list[Crux] = Field(default_factory=list)
    evidence: list[EvidenceResult] = Field(default_factory=list)
    tally: dict[str, int] = Field(default_factory=dict)  # option id -> count
    decision: Optional[Decision] = None
    plan: Optional[Plan] = None
    task_statuses: dict[str, TaskStatus] = Field(default_factory=dict)  # task id -> status
    work_report: Optional[WorkReport] = None
    pending_input: Optional[UserQuestion] = None
    counters: RunCounters = Field(default_factory=RunCounters)
    error: Optional[str] = None
    last_seq: int = 0
    created_at: Optional[float] = None
    updated_at: Optional[float] = None
    finished_at: Optional[float] = None
    tribunal: Optional[TribunalOutcome] = None
    corrections: list[Correction] = Field(default_factory=list)
    claim_scores: list[ClaimScore] = Field(default_factory=list)


class UserInput(_Model):
    """Body of POST /runs/{id}/input. One of `choice` or `text`."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    request_id: str
    choice: Optional[str] = None
    text: Optional[str] = None


# --------------------------------------------------------------------------------------
# 18.1 Bench
# --------------------------------------------------------------------------------------


class BenchTask(_Model):
    """One line of the benchmark JSONL."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    id: str
    prompt: str
    source: str = ""
    category: Category = "knowledge"
    difficulty: Difficulty = "medium"
    split: Split = "test"
    choices: Optional[list[str]] = None
    answer_type: AnswerType = "freeform"
    answer: str = ""  # ground truth, or for code: the test file
    grader: dict[str, Any] = Field(default_factory=dict)  # {"type": GraderType, ...}


class BenchResult(_Model):
    """One line per task per mode. `mode` is a bench mode string such as "solo:<model>" or "council"."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    id: str
    mode: str
    answer: str = ""
    answer_key: Optional[str] = None
    correct: Optional[bool] = None
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_reasoning: int = 0
    wall_ms: float = 0.0
    lineup: list[str] = Field(default_factory=list)  # model ids
    rounds_run: int = 0
    outcome: Optional[Outcome] = None
    agreement: Optional[float] = None


class CalibrationCell(_Model):
    """One cell of the Router's calibration table: one model's solo answer to one task."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    task_id: str
    model_id: str
    correct: bool = False
    answer_key: Optional[str] = None


class BenchRunRequest(_Model):
    """`modes` are bench mode strings (18.2). Empty `models` means the whole registry."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    tasks_path: str = ""
    modes: list[str] = Field(default_factory=list)
    split: Split = "test"
    limit: Optional[int] = None
    models: list[str] = Field(default_factory=list)  # model ids
    # Run-size options (all optional, defaults keep the 18.2 behaviour).
    calibration_limit: Optional[int] = None  # at most N calibration tasks; 0 = skip, route with Tier A
    calibration_models: Literal["lineup", "all"] = "lineup"  # who answers the calibration split
    reasoning: ReasoningLevel = "max"  # solo calls; "max" is 18.2, the others are for a fast run
    max_output_tokens: Optional[int] = None  # solo calls; None = config.bench
    max_reasoning_tokens: Optional[int] = None  # solo calls; None = config.bench (none when off)
    resume: bool = True  # reuse cached solo calls and results already written for the same settings
    progress: bool = False  # the runner prints progress lines to stderr


class BenchSummaryRow(_Model):
    """One row of the 18.7 report."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    mode: str
    n: int = 0
    accuracy: float = 0.0
    by_difficulty: dict[str, float] = Field(default_factory=dict)  # difficulty -> accuracy
    by_category: dict[str, float] = Field(default_factory=dict)  # category -> accuracy
    mean_tokens: float = 0.0
    mean_wall_ms: float = 0.0


# --------------------------------------------------------------------------------------
# 19 Telemetry
# --------------------------------------------------------------------------------------


class ResidentModel(_Model):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    model_id: str
    footprint_gib: float = 0.0


class TelemetrySnapshot(_Model):
    """Payload of telemetry.tick and GET /telemetry. Null means the signal is unavailable."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    ts: float = 0.0
    mem_total_gib: float = 0.0
    mem_available_gib: float = 0.0
    mem_used_gib: float = 0.0
    swap_used_gib: float = 0.0
    resident: list[ResidentModel] = Field(default_factory=list)
    tps_by_model: dict[str, float] = Field(default_factory=dict)
    tps_total: float = 0.0
    in_flight: dict[str, int] = Field(default_factory=dict)  # model id -> calls in flight
    queue_depth: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_reasoning: int = 0
    gpu_util: Optional[float] = None
    gpu_temp_c: Optional[float] = None
    gpu_power_w: Optional[float] = None
    cpu_util: Optional[float] = None
    cloud_equiv_usd: float = 0.0  # estimate: tokens x a configurable reference price


__all__ = [
    # aliases
    "Purpose", "ReasoningLevel", "Priority", "CallError", "Category", "Difficulty", "Deliverable_",
    "Need", "Outcome", "Severity", "FlawKind", "DraftVerdict", "Position", "Stance", "CruxKind",
    "CheckKind", "LensName", "Mode", "RouterTier", "InterfaceKind", "TaskKind", "TaskTier",
    "CheckType", "WorkerOpKind", "InspectLevel", "ReviewVerdict", "EntryKind", "EntryStatus",
    "Scope", "MemoryAction", "ReasoningKind", "StructuredMode", "ModelRole", "ModelStatus",
    "ServeProfileName", "AnswerType", "Split", "GraderType", "Unit",
    "ErrorKind", "TribunalOutcomeKind", "VerifiedBy", "ClaimLabel", "LabelledBy",
    "ProbeStatus",
    # constants
    "CATEGORIES", "DIFFICULTIES", "PURPOSES", "LENSES", "NEEDS", "MEMORY_ACTIONS", "MODE_DEFAULTS",
    # models
    "ModelSource", "ServeProfile", "ServeConfig", "ReasoningControl", "MeasuredStats", "ModelEntry",
    "CallSpec", "CallResult", "TaskProfile", "SeatAssignment", "LineupScore", "RejectedLineup",
    "LineupRecord", "Claim", "Draft", "Flaw", "Review", "CheckRequest", "Critique", "CruxVote",
    "Ballot", "Option", "Crux", "EvidenceResult", "MinorityPosition", "Departure", "UserQuestion",
    "Decision", "ModeConfig", "InterfaceDef", "Deliverable", "Check", "ContextFile", "TaskContext",
    "TaskBudget", "MicroTask", "Plan", "WorkerOp", "WorkerOutput", "CheckResult", "TaskStatus",
    "AttemptRecord", "WorkSummary", "DiffStats", "WorkReportTask", "WorkReport", "ReviewFix",
    "ReviewBallot", "EvidenceRef", "MemoryVerdict", "MemoryCandidate", "ChronicleEntry", "Event",
    "RunState", "RunRequest", "RunCounters", "RunSnapshot", "UserInput", "BenchTask", "BenchResult",
    "ResidentModel", "TelemetrySnapshot",
    # added 2026-10-10 (27, 28, bench, router stats)
    "TribunalQuestion", "TribunalAnswer", "DefenseVerdict", "TribunalOutcome", "TrainingExample",
    "Correction", "ClaimRecord", "BehaviourSignals", "ClaimScore", "Probe",
    "BehaviourStats", "CalibrationCell", "BenchRunRequest", "BenchSummaryRow",
    # added 2026-10-11
    "EffortPlan",
]
