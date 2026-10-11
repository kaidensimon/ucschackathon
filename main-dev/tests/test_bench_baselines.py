"""Tests for council.bench.baselines. Stdlib unittest only, no model server."""

from __future__ import annotations

import unittest

from council.bench.baselines import (
    accuracy,
    best_k,
    by_model,
    common_tasks,
    oracle,
    per_task,
    vote,
)
from council.core.schemas_v15 import SoloScore


def S(model: str, task: str, correct=None, score=None) -> SoloScore:
    return SoloScore(model_id=model, task_id=task, correct=correct, score=score)


def fixture() -> list[SoloScore]:
    # a: t1 right, t2 wrong, t3 right (score 0.7)  -> 2/3
    # b: t1 wrong, t2 right, t3 wrong (score 0.2)  -> 1/3
    # c: t1 wrong, t2 right, t3 no answer          -> 1/3
    return [
        S("a", "t1", correct=True),
        S("b", "t1", correct=False),
        S("c", "t1", correct=False),
        S("a", "t2", correct=False),
        S("b", "t2", correct=True),
        S("c", "t2", correct=True),
        S("a", "t3", score=0.7),
        S("b", "t3", score=0.2),
        S("c", "t3"),
    ]


class PerTaskTests(unittest.TestCase):
    def test_nests_task_then_model(self):
        table = per_task(fixture())
        self.assertEqual(set(table), {"t1", "t2", "t3"})
        self.assertEqual(set(table["t1"]), {"a", "b", "c"})
        self.assertIs(table["t1"]["a"].correct, True)

    def test_last_row_wins(self):
        rows = fixture() + [S("a", "t1", correct=False)]
        self.assertIs(per_task(rows)["t1"]["a"].correct, False)

    def test_empty(self):
        self.assertEqual(per_task([]), {})

    def test_does_not_mutate_input(self):
        rows = fixture()
        before = list(rows)
        per_task(rows)
        self.assertEqual(rows, before)


class AccuracyTests(unittest.TestCase):
    def test_empty_is_zero(self):
        self.assertEqual(accuracy([]), 0.0)

    def test_all_right(self):
        self.assertEqual(accuracy([S("a", "t", correct=True)] * 4), 1.0)

    def test_mixed_share(self):
        rows = [S("a", "t1", correct=True), S("a", "t2", correct=False),
                S("a", "t3", correct=True), S("a", "t4", correct=False)]
        self.assertEqual(accuracy(rows), 0.5)

    def test_score_threshold_when_correct_is_none(self):
        self.assertEqual(accuracy([S("a", "t", score=0.5)]), 1.0)
        self.assertEqual(accuracy([S("a", "t", score=0.49)]), 0.0)
        self.assertEqual(accuracy([S("a", "t", score=0.9)]), 1.0)

    def test_correct_overrides_score(self):
        self.assertEqual(accuracy([S("a", "t", correct=False, score=0.9)]), 0.0)
        self.assertEqual(accuracy([S("a", "t", correct=True, score=0.1)]), 1.0)

    def test_neither_field_counts_wrong(self):
        self.assertEqual(accuracy([S("a", "t")]), 0.0)

    def test_fixture_accuracy(self):
        self.assertAlmostEqual(accuracy(fixture()), 4 / 9)


class ByModelTests(unittest.TestCase):
    def test_per_model_accuracy(self):
        scores = by_model(fixture())
        self.assertEqual(set(scores), {"a", "b", "c"})
        self.assertAlmostEqual(scores["a"], 2 / 3)
        self.assertAlmostEqual(scores["b"], 1 / 3)
        self.assertAlmostEqual(scores["c"], 1 / 3)

    def test_rerun_replaces_earlier_answer(self):
        rows = fixture() + [S("b", "t1", correct=True)]
        self.assertAlmostEqual(by_model(rows)["b"], 2 / 3)

    def test_empty(self):
        self.assertEqual(by_model([]), {})


class BestKTests(unittest.TestCase):
    def test_top_one(self):
        self.assertEqual(best_k(fixture(), 1), ["a"])

    def test_ties_by_id(self):
        self.assertEqual(best_k(fixture(), 3), ["a", "b", "c"])
        self.assertEqual(best_k(fixture(), 2), ["a", "b"])

    def test_k_larger_than_pool(self):
        self.assertEqual(len(best_k(fixture(), 10)), 3)

    def test_k_zero_or_negative(self):
        self.assertEqual(best_k(fixture(), 0), [])
        self.assertEqual(best_k(fixture(), -2), [])

    def test_empty(self):
        self.assertEqual(best_k([], 3), [])


class OracleTests(unittest.TestCase):
    def test_all_models(self):
        self.assertEqual(oracle(fixture()), {"t1": True, "t2": True, "t3": True})

    def test_subset_can_be_false(self):
        self.assertEqual(oracle(fixture(), ["b"]), {"t1": False, "t2": True, "t3": False})

    def test_subset_without_answers_gives_no_tasks(self):
        self.assertEqual(oracle(fixture(), ["zzz"]), {})

    def test_all_wrong_task_is_false(self):
        rows = [S("a", "t9", correct=False), S("b", "t9", score=0.1)]
        self.assertEqual(oracle(rows), {"t9": False})

    def test_empty(self):
        self.assertEqual(oracle([]), {})


class VoteTests(unittest.TestCase):
    def test_all_models_majority(self):
        # t1: 1 of 3 right, t2: 2 of 3 right, t3: 1 of 3 right
        self.assertEqual(vote(fixture()), {"t1": False, "t2": True, "t3": False})

    def test_tie_is_not_majority(self):
        rows = [S("a", "t", correct=True), S("b", "t", correct=False)]
        self.assertEqual(vote(rows), {"t": False})

    def test_missing_voter_counts_wrong(self):
        rows = [S("a", "t", correct=True), S("b", "t", correct=True)]
        # voters a, b, c: 2 of 3 right -> majority
        self.assertEqual(vote(rows, ["a", "b", "c"]), {"t": True})
        # voters a, b, c, d: 2 of 4 right -> tie -> not majority
        self.assertEqual(vote(rows, ["a", "b", "c", "d"]), {"t": False})

    def test_listed_subset(self):
        self.assertEqual(
            vote(fixture(), ["a", "b"]),
            {"t1": False, "t2": False, "t3": False},
        )

    def test_no_answers_needed_for_score_rows(self):
        rows = [S("a", "t", score=0.9), S("b", "t", score=0.8), S("c", "t", score=0.1)]
        self.assertEqual(vote(rows), {"t": True})

    def test_empty(self):
        self.assertEqual(vote([]), {})


class CommonTasksTests(unittest.TestCase):
    def setUp(self):
        # t1, t2, t3 answered by a, b, c; t2 also by d; t4 only by a.
        self.rows = fixture() + [S("d", "t2", correct=True), S("a", "t4", correct=True)]

    def test_all_models_common(self):
        self.assertEqual(common_tasks(self.rows), ["t2"])

    def test_listed_subset(self):
        self.assertEqual(common_tasks(self.rows, ["a", "b"]), ["t1", "t2", "t3"])

    def test_sorted_output(self):
        shuffled = list(reversed(self.rows))
        self.assertEqual(common_tasks(shuffled, ["a", "b"]), ["t1", "t2", "t3"])

    def test_empty_models_list(self):
        self.assertEqual(common_tasks(self.rows, []), [])

    def test_empty_solo(self):
        self.assertEqual(common_tasks([]), [])


if __name__ == "__main__":
    unittest.main()
