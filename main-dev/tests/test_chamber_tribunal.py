"""Tests for council/chamber/tribunal.py (spec 27.2 - 27.5). No model server: results are faked."""

from __future__ import annotations

import json
import unittest

from council.chamber import lie_notes
from council.chamber.tribunal import (
    LIE_HINTS_HEADING,
    MAX_LIE_HINTS,
    QUESTION_PROMPT,
    Tribunal,
    answer_schema,
    question_schema,
    verdict_schema,
)
from council.core import event_types as E
from council.core.config import TribunalConfig
from council.core.schemas import (
    PURPOSES,
    CallResult,
    Crux,
    Decision,
    DefenseVerdict,
    EvidenceResult,
    LineupRecord,
    SeatAssignment,
    TribunalAnswer,
    TribunalOutcome,
    TribunalQuestion,
)
from council.core.schemas_v15 import LieFlag

RUN = "run1"
OUTLIER = 3


def lineup(k: int = 5) -> LineupRecord:
    return LineupRecord(
        seats=[SeatAssignment(seat_no=i, model_id=f"m{i}", q=0.9 - 0.1 * i) for i in range(k)], k=k
    )


def decision(agreement: float = 0.6, outcome: str = "majority") -> Decision:
    return Decision(
        outcome=outcome, option_id="o1", final_text="The answer is 42.", answer_key="42",
        agreement=agreement, tally={"o1": 3, "o2": 2},
    )


def make(**kw) -> Tribunal:
    args = dict(
        run_id=RUN,
        task="What is six times seven?",
        decision=decision(),
        lineup=lineup(),
        outlier_seat=OUTLIER,
        outlier_position="The answer is 41.",
        examiner_seats=[0, 1, 2],
        cruxes=[
            Crux(id="x1", statement="Is the product 42 or 41?", between=["o1", "o2"]),
            Crux(id="x2", statement="An old settled point", resolved=True),
        ],
        evidence=[EvidenceResult(kind="python", id="k1", spec="print(6*7)", ok=True, output="42")],
        cfg=TribunalConfig(),
    )
    args.update(kw)
    return Tribunal(**args)


def good(spec, data) -> CallResult:
    return CallResult(call_id=spec.call_id, ok=True, model_id=spec.model_id, parsed=data,
                      content=json.dumps(data))


def bad(spec, error: str = "invalid_output") -> CallResult:
    return CallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id, error=error)


def verdict(held: bool, kind: str = "none", lesson: str = "", score: float = 0.5) -> dict:
    return {"held": held, "score": score, "decisive_point": "p", "error_kind": kind, "lesson": lesson}


def drive(t: Tribunal, questions=None, answers=None, verdicts=None):
    """Run a tribunal to the end.

    questions / answers: {index: dict or None}; verdicts: {seat: dict or None}. None = invalid
    result. A missing key gets a plain valid default (verdict default: not held, factual).
    Returns every event emitted.
    """
    questions, answers, verdicts = questions or {}, answers or {}, verdicts or {}
    events = list(t.take_events())
    guard = 0
    while not t.is_done():
        guard += 1
        if guard > 10:
            raise AssertionError("tribunal does not finish")
        for spec in t.pending_calls():
            seat = spec.meta["seat_no"]
            index = spec.meta.get("index")
            if spec.purpose == "tribunal.question":
                data = questions.get(index, {"question": f"why {index}?", "targets_claim": "c1"})
            elif spec.purpose == "tribunal.answer":
                data = answers.get(index, {"answer": f"because {index}"})
            else:
                data = verdicts.get(seat, verdict(False, "factual", "Check the sum."))
            events += t.on_result(bad(spec) if data is None else good(spec, data))
    return events


def types(events) -> list[str]:
    return [t for t, _ in events]


