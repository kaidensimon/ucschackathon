import asyncio
import unittest

from council.core import event_types as ET
from council.core.schemas import ModelEntry
from council.host.drivers import MockDriver
from council.host.host import Host, HostError
from council.host.ram import RamBudget


class FakeBus:
    def __init__(self):
        self.events = []

    def emit(self, type, run_id, payload=None):
        self.events.append((type, run_id, payload))

    def types(self):
        return [e[0] for e in self.events]


def make(avail=30.0, fail=None, ids=("a", "b", "c")):
    reg = [ModelEntry(id=i) for i in ids]
    fp = {(i, p): 10.0 for i in ids for p in ("live", "batch")}
    holder = {}

    def read():
        h = holder["h"]
        return avail - sum(r.footprint_gib for r in h._resident.values())

    ram = RamBudget(read, 0.0, set(), fp)
    bus = FakeBus()
    t = [0.0]

    def clock():
        t[0] += 1
        return t[0]

    host = Host(MockDriver(fail=fail), ram, reg, bus, clock)
    holder['h'] = host
    return host, bus


class HostTest(unittest.IsolatedAsyncioTestCase):
    async def test_load_and_status(self):
        h, bus = make()
        await h.start()
        out = await h.ensure_resident(["a", "b"], "live", "r1")
        self.assertEqual(out, {"a": "mock://a", "b": "mock://b"})
        self.assertEqual(h.endpoint("a"), "mock://a")
        self.assertIsNone(h.endpoint("zz"))
        st = {s["model_id"]: s for s in h.status()}
        self.assertFalse(st["a"]["idle"])
        self.assertEqual(st["a"]["footprint_gib"], 10.0)
        self.assertEqual(bus.types().count(ET.MODEL_LOADED), 2)
        # second call no reload
        await h.ensure_resident(["a"], "live", "r1")
        self.assertEqual(bus.types().count(ET.MODEL_LOADING), 2)

    async def test_release_idle(self):
        h, _ = make()
        await h.ensure_resident(["a"], "live", "r1")
        h.release("r1")
        self.assertTrue(h.status()[0]["idle"])

    async def test_evict_idle(self):
        h, bus = make(avail=20.0)
        await h.ensure_resident(["a", "b"], "live", "r1")
        h.release("r1")
        h.touch("b")
        await h.ensure_resident(["c"], "live", "r2")
        ids = {s["model_id"] for s in h.status()}
        self.assertEqual(ids, {"b", "c"})
        t = bus.types()
        self.assertLess(t.index(ET.MODEL_EVICTED), t.index(ET.MODEL_UNLOADED))
        self.assertIsNone(h.endpoint("a"))

    async def test_no_room_raises(self):
        h, _ = make(avail=20.0)
        await h.ensure_resident(["a", "b"], "live", "r1")
        with self.assertRaises(HostError):
            await h.ensure_resident(["c"], "live", "r2")

    async def test_failure_retry_then_raise(self):
        h, bus = make(fail={"a"})
        with self.assertRaises(HostError):
            await h.ensure_resident(["a"], "live", "r1")
        self.assertEqual(bus.types().count(ET.MODEL_FAILED), 2)
        self.assertEqual(bus.types().count(ET.MODEL_LOADING), 2)
        self.assertEqual(h.status(), [])

    async def test_retry_succeeds(self):
        h, bus = make()
        calls = {"n": 0}
        orig = h.driver.load

        async def flaky(mid, profile):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            return await orig(mid, profile)

        h.driver.load = flaky
        out = await h.ensure_resident(["a"], "live", "r1")
        self.assertEqual(out["a"], "mock://a")
        self.assertEqual(bus.types().count(ET.MODEL_FAILED), 1)


if __name__ == "__main__":
    unittest.main()


class HostLoadTest(unittest.IsolatedAsyncioTestCase):
    async def test_load_unload(self):
        h, bus = make()
        self.assertEqual(await h.load("a", "live"), "mock://a")
        h.release("manual")
        await h.unload("a")
        self.assertIsNone(h.endpoint("a"))
        await h.unload("a")  # no-op

    def test_build_driver(self):
        from council.core.config import Config
        from council.host.drivers import LlamaRouterDriver
        from council.host.host import build_driver
        from council.host.ollama_driver import OllamaDriver

        c = Config()
        self.assertIsInstance(build_driver(c, []), LlamaRouterDriver)
        c.host.driver = "ollama"
        self.assertIsInstance(build_driver(c, []), OllamaDriver)
        c.gateway.mock = True
        self.assertIsInstance(build_driver(c, []), MockDriver)


