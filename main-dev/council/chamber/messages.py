"""Open council messages: the shared transcript, the short note cards and the tally.

Protocol (decided by the user, replaces the blind anonymised JSON rounds):
  - every member writes free text; all of it is shared with the whole council, by name;
  - every message says whom it addresses ("all" or named seats); everyone still sees it;
  - every message carries a lie-detector metric computed by the engine;
  - after its text each member gives a small structured card (short note + vote fields);
  - chat view = full messages, table view = only the cards ("thinking..." while a call runs).

Pure module: no I/O, no clock, no randomness.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Literal, Union

from pydantic import BaseModel, Field, field_validator

NOTE_MAX = 55
STANCE_MAX = 160
BECAUSE_MAX = 160
KEY_MAX = 80
# Answer types the benchmark grades by key. For these the table groups seats by answer_key.
KEYED_TYPES = ("mcq", "numeric", "exact")
NEW = "new"
ALL = "all"

To = Union[Literal["all"], list[str]]


# --------------------------------------------------------------------------- text helpers


def _squash(text: Any) -> str:
    """One line, single spaces."""
    return " ".join(str(text or "").split())


def clip(text: Any, limit: int) -> str:
    """Squash whitespace and cut to `limit` characters at a word boundary. No ellipsis."""
    s = _squash(text)
    if len(s) <= limit:
        return s
    if limit <= 0:
        return ""
    cut = s[:limit]
    if s[limit] != " ":
        space = cut.rfind(" ")
        if space > 0:
            cut = cut[:space]
    return cut.rstrip(" ,;:-")


# Same pattern as council.bench.solo._ANSWER_LINE (kept here: this module must stay pure).
_ANSWER_LINE = re.compile(r"^\W*answer\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def last_answer_line(text: Any) -> str | None:
    """The value of the last "ANSWER: x" line of a message, as bench/solo.py reads it."""
    if not text:
        return None
    found = _ANSWER_LINE.findall(str(text))
    return found[-1].strip() if found else None


def _first_sentence(text: str) -> str:
    for line in str(text or "").splitlines():
        line = _squash(line)
        if not line:
            continue
        parts = re.split(r"(?<=[.!?])\s+", line, maxsplit=1)
        return parts[0]
    return ""


# --------------------------------------------------------------------------- types


class LieMetric(BaseModel):
    """0 = likely false .. 1 = likely true. None = could not be measured."""

    score: float | None = None
    level: Literal["ok", "watch", "flag"] = "ok"
    reasons: list[str] = Field(default_factory=list)


class Card(BaseModel):
    """The member's own short note of what it just said, plus the vote fields."""

    note: str
    to: To = ALL
    stance: str
    backs: str = NEW
    confidence: float = 0.5
    changed: bool = False
    changed_because: str = ""
    answer_key: str = ""  # benchmark tasks only: the letter, number or short answer

    @field_validator("answer_key", mode="before")
    @classmethod
    def _clip_key(cls, v: Any) -> str:
        return clip(v, KEY_MAX)

    @field_validator("note", mode="before")
    @classmethod
    def _clip_note(cls, v: Any) -> str:
        return clip(v, NOTE_MAX)

    @field_validator("stance", mode="before")
    @classmethod
    def _clip_stance(cls, v: Any) -> str:
        return clip(v, STANCE_MAX)

    @field_validator("changed_because", mode="before")
    @classmethod
    def _clip_because(cls, v: Any) -> str:
        return clip(v, BECAUSE_MAX)

    @field_validator("confidence", mode="after")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        if v != v:  # NaN
            return 0.5
        return min(1.0, max(0.0, v))

    @field_validator("to", mode="after")
    @classmethod
    def _empty_to_all(cls, v: To) -> To:
        return v if v else ALL


class CouncilMessage(BaseModel):
    turn_id: str
    seat_id: str
    seat_no: int
    name: str
    round: int
    kind: Literal["position", "reply", "answer", "dissent"] = "reply"
    to: To = ALL
    text: str = ""
    card: Card | None = None
    lie: LieMetric | None = None
    thinking: bool = False
    done: bool = False


