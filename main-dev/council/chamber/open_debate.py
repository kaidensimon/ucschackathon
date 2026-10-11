"""The open council debate: free text for all, by name, plus a short card per message.

PURE: no I/O, no clock (time comes in through set_remaining / on_deadline), no randomness
beyond the injected seed. Same driving interface as council.chamber.deliberation.Deliberation,
so LiveExecutor runs either one.

Driving loop
    d = OpenDebate(...)
    events = d.take_events()
    while not d.is_done():
        for spec in d.pending_calls():       # each call is returned once
            ... run it, then: events = d.on_result(result)
        ... between rounds: d.set_lie_metrics({turn_id: LieMetric})
        ... when the run deadline passes: events = d.on_deadline(remaining)
    decision = d.decision()

Protocol
- A turn is two calls: the message (free text, streamed, kind "msg") and then the card (JSON,
  kind "card"), which is given the member's own message.
- Round 0: every seat writes its opening position at the same time, blind. When all messages
  and cards are in, the positions are published and put on the table.
- Rounds 1..n: every seat reads the whole transcript up to the previous round, the table and
  what was addressed to it. All seats of a round write at the same time.
- Votes come from the card field "backs". The engine never moves a seat that named an answer.
  Only after round 0 (no table existed, every card says "new") one small call (clerk.merge, on
  the first seat's model) says which opening stances are the same answer. It can only join
  whole answers; it cannot split seats that gave the same stance or move a seat elsewhere.
  Every seat confirms or leaves its group itself in round 1.
- After every round the table is tallied. agree >= ceil(threshold * seats) ends the debate
  with "consensus". Rounds used up, the deadline, or no time for another round: one seat,
  random.Random(f"{seed}:decider").choice over the seats sorted by seat_no, casts the deciding
  vote from the transcript. Outcome "chair" (the literal used for the Chair fallback).

Phases (property `phase`): r0 -> merge -> r1 -> r2 ... -> write | chair -> done

The final answer
- Consensus (also the round-0 early exit): consensus.reached is emitted, then ONE more call
  (purpose "seat.final", streamed, plain text, template open_writer) goes to the writer: the
  backer of the winning answer with the highest stated confidence (ties: lowest seat number).
  It is announced as a message of kind "answer" (msg.started / msg.ended, no card, not kept in
  the transcript). Its text is Decision.final_text; decision.final follows it. Phase "write".
- The writer call fails, times out, comes back empty, or the deadline has passed (also
  on_deadline() while it is out): final_text = the winning answer's statement, a blank line,
  the best backer's last message. The decision is never lost.
- write_final=False (the benchmark): no writer call, final_text = the best backer's last message.
- The decider's final_answer shorter than MIN_FINAL_ANSWER_CHARS, or equal to its objection
  (seen on the box: "No objection raised."), is replaced the same way (free-form tasks only).

Choices made here
- Reply rounds n = len(mode.rounds) - 1 + max_extra_rounds, or `max_rounds` when given.
- turn_id of a message = call_id of its message call: "<run_id>:open:<round>:s<seat_no>".
  Card call: "<run_id>:card:<round>:s<seat_no>". Neither parses as "<round>:<seat_no>", and
  meta carries "seat" (not "seat_no"), so the gateway does not announce these calls as seat
  turns of its own: the msg.* events are the only turns of this protocol.
- Purposes: "seat.r0" (positions), "seat.r1".."seat.r3" (replies, capped at r3), "seat.card",
  "clerk.merge", "chair" (the decider).
- Seats counted = seats not dropped. A seat whose message fails keeps its last card; two
  failed turns in a row drop it. A failed card call is not a failed turn: the engine makes a
  fallback card that keeps the seat on the answer it backed before.
- Fewer cards on the table than the quorum (consensus.quorum_for): no consensus, the decider
  decides. No card at all: deadlock.
- Round 0 early exit also needs the mean stated confidence of the agreeing seats to reach
  cfg.early_exit_min_confidence while another round is still possible (fallback cards are left
  out of the mean). With no round left, the agreement alone is a consensus.
- table.tally "reached" is true only when the debate ends on that tally. Round-0 agreement
  that still goes to round 1 is posted with reached false and "unconfirmed" true.
- A message's `to` is set from its card (the member's own word on whom it addressed).
- A card that says "new" gets the id of the answer it was put on once the round is counted
  (also in the transcript), so later readers see "backs A3", not "backs new".
- Decision.agreement = backers of the chosen answer / seats counted.
- Benchmark tasks (answer_type "mcq", "numeric" or "exact", the ones graded by key): the card
  has one more field, "answer_key". The table groups seats by normalize(answer_key, answer_type)
  and the statement of an answer IS that key; "backs" is then set by the engine and there is no
  clerk.merge call. A card with no usable key: the last "ANSWER: x" line of the member's
  message, else the answer id the card backs, else where the seat sat, else the seat is not on
  the table. Decision.answer_key = the winning key; when the decider decides, the key in its
  JSON (else its "ANSWER:" line, else the key of the answer it backs). Free-form tasks:
  nothing of this applies and answer_key stays None.
- seed_position(seat_no, text) supplies a seat's round-0 message without a model call (the
  bench reuses the model's solo answer). Call it before pending_calls(); only the card call is
  then made for that seat.
- Round 0 only: a seat whose opening message call fails (not by timeout or cancel) is given
  the next model of lineup.alternates once. seat.assigned (replaces_model_id) and msg.ended
  (error) for the failed turn are emitted, then msg.started for a new turn.
- Streaming: msg.started carries "call_id", the gateway call id of the message call. The
  engine does not emit msg.delta: the gateway streams the text as "turn.delta" with that
  call_id, and a consumer maps call_id -> turn_id from msg.started (today they are equal).
- on_deadline(): open message calls are dropped, open card calls get a fallback card, what
  came in is counted, then consensus or the decider. A decider call that is out is not
  cancelled: it ends by its own timeout.
- Outliers (question_outliers=True, the default): after every tally, the seats that back an
  answer held by at most max(1, seats // 3) seats while another answer is held by more than
  half of the seats are the outliers (at most 2; none on a consensus or an even split).
  "outlier.named" {round, seats, leading, their_answers} is emitted and the next round uses the
  templates open_question (every other member puts one question to the outlier, by name) and
  open_examined (the outlier answers every question put to it). No extra phase, no extra call.
  While an outlier exists and the tally changed in the last round, the debate gets up to
  QUESTION_EXTRA_ROUNDS rounds beyond the planned ones. "outlier.resolved" {seat, outcome,
  round}: "moved" (the seat joined the leading answer), "vindicated" (its answer is now backed
  by at least as many seats as any other), "held" (still apart when the debate ends; its
  position is in Decision.minority_report). With no outlier nothing changes.
  The two outlier events are not in core/event_types.py and the pipeline's event bus refuses
  unknown types, so they are kept in outlier_events() (the whole history, in order) and go out
  through take_events() only once the contract knows them. Every closed case is also a line
  in Decision.notes.
- Not used by this protocol, kept for the shared interface: pending_checks() and evidence()
  and cruxes() return [], drafts() returns {}, set_claim_scores() and set_lie_flags() do
  nothing, plan_mode / clerk_model_id are stored only.
"""

from __future__ import annotations

import dataclasses
import json
import random
import re
from typing import Any, Callable, Optional

from council.chamber import budget, compact, consensus
from council.chamber import messages as M
from council.chamber import protocol_prompts as P
from council.chamber.consensus import ConsensusConfig
from council.core import event_types as E
from council.core.schemas import (
    Ballot,
    CallResult,
    CallSpec,
    Decision,
    LineupRecord,
    MinorityPosition,
    ModeConfig,
    Option,
    SeatAssignment,
    TaskProfile,
)

POSITION_TOKENS = 450
ALWAYS_THINK_TOKENS = 1200  # room for models that think whatever they are told
REPLY_TOKENS = 400
CARD_TOKENS = 160
# Thinking room for the JSON calls. Models that cannot switch thinking off (gpt-oss under
# llama.cpp) spent the whole card budget thinking and returned an empty card on the box.
CARD_THINK_TOKENS = 600
WRITER_TOKENS = 500
WRITER_THINK_TOKENS = 1200
MIN_FINAL_ANSWER_CHARS = 25
MERGE_TOKENS = 200
DECIDER_TOKENS = 700
REPLY_TEMPERATURE = 0.4
DECIDER_TEMPERATURE = 0.2
DECIDER_FLOOR_S = 60.0
MAX_DECIDER_TRIES = 3
MAX_FAILS_IN_A_ROW = 2
DEFAULT_CTX_TOKENS = 16384
ADDRESSED_CLIP = 400
QUESTION_EXTRA_ROUNDS = 2  # rounds beyond the planned ones while an outlier is questioned
MAX_OUTLIERS = 2
OUTLIER_NAMED = "outlier.named"
OUTLIER_RESOLVED = "outlier.resolved"
QUESTIONED_MARK = " (being questioned)"
NO_QUESTIONS = (
    "(no member has put a question to you by name yet: answer the strongest objection to your "
    "answer in the debate above)"
)
LATE_DECIDER_NOTE = (
    "the run deadline had passed when the deciding vote was asked for; it was given its minimum time anyway"
)

