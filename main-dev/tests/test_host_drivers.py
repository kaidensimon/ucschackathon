import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from council.core.schemas import ModelEntry, ModelSource
from council.host.drivers import HostDriver, LlamaRouterDriver, MockDriver, write_preset_ini


def run(coro):
    return asyncio.run(coro)


class TestMock(unittest.TestCase):
    def test_load_unload(self):
        async def go():
            d = MockDriver()
            self.assertIsInstance(d, HostDriver)
            await d.start()
            self.assertEqual(await d.load("a", "live"), "mock://a")
            self.assertEqual((await d.status())["a"], "loaded")
            await d.unload("a")
            self.assertEqual((await d.status())["a"], "unloaded")
            await d.stop()

        run(go())

    def test_fail(self):
        async def go():
            d = MockDriver(fail={"bad"})
            with self.assertRaises(RuntimeError):
                await d.load("bad", "live")
            self.assertEqual((await d.status())["bad"], "failed")

        run(go())

    def test_delay(self):
        async def go():
            d = MockDriver(load_delay_s=0.01)
            await d.load("a", "batch")

        run(go())


class TestRouter(unittest.TestCase):
    def _driver(self, states):
        calls = []
        seq = iter(states)
        last = {"v": "loading"}

        def handler(req: httpx.Request) -> httpx.Response:
            calls.append((req.method, req.url.path, req.content))
            if req.url.path == "/models/load":
                return httpx.Response(200, json={"success": True})
            if req.url.path == "/models/unload":
                return httpx.Response(200, json={"success": True})
            if req.url.path == "/models":
                try:
                    last["v"] = next(seq)
                except StopIteration:
                    pass
                return httpx.Response(
                    200, json={"data": [{"id": "m1", "status": {"value": last["v"]}}]}
                )
            return httpx.Response(404)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return LlamaRouterDriver("http://h:8080/", client=client, poll_s=0.001), calls

    def test_load_polls(self):
        async def go():
            d, calls = self._driver(["loading", "loading", "loaded"])
            url = await d.load("m1", "live")
            self.assertEqual(url, "http://h:8080")
            load = [c for c in calls if c[1] == "/models/load"][0]
            self.assertEqual(json.loads(load[2]), {"model": "m1"})
            self.assertEqual(len([c for c in calls if c[1] == "/models"]), 3)

        run(go())

    def test_load_failed(self):
        async def go():
            d, _ = self._driver(["failed"])
            with self.assertRaises(RuntimeError):
                await d.load("m1", "live")

        run(go())

    def test_load_timeout(self):
        async def go():
            d, _ = self._driver(["loading"] * 1000)
            d.load_timeout_s = 0.02
            with self.assertRaises(TimeoutError):
                await d.load("m1", "live")

        run(go())

    def test_unload_status(self):
        async def go():
            d, calls = self._driver(["unloaded"])
            await d.unload("m1")
            self.assertEqual(json.loads(calls[0][2]), {"model": "m1"})
            self.assertEqual(await d.status(), {"m1": "unloaded"})

        run(go())


class TestPreset(unittest.TestCase):
    def test_ini(self):
        reg = [
            ModelEntry(id="a", source=ModelSource(file="a.gguf")),
            ModelEntry(id="b", source=ModelSource(file="sub/b.gguf")),
        ]
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "p" / "preset.ini"
            write_preset_ini(reg, Path(t) / "models", "batch", out)
            txt = out.read_text(encoding="utf-8")
        self.assertIn("[a]", txt)
        self.assertIn("[b]", txt)
        self.assertIn("a.gguf", txt)
        self.assertIn("ctx-size = 8192", txt)
        self.assertIn("parallel = 16", txt)
        with tempfile.TemporaryDirectory() as t:
            write_preset_ini(reg, Path(t), "live", Path(t) / "l.ini")
            live = (Path(t) / "l.ini").read_text(encoding="utf-8")
        self.assertIn("ctx-size = 32768", live)
        self.assertIn("parallel = 2", live)


