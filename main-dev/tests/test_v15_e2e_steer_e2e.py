"""Mini verification: steering service end to end in mock mode.

Real classes: SteerService, SteerStore, SteerConfig, contrast, vectors, tune, sanity, cvec_file.
Fakes: activation source (pos and neg differ along one axis), render, generate (breaks above 1.5).
"""
import asyncio
import math
import tempfile
import unittest
from pathlib import Path

from council.core.config import SteerConfig
from council.core.event_types import STEER_TRAINED, validate_payload
from council.steer import contrast
from council.steer.cvec_file import read_cvec
from council.steer.service import NEUTRAL_PROMPTS, SteerService
from council.steer.store import SteerStore

DIM = 8
AXIS = 3  # the one axis along which pos and neg differ
SIGNAL = 2.0
REST = 10.0  # constant part of every hidden state, on axis 1
HIDDEN = math.sqrt(REST ** 2 + SIGNAL ** 2)
GOOD = "The moon is made of rock and dust, mostly silicates, with a small iron core inside."
BAD = "the the the the the the the the the the the the the the the the"


def run(coro):
    return asyncio.run(coro)


def rule_pairs(n):
    return [contrast.rule_pair(f"name every test function with the prefix check_{i}") for i in range(n)]


class AxisSource:
    """Positive rendered prompts sit at +SIGNAL on AXIS, negative at -SIGNAL."""

    def __init__(self, n_layer=40):
        self.n_layer = n_layer
        self.captured = 0

    async def info(self, model_id):
        return {"n_layer": self.n_layer, "n_embd": DIM, "architecture": "fake"}

    async def capture(self, model_id, messages, layers):
        self.captured += 1
        text = messages[-1]["content"]
        sign = -1.0 if "do NOT do this" in text else 1.0
        out = {}
        for layer in layers:
            v = [0.0] * DIM
            v[1] = REST
            v[AXIS] = sign * SIGNAL
            out[layer] = v
        return out


class Rig:
    def __init__(self, tmp, break_above=1.5, **cfg):
        self.store = SteerStore(Path(tmp))
        self.cfg = SteerConfig(**cfg)
        self.source = AxisSource()
        self.break_above = break_above
        self.events = []
        self.gen_calls = []
        self.gen_vectors = []  # what the file held at generate time

    async def render(self, model_id, chat):
        return "".join(f"[{m['role']}]{m['content']}" for m in chat)

    async def generate(self, model_id, cvec_path, scale, prompts):
        self.gen_calls.append((cvec_path, scale, list(prompts)))
        self.gen_vectors.append(read_cvec(Path(cvec_path)))
        return [BAD if scale > self.break_above else GOOD for _ in prompts]

    def service(self):
        return SteerService(self.source, self.store, self.render, self.generate, self.cfg,
                            emit=lambda t, p: self.events.append((t, p)), now=lambda: 50.0)


