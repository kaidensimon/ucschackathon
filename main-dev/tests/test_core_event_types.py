import json
import unittest

from pydantic import BaseModel

from council.core import event_types as et
from council.core import schemas as s

# Added 2026-10-10 (27.8, 28.5, bench), appended after the 16.3 table.
NEW_TYPES = (
    "tribunal.started tribunal.question tribunal.answer tribunal.verdict tribunal.outcome "
    "correction.recorded "
    "probe.scores probe.trained "
    "bench.started bench.progress bench.completed "
    "effort.planned round.extended review.debate review.final_say "
    "lie.report steer.applied steer.trained memory.planned"
).split()

# Added 2026-10-11: the open council protocol (chamber/open_debate.py), appended last.
OPEN_TYPES = "msg.started msg.delta msg.thinking msg.ended msg.card msg.lie table.tally".split()

# 16.3, in table order.
SPEC_TYPES = (
    "run.created run.state_changed run.completed run.failed run.cancelled "
    "brief.ready recall.ready profile.ready "
    "router.candidates_scored router.lineup_selected "
    "model.loading model.loaded model.unloaded model.evicted model.failed "
    "seat.assigned round.started turn.started turn.delta turn.reasoning_delta turn.completed "
    "turn.invalid turn.timeout options.clustered cruxes.extracted evidence.requested "
    "evidence.result ballot.cast round.completed "
    "consensus.reached consensus.failed chair.started chair.delta ratify.result decision.final "
    "user.input_requested user.input_received "
    "plan.drafted plan.linted plan.reviewed plan.ready "
    "delegation.started task.queued task.started task.delta task.attempt_completed check.started "
    "check.result task.passed task.failed task.blocked task.skipped task.escalated "
    "integration.result "
    "review.started review.ballot review.verdict "
    "memory.candidate memory.verdict memory.committed memory.contested memory.retracted "
    "telemetry.tick"
).split() + NEW_TYPES + OPEN_TYPES


def minimal(type_):
    """Only the required fields of the payload class, with dummy ids."""
    cls = et.PAYLOADS[type_]
    return {name: "x" for name, f in cls.model_fields.items() if f.is_required()}


