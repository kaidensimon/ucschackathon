"""Chronicle rules of evidence (spec 15.4 step 4, 15.5, 15.7). Pure functions, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from council.core.schemas import ChronicleEntry, MemoryVerdict

SOURCE_KINDS = (
    "explicit_rule",
    "single_choice",
    "repeat_pattern",
    "override",
    "inferred",
    "contradiction",
    "task_only",
)

_TARGETED = ("merge", "supersede", "contest")


@dataclass
class RuleOutcome:
    action: str
    status: Optional[str]
    confidence: float
    scope_hint: Optional[str]
    note: str


def _split(action: str) -> tuple[str, Optional[str]]:
    word, sep, target = (action or "").partition(":")
    word = word.strip()
    target = target.strip()
    return word, (target if sep and target else None)


def _norm(action: str) -> Optional[str]:
    """Canonical form for voting. Targeted actions without a target are invalid (None)."""
    word, target = _split(action)
    if word in _TARGETED:
        return f"{word}:{target}" if target else None
    if word in ("reject", "provisional", "adopt"):
        return word
    return None


def panel_decision(verdicts: list[MemoryVerdict]) -> str:
    """Action backed by at least 2 of 3 verdicts, else "reject"."""
    counts: dict[str, int] = {}
    for v in verdicts:
        key = _norm(v.action)
        if key is not None:
            counts[key] = counts.get(key, 0) + 1
    for key, n in counts.items():
        if n >= 2:
            return key
    return "reject"


def _reject(note: str) -> RuleOutcome:
    return RuleOutcome("reject", None, 0.0, None, note)


def apply_rules(source_kind: str, panel_action: str, related: list[ChronicleEntry]) -> RuleOutcome:
    """Cap the panel action by the rules of evidence (15.5)."""
    if source_kind not in SOURCE_KINDS:
        raise ValueError(f"unknown source_kind: {source_kind!r}")

    word, target = _split(panel_action)
    if word not in ("reject", "provisional", "adopt") + _TARGETED:
        word, target = "reject", None
    if word in _TARGETED and not target:
        word = "reject"

    if source_kind == "task_only":
        return _reject("applies to current task only; stays in run record")

    if source_kind == "contradiction":
        active = [e for e in related if e.status == "active"]
        if not active and word != "contest":
            return _reject("no active entry contradicted")
        tid = target if (word == "contest" and target) else active[0].id
        return RuleOutcome(
            f"contest:{tid}", "contested", 0.5, None,
            "contradicts active entry; both contested; question queued for user",
        )

    if word == "reject":
        return _reject("panel rejected; rules only cap, never force")

    if word == "contest":
        return RuleOutcome(f"contest:{target}", "contested", 0.5, None, "panel contest")

    full = f"{word}:{target}" if target else word

    if source_kind == "explicit_rule":
        return RuleOutcome(full, "active", 0.9, None, "standing rule in user words; store quote")

    if source_kind == "single_choice":
        act = full if word == "merge" else "provisional"
        return RuleOutcome(act, "provisional", 0.5, "project", "single choice; provisional, project scope")

    if source_kind == "repeat_pattern":
        act = full if word == "merge" else "adopt"
        return RuleOutcome(act, "active", 0.8, None, "pattern seen again in another run; promoted to active")

    if source_kind == "override":
        return RuleOutcome(
            "provisional", "provisional", 0.5, None,
            "user override; provisional lesson; count against entries behind the decision",
        )

    # inferred
    return RuleOutcome("provisional", "provisional", 0.3, None, "inferred only; provisional low confidence")


def age(
    entry: ChronicleEntry,
    runs_since_confirmed: int,
    decay: float = 0.9,
    retract_below: float = 0.3,
) -> ChronicleEntry:
    """Return a copy with decayed confidence, retracted below the threshold (15.7)."""
    if runs_since_confirmed < entry.review_after:
        return entry.model_copy(deep=True)
    conf = entry.confidence * decay
    updates: dict = {"confidence": conf}
    if conf < retract_below:
        updates["status"] = "retracted"
    return entry.model_copy(update=updates, deep=True)


__all__ = ["SOURCE_KINDS", "RuleOutcome", "panel_decision", "apply_rules", "age"]