class TableAnswer(BaseModel):
    id: str
    statement: str
    proposed_by: str
    seat_ids: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- card call


def card_schema(seat_ids: list[str], answer_ids: list[str], answer_type: str | None = None) -> dict:
    """JSON schema for the card call. `seat_ids` = the OTHER seats this member may address.

    A keyed `answer_type` (mcq, numeric, exact) adds the required field "answer_key".
    """
    schema = _card_schema(seat_ids, answer_ids)
    if answer_type in KEYED_TYPES:
        key: dict = {"type": "string", "minLength": 1, "maxLength": KEY_MAX}
        if answer_type == "mcq":
            key = {"type": "string", "minLength": 1, "maxLength": 1}
        schema["properties"]["answer_key"] = key
        schema["required"].append("answer_key")
    return schema


def _card_schema(seat_ids: list[str], answer_ids: list[str]) -> dict:
    seats = list(dict.fromkeys(seat_ids))
    backs = list(dict.fromkeys([*answer_ids, NEW]))
    if seats:
        to_schema: dict = {
            "anyOf": [
                {"type": "string", "enum": [ALL]},
                {
                    "type": "array",
                    "items": {"type": "string", "enum": seats},
                    "minItems": 1,
                    "maxItems": len(seats),
                    "uniqueItems": True,
                },
            ]
        }
    else:
        to_schema = {"type": "string", "enum": [ALL]}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "note": {"type": "string", "minLength": 1, "maxLength": NOTE_MAX},
            "to": to_schema,
            "stance": {"type": "string", "minLength": 1, "maxLength": STANCE_MAX},
            "backs": {"type": "string", "enum": backs},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "changed": {"type": "boolean"},
            "changed_because": {"type": "string", "maxLength": BECAUSE_MAX},
        },
        "required": ["note", "to", "stance", "backs", "confidence", "changed", "changed_because"],
    }


def _load(data: Any) -> dict | None:
    if isinstance(data, dict):
        return data
    if not isinstance(data, str):
        return None
    s = data.strip()
    try:
        obj = json.loads(s)
    except ValueError:
        start, end = s.find("{"), s.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            obj = json.loads(s[start : end + 1])
        except ValueError:
            return None
    return obj if isinstance(obj, dict) else None


def _match(value: Any, known: list[str]) -> str | None:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    s = str(value).strip()
    if s in known:
        return s
    low = s.lower()
    for k in known:
        if k.lower() == low:
            return k
    return None


def _parse_to(value: Any, seat_ids: list[str]) -> To:
    if isinstance(value, str):
        items: list[Any] = [p for p in re.split(r"[,;]", value)]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        return ALL
    out: list[str] = []
    for item in items:
        hit = _match(item, seat_ids)
        if hit is not None and hit not in out:
            out.append(hit)
    return out or ALL


def _parse_confidence(value: Any) -> float:
    if isinstance(value, bool):
        return 0.5
    if isinstance(value, str):
        s = value.strip()
        pct = s.endswith("%")
        try:
            value = float(s.rstrip("%").strip())
        except ValueError:
            return 0.5
        if pct:
            value = value / 100.0
    if not isinstance(value, (int, float)) or value != value:
        return 0.5
    v = float(value)
    if 1.0 < v <= 100.0:
        v = v / 100.0
    return min(1.0, max(0.0, v))


def _parse_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "y", "1")
    return bool(value) if isinstance(value, (bool, int)) else False


def parse_card(data: dict | str | None, seat_ids: list[str], answer_ids: list[str]) -> Card | None:
    """Tolerant read of the card call's output. None when there is nothing usable."""
    obj = _load(data)
    if obj is None:
        return None
    note = clip(obj.get("note") if isinstance(obj.get("note"), (str, int, float)) else "", NOTE_MAX)
    stance = clip(obj.get("stance") if isinstance(obj.get("stance"), (str, int, float)) else "", STANCE_MAX)
    if not note and not stance:
        return None
    if not note:
        note = clip(_first_sentence(stance), NOTE_MAX)
    if not stance:
        stance = note
    because = obj.get("changed_because")
    key = obj.get("answer_key")
    return Card(
        note=note,
        to=_parse_to(obj.get("to"), list(seat_ids)),
        stance=stance,
        backs=_match(obj.get("backs"), list(answer_ids)) or NEW,
        confidence=_parse_confidence(obj.get("confidence", 0.5)),
        changed=_parse_bool(obj.get("changed", False)),
        changed_because=because if isinstance(because, str) else "",
        answer_key=key if isinstance(key, (str, int, float)) and not isinstance(key, bool) else "",
    )


