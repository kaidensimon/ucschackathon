import asyncio
import json
import unittest

import httpx

from council.core.schemas import ModelEntry
from council.host.drivers import HostDriver
from council.host.ollama_driver import OllamaDriver


def run(coro):
    return asyncio.run(coro)


def make_registry():
    return [
        ModelEntry(id="a", ollama_tag="alpha:7b"),
        ModelEntry(id="b", ollama_tag="beta:1b"),
        ModelEntry(id="c"),
    ]


class FakeOllama:
    def __init__(self, installed=("alpha:7b",)):
        self.installed = list(installed)
        self.running = []
        self.calls = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        body = json.loads(req.content) if req.content else {}
        self.calls.append((req.method, path, body))
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": t} for t in self.installed]})
        if path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": t} for t in self.running]})
        if path == "/api/generate":
            tag = body["model"]
            if body.get("keep_alive") == 0:
                if tag in self.running:
                    self.running.remove(tag)
            elif tag not in self.running:
                self.running.append(tag)
            return httpx.Response(200, json={"done": True})
        return httpx.Response(404)


def make_driver(fake, runner=None, **kw):
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    return OllamaDriver("http://x:11434/", make_registry(), client=client, runner=runner, **kw)


class OllamaDriverTests(unittest.TestCase):
    def test_protocol_and_start(self):
        fake = FakeOllama()
        d = make_driver(fake)
        self.assertIsInstance(d, HostDriver)
        run(d.start())
        self.assertEqual(d.missing_tags(), ["beta:1b"])

    def test_latest_normalized(self):
        fake = FakeOllama(installed=["alpha:7b", "beta:1b"])
        d = make_driver(fake)
        run(d.start())
        self.assertEqual(d.missing_tags(), [])

    def test_load_and_status_unload(self):
        fake = FakeOllama()
        d = make_driver(fake, num_ctx={"live": 4096})

        async def go():
            await d.start()
            url = await d.load("a", "live")
            st = await d.status()
            await d.unload("a")
            st2 = await d.status()
            return url, st, st2

        url, st, st2 = run(go())
        self.assertEqual(url, "http://x:11434")
        self.assertEqual(st, {"a": "loaded", "b": "unloaded"})
        self.assertEqual(st2["a"], "unloaded")
        gen = [c for c in fake.calls if c[1] == "/api/generate"]
        self.assertEqual(gen[0][2]["options"]["num_ctx"], 4096)
        self.assertEqual(gen[0][2]["keep_alive"], -1)
        self.assertNotIn("prompt", gen[0][2])
        self.assertEqual(gen[1][2], {"model": "alpha:7b", "keep_alive": 0})

    def test_load_uses_profile_ctx_default(self):
        fake = FakeOllama()
        d = make_driver(fake)

        async def go():
            await d.start()
            await d.load("a", "batch")

        run(go())
        gen = [c for c in fake.calls if c[1] == "/api/generate"][0]
        self.assertEqual(gen[2]["options"]["num_ctx"], 8192)

    def test_missing_tag_raises(self):
        fake = FakeOllama()
        d = make_driver(fake)

        async def go():
            await d.start()
            await d.load("b", "live")

        with self.assertRaises(RuntimeError) as cm:
            run(go())
        self.assertIn("beta:1b", str(cm.exception))

    def test_no_tag_model(self):
        d = make_driver(FakeOllama())
        with self.assertRaises(ValueError):
            d.tag_for("c")


if __name__ == "__main__":
    unittest.main()
