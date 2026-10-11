import unittest

from council.core.schemas import (
    Check,
    MicroTask,
    Plan,
    ReviewBallot,
    ReviewFix,
    SeatAssignment,
)
from council.works.review import (
    ballot_record,
    build_final_call,
    build_rebuttal_call,
    build_review_call,
    decide_review,
    final_verdict,
    fixes_to_tasks,
    merge_fixes,
    needs_debate,
    pick_decider,
)


def B(v, fixes=None):
    return ReviewBallot(verdict=v, fixes=fixes or [])


class ReviewTests(unittest.TestCase):
    def test_build_call(self):
        seat = SeatAssignment(seat_no=3, model_id="m1")
        c = build_review_call("r1", seat, "REPORT", "GOAL", 2)
        self.assertEqual(c.call_id, "r1:rv2:3")
        self.assertEqual(c.purpose, "review")
        self.assertEqual(c.model_id, "m1")
        self.assertIn("verdict", c.json_schema["properties"])
        self.assertIn("REPORT", c.messages[1]["content"])
        self.assertIn("GOAL", c.messages[1]["content"])

    def test_accept(self):
        d, c = decide_review({1: B("accept"), 2: B("accept"), 3: B("accept"), 4: B("accept"), 5: B("fix")})
        self.assertEqual(d, "accept")
        self.assertEqual(c["accept"], 4)

    def test_none_ballots_ignored(self):
        d, _ = decide_review({1: B("accept"), 2: None, 3: B("accept")})
        self.assertEqual(d, "accept")

    def test_fix_majority(self):
        d, _ = decide_review({1: B("accept"), 2: B("fix"), 3: B("fix"), 4: B("replan")})
        self.assertEqual(d, "fix")

    def test_replan(self):
        d, _ = decide_review({1: B("replan"), 2: B("replan"), 3: B("replan"), 4: B("fix")})
        self.assertEqual(d, "replan")

    def test_ask_user_and_empty(self):
        d, _ = decide_review({1: B("ask_user"), 2: B("replan"), 3: B("fix"), 4: B("replan")})
        self.assertEqual(d, "ask_user")
        d, c = decide_review({1: None})
        self.assertEqual(d, "ask_user")
        self.assertEqual(sum(c.values()), 0)

    def test_merge_dedup(self):
        f1 = ReviewFix(task_id="t1", problem="Missing  import")
        f2 = ReviewFix(task_id="t1", problem="missing import ")
        f3 = ReviewFix(task_id=None, problem="missing import")
        out = merge_fixes({1: B("fix", [f1]), 2: B("fix", [f2, f3]), 3: None})
        self.assertEqual(len(out), 2)

    def test_fixes_to_tasks(self):
        chk = Check(type="exists", path="a.py")
        plan = Plan(goal="g", tasks=[MicroTask(id="t1", title="T", write_set=["a.py"], acceptance=[chk])])
        fixes = [
            ReviewFix(task_id="t1", problem="bad", proposed_change="do x"),
            ReviewFix(task_id="zzz", problem="other"),
        ]
        ts = fixes_to_tasks(fixes, plan, 1)
        # One revise task per file: both problems land on a.py, the only file the plan writes.
        self.assertEqual([t.id for t in ts], ["fix1_1"])
        self.assertEqual(ts[0].kind, "edit_file")
        self.assertEqual(ts[0].write_set, ["a.py"])
        self.assertEqual(ts[0].acceptance[0].path, "a.py")
        self.assertIn("do x", ts[0].goal)
        self.assertIn("other", ts[0].goal)

    def test_fixes_are_grouped_per_file_and_tests_come_after_code(self):
        plan = Plan(goal="g", tasks=[
            MicroTask(id="c", write_set=["pkg/m.py"]),
            MicroTask(id="t", write_set=["tests/test_m.py"]),
        ])
        ts = fixes_to_tasks([ReviewFix(task_id=None, problem="tests fail")], plan, 2)
        self.assertEqual([t.write_set for t in ts], [["pkg/m.py"], ["tests/test_m.py"]])
        self.assertEqual(ts[1].deps, [ts[0].id])
        self.assertEqual(fixes_to_tasks([], plan, 2), [])