class TestBuildDriver(unittest.TestCase):
    def _cfg(self, driver, mock_mode=False):
        from council.core.config import Config

        c = Config()
        c.host.driver = driver
        c.gateway.mock = mock_mode
        return c

    def _models(self, root: Path) -> Path:
        digest = "sha256:" + "cd" * 32
        man = root / "manifests" / "registry.ollama.ai" / "library" / "qwen" / "7b"
        man.parent.mkdir(parents=True)
        man.write_text(json.dumps({"layers": [
            {"mediaType": "application/vnd.ollama.image.model", "digest": digest}]}),
            encoding="utf-8")
        blob = root / "blobs" / digest.replace(":", "-")
        blob.parent.mkdir(parents=True)
        blob.write_bytes(b"GGUF")
        return blob

    def test_existing_choices(self):
        from council.host.drivers import build_driver
        from council.host.ollama_driver import OllamaDriver

        self.assertIsInstance(build_driver(self._cfg("llama_router"), []), LlamaRouterDriver)
        self.assertIsInstance(build_driver(self._cfg("ollama"), []), OllamaDriver)
        self.assertIsInstance(build_driver(self._cfg("mock"), []), MockDriver)

    def test_mock_mode_wins_over_llamacpp(self):
        from council.host.drivers import build_driver

        self.assertIsInstance(build_driver(self._cfg("llamacpp", mock_mode=True), []), MockDriver)

    def test_llamacpp_uses_ollama_blobs(self):
        from council.host.drivers import build_driver
        from council.host.llamacpp_server import LlamaServerDriver

        reg = [ModelEntry(id="a", ollama_tag="qwen:7b"), ModelEntry(id="b", ollama_tag="gone:1")]
        with tempfile.TemporaryDirectory() as t:
            blob = self._models(Path(t))
            c = self._cfg("llamacpp")
            c.llamacpp.ollama_models_dir = t
            c.llamacpp.base_port = 19000
            d = build_driver(c, reg)
            self.assertIsInstance(d, LlamaServerDriver)
            self.assertIsInstance(d, HostDriver)
            self.assertEqual(Path(d.blob_for("qwen:7b")), blob)
            self.assertIsNone(d.blob_for("gone:1"))
            self.assertIn(str(blob), d.argv_for("a"))
            self.assertEqual(d.url_for("a"), "http://127.0.0.1:19000")
            self.assertEqual(d.url_for("b"), "http://127.0.0.1:19001")

    def test_llamacpp_prefers_from_config(self):
        from unittest import mock

        from council.host import drivers, llamacpp_server

        seen = {}

        class Fake:
            @classmethod
            def from_config(cls, config, registry, blob_for=None):
                seen.update(config=config, registry=registry, blob_for=blob_for)
                return cls()

        c = self._cfg("llamacpp")
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.object(llamacpp_server, "LlamaServerDriver", Fake):
            blob = self._models(Path(t))
            c.llamacpp.ollama_models_dir = t
            d = drivers.build_driver(c, ["r"])
            self.assertIsInstance(d, Fake)
            self.assertIs(seen["config"], c)
            self.assertEqual(seen["registry"], ["r"])
            self.assertEqual(seen["blob_for"]("qwen:7b"), blob)

    def test_llamacpp_from_config_other_signature_falls_back(self):
        from unittest import mock

        from council.host import drivers, llamacpp_server

        class Fake:
            def __init__(self, registry, blob_for, base_port=1, ctx=2):
                self.args = (registry, base_port, ctx)

            @classmethod
            def from_config(cls, only_one):
                return cls([], None)

        c = self._cfg("llamacpp")
        c.llamacpp.base_port = 19500
        c.llamacpp.ctx = 4096
        c.llamacpp.health_timeout_s = 7
        with mock.patch.object(llamacpp_server, "LlamaServerDriver", Fake):
            d = drivers.build_driver(c, ["r"])
        self.assertEqual(d.args, (["r"], 19500, 4096))
        self.assertEqual(d.health_timeout_s, 7.0)

    def test_accepted(self):
        from council.host.drivers import _accepted

        def f(a, b=1):
            pass

        def g(**kw):
            pass

        self.assertEqual(_accepted(f, {"a": 1, "z": 2}), {"a": 1})
        self.assertEqual(_accepted(g, {"a": 1, "z": 2}), {"a": 1, "z": 2})


if __name__ == "__main__":
    unittest.main()
