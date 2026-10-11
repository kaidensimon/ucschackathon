"""Tests for council/core/schemas.py: every model constructs from minimal args and round-trips."""

import typing
import unittest
from enum import Enum

from pydantic import BaseModel, ValidationError

from council.core import schemas as S

# Minimal constructor args for every model. Empty dict = no required fields.
MINIMAL = {
    "ModelSource": {},
    "ServeProfile": {},
    "ServeConfig": {},
    "ReasoningControl": {},
    "MeasuredStats": {},
    "ModelEntry": {"id": "m1"},
    "CallSpec": {"model_id": "m1"},
    "CallResult": {"call_id": "c1", "ok": True},
    "TaskProfile": {},
    "SeatAssignment": {"seat_no": 0, "model_id": "m1"},
    "LineupScore": {},
    "RejectedLineup": {},
    "LineupRecord": {},
    "Claim": {"id": "c1", "text": "t"},
    "Draft": {"answer": "a"},
    "Flaw": {"id": "f1", "text": "t"},
    "Review": {"target": "A"},
    "CheckRequest": {"kind": "python"},
    "Critique": {},
    "CruxVote": {"crux_id": "x1"},
    "Ballot": {"choice": "o1"},
    "Option": {"id": "o1"},
    "Crux": {"id": "x1"},
    "EvidenceResult": {"kind": "grep"},
    "MinorityPosition": {},
    "Departure": {"chronicle_entry_id": "e1"},
    "UserQuestion": {"question": "q?"},
    "Decision": {"outcome": "consensus"},
    "ModeConfig": {"name": "standard"},
    "EffortPlan": {},
    "InterfaceDef": {"name": "f"},
    "Deliverable": {"id": "d1"},
    "Check": {"type": "exists"},
    "ContextFile": {"path": "a.py"},
    "TaskContext": {},
    "TaskBudget": {},
    "MicroTask": {"id": "t1"},
    "Plan": {},
    "WorkerOp": {"op": "write_file", "path": "a.py"},
    "WorkerOutput": {},
    "CheckResult": {"ok": True},
    "AttemptRecord": {"task_id": "t1"},
    "WorkSummary": {},
    "DiffStats": {},
    "WorkReportTask": {"id": "t1"},
    "WorkReport": {},
    "ReviewFix": {"problem": "p"},
    "ReviewBallot": {"verdict": "accept"},
    "EvidenceRef": {"run_id": "r1"},
    "MemoryVerdict": {"durable": True},
    "MemoryCandidate": {"text": "user likes tabs"},
    "ChronicleEntry": {"id": "e1"},
    "Event": {"type": "run.created"},
    "RunRequest": {"task": "do it"},
    "RunCounters": {},
    "RunSnapshot": {"run_id": "r1"},
    "UserInput": {"request_id": "q1"},
    "BenchTask": {"id": "b1", "prompt": "2+2?"},
    "BenchResult": {"id": "b1", "mode": "council"},
    "ResidentModel": {"model_id": "m1"},
    "TelemetrySnapshot": {},
    # added 2026-10-10 (27, 28, bench, router stats)
    "TribunalQuestion": {"question": "why?"},
    "TribunalAnswer": {"answer": "because"},
    "DefenseVerdict": {"held": False},
    "TribunalOutcome": {},
    "TrainingExample": {},
    "Correction": {},
    "ClaimRecord": {},
    "BehaviourSignals": {},
    "ClaimScore": {},
    "Probe": {},
    "BehaviourStats": {"model_id": "m1"},
    "CalibrationCell": {"task_id": "b1", "model_id": "m1"},
    "BenchRunRequest": {},
    "BenchSummaryRow": {"mode": "council"},
}

NEW_NAMES = [
    "TribunalQuestion", "TribunalAnswer", "DefenseVerdict", "TribunalOutcome", "TrainingExample",
    "Correction", "ClaimRecord", "BehaviourSignals", "ClaimScore", "Probe",
    "BehaviourStats", "CalibrationCell", "BenchRunRequest", "BenchSummaryRow",
]

