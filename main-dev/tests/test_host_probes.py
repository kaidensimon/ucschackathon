import json
import tempfile
import unittest
from pathlib import Path

from council.core.config import Config
from council.core.events import EventBus
from council.core.schemas import (
    CallResult, MeasuredStats, ModelEntry, ReasoningControl, ServeConfig, ServeProfile,
)
from council.core.store import Store
from council.gateway.gateway import Gateway
from council.gateway.mock import MockResponder
from council.host.drivers import MockDriver
from council.host.host import Host
from council.host.probes import ProbeSuite, write_measured
from council.host.ram import RamBudget


def entry(i, ctx=2048):
    return ModelEntry(
        id=i,
        params_b=10,
        serve=ServeConfig(live=ServeProfile(ctx=ctx, parallel=2), batch=ServeProfile(ctx=512, parallel=8)),
        reasoning=ReasoningControl(kind="effort"),
    )


class Bus:
    def emit(self, *a, **k):
        pass


class Scripted:
    """Responder that answers the P6 prompts exactly and scales gen time per model."""

    def __init__(self, inner, slow=None):
        self.inner = inner
        self.slow = slow or {}

    async def respond(self, s, on_delta=None):
        sysmsg = next((m["content"] for m in s.messages if m["role"] == "system"), "")
        if "PONG" in sysmsg:
            txt = "PONG"
        elif "number" in sysmsg:
            txt = "12"
        elif "lowercase" in sysmsg:
            txt = "hello world"
        else:
            r = await self.inner.respond(s, on_delta)
            f = self.slow.get(s.model_id)
            if f:
                r = r.model_copy(update={"gen_ms": r.gen_ms * f})
            return r
        return CallResult(call_id=s.call_id, ok=True, model_id=s.model_id, content=txt,
                          tokens_in=5, tokens_out=2, gen_ms=10.0)