class TestCalls(unittest.TestCase):
    def test_question_calls(self):
        t = make()
        self.assertEqual(t.phase, "question")
        specs = t.pending_calls()
        self.assertEqual([s.call_id for s in specs], ["run1:tq0:0", "run1:tq1:1", "run1:tq2:2"])
        self.assertEqual([s.model_id for s in specs], ["m0", "m1", "m2"])
        for s in specs:
            self.assertEqual(s.purpose, "tribunal.question")
            self.assertIn(s.purpose, PURPOSES)
            self.assertEqual(s.run_id, RUN)
            self.assertEqual(s.json_schema, question_schema())
            self.assertEqual(s.seed, 0)
            self.assertEqual([m["role"] for m in s.messages], ["system", "user"])
            system = s.messages[0]["content"]
            for text in ("What is six times seven?", "The answer is 42.", "The answer is 41.",
                         "x1: Is the product 42 or 41?", "print(6*7)"):
                self.assertIn(text, system)
            self.assertNotIn("An old settled point", system)  # resolved cruxes are not shown
            self.assertNotIn("m3", system)  # no model names
            self.assertIn("one pointed question", s.messages[1]["content"])
        self.assertEqual(t.pending_calls(), [])  # each call is returned once

    def test_schemas_hide_seat_no(self):
        for schema, required in ((question_schema(), "question"), (answer_schema(), "answer"),
                                 (verdict_schema(), "held")):
            self.assertEqual(schema["required"], [required])
            self.assertNotIn("seat_no", schema["properties"])
        self.assertIn("seat_no", TribunalQuestion.model_json_schema()["properties"])  # untouched
        json.dumps(verdict_schema())

    def test_examiners_limited_and_cleaned(self):
        t = make(examiner_seats=[OUTLIER, 2, 2, 99, 0, 1, 4], cfg={"questions": 2})
        self.assertEqual(t.examiner_seats, [2, 0])
        self.assertEqual([s.call_id for s in t.pending_calls()], ["run1:tq0:2", "run1:tq1:0"])

    def test_cfg_forms(self):
        self.assertEqual(len(make(cfg=None).pending_calls()), 3)
        self.assertEqual(len(make(cfg={"questions": 1}).pending_calls()), 1)
        self.assertEqual(len(make(cfg=TribunalConfig(questions=2)).pending_calls()), 2)
        self.assertEqual(make(cfg=None).min_agreement, 0.80)
        self.assertEqual(make(cfg={"min_agreement": 0.5}).min_agreement, 0.5)

    def test_answer_and_verdict_calls(self):
        t = make()
        for spec in t.pending_calls():
            t.on_result(good(spec, {"question": f"q{spec.meta['index']}?"}))
        self.assertEqual(t.phase, "answer")
        answers = t.pending_calls()
        self.assertEqual([s.call_id for s in answers], ["run1:ta0:3", "run1:ta1:3", "run1:ta2:3"])
        for i, s in enumerate(answers):
            self.assertEqual((s.purpose, s.model_id), ("tribunal.answer", "m3"))
            self.assertEqual(s.json_schema, answer_schema())
            self.assertIn(f"q{i}?", s.messages[1]["content"])
            self.assertIn("concedes", s.messages[1]["content"])
        for i, spec in enumerate(answers):
            t.on_result(good(spec, {"answer": f"a{i}", "concedes": i == 1, "new_evidence": "ev"}))
        self.assertEqual(t.phase, "verdict")
        verdicts = t.pending_calls()
        self.assertEqual([s.call_id for s in verdicts],
                         ["run1:tv:0", "run1:tv:1", "run1:tv:2", "run1:tv:4"])
        for s in verdicts:
            self.assertEqual(s.purpose, "tribunal.verdict")
            self.assertEqual(s.json_schema, verdict_schema())
            user = s.messages[1]["content"]
            for text in ("Q1: q0?", "A1: a0", "Q2: q1?", "concedes this point", "new evidence offered: ev",
                         "error_kind"):
                self.assertIn(text, user)

    def test_deterministic(self):
        a = [s.model_dump() for s in make(seed=7).pending_calls()]
        b = [s.model_dump() for s in make(seed=7).pending_calls()]
        self.assertEqual(a, b)
        self.assertEqual(a[0]["seed"], 7)


class TestFlowAndEvents(unittest.TestCase):
    def test_event_order_and_payloads(self):
        t = make()
        self.assertEqual(t.take_events(), [])
        events = drive(t)
        self.assertEqual(
            types(events),
            ["tribunal.question"] * 3 + ["tribunal.answer"] * 3 + ["tribunal.verdict"] * 4
            + ["tribunal.outcome"],
        )
        for type_, payload in events:
            E.validate_payload(type_, payload)
            json.dumps(payload)
        q = events[1][1]
        self.assertEqual((q["seat_no"], q["model_id"], q["index"], q["outlier_seat"], q["call_id"]),
                         (1, "m1", 1, OUTLIER, "run1:tq1:1"))
        self.assertEqual(q["question"]["seat_no"], 1)
        self.assertEqual(q["question"]["targets_claim"], "c1")
        a = events[5][1]
        self.assertEqual((a["seat_no"], a["model_id"], a["index"], a["call_id"]),
                         (OUTLIER, "m3", 2, "run1:ta2:3"))
        self.assertEqual(a["answer"]["seat_no"], OUTLIER)
        v = events[9][1]
        self.assertEqual((v["seat_no"], v["model_id"], v["call_id"]), (4, "m4", "run1:tv:4"))
        self.assertEqual(v["verdict"]["seat_no"], 4)
        out = events[-1][1]
        self.assertEqual((out["seat_no"], out["model_id"]), (OUTLIER, "m3"))
        self.assertEqual(TribunalOutcome.model_validate(out["outcome"]), t.outcome())

    def test_outcome_before_done_raises(self):
        t = make()
        self.assertFalse(t.is_done())
        with self.assertRaises(RuntimeError):
            t.outcome()
        self.assertEqual(t.eligible(), (False, "tribunal is not done"))

    def test_unknown_and_repeated_results_are_ignored(self):
        t = make()
        specs = t.pending_calls()
        self.assertEqual(t.on_result(CallResult(call_id="nope", ok=True, parsed={"question": "x"})), [])
        first = t.on_result(good(specs[0], {"question": "q?"}))
        self.assertEqual(types(first), ["tribunal.question"])
        self.assertEqual(t.on_result(good(specs[0], {"question": "again?"})), [])
        self.assertEqual(t.phase, "question")

    def test_json_in_content_is_accepted(self):
        t = make(examiner_seats=[0])
        spec = t.pending_calls()[0]
        events = t.on_result(CallResult(call_id=spec.call_id, ok=True, content='{"question": "why?"}'))
        self.assertEqual(types(events), ["tribunal.question"])
        self.assertEqual(t.phase, "answer")

    def test_results_after_done_are_ignored(self):
        t = make()
        drive(t)
        self.assertEqual(t.on_result(CallResult(call_id="run1:tv:0", ok=True, parsed=verdict(True))), [])
        self.assertEqual(t.pending_calls(), [])