MSG_STARTED = E.MSG_STARTED
MSG_ENDED = E.MSG_ENDED
MSG_CARD = E.MSG_CARD
MSG_LIE = E.MSG_LIE
TABLE_TALLY = E.TABLE_TALLY

MERGE_SYSTEM = """You are the clerk of a council of AI models. You do not judge who is right.
You only say which answers are the same answer.

TASK
{task}"""

MERGE_USER = """These are the opening answers of the council members to the TASK, one per line, with the seat id:
{stances}

Which of these are the same answer, meaning the same result for the user? Different wording,
detail or reasoning does not matter. A different result does. When in doubt, keep them apart.
Return groups of seat ids. Every seat id is in exactly one group. An answer that matches no
other is a group of one.

Reply with the JSON object only, like {{"groups": [["s0", "s2"], ["s1"]]}}"""


def merge_schema(seat_ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "groups": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "string", "enum": list(seat_ids)}},
            }
        },
        "required": ["groups"],
    }


def decider_schema(answer_ids: list[str], answer_type: str | None = None) -> dict[str, Any]:
    backs: dict[str, Any] = {"type": "string"}
    if answer_ids:
        backs = {"type": "string", "enum": list(answer_ids)}
    schema = _decider_schema(backs)
    if answer_type in M.KEYED_TYPES:
        schema["properties"]["answer_key"] = {"type": "string", "minLength": 1, "maxLength": M.KEY_MAX}
        schema["required"].append("answer_key")
    return schema


def _decider_schema(backs: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "backs": backs,
            "final_answer": {"type": "string", "minLength": 1},
            "objection": {"type": "string"},
        },
        "required": ["backs", "final_answer", "objection"],
    }


def seat_id(seat_no: int) -> str:
    return f"s{int(seat_no)}"


def _seat_no(sid: str) -> int:
    return int(str(sid).lstrip("s"))


def _name_from_model(model_id: str, seat_no: int) -> str:
    words = [w for w in re.split(r"[\s\-_:/]+", str(model_id or "").strip()) if w]
    word = words[0] if words else f"Seat{seat_no}"
    return word[:1].upper() + word[1:]


def _dump(obj: Any) -> Any:
    return None if obj is None else obj.model_dump(mode="json")


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


_GARBAGE_CARD = re.compile(r"\s*text to restate", re.IGNORECASE)
_BACKS_IN_TEXT = re.compile(r"\bback(?:s|ing)?\s+\**\s*(A\d+)\b", re.IGNORECASE)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_WORD = re.compile(r"[a-z0-9]+")


def _same_result(a: str, b: str) -> bool:
    """True when two answer statements name the same numbers and share most of their words."""
    na, nb = sorted(_NUMBER.findall(a or "")), sorted(_NUMBER.findall(b or ""))
    if not na or na != nb:
        return False
    wa, wb = set(_WORD.findall((a or "").lower())), set(_WORD.findall((b or "").lower()))
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= 0.5