class ProbesTest(unittest.IsolatedAsyncioTestCase):
    def make(self, ids=("a", "b", "c"), responder=None):
        reg = [entry(i) for i in ids]
        cfg = Config()
        cfg.gateway.mock = True
        store = Store(":memory:")
        gw = Gateway(cfg, reg, store, EventBus(store), responder=responder or MockResponder(seed=1))
        holder = {}

        def read():
            return 100.0 - sum(r.footprint_gib for r in holder["h"]._resident.values())

        ram = RamBudget(read, 0.0, set(), {})
        host = Host(MockDriver(), ram, reg, Bus())
        holder["h"] = host
        return ProbeSuite(gw, host, read, reg), host, gw

    async def test_p1_footprint(self):
        s, host, _ = self.make()
        r = await s.p1_footprint("a", "live")
        self.assertEqual(r["available_before_gib"], 100.0)
        self.assertEqual(r["available_after_gib"], 100.0 - r["footprint_gib"])
        self.assertGreater(r["footprint_gib"], 0)
        self.assertGreaterEqual(r["load_s"], 0)
        # second profile reloads cold
        r2 = await s.p1_footprint("a", "batch")
        self.assertEqual(r2["available_before_gib"], 100.0)
        self.assertEqual(host.status()[0]["profile"], "batch")

    async def test_p1_unknown_model(self):
        s, _, _ = self.make()
        with self.assertRaises(KeyError):
            await s.p1_footprint("zz", "live")

    async def test_p2_speed_mock(self):
        s, _, gw = self.make()
        r = await s.p2_speed("a")
        self.assertEqual(set(r), {1, 8, 32})
        self.assertGreater(r[1], 0)
        # Rates are tokens per second of wall clock; the mock answers instantly, so their
        # order is timing noise. Only that each stream count produced a rate is checked.
        self.assertGreater(r[32], 0)
        self.assertGreater(r[8], 0)
        self.assertEqual(gw.governor._slots["a"], 2)  # restored

    async def test_p3_structured_mock(self):
        s, _, _ = self.make()
        self.assertEqual(await s.p3_structured("a", n=5), 1.0)

    async def test_p3_bad_output(self):
        class Bad:
            async def respond(self, sp, on_delta=None):
                return CallResult(call_id=sp.call_id, ok=True, model_id=sp.model_id, content="x")

        s, _, _ = self.make(responder=Bad())
        self.assertEqual(await s.p3_structured("a", n=4), 0.0)

    async def test_p4_reasoning_mock(self):
        s, _, _ = self.make()
        r = await s.p4_reasoning("a")
        self.assertEqual(r["off"], 0)
        self.assertGreater(r["council"], 0)
        self.assertGreater(r["max"], r["council"])
        self.assertTrue(r["differs"])

    async def test_p5_context_mock(self):
        s, _, _ = self.make()
        self.assertTrue(await s.p5_context("a"))

    async def test_p6_template(self):
        s, _, _ = self.make()
        self.assertFalse(await s.p6_template("a"))  # plain mock text is not the expected output
        s2, _, _ = self.make(responder=Scripted(MockResponder(seed=1)))
        self.assertTrue(await s2.p6_template("a"))

    async def test_p7_cross_model(self):
        s, _, gw = self.make()
        r = await s.p7_cross_model(["a", "b", "c"])
        self.assertGreater(r["simultaneous_tps"], r["sequential_tps"])
        self.assertEqual(r["recommended_max_concurrent_models"], 3)
        self.assertEqual(gw.governor._max_models, 2)  # restored

    async def test_p7_contention_says_one(self):
        # together each call takes as long as all of them one after another
        s, _, _ = self.make(ids=("a", "b"), responder=Scripted(MockResponder(seed=1), slow={"a": 1.0, "b": 1.0}))
        orig = s.gateway.call_many

        async def slow_many(specs):
            res = await orig(specs)
            total = sum(r.gen_ms for r in res)
            return [r.model_copy(update={"gen_ms": total}) for r in res]

        s.gateway.call_many = slow_many
        r = await s.p7_cross_model(["a", "b"])
        self.assertEqual(r["recommended_max_concurrent_models"], 1)

    async def test_p8_speculative_mock(self):
        s, _, gw = self.make()
        r = await s.p8_speculative("a")
        self.assertEqual(set(r["tps"]), {0, 4, 8})
        self.assertIn(r["best"], (0, 4, 8))
        self.assertTrue(r["honoured"])
        self.assertEqual(gw.registry["a"].ollama_options, {})  # restored
        bad = await s.p8_speculative("zz")
        self.assertIn("error", bad)

    async def test_context_cost_mock(self):
        s, host, _ = self.make()
        r = await s.context_cost("a")
        self.assertEqual(set(r["points"]), {8192, 16384, 32768})
        self.assertIsNotNone(r["gib_per_1k_ctx"])
        self.assertEqual(s._entry("a").serve.live.ctx, 2048)  # restored
        self.assertIn("error", await s.context_cost("zz"))

    async def test_run_model(self):
        s, host, _ = self.make()
        m = await s.run_model("a")
        self.assertIsInstance(m, MeasuredStats)
        self.assertIsNotNone(m.ram_gb_live)
        self.assertIsNotNone(m.load_s)
        self.assertGreater(m.tps_32, m.tps_1)
        self.assertEqual(m.structured_valid_rate, 1.0)
        self.assertIsNotNone(m.probe_date)
        self.assertEqual(s.reports["a"]["structured_recommended"], "grammar")
        self.assertEqual(host.status()[0]["profile"], "live")

    async def test_write_measured(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "models.json"
            p.write_text(json.dumps([
                {"id": "a", "measured": {"tps_1": 1.0, "load_s": 5.0}},
                {"id": "b", "measured": {"tps_1": 9.0}},
            ]))
            write_measured(p, "a", MeasuredStats(tps_1=42.0, probe_date="2026-10-10"))
            rows = json.loads(p.read_text())
            self.assertEqual(rows[0]["measured"]["tps_1"], 42.0)
            self.assertEqual(rows[0]["measured"]["load_s"], 5.0)  # null keeps old
            self.assertEqual(rows[0]["measured"]["probe_date"], "2026-10-10")
            self.assertEqual(rows[1]["measured"], {"tps_1": 9.0})
            with self.assertRaises(KeyError):
                write_measured(p, "zz", MeasuredStats())


if __name__ == "__main__":
    unittest.main()