class TestOutcomes(unittest.TestCase):
    def test_failed(self):
        t = make()
        events = drive(t, verdicts={
            0: verdict(False, "factual", "Do the sum again.", 0.1),
            1: verdict(False, "factual", "Multiply, do not guess.", 0.3),
            2: verdict(False, "logic", "Mind the steps.", 0.0),
            4: verdict(True),
        })
        out = t.outcome()
        self.assertEqual(out.outcome, "failed")
        self.assertEqual(out.held_share, 0.25)
        self.assertEqual(out.error_kind, "factual")
        self.assertEqual(out.lesson, "Do the sum again.")  # majority kind, lowest score
        self.assertEqual((out.outlier_seat, out.outlier_model_id), (OUTLIER, "m3"))
        self.assertEqual([q.seat_no for q in out.questions], [0, 1, 2])
        self.assertEqual([a.answer for a in out.answers], ["because 0", "because 1", "because 2"])
        self.assertEqual([v.seat_no for v in out.verdicts], [0, 1, 2, 4])
        self.assertIsNone(out.correction_id)
        payload = events[-1][1]
        self.assertFalse(payload["contested_after_review"])

    def test_vindicated(self):
        t = make()
        events = drive(t, verdicts={0: verdict(True), 1: verdict(True), 2: verdict(True),
                                    4: verdict(False, "factual", "No.")})
        out = t.outcome()
        self.assertEqual((out.outcome, out.held_share), ("vindicated", 0.75))
        self.assertEqual(out.lesson, "")
        payload = events[-1][1]
        self.assertTrue(payload["contested_after_review"])
        self.assertFalse(payload["correction_eligible"])
        self.assertEqual(payload["reason"], "the defence held")
        self.assertEqual(t.eligible(), (False, "the defence held"))

    def test_exactly_half_is_vindicated(self):
        t = make()
        drive(t, verdicts={0: verdict(True), 1: verdict(True),
                           2: verdict(False, "factual"), 4: verdict(False, "factual")})
        self.assertEqual((t.outcome().outcome, t.outcome().held_share), ("vindicated", 0.5))

    def test_just_under_half_fails(self):
        t = make(lineup=lineup(6), examiner_seats=[0])
        drive(t, verdicts={0: verdict(True), 1: verdict(True), 2: verdict(False, "logic"),
                           4: verdict(False, "logic"), 5: verdict(False, "logic")})
        self.assertEqual((t.outcome().outcome, t.outcome().held_share), ("failed", 0.4))
        self.assertEqual(t.outcome().error_kind, "logic")

    def test_conceded(self):
        t = make()
        drive(t, answers={1: {"answer": "You are right, I was wrong.", "concedes": True}})
        out = t.outcome()
        self.assertEqual(out.outcome, "conceded")
        self.assertEqual([a.concedes for a in out.answers], [False, True, False])
        self.assertEqual(out.error_kind, "factual")
        self.assertEqual(out.lesson, "Check the sum.")

    def test_concession_wins_over_judges_who_say_it_held(self):
        t = make()
        events = drive(t, answers={0: {"answer": "", "concedes": True}},
                       verdicts={s: verdict(True) for s in (0, 1, 2, 4)})
        out = t.outcome()
        self.assertEqual((out.outcome, out.held_share, out.error_kind), ("conceded", 1.0, "none"))
        self.assertFalse(events[-1][1]["contested_after_review"])
        self.assertEqual(t.eligible(), (False, "majority error_kind is none"))

    def test_invalid_verdicts_abstain(self):
        t = make()
        events = drive(t, verdicts={0: {"score": 0.9}, 1: verdict(True), 2: verdict(True),
                                    4: verdict(False, "factual")})
        out = t.outcome()
        self.assertEqual(types(events).count("tribunal.verdict"), 3)
        self.assertEqual([v.seat_no for v in out.verdicts], [1, 2, 4])
        self.assertEqual(out.outcome, "vindicated")
        self.assertAlmostEqual(out.held_share, 2 / 3)

    def test_bad_error_kind_abstains_and_score_is_clipped(self):
        t = make()
        drive(t, verdicts={0: verdict(False, "vibes"), 1: verdict(False, "logic", "L", 1.7),
                           2: verdict(False, "logic", "M", -3), 4: verdict(False, "logic", "Z")})
        out = t.outcome()
        self.assertEqual([(v.seat_no, v.score) for v in out.verdicts], [(1, 1.0), (2, 0.0), (4, 0.5)])
        self.assertEqual((out.outcome, out.lesson), ("failed", "M"))

    def test_skipped_no_valid_verdict(self):
        t = make()
        events = drive(t, verdicts={s: None for s in (0, 1, 2, 4)})
        out = t.outcome()
        self.assertEqual((out.outcome, out.held_share, out.verdicts), ("skipped", 0.0, []))
        self.assertEqual(len(out.questions), 3)
        self.assertEqual(len(out.answers), 3)
        self.assertEqual(events[-1][0], "tribunal.outcome")
        self.assertEqual(events[-1][1]["reason"], "no valid verdict")
        self.assertEqual(t.eligible(), (False, "no valid verdict"))

    def test_skipped_no_valid_verdict_even_after_a_concession(self):
        t = make()
        drive(t, answers={0: {"answer": "I concede.", "concedes": True}},
              verdicts={s: None for s in (0, 1, 2, 4)})
        self.assertEqual(t.outcome().outcome, "skipped")
        self.assertFalse(t.eligible()[0])

    def test_skipped_no_valid_question(self):
        t = make()
        events = drive(t, questions={0: None, 1: {"question": "   "}, 2: {"nope": 1}})
        self.assertEqual(types(events), ["tribunal.outcome"])
        self.assertEqual(t.outcome().outcome, "skipped")
        self.assertEqual(t.eligible(), (False, "no valid question"))

    def test_skipped_no_valid_answer(self):
        t = make()
        events = drive(t, answers={0: None, 1: {"answer": " "}, 2: {"concedes": True}})
        self.assertEqual(types(events), ["tribunal.question"] * 3 + ["tribunal.outcome"])
        out = t.outcome()
        self.assertEqual((out.outcome, len(out.questions), out.answers), ("skipped", 3, []))
        self.assertEqual(t.eligible(), (False, "no valid answer"))

    def test_skipped_at_once_without_examiners(self):
        for kw, reason in (
            (dict(examiner_seats=[]), "no examiner"),
            (dict(examiner_seats=[OUTLIER]), "no examiner"),
            (dict(cfg={"questions": 0}), "no examiner"),
            (dict(outlier_seat=42), "the outlier seat is not in the lineup"),
        ):
            t = make(**kw)
            self.assertTrue(t.is_done())
            self.assertEqual(t.pending_calls(), [])
            events = t.take_events()
            self.assertEqual(types(events), ["tribunal.outcome"])
            E.validate_payload(*events[0])
            self.assertEqual(events[0][1]["reason"], reason)
            self.assertEqual(t.outcome().outcome, "skipped")
            self.assertEqual(t.eligible(), (False, reason))

    def test_partial_questions_and_answers(self):
        t = make()
        events = drive(t, questions={1: None}, answers={2: None})
        out = t.outcome()
        self.assertEqual([p["index"] for ty, p in events if ty == "tribunal.question"], [0, 2])
        self.assertEqual([p["index"] for ty, p in events if ty == "tribunal.answer"], [0])
        self.assertEqual([q.seat_no for q in out.questions], [0, 2])
        self.assertEqual([a.answer for a in out.answers], ["because 0", ""])  # aligned
        self.assertEqual(out.outcome, "failed")

    def test_error_kind_tie_goes_to_the_uncorrected_kind(self):
        t = make()
        drive(t, verdicts={0: verdict(False, "factual"), 1: verdict(False, "preference"),
                           2: verdict(False, "factual"), 4: verdict(False, "preference")})
        self.assertEqual(t.outcome().error_kind, "preference")
        self.assertFalse(t.eligible()[0])

    def test_error_kind_counts_every_valid_verdict(self):
        # 2 none, 2 factual, 1 logic: a tie between none and factual goes to none (27.5).
        t = make(lineup=lineup(6), examiner_seats=[0], decision=decision(0.9))
        drive(t, verdicts={0: verdict(True), 1: verdict(True), 2: verdict(False, "factual"),
                           4: verdict(False, "factual"), 5: verdict(False, "logic")})
        self.assertEqual((t.outcome().outcome, t.outcome().error_kind), ("failed", "none"))
        self.assertEqual(t.eligible(), (False, "majority error_kind is none"))

        t = make(lineup=lineup(6), examiner_seats=[0], decision=decision(0.9))
        drive(t, verdicts={0: verdict(True), 1: verdict(False, "factual", "A", 0.4),
                           2: verdict(False, "factual", "B", 0.2), 4: verdict(False, "factual"),
                           5: verdict(False, "logic", "C", 0.0)})
        out = t.outcome()
        self.assertEqual((out.outcome, out.error_kind, out.lesson), ("failed", "factual", "B"))
        self.assertEqual(t.eligible(), (True, "agreement"))

    def test_one_error_vote_does_not_outweigh_judges_who_said_it_held(self):
        # Reviewer repro: the outlier concedes, 3 of 4 judges say held / none, 1 says factual.
        t = make()
        drive(t, answers={0: {"answer": "I was wrong.", "concedes": True}},
              verdicts={0: verdict(True), 1: verdict(True), 2: verdict(True),
                        4: verdict(False, "factual", "Check it.")})
        out = t.outcome()
        self.assertEqual((out.outcome, out.error_kind), ("conceded", "none"))
        self.assertEqual(t.eligible(), (False, "majority error_kind is none"))

        # one factual vote against two preference votes cast with held=true
        t = make(decision=decision(0.9))
        drive(t, verdicts={0: verdict(True, "preference"), 1: verdict(True, "preference"),
                           2: verdict(False, "logic"), 4: verdict(False, "factual")})
        self.assertEqual(t.outcome().error_kind, "preference")
        self.assertFalse(t.eligible()[0])

    def test_judge_quorum(self):
        # Reviewer repro: 4 judges, 3 verdict calls fail, 1 says not held / factual, agreement 0.80.
        t = make(decision=decision(0.8))
        self.assertEqual(t.judge_quorum(), 3)
        events = drive(t, verdicts={0: None, 1: None, 2: None, 4: verdict(False, "factual", "L")})
        out = t.outcome()
        self.assertEqual(out.outcome, "skipped")
        self.assertEqual([v.seat_no for v in out.verdicts], [4])  # kept for the record
        self.assertFalse(t.eligible()[0])
        self.assertIn("too few verdicts", t.eligible()[1])
        self.assertFalse(events[-1][1]["correction_eligible"])

        t = make(decision=decision(0.8))  # exactly half is not a quorum
        drive(t, verdicts={0: None, 1: None, 2: verdict(False, "factual"), 4: verdict(False, "factual")})
        self.assertEqual(t.outcome().outcome, "skipped")

        t = make(decision=decision(0.8))  # 3 of 4 is
        drive(t, verdicts={0: None, 1: verdict(False, "factual"), 2: verdict(False, "factual"),
                           4: verdict(False, "factual", "L")})
        self.assertEqual(t.outcome().outcome, "failed")
        self.assertEqual(t.eligible(), (True, "agreement"))
        for k, need in ((2, 1), (3, 2), (4, 2), (6, 3)):
            self.assertEqual(make(lineup=lineup(k), outlier_seat=0, examiner_seats=[1]).judge_quorum(), need)


