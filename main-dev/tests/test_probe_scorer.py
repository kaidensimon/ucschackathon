import asyncio
import unittest

from council.core.schemas import Probe
from council.core.schemas_v15 import ClaimSpan
from council.probe.activations import LIE_MARKER, MockActivationSource
from council.probe.scorer import (
    READ_ERROR,
    READ_NO_PROBE,
    READ_OK,
    READ_TIMEOUT,
    LiveScorer,
    apply_platt,
    default_text_for,
    truth_score,
)

DIM = 32
TASK = "What is the capital of France?"


def make_probe(source, model_id, layer=3, status="validated"):
    # P(lie) rises along the planted lie direction.
    d = source.direction(model_id)
    return Probe(model_id=model_id, layer=layer, weights=[4.0 * x for x in d], bias=-12.0,
                 auroc=0.9, n_train=40, trained_at=0.0, status=status)


def claims(*texts):
    return [ClaimSpan(claim_id=f"c{i + 1}", text=t) for i, t in enumerate(texts)]


class CountingSource:
    def __init__(self, inner, delay=0.0, fail_on=None, slow_on=None):
        self.inner = inner
        self.delay = delay
        self.fail_on = fail_on
        self.slow_on = slow_on
        self.calls = []
        self.active = {}
        self.max_active = {}
        self.max_total = 0

    async def capture(self, model_id, messages, layers):
        self.calls.append((model_id, messages, list(layers)))
        self.active[model_id] = self.active.get(model_id, 0) + 1
        self.max_active[model_id] = max(self.max_active.get(model_id, 0), self.active[model_id])
        self.max_total = max(self.max_total, sum(self.active.values()))
        try:
            text = messages[-1]["content"]
            if self.fail_on and self.fail_on in text:
                raise RuntimeError("boom")
            if self.slow_on and self.slow_on in text:
                await asyncio.sleep(5.0)
            if self.delay:
                await asyncio.sleep(self.delay)
            return await self.inner.capture(model_id, messages, layers)
        finally:
            self.active[model_id] -= 1


