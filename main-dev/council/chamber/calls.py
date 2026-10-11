"""Builders for chamber model calls (spec 10.3, 10.4, 10.9, 25).

Each builder returns a CallSpec. The engine runs it through the gateway.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

from council.chamber.prompts import render, with_notes
from council.core.schemas import (
    Ballot,
    CallSpec,
    Critique,
    Draft,
    ModeConfig,
    SeatAssignment,
)

_SEAT_ROUNDS = ("r0", "r1", "r2", "r3")


# --------------------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------------------


def _enum_or_string(values: list[str]) -> dict[str, Any]:
    """Enum of values when there are any, else a free string."""
    if values:
        return {"type": "string", "enum": list(values)}
    return {"type": "string"}


def _resolve(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    """Follow a local $ref (or a single-entry allOf) to the definition it names."""
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        return schema["$defs"][name]
    if "allOf" in node and len(node["allOf"]) == 1:
        return _resolve(schema, node["allOf"][0])
    return node


def draft_schema() -> dict[str, Any]:
    return Draft.model_json_schema()


def critique_schema(labels: list[str], allowed_refs: list[str]) -> dict[str, Any]:
    schema = copy.deepcopy(Critique.model_json_schema())
    props = schema["properties"]

    reviews_items = _resolve(schema, props["reviews"]["items"])
    review_props = reviews_items["properties"]
    review_props["target"] = {**_enum_or_string(labels), "title": "Target"}

    positions = ["keep", "revise"] + [f"adopt:{x}" for x in labels]
    props["position"] = {
        **_enum_or_string(positions),
        "title": "Position",
        "default": "keep",
    }

    props["changed_because"] = {
        "type": "array",
        "items": _enum_or_string(allowed_refs),
        "title": "Changed Because",
    }
    return schema


def ballot_schema(option_ids: list[str], crux_ids: list[str], allowed_refs: list[str]) -> dict[str, Any]:
    schema = copy.deepcopy(Ballot.model_json_schema())
    props = schema["properties"]

    props["choice"] = {**_enum_or_string(option_ids), "title": "Choice"}
    props["ranking"] = {
        "type": "array",
        "items": _enum_or_string(option_ids),
        "title": "Ranking",
    }
    props["changed_because"] = {
        "type": "array",
        "items": _enum_or_string(allowed_refs),
        "title": "Changed Because",
    }

    if crux_ids:
        vote = _resolve(schema, props["crux_votes"]["items"])
        vote["properties"]["crux_id"] = {**_enum_or_string(crux_ids), "title": "Crux Id"}
    return schema


# --------------------------------------------------------------------------------------
# Call builders
# --------------------------------------------------------------------------------------


_JSON_ONLY = "Reply with the JSON object only."

# (output requirement, final line) per call kind. The final line is for reasoning-only models: the last
# thing they read is the instruction to do the job on the TASK.
_FRAME_PARTS: dict[str, tuple[str, str]] = {
    "r0": (
        _JSON_ONLY + ' The "answer" field must hold the actual answer to the TASK itself, '
        "not a plan for how you will answer and not a description of what an answer would contain. "
        "Also fill summary, claims, assumptions, risks, confidence, would_change_mind and user_questions.",
        "Now answer the TASK.",
    ),
    "r1": (
        _JSON_ONLY + " Fields: reviews, checks_requested, position, changed_because.",
        "Now review the other drafts and state your position on the TASK.",
    ),
    "r2": (
        _JSON_ONLY + ' Fields: choice, ranking, final_answer, confidence, blocking_objection, lesson. '
        'The "final_answer" field holds the actual final answer to the TASK.',
        "Now rank the options and give your final answer to the TASK.",
    ),
    "r3": (
        _JSON_ONLY + ' Fields: choice, ranking, final_answer, confidence, crux_votes, changed_because. '
        'The "final_answer" field holds the actual final answer to the TASK.',
        "Now rank the options and give your final answer to the TASK.",
    ),
    "chair": (_JSON_ONLY, "Now decide the TASK as chair."),
    "ratify": (_JSON_ONLY, "Now judge the final text against the TASK."),
}


def _user_message(template: str, task: str, body_vars: dict) -> str:
    """TASK first (in full), then the round instructions, then the output requirement, then one last line."""
    body_vars = body_vars or {}
    output_rule, closing = _FRAME_PARTS.get(template, (_JSON_ONLY, "Now answer the TASK."))
    return render(
        "user_frame",
        task=task or body_vars.get("task"),
        instructions=render(template, **body_vars),
        output_rule=output_rule,
        closing=closing,
    )


def _cap(caps: dict, key: str, default: Any = None) -> Any:
    value = caps.get(key, default) if caps else default
    return value


def _build(
    purpose: str,
    call_name: str,
    run_id: str,
    seat: SeatAssignment,
    template: str,
    task: str,
    brief: str,
    record: str,
    lens_text: str,
    body_vars: dict,
    schema: Optional[dict],
    mode: ModeConfig,
    caps: dict,
    seed: int,
    notes: str = "",
) -> CallSpec:
    system = render(
        "seat_system",
        lens_text=lens_text,
        task=task,
        workspace_brief=brief,
        council_record=record,
    )
    system = with_notes(system, notes)
    user = _user_message(template, task, body_vars)

    max_out = _cap(caps, "max_output", 1024)
    max_reason = _cap(caps, "max_reasoning", None)
    reasoning = mode.reasoning
    if max_reason == 0:
        reasoning = "off"

    return CallSpec(
        model_id=seat.model_id,
        call_id=f"{run_id}:{call_name}:{seat.seat_no}",
        run_id=run_id,
        purpose=purpose,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        json_schema=schema,
        reasoning=reasoning,
        max_output_tokens=int(max_out),
        max_reasoning_tokens=None if max_reason is None else int(max_reason),
        temperature=_cap(caps, "temperature", None),
        seed=seed,
        priority="interactive",
        stream=True,
        meta={"seat_no": seat.seat_no, "round": call_name, "lens": seat.lens},
    )


def build_seat_call(
    round_name: str,
    run_id: str,
    seat: SeatAssignment,
    task: str,
    brief: str,
    record: str,
    lens_text: str,
    body_vars: dict,
    schema: dict,
    mode: ModeConfig,
    caps: dict,
    seed: int,
    notes: str = "",
) -> CallSpec:
    """`notes` (27.6 effect 1) is appended to the seat system prompt after the council record."""
    return _build(
        f"seat.{round_name}", round_name, run_id, seat, round_name,
        task, brief, record, lens_text, body_vars, schema, mode, caps, seed, notes,
    )


def build_chair_call(
    run_id: str,
    seat: SeatAssignment,
    task: str,
    brief: str,
    record: str,
    lens_text: str,
    body_vars: dict,
    schema: Optional[dict],
    mode: ModeConfig,
    caps: dict,
    seed: int,
) -> CallSpec:
    return _build(
        "chair", "chair", run_id, seat, "chair",
        task, brief, record, lens_text, body_vars, schema, mode, caps, seed,
    )


def build_ratify_call(
    run_id: str,
    seat: SeatAssignment,
    task: str,
    brief: str,
    record: str,
    lens_text: str,
    body_vars: dict,
    schema: Optional[dict],
    mode: ModeConfig,
    caps: dict,
    seed: int,
) -> CallSpec:
    return _build(
        "ratify", "ratify", run_id, seat, "ratify",
        task, brief, record, lens_text, body_vars, schema, mode, caps, seed,
    )


def parse_position(position: str) -> tuple[str, str | None]:
    """"keep" -> ("keep", None); "adopt:B" -> ("adopt", "B"); anything else is returned lowercased."""
    text = (position or "").strip()
    if not text:
        return ("keep", None)
    if ":" in text:
        head, _, tail = text.partition(":")
        head = head.strip().lower()
        tail = tail.strip()
        if head == "adopt" and tail:
            return ("adopt", tail)
        return (head, tail or None)
    return (text.lower(), None)


__all__ = [
    "draft_schema",
    "critique_schema",
    "ballot_schema",
    "build_seat_call",
    "build_chair_call",
    "build_ratify_call",
    "parse_position",
]
