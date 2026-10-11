"""Engine events -> the partner UI's DebateEvent stream. Pure translation: no I/O, no clock.

The partner's UI (docs/ui_ref/lib/events.ts) draws a debate from a numbered list of DebateEvent
objects. Our engine emits its own events (council/core/event_types.py, plus the open-protocol
"msg.*" / "table.tally" events). UiBridge.feed() turns one of ours into zero or more of theirs,
so the UI needs no changes.

Every UI event is  {"v": 1, "seq", "debateId", "at", "clock", "type", ...body}  with the body
fields named exactly as in events.ts (camelCase). `seq` is the bridge's own counter from 1,
`at` is ms since the first engine event (ts is epoch seconds or an ISO-8601 string), `clock` is ms of debate time (it runs only in the
research / debate / vote phases, stops while paused and for good once a tally is reached).

Open protocol (preferred)
    msg.started   -> [round.started] turn.started {turnId, seatId, round, kind, to}, seat.thinking on
    msg.thinking  -> seat.thinking on
    msg.delta     -> turn.delta
    msg.ended     -> turn.ended {text, citations: [], error?}
    msg.card      -> summary.posted {summaryId, seatId, turnId, text <= 55 chars, source "self";
                     "engine" when the card is the engine's fallback},
                     turn.addressed (only when the card's "to" differs from turn.started's),
                     seat.thinking off
    msg.lie       -> lie.posted (nothing when the reading has no score)
    chair.started -> seat.thinking on for the seat casting the deciding vote; that seat is the
                     author of the answer turn when the outcome is "chair"
    turn.delta    -> turn.delta, when its call_id is the turn id of an open message (the gateway
                     streams the message call under that id)
    table.tally   -> tally.posted (seat ids become "s<n>")

Today's events (fallback)
    run.created + router.lineup_selected -> debate.created, as soon as the lineup is announced
        (anything translated before that is sent right after it). With no lineup event the seats
        come from seat.assigned / round.started / the first message.
    debate.created is sent AGAIN, whole, whenever what it says changes: a seat got another model
        (its name), the time limit became known (effort.planned), a seat was added. viewAt()
        keeps the newest one; seat ids never change.
    model.loading / model.loaded / model.failed -> seat.status, at the moment they happen.
        Models that hold no seat (clerk, helpers) give nothing. A model named "resident" by the
        lineup is ready at once. model.failed with replaced_by: the seat takes the new model and
        shows "loading" with a reason, then "ready". Without: "failed" with the reason.
        Every seat still "loading" when the debate begins is "ready" (the engine only begins with
        all seats resident; models that were resident get no model.* event).
    a second router.lineup_selected (a seat was dropped while loading; the engine renumbers) ->
        engine seat numbers are mapped onto the seats already on screen by model; a seat with no
        model left is "dropped" (or stays "failed") with a reason.
    round.started {seats} -> a seat that is no longer listed is "dropped" with a reason.
    seat.assigned with replaces_model_id (round-0 swap) -> debate.created again with the new
        name, seat.status "loading" with a reason, "ready" when its message starts.
    run.state_changed -> phase.changed; AWAITING_USER -> clock.paused / clock.resumed
    round.started -> round.started
    turn.started / turn.delta / turn.completed / turn.invalid / turn.timeout
        -> turn.started (kind "position" in round 0, "reply" later, to "all") / turn.delta /
           turn.ended; calls without a seat (clerk, workers) are dropped. A turn opened by
           msg.started ends only with msg.ended: the gateway's turn.completed / turn.timeout of
           the same call id is ignored (the engine may still retry it).
    round.completed -> tally.posted (groups from options[].holders), unless table.tally already
        counted that round
    tally.posted: "seats" / "needed" are the engine's when it sends them, else the seats still in
        the debate (not failed, not dropped) and 80% of them. A seat is in at most one group.
    decision.final -> a final turn of kind "answer"
    run.completed / run.failed / run.cancelled -> answer.released (agreed / no-consensus /
        stopped), then phase.changed released

EXTENSIONS for the partner. events.ts does not have these three types yet. viewAt()'s switch has
no default branch, so an old UI ignores them.
    {type: "lie.posted",     turnId: Id, seatId: Id, score: number, level: "ok"|"watch"|"flag",
                             reasons: string[]}
        The engine's lie-detector reading of one message. score 0 = likely false .. 1 = likely true.
    {type: "seat.thinking",  seatId: Id, turnId: Id, on: boolean}
        on = the seat is writing a message whose note card has not arrived. The table view shows
        "thinking..." in place of the card while on. Goes off with the card, with a failed turn,
        and at the latest when the round is tallied or the debate ends.
    {type: "turn.addressed", turnId: Id, to: "all" | Id[]}
        The member's own statement of whom the turn addressed, when it differs from the `to`
        announced at turn.started. The chat view should replace the turn's `to` with it.

Seat ids are "s<seat_no>". shortName is the first word of the model's display name, at most 7
characters. table_snapshot() rebuilds the table view (one note card per seat) from the UI stream
alone.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

NOTE_MAX = 55
REASON_MAX = 140
SHORT_NAME_MAX = 7
PHASES = ("spooling", "research", "debate", "vote", "writing", "released")
TURN_KINDS = ("research", "position", "reply", "answer", "dissent")
TALLY_BASES = ("round-vote", "closing", "live")
LIE_LEVELS = ("ok", "watch", "flag")
_CLOCK_RUNS_IN = ("research", "debate", "vote")

STATE_TO_PHASE: dict[str, str] = {
    "INTAKE": "spooling", "PROFILING": "spooling", "CONVENING": "spooling",
    "DELIBERATING": "debate",
    "DECIDED": "vote", "EXAMINING": "vote",
    "PLANNING": "writing", "AWAITING_DELEGATION": "writing", "EXECUTING": "writing",
    "REVIEWING": "writing", "INTEGRATING": "writing", "REFLECTING": "writing",
}
# Engine events that cannot be drawn without the seats: they force debate.created out.
_NEEDS_SEATS = (
    "round.started", "turn.started", "msg.started", "msg.thinking", "msg.card", "msg.lie",
    "table.tally", "round.completed", "chair.started", "decision.final",
    "run.completed", "run.failed", "run.cancelled",
)


def seat_id(seat_no: Any) -> str:
    """3 -> "s3". A value that already is "s3" stays "s3"."""
    text = str(seat_no).strip()
    return text if re.fullmatch(r"s\d+", text) else f"s{text}"


def short_name(display: str) -> str:
    """First word of the display name, at most 7 characters. "Qwen 2.5 Coder" -> "Qwen"."""
    words = [w for w in re.split(r"[\s\-_:/]+", str(display or "").strip()) if w]
    return (words[0] if words else "seat")[:SHORT_NAME_MAX]


def seat_names(displays: dict[int, str]) -> dict[int, str]:
    """{seat_no: display name} -> {seat_no: first word}, made unique: a clash gets a digit
    ("Qwen", "Qwen2"). These are the names the open protocol's members call each other by."""
    out: dict[int, str] = {}
    used: set[str] = set()
    for no in sorted(displays):
        words = [w for w in re.split(r"[\s\-_:/]+", str(displays[no] or "").strip()) if w]
        base = words[0] if words else f"Seat{no}"
        name, n = base, 1
        while name.casefold() in used:
            n += 1
            name = f"{base}{n}"
        used.add(name.casefold())
        out[int(no)] = name
    return out


