import unittest

from council.api.run_summary import summarize, summary_text

KEYS = {
    "run_id", "started", "ended", "wall_s", "state", "lineup", "effort", "rounds",
    "agreement_trend", "decision", "extended", "tribunal", "plan", "tasks", "reviews",
    "final_say", "integration", "memory", "failures", "tokens", "calls",
}


def ev(seq, sec, typ, **payload):
    return {"seq": seq, "ts": f"2026-10-11T10:00:{sec:02d}+00:00", "type": typ, "payload": payload}


def full_run():
    return [
        {**ev(1, 0, "run.created", task="x"), "run_id": "r1"},
        ev(2, 1, "run.state_changed", to_state="routing"),
        ev(3, 2, "router.lineup_selected", lineup={"seats": [
            {"seat_no": 1, "model_id": "m1", "lens": "skeptic"},
            {"seat_no": 2, "model_id": "m2", "lens": None}]}),
        ev(4, 3, "effort.planned", level="light", deadline_s=60, max_extra_rounds=1),
        ev(5, 4, "round.started", round=1),
        ev(6, 10, "round.completed", round=1, agreement=0.5, tally={"A": 3, "B": 3}, converged=False, ms=6000),
        ev(7, 11, "round.extended", round=2),
        ev(8, 12, "round.started", round=2),
        ev(9, 15, "round.completed", round=2, agreement=0.83, tally={"A": 5, "B": 1}, converged=True),
        ev(10, 16, "decision.final", decision={
            "outcome": "consensus", "option_id": "A", "agreement": 0.83, "rounds_run": 2,
            "confidence": 0.7, "final_text": "z" * 900}),
        ev(11, 17, "tribunal.outcome", outcome="upheld", seat_no=3),
        ev(12, 18, "plan.ready", plan={"tasks": [{"id": "t1", "title": "one"}, {"id": "t2", "title": "two"}]}),
        ev(13, 19, "task.failed", task_id="t1", failing_check="c1"),
        ev(14, 20, "task.passed", task_id="t1"),
        ev(15, 21, "task.blocked", task_id="t2"),
        ev(16, 22, "review.verdict", verdict="approve", tally={"approve": 5}, cycle=1),
        ev(17, 23, "review.final_say", seat_no=2, verdict="approve"),
        ev(18, 24, "integration.result", ok=False, files_written=["a"]),
        ev(19, 25, "integration.result", ok=True, files_written=["a", "b"]),
        ev(20, 26, "memory.candidate"),
        ev(21, 26, "memory.candidate"),
        ev(22, 27, "memory.committed"),
        ev(23, 28, "turn.completed", call_id="c", tokens_in=10, tokens_out=5),
        ev(24, 28, "turn.completed", call_id="d", tokens=7),
        ev(25, 29, "turn.timeout", call_id="e", model_id="m1", timeout_s=30),
        ev(26, 30, "run.state_changed", to_state="done"),
    ]


class RunSummaryTest(unittest.TestCase):
    def test_empty(self):
        s = summarize([])
        self.assertEqual(set(s), KEYS)
        self.assertIsNone(s["effort"])
        self.assertEqual(s["calls"], 0)
        self.assertIsInstance(summary_text(s), str)

    def test_full(self):
        s = summarize(full_run())
        self.assertEqual(set(s), KEYS)
        self.assertEqual(s["run_id"], "r1")
        self.assertEqual(s["state"], "done")
        self.assertEqual(s["wall_s"], 30.0)
        self.assertEqual(s["lineup"][0], {"seat_no": 1, "model_id": "m1", "lens": "skeptic"})
        self.assertEqual(s["effort"]["level"], "light")
        self.assertEqual(s["agreement_trend"], [0.5, 0.83])
        self.assertEqual(s["rounds"][0]["seconds"], 6.0)
        self.assertEqual(s["rounds"][1]["seconds"], 3.0)
        self.assertTrue(s["rounds"][1]["converged"])
        self.assertEqual(s["extended"], 1)
        self.assertEqual(len(s["decision"]["final_text"]), 600)
        self.assertEqual(s["decision"]["outcome"], "consensus")
        self.assertEqual(s["tribunal"]["outcome"], "upheld")
        self.assertEqual(s["plan"], {"tasks": 2, "titles": ["one", "two"]})
        self.assertEqual(s["tasks"], {"passed": 1, "failed": 0, "blocked": 1, "skipped": 0})
        self.assertEqual(s["reviews"][0]["verdict"], "approve")
        self.assertEqual(s["final_say"]["seat_no"], 2)
        self.assertEqual(s["integration"], {"ok": True, "files_written": 2})
        self.assertEqual(s["memory"], {"candidates": 2, "committed": 1})
        self.assertEqual(s["tokens"], {"in": 10, "out": 12})
        self.assertEqual(s["calls"], 2)
        self.assertEqual([f["type"] for f in s["failures"]], ["task.failed", "turn.timeout"])
        self.assertEqual(s["failures"][1]["seq"], 25)

    def test_malformed_skipped(self):
        bad = [None, 5, "x", {}, {"type": 3}, {"type": "round.completed", "payload": "no"},
               {"type": "turn.completed", "payload": {"tokens_in": "many"}, "ts": "garbage"},
               {"type": "plan.ready", "payload": {"plan": {"tasks": "zzz"}}},
               {"type": "router.lineup_selected", "payload": {"lineup": {"seats": [1, None]}}}]
        s = summarize(bad + full_run())
        self.assertEqual(s["run_id"], "r1")
        self.assertEqual(s["plan"]["tasks"], 2)
        self.assertEqual(len(s["lineup"]), 2)  # bad lineup came first, good one overwrote it
        self.assertEqual(summarize(bad)["lineup"], [])
        self.assertEqual(summarize(None)["calls"], 0)

    def test_failure_types(self):
        s = summarize([
            ev(1, 0, "model.failed", model_id="m", error="boom", stage="load"),
            ev(2, 1, "turn.invalid", call_id="c", error="bad json"),
            ev(3, 2, "run.failed", error="x" * 500),
        ])
        self.assertEqual(len(s["failures"]), 3)
        self.assertLessEqual(len(s["failures"][2]["short"]), 120)

    def test_review_rounds_not_in_deliberation(self):
        s = summarize([ev(1, 0, "round.started", round=1, is_review=True),
                       ev(2, 1, "round.completed", round=1, agreement=1.0)])
        self.assertEqual(s["rounds"], [])

    def test_text(self):
        t = summary_text(summarize(full_run()))
        self.assertIn("RUN r1", t)
        self.assertIn("DECISION consensus", t)
        self.assertIn("FAILURES 2", t)
        self.assertLessEqual(len(t.splitlines()), 40)

    def test_text_partial(self):
        self.assertIsInstance(summary_text({}), str)
        self.assertIsInstance(summary_text(None), str)
        self.assertIsInstance(summary_text({"decision": None, "rounds": [None]}), str)


if __name__ == "__main__":
    unittest.main()