class TestEligibility(unittest.TestCase):
    def run_failed(self, kind="factual", **kw) -> Tribunal:
        t = make(**kw)
        drive(t, verdicts={s: verdict(False, kind, "L") for s in (0, 1, 2, 4)})
        self.assertEqual(t.outcome().outcome, "failed")
        return t

    def test_evidence(self):
        t = self.run_failed(verified_by_evidence=True)
        self.assertEqual(t.eligible(), (True, "evidence"))

    def test_ground_truth(self):
        t = self.run_failed(ground_truth_supports=True)
        self.assertEqual(t.eligible(), (True, "ground_truth"))

    def test_conceded(self):
        t = make()
        events = drive(t, answers={0: {"answer": "I was wrong.", "concedes": True}})
        self.assertEqual(t.eligible(), (True, "conceded"))
        self.assertTrue(events[-1][1]["correction_eligible"])
        self.assertEqual(events[-1][1]["reason"], "")

    def test_agreement(self):
        t = self.run_failed(decision=decision(agreement=0.80))
        self.assertEqual(t.eligible(), (True, "agreement"))
        t = self.run_failed(decision=decision(agreement=0.79))
        self.assertEqual(t.eligible(), (False, "the council's position is not verified"))
        t = self.run_failed(decision=decision(agreement=0.6), cfg={"min_agreement": 0.6})
        self.assertEqual(t.eligible(), (True, "agreement"))

    def test_not_verified(self):
        t = make()
        events = drive(t)
        self.assertEqual(t.outcome().outcome, "failed")
        self.assertEqual(t.eligible(), (False, "the council's position is not verified"))
        self.assertFalse(events[-1][1]["correction_eligible"])
        self.assertEqual(events[-1][1]["reason"], "the council's position is not verified")

    def test_preference_is_never_corrected(self):
        t = self.run_failed("preference", verified_by_evidence=True, ground_truth_supports=True,
                            decision=decision(agreement=1.0))
        self.assertEqual(t.eligible(), (False, "majority error_kind is preference"))

    def test_none_is_never_corrected(self):
        t = self.run_failed("none", verified_by_evidence=True)
        self.assertEqual(t.eligible(), (False, "majority error_kind is none"))

    def test_every_real_error_kind_is_eligible(self):
        for kind in ("factual", "logic", "misread_task", "ignored_evidence"):
            t = self.run_failed(kind, verified_by_evidence=True)
            self.assertEqual((t.outcome().error_kind, t.eligible()), (kind, (True, "evidence")))

    def test_ground_truth_against_the_council_blocks(self):
        t = self.run_failed(ground_truth_supports=False, verified_by_evidence=True,
                            decision=decision(agreement=1.0))
        self.assertEqual(
            t.eligible(), (False, "ground truth does not support the council's position")
        )

    def test_verified_by_order(self):
        def conceded(**kw):
            t = make(**kw)
            drive(t, answers={0: {"answer": "ok", "concedes": True}})
            return t.eligible()

        full = dict(decision=decision(agreement=1.0))
        self.assertEqual(conceded(verified_by_evidence=True, ground_truth_supports=True, **full),
                         (True, "evidence"))
        self.assertEqual(conceded(ground_truth_supports=True, **full), (True, "ground_truth"))
        self.assertEqual(conceded(**full), (True, "conceded"))

    def test_vindicated_is_not_eligible(self):
        t = make(verified_by_evidence=True, decision=decision(agreement=1.0))
        drive(t, verdicts={s: verdict(True, "factual") for s in (0, 1, 2, 4)})
        self.assertEqual(t.eligible(), (False, "the defence held"))