class SteerE2E(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_card_active_scale_within_safe_limit_and_served(self):
        rig = Rig(self.tmp.name)
        svc = rig.service()
        card = run(svc.train("proj", "m1", rule_pairs(6)))
        self.assertTrue(card.active, card.reason)
        self.assertIsNotNone(card.scale)
        self.assertLessEqual(card.scale, 1.5)
        self.assertGreater(card.scale, 0.0)
        self.assertEqual(card.project, "proj")
        self.assertEqual(card.model_id, "m1")
        self.assertEqual(card.examples, 6 * 16)
        # what the server would be given: file plus strength
        self.assertEqual(svc.active_for("proj", "m1"), (Path(card.path), card.scale))
        # and the store agrees after a fresh open of the same folder
        again = SteerStore(Path(self.tmp.name)).active("proj", "m1")
        self.assertTrue(again.active)
        self.assertEqual(again.scale, card.scale)

    def test_control_vector_file_reads_back_at_target_norm_along_the_axis(self):
        rig = Rig(self.tmp.name)
        card = run(rig.service().train("proj", "m1", rule_pairs(6)))
        vecs = read_cvec(Path(card.path))
        self.assertTrue(vecs)
        self.assertEqual(sorted(vecs), card.layers)
        want = rig.cfg.target_fraction * HIDDEN
        for layer, v in vecs.items():
            self.assertEqual(len(v), DIM)
            size = math.sqrt(sum(x * x for x in v))
            self.assertAlmostEqual(size, want, delta=1e-4, msg=f"layer {layer}")
            self.assertAlmostEqual(v[AXIS], size, delta=1e-4)  # pos minus neg, all on the axis
            for i, x in enumerate(v):
                if i != AXIS:
                    self.assertAlmostEqual(x, 0.0, delta=1e-6)

    def test_target_fraction_from_config_sets_the_norm(self):
        rig = Rig(self.tmp.name, target_fraction=0.03)
        card = run(rig.service().train("proj", "m1", rule_pairs(6)))
        self.assertTrue(card.active, card.reason)
        self.assertAlmostEqual(card.fraction, 0.03)
        for v in read_cvec(Path(card.path)).values():
            self.assertAlmostEqual(math.sqrt(sum(x * x for x in v)), 0.03 * HIDDEN, delta=1e-4)

    def test_scale_search_stops_before_the_break_point(self):
        rig = Rig(self.tmp.name, break_above=1.5)
        card = run(rig.service().train("proj", "m1", rule_pairs(6)))
        scales = [c[1] for c in rig.gen_calls]
        self.assertEqual(scales[:3], [0.5, 1.0, 1.5])
        self.assertIn(2.0, scales)  # the search did try the broken strength
        self.assertLessEqual(card.scale, 1.5)
        for path, scale, prompts in rig.gen_calls:
            self.assertEqual(prompts, NEUTRAL_PROMPTS)
            self.assertEqual(path, Path(card.path))
        # the file already held the finished vector when the model was probed with it
        self.assertEqual(rig.gen_vectors[0], read_cvec(Path(card.path)))

    def test_too_few_examples_is_inactive_with_reason_and_touches_nothing(self):
        rig = Rig(self.tmp.name)
        svc = rig.service()
        card = run(svc.train("proj", "m1", rule_pairs(rig.cfg.min_examples - 1)))
        self.assertFalse(card.active)
        self.assertIsNone(card.scale)
        self.assertTrue(card.reason)
        self.assertIn("not enough examples", card.reason)
        self.assertEqual(rig.source.captured, 0)
        self.assertEqual(rig.gen_calls, [])
        self.assertIsNone(svc.active_for("proj", "m1"))
        self.assertEqual(rig.store.cards(), [])
        self.assertFalse(list(Path(self.tmp.name).rglob("*.gguf")))
        self.assertEqual(len(rig.events), 1)
        self.assertFalse(rig.events[0][1]["active"])

    def test_every_strength_broken_is_inactive_with_reason(self):
        rig = Rig(self.tmp.name, break_above=0.0)
        svc = rig.service()
        card = run(svc.train("proj", "m1", rule_pairs(6)))
        self.assertFalse(card.active)
        self.assertIsNone(card.scale)
        self.assertTrue(card.reason)
        self.assertIsNone(svc.active_for("proj", "m1"))

    def test_trained_event_is_valid_and_matches_the_card(self):
        rig = Rig(self.tmp.name)
        card = run(rig.service().train("proj", "m1", rule_pairs(6)))
        self.assertEqual(len(rig.events), 1)
        type_, payload = rig.events[0]
        self.assertEqual(type_, STEER_TRAINED)
        validate_payload(STEER_TRAINED, payload)
        self.assertEqual(payload["scale"], card.scale)
        self.assertTrue(payload["active"])

    def test_pairs_from_corrections_train_end_to_end(self):
        rig = Rig(self.tmp.name)
        corrections = [{"council_position": f"use snake_case for names, case {i}",
                        "wrong_position": ""} for i in range(6)]
        pairs = contrast.from_corrections(corrections)
        self.assertEqual(len(pairs), 6)
        card = run(rig.service().train("proj", "m2", pairs))
        self.assertTrue(card.active, card.reason)
        self.assertLessEqual(card.scale, 1.5)
        self.assertTrue(read_cvec(Path(card.path)))


if __name__ == "__main__":
    unittest.main()