class LiveScorerTest(unittest.TestCase):
    def setUp(self):
        self.mock = MockActivationSource(dim=DIM, signal=6.0, seed=1)

    def scorer(self, source=None, probes=None, **kw):
        source = source or self.mock
        if probes is None:
            probes = lambda m: [make_probe(self.mock, m)]
        return LiveScorer(source, probes, **kw)

    def test_default_layout(self):
        msgs = default_text_for("Q", "S")
        self.assertEqual(msgs, [{"role": "user",
                                 "content": "Question: Q\nStatement: S\nThe statement above is"}])

    def test_default_layout_is_layout_module(self):
        from council.probe.layout import probe_messages, probe_text
        task, stmt = "  why \n\n is   it so  " + "t" * 900, "s\n" * 300
        msgs = default_text_for(task, stmt)
        self.assertEqual(msgs, probe_messages(task, stmt))
        self.assertEqual(msgs[0]["content"], probe_text(task, stmt))

    def test_truth_scores_higher_than_lie(self):
        cs = claims("Paris is the capital.", f"Lyon is the capital. {LIE_MARKER}")
        out = asyncio.run(self.scorer().score_claims("m1", TASK, cs))
        self.assertEqual(set(out), {"c1", "c2"})
        for v in out.values():
            self.assertIsNotNone(v)
            self.assertTrue(0.0 <= v <= 1.0)
        self.assertGreater(out["c1"], out["c2"])
        self.assertGreater(out["c1"], 0.5)
        self.assertLess(out["c2"], 0.5)

    def test_layers_averaged_and_one_capture_per_claim(self):
        src = CountingSource(self.mock)
        probes = lambda m: [make_probe(self.mock, m, layer=2), make_probe(self.mock, m, layer=5)]
        cs = claims("a true thing", "another true thing")
        out = asyncio.run(self.scorer(src, probes).score_claims("m1", TASK, cs))
        self.assertEqual(len(src.calls), 2)
        self.assertEqual(src.calls[0][2], [2, 5])
        acts = asyncio.run(self.mock.capture("m1", default_text_for(TASK, "a true thing"), [2, 5]))
        each = [truth_score([p], acts) for p in probes("m1")]
        self.assertAlmostEqual(out["c1"], sum(each) / 2)

    def test_no_probe_no_capture(self):
        src = CountingSource(self.mock)
        out = asyncio.run(self.scorer(src, lambda m: []).score_claims("m1", TASK, claims("x")))
        self.assertEqual(out, {})
        self.assertEqual(src.calls, [])

    def test_unvalidated_probe_counts_as_none(self):
        src = CountingSource(self.mock)
        probes = lambda m: [make_probe(self.mock, m, status="candidate")]
        out = asyncio.run(self.scorer(src, probes).score_claims("m1", TASK, claims("x")))
        self.assertEqual(out, {})
        self.assertEqual(src.calls, [])

    def test_probes_for_raises(self):
        def bad(m):
            raise KeyError(m)
        self.assertEqual(asyncio.run(self.scorer(probes=bad).score_claims("m1", TASK, claims("x"))), {})

    def test_exception_gives_none_for_that_claim(self):
        src = CountingSource(self.mock, fail_on="BAD")
        out = asyncio.run(self.scorer(src).score_claims("m1", TASK, claims("ok one", "BAD", "ok two")))
        self.assertIsNone(out["c2"])
        self.assertIsNotNone(out["c1"])
        self.assertIsNotNone(out["c3"])

    def test_timeout_gives_none_for_that_claim(self):
        src = CountingSource(self.mock, slow_on="SLOW")
        sc = self.scorer(src, timeout_s=0.05)
        out = asyncio.run(sc.score_claims("m1", TASK, claims("SLOW", "fast")))
        self.assertIsNone(out["c1"])
        self.assertIsNotNone(out["c2"])

    def test_wrong_width_gives_none(self):
        probes = lambda m: [Probe(model_id=m, layer=3, weights=[1.0] * 5, status="validated")]
        out = asyncio.run(self.scorer(probes=probes).score_claims("m1", TASK, claims("x")))
        self.assertEqual(out, {"c1": None})

    def test_max_claims(self):
        src = CountingSource(self.mock)
        cs = claims("a", "b", "c", "d")
        out = asyncio.run(self.scorer(src, max_claims=2).score_claims("m1", TASK, cs))
        self.assertEqual(len(src.calls), 2)
        self.assertEqual(set(out), {"c1", "c2", "c3", "c4"})
        self.assertIsNotNone(out["c2"])
        self.assertIsNone(out["c3"])
        self.assertIsNone(out["c4"])

    def test_platt(self):
        self.assertEqual(apply_platt(0.3, None), 0.3)
        self.assertAlmostEqual(apply_platt(0.5, (2.0, -1.0)), 0.5)
        cs = claims("Paris is the capital.")
        raw = asyncio.run(self.scorer().score_claims("m1", TASK, cs))["c1"]
        cal = asyncio.run(self.scorer(platt_for=lambda m: (2.0, -1.0)).score_claims("m1", TASK, cs))["c1"]
        self.assertAlmostEqual(cal, apply_platt(raw, (2.0, -1.0)))
        bad = asyncio.run(self.scorer(platt_for=lambda m: 1 / 0).score_claims("m1", TASK, cs))["c1"]
        self.assertAlmostEqual(bad, raw)

    def test_custom_text_for(self):
        src = CountingSource(self.mock)
        sc = self.scorer(src, text_for=lambda t, s: [{"role": "user", "content": f"{t}|{s}"}])
        asyncio.run(sc.score_claims("m1", "T", claims("S")))
        self.assertEqual(src.calls[0][1][0]["content"], "T|S")

    def test_score_seats(self):
        src = CountingSource(self.mock, delay=0.02)
        probes = lambda m: [] if m == "none" else [make_probe(self.mock, m)]
        by_seat = {
            1: ("m1", claims("true one", f"lie {LIE_MARKER}")),
            2: ("m2", claims("true two")),
            3: ("m1", claims("true three")),
            4: ("none", claims("whatever")),
            5: ("m2", []),
        }
        out = asyncio.run(self.scorer(src, probes).score_seats(TASK, by_seat))
        self.assertEqual(set(out), {1, 2, 3, 4, 5})
        self.assertGreater(out[1]["c1"], out[1]["c2"])
        self.assertIsNotNone(out[2]["c1"])
        self.assertIsNotNone(out[3]["c1"])
        self.assertEqual(out[4], {})
        self.assertEqual(out[5], {})
        self.assertEqual(src.max_active, {"m1": 1, "m2": 1})  # same model in turn
        self.assertEqual(src.max_total, 2)  # different models at once

    def test_score_seats_never_raises(self):
        src = CountingSource(self.mock, fail_on="true")
        out = asyncio.run(self.scorer(src).score_seats(TASK, {1: ("m1", claims("true one"))}))
        self.assertEqual(out, {1: {"c1": None}})
        self.assertEqual(asyncio.run(self.scorer().score_seats(TASK, {})), {})


class OneAtATime(CountingSource):
    """Like the box: one model in memory, captures queue behind one lock."""

    max_models = 1

    def __init__(self, inner, **kw):
        super().__init__(inner, **kw)
        self._lock = None

    async def capture(self, model_id, messages, layers):
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            return await super().capture(model_id, messages, layers)


