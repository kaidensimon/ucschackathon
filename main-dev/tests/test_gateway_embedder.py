"""Tests for council.gateway.embedder. Mock mode only: no model server, no network."""

from __future__ import annotations

import asyncio
import json
import unittest

import httpx

from council.chronicle.recall import keyword_embedding
from council.gateway.embedder import MockEmbedder, OllamaEmbedder, OpenAIEmbedder


def run(coro):
    return asyncio.run(coro)


class FakeOllama:
    def __init__(self, result=None, exc: Exception | None = None):
        self.result = result
        self.exc = exc
        self.calls: list[tuple[str, list[str]]] = []

    async def embed(self, model_tag, inputs):
        self.calls.append((model_tag, list(inputs)))
        if self.exc is not None:
            raise self.exc
        return self.result


class MockEmbedderTests(unittest.TestCase):
    def test_empty_input_returns_empty(self):
        self.assertEqual(run(MockEmbedder().embed([])), [])

    def test_matches_keyword_embedding(self):
        out = run(MockEmbedder(dim=32).embed(["hello world", "other"]))
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0], keyword_embedding("hello world", 32))
        self.assertEqual(out[1], keyword_embedding("other", 32))
        self.assertEqual(len(out[0]), 32)

    def test_default_dim_is_64(self):
        out = run(MockEmbedder().embed(["abc"]))
        self.assertEqual(len(out[0]), 64)

    def test_deterministic(self):
        a = run(MockEmbedder().embed(["same text here"]))
        b = run(MockEmbedder().embed(["same text here"]))
        self.assertEqual(a, b)


class OllamaEmbedderTests(unittest.TestCase):
    def test_empty_input_returns_empty_and_skips_client(self):
        client = FakeOllama(result=[])
        self.assertEqual(run(OllamaEmbedder(client, "m").embed([])), [])
        self.assertEqual(client.calls, [])

    def test_passes_model_and_inputs_and_returns_vectors(self):
        client = FakeOllama(result=[[1.0, 2.0], [3.0, 4.0]])
        out = run(OllamaEmbedder(client, "nomic").embed(["a", "b"]))
        self.assertEqual(out, [[1.0, 2.0], [3.0, 4.0]])
        self.assertEqual(client.calls, [("nomic", ["a", "b"])])

    def test_accepts_embeddings_dict(self):
        client = FakeOllama(result={"embeddings": [[0.5, 0.25]]})
        self.assertEqual(run(OllamaEmbedder(client, "m").embed(["x"])), [[0.5, 0.25]])

    def test_exception_gives_zero_vectors_of_right_count(self):
        client = FakeOllama(exc=RuntimeError("boom"))
        out = run(OllamaEmbedder(client, "m", dim=8).embed(["a", "b", "c"]))
        self.assertEqual(out, [[0.0] * 8] * 3)

    def test_wrong_count_gives_zero_vectors(self):
        client = FakeOllama(result=[[1.0, 2.0]])
        out = run(OllamaEmbedder(client, "m", dim=2).embed(["a", "b"]))
        self.assertEqual(out, [[0.0, 0.0], [0.0, 0.0]])

    def test_ragged_or_bad_result_gives_zero_vectors(self):
        for bad in (None, "nope", [[1.0], [1.0, 2.0]], [[]], [["x"]]):
            client = FakeOllama(result=bad)
            out = run(OllamaEmbedder(client, "m", dim=3).embed(["a", "b"]))
            self.assertEqual(out, [[0.0, 0.0, 0.0]] * 2, msg=repr(bad))


def _openai_transport(handler):
    return httpx.MockTransport(handler)


class OpenAIEmbedderTests(unittest.TestCase):
    def test_empty_input_returns_empty_without_request(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, json={"data": []})

        async def go():
            async with httpx.AsyncClient(transport=_openai_transport(handler)) as c:
                return await OpenAIEmbedder("http://h", "m", client=c).embed([])

        self.assertEqual(run(go()), [])
        self.assertEqual(seen, [])

    def test_posts_to_v1_embeddings_and_sorts_by_index(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": 1, "embedding": [0.0, 1.0]},
                        {"index": 0, "embedding": [1.0, 0.0]},
                    ]
                },
            )

        async def go():
            async with httpx.AsyncClient(transport=_openai_transport(handler)) as c:
                return await OpenAIEmbedder("http://localhost:11434/", "bge", client=c).embed(["a", "b"])

        out = run(go())
        self.assertEqual(out, [[1.0, 0.0], [0.0, 1.0]])
        self.assertEqual(seen["url"], "http://localhost:11434/v1/embeddings")
        self.assertEqual(seen["body"], {"model": "bge", "input": ["a", "b"]})

    def test_http_error_gives_zero_vectors(self):
        def handler(request):
            return httpx.Response(500, json={"error": "down"})

        async def go():
            async with httpx.AsyncClient(transport=_openai_transport(handler)) as c:
                return await OpenAIEmbedder("http://h", "m", client=c, dim=4).embed(["a"])

        self.assertEqual(run(go()), [[0.0, 0.0, 0.0, 0.0]])

    def test_connection_failure_gives_zero_vectors(self):
        def handler(request):
            raise httpx.ConnectError("refused", request=request)

        async def go():
            async with httpx.AsyncClient(transport=_openai_transport(handler)) as c:
                return await OpenAIEmbedder("http://h", "m", client=c, dim=2).embed(["a", "b"])

        self.assertEqual(run(go()), [[0.0, 0.0]] * 2)

    def test_malformed_body_gives_zero_vectors(self):
        def handler(request):
            return httpx.Response(200, json={"nothing": True})

        async def go():
            async with httpx.AsyncClient(transport=_openai_transport(handler)) as c:
                return await OpenAIEmbedder("http://h", "m", client=c, dim=2).embed(["a"])

        self.assertEqual(run(go()), [[0.0, 0.0]])

    def test_count_mismatch_gives_zero_vectors(self):
        def handler(request):
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})

        async def go():
            async with httpx.AsyncClient(transport=_openai_transport(handler)) as c:
                return await OpenAIEmbedder("http://h", "m", client=c, dim=1).embed(["a", "b"])

        self.assertEqual(run(go()), [[0.0], [0.0]])


if __name__ == "__main__":
    unittest.main()