class TestDeadline(unittest.TestCase):
    def test_deadline_before_verdicts_skips(self):
        t = make()
        t.pending_calls()
        events = t.on_deadline()
        self.assertEqual(types(events), ["tribunal.outcome"])
        self.assertEqual(t.outcome().outcome, "skipped")
        self.assertEqual(t.pending_calls(), [])
        self.assertEqual(t.on_deadline(), [])

    def test_deadline_in_verdicts_counts_what_is_in(self):
        t = make()
        for spec in t.pending_calls():
            t.on_result(good(spec, {"question": "q?"}))
        for spec in t.pending_calls():
            t.on_result(good(spec, {"answer": "a"}))
        specs = t.pending_calls()
        for spec in specs[:3]:
            t.on_result(good(spec, verdict(False, "logic", "L")))
        events = t.on_deadline()
        self.assertEqual(types(events), ["tribunal.outcome"])
        out = t.outcome()
        self.assertEqual((out.outcome, out.held_share, len(out.verdicts)), ("failed", 0.0, 3))
        self.assertEqual(t.on_result(good(specs[3], verdict(True))), [])

    def test_deadline_in_verdicts_below_quorum_skips(self):
        t = make(decision=decision(0.9))
        for spec in t.pending_calls():
            t.on_result(good(spec, {"question": "q?"}))
        for spec in t.pending_calls():
            t.on_result(good(spec, {"answer": "a"}))
        specs = t.pending_calls()
        t.on_result(good(specs[0], verdict(False, "logic", "L")))
        t.on_deadline()
        self.assertEqual(t.outcome().outcome, "skipped")
        self.assertFalse(t.eligible()[0])


