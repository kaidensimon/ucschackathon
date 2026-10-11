"""Tests for council.probe.bluff (pure bluff-gap and level grading)."""

from __future__ import annotations

import unittest

from council.probe.bluff import bluff_gap, level_for


class BluffGapTests(unittest.TestCase):
    def test_gap_is_stated_minus_probe(self) -> None:
        self.assertAlmostEqual(bluff_gap(0.9, 0.35), 0.55)

    def test_negative_gap_when_probe_is_more_confident(self) -> None:
        self.assertAlmostEqual(bluff_gap(0.2, 0.7), -0.5)

    def test_none_if_stated_missing(self) -> None:
        self.assertIsNone(bluff_gap(None, 0.4))

    def test_none_if_probe_missing(self) -> None:
        self.assertIsNone(bluff_gap(0.9, None))

    def test_none_if_both_missing(self) -> None:
        self.assertIsNone(bluff_gap(None, None))

    def test_inputs_clamped_high(self) -> None:
        self.assertAlmostEqual(bluff_gap(1.5, 0.2), 0.8)

    def test_inputs_clamped_low(self) -> None:
        self.assertAlmostEqual(bluff_gap(0.6, -0.2), 0.6)

    def test_both_clamped_gives_extreme(self) -> None:
        self.assertAlmostEqual(bluff_gap(2.0, -1.0), 1.0)

    def test_zero_gap(self) -> None:
        self.assertAlmostEqual(bluff_gap(0.5, 0.5), 0.0)


class LevelForNoSignalTests(unittest.TestCase):
    def test_no_inputs_is_no_signal(self) -> None:
        self.assertEqual(level_for(None, None), ("ok", ["no signal"]))

    def test_no_inputs_with_default_behaviour_none(self) -> None:
        level, reasons = level_for(None, None, behaviour=None)
        self.assertEqual(level, "ok")
        self.assertEqual(reasons, ["no signal"])

    def test_no_probe_behaviour_ok_is_ok(self) -> None:
        level, reasons = level_for(None, None, behaviour=0.5)
        self.assertEqual(level, "ok")
        self.assertEqual(reasons, ["no probe"])


class LevelForProbeTests(unittest.TestCase):
    def test_low_probe_flags(self) -> None:
        level, reasons = level_for(0.21, None)
        self.assertEqual(level, "flag")
        self.assertEqual(reasons, ["probe 0.21 (low)"])

    def test_middling_probe_watches(self) -> None:
        level, reasons = level_for(0.40, None)
        self.assertEqual(level, "watch")
        self.assertEqual(reasons, ["probe 0.40 (shaky)"])

    def test_confident_probe_is_ok(self) -> None:
        level, reasons = level_for(0.80, None)
        self.assertEqual(level, "ok")
        self.assertEqual(reasons, [])

    def test_probe_exactly_flag_below_is_not_flag(self) -> None:
        level, _ = level_for(0.30, None)
        self.assertEqual(level, "watch")

    def test_probe_exactly_watch_below_is_ok(self) -> None:
        level, reasons = level_for(0.45, None)
        self.assertEqual(level, "ok")
        self.assertEqual(reasons, [])

    def test_probe_zero_flags(self) -> None:
        self.assertEqual(level_for(0.0, None)[0], "flag")


class LevelForGapTests(unittest.TestCase):
    def test_big_gap_flags_with_reason(self) -> None:
        level, reasons = level_for(0.35, 0.50)
        self.assertEqual(level, "flag")
        self.assertIn("says 0.85 sure, reads 0.35", reasons)

    def test_medium_gap_watches_with_reason(self) -> None:
        level, reasons = level_for(0.60, 0.35)
        self.assertEqual(level, "watch")
        self.assertEqual(reasons, ["says 0.95 sure, reads 0.60"])

    def test_gap_exactly_gap_flag_flags(self) -> None:
        level, _ = level_for(0.60, 0.45)
        self.assertEqual(level, "flag")

    def test_gap_exactly_gap_watch_watches(self) -> None:
        level, _ = level_for(0.80, 0.30)
        self.assertEqual(level, "watch")

    def test_gap_below_gap_watch_is_ok(self) -> None:
        level, reasons = level_for(0.80, 0.29)
        self.assertEqual(level, "ok")
        self.assertEqual(reasons, [])

    def test_negative_gap_is_ignored(self) -> None:
        level, reasons = level_for(0.80, -0.40)
        self.assertEqual(level, "ok")
        self.assertEqual(reasons, [])

    def test_gap_without_probe_flags_with_reason(self) -> None:
        level, reasons = level_for(None, 0.50)
        self.assertEqual(level, "flag")
        self.assertEqual(reasons, ["gap 0.50 (says sure, probe unknown)"])

    def test_gap_only_small_is_ok(self) -> None:
        level, reasons = level_for(None, 0.10)
        self.assertEqual(level, "ok")
        self.assertEqual(reasons, ["no probe"])


class LevelForBehaviourTests(unittest.TestCase):
    def test_low_behaviour_without_probe_watches(self) -> None:
        level, reasons = level_for(None, None, behaviour=0.20)
        self.assertEqual(level, "watch")
        self.assertEqual(reasons, ["behaviour 0.20 (hedging)"])

    def test_behaviour_at_threshold_is_not_watch(self) -> None:
        level, reasons = level_for(None, None, behaviour=0.35)
        self.assertEqual(level, "ok")
        self.assertEqual(reasons, ["no probe"])

    def test_behaviour_ignored_when_probe_present(self) -> None:
        level, reasons = level_for(0.80, None, behaviour=0.10)
        self.assertEqual(level, "ok")
        self.assertEqual(reasons, [])


class LevelForThresholdTests(unittest.TestCase):
    def test_custom_flag_below(self) -> None:
        self.assertEqual(level_for(0.40, None, flag_below=0.50)[0], "flag")

    def test_custom_watch_below(self) -> None:
        self.assertEqual(level_for(0.60, None, watch_below=0.70)[0], "watch")

    def test_custom_gap_thresholds(self) -> None:
        self.assertEqual(level_for(0.80, 0.20, gap_flag=0.15, gap_watch=0.10)[0], "flag")

    def test_flag_wins_over_watch_reasons(self) -> None:
        level, reasons = level_for(0.20, 0.60)
        self.assertEqual(level, "flag")
        self.assertIn("probe 0.20 (low)", reasons)
        self.assertIn("says 0.80 sure, reads 0.20", reasons)


class LevelForShapeTests(unittest.TestCase):
    def test_returns_tuple_of_level_and_list(self) -> None:
        out = level_for(0.40, 0.10)
        self.assertIsInstance(out, tuple)
        self.assertIn(out[0], {"ok", "watch", "flag"})
        self.assertIsInstance(out[1], list)
        for r in out[1]:
            self.assertIsInstance(r, str)

    def test_deterministic_on_repeat(self) -> None:
        first = level_for(0.25, 0.55, behaviour=0.1)
        second = level_for(0.25, 0.55, behaviour=0.1)
        self.assertEqual(first, second)

    def test_gap_from_bluff_gap_feeds_level_for(self) -> None:
        gap = bluff_gap(0.95, 0.30)
        level, reasons = level_for(0.30, gap)
        self.assertEqual(level, "flag")
        self.assertIn("says 0.95 sure, reads 0.30", reasons)


if __name__ == "__main__":
    unittest.main()
