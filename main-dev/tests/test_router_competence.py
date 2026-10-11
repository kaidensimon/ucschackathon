import math
import unittest

from council.core.schemas import TaskProfile
from council.router.competence import (
    SkillTable,
    exploration_bonus,
    passes_floor,
    q_tier_a,
    q_tier_b,
)


class SkillTableTest(unittest.TestCase):
    def setUp(self):
        self.t = SkillTable({"m1": {"math": 0.8, "code": 0.4}})

    def test_prior_mean(self):
        self.assertAlmostEqual(self.t.mean("m1", "math"), 0.8)
        self.assertAlmostEqual(self.t.mean("zzz", "math"), 0.5)
        self.assertEqual(self.t.trials("m1", "math"), 0.0)

    def test_update(self):
        self.t.update("m1", "math", 0.0)
        self.assertAlmostEqual(self.t.mean("m1", "math"), 3.2 / 5.0)
        self.assertAlmostEqual(self.t.trials("m1", "math"), 1.0)
        self.t.update("m1", "math", 1.0, weight=0.5)
        self.assertAlmostEqual(self.t.trials("m1", "math"), 1.5)

    def test_stats_init_and_export(self):
        t = SkillTable({}, stats={("a", "code"): (3.0, 1.0)})
        self.assertAlmostEqual(t.mean("a", "code"), 0.75)
        ex = t.export()
        self.assertEqual(ex["stats"][0]["alpha"], 3.0)
        self.assertEqual(ex["prior_strength"], 4.0)

    def test_tier_a(self):
        p = TaskProfile(categories={"math": 0.5, "code": 0.5})
        self.assertAlmostEqual(q_tier_a("m1", p, self.t), 0.6)
        self.assertAlmostEqual(q_tier_a("m1", TaskProfile(), self.t), 0.5)


class TierBTest(unittest.TestCase):
    def test_no_neighbours(self):
        self.assertAlmostEqual(q_tier_b(0.7, []), 0.7)

    def test_shrink(self):
        nb = [(1.0, True)] * 5
        self.assertAlmostEqual(q_tier_b(0.0, nb), 0.5)
        nb = [(1.0, True)] * 30
        self.assertAlmostEqual(q_tier_b(0.0, nb), 30 / 35)

    def test_similarity_weight(self):
        nb = [(1.0, True), (0.1, False)]
        self.assertGreater(q_tier_b(0.5, nb, pseudo=0.0001), 0.9)


class FloorTest(unittest.TestCase):
    def test_floor(self):
        self.assertTrue(passes_floor(0.70, 0.80, False))
        self.assertFalse(passes_floor(0.69, 0.80, False))
        self.assertTrue(passes_floor(0.60, 0.80, True))
        self.assertFalse(passes_floor(0.59, 0.80, True))

    def test_bonus(self):
        self.assertAlmostEqual(exploration_bonus(0, 0), math.sqrt(2 * math.log(2)))
        self.assertLess(exploration_bonus(100, 10), exploration_bonus(100, 1))
        self.assertGreater(exploration_bonus(1000, 5), exploration_bonus(10, 5))


if __name__ == "__main__":
    unittest.main()
