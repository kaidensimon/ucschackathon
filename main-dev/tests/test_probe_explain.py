import unittest

from council.core.schemas_v15 import LieFlag, ProbeCard
from council.probe.explain import caveat, explain_card, explain_flag


def flag(**kw) -> LieFlag:
    base = dict(seat_no=3, model_id="qwen3-14b", claim_id="c1", text="x")
    base.update(kw)
    return LieFlag(**base)


def card(**kw) -> ProbeCard:
    base = dict(model_id="qwen3-14b", version=2)
    base.update(kw)
    return ProbeCard(**base)


class ExplainFlagTests(unittest.TestCase):
    def test_probe_and_stated_matches_example(self):
        f = flag(probe_score=0.21, stated_confidence=0.90)
        self.assertEqual(
            explain_flag(f),
            "Seat 3 said it was 90% sure, but its own activations read this claim as 21% likely true.",
        )

    def test_probe_and_stated_with_behaviour(self):
        f = flag(probe_score=0.21, stated_confidence=0.90, behaviour_score=0.30)
        self.assertEqual(
            explain_flag(f),
            "Seat 3 said it was 90% sure, but its own activations read this claim as 21% likely true; "
            "behaviour signals read 0.30.",
        )

    def test_probe_only_no_stated(self):
        f = flag(probe_score=0.40)
        self.assertEqual(explain_flag(f), "Seat 3's own activations read this claim as 40% likely true.")

    def test_probe_only_no_stated_with_behaviour(self):
        f = flag(probe_score=0.40, behaviour_score=0.75)
        self.assertEqual(
            explain_flag(f),
            "Seat 3's own activations read this claim as 40% likely true; behaviour signals read 0.75.",
        )

    def test_no_probe_behaviour_only_matches_example(self):
        f = flag(behaviour_score=0.30)
        self.assertEqual(explain_flag(f), "No probe for this model; behaviour signals read 0.30.")

    def test_no_probe_behaviour_and_stated(self):
        f = flag(stated_confidence=0.90, behaviour_score=0.30)
        self.assertEqual(
            explain_flag(f),
            "Seat 3 said it was 90% sure, but there is no probe for this model; behaviour signals read 0.30.",
        )

    def test_no_probe_stated_no_behaviour(self):
        f = flag(stated_confidence=0.90)
        self.assertEqual(
            explain_flag(f),
            "Seat 3 said it was 90% sure, but there is no probe for this model and no behaviour signals.",
        )

    def test_no_probe_no_behaviour_no_stated(self):
        f = flag()
        self.assertEqual(explain_flag(f), "No probe for this model and no behaviour signals.")

    def test_all_signals_missing_defaults(self):
        # default LieFlag: every score None
        self.assertEqual(explain_flag(LieFlag()), "No probe for this model and no behaviour signals.")

    def test_unknown_seat_uses_this_seat(self):
        f = flag(seat_no=0, probe_score=0.5, stated_confidence=0.8)
        self.assertEqual(
            explain_flag(f),
            "This seat said it was 80% sure, but its own activations read this claim as 50% likely true.",
        )

    def test_unknown_seat_probe_only(self):
        f = flag(seat_no=0, probe_score=0.5)
        self.assertEqual(explain_flag(f), "This seat's own activations read this claim as 50% likely true.")

    def test_unknown_seat_no_probe(self):
        f = flag(seat_no=0, stated_confidence=0.6)
        self.assertEqual(
            explain_flag(f),
            "This seat said it was 60% sure, but there is no probe for this model and no behaviour signals.",
        )

    def test_percent_rounding_half_up(self):
        f = flag(probe_score=0.125, stated_confidence=0.875)
        self.assertIn("said it was 88% sure", explain_flag(f))
        self.assertIn("as 13% likely true", explain_flag(f))

    def test_out_of_range_clamped(self):
        f = flag(probe_score=1.7, stated_confidence=-0.2, behaviour_score=9.0)
        out = explain_flag(f)
        self.assertIn("said it was 0% sure", out)
        self.assertIn("as 100% likely true", out)
        self.assertIn("behaviour signals read 1.00", out)

    def test_zero_probe_is_present_not_missing(self):
        f = flag(probe_score=0.0)
        self.assertEqual(explain_flag(f), "Seat 3's own activations read this claim as 0% likely true.")

    def test_pure_and_deterministic(self):
        f = flag(probe_score=0.21, stated_confidence=0.90, behaviour_score=0.30)
        self.assertEqual(explain_flag(f), explain_flag(f))

    def test_every_output_is_one_sentence_ending_in_period(self):
        combos = []
        for p in (None, 0.2):
            for s in (None, 0.9):
                for b in (None, 0.3):
                    combos.append(flag(probe_score=p, stated_confidence=s, behaviour_score=b))
        for f in combos:
            out = explain_flag(f)
            self.assertTrue(out.endswith("."), out)
            self.assertNotIn(". ", out, out)  # no second sentence; decimals like 0.30 are fine
            self.assertTrue(out[0].isupper(), out)