def fallback_card(text: str) -> Card:
    """Engine-made card for when the card call fails."""
    body = _squash(text)
    note = clip(_first_sentence(text), NOTE_MAX) or "(no text)"
    return Card(note=note, to=ALL, stance=body[:STANCE_MAX].rstrip() or note, backs=NEW)


# --------------------------------------------------------------------------- transcript


def _to_of(m: CouncilMessage) -> To:
    """Whom a message addresses: its own `to`, else what its card says."""
    if isinstance(m.to, list) and m.to:
        return m.to
    if m.card is not None and isinstance(m.card.to, list) and m.card.to:
        return m.card.to
    return ALL


def _num(x: float) -> str:
    return f"{round(x, 2):g}"


def _lie_words(lie: LieMetric | None) -> str:
    if lie is None or lie.score is None:
        base = "n/a"
        if lie is None or lie.level == "ok":
            return f"(lie detector: {base})"
    else:
        base = f"{lie.score:.2f}"
    level = "FLAG" if lie.level == "flag" else lie.level
    reasons = "; ".join(_squash(r) for r in lie.reasons if _squash(r))
    if reasons and lie.level != "ok":
        return f"(lie detector: {base} {level}: {reasons})"
    return f"(lie detector: {base} {level})"


def _header(m: CouncilMessage, names: dict[str, str], viewer: str | None) -> str:
    who = "YOU" if viewer is not None and m.seat_id == viewer else m.name
    to = _to_of(m)
    if to == ALL:
        target = ALL
    else:
        target = ", ".join("YOU" if viewer is not None and s == viewer else names.get(s, s) for s in to)
    return f"[round {m.round}] {who} -> {target}   {_lie_words(m.lie)}"


def _note_line(card: Card | None) -> str:
    if card is None:
        return "note: (none yet)"
    return f"note: {card.note} | backs {card.backs} | confidence {_num(card.confidence)}"


def transcript_text(
    messages: list[CouncilMessage],
    viewer_seat: str | None = None,
    max_chars: int = 24000,
) -> str:
    """The debate so far as every member reads it. Old rounds shrink to cards when too long."""
    shown = [m for m in messages if m.text.strip() or m.card is not None]
    if not shown:
        return ""
    names = {m.seat_id: m.name for m in messages}
    rounds = sorted({m.round for m in shown})

    def render(compact: set[int]) -> str:
        blocks = []
        for m in shown:
            lines = [_header(m, names, viewer_seat)]
            if m.round not in compact and m.text.strip():
                lines.append(m.text.strip())
            lines.append(_note_line(m.card))
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    compact: set[int] = set()
    out = render(compact)
    for r in rounds[:-1]:  # never the last round
        if len(out) <= max_chars:
            break
        compact.add(r)
        out = render(compact)
    return out


def addressed_to(messages: list[CouncilMessage], seat_id: str, since_round: int) -> list[CouncilMessage]:
    """Messages (round >= since_round) addressed to `seat_id` by name and not answered yet.

    Answered = the seat wrote a later message whose "to" names the asker.
    """
    out: list[CouncilMessage] = []
    for i, m in enumerate(messages):
        if m.round < since_round or m.seat_id == seat_id:
            continue
        to = _to_of(m)
        if to == ALL or seat_id not in to:
            continue
        answered = False
        for later in messages[i + 1 :]:
            if later.seat_id != seat_id or (later.thinking and not later.text):
                continue
            later_to = _to_of(later)
            if later_to != ALL and m.seat_id in later_to:
                answered = True
                break
        if not answered:
            out.append(m)
    return out


