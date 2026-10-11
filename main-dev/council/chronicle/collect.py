"""Chronicle step 1 (spec 15.4): collect candidate observations from one run. Pure, no I/O."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

from council.chronicle.explicit import find_rules
from council.core.schemas import EvidenceRef, Event, MemoryCandidate

_RULE_RE = re.compile(r"\b(always|never|from now on|do not ever|every time)\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9]+")
_SIM_LIMIT = 0.85
_QUOTE_MAX = 240
_STRENGTH = {
    "user": 7,
    "explicit_rule": 6,
    "contradiction": 5,
    "override": 4,
    "single_choice": 3,
    "inferred": 1,
}
_KIND_HINT = {
    "user": "preference",
    "explicit_rule": "preference",
    "single_choice": "preference",
    "override": "lesson",
    "inferred": "lesson",
    "contradiction": "lesson",
}


def _is_rule(text: str) -> bool:
    return bool(_RULE_RE.search(text or ""))


def _s(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def _quote(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= _QUOTE_MAX else text[: _QUOTE_MAX - 3] + "..."


def _norm(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def _make_id(source_kind: str, text: str) -> str:
    key = source_kind + "|" + " ".join(_norm(text))
    return "mc_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _cand(
    text: str, source_kind: str, run_id: str, seq: Optional[int], quote: str, scope_hint: Optional[str] = None
) -> MemoryCandidate:
    text = " ".join((text or "").split())
    return MemoryCandidate(
        scope_hint=scope_hint,
        text=text,
        id=_make_id(source_kind, text),
        run_id=run_id or None,
        source=source_kind,
        kind_hint=_KIND_HINT.get(source_kind),
        evidence=[EvidenceRef(run_id=run_id or "", event_seq=seq, quote=_quote(quote or text))],
    )


def _similar(a: list[str], b: list[str]) -> bool:
    if a == b:
        return True
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return False
    return len(sa & sb) / len(sa | sb) >= _SIM_LIMIT


def _dedupe(cands: list[MemoryCandidate]) -> list[MemoryCandidate]:
    kept: list[MemoryCandidate] = []
    toks: list[list[str]] = []
    for c in cands:
        t = _norm(c.text)
        for i, k in enumerate(kept):
            if _similar(t, toks[i]):
                seen = {(e.run_id, e.event_seq, e.quote) for e in k.evidence}
                for e in c.evidence:
                    if (e.run_id, e.event_seq, e.quote) not in seen:
                        k.evidence.append(e)
                if _STRENGTH.get(c.source, 0) > _STRENGTH.get(k.source, 0):
                    k.source = c.source
                    k.kind_hint = c.kind_hint
                    k.id = _make_id(k.source, k.text)
                break
        else:
            kept.append(c)
            toks.append(t)
    return kept


def _d(v: Any) -> dict:
    if isinstance(v, dict):
        return v
    dump = getattr(v, "model_dump", None)
    return dump() if callable(dump) else {}


def collect_candidates(events: list[Event], task: str) -> list[MemoryCandidate]:
    """Extract candidate observations from one run's events and its task text."""
    events = list(events or [])
    run_id = next((e.run_id for e in events if e.run_id), "") or ""
    out: list[MemoryCandidate] = []

    questions: dict[str, str] = {}
    for e in events:
        if e.type == "user.input_requested":
            rid = _s(e.payload.get("request_id"))
            if rid:
                questions[rid] = _s(e.payload.get("question"))

    failures: dict[str, list[Event]] = {}

    for e in events:
        rid = e.run_id or run_id
        p = e.payload or {}
        t = e.type

        if t == "user.input_received":
            answer = _s(p.get("text")) or _s(p.get("choice"))
            if not answer:
                continue
            q = questions.get(_s(p.get("request_id")), "")
            if _is_rule(answer):
                out.append(_cand(answer, "explicit_rule", rid, e.seq, answer))
            else:
                body = f"When asked '{q}', the user answered: {answer}" if q else f"The user answered: {answer}"
                out.append(_cand(body, "single_choice", rid, e.seq, answer))

        elif t == "plan.drafted":
            marked = (
                bool(p.get("edited_by_user"))
                or p.get("by") == "user"
                or p.get("source") == "user"
                or p.get("edited_by") == "user"
            )
            if not marked:
                continue
            goal = _s(_d(p.get("plan")).get("goal")) or _s(p.get("note")) or "the plan"
            out.append(_cand(f"The user edited the plan for: {goal}", "single_choice", rid, e.seq, goal))

        elif t == "run.cancelled":
            reason = _s(p.get("reason"))
            body = f"The user cancelled the run: {_quote(task)}" + (f" ({reason})" if reason else "")
            out.append(_cand(body, "override", rid, e.seq, reason or task))

        elif t == "review.verdict":
            if p.get("overridden_by_user") or p.get("user_override") or p.get("overridden"):
                v = _s(p.get("verdict")) or "a verdict"
                reason = _s(p.get("reason"))
                body = f"The user overrode the review verdict '{v}'" + (f": {reason}" if reason else "")
                out.append(_cand(body, "override", rid, e.seq, reason or v))

        elif t == "ballot.cast":
            lesson = _s(_d(p.get("ballot")).get("lesson"))
            if lesson:
                out.append(_cand(lesson, "inferred", rid, e.seq, lesson))

        elif t == "task.failed":
            tid = _s(p.get("task_id"))
            if tid:
                failures.setdefault(tid, []).append(e)

        elif t == "decision.final":
            for dep in _d(p.get("decision")).get("departures") or []:
                dep = _d(dep)
                eid, why = _s(dep.get("chronicle_entry_id")), _s(dep.get("why"))
                if not eid and not why:
                    continue
                body = f"The council departed from record entry {eid}" + (f": {why}" if why else "")
                out.append(_cand(body, "contradiction", rid, e.seq, why or eid))

    for tid, evs in failures.items():
        worst = max(int(x.payload.get("attempts") or 0) for x in evs)
        if len(evs) < 2 and worst < 2:
            continue
        last = evs[-1]
        lp = last.payload
        title = _s(lp.get("title")) or tid
        cause = _s(lp.get("failing_check")) or _s(lp.get("reason")) or _s(lp.get("error_tail"))
        body = f"Task '{title}' failed repeatedly across attempts" + (f": {cause}" if cause else "")
        out.append(_cand(body, "inferred", last.run_id or run_id, last.seq, cause or title))

    # A standing rule in the user's task text is explicit: source "user" tells the Reflector
    # to store it without asking the panel (the user already said it).
    for rule in find_rules(task):
        hint = "global" if rule["scope"] == "user" else None
        out.append(_cand(rule["text"], "user", run_id, None, rule["text"], scope_hint=hint))

    return _dedupe(out)
