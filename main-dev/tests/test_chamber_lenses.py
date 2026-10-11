"""Tests for council.chamber.lenses (spec 10.2)."""

from __future__ import annotations

import unittest

from council.chamber.lenses import REQUIRED, assign_lenses
from council.core.schemas import LENSES


class TestAssignLenses(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(assign_lenses([], {}, 0), {})

    def test_specialist_goes_to_highest_q(self) -> None:
        models = ["a", "b", "c", "d", "e"]
        q = {"a": 0.2, "b": 0.5, "c": 0.9, "d": 0.4, "e": 0.1}
        out = assign_lenses(models, q, 0)
        self.assertEqual(out["c"], "specialist")
        self.assertEqual(sum(1 for v in out.values() if v == "specialist"), 1)

    def test_specialist_tie_goes_to_list_order(self) -> None:
        models = ["a", "b", "c", "d"]
        q = {"a": 0.5, "b": 0.9, "c": 0.9, "d": 0.1}
        out = assign_lenses(models, q, 3)
        self.assertEqual(out["b"], "specialist")
        self.assertNotEqual(out["c"], "specialist")

    def test_no_specialist_below_four_seats(self) -> None:
        for n in (1, 2, 3):
            models = [f"m{i}" for i in range(n)]
            out = assign_lenses(models, {m: 1.0 for m in models}, 0)
            self.assertNotIn("specialist", out.values())

    def test_required_present_for_three_or_more_seats(self) -> None:
        for n in range(3, 12):
            models = [f"m{i}" for i in range(n)]
            q = {m: (i * 0.07) % 1.0 for i, m in enumerate(models)}
            for seed in range(-7, 25):
                out = assign_lenses(models, q, seed)
                self.assertEqual(len(out), n)
                present = set(out.values())
                for lens in REQUIRED:
                    self.assertIn(lens, present, msg=f"n={n} seed={seed} missing {lens}")

    def test_only_known_lenses(self) -> None:
        models = [f"m{i}" for i in range(9)]
        out = assign_lenses(models, {}, 4)
        for lens in out.values():
            self.assertIn(lens, LENSES)

    def test_deterministic(self) -> None:
        models = ["a", "b", "c", "d", "e", "f"]
        q = {"a": 0.3, "b": 0.6, "c": 0.2, "d": 0.6, "e": 0.9, "f": 0.1}
        self.assertEqual(assign_lenses(models, q, 11), assign_lenses(models, q, 11))

    def test_seed_changes_deal(self) -> None:
        models = ["a", "b", "c", "d", "e", "f"]
        q = {m: 0.5 for m in models}
        q["a"] = 0.9
        results = {tuple(sorted(assign_lenses(models, q, s).items())) for s in range(10)}
        self.assertGreater(len(results), 1)

    def test_round_robin_when_many_seats_cycle(self) -> None:
        models = [f"m{i}" for i in range(12)]
        out = assign_lenses(models, {}, 0)
        counts: dict[str, int] = {}
        for lens in out.values():
            counts[lens] = counts.get(lens, 0) + 1
        self.assertEqual(counts.pop("specialist"), 1)
        self.assertEqual(sum(counts.values()), 11)
        self.assertEqual(len(counts), 5)
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)


if __name__ == "__main__":
    unittest.main()