REQUIRED_NAMES = [
    "ModelEntry", "ServeProfile", "ReasoningControl", "MeasuredStats", "ModelSource", "CallSpec",
    "CallResult", "TaskProfile", "SeatAssignment", "LineupScore", "LineupRecord", "Claim", "Draft",
    "Flaw", "Review", "CheckRequest", "Critique", "CruxVote", "Ballot", "Option", "Crux",
    "EvidenceResult", "MinorityPosition", "Departure", "UserQuestion", "Decision", "ModeConfig",
    "InterfaceDef", "Deliverable", "Check", "MicroTask", "Plan", "WorkerOp", "WorkerOutput",
    "CheckResult", "TaskStatus", "AttemptRecord", "WorkReportTask", "WorkReport", "ReviewFix",
    "ReviewBallot", "EvidenceRef", "ChronicleEntry", "MemoryCandidate", "MemoryVerdict", "Event",
    "RunState", "RunRequest", "RunCounters", "RunSnapshot", "UserInput", "BenchTask", "BenchResult",
    "TelemetrySnapshot",
]

ALIASES = [
    "Purpose", "ReasoningLevel", "Priority", "CallError", "Category", "Difficulty", "Deliverable_",
    "Outcome", "Severity", "FlawKind", "CruxKind", "EntryKind", "EntryStatus", "LensName", "Mode",
    "MemoryAction",
]


def all_models():
    out = {}
    for name in dir(S):
        obj = getattr(S, name)
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__ == S.__name__:
            if not name.startswith("_"):
                out[name] = obj
    return out


class TestInventory(unittest.TestCase):
    def test_required_names_exist(self):
        for name in REQUIRED_NAMES + ALIASES + ["CATEGORIES", "PURPOSES"]:
            self.assertTrue(hasattr(S, name), name)

    def test_new_names_exist_and_are_exported(self):
        for name in NEW_NAMES + ["ErrorKind", "TribunalOutcomeKind", "VerifiedBy",
                                 "ClaimLabel", "LabelledBy", "ProbeStatus"]:
            self.assertTrue(hasattr(S, name), name)
            self.assertIn(name, S.__all__)

    def test_all_exports_resolve(self):
        for name in S.__all__:
            self.assertTrue(hasattr(S, name), name)

    def test_every_model_has_minimal_args(self):
        self.assertEqual(sorted(all_models()), sorted(MINIMAL))

    def test_every_model_ignores_extra(self):
        for name, cls in all_models().items():
            self.assertEqual(cls.model_config.get("extra"), "ignore", name)

    def test_docstring_lists_every_class(self):
        for name in list(all_models()) + ["TaskStatus", "RunState"]:
            self.assertIn(name, S.__doc__, name)


class TestRoundTrip(unittest.TestCase):
    def test_minimal_construct_and_round_trip(self):
        for name, cls in all_models().items():
            with self.subTest(model=name):
                obj = cls(**MINIMAL[name])
                back = cls.model_validate_json(obj.model_dump_json())
                self.assertEqual(obj, back)
                self.assertEqual(obj.model_dump(mode="json"), back.model_dump(mode="json"))

    def test_extra_keys_are_ignored(self):
        for name, cls in all_models().items():
            with self.subTest(model=name):
                obj = cls(**MINIMAL[name], zz_unknown_key=1)
                self.assertNotIn("zz_unknown_key", obj.model_dump())

    def test_list_defaults_are_not_shared(self):
        a, b = S.Draft(answer="a"), S.Draft(answer="b")
        a.claims.append(S.Claim(id="c1", text="t"))
        self.assertEqual(b.claims, [])
        p, q = S.Plan(), S.Plan()
        p.tasks.append(S.MicroTask(id="t1"))
        self.assertEqual(q.tasks, [])

    def test_json_schema_for_every_model(self):
        for name, cls in all_models().items():
            with self.subTest(model=name):
                self.assertEqual(cls.model_json_schema()["type"], "object")

    def test_draft_and_ballot_json_schema(self):
        d = S.Draft.model_json_schema()
        for key in ("answer", "answer_key", "summary", "claims", "assumptions", "risks",
                    "confidence", "would_change_mind", "user_questions"):
            self.assertIn(key, d["properties"])
        self.assertIn("answer", d["required"])
        b = S.Ballot.model_json_schema()
        for key in ("choice", "ranking", "final_answer", "answer_key", "confidence", "crux_votes",
                    "blocking_objection", "changed_because", "lesson"):
            self.assertIn(key, b["properties"])
        self.assertIn("choice", b["required"])