class TestSnapshot(unittest.TestCase):
    def finish(self, t: Tribunal) -> TribunalOutcome:
        drive(t, answers={1: {"answer": "fine", "concedes": True}})
        return t.outcome()

    def test_round_trip_in_every_phase(self):
        expected = self.finish(make(verified_by_evidence=True))
        for stop in ("question", "answer", "verdict"):
            t = make(verified_by_evidence=True)
            while t.phase != stop:
                for spec in t.pending_calls():
                    data = ({"question": f"why {spec.meta['index']}?", "targets_claim": "c1"}
                            if spec.purpose == "tribunal.question"
                            else {"answer": "fine", "concedes": True} if spec.meta["index"] == 1
                            else {"answer": f"because {spec.meta['index']}"})
                    t.on_result(good(spec, data))
            out_ids = [s.call_id for s in t.pending_calls()]  # the calls are now out
            snap = t.snapshot()
            json.dumps(snap)
            r = Tribunal.restore(snap)
            self.assertEqual(r.phase, stop)
            self.assertEqual(r.snapshot(), snap)
            self.assertEqual([s.call_id for s in r.pending_calls()], out_ids)  # handed out again
            r2 = Tribunal.restore(snap)
            self.assertEqual(self.finish(r2), expected)
            self.assertEqual(r2.eligible(), (True, "evidence"))

    def test_partial_phase_keeps_results(self):
        t = make()
        specs = t.pending_calls()
        t.on_result(good(specs[0], {"question": "first?"}))
        snap = t.snapshot()
        self.assertEqual([s.call_id for s in Tribunal.restore(snap).pending_calls()],
                         ["run1:tq1:1", "run1:tq2:2"])
        r = Tribunal.restore(snap)
        drive(r)
        self.assertEqual(r.outcome().questions[0].question, "first?")
        self.assertEqual(len(r.outcome().questions), 3)

    def test_done_round_trip(self):
        t = make(ground_truth_supports=True, cfg={"questions": 2, "min_agreement": 0.7})
        drive(t)
        r = Tribunal.restore(t.snapshot())
        self.assertTrue(r.is_done())
        self.assertEqual(r.outcome(), t.outcome())
        self.assertEqual(r.eligible(), t.eligible())
        self.assertEqual((r.max_questions, r.min_agreement), (2, 0.7))
        self.assertEqual(r.pending_calls(), [])

    def test_skipped_round_trip_keeps_reason_and_events(self):
        t = make(examiner_seats=[])
        r = Tribunal.restore(t.snapshot())
        self.assertEqual(r.eligible(), (False, "no examiner"))
        self.assertEqual(types(r.take_events()), ["tribunal.outcome"])

    def test_snapshot_is_a_copy(self):
        t = make()
        snap = t.snapshot()
        snap["args"]["task"] = "changed"
        self.assertEqual(t.task, "What is six times seven?")


