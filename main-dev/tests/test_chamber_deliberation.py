"""Tests for council.chamber.deliberation. Hand-built CallResults, no I/O."""

import json
import unittest

from council.chamber import lie_notes
from council.chamber.anonymize import label_to_seat
from council.chamber.deliberation import (
    CHAIR_FLOOR_S,
    DEFAULT_CTX_TOKENS,
    LATE_CHAIR_NOTE,
    Deliberation,
    PendingCheck,
)
from council.core.event_types import validate_payload
from council.core.schemas import (
    MODE_DEFAULTS,
    CallResult,
    ClaimScore,
    EvidenceResult,
    LineupRecord,
    ModeConfig,
    SeatAssignment,
    TaskProfile,
)
from council.core.schemas_v15 import LieFlag

LENSES = ["builder", "skeptic", "first_principles", "risk", "specialist"]
QS = [0.9, 0.8, 0.7, 0.6, 0.5]


def lineup(k=5, alternates=(), chair=None):
    seats = [
        SeatAssignment(seat_no=i, model_id=f"m{i}", lens=LENSES[i], q=QS[i]) for i in range(k)
    ]
    return LineupRecord(seats=seats, alternates=list(alternates), chair_model_id=chair, k=k)


def make(mode="standard", **kw):
    kw.setdefault("lineup", lineup())
    kw.setdefault("answer_type", "mcq")
    if isinstance(mode, str):
        mode = MODE_DEFAULTS[mode]
    return Deliberation("run1", "What is the answer?", TaskProfile(), mode=mode, **kw)


def ok(spec, parsed):
    return CallResult(call_id=spec.call_id, ok=True, model_id=spec.model_id, parsed=parsed)


def bad(spec, error="invalid_output"):
    return CallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id, error=error)


def draft(key, conf=0.9, text=None):
    return {
        "answer": text or f"The answer is {key}.",
        "answer_key": key,
        "summary": f"Answer {key}",
        "claims": [{"id": "c1", "text": f"{key} follows from the premise"}],
        "confidence": conf,
    }


def ballot(choice, conf=0.8, **kw):
    out = {"choice": choice, "ranking": [choice], "final_answer": f"Final for {choice}", "confidence": conf}
    out.update(kw)
    return out


class Driver:
    """Feeds results in and keeps every event, checking each against the event contract."""

    def __init__(self, test, d):
        self.test, self.d = test, d
        self.events = []
        self.take(d.take_events())

    def take(self, events):
        for type_, payload in events:
            validate_payload(type_, payload)
            json.dumps(payload)
            self.events.append((type_, payload))
        return events

    def types(self):
        return [t for t, _ in self.events]

    def calls(self, purpose=None, n=None):
        specs = self.d.pending_calls()
        if purpose is not None:
            self.test.assertEqual({s.purpose for s in specs}, {purpose})
        if n is not None:
            self.test.assertEqual(len(specs), n)
        return specs

    def feed(self, spec, parsed):
        return self.take(self.d.on_result(ok(spec, parsed)))

    def fail(self, spec, error="invalid_output"):
        return self.take(self.d.on_result(bad(spec, error)))

    def r0(self, keys, conf=0.9):
        specs = self.calls("seat.r0")
        for spec, key in zip(specs, keys):
            if key is None:
                self.fail(spec)
            else:
                self.feed(spec, draft(key, conf))
        return specs

    def r1(self, parsed=None):
        specs = self.calls("seat.r1")
        for spec in specs:
            self.feed(spec, parsed or {"reviews": [], "position": "keep"})
        return specs

    def ballots(self, purpose, choices):
        specs = self.calls(purpose)
        for spec, choice in zip(specs, choices):
            self.feed(spec, ballot(choice))
        return specs

    def last(self, type_):
        return [p for t, p in self.events if t == type_][-1]


class EarlyExit(unittest.TestCase):
    def test_all_agree_ends_after_r0(self):
        d = make()
        drv = Driver(self, d)
        self.assertEqual(d.phase, "r0")
        self.assertEqual(drv.types(), ["round.started"])
        specs = drv.calls("seat.r0", 5)
        self.assertEqual(d.pending_calls(), [])  # each call is returned once
        for i, spec in enumerate(specs):
            self.assertFalse(d.is_done())
            drv.feed(spec, draft("B", conf=0.7 + 0.05 * i))
        self.assertTrue(d.is_done())
        self.assertEqual(d.phase, "done")
        dec = d.decision()
        self.assertEqual(dec.outcome, "consensus")
        self.assertEqual(dec.answer_key, "b")
        self.assertEqual(dec.rounds_run, 1)
        self.assertEqual(dec.agreement, 1.0)
        self.assertEqual(dec.tally, {"o1": 5})
        self.assertEqual(dec.final_text, "The answer is B.")
        self.assertEqual(dec.minority_report, [])
        self.assertEqual(
            drv.types(),
            ["round.started", "options.clustered", "round.completed", "consensus.reached", "decision.final"],
        )
        self.assertTrue(drv.last("consensus.reached")["early"])
        self.assertTrue(drv.last("round.completed")["converged"])
        self.assertEqual(d.pending_calls(), [])

    def test_highest_confidence_draft_is_the_text(self):
        d = make()
        drv = Driver(self, d)
        specs = drv.calls()
        confs = [0.8, 0.95, 0.8, 0.8, 0.8]
        for i, spec in enumerate(specs):
            drv.feed(spec, draft("B", confs[i], text=f"text from seat {i}"))
        self.assertEqual(d.decision().final_text, "text from seat 1")

    def test_low_confidence_agreement_goes_to_debate(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B"] * 5, conf=0.4)
        self.assertFalse(d.is_done())
        self.assertEqual(d.phase, "r1")

    def test_four_of_five_with_minority_report(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "B", "C"])
        dec = d.decision()
        self.assertEqual(dec.outcome, "consensus")
        self.assertAlmostEqual(dec.agreement, 0.8)
        self.assertEqual(len(dec.minority_report), 1)
        self.assertEqual(dec.minority_report[0].seats, [4])
        self.assertEqual(dec.minority_report[0].option_id, "o2")

    def test_not_done_raises(self):
        d = make()
        with self.assertRaises(RuntimeError):
            d.decision()

    def test_unknown_result_is_ignored(self):
        d = make()
        self.assertEqual(d.on_result(CallResult(call_id="nope", ok=True))[1:], [])
        self.assertEqual(d.phase, "r0")