class DebateTests(unittest.TestCase):
    def test_review_call_uses_templates(self):
        c = build_review_call("r1", SeatAssignment(seat_no=1, model_id="m"), "REP", "GOAL", 1)
        self.assertEqual(c.max_output_tokens, 900)
        self.assertIn("reviewer", c.messages[0]["content"])
        self.assertIn("CURRENT STATE", c.messages[1]["content"])
        self.assertIn("review cycle 1", c.messages[1]["content"])

    def test_rebuttal_call_letters_no_seats(self):
        seat = SeatAssignment(seat_no=4, model_id="secret-model")
        own = B("fix", [ReviewFix(problem="p0", task_id="t1", proposed_change="c0")])
        others = [B("accept"), B("fix", [ReviewFix(problem="p1")])]
        c = build_rebuttal_call("r1", seat, "REP", "GOAL", 2, own, others)
        self.assertEqual(c.call_id, "r1:rvd2:4")
        self.assertEqual(c.meta["round"], "rvd2")
        u = c.messages[1]["content"]
        self.assertIn('"reviewer":"A"', u)
        self.assertIn('"reviewer":"B"', u)
        self.assertIn("p1", u)
        self.assertIn("p0", u)
        self.assertNotIn("secret-model", u)
        self.assertNotIn("seat", u.lower().replace("seats", ""))
        c2 = build_rebuttal_call("r1", seat, "REP", "GOAL", 2, None, others)
        self.assertIn("none", c2.messages[1]["content"])

    def test_needs_debate(self):
        self.assertFalse(needs_debate({1: B("accept"), 2: B("accept"), 3: B("accept"), 4: B("accept"), 5: B("accept")}))
        self.assertFalse(needs_debate({1: B("accept"), 2: B("accept"), 3: B("accept"), 4: B("accept"), 5: B("fix")}))
        self.assertTrue(needs_debate({1: B("accept"), 2: B("accept"), 3: B("accept"), 4: B("fix"), 5: B("fix")}))
        self.assertFalse(needs_debate({1: B("accept"), 2: None}))
        self.assertFalse(needs_debate({}))
        self.assertTrue(needs_debate({1: B("accept"), 2: B("fix"), 3: None}))
        self.assertFalse(needs_debate({1: B("fix"), 2: B("fix"), 3: B("fix"), 4: None}))
        self.assertTrue(needs_debate({1: B("accept"), 2: B("fix")}, threshold=0.6))

    def test_pick_decider(self):
        seats = [SeatAssignment(seat_no=n, model_id=f"m{n}") for n in (5, 1, 3, 2, 4)]
        a = pick_decider(seats, 7, 1)
        self.assertEqual(a.seat_no, pick_decider(list(reversed(seats)), 7, 1).seat_no)
        self.assertIn(a, seats)
        picks = {pick_decider(seats, s, c).seat_no for s in range(10) for c in range(3)}
        self.assertGreater(len(picks), 1)
        with self.assertRaises(ValueError):
            pick_decider([], 1, 1)

    def test_final_call_and_verdict(self):
        seat = SeatAssignment(seat_no=2, model_id="m")
        hist = [{"cycle": 1, "tally": {"accept": 2}, "ballots": [{"reviewer": "A", "verdict": "accept", "reason": "ok"}]}]
        c = build_final_call("r1", seat, "REP", "GOAL", 1, hist)
        self.assertEqual(c.call_id, "r1:rvf1:2")
        self.assertEqual(c.max_output_tokens, 600)
        self.assertEqual(c.purpose, "review")
        self.assertIn('"reviewer":"A"', c.messages[1]["content"])
        self.assertIn("verdict", c.json_schema["properties"])
        self.assertTrue(final_verdict(None))
        self.assertTrue(final_verdict(B("accept")))
        self.assertFalse(final_verdict(B("fix")))
        self.assertFalse(final_verdict(B("replan")))

    def test_ballot_record(self):
        rec = ballot_record(
            {3: ReviewBallot(verdict="fix", reason="r3"), 1: ReviewBallot(verdict="accept", reason="r1"), 2: None},
            2,
            {"accept": 1, "fix": 1},
        )
        self.assertEqual(rec["cycle"], 2)
        self.assertEqual(rec["tally"], {"accept": 1, "fix": 1})
        self.assertEqual(
            rec["ballots"],
            [
                {"reviewer": "A", "verdict": "accept", "reason": "r1"},
                {"reviewer": "B", "verdict": "fix", "reason": "r3"},
            ],
        )

    def test_fix_tasks_test_cmd(self):
        plan = Plan(goal="g", tasks=[
            MicroTask(id="c", write_set=["pkg/m.py"]),
            MicroTask(id="t", write_set=["tests/test_m.py"]),
            MicroTask(id="d", write_set=["pkg/z.py"]),
        ])
        fx = [ReviewFix(task_id=None, problem="x")]
        cmd = "python -m unittest discover -s tests"
        ts = fixes_to_tasks(fx, plan, 1, test_cmd=cmd)
        has = [any(k.type == "command" and k.cmd == cmd and k.timeout_s == 120 for k in t.acceptance) for t in ts]
        self.assertEqual([t.write_set[0] for t in ts], ["pkg/m.py", "pkg/z.py", "tests/test_m.py"])
        self.assertEqual(has, [False, False, True])
        ts = fixes_to_tasks([ReviewFix(task_id="c", problem="x")], plan, 1, test_cmd=cmd)
        self.assertEqual(len(ts), 1)
        self.assertEqual(ts[0].acceptance[-1].type, "command")
        ts = fixes_to_tasks(fx, plan, 1)
        self.assertFalse(any(k.type == "command" for t in ts for k in t.acceptance))


if __name__ == "__main__":
    unittest.main()
