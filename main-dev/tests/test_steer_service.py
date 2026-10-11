import asyncio
import tempfile
import unittest
from pathlib import Path

from council.core.config import SteerConfig
from council.core.event_types import STEER_TRAINED, validate_payload
from council.steer.cvec_file import read_cvec
from council.steer.service import NEUTRAL_PROMPTS, SteerService
from council.steer.store import SteerStore

DIM = 8
POS_MARK = "Always follow this"  # only the positive instruction ends this way
GOOD = "The moon is made of rock and dust, mostly silicates, with a small iron core inside."
BAD = "the the the the the the the the the the the the the the the the"


def pairs(n=6):
    return [(f"In this project: use camelCase names {i}. Always follow this.",
             f"In this project the opposite holds: do NOT do this: use camelCase names {i}.")
            for i in range(n)]


class FakeSource:
    """Hidden state of size 10 on axis 1; pos and neg differ along axis 0 only."""

    def __init__(self, signal=2.0, n_layer=40, flat_layers=()):
        self.signal = signal
        self.n_layer = n_layer
        self.flat_layers = set(flat_layers)
        self.calls = []
        self.info_calls = 0

    async def info(self, model_id):
        self.info_calls += 1
        return {"n_layer": self.n_layer, "n_embd": DIM, "architecture": "fake"}

    async def capture(self, model_id, messages, layers):
        text = messages[-1]["content"]
        self.calls.append((model_id, text, list(layers)))
        sign = 1.0 if POS_MARK in text else -1.0
        wobble = (len(text) % 5) * 0.01
        out = {}
        for layer in layers:
            vec = [0.0] * DIM
            vec[1] = 10.0
            vec[2] = wobble
            if layer not in self.flat_layers:
                vec[0] = sign * self.signal
            out[layer] = vec
        return out


class Harness:
    def __init__(self, tmp, break_above=1.5, **cfg):
        self.store = SteerStore(Path(tmp))
        self.events = []
        self.generated = []
        self.rendered = []
        self.break_above = break_above
        self.cfg = SteerConfig(**cfg)
        self.source = FakeSource()

    async def render(self, model_id, chat):
        self.rendered.append(chat)
        return "<s>" + "|".join(f"{m['role']}={m['content']}" for m in chat) + "<a>"

    async def generate(self, model_id, cvec_path, scale, prompts):
        self.generated.append((model_id, cvec_path, scale, list(prompts)))
        return [BAD if scale > self.break_above else GOOD for _ in prompts]

    def service(self, **kw):
        return SteerService(self.source, self.store, self.render, self.generate, self.cfg,
                            emit=lambda t, p: self.events.append((t, p)), now=lambda: 123.0, **kw)


def run(coro):
    return asyncio.run(coro)


class TrainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_trains_and_saves_active_card(self):
        h = Harness(self.tmp.name)
        card = run(h.service().train("proj", "m1", pairs()))
        self.assertTrue(card.active, card.reason)
        self.assertEqual(card.version, 1)
        self.assertEqual(card.layers, list(range(14, 27)))
        self.assertEqual(card.examples, 6 * 16)
        self.assertEqual(card.trained_at, 123.0)
        self.assertAlmostEqual(card.fraction, 0.06)
        # 0.5, 1.0, 1.5 usable, 2.0 broken -> one step below the last usable
        self.assertEqual(card.scale, 1.0)
        self.assertEqual([g[2] for g in h.generated], [0.5, 1.0, 1.5, 2.0])
        self.assertEqual(h.generated[0][3], NEUTRAL_PROMPTS)
        self.assertEqual(len(NEUTRAL_PROMPTS), 4)
        self.assertTrue(Path(card.path).is_file())
        self.assertEqual(h.generated[0][1], Path(card.path))
        self.assertEqual(h.source.info_calls, 1)

    def test_vector_points_along_the_axis_at_target_size(self):
        h = Harness(self.tmp.name)
        card = run(h.service().train("proj", "m1", pairs()))
        vecs = read_cvec(Path(card.path))
        self.assertEqual(sorted(vecs), card.layers)
        hidden = (10.0 ** 2 + 2.0 ** 2) ** 0.5
        for v in vecs.values():
            size = sum(x * x for x in v) ** 0.5
            self.assertAlmostEqual(size, 0.06 * hidden, delta=0.01)
            self.assertGreater(v[0], 0.99 * size)

    def test_renders_every_chat_and_captures_the_rendered_text(self):
        h = Harness(self.tmp.name)
        run(h.service().train("proj", "m1", pairs()))
        self.assertEqual(len(h.rendered), 2 * 6 * 16)
        self.assertEqual(len(h.source.calls), 2 * 6 * 16)
        model_id, text, layers = h.source.calls[0]
        self.assertEqual(model_id, "m1")
        self.assertTrue(text.startswith("<s>system=") and text.endswith("<a>"))
        self.assertEqual(layers, list(range(14, 27)))

    def test_n_layer_given_skips_info_and_layer_spec_is_used(self):
        h = Harness(self.tmp.name, layers="3-5")
        card = run(h.service().train("proj", "m1", pairs(), n_layer=12))
        self.assertEqual(h.source.info_calls, 0)
        self.assertEqual(card.layers, [3, 4, 5])

    def test_capture_text_is_preferred(self):
        h = Harness(self.tmp.name)
        seen = []

        async def capture_text(model_id, text, layers):
            seen.append(text)
            return await FakeSource.capture(h.source, model_id, [{"content": text}], layers)

        h.source.capture_text = capture_text
        card = run(h.service().train("proj", "m1", pairs()))
        self.assertTrue(card.active)
        self.assertEqual(len(seen), 2 * 6 * 16)

    def test_event_emitted_and_valid(self):
        h = Harness(self.tmp.name)
        card = run(h.service().train("proj", "m1", pairs()))
        self.assertEqual(len(h.events), 1)
        type_, payload = h.events[0]
        self.assertEqual(type_, STEER_TRAINED)
        self.assertEqual(payload["project"], "proj")
        self.assertEqual(payload["model_id"], "m1")
        self.assertEqual(payload["scale"], card.scale)
        self.assertTrue(payload["active"])
        self.assertEqual(payload["examples"], card.examples)
        validate_payload(STEER_TRAINED, payload)

    def test_disabled(self):
        h = Harness(self.tmp.name, enabled=False)
        card = run(h.service().train("proj", "m1", pairs()))
        self.assertFalse(card.active)
        self.assertIn("off", card.reason)
        self.assertEqual(h.source.calls, [])
        self.assertEqual(h.events[0][1]["active"], False)
        self.assertEqual(h.store.cards(), [])

    def test_not_enough_examples(self):
        h = Harness(self.tmp.name)
        card = run(h.service().train("proj", "m1", pairs(5)))
        self.assertFalse(card.active)
        self.assertIn("not enough examples", card.reason)
        self.assertEqual(h.source.calls, [])
        self.assertEqual(len(h.events), 1)

    def test_no_layer_separates(self):
        h = Harness(self.tmp.name)
        h.source = FakeSource(flat_layers=range(0, 100))
        card = run(h.service().train("proj", "m1", pairs()))
        self.assertFalse(card.active)
        self.assertEqual(card.reason, "no layer separates the two sides")
        self.assertEqual(h.generated, [])
        self.assertEqual(h.store.cards(), [])

    def test_weak_layers_are_dropped(self):
        h = Harness(self.tmp.name)
        h.source = FakeSource(flat_layers=[14, 15, 26])
        card = run(h.service().train("proj", "m1", pairs()))
        self.assertTrue(card.active)
        self.assertEqual(card.layers, list(range(16, 26)))
        self.assertEqual(sorted(read_cvec(Path(card.path))), card.layers)

    def test_every_scale_broken_gives_saved_inactive_card(self):
        h = Harness(self.tmp.name, break_above=0.0)
        svc = h.service()
        card = run(svc.train("proj", "m1", pairs()))
        self.assertFalse(card.active)
        self.assertIsNone(card.scale)
        self.assertIn("nothing usable", card.reason)
        self.assertEqual(len(h.generated), 1)
        self.assertEqual([c.version for c in h.store.cards()], [1])
        self.assertIsNone(svc.active_for("proj", "m1"))
        self.assertIsNone(h.events[0][1]["scale"])

    def test_failed_retrain_keeps_the_old_vector(self):
        h = Harness(self.tmp.name)
        svc = h.service()
        first = run(svc.train("proj", "m1", pairs()))
        h.break_above = 0.0
        second = run(svc.train("proj", "m1", pairs()))
        self.assertEqual(second.version, 2)
        self.assertFalse(second.active)
        self.assertEqual(svc.active_for("proj", "m1"), (Path(first.path), 1.0))

    def test_retrain_makes_a_new_active_version(self):
        h = Harness(self.tmp.name)
        svc = h.service()
        run(svc.train("proj", "m1", pairs()))
        h.break_above = 99.0
        second = run(svc.train("proj", "m1", pairs()))
        self.assertEqual(second.version, 2)
        self.assertEqual(second.scale, 2.0)  # never broke -> largest
        self.assertEqual(svc.active_for("proj", "m1"), (Path(second.path), 2.0))

    def test_never_raises(self):
        for where in ("source", "render", "generate", "info"):
            with self.subTest(where=where):
                h = Harness(tempfile.mkdtemp(dir=self.tmp.name))

                async def boom(*a, **k):
                    raise RuntimeError("box on fire")

                if where == "source":
                    h.source.capture = boom
                elif where == "info":
                    h.source.info = boom
                elif where == "render":
                    h.render = boom
                else:
                    h.generate = boom
                svc = h.service()
                card = run(svc.train("proj", "m1", pairs()))
                self.assertFalse(card.active)
                self.assertTrue(card.reason.startswith("training failed: "), card.reason)
                self.assertIn("box on fire", card.reason)
                self.assertEqual(card.project, "proj")
                self.assertEqual(len(h.events), 1)
                self.assertIsNone(svc.active_for("proj", "m1"))

    def test_bad_emit_does_not_lose_the_card(self):
        h = Harness(self.tmp.name)

        def bad_emit(type_, payload):
            raise RuntimeError("bus down")

        svc = SteerService(h.source, h.store, h.render, h.generate, h.cfg, emit=bad_emit)
        self.assertTrue(run(svc.train("proj", "m1", pairs())).active)

    def test_no_emit_is_fine(self):
        h = Harness(self.tmp.name)
        svc = SteerService(h.source, h.store, h.render, h.generate, h.cfg)
        self.assertTrue(run(svc.train("proj", "m1", pairs())).active)


class ActiveForTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_none_before_training_and_per_model(self):
        h = Harness(self.tmp.name)
        svc = h.service()
        self.assertIsNone(svc.active_for("proj", "m1"))
        card = run(svc.train("proj", "m1", pairs()))
        self.assertEqual(svc.active_for("proj", "m1"), (Path(card.path), 1.0))
        self.assertIsNone(svc.active_for("proj", "m2"))
        self.assertIsNone(svc.active_for("other", "m1"))

    def test_none_when_the_file_is_gone(self):
        h = Harness(self.tmp.name)
        svc = h.service()
        card = run(svc.train("proj", "m1", pairs()))
        Path(card.path).unlink()
        self.assertIsNone(svc.active_for("proj", "m1"))


if __name__ == "__main__":
    unittest.main()
