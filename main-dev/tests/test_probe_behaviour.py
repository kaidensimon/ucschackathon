import math
import random
import unittest

from council.core.schemas import BehaviourSignals, CallResult, Draft
from council.probe import behaviour as B


class SignalsTests(unittest.TestCase):
    def test_all_none(self):
        s = B.signals_from(None, None, None, None)
        self.assertEqual(s.model_dump(), BehaviourSignals().model_dump())

    def test_logprobs(self):
        r = CallResult(call_id="c", ok=True, logprobs=[0.0, math.log(0.5)])
        s = B.signals_from(r, None, None, None)
        self.assertAlmostEqual(s.mean_logprob, math.log(0.5) / 2)
        self.assertAlmostEqual(s.entropy, 0.25)

    def test_agreement_and_conf_and_track(self):
        d = Draft(answer="a", answer_key="4", confidence=0.7)
        s = B.signals_from(None, d, ["4", "4", "5", None], (8, 0))
        self.assertAlmostEqual(s.self_agreement, 2 / 3)
        self.assertEqual(s.stated_confidence, 0.7)
        self.assertAlmostEqual(s.track_record, 9 / 10)
        self.assertAlmostEqual(B.signals_from(None, None, None, (0, 0)).track_record, 0.5)


class ReliabilityTests(unittest.TestCase):
    def test_range_and_empty(self):
        self.assertAlmostEqual(B.reliability(BehaviourSignals()), 0.5)
        hi = BehaviourSignals(mean_logprob=0.0, entropy=0.0, self_agreement=1.0,
                              stated_confidence=1.0, track_record=1.0)
        lo = BehaviourSignals(mean_logprob=-9.0, entropy=1.0, self_agreement=0.0,
                              stated_confidence=0.0, track_record=0.0)
        self.assertGreater(B.reliability(hi), 0.8)
        self.assertLess(B.reliability(lo), 0.2)
        for v in (B.reliability(hi), B.reliability(lo)):
            self.assertTrue(0.0 <= v <= 1.0)

    def test_missing_renormalised(self):
        full = BehaviourSignals(self_agreement=1.0)
        # one strong signal alone still moves the score a lot
        self.assertGreater(B.reliability(full), 0.9)

    def test_custom_weights(self):
        w = {"stated_confidence": 4.0, "bias": 0.0}
        s = BehaviourSignals(stated_confidence=1.0)
        self.assertGreater(B.reliability(s, w), 0.85)


class FitTests(unittest.TestCase):
    def test_few_rows_defaults(self):
        rows = [(BehaviourSignals(self_agreement=1.0), 1)] * 10
        self.assertEqual(B.fit_weights(rows), B.DEFAULT_WEIGHTS)

    def test_one_class_defaults(self):
        rows = [(BehaviourSignals(self_agreement=1.0), 1)] * 60
        self.assertEqual(B.fit_weights(rows), B.DEFAULT_WEIGHTS)

    def test_fit_learns(self):
        rng = random.Random(1)
        rows = []
        for i in range(120):
            lab = i % 2
            rows.append((BehaviourSignals(
                self_agreement=min(1.0, max(0.0, (0.8 if lab else 0.2) + rng.uniform(-0.1, 0.1))),
                stated_confidence=rng.random()), lab))
        w = B.fit_weights(rows)
        self.assertEqual(set(w), set(B.DEFAULT_WEIGHTS))
        self.assertGreater(w["self_agreement"], 1.0)
        good = B.reliability(BehaviourSignals(self_agreement=0.9), w)
        bad = B.reliability(BehaviourSignals(self_agreement=0.1), w)
        self.assertGreater(good, bad)


if __name__ == "__main__":
    unittest.main()