class OpenDebate:
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
        seat_names: dict[int, str] | None = None,
        max_rounds: int | None = None,
        write_final: bool = True,
        question_outliers: bool = True,
    ) -> None:
        self._setup(
            run_id, task, profile, lineup, mode, record, brief, lens_texts, seat_tps,
            clerk_model_id, answer_type, normalize, cfg, seed, plan_mode, seat_notes,
            max_extra_rounds=max_extra_rounds, extend_min_agreement=extend_min_agreement,
            ctx_tokens=ctx_tokens, seat_names=seat_names, max_rounds=max_rounds,
            write_final=write_final, question_outliers=question_outliers,
        )
        self._start_round(0)

    # ----------------------------------------------------------------------------------
    # Setup
    # ----------------------------------------------------------------------------------

    def _setup(
        self, run_id, task, profile, lineup, mode, record, brief, lens_texts, seat_tps,
        clerk_model_id, answer_type, normalize, cfg, seed, plan_mode, seat_notes=None,
        *, max_extra_rounds: int = 0, extend_min_agreement: float = 0.5,
        ctx_tokens: int = DEFAULT_CTX_TOKENS, seat_names=None, max_rounds=None,
        write_final: bool = True, question_outliers: bool = True,
    ) -> None:
        self.write_final = bool(write_final)
        self.question_outliers = bool(question_outliers)
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
        self.clerk_model_id = clerk_model_id
        self.answer_type = answer_type
        self._keyed = answer_type in M.KEYED_TYPES  # benchmark task: seats are grouped by key
        self._alternates: list[str] = list(lineup.alternates)
        self._substituted: set[int] = set()
        self.seed = int(seed)
        self.plan_mode = bool(plan_mode)
        self._normalize = normalize
        self._cfg = cfg or ConsensusConfig()
        self.max_extra_rounds = max(0, int(max_extra_rounds or 0))
        self.extend_min_agreement = float(extend_min_agreement)
        self.ctx_tokens = int(ctx_tokens or DEFAULT_CTX_TOKENS)
        self.max_rounds = None if max_rounds is None else max(0, int(max_rounds))

        self._seats: dict[int, SeatAssignment] = {s.seat_no: s.model_copy() for s in lineup.seats}
        self._k = len(self._seats) or lineup.k or mode.k
        if self.max_rounds is not None:
            self._n_rounds = self.max_rounds
        else:
            self._n_rounds = max(0, len(list(mode.rounds) or ["r0"]) - 1) + self.max_extra_rounds

        given = {int(k): str(v).strip() for k, v in (seat_names or {}).items() if str(v or "").strip()}
        self.seat_names = given
        names = {n: given.get(n) or _name_from_model(s.model_id, n) for n, s in sorted(self._seats.items())}
        folded = [v.casefold() for v in names.values()]
        self._names = {
            n: (f"{v}-s{n}" if folded.count(v.casefold()) > 1 else v) for n, v in names.items()
        }

        order = sorted(self._seats)
        rng = random.Random(f"{self.seed}:decider")
        self._decider_order: list[int] = []
        if order:
            first = rng.choice(order)
            rest = [s for s in order if s != first]
            rng.shuffle(rest)
            self._decider_order = [first] + rest

        self._phase = "r0"
        self._round = 0
        self._rounds_run = 0
        self._remaining = float(mode.deadline_s)
        self._deadline_hit = False
        self._notes: list[str] = []

        self._messages: list[M.CouncilMessage] = []
        self._answers: list[M.TableAnswer] = []
        self._cards: dict[int, M.Card] = {}  # each seat's last card, `backs` = where it sits
        self._round_cards: dict[int, M.Card] = {}  # cards of the round that is running
        self._fallbacks: set[int] = set()  # seats whose last card was made by the engine
        self._fails: dict[int, int] = {}  # failed turns in a row
        self._dropped: set[int] = set()
        self._round_failed: list[int] = []
        self._voided: list[int] = []
        self._r0_pos: dict[int, str] = {}

        self._outbox: list[CallSpec] = []
        self._waiting: dict[str, dict[str, Any]] = {}  # call_id -> {kind, seat, round, spec, ...}
        self._used: set[str] = set()

        self._decider: Optional[dict[str, Any]] = None
        self._writer: Optional[dict[str, Any]] = None  # {answer_id, seat, turn_id} while writing
        self._decision: Optional[Decision] = None
        self._last_tally: dict[str, Any] = {}
        self._events: list[tuple[str, dict]] = []
        self._outliers: list[int] = []  # the seats questioned in the round that runs or comes next
        self._questioned: dict[int, str] = {}  # named seat, not resolved yet -> the answer it backed
        self._q_extra = 0  # extra rounds given for the questioning
        self._outlier_log: list[tuple[str, dict]] = []  # every outlier.* event, in order

    # ----------------------------------------------------------------------------------
    # Public API (same shape as Deliberation)
    # ----------------------------------------------------------------------------------

    @property
    def phase(self) -> str:
        return self._phase

    def is_done(self) -> bool:
        return self._phase == "done"

    def decision(self) -> Decision:
        if self._decision is None:
            raise RuntimeError("debate is not done")
        return self._decision

    def set_remaining(self, seconds: float) -> None:
        self._remaining = max(0.0, float(seconds))

    def chair_reserve_s(self) -> float:
        """Seconds of the deadline kept back for the deciding vote. 0 once it is asked for."""
        if self._phase in ("chair", "write", "done"):
            return 0.0
        who = self.decider_seat()
        want = budget.turn_timeout_s("chair", self._tps_of(who), "off", 1, None, tokens=DECIDER_TOKENS)
        return max(0.0, min(want, budget.CHAIR_RESERVE_SHARE * max(0.0, float(self.mode.deadline_s))))

    def decider_seat(self) -> Optional[int]:
        """The seat that casts the deciding vote if the council does not agree."""
        left = [s for s in self._decider_order if s not in self._dropped]
        return left[0] if left else None

    def pending_calls(self) -> list[CallSpec]:
        out, self._outbox = self._outbox, []
        return out

    def pending_checks(self) -> list:
        return []

    def on_evidence(self, check_id: str = "", result: Any = None) -> list[tuple[str, dict]]:
        return self.take_events()

    def take_events(self) -> list[tuple[str, dict]]:
        out, self._events = self._events, []
        return out

    def set_claim_scores(self, scores: Any = None) -> None:
        """Not used by the open protocol (the lie metric is per message: set_lie_metrics)."""

    def set_lie_flags(self, flags: Any = None) -> None:
        """Not used by the open protocol (the lie metric is per message: set_lie_metrics)."""

    def set_lie_metrics(self, metrics: dict[str, Any]) -> None:
        """Attach lie-detector readings {turn_id: LieMetric or dict} to messages.

        They show in the transcript of the next round: reply calls and the deciding-vote call
        still waiting in pending_calls() are rebuilt, calls already handed out are not.
        Emits msg.lie.
        """
        for turn_id, metric in (metrics or {}).items():
            msg = self._msg(str(turn_id))
            if msg is None or metric is None:
                continue
            try:
                lie = metric if isinstance(metric, M.LieMetric) else M.LieMetric.model_validate(metric)
            except Exception:
                continue
            msg.lie = lie
            self._emit(
                MSG_LIE, turn_id=msg.turn_id, seat_no=msg.seat_no, score=lie.score, level=lie.level,
                reasons=list(lie.reasons),
            )
        for i, spec in enumerate(self._outbox):
            info = self._waiting.get(spec.call_id)
            if info is None:
                continue
            if info["kind"] == "msg" and info["round"] > 0:
                fresh = self._msg_messages(info["seat"], info["round"])
            elif info["kind"] == "decider":
                fresh = self._decider_messages(info["seat"])
            else:
                continue
            spec = spec.model_copy(update={"messages": fresh})
            self._outbox[i] = spec
            info["spec"] = spec

    def seed_position(self, seat_no: int, text: str) -> bool:
        """Give a seat its round-0 message without a model call (the bench's solo answer).

        Call it before pending_calls(): the seat's message call is taken back and only its card
        call is made. False (nothing done) when the text is empty or the seat has no open
        round-0 message call. The events wait in take_events().
        """
        text = str(text or "").strip()
        info = next(
            (i for i in self._waiting.values()
             if i["kind"] == "msg" and i["round"] == 0 and i["seat"] == int(seat_no)), None)
        if not text or info is None or self._phase != "r0":
            return False
        spec = info["spec"]
        del self._waiting[spec.call_id]
        self._outbox = [s for s in self._outbox if s.call_id != spec.call_id]
        self._on_msg(info, CallResult(call_id=spec.call_id, ok=True, model_id=spec.model_id, content=text))
        return True

    def messages(self) -> list[M.CouncilMessage]:
        return [m.model_copy(deep=True) for m in self._messages]

    def answers(self) -> list[M.TableAnswer]:
        """The answers on the table that a seat backs."""
        return [a.model_copy(deep=True) for a in self._answers if a.seat_ids]

    def chat_view(self) -> list[dict]:
        return M.chat_view(self._messages)

    def table_view(self) -> dict[str, dict]:
        return M.table_view(self._messages, [seat_id(n) for n in sorted(self._seats)])

    def outliers(self) -> list[int]:
        """The seats far from the rest of the council after the last tally (at most 2)."""
        return list(self._outliers)

    def outlier_events(self) -> list[tuple[str, dict]]:
        """Every "outlier.named" / "outlier.resolved" event so far, in order."""
        return [(t, json.loads(json.dumps(p))) for t, p in self._outlier_log]

    def tally(self) -> dict[str, Any]:
        """The last table.tally payload ({} before round 0 is counted)."""
        return json.loads(json.dumps(self._last_tally))

    def options(self) -> list[Option]:
        return [
            Option(id=a.id, summary=a.statement, holders=sorted(_seat_no(s) for s in a.seat_ids))
            for a in self._answers
            if a.seat_ids
        ]

    def r0_options(self) -> dict[int, Optional[str]]:
        return {seat: self._r0_pos.get(seat) for seat in sorted(self._seats)}

    def final_ballots(self) -> dict[int, Optional[Ballot]]:
        """Each seat's last position as a ballot. None: the seat has no card on the table."""
        out: dict[int, Optional[Ballot]] = {}
        for seat in sorted(self._seats):
            where, card = self._where(seat), self._cards.get(seat)
            if where is None or card is None:
                out[seat] = None
                continue
            because = [card.changed_because] if card.changed and card.changed_because else []
            out[seat] = Ballot(
                choice=where, ranking=[where], final_answer=self._last_text(seat) or card.stance,
                confidence=card.confidence, changed_because=because,
            )
        return out

    def drafts(self) -> dict:
        return {}

    def cruxes(self) -> list:
        return []

    def evidence(self) -> list:
        return []

    def on_result(self, result: CallResult) -> list[tuple[str, dict]]:
        info = self._waiting.pop(result.call_id, None)
        if info is None or self.is_done():
            return self.take_events()
        kind = info["kind"]
        if kind == "msg":
            self._on_msg(info, result)
        elif kind == "card":
            self._on_card(info, result)
        elif kind == "merge":
            self._on_merge(result)
        elif kind == "decider":
            self._on_decider(info, result)
        elif kind == "writer":
            self._on_writer(info, result)
        return self.take_events()

    def on_deadline(self, remaining_s: Optional[float] = None) -> list[tuple[str, dict]]:
        """The debate must stop now. `remaining_s` is the time really left (the decider's reserve)."""
        if self.is_done():
            return self.take_events()
        self._deadline_hit = True
        self._remaining = 0.0 if remaining_s is None else max(0.0, float(remaining_s))
        if self._phase == "chair":
            return self.take_events()  # the decider call that is out ends by its own timeout
        if self._phase == "write":  # the vote stands: the answer is put together without the writer
            self._end_writer("", "cancelled")
            return self.take_events()
        if self._phase == "merge":
            self._void()
            self._close_round()
            return self.take_events()
        for info in list(self._waiting.values()):
            seat, msg = info["seat"], self._msg(info.get("turn_id", ""))
            if info["kind"] == "msg":
                self._voided.append(seat)
                if msg is not None:
                    msg.thinking, msg.done = False, True
                self._emit(MSG_ENDED, turn_id=info["turn_id"], seat_no=seat, text="", error="cancelled")
            elif info["kind"] == "card" and msg is not None:
                self._take_card(seat, msg, None)
        self._void()
        self._finish_round()
        return self.take_events()

    # ----------------------------------------------------------------------------------
    # Small helpers
    # ----------------------------------------------------------------------------------

    def _emit(self, type_: str, **fields: Any) -> None:
        if type_ in (OUTLIER_NAMED, OUTLIER_RESOLVED):
            self._outlier_log.append((type_, json.loads(json.dumps(fields))))
            if type_ not in E.PAYLOADS:  # the bus refuses a type the contract does not know
                return
        if type_ in E.PAYLOADS:
            self._events.append((type_, E.make_payload(type_, **fields)))
        else:  # the open-protocol events: plain payloads
            self._events.append((type_, json.loads(json.dumps(fields))))

    def _active(self) -> list[int]:
        return [s for s in sorted(self._seats) if s not in self._dropped]

    def _tps_of(self, seat: Optional[int]) -> Optional[float]:
        return None if seat is None else self.seat_tps.get(seat)

    def _debate_left(self) -> float:
        return self._remaining - self.chair_reserve_s()

    def _msg(self, turn_id: str) -> Optional[M.CouncilMessage]:
        return next((m for m in self._messages if m.turn_id == turn_id), None)

    def _last_text(self, seat: int) -> str:
        for m in reversed(self._messages):
            if m.seat_no == seat and m.text.strip():
                return m.text.strip()
        return ""

    def _where(self, seat: int) -> Optional[str]:
        sid = seat_id(seat)
        return next((a.id for a in self._answers if sid in a.seat_ids), None)

    def _backed_ids(self) -> list[str]:
        return [a.id for a in self._answers if a.seat_ids]

    def _reason_tokens(self, rnd: int) -> int:
        if self.mode.reasoning == "off":
            return 0
        return int(budget.TURN_CAPS["r0" if rnd == 0 else "r1"]["max_reasoning"])

    def _norm(self, raw: Any) -> str:
        """A raw answer as the grader's key. "" when there is none."""
        raw = str(raw or "").strip()
        if not raw:
            return ""
        if self._normalize is None:
            return " ".join(raw.lower().split())
        try:
            return str(self._normalize(raw, self.answer_type or "") or "").strip()
        except Exception:
            return ""

    def _key_of(self, answer_key: Any, text: str) -> str:
        """The key a member gave: its answer_key, else the last "ANSWER: x" line of its text."""
        return self._norm(answer_key) or self._norm(M.last_answer_line(text))

    def _queue(self, spec: CallSpec, kind: str, seat: Optional[int], tokens: int, **extra: Any) -> CallSpec:
        base = cid = spec.call_id
        n = 2
        while cid in self._used:
            cid = f"{base}#{n}"
            n += 1
        self._used.add(cid)
        if kind == "decider":
            if self._remaining <= 0:
                if LATE_DECIDER_NOTE not in self._notes:
                    self._notes.append(LATE_DECIDER_NOTE)
                timeout = DECIDER_FLOOR_S
            else:
                timeout = max(DECIDER_FLOOR_S, budget.turn_timeout_s(
                    "chair", self._tps_of(seat), "off", 1, self._remaining, tokens=tokens))
        else:
            together = 1 if kind in ("merge", "writer") else max(1, len(self._active()))
            timeout = budget.turn_timeout_s(
                "r1", self._tps_of(seat), "off", together, self._debate_left(), tokens=tokens)
        spec = spec.model_copy(update={"call_id": cid, "timeout_s": timeout})
        self._waiting[cid] = {"kind": kind, "seat": seat, "round": self._round, "spec": spec, **extra}
        self._outbox.append(spec)
        return spec

    def _void(self) -> None:
        self._waiting = {}
        self._outbox = []

    def _waiting_on(self, *kinds: str) -> bool:
        return any(i["kind"] in kinds for i in self._waiting.values())

    def _can_start(self) -> bool:
        """Does one more reply round (message + card) fit in the time left for debate?"""
        left = self._debate_left()
        if self._deadline_hit or left <= 0:
            return False
        seats = self._active()
        tps = [self.seat_tps[s] for s in seats if self.seat_tps.get(s, 0) > 0]
        if not tps:
            return True
        tokens = REPLY_TOKENS + CARD_TOKENS + self._reason_tokens(self._round + 1)
        share = max(1.0, len(seats) * 0.5)
        return tokens / (min(tps) / share) <= left

    # ----------------------------------------------------------------------------------
    # Prompts
    # ----------------------------------------------------------------------------------

    def _system(self, seat_no: int) -> str:
        seat = self._seats[seat_no]
        text = P.render(
            "open_system",
            name=self._names[seat_no],
            members=P.members_line([self._names[n] for n in self._active()], self._names[seat_no]),
            lens_text=self.lens_texts.get(seat.lens or "", ""),
            task=self.task,
            workspace_brief=self.brief,
            council_record=self.record,
        )
        notes = self.seat_notes.get(seat_no, "")
        return f"{text}\n\nNOTES FOR YOU\n{notes}" if notes else text

    def _table_text(self, viewer: Optional[int]) -> str:
        n = len(self._active())
        lines = []
        for a in self._answers:
            if not a.seat_ids:
                continue
            who = ", ".join(
                self._names[_seat_no(s)] + (" (you)" if viewer is not None and _seat_no(s) == viewer else "")
                + (QUESTIONED_MARK if _seat_no(s) in self._outliers else "")
                for s in a.seat_ids
            )
            lines.append(f"{a.id}: {a.statement} - backed by {who} ({len(a.seat_ids)} of {n})")
        return "\n".join(lines) or "(no answers on the table yet)"

    def _addressed_text(self, seat_no: int, rnd: int) -> str:
        before = [m for m in self._messages if m.round < rnd]
        asked = M.addressed_to(before, seat_id(seat_no), max(0, rnd - 1))
        lines = [f"- {m.name} (round {m.round}): {M.clip(m.text, ADDRESSED_CLIP)}" for m in asked]
        return "\n".join(lines) or "(none)"

    def _answer_label(self, answer_id: Optional[str]) -> str:
        answer = next((a for a in self._answers if a.id == answer_id), None)
        if answer is None:
            return str(answer_id or "no answer")
        return f"{answer.id} ({M.clip(answer.statement, 120)})"

    def _outlier_lines(self) -> str:
        leading = self._answer_label(self._last_tally.get("leading") or None)
        return "\n".join(
            f"{self._names[s]} is far from the rest of the council: it backs "
            f"{self._answer_label(self._where(s))} while most back {leading}."
            for s in self._outliers
        )

    def _questions_text(self, seat_no: int, rnd: int) -> str:
        """What was addressed to the seat since its last message, with the asker's name."""
        before = [m for m in self._messages if m.round < rnd]
        last = max((m.round for m in before if m.seat_no == seat_no and m.text.strip()), default=0)
        asked = M.questions_to(before, seat_id(seat_no), last)
        lines = [f"- {m.name} (round {m.round}): {M.clip(m.text, ADDRESSED_CLIP)}" for m in asked]
        return "\n".join(lines) or NO_QUESTIONS

    def _find_outliers(self, tally: dict[str, Any]) -> list[int]:
        """Seats on an answer of at most max(1, n // 3) seats while another has more than half."""
        groups, n = tally["groups"], tally["seats"]
        if not self.question_outliers or not groups or 2 * len(groups[0]["seat_ids"]) <= n:
            return []
        small = max(1, n // 3)
        far = sorted(
            (len(g["seat_ids"]), _seat_no(s))
            for g in groups[1:] if len(g["seat_ids"]) <= small for s in g["seat_ids"]
        )
        return sorted(seat for _, seat in far[:MAX_OUTLIERS])

    def _judge_outliers(self, tally: dict[str, Any], rnd: int, outliers: list[int]) -> None:
        """Close the cases of named seats that are back with the council, then name the new ones."""
        counts = {g["answer_id"]: len(g["seat_ids"]) for g in tally["groups"]}
        top = max(counts.values(), default=0)
        for seat in sorted(self._questioned):
            was, now = self._questioned[seat], self._where(seat)
            if seat in self._dropped or now is None:
                del self._questioned[seat]
                continue
            if now == was and counts.get(now, 0) >= top:
                outcome = "vindicated"
            elif now != was and now == tally["leading"]:
                outcome = "moved"
            else:
                continue
            del self._questioned[seat]
            self._emit(OUTLIER_RESOLVED, seat=seat, outcome=outcome, round=rnd)
        self._outliers = list(outliers)
        if outliers:
            theirs = {str(s): self._where(s) for s in outliers}
            self._questioned.update({s: theirs[str(s)] for s in outliers})
            self._emit(
                OUTLIER_NAMED, round=rnd, seats=list(outliers), leading=tally["leading"],
                their_answers=theirs,
            )

    @staticmethod
    def _seating(groups: Any) -> dict[str, list[str]]:
        return {g["answer_id"]: sorted(g["seat_ids"]) for g in groups or []}

    def _time_note(self, rnd: int) -> str:
        return P.time_note(self._debate_left(), rnd, max(0, self._n_rounds - rnd))

    def _msg_messages(self, seat_no: int, rnd: int) -> list[dict[str, Any]]:
        system = self._system(seat_no)
        if rnd == 0:
            user = P.render("open_position", time_note=self._time_note(0))
            return [{"role": "system", "content": system}, {"role": "user", "content": user}]
        template = "open_final" if rnd >= 2 and rnd >= self._n_rounds else "open_reply"
        fixed = dict(
            table=self._table_text(seat_no), addressed_to_you=self._addressed_text(seat_no, rnd),
            time_note=self._time_note(rnd),
        )
        if seat_no in self._outliers:  # the council is questioning this seat
            template = "open_examined"
            fixed = dict(
                table=fixed["table"], time_note=fixed["time_note"],
                questions=self._questions_text(seat_no, rnd),
            )
        elif self._outliers:
            template = "open_question"
            names = [self._names[s] for s in self._outliers]
            fixed.update(
                outlier_lines=self._outlier_lines(),
                outlier_names=" and ".join(names) + (" (one question each)" if len(names) > 1 else ""),
            )
        room = compact.budget_chars(
            self.ctx_tokens, REPLY_TOKENS + self._reason_tokens(rnd),
            len(system) + len(P.render(template, transcript="", **fixed)),
        )
        before = [m for m in self._messages if m.round < rnd]
        user = P.render(template, transcript=M.transcript_text(before, seat_id(seat_no), room), **fixed)
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    # ----------------------------------------------------------------------------------
    # Rounds
    # ----------------------------------------------------------------------------------

    def _start_round(self, rnd: int) -> None:
        self._round = rnd
        self._phase = f"r{rnd}"
        self._round_cards = {}
        self._round_failed = []
        self._voided = []
        seats = self._active()
        purpose = f"seat.r{min(rnd, 3)}"
        self._emit(E.ROUND_STARTED, round=rnd, purpose=purpose, seats=seats, deadline_s=self._remaining)
        for seat_no in seats:
            self._queue_msg(seat_no, rnd)
        if not seats:
            self._finish_round()

    def _queue_msg(self, seat_no: int, rnd: int) -> None:
        """Queue one seat's message call and announce the turn (msg.started with its call_id)."""
        purpose = f"seat.r{min(rnd, 3)}"
        reason = self._reason_tokens(rnd)
        out = POSITION_TOKENS if rnd == 0 else REPLY_TOKENS
        kind = "position" if rnd == 0 else "reply"
        seat = self._seats[seat_no]
        turn_id = f"{self.run_id}:open:{rnd}:{seat_id(seat_no)}"
        spec = CallSpec(
            model_id=seat.model_id, call_id=turn_id, run_id=self.run_id, purpose=purpose,
            messages=self._msg_messages(seat_no, rnd), json_schema=None,
            # The message is itself the member's reasoning, so thinking is asked off. Models that
            # cannot switch it off (DeepSeek R1) still get a thinking allowance, or they would
            # spend the whole reply thinking and say nothing (seen on the box with Gemma).
            reasoning="off", max_output_tokens=out,
            max_reasoning_tokens=max(int(reason or 0), ALWAYS_THINK_TOKENS),
            temperature=None if rnd == 0 else REPLY_TEMPERATURE, seed=self.seed,
            priority="interactive", stream=True,
            meta={"seat": seat_no, "round_no": rnd, "kind": "msg", "lens": seat.lens},
        )
        spec = self._queue(spec, "msg", seat_no, out + reason)
        turn_id = spec.call_id
        self._waiting[turn_id]["turn_id"] = turn_id
        spec.meta["turn_id"] = turn_id
        self._messages.append(M.CouncilMessage(
            turn_id=turn_id, seat_id=seat_id(seat_no), seat_no=seat_no, name=self._names[seat_no],
            round=rnd, kind=kind, to=M.ALL, thinking=True, done=False,
        ))
        self._emit(
            MSG_STARTED, turn_id=turn_id, call_id=turn_id, seat_no=seat_no, model_id=seat.model_id,
            name=self._names[seat_no], round=rnd, kind=kind, to=M.ALL,
        )

    def _swap_model(self, seat: int, msg: M.CouncilMessage, result: CallResult) -> bool:
        """Round 0: a seat whose opening call failed gets the next lineup alternate, once."""
        if (msg.round != 0 or seat in self._substituted or not self._alternates
                or self._deadline_hit or result.error in ("timeout", "cancelled")):
            return False
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
        self._emit(
            MSG_ENDED, turn_id=msg.turn_id, seat_no=seat, text="",
            error=result.error or "invalid_output",
        )
        self._messages.remove(msg)
        self._queue_msg(seat, 0)
        return True

    def _on_msg(self, info: dict, result: CallResult) -> None:
        seat, msg = info["seat"], self._msg(info["turn_id"])
        text = (result.content or "").strip() if result.ok else ""
        if msg is None:
            return
        msg.thinking = False
        if not text and self._swap_model(seat, msg, result):
            return
        if not text:
            msg.done = True
            self._round_failed.append(seat)
            self._emit(
                MSG_ENDED, turn_id=msg.turn_id, seat_no=seat, text="",
                error=result.error or "invalid_output",
            )
        else:
            msg.text = text
            self._emit(MSG_ENDED, turn_id=msg.turn_id, seat_no=seat, text=text, error=None)
            self._queue_card(seat, msg)
        self._maybe_finish_round()

    def _queue_card(self, seat_no: int, msg: M.CouncilMessage) -> None:
        rnd = msg.round
        seat = self._seats[seat_no]
        others = [seat_id(n) for n in self._active() if n != seat_no]
        ids = self._backed_ids() if rnd > 0 else []
        members = "\n".join(
            f"{seat_id(n)} {self._names[n]}" + (" (you)" if n == seat_no else "") for n in self._active()
        )
        table = self._table_text(seat_no) if rnd > 0 else "(empty: these are the opening positions)"
        a_type = self.answer_type if self._keyed else None
        user = P.render(
            "open_card", message=msg.text, members=members, table=table,
            answer_key_rule=P.answer_key_rule(a_type),
        )
        spec = CallSpec(
            model_id=seat.model_id, call_id=f"{self.run_id}:card:{rnd}:{seat_id(seat_no)}",
            run_id=self.run_id, purpose="seat.card",
            messages=[{"role": "system", "content": self._system(seat_no)}, {"role": "user", "content": user}],
            json_schema=M.card_schema(others, ids, a_type), reasoning="off", max_output_tokens=CARD_TOKENS,
            max_reasoning_tokens=CARD_THINK_TOKENS, temperature=0.0, seed=self.seed,
            priority="interactive", stream=False,
            meta={"seat": seat_no, "round_no": rnd, "kind": "card", "turn_id": msg.turn_id},
        )
        self._queue(
            spec, "card", seat_no, CARD_TOKENS + CARD_THINK_TOKENS,
            turn_id=msg.turn_id, others=others, ids=ids,
        )

    def _on_card(self, info: dict, result: CallResult) -> None:
        msg = self._msg(info["turn_id"])
        if msg is None:
            return
        data = (result.parsed if result.parsed is not None else result.content) if result.ok else None
        card = M.parse_card(data, list(info["others"]), list(info["ids"])) if data is not None else None
        if card is not None and _GARBAGE_CARD.match(card.note or ""):
            # Seen on the box (gpt-oss under llama.cpp): the model returned nothing, the repair step
            # asked it to restate an empty text, and it echoed the repair prompt. Not a card.
            card = None
        self._take_card(info["seat"], msg, card, list(info["ids"]))
        self._maybe_finish_round()

    def _take_card(self, seat: int, msg: M.CouncilMessage, card: Optional[M.Card],
                   ids: Optional[list[str]] = None) -> None:
        """Store the card of a message. None: the card call failed, the engine makes one."""
        fallback = card is None
        if card is None:
            card = M.fallback_card(msg.text)
            prev, where = self._cards.get(seat), self._where(seat)
            if prev is not None and where is not None:
                # A broken card call must not move the seat off the answer it backs.
                card = card.model_copy(
                    update={"backs": where, "stance": prev.stance, "confidence": prev.confidence}
                )
            # The member's own words win over where it sat: "I back A5" in the message moves it.
            said = _BACKS_IN_TEXT.search(msg.text or "")
            if said and ids and said.group(1).upper() in ids:
                named = next((x for x in self._answers if x.id == said.group(1).upper()), None)
                card = card.model_copy(update={
                    "backs": said.group(1).upper(),
                    "stance": named.statement if named is not None else card.stance,
                })
        (self._fallbacks.add if fallback else self._fallbacks.discard)(seat)
        self._round_cards[seat] = card
        msg.card, msg.thinking, msg.done = card, False, True
        msg.to = list(card.to) if isinstance(card.to, list) and card.to else M.ALL
        self._emit(MSG_CARD, turn_id=msg.turn_id, seat_no=seat, card=_dump(card), fallback=fallback)

    def _maybe_finish_round(self) -> None:
        if not self._waiting_on("msg", "card"):
            self._finish_round()

    def _apply(self, answers: list[M.TableAnswer], sid: str, card: M.Card) -> list[M.TableAnswer]:
        """messages.apply_card, but an answer that loses its last seat stays in the list.

        Cards of one round name the ids of the table as it stood when the round began, and
        an id is never given to a second answer.
        """
        out = M.apply_card(answers, sid, card)
        by_id = {a.id: a for a in out}
        kept = [
            by_id.get(a.id) or a.model_copy(update={"seat_ids": [s for s in a.seat_ids if s != sid]})
            for a in answers
        ]
        old = {a.id for a in answers}
        return kept + [a for a in out if a.id not in old]

    def _apply_keyed(self, seat: int, card: M.Card) -> M.Card:
        """Benchmark task: put the seat on the answer whose statement is its normalized key.

        No usable key: the answer id the card backs, else where the seat sat, else the seat is
        not on the table. Returns the card with `backs` and `answer_key` set to that answer.
        """
        sid = seat_id(seat)
        msg = next(
            (m for m in reversed(self._messages) if m.seat_no == seat and m.round == self._round), None)
        key = self._key_of(card.answer_key, msg.text if msg is not None else "")
        if key:
            target = next((a for a in self._answers if a.statement == key), None)
            if target is None:
                target = M.TableAnswer(id=M._next_id(self._answers), statement=key, proposed_by=sid)
                self._answers.append(target)
        else:
            target = next((a for a in self._answers if a.id == card.backs), None) or next(
                (a for a in self._answers if sid in a.seat_ids), None)
        if target is None:
            return card
        for a in self._answers:
            a.seat_ids = [s for s in a.seat_ids if s != sid]
        target.seat_ids.append(sid)
        card = card.model_copy(update={"backs": target.id, "answer_key": target.statement})
        if msg is not None and msg.card is not None:
            msg.card = card
        return card

    def _finish_round(self) -> None:
        rnd = self._round
        for seat in self._active():
            if seat in self._round_cards:
                self._fails[seat] = 0
            elif seat in self._round_failed:
                self._fails[seat] = self._fails.get(seat, 0) + 1
                if self._fails[seat] >= MAX_FAILS_IN_A_ROW:
                    self._dropped.add(seat)
        for seat in sorted(self._round_cards):
            if seat in self._dropped:
                continue
            card = self._round_cards[seat]
            if self._keyed:
                card = self._apply_keyed(seat, card)
            else:
                self._answers = self._apply(self._answers, seat_id(seat), card)
            self._cards[seat] = card
        gone = {seat_id(s) for s in self._dropped}
        for a in self._answers:
            a.seat_ids = [s for s in a.seat_ids if s not in gone]
        self._rounds_run = rnd + 1
        if not self._keyed:
            self._merge_similar()
        merge = rnd == 0 and not self._keyed and len(self._backed_ids()) > 1
        if merge and not self._deadline_hit and self._debate_left() > 0:
            self._start_merge()
        else:
            self._close_round()

    # ----------------------------------------------------------------------------------
    # Round 0 merge
    # ----------------------------------------------------------------------------------

    def _start_merge(self) -> None:
        self._phase = "merge"
        seats = [s for s in self._active() if self._where(s) is not None]
        clerk = self._seats[seats[0]]
        stances = "\n".join(f"{seat_id(s)}: {self._cards[s].stance}" for s in seats)
        spec = CallSpec(
            model_id=clerk.model_id, call_id=f"{self.run_id}:clerk.merge", run_id=self.run_id,
            purpose="clerk.merge",
            messages=[
                {"role": "system", "content": MERGE_SYSTEM.format(task=self.task)},
                {"role": "user", "content": MERGE_USER.format(stances=stances)},
            ],
            json_schema=merge_schema([seat_id(s) for s in seats]), reasoning="off",
            max_output_tokens=MERGE_TOKENS, max_reasoning_tokens=0, temperature=0.0, seed=self.seed,
            priority="interactive", stream=False, meta={"kind": "merge", "round_no": 0},
        )
        self._queue(spec, "merge", seats[0], MERGE_TOKENS)

    def _on_merge(self, result: CallResult) -> None:
        data = _data(result)
        groups = data.get("groups") if isinstance(data, dict) else data
        if isinstance(groups, list):
            self._merge(groups)
        self._close_round()

    def _merge_similar(self) -> None:
        """Join answers that are plainly the same result in other words, with no model call.

        Seen on the box: "Each brother has 3 sisters, and the snail reaches the top on day 8." and
        "Each brother has 3 sisters; the snail reaches the top on day 8." stayed two answers, so the
        tally showed 3-2-1 when the council was split 3-3. Two answers are joined only when they
        name exactly the same numbers and share most of their words.
        """
        held = [a for a in self._answers if a.seat_ids]
        groups: list[list[str]] = []
        used: set[str] = set()
        for i, a in enumerate(held):
            if a.id in used:
                continue
            group = list(a.seat_ids)
            for b in held[i + 1:]:
                if b.id not in used and _same_result(a.statement, b.statement):
                    used.add(b.id)
                    group += list(b.seat_ids)
            if len(group) > len(a.seat_ids):
                groups.append(group)
        if groups:
            self._merge(groups)

    def _merge(self, groups: list) -> None:
        """Join whole answers the clerk calls the same. A seat is read once; nothing is split."""
        by_seat = {sid: a.id for a in self._answers for sid in a.seat_ids}
        root = {a.id: a.id for a in self._answers}
        order = [a.id for a in self._answers]

        def find(x: str) -> str:
            while root[x] != x:
                x = root[x]
            return x

        seen: set[str] = set()
        for group in groups:
            if not isinstance(group, (list, tuple)):
                continue
            ids: list[str] = []
            for item in group:
                sid = str(item).strip().lower()
                sid = sid if sid.startswith("s") else f"s{sid}"
                if sid in seen or sid not in by_seat:
                    continue
                seen.add(sid)
                ids.append(by_seat[sid])
            for other in ids[1:]:
                a, b = find(ids[0]), find(other)
                if a != b:
                    low, high = sorted((a, b), key=order.index)
                    root[high] = low
        merged: list[M.TableAnswer] = []
        for a in self._answers:
            if find(a.id) != a.id:
                continue
            seats = [s for b in self._answers if find(b.id) == a.id for s in b.seat_ids]
            merged.append(a.model_copy(update={"seat_ids": sorted(seats, key=_seat_no)}))
        self._answers = merged

    # ----------------------------------------------------------------------------------
    # Tally and what comes next
    # ----------------------------------------------------------------------------------

    def _count(self) -> dict[str, Any]:
        seats = self._active()
        cards = {seat_id(s): self._cards[s] for s in seats if s in self._cards and self._where(s)}
        out = M.tally(self._answers, cards, len(seats), self._cfg.threshold)
        out["valid"] = sum(len(g["seat_ids"]) for g in out["groups"])
        out["quorum"] = consensus.quorum_for(self._k, self._cfg)
        if out["valid"] < out["quorum"]:
            out["reached"] = False
        return out

    def _confident(self, tally: dict[str, Any]) -> bool:
        """Round 0 early exit: the agreeing seats must also say they are sure."""
        backers = [_seat_no(s) for g in tally["groups"][:1] for s in g["seat_ids"]]
        stated = [self._cards[s].confidence for s in backers if s not in self._fallbacks]
        if not stated or 2 * len(stated) < len(backers):
            return False
        return sum(stated) / len(stated) >= self._cfg.early_exit_min_confidence - 1e-9

    def _close_round(self) -> None:
        rnd = self._round
        for a in self._answers:  # a card that said "new" now carries the id it was given
            for sid in a.seat_ids:
                seat = _seat_no(sid)
                card = self._cards.get(seat)
                if card is None or card.backs == a.id:
                    continue
                card = card.model_copy(update={"backs": a.id})
                self._cards[seat] = card
                for m in self._messages:
                    if m.seat_no == seat and m.round == rnd and m.card is not None:
                        m.card = m.card.model_copy(update={"backs": a.id})
        if rnd == 0:
            self._r0_pos = {s: w for s in sorted(self._seats) if (w := self._where(s)) is not None}

        tally = self._count()
        n = tally["seats"]
        share = tally["agree"] / n if n else 0.0
        counts = {g["answer_id"]: len(g["seat_ids"]) for g in tally["groups"]}
        leading = tally["leading"] or None
        more = rnd < self._n_rounds and self._can_start()
        reached = bool(tally["reached"]) and (rnd > 0 or not more or self._confident(tally))
        outliers = [] if reached else self._find_outliers(tally)
        if (outliers and not more and rnd >= self._n_rounds and rnd > 0
                and self._q_extra < QUESTION_EXTRA_ROUNDS
                and self._seating(self._last_tally.get("groups")) != self._seating(tally["groups"])
                and self._can_start()):
            # Someone moved while an outlier is questioned: one more round of questions.
            self._n_rounds += 1
            self._q_extra += 1
            more = True
        # The posted tally says "reached" only when the debate ends on it: the UI stops its
        # clock for good on a reached tally. Round-0 agreement that is still to be tested is
        # posted as not reached ("unconfirmed": true).
        self._last_tally = {
            "round": rnd, **tally, "reached": reached,
            "unconfirmed": bool(tally["reached"]) and not reached, "basis": "round-vote",
        }
        self._emit(TABLE_TALLY, **self._last_tally)
        self._emit(
            E.ROUND_COMPLETED, round=rnd, options=[_dump(o) for o in self.options()], tally=counts,
            agreement=share, leading_option_id=leading, valid_turns=len(self._round_cards),
            failed_seats=sorted(set(self._round_failed) | set(self._voided)), converged=reached,
        )
        if self.question_outliers:
            self._judge_outliers(tally, rnd, outliers)
        common = dict(round=rnd, agreement=share, threshold=self._cfg.threshold, tally=counts)
        if reached:
            self._emit(
                E.CONSENSUS_REACHED, option_id=leading, outcome="consensus", early=rnd == 0, **common
            )
            self._start_writer(leading)
            return
        if tally["valid"] < tally["quorum"]:
            reason = f"{tally['valid']} seats on the table, quorum is {tally['quorum']}"
        elif tally["reached"]:
            reason = "agreement in round 0 without enough stated confidence"
        else:
            reason = f"{tally['agree']} of {n} agree, {tally['needed']} needed"
        failed = dict(leading_option_id=leading, reason=reason, **common)
        if tally["valid"] == 0:
            self._emit(E.CONSENSUS_FAILED, next_step="deadlock", **failed)
            self._finalize(Decision(outcome="deadlock", rounds_run=self._rounds_run))
        elif more and tally["valid"] >= tally["quorum"]:
            self._emit(E.CONSENSUS_FAILED, next_step="round", **failed)
            self._start_round(rnd + 1)
        else:
            self._emit(E.CONSENSUS_FAILED, next_step="chair", **failed)
            self._start_decider(reason)

    # ----------------------------------------------------------------------------------
    # Decisions
    # ----------------------------------------------------------------------------------

    def _backers(self, answer_id: Optional[str]) -> list[int]:
        """Seats on the answer, most confident first (then by q, then by seat_no)."""
        answer = next((a for a in self._answers if a.id == answer_id), None)
        seats = [_seat_no(s) for s in answer.seat_ids] if answer is not None else []
        return sorted(
            seats,
            key=lambda s: (-(self._cards[s].confidence if s in self._cards else 0.0), -self._seats[s].q, s),
        )

    def _best_text(self, answer_id: Optional[str]) -> tuple[str, float]:
        backers = self._backers(answer_id)
        text = next((t for t in (self._last_text(s) for s in backers) if t), "")
        if not text:
            answer = next((a for a in self._answers if a.id == answer_id), None)
            text = answer.statement if answer is not None else ""
        conf = [self._cards[s].confidence for s in backers if s in self._cards]
        return text, (sum(conf) / len(conf) if conf else 0.0)

    def _fallback_text(self, answer_id: Optional[str]) -> str:
        """The answer's statement, a blank line, the best backer's last message."""
        answer = next((a for a in self._answers if a.id == answer_id), None)
        statement = answer.statement.strip() if answer is not None else ""
        best = self._best_text(answer_id)[0].strip()
        if not statement or not best or best == statement:
            return best or statement
        return f"{statement}\n\n{best}"

    # ----------------------------------------------------------------------------------
    # The final answer after a consensus
    # ----------------------------------------------------------------------------------

    def _writer_seat(self, answer_id: Optional[str]) -> Optional[int]:
        """The backer with the highest stated confidence; ties go to the lowest seat number."""
        answer = next((a for a in self._answers if a.id == answer_id), None)
        seats = [_seat_no(s) for s in answer.seat_ids] if answer is not None else []
        seats = [s for s in seats if s in self._seats and s not in self._dropped]
        if not seats:
            return None
        return min(seats, key=lambda s: (-(self._cards[s].confidence if s in self._cards else 0.0), s))

    def _finish_consensus(self, answer_id: Optional[str], text: str = "") -> None:
        decision = self._base_decision("consensus", answer_id)
        best, decision.confidence = self._best_text(answer_id)
        if not self.write_final:
            decision.final_text = best
        else:
            decision.final_text = text.strip() or self._fallback_text(answer_id)
        self._writer = None
        self._finalize(decision)

    def _start_writer(self, answer_id: Optional[str]) -> None:
        """The vote is in: one backer writes the answer the user reads."""
        seat_no = self._writer_seat(answer_id)
        answer = next((a for a in self._answers if a.id == answer_id), None)
        if (not self.write_final or seat_no is None or answer is None
                or self._deadline_hit or self._remaining <= 0):
            self._finish_consensus(answer_id)
            return
        self._phase = "write"  # no reserve is kept back any more: the writer has what is left
        seat = self._seats[seat_no]
        system = self._system(seat_no)
        room = compact.budget_chars(
            self.ctx_tokens, WRITER_TOKENS + WRITER_THINK_TOKENS,
            len(system) + len(P.render("open_writer", answer=answer.statement, transcript="")),
        )
        user = P.render(
            "open_writer", answer=answer.statement,
            transcript=M.transcript_text(self._messages, seat_id(seat_no), room),
        )
        spec = CallSpec(
            model_id=seat.model_id, call_id=f"{self.run_id}:final:{seat_id(seat_no)}",
            run_id=self.run_id, purpose="seat.final",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            json_schema=None, reasoning="off", max_output_tokens=WRITER_TOKENS,
            max_reasoning_tokens=WRITER_THINK_TOKENS, temperature=DECIDER_TEMPERATURE, seed=self.seed,
            priority="interactive", stream=True,
            meta={"seat": seat_no, "round_no": self._round, "kind": "answer", "lens": seat.lens},
        )
        spec = self._queue(spec, "writer", seat_no, WRITER_TOKENS + WRITER_THINK_TOKENS)
        turn_id = spec.call_id
        spec.meta["turn_id"] = turn_id
        self._writer = {"answer_id": answer_id, "seat": seat_no, "turn_id": turn_id}
        self._emit(
            MSG_STARTED, turn_id=turn_id, call_id=turn_id, seat_no=seat_no, model_id=seat.model_id,
            name=self._names[seat_no], round=self._round, kind="answer", to=M.ALL,
        )

    def _on_writer(self, info: dict, result: CallResult) -> None:
        text = (result.content or "").strip() if result.ok else ""
        self._end_writer(text, None if text else (result.error or "invalid_output"))

    def _end_writer(self, text: str, error: Optional[str]) -> None:
        writer = self._writer or {}
        if writer:
            self._emit(MSG_ENDED, turn_id=writer["turn_id"], seat_no=writer["seat"], text=text, error=error)
        answer_id = writer.get("answer_id") or self._last_tally.get("leading") or None
        self._finish_consensus(answer_id, text)

    def _minority(self, chosen: Optional[str]) -> list[MinorityPosition]:
        report: list[MinorityPosition] = []
        for a in self._answers:
            if a.id == chosen or not a.seat_ids:
                continue
            lead = self._backers(a.id)[0]
            report.append(MinorityPosition(
                seats=sorted(_seat_no(s) for s in a.seat_ids), position=a.statement,
                strongest_argument=(self._last_text(lead) or a.statement)[:600], option_id=a.id,
            ))
        return report

    def _base_decision(self, outcome: str, answer_id: Optional[str]) -> Decision:
        counts = {a.id: len(a.seat_ids) for a in self._answers if a.seat_ids}
        n = len(self._active())
        key = None
        if self._keyed:
            key = next((a.statement for a in self._answers if a.id == answer_id), None)
        return Decision(
            outcome=outcome, option_id=answer_id, answer_key=key,
            agreement=counts.get(answer_id or "", 0) / n if n else 0.0,
            tally=counts, rounds_run=self._rounds_run, minority_report=self._minority(answer_id),
        )

    def _finalize(self, decision: Decision) -> None:
        decision.rounds_run = self._rounds_run
        for note in self._notes:
            if note not in decision.notes:
                decision.notes.append(note)
        for m in self._messages:  # nobody is still writing once the debate is over
            m.thinking, m.done = False, True
        self._decision = decision
        self._phase = "done"
        self._void()
        for seat in sorted(self._questioned):  # still apart at the end
            self._emit(OUTLIER_RESOLVED, seat=seat, outcome="held", round=self._round)
        self._questioned = {}
        for type_, p in self._outlier_log:
            if type_ != OUTLIER_RESOLVED or p["seat"] not in self._names:
                continue
            decision.notes.append(
                f"{self._names[p['seat']]} (seat {p['seat']}) was questioned as an outlier: "
                f"{p['outcome']} in round {p['round']}"
            )
        self._emit(
            E.DECISION_FINAL, decision=_dump(decision), options=[_dump(o) for o in self.options()], ms=0.0
        )

    # ----------------------------------------------------------------------------------
    # The deciding vote
    # ----------------------------------------------------------------------------------

    def _start_decider(self, reason: str) -> None:
        self._phase = "chair"
        self._decider = {"reason": reason, "tried": [], "who": None}
        self._next_decider()

    def _next_decider(self) -> None:
        tried = self._decider["tried"]
        left = [s for s in self._decider_order if s not in tried and s not in self._dropped]
        if not left or len(tried) >= MAX_DECIDER_TRIES or (tried and self._remaining <= 0):
            leading = self._last_tally.get("leading") or None
            decision = self._base_decision("deadlock", leading)
            decision.final_text, decision.confidence = self._best_text(leading)
            self._finalize(decision)
            return
        seat_no = left[0]
        tried.append(seat_no)
        self._decider["who"] = seat_no
        seat = self._seats[seat_no]
        ids = self._backed_ids()
        spec = CallSpec(
            model_id=seat.model_id, call_id=f"{self.run_id}:decider:{seat_id(seat_no)}",
            run_id=self.run_id, purpose="chair", messages=self._decider_messages(seat_no),
            json_schema=decider_schema(ids, self.answer_type if self._keyed else None),
            reasoning="off", max_output_tokens=DECIDER_TOKENS,
            max_reasoning_tokens=CARD_THINK_TOKENS, temperature=DECIDER_TEMPERATURE, seed=self.seed,
            priority="interactive", stream=False,
            meta={"seat": seat_no, "round_no": self._round, "kind": "decider"},
        )
        spec = self._queue(spec, "decider", seat_no, DECIDER_TOKENS + CARD_THINK_TOKENS, ids=ids)
        self._emit(
            E.CHAIR_STARTED, call_id=spec.call_id, model_id=seat.model_id, seat_no=seat_no,
            reason=f"deciding vote, seat picked at random: {self._decider['reason']}",
        )

    def _decider_messages(self, seat_no: int) -> list[dict[str, Any]]:
        system = self._system(seat_no)
        table = self._table_text(seat_no)
        rule = P.answer_key_rule(self.answer_type if self._keyed else None)
        room = compact.budget_chars(
            self.ctx_tokens, DECIDER_TOKENS,
            len(system) + len(P.render("open_decider", transcript="", table=table, answer_key_rule=rule)),
        )
        user = P.render(
            "open_decider", table=table, answer_key_rule=rule,
            transcript=M.transcript_text(self._messages, seat_id(seat_no), room),
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def _on_decider(self, info: dict, result: CallResult) -> None:
        data = _data(result)
        if not isinstance(data, dict):
            found = M._load(result.content) if result.ok else None
            data = found if isinstance(found, dict) else None
        text = data.get("final_answer") if data is not None else None
        if not isinstance(text, str) or not text.strip():
            text = result.content if result.ok and data is None else ""
        if not text.strip():
            self._next_decider()
            return
        data = data or {}
        seat, ids = info["seat"], list(info["ids"])
        backs = M._match(data.get("backs"), ids) or self._last_tally.get("leading") or (ids[0] if ids else None)
        key = self._key_of(data.get("answer_key"), text) if self._keyed else ""
        if key:  # the decider's key names the answer, whatever "backs" says
            backs = next((a.id for a in self._answers if a.statement == key and a.seat_ids), backs)
        decision = self._base_decision("chair", backs)
        if key:
            decision.answer_key = key
        objection = data.get("objection")
        said = objection.strip() if isinstance(objection, str) else ""
        final = text.strip()
        # Seen on the box: a decider put "No objection raised." into final_answer.
        if not self._keyed and (
            len(final) < MIN_FINAL_ANSWER_CHARS or (said and final.casefold() == said.casefold())
        ):
            final = self._fallback_text(backs) or final
        decision.final_text = final
        decision.confidence = self._best_text(backs)[1]
        decision.notes.append(
            f"no agreement: {self._names[seat]} (seat {seat}), picked at random, cast the deciding vote"
        )
        if said:
            decision.notes.append(f"remaining objection: {M.clip(said, 300)}")
        self._finalize(decision)

    # ----------------------------------------------------------------------------------
    # Snapshot / restore
    # ----------------------------------------------------------------------------------

    def snapshot(self) -> dict:
        snap = {
            "v": 1,
            "protocol": "open",
            "args": {
                "run_id": self.run_id, "task": self.task, "profile": _dump(self.profile),
                "lineup": _dump(self.lineup), "mode": _dump(self.mode), "record": self.record,
                "brief": self.brief, "lens_texts": dict(self.lens_texts),
                "seat_tps": {str(k): v for k, v in self.seat_tps.items()},
                "clerk_model_id": self.clerk_model_id, "answer_type": self.answer_type,
                "cfg": dataclasses.asdict(self._cfg), "seed": self.seed, "plan_mode": self.plan_mode,
                "seat_notes": {str(k): v for k, v in self.seat_notes.items()},
                "max_extra_rounds": self.max_extra_rounds,
                "extend_min_agreement": self.extend_min_agreement, "ctx_tokens": self.ctx_tokens,
                "seat_names": {str(k): v for k, v in self.seat_names.items()},
                "max_rounds": self.max_rounds, "write_final": self.write_final,
                "question_outliers": self.question_outliers,
            },
            "state": {
                "seats": [_dump(s) for _, s in sorted(self._seats.items())],
                "alternates": list(self._alternates), "substituted": sorted(self._substituted),
                "phase": self._phase, "round": self._round, "rounds_run": self._rounds_run,
                "remaining": self._remaining, "deadline_hit": self._deadline_hit,
                "notes": list(self._notes),
                "messages": [_dump(m) for m in self._messages],
                "answers": [_dump(a) for a in self._answers],
                "cards": {str(k): _dump(v) for k, v in self._cards.items()},
                "round_cards": {str(k): _dump(v) for k, v in self._round_cards.items()},
                "fallbacks": sorted(self._fallbacks),
                "fails": {str(k): v for k, v in self._fails.items()},
                "dropped": sorted(self._dropped),
                "round_failed": list(self._round_failed), "voided": list(self._voided),
                "r0_pos": {str(k): v for k, v in self._r0_pos.items()},
                "waiting": [{**i, "spec": _dump(i["spec"])} for i in self._waiting.values()],
                "used": sorted(self._used),
                "decider": None if self._decider is None else dict(self._decider),
                "writer": None if self._writer is None else dict(self._writer),
                "decision": _dump(self._decision), "last_tally": self._last_tally,
                "events": [[t, p] for t, p in self._events],
                "outliers": list(self._outliers),
                "questioned": {str(k): v for k, v in self._questioned.items()},
                "q_extra": self._q_extra, "n_rounds": self._n_rounds,
                "outlier_log": [[t, p] for t, p in self._outlier_log],
            },
        }
        return json.loads(json.dumps(snap))  # a deep copy that is proven JSON-serializable

    @classmethod
    def restore(
        cls, snapshot: dict, normalize: Callable[[str, str], str] | None = None
    ) -> "OpenDebate":
        a, s = snapshot["args"], snapshot["state"]
        self = cls.__new__(cls)
        self._setup(
            a["run_id"], a["task"], TaskProfile.model_validate(a["profile"]),
            LineupRecord.model_validate(a["lineup"]), ModeConfig.model_validate(a["mode"]),
            a["record"], a["brief"], a["lens_texts"], a["seat_tps"], a["clerk_model_id"],
            a["answer_type"], normalize, ConsensusConfig(**a["cfg"]), a["seed"], a["plan_mode"],
            a.get("seat_notes"), max_extra_rounds=a.get("max_extra_rounds", 0),
            extend_min_agreement=a.get("extend_min_agreement", 0.5),
            ctx_tokens=a.get("ctx_tokens", DEFAULT_CTX_TOKENS), seat_names=a.get("seat_names"),
            max_rounds=a.get("max_rounds"), write_final=a.get("write_final", True),
            question_outliers=a.get("question_outliers", True),
        )
        if s.get("seats"):
            self._seats = {x["seat_no"]: SeatAssignment.model_validate(x) for x in s["seats"]}
        self._alternates = list(s.get("alternates", self._alternates))
        self._substituted = set(s.get("substituted", []))
        self._phase = s["phase"]
        self._round = s["round"]
        self._rounds_run = s["rounds_run"]
        self._remaining = s["remaining"]
        self._deadline_hit = s["deadline_hit"]
        self._notes = list(s["notes"])
        self._messages = [M.CouncilMessage.model_validate(m) for m in s["messages"]]
        self._answers = [M.TableAnswer.model_validate(x) for x in s["answers"]]
        self._cards = {int(k): M.Card.model_validate(v) for k, v in s["cards"].items()}
        self._round_cards = {int(k): M.Card.model_validate(v) for k, v in s["round_cards"].items()}
        self._fallbacks = set(s["fallbacks"])
        self._fails = {int(k): int(v) for k, v in s["fails"].items()}
        self._dropped = set(s["dropped"])
        self._round_failed = list(s["round_failed"])
        self._voided = list(s["voided"])
        self._r0_pos = {int(k): v for k, v in s["r0_pos"].items()}
        self._used = set(s["used"])
        self._decider = None if s["decider"] is None else dict(s["decider"])
        self._writer = None if s.get("writer") is None else dict(s["writer"])
        self._decision = None if s["decision"] is None else Decision.model_validate(s["decision"])
        self._last_tally = dict(s["last_tally"])
        self._events = [(t, p) for t, p in s["events"]]
        self._outliers = [int(x) for x in s.get("outliers", [])]
        self._questioned = {int(k): v for k, v in s.get("questioned", {}).items()}
        self._q_extra = int(s.get("q_extra", 0))
        self._n_rounds = int(s.get("n_rounds", self._n_rounds))
        self._outlier_log = [(t, p) for t, p in s.get("outlier_log", [])]
        # Calls that were out are handed out again: the old in-flight ones are gone.
        self._waiting, self._outbox = {}, []
        for item in s["waiting"]:
            spec = CallSpec.model_validate(item["spec"])
            self._waiting[spec.call_id] = {**item, "spec": spec}
            self._outbox.append(spec)
        return self


__all__ = [
    "OpenDebate",
    "merge_schema",
    "decider_schema",
    "seat_id",
    "POSITION_TOKENS",
    "REPLY_TOKENS",
    "CARD_TOKENS",
    "CARD_THINK_TOKENS",
    "WRITER_TOKENS",
    "WRITER_THINK_TOKENS",
    "MIN_FINAL_ANSWER_CHARS",
    "DECIDER_FLOOR_S",
    "LATE_DECIDER_NOTE",
    "OUTLIER_NAMED",
    "OUTLIER_RESOLVED",
    "QUESTION_EXTRA_ROUNDS",
    "MSG_STARTED",
    "MSG_ENDED",
    "MSG_CARD",
    "MSG_LIE",
    "TABLE_TALLY",
]
