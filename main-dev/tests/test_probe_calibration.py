import math
import random
import unittest

from council.probe.calibration import (
    apply_platt,
    auroc,
    brier,
    ece,
    fit_platt,
    reliability_table,
)


class PlattTests(unittest.TestCase):
    def test_one_class_identity(self):
        self.assertEqual(fit_platt([0.1, 0.5, 0.9], [1, 1, 1]), (1.0, 0.0))
        self.assertEqual(fit_platt([0.1, 0.5], [0, 0]), (1.0, 0.0))

    def test_empty_identity(self):
        self.assertEqual(fit_platt([], []), (1.0, 0.0))

    def test_fit_separable_is_monotone_up(self):
        scores = [-2.0, -1.5, -1.0, -0.5, 0.5, 1.0, 1.5, 2.0]
        labels = [0, 0, 0, 0, 1, 1, 1, 1]
        ab = fit_platt(scores, labels, iters=500, lr=0.5)
        self.assertGreater(ab[0], 1.0)
        self.assertGreater(apply_platt(2.0, ab), 0.8)
        self.assertLess(apply_platt(-2.0, ab), 0.2)

    def test_fit_improves_brier(self):
        rng = random.Random(7)
        scores, labels = [], []
        for _ in range(300):
            y = rng.randint(0, 1)
            scores.append(rng.gauss(2.0 * y - 1.0, 1.0))
            labels.append(y)
        raw = [apply_platt(s, (1.0, 0.0)) for s in scores]
        ab = fit_platt(scores, labels, iters=400, lr=0.3)
        fitted = [apply_platt(s, ab) for s in scores]
        self.assertLessEqual(brier(fitted, labels), brier(raw, labels) + 1e-9)

    def test_apply_platt_range_and_extremes(self):
        self.assertAlmostEqual(apply_platt(0.0, (1.0, 0.0)), 0.5)
        self.assertEqual(apply_platt(1e6, (1.0, 0.0)), 1.0)
        self.assertEqual(apply_platt(-1e6, (1.0, 0.0)), 0.0)
        self.assertTrue(0.0 < apply_platt(1.0, (2.0, -1.0)) < 1.0)

    def test_length_mismatch(self):
        with self.assertRaises(ValueError):
            fit_platt([0.1], [1, 0])


class MetricTests(unittest.TestCase):
    def test_brier(self):
        self.assertAlmostEqual(brier([1.0, 0.0], [1, 0]), 0.0)
        self.assertAlmostEqual(brier([0.0, 1.0], [1, 0]), 1.0)
        self.assertAlmostEqual(brier([0.5, 0.5], [1, 0]), 0.25)
        self.assertEqual(brier([], []), 0.0)

    def test_ece_perfect_and_bad(self):
        self.assertAlmostEqual(ece([1.0, 1.0, 0.0, 0.0], [1, 1, 0, 0]), 0.0)
        self.assertAlmostEqual(ece([0.9, 0.9], [0, 0]), 0.9)
        self.assertEqual(ece([], []), 0.0)

    def test_ece_calibrated_bin(self):
        probs = [0.75] * 4
        labels = [1, 1, 1, 0]
        self.assertAlmostEqual(ece(probs, labels), 0.0)

    def test_reliability_table(self):
        rows = reliability_table([0.05, 0.15, 0.95, 1.0], [0, 1, 1, 1], bins=10)
        self.assertEqual(len(rows), 10)
        self.assertEqual(sum(r["n"] for r in rows), 4)
        self.assertEqual(rows[0]["n"], 1)
        self.assertEqual(rows[9]["n"], 2)  # 1.0 lands in last bin
        self.assertAlmostEqual(rows[9]["mean_p"], 0.975)
        self.assertAlmostEqual(rows[9]["frac_true"], 1.0)
        self.assertEqual(rows[5]["n"], 0)
        self.assertIsNone(rows[5]["mean_p"])
        self.assertAlmostEqual(rows[3]["lo"], 0.3)
        self.assertAlmostEqual(rows[3]["hi"], 0.4)

    def test_auroc_perfect_inverse_random(self):
        self.assertEqual(auroc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]), 1.0)
        self.assertEqual(auroc([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1]), 0.0)
        self.assertAlmostEqual(auroc([0.5, 0.5, 0.5, 0.5], [0, 1, 0, 1]), 0.5)

    def test_auroc_ties_averaged(self):
        # pos scores {1, 2}, neg scores {1, 0}: pairs: 1>1 tie(.5), 1>0 (1), 2>1 (1), 2>0 (1) => 3.5/4
        self.assertAlmostEqual(auroc([1, 2, 1, 0], [1, 1, 0, 0]), 0.875)

    def test_auroc_one_class_none(self):
        self.assertIsNone(auroc([0.1, 0.2], [1, 1]))
        self.assertIsNone(auroc([0.1, 0.2], [0, 0]))
        self.assertIsNone(auroc([], []))

    def test_auroc_matches_bruteforce(self):
        rng = random.Random(3)
        scores = [round(rng.random(), 1) for _ in range(60)]
        labels = [rng.randint(0, 1) for _ in range(60)]
        pos = [s for s, y in zip(scores, labels) if y]
        neg = [s for s, y in zip(scores, labels) if not y]
        wins = sum(1.0 if p > q else 0.5 if p == q else 0.0 for p in pos for q in neg)
        self.assertTrue(math.isclose(auroc(scores, labels), wins / (len(pos) * len(neg))))


if __name__ == "__main__":
    unittest.main()