class TestSchemaObjectsAsResults(unittest.TestCase):
    def test_model_instances_in_parsed(self):
        t = make(examiner_seats=[0])
        spec = t.pending_calls()[0]
        t.on_result(CallResult(call_id=spec.call_id, ok=True, parsed=TribunalQuestion(question="q?")))
        spec = t.pending_calls()[0]
        t.on_result(CallResult(call_id=spec.call_id, ok=True, parsed=TribunalAnswer(answer="a")))
        for spec in t.pending_calls():
            t.on_result(CallResult(call_id=spec.call_id, ok=True,
                                   parsed=DefenseVerdict(held=False, error_kind="misread_task")))
        out = t.outcome()
        self.assertEqual((out.outcome, out.error_kind), ("failed", "misread_task"))
        self.assertEqual(out.questions[0].seat_no, 0)
        self.assertEqual(out.answers[0].seat_no, OUTLIER)
        self.assertEqual([v.seat_no for v in out.verdicts], [0, 1, 2, 4])


class TestTimeouts(unittest.TestCase):
    """Call timeouts come from budget.turn_timeout_s, not a flat 120 s."""

    def phases(self, t: Tribunal):
        out = {}
        for spec in t.pending_calls():
            out.setdefault("question", set()).add(spec.timeout_s)
            t.on_result(good(spec, {"question": "q?"}))
        for spec in t.pending_calls():
            out.setdefault("answer", set()).add(spec.timeout_s)
            t.on_result(good(spec, {"answer": "a"}))
        for spec in t.pending_calls():
            out.setdefault("verdict", set()).add(spec.timeout_s)
        return out

    def test_unknown_speed(self):
        got = self.phases(make())
        # 15 tps; 3 questions, 3 answers and 4 verdicts go out together
        self.assertAlmostEqual(got["question"].pop(), 2.5 * 250 / (15 / 1.5))
        self.assertAlmostEqual(got["answer"].pop(), 2.5 * 400 / (15 / 1.5))
        self.assertAlmostEqual(got["verdict"].pop(), 2.5 * 300 / (15 / 2.0))

    def test_known_speed_and_floor(self):
        t = make(seat_tps={0: 150.0, 1: 5.0, OUTLIER: 150.0})
        by_seat = {s.meta["seat_no"]: s.timeout_s for s in t.pending_calls()}
        self.assertEqual(by_seat[0], 60.0)  # fast seat: the floor
        self.assertAlmostEqual(by_seat[1], 2.5 * 250 / (5 / 1.5))  # slow seat: 187.5 s
        self.assertAlmostEqual(by_seat[2], 62.5)

    def test_capped_by_the_time_left(self):
        t = make(remaining_s=50.0)
        specs = t.pending_calls()
        self.assertEqual({s.timeout_s for s in specs}, {50.0})
        t.set_remaining(10.0)
        for spec in specs:
            t.on_result(good(spec, {"question": "q?"}))
        self.assertEqual({s.timeout_s for s in t.pending_calls()}, {45.0})  # never under 45

    def test_snapshot_keeps_speed_and_time_left(self):
        t = make(seat_tps={OUTLIER: 5.0}, remaining_s=500.0)
        again = Tribunal.restore(t.snapshot())
        for spec in again.pending_calls():
            again.on_result(good(spec, {"question": "q?"}))
        self.assertEqual(
            {s.timeout_s for s in again.pending_calls()}, {2.5 * 400 / (5 / 1.5)}
        )


def flag(seat, claim, level="flag", score=0.2, text=None) -> LieFlag:
    return LieFlag(
        run_id=RUN, seat_no=seat, model_id=f"m{seat}", claim_id=claim,
        text=text or f"claim {claim} of seat {seat}", probe_score=score, level=level,
    )


def question_prompts(t: Tribunal) -> dict[int, str]:
    return {s.meta["index"]: s.messages[1]["content"] for s in t.pending_calls()}


