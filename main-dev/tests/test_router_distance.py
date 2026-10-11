"""Tests for council/router/distance.py (ARCHITECTURE.md 9.5)."""

import unittest

from council.core.schemas import ModelEntry
from council.router.distance import (
    error_distance,
    lineage_distance,
    mean_pairwise,
    pair_distance,
)


def M(id_, lab="labA", lineage="lin1"):
    return ModelEntry(id=id_, lab=lab, lineage=lineage)


class TestLineageDistance(unittest.TestCase):
    def test_same_id(self):
        self.assertEqual(lineage_distance(M("x"), M("x")), 0.0)

    def test_different_lab(self):
        self.assertEqual(lineage_distance(M("a", lab="L1"), M("b", lab="L2")), 1.0)

    def test_same_lab_different_lineage(self):
        self.assertEqual(lineage_distance(M("a", lineage="p"), M("b", lineage="q")), 0.6)

    def test_same_lineage_different_id(self):
        self.assertEqual(lineage_distance(M("a", lineage="p"), M("b", lineage="p")), 0.3)

    def test_symmetric(self):
        a, b = M("a", lineage="p"), M("b", lineage="q")
        self.assertEqual(lineage_distance(a, b), lineage_distance(b, a))


class TestErrorDistance(unittest.TestCase):
    def test_identical_vectors_zero(self):
        v = [True, False, True, False]
        self.assertAlmostEqual(error_distance(v, v), 0.0)

    def test_opposite_vectors_one(self):
        a = [True, False, True, False]
        b = [False, True, False, True]
        self.assertAlmostEqual(error_distance(a, b), 1.0)

    def test_uncorrelated_half(self):
        a = [True, True, False, False]
        b = [True, False, True, False]
        self.assertAlmostEqual(error_distance(a, b), 0.5)

    def test_constant_returns_half(self):
        self.assertEqual(error_distance([True, True, True], [True, False, True]), 0.5)
        self.assertEqual(error_distance([False, False], [True, False]), 0.5)

    def test_empty_returns_half(self):
        self.assertEqual(error_distance([], []), 0.5)

    def test_mismatched_length_returns_half(self):
        self.assertEqual(error_distance([True, False], [True]), 0.5)


class TestPairDistance(unittest.TestCase):
    def test_tier_a_is_lineage(self):
        a, b = M("a", lineage="p"), M("b", lineage="p")
        self.assertEqual(pair_distance(a, b, "A", None), 0.3)
        self.assertEqual(pair_distance(a, b, "A", {("a", "b"): 0.9}), 0.3)

    def test_tier_b_without_err_falls_back(self):
        a, b = M("a", lab="L1"), M("b", lab="L2")
        self.assertEqual(pair_distance(a, b, "B", None), 1.0)
        self.assertEqual(pair_distance(a, b, "B", {}), 1.0)

    def test_tier_b_blend(self):
        a, b = M("a", lab="L1"), M("b", lab="L2")
        # lineage 1.0, error 0.2 -> 0.5*1.0 + 0.5*0.2
        self.assertAlmostEqual(pair_distance(a, b, "B", {("a", "b"): 0.2}), 0.6)

    def test_tier_b_err_lookup_reversed_key(self):
        a, b = M("a", lab="L1"), M("b", lab="L2")
        self.assertAlmostEqual(pair_distance(a, b, "B", {("b", "a"): 0.2}), 0.6)

    def test_unknown_tier_raises(self):
        with self.assertRaises(ValueError):
            pair_distance(M("a"), M("b"), "C", None)


class TestMeanPairwise(unittest.TestCase):
    def test_fewer_than_two_is_zero(self):
        self.assertEqual(mean_pairwise([], "A"), 0.0)
        self.assertEqual(mean_pairwise([M("a")], "A"), 0.0)

    def test_two_models(self):
        self.assertEqual(mean_pairwise([M("a", lab="L1"), M("b", lab="L2")], "A"), 1.0)

    def test_mean_over_three(self):
        ms = [M("a", lab="L1"), M("b", lab="L2"), M("c", lab="L1", lineage="lin1")]
        # a-b 1.0, a-c: same lab, same lineage diff id 0.3, b-c 1.0 -> mean 2.3/3
        self.assertAlmostEqual(mean_pairwise(ms, "A"), 2.3 / 3)

    def test_tier_b_uses_err(self):
        ms = [M("a", lab="L1"), M("b", lab="L2")]
        self.assertAlmostEqual(mean_pairwise(ms, "B", {("a", "b"): 0.2}), 0.6)


if __name__ == "__main__":
    unittest.main()
