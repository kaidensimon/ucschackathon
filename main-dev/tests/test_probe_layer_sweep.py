import random
import unittest

from council.probe import layer_sweep as ls


def _data(n=60, d=4, signal=3.0, seed=1):
    rng = random.Random(seed)
    labels = [i % 2 for i in range(n)]
    good = [[rng.gauss(0, 1) + (signal if l else 0.0) * (j == 0) for j in range(d)] for l in labels]
    noise = [[rng.gauss(0, 1) for _ in range(d)] for _ in labels]
    return good, noise, labels


class LayerScoresTest(unittest.TestCase):
    def test_signal_beats_noise(self):
        good, noise, labels = _data()
        s = ls.layer_scores({3: good, 7: noise}, labels, seed=2)
        self.assertGreater(s[3], 0.9)
        self.assertLess(s[7], 0.8)
        self.assertGreater(s[3], s[7])

    def test_deterministic(self):
        good, noise, labels = _data()
        a = ls.layer_scores({1: good, 2: noise}, labels, seed=5)
        b = ls.layer_scores({1: good, 2: noise}, labels, seed=5)
        self.assertEqual(a, b)

    def test_scores_in_range(self):
        good, noise, labels = _data()
        for v in ls.layer_scores({1: good, 2: noise}, labels).values():
            self.assertTrue(0.0 <= v <= 1.0)

    def test_groups_never_straddle(self):
        groups = [f"g{i // 4}" for i in range(60)]
        for seed in range(10):
            train, test = ls._split_indices(60, groups, seed)
            self.assertTrue(train and test)
            self.assertEqual(set(groups[i] for i in train) & set(groups[i] for i in test), set())
            self.assertEqual(sorted(train + test), list(range(60)))

    def test_index_split_70_30(self):
        train, test = ls._split_indices(100, None, 0)
        self.assertEqual(len(test), 30)
        self.assertEqual(len(train), 70)
        self.assertEqual(set(train) & set(test), set())

    def test_groups_scoring_works(self):
        good, _, labels = _data()
        groups = [f"g{i // 2}" for i in range(len(labels))]
        s = ls.layer_scores({0: good}, labels, groups=groups, seed=3)
        self.assertGreater(s[0], 0.8)

    def test_single_class_gives_half(self):
        rows = [[float(i), 1.0] for i in range(10)]
        s = ls.layer_scores({0: rows}, [1] * 10)
        self.assertEqual(s[0], 0.5)

    def test_bad_lengths(self):
        with self.assertRaises(ValueError):
            ls.layer_scores({0: [[1.0]] * 3}, [0, 1])
        with self.assertRaises(ValueError):
            ls.layer_scores({0: [[1.0]] * 2}, [0, 1], groups=["a"])

    def test_empty(self):
        self.assertEqual(ls.layer_scores({}, []), {})


class PickLayersTest(unittest.TestCase):
    def test_best_k_sorted(self):
        s = {2: 0.5, 6: 0.9, 10: 0.8, 14: 0.7, 18: 0.6}
        self.assertEqual(ls.pick_layers(s, k=3), [6, 10, 14])

    def test_gap_respected(self):
        s = {5: 0.95, 6: 0.94, 7: 0.93, 12: 0.7, 20: 0.6}
        self.assertEqual(ls.pick_layers(s, k=3, min_gap=2), [5, 7, 12])

    def test_gap_relaxed_when_short(self):
        s = {5: 0.9, 6: 0.8, 7: 0.7}
        self.assertEqual(ls.pick_layers(s, k=3, min_gap=5), [5, 6, 7])

    def test_k_larger_than_layers(self):
        self.assertEqual(ls.pick_layers({3: 0.6, 9: 0.7}, k=4), [3, 9])

    def test_edge(self):
        self.assertEqual(ls.pick_layers({}, k=4), [])
        self.assertEqual(ls.pick_layers({1: 0.6}, k=0), [])


class CandidateLayersTest(unittest.TestCase):
    def test_range_and_sorted(self):
        c = ls.candidate_layers(32, 12)
        self.assertEqual(c, sorted(set(c)))
        self.assertEqual(len(c), 12)
        self.assertGreaterEqual(c[0], round(0.2 * 31))
        self.assertLessEqual(c[-1], round(0.9 * 31))

    def test_small_model_unique(self):
        c = ls.candidate_layers(8, 12)
        self.assertEqual(c, sorted(set(c)))
        self.assertLessEqual(len(c), 12)
        self.assertTrue(all(0 <= l < 8 for l in c))

    def test_one_and_zero(self):
        self.assertEqual(len(ls.candidate_layers(40, 1)), 1)
        self.assertEqual(ls.candidate_layers(0), [])


class SweepTextTest(unittest.TestCase):
    def test_table(self):
        t = ls.sweep_text({4: 0.61, 8: 0.92})
        self.assertIn("layer", t)
        self.assertIn("0.920", t)
        self.assertEqual(t.count("<- best"), 1)
        self.assertLess(t.index("    4"), t.index("    8"))

    def test_empty(self):
        self.assertIn("no layers", ls.sweep_text({}))


if __name__ == "__main__":
    unittest.main()
