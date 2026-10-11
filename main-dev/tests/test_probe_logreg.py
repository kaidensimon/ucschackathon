import random
import unittest

from council.probe.logreg import (
    auroc,
    predict_proba,
    split,
    standardize,
    top_dimensions,
    train_logreg,
)


def separable(n=100, d=5, seed=1):
    rng = random.Random(seed)
    X, y = [], []
    for i in range(n):
        label = i % 2
        row = [rng.gauss(0, 1) for _ in range(d)]
        row[2] += 3.0 if label else -3.0
        X.append(row)
        y.append(label)
    return X, y


class LogregTests(unittest.TestCase):
    def test_standardize(self):
        X2, means, stds = standardize([[1.0, 5.0], [3.0, 5.0]])
        self.assertEqual(means, [2.0, 5.0])
        self.assertEqual(stds[1], 1.0)
        self.assertAlmostEqual(X2[0][0], -1.0)
        self.assertEqual(X2[0][1], 0.0)

    def test_separable_learns(self):
        X, y = separable()
        X2, _, _ = standardize(X)
        tr_x, tr_y, te_x, te_y = split(X2, y, 0.3, seed=2)
        w, b = train_logreg(tr_x, tr_y)
        scores = [predict_proba(w, b, r) for r in te_x]
        self.assertGreater(auroc(scores, te_y), 0.95)
        self.assertEqual(top_dimensions(w, 1)[0][0], 2)

    def test_deterministic(self):
        X, y = separable(40)
        self.assertEqual(train_logreg(X, y, seed=3), train_logreg(X, y, seed=3))

    def test_random_data_near_chance(self):
        rng = random.Random(5)
        X = [[rng.gauss(0, 1) for _ in range(4)] for _ in range(400)]
        y = [rng.randint(0, 1) for _ in range(400)]
        tr_x, tr_y, te_x, te_y = split(X, y, 0.5, seed=1)
        w, b = train_logreg(tr_x, tr_y)
        a = auroc([predict_proba(w, b, r) for r in te_x], te_y)
        self.assertLess(abs(a - 0.5), 0.15)

    def test_auroc_edges(self):
        self.assertEqual(auroc([0.1, 0.9], [0, 1]), 1.0)
        self.assertEqual(auroc([0.9, 0.1], [0, 1]), 0.0)
        self.assertEqual(auroc([0.5, 0.5], [0, 1]), 0.5)
        self.assertEqual(auroc([0.1, 0.2], [1, 1]), 0.5)
        self.assertEqual(auroc([], []), 0.5)

    def test_split(self):
        X = [[float(i)] for i in range(10)]
        y = [i % 2 for i in range(10)]
        a = split(X, y, 0.3, seed=4)
        self.assertEqual(len(a[2]), 3)
        self.assertEqual(len(a[0]), 7)
        self.assertEqual(a, split(X, y, 0.3, seed=4))

    def test_top_dimensions(self):
        self.assertEqual(top_dimensions([0.1, -3.0, 2.0], 2), [(1, -3.0), (2, 2.0)])

    def test_extreme_proba(self):
        self.assertEqual(predict_proba([1000.0], 0.0, [-1000.0]), 0.0)
        self.assertEqual(predict_proba([1000.0], 0.0, [1000.0]), 1.0)


if __name__ == "__main__":
    unittest.main()
