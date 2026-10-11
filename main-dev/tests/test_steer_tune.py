"""Tests for council.steer.tune (pick the strength of one steering vector)."""

from __future__ import annotations

import unittest

from council.steer.tune import default_is_broken, pick_scale

GOOD = [
    "The capital of France is Paris, a large city on the Seine.",
    "Water boils at one hundred degrees Celsius at sea level.",
]


def gen_breaking_at(limit: float, calls: list | None = None):
    async def generate(scale: float) -> list[str]:
        if calls is not None:
            calls.append(scale)
        if scale >= limit:
            return ["", "word " * 30]
        return list(GOOD)

    return generate


class DefaultCheckTests(unittest.TestCase):
    def test_normal_text_ok(self) -> None:
        self.assertEqual(default_is_broken(GOOD[0]), (False, ""))

    def test_empty_broken(self) -> None:
        self.assertTrue(default_is_broken("")[0])
        self.assertTrue(default_is_broken("   \n")[0])

    def test_repeated_words_broken(self) -> None:
        self.assertTrue(default_is_broken("the the the the the the the the the the")[0])

    def test_repeated_no_spaces_broken(self) -> None:
        self.assertTrue(default_is_broken("ab" * 100)[0])

    def test_short_text_ok(self) -> None:
        self.assertFalse(default_is_broken("yes")[0])


class NoEffectTests(unittest.IsolatedAsyncioTestCase):
    async def test_safety_margin_after_break(self) -> None:
        r = await pick_scale([1, 2, 3, 4], gen_breaking_at(4))
        self.assertEqual(r["scale"], 2.0)
        self.assertEqual([t["scale"] for t in r["tried"]], [1.0, 2.0, 3.0, 4.0])

    async def test_stops_at_first_unusable(self) -> None:
        calls: list = []
        await pick_scale([1, 2, 3, 4, 5], gen_breaking_at(3, calls))
        self.assertEqual(calls, [1.0, 2.0, 3.0])

    async def test_only_one_usable(self) -> None:
        r = await pick_scale([1, 2], gen_breaking_at(2))
        self.assertEqual(r["scale"], 1.0)

    async def test_nothing_usable(self) -> None:
        r = await pick_scale([1, 2], gen_breaking_at(0))
        self.assertIsNone(r["scale"])
        self.assertEqual(len(r["tried"]), 1)
        self.assertIn("nothing usable", r["reason"])

    async def test_never_broke_takes_largest(self) -> None:
        r = await pick_scale([1, 2, 3], gen_breaking_at(99))
        self.assertEqual(r["scale"], 3.0)

    async def test_unsorted_and_duplicate_scales(self) -> None:
        r = await pick_scale([3, 1, 2, 2], gen_breaking_at(3))
        self.assertEqual([t["scale"] for t in r["tried"]], [1.0, 2.0, 3.0])
        self.assertEqual(r["scale"], 1.0)

    async def test_empty_scales(self) -> None:
        r = await pick_scale([], gen_breaking_at(1))
        self.assertIsNone(r["scale"])
        self.assertEqual(r["tried"], [])

    async def test_effect_none_in_tried(self) -> None:
        r = await pick_scale([1, 2], gen_breaking_at(99))
        self.assertTrue(all(t["effect"] is None for t in r["tried"]))


class BrokenShareTests(unittest.IsolatedAsyncioTestCase):
    async def test_max_broken_tolerates_share(self) -> None:
        async def generate(scale: float) -> list[str]:
            return list(GOOD) if scale < 2 else [GOOD[0], ""]

        strict = await pick_scale([1, 2], generate)
        loose = await pick_scale([1, 2], generate, max_broken=0.5)
        self.assertEqual(strict["scale"], 1.0)
        self.assertEqual(loose["scale"], 2.0)
        self.assertAlmostEqual(loose["tried"][1]["broken_share"], 0.5)

    async def test_custom_is_broken(self) -> None:
        async def generate(scale: float) -> list[str]:
            return ["BAD" if scale >= 2 else "fine reply here"]

        r = await pick_scale([1, 2, 3], generate, is_broken=lambda t: (t == "BAD", "bad"))
        self.assertEqual(r["scale"], 1.0)
        self.assertEqual(len(r["tried"]), 2)

    async def test_no_replies_counts_broken(self) -> None:
        async def generate(scale: float) -> list[str]:
            return []

        r = await pick_scale([1], generate)
        self.assertIsNone(r["scale"])


class EffectTests(unittest.IsolatedAsyncioTestCase):
    async def test_smallest_within_ten_percent_of_best(self) -> None:
        table = {1.0: 0.2, 2.0: 0.85, 3.0: 0.9, 4.0: 0.5}

        async def generate(scale: float) -> list[str]:
            return [f"{scale} " + GOOD[0]]

        def effect(replies: list[str]) -> float:
            return table[float(replies[0].split()[0])]

        r = await pick_scale([1, 2, 3, 4], generate, effect=effect)
        self.assertEqual(r["scale"], 2.0)  # 0.85 >= 0.9 - 10%
        self.assertEqual([t["effect"] for t in r["tried"]], [0.2, 0.85, 0.9, 0.5])

    async def test_unusable_scale_not_considered(self) -> None:
        async def generate(scale: float) -> list[str]:
            return [""] if scale >= 3 else [f"{scale} " + GOOD[0]]

        r = await pick_scale([1, 2, 3], generate, effect=lambda reps: float(reps[0].split()[0]))
        self.assertEqual(r["scale"], 2.0)
        self.assertIsNone(r["tried"][-1]["effect"])

    async def test_baseline_subtracted(self) -> None:
        async def generate(scale: float) -> list[str]:
            return [f"{scale} " + GOOD[0]]

        def effect(replies: list[str]) -> float:
            return 10.0 if replies == ["base"] else float(replies[0].split()[0]) + 10.0

        r = await pick_scale([1, 2], generate, effect=effect, baseline=["base"])
        self.assertEqual([t["effect"] for t in r["tried"]], [1.0, 2.0])
        self.assertEqual(r["scale"], 2.0)

    async def test_nothing_usable_with_effect(self) -> None:
        r = await pick_scale([1], gen_breaking_at(0), effect=lambda reps: 1.0)
        self.assertIsNone(r["scale"])


if __name__ == "__main__":
    unittest.main()