class _LlamaFake:
    """Shaped like LlamaServerDriver: one URL per model, measured sizes, steering, render."""

    def __init__(self, ids=("a", "b", "c"), sizes=None, loaded=()):
        self.ports = {m: 18100 + i for i, m in enumerate(ids)}
        self.sizes = dict(sizes or {})
        self.state = {m: "loaded" for m in loaded}
        self.steer = []
        self.started = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.started = False

    def url_for(self, mid):
        return f"http://127.0.0.1:{self.ports[mid]}"

    async def load(self, mid, profile):
        self.state[mid] = "loaded"
        return self.url_for(mid)

    async def unload(self, mid):
        self.state[mid] = "unloaded"

    async def status(self):
        return dict(self.state)

    async def footprints(self):
        return {m: g for m, g in self.sizes.items() if self.state.get(m) == "loaded"}

    async def set_steering(self, mid, path, scale):
        self.steer.append((mid, path, scale))
        return f"http://127.0.0.1:{self.ports[mid] + 500}"  # restarted on another port

    async def render(self, mid, messages):
        return "|".join(m["content"] for m in messages)


def make_llama(avail=30.0, **kw):
    h, bus = make(avail=avail)
    h.driver = _LlamaFake(**kw)
    return h, bus


class HostLlamaCppTest(unittest.IsolatedAsyncioTestCase):
    async def test_one_endpoint_per_model(self):
        h, _ = make_llama()
        out = await h.ensure_resident(["a", "b"], "live", "r1")
        self.assertEqual(out, {"a": "http://127.0.0.1:18100", "b": "http://127.0.0.1:18101"})
        self.assertEqual(h.endpoint_for("b"), "http://127.0.0.1:18101")
        self.assertEqual(h.endpoint("b"), h.endpoint_for("b"))
        self.assertIsNone(h.endpoint_for("c"))
        self.assertEqual(h.endpoints(), out)
        eps = h.endpoints()
        eps["zz"] = "x"  # a copy: the host map is not touched
        self.assertNotIn("zz", h.endpoints())
        h.release("r1")
        await h.unload("a")
        self.assertEqual(h.endpoints(), {"b": "http://127.0.0.1:18101"})

    async def test_adopt_asks_the_driver(self):
        h, _ = make_llama(sizes={"b": 4.5}, loaded=("b", "c", "stranger"))
        await h.start()
        st = {s["model_id"]: s for s in h.status()}
        self.assertEqual(set(st), {"b", "c"})  # not in the registry: left alone
        self.assertEqual(st["b"]["footprint_gib"], 4.5)  # measured
        self.assertEqual(st["c"]["footprint_gib"], 10.0)  # table, driver did not say
        self.assertEqual(st["b"]["endpoint"], "http://127.0.0.1:18101")
        self.assertTrue(st["b"]["idle"])

    async def test_adopt_measured_only_model(self):
        h, _ = make_llama(sizes={"b": 3.0}, loaded=("b",))
        h.ram.footprints.clear()  # nothing in the table: the measured size is enough
        await h.start()
        self.assertEqual(h.status()[0]["footprint_gib"], 3.0)

    async def test_adopt_survives_broken_driver(self):
        h, _ = make_llama(loaded=("a",))

        async def boom():
            raise RuntimeError("down")

        h.driver.footprints = boom
        await h.start()
        self.assertEqual(h.status()[0]["footprint_gib"], 10.0)
        h2, _ = make_llama(loaded=("a",))
        h2.driver.status = boom
        await h2.start()
        self.assertEqual(h2.status(), [])

    async def test_adopt_single_url_driver(self):
        h, _ = make()
        h.driver.base_url = "http://one:11434"
        h.driver._state["a"] = "loaded"
        await h.start()
        self.assertEqual(h.endpoint_for("a"), "http://one:11434")

    async def test_memory_uses_measured_footprints(self):
        h, _ = make_llama(avail=20.0, sizes={"a": 2.0, "b": 2.0, "c": 2.0})
        await h.ensure_resident(["a", "b"], "live", "r1")
        st = {s["model_id"]: s["footprint_gib"] for s in h.status()}
        self.assertEqual(st, {"a": 2.0, "b": 2.0})
        # the table says 10 each (no room for a third); measured they take 4 of 20
        await h.ensure_resident(["c"], "live", "r1")
        self.assertEqual({s["model_id"] for s in h.status()}, {"a", "b", "c"})

    async def test_zero_measure_keeps_table_value(self):
        h, _ = make_llama(sizes={"a": 0.0})
        await h.ensure_resident(["a"], "live", "r1")
        self.assertEqual(h.status()[0]["footprint_gib"], 10.0)

    async def test_set_steering_passes_through(self):
        h, _ = make_llama()
        await h.ensure_resident(["a"], "live", "r1")
        self.assertTrue(await h.set_steering("a", "/v/a.gguf", 0.5))
        self.assertEqual(h.driver.steer, [("a", "/v/a.gguf", 0.5)])
        self.assertEqual(h.endpoint_for("a"), "http://127.0.0.1:18600")
        self.assertTrue(await h.set_steering("b", None, 0.0))  # not resident: no endpoint made
        self.assertIsNone(h.endpoint_for("b"))

    async def test_set_steering_sync_driver_and_error(self):
        h, _ = make_llama()
        calls = []
        h.driver.set_steering = lambda m, p, s: calls.append((m, p, s))
        self.assertTrue(await h.set_steering("a", "p", 1.5))
        self.assertEqual(calls, [("a", "p", 1.5)])

        def bad(m, p, s):
            raise RuntimeError("no vector")

        h.driver.set_steering = bad
        with self.assertRaises(RuntimeError):
            await h.set_steering("a", "p", 1.0)
        await h.ensure_resident(["a"], "live", "r1")  # the lock was released

    async def test_render_passes_through(self):
        h, _ = make_llama()
        msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}]
        self.assertEqual(await h.render("a", msgs), "hi|yo")
        h.driver.render = lambda m, ms: f"{m}:{len(ms)}"
        self.assertEqual(await h.render("a", msgs), "a:2")

    async def test_unsupported_driver_is_noop(self):
        h, _ = make()  # MockDriver: no steering, no render, no footprints
        await h.ensure_resident(["a"], "live", "r1")
        self.assertFalse(await h.set_steering("a", "/v/a.gguf", 0.5))
        self.assertIsNone(await h.render("a", [{"role": "user", "content": "hi"}]))
        self.assertEqual(h.endpoint_for("a"), "mock://a")
        self.assertEqual(h.status()[0]["footprint_gib"], 10.0)

    async def test_real_llamacpp_driver_through_host(self):
        from pathlib import Path

        from council.host.llamacpp_server import LlamaServerDriver

        class Proc:
            returncode = None

            def terminate(self):
                self.returncode = 0

            def kill(self):
                self.returncode = -9

            async def wait(self):
                while self.returncode is None:
                    await asyncio.sleep(0.01)
                return self.returncode

        async def spawn(argv):
            return Proc()

        async def healthy(url):
            return True

        h, _ = make()
        h.driver = LlamaServerDriver(
            list(h.registry.values()), lambda tag: Path("/blobs") / tag,
            base_port=19100, spawn=spawn, probe_health=healthy)
        out = await h.ensure_resident(["a", "c"], "live", "r1")
        self.assertEqual(out, {"a": "http://127.0.0.1:19100", "c": "http://127.0.0.1:19102"})
        h.release("r1")
        await h.unload("a")
        self.assertEqual(h.endpoints(), {"c": "http://127.0.0.1:19102"})
        await h.driver.stop()

    def test_build_driver_llamacpp(self):
        from council.core.config import Config
        from council.host.host import build_driver
        from council.host.llamacpp_server import LlamaServerDriver

        c = Config()
        c.host.driver = "llamacpp"
        self.assertIsInstance(build_driver(c, []), LlamaServerDriver)
