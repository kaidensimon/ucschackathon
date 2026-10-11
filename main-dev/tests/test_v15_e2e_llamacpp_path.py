"""End to end, mock mode: the llama.cpp serving path without a real server.

config driver "llamacpp" -> build_driver -> LlamaServerDriver (spawn + health are fakes) -> Host loads
six models -> six ports -> Gateway call reaches that model's URL (httpx.MockTransport) with a JSON
schema -> steering restarts the server with --control-vector-scaled -> unload frees the port.
All classes are the real ones; only the process spawn, the health probe and the HTTP transport are faked.
"""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx

from council.api.run_pipeline import apply_steering
from council.core import event_types as ET
from council.core.config import Config
from council.core.schemas import CallSpec, ModelEntry
from council.gateway.gateway import Gateway
from council.host.drivers import build_driver
from council.host.host import Host
from council.host.llamacpp_server import LlamaServerDriver
from council.host.ram import RamBudget

BASE_PORT = 18100
IDS = [f"m{i}" for i in range(6)]
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "confidence": {"type": "number"}},
    "required": ["answer", "confidence"],
}
REAL_ASYNC_CLIENT = httpx.AsyncClient


class FakeProc:
    next_pid = 9000

    def __init__(self):
        self.returncode = None
        self.terminated = 0
        self.killed = 0
        self._gone = asyncio.Event()
        FakeProc.next_pid += 1
        self.pid = FakeProc.next_pid

    def terminate(self):
        self.terminated += 1
        self.returncode = -15
        self._gone.set()

    def kill(self):
        self.killed += 1
        self.returncode = -9
        self._gone.set()

    async def wait(self):
        await self._gone.wait()
        return self.returncode


class Rig:
    """Records every spawn and every health probe."""

    def __init__(self):
        self.argvs: list[list[str]] = []
        self.procs: list[FakeProc] = []
        self.probed: list[str] = []

    async def spawn(self, argv):
        self.argvs.append(list(argv))
        proc = FakeProc()
        self.procs.append(proc)
        return proc

    async def probe(self, url):
        self.probed.append(url)
        return True


class FakeBus:
    def __init__(self):
        self.events = []

    def emit(self, type_, run_id, payload=None):
        self.events.append((type_, run_id, payload))

    def types(self):
        return [e[0] for e in self.events]


def make_models_dir(root: Path) -> dict[str, Path]:
    """A tiny Ollama store: one manifest + one blob per model. Returns tag -> blob."""
    blobs = {}
    for i, mid in enumerate(IDS):
        tag = f"{mid}:7b"
        digest = f"sha256-{i:064x}"
        mfile = root / "manifests" / "registry.ollama.ai" / "library" / mid / "7b"
        mfile.parent.mkdir(parents=True, exist_ok=True)
        mfile.write_text(json.dumps({"layers": [
            {"mediaType": "application/vnd.ollama.image.model", "digest": digest.replace("-", ":", 1)},
        ]}), encoding="utf-8")
        blob = root / "blobs" / digest
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(b"GGUF")
        blobs[tag] = blob
    return blobs


def make_registry() -> list[ModelEntry]:
    return [ModelEntry(id=mid, ollama_tag=f"{mid}:7b") for mid in IDS]


def make_config(models_dir: Path) -> Config:
    return Config.model_validate({
        "host": {"driver": "llamacpp"},
        "gateway": {"mock": False, "cache": False},
        "llamacpp": {
            "server_bin": "fake-bin/llama-server", "base_port": BASE_PORT, "ctx": 4096,
            "parallel": 1, "health_timeout_s": 5, "ollama_models_dir": str(models_dir),
        },
    })


def chat_body(content: str) -> dict:
    return {
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 9},
        "timings": {"predicted_per_second": 40.0},
    }


class LlamaCppPathTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.models_dir = Path(self._tmp.name) / "ollama"
        self.blobs = make_models_dir(self.models_dir)
        self.config = make_config(self.models_dir)
        self.registry = make_registry()
        self.rig = Rig()
        self.bus = FakeBus()

    def make_driver(self) -> LlamaServerDriver:
        from council.host import ollama_blobs
        return LlamaServerDriver.from_config(
            self.config, self.registry, ollama_blobs.resolver(self.models_dir),
            spawn=self.rig.spawn, probe_health=self.rig.probe,
        )

    def make_host(self, driver) -> Host:
        fp = {(m, p): 5.0 for m in IDS for p in ("live", "batch")}
        ram = RamBudget(lambda: 200.0, 1.0, set(), fp)
        return Host(driver, ram, self.registry, self.bus)

    def port_of(self, argv: list[str]) -> int:
        return int(argv[argv.index("--port") + 1])

    # ---- 1 ----
    async def test_config_driver_llamacpp_builds_llama_server_driver(self):
        drv = build_driver(self.config, self.registry)
        self.assertIsInstance(drv, LlamaServerDriver)
        self.assertEqual(drv.base_port, BASE_PORT)
        self.assertEqual(drv.ctx, 4096)
        self.assertEqual(drv.server_bin, Path("fake-bin/llama-server"))
        argv = drv.argv_for("m2")  # resolves the blob through the fake Ollama store
        self.assertEqual(argv[argv.index("-m") + 1], str(self.blobs["m2:7b"]))
        self.assertEqual(self.port_of(argv), BASE_PORT + 2)
        self.assertIn("--jinja", argv)
        self.assertEqual(argv[argv.index("-c") + 1], "4096")
        # the fallback stays selectable: ollama driver on the same config
        fallback = Config.model_validate({"host": {"driver": "ollama"}, "gateway": {"mock": False}})
        from council.host.ollama_driver import OllamaDriver
        self.assertIsInstance(build_driver(fallback, self.registry), OllamaDriver)

    # ---- 2 ----
    async def test_six_models_get_six_distinct_ports_and_endpoints(self):
        drv = self.make_driver()
        host = self.make_host(drv)
        out = await host.ensure_resident(IDS, "live", "run1")
        self.assertEqual(set(out), set(IDS))
        self.assertEqual(len(set(out.values())), 6, out)
        for i, mid in enumerate(IDS):
            self.assertEqual(out[mid], f"http://127.0.0.1:{BASE_PORT + i}")
            self.assertEqual(host.endpoint_for(mid), out[mid])
        # six spawns, each with its own blob and port
        self.assertEqual(len(self.rig.argvs), 6)
        ports = [self.port_of(a) for a in self.rig.argvs]
        self.assertEqual(sorted(ports), [BASE_PORT + i for i in range(6)])
        blobs_used = {a[a.index("-m") + 1] for a in self.rig.argvs}
        self.assertEqual(blobs_used, {str(b) for b in self.blobs.values()})
        # health was probed on every endpoint, events say loaded with that endpoint
        self.assertEqual(set(self.rig.probed), set(out.values()))
        loaded = {p["model_id"]: p["endpoint"] for t, _r, p in self.bus.events if t == ET.MODEL_LOADED}
        self.assertEqual(loaded, out)
        self.assertEqual(set((await drv.status()).values()), {"loaded"})
        # asking again does not spawn again
        await host.ensure_resident(IDS, "live", "run1")
        self.assertEqual(len(self.rig.argvs), 6)

    # ---- 3 ----
    async def test_gateway_call_goes_to_model_url_with_schema(self):
        drv = self.make_driver()
        host = self.make_host(drv)
        await host.ensure_resident(IDS, "live", "run1")
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            body = json.loads(request.content)
            self.assertIn("response_format", body)
            return httpx.Response(200, json=chat_body(json.dumps(
                {"answer": f"port{request.url.port}", "confidence": 0.8})))

        def factory(*a, **kw):
            return REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

        gw = Gateway(self.config, self.registry, None, None, endpoint_for=host.endpoint_for)
        self.assertTrue(gw.uses_llamacpp)
        with mock.patch.object(httpx, "AsyncClient", factory):
            for i, mid in enumerate(IDS):
                spec = CallSpec(
                    model_id=mid, run_id="run1", call_id=f"c{i}", purpose="seat.r0",
                    messages=[{"role": "user", "content": "pick a rate limiter"}],
                    json_schema=SCHEMA, reasoning="off", stream=False,
                )
                res = await gw.call(spec)
                self.assertTrue(res.ok, f"{mid}: {res.error}")
                self.assertEqual(res.parsed, {"answer": f"port{BASE_PORT + i}", "confidence": 0.8})
                self.assertEqual(res.tokens_out, 9)
        self.assertEqual([r.url.port for r in seen], [BASE_PORT + i for i in range(6)])
        for r in seen:
            self.assertEqual(r.url.host, "127.0.0.1")
            self.assertEqual(r.url.path, "/v1/chat/completions")
            body = json.loads(r.content)
            fmt = body["response_format"]
            self.assertEqual(fmt["type"], "json_schema")
            self.assertEqual(fmt["json_schema"]["schema"], SCHEMA)

    # ---- 4 ----
    async def test_steering_restarts_server_with_control_vector(self):
        drv = self.make_driver()
        host = self.make_host(drv)
        await host.ensure_resident(["m0", "m1"], "live", "run1")
        self.assertEqual(len(self.rig.argvs), 2)
        self.assertTrue(all("--control-vector-scaled" not in a for a in self.rig.argvs))
        first_proc = self.rig.procs[0]
        vec = Path("vectors") / "proj.gguf"
        live: dict = {}
        ok = await apply_steering(host, live, "m0", vec, 0.5)
        self.assertTrue(ok)
        self.assertEqual(drv.steering_of("m0"), (vec, 0.5))
        self.assertIsNone(drv.steering_of("m1"))
        self.assertEqual(first_proc.terminated, 1, "old server must be stopped")
        self.assertIsNone(host.endpoint_for("m0"))
        # next load starts it again with the vector
        out = await host.ensure_resident(["m0", "m1"], "live", "run2")
        self.assertEqual(len(self.rig.argvs), 3, "only m0 restarts")
        argv = self.rig.argvs[2]
        self.assertEqual(argv[argv.index("--port") + 1], str(BASE_PORT))
        self.assertEqual(argv[argv.index("--control-vector-scaled") + 1], f"{vec}:0.5")
        self.assertEqual(out["m0"], f"http://127.0.0.1:{BASE_PORT}")
        self.assertEqual(self.rig.procs[1].terminated, 0, "m1 untouched")
        # same steering again: no restart
        await apply_steering(host, live, "m0", vec, 0.5)
        await host.ensure_resident(["m0"], "live", "run3")
        self.assertEqual(len(self.rig.argvs), 3)
        # steering off: restart without the flag
        await apply_steering(host, live, "m0", None)
        await host.ensure_resident(["m0"], "live", "run4")
        self.assertEqual(len(self.rig.argvs), 4)
        self.assertNotIn("--control-vector-scaled", self.rig.argvs[3])
        self.assertIsNone(drv.steering_of("m0"))

    # ---- 5 ----
    async def test_gateway_reaches_steered_server_on_same_url_after_restart(self):
        drv = self.make_driver()
        host = self.make_host(drv)
        await host.ensure_resident(["m3"], "live", "run1")
        ports = []

        def handler(request: httpx.Request) -> httpx.Response:
            ports.append(request.url.port)
            return httpx.Response(200, json=chat_body('{"answer": "ok", "confidence": 0.5}'))

        def factory(*a, **kw):
            return REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

        gw = Gateway(self.config, self.registry, None, None, endpoint_for=host.endpoint_for)

        def spec(n):
            return CallSpec(model_id="m3", run_id="run1", call_id=f"c{n}", purpose="seat.r0",
                            messages=[{"role": "user", "content": "q"}], json_schema=SCHEMA,
                            reasoning="off", stream=False)

        with mock.patch.object(httpx, "AsyncClient", factory):
            self.assertTrue((await gw.call(spec(1))).ok)
            await apply_steering(host, {}, "m3", Path("v.gguf"), 1.0)
            # unloaded: no endpoint, so a call fails cleanly instead of hitting a dead port
            down = await gw.call(spec(2))
            self.assertFalse(down.ok)
            self.assertEqual(down.error, "server_error")
            await host.ensure_resident(["m3"], "live", "run2")
            self.assertTrue((await gw.call(spec(3))).ok)
        self.assertEqual(ports, [BASE_PORT + 3, BASE_PORT + 3])
        self.assertIn("--control-vector-scaled", self.rig.argvs[-1])

    # ---- 6 ----
    async def test_unload_frees_port_and_reload_reuses_it(self):
        drv = self.make_driver()
        host = self.make_host(drv)
        await host.ensure_resident(["m0", "m1", "m2"], "live", "run1")
        victim = self.rig.procs[1]
        port = drv.port_for("m1")
        self.assertIn("m1", drv.pids())
        await host.unload("m1")
        self.assertEqual(victim.terminated, 1)
        self.assertIsNotNone(victim.returncode)
        self.assertNotIn("m1", drv.pids())
        self.assertEqual((await drv.status())["m1"], "unloaded")
        self.assertIsNone(host.endpoint_for("m1"))
        self.assertEqual({s["model_id"] for s in host.status()}, {"m0", "m2"})
        self.assertIn(ET.MODEL_UNLOADED, self.bus.types())
        # others keep running
        self.assertEqual({m for m in drv.pids()}, {"m0", "m2"})
        # reload: same fixed port, new process
        out = await host.ensure_resident(["m1"], "live", "run2")
        self.assertEqual(out["m1"], f"http://127.0.0.1:{port}")
        self.assertEqual(self.port_of(self.rig.argvs[-1]), port)
        self.assertEqual(len(self.rig.procs), 4)
        # stop() takes everything down
        await drv.stop()
        self.assertTrue(all(p.returncode is not None for p in self.rig.procs))
        self.assertEqual(drv.pids(), {})

    # ---- 7 ----
    async def test_unhealthy_server_fails_load_and_frees_the_slot(self):
        async def never_healthy(url):
            return False

        from council.host import ollama_blobs
        drv = LlamaServerDriver.from_config(
            self.config, self.registry, ollama_blobs.resolver(self.models_dir),
            spawn=self.rig.spawn, probe_health=never_healthy,
        )
        host = self.make_host(drv)
        from council.host.host import HostError
        with self.assertRaises(HostError):
            await host.ensure_resident(["m4"], "live", "run1")
        self.assertEqual(self.bus.types().count(ET.MODEL_FAILED), 2)  # one retry
        self.assertEqual(len(self.rig.procs), 2)
        self.assertTrue(all(p.returncode is not None for p in self.rig.procs), "no zombie server")
        self.assertIsNone(host.endpoint_for("m4"))
        self.assertEqual(drv.pids(), {})
        self.assertEqual(host.status(), [])


if __name__ == "__main__":
    unittest.main()
