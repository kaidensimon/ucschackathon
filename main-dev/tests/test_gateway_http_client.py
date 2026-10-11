import asyncio
import json
import unittest

import httpx

from council.core.schemas import CallSpec
from council.gateway.http_client import OpenAIClient

SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}}


def run(coro):
    return asyncio.run(coro)


def make(handler):
    return OpenAIClient("http://x", httpx.AsyncClient(transport=httpx.MockTransport(handler)))


class NonStreamTests(unittest.TestCase):
    def test_ok(self):
        seen = {}

        def handler(req):
            seen["url"] = str(req.url)
            seen["body"] = json.loads(req.content)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": '{"a": 1}', "reasoning_content": "hmm"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 7},
                "timings": {"prompt_ms": 10.0, "predicted_ms": 70.0, "predicted_per_second": 100.0},
            })

        spec = CallSpec(model_id="m", messages=[{"role": "user", "content": "hi"}],
                        json_schema=SCHEMA, temperature=0.5, top_p=0.9, seed=3)
        res = run(make(handler).chat(spec, extra_fields={"foo": "bar"}))
        self.assertTrue(res.ok)
        self.assertEqual(res.content, '{"a": 1}')
        self.assertEqual(res.parsed, {"a": 1})
        self.assertEqual(res.reasoning_text, "hmm")
        self.assertEqual((res.tokens_in, res.tokens_out), (5, 7))
        self.assertEqual((res.prompt_ms, res.gen_ms, res.tps), (10.0, 70.0, 100.0))
        self.assertEqual(seen["url"], "http://x/v1/chat/completions")
        b = seen["body"]
        self.assertEqual(b["model"], "m")
        self.assertEqual(b["foo"], "bar")
        self.assertEqual(b["seed"], 3)
        self.assertFalse(b["stream"])
        self.assertEqual(b["response_format"]["json_schema"]["strict"], True)
        self.assertEqual(b["response_format"]["json_schema"]["schema"], SCHEMA)

    def test_prompt_mode(self):
        seen = {}

        def handler(req):
            seen["body"] = json.loads(req.content)
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

        spec = CallSpec(model_id="m", messages=[{"role": "user", "content": "hi"}], json_schema=SCHEMA)
        res = run(make(handler).chat(spec, mode="prompt"))
        self.assertTrue(res.ok)
        self.assertNotIn("response_format", seen["body"])
        self.assertEqual(len(seen["body"]["messages"]), 2)
        self.assertIn("JSON", seen["body"]["messages"][-1]["content"])
        self.assertEqual(len(spec.messages), 1)

    def test_500(self):
        res = run(make(lambda r: httpx.Response(503)).chat(CallSpec(model_id="m")))
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "server_error")

    def test_timeout(self):
        def handler(req):
            raise httpx.ReadTimeout("slow", request=req)

        res = run(make(handler).chat(CallSpec(model_id="m")))
        self.assertEqual(res.error, "timeout")

    def test_connect_error(self):
        def handler(req):
            raise httpx.ConnectError("nope", request=req)

        res = run(make(handler).chat(CallSpec(model_id="m")))
        self.assertEqual(res.error, "server_error")

    def test_bad_json(self):
        res = run(make(lambda r: httpx.Response(200, content=b"not json")).chat(CallSpec(model_id="m")))
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "server_error")


class StreamTests(unittest.TestCase):
    def test_stream(self):
        chunks = [
            {"choices": [{"delta": {"reasoning_content": "th"}}]},
            {"choices": [{"delta": {"reasoning_content": "ink"}}]},
            {"choices": [{"delta": {"content": "he"}}]},
            {"choices": [{"delta": {"content": "llo"}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 4, "completion_tokens": 2},
             "timings": {"prompt_ms": 1.5, "predicted_ms": 20.0, "predicted_per_second": 99.0}},
        ]
        text = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        text += 'data: {"choices":[{"delta":{"content":"IGNORED"}}]}\n\n'
        seen = {}

        def handler(req):
            seen["body"] = json.loads(req.content)
            return httpx.Response(200, content=text.encode(),
                                  headers={"content-type": "text/event-stream"})

        deltas = []
        spec = CallSpec(model_id="m", stream=True, messages=[{"role": "user", "content": "hi"}])
        res = run(make(handler).chat(spec, on_delta=lambda k, t: deltas.append((k, t))))
        self.assertTrue(seen["body"]["stream"])
        self.assertTrue(res.ok)
        self.assertEqual(res.content, "hello")
        self.assertEqual(res.reasoning_text, "think")
        self.assertEqual(res.finish_reason, "stop")
        self.assertEqual((res.tokens_in, res.tokens_out), (4, 2))
        self.assertEqual(res.tps, 99.0)
        self.assertEqual(deltas, [("reasoning", "th"), ("reasoning", "ink"),
                                  ("content", "he"), ("content", "llo")])

    def test_stream_500(self):
        spec = CallSpec(model_id="m", stream=True)
        res = run(make(lambda r: httpx.Response(500)).chat(spec))
        self.assertEqual(res.error, "server_error")

    def test_stream_timeout(self):
        def handler(req):
            raise httpx.ConnectTimeout("slow", request=req)

        res = run(make(handler).chat(CallSpec(model_id="m", stream=True)))
        self.assertEqual(res.error, "timeout")


if __name__ == "__main__":
    unittest.main()