class FullDebate(unittest.TestCase):
    def test_r1_evidence_r2_consensus(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        self.assertEqual(d.phase, "r1")
        self.assertIn("cruxes.extracted", drv.types())  # empty: no clerk
        specs = drv.calls("seat.r1", 5)
        self.assertIn("names removed", specs[0].messages[1]["content"])
        self.assertNotIn("m1", specs[0].messages[1]["content"])  # no model ids shown
        target = specs[0].json_schema["$defs"]["Review"]["properties"]["target"]["enum"]
        self.assertEqual(sorted(target), ["A", "B", "C", "D"])
        check = {"kind": "python", "spec": "print(1+1)", "settles": "A.c1"}
        for i, spec in enumerate(specs):
            crit = {
                "reviews": [{"target": "A", "flaws": [{"id": "f1", "text": "weak step", "severity": "major"}]}],
                "position": "keep",
                "checks_requested": [check] if i < 2 else [],
            }
            drv.feed(spec, crit)
        self.assertEqual(d.phase, "evidence")
        self.assertEqual(d.pending_calls(), [])
        checks = d.pending_checks()
        self.assertEqual(len(checks), 1)  # two identical requests are merged
        self.assertIsInstance(checks[0], PendingCheck)
        self.assertEqual(checks[0].check_id, "k1")
        self.assertEqual(checks[0].requested_by, [0, 1])
        self.assertEqual(d.pending_checks(), [])
        self.assertEqual(drv.last("evidence.requested")["check_id"], "k1")
        drv.take(d.on_evidence("k1", EvidenceResult(kind="python", ok=True, output="2")))
        self.assertEqual(drv.last("evidence.result")["result"]["output"], "2")
        self.assertEqual(d.phase, "r2")

        specs = drv.calls("seat.r2", 5)
        user = specs[0].messages[1]["content"]
        self.assertIn('"output":"2"', user)
        self.assertIn("weak step", "".join(s.messages[1]["content"] for s in specs))
        self.assertNotIn("holders", user)  # seats never see tallies
        self.assertEqual(specs[0].json_schema["properties"]["choice"]["enum"], ["o1", "o2"])
        for spec, choice in zip(specs, ["o1", "o1", "o1", "o1", "o2"]):
            drv.feed(spec, ballot(choice))
        self.assertTrue(d.is_done())
        dec = d.decision()
        self.assertEqual(dec.outcome, "consensus")
        self.assertEqual(dec.option_id, "o1")
        self.assertEqual(dec.rounds_run, 3)
        self.assertEqual(dec.tally, {"o1": 4, "o2": 1})
        self.assertAlmostEqual(dec.agreement, 0.8)
        self.assertEqual(dec.answer_key, "b")
        self.assertEqual(dec.final_text, "Final for o1")
        self.assertEqual([m.seats for m in dec.minority_report], [[4]])
        types = drv.types()
        self.assertEqual(types.count("ballot.cast"), 5)
        self.assertEqual(types.count("round.started"), 3)
        self.assertEqual(types.count("round.completed"), 3)
        self.assertEqual(types[-2:], ["consensus.reached", "decision.final"])
        self.assertFalse(drv.last("consensus.reached")["early"])
        cast = [p for t, p in drv.events if t == "ballot.cast"]
        self.assertEqual([p["changed"] for p in cast], [False, False, False, True, False])
        self.assertEqual(drv.last("decision.final")["decision"]["outcome"], "consensus")

    def test_r3_after_split_r2(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        drv.r1()
        drv.ballots("seat.r2", ["o1", "o1", "o1", "o2", "o2"])
        self.assertEqual(d.phase, "r3")
        failed = drv.last("consensus.failed")
        self.assertEqual(failed["next_step"], "round")
        self.assertEqual(failed["leading_option_id"], "o1")
        specs = drv.ballots("seat.r3", ["o1", "o1", "o1", "o1", "o2"])
        self.assertIn("Round 3", specs[0].messages[1]["content"])
        dec = d.decision()
        self.assertEqual(dec.outcome, "consensus")
        self.assertEqual(dec.rounds_run, 4)
        self.assertEqual(drv.last("round.completed")["round"], 3)

    def test_two_blocking_objections_stop_consensus(self):
        d = make(lineup=lineup(), mode=MODE_DEFAULTS["standard"].model_copy(update={"rounds": ["r0", "r1", "r2"]}))
        drv = Driver(self, d)
        drv.r0(["A", "A", "A", "B", "C"])
        drv.r1()
        specs = drv.calls("seat.r2")
        # 3 of 5 for o1, two blockers: not consensus, no round left -> majority
        for spec, choice in zip(specs, ["o1", "o1", "o1", "o2", "o3"]):
            extra = {"blocking_objection": "o1 is wrong"} if choice != "o1" else {}
            drv.feed(spec, ballot(choice, **extra))
        dec = d.decision()
        self.assertEqual(dec.outcome, "majority")
        self.assertEqual(len(dec.minority_report), 2)
        self.assertEqual(dec.minority_report[0].strongest_argument, "o1 is wrong")

    def test_adopt_without_reason_is_kept(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        specs = drv.calls("seat.r1")
        for spec in specs:
            drv.feed(spec, {"reviews": [], "position": "adopt:A", "changed_because": []})
        self.assertEqual(drv.last("round.completed")["tally"], {"o1": 3, "o2": 2})

    def test_clerk_cluster_and_cruxes(self):
        d = make(answer_type=None, clerk_model_id="clerk")
        drv = Driver(self, d)
        drv.r0(["x", "x", "x", "y", "y"])
        self.assertEqual(d.phase, "cluster")
        (spec,) = drv.calls("clerk.cluster_options", 1)
        self.assertEqual(spec.model_id, "clerk")
        self.assertEqual(spec.call_id, "run1:clerk.cluster_options")
        drv.feed(spec, {"options": [{"summary": "X", "holders": [0, 1, 2]}, {"summary": "Y", "holders": [3, 4]}]})
        self.assertEqual(d.phase, "cruxes")
        (spec,) = drv.calls("clerk.extract_cruxes", 1)
        drv.feed(
            spec,
            {
                "cruxes": [
                    {"statement": "Is x faster?", "between": ["o1", "o2", "zz"], "kind": "checkable"},
                    {"statement": "", "between": [], "kind": "factual"},
                ]
            },
        )
        cruxes = drv.last("cruxes.extracted")["cruxes"]
        self.assertEqual(len(cruxes), 1)
        self.assertEqual(cruxes[0]["id"], "x1")
        self.assertEqual(cruxes[0]["between"], ["o1", "o2"])
        specs = drv.r1()
        self.assertIn("Is x faster?", specs[0].messages[1]["content"])
        specs = drv.calls("seat.r2")
        vote = specs[0].json_schema["$defs"]["CruxVote"]["properties"]["crux_id"]["enum"]
        self.assertEqual(vote, ["x1"])
        for spec in specs:
            drv.feed(spec, ballot("o1", crux_votes=[{"crux_id": "x1", "stance": "agree"}]))
        dec = d.decision()
        self.assertEqual(dec.outcome, "consensus")
        self.assertEqual(dec.open_cruxes, [])  # settled by the vote

    def test_clerk_failure_falls_back_to_one_option_per_draft(self):
        d = make(answer_type=None, clerk_model_id="clerk", lineup=lineup(3), mode="quick")
        drv = Driver(self, d)
        drv.r0(["x", "y", "z"])
        (spec,) = drv.calls("clerk.cluster_options")
        drv.fail(spec)
        self.assertEqual(len(drv.last("options.clustered")["options"]), 3)
        self.assertEqual(d.phase, "chair")


class Fallbacks(unittest.TestCase):
    def test_majority_at_deadline(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        drv.r1()
        specs = drv.calls("seat.r2", 5)
        drv.feed(specs[0], ballot("o1"))
        drv.feed(specs[3], ballot("o2"))
        self.assertFalse(d.is_done())
        events = drv.take(d.on_deadline())
        self.assertTrue(d.is_done())
        dec = d.decision()
        self.assertEqual(dec.outcome, "majority")
        self.assertEqual(dec.option_id, "o1")
        self.assertEqual(dec.tally, {"o1": 3, "o2": 2})  # late seats keep their last position
        self.assertAlmostEqual(dec.agreement, 0.6)
        self.assertEqual(dec.minority_report[0].seats, [3, 4])
        self.assertEqual([t for t, _ in events], ["round.completed", "consensus.failed", "decision.final"])
        self.assertEqual(drv.last("consensus.failed")["next_step"], "majority")
        self.assertEqual(drv.last("round.completed")["failed_seats"], [1, 2, 4])
        self.assertEqual(d.on_result(ok(specs[1], ballot("o2"))), [])  # late result: ignored
        self.assertEqual(d.on_deadline(), [])
        self.assertEqual(d.decision().tally, {"o1": 3, "o2": 2})

    def test_deadline_in_r0_uses_the_drafts_that_arrived(self):
        d = make()
        drv = Driver(self, d)
        specs = drv.calls()
        for spec in specs[:4]:
            drv.feed(spec, draft("B"))
        drv.take(d.on_deadline())
        dec = d.decision()
        self.assertEqual(dec.outcome, "consensus")
        self.assertEqual(dec.tally, {"o1": 4})

    def test_deadline_in_r1_falls_back_to_r0_positions(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        drv.calls("seat.r1")
        drv.take(d.on_deadline())
        dec = d.decision()
        self.assertEqual(dec.outcome, "majority")
        self.assertEqual(dec.final_text, "The answer is B.")
        self.assertEqual(dec.rounds_run, 2)

    def test_round_skipped_when_the_estimate_exceeds_time_left(self):
        d = make(seat_tps={i: 10.0 for i in range(5)})  # r1 needs 5 * 1300 / 10 / 2 = 325 s
        drv = Driver(self, d)
        d.set_remaining(100.0)
        drv.r0(["B", "B", "B", "C", "C"])
        self.assertEqual(d.decision().outcome, "majority")
        self.assertNotIn("seat.r1", [p.get("purpose") for _, p in drv.events])

    def test_turn_timeout_is_capped_by_time_left(self):
        d = make()  # deadline 300, Chair reserve 120
        drv = Driver(self, d)
        d.set_remaining(200.0)
        drv.r0(["B", "B", "B", "C", "C"])
        self.assertEqual({s.timeout_s for s in drv.calls("seat.r1")}, {80.0})

    def test_timeout_keeps_position_invalid_abstains(self):
        d = make(mode=MODE_DEFAULTS["standard"].model_copy(update={"rounds": ["r0", "r1", "r2"]}))
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        drv.r1()
        specs = drv.calls("seat.r2")
        drv.feed(specs[0], ballot("o1"))
        drv.fail(specs[1], "timeout")  # carries o1
        drv.fail(specs[2], "invalid_output")  # abstains
        drv.feed(specs[3], ballot("o2"))
        drv.feed(specs[4], {"choice": "nope"})  # not an option: void
        dec = d.decision()
        self.assertEqual(dec.tally, {"o1": 2, "o2": 1})
        self.assertEqual(dec.outcome, "majority")

    def test_chair_fallback(self):
        d = make(mode="quick", lineup=lineup(5))
        drv = Driver(self, d)
        drv.r0(["A", "A", "B", "B", "C"], conf=0.6)
        self.assertEqual(d.phase, "chair")
        self.assertEqual(drv.last("consensus.failed")["next_step"], "chair")
        (spec,) = drv.calls("chair", 1)
        self.assertEqual(spec.model_id, "m0")  # highest q
        self.assertEqual(drv.last("chair.started")["call_id"], spec.call_id)
        self.assertEqual(spec.json_schema["properties"]["option_id"]["enum"], ["o1", "o2"])
        self.assertIn("leading_options", spec.messages[1]["content"])
        drv.fail(spec)  # 10.11: the next-highest-q seat takes the chair
        (spec2,) = drv.calls("chair", 1)
        self.assertEqual(spec2.model_id, "m1")
        self.assertNotEqual(spec2.call_id, spec.call_id)
        drv.feed(spec2, {"option_id": "o2", "final_text": "Merged: B.", "answer_key": " B ", "confidence": 0.7})
        dec = d.decision()
        self.assertEqual(dec.outcome, "chair")
        self.assertEqual(dec.option_id, "o2")
        self.assertEqual(dec.final_text, "Merged: B.")
        self.assertEqual(dec.answer_key, "b")
        self.assertAlmostEqual(dec.agreement, 0.4)
        self.assertEqual(dec.confidence, 0.7)
        self.assertEqual(sorted(m.option_id for m in dec.minority_report), ["o1", "o3"])
        self.assertEqual(drv.types().count("chair.started"), 2)
        self.assertEqual(drv.types()[-1], "decision.final")

    def test_named_chair_outside_the_lineup(self):
        d = make(mode="quick", lineup=lineup(3, chair="big"))
        drv = Driver(self, d)
        drv.r0(["A", "B", "C"])
        (spec,) = drv.calls("chair")
        self.assertEqual(spec.model_id, "big")
        self.assertIsNone(drv.last("chair.started")["seat_no"])
        drv.take(d.on_result(CallResult(call_id=spec.call_id, ok=True, content="Plain text verdict.")))
        self.assertEqual(d.decision().final_text, "Plain text verdict.")

    def test_every_chair_fails_gives_deadlock_with_a_text(self):
        d = make(mode="quick", lineup=lineup(3))
        drv = Driver(self, d)
        drv.r0(["A", "B", "C"])
        for _ in range(3):
            (spec,) = drv.calls("chair")
            drv.fail(spec)
        dec = d.decision()
        self.assertEqual(dec.outcome, "deadlock")
        self.assertEqual(dec.final_text, "The answer is A.")  # seat 0 has the highest q

    def test_quorum_failure_goes_to_chair(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", None, None, None])  # 2 valid, quorum is 3
        self.assertEqual(d.phase, "chair")
        failed = drv.last("consensus.failed")
        self.assertIn("quorum is 3", failed["reason"])
        self.assertEqual(drv.last("round.completed")["failed_seats"], [2, 3, 4])
        self.assertNotIn("consensus.reached", drv.types())
        (spec,) = drv.calls("chair")
        drv.feed(spec, {"option_id": "o1", "final_text": "B it is.", "confidence": 0.6})
        dec = d.decision()
        self.assertEqual(dec.outcome, "chair")
        self.assertEqual(dec.rounds_run, 1)

    def test_no_valid_draft_is_a_deadlock(self):
        d = make(lineup=lineup(3))
        drv = Driver(self, d)
        drv.r0([None, None, None])
        dec = d.decision()
        self.assertEqual(dec.outcome, "deadlock")
        self.assertEqual(dec.final_text, "")
        self.assertEqual(drv.types()[-1], "decision.final")


class InvalidSeat(unittest.TestCase):
    def test_alternate_substituted_once(self):
        d = make(lineup=lineup(5, alternates=["alt1", "alt2"]))
        drv = Driver(self, d)
        specs = drv.calls("seat.r0", 5)
        drv.fail(specs[2])
        assigned = drv.last("seat.assigned")
        self.assertEqual((assigned["seat_no"], assigned["model_id"], assigned["replaces_model_id"]), (2, "alt1", "m2"))
        (sub,) = drv.calls("seat.r0", 1)
        self.assertEqual(sub.model_id, "alt1")
        self.assertEqual(sub.meta["seat_no"], 2)
        self.assertNotEqual(sub.call_id, specs[2].call_id)
        drv.fail(sub)  # second failure: no second substitution, the seat abstains
        self.assertEqual(d.pending_calls(), [])
        for i in (0, 1, 3, 4):
            drv.feed(specs[i], draft("B"))
        dec = d.decision()
        self.assertEqual(dec.outcome, "consensus")
        self.assertEqual(dec.tally, {"o1": 4})
        self.assertEqual(drv.last("round.completed")["failed_seats"], [2])
        self.assertEqual(drv.types().count("seat.assigned"), 1)

    def test_alternate_draft_counts(self):
        d = make(lineup=lineup(5, alternates=["alt1"]))
        drv = Driver(self, d)
        specs = drv.calls()
        drv.fail(specs[0], "server_error")
        (sub,) = drv.calls()
        for spec in [sub] + specs[1:]:
            drv.feed(spec, draft("B"))
        self.assertEqual(d.decision().tally, {"o1": 5})

    def test_no_alternate_means_abstain(self):
        d = make()
        drv = Driver(self, d)
        specs = drv.calls()
        drv.take(d.on_result(CallResult(call_id=specs[0].call_id, ok=True, parsed={"no_answer": 1})))
        self.assertEqual(d.pending_calls(), [])
        for spec in specs[1:]:
            drv.feed(spec, draft("B"))
        self.assertEqual(d.decision().tally, {"o1": 4})

    def test_timeout_in_r0_is_not_substituted(self):
        d = make(lineup=lineup(5, alternates=["alt1"]))
        drv = Driver(self, d)
        specs = drv.calls()
        drv.fail(specs[0], "timeout")
        self.assertEqual(d.pending_calls(), [])


class PlanMode(unittest.TestCase):
    def setUp(self):
        self.mode = MODE_DEFAULTS["standard"].model_copy(update={"rounds": ["r0"]})

    def start(self, keys, **kw):
        kw.setdefault("answer_type", None)
        d = make(mode=self.mode, plan_mode=True, **kw)
        drv = Driver(self, d)
        drv.r0(keys, conf=0.8)
        return d, drv

    def test_ratified(self):
        d, drv = self.start(["A", "B", "C", "D", "E"])
        (spec,) = drv.calls("chair")
        drv.feed(spec, {"option_id": "o1", "final_text": "Plan v1", "confidence": 0.8})
        self.assertEqual(d.phase, "ratify")
        specs = drv.calls("ratify", 5)
        self.assertIn("Plan v1", specs[0].messages[1]["content"])
        for i, spec in enumerate(specs):
            drv.feed(spec, {"approve": i != 4, "reason": "fine" if i != 4 else "too slow"})
        res = drv.last("ratify.result")
        self.assertTrue(res["ratified"])
        self.assertEqual((res["votes_for"], res["votes_against"]), (4, 1))
        self.assertEqual(res["objections"], ["too slow"])
        self.assertEqual(d.decision().final_text, "Plan v1")
        self.assertEqual(d.decision().outcome, "chair")

    def test_rejected_then_revised_once(self):
        d, drv = self.start(["A", "B", "C", "D", "E"])
        (spec,) = drv.calls("chair")
        drv.feed(spec, {"option_id": "o1", "final_text": "Plan v1", "confidence": 0.8})
        for i, spec in enumerate(drv.calls("ratify", 5)):
            drv.feed(spec, {"approve": i < 2, "reason": f"objection {i}"})
        self.assertFalse(drv.last("ratify.result")["ratified"])
        self.assertEqual(d.phase, "chair")
        (rev,) = drv.calls("chair", 1)
        self.assertIn("objection 3", rev.messages[1]["content"])
        self.assertIn("Plan v1", rev.messages[1]["content"])
        drv.feed(rev, {"option_id": "o1", "final_text": "Plan v2", "confidence": 0.8})
        dec = d.decision()  # the second version is final, with no second vote
        self.assertEqual(dec.final_text, "Plan v2")
        self.assertEqual(dec.minority_report[-1].seats, [2, 3, 4])
        self.assertIn("objection 2", dec.minority_report[-1].strongest_argument)
        self.assertEqual(drv.types().count("ratify.result"), 1)

    def test_low_chair_confidence_asks_the_user(self):
        d, drv = self.start(["A", "B", "C", "D", "E"])
        (spec,) = drv.calls("chair")
        drv.feed(spec, {"option_id": "o1", "final_text": "Unsure", "confidence": 0.3, "user_question": "Fast or safe?"})
        dec = d.decision()
        self.assertEqual(dec.outcome, "user")
        self.assertEqual(dec.needs_user.question, "Fast or safe?")
        self.assertEqual(len(dec.needs_user.options), 2)

    def test_early_agreement_is_merged_by_the_chair(self):
        d, drv = self.start(["A"] * 5, answer_type="exact")
        self.assertTrue(drv.last("consensus.reached")["early"])
        (spec,) = drv.calls("chair")
        self.assertIn("Merge these drafts", spec.messages[1]["content"])
        drv.feed(spec, {"option_id": "o1", "final_text": "Merged plan", "confidence": 0.9})
        for spec in drv.calls("ratify", 5):
            drv.feed(spec, {"approve": True, "reason": "ok"})
        dec = d.decision()
        self.assertEqual(dec.outcome, "consensus")
        self.assertEqual(dec.final_text, "Merged plan")


class SnapshotRestore(unittest.TestCase):
    def finish(self, d):
        """Drive whatever is left to the end with fixed answers. Returns the Decision as a dict."""
        guard = 0
        while not d.is_done():
            guard += 1
            self.assertLess(guard, 50)
            for spec in d.pending_calls():
                seat = spec.meta.get("seat_no")
                if spec.purpose == "seat.r1":
                    parsed = {
                        "reviews": [{"target": "A", "flaws": [{"id": "f1", "text": "gap"}]}],
                        "position": "keep",
                        "checks_requested": [{"kind": "grep", "spec": "TODO"}],
                    }
                elif spec.purpose in ("seat.r2", "seat.r3"):
                    parsed = ballot("o1" if seat != 4 else "o2")
                else:
                    self.fail(f"unexpected call {spec.purpose}")
                d.on_result(ok(spec, parsed))
            for check in d.pending_checks():
                d.on_evidence(check.check_id, EvidenceResult(kind=check.kind, ok=True, output="3 hits"))
        return d.decision().model_dump(mode="json")

    def test_mid_r1(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        specs = drv.calls("seat.r1", 5)
        for spec in specs[:2]:
            drv.feed(
                spec,
                {
                    "reviews": [{"target": "A", "flaws": [{"id": "f1", "text": "gap"}]}],
                    "position": "keep",
                    "checks_requested": [{"kind": "grep", "spec": "TODO"}],
                },
            )
        snap = d.snapshot()
        text = json.dumps(snap)  # JSON-serializable
        d2 = Deliberation.restore(json.loads(text))
        self.assertEqual(d2.phase, "r1")
        self.assertFalse(d2.is_done())
        self.assertEqual(d2.snapshot(), snap)
        again = d2.pending_calls()  # the three calls still out are handed out again
        self.assertEqual([s.call_id for s in again], [s.call_id for s in specs[2:]])
        self.assertEqual(again[0].messages, specs[2].messages)
        for spec in again:
            d2.on_result(ok(spec, {"reviews": [], "position": "keep"}))
        for spec in specs[2:]:
            d.on_result(ok(spec, {"reviews": [], "position": "keep"}))
        self.assertEqual(d2.phase, "evidence")
        self.assertEqual(self.finish(d2), self.finish(d))
        self.assertEqual(d2.decision().outcome, "consensus")

    def test_mid_evidence_and_done(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        drv.r1({"reviews": [], "position": "keep", "checks_requested": [{"kind": "grep", "spec": "x"}]})
        d.pending_checks()  # handed out, then the process dies
        d2 = Deliberation.restore(json.loads(json.dumps(d.snapshot())))
        self.assertEqual(d2.phase, "evidence")
        checks = d2.pending_checks()  # handed out again after the restart
        self.assertEqual([c.check_id for c in checks], ["k1"])
        d2.on_evidence("", EvidenceResult(kind="grep", id="k1", ok=True, output="hit"))  # id from the result
        self.assertEqual(d2.phase, "r2")
        expected = self.finish(d2)
        d3 = Deliberation.restore(d2.snapshot())
        self.assertTrue(d3.is_done())
        self.assertEqual(d3.decision().model_dump(mode="json"), expected)
        self.assertEqual(d3.pending_calls(), [])

    def test_buffered_events_survive(self):
        d = make()
        d2 = Deliberation.restore(d.snapshot())
        self.assertEqual([t for t, _ in d2.take_events()], ["round.started"])
        self.assertEqual(len(d2.pending_calls()), 5)


class Purity(unittest.TestCase):
    def test_same_inputs_same_calls(self):
        a, b = make(seed=7), make(seed=7)
        da = [s.model_dump() for s in a.pending_calls()]
        db = [s.model_dump() for s in b.pending_calls()]
        self.assertEqual(da, db)
        self.assertEqual(len({s["call_id"] for s in da}), 5)
        self.assertTrue(all(s["seed"] == 7 for s in da))

    def test_r0_call_shape(self):
        d = make(lens_texts={"builder": "Ship the simplest thing."}, record="ACTIVE: use tabs", brief="repo")
        spec = d.pending_calls()[0]
        self.assertEqual(spec.purpose, "seat.r0")
        self.assertEqual(spec.run_id, "run1")
        self.assertEqual(spec.max_output_tokens, 700)
        self.assertEqual(spec.reasoning, "council")
        system = spec.messages[0]["content"]
        for piece in ("Ship the simplest thing.", "ACTIVE: use tabs", "What is the answer?", "repo"):
            self.assertIn(piece, system)
        self.assertIn("answer", spec.json_schema["properties"])

    def test_custom_normalize(self):
        d = make(normalize=lambda key, kind: key.strip().upper()[:1])
        drv = Driver(self, d)
        specs = drv.calls()
        for spec, key in zip(specs, ["b", "B)", " B", "b.", "B"]):
            drv.feed(spec, draft(key))
        self.assertEqual(d.decision().answer_key, "B")
        self.assertEqual(d.decision().tally, {"o1": 5})

    def test_deep_mode_runs_r3_twice_with_unique_call_ids(self):
        d = make(mode="deep")
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        drv.r1()
        first = drv.ballots("seat.r2", ["o1", "o1", "o1", "o2", "o2"])
        second = drv.ballots("seat.r3", ["o1", "o1", "o1", "o2", "o2"])
        third = drv.ballots("seat.r3", ["o1", "o1", "o1", "o2", "o2"])
        ids = [s.call_id for s in first + second + third]
        self.assertEqual(len(set(ids)), 15)
        dec = d.decision()
        self.assertEqual(dec.outcome, "majority")
        self.assertEqual(dec.rounds_run, 5)
        self.assertEqual(drv.last("round.completed")["round"], 4)


NOTE = "Corrections from earlier sessions in this project:\n- check the units"
HEADING = "Engine reliability scores (advisory, not a vote)"


def scores(seats=range(5), probe=None, auroc=None):
    out = []
    for s in seats:
        for ref in ("answer", "c1"):
            out.append(
                ClaimScore(claim_ref=ref, reliability=0.1 * (s + 1), probe=probe, probe_auroc=auroc, seat_no=s)
            )
    return out


class SeatNotes(unittest.TestCase):
    def test_only_the_noted_seat_gets_them_in_every_round(self):
        d = make(seat_notes={1: NOTE}, record="ACTIVE: use tabs")
        drv = Driver(self, d)
        specs = drv.r0(["B", "B", "B", "C", "C"])
        specs += drv.r1()
        specs += drv.ballots("seat.r2", ["o1", "o1", "o1", "o1", "o2"])
        self.assertTrue(d.is_done())
        self.assertEqual(len(specs), 15)
        for spec in specs:
            system = spec.messages[0]["content"]
            if spec.meta["seat_no"] == 1:
                self.assertTrue(system.endswith("- check the units"))
                self.assertLess(system.index("ACTIVE: use tabs"), system.index("Corrections from"))
            else:
                self.assertNotIn("Corrections from", system)

    def test_default_is_unchanged(self):
        a = [s.model_dump() for s in make().pending_calls()]
        b = [s.model_dump() for s in make(seat_notes={}).pending_calls()]
        self.assertEqual(a, b)

    def test_substituted_seat_loses_its_notes(self):
        d = make(lineup=lineup(alternates=["alt1"]), seat_notes={0: NOTE})
        drv = Driver(self, d)
        specs = drv.calls("seat.r0", 5)
        self.assertIn("check the units", specs[0].messages[0]["content"])
        drv.fail(specs[0])
        (retry,) = drv.calls("seat.r0", 1)
        self.assertEqual(retry.model_id, "alt1")
        self.assertNotIn("check the units", retry.messages[0]["content"])

    def test_snapshot_keeps_notes(self):
        d = make(seat_notes={2: NOTE})
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        d2 = Deliberation.restore(json.loads(json.dumps(d.snapshot())))
        self.assertEqual(d2.seat_notes, {2: NOTE})
        self.assertEqual(d2.snapshot(), d.snapshot())


class ClaimScores(unittest.TestCase):
    def start(self, **kw):
        d = make(**kw)
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        self.assertEqual(d.phase, "r1")
        return d, drv

    def test_no_scores_no_block(self):
        d, drv = self.start()
        for spec in drv.calls("seat.r1", 5):
            self.assertNotIn(HEADING, spec.messages[1]["content"])

    def test_block_has_only_the_other_seats_under_their_labels(self):
        d, drv = self.start()
        d.set_claim_scores(scores())
        specs = drv.calls("seat.r1", 5)
        for spec in specs:
            seat = spec.meta["seat_no"]
            body = spec.messages[1]["content"]
            self.assertEqual(body.count(HEADING), 1)
            block = body[body.index(HEADING):]
            self.assertNotIn("Y.c1", block)
            self.assertNotIn(f"reliability {0.1 * (seat + 1):.2f}", block)  # its own score is not shown
            for label, other in label_to_seat(list(range(5)), seat, 0).items():
                self.assertIn(f"{label}.c1: reliability {0.1 * (other + 1):.2f}", block)
                self.assertIn(f"{label} answer: reliability {0.1 * (other + 1):.2f}", block)
            self.assertNotIn("probe", block)
            self.assertNotIn("m1", block)
        # the patched calls are the ones a result is matched against
        drv.feed(specs[0], {"reviews": [], "position": "keep"})
        self.assertEqual(d.phase, "r1")
        for spec in specs[1:]:
            drv.feed(spec, {"reviews": [], "position": "keep"})
        self.assertEqual(d.phase, "r2")

    def test_probe_is_labelled_with_its_accuracy(self):
        d, drv = self.start()
        d.set_claim_scores(scores(probe=0.25, auroc=0.86))
        body = drv.calls("seat.r1", 5)[0].messages[1]["content"]
        self.assertIn("truth-probe 0.25 (probe held-out AUROC 0.86)", body)
        # one direction for every number on the line: the template says which
        self.assertIn("0 = likely wrong, 1 = likely right", body)

    def test_setting_twice_replaces_the_block(self):
        d, drv = self.start()
        d.set_claim_scores(scores())
        d.set_claim_scores(scores(seats=[0]))
        specs = drv.calls("seat.r1", 5)
        self.assertNotIn(HEADING, specs[0].messages[1]["content"])  # seat 0 is not shown its own score
        body = specs[1].messages[1]["content"]
        self.assertEqual(body.count(HEADING), 1)
        self.assertEqual(body.count(": reliability "), 2)  # answer and c1 of seat 0
        d2, drv2 = self.start()
        d2.set_claim_scores(scores())
        d2.set_claim_scores([])
        plain = self.start()[1].calls("seat.r1", 5)
        self.assertEqual([s.messages for s in drv2.calls("seat.r1", 5)], [s.messages for s in plain])

    def test_scores_do_not_change_the_vote(self):
        def run(with_scores):
            d, drv = self.start()
            if with_scores:
                d.set_claim_scores(scores(probe=0.01, auroc=0.99))
            drv.r1()
            drv.ballots("seat.r2", ["o1", "o1", "o1", "o1", "o2"])
            return d.decision().model_dump(mode="json")

        self.assertEqual(run(True), run(False))

    def test_scores_are_not_shown_after_round_1(self):
        d, drv = self.start()
        d.set_claim_scores(scores())
        drv.r1()
        for spec in drv.calls("seat.r2", 5):
            self.assertNotIn(HEADING, spec.messages[1]["content"])

    def test_snapshot_keeps_scores_and_the_patched_calls(self):
        d, drv = self.start()
        d.set_claim_scores(scores())
        snap = json.loads(json.dumps(d.snapshot()))
        d2 = Deliberation.restore(snap)
        self.assertEqual(d2.snapshot(), snap)
        a, b = d.pending_calls(), d2.pending_calls()
        self.assertEqual([s.messages for s in a], [s.messages for s in b])
        self.assertIn(HEADING, b[0].messages[1]["content"])


class RealCruxes(unittest.TestCase):
    FLAW = {"id": "f1", "text": "The loop is O(n^2)", "severity": "fatal", "kind": "factual", "claim_ref": "A.c1"}

    def crit(self, check=None, flaw=None):
        return {
            "reviews": [{"target": "A", "flaws": [flaw or self.FLAW]}],
            "position": "keep",
            "checks_requested": [check] if check else [],
        }

    def clerk_then_r1(self, reply):
        d = make(answer_type=None, clerk_model_id="clerk")
        drv = Driver(self, d)
        drv.r0(["x", "x", "x", "y", "y"])
        (spec,) = drv.calls("clerk.cluster_options", 1)
        drv.feed(spec, {"options": [{"summary": "X", "holders": [0, 1, 2]}, {"summary": "Y", "holders": [3, 4]}]})
        (spec,) = drv.calls("clerk.extract_cruxes", 1)
        self.assertEqual(spec.call_id, "run1:clerk.extract_cruxes")
        self.assertEqual(spec.model_id, "clerk")
        self.assertEqual(spec.reasoning, "off")
        between = spec.json_schema["properties"]["cruxes"]["items"]["properties"]["between"]
        self.assertEqual(between["items"]["enum"], ["o1", "o2"])  # built by council.chamber.cruxes
        self.assertGreater(spec.timeout_s, 0)
        if reply is None:
            drv.fail(spec)
        else:
            drv.feed(spec, reply)
        self.assertEqual(d.phase, "r1")
        return d, drv

    def test_clerk_failure_then_heuristic_after_r1(self):
        d, drv = self.clerk_then_r1(None)
        self.assertEqual(d.cruxes(), [])
        self.assertEqual(drv.last("cruxes.extracted")["cruxes"], [])
        drv.r1(self.crit())
        (crux,) = d.cruxes()
        self.assertEqual((crux.id, crux.statement, crux.kind), ("x1", "The loop is O(n^2)", "factual"))
        self.assertEqual(crux.between, ["o1", "o2"])
        self.assertEqual(drv.last("cruxes.extracted")["cruxes"][0]["id"], "x1")
        specs = drv.calls("seat.r2", 5)
        self.assertIn("The loop is O(n^2)", specs[0].messages[1]["content"])
        vote = specs[0].json_schema["$defs"]["CruxVote"]["properties"]["crux_id"]["enum"]
        self.assertEqual(vote, ["x1"])

    def test_clerk_cruxes_are_not_replaced_by_the_heuristic(self):
        reply = {"cruxes": [{"statement": "Is x faster?", "between": ["o1", "o2"], "kind": "checkable"}]}
        d, drv = self.clerk_then_r1(reply)
        before = drv.types().count("cruxes.extracted")
        drv.r1(self.crit())
        self.assertEqual([c.statement for c in d.cruxes()], ["Is x faster?"])
        self.assertEqual(drv.types().count("cruxes.extracted"), before)

    def test_between_with_no_known_option_means_all_options(self):
        reply = {"cruxes": [{"statement": "Which is safer?", "between": ["zz"], "kind": "value"}]}
        d, drv = self.clerk_then_r1(reply)
        (crux,) = d.cruxes()
        self.assertEqual(crux.between, ["o1", "o2"])
        self.assertEqual(crux.kind, "value")

    def test_no_clerk_heuristic_and_evidence_settles_the_crux(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        self.assertEqual(d.cruxes(), [])
        drv.r1(self.crit(check={"kind": "python", "spec": "time_it()", "settles": "A.c1"}))
        self.assertEqual(d.phase, "evidence")
        (crux,) = d.cruxes()
        self.assertFalse(crux.resolved)
        (check,) = d.pending_checks()
        self.assertEqual(check.crux_id, "x1")  # found through the flaw's claim ref
        self.assertEqual(drv.last("evidence.requested")["crux_id"], "x1")
        drv.take(d.on_evidence(check.check_id, EvidenceResult(kind="python", ok=True, output="linear")))
        self.assertTrue(drv.last("evidence.result")["crux_resolved"])
        (crux,) = d.cruxes()
        self.assertTrue(crux.resolved)
        self.assertEqual(crux.resolved_by, "k1")
        (ev,) = d.evidence()
        self.assertEqual((ev.id, ev.crux_id, ev.output), ("k1", "x1", "linear"))
        specs = drv.calls("seat.r2", 5)
        self.assertNotIn("open_cruxes", specs[0].messages[1]["content"])  # nothing is open any more
        for spec in specs:
            drv.feed(spec, ballot("o1"))
        self.assertEqual(d.decision().open_cruxes, [])

    def test_failed_check_leaves_the_crux_open(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        drv.r1(self.crit(check={"kind": "python", "spec": "time_it()", "settles": "the loop is o(n^2)"}))
        (check,) = d.pending_checks()
        self.assertEqual(check.crux_id, "x1")  # matched by the crux statement
        drv.take(d.on_evidence(check.check_id, EvidenceResult(kind="python", ok=False, error="boom")))
        self.assertFalse(drv.last("evidence.result")["crux_resolved"])
        self.assertFalse(d.cruxes()[0].resolved)
        drv.ballots("seat.r2", ["o1"] * 5)
        self.assertEqual([c.id for c in d.decision().open_cruxes], ["x1"])

    def test_minor_flaws_make_no_crux(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        drv.r1(self.crit(flaw={"id": "f1", "text": "typo", "severity": "minor"}))
        self.assertEqual(d.cruxes(), [])
        self.assertEqual(drv.types().count("cruxes.extracted"), 1)

    def test_preference_flaw_becomes_a_value_crux(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        drv.r1(self.crit(flaw={"id": "f1", "text": "Tabs or spaces", "severity": "major", "kind": "preference"}))
        self.assertEqual([c.kind for c in d.cruxes()], ["value"])

    def test_snapshot_keeps_heuristic_cruxes(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        drv.r1(self.crit(check={"kind": "python", "spec": "time_it()", "settles": "A.c1"}))
        d2 = Deliberation.restore(json.loads(json.dumps(d.snapshot())))
        self.assertEqual(d2.cruxes(), d.cruxes())
        self.assertEqual([c.crux_id for c in d2.pending_checks()], ["x1"])


class Accessors(unittest.TestCase):
    def test_after_a_full_debate(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", None])
        drv.r1()
        for spec in drv.calls("seat.r2", 4):
            drv.feed(spec, ballot("o1", ranking=["o1", "o2"]))
        self.assertTrue(d.is_done())
        self.assertEqual(d.r0_options(), {0: "o1", 1: "o1", 2: "o1", 3: "o2", 4: None})
        fb = d.final_ballots()
        self.assertEqual(sorted(fb), [0, 1, 2, 3, 4])
        self.assertIsNone(fb[4])
        self.assertEqual([fb[s].choice for s in range(4)], ["o1"] * 4)
        self.assertEqual(fb[3].ranking, ["o1", "o2"])
        self.assertEqual(sorted(d.drafts()), [0, 1, 2, 3])
        self.assertEqual(d.drafts()[3].answer_key, "C")
        self.assertEqual([o.id for o in d.options()], ["o1", "o2"])
        self.assertEqual(d.options()[0].holders, [0, 1, 2, 3])
        self.assertEqual(d.cruxes(), [])
        self.assertEqual(d.evidence(), [])

    def test_early_exit_gives_ballots_built_from_the_drafts(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "B", "C"])
        self.assertTrue(d.is_done())
        fb = d.final_ballots()
        self.assertEqual([fb[s].choice for s in range(5)], ["o1", "o1", "o1", "o1", "o2"])
        self.assertEqual(fb[4].ranking, ["o2"])
        self.assertEqual(d.r0_options()[4], "o2")

    def test_returned_objects_are_copies(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        d.options()[0].holders.append(99)
        d.drafts()[0].claims.clear()
        d.final_ballots()[0].ranking.append("zz")
        d.r0_options()[0] = "zz"
        self.assertEqual(d.options()[0].holders, [0, 1, 2])
        self.assertEqual(len(d.drafts()[0].claims), 1)
        self.assertEqual(d.final_ballots()[0].ranking, ["o1"])
        self.assertEqual(d.r0_options()[0], "o1")

    def test_feeds_the_outlier_module(self):
        try:
            from council.chamber.outlier import find_outlier
        except ImportError:
            self.skipTest("outlier module not there yet")
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        drv.r1()
        drv.ballots("seat.r2", ["o1", "o1", "o1", "o1", "o2"])
        found = find_outlier(d.final_ballots(), d.r0_options(), d.decision().option_id, len(d.options()))
        seat = found[0] if isinstance(found, tuple) else found
        self.assertEqual(getattr(seat, "seat_no", seat), 4)


class EvidenceSide(unittest.TestCase):
    """EvidenceResult.supports: which option a check result positively supports (27.5)."""

    def run_check(self, settles, result_kw, kind="python"):
        from council.chamber.anonymize import label_to_seat
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])  # seats 0-2 draft o1, seats 3-4 draft o2
        specs = drv.calls("seat.r1", 5)
        check = {"kind": kind, "spec": "print(1+1)", "settles": settles}
        for i, spec in enumerate(specs):
            drv.feed(spec, {"reviews": [], "position": "keep",
                            "checks_requested": [check] if i == 0 else []})
        pending = d.pending_checks()
        drv.take(d.on_evidence(pending[0].check_id, EvidenceResult(kind=kind, ok=True, **result_kw)))
        owner = label_to_seat(list(range(5)), 0, d.seed)
        return d, d.evidence()[-1], owner

    def test_passing_check_supports_the_option_of_the_claims_owner(self):
        for label in ("A", "B", "C", "D"):
            d, ev, owner = self.run_check(f"{label}.c1", {"exit_code": 0})
            self.assertEqual(ev.supports, d.r0_options()[owner[label]], label)
        d, ev, _ = self.run_check("Y.c1", {"exit_code": 0})  # the requester's own claim
        self.assertEqual(ev.supports, d.r0_options()[0])
        d, ev, _ = self.run_check("4:c1", {"exit_code": 0})  # a seat named outright
        self.assertEqual(ev.supports, d.r0_options()[4])

    def test_a_check_that_only_ran_supports_nothing(self):
        for settles, kw, kind in (
            ("A.c1", {"exit_code": 1}, "python"),      # it refuted the claim
            ("A.c1", {}, "python"),                    # no exit code
            ("A.c1", {}, "grep"),                      # a grep is not a verdict
            ("A.c9", {"exit_code": 0}, "python"),      # no such claim
            ("Z.c1", {"exit_code": 0}, "python"),      # no such label
            ("is it B or C?", {"exit_code": 0}, "python"),
            (None, {"exit_code": 0}, "python"),
        ):
            _, ev, _ = self.run_check(settles, kw, kind)
            self.assertIsNone(ev.supports, (settles, kw, kind))

    def test_supports_survives_a_snapshot(self):
        d, ev, _ = self.run_check("A.c1", {"exit_code": 0})
        again = Deliberation.restore(d.snapshot())
        self.assertEqual(again.evidence()[-1].supports, ev.supports)
        self.assertIsNotNone(ev.supports)


def long_mode(reasoning="off", rounds=("r0",), k=3, deadline_s=1000.0):
    return ModeConfig(name="standard", k=k, rounds=list(rounds), deadline_s=deadline_s, reasoning=reasoning)


def lineup6():
    lens = LENSES + ["builder"]
    qs = QS + [0.4]
    return LineupRecord(
        seats=[SeatAssignment(seat_no=i, model_id=f"m{i}", lens=lens[i], q=qs[i]) for i in range(6)], k=6
    )


class TurnTimeouts(unittest.TestCase):
    """Point 1: every call's timeout comes from budget.turn_timeout_s."""

    def test_seat_timeout_follows_the_seat_speed(self):
        d = make(mode=long_mode("council", ("r0", "r1"), k=5, deadline_s=9000.0), seat_tps={0: 75.0, 1: 15.0})
        drv = Driver(self, d)
        specs = drv.calls("seat.r0", 5)
        # five seats share the GPU: speed / 2.5; r0 council is 2200 tokens
        self.assertAlmostEqual(specs[0].timeout_s, 2.5 * 2200 / (75.0 / 2.5))
        self.assertAlmostEqual(specs[1].timeout_s, 2.5 * 2200 / (15.0 / 2.5))
        self.assertAlmostEqual(specs[2].timeout_s, specs[1].timeout_s)  # unknown speed = 15 tps
        self.assertTrue(all(s.timeout_s > 120.0 for s in specs))  # the old flat cut-off

    def test_seat_timeout_is_capped_by_the_time_left_after_the_chair_reserve(self):
        d = make()  # standard: deadline 300, Chair reserve min(400, 0.4 * 300) = 120
        drv = Driver(self, d)
        self.assertAlmostEqual(d.chair_reserve_s(), 120.0)
        self.assertEqual({s.timeout_s for s in drv.calls("seat.r0", 5)}, {180.0})

    def test_seat_timeout_is_never_under_45(self):
        d = make(lineup=lineup(5, alternates=["alt"]))
        drv = Driver(self, d)
        specs = drv.calls("seat.r0", 5)
        d.set_remaining(1.0)
        drv.fail(specs[2])  # invalid output: the alternate is called with 1 s left
        (again,) = drv.calls("seat.r0", 1)
        self.assertEqual(again.model_id, "alt")
        self.assertEqual(again.timeout_s, 45.0)

    def test_chair_timeout(self):
        d = make(mode=long_mode(), lineup=lineup(3))
        drv = Driver(self, d)
        drv.r0(["A", "B", "C"])
        (spec,) = drv.calls("chair")
        self.assertAlmostEqual(spec.timeout_s, 2.5 * 900 / 15.0)  # alone, speed unknown: 150 s
        self.assertEqual(d.chair_reserve_s(), 0.0)  # nothing is held back from the Chair itself

        fast = make(mode=long_mode(), lineup=lineup(3), seat_tps={0: 75.0})
        drv = Driver(self, fast)
        drv.r0(["A", "B", "C"])
        (spec,) = drv.calls("chair")
        self.assertEqual(spec.timeout_s, CHAIR_FLOOR_S)  # 30 s wanted, the floor is 60

    def test_chair_timeout_is_capped_by_the_time_left(self):
        d = make(mode=long_mode(), lineup=lineup(3))
        drv = Driver(self, d)
        specs = drv.calls("seat.r0", 3)
        d.set_remaining(100.0)
        for spec, key in zip(specs, "ABC"):
            drv.feed(spec, draft(key))
        (spec,) = drv.calls("chair")
        self.assertEqual(spec.timeout_s, 100.0)

    def test_ratify_timeout_has_the_floor(self):
        d = make(lineup=lineup(3), mode=long_mode(k=3), plan_mode=True)
        drv = Driver(self, d)
        drv.r0(["A", "B", "C"])
        (spec,) = drv.calls("chair")
        drv.feed(spec, {"option_id": "o1", "final_text": "Plan", "confidence": 0.9})
        specs = drv.calls("ratify", 3)
        self.assertEqual({s.timeout_s for s in specs}, {CHAIR_FLOOR_S})

    def test_clerk_timeout(self):
        d = make(answer_type="freeform", clerk_model_id="clerk")
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        (spec,) = drv.calls("clerk.cluster_options")
        self.assertAlmostEqual(spec.timeout_s, 2.5 * spec.max_output_tokens / 15.0)
        self.assertGreater(spec.timeout_s, 60.0)


class ChairReserve(unittest.TestCase):
    """Point 2: the Chair's time is kept back from the deadline, and a late Chair is still called."""

    def tps(self):
        return {i: 100.0 for i in range(5)}

    def test_no_round_starts_inside_the_chair_reserve(self):
        # Chair (seat 0, 100 tps, council): 2.5 * 2400 / 100 = 60 s reserve.
        # r1 needs 5 * 1300 / 100 / 2 = 32.5 s.
        d = make(seat_tps=self.tps())
        drv = Driver(self, d)
        self.assertAlmostEqual(d.chair_reserve_s(), 60.0)
        d.set_remaining(90.0)  # 30 s of debate left: r1 does not fit
        drv.r0(["B", "B", "B", "C", "C"])
        self.assertEqual(d.decision().outcome, "majority")
        self.assertNotIn("seat.r1", [p.get("purpose") for _, p in drv.events])

        d = make(seat_tps=self.tps())
        drv = Driver(self, d)
        d.set_remaining(95.0)  # 35 s of debate left: r1 fits
        drv.r0(["B", "B", "B", "C", "C"])
        self.assertEqual(d.phase, "r1")

    def test_only_the_reserve_left_goes_straight_to_the_chair(self):
        d = make(seat_tps=self.tps())
        drv = Driver(self, d)
        specs = drv.calls("seat.r0", 5)
        d.set_remaining(60.0)
        for spec, key in zip(specs, ["B", "B", "C", "C", "D"]):
            drv.feed(spec, draft(key))
        self.assertEqual(d.phase, "chair")
        (spec,) = drv.calls("chair")
        self.assertEqual(spec.timeout_s, 60.0)  # the reserve is exactly what the Chair gets

    def test_deadline_with_time_really_left_gives_it_to_the_chair(self):
        d = make(mode=long_mode(rounds=("r0", "r1"), k=5), lineup=lineup(5))
        drv = Driver(self, d)
        drv.r0(["B", "B", "C", "C", "D"])
        drv.calls("seat.r1", 5)
        drv.take(d.on_deadline(120.0))  # the driver stops the debate with the reserve still left
        self.assertEqual(d.phase, "chair")
        (spec,) = drv.calls("chair")
        self.assertEqual(spec.timeout_s, 120.0)
        drv.fail(spec, "server_error")  # a quick failure with time left: the next Chair is tried
        (second,) = drv.calls("chair")
        self.assertNotEqual(second.model_id, spec.model_id)
        drv.feed(second, {"option_id": "o2", "final_text": "C.", "confidence": 0.7})
        dec = d.decision()
        self.assertEqual((dec.outcome, dec.option_id, dec.notes), ("chair", "o2", []))

    def test_chair_called_after_the_deadline_gets_its_floor_and_a_note(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "C", "C", "D"])
        drv.calls("seat.r1", 5)
        drv.take(d.on_deadline())  # no time left at all
        self.assertEqual(d.phase, "chair")
        (spec,) = drv.calls("chair")
        self.assertEqual(spec.timeout_s, CHAIR_FLOOR_S)
        drv.feed(spec, {"option_id": "o1", "final_text": "B, late.", "confidence": 0.7})
        dec = d.decision()
        self.assertEqual(dec.outcome, "chair")
        self.assertEqual(dec.final_text, "B, late.")
        self.assertEqual(dec.notes, [LATE_CHAIR_NOTE])
        self.assertEqual(drv.last("decision.final")["decision"]["notes"], [LATE_CHAIR_NOTE])

    def test_no_note_when_the_chair_was_in_time(self):
        d = make(mode="quick", lineup=lineup(3))
        drv = Driver(self, d)
        drv.r0(["A", "B", "C"])
        (spec,) = drv.calls("chair")
        drv.feed(spec, {"option_id": "o1", "final_text": "A.", "confidence": 0.7})
        self.assertEqual(d.decision().notes, [])

    def test_the_note_survives_a_snapshot(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "C", "C", "D"])
        drv.calls("seat.r1", 5)
        drv.take(d.on_deadline())
        again = Deliberation.restore(d.snapshot())
        (spec,) = again.pending_calls()
        again.on_result(ok(spec, {"option_id": "o1", "final_text": "B.", "confidence": 0.7}))
        self.assertEqual(again.decision().notes, [LATE_CHAIR_NOTE])


class DeadlineFallback(unittest.TestCase):
    """Point 3: majority only above 50%, else the Chair; deadlock only when the Chair call fails."""

    def at_deadline(self, keys, k=5):
        d = make(lineup=lineup(k))
        drv = Driver(self, d)
        drv.r0(keys)
        drv.calls("seat.r1")
        drv.take(d.on_deadline())
        return d, drv

    def test_over_half_is_majority(self):
        d, drv = self.at_deadline(["B", "B", "B", "C", "D"])
        self.assertEqual(d.decision().outcome, "majority")
        self.assertEqual(d.decision().notes, [])

    def test_strict_plurality_under_half_goes_to_the_chair(self):
        d, drv = self.at_deadline(["B", "B", "C", "D", "E"])  # B leads with 40%
        self.assertFalse(d.is_done())
        self.assertEqual(d.phase, "chair")
        self.assertEqual(drv.last("consensus.failed")["next_step"], "chair")
        (spec,) = drv.calls("chair")
        drv.feed(spec, {"option_id": "o1", "final_text": "B.", "confidence": 0.6})
        dec = d.decision()
        self.assertEqual((dec.outcome, dec.option_id), ("chair", "o1"))
        self.assertEqual(dec.tally["o1"], 2)

    def test_half_by_count_is_decided_by_the_weighted_share_as_before(self):
        # B has 2 of 4. Held by the two weakest seats its weighted share is under 50%: Chair.
        d, drv = self.at_deadline(["C", "D", "B", "B"], k=4)
        self.assertEqual(d.phase, "chair")
        # Held by the two strongest seats its weighted share is over 50%: majority.
        d, drv = self.at_deadline(["B", "B", "C", "D"], k=4)
        self.assertEqual(d.decision().outcome, "majority")

    def test_deadlock_only_when_the_chair_call_fails(self):
        d, drv = self.at_deadline(["B", "B", "C", "D", "E"])
        (spec,) = drv.calls("chair")
        self.assertFalse(d.is_done())
        drv.fail(spec, "timeout")
        dec = d.decision()
        self.assertEqual(dec.outcome, "deadlock")
        self.assertEqual(dec.option_id, "o1")
        self.assertEqual(dec.final_text, "The answer is B.")  # the leading option's best text
        self.assertEqual(d.pending_calls(), [])  # no time left: no second Chair

    def test_deadline_in_a_ballot_round_goes_to_the_chair(self):
        d = make()
        drv = Driver(self, d)
        drv.r0(["B", "B", "C", "C", "D"])
        drv.r1()
        specs = drv.calls("seat.r2", 5)
        drv.feed(specs[0], ballot("o1"))
        drv.take(d.on_deadline(90.0))
        self.assertEqual(d.phase, "chair")
        (spec,) = drv.calls("chair")
        self.assertEqual(spec.timeout_s, 90.0)
        drv.feed(spec, {"option_id": "o1", "final_text": "B.", "confidence": 0.6})
        self.assertEqual(d.decision().outcome, "chair")


class EarlyAgreementSixSeats(unittest.TestCase):
    """Point 4: 5 of 6 agreeing (83%) with mean confidence >= 0.7 ends after round 0."""

    def run_r0(self, drafts):
        d = make(lineup=lineup6())
        drv = Driver(self, d)
        for spec, parsed in zip(drv.calls("seat.r0", 6), drafts):
            drv.feed(spec, parsed)
        return d, drv

    def test_five_of_six_at_the_confidence_bar_exits(self):
        d, drv = self.run_r0([draft("B", 0.7)] * 5 + [draft("C", 0.2)])
        self.assertTrue(d.is_done())
        dec = d.decision()
        self.assertEqual(dec.outcome, "consensus")
        self.assertAlmostEqual(dec.agreement, 5 / 6)
        self.assertEqual(dec.rounds_run, 1)
        self.assertTrue(drv.last("consensus.reached")["early"])
        self.assertNotIn("seat.r1", [p.get("purpose") for _, p in drv.events])
        self.assertEqual(dec.minority_report[0].seats, [5])

    def test_the_dissenter_confidence_does_not_count(self):
        d, _ = self.run_r0([draft("C", 0.0)] + [draft("B", 0.75)] * 5)
        self.assertTrue(d.is_done())

    def test_under_the_confidence_bar_debates_by_design(self):
        d, _ = self.run_r0([draft("B", 0.69)] * 5 + [draft("C", 0.99)])
        self.assertFalse(d.is_done())
        self.assertEqual(d.phase, "r1")

    def test_four_of_six_debates(self):
        d, _ = self.run_r0([draft("B", 0.95)] * 4 + [draft("C", 0.9)] * 2)
        self.assertEqual(d.phase, "r1")

    def test_a_missing_confidence_is_not_counted_as_half(self):
        # Three seats state 0.8, two say nothing. Counting the silent two as 0.5 would give a
        # mean of 0.68 and a debate round at 83% agreement.
        silent = {k: v for k, v in draft("B").items() if k != "confidence"}
        d, _ = self.run_r0([draft("B", 0.8)] * 3 + [silent] * 2 + [draft("C", 0.9)])
        self.assertTrue(d.is_done())
        self.assertEqual(d.decision().outcome, "consensus")
        self.assertAlmostEqual(d.decision().agreement, 5 / 6)

    def test_too_few_stated_confidences_debate(self):
        silent = {k: v for k, v in draft("B").items() if k != "confidence"}
        d, _ = self.run_r0([draft("B", 0.95)] * 2 + [silent] * 3 + [draft("C", 0.9)])
        self.assertEqual(d.phase, "r1")  # 2 of 5 stated one: not enough to skip the debate
        d, _ = self.run_r0([silent] * 5 + [draft("C", 0.9)])
        self.assertEqual(d.phase, "r1")

    def test_stated_confidences_survive_a_snapshot(self):
        silent = {k: v for k, v in draft("B").items() if k != "confidence"}
        d = make(lineup=lineup6())
        specs = d.pending_calls()
        for spec, parsed in zip(specs[:5], [draft("B", 0.8)] * 3 + [silent] * 2):
            d.on_result(ok(spec, parsed))
        again = Deliberation.restore(d.snapshot())
        (last,) = again.pending_calls()
        again.on_result(ok(last, draft("C", 0.9)))
        self.assertTrue(again.is_done())
        self.assertEqual(again.decision().outcome, "consensus")


def short_mode():
    """Standard mode with r2 as the last planned round."""
    return MODE_DEFAULTS["standard"].model_copy(update={"rounds": ["r0", "r1", "r2"]})


def flat_lineup(k=6):
    """Equal q for every seat: a tie by count is a tie by weight, so the fallback is the Chair."""
    lens = LENSES + ["builder"]
    seats = [SeatAssignment(seat_no=i, model_id=f"m{i}", lens=lens[i], q=0.5) for i in range(k)]
    return LineupRecord(seats=seats, k=k)


class DynamicExtension(unittest.TestCase):
    """The council may keep arguing while it is getting closer (max_extra_rounds)."""

    def test_sixty_percent_then_extension_then_consensus(self):
        d = make(mode=short_mode(), max_extra_rounds=2)
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        drv.r1()
        drv.ballots("seat.r2", ["o1", "o1", "o1", "o2", "o2"])
        self.assertEqual(d.phase, "r3")
        ext = drv.last("round.extended")
        self.assertEqual(ext["round"], 3)
        self.assertAlmostEqual(ext["agreement"], 0.6)
        self.assertEqual((ext["extra_used"], ext["extra_max"]), (1, 2))
        self.assertTrue(ext["reason"])
        self.assertEqual(drv.last("consensus.failed")["next_step"], "round")
        tail = drv.types()[-4:]
        self.assertEqual(tail, ["round.completed", "round.extended", "consensus.failed", "round.started"])
        self.assertEqual(drv.last("round.started")["round"], 3)
        specs = drv.ballots("seat.r3", ["o1"] * 5)
        self.assertEqual(len(specs), 5)
        self.assertIn("Round 3", specs[0].messages[1]["content"])
        dec = d.decision()
        self.assertEqual(dec.outcome, "consensus")
        self.assertEqual(dec.rounds_run, 4)  # one more than the three planned rounds
        self.assertEqual(dec.tally, {"o1": 5})
        self.assertEqual(drv.types().count("round.extended"), 1)

    def test_rising_agreement_extends_after_the_planned_r3(self):
        d = make(max_extra_rounds=1)
        drv = Driver(self, d)
        drv.r0(["B", "B", "C", "C", "D"])
        drv.r1()
        drv.ballots("seat.r2", ["o1", "o1", "o2", "o2", "o3"])  # 40%
        self.assertNotIn("round.extended", drv.types())  # a planned round was left
        drv.ballots("seat.r3", ["o1", "o1", "o1", "o2", "o2"])  # 60%: rose
        self.assertEqual(d.phase, "r3")
        self.assertIn("rose", drv.last("round.extended")["reason"])
        drv.ballots("seat.r3", ["o1", "o1", "o1", "o1", "o2"])
        dec = d.decision()
        self.assertEqual(dec.outcome, "consensus")
        self.assertEqual(dec.rounds_run, 5)
        self.assertEqual(drv.last("round.completed")["round"], 4)

    def test_extra_rounds_are_capped(self):
        d = make(mode=short_mode(), lineup=flat_lineup(), max_extra_rounds=1)
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C", "C"])
        drv.r1()
        drv.ballots("seat.r2", ["o1", "o1", "o1", "o2", "o2", "o2"])  # 50%, first ballot round
        self.assertEqual(d.phase, "r3")
        drv.ballots("seat.r3", ["o1", "o1", "o1", "o1", "o2", "o2"])  # 67%: rose, but none left
        self.assertTrue(d.is_done())
        self.assertEqual(d.decision().outcome, "majority")
        self.assertEqual(drv.types().count("round.extended"), 1)

    def test_stagnating_tallies_go_to_the_chair_without_extension(self):
        d = make(lineup=flat_lineup(), max_extra_rounds=2)
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C", "C"])
        drv.r1()
        split = ["o1", "o1", "o1", "o2", "o2", "o2"]
        drv.ballots("seat.r2", split)
        drv.ballots("seat.r3", split)  # same tally twice: arguing changed nothing
        self.assertNotIn("round.extended", drv.types())
        self.assertEqual(d.phase, "chair")
        self.assertEqual(drv.last("consensus.failed")["next_step"], "chair")
        (spec,) = drv.calls("chair")
        drv.feed(spec, {"option_id": "o1", "final_text": "Chair text", "confidence": 0.7})
        self.assertEqual(d.decision().outcome, "chair")
        self.assertEqual(d.decision().rounds_run, 4)

    def test_stagnation_stops_a_running_extension(self):
        d = make(mode=short_mode(), lineup=flat_lineup(), max_extra_rounds=3)
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C", "C"])
        drv.r1()
        split = ["o1", "o1", "o1", "o2", "o2", "o2"]
        drv.ballots("seat.r2", split)  # first ballot round: extended
        drv.ballots("seat.r3", split)  # nothing moved: stop, two extra rounds unused
        self.assertEqual(drv.types().count("round.extended"), 1)
        self.assertEqual(d.phase, "chair")

    def test_low_agreement_is_not_extended(self):
        d = make(mode=short_mode(), max_extra_rounds=2)
        drv = Driver(self, d)
        drv.r0(["B", "B", "C", "C", "D"])
        drv.r1()
        drv.ballots("seat.r2", ["o1", "o1", "o2", "o2", "o3"])  # 40% < extend_min_agreement
        self.assertNotIn("round.extended", drv.types())
        self.assertEqual(d.phase, "chair")

    def test_blocking_objections_are_not_extended(self):
        d = make(mode=short_mode(), max_extra_rounds=2)
        drv = Driver(self, d)
        drv.r0(["A", "A", "A", "B", "C"])
        drv.r1()
        for spec, choice in zip(drv.calls("seat.r2"), ["o1", "o1", "o1", "o2", "o3"]):
            extra = {"blocking_objection": "o1 is wrong"} if choice != "o1" else {}
            drv.feed(spec, ballot(choice, **extra))
        self.assertNotIn("round.extended", drv.types())
        self.assertEqual(d.decision().outcome, "majority")

    def test_no_extension_without_time(self):
        d = make(mode=short_mode(), max_extra_rounds=2)
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        drv.r1()
        specs = drv.calls("seat.r2")
        for spec, choice in zip(specs[:4], ["o1", "o1", "o1", "o2"]):
            drv.feed(spec, ballot(choice))
        drv.take(d.on_deadline())
        self.assertNotIn("round.extended", drv.types())
        self.assertTrue(d.is_done())
        self.assertEqual(d.decision().outcome, "majority")

    def run_plain(self, **kw):
        d = make(mode=short_mode(), **kw)
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        drv.r1()
        drv.ballots("seat.r2", ["o1", "o1", "o1", "o2", "o2"])
        return d, drv

    def test_zero_extra_rounds_is_identical_to_before(self):
        d, drv = self.run_plain()
        d0, drv0 = self.run_plain(max_extra_rounds=0)
        self.assertTrue(d.is_done())
        self.assertEqual(d.decision().outcome, "majority")
        self.assertEqual(d.decision().rounds_run, 3)
        self.assertNotIn("round.extended", drv.types())
        self.assertEqual(drv0.events, drv.events)
        self.assertEqual(d0.decision(), d.decision())

    def test_snapshot_and_restore_mid_extension(self):
        d = make(mode=short_mode(), lineup=flat_lineup(), max_extra_rounds=1)
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C", "C"])
        drv.r1()
        drv.ballots("seat.r2", ["o1", "o1", "o1", "o2", "o2", "o2"])
        specs = drv.calls("seat.r3", 6)
        for spec in specs[:2]:
            drv.feed(spec, ballot("o1"))
        snap = json.loads(json.dumps(d.snapshot()))
        self.assertEqual(snap["state"]["extra_used"], 1)
        self.assertAlmostEqual(snap["state"]["prev_agreement"], 0.5)
        self.assertEqual(snap["state"]["prev_tally"], {"o1": 3, "o2": 3})
        self.assertEqual(snap["args"]["max_extra_rounds"], 1)
        d2 = Deliberation.restore(snap)
        self.assertEqual(d2.phase, "r3")
        self.assertEqual(d2.snapshot(), snap)
        again = d2.pending_calls()
        self.assertEqual([s.call_id for s in again], [s.call_id for s in specs[2:]])
        out = []
        for machine, rest in ((d, specs[2:]), (d2, again)):
            events = []
            for spec, choice in zip(rest, ["o1", "o1", "o2", "o2"]):  # 67%: rose, cap reached
                events = machine.on_result(ok(spec, ballot(choice)))
            self.assertNotIn("round.extended", [t for t, _ in events])
            self.assertTrue(machine.is_done())
            out.append(machine.decision().model_dump(mode="json"))
        self.assertEqual(out[0], out[1])
        self.assertEqual(out[0]["outcome"], "majority")
        self.assertEqual(out[0]["rounds_run"], 4)

    def test_old_snapshot_without_the_new_keys_restores(self):
        d = make()
        snap = d.snapshot()
        for key in ("max_extra_rounds", "extend_min_agreement"):
            del snap["args"][key]
        for key in ("extra_used", "prev_agreement", "prev_tally"):
            del snap["state"][key]
        d2 = Deliberation.restore(snap)
        self.assertEqual(d2.max_extra_rounds, 0)
        self.assertEqual(len(d2.pending_calls()), 5)


# --------------------------------------------------------------------------------------
# 1.5: lie notes, compaction, council sizes 2 to 6
# --------------------------------------------------------------------------------------

LIE_HEADER = lie_notes.HEADER


def flag(seat, claim="c1", level="flag", score=0.2, text=None):
    return LieFlag(
        run_id="run1", seat_no=seat, model_id=f"m{seat}", claim_id=claim,
        text=text or f"shaky claim of seat {seat}", probe_score=score, level=level,
    )


class LieNotes(unittest.TestCase):
    def start(self, **kw):
        d = make(**kw)
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        self.assertEqual(d.phase, "r1")
        return d, drv

    def test_no_flags_no_block(self):
        d, drv = self.start()
        d.set_lie_flags([])
        for spec in drv.calls("seat.r1", 5):
            self.assertNotIn(LIE_HEADER, spec.messages[1]["content"])

    def test_ok_flags_make_no_block(self):
        d, drv = self.start()
        d.set_lie_flags([flag(1, level="ok")])
        plain = self.start()[1].calls("seat.r1", 5)
        self.assertEqual([s.messages for s in drv.calls("seat.r1", 5)], [s.messages for s in plain])

    def test_block_uses_the_letters_that_seat_sees(self):
        d, drv = self.start()
        d.set_lie_flags([flag(1), flag(3, level="watch", score=0.4)])
        for spec in drv.calls("seat.r1", 5):
            seat = spec.meta["seat_no"]
            body = spec.messages[1]["content"]
            self.assertEqual(body.count(LIE_HEADER), 1)
            block = body[body.index(LIE_HEADER):]
            self.assertTrue(body.endswith(lie_notes.FOOTER))
            letter = {s: lab for lab, s in label_to_seat(list(range(5)), seat, 0).items()}
            for other in (1, 3):
                if other == seat:
                    self.assertIn(f'Your claim c1: "shaky claim of seat {other}"', block)
                else:
                    self.assertIn(f'Draft {letter[other]}, claim c1: "shaky claim of seat {other}"', block)
            self.assertNotIn("m1", block)  # no model id
            self.assertNotIn("seat_no", block)
            # the block is exactly what lie_notes builds
            self.assertEqual(block, lie_notes.notes_for_seat(d._lie_flags, seat, letter))

    def test_block_comes_after_the_claim_scores(self):
        d, drv = self.start()
        d.set_lie_flags([flag(1)])
        d.set_claim_scores([ClaimScore(seat_no=1, claim_ref="c1", text="t", reliability=0.3)])
        body = drv.calls("seat.r1", 5)[0].messages[1]["content"]
        self.assertEqual(body.count(HEADING), 1)
        self.assertEqual(body.count(LIE_HEADER), 1)
        self.assertLess(body.index(HEADING), body.index(LIE_HEADER))

    def test_either_setter_keeps_the_other_block(self):
        for first in ("scores", "flags"):
            d, drv = self.start()
            score = [ClaimScore(seat_no=1, claim_ref="c1", text="t", reliability=0.3)]
            if first == "scores":
                d.set_claim_scores(score)
                d.set_lie_flags([flag(1)])
            else:
                d.set_lie_flags([flag(1)])
                d.set_claim_scores(score)
            body = drv.calls("seat.r1", 5)[0].messages[1]["content"]
            self.assertEqual((body.count(HEADING), body.count(LIE_HEADER)), (1, 1), first)

    def test_setting_twice_replaces_and_empty_removes(self):
        d, drv = self.start()
        d.set_lie_flags([flag(1), flag(2)])
        d.set_lie_flags([flag(2, text="only this one")])
        body = drv.calls("seat.r1", 5)[0].messages[1]["content"]
        self.assertEqual(body.count(LIE_HEADER), 1)
        self.assertIn("only this one", body)
        self.assertNotIn("shaky claim of seat 1", body)
        d2, drv2 = self.start()
        d2.set_lie_flags([flag(1)])
        d2.set_lie_flags([])
        plain = self.start()[1].calls("seat.r1", 5)
        self.assertEqual([s.messages for s in drv2.calls("seat.r1", 5)], [s.messages for s in plain])

    def test_flags_set_before_round_1_are_used(self):
        d = make()
        d.set_lie_flags([flag(1).model_dump()])  # a plain dict is accepted
        drv = Driver(self, d)
        drv.r0(["B", "B", "B", "C", "C"])
        self.assertIn(LIE_HEADER, drv.calls("seat.r1", 5)[0].messages[1]["content"])

    def test_notes_are_not_shown_after_round_1_and_do_not_change_the_vote(self):
        def run(with_flags):
            d, drv = self.start()
            if with_flags:
                d.set_lie_flags([flag(s) for s in range(5)])
            drv.r1()
            specs = drv.calls("seat.r2", 5)
            for spec, choice in zip(specs, ["o1", "o1", "o1", "o1", "o2"]):
                self.assertNotIn(LIE_HEADER, spec.messages[1]["content"])
                drv.feed(spec, ballot(choice))
            return d.decision().model_dump(mode="json")

        self.assertEqual(run(True), run(False))

    def test_patched_calls_are_the_ones_a_result_is_matched_against(self):
        d, drv = self.start()
        d.set_lie_flags([flag(1)])
        drv.r1()
        self.assertEqual(d.phase, "r2")

    def test_snapshot_keeps_flags_and_the_patched_calls(self):
        d, drv = self.start()
        d.set_lie_flags([flag(1), flag(3, level="watch")])
        snap = json.loads(json.dumps(d.snapshot()))
        d2 = Deliberation.restore(snap)
        self.assertEqual(d2.snapshot(), snap)
        self.assertEqual([f.seat_no for f in d2._lie_flags], [1, 3])
        a, b = d.pending_calls(), d2.pending_calls()
        self.assertEqual([s.messages for s in a], [s.messages for s in b])
        self.assertIn(LIE_HEADER, b[0].messages[1]["content"])

    def test_old_snapshot_without_flags_restores(self):
        d, _ = self.start()
        snap = d.snapshot()
        del snap["state"]["lie_flags"]
        del snap["args"]["ctx_tokens"]
        d2 = Deliberation.restore(snap)
        self.assertEqual(d2._lie_flags, [])
        self.assertEqual(d2.ctx_tokens, DEFAULT_CTX_TOKENS)


def big_draft(key, claims=8, risks=5):
    return {
        "answer": f"The answer is {key}.",
        "answer_key": key,
        "summary": f"Answer {key}",
        "claims": [{"id": f"c{i}", "text": f"claim {i} of {key} " + "x" * 70} for i in range(1, claims + 1)],
        "risks": [f"risk {i} " + "y" * 30 for i in range(1, risks + 1)],
        "confidence": 0.9,
    }


def refs_of(spec):
    return spec.json_schema["properties"]["changed_because"]["items"].get("enum", [])


class Compaction(unittest.TestCase):
    def r1_specs(self, drafts, **kw):
        d = make(**kw)
        drv = Driver(self, d)
        for spec, parsed in zip(drv.calls("seat.r0", 5), drafts):
            drv.feed(spec, parsed)
        self.assertEqual(d.phase, "r1")
        return d, drv, drv.calls("seat.r1", 5)

    def test_default_is_16384(self):
        self.assertEqual(DEFAULT_CTX_TOKENS, 16384)
        self.assertEqual(make().ctx_tokens, 16384)

    def test_default_changes_nothing_for_small_inputs(self):
        keys = ["B", "B", "B", "C", "C"]
        for drafts in ([draft(k) for k in keys], [big_draft(k) for k in keys]):
            _, _, default = self.r1_specs(drafts)
            _, _, huge = self.r1_specs(drafts, ctx_tokens=10**7)
            self.assertEqual(
                [(s.messages, s.json_schema) for s in default], [(s.messages, s.json_schema) for s in huge]
            )

    def test_small_context_cuts_the_pasted_drafts_in_round_1(self):
        drafts = [big_draft(k) for k in ["B", "B", "B", "C", "C"]]
        _, _, full = self.r1_specs(drafts)
        d, drv, small = self.r1_specs(drafts, ctx_tokens=2048)
        for a, b in zip(full, small):
            self.assertLess(len(b.messages[1]["content"]), len(a.messages[1]["content"]))
            self.assertEqual(a.messages[0], b.messages[0])  # the system prompt is not touched
            body = b.messages[1]["content"]
            self.assertIn("A.c5", body)
            self.assertNotIn("A.c6", body)  # compact keeps five claims
            self.assertIn("Y.c8", body)  # the seat's own draft is not cut
            self.assertNotIn("risk 3", body.split("OTHERS:")[1].split("POINTS OF DISAGREEMENT")[0])
            # a claim that was cut cannot be cited
            self.assertIn("A.c6", refs_of(a))
            self.assertNotIn("A.c6", refs_of(b))
            self.assertIn("A.c5", refs_of(b))
            self.assertIn("Y.c8", refs_of(b))
        # the debate still runs to the end
        for spec in small:
            drv.feed(spec, {"reviews": [], "position": "keep"})
        drv.ballots("seat.r2", ["o1"] * 5)
        self.assertEqual(d.decision().outcome, "consensus")

    def critique_run(self, n_flaws, **kw):
        d, drv, specs = self.r1_specs([draft(k) for k in ["B", "B", "B", "C", "C"]], **kw)
        for spec in specs:
            seat = spec.meta["seat_no"]
            flaws = [
                {"id": f"f{i}", "text": f"flaw {i} " + "z" * 200, "severity": "minor"}
                for i in range(1, n_flaws + 1)
            ]
            flaws.append({"id": "f99", "text": "the fatal one", "severity": "fatal"})
            reviews = [
                {"target": label, "flaws": flaws}
                for label in label_to_seat(list(range(5)), seat, 0)
            ]
            drv.feed(spec, {"reviews": reviews, "position": "keep"})
        self.assertEqual(d.phase, "r2")
        return d, drv, drv.calls("seat.r2", 5)

    def test_default_pastes_all_critiques_in_round_2(self):
        _, _, default = self.critique_run(2)
        _, _, huge = self.critique_run(2, ctx_tokens=10**7)
        self.assertEqual(
            [(s.messages, s.json_schema) for s in default], [(s.messages, s.json_schema) for s in huge]
        )
        body = default[0].messages[1]["content"]
        self.assertEqual(body.count('"severity":"minor"'), 8)  # 4 reviewers x 2 flaws
        self.assertEqual(body.count('"severity":"fatal"'), 4)
        self.assertIn("z" * 200, body)  # text is not clipped when it fits

    def test_small_context_keeps_the_worst_critiques_in_round_2(self):
        _, _, full = self.critique_run(6)
        d, drv, small = self.critique_run(6, ctx_tokens=2048)
        for a, b in zip(full, small):
            body = b.messages[1]["content"]
            self.assertLess(len(body), len(a.messages[1]["content"]))
            self.assertEqual(body.count('"severity":"fatal"'), 4)  # the fatal flaws come first and stay
            self.assertLess(body.count('"severity":"minor"'), 24)
            self.assertNotIn("blocking", body.split("Criticisms aimed")[1].split("Results of checks")[0])
            kept = [r for r in refs_of(b) if r.endswith(".f99")]
            self.assertEqual(len(kept), 4)
            # a critique that was dropped cannot be cited
            self.assertLess(len(refs_of(b)), len(refs_of(a)))
            for ref in refs_of(b):
                if "." in ref and ref.split(".")[1].startswith("f"):
                    self.assertIn(f'"id":"{ref}"', body)
        for spec in small:
            drv.feed(spec, ballot("o1"))
        self.assertEqual(d.decision().outcome, "consensus")

    def test_snapshot_keeps_ctx_tokens(self):
        d = make(ctx_tokens=4096)
        d2 = Deliberation.restore(json.loads(json.dumps(d.snapshot())))
        self.assertEqual(d2.ctx_tokens, 4096)
        self.assertEqual(d2.snapshot(), d.snapshot())


SIZE_LENSES = LENSES + ["user_advocate"]
SIZE_QS = QS + [0.4]


def lineup_k(k):
    seats = [
        SeatAssignment(seat_no=i, model_id=f"m{i}", lens=SIZE_LENSES[i], q=SIZE_QS[i]) for i in range(k)
    ]
    return LineupRecord(seats=seats, k=k)


def split_keys(k):
    """A round 0 split under 80% for every size: 1-1, 2-1, 2-2, 3-2, 3-3. B is option o1."""
    lead = (k + 1) // 2
    return ["B"] * lead + ["C"] * (k - lead)


class CouncilSizes(unittest.TestCase):
    """A full mock deliberation for every council size the UI offers: 2, 3, 4, 5, 6."""

    SIZES = (2, 3, 4, 5, 6)

    def run_all(self, k, r0_keys, votes, mode="standard", chair_pick=None, **kw):
        """Drive to the end. votes: {seat: option id} used in every ballot round."""
        d = make(mode, lineup=lineup_k(k), **kw)
        drv = Driver(self, d)
        seen = []
        guard = 0
        while not d.is_done():
            guard += 1
            self.assertLess(guard, 20, "deliberation does not finish")
            specs = d.pending_calls()
            self.assertTrue(specs, f"k={k}: stuck in phase {d.phase}")
            for spec in specs:
                seen.append(spec)
                seat = spec.meta.get("seat_no")
                if spec.purpose == "seat.r0":
                    key = r0_keys[seat]
                    drv.fail(spec) if key is None else drv.feed(spec, draft(key))
                elif spec.purpose == "seat.r1":
                    drv.feed(spec, {"reviews": [], "position": "keep"})
                elif spec.purpose in ("seat.r2", "seat.r3"):
                    drv.feed(spec, ballot(votes[seat]))
                elif spec.purpose == "chair":
                    top = spec.json_schema["properties"]["option_id"]["enum"]
                    drv.feed(spec, {"option_id": chair_pick or top[0], "final_text": "Chair text.",
                                    "confidence": 0.8})
                elif spec.purpose == "ratify":
                    drv.feed(spec, {"approve": True, "reason": "fine"})
                else:
                    self.fail(f"unexpected call {spec.purpose}")
        return d, drv, seen

    def test_everyone_agrees_at_once(self):
        for k in self.SIZES:
            with self.subTest(k=k):
                d, drv, seen = self.run_all(k, ["B"] * k, {})
                dec = d.decision()
                self.assertEqual(dec.outcome, "consensus")
                self.assertEqual(dec.agreement, 1.0)
                self.assertEqual(dec.rounds_run, 1)
                self.assertEqual(dec.minority_report, [])
                self.assertEqual(len(seen), k)
                self.assertTrue(drv.last("consensus.reached")["early"])

    def test_split_then_everyone_converges(self):
        for k in self.SIZES:
            with self.subTest(k=k):
                keys = split_keys(k)
                d, drv, seen = self.run_all(k, keys, {s: "o1" for s in range(k)})
                dec = d.decision()
                self.assertEqual(dec.outcome, "consensus")
                self.assertEqual(dec.agreement, 1.0)
                self.assertEqual(dec.tally, {"o1": k})
                self.assertEqual(dec.answer_key, "b")
                self.assertEqual([s.purpose for s in seen].count("seat.r1"), k)
                self.assertNotIn("chair.started", drv.types())

    def test_anonymous_letters_cover_the_other_seats(self):
        for k in self.SIZES:
            with self.subTest(k=k):
                keys = split_keys(k)
                _, _, seen = self.run_all(k, keys, {s: "o1" for s in range(k)})
                letters = [chr(ord("A") + i) for i in range(k - 1)]
                for spec in seen:
                    if spec.purpose != "seat.r1":
                        continue
                    target = spec.json_schema["$defs"]["Review"]["properties"]["target"]
                    self.assertEqual(target["enum"], letters)
                    position = spec.json_schema["properties"]["position"]["enum"]
                    self.assertEqual(position, ["keep", "revise"] + [f"adopt:{x}" for x in letters])
                    self.assertNotIn(f"m{spec.meta['seat_no']}", spec.messages[1]["content"])

    def test_one_dissenter_to_the_end(self):
        # share of the leading option is (k-1)/k: under 80% for 2, 3 and 4 seats, at least 80% for 5 and 6
        want = {2: "chair", 3: "majority", 4: "majority", 5: "consensus", 6: "consensus"}
        for k in self.SIZES:
            with self.subTest(k=k):
                keys = split_keys(k)
                votes = {s: "o1" for s in range(k - 1)}
                votes[k - 1] = "o2"
                d, drv, _ = self.run_all(k, keys, votes)
                dec = d.decision()
                self.assertEqual(dec.outcome, want[k])
                self.assertEqual(dec.option_id, "o1")
                self.assertAlmostEqual(dec.agreement, (k - 1) / k)
                self.assertEqual(dec.tally, {"o1": k - 1, "o2": 1})
                (minority,) = dec.minority_report
                self.assertEqual(minority.seats, [k - 1])
                self.assertEqual(minority.option_id, "o2")
                self.assertTrue(minority.strongest_argument)
                self.assertEqual(d.final_ballots()[k - 1].choice, "o2")

    def test_quick_mode_runs_for_every_size(self):
        for k in self.SIZES:
            with self.subTest(k=k):
                keys = split_keys(k)
                d, _, _ = self.run_all(k, keys, {s: "o1" for s in range(k)}, mode="quick")
                self.assertTrue(d.is_done())
                self.assertIn(d.decision().outcome, ("consensus", "majority", "chair"))
                self.assertEqual(d.decision().option_id, "o1")

    def test_snapshot_round_trip_for_every_size(self):
        for k in self.SIZES:
            with self.subTest(k=k):
                d = make(lineup=lineup_k(k))
                drv = Driver(self, d)
                drv.r0(split_keys(k))
                snap = json.loads(json.dumps(d.snapshot()))
                d2 = Deliberation.restore(snap)
                self.assertEqual(d2.snapshot(), snap)
                self.assertEqual(len(d2.pending_calls()), k)


class TwoSeats(unittest.TestCase):
    """k = 2: quorum is 2 and the 80% bar means both must agree."""

    def start(self, mode="standard", **kw):
        d = make(mode, lineup=lineup_k(2), **kw)
        return d, Driver(self, d)

    def test_both_agree_is_consensus_after_r0(self):
        d, drv = self.start()
        drv.r0(["B", "B"])
        self.assertEqual(d.decision().outcome, "consensus")
        self.assertEqual(d.decision().tally, {"o1": 2})

    def test_agreement_under_the_confidence_bar_debates(self):
        d, drv = self.start()
        drv.r0(["B", "B"], conf=0.5)
        self.assertEqual(d.phase, "r1")
        (spec0, spec1) = drv.calls("seat.r1", 2)
        self.assertIn('"label":"A"', spec0.messages[1]["content"])
        self.assertNotIn('"label":"B"', spec0.messages[1]["content"])

    def test_split_goes_to_debate_not_to_an_early_exit(self):
        d, drv = self.start()
        drv.r0(["B", "C"])
        self.assertEqual(d.phase, "r1")
        self.assertEqual(drv.last("round.completed")["agreement"], 0.5)
        self.assertFalse(drv.last("round.completed")["converged"])

    def test_one_seat_changes_its_mind_is_consensus(self):
        d, drv = self.start()
        drv.r0(["B", "C"])
        drv.r1()
        drv.ballots("seat.r2", ["o2", "o2"])
        dec = d.decision()
        self.assertEqual((dec.outcome, dec.option_id, dec.agreement), ("consensus", "o2", 1.0))
        self.assertEqual(dec.minority_report, [])

    def test_a_one_one_split_is_never_consensus_or_majority(self):
        # seat 0 has the higher q: its weighted share is over 50%, and that must not decide it
        d, drv = self.start()
        drv.r0(["B", "C"])
        drv.r1()
        drv.ballots("seat.r2", ["o1", "o2"])
        drv.ballots("seat.r3", ["o1", "o2"])
        self.assertEqual(d.phase, "chair")
        failed = drv.last("consensus.failed")
        self.assertEqual(failed["next_step"], "chair")
        self.assertEqual(failed["agreement"], 0.5)
        (chair,) = drv.calls("chair", 1)
        self.assertEqual(chair.model_id, "m0")  # no named chair: the seat with the highest q
        self.assertEqual(chair.json_schema["properties"]["option_id"]["enum"], ["o1", "o2"])
        drv.feed(chair, {"option_id": "o2", "final_text": "C it is.", "confidence": 0.7})
        dec = d.decision()
        self.assertEqual((dec.outcome, dec.option_id, dec.agreement), ("chair", "o2", 0.5))
        (minority,) = dec.minority_report
        self.assertEqual((minority.seats, minority.option_id), ([0], "o1"))

    def test_deadline_with_a_one_one_split_goes_to_the_chair(self):
        d, drv = self.start()
        drv.r0(["B", "C"])
        drv.take(d.on_deadline(120.0))
        self.assertEqual(d.phase, "chair")
        self.assertEqual(drv.last("consensus.failed")["next_step"], "chair")

    def test_four_seats_two_two_split_keeps_the_weighted_majority(self):
        d = make(lineup=lineup_k(4))
        drv = Driver(self, d)
        drv.r0(["B", "B", "C", "C"])
        drv.take(d.on_deadline())
        self.assertEqual(d.decision().outcome, "majority")  # only k = 2 is special

    def test_named_external_chair_is_used(self):
        seats = lineup_k(2)
        seats.chair_model_id = "judge"
        d = make(lineup=seats)
        drv = Driver(self, d)
        drv.r0(["B", "C"])
        drv.take(d.on_deadline(120.0))
        (chair,) = drv.calls("chair", 1)
        self.assertEqual(chair.model_id, "judge")

    def test_one_failed_draft_is_under_quorum_and_goes_to_the_chair(self):
        d, drv = self.start()
        drv.r0(["B", None])
        self.assertEqual(d.phase, "chair")
        self.assertIn("quorum is 2", drv.last("consensus.failed")["reason"])
        (chair,) = drv.calls("chair", 1)
        drv.feed(chair, {"option_id": "o1", "final_text": "B.", "confidence": 0.6})
        self.assertEqual(d.decision().outcome, "chair")
        self.assertEqual(d.decision().tally, {"o1": 1})

    def test_no_draft_at_all_is_a_deadlock(self):
        d, drv = self.start()
        drv.r0([None, None])
        self.assertEqual(d.decision().outcome, "deadlock")

    def test_adopting_the_other_draft_in_r1(self):
        d, drv = self.start(mode=MODE_DEFAULTS["standard"].model_copy(update={"rounds": ["r0", "r1"]}))
        drv.r0(["B", "C"])
        s0, s1 = drv.calls("seat.r1", 2)
        drv.feed(s0, {"reviews": [], "position": "keep"})
        drv.feed(s1, {"reviews": [], "position": "adopt:A", "changed_because": ["A.c1"]})
        dec = d.decision()
        self.assertEqual((dec.outcome, dec.option_id, dec.agreement), ("consensus", "o1", 1.0))

    def test_plan_mode_ratify_needs_both(self):
        d, drv = self.start(plan_mode=True)
        drv.r0(["B", "C"])
        drv.take(d.on_deadline(300.0))
        (chair,) = drv.calls("chair", 1)
        drv.feed(chair, {"option_id": "o1", "final_text": "Plan B.", "confidence": 0.9})
        self.assertEqual(d.phase, "ratify")
        r0, r1 = drv.calls("ratify", 2)
        drv.feed(r0, {"approve": True, "reason": "ok"})
        drv.feed(r1, {"approve": False, "reason": "misses C"})
        self.assertFalse(drv.last("ratify.result")["ratified"])  # 1 of 2 is under 60%
        self.assertEqual(d.phase, "chair")

    def test_two_seat_cruxes_are_voted_by_both(self):
        d, drv = self.start()
        drv.r0(["B", "C"])
        specs = drv.calls("seat.r1", 2)
        for spec in specs:
            drv.feed(spec, {
                "reviews": [{"target": "A", "flaws": [
                    {"id": "f1", "text": "the premise is false", "claim_ref": "A.c1", "severity": "major"}
                ]}],
                "position": "keep",
            })
        self.assertTrue(d.cruxes())
        crux = d.cruxes()[0].id
        for spec, stance in zip(drv.calls("seat.r2", 2), ["agree", "agree"]):
            drv.feed(spec, ballot("o1", crux_votes=[{"crux_id": crux, "stance": stance}]))
        self.assertEqual(d.decision().outcome, "consensus")
        self.assertEqual(d.decision().open_cruxes, [])


if __name__ == "__main__":
    unittest.main()
