"""Chronicle reflection (spec 15.4 steps 2 to 5, 15.7).

Recall, judge with a blind panel of three, decide, commit. All I/O is injected:
the gateway makes the calls, the store keeps the entries, `emit` reports events.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Awaitable, Callable, Optional

from council.chamber.prompts import render
from council.chronicle import recall, rules
from council.core import event_types as E
from council.core.schemas import (
    CallSpec,
    ChronicleEntry,
    EvidenceRef,
    MemoryCandidate,
    MemoryVerdict,
)
from council.core.util import new_id

PURPOSE = "memory.judge"
USER_SOURCE = "user"  # candidate source for a standing rule the user stated: stored without a panel vote

# MemoryCandidate.source -> rules.SOURCE_KINDS. A source that is already a kind passes through.
_SOURCE_TO_KIND = {
    "user_choice": "single_choice",
    "plan_edit": "single_choice",
    "override": "override",
    "lesson": "inferred",
    "review_failure": "inferred",
    "departure": "inferred",
}
_STANDING = re.compile(r"\b(always|never|from now on)\b", re.IGNORECASE)
_JUDGE_ROLES = frozenset({"seat", "chair", "clerk", "worker", "senior_worker"})
_DEAD = ("superseded", "retracted")
_MERGE_BUMP = 0.05
_DUP_COSINE = 0.92
_DUP_JACCARD = 0.8
_WORDS = re.compile(r"\w+")

_SYSTEM = (
    "You are one member of a three-seat memory panel. You judge alone and do not see the other verdicts. "
    "Reply with the JSON object only."
)


def _cfg(cfg: Any, key: str, default: Any) -> Any:
    if cfg is None:
        return default
    if isinstance(cfg, dict):
        value = cfg.get(key, default)
    else:
        value = getattr(cfg, key, default)
    return default if value is None else value


def source_kind(candidate: MemoryCandidate, panel_action: str, related: list[ChronicleEntry]) -> str:
    """Map a candidate to a row of the rules of evidence (15.5)."""
    src = (candidate.source or "").strip()
    quotes = " ".join([candidate.text] + [ev.quote for ev in candidate.evidence])
    if src in rules.SOURCE_KINDS:
        kind = src
    elif src == "user_statement":
        kind = "explicit_rule" if _STANDING.search(quotes) else "inferred"
    else:
        kind = _SOURCE_TO_KIND.get(src, "inferred")
    if kind in ("explicit_rule", "task_only", "contradiction", "override"):
        return kind
    # The same pattern seen again in a different run promotes the entry it merges into.
    word, _, target = (panel_action or "").partition(":")
    if word == "merge" and target:
        seen = {ev.run_id for ev in candidate.evidence} | ({candidate.run_id} if candidate.run_id else set())
        for entry in related:
            if entry.id == target and any(ev.run_id not in seen for ev in entry.evidence):
                return "repeat_pattern"
    return kind


def _tokens(text: str) -> list[str]:
    return _WORDS.findall((text or "").lower())


def similarity(a: str, b: str, ea: list[float], eb: list[float]) -> float:
    """Duplicate score in [0, 1]: 1.0 for equal normalized text, else the larger of token Jaccard
    and embedding cosine, each counted only when it clears its duplicate threshold. 0.0 means distinct."""
    ta, tb = _tokens(a), _tokens(b)
    if ta and ta == tb:
        return 1.0
    best = 0.0
    sa, sb = set(ta), set(tb)
    if sa and sb:
        jac = len(sa & sb) / len(sa | sb)
        if jac >= _DUP_JACCARD:
            best = jac
    if ea and eb:
        cos = recall.cosine(ea, eb)
        if cos >= _DUP_COSINE:
            best = max(best, cos)
    return best


def verdict_schema(related_ids: list[str], project: str, categories: list[str]) -> dict[str, Any]:
    """MemoryVerdict schema with `action` and `scope` closed to the values that make sense here."""
    schema = MemoryVerdict.model_json_schema()
    props = schema.get("properties", {})
    actions = ["reject", "provisional", "adopt"]
    for word in ("merge", "supersede", "contest"):
        actions += [f"{word}:{rid}" for rid in related_ids]
    scopes = ([f"project:{project}"] if project else []) + ["global"]
    scopes += [f"category:{c}" for c in categories]
    if "action" in props:
        props["action"] = {"type": "string", "enum": actions}
    if "scope" in props:
        props["scope"] = {"type": "string", "enum": scopes}
    return schema


def _footprint(model: Any) -> float:
    measured = getattr(model, "measured", None)
    for value in (
        getattr(measured, "ram_gb_batch", None),
        getattr(measured, "ram_gb_live", None),
        getattr(model, "active_params_b", None),
        getattr(model, "params_b", None),
    ):
        if value is not None:
            return float(value)
    return float("inf")


def _lineup_ids(lineup: Any) -> list[str]:
    if lineup is None:
        return []
    seats = getattr(lineup, "seats", lineup)
    out: list[str] = []
    for seat in seats or []:
        mid = seat if isinstance(seat, str) else getattr(seat, "model_id", None)
        if mid and mid not in out:
            out.append(mid)
    return out


def pick_judges(registry: Any, lineup: Any, n: int = 3) -> list[str]:
    """`n` models from `n` labs, cheapest footprint first.

    Lineup models go first (they are already resident), the rest of the registry fills in.
    When there are fewer than `n` labs, labs repeat rather than leaving a seat empty.
    """
    models = list(registry.values()) if isinstance(registry, dict) else list(registry or [])
    eligible = []
    for m in models:
        if getattr(m, "status", "active") != "active":
            continue
        roles = set(getattr(m, "roles", None) or [])
        if roles and not (roles & _JUDGE_ROLES):
            continue
        eligible.append(m)
    in_lineup = set(_lineup_ids(lineup))
    order = sorted(eligible, key=lambda m: (m.id not in in_lineup, _footprint(m), m.id))

    picked: list[str] = []
    labs: set[str] = set()
    for m in order:
        if len(picked) >= n:
            break
        lab = getattr(m, "lab", "") or getattr(m, "lineage", "") or m.id
        if lab in labs:
            continue
        labs.add(lab)
        picked.append(m.id)
    for m in order:
        if len(picked) >= n:
            break
        if m.id not in picked:
            picked.append(m.id)
    return picked


class Reflector:
    def __init__(
        self,
        gateway: Any,
        store: Any,
        emit: Callable[[str, dict], None],
        embed: Callable[[list[str]], Awaitable[list[list[float]]]],
        cfg: Any,
        now: Callable[[], float],
    ) -> None:
        self.gateway = gateway
        self.store = store
        self.emit = emit
        self.embed = embed
        self.cfg = cfg
        self.now = now

    # ------------------------------------------------------------------ helpers

    async def _embed_one(self, text: str) -> list[float]:
        try:
            vectors = await self.embed([text])
            vec = vectors[0] if vectors else []
            return [float(x) for x in vec]
        except Exception:
            return recall.keyword_embedding(text)

    def _related(
        self,
        candidate: MemoryCandidate,
        entries: list[ChronicleEntry],
        query: list[float],
        project: str,
        categories: list[str],
    ) -> list[ChronicleEntry]:
        k = int(_cfg(self.cfg, "recall_k", 8))
        related = recall.rank(entries, query, project or None, categories, k=k)
        have = {e.id for e in related}
        for entry in entries:
            if entry.id in candidate.related_entry_ids and entry.id not in have and entry.status not in _DEAD:
                related.append(entry)
                have.add(entry.id)
        return related

    def _spec(
        self,
        run_id: str,
        candidate: MemoryCandidate,
        seat_no: int,
        model_id: str,
        related: list[ChronicleEntry],
        schema: dict[str, Any],
    ) -> CallSpec:
        quotes = [ev.quote for ev in candidate.evidence if ev.quote] or [candidate.text]
        lines = [f"{e.id} [{e.status.upper()} {e.confidence:.2f}] {e.statement}" for e in related]
        user = render(
            "memory_judge",
            candidate=candidate.text,
            quotes=" | ".join(quotes),
            related="\n".join(lines) if lines else "(none)",
        )
        return CallSpec(
            model_id=model_id,
            call_id=f"{run_id}:memory.judge:{candidate.id}:{seat_no}",
            run_id=run_id,
            purpose=PURPOSE,
            messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            json_schema=schema,
            reasoning="off",
            max_output_tokens=512,
            priority="batch",
            stream=False,
            meta={"seat_no": seat_no, "candidate_id": candidate.id},
        )

    async def _judge(
        self,
        run_id: str,
        candidate: MemoryCandidate,
        judge_models: list[str],
        related: list[ChronicleEntry],
        project: str,
        categories: list[str],
    ) -> list[MemoryVerdict]:
        schema = verdict_schema([e.id for e in related], project, categories)
        specs = [
            self._spec(run_id, candidate, i, model_id, related, schema)
            for i, model_id in enumerate(judge_models)
        ]
        results = await asyncio.gather(*(self.gateway.call(s) for s in specs), return_exceptions=True)
        verdicts: list[MemoryVerdict] = []
        for seat_no, (model_id, res) in enumerate(zip(judge_models, results)):
            if isinstance(res, BaseException) or not getattr(res, "ok", False):
                continue
            try:
                verdict = MemoryVerdict.model_validate(res.parsed)
            except Exception:
                continue
            verdicts.append(verdict)
            self.emit(
                E.MEMORY_VERDICT,
                E.MemoryVerdictPayload(
                    candidate_id=candidate.id, seat_no=seat_no, model_id=model_id, verdict=verdict
                ).model_dump(),
            )
        return verdicts

    def _committed(self, entry: ChronicleEntry, candidate: MemoryCandidate, action: str, **extra: Any) -> None:
        self.emit(
            E.MEMORY_COMMITTED,
            E.MemoryCommittedPayload(entry=entry, candidate_id=candidate.id, action=action, **extra).model_dump(),
        )

    @staticmethod
    def _statement(candidate: MemoryCandidate, verdicts: list[MemoryVerdict], panel_action: str) -> str:
        backing = [v for v in verdicts if rules._norm(v.action) == panel_action] or verdicts
        statement = next((v.statement_rewrite.strip() for v in backing if v.statement_rewrite.strip()), "")
        return statement or candidate.text

    async def _find_duplicate(
        self,
        candidate: MemoryCandidate,
        statement: str,
        entries: list[ChronicleEntry],
        project: str,
        categories: list[str],
    ) -> Optional[ChronicleEntry]:
        """Closest live in-scope entry that says the same thing as the would-be new entry."""
        st_vec = await self._embed_one(statement)
        tx_vec = st_vec if candidate.text == statement else await self._embed_one(candidate.text)
        best: Optional[ChronicleEntry] = None
        best_score = 0.0
        for entry in entries:
            if entry.status not in ("active", "provisional"):
                continue
            if not recall.in_scope(entry, project or None, categories):
                continue
            score = max(
                similarity(statement, entry.statement, st_vec, entry.embedding),
                similarity(candidate.text, entry.statement, tx_vec, entry.embedding),
            )
            if score > best_score:
                best, best_score = entry, score
        return best

    async def _new_entry(
        self,
        run_id: str,
        candidate: MemoryCandidate,
        verdicts: list[MemoryVerdict],
        panel_action: str,
        outcome: rules.RuleOutcome,
        kind: str,
        project: str,
        status: str,
        supersedes: Optional[str] = None,
    ) -> ChronicleEntry:
        # The verdicts that carried the vote speak for the panel.
        backing = [v for v in verdicts if rules._norm(v.action) == panel_action] or verdicts
        statement = self._statement(candidate, verdicts, panel_action)
        reason = next((v.reason.strip() for v in backing if v.reason.strip()), "")
        kinds = [v.kind for v in backing]
        entry_kind = max(kinds, key=kinds.count) if kinds else (candidate.kind_hint or "lesson")

        # Project scope by default. Global only when the panel says so about an explicit rule.
        says_global = sum(1 for v in verdicts if v.scope == "global") >= 2
        if not project or (says_global and kind == "explicit_rule" and outcome.scope_hint != "project"):
            scope = "global"
        else:
            scope = f"project:{project}"

        evidence = [ev.model_copy() for ev in candidate.evidence]
        if not evidence:
            evidence = [EvidenceRef(run_id=candidate.run_id or run_id, quote=candidate.text)]
        ts = self.now()
        return ChronicleEntry(
            id=new_id("mem"),
            kind=entry_kind,
            scope=scope,
            statement=statement,
            rationale="; ".join(p for p in (reason, outcome.note) if p),
            evidence=evidence,
            status=status,
            confidence=outcome.confidence,
            support_count=1,
            created_at=ts,
            last_confirmed_at=ts,
            review_after=int(_cfg(self.cfg, "review_after_runs", 10)),
            supersedes=supersedes,
            votes=list(verdicts),
            embedding=await self._embed_one(statement),
        )

    # ------------------------------------------------------------------ reflect

    async def reflect(
        self,
        run_id: str,
        candidates: list[MemoryCandidate],
        judge_models: list[str],
        project: str,
        categories: list[str],
    ) -> list[ChronicleEntry]:
        """Judge each candidate and commit the result. Returns every entry written as committed."""
        written: list[ChronicleEntry] = []
        total = len(candidates)
        for index, cand in enumerate(candidates):
            candidate = cand if cand.id else cand.model_copy(update={"id": new_id("cand")})
            self.emit(
                E.MEMORY_CANDIDATE,
                E.MemoryCandidatePayload(candidate=candidate, index=index, total=total).model_dump(),
            )
            entries = list(self.store.chronicle_list())  # fresh: sees what earlier candidates committed
            if candidate.source == USER_SOURCE:
                written += await self._commit_explicit(run_id, candidate, entries, project, categories)
                continue
            query = await self._embed_one(candidate.text)
            related = self._related(candidate, entries, query, project, categories)

            verdicts = await self._judge(run_id, candidate, judge_models, related, project, categories)
            panel_action = rules.panel_decision(verdicts)
            loose = False
            if panel_action == "reject" and self._majority_accepts(verdicts, len(judge_models)):
                panel_action, loose = "provisional", True  # most of the panel accepts, but not as one
            kind = source_kind(candidate, panel_action, related)
            outcome = rules.apply_rules(kind, panel_action, related)
            if loose and outcome.action in ("provisional", "adopt"):
                outcome = rules.RuleOutcome(
                    "provisional", "provisional", min(outcome.confidence, 0.5), outcome.scope_hint,
                    "; ".join(p for p in (outcome.note, "panel majority, not agreed; provisional") if p),
                )
            written += await self._commit(
                run_id, candidate, verdicts, panel_action, kind, outcome, entries, project, categories
            )
        return written

    @staticmethod
    def _majority_accepts(verdicts: list[MemoryVerdict], panel_size: int) -> bool:
        """More than half of the panel seats said adopt or provisional (they may differ)."""
        accepting = sum(1 for v in verdicts if rules._norm(v.action) in ("adopt", "provisional"))
        return accepting * 2 > max(panel_size, len(verdicts))

    async def _commit_explicit(
        self,
        run_id: str,
        candidate: MemoryCandidate,
        entries: list[ChronicleEntry],
        project: str,
        categories: list[str],
    ) -> list[ChronicleEntry]:
        """A standing rule the user stated: ACTIVE at once, no panel. Skips what the Chronicle holds."""
        statement = " ".join(candidate.text.split())
        if not statement:
            return []
        evidence = [ev.model_copy() for ev in candidate.evidence] or [
            EvidenceRef(run_id=candidate.run_id or run_id, quote=statement)
        ]
        ts = self.now()
        dup = await self._find_duplicate(candidate, statement, entries, project, categories)
        if dup is not None:
            cand_runs = {ev.run_id for ev in evidence} | {candidate.run_id or run_id}
            if not (cand_runs - {ev.run_id for ev in dup.evidence}):
                return []  # same run saying it twice: nothing to add
            merged = dup.model_copy(
                update={
                    "support_count": dup.support_count + 1,
                    "last_confirmed_at": ts,
                    "confidence": min(1.0, max(dup.confidence + _MERGE_BUMP, 0.9)),
                    "status": "active",
                    "evidence": list(dup.evidence) + evidence,
                },
                deep=True,
            )
            self.store.chronicle_put(merged)
            self._committed(merged, candidate, f"merge:{merged.id}", merged_into_id=merged.id)
            return [merged]
        hint = candidate.scope_hint
        if hint and (hint == "global" or not project or hint.startswith(("project:", "category:"))):
            scope = hint
        else:
            scope = f"project:{project}" if project else "global"
        entry = ChronicleEntry(
            id=new_id("mem"),
            kind=candidate.kind_hint or "preference",
            scope=scope,
            statement=statement,
            rationale="standing rule in user words; stored without a panel vote",
            evidence=evidence,
            status="active",
            confidence=0.9,
            support_count=1,
            created_at=ts,
            last_confirmed_at=ts,
            review_after=int(_cfg(self.cfg, "review_after_runs", 10)),
            embedding=await self._embed_one(statement),
        )
        self.store.chronicle_put(entry)
        self._committed(entry, candidate, "adopt")
        return [entry]

    async def _commit(
        self,
        run_id: str,
        candidate: MemoryCandidate,
        verdicts: list[MemoryVerdict],
        panel_action: str,
        kind: str,
        outcome: rules.RuleOutcome,
        entries: list[ChronicleEntry],
        project: str,
        categories: Optional[list[str]] = None,
    ) -> list[ChronicleEntry]:
        word, _, target_id = outcome.action.partition(":")
        if word == "reject":
            return []
        by_id = {e.id: e for e in entries}
        target = by_id.get(target_id) if target_id else None
        if target is not None and target.status in _DEAD:
            target = None
        if word == "contest" and target is None:
            return []  # nothing real to contest
        if word in ("merge", "supersede") and target is None:
            word = "adopt"  # the panel named an entry that is not there: write a plain new one

        if kind == "override":
            # An override counts against the entries that led to the overridden decision.
            for rid in candidate.related_entry_ids:
                led = by_id.get(rid)
                if led is not None and led.status not in _DEAD and led is not target:
                    self.store.chronicle_put(
                        led.model_copy(update={"contradict_count": led.contradict_count + 1}, deep=True)
                    )

        if word in ("adopt", "provisional"):
            # Never write a second entry for what the Chronicle already holds: merge into it.
            statement = self._statement(candidate, verdicts, panel_action)
            dup = await self._find_duplicate(candidate, statement, entries, project, categories or [])
            if dup is not None:
                cand_runs = {ev.run_id for ev in candidate.evidence} | {candidate.run_id or run_id}
                if not (cand_runs - {ev.run_id for ev in dup.evidence}):
                    return []  # same run saying it twice: one observation, nothing to add
                if kind in ("single_choice", "inferred", "override"):
                    kind = "repeat_pattern"  # seen again in an independent run (15.5)
                outcome = rules.apply_rules(kind, f"merge:{dup.id}", [dup])
                word, target = "merge", dup

        ts = self.now()
        if word == "merge":
            fresh = [ev.model_copy() for ev in candidate.evidence] or [
                EvidenceRef(run_id=candidate.run_id or run_id, quote=candidate.text)
            ]
            status = target.status
            if status == "provisional" and outcome.status == "active":
                status = "active"
            merged = target.model_copy(
                update={
                    "support_count": target.support_count + 1,
                    "last_confirmed_at": ts,
                    "confidence": min(1.0, max(target.confidence + _MERGE_BUMP, outcome.confidence)),
                    "status": status,
                    "evidence": list(target.evidence) + fresh,
                    "votes": list(target.votes) + list(verdicts),
                },
                deep=True,
            )
            self.store.chronicle_put(merged)
            self._committed(merged, candidate, outcome.action, merged_into_id=merged.id)
            return [merged]

        if word == "supersede":
            entry = await self._new_entry(
                run_id, candidate, verdicts, panel_action, outcome, kind, project,
                status=outcome.status or "provisional", supersedes=target.id,
            )
            self.store.chronicle_put(target.model_copy(update={"status": "superseded"}, deep=True))
            self.store.chronicle_put(entry)
            self._committed(entry, candidate, outcome.action, superseded_id=target.id)
            return [entry]

        if word == "contest":
            entry = await self._new_entry(
                run_id, candidate, verdicts, panel_action, outcome, kind, project, status="contested",
            )
            old = target.model_copy(
                update={"status": "contested", "contradict_count": target.contradict_count + 1}, deep=True
            )
            self.store.chronicle_put(old)
            self.store.chronicle_put(entry)
            self.emit(
                E.MEMORY_CONTESTED,
                E.MemoryContestedPayload(
                    entry_id=old.id, entry=old, candidate_id=candidate.id, reason=outcome.note
                ).model_dump(),
            )
            self._committed(entry, candidate, outcome.action)
            return [entry]

        # provisional | adopt
        entry = await self._new_entry(
            run_id, candidate, verdicts, panel_action, outcome, kind, project,
            status=outcome.status or "provisional",
        )
        self.store.chronicle_put(entry)
        self._committed(entry, candidate, "adopt" if entry.status == "active" else "provisional")
        return [entry]

    # ------------------------------------------------------------------ aging

    async def age_pass(self, project: str, runs_since: dict[str, int]) -> list[ChronicleEntry]:
        """Decay entries not confirmed within `review_after` in-scope runs (15.7). Returns the changed ones.

        `runs_since` maps entry id to in-scope runs since its last confirmation; ids not listed are left alone.
        """
        decay = float(_cfg(self.cfg, "decay", 0.9))
        retract_below = float(_cfg(self.cfg, "retract_below", 0.3))
        changed: list[ChronicleEntry] = []
        for entry in list(self.store.chronicle_list()):
            if entry.id not in runs_since or entry.status in _DEAD:
                continue
            if entry.scope.startswith("project:") and entry.scope != f"project:{project}":
                continue
            aged = rules.age(entry, int(runs_since[entry.id]), decay=decay, retract_below=retract_below)
            if aged.confidence == entry.confidence and aged.status == entry.status:
                continue
            self.store.chronicle_put(aged)
            changed.append(aged)
            if aged.status == "retracted":
                self.emit(
                    E.MEMORY_RETRACTED,
                    E.MemoryRetractedPayload(
                        entry_id=aged.id,
                        entry=aged,
                        reason=f"not confirmed in {int(runs_since[entry.id])} runs; confidence {aged.confidence:.2f}",
                        by="aging",
                    ).model_dump(),
                )
        return changed


__all__ = ["PURPOSE", "USER_SOURCE", "Reflector", "pick_judges", "source_kind", "verdict_schema"]
