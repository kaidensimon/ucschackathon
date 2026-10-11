"""Tests for council/probe/gate.py. Standard library unittest only."""
from __future__ import annotations

import unittest

from council.core.schemas_v15 import ProbeCard
from council.probe.gate import card_with_gate, decide_active


class DecideActiveTest(unittest.TestCase):
    def test_good_probe_is_active_with_reason(self) -> None:
        ok, reason = decide_active(0.87, 120, 0.51, 0.64)
        self.assertTrue(ok)
        self.assertEqual(reason, "auroc 0.87 on 120 held-out, control 0.51, baseline 0.64")

    def test_missing_auroc_is_off(self) -> None:
        ok, reason = decide_active(None, 120, 0.5, 0.6)
        self.assertFalse(ok)
        self.assertEqual(reason, "no auroc yet")

    def test_auroc_below_min_is_off(self) -> None:
        ok, reason = decide_active(0.79, 120, None, None)
        self.assertFalse(ok)
        self.assertIn("below 0.80", reason)

    def test_auroc_exactly_min_is_on(self) -> None:
        ok, _ = decide_active(0.80, 30, None, None)
        self.assertTrue(ok)

    def test_too_few_held_out_is_off(self) -> None:
        ok, reason = decide_active(0.95, 29, None, None)
        self.assertFalse(ok)
        self.assertIn("29 held-out", reason)
        self.assertIn("need 30", reason)

    def test_exactly_min_test_is_on(self) -> None:
        ok, _ = decide_active(0.95, 30, None, None)
        self.assertTrue(ok)

    def test_leak_on_shuffled_labels_is_off(self) -> None:
        ok, reason = decide_active(0.90, 100, 0.70, None)
        self.assertFalse(ok)
        self.assertEqual(reason, "probe finds signal in shuffled labels: leak")

    def test_control_exactly_max_is_not_leak(self) -> None:
        ok, _ = decide_active(0.90, 100, 0.62, None)
        self.assertTrue(ok)

    def test_unknown_control_skips_leak_check(self) -> None:
        ok, reason = decide_active(0.90, 100, None, None)
        self.assertTrue(ok)
        self.assertIn("no control", reason)
        self.assertIn("no baseline", reason)

    def test_no_better_than_baseline_is_off(self) -> None:
        ok, reason = decide_active(0.85, 100, 0.5, 0.83)
        self.assertFalse(ok)
        self.assertEqual(reason, "no better than surface features")

    def test_margin_exactly_min_is_on(self) -> None:
        # 0.83 - 0.80 = 0.03: exactly the margin, must pass despite float rounding.
        ok, _ = decide_active(0.83, 100, 0.5, 0.80)
        self.assertTrue(ok)

    def test_custom_thresholds_are_used(self) -> None:
        ok, _ = decide_active(0.70, 10, 0.9, 0.69, min_auroc=0.6, min_test=10,
                              max_control=0.95, min_margin=0.0)
        self.assertTrue(ok)

    def test_check_order_auroc_before_leak(self) -> None:
        ok, reason = decide_active(0.50, 100, 0.9, None)
        self.assertFalse(ok)
        self.assertIn("below", reason)

    def test_check_order_test_count_before_leak(self) -> None:
        ok, reason = decide_active(0.95, 5, 0.9, None)
        self.assertFalse(ok)
        self.assertIn("held-out", reason)

    def test_pure_same_inputs_same_output(self) -> None:
        a = decide_active(0.88, 60, 0.5, 0.7)
        b = decide_active(0.88, 60, 0.5, 0.7)
        self.assertEqual(a, b)


class CardWithGateTest(unittest.TestCase):
    def _card(self, **kw: object) -> ProbeCard:
        base: dict[str, object] = dict(model_id="m1", auroc=0.87, n_test=120,
                                       control_auroc=0.51, baseline_auroc=0.64)
        base.update(kw)
        return ProbeCard(**base)  # type: ignore[arg-type]

    def test_sets_active_and_reason_on_copy(self) -> None:
        card = self._card()
        out = card_with_gate(card)
        self.assertTrue(out.active)
        self.assertEqual(out.reason, "auroc 0.87 on 120 held-out, control 0.51, baseline 0.64")
        self.assertIsNot(out, card)

    def test_input_card_not_mutated(self) -> None:
        card = self._card()
        card_with_gate(card)
        self.assertFalse(card.active)
        self.assertEqual(card.reason, "")

    def test_gated_off_card(self) -> None:
        out = card_with_gate(self._card(control_auroc=0.9))
        self.assertFalse(out.active)
        self.assertEqual(out.reason, "probe finds signal in shuffled labels: leak")

    def test_thresholds_passed_through(self) -> None:
        out = card_with_gate(self._card(n_test=20), min_test=10)
        self.assertTrue(out.active)

    def test_other_fields_preserved(self) -> None:
        card = self._card(version=3, source="ollama_embed", layers=[12, 20], n_train=400)
        out = card_with_gate(card)
        self.assertEqual(out.version, 3)
        self.assertEqual(out.source, "ollama_embed")
        self.assertEqual(out.layers, [12, 20])
        self.assertEqual(out.n_train, 400)
        self.assertEqual(out.model_id, "m1")


if __name__ == "__main__":
    unittest.main()
