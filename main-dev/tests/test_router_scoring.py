import random
import unittest

from council.router.scoring import ScoringContext, score_lineup, softmax_sample

W = dict(merit=1, vote=1, cover=1, div=1, load=1, repeat=1)


def ctx(**kw):
    base = dict(q={"a": 0.8, "b": 0.4, "c": 0.6}, distance=lambda i, j: 0.5, weights=W)
    base.update(kw)
    return ScoringContext(**base)


class T(unittest.TestCase):
    def test_merit_div(self):
        s = score_lineup(["a", "b"], ctx())
        self.assertAlmostEqual(s.merit, 0.6)
        self.assertAlmostEqual(s.div, 0.5)
        self.assertAlmostEqual(s.total, 0.6 + 0.5)

    def test_single_div_zero(self):
        self.assertEqual(score_lineup(["a"], ctx()).div, 0.0)

    def test_vote_cover_tier_b(self):
        nbs = [
            {"weight": 3, "truth": "X", "answers": {"a": "X", "b": "X", "c": "Y"}},
            {"weight": 1, "truth": "X", "answers": {"a": "Y", "b": "Y", "c": "X"}},
        ]
        s = score_lineup(["a", "b", "c"], ctx(tier="B", neighbours=nbs))
        self.assertAlmostEqual(s.vote, 0.75)
        self.assertAlmostEqual(s.cover, 1.0)

    def test_tie_includes_truth(self):
        nbs = [{"weight": 1, "truth": "X", "answers": {"a": "X", "b": "Y"}}]
        s = score_lineup(["a", "b"], ctx(tier="B", neighbours=nbs))
        self.assertAlmostEqual(s.vote, 0.5)

    def test_tier_a_or_none(self):
        nbs = [{"weight": 1, "truth": "X", "answers": {"a": "X"}}]
        self.assertEqual(score_lineup(["a"], ctx(tier="A", neighbours=nbs)).vote, 0.0)
        self.assertEqual(score_lineup(["a"], ctx(tier="B", neighbours=None)).cover, 0.0)

    def test_load(self):
        c = ctx(resident={"a"}, load_s={"a": 100, "b": 60, "c": 600}, deadline_s=300)
        self.assertAlmostEqual(score_lineup(["a", "b"], c).load, 0.2)
        self.assertEqual(score_lineup(["a", "c"], c).load, 1.0)

    def test_repeat(self):
        rec = [["a", "b"], ["c", "d"]] 
        s = score_lineup(["a", "b"], ctx(recent=rec))
        self.assertAlmostEqual(s.repeat, 0.5)
        many = [["a", "b"]] * 5
        self.assertAlmostEqual(score_lineup(["a", "b"], ctx(recent=[["z"]] * 3 + many)).repeat, 1.0)

    def test_softmax(self):
        scored = [(["a"], 1.0), (["b"], 0.0), (["c"], 0.9)]
        self.assertEqual(softmax_sample(scored, 0.0001, 3, random.Random(1)), ["a"])
        picks = {tuple(softmax_sample(scored, 0.05, 2, random.Random(i))) for i in range(50)}
        self.assertTrue(picks <= {("a",), ("c",)})
        self.assertEqual(softmax_sample(scored, 0.05, 3, random.Random(3)), softmax_sample(scored, 0.05, 3, random.Random(3)))


if __name__ == "__main__":
    unittest.main()
