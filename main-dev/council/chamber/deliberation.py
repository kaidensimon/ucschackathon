"""The deliberation state machine (spec 10.1 - 10.12).

PURE: no I/O, no clock, no randomness beyond the injected seed. It says which calls and
checks it needs and is told the results. The same logic serves a live run and a benchmark.

Driving loop
    d = Deliberation(...)
    events = d.take_events()                 # round.started of R0 (also returned by the next on_*)
    while not d.is_done():
        for spec in d.pending_calls():       # each call is returned once
            ... run it, then: events = d.on_result(result)
        for check in d.pending_checks():     # PendingCheck (a CheckRequest with a check_id)
            ... run it, then: events = d.on_evidence(check.check_id, evidence_result)
        ... when the run deadline passes: events = d.on_deadline()
    decision = d.decision()

Phases (property `phase`)
    r0 -> cluster -> cruxes -> r1 -> evidence -> r2 -> r3 -> chair -> ratify -> done
    (cluster and cruxes are only waited on when a Clerk call is out; rounds follow mode.rounds)

Choices the spec leaves open, as made here
- Round number in events = index into mode.rounds (r0=0, r1=1, r2=2, r3=3, second r3=4).
- Closed-form clustering is used for answer_type mcq / numeric / exact. "freeform" and "code"
  are open tasks (Clerk call, or one option per draft without a Clerk).
- R0 substitution: once per seat, for invalid output or a server error. A timeout or a
  cancelled call makes the seat abstain (10.10).
- A ballot-round timeout carries the seat's last valid position; invalid output abstains.
- Fewer valid drafts than quorum goes to the Chair. No valid draft at all is a deadlock.
- on_deadline() voids open seat, Clerk and evidence work and applies the 10.7 fallback at once.
  A Chair or ratify call that is already out is NOT cancelled: it ends by its own timeout.
  on_deadline(remaining_s) says how much time is really left (the Chair reserve, see below);
  with no argument none is left. With none left no further Chair is tried and no revision is
  asked for.
- If every Chair fails, the Decision is `deadlock` carrying the best text of the leading option.
  A deadline fallback is never a deadlock by itself: a share over 50% is `majority`, anything
  else goes to the Chair, and only a failed Chair call gives `deadlock`.

Time (the engine has no clock: set_remaining() and on_deadline() tell it)
- Every call's timeout is budget.turn_timeout_s: token caps of the round, the seat's speed
  (seat_tps, 15 tokens/s when unknown) and the number of seats that generate together.
- chair_reserve_s() is kept back from the deadline for the Chair. Seat and Clerk calls are
  capped by the time left MINUS that reserve, and no round starts once only the reserve is
  left. The driver should call on_deadline(remaining) when remaining <= chair_reserve_s().
- The Chair is capped by the time really left but always gets CHAIR_FLOOR_S. A Chair called
  with no time left is still called, and the Decision carries LATE_CHAIR_NOTE in `notes`.
- Round 0 early exit uses only confidences the seats stated. A draft with no `confidence`
  field (the schema default 0.5) is left out of the mean; when fewer than half of the
  agreeing seats stated one there is no early exit.
- The engine emits evidence.requested and evidence.result itself (it owns the check ids).
- snapshot() keeps the calls that are out. restore() hands them out again from pending_calls(),
  because after a restart the old in-flight calls are gone. `normalize` is not serializable:
  pass it to restore() again.

Additions (27.6, 28.5, 10.5), all optional
- seat_notes {seat_no: text} is appended to that seat's system prompt after the council record.
  A seat whose model is substituted loses its notes: they were written for the old model.
- set_claim_scores() attaches advisory engine scores to the round 1 body, for the OTHER seats'
  claims under the labels that seat sees. Round 1 calls still waiting in pending_calls() are
  updated; calls already handed out are not. Scores never touch a vote or a weight.
- Cruxes come from council.chamber.cruxes. With a Clerk: one call before round 1, and the
  heuristic if it returns nothing usable. In every case, when no crux exists after round 1 the
  heuristic runs once over the critiques (cruxes.extracted is emitted again if it finds any).
  A Clerk crux whose `between` names no known option is taken to be between all options.
- A check settles a crux when its `settles` is the crux id or the crux statement, or the
  claim ref of the requesting seat's flaw that the crux was built from.
- final_ballots() gives each seat's last valid position as a ballot: its last cast ballot, or
  one built from its draft position when it never cast one. None = no valid draft at all.

Additions of 1.5, all optional
- set_lie_flags() puts the lie detector's notes (council.chamber.lie_notes) in the round 1 body,
  after the claim-score block, under the anonymous letters that seat sees. Same timing rule as
  set_claim_scores(). Advisory only: a flag never touches a vote or a weight.
- ctx_tokens is the context window of the seats. The other seats' drafts pasted into round 1
  and the critiques pasted into round 2 are cut (council.chamber.compact) to the room that is
  left after the rest of the prompt and the reply. Material that fits is pasted unchanged.
  A claim or critique that was cut away cannot be cited in changed_because.
- Council sizes 2 to 6 use the same rules. With two seats the quorum is 2 and the 80% bar
  means both must agree; a 1-1 split is not a consensus. It is not a majority either: the
  competence weights do not break it, the Chair decides.

Dynamic extension (optional, off by default: max_extra_rounds=0)
- "The council may keep arguing while it is getting closer." When a ballot round ends with no
  consensus and no planned round is left, one more "r3" re-ballot is added instead of the
  fallback (majority / Chair) when ALL of these hold:
    extra rounds used < max_extra_rounds; leading share >= extend_min_agreement;
    the share rose against the previous ballot round, OR an open crux is left, OR this was
    the first ballot round; the tally is not the same as the previous ballot round's with a
    share that did not rise (arguing changed nothing: stop); _can_start("r3") passes; a
    quorum voted and there is no blocking-objection veto.
- The added round is appended to the engine's own round list, so it is numbered and begun
  exactly like a planned r3. round.extended is emitted after round.completed of the round
  that fell short and before the consensus.failed (next_step "round") that leads into it.
- on_deadline() never extends.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, Callable, Optional

from pydantic import Field

from council.chamber import budget, cluster, compact, consensus, lie_notes
from council.chamber import cruxes as crux_steps
from council.chamber.anonymize import OWN_PREFIX, allowed_refs, anonymize, compress_for_seat, label_to_seat
from council.chamber.calls import (
    ballot_schema,
    build_chair_call,
    build_ratify_call,
    build_seat_call,
    critique_schema,
    draft_schema,
    parse_position,
)
from council.chamber.consensus import ConsensusConfig
from council.chamber.prompts import render
from council.core import event_types as E
from council.core.schemas import (
    Ballot,
    CallResult,
    CallSpec,
    CheckRequest,
    ClaimScore,
    Critique,
    Crux,
    Decision,
    Draft,
    EvidenceResult,
    LineupRecord,
    MinorityPosition,
    ModeConfig,
    Option,
    SeatAssignment,
    TaskProfile,
    UserQuestion,
)
from council.core.schemas_v15 import LieFlag

MAX_CHECKS_PER_ROUND = 6
MAX_CRUXES = 5
MAX_CHAIR_TRIES = 3
CHAIR_FLOOR_S = 60.0  # a Chair or ratify call gets at least this long, even past the deadline
LATE_CHAIR_NOTE = (
    "the run deadline had passed when the Chair was called; it was given its minimum time anyway"
)
SEAT_ROUNDS = ("r0", "r1", "r2", "r3")
RATIFY_THRESHOLD = 0.60
USER_CONFIDENCE_FLOOR = 0.5
CLOSED_TYPES = ("mcq", "numeric", "exact")
BALLOT_ROUNDS = ("r2", "r3")
CHAIR_LENS = "You are the Chair: neutral, fair to every position, bound by the record."
EXTERNAL_CHAIR = "x"
SCORES_HEADING = "Engine reliability scores (advisory, not a vote)"
MAX_SCORE_LINES = 24
DEFAULT_CTX_TOKENS = 16384

CRUX_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cruxes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "between": {"type": "array", "items": {"type": "string"}},
                    "kind": {"type": "string", "enum": ["factual", "checkable", "value"]},
                },
                "required": ["statement", "between", "kind"],
            },
        }
    },
    "required": ["cruxes"],
}

RATIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"approve": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["approve", "reason"],
}


def chair_schema(option_ids: list[str]) -> dict[str, Any]:
    option: dict[str, Any] = {"type": "string"}
    if option_ids:
        option = {"type": "string", "enum": list(option_ids)}
    return {
        "type": "object",
        "properties": {
            "option_id": option,
            "final_text": {"type": "string"},
            "answer_key": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "minority_view": {"type": "string"},
            "user_question": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
        "required": ["option_id", "final_text", "confidence"],
    }


class PendingCheck(CheckRequest):
    """A CheckRequest plus the id to hand back to on_evidence()."""

    check_id: str = ""
    crux_id: Optional[str] = None
    requested_by: list[int] = Field(default_factory=list)


def _default_normalize(key: str, answer_type: str) -> str:
    return " ".join(str(key).strip().casefold().split())


def _dump(obj: Any) -> Any:
    return None if obj is None else obj.model_dump(mode="json")


def _clip01(value: Any, default: float = 0.5) -> float:
    try:
        if isinstance(value, bool):
            return default
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return default


class Deliberation:
    def __init__(
        self,
        run_id: str,
        task: str,
        profile: TaskProfile,
        lineup: LineupRecord,
        mode: ModeConfig,
        record: str = "",
        brief: str = "",
        lens_texts: dict[str, str] | None = None,
        seat_tps: dict[int, float] | None = None,
        clerk_model_id: str | None = None,
        answer_type: str | None = None,
        normalize: Callable[[str, str], str] | None = None,
        cfg: ConsensusConfig | None = None,
        seed: int = 0,
        plan_mode: bool = False,
        seat_notes: dict[int, str] | None = None,
        *,
        max_extra_rounds: int = 0,
        extend_min_agreement: float = 0.5,
        ctx_tokens: int = DEFAULT_CTX_TOKENS,
    ) -> None:
        self._setup(
            run_id, task, profile, lineup, mode, record, brief, lens_texts, seat_tps,
            clerk_model_id, answer_type, normalize, cfg, seed, plan_mode, seat_notes,
            max_extra_rounds=max_extra_rounds, extend_min_agreement=extend_min_agreement,
            ctx_tokens=ctx_tokens,
        )
        self._start_r0()

    # ----------------------------------------------------------------------------------
    # Setup
    # ----------------------------------------------------------------------------------

    def _setup(
        self, run_id, task, profile, lineup, mode, record, brief, lens_texts, seat_tps,
        clerk_model_id, answer_type, normalize, cfg, seed, plan_mode, seat_notes=None,
        *, max_extra_rounds: int = 0, extend_min_agreement: float = 0.5,
        ctx_tokens: int = DEFAULT_CTX_TOKENS,
    ) -> None:
        self.run_id = run_id
        self.task = task
        self.profile = profile
        self.lineup = lineup
        self.mode = mode
        self.record = record or ""
        self.brief = brief or ""
        self.lens_texts = dict(lens_texts or {})
        self.seat_tps = {int(k): float(v) for k, v in (seat_tps or {}).items()}
        self.seat_notes = {int(k): str(v) for k, v in (seat_notes or {}).items() if v}
        self._claim_scores: list[ClaimScore] = []
        self._lie_flags: list[LieFlag] = []
        self.ctx_tokens = int(ctx_tokens or DEFAULT_CTX_TOKENS)
        self.clerk_model_id = clerk_model_id
        self.answer_type = answer_type
        self.seed = int(seed)
        self.plan_mode = bool(plan_mode)
        self._normalize = normalize or _default_normalize
        self._cfg = cfg or ConsensusConfig()

        self._seats: dict[int, SeatAssignment] = {s.seat_no: s.model_copy() for s in lineup.seats}
        self._k = len(self._seats) or lineup.k or mode.k
        self._weights = consensus.competence_weights({n: s.q for n, s in self._seats.items()})
        self._rounds = list(mode.rounds) or ["r0"]
        self.max_extra_rounds = max(0, int(max_extra_rounds or 0))
        self.extend_min_agreement = float(extend_min_agreement)
        self._extra_used = 0  # extension rounds added to self._rounds so far
        self._prev_agreement: Optional[float] = None  # share of the previous ballot round
        self._prev_tally: Optional[dict[str, int]] = None  # its tally

        self._alternates: list[str] = list(lineup.alternates)
        self._substituted: set[int] = set()
        self._phase = "r0"
        self._ri = 0
        self._rounds_run = 0
        self._remaining = float(mode.deadline_s)
        self._deadline_hit = False
        self._crux_done = False
        self._notes: list[str] = []
        self._stated_conf: set[int] = set()  # seats whose draft carried a confidence of its own

        self._drafts: dict[int, Draft] = {}
        self._r0_pos: dict[int, str] = {}
        self._positions: dict[int, str] = {}
        self._options: list[Option] = []
        self._cruxes: list[Crux] = []
        self._critiques: dict[int, Critique] = {}
        self._last_ballots: dict[int, Ballot] = {}
        self._cur_ballots: dict[int, Ballot] = {}
        self._round_ballots: dict[int, Ballot] = {}
        self._carry: list[int] = []
        self._round_opts: list[str] = []
        self._failed: list[int] = []

        self._checks: list[dict[str, Any]] = []  # PendingCheck dump + "done"
        self._check_outbox: list[str] = []
        self._evidence: list[EvidenceResult] = []

        self._outbox: list[CallSpec] = []
        self._waiting: dict[str, dict[str, Any]] = {}  # call_id -> {kind, seat, spec}
        self._used: set[str] = set()

        self._chair: Optional[dict[str, Any]] = None
        self._ratify: dict[int, Optional[list]] = {}
        self._pending: Optional[Decision] = None
        self._decision: Optional[Decision] = None
        self._tally: dict[str, int] = {}
        self._agreement = 0.0
        self._valid_n = 0
        self._top: Optional[str] = None
        self._events: list[tuple[str, dict]] = []

    # ----------------------------------------------------------------------------------
    # Public API (10.12)
    # ----------------------------------------------------------------------------------

    @property
    def phase(self) -> str:
        return self._phase

    def is_done(self) -> bool:
        return self._phase == "done"

    def decision(self) -> Decision:
        if self._decision is None:
            raise RuntimeError("deliberation is not done")
        return self._decision

    def set_remaining(self, seconds: float) -> None:
        self._remaining = max(0.0, float(seconds))

    def chair_reserve_s(self) -> float:
        """Seconds of the deadline kept back for the Chair. 0 once the Chair phase is reached."""
        if self._phase in ("chair", "ratify", "done"):
            return 0.0
        order = self._chair_order()
        return budget.chair_reserve_s(
            self._tps_of(order[0] if order else None), self.mode.reasoning, self.mode.deadline_s
        )

    def set_claim_scores(self, scores: list[ClaimScore]) -> None:
        """Advisory engine scores for draft claims (28.5). Shown in round 1 only. Not a vote.

        Call it before the round 1 calls are taken from pending_calls().
        """
        self._claim_scores = [
            s if isinstance(s, ClaimScore) else ClaimScore.model_validate(s) for s in (scores or [])
        ]
        self._repatch_r1()

    def set_lie_flags(self, flags: list[LieFlag]) -> None:
        """Lie detector flags for draft claims. Shown in round 1 only, as notes. Not a vote.

        Call it before the round 1 calls are taken from pending_calls().
        """
        self._lie_flags = [
            f if isinstance(f, LieFlag) else LieFlag.model_validate(f) for f in (flags or [])
        ]
        self._repatch_r1()

    def _repatch_r1(self) -> None:
        """Rebuild the advisory blocks of the round 1 calls that are still in the outbox."""
        for i, spec in enumerate(self._outbox):
            info = self._waiting.get(spec.call_id)
            if info is None or info["kind"] != "r1" or info["seat"] is None:
                continue
            spec = self._with_scores(spec, info["seat"])
            self._outbox[i] = spec
            info["spec"] = spec

    def final_ballots(self) -> dict[int, Optional[Ballot]]:
        """Each seat's last valid position as a ballot. None: the seat never gave a valid draft."""
        return {
            seat: None if b is None else b.model_copy(deep=True)
            for seat, b in self._all_position_ballots().items()
        }

    def r0_options(self) -> dict[int, Optional[str]]:
        """The option each seat's round 0 draft fell in. None: no valid draft."""
        return {seat: self._r0_pos.get(seat) for seat in sorted(self._seats)}

    def drafts(self) -> dict[int, Draft]:
        return {seat: d.model_copy(deep=True) for seat, d in sorted(self._drafts.items())}

    def options(self) -> list[Option]:
        return [o.model_copy(deep=True) for o in self._options]

    def cruxes(self) -> list[Crux]:
        return [c.model_copy(deep=True) for c in self._cruxes]

    def evidence(self) -> list[EvidenceResult]:
        return [e.model_copy(deep=True) for e in self._evidence]

    def pending_calls(self) -> list[CallSpec]:
        out, self._outbox = self._outbox, []
        return out

    def pending_checks(self) -> list[CheckRequest]:
        ids, self._check_outbox = self._check_outbox, []
        by_id = {c["check_id"]: c for c in self._checks}
        return [
            PendingCheck.model_validate(by_id[i]) for i in ids if i in by_id and not by_id[i]["done"]
        ]

    def take_events(self) -> list[tuple[str, dict]]:
        """Events buffered since the last on_* call (round.started of R0 right after construction)."""
        out, self._events = self._events, []
        return out

    def on_result(self, result: CallResult) -> list[tuple[str, dict]]:
        info = self._waiting.pop(result.call_id, None)
        if info is None or self.is_done():
            return self.take_events()
        kind, seat = info["kind"], info["seat"]
        if kind == "r0":
            self._on_r0(seat, result)
        elif kind == "cluster":
            self._on_cluster(result)
        elif kind == "cruxes":
            self._on_cruxes(result)
        elif kind == "r1":
            self._on_r1(seat, result)
        elif kind in BALLOT_ROUNDS:
            self._on_ballot(seat, result, info["spec"])
        elif kind == "chair":
            self._on_chair(result)
        elif kind == "ratify":
            self._on_ratify(seat, result)
        return self.take_events()

    def on_evidence(self, check_id: str, result: EvidenceResult) -> list[tuple[str, dict]]:
        cid = check_id or result.id
        check = next((c for c in self._checks if c["check_id"] == cid), None)
        if check is None or check["done"] or self.is_done():
            return self.take_events()
        check["done"] = True
        result = result.model_copy(
            update={
                "id": cid,
                "spec": result.spec or check["spec"],
                "settles": result.settles or check["settles"],
                "crux_id": result.crux_id or check["crux_id"],
                "requested_by": list(result.requested_by) or list(check["requested_by"]),
            }
        )
        result = result.model_copy(update={"supports": self._supported_option(result)})
        self._evidence.append(result)
        resolved = False
        if result.ok:
            for crux in self._cruxes:
                if not crux.resolved and crux.id in (result.crux_id, result.settles):
                    crux.resolved = True
                    crux.resolved_by = cid
                    resolved = True
        self._emit(
            E.EVIDENCE_RESULT, round=self._ri, check_id=cid, result=_dump(result),
            crux_id=result.crux_id, crux_resolved=resolved,
        )
        if self._phase == "evidence" and all(c["done"] for c in self._checks):
            self._proceed_or_fallback()
        return self.take_events()

    def on_deadline(self, remaining_s: Optional[float] = None) -> list[tuple[str, dict]]:
        """The debate must stop now. `remaining_s` is the time really left (the Chair reserve)."""
        if self.is_done():
            return self.take_events()
        self._deadline_hit = True
        self._remaining = 0.0 if remaining_s is None else max(0.0, float(remaining_s))
        phase = self._phase
        if phase == "r0":
            self._failed.extend(self._void())
            self._after_r0()
        elif phase == "cluster":
            self._void()
            self._after_cluster(cluster.cluster_fallback(self._cluster_positions()))
        elif phase == "cruxes":
            self._void()
            self._emit(E.CRUXES_EXTRACTED, round=self._ri, cruxes=[])
            self._ri -= 1  # the round that was about to start never ran
            self._proceed_or_fallback()
        elif phase == "r1":
            self._failed.extend(self._void())
            self._finish_r1()
        elif phase == "evidence":
            for check in self._checks:
                check["done"] = True
            self._check_outbox = []
            self._proceed_or_fallback()
        elif phase in BALLOT_ROUNDS:
            self._carry.extend(self._void())
            self._finish_ballot()
        # chair / ratify: the call that is out ends by its own timeout
        return self.take_events()

    # ----------------------------------------------------------------------------------
    # Small helpers
    # ----------------------------------------------------------------------------------

    def _emit(self, type_: str, **fields: Any) -> None:
        self._events.append((type_, E.make_payload(type_, **fields)))

    def _tps_of(self, who: Any) -> Optional[float]:
        """Known speed of a seat (seat_no, or its text key from _chair_order). None = unknown."""
        try:
            return self.seat_tps.get(int(who))
        except (TypeError, ValueError):
            return None

    def _debate_left(self) -> float:
        """Time left for seat and Clerk work: what is left after the Chair reserve."""
        return self._remaining - self.chair_reserve_s()

    def _timeout(self, kind: str, seat: Optional[int], spec: CallSpec) -> float:
        together = max(1, len(self._seats))
        reasoning = self.mode.reasoning
        if kind in SEAT_ROUNDS:
            return budget.turn_timeout_s(
                kind, self._tps_of(seat), reasoning, together, self._debate_left()
            )
        if kind == "chair":
            who = self._chair["who"] if self._chair else None
            if self._remaining <= 0:
                # A late decision beats a deadlock: the Chair still gets its floor.
                if LATE_CHAIR_NOTE not in self._notes:
                    self._notes.append(LATE_CHAIR_NOTE)
                return CHAIR_FLOOR_S
            out = budget.turn_timeout_s("chair", self._tps_of(who), reasoning, 1, self._remaining)
            return max(CHAIR_FLOOR_S, out)
        if kind == "ratify":
            left = self._remaining if self._remaining > 0 else None
            out = budget.turn_timeout_s("ratify", self._tps_of(seat), reasoning, together, left)
            return max(CHAIR_FLOOR_S, out)
        # Clerk steps (cluster, cruxes): one model, alone, speed unknown.
        return budget.turn_timeout_s(
            "clerk", None, "off", 1, self._debate_left(), tokens=int(spec.max_output_tokens)
        )

    def _queue(self, spec: CallSpec, kind: str, seat: Optional[int] = None) -> CallSpec:
        base = cid = spec.call_id
        n = 2
        while cid in self._used:
            cid = f"{base}#{n}"
            n += 1
        self._used.add(cid)
        spec = spec.model_copy(update={"call_id": cid, "timeout_s": self._timeout(kind, seat, spec)})
        self._waiting[cid] = {"kind": kind, "seat": seat, "spec": spec}
        self._outbox.append(spec)
        return spec

    def _void(self) -> list[int]:
        """Drop every call that is out or queued. Returns the seats that were waited on."""
        seats = [i["seat"] for i in self._waiting.values() if i["seat"] is not None]
        self._waiting = {}
        self._outbox = []
        return seats

    def _waiting_on(self, kind: str) -> bool:
        return any(i["kind"] == kind for i in self._waiting.values())

    def _lens_text(self, seat: SeatAssignment) -> str:
        return self.lens_texts.get(seat.lens or "", "")

    def _queue_seat(self, round_name: str, seat_no: int, body_vars: dict, schema: dict) -> None:
        seat = self._seats[seat_no]
        spec = build_seat_call(
            round_name, self.run_id, seat, self.task, self.brief, self.record,
            self._lens_text(seat), body_vars, schema, self.mode,
            dict(budget.TURN_CAPS[round_name]), self.seed,
            notes=self.seat_notes.get(seat_no, ""),
        )
        if round_name == "r1" and (self._claim_scores or self._lie_flags):
            spec = self._with_scores(spec, seat_no)
        self._queue(spec, round_name, seat_no)

    def _paste_room(self, round_name: str, seat_no: int, body_vars: dict) -> int:
        """Characters left for pasted material in this seat's call (compact.budget_chars).

        `body_vars` is the round body WITHOUT the pasted material: the prompt built from it is
        the fixed part. The reply (and its reasoning, when on) is taken off the context first.
        """
        seat = self._seats[seat_no]
        spec = build_seat_call(
            round_name, self.run_id, seat, self.task, self.brief, self.record,
            self._lens_text(seat), body_vars, None, self.mode,
            dict(budget.TURN_CAPS[round_name]), self.seed,
            notes=self.seat_notes.get(seat_no, ""),
        )
        fixed = sum(len(str(m.get("content") or "")) for m in spec.messages)
        reply = budget.turn_tokens(round_name, self.mode.reasoning)
        return compact.budget_chars(self.ctx_tokens, reply, fixed)

    @staticmethod
    def _fit_critiques(critiques: list[dict], room: int) -> list[dict]:
        """The critiques cut to `room` characters of JSON, worst first. Unchanged when they fit."""
        if len(json.dumps(critiques, ensure_ascii=False, default=str)) <= room:
            return critiques
        # compact ranks blocking > major > minor; the chamber's worst severity is "fatal".
        marked = [{**c, "severity": "blocking"} if c.get("severity") == "fatal" else c for c in critiques]
        out = compact.compact_critiques(marked, room)
        return [{**c, "severity": "fatal"} if c.get("severity") == "blocking" else c for c in out]

    def _scores_block(self, seat_no: int) -> str:
        """Scores for the OTHER seats' claims, under the labels this seat sees. "" when none."""
        lines: list[str] = []
        for label, other in label_to_seat(list(self._drafts), seat_no, self.seed).items():
            draft = self._drafts.get(other)
            if draft is None:
                continue
            by_ref: dict[str, ClaimScore] = {}
            for score in self._claim_scores:
                if score.seat_no == other and score.claim_ref not in by_ref:
                    by_ref[score.claim_ref] = score
            for ref in ["answer"] + [c.id for c in draft.claims]:
                score = by_ref.get(ref)
                if score is None or len(lines) >= MAX_SCORE_LINES:
                    continue
                name = f"{label} answer" if ref == "answer" else f"{label}.{ref}"
                line = f"{name}: reliability {_clip01(score.reliability):.2f}"
                if score.probe is not None:
                    # ClaimScore.probe is 1 - P(deceptive): same direction as reliability.
                    line += f", truth-probe {_clip01(score.probe):.2f}"
                    if score.probe_auroc is not None:
                        line += f" (probe held-out AUROC {_clip01(score.probe_auroc):.2f})"
                lines.append(line)
        if not lines:
            return ""
        return render("claim_scores", scores="\n".join(lines))

    def _lie_block(self, seat_no: int) -> str:
        """Lie detector notes for this seat, under the letters it sees. "" when none."""
        if not self._lie_flags:
            return ""
        letter_of = {
            other: label
            for label, other in label_to_seat(list(self._drafts), seat_no, self.seed).items()
        }
        return lie_notes.notes_for_seat(self._lie_flags, seat_no, letter_of)

    def _with_scores(self, spec: CallSpec, seat_no: int) -> CallSpec:
        """The spec with the advisory blocks at the end of its user message (replacing old ones).

        Order: the claim-score block, then the lie notes.
        """
        messages = [dict(m) for m in spec.messages]
        if not messages:
            return spec
        body = str(messages[-1].get("content") or "")
        cuts = [body.rfind("\n\n" + SCORES_HEADING), body.rfind("\n\n" + lie_notes.HEADER)]
        cuts = [c for c in cuts if c >= 0]
        if cuts:
            body = body[: min(cuts)]
        for block in (self._scores_block(seat_no), self._lie_block(seat_no)):
            if block:
                body = f"{body}\n\n{block}"
        messages[-1]["content"] = body
        return spec.model_copy(update={"messages": messages})

    @staticmethod
    def _data(result: CallResult) -> Any:
        """The parsed object of a good result, else None. Falls back to JSON in `content`."""
        if not result.ok:
            return None
        if result.parsed is not None:
            return result.parsed
        try:
            return json.loads(result.content)
        except (TypeError, ValueError):
            return None

    def _parse(self, cls, result: CallResult):
        data = self._data(result)
        if isinstance(data, cls):
            return data
        if not isinstance(data, dict):
            return None
        try:
            return cls.model_validate(data)
        except Exception:
            return None

    def _next_round(self) -> Optional[str]:
        return self._rounds[self._ri + 1] if self._ri + 1 < len(self._rounds) else None

    def _can_start(self, name: str) -> bool:
        left = self._debate_left()  # the Chair reserve is not spent on debate
        if self._deadline_hit or left <= 0:
            return False
        if name not in budget.TURN_CAPS:
            return True
        tps = [self.seat_tps[s] for s in sorted(self._drafts) if s in self.seat_tps]
        if not tps:
            return True
        return budget.can_start_round(name, tps, self.mode.reasoning, left, concurrent=len(tps))

    def _option(self, option_id: Optional[str]) -> Optional[Option]:
        return next((o for o in self._options if o.id == option_id), None)

    def _option_ids(self) -> list[str]:
        return [o.id for o in self._options]

    def _open_cruxes(self) -> list[Crux]:
        return [c for c in self._cruxes if not c.resolved]

    def _crux_view(self, cruxes: list[Crux]) -> list[dict]:
        return [
            {"id": c.id, "statement": c.statement, "between": list(c.between), "kind": c.kind}
            for c in cruxes
        ]

    def _evidence_view(self) -> list[dict]:
        return [
            {
                "id": e.id, "kind": e.kind, "spec": e.spec, "settles": e.settles,
                "ok": e.ok, "output": e.output, "error": e.error,
            }
            for e in self._evidence
        ]

    def _tally_now(self) -> dict[str, int]:
        tally: dict[str, int] = {}
        for seat in sorted(self._positions):
            opt = self._positions[seat]
            tally[opt] = tally.get(opt, 0) + 1
        return tally

    def _leader(self, tally: dict[str, int]) -> tuple[Optional[str], float]:
        total = sum(tally.values())
        if not total:
            return None, 0.0
        top = sorted(tally, key=lambda o: (-tally[o], o))[0]
        return top, tally[top] / total

    def _sync_holders(self) -> None:
        for opt in self._options:
            opt.holders = sorted(s for s, o in self._positions.items() if o == opt.id)

    def _position_ballot(self, seat: int) -> Optional[Ballot]:
        """The seat's last valid position as a ballot: its last ballot, else built from its draft."""
        if seat in self._last_ballots:
            return self._last_ballots[seat]
        opt = self._positions.get(seat)
        draft = self._drafts.get(seat)
        if opt is None or draft is None:
            return None
        own = self._r0_pos.get(seat) == opt  # False when the seat adopted another draft in R1
        return Ballot(
            choice=opt,
            ranking=[opt],
            final_answer=draft.answer if own else "",
            answer_key=draft.answer_key if own else None,
            confidence=draft.confidence,
        )

    def _all_position_ballots(self) -> dict[int, Optional[Ballot]]:
        return {seat: self._position_ballot(seat) for seat in sorted(self._seats)}

    # ----------------------------------------------------------------------------------
    # R0
    # ----------------------------------------------------------------------------------

    def _start_r0(self) -> None:
        self._phase = "r0"
        self._failed = []
        seats = sorted(self._seats)
        self._emit(
            E.ROUND_STARTED, round=0, purpose="seat.r0", seats=seats, deadline_s=self._remaining
        )
        for seat in seats:
            self._queue_seat("r0", seat, {}, draft_schema())
        if not seats:
            self._after_r0()

    def _on_r0(self, seat: int, result: CallResult) -> None:
        draft = self._parse(Draft, result)
        can_swap = (
            seat not in self._substituted
            and self._alternates
            and not self._deadline_hit
            and result.error not in ("timeout", "cancelled")
        )
        if draft is not None:
            self._drafts[seat] = draft
            data = self._data(result)
            if isinstance(data, Draft):
                stated = "confidence" in data.model_fields_set
            else:
                stated = isinstance(data, dict) and data.get("confidence") is not None
            (self._stated_conf.add if stated else self._stated_conf.discard)(seat)
        elif can_swap:
            self._substituted.add(seat)
            old = self._seats[seat]
            new = old.model_copy(update={"model_id": self._alternates.pop(0)})
            self._seats[seat] = new
            self.seat_notes.pop(seat, None)  # the notes were written for the old model
            self._emit(
                E.SEAT_ASSIGNED, seat_no=seat, model_id=new.model_id, lens=new.lens,
                is_wildcard=new.is_wildcard, is_chair=new.is_chair, q=new.q,
                replaces_model_id=old.model_id,
            )
            self._queue_seat("r0", seat, {}, draft_schema())
        else:
            self._failed.append(seat)
        if not self._waiting_on("r0"):
            self._after_r0()

    def _after_r0(self) -> None:
        if not self._drafts:
            self._rounds_run = 1
            self._emit(
                E.ROUND_COMPLETED, round=0, valid_turns=0, failed_seats=sorted(set(self._failed))
            )
            self._emit(
                E.CONSENSUS_FAILED, round=0, threshold=self._cfg.threshold,
                reason="no valid drafts", next_step="deadlock",
            )
            self._finalize(Decision(outcome="deadlock", rounds_run=1))
            return
        positions = self._cluster_positions()
        if self.answer_type in CLOSED_TYPES:
            try:
                options = cluster.cluster_closed(positions, self.answer_type, self._normalize)
            except Exception:
                options = cluster.cluster_closed(positions, self.answer_type, _default_normalize)
            self._after_cluster(options)
        elif self.clerk_model_id and len(positions) > 1 and not self._deadline_hit:
            spec = cluster.build_cluster_call(self.run_id, self.clerk_model_id, positions)
            spec = spec.model_copy(
                update={"call_id": f"{self.run_id}:clerk.cluster_options", "seed": self.seed}
            )
            self._phase = "cluster"
            self._queue(spec, "cluster")
        else:
            self._after_cluster(cluster.cluster_fallback(positions))

    def _cluster_positions(self) -> dict[int, tuple[Optional[str], str]]:
        return {
            seat: (d.answer_key, d.summary or d.answer[:240]) for seat, d in sorted(self._drafts.items())
        }

    def _on_cluster(self, result: CallResult) -> None:
        data = self._data(result)
        self._after_cluster(
            cluster.parse_cluster_result(data if isinstance(data, dict) else None, self._cluster_positions())
        )

    def _after_cluster(self, options: list[Option]) -> None:
        self._options = options
        self._positions = {seat: o.id for o in options for seat in o.holders}
        self._r0_pos = dict(self._positions)
        self._rounds_run = 1
        tally = cluster.tally_from_options(options)
        top, share = self._leader(tally)
        self._tally, self._agreement, self._top = tally, share, top
        self._valid_n = len(self._drafts)
        self._emit(
            E.OPTIONS_CLUSTERED, round=0, options=[_dump(o) for o in options], tally=tally,
            agreement=share, leading_option_id=top,
        )
        confidences = self._early_confidences(top)
        early = None
        if len(self._drafts) >= consensus.quorum_for(self._k, self._cfg):
            early = consensus.early_agreement(options, confidences, self._k, self._cfg)
        self._emit(
            E.ROUND_COMPLETED, round=0, options=[_dump(o) for o in options], tally=tally,
            agreement=share, leading_option_id=top, valid_turns=len(self._drafts),
            failed_seats=sorted(set(self._failed)), converged=early is not None,
        )
        if early is not None:
            self._early_exit(early)
        elif len(self._drafts) < consensus.quorum_for(self._k, self._cfg):
            self._fallback_now()  # below quorum: evaluate() sends it to the Chair
        else:
            self._proceed_or_fallback()

    def _early_confidences(self, top: Optional[str]) -> dict[int, float]:
        """Confidences for the round 0 early exit: only the ones the seats stated themselves.

        A draft without a `confidence` field parses with the schema default 0.5. Counting that
        as a real 0.5 pulls an agreeing council under the confidence bar and sends it to a
        debate nobody asked for. Such a seat is left out of the mean instead. When fewer than
        half of the leading option's seats stated a confidence, there is no early exit.
        """
        stated = {
            seat: d.confidence for seat, d in self._drafts.items() if seat in self._stated_conf
        }
        option = self._option(top)
        holders = list(option.holders) if option is not None else []
        if 2 * sum(1 for seat in holders if seat in stated) < len(holders):
            return {}
        return stated

    def _early_exit(self, option: Option) -> None:
        self._cur_ballots = {
            s: b for s, b in self._all_position_ballots().items() if b is not None
        }
        self._emit(
            E.CONSENSUS_REACHED, round=0, option_id=option.id, agreement=self._agreement,
            threshold=self._cfg.threshold, tally=self._tally, outcome="consensus", early=True,
        )
        decision = self._vote_decision("consensus", option.id)
        if self.plan_mode and len(option.holders) > 1:
            self._pending = decision
            self._start_chair("merge of the agreeing drafts", "merge", [option.id])
        else:
            self._finalize(decision)

    # ----------------------------------------------------------------------------------
    # Moving between rounds
    # ----------------------------------------------------------------------------------

    def _proceed_or_fallback(self) -> None:
        nxt = self._next_round()
        if nxt is not None and self._can_start(nxt):
            self._advance()
        else:
            self._fallback_now()

    def _fallback_now(self) -> None:
        """10.7 with no round left: consensus, majority or chair from the last valid positions."""
        ballots = self._all_position_ballots()
        res = consensus.evaluate(ballots, self._k, self._cfg, False, False, self._weights)
        self._cur_ballots = {s: b for s, b in ballots.items() if b is not None}
        self._apply_result(res)

    def _advance(self) -> None:
        self._ri += 1
        name = self._rounds[self._ri]
        if not self._crux_done:
            self._crux_done = True
            if self.clerk_model_id and len(self._options) > 1:
                self._phase = "cruxes"
                self._queue(self._crux_call(), "cruxes")
                return
            self._emit(E.CRUXES_EXTRACTED, round=self._ri, cruxes=[])
        self._begin_round(name)

    def _begin_round(self, name: str) -> None:
        self._failed = []
        if name == "r1":
            self._begin_r1()
        elif name in BALLOT_ROUNDS:
            self._begin_ballot(name)
        else:  # an unknown round name (or a second r0) is skipped
            self._proceed_or_fallback()

    def _apply_result(self, res: consensus.ConsensusResult) -> None:
        self._tally, self._agreement, self._top = dict(res.tally), res.share, res.top
        self._valid_n = res.valid
        common = dict(round=self._ri, agreement=res.share, threshold=self._cfg.threshold, tally=res.tally)
        if res.status == "consensus":
            self._emit(E.CONSENSUS_REACHED, option_id=res.top, outcome="consensus", early=False, **common)
            self._finalize(self._vote_decision("consensus", res.top))
            return
        if res.valid < res.quorum:
            reason = f"{res.valid} valid positions, quorum is {res.quorum}"
        elif res.blocked and res.share >= self._cfg.threshold:
            reason = "blocking objections against the leading option"
        else:
            reason = f"share {res.share:.2f} is under {self._cfg.threshold:.2f}"
        failed = dict(
            leading_option_id=res.top, open_cruxes=[_dump(c) for c in self._open_cruxes()], **common
        )
        status = res.status
        if status == "majority" and (self._k == 2 or res.valid == 2) and res.share <= 0.5 + 1e-9:
            # Two valid votes, one each (two seats, or a third seat that gave no ballot): a 1-1
            # split is no majority, whatever the weights say.
            status = "chair"
        if status == "continue":
            self._emit(E.CONSENSUS_FAILED, reason=reason, next_step="round", **failed)
            self._advance()
        elif status == "majority":
            self._emit(E.CONSENSUS_FAILED, reason=reason, next_step="majority", **failed)
            self._finalize(self._vote_decision("majority", res.top))
        else:
            self._emit(E.CONSENSUS_FAILED, reason=reason, next_step="chair", **failed)
            top = consensus.top_two(dict(self._cur_ballots), self._weights)
            self._start_chair(reason, "arbitrate", top or self._option_ids()[:2])

    # ----------------------------------------------------------------------------------
    # Cruxes (Clerk)
    # ----------------------------------------------------------------------------------

    def _crux_call(self) -> CallSpec:
        spec = crux_steps.build_cruxes_call(
            self.run_id, self.clerk_model_id, self._options, self._critiques, MAX_CRUXES
        )
        return spec.model_copy(
            update={"call_id": f"{self.run_id}:clerk.extract_cruxes", "seed": self.seed}
        )

    def _on_cruxes(self, result: CallResult) -> None:
        data = self._data(result)
        if isinstance(data, list):
            data = {"cruxes": data}
        ids = self._option_ids()
        if isinstance(data, dict) and isinstance(data.get("cruxes"), list):
            # Be lenient about `between`: drop unknown ids; none left means "between all options".
            items = []
            for item in data["cruxes"]:
                if isinstance(item, dict):
                    between = item.get("between")
                    between = [b for b in between if b in ids] if isinstance(between, list) else []
                    item = {**item, "between": between or list(ids)}
                items.append(item)
            data = {"cruxes": items}
        else:
            data = None
        cruxes = crux_steps.parse_cruxes(data, self._options, MAX_CRUXES)
        if not cruxes:
            cruxes = crux_steps.heuristic_cruxes(self._options, self._critiques, MAX_CRUXES)
        self._cruxes = cruxes
        self._emit(E.CRUXES_EXTRACTED, round=self._ri, cruxes=[_dump(c) for c in cruxes])
        self._begin_round(self._rounds[self._ri])

    def _heuristic_cruxes_after_r1(self) -> None:
        """No crux yet but the critiques are in: build cruxes from their major and fatal flaws."""
        if self._cruxes or not self._critiques:
            return
        found = crux_steps.heuristic_cruxes(self._options, self._critiques, MAX_CRUXES)
        if found:
            self._cruxes = found
            self._emit(E.CRUXES_EXTRACTED, round=self._ri, cruxes=[_dump(c) for c in found])

    def _claim_owner(self, requesters: list[int], settles: Optional[str]) -> Optional[int]:
        """The seat whose claim `settles` names, or None when that cannot be told.

        Refs: "A.c1" is a claim of the seat the FIRST requester saw as A (labels differ per
        seat), "Y.c1" is the requester's own claim, "2:c1" names seat 2 outright.
        """
        if not settles or not isinstance(settles, str):
            return None
        ref = settles.strip()
        owner: Optional[int] = None
        claim = ""
        if ":" in ref:
            head, _, claim = ref.partition(":")
            try:
                owner = int(head)
            except ValueError:
                return None
        elif "." in ref and requesters:
            head, _, claim = ref.partition(".")
            asker = requesters[0]
            if head == OWN_PREFIX:
                owner = asker
            else:
                owner = label_to_seat(list(self._drafts), asker, self.seed).get(head)
        draft = self._drafts.get(owner) if owner is not None else None
        if draft is None or not any(c.id == claim for c in draft.claims):
            return None
        return owner

    def _supported_option(self, result: EvidenceResult) -> Optional[str]:
        """The option a check result positively supports (27.5), else None.

        Only a python check that ran and exited 0 confirms the claim it settles; that supports
        the option its owner drafted. A check that only ran, a failed one, a read or a grep,
        or a ref with no known owner supports nothing: running a check is not a verdict.
        """
        if not result.ok or result.kind != "python" or result.exit_code != 0:
            return None
        owner = self._claim_owner(list(result.requested_by), result.settles)
        if owner is None:
            return None
        return self._r0_pos.get(owner) or self._positions.get(owner)

    def _crux_for(self, seat: int, settles: Optional[str]) -> Optional[str]:
        """The crux a requested check would settle, or None."""
        if not settles:
            return None
        by_text = {c.statement.strip().casefold(): c.id for c in self._cruxes}
        if settles in {c.id for c in self._cruxes}:
            return settles
        if settles.strip().casefold() in by_text:
            return by_text[settles.strip().casefold()]
        critique = self._critiques.get(seat)
        for review in critique.reviews if critique is not None else []:
            for flaw in review.flaws:
                if flaw.claim_ref == settles and flaw.text.strip().casefold() in by_text:
                    return by_text[flaw.text.strip().casefold()]
        return None

    # ----------------------------------------------------------------------------------
    # R1
    # ----------------------------------------------------------------------------------

    def _begin_r1(self) -> None:
        self._phase = "r1"
        seats = sorted(self._drafts)
        self._emit(
            E.ROUND_STARTED, round=self._ri, purpose="seat.r1", seats=seats,
            deadline_s=self._remaining, focus_crux_ids=[c.id for c in self._cruxes],
        )
        cruxes = self._crux_view(self._cruxes)
        for seat in seats:
            view = anonymize(self._drafts, seat, self.seed)
            body = {"own_draft": view["own"], "anonymized_drafts": [], "cruxes": cruxes}
            view["others"] = compact.compact_drafts(view["others"], self._paste_room("r1", seat, body))
            body["anonymized_drafts"] = view["others"]
            schema = critique_schema(list(view["labels"]), allowed_refs(view))
            self._queue_seat("r1", seat, body, schema)
        if not seats:
            self._finish_r1()

    def _on_r1(self, seat: int, result: CallResult) -> None:
        critique = self._parse(Critique, result)
        if critique is None:
            self._failed.append(seat)
        else:
            kind, _ = parse_position(critique.position)
            if kind != "keep" and not critique.changed_because:
                critique = critique.model_copy(update={"position": "keep"})  # 10.4: no reason, no move
            self._critiques[seat] = critique
        if not self._waiting_on("r1"):
            self._finish_r1()

    def _finish_r1(self) -> None:
        before = dict(self._positions)
        for seat, critique in sorted(self._critiques.items()):
            kind, label = parse_position(critique.position)
            if kind != "adopt":
                continue
            target = label_to_seat(list(self._drafts), seat, self.seed).get(label or "")
            if target in before:
                self._positions[seat] = before[target]
        self._sync_holders()
        self._rounds_run += 1
        tally = self._tally_now()
        top, share = self._leader(tally)
        self._emit(
            E.ROUND_COMPLETED, round=self._ri, options=[_dump(o) for o in self._options],
            tally=tally, agreement=share, leading_option_id=top,
            valid_turns=len(self._critiques), failed_seats=sorted(set(self._failed)),
        )
        self._heuristic_cruxes_after_r1()
        if not self._deadline_hit and self._collect_checks():
            self._phase = "evidence"
            return
        self._proceed_or_fallback()

    def _collect_checks(self) -> bool:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for seat, critique in sorted(self._critiques.items()):
            for req in critique.checks_requested:
                spec = (req.spec or "").strip()
                if not spec:
                    continue
                key = (req.kind, spec)
                if key in merged:
                    if seat not in merged[key]["requested_by"]:
                        merged[key]["requested_by"].append(seat)
                    continue
                if len(merged) >= MAX_CHECKS_PER_ROUND:
                    continue
                merged[key] = {
                    "kind": req.kind, "spec": req.spec, "settles": req.settles,
                    "crux_id": self._crux_for(seat, req.settles),
                    "requested_by": [seat], "done": False,
                }
        for check in merged.values():
            check["check_id"] = f"k{len(self._checks) + 1}"
            self._checks.append(check)
            self._check_outbox.append(check["check_id"])
            self._emit(
                E.EVIDENCE_REQUESTED, round=self._ri, check_id=check["check_id"], kind=check["kind"],
                spec=check["spec"], settles=check["settles"], crux_id=check["crux_id"],
                requested_by=check["requested_by"],
            )
        return bool(merged)

    # ----------------------------------------------------------------------------------
    # R2 / R3
    # ----------------------------------------------------------------------------------

    def _critiques_of(self, seat: int) -> list[dict]:
        """Flaws other seats filed against this seat's draft, under the labels this seat saw in R1."""
        mine = {s: lab for lab, s in label_to_seat(list(self._drafts), seat, self.seed).items()}
        out: list[dict] = []
        for reviewer, critique in sorted(self._critiques.items()):
            if reviewer == seat:
                continue
            theirs = label_to_seat(list(self._drafts), reviewer, self.seed)
            lab = mine.get(reviewer, "?")
            for review in critique.reviews:
                if theirs.get(review.target) != seat:
                    continue
                for flaw in review.flaws:
                    ref = flaw.claim_ref
                    if ref and ref.startswith(f"{review.target}."):
                        ref = "Y." + ref[len(review.target) + 1:]
                    out.append(
                        {
                            "id": f"{lab}.{flaw.id}", "from": lab, "text": flaw.text,
                            "claim_ref": ref, "severity": flaw.severity, "kind": flaw.kind,
                        }
                    )
        return out

    def _begin_ballot(self, name: str) -> None:
        self._phase = name
        self._round_ballots = {}
        self._carry = []
        open_cruxes = self._open_cruxes()
        opt_ids = self._option_ids()
        if name == "r3":
            lead = consensus.top_two(self._all_position_ballots(), self._weights)
            opt_ids = lead or opt_ids[:2]
        self._round_opts = list(opt_ids)
        seats = sorted(self._drafts)
        self._emit(
            E.ROUND_STARTED, round=self._ri, purpose=f"seat.{name}", seats=seats,
            deadline_s=self._remaining, focus_crux_ids=[c.id for c in open_cruxes],
        )
        crux_view = self._crux_view(open_cruxes)
        evidence = self._evidence_view()
        for seat in seats:
            critiques = self._critiques_of(seat)
            view = anonymize(self._drafts, seat, self.seed)
            table = [
                {"id": o.id, "summary": o.summary, "yours": self._positions.get(seat) == o.id}
                for o in self._options
                if o.id in opt_ids
            ]
            if name == "r3":
                body = {"open_cruxes": crux_view, "leading_options": table}
            else:
                options: Any = {"options": table, "open_cruxes": crux_view} if crux_view else table
                body = {"options": options, "critiques_of_you": [], "evidence": evidence}
                critiques = self._fit_critiques(critiques, self._paste_room(name, seat, body))
                body["critiques_of_you"] = critiques
            refs = allowed_refs(view) + [c["id"] for c in critiques]
            schema = ballot_schema(list(opt_ids), [c.id for c in open_cruxes], refs)
            self._queue_seat(name, seat, body, schema)
        if not seats:
            self._finish_ballot()

    def _on_ballot(self, seat: int, result: CallResult, spec: CallSpec) -> None:
        ballot = self._parse(Ballot, result)
        if ballot is not None and ballot.choice in self._round_opts:
            ids = self._option_ids()
            ranking: list[str] = []
            for opt in ballot.ranking:
                if opt in ids and opt not in ranking:
                    ranking.append(opt)
            ballot = ballot.model_copy(update={"ranking": ranking or [ballot.choice]})
            self._round_ballots[seat] = ballot
            self._emit(
                E.BALLOT_CAST, seat_no=seat, round=self._ri, ballot=_dump(ballot),
                model_id=self._seats[seat].model_id, call_id=spec.call_id,
                changed=self._positions.get(seat) != ballot.choice,
            )
        elif result.error == "timeout":
            self._carry.append(seat)  # 10.10: keeps its last valid position
        if not self._waiting_on(self._phase):
            self._finish_ballot()

    def _finish_ballot(self) -> None:
        ballots: dict[int, Optional[Ballot]] = {}
        failed: list[int] = []
        for seat in sorted(self._seats):
            ballot = self._round_ballots.get(seat)
            if ballot is None:
                failed.append(seat)
                if seat in self._carry:
                    ballot = self._position_ballot(seat)
            ballots[seat] = ballot
        valid = {s: b for s, b in ballots.items() if b is not None}
        self._cur_ballots = valid
        self._last_ballots.update(valid)
        self._positions.update({s: b.choice for s, b in valid.items()})
        self._sync_holders()
        self._vote_cruxes(valid)
        self._rounds_run += 1

        nxt = self._next_round()
        res = consensus.evaluate(
            ballots, self._k, self._cfg,
            rounds_remain=nxt is not None,
            time_remains=nxt is not None and self._can_start(nxt),
            weights=self._weights,
        )
        why = self._extension_reason(res) if nxt is None else None
        if why is not None:
            # One more r3, begun exactly like a planned one: it joins the round list and the
            # same ballots now evaluate to "continue".
            self._rounds.append("r3")
            self._extra_used += 1
            res = consensus.evaluate(ballots, self._k, self._cfg, True, True, self._weights)
        self._emit(
            E.ROUND_COMPLETED, round=self._ri, options=[_dump(o) for o in self._options],
            tally=res.tally, agreement=res.share, leading_option_id=res.top,
            valid_turns=len(self._round_ballots), failed_seats=failed,
            converged=res.status == "consensus",
        )
        self._prev_agreement, self._prev_tally = res.share, dict(res.tally)
        if why is not None:
            self._emit(
                E.ROUND_EXTENDED, round=self._ri + 1, agreement=res.share,
                extra_used=self._extra_used, extra_max=self.max_extra_rounds, reason=why,
            )
        self._apply_result(res)

    def _extension_reason(self, res: consensus.ConsensusResult) -> Optional[str]:
        """Why one more re-ballot is worth it, or None when the fallback must run now.

        Called when a ballot round ended and no planned round is left.
        """
        if res.status == "consensus" or self._extra_used >= self.max_extra_rounds:
            return None
        if res.valid < res.quorum or res.blocked or res.top is None:
            return None  # the Chair is already forced: more talk does not lift a veto
        if res.share < self.extend_min_agreement - 1e-9:
            return None
        prev = self._prev_agreement
        first = prev is None
        rose = prev is not None and res.share > prev + 1e-9
        if not first and not rose and dict(res.tally) == (self._prev_tally or {}):
            return None  # two ballot rounds in a row, same tally: arguing is pointless
        if first:
            reason = "first ballot round fell short"
        elif rose:
            reason = f"agreement rose from {prev:.2f} to {res.share:.2f}"
        elif self._open_cruxes():
            reason = f"{len(self._open_cruxes())} open crux(es) left"
        else:
            return None
        if not self._can_start("r3"):
            return None
        return reason

    def _vote_cruxes(self, valid: dict[int, Ballot]) -> None:
        quorum = consensus.quorum_for(self._k, self._cfg)
        for crux in self._open_cruxes():
            stances = [
                v.stance for b in valid.values() for v in b.crux_votes
                if v.crux_id == crux.id and v.stance != "abstain"
            ]
            if len(stances) < max(1, quorum):
                continue
            best = max(stances.count("agree"), stances.count("disagree"))
            if best / len(stances) >= self._cfg.threshold - 1e-9:
                crux.resolved = True
                crux.resolved_by = "vote"

    # ----------------------------------------------------------------------------------
    # Decisions
    # ----------------------------------------------------------------------------------

    def _rank_key(self, seat: int, ballot: Ballot):
        return (-ballot.confidence, -self._seats[seat].q if seat in self._seats else 0.0, seat)

    def _best_text(self, option_id: Optional[str]) -> tuple[str, Optional[str], float]:
        """(final text, answer key, mean confidence) for an option, from the current ballots."""
        option = self._option(option_id)
        group = sorted(
            ((s, b) for s, b in self._cur_ballots.items() if b.choice == option_id),
            key=lambda sb: self._rank_key(*sb),
        )
        text, key = "", option.answer_key if option else None
        for seat, ballot in group:
            draft = self._drafts.get(seat)
            own = self._r0_pos.get(seat) == option_id
            candidate = ballot.final_answer or (draft.answer if draft and own else "")
            if candidate and not text:
                text = candidate
                key = key or ballot.answer_key or (draft.answer_key if draft and own else None)
        if not text and option is not None:
            text = option.summary
        confidence = sum(b.confidence for _, b in group) / len(group) if group else 0.0
        return text, key, confidence

    def _minority(self, chosen: Optional[str]) -> list[MinorityPosition]:
        report: list[MinorityPosition] = []
        for option in self._options:
            seats = sorted(s for s, b in self._cur_ballots.items() if b.choice == option.id)
            if option.id == chosen or not seats:
                continue
            lead = sorted(seats, key=lambda s: self._rank_key(s, self._cur_ballots[s]))[0]
            ballot, draft = self._cur_ballots[lead], self._drafts.get(lead)
            argument = ballot.blocking_objection or ""
            if not argument and draft is not None:
                argument = draft.claims[0].text if draft.claims else draft.summary
            argument = argument or ballot.final_answer
            report.append(
                MinorityPosition(
                    seats=seats, position=option.summary, strongest_argument=argument[:600],
                    option_id=option.id,
                )
            )
        return report

    def _decision_base(self, outcome: str, option_id: Optional[str]) -> Decision:
        valid = len(self._cur_ballots)
        tally: dict[str, int] = {}
        for seat in sorted(self._cur_ballots):
            choice = self._cur_ballots[seat].choice
            tally[choice] = tally.get(choice, 0) + 1
        return Decision(
            outcome=outcome,
            option_id=option_id,
            agreement=tally.get(option_id, 0) / valid if valid and option_id else 0.0,
            tally=tally,
            rounds_run=self._rounds_run,
            minority_report=self._minority(option_id),
            open_cruxes=[c.model_copy() for c in self._open_cruxes()],
        )

    def _vote_decision(self, outcome: str, option_id: Optional[str]) -> Decision:
        decision = self._decision_base(outcome, option_id)
        decision.final_text, decision.answer_key, decision.confidence = self._best_text(option_id)
        return decision

    def _finalize(self, decision: Decision) -> None:
        decision.rounds_run = self._rounds_run
        for note in self._notes:
            if note not in decision.notes:
                decision.notes.append(note)
        self._decision = decision
        self._pending = None
        self._phase = "done"
        self._waiting = {}
        self._outbox = []
        self._check_outbox = []
        self._emit(
            E.DECISION_FINAL, decision=_dump(decision), options=[_dump(o) for o in self._options], ms=0.0
        )

    # ----------------------------------------------------------------------------------
    # Chair
    # ----------------------------------------------------------------------------------

    def _chair_order(self) -> list[str]:
        """Who chairs, in order: the named chair, then seats by q (10.11). Keys: seat_no text or "x"."""
        order: list[str] = []
        named = self.lineup.chair_model_id
        if named:
            match = [n for n, s in sorted(self._seats.items()) if s.model_id == named]
            order.append(str(match[0]) if match else EXTERNAL_CHAIR)
        for n, s in sorted(self._seats.items()):
            if s.is_chair and str(n) not in order:
                order.append(str(n))
        for n, s in sorted(self._seats.items(), key=lambda ns: (-ns[1].q, ns[0])):
            if str(n) not in order:
                order.append(str(n))
        return order

    def _start_chair(self, reason: str, kind: str, top: list[str]) -> None:
        self._phase = "chair"
        self._chair = {"reason": reason, "kind": kind, "top": list(top), "tried": [], "who": None}
        self._next_chair()

    def _next_chair(self) -> None:
        chair = self._chair
        tried = chair["tried"]
        left = [w for w in self._chair_order() if w not in tried]
        if not left or len(tried) >= MAX_CHAIR_TRIES or (tried and self._remaining <= 0):
            self._chair_exhausted()
            return
        self._send_chair(left[0])

    def _send_chair(self, who: str, extra: Optional[dict] = None) -> None:
        chair = self._chair
        chair["tried"].append(who)
        chair["who"] = who
        if who == EXTERNAL_CHAIR:
            seat = SeatAssignment(seat_no=-1, model_id=self.lineup.chair_model_id or "", is_chair=True)
        else:
            seat = self._seats[int(who)]
        transcript = self._transcript(chair["kind"], chair["top"])
        transcript.update(extra or {})
        spec = build_chair_call(
            self.run_id, seat, self.task, self.brief, self.record, CHAIR_LENS,
            {"transcript": transcript}, chair_schema(chair["top"]), self.mode,
            dict(budget.TURN_CAPS["chair"]), self.seed,
        )
        spec = self._queue(spec, "chair", None)
        self._emit(
            E.CHAIR_STARTED, call_id=spec.call_id, model_id=seat.model_id,
            seat_no=None if who == EXTERNAL_CHAIR else seat.seat_no, reason=chair["reason"],
        )

    def _transcript(self, kind: str, top: list[str]) -> dict[str, Any]:
        labels = label_to_seat(list(self._drafts), -1, self.seed)  # one labelling for the Chair
        by_seat = {seat: lab for lab, seat in labels.items()}
        members = set(self._drafts)
        if kind == "merge":
            members = {s for s in members if self._positions.get(s) in top}
        drafts = []
        for lab, seat in labels.items():
            if seat in members:
                drafts.append(
                    {"label": lab, "option": self._positions.get(seat), **compress_for_seat(self._drafts[seat])}
                )
        critiques = []
        for reviewer, critique in sorted(self._critiques.items()):
            theirs = label_to_seat(list(self._drafts), reviewer, self.seed)
            for review in critique.reviews:
                target = by_seat.get(theirs.get(review.target))
                if target is None:
                    continue
                critiques.append(
                    {
                        "about": target,
                        "strongest_point": review.strongest_point,
                        "flaws": [{"text": f.text, "severity": f.severity, "kind": f.kind} for f in review.flaws],
                    }
                )
        positions = [
            {
                "option": b.choice, "final_answer": b.final_answer[:600],
                "blocking_objection": b.blocking_objection,
            }
            for _, b in sorted(self._cur_ballots.items())
            if kind != "merge" or b.choice in top
        ]
        out: dict[str, Any] = {
            "leading_options": [
                {"id": o.id, "summary": o.summary, "answer_key": o.answer_key}
                for o in self._options if o.id in top
            ],
            "other_options": [
                {"id": o.id, "summary": o.summary} for o in self._options if o.id not in top
            ],
            "drafts": drafts,
            "critiques": critiques,
            "open_cruxes": self._crux_view(self._open_cruxes()),
            "evidence": self._evidence_view(),
            "positions": positions,
        }
        if kind == "merge":
            out["instruction"] = (
                "The council already agrees on the leading option. Merge these drafts into one final text."
            )
        return out

    def _on_chair(self, result: CallResult) -> None:
        chair = self._chair
        data = self._data(result)
        text = data.get("final_text") if isinstance(data, dict) else None
        if not isinstance(text, str) or not text.strip():
            text = result.content if result.ok and not isinstance(data, dict) else ""
        if not text.strip():
            if chair["kind"] == "revise":
                self._finalize(self._pending)  # the first version stands
            else:
                self._next_chair()
            return
        data = data if isinstance(data, dict) else {}
        kind = chair["kind"]
        if kind == "revise":
            self._pending.final_text = text
            self._finalize(self._pending)
            return
        if kind == "merge":
            self._pending.final_text = text
            self._start_ratify()
            return

        top = chair["top"]
        option_id = data.get("option_id") if data.get("option_id") in top else (top[0] if top else None)
        option = self._option(option_id)
        key = data.get("answer_key") if isinstance(data.get("answer_key"), str) else None
        if key and self.answer_type in CLOSED_TYPES:
            try:
                key = self._normalize(key, self.answer_type)
            except Exception:
                pass
        decision = self._decision_base("chair", option_id)
        decision.final_text = text
        decision.answer_key = key or (option.answer_key if option else None)
        decision.confidence = _clip01(data.get("confidence"))
        if self.plan_mode:
            value = next((c for c in self._open_cruxes() if c.kind == "value"), None)
            if value is not None or decision.confidence < USER_CONFIDENCE_FLOOR:
                asked = data.get("user_question")
                question = asked if isinstance(asked, str) and asked.strip() else None
                question = question or (value.statement if value else "Which of these should the council go with?")
                decision.outcome = "user"
                decision.needs_user = UserQuestion(
                    question=question,
                    options=[o.summary for o in self._options if o.id in top],
                    request_id=f"{self.run_id}:user",
                    crux_id=value.id if value else None,
                    context=text[:600],
                )
                self._finalize(decision)
                return
            self._pending = decision
            self._start_ratify()
            return
        self._finalize(decision)

    def _chair_exhausted(self) -> None:
        kind = self._chair["kind"]
        if kind in ("merge", "revise"):
            self._finalize(self._pending)  # the best agreeing draft, or the first Chair version
            return
        top = self._chair["top"]
        self._finalize(self._vote_decision("deadlock", top[0] if top else None))

    # ----------------------------------------------------------------------------------
    # Ratification (plan mode)
    # ----------------------------------------------------------------------------------

    def _start_ratify(self) -> None:
        seats = sorted(self._drafts)
        if not seats:
            self._finalize(self._pending)
            return
        self._phase = "ratify"
        self._ratify = {seat: None for seat in seats}
        body = {"task": self.task, "final_text": self._pending.final_text}
        for seat_no in seats:
            seat = self._seats[seat_no]
            spec = build_ratify_call(
                self.run_id, seat, self.task, self.brief, self.record, self._lens_text(seat),
                body, RATIFY_SCHEMA, self.mode, dict(budget.TURN_CAPS["ratify"]), self.seed,
            )
            self._queue(spec, "ratify", seat_no)

    def _on_ratify(self, seat: int, result: CallResult) -> None:
        data = self._data(result)
        if isinstance(data, dict) and isinstance(data.get("approve"), bool):
            reason = data.get("reason") if isinstance(data.get("reason"), str) else ""
            self._ratify[seat] = [data["approve"], reason]
        if not self._waiting_on("ratify"):
            self._finish_ratify()

    def _finish_ratify(self) -> None:
        votes = {seat: v for seat, v in sorted(self._ratify.items()) if v is not None}
        yes = [s for s, v in votes.items() if v[0]]
        no = [s for s, v in votes.items() if not v[0]]
        ratified = (len(yes) / len(votes) if votes else 1.0) >= RATIFY_THRESHOLD - 1e-9
        objections = [votes[s][1] for s in no if votes[s][1]]
        self._emit(
            E.RATIFY_RESULT, ratified=ratified, votes_for=len(yes), votes_against=len(no),
            votes={str(s): v[0] for s, v in votes.items()}, objections=objections,
            option_id=self._pending.option_id,
        )
        if ratified:
            self._finalize(self._pending)
            return
        self._pending.minority_report.append(
            MinorityPosition(
                seats=no, position="rejected the final text at ratification",
                strongest_argument=" | ".join(objections)[:600], option_id=None,
            )
        )
        who = self._chair["who"] if self._chair else None
        if self._remaining <= 0 or who is None:
            self._finalize(self._pending)
            return
        self._phase = "chair"
        self._chair["kind"] = "revise"
        self._chair["reason"] = "ratification failed: revise once using the objections"
        self._send_chair(
            who,
            {
                "previous_final_text": self._pending.final_text,
                "objections": objections,
                "instruction": "Revise the previous final text once so that it answers the objections.",
            },
        )

    # ----------------------------------------------------------------------------------
    # Snapshot / restore
    # ----------------------------------------------------------------------------------

    def snapshot(self) -> dict:
        def by_seat(d: dict) -> dict:
            return {str(k): _dump(v) for k, v in d.items()}

        snap = {
            "v": 1,
            "args": {
                "run_id": self.run_id,
                "task": self.task,
                "profile": _dump(self.profile),
                "lineup": _dump(self.lineup),
                "mode": _dump(self.mode),
                "record": self.record,
                "brief": self.brief,
                "lens_texts": dict(self.lens_texts),
                "seat_tps": {str(k): v for k, v in self.seat_tps.items()},
                "clerk_model_id": self.clerk_model_id,
                "answer_type": self.answer_type,
                "cfg": dataclasses.asdict(self._cfg),
                "seed": self.seed,
                "plan_mode": self.plan_mode,
                "seat_notes": {str(k): v for k, v in self.seat_notes.items()},
                "max_extra_rounds": self.max_extra_rounds,
                "extend_min_agreement": self.extend_min_agreement,
                "ctx_tokens": self.ctx_tokens,
            },
            "state": {
                "seats": [_dump(s) for _, s in sorted(self._seats.items())],
                "alternates": list(self._alternates),
                "substituted": sorted(self._substituted),
                "phase": self._phase,
                "ri": self._ri,
                "rounds_run": self._rounds_run,
                "remaining": self._remaining,
                "deadline_hit": self._deadline_hit,
                "crux_done": self._crux_done,
                "notes": list(self._notes),
                "stated_conf": sorted(self._stated_conf),
                "drafts": by_seat(self._drafts),
                "r0_pos": {str(k): v for k, v in self._r0_pos.items()},
                "positions": {str(k): v for k, v in self._positions.items()},
                "options": [_dump(o) for o in self._options],
                "cruxes": [_dump(c) for c in self._cruxes],
                "critiques": by_seat(self._critiques),
                "last_ballots": by_seat(self._last_ballots),
                "cur_ballots": by_seat(self._cur_ballots),
                "round_ballots": by_seat(self._round_ballots),
                "carry": list(self._carry),
                "round_opts": list(self._round_opts),
                "failed": list(self._failed),
                "checks": [dict(c) for c in self._checks],
                "evidence": [_dump(e) for e in self._evidence],
                "claim_scores": [_dump(c) for c in self._claim_scores],
                "lie_flags": [_dump(f) for f in self._lie_flags],
                "waiting": [
                    {"kind": i["kind"], "seat": i["seat"], "spec": _dump(i["spec"])}
                    for i in self._waiting.values()
                ],
                "used": sorted(self._used),
                "chair": None if self._chair is None else dict(self._chair),
                "ratify": {str(k): v for k, v in self._ratify.items()},
                "pending": _dump(self._pending),
                "decision": _dump(self._decision),
                "tally": dict(self._tally),
                "agreement": self._agreement,
                "valid_n": self._valid_n,
                "top": self._top,
                "extra_used": self._extra_used,
                "prev_agreement": self._prev_agreement,
                "prev_tally": None if self._prev_tally is None else dict(self._prev_tally),
                "events": [[t, p] for t, p in self._events],
            },
        }
        return json.loads(json.dumps(snap))  # a deep copy that is proven JSON-serializable

    @classmethod
    def restore(
        cls, snapshot: dict, normalize: Callable[[str, str], str] | None = None
    ) -> "Deliberation":
        a, s = snapshot["args"], snapshot["state"]
        self = cls.__new__(cls)
        self._setup(
            a["run_id"], a["task"], TaskProfile.model_validate(a["profile"]),
            LineupRecord.model_validate(a["lineup"]), ModeConfig.model_validate(a["mode"]),
            a["record"], a["brief"], a["lens_texts"], a["seat_tps"], a["clerk_model_id"],
            a["answer_type"], normalize, ConsensusConfig(**a["cfg"]), a["seed"], a["plan_mode"],
            a.get("seat_notes"),
            max_extra_rounds=a.get("max_extra_rounds", 0),
            extend_min_agreement=a.get("extend_min_agreement", 0.5),
            ctx_tokens=a.get("ctx_tokens", DEFAULT_CTX_TOKENS),
        )

        def by_seat(d: dict, model) -> dict:
            return {int(k): model.model_validate(v) for k, v in d.items()}

        self._seats = {x["seat_no"]: SeatAssignment.model_validate(x) for x in s["seats"]}
        self._alternates = list(s["alternates"])
        self._substituted = set(s["substituted"])
        self._phase = s["phase"]
        self._ri = s["ri"]
        self._rounds_run = s["rounds_run"]
        self._remaining = s["remaining"]
        self._deadline_hit = s["deadline_hit"]
        self._crux_done = s["crux_done"]
        self._notes = list(s.get("notes", []))
        self._drafts = by_seat(s["drafts"], Draft)
        # An older snapshot has no record of it: take every draft's confidence as stated.
        self._stated_conf = {int(x) for x in s.get("stated_conf", list(self._drafts))}
        self._r0_pos = {int(k): v for k, v in s["r0_pos"].items()}
        self._positions = {int(k): v for k, v in s["positions"].items()}
        self._options = [Option.model_validate(o) for o in s["options"]]
        self._cruxes = [Crux.model_validate(c) for c in s["cruxes"]]
        self._critiques = by_seat(s["critiques"], Critique)
        self._last_ballots = by_seat(s["last_ballots"], Ballot)
        self._cur_ballots = by_seat(s["cur_ballots"], Ballot)
        self._round_ballots = by_seat(s["round_ballots"], Ballot)
        self._carry = list(s["carry"])
        self._round_opts = list(s["round_opts"])
        self._failed = list(s["failed"])
        self._checks = [dict(c) for c in s["checks"]]
        self._evidence = [EvidenceResult.model_validate(e) for e in s["evidence"]]
        self._claim_scores = [ClaimScore.model_validate(c) for c in s.get("claim_scores", [])]
        self._lie_flags = [LieFlag.model_validate(f) for f in s.get("lie_flags", [])]
        self._used = set(s["used"])
        self._chair = None if s["chair"] is None else dict(s["chair"])
        self._ratify = {int(k): v for k, v in s["ratify"].items()}
        self._pending = None if s["pending"] is None else Decision.model_validate(s["pending"])
        self._decision = None if s["decision"] is None else Decision.model_validate(s["decision"])
        self._tally = dict(s["tally"])
        self._agreement = s["agreement"]
        self._valid_n = s["valid_n"]
        self._top = s["top"]
        self._extra_used = int(s.get("extra_used", 0))
        self._rounds = self._rounds + ["r3"] * self._extra_used  # the rounds that were added
        self._prev_agreement = s.get("prev_agreement")
        prev_tally = s.get("prev_tally")
        self._prev_tally = None if prev_tally is None else dict(prev_tally)
        self._events = [(t, p) for t, p in s["events"]]
        # Calls and checks that were out are handed out again: the old in-flight ones are gone.
        self._waiting = {}
        self._outbox = []
        for item in s["waiting"]:
            spec = CallSpec.model_validate(item["spec"])
            self._waiting[spec.call_id] = {"kind": item["kind"], "seat": item["seat"], "spec": spec}
            self._outbox.append(spec)
        self._check_outbox = [c["check_id"] for c in self._checks if not c["done"]]
        return self


__all__ = [
    "Deliberation",
    "PendingCheck",
    "CRUX_SCHEMA",
    "RATIFY_SCHEMA",
    "chair_schema",
    "MAX_CHECKS_PER_ROUND",
    "SCORES_HEADING",
    "DEFAULT_CTX_TOKENS",
    "CHAIR_FLOOR_S",
    "LATE_CHAIR_NOTE",
]