class TestAliasesAndEnums(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(len(S.CATEGORIES), 8)
        self.assertEqual(tuple(typing.get_args(S.Category)), S.CATEGORIES)
        self.assertEqual(tuple(typing.get_args(S.LensName)), S.LENSES)
        self.assertEqual(tuple(typing.get_args(S.Difficulty)), S.DIFFICULTIES)

    def test_open_aliases_are_str(self):
        self.assertIs(S.Purpose, str)
        self.assertIs(S.MemoryAction, str)
        self.assertIn("seat.r0", S.PURPOSES)
        self.assertIn("worker", S.PURPOSES)
        S.CallSpec(model_id="m", purpose="clerk.anything_new")
        S.MemoryVerdict(durable=True, action="merge:e7")

    def test_literal_values(self):
        self.assertEqual(typing.get_args(S.ReasoningLevel), ("off", "council", "max"))
        self.assertEqual(typing.get_args(S.Priority), ("interactive", "batch"))
        self.assertEqual(typing.get_args(S.CallError),
                         ("timeout", "invalid_output", "server_error", "cancelled"))
        self.assertEqual(typing.get_args(S.Deliverable_), ("answer", "plan", "build"))
        self.assertEqual(typing.get_args(S.Outcome),
                         ("consensus", "majority", "chair", "user", "deadlock"))
        self.assertEqual(typing.get_args(S.Severity), ("minor", "major", "fatal"))
        self.assertEqual(typing.get_args(S.CruxKind), ("factual", "checkable", "value"))
        self.assertEqual(typing.get_args(S.Mode), ("quick", "standard", "deep"))

    def test_literals_reject_unknown(self):
        with self.assertRaises(ValidationError):
            S.Decision(outcome="maybe")
        with self.assertRaises(ValidationError):
            S.CallSpec(model_id="m", reasoning="huge")
        with self.assertRaises(ValidationError):
            S.Draft(answer="a", confidence=1.5)
        with self.assertRaises(ValidationError):
            S.Check(type="vibes")

    def test_task_status(self):
        self.assertTrue(issubclass(S.TaskStatus, str) and issubclass(S.TaskStatus, Enum))
        self.assertEqual([s.value for s in S.TaskStatus],
                         ["queued", "running", "passed", "failed", "blocked", "skipped"])
        self.assertIs(S.TaskStatus.PASSED, S.TaskStatus.passed)
        self.assertEqual(S.TaskStatus.passed, "passed")
        snap = S.RunSnapshot(run_id="r", task_statuses={"t1": "passed"})
        self.assertIs(snap.task_statuses["t1"], S.TaskStatus.passed)

    def test_run_state(self):
        names = {s.value for s in S.RunState}
        self.assertEqual(names, {
            "INTAKE", "PROFILING", "CONVENING", "DELIBERATING", "DECIDED", "PLANNING",
            "AWAITING_DELEGATION", "EXECUTING", "REVIEWING", "INTEGRATING", "REFLECTING", "DONE",
            "AWAITING_USER", "CANCELLED", "FAILED", "EXAMINING",
        })
        self.assertEqual(S.RunState.EXAMINING, "EXAMINING")
        order = [s.value for s in S.RunState]
        self.assertEqual(order.index("EXAMINING"), order.index("DECIDED") + 1)
        self.assertIs(S.RunSnapshot(run_id="r", state="EXAMINING").state, S.RunState.EXAMINING)
        self.assertEqual(S.RunState.DONE, "DONE")
        self.assertIn('"state":"INTAKE"', S.RunSnapshot(run_id="r").model_dump_json())


class TestShapes(unittest.TestCase):
    def test_call_spec(self):
        a, b = S.CallSpec(model_id="m"), S.CallSpec(model_id="m")
        self.assertTrue(a.call_id and a.call_id != b.call_id)
        spec = S.CallSpec(model_id="m", messages=[{"role": "user", "content": "hi"}],
                          json_schema=S.Draft.model_json_schema())
        self.assertEqual(spec.messages[0]["role"], "user")
        self.assertIn("json_schema", S.CallSpec.model_fields)
        self.assertNotIn("schema", S.CallSpec.model_fields)

    def test_registry_example_loads(self):
        entry = S.ModelEntry.model_validate({
            "id": "qwen38-27b-q4", "display": "Qwen3.8 27B", "lab": "alibaba", "lineage": "qwen3",
            "arch": "dense", "params_b": 27, "active_params_b": 27, "quant": "Q4_K_M",
            "source": {"repo": "o/r", "file": "x.gguf", "sha256": "h", "license": "l"},
            "roles": ["seat", "chair"], "modalities": ["text", "image"],
            "serve": {"live": {"ctx": 32768, "parallel": 2},
                      "batch": {"ctx": 8192, "parallel": 16}, "extra_args": []},
            "reasoning": {"kind": "toggle", "off": {}, "council": {}, "max": {}},
            "structured": "grammar", "sampling": {"temperature": 0.6, "top_p": 0.95},
            "priors": {c: 0.6 for c in S.CATEGORIES},
            "measured": {"ram_gb_live": None, "tps_1": None, "probe_date": None},
            "status": "active",
        })
        self.assertEqual(entry.serve.batch.parallel, 16)
        self.assertEqual(entry.reasoning.kind, "toggle")
        self.assertIsNone(entry.measured.tps_8)

    def test_lineup_record(self):
        rec = S.LineupRecord(
            seats=[{"seat_no": 0, "model_id": "a", "lens": "skeptic", "is_chair": True, "q": 0.7}],
            alternates=["b"], chair_model_id="a", tier="B", k=1, seed=7,
            chosen_score={"merit": 0.7, "total": 0.5},
            rejected=[{"models": ["b"], "score": {"total": 0.4}}],
        )
        self.assertEqual(rec.rejected[0].score.total, 0.4)
        self.assertEqual(rec.seats[0].lens, "skeptic")
        for f in ("merit", "vote", "cover", "div", "load", "repeat", "total"):
            self.assertIn(f, S.LineupScore.model_fields)

    def test_check_variants(self):
        S.Check(type="command", cmd="python -m unittest", expect_exit=0, timeout_s=30)
        S.Check(type="parses", path="a.py", language="python")
        S.Check(type="contains", path="a.py", pattern="def f")
        S.Check(type="schema", path="a.json", json_schema={"type": "object"})
        S.Check(type="review", rubric="clear")
        task = S.MicroTask(id="t1", acceptance=[{"type": "exists", "path": "a.py"}])
        self.assertEqual(task.budget.max_output_tokens, 1500)
        self.assertEqual(task.budget.max_attempts, 3)
        self.assertEqual(task.acceptance[0].path, "a.py")

    def test_decision_nested(self):
        d = S.Decision(
            outcome="user", tally={"o1": 3, "o2": 2},
            minority_report=[{"seats": [1, 4], "position": "p", "strongest_argument": "s"}],
            open_cruxes=[{"id": "x1", "statement": "s", "between": ["o1", "o2"], "kind": "value"}],
            departures=[{"chronicle_entry_id": "e1", "why": "w"}],
            needs_user={"question": "which?", "options": ["a", "b"]},
        )
        self.assertEqual(d.needs_user.options, ["a", "b"])
        self.assertEqual(d.open_cruxes[0].kind, "value")
        self.assertEqual(S.Decision.model_validate_json(d.model_dump_json()), d)

    def test_telemetry_fields(self):
        t = S.TelemetrySnapshot(resident=[{"model_id": "m", "footprint_gib": 18.5}],
                                tps_by_model={"m": 40.0}, in_flight={"m": 2})
        self.assertEqual(t.resident[0].footprint_gib, 18.5)
        for f in ("mem_total_gib", "mem_available_gib", "mem_used_gib", "swap_used_gib", "resident",
                  "tps_by_model", "tps_total", "in_flight", "queue_depth", "tokens_in", "tokens_out",
                  "tokens_reasoning", "gpu_util", "gpu_temp_c", "gpu_power_w", "cpu_util",
                  "cloud_equiv_usd"):
            self.assertIn(f, S.TelemetrySnapshot.model_fields)

    def test_mode_defaults(self):
        self.assertEqual(set(S.MODE_DEFAULTS), {"quick", "standard", "deep"})
        self.assertEqual(S.MODE_DEFAULTS["quick"].k, 3)
        self.assertEqual(S.MODE_DEFAULTS["standard"].k, 6)
        self.assertEqual(S.MODE_DEFAULTS["deep"].k, 6)
        self.assertEqual(S.MODE_DEFAULTS["quick"].k_options, [2, 3, 4, 5, 6])
        self.assertEqual(S.MODE_DEFAULTS["standard"].k_options, [2, 3, 4, 5, 6])
        self.assertEqual(S.MODE_DEFAULTS["deep"].k_options, [2, 3, 4, 5, 6, 7])
        for m in S.MODE_DEFAULTS.values():
            self.assertIn(m.k, m.k_options)

    def test_model_entry_speculative_fields(self):
        e = S.ModelEntry(id="m")
        self.assertEqual((e.ollama_options, e.speculative), ({}, "none"))
        e = S.ModelEntry(id="m", ollama_options={"draft_num_predict": 4}, speculative="mtp")
        self.assertEqual(e.ollama_options, {"draft_num_predict": 4})
        with self.assertRaises(Exception):
            S.ModelEntry(id="m", speculative="bogus")

    def test_mode_defaults_rest(self):
        self.assertEqual(S.MODE_DEFAULTS["standard"].deadline_s, 300.0)
        self.assertEqual(S.MODE_DEFAULTS["deep"].reasoning, "max")

    def test_event_and_run_request(self):
        e = S.Event(seq=5, ts=1.5, run_id="r", type="turn.completed", payload={"seat_no": 2})
        self.assertEqual(S.Event.model_validate(e.model_dump()).payload["seat_no"], 2)
        r = S.RunRequest(task="t")
        self.assertEqual((r.mode, r.deliverable, r.lineup_override, r.options),
                         ("standard", None, None, {}))


class TestTribunalAndReliability(unittest.TestCase):
    """Sections 27 and 28, plus the bench and router additions."""

    def test_new_literals(self):
        self.assertEqual(typing.get_args(S.ErrorKind),
                         ("factual", "logic", "misread_task", "ignored_evidence", "preference",
                          "none"))
        self.assertEqual(typing.get_args(S.TribunalOutcomeKind),
                         ("vindicated", "conceded", "failed", "skipped"))
        self.assertEqual(typing.get_args(S.VerifiedBy),
                         ("evidence", "ground_truth", "conceded", "agreement"))
        self.assertEqual(typing.get_args(S.ClaimLabel), ("true", "false", "unknown"))
        self.assertEqual(typing.get_args(S.LabelledBy),
                         ("evidence", "ground_truth", "tribunal", "user", "none"))
        self.assertEqual(typing.get_args(S.ProbeStatus),
                         ("untrained", "candidate", "validated", "rejected"))
        for p in ("tribunal.question", "tribunal.answer", "tribunal.verdict"):
            self.assertIn(p, S.PURPOSES)

    def test_new_literals_reject_unknown(self):
        with self.assertRaises(ValidationError):
            S.TribunalOutcome(outcome="acquitted")
        with self.assertRaises(ValidationError):
            S.DefenseVerdict(held=True, error_kind="vibes")
        with self.assertRaises(ValidationError):
            S.DefenseVerdict(held=True, score=1.2)
        with self.assertRaises(ValidationError):
            S.Correction(verified_by="rumour")
        with self.assertRaises(ValidationError):
            S.ClaimRecord(label="maybe")
        with self.assertRaises(ValidationError):
            S.ClaimRecord(labelled_by="nobody")
        with self.assertRaises(ValidationError):
            S.Probe(status="great")
        with self.assertRaises(ValidationError):
            S.BenchRunRequest(split="train")

    def test_llm_facing_tribunal_schemas(self):
        q = S.TribunalQuestion.model_json_schema()
        self.assertEqual(q["required"], ["question"])
        self.assertIn("targets_claim", q["properties"])
        a = S.TribunalAnswer.model_json_schema()
        self.assertEqual(a["required"], ["answer"])
        for key in ("answer", "concedes", "new_evidence"):
            self.assertIn(key, a["properties"])
        v = S.DefenseVerdict.model_json_schema()
        self.assertEqual(v["required"], ["held"])
        for key in ("held", "score", "decisive_point", "error_kind", "lesson"):
            self.assertIn(key, v["properties"])
        ans = S.TribunalAnswer(answer="x")
        self.assertEqual((ans.concedes, ans.new_evidence), (False, ""))
        ver = S.DefenseVerdict(held=True)
        self.assertEqual((ver.score, ver.error_kind, ver.lesson), (0.5, "none", ""))

    def test_tribunal_outcome(self):
        t = S.TribunalOutcome()
        self.assertEqual((t.outcome, t.outlier_seat, t.held_share, t.error_kind),
                         ("skipped", None, 0.0, "none"))
        self.assertEqual((t.questions, t.answers, t.verdicts, t.correction_id),
                         ([], [], [], None))
        t = S.TribunalOutcome(
            outlier_seat=3, outlier_model_id="m3", outcome="failed", held_share=0.25,
            error_kind="factual", lesson="Check the units.",
            questions=[{"question": "why 9.8?", "targets_claim": "c2", "seat_no": 0}],
            answers=[{"answer": "I assumed g.", "concedes": False, "seat_no": 3}],
            verdicts=[{"held": False, "score": 0.2, "error_kind": "factual", "seat_no": 0},
                      {"held": True, "score": 0.7, "seat_no": 1}],
            correction_id="k1",
        )
        self.assertEqual(t.questions[0].targets_claim, "c2")
        self.assertEqual(t.verdicts[1].seat_no, 1)
        self.assertEqual(S.TribunalOutcome.model_validate_json(t.model_dump_json()), t)
        for f in ("outlier_seat", "outlier_model_id", "outcome", "held_share", "error_kind",
                  "lesson", "questions", "answers", "verdicts", "correction_id"):
            self.assertIn(f, S.TribunalOutcome.model_fields)

    def test_correction_and_training_example(self):
        a, b = S.Correction(), S.Correction()
        self.assertTrue(a.id and a.id != b.id)
        self.assertIsNone(a.verified_by)
        c = S.Correction(
            id="k1", project="abc123", model_id="m3", lineage="qwen3", run_id="r1", created_at=5.0,
            task="t", wrong_position="w", council_position="c", error_kind="logic", lesson="l",
            verified_by="evidence",
            examples=[{"messages": [{"role": "user", "content": "q"}], "target": "a"}],
        )
        self.assertIsInstance(c.examples[0], S.TrainingExample)
        self.assertEqual(c.examples[0].messages[0]["role"], "user")
        self.assertEqual(c.examples[0].target, "a")
        self.assertEqual(S.Correction.model_validate(c.model_dump(mode="json")), c)
        for f in ("id", "project", "model_id", "lineage", "run_id", "created_at", "task",
                  "wrong_position", "council_position", "error_kind", "lesson", "verified_by",
                  "examples"):
            self.assertIn(f, S.Correction.model_fields)
        self.assertEqual(set(S.TrainingExample.model_fields), {"messages", "target"})

    def test_claim_record(self):
        r = S.ClaimRecord()
        self.assertEqual((r.label, r.labelled_by, r.confidence), ("unknown", "none", 0.5))
        self.assertTrue(r.id and r.id != S.ClaimRecord().id)
        r = S.ClaimRecord(run_id="r1", project="p", model_id="m", seat_no=2, claim_id="c1",
                          text="t", confidence=0.9, label="false", labelled_by="tribunal")
        self.assertEqual((r.label, r.seat_no), ("false", 2))
        self.assertEqual(set(S.ClaimRecord.model_fields),
                         {"id", "run_id", "project", "model_id", "seat_no", "claim_id", "text",
                          "confidence", "label", "labelled_by", "created_at"})

    def test_behaviour_signals_all_optional(self):
        sig = S.BehaviourSignals()
        self.assertEqual(set(S.BehaviourSignals.model_fields),
                         {"mean_logprob", "entropy", "self_agreement", "stated_confidence",
                          "track_record"})
        for name, f in S.BehaviourSignals.model_fields.items():
            self.assertFalse(f.is_required(), name)
            self.assertIsNone(getattr(sig, name), name)
        self.assertEqual(S.BehaviourSignals(mean_logprob=-0.4).mean_logprob, -0.4)

    def test_claim_score_and_probe(self):
        cs = S.ClaimScore()
        self.assertEqual((cs.claim_ref, cs.reliability, cs.probe, cs.probe_auroc, cs.seat_no),
                         ("", 0.5, None, None, None))
        cs = S.ClaimScore(claim_ref="c1", reliability=0.8, probe=0.3, probe_auroc=0.86, seat_no=1)
        self.assertEqual(S.ClaimScore.model_validate(cs.model_dump()), cs)
        p = S.Probe()
        self.assertEqual((p.status, p.weights, p.bias, p.n_train), ("untrained", [], 0.0, 0))
        p = S.Probe(model_id="m", layer=12, weights=[0.1, -0.2], bias=0.05, auroc=0.84,
                    n_train=80, trained_at=9.0, status="validated")
        self.assertEqual(p.weights, [0.1, -0.2])
        self.assertEqual(set(S.Probe.model_fields),
                         {"model_id", "layer", "weights", "bias", "auroc", "n_train", "trained_at",
                          "status"})

    def test_behaviour_stats_and_calibration_cell(self):
        b = S.BehaviourStats(model_id="m")
        for f in ("flip_to_wrong", "flip_to_right", "persuaded", "invalid", "timeouts", "runs",
                  "agree_with_decision"):
            self.assertEqual(getattr(b, f), 0, f)
        with self.assertRaises(ValidationError):
            S.BehaviourStats()
        c = S.CalibrationCell(task_id="b1", model_id="m", correct=True, answer_key="B")
        self.assertEqual((c.correct, c.answer_key), (True, "B"))
        self.assertEqual(S.CalibrationCell(task_id="b1", model_id="m").correct, False)
        with self.assertRaises(ValidationError):
            S.CalibrationCell(task_id="b1")

    def test_bench_request_and_summary(self):
        r = S.BenchRunRequest()
        self.assertEqual((r.tasks_path, r.modes, r.split, r.limit, r.models),
                         ("", [], "test", None, []))
        r = S.BenchRunRequest(tasks_path="b.jsonl", modes=["solo:m1", "council"],
                              split="calibration", limit=10, models=["m1"])
        self.assertEqual(r.modes, ["solo:m1", "council"])
        row = S.BenchSummaryRow(mode="council", n=3, accuracy=2 / 3,
                                by_difficulty={"hard": 0.5}, by_category={"math": 1.0},
                                mean_tokens=900.5, mean_wall_ms=1200)
        self.assertEqual(row.by_difficulty["hard"], 0.5)
        self.assertEqual(set(S.BenchSummaryRow.model_fields),
                         {"mode", "n", "accuracy", "by_difficulty", "by_category", "mean_tokens",
                          "mean_wall_ms"})

    def test_additions_to_existing_models(self):
        self.assertIsNone(S.ModelEntry(id="m").ollama_tag)
        self.assertEqual(S.ModelEntry(id="m", ollama_tag="gpt-oss:20b").ollama_tag, "gpt-oss:20b")
        self.assertIs(S.Decision(outcome="majority").contested_after_review, False)
        self.assertTrue(S.Decision(outcome="majority", contested_after_review=True)
                        .contested_after_review)
        res = S.CallResult(call_id="c", ok=True)
        self.assertIsNone(res.logprobs)
        self.assertEqual(S.CallResult(call_id="c", ok=True, logprobs=[-0.1, -2]).logprobs,
                         [-0.1, -2.0])
        snap = S.RunSnapshot(run_id="r")
        self.assertEqual((snap.tribunal, snap.corrections, snap.claim_scores), (None, [], []))
        snap = S.RunSnapshot(
            run_id="r", state="EXAMINING",
            tribunal={"outlier_seat": 2, "outcome": "vindicated", "held_share": 0.75},
            corrections=[{"id": "k1", "model_id": "m", "lesson": "l"}],
            claim_scores=[{"claim_ref": "c1", "reliability": 0.4, "seat_no": 0}],
        )
        self.assertIsInstance(snap.tribunal, S.TribunalOutcome)
        self.assertEqual(snap.corrections[0].id, "k1")
        self.assertEqual(snap.claim_scores[0].seat_no, 0)
        self.assertEqual(S.RunSnapshot.model_validate_json(snap.model_dump_json()), snap)

    def test_old_json_still_loads(self):
        # Records written before the additions carry none of the new keys.
        self.assertEqual(S.Decision.model_validate({"outcome": "consensus"}).outcome, "consensus")
        self.assertIsNone(S.RunSnapshot.model_validate({"run_id": "r", "state": "DECIDED"})
                          .tribunal)
        self.assertIsNone(S.CallResult.model_validate({"call_id": "c", "ok": False}).logprobs)

    def test_new_list_defaults_are_not_shared(self):
        a, b = S.TribunalOutcome(), S.TribunalOutcome()
        a.verdicts.append(S.DefenseVerdict(held=True))
        self.assertEqual(b.verdicts, [])
        x, y = S.RunSnapshot(run_id="x"), S.RunSnapshot(run_id="y")
        x.corrections.append(S.Correction())
        self.assertEqual(y.corrections, [])


if __name__ == "__main__":
    unittest.main()