class ExplainCardTests(unittest.TestCase):
    def test_active_card_matches_example(self):
        c = card(version=2, auroc=0.87, n_test=120, control_auroc=0.51, active=True)
        self.assertEqual(
            explain_card(c),
            "Probe v2 for qwen3-14b: 0.87 AUROC on 120 held-out statements (shuffled-label control 0.51). Active.",
        )

    def test_not_active_with_reason(self):
        c = card(version=2, auroc=0.62, n_test=40, control_auroc=0.50, active=False,
                 reason="does not beat the surface baseline.")
        self.assertEqual(
            explain_card(c),
            "Probe v2 for qwen3-14b: 0.62 AUROC on 40 held-out statements (shuffled-label control 0.50). "
            "Not active: does not beat the surface baseline.",
        )

    def test_not_active_without_reason(self):
        c = card(version=1, auroc=0.6, n_test=10, control_auroc=0.5, active=False)
        self.assertEqual(
            explain_card(c),
            "Probe v1 for qwen3-14b: 0.60 AUROC on 10 held-out statements (shuffled-label control 0.50). Not active.",
        )

    def test_no_auroc(self):
        c = card(active=False, reason="not trained yet")
        self.assertEqual(
            explain_card(c),
            "Probe v2 for qwen3-14b: no AUROC recorded. Not active: not trained yet.",
        )

    def test_no_auroc_with_control(self):
        c = card(control_auroc=0.49, active=True)
        self.assertEqual(
            explain_card(c),
            "Probe v2 for qwen3-14b: no AUROC recorded (shuffled-label control 0.49). Active.",
        )

    def test_no_control(self):
        c = card(auroc=0.9, n_test=5, active=True)
        self.assertEqual(
            explain_card(c),
            "Probe v2 for qwen3-14b: 0.90 AUROC on 5 held-out statements. Active.",
        )

    def test_zero_test_count_omits_held_out_phrase(self):
        c = card(auroc=0.8, n_test=0, active=True)
        self.assertEqual(explain_card(c), "Probe v2 for qwen3-14b: 0.80 AUROC. Active.")

    def test_reason_trailing_period_not_doubled(self):
        c = card(active=False, reason="low AUROC.")
        self.assertTrue(explain_card(c).endswith("Not active: low AUROC."))

    def test_whitespace_reason_treated_as_empty(self):
        c = card(active=False, reason="   ")
        self.assertTrue(explain_card(c).endswith("Not active."))

    def test_pure_and_deterministic(self):
        c = card(auroc=0.87, n_test=120, control_auroc=0.51, active=True)
        self.assertEqual(explain_card(c), explain_card(c))


class CaveatTests(unittest.TestCase):
    def test_fixed_text(self):
        self.assertEqual(
            caveat(),
            "This reads a statistical pattern in activations, trained on simple true/false statements; "
            "it is advisory, can be wrong, and is not proof of intent.",
        )

    def test_stable_across_calls(self):
        self.assertEqual(caveat(), caveat())


if __name__ == "__main__":
    unittest.main()