def clip(text: Any, limit: int = NOTE_MAX) -> str:
    """One line, at most `limit` characters; a cut text ends in an ellipsis."""
    line = " ".join(str(text or "").split())
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def needed(seats: int) -> int:
    """Seats that must back the same answer: 80%, rounded up (events.ts needed())."""
    return -(-4 * seats // 5)


def epoch(ts: Any) -> float:
    """Seconds from an engine timestamp: a number, a numeric string or ISO-8601. 0.0 if neither."""
    if isinstance(ts, bool) or ts is None:
        return 0.0
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, datetime):
        when = ts
    else:
        text = str(ts).strip()
        try:
            return float(text)
        except ValueError:
            pass
        try:
            when = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.timestamp()


def _int(value: Any) -> Optional[int]:
    """3, "3", "s3" -> 3. None when it is no seat number."""
    if isinstance(value, bool) or value is None:
        return None
    match = re.fullmatch(r"s?(-?\d+)", str(value).strip())
    return int(match.group(1)) if match else None


def _dump(value: Any) -> Any:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


class UiBridge:
    def __init__(self, debate_id: str, limit_ms: int = 0) -> None:
        self.debate_id = debate_id
        self.limit_ms = int(limit_ms or 0)
        self._seq = 0
        self._t0: Optional[float] = None
        self._at = 0
        self._clock = 0
        self._phase = "idle"
        self._paused = False
        self._agreed = False
        self._question = ""
        # UI seat number -> {"model_id", "display", "role", "status", "reason"}. A UI seat keeps
        # its number ("s<n>") for the whole debate.
        self._seats: dict[int, dict] = {}
        self._eng: dict[int, int] = {}  # engine seat_no -> UI seat number, where they differ
        self._displays: dict[str, str] = {}  # model id -> display name
        self._model_state: dict[str, tuple[str, str]] = {}  # model id -> (seat status, reason)
        self._created = False
        self._created_body: Optional[dict] = None  # the last debate.created sent
        self._pre: list[dict] = []  # bodies held until debate.created
        self._round = -1
        self._rounds_started = 0
        self._turns: dict[str, dict] = {}  # turnId -> {"seat", "to", "text", "done"}
        self._call_turn: dict[str, str] = {}  # engine call id -> current turnId
        self._thinking: dict[str, str] = {}  # seatId -> turnId
        self._last_turn: dict[str, str] = {}  # seatId -> its newest position / reply turn
        self._open_tally_rounds: set[int] = set()
        self._tally: Optional[dict] = None
        self._decision: dict = {}
        self._answer_turn: Optional[str] = None
        self._writer_turn: Optional[str] = None  # open protocol: the streamed final answer
        self._decider: Optional[str] = None  # seat id of the deciding vote, if one was asked for
        self._released = False
        self._out: list[dict] = []

    # ---- public ----

    def feed(self, event: dict) -> list[dict]:
        etype = str(event.get("type") or "")
        payload = _dump(event.get("payload")) or {}
        self._tick(event.get("ts"))
        self._out = []
        handler = getattr(self, "_on_" + etype.replace(".", "_"), None)
        if handler is not None and isinstance(payload, dict):
            if etype in _NEEDS_SEATS:
                if payload.get("seat_no") is not None:  # a seat nobody announced, or its model
                    self._learn(payload["seat_no"], str(payload.get("model_id") or ""))
                if not self._created and etype == "round.started" and isinstance(payload.get("seats"), list):
                    for no in payload["seats"]:  # no lineup was announced: take the round's seats
                        self._learn(no)
                self._flush_created()
            handler(payload)
        out, self._out = self._out, []
        return out

    # ---- time, envelope ----

    def _tick(self, ts: Any) -> None:
        now = epoch(ts)
        if now > 0 and self._t0 is None:
            self._t0 = now
        at = self._at if (now <= 0 or self._t0 is None) else int(round((now - self._t0) * 1000))
        at = max(at, self._at)
        if self._phase in _CLOCK_RUNS_IN and not self._paused and not self._agreed:
            clock = self._clock + (at - self._at)
            self._clock = min(clock, self.limit_ms) if self.limit_ms > 0 else clock
        self._at = at

    def _emit(self, type_: str, **body: Any) -> None:
        if not self._created and type_ != "debate.created":
            self._pre.append({"type": type_, **body})
            return
        self._seq += 1
        self._out.append({"v": 1, "seq": self._seq, "debateId": self.debate_id,
                          "at": self._at, "clock": self._clock, "type": type_, **body})

    # ---- seats, debate.created ----

    @property
    def released(self) -> bool:
        """answer.released went out: the stream is complete."""
        return self._released

    def _ui_no(self, seat_no: Any) -> Optional[int]:
        """Engine seat number (3, "3", "s3") -> the UI seat that holds it."""
        no = _int(seat_no)
        return None if no is None else self._eng.get(no, no)

    def _sid(self, seat_no: Any) -> str:
        no = self._ui_no(seat_no)
        return seat_id(seat_no) if no is None else seat_id(no)

    def _name(self, seat: dict, no: int) -> str:
        return seat["display"] or self._displays.get(seat["model_id"], "") or seat["model_id"] or f"Seat {no}"

    def _model_name(self, model_id: str) -> str:
        return self._displays.get(model_id, "") or model_id

    def _seat(self, no: int, model_id: str = "", display: str = "", role: Any = None) -> dict:
        """The UI seat `no`, made if new. Given fields overwrite; a new model clears the old name."""
        seat = self._seats.setdefault(
            no, {"model_id": "", "display": "", "role": None, "status": None, "reason": ""})
        if model_id and model_id != seat["model_id"]:
            seat["model_id"], seat["display"] = model_id, ""
        seat["display"] = display or seat["display"]
        seat["role"] = role or seat["role"]
        return seat

    def _learn(self, seat_no: Any, model_id: str = "") -> None:
        """A seat named by an event: add it if unknown, give it its model if it had none."""
        no = self._ui_no(seat_no)
        if no is None:
            return
        known = self._seats.get(no)
        if known is None or (model_id and not known["model_id"]):
            self._seat(no, model_id)
            self._recreate()

    def _ui_seats(self) -> list[dict]:
        seats = []
        for index, no in enumerate(sorted(self._seats)):
            seat = self._seats[no]
            name = self._name(seat, no)
            ui = {"id": seat_id(no), "index": index, "shortName": short_name(name), "modelName": name}
            if seat["role"]:
                ui["role"] = str(seat["role"])
            seats.append(ui)
        return seats

    def _send_created(self) -> None:
        body = {"question": self._question, "files": [], "seats": self._ui_seats(), "limitMs": self.limit_ms}
        if body != self._created_body:
            self._created_body = body
            self._emit("debate.created", **body)

    def _recreate(self) -> None:
        """debate.created again, when it is out and what it says has changed."""
        if self._created:
            self._send_created()

    def _flush_created(self) -> None:
        if self._created:
            return
        self._created = True
        self._send_created()
        held, self._pre = self._pre, []
        for body in held:
            body = dict(body)
            self._emit(body.pop("type"), **body)
        for no in sorted(self._seats):  # what the models did before the seats were known
            state = self._model_state.get(self._seats[no]["model_id"])
            if state:
                self._seats[no]["status"] = None
                self._set_status(no, *state)

    def _set_status(self, no: int, status: str, reason: str = "") -> None:
        seat = self._seats.get(no)
        if seat is None:
            return
        reason = clip(reason, REASON_MAX)
        if seat["status"] == status and (not reason or reason == seat["reason"] or status != "loading"):
            return
        seat["status"], seat["reason"] = status, reason
        if not self._created:
            return  # sent with the seats, by _flush_created (from _model_state) or _settle
        body: dict[str, Any] = {"seatId": seat_id(no), "status": status}
        if reason:
            body["reason"] = reason
        self._emit("seat.status", **body)

    def _model_status(self, model_id: str, status: str, reason: str = "") -> None:
        """A model changed state: every seat that holds it shows it. No seat: nothing."""
        if not model_id:
            return
        self._model_state[model_id] = (status, clip(reason, REASON_MAX))
        if self._created:
            for no in sorted(self._seats):
                if self._seats[no]["model_id"] == model_id:
                    self._set_status(no, status, reason)

    def _settle(self) -> None:
        """The debate begins: the engine only gets here with every seat resident."""
        if not self._created:
            return
        for no in sorted(self._seats):
            if self._seats[no]["status"] in (None, "loading"):
                self._set_status(no, "ready")

    def _swap(self, no: int, new_model: str, why: str) -> None:
        """Seat `no` gets another model: new name on screen, then its status."""
        seat = self._seats[no]
        old = self._name(seat, no)
        self._seat(no, new_model)
        self._recreate()
        seat["status"] = None  # the status is said again, for the new model
        if self._model_state.get(new_model, ("", ""))[0] == "ready":
            self._set_status(no, "ready")
        else:
            self._set_status(no, "loading", f"{old} {why}. {self._model_name(new_model)} takes the seat.")

    def _to(self, to: Any) -> Any:
        """"all" or a list of seat ids, from seat numbers, "s2", or a model / short name."""
        if to is None or isinstance(to, str) and to.strip().lower() in ("", "all", "council"):
            return "all"
        items = to if isinstance(to, (list, tuple)) else [to]
        names: dict[str, str] = {}
        for seat in self._ui_seats():
            names[seat["shortName"].lower()] = seat["id"]
            names[seat["modelName"].lower()] = seat["id"]
        ids: list[str] = []
        for item in items:
            text = str(item).strip().lower()
            if text in ("all", "council"):
                return "all"
            match = re.fullmatch(r"(?:s|seat\s*)?(\d+)", text)
            sid = self._sid(match.group(1)) if match else names.get(text)
            if sid and sid not in ids:
                ids.append(sid)
        return ids or "all"

    # ---- phases, rounds, thinking ----

    def _set_phase(self, phase: str) -> None:
        if phase in PHASES and phase != self._phase:
            self._phase = phase
            self._emit("phase.changed", phase=phase)

    def _set_round(self, round_no: Any) -> int:
        try:
            no = int(round_no)
        except (TypeError, ValueError):
            no = max(self._round, 0)
        if no > self._round:
            self._round = no
            self._rounds_started += 1
            self._emit("round.started", round=no)
        return no

    def _think(self, sid: str, turn_id: str, on: bool) -> None:
        if on and self._thinking.get(sid) != turn_id:
            self._thinking[sid] = turn_id
            self._emit("seat.thinking", seatId=sid, turnId=turn_id, on=True)
        elif not on and sid in self._thinking:
            self._emit("seat.thinking", seatId=sid, turnId=self._thinking.pop(sid), on=False)

    def _stop_all_thinking(self) -> None:
        for sid in sorted(self._thinking):
            self._think(sid, "", False)

    def _start_turn(self, turn_id: str, seat_no: Any, round_no: Any, kind: Any, to: Any) -> None:
        if self._phase in ("idle", "spooling"):
            self._settle()  # the first turn: the debate has begun
            self._set_phase("debate")
        no = self._set_round(round_no)
        if kind not in TURN_KINDS:
            kind = "position" if no <= 0 else "reply"
        sid = self._sid(seat_no)
        ui_no = self._ui_no(seat_no)
        if ui_no in self._seats and self._seats[ui_no]["status"] != "ready":
            self._set_status(ui_no, "ready")  # it speaks, so it is at the table
        self._turns[turn_id] = {"seat": sid, "to": to, "text": "", "done": False, "open": False}
        if kind in ("position", "reply"):
            self._last_turn[sid] = turn_id
        self._emit("turn.started", turnId=turn_id, seatId=sid, round=no, kind=kind, to=to)

    def _end_turn(self, turn_id: str, text: Any, error: Any = None) -> None:
        turn = self._turns.get(turn_id)
        if turn is None or turn["done"]:
            return
        turn["done"] = True
        turn["text"] = str(text) if text else turn["text"]
        body: dict[str, Any] = {"turnId": turn_id, "text": turn["text"], "citations": []}
        if error:
            body["error"] = str(error)
        self._emit("turn.ended", **body)

    def _summary(self, sid: str, turn_id: str, text: Any, source: str) -> None:
        note = clip(text)
        if note:
            self._emit("summary.posted", summaryId=f"sum-{turn_id}", seatId=sid, turnId=turn_id,
                       text=note, source=source)

    # ---- open protocol ----

    def _on_msg_started(self, p: dict) -> None:
        turn_id = str(p.get("turn_id") or f"t{len(self._turns) + 1}")
        self._start_turn(turn_id, p.get("seat_no"), p.get("round"), p.get("kind"), self._to(p.get("to")))
        self._turns[turn_id]["open"] = True  # ends with msg.ended, not with the gateway's events
        if p.get("kind") == "answer":  # the agreed answer, written by one backer after the vote
            self._writer_turn = turn_id
        if p.get("call_id"):  # the gateway streams the message call under this id (turn.delta)
            self._call_turn[str(p["call_id"])] = turn_id
        self._think(self._sid(p.get("seat_no")), turn_id, True)

    def _on_msg_thinking(self, p: dict) -> None:
        self._think(self._sid(p.get("seat_no")), str(p.get("turn_id") or ""), True)

    def _on_msg_delta(self, p: dict) -> None:
        turn = self._turns.get(str(p.get("turn_id") or ""))
        text = p.get("text") or ""
        if turn is not None and not turn["done"] and text:
            turn["text"] += text
            self._emit("turn.delta", turnId=str(p["turn_id"]), text=text)

    def _on_msg_ended(self, p: dict) -> None:
        turn_id = str(p.get("turn_id") or "")
        self._end_turn(turn_id, p.get("text"), p.get("error"))
        turn = self._turns.get(turn_id)
        if turn is not None and turn_id == self._writer_turn:  # no card follows the final answer
            self._think(turn["seat"], turn_id, False)
            if not p.get("error") and turn["text"]:
                self._answer_turn = turn_id  # this turn IS the answer: decision.final adds none
        elif p.get("error") and turn is not None:  # no card will follow a failed message
            self._think(turn["seat"], turn_id, False)

    def _on_msg_card(self, p: dict) -> None:
        turn_id = str(p.get("turn_id") or "")
        card = p.get("card") if isinstance(p.get("card"), dict) else {}
        turn = self._turns.get(turn_id)
        sid = turn["seat"] if turn else self._sid(p.get("seat_no"))
        # A card the engine had to make (the member's card call failed) is not the member's word.
        source = "engine" if p.get("fallback") else "self"
        self._summary(sid, turn_id, card.get("note") or card.get("stance"), source)
        if turn is not None and "to" in card:
            to = self._to(card.get("to"))
            if to != turn["to"]:
                turn["to"] = to
                self._emit("turn.addressed", turnId=turn_id, to=to)
        self._think(sid, turn_id, False)

    def _on_msg_lie(self, p: dict) -> None:
        turn_id = str(p.get("turn_id") or "")
        turn = self._turns.get(turn_id)
        try:
            score = float(p.get("score"))
        except (TypeError, ValueError):
            return  # not measured: no reading is shown, never a made-up one
        if score != score:
            return
        score = min(1.0, max(0.0, score))
        level = p.get("level")
        if level not in LIE_LEVELS:
            level = "ok" if score >= 0.6 else "watch" if score >= 0.35 else "flag"
        reasons = p.get("reasons") or []
        reasons = [reasons] if isinstance(reasons, str) else [str(r) for r in reasons]
        self._emit("lie.posted", turnId=turn_id, seatId=turn["seat"] if turn else self._sid(p.get("seat_no")),
                   score=score, level=level, reasons=reasons)

    def _on_table_tally(self, p: dict) -> None:
        groups = [{"answerId": str(g.get("answer_id") or g.get("id") or ""),
                   "statement": str(g.get("statement") or g.get("summary") or ""),
                   "seatIds": [self._sid(s) for s in (g.get("seat_ids") or g.get("holders") or [])]}
                  for g in (p.get("groups") or []) if isinstance(g, dict)]
        self._open_tally_rounds.add(self._post_tally(p, groups, p.get("leading"), p.get("reached")))

    def _post_tally(self, p: dict, groups: list[dict], leading: Any, reached: Any) -> int:
        try:
            round_no = int(p.get("round"))
        except (TypeError, ValueError):
            round_no = max(self._round, 0)
        counted: set[str] = set()
        for group in groups:  # a seat backs one answer: its first group keeps it
            group["seatIds"] = [s for s in dict.fromkeys(group["seatIds"]) if s not in counted]
            counted.update(group["seatIds"])
        biggest = max(groups, key=lambda g: len(g["seatIds"]), default=None)
        if not leading or all(g["answerId"] != leading for g in groups):
            leading = biggest["answerId"] if biggest else ""
        lead = next((g for g in groups if g["answerId"] == leading), None)
        agree = p.get("agree") if isinstance(p.get("agree"), int) else len(lead["seatIds"]) if lead else 0
        in_debate = sum(1 for seat in self._seats.values() if seat["status"] not in ("failed", "dropped"))
        seats = p.get("seats") if isinstance(p.get("seats"), int) else max(in_debate, len(counted))
        need = p.get("needed") if isinstance(p.get("needed"), int) else needed(seats)
        if reached is None:
            reached = seats > 0 and agree >= need
        basis = p.get("basis") if p.get("basis") in TALLY_BASES else "round-vote"
        self._stop_all_thinking()  # a counted round has no member still writing
        self._tally = {"round": round_no, "basis": basis, "groups": groups, "leading": str(leading),
                       "agree": agree, "seats": seats, "needed": need, "reached": bool(reached)}
        self._emit("tally.posted", **self._tally)
        self._agreed = self._agreed or bool(reached)
        return round_no

    # ---- today's events ----

    def _on_run_created(self, p: dict) -> None:
        self._question = str(p.get("task") or "")
        self._set_phase("spooling")

    def _on_effort_planned(self, p: dict) -> None:
        if self.limit_ms <= 0 and p.get("deadline_s"):
            try:
                self.limit_ms = max(0, int(float(p["deadline_s"]) * 1000))
            except (TypeError, ValueError):
                return
            self._recreate()  # the limit is part of debate.created

    def _on_router_candidates_scored(self, p: dict) -> None:
        for m in p.get("candidates") or []:
            if isinstance(m, dict) and m.get("model_id") and m.get("display"):
                self._displays[str(m["model_id"])] = str(m["display"])

    def _on_router_lineup_selected(self, p: dict) -> None:
        models = [m for m in (p.get("models") or []) if isinstance(m, dict)]
        for m in models:
            if m.get("model_id") and m.get("display"):
                self._displays[str(m["model_id"])] = str(m["display"])
        lineup = [s for s in ((p.get("lineup") or {}).get("seats") or [])
                  if isinstance(s, dict) and _int(s.get("seat_no")) is not None]
        if not lineup:
            return
        if not self._seats:
            for seat in lineup:
                self._seat(_int(seat["seat_no"]), str(seat.get("model_id") or ""), "", seat.get("lens"))
            self._flush_created()
        else:
            self._remap(lineup)
        self._recreate()
        for m in models:  # already in memory: no model.loading / model.loaded will come for it
            mid = str(m.get("model_id") or "")
            if m.get("resident") is True and self._model_state.get(mid, ("", ""))[0] != "failed":
                self._model_status(mid, "ready")

    def _remap(self, lineup: list[dict]) -> None:
        """A new lineup while seats are on screen (the engine dropped a seat and renumbered):
        each engine seat is the UI seat that holds its model; a model nobody holds takes the
        UI seat with that number if free, else a free one, else a new one."""
        by_model = {seat["model_id"]: no for no, seat in self._seats.items() if seat["model_id"]}
        eng: dict[int, int] = {}
        left: list[dict] = []
        for seat in lineup:
            ui_no = by_model.get(str(seat.get("model_id") or ""))
            if ui_no is None or ui_no in eng.values():
                left.append(seat)
            else:
                eng[_int(seat["seat_no"])] = ui_no
        self._flush_created()
        for seat in left:
            no, mid = _int(seat["seat_no"]), str(seat.get("model_id") or "")
            free = [n for n in sorted(self._seats) if n not in eng.values()]
            if no in free or (no not in self._seats and no not in eng.values()):
                ui_no = no
            else:
                ui_no = free[0] if free else max(self._seats) + 1
            if ui_no in self._seats and mid and self._seats[ui_no]["model_id"] not in ("", mid):
                self._swap(ui_no, mid, "is not at the table")
            else:
                self._seat(ui_no, mid)
            eng[no] = ui_no
        for seat in lineup:
            if seat.get("lens"):
                self._seats[eng[_int(seat["seat_no"])]]["role"] = seat["lens"]
        self._eng = {no: ui_no for no, ui_no in eng.items() if no != ui_no}
        self._recreate()
        for no in sorted(self._seats):  # no engine seat is this one any more
            if no not in eng.values() and self._seats[no]["status"] not in ("failed", "dropped"):
                self._set_status(no, "dropped", f"{self._name(self._seats[no], no)} was left out of this debate.")

    def _on_seat_assigned(self, p: dict) -> None:
        no = self._ui_no(p.get("seat_no"))
        if no is None:
            return
        model_id, display = str(p.get("model_id") or ""), str(p.get("display") or "")
        if display and model_id:
            self._displays[model_id] = display
        seat = self._seats.get(no)
        if self._created and seat is not None and model_id and seat["model_id"] not in ("", model_id):
            self._swap(no, model_id, "did not answer")  # round-0 swap, or a load the bridge missed
            seat["role"] = p.get("lens") or seat["role"]
        else:
            self._seat(no, model_id, display, p.get("lens"))
        self._recreate()

    def _on_model_loading(self, p: dict) -> None:
        self._model_status(str(p.get("model_id") or ""), "loading")

    def _on_model_loaded(self, p: dict) -> None:
        self._model_status(str(p.get("model_id") or ""), "ready")

    def _on_model_failed(self, p: dict) -> None:
        model_id = str(p.get("model_id") or "")
        if p.get("display") and model_id:
            self._displays.setdefault(model_id, str(p["display"]))
        error = " ".join(str(p.get("error") or "").split()) or "did not load"
        new_model = str(p.get("replaced_by") or "")
        holders = [no for no in sorted(self._seats) if self._seats[no]["model_id"] == model_id]
        if new_model and new_model != model_id and holders:
            self._model_state[model_id] = ("failed", clip(error, REASON_MAX))
            for no in holders:
                if self._created:
                    self._swap(no, new_model, "did not load")
                else:
                    self._seat(no, new_model)
            return
        self._model_status(model_id, "failed", error)

    def _on_run_state_changed(self, p: dict) -> None:
        state = str(getattr(p.get("to_state"), "value", p.get("to_state")) or "")
        if state == "AWAITING_USER":
            if not self._paused:
                self._paused = True
                self._emit("clock.paused")
            return
        if self._paused:
            self._paused = False
            self._emit("clock.resumed")
        if state in STATE_TO_PHASE:
            if STATE_TO_PHASE[state] != "spooling" and self._seats:
                self._flush_created()
                self._settle()
            self._set_phase(STATE_TO_PHASE[state])

    def _on_round_started(self, p: dict) -> None:
        self._settle()
        listed = p.get("seats")
        if isinstance(listed, list) and listed:
            here = {self._ui_no(no) for no in listed}
            for no in sorted(self._seats):
                if no not in here and self._seats[no]["status"] == "ready":
                    self._set_status(no, "dropped", f"{self._name(self._seats[no], no)} stopped answering "
                                                    "and was left out of the debate.")
        self._set_round(p.get("round"))

    def _on_turn_started(self, p: dict) -> None:
        if p.get("seat_no") is None:
            return
        call_id = str(p.get("call_id") or "")
        turn_id, n = call_id, 1
        while turn_id in self._turns:  # a retry of the same call is a new turn for the UI
            n += 1
            turn_id = f"{call_id}#{n}"
        self._call_turn[call_id] = turn_id
        self._start_turn(turn_id, p["seat_no"], p.get("round"), None, "all")

    def _on_turn_delta(self, p: dict) -> None:
        call_id = str(p.get("call_id") or "")
        # An open-protocol message is streamed by the gateway under its own call id, which is
        # the message's turn id (the gateway announces no seat turn for it).
        turn_id = self._call_turn.get(call_id) or (call_id if call_id in self._turns else None)
        if turn_id:
            self._on_msg_delta({"turn_id": turn_id, "text": p.get("text")})

    def _on_turn_completed(self, p: dict) -> None:
        turn_id = self._call_turn.get(str(p.get("call_id") or ""))
        turn = self._turns.get(turn_id or "")
        if turn is None or turn["done"] or turn.get("open"):
            return
        parsed = p.get("parsed") if isinstance(p.get("parsed"), dict) else {}
        said = next((parsed[k] for k in ("answer", "final_answer", "summary")
                     if isinstance(parsed.get(k), str) and parsed[k].strip()), "")
        self._end_turn(turn_id, said or p.get("content"))
        self._summary(turn["seat"], turn_id, parsed.get("summary") or said, "engine")

    def _gateway_turn(self, p: dict) -> Optional[str]:
        """The turn a gateway event is about; None for an open-protocol message (msg.ended ends it)."""
        turn_id = self._call_turn.get(str(p.get("call_id") or ""))
        return None if turn_id is None or self._turns.get(turn_id, {}).get("open") else turn_id

    def _on_turn_invalid(self, p: dict) -> None:
        turn_id = self._gateway_turn(p)
        if turn_id:
            self._end_turn(turn_id, "", p.get("error") or "invalid reply")

    def _on_turn_timeout(self, p: dict) -> None:
        turn_id = self._gateway_turn(p)
        if turn_id:
            self._end_turn(turn_id, "", "timed out")

    def _on_round_completed(self, p: dict) -> None:
        try:
            if int(p.get("round")) in self._open_tally_rounds:
                return
        except (TypeError, ValueError):
            pass
        groups = [{"answerId": str(o.get("id") or ""), "statement": str(o.get("summary") or ""),
                   "seatIds": [self._sid(s) for s in (o.get("holders") or [])]}
                  for o in (p.get("options") or []) if isinstance(o, dict)]
        self._post_tally({"round": p.get("round")}, groups, p.get("leading_option_id"), p.get("converged"))

    def _on_chair_started(self, p: dict) -> None:
        """The deciding vote: that seat shows "thinking..." and writes the answer turn."""
        if p.get("seat_no") is None:
            return
        self._decider = self._sid(p["seat_no"])
        self._think(self._decider, str(p.get("call_id") or "decider"), True)

    def _on_decision_final(self, p: dict) -> None:
        self._decision = p.get("decision") or {}
        self._stop_all_thinking()
        self._answer(str(self._decision.get("final_text") or ""))

    def _answer(self, text: str, error: str = "") -> None:
        if self._answer_turn is not None or not (text or error):
            return
        lead = next((g for g in (self._tally or {}).get("groups", [])
                     if g["answerId"] == self._tally["leading"] and g["seatIds"]), None)
        writer = lead["seatIds"][0] if lead else seat_id(min(self._seats, default=1))
        if self._decider and self._decision.get("outcome") == "chair":
            writer = self._decider  # no agreement: the seat that cast the deciding vote wrote it
        self._answer_turn = "answer"
        self._turns["answer"] = {"seat": writer, "to": "all", "text": "", "done": False}
        self._emit("turn.started", turnId="answer", seatId=writer, round=max(self._round, 0),
                   kind="answer", to="all")
        self._end_turn("answer", text, error)

    def _release(self, outcome: str, text: str, error: str = "") -> None:
        if self._released:
            return
        self._released = True
        self._stop_all_thinking()
        for turn_id in [t for t, turn in self._turns.items() if not turn["done"]]:
            self._end_turn(turn_id, "", "stopped")
        self._answer(text, error or ("" if text else "no answer"))
        tally = self._tally or {}
        dissent = [self._last_turn[s] for g in tally.get("groups", []) if g["answerId"] != tally["leading"]
                   for s in g["seatIds"] if s in self._last_turn]
        self._emit("answer.released", outcome=outcome, turnId=self._answer_turn,
                   tallyRound=tally.get("round", max(self._round, 0)),
                   rounds=int(self._decision.get("rounds_run") or 0) or self._rounds_started,
                   elapsedMs=self._clock, dissentTurnIds=dissent)
        self._set_phase("released")

    def _on_run_completed(self, p: dict) -> None:
        self._decision = self._decision or p.get("decision") or {}
        outcome = p.get("outcome") or self._decision.get("outcome")
        agreed = outcome == "consensus" or (not outcome and bool((self._tally or {}).get("reached")))
        text = str(p.get("final_text") or self._decision.get("final_text") or "")
        self._release("agreed" if agreed else "no-consensus", text)

    def _on_run_failed(self, p: dict) -> None:
        self._release("stopped", "", str(p.get("error") or "failed"))

    def _on_run_cancelled(self, p: dict) -> None:
        self._release("stopped", "", str(p.get("reason") or "stopped"))


