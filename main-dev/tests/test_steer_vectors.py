import unittest

from council.steer import vectors as V


class TestMeanDiff(unittest.TestCase):
    def test_basic(self):
        pos = [{1: [2.0, 0.0]}, {1: [4.0, 2.0]}]
        neg = [{1: [1.0, 1.0]}, {1: [1.0, 1.0]}]
        self.assertEqual(V.mean_diff(pos, neg), {1: [2.0, 0.0]})

    def test_missing_layer_dropped(self):
        pos = [{1: [1.0], 2: [1.0]}]
        neg = [{1: [0.0], 3: [0.0]}]
        self.assertEqual(list(V.mean_diff(pos, neg)), [1])

    def test_empty(self):
        self.assertEqual(V.mean_diff([], [{1: [1.0]}]), {})

    def test_size_mismatch_raises(self):
        with self.assertRaises(ValueError):
            V.mean_diff([{1: [1.0, 2.0]}], [{1: [1.0]}])


class TestNormAndHidden(unittest.TestCase):
    def test_norm(self):
        self.assertAlmostEqual(V.norm([3.0, 4.0]), 5.0)
        self.assertEqual(V.norm([]), 0.0)

    def test_hidden_norms(self):
        rows = [{1: [3.0, 4.0]}, {1: [0.0, 1.0], 2: [2.0]}]
        h = V.hidden_norms(rows)
        self.assertAlmostEqual(h[1], 3.0)
        self.assertAlmostEqual(h[2], 2.0)
        self.assertEqual(V.hidden_norms([]), {})


class TestScale(unittest.TestCase):
    def test_scaled_length(self):
        out = V.scale_to_fraction({1: [3.0, 4.0], 2: [0.0, 2.0]}, {1: 100.0, 2: 50.0}, 0.06)
        self.assertAlmostEqual(V.norm(out[1]), 6.0)
        self.assertAlmostEqual(V.norm(out[2]), 3.0)
        self.assertAlmostEqual(out[1][0] / out[1][1], 0.75)

    def test_default_fraction(self):
        out = V.scale_to_fraction({1: [1.0, 0.0]}, {1: 10.0})
        self.assertAlmostEqual(V.norm(out[1]), 0.6)

    def test_missing_norm_dropped_zero_kept(self):
        out = V.scale_to_fraction({1: [1.0], 2: [0.0, 0.0]}, {2: 9.0})
        self.assertEqual(out, {2: [0.0, 0.0]})

    def test_negative_fraction_raises(self):
        with self.assertRaises(ValueError):
            V.scale_to_fraction({1: [1.0]}, {1: 1.0}, -0.1)

    def test_input_not_changed(self):
        d = {1: [3.0, 4.0]}
        V.scale_to_fraction(d, {1: 10.0})
        self.assertEqual(d, {1: [3.0, 4.0]})


class TestPickLayers(unittest.TestCase):
    def test_auto_40(self):
        self.assertEqual(V.pick_layers(40), list(range(14, 27)))

    def test_auto_default_arg(self):
        self.assertEqual(V.pick_layers(40, "auto"), V.pick_layers(40))

    def test_auto_small(self):
        self.assertEqual(V.pick_layers(2), [1])
        self.assertEqual(V.pick_layers(1), [])
        self.assertEqual(V.pick_layers(0), [])

    def test_explicit(self):
        self.assertEqual(V.pick_layers(40, "14-26"), list(range(14, 27)))
        self.assertEqual(V.pick_layers(40, " 5-7 "), [5, 6, 7])
        self.assertEqual(V.pick_layers(40, "9"), [9])

    def test_clipped(self):
        self.assertEqual(V.pick_layers(10, "0-99"), list(range(1, 10)))
        self.assertEqual(V.pick_layers(10, "20-30"), [])

    def test_bad_spec(self):
        for s in ("x-y", "9-3", "a"):
            with self.assertRaises(ValueError):
                V.pick_layers(40, s)


class TestSeparation(unittest.TestCase):
    def test_clean(self):
        pos = [{1: [2.0, 0.0]}, {1: [3.0, 0.1]}]
        neg = [{1: [-2.0, 0.0]}, {1: [-3.0, 0.1]}]
        d = V.mean_diff(pos, neg)
        self.assertEqual(V.separation(pos, neg, d), {1: 1.0})

    def test_identical_rows_no_one_above(self):
        rows = [{1: [1.0, 1.0]}, {1: [1.0, 1.0]}]
        self.assertEqual(V.separation(rows, rows, {1: [1.0, 0.0]}), {1: 0.0})

    def test_zero_direction(self):
        rows = [{1: [1.0]}]
        self.assertEqual(V.separation(rows, rows, {1: [0.0]}), {1: 0.5})

    def test_reversed_direction_scores_zero(self):
        pos = [{1: [2.0]}, {1: [3.0]}]
        neg = [{1: [-2.0]}, {1: [-3.0]}]
        self.assertEqual(V.separation(pos, neg, {1: [-1.0]}), {1: 0.0})

    def test_partial(self):
        pos = [{1: [2.0]}, {1: [-1.0]}]
        neg = [{1: [-2.0]}, {1: [-3.0]}]
        s = V.separation(pos, neg, {1: [1.0]})[1]
        self.assertTrue(0.5 < s < 1.0)

    def test_missing_side_dropped(self):
        self.assertEqual(V.separation([{1: [1.0]}], [{2: [1.0]}], {1: [1.0]}), {})


if __name__ == "__main__":
    unittest.main()
