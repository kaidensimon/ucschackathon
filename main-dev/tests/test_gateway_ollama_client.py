import json
import unittest

import httpx

from council.core.schemas import CallSpec
from council.gateway.ollama_client import OllamaClient

SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}}


def make(handler, **kw):
    return OllamaClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **kw)


class OllamaClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_stream(self):
        seen = {}

        def handler(req):
            seen["url"] = str(req.url)
            seen["body"] = json.loads(req.content)
            return httpx.Response(200, json={
                "message": {"content": '{"a": 1}', "thinking": "hmm"},
                "done": True, "done_reason": "stop",
                "prompt_eval_count": 10, "eval_count": 20,
                "eval_duration": 1_000_000_000, "prompt_eval_duration": 50_000_000,
                "logprobs": [{"token": "x", "logprob": -0.5}, {"token": "y", "logprob": -1.5}],
            })

        c = make(handler, num_ctx=4096)
        spec = CallSpec(model_id="m", messages=[{"role": "user", "content": "hi"}],
                        json_schema=SCHEMA, temperature=0.2, top_p=0.9, seed=3,
                        max_output_tokens=100, max_reasoning_tokens=50)
        r = await c.chat(spec, extra_fields={"think": True}, model_tag="qwen3:8b")
        self.assertTrue(r.ok)
        self.assertEqual(r.parsed, {"a": 1})
        self.assertEqual(r.reasoning_text, "hmm")
        self.assertEqual((r.tokens_in, r.tokens_out), (10, 20))
        self.assertAlmostEqual(r.gen_ms, 1000.0)
        self.assertAlmostEqual(r.prompt_ms, 50.0)
        self.assertAlmostEqual(r.tps, 20.0)
        self.assertEqual(r.logprobs, [-0.5, -1.5])
        self.assertEqual(r.finish_reason, "stop")
        b = seen["body"]
        self.assertTrue(seen["url"].endswith("/api/chat"))
        self.assertEqual(b["model"], "qwen3:8b")
        self.assertEqual(b["format"], SCHEMA)
        self.assertTrue(b["think"])
        self.assertEqual(b["keep_alive"], -1)
        self.assertEqual(b["options"]["num_predict"], 150)
        self.assertEqual(b["options"]["num_ctx"], 4096)
        self.assertEqual(b["options"]["seed"], 3)
        self.assertFalse(b["stream"])

    async def test_options_merged_last(self):
        seen = {}

        def handler(req):
            seen["body"] = json.loads(req.content)
            return httpx.Response(200, json={"message": {"content": "{}"}, "done": True})

        c = make(handler, num_ctx=4096)
        spec = CallSpec(model_id="m", messages=[{"role": "user", "content": "hi"}],
                        temperature=0.2, max_output_tokens=100)
        await c.chat(spec, options={"draft_num_predict": 4, "temperature": 0.9, "weird": [1]})
        o = seen["body"]["options"]
        self.assertEqual(o["draft_num_predict"], 4)
        self.assertEqual(o["temperature"], 0.9)  # options override spec-derived values
        self.assertEqual(o["weird"], [1])  # unknown passes through untouched
        self.assertEqual(o["num_ctx"], 4096)
        await c.chat(spec)
        self.assertNotIn("draft_num_predict", seen["body"]["options"])

    async def test_prompt_mode(self):
        seen = {}

        def handler(req):
            seen["body"] = json.loads(req.content)
            return httpx.Response(200, json={"message": {"content": "{}"}, "done": True})

        c = make(handler)
        spec = CallSpec(model_id="m", messages=[{"role": "user", "content": "hi"}], json_schema=SCHEMA)
        r = await c.chat(spec, mode="prompt")
        self.assertTrue(r.ok)
        self.assertNotIn("format", seen["body"])
        self.assertEqual(len(seen["body"]["messages"]), 2)
        self.assertEqual(len(spec.messages), 1)

    async def test_stream(self):
        lines = [
            {"message": {"thinking": "t1"}, "done": False},
            {"message": {"content": "he"}, "done": False},
            {"message": {"content": "llo"}, "done": False},
            {"message": {"content": ""}, "done": True, "done_reason": "stop",
             "prompt_eval_count": 4, "eval_count": 8, "eval_duration": 2_000_000_000,
             "prompt_eval_duration": 10_000_000},
        ]
        data = "\n".join(json.dumps(x) for x in lines) + "\n"

        def handler(req):
            return httpx.Response(200, content=data.encode())

        deltas = []
        c = make(handler)
        spec = CallSpec(model_id="m", stream=True)
        r = await c.chat(spec, on_delta=lambda k, t: deltas.append((k, t)))
        self.assertTrue(r.ok)
        self.assertEqual(r.content, "hello")
        self.assertEqual(r.reasoning_text, "t1")
        self.assertEqual(deltas, [("reasoning", "t1"), ("content", "he"), ("content", "llo")])
        self.assertEqual((r.tokens_in, r.tokens_out), (4, 8))
        self.assertAlmostEqual(r.tps, 4.0)

    async def test_errors(self):
        def timeout(req):
            raise httpx.ReadTimeout("slow")

        def boom(req):
            raise httpx.ConnectError("down")

        def bad(req):
            return httpx.Response(500, text="no")

        spec = CallSpec(model_id="m")
        self.assertEqual((await make(timeout).chat(spec)).error, "timeout")
        self.assertEqual((await make(boom).chat(spec)).error, "server_error")
        self.assertEqual((await make(bad).chat(spec)).error, "server_error")
        r = await make(bad).chat(CallSpec(model_id="m", stream=True))
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "server_error")

    async def test_embed(self):
        seen = {}

        def handler(req):
            seen["url"] = str(req.url)
            seen["body"] = json.loads(req.content)
            return httpx.Response(200, json={"embeddings": [[1, 2], [3, 4]]})

        out = await make(handler).embed("nomic-embed-text", ["a", "b"])
        self.assertEqual(out, [[1.0, 2.0], [3.0, 4.0]])
        self.assertTrue(seen["url"].endswith("/api/embed"))
        self.assertEqual(seen["body"]["input"], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