def questions_to(messages: list[CouncilMessage], seat_id: str, since_round: int) -> list[CouncilMessage]:
    """Every message with text (round >= since_round) that another seat addressed to `seat_id` by name.

    Unlike addressed_to() nothing is left out as answered: a member under questioning is shown
    all that was put to it since its last message.
    """
    out: list[CouncilMessage] = []
    for m in messages:
        if m.round < since_round or m.seat_id == seat_id or not m.text.strip():
            continue
        to = _to_of(m)
        if to != ALL and seat_id in to:
            out.append(m)
    return out


# --------------------------------------------------------------------------- views


def table_view(messages: list[CouncilMessage], seat_ids: list[str]) -> dict[str, dict]:
    """Per seat, only the card. `thinking` = its newest turn is still running."""
    view: dict[str, dict] = {}
    for seat in seat_ids:
        mine = [m for m in messages if m.seat_id == seat]
        last = mine[-1] if mine else None
        carded = next((m for m in reversed(mine) if m.card is not None), None)
        card = carded.card if carded is not None else None
        view[seat] = {
            "note": card.note if card is not None else None,
            "thinking": bool(last is not None and (last.thinking or not last.done)),
            "to": (list(card.to) if isinstance(card.to, list) else ALL) if card is not None else None,
            "backs": card.backs if card is not None else None,
            "lie": carded.lie.model_dump(mode="json") if carded is not None and carded.lie is not None else None,
            "round": last.round if last is not None else None,
        }
    return view


def chat_view(messages: list[CouncilMessage]) -> list[dict]:
    """Full messages in order, JSON-safe."""
    return [m.model_dump(mode="json") for m in messages]


# --------------------------------------------------------------------------- votes


def tally(
    answers: list[TableAnswer],
    latest_cards: dict[str, Card],
    n_seats: int,
    threshold: float = 0.8,
) -> dict:
    """Count seats per answer from their latest cards. Seats with no card back nothing."""
    ids = [a.id for a in answers]
    held: dict[str, list[str]] = {a.id: [] for a in answers}
    for seat, card in latest_cards.items():
        if card is None:
            continue
        target = card.backs if card.backs in held else None
        if target is None:  # "new": apply_card already put the seat on its answer
            target = next((a.id for a in answers if seat in a.seat_ids), None)
        if target is not None and seat not in held[target]:
            held[target].append(seat)
    groups = [
        {"answer_id": a.id, "statement": a.statement, "seat_ids": held[a.id]}
        for a in answers
        if held[a.id]
    ]
    groups.sort(key=lambda g: (-len(g["seat_ids"]), ids.index(g["answer_id"])))
    agree = len(groups[0]["seat_ids"]) if groups else 0
    needed = int(math.ceil(round(threshold * n_seats, 9)))
    return {
        "groups": groups,
        "leading": groups[0]["answer_id"] if groups else "",
        "agree": agree,
        "seats": n_seats,
        "needed": needed,
        "reached": n_seats > 0 and agree >= needed,
    }


def _next_id(answers: list[TableAnswer]) -> str:
    top = 0
    for a in answers:
        m = re.fullmatch(r"A(\d+)", a.id)
        if m:
            top = max(top, int(m.group(1)))
    return f"A{max(top, len(answers)) + 1}"


def apply_card(answers: list[TableAnswer], seat_id: str, card: Card) -> list[TableAnswer]:
    """Move the seat to the answer its card backs. Returns a new list; input untouched."""
    out = [a.model_copy(update={"seat_ids": [s for s in a.seat_ids if s != seat_id]}) for a in answers]
    target = next((a for a in out if a.id == card.backs), None)
    if target is None:
        # "new" with the very words of an answer already on the table: same answer, no churn.
        key = _squash(card.stance).lower()
        target = next((a for a in out if _squash(a.statement).lower() == key), None)
    if target is None:
        out.append(
            TableAnswer(id=_next_id(answers), statement=card.stance, proposed_by=seat_id, seat_ids=[seat_id])
        )
    else:
        target.seat_ids.append(seat_id)
    kept = [a for a in out if a.seat_ids]
    return kept if kept else out[:1]
