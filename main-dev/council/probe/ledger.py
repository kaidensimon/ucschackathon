"""Claim ledger (ARCHITECTURE 28.2).

Logs every Draft claim (plus the answer itself, claim_id "answer") and takes labels later:
evidence, ground truth, tribunal outcome, user. Unlabelled records stay "unknown".
"""
from __future__ import annotations

from typing import Callable, Optional

from council.core.schemas import (
    ClaimRecord,
    Crux,
    Draft,
    EvidenceResult,
    TribunalOutcome,
)

ANSWER_ID = "answer"


def _rid(run_id: str, seat_no: int, claim_id: str) -> str:
    return f"{run_id}:{seat_no}:{claim_id}"


class ClaimLedger:
    def __init__(self, store, now: Callable[[], float]) -> None:
        self.store = store
        self.now = now

    # ------------------------------------------------------------------ logging

    def log_draft(self, run_id: str, project: str, model_id: str, seat_no: int,
                  draft: Draft) -> list[ClaimRecord]:
        """One record per claim plus one for the answer. Ids are stable, so a re-log overwrites."""
        t = self.now()
        out: list[ClaimRecord] = []
        out.append(ClaimRecord(
            id=_rid(run_id, seat_no, ANSWER_ID), run_id=run_id, project=project,
            model_id=model_id, seat_no=seat_no, claim_id=ANSWER_ID, text=draft.answer,
            confidence=draft.confidence, created_at=t))
        for c in draft.claims:
            out.append(ClaimRecord(
                id=_rid(run_id, seat_no, c.id), run_id=run_id, project=project,
                model_id=model_id, seat_no=seat_no, claim_id=c.id, text=c.text,
                confidence=draft.confidence, created_at=t))
        for rec in out:
            self.store.claims_put(rec)
        return out

    # ------------------------------------------------------------------ labelling

    def _run(self, run_id: str) -> list[ClaimRecord]:
        return [r for r in self.store.claims_list() if r.run_id == run_id]

    def _set(self, rec: ClaimRecord, label: str, by: str) -> int:
        if rec.label == label and rec.labelled_by == by:
            return 0
        self.store.claim_label(rec.id, label, by)
        return 1

    def label_from_evidence(self, run_id: str, evidence: list[EvidenceResult],
                            cruxes: list[Crux]) -> int:
        """An ok check that exits 0 (or has no exit code) supports the claim it settles;
        a nonzero exit refutes it. `settles` is a claim id ("c1") or "seat:claim" ("2:c1").
        A ref that names a crux, not a claim, labels nothing. Only unknown records change."""
        crux_ids = {c.id for c in cruxes}
        recs = [r for r in self._run(run_id) if r.claim_id != ANSWER_ID]
        changed = 0
        for ev in evidence:
            ref = ev.settles
            if not ref or not ev.ok:
                continue
            seat: Optional[int] = None
            cid = ref
            if ":" in ref:
                head, _, cid = ref.partition(":")
                try:
                    seat = int(head)
                except ValueError:
                    continue
            elif ref in crux_ids and not any(r.claim_id == ref for r in recs):
                continue
            label = "true" if ev.exit_code in (None, 0) else "false"
            for r in recs:
                if r.claim_id != cid or r.label != "unknown":
                    continue
                if seat is not None and r.seat_no != seat:
                    continue
                changed += self._set(r, label, "evidence")
        return changed

    def label_from_truth(self, run_id: str, seat_no: int, correct: bool) -> int:
        """Benchmark ground truth for a seat's answer record."""
        rid = _rid(run_id, seat_no, ANSWER_ID)
        for r in self._run(run_id):
            if r.id == rid:
                return self._set(r, "true" if correct else "false", "ground_truth")
        return 0

    def label_from_tribunal(self, run_id: str, outcome: TribunalOutcome) -> int:
        """Eligible (correction_id set) conceded or failed: the outlier's load-bearing claims
        are false. Vindicated: true. Load-bearing = the claims the questions targeted, or all
        the outlier's claims when no question named one. The answer record is not touched."""
        seat = outcome.outlier_seat
        if seat is None:
            return 0
        if outcome.outcome == "vindicated":
            label = "true"
        elif outcome.outcome in ("conceded", "failed"):
            if not outcome.correction_id:
                return 0
            label = "false"
        else:
            return 0
        recs = [r for r in self._run(run_id)
                if r.seat_no == seat and r.claim_id != ANSWER_ID]
        targeted = {q.targets_claim for q in outcome.questions if q.targets_claim}
        picked = [r for r in recs if r.claim_id in targeted] or recs
        changed = 0
        for r in picked:
            if r.label == "unknown":
                changed += self._set(r, label, "tribunal")
        return changed

    def label_user(self, record_id: str, label: str) -> int:
        for r in self.store.claims_list():
            if r.id == record_id:
                return self._set(r, label, "user")
        return 0

    # ------------------------------------------------------------------ reading

    def labelled(self, model_id: str) -> list[ClaimRecord]:
        return self.store.claims_list(model_id=model_id, labelled_only=True)

    def track_record(self, model_id: str, project: Optional[str] = None) -> tuple[float, float]:
        recs = self.store.claims_list(model_id=model_id, project=project, labelled_only=True)
        t = float(sum(1 for r in recs if r.label == "true"))
        f = float(sum(1 for r in recs if r.label == "false"))
        return t, f