def table_snapshot(ui_events: list[dict]) -> dict:
    """The table view from the UI stream alone: seatId -> {"note", "thinking", "lie", "mark"}.

    note: the seat's newest card text (None before its first); thinking: show "thinking..."
    in place of the note; lie: {"score", "level"} of its newest message; mark: "agrees" /
    "differs" at the last tally, cleared when the next round starts.
    """
    table: dict[str, dict] = {}

    def row(sid: Any) -> dict:
        return table.setdefault(str(sid), {"note": None, "thinking": False, "lie": None, "mark": None})

    for e in ui_events:
        kind = e.get("type")
        if kind == "debate.created":
            for seat in e.get("seats", []):
                row(seat["id"])
        elif kind == "summary.posted":
            row(e["seatId"])["note"] = e["text"]
        elif kind == "seat.thinking":
            row(e["seatId"])["thinking"] = bool(e["on"])
        elif kind == "lie.posted":
            row(e["seatId"])["lie"] = {"score": e["score"], "level": e["level"]}
        elif kind == "round.started":
            for seat in table.values():
                seat["mark"] = None
        elif kind == "tally.posted":
            for seat in table.values():
                seat["mark"] = None
            for group in e.get("groups", []):
                for sid in group.get("seatIds", []):
                    row(sid)["mark"] = "agrees" if group.get("answerId") == e.get("leading") else "differs"
    return table


__all__ = ["UiBridge", "table_snapshot", "seat_id", "short_name", "seat_names", "clip", "needed", "epoch",
           "NOTE_MAX", "SHORT_NAME_MAX", "STATE_TO_PHASE"]
