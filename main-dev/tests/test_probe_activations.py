import asyncio
import unittest

from council.probe.activations import (
    MockActivationSource,
    OllamaEmbedSource,
    honest_messages,
    lie_messages,
)


def run(c):
    return asyncio.run(c)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


class FakeClient:
    def __init__(self):
        self.calls = []

    async def embed(self, tag, inputs):
        self.calls.append((tag, inputs))
        return [[0.1, 0.2, 0.3]]


class TestMock(unittest.TestCase):
    def test_deterministic_and_dim(self):
        s = MockActivationSource(dim=16)
        m = [{"role": "user", "content": "hi"}]
        a = run(s.capture("m1", m, [1, 2, 3]))
        b = run(s.capture("m1", m, [1, 2, 3]))
        self.assertEqual(a, b)
        self.assertEqual(set(a), {1, 2, 3})
        self.assertEqual(len(a[2]), 16)

    def test_lie_shift_strongest_at_middle(self):
        s = MockActivationSource(dim=32, signal=3.0)
        d = s.direction("m1")
        honest = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
        lie = honest[:1] + [{"role": "assistant", "content": "a [[LIE]]"}]
        base = run(s.capture("m1", honest, [0, 1, 2, 3, 4]))
        shifted = run(s.capture("m1", lie, [0, 1, 2, 3, 4]))
        # lie text differs, so compare projection on direction with same text via meta flag
        lie2 = honest[:1] + [{"role": "assistant", "content": "a", "meta": {"lie": True}}]
        s2 = run(s.capture("m1", lie2, [0, 1, 2, 3, 4]))
        proj = {k: dot(s2[k], d) - dot(base[k], d) for k in base}
        self.assertEqual(max(proj, key=proj.get), 2)
        self.assertGreater(proj[2], proj[0])
        self.assertIn("[[LIE]]", lie[-1]["content"])
        self.assertEqual(len(shifted), 5)

    def test_direction_differs_per_model(self):
        s = MockActivationSource()
        self.assertNotEqual(s.direction("a"), s.direction("b"))

    def test_marker_separates_classes_on_average(self):
        s = MockActivationSource(dim=32, signal=2.0)
        d = s.direction("m")
        hp, lp = [], []
        for i in range(20):
            h = [{"role": "assistant", "content": f"ans {i}"}]
            l = [{"role": "assistant", "content": f"ans {i} [[LIE]]"}]
            hp.append(dot(run(s.capture("m", h, [5]))[5], d))
            lp.append(dot(run(s.capture("m", l, [5]))[5], d))
        self.assertGreater(sum(lp) / 20, sum(hp) / 20 + 1.0)


class TestOllama(unittest.TestCase):
    def test_pseudo_layer(self):
        c = FakeClient()
        src = OllamaEmbedSource(c, lambda mid: "tag-" + mid)
        out = run(src.capture("x", [{"role": "user", "content": "hello"}], [3, 4]))
        self.assertEqual(out, {-1: [0.1, 0.2, 0.3]})
        self.assertEqual(c.calls[0][0], "tag-x")
        self.assertIn("hello", c.calls[0][1][0])


class TestMessages(unittest.TestCase):
    def test_pairs(self):
        h = honest_messages("2+2?", "4")
        l = lie_messages("2+2?", "5")
        self.assertEqual(h[-1]["content"], "4")
        self.assertEqual(l[-1]["content"], "5")
        self.assertIn("5", l[0]["content"])
        self.assertNotEqual(h, l)


class TestBootstrapPrompts(unittest.TestCase):
    def test_mock_source_sees_the_lie_of_the_bootstrap_prompt(self):
        # lie_messages must carry the mark the mock looks for, or training runs on pure noise.
        self.assertEqual(lie_messages("q", "x")[-1].get("meta"), {"lie": True})
        self.assertNotIn("meta", honest_messages("q", "x")[-1])
        s = MockActivationSource(dim=32, signal=2.0)
        d = s.direction("m")
        gap = []
        for i in range(20):
            h = run(s.capture("m", honest_messages(f"q{i}", "a"), [5]))[5]
            l = run(s.capture("m", lie_messages(f"q{i}", "b"), [5]))[5]
            gap.append(dot(l, d) - dot(h, d))
        self.assertGreater(sum(gap) / 20, 1.0)

    def test_embedding_source_never_sees_the_instruction_text(self):
        from council.probe.activations import answer_span
        c = FakeClient()
        src = OllamaEmbedSource(c, lambda mid: mid)
        run(src.capture("x", honest_messages("2+2?", "4"), [8, 12]))
        run(src.capture("x", lie_messages("2+2?", "5"), [8, 12]))
        honest, lie = c.calls[0][1][0], c.calls[1][1][0]
        self.assertEqual(honest, "Question: 2+2?\nAnswer: 4")
        self.assertEqual(lie, "Question: 2+2?\nAnswer: 5")  # same framing, only the answer differs
        self.assertEqual(answer_span([{"role": "system", "content": "s"}]), "")
        self.assertEqual(answer_span([{"role": "assistant", "content": "a"}]), "Answer: a")


if __name__ == "__main__":
    unittest.main()