class EventTypesTest(unittest.TestCase):
    def test_types_match_spec_in_order(self):
        self.assertEqual(list(et.EVENT_TYPES), SPEC_TYPES)
        self.assertEqual(len(set(et.EVENT_TYPES)), len(et.EVENT_TYPES))

    def test_constant_per_type(self):
        for t in et.EVENT_TYPES:
            self.assertEqual(getattr(et, et.constant_name(t)), t)
        self.assertEqual(et.RUN_CREATED, "run.created")
        self.assertEqual(et.TURN_REASONING_DELTA, "turn.reasoning_delta")

    def test_payload_class_per_type(self):
        self.assertEqual(set(et.PAYLOADS), set(et.EVENT_TYPES))
        for t in et.EVENT_TYPES:
            cls = et.PAYLOADS[t]
            self.assertTrue(issubclass(cls, BaseModel), t)
            self.assertEqual(cls.__name__, et.payload_class_name(t))
            self.assertEqual(cls.model_config.get("extra"), "ignore", t)
        self.assertIs(et.PAYLOADS["run.state_changed"], et.RunStateChangedPayload)

    def test_only_ids_are_required(self):
        for t in et.EVENT_TYPES:
            for name in minimal(t):
                self.assertTrue(name.endswith("_id"), f"{t}.{name} has no default")

    def test_minimal_payload_validates_and_is_json_ready(self):
        for t in et.EVENT_TYPES:
            m = minimal(t)
            self.assertIsInstance(et.validate_payload(t, m), et.PAYLOADS[t])
            out = et.make_payload(t, **m)
            self.assertIsInstance(out, dict)
            self.assertEqual(json.loads(json.dumps(out)), out, t)
            # round trip
            et.validate_payload(t, out)

    def test_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            et.validate_payload("nope.nothing", {})
        with self.assertRaises(ValueError):
            et.make_payload("nope.nothing")

    def test_invalid_payload_raises(self):
        with self.assertRaises(ValueError):
            et.validate_payload("turn.started", {})  # call_id missing
        with self.assertRaises(ValueError):
            et.validate_payload("task.started", {"task_id": "t1", "attempt": "many"})
        with self.assertRaises(ValueError):
            et.validate_payload("run.state_changed", {"to_state": "NOT_A_STATE"})
        with self.assertRaises(ValueError):
            et.validate_payload("run.created", "not a dict")

    def test_unknown_keys_ignored(self):
        out = et.make_payload("turn.delta", call_id="c1", seat_no=2, text="hi", junk=1)
        self.assertEqual(out, {"call_id": "c1", "seat_no": 2, "text": "hi"})

    def test_terminal_and_ephemeral(self):
        self.assertEqual(
            set(et.TERMINAL_EVENTS), {"run.completed", "run.failed", "run.cancelled"}
        )
        self.assertEqual(
            set(et.EPHEMERAL_EVENTS),
            {"turn.delta", "turn.reasoning_delta", "chair.delta", "task.delta", "msg.delta"},
        )
        for t in et.EVENT_TYPES:
            if t.endswith(".delta"):
                self.assertIn(t, et.EPHEMERAL_EVENTS)

    def test_rich_payloads_carry_schema_types(self):
        lineup = s.LineupRecord(seats=[s.SeatAssignment(seat_no=0, model_id="m1")], k=1)
        out = et.make_payload(
            "router.lineup_selected",
            lineup=lineup,
            models=[{"model_id": "m1", "display": "M One", "lab": "LabA", "footprint_gib": 9.5}],
        )
        self.assertEqual(out["lineup"]["seats"][0]["model_id"], "m1")
        self.assertEqual(out["models"][0]["lab"], "LabA")
        self.assertEqual(out["models"][0]["footprint_gib"], 9.5)

        out = et.make_payload(
            "run.state_changed", from_state=s.RunState.INTAKE, to_state="PROFILING"
        )
        self.assertEqual((out["from_state"], out["to_state"]), ("INTAKE", "PROFILING"))

        out = et.make_payload(
            "turn.completed", call_id="c1", seat_no=1, round=2, purpose="seat.r2",
            tokens=40, tps=31.5, ms=1200, parsed={"choice": "o1"},
        )
        self.assertEqual(out["parsed"], {"choice": "o1"})
        self.assertEqual(out["tps"], 31.5)

        out = et.make_payload("ballot.cast", seat_no=3, round=2, ballot=s.Ballot(choice="o1"))
        self.assertEqual(out["ballot"]["choice"], "o1")

        out = et.make_payload("decision.final", decision=s.Decision(outcome="consensus"))
        self.assertEqual(out["decision"]["outcome"], "consensus")

        out = et.make_payload("plan.ready", plan=s.Plan(goal="g", tasks=[s.MicroTask(id="t1")]))
        self.assertEqual(out["plan"]["tasks"][0]["id"], "t1")

        out = et.make_payload("task.passed", task_id="t1", attempt=2, model_id="w1")
        self.assertEqual((out["status"], out["attempt"]), ("passed", 2))

        out = et.make_payload("check.result", result=s.CheckResult(ok=True, task_id="t1"))
        self.assertTrue(out["result"]["ok"])

        out = et.make_payload(
            "review.verdict", verdict="fix", tally={"fix": 3, "accept": 2},
            fixes=[s.ReviewFix(problem="p")],
        )
        self.assertEqual(out["verdict"], "fix")
        self.assertEqual(out["fixes"][0]["problem"], "p")

        out = et.make_payload("memory.committed", entry=s.ChronicleEntry(id="e1"))
        self.assertEqual(out["entry"]["id"], "e1")

        snap = s.TelemetrySnapshot(mem_total_gib=128.0, tps_total=900.0)
        out = et.make_payload("telemetry.tick", **snap.model_dump())
        self.assertEqual(out["mem_total_gib"], 128.0)
        self.assertEqual(s.TelemetrySnapshot.model_validate(out), snap)

        out = et.make_payload("user.input_requested", question="A or B?", options=["A", "B"])
        self.assertEqual(out["options"], ["A", "B"])

        out = et.make_payload("options.clustered", options=[s.Option(id="o1", holders=[0, 1])])
        self.assertEqual(out["options"][0]["holders"], [0, 1])

    def test_original_types_keep_their_order(self):
        self.assertEqual(list(et.EVENT_TYPES[:63]), SPEC_TYPES[:63])
        self.assertEqual(et.EVENT_TYPES[62], "telemetry.tick")
        self.assertEqual(list(et.EVENT_TYPES[63:]), NEW_TYPES + OPEN_TYPES)

    def test_new_constants_and_classes(self):
        self.assertEqual(et.TRIBUNAL_STARTED, "tribunal.started")
        self.assertEqual(et.TRIBUNAL_QUESTION, "tribunal.question")
        self.assertEqual(et.TRIBUNAL_ANSWER, "tribunal.answer")
        self.assertEqual(et.TRIBUNAL_VERDICT, "tribunal.verdict")
        self.assertEqual(et.TRIBUNAL_OUTCOME, "tribunal.outcome")
        self.assertEqual(et.CORRECTION_RECORDED, "correction.recorded")
        self.assertEqual(et.PROBE_SCORES, "probe.scores")
        self.assertEqual(et.PROBE_TRAINED, "probe.trained")
        self.assertEqual(et.BENCH_STARTED, "bench.started")
        self.assertEqual(et.BENCH_PROGRESS, "bench.progress")
        self.assertEqual(et.BENCH_COMPLETED, "bench.completed")
        self.assertIs(et.PAYLOADS["tribunal.outcome"], et.TribunalOutcomePayload)
        self.assertIs(et.PAYLOADS["correction.recorded"], et.CorrectionRecordedPayload)
        self.assertIs(et.PAYLOADS["probe.scores"], et.ProbeScoresPayload)
        self.assertIs(et.PAYLOADS["bench.progress"], et.BenchProgressPayload)
        for t in NEW_TYPES:
            self.assertIn(et.constant_name(t), et.__all__)
            self.assertIn(et.payload_class_name(t), et.__all__)
            self.assertNotIn(t, et.EPHEMERAL_EVENTS)
            self.assertNotIn(t, et.TERMINAL_EVENTS)
            self.assertEqual(minimal(t), {}, t)  # every field has a default

    def test_tribunal_payloads(self):
        out = et.make_payload("tribunal.started", outlier_seat=3, outlier_model_id="m3",
                              distance=1.2, examiners=[0, 1], judges=[0, 1, 2, 4], questions=2)
        self.assertEqual((out["outlier_seat"], out["examiners"], out["questions"]),
                         (3, [0, 1], 2))

        out = et.make_payload(
            "tribunal.question", seat_no=0, model_id="m0", index=1,
            question=s.TribunalQuestion(question="why?", targets_claim="c2"),
        )
        self.assertEqual((out["seat_no"], out["model_id"], out["index"]), (0, "m0", 1))
        self.assertEqual(out["question"]["targets_claim"], "c2")

        out = et.make_payload("tribunal.answer", seat_no=3, model_id="m3",
                              answer=s.TribunalAnswer(answer="ok", concedes=True))
        self.assertTrue(out["answer"]["concedes"])
        self.assertEqual(out["seat_no"], 3)

        out = et.make_payload(
            "tribunal.verdict", seat_no=1, model_id="m1",
            verdict={"held": False, "score": 0.1, "error_kind": "logic", "lesson": "l"},
        )
        self.assertEqual(out["verdict"]["error_kind"], "logic")
        self.assertEqual(out["model_id"], "m1")

        outcome = s.TribunalOutcome(outlier_seat=3, outlier_model_id="m3", outcome="conceded",
                                    held_share=0.0, error_kind="factual", correction_id="k1")
        out = et.make_payload("tribunal.outcome", outcome=outcome, seat_no=3, model_id="m3",
                              correction_eligible=True)
        self.assertEqual(out["outcome"]["outcome"], "conceded")
        self.assertEqual(out["outcome"]["correction_id"], "k1")
        self.assertTrue(out["correction_eligible"])
        self.assertEqual(s.TribunalOutcome.model_validate(out["outcome"]), outcome)

        with self.assertRaises(ValueError):
            et.validate_payload("tribunal.outcome", {"outcome": {"outcome": "acquitted"}})
        with self.assertRaises(ValueError):
            et.validate_payload("tribunal.verdict", {"verdict": {"score": 0.5}})  # held missing

    def test_correction_payload(self):
        corr = s.Correction(id="k1", project="p", model_id="m3", lesson="l",
                            examples=[s.TrainingExample(target="a")])
        out = et.make_payload("correction.recorded", correction=corr, seat_no=3, model_id="m3",
                              project="p", dataset_size=9)
        self.assertEqual(out["correction"]["id"], "k1")
        self.assertEqual(out["correction"]["examples"][0]["target"], "a")
        self.assertEqual((out["seat_no"], out["dataset_size"]), (3, 9))

    def test_probe_payloads(self):
        out = et.make_payload(
            "probe.scores", seat_no=2, model_id="m2", round=0,
            scores=[s.ClaimScore(claim_ref="c1", reliability=0.8, seat_no=2),
                    {"claim_ref": "c2", "reliability": 0.3, "probe": 0.2, "probe_auroc": 0.85}],
        )
        self.assertEqual((out["seat_no"], out["model_id"], out["round"]), (2, "m2", 0))
        self.assertEqual([c["claim_ref"] for c in out["scores"]], ["c1", "c2"])
        self.assertIsNone(out["scores"][0]["probe"])
        self.assertEqual(out["scores"][1]["probe_auroc"], 0.85)

        probe = s.Probe(model_id="m2", layer=12, weights=[0.5, -0.5], auroc=0.9,
                        status="validated")
        out = et.make_payload("probe.trained", probe=probe, model_id="m2", validated=True,
                              layers_tried=[8, 12], auroc_by_layer={"8": 0.7, "12": 0.9},
                              top_dims=[0, 1])
        self.assertEqual((out["probe"]["layer"], out["probe"]["status"]), (12, "validated"))
        self.assertEqual(out["auroc_by_layer"]["12"], 0.9)
        self.assertEqual(s.Probe.model_validate(out["probe"]), probe)

    def test_v15_payloads(self):
        from council.core import schemas_v15 as v
        self.assertEqual((et.LIE_REPORT, et.STEER_APPLIED, et.STEER_TRAINED, et.MEMORY_PLANNED),
                         ("lie.report", "steer.applied", "steer.trained", "memory.planned"))
        self.assertEqual(list(et.EVENT_TYPES[-11:-7]),
                         ["lie.report", "steer.applied", "steer.trained", "memory.planned"])
        rep = v.LieReport(run_id="r1", flags=[v.LieFlag(claim_id="c1", level="flag")])
        out = et.make_payload("lie.report", report=rep.model_dump(), flagged=1, watched=2)
        self.assertEqual((out["flagged"], out["watched"]), (1, 2))
        self.assertEqual(v.LieReport.model_validate(out["report"]), rep)
        self.assertEqual(et.make_payload("lie.report"), {"report": {}, "flagged": 0, "watched": 0})

        out = et.make_payload("steer.applied", project="p", model_id="m1", scale=1.5,
                              layers=[14, 15], source="p/m1.gguf", junk=1)
        self.assertEqual(out, {"project": "p", "model_id": "m1", "scale": 1.5,
                               "layers": [14, 15], "source": "p/m1.gguf"})

        out = et.make_payload("steer.trained", project="p", model_id="m1", examples=8,
                              active=False, reason="no scale passed")
        self.assertEqual(out, {"project": "p", "model_id": "m1", "examples": 8, "scale": None,
                               "active": False, "reason": "no scale passed"})
        self.assertEqual(et.make_payload("steer.trained", scale=1.0, active=True)["scale"], 1.0)

        plan = v.MemoryPlan(fits=False, budget_gib=100.0, dropped=["m9"])
        out = et.make_payload("memory.planned", plan=plan.model_dump())
        self.assertEqual(v.MemoryPlan.model_validate(out["plan"]), plan)
        with self.assertRaises(ValueError):
            et.validate_payload("steer.applied", {"layers": "all"})
        with self.assertRaises(ValueError):
            et.validate_payload("memory.planned", {"plan": [1]})

    def test_steer_card(self):
        from council.core import schemas_v15 as v
        self.assertIn("SteerCard", v.__all__)
        c = v.SteerCard(project="p", model_id="m1")
        self.assertEqual(c.model_dump(),
                         {"project": "p", "model_id": "m1", "version": 1, "layers": [],
                          "scale": None, "examples": 0, "fraction": 0.0, "active": False,
                          "reason": "", "trained_at": 0.0, "path": ""})
        c.layers.append(3)
        self.assertEqual(v.SteerCard(project="p", model_id="m1").layers, [])
        with self.assertRaises(Exception):
            v.SteerCard(project="p")

    def test_bench_payloads(self):
        req = s.BenchRunRequest(tasks_path="b.jsonl", modes=["council"], limit=5)
        out = et.make_payload("bench.started", request=req, bench_id="b1", modes=req.modes,
                              tasks=5, total=5)
        self.assertEqual(out["request"]["tasks_path"], "b.jsonl")
        self.assertEqual((out["modes"], out["total"]), (["council"], 5))

        out = et.make_payload("bench.progress", bench_id="b1", mode="solo:m1", model_id="m1",
                              done=2, total=5, correct=1,
                              result=s.BenchResult(id="t1", mode="solo:m1", correct=True))
        self.assertEqual((out["done"], out["total"], out["model_id"]), (2, 5, "m1"))
        self.assertTrue(out["result"]["correct"])

        out = et.make_payload(
            "bench.completed", bench_id="b1",
            summary=[s.BenchSummaryRow(mode="council", n=5, accuracy=0.8,
                                       by_difficulty={"hard": 0.5})],
            results_path="out.jsonl", ms=12.5,
        )
        self.assertEqual(out["summary"][0]["accuracy"], 0.8)
        self.assertEqual(out["summary"][0]["by_difficulty"], {"hard": 0.5})
        self.assertEqual(out["results_path"], "out.jsonl")


if __name__ == "__main__":
    unittest.main()
