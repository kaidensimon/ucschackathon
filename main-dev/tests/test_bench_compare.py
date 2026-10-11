import unittest

from council.bench.compare import FEW_TASKS_NOTE, compare, sign_test
from council.core.schemas_v15 import SoloScore


def S(m, t, ok, ans="", lat=None):
    return SoloScore(model_id=m, task_id=t, correct=ok, answer=ans, latency_s=lat)


def row(rep, name):
    return next(r for r in rep.rows if r.name == name)


class CompareTests(unittest.TestCase):
    def setUp(self):
        # 4 tasks, 3 models
        self.solo = [
            S("a", "t1", True, "A", 1.0), S("a", "t2", True, "B", 3.0),
            S("a", "t3", False, "C"), S("a", "t4", False, "D"),
            S("b", "t1", True, "A"), S("b", "t2", False, "X"),
            S("b", "t3", False, "C"), S("b", "t4", False, "E"),
            S("c", "t1", False, "Z"), S("c", "t2", False, "X"),
            S("c", "t3", True, "Q"), S("c", "t4", False, "F"),
        ]
        self.council = {"t1": True, "t2": False, "t3": True, "t4": True}

    def test_rows_and_accuracy(self):
        rep = compare(self.solo, self.council)
        self.assertEqual(rep.n_tasks, 4)
        self.assertEqual(row(rep, "a").accuracy, 0.5)
        self.assertEqual(row(rep, "b").accuracy, 0.25)
        self.assertAlmostEqual(row(rep, "mean_solo").accuracy, (0.5 + 0.25 + 0.25) / 3)
        self.assertEqual(row(rep, "oracle").accuracy, 0.75)
        self.assertEqual(row(rep, "council").accuracy, 0.75)
        self.assertEqual(row(rep, "council").kind, "council")
        self.assertEqual(row(rep, "oracle").kind, "baseline")
        self.assertEqual(row(rep, "a").mean_latency_s, 2.0)

    def test_best_and_diffs(self):
        rep = compare(self.solo, self.council)
        self.assertEqual(rep.best_solo, "a")
        self.assertAlmostEqual(rep.council_minus_best, 0.25)
        self.assertAlmostEqual(rep.council_minus_mean, 0.75 - 1 / 3)

    def test_only_right_wrong(self):
        rep = compare(self.solo, self.council)
        self.assertEqual(rep.council_only_right, ["t4"])
        self.assertEqual(rep.council_only_wrong, ["t2"])

    def test_majority_vote_by_answer(self):
        rep = compare(self.solo, self.council)
        # t1: A,A,Z -> A right. t2: B,X,X -> X, wrong. t3: C,C,Q -> C wrong. t4: all differ,
        # tie broken by best model a -> D wrong.
        self.assertEqual(row(rep, "majority_vote").accuracy, 0.25)
        self.assertAlmostEqual(rep.council_minus_vote, 0.5)

    def test_majority_vote_fallback_without_answers(self):
        solo = [S("a", "t1", True), S("b", "t1", True), S("c", "t1", False),
                S("a", "t2", True), S("b", "t2", False), S("c", "t2", False)]
        rep = compare(solo, {"t1": True, "t2": True})
        self.assertEqual(row(rep, "majority_vote").accuracy, 0.5)

    def test_vote_tie_uses_best_model(self):
        solo = [S("a", "t1", True), S("b", "t1", False),
                S("a", "t2", True), S("b", "t2", False),
                S("a", "t3", False), S("b", "t3", True)]
        rep = compare(solo, {"t1": True, "t2": True, "t3": True})
        # a is best (2/3); ties follow a: right, right, wrong
        self.assertAlmostEqual(row(rep, "majority_vote").accuracy, 2 / 3)

    def test_seat_models_subset(self):
        rep = compare(self.solo, self.council, seat_models=["a", "b"])
        # t1 A,A right. t2 B,X tie -> a: B right. t3 C,C wrong. t4 D,E tie -> a: D wrong.
        self.assertEqual(row(rep, "majority_vote").accuracy, 0.5)

    def test_drops_unanswered(self):
        solo = self.solo + [S("a", "t5", True)]
        council = dict(self.council, t6=True)
        rep = compare(solo, council)
        self.assertEqual(rep.n_tasks, 4)
        self.assertTrue(any("2 task(s) dropped" in n for n in rep.notes))

    def test_none_correct_is_unanswered(self):
        solo = self.solo + [S("a", "t5", None), S("b", "t5", True), S("c", "t5", True)]
        rep = compare(solo, dict(self.council, t5=True))
        self.assertEqual(rep.n_tasks, 4)

    def test_few_tasks_note(self):
        rep = compare(self.solo, self.council)
        self.assertIn(FEW_TASKS_NOTE, rep.notes)

    def test_no_few_tasks_note_at_30(self):
        solo, council = [], {}
        for i in range(30):
            t = f"t{i}"
            council[t] = True
            for m in ("a", "b"):
                solo.append(S(m, t, i % 2 == 0))
        rep = compare(solo, council)
        self.assertEqual(rep.n_tasks, 30)
        self.assertNotIn(FEW_TASKS_NOTE, rep.notes)

    def test_categories(self):
        cats = {"t1": "math", "t2": "math", "t3": "code", "t4": "code"}
        rep = compare(self.solo, self.council, categories=cats)
        self.assertEqual(row(rep, "a").by_category, {"code": 0.0, "math": 1.0})
        self.assertEqual(row(rep, "council").by_category, {"code": 1.0, "math": 0.5})
        self.assertIn("math", row(rep, "mean_solo").by_category)
        self.assertEqual(row(compare(self.solo, self.council), "a").by_category, {})

    def test_latency_override(self):
        rep = compare(self.solo, self.council, latency={"council": 42.0})
        self.assertEqual(row(rep, "council").mean_latency_s, 42.0)

    def test_empty(self):
        rep = compare([], {"t1": True})
        self.assertEqual(rep.n_tasks, 0)
        self.assertIsNone(rep.council_minus_best)
        rep2 = compare(self.solo, {})
        self.assertEqual(rep2.n_tasks, 0)
        self.assertIsNone(rep2.council_minus_best)
        self.assertEqual(row(rep2, "council").accuracy, 0.0)


class SignTestTests(unittest.TestCase):
    def test_counts(self):
        r = sign_test({"a": True, "b": False, "c": True, "d": True},
                      {"a": False, "b": True, "c": True, "e": True})
        self.assertEqual((r["wins"], r["losses"], r["ties"]), (1, 1, 1))
        self.assertEqual(r["p"], 1.0)

    def test_exact_p(self):
        council = {f"t{i}": True for i in range(10)}
        other = {f"t{i}": False for i in range(10)}
        r = sign_test(council, other)
        self.assertEqual(r["wins"], 10)
        self.assertAlmostEqual(r["p"], 2 / 1024)

    def test_no_discordant(self):
        r = sign_test({"a": True}, {"a": True})
        self.assertEqual(r["p"], 1.0)
        self.assertEqual(r["ties"], 1)

    def test_p_capped_and_symmetric(self):
        r1 = sign_test({"a": True, "b": False, "c": True}, {"a": False, "b": True, "c": False})
        r2 = sign_test({"a": False, "b": True, "c": False}, {"a": True, "b": False, "c": True})
        self.assertEqual(r1["p"], r2["p"])
        self.assertAlmostEqual(r1["p"], 1.0)


if __name__ == "__main__":
    unittest.main()