class TestLieHints(unittest.TestCase):
    def test_default_is_no_change(self):
        for t in (make(), make(lie_flags=None), make(lie_flags=[])):
            self.assertEqual(set(question_prompts(t).values()), {QUESTION_PROMPT})

    def test_flags_of_other_seats_or_ok_claims_change_nothing(self):
        t = make(lie_flags=[flag(0, "c1"), flag(2, "c2"), flag(OUTLIER, "c3", level="ok")])
        self.assertEqual(set(question_prompts(t).values()), {QUESTION_PROMPT})

    def test_hints_for_the_examined_seat(self):
        flags = [flag(OUTLIER, "c2", level="watch", score=0.4), flag(OUTLIER, "c1"), flag(1, "c9")]
        prompts = question_prompts(make(lie_flags=flags))
        first = prompts[0]
        self.assertTrue(first.startswith(QUESTION_PROMPT))
        self.assertEqual(first.count(LIE_HINTS_HEADING), 1)
        hints = [line for line in first.splitlines() if line.startswith("- Ask for the evidence behind:")]
        self.assertEqual(hints, [  # flag before watch
            f'- Ask for the evidence behind: "claim c1 of seat {OUTLIER}"',
            f'- Ask for the evidence behind: "claim c2 of seat {OUTLIER}"',
        ])
        self.assertNotIn("claim c9", first)  # another seat's claim
        self.assertNotIn(f"m{OUTLIER}", first)  # no model id
        self.assertIn("estimate, not a fact", first)

    def test_at_most_three_hints_worst_first(self):
        flags = [flag(OUTLIER, f"c{i}", score=0.1 * i) for i in range(1, 6)]
        prompts = question_prompts(make(lie_flags=flags))
        self.assertEqual(MAX_LIE_HINTS, 3)
        want = [lie_notes.question_hint(f) for f in lie_notes.tribunal_targets(flags, OUTLIER, 3)]
        self.assertEqual(len(prompts), 3)
        for index, prompt in prompts.items():
            hints = [line[2:] for line in prompt.splitlines() if line.startswith("- Ask for")]
            self.assertEqual(len(hints), 3)
            self.assertEqual(sorted(hints), sorted(want))
            self.assertEqual(hints[0], want[index % 3])  # each examiner starts at another claim
            self.assertNotIn("claim c4", prompt)
            self.assertNotIn("claim c5", prompt)

    def test_only_the_question_prompt_gets_hints(self):
        t = make(lie_flags=[flag(OUTLIER, "c1")])
        seen = []
        while not t.is_done():
            for spec in t.pending_calls():
                seen.append(spec)
                if spec.purpose == "tribunal.question":
                    data = {"question": "why?"}
                elif spec.purpose == "tribunal.answer":
                    data = {"answer": "because"}
                else:
                    data = verdict(False, "factual", "Check it.")
                t.on_result(good(spec, data))
        self.assertEqual({s.purpose for s in seen},
                         {"tribunal.question", "tribunal.answer", "tribunal.verdict"})
        for spec in seen:
            text = spec.messages[0]["content"] + spec.messages[1]["content"]
            self.assertEqual(LIE_HINTS_HEADING in text, spec.purpose == "tribunal.question")

    def test_hints_do_not_change_the_outcome(self):
        a, b = make(), make(lie_flags=[flag(OUTLIER, "c1")])
        drive(a)
        drive(b)
        self.assertEqual(a.outcome(), b.outcome())
        self.assertEqual(a.eligible(), b.eligible())

    def test_dicts_are_accepted_and_snapshot_keeps_the_flags(self):
        t = make(lie_flags=[flag(OUTLIER, "c1").model_dump()])
        snap = json.loads(json.dumps(t.snapshot()))
        r = Tribunal.restore(snap)
        self.assertEqual(r.snapshot(), snap)
        self.assertEqual([f.claim_id for f in r.lie_flags], ["c1"])
        self.assertEqual(question_prompts(r), question_prompts(t))

    def test_old_snapshot_without_flags_restores(self):
        snap = make().snapshot()
        del snap["args"]["lie_flags"]
        r = Tribunal.restore(snap)
        self.assertEqual(r.lie_flags, [])
        self.assertEqual(set(question_prompts(r).values()), {QUESTION_PROMPT})


class TestCouncilSizes(unittest.TestCase):
    """The tribunal for every council size the UI offers. The outlier is the last seat."""

    def test_runs_for_two_to_six_seats(self):
        for k in (2, 3, 4, 5, 6):
            with self.subTest(k=k):
                outlier = k - 1
                t = make(lineup=lineup(k), outlier_seat=outlier, examiner_seats=list(range(k)),
                         lie_flags=[flag(outlier, "c1")])
                self.assertEqual(t.examiner_seats, list(range(k - 1))[:3])  # never the outlier
                self.assertEqual(t.judge_seats, list(range(k - 1)))
                self.assertEqual(t.judge_quorum(), (k - 1) // 2 + 1)
                events = drive(t)
                out = t.outcome()
                self.assertEqual(out.outcome, "failed")
                self.assertEqual(out.outlier_seat, outlier)
                self.assertEqual(len(out.verdicts), k - 1)
                self.assertEqual(types(events)[-1], E.TRIBUNAL_OUTCOME)

    def test_two_seats_one_judge(self):
        t = make(lineup=lineup(2), outlier_seat=1, examiner_seats=[0, 1],
                 decision=decision(agreement=0.5, outcome="chair"))
        (q,) = t.pending_calls()
        self.assertEqual(q.meta["seat_no"], 0)
        t.on_result(good(q, {"question": "why 41?"}))
        (a,) = t.pending_calls()
        self.assertEqual(a.meta["seat_no"], 1)
        t.on_result(good(a, {"answer": "because"}))
        (v,) = t.pending_calls()
        self.assertEqual(v.meta["seat_no"], 0)
        t.on_result(good(v, verdict(False, "factual", "Check the sum.")))
        self.assertEqual(t.outcome().outcome, "failed")
        # one judge against one member, at 50% agreement: not a correction without proof
        self.assertEqual(t.eligible(), (False, "the council's position is not verified"))

    def test_two_seats_a_concession_is_eligible(self):
        t = make(lineup=lineup(2), outlier_seat=1, examiner_seats=[0],
                 decision=decision(agreement=0.5, outcome="chair"))
        drive(t, answers={0: {"answer": "you are right", "concedes": True}})
        self.assertEqual(t.outcome().outcome, "conceded")
        self.assertEqual(t.eligible(), (True, "conceded"))

    def test_two_seats_the_judge_fails_is_skipped(self):
        t = make(lineup=lineup(2), outlier_seat=1, examiner_seats=[0])
        drive(t, verdicts={0: None})
        self.assertEqual(t.outcome().outcome, "skipped")


if __name__ == "__main__":
    unittest.main()