class ReadingsTest(unittest.TestCase):
    def setUp(self):
        self.mock = MockActivationSource(dim=DIM, signal=6.0, seed=1)
        self.probes = lambda m: [] if m == "none" else [make_probe(self.mock, m)]

    def items(self, n=6, text="true thing"):
        return [(f"t{i}", f"m{i}", text) for i in range(n)]

    def test_read_one_reasons(self):
        src = OneAtATime(self.mock, fail_on="BAD", slow_on="SLOW")
        sc = LiveScorer(src, self.probes, timeout_s=0.05)
        score, why = asyncio.run(sc.read_one("m1", TASK, "true thing"))
        self.assertEqual(why, READ_OK)
        self.assertTrue(0.0 <= score <= 1.0)
        self.assertEqual(asyncio.run(sc.read_one("none", TASK, "x")), (None, READ_NO_PROBE))
        self.assertEqual(asyncio.run(sc.read_one("m1", TASK, "SLOW")), (None, READ_TIMEOUT))
        self.assertEqual(asyncio.run(sc.read_one("m1", TASK, "BAD")), (None, READ_ERROR))
        calls = len(src.calls)
        self.assertEqual(asyncio.run(sc.read_one("m1", TASK, "x", timeout_s=0.0)), (None, READ_TIMEOUT))
        self.assertEqual(len(src.calls), calls)  # no time left: no capture

    def test_six_members_each_get_their_own_timeout(self):
        # Scaled box numbers: each reading takes 0.1 s (5 s), the per-member limit is 0.4 s
        # (20 s). Six in a row take 0.6 s: counted from the start of the batch, the later
        # members would all be cut off.
        src = OneAtATime(self.mock, delay=0.1)
        sc = LiveScorer(src, self.probes, timeout_s=0.4)
        out = asyncio.run(sc.read_many(TASK, self.items()))
        self.assertEqual([why for _s, why in out.values()], [READ_OK] * 6)
        self.assertTrue(all(score is not None for score, _w in out.values()))
        self.assertEqual([c[0] for c in src.calls], [f"m{i}" for i in range(6)])  # fixed order
        self.assertEqual(src.max_total, 1)  # never two captures at once

    def test_unknown_room_is_one_at_a_time(self):
        src = CountingSource(self.mock, delay=0.01)  # no max_models
        out = asyncio.run(LiveScorer(src, self.probes).read_many(TASK, self.items(4)))
        self.assertEqual(src.max_total, 1)
        self.assertEqual([why for _s, why in out.values()], [READ_OK] * 4)

    def test_room_for_more_runs_that_many(self):
        src = CountingSource(self.mock, delay=0.03)
        src.max_models = 2
        items = self.items(4) + [("t9", "m0", "another")]
        out = asyncio.run(LiveScorer(src, self.probes, timeout_s=1.0).read_many(TASK, items))
        self.assertEqual(src.max_total, 2)
        self.assertEqual(src.max_active["m0"], 1)
        self.assertEqual({why for _s, why in out.values()}, {READ_OK})

    def test_one_slow_member_does_not_cost_the_others(self):
        src = OneAtATime(self.mock, delay=0.02, slow_on="SLOW", fail_on="BAD")
        items = [("a", "m0", "fine"), ("b", "m1", "SLOW"), ("c", "none", "x"), ("d", "m2", "BAD"),
                 ("e", "m3", "fine")]
        out = asyncio.run(LiveScorer(src, self.probes, timeout_s=0.15).read_many(TASK, items))
        self.assertEqual([out[k][1] for k in "abcde"],
                         [READ_OK, READ_TIMEOUT, READ_NO_PROBE, READ_ERROR, READ_OK])

    def test_budget_is_respected(self):
        import time
        src = OneAtATime(self.mock, delay=0.1)
        sc = LiveScorer(src, self.probes, timeout_s=5.0)
        t0 = time.monotonic()
        out = asyncio.run(sc.read_many(TASK, self.items(), budget_s=0.28))
        took = time.monotonic() - t0
        self.assertLess(took, 0.6)  # six readings would take 0.6 s
        whys = [why for _s, why in out.values()]
        self.assertEqual(whys[:2], [READ_OK, READ_OK])
        self.assertEqual(whys[3:], [READ_TIMEOUT] * 3)
        self.assertLessEqual(len(src.calls), 3)  # the rest were never started

    def test_default_budget_is_timeout_times_members(self):
        clock = iter([0.0] + [100.0] * 20)  # the fake clock jumps past any budget
        src = OneAtATime(self.mock)
        sc = LiveScorer(src, self.probes, timeout_s=2.0)
        out = asyncio.run(sc.read_many(TASK, self.items(3), clock=lambda: next(clock)))
        self.assertEqual([why for _s, why in out.values()], [READ_TIMEOUT] * 3)
        self.assertEqual(src.calls, [])
        clock = iter([0.0, 1.9, 3.9, 5.9])  # each member starts inside 3 * 2.0
        out = asyncio.run(sc.read_many(TASK, self.items(3), clock=lambda: next(clock)))
        self.assertEqual([why for _s, why in out.values()], [READ_OK] * 3)

    def test_read_many_empty(self):
        self.assertEqual(asyncio.run(LiveScorer(self.mock, self.probes).read_many(TASK, [])), {})


if __name__ == "__main__":
    unittest.main()
