import json
import unittest

import httpx

from council.core.schemas import CallResult, CallSpec
from council.gateway.llamacpp_client import LlamaCppClient, thinking_fields

SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}}


def make(handler, **kw):
    return LlamaCppClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **kw)


def spec(**kw):
    return CallSpec(model_id="m", messages=[{"role": "user", "content": "hi"}], **kw)


class LlamaCppClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_stream(self):
        seen = {}

        def handler(req):
            seen["url"] = str(req.url)
            seen["body"] = json.loads(req.content)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": '{"a": 1}', "reasoning_content": "hmm"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20,
                          "completion_tokens_details": {"reasoning_tokens": 5}},
                "timings": {"prompt_ms": 50.0, "predicted_ms": 1000.0, "predicted_per_second": 20.0,
                            "predicted_n": 20, "prompt_n": 10, "draft_n": 30, "draft_n_accepted": 24},
            })

        c = make(handler, base_url="http://box:8080/")
        r = await c.chat(spec(json_schema=SCHEMA, temperature=0.2, top_p=0.9, seed=3,
                              max_output_tokens=100, max_reasoning_tokens=50),
                         model_tag="tag")
        self.assertIsInstance(r, CallResult)
        self.assertTrue(r.ok)
        self.assertEqual(r.parsed, {"a": 1})
        self.assertEqual(r.reasoning_text, "hmm")
        self.assertEqual((r.tokens_in, r.tokens_out, r.tokens_reasoning), (10, 20, 5))
        self.assertAlmostEqual(r.gen_ms, 1000.0)
        self.assertAlmostEqual(r.prompt_ms, 50.0)
        self.assertAlmostEqual(r.tps, 20.0)
        self.assertEqual(r.finish_reason, "stop")
        self.assertEqual(r.extra["draft_n"], 30)
        self.assertEqual(r.extra["draft_n_accepted"], 24)
        self.assertAlmostEqual(r.extra["accept_rate"], 0.8)
        b = seen["body"]
        self.assertEqual(seen["url"], "http://box:8080/v1/chat/completions")
        self.assertEqual(b["model"], "tag")
        self.assertEqual(b["max_tokens"], 150)
        self.assertEqual(b["seed"], 3)
        self.assertFalse(b["stream"])
        self.assertEqual(b["response_format"], {
            "type": "json_schema", "json_schema": {"name": "out", "schema": SCHEMA, "strict": True}})

    async def test_no_draft_means_no_draft_keys(self):
        def handler(req):
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "yo"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2},
                "timings": {"predicted_n": 2, "prompt_n": 1, "predicted_ms": 500.0},
            })

        r = await make(handler).chat(spec())
        self.assertTrue(r.ok)
        self.assertNotIn("draft_n", r.extra)
        self.assertNotIn("accept_rate", r.extra)
        self.assertAlmostEqual(r.tps, 4.0)  # fallback: tokens / gen seconds

    async def test_tokens_fall_back_to_timings(self):
        def handler(req):
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "x"}}],
                "timings": {"predicted_n": 7, "prompt_n": 3, "predicted_per_second": 9.0},
            })

        r = await make(handler).chat(spec())
        self.assertEqual((r.tokens_in, r.tokens_out), (3, 7))
        self.assertEqual(r.tps, 9.0)

    async def test_prompt_mode_and_options_and_extra_fields(self):
        seen = {}

        def handler(req):
            seen["body"] = json.loads(req.content)
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

        await make(handler).chat(spec(json_schema=SCHEMA), extra_fields={"cache_prompt": True},
                                 mode="prompt", options={"top_k": 40})
        b = seen["body"]
        self.assertNotIn("response_format", b)
        self.assertEqual(b["messages"][-1]["role"], "system")
        self.assertTrue(b["cache_prompt"])
        self.assertEqual(b["top_k"], 40)

    async def test_bad_json_gives_parsed_none(self):
        def handler(req):
            return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

        r = await make(handler).chat(spec(json_schema=SCHEMA))
        self.assertTrue(r.ok)
        self.assertIsNone(r.parsed)

    async def test_http_error(self):
        r = await make(lambda req: httpx.Response(500, text="boom")).chat(spec())
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "server_error")

    async def test_garbage_body(self):
        r = await make(lambda req: httpx.Response(200, text="<html>")).chat(spec())
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "server_error")

    async def test_timeout(self):
        def handler(req):
            raise httpx.ReadTimeout("slow", request=req)

        r = await make(handler).chat(spec())
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "timeout")

    async def test_connect_error(self):
        def handler(req):
            raise httpx.ConnectError("down", request=req)

        r = await make(handler).chat(spec())
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "server_error")

    async def test_stream(self):
        seen = {}
        chunks = [
            {"choices": [{"delta": {"reasoning_content": "th"}}]},
            {"choices": [{"delta": {"content": "he"}}]},
            {"choices": [{"delta": {"content": "llo"}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 4, "completion_tokens": 6},
             "timings": {"predicted_per_second": 12.0, "predicted_ms": 500.0, "prompt_ms": 20.0,
                         "draft_n": 10, "draft_n_accepted": 5}},
        ]
        text = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"

        def handler(req):
            seen["body"] = json.loads(req.content)
            return httpx.Response(200, text=text)

        deltas = []
        r = await make(handler).chat(spec(stream=True), on_delta=lambda k, t: deltas.append((k, t)))
        self.assertTrue(seen["body"]["stream"])
        self.assertTrue(r.ok)
        self.assertEqual(r.content, "hello")
        self.assertEqual(r.reasoning_text, "th")
        self.assertEqual(r.finish_reason, "stop")
        self.assertEqual((r.tokens_in, r.tokens_out), (4, 6))
        self.assertEqual(r.tps, 12.0)
        self.assertEqual(r.extra["draft_n_accepted"], 5)
        self.assertEqual(deltas, [("reasoning", "th"), ("content", "he"), ("content", "llo")])

    async def test_stream_http_error(self):
        r = await make(lambda req: httpx.Response(503)).chat(spec(stream=True))
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "server_error")

    async def test_thinking_fields(self):
        self.assertEqual(thinking_fields("off"), {"chat_template_kwargs": {"enable_thinking": False}})
        on = thinking_fields("council")
        self.assertTrue(on["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(on["reasoning_format"], "deepseek")
        self.assertEqual(thinking_fields("max"), on)

    async def test_optional_fields_sent_and_card_wins(self):
        bodies = []

        def handler(req):
            bodies.append(json.loads(req.content))
            return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

        r = await make(handler).chat(spec(), optional_fields=thinking_fields("off"))
        self.assertTrue(r.ok)
        self.assertEqual(len(bodies), 1)
        self.assertEqual(bodies[0]["chat_template_kwargs"], {"enable_thinking": False})
        await make(handler).chat(spec(), extra_fields={"chat_template_kwargs": {"enable_thinking": True}},
                                 optional_fields=thinking_fields("off"))
        self.assertEqual(bodies[1]["chat_template_kwargs"], {"enable_thinking": True})

    async def test_optional_fields_dropped_on_4xx(self):
        for stream in (False, True):
            bodies = []

            def handler(req):
                body = json.loads(req.content)
                bodies.append(body)
                if "chat_template_kwargs" in body:
                    return httpx.Response(400, json={"error": "unknown field"})
                if body["stream"]:
                    chunk = {"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}
                    return httpx.Response(200, text=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")
                return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

            deltas = []
            r = await make(handler).chat(spec(stream=stream), extra_fields={"cache_prompt": True},
                                         on_delta=lambda k, t: deltas.append(t),
                                         optional_fields=thinking_fields("off"))
            self.assertTrue(r.ok, stream)
            self.assertEqual(r.content, "ok")
            self.assertEqual(len(bodies), 2)
            self.assertNotIn("chat_template_kwargs", bodies[1])
            self.assertTrue(bodies[1]["cache_prompt"])  # only the optional fields are dropped
            self.assertEqual(deltas, ["ok"] if stream else [])

    async def test_no_retry_on_5xx_or_without_optional_fields(self):
        hits = []

        def handler(req):
            hits.append(1)
            return httpx.Response(500 if len(hits) == 1 else 400)

        r = await make(handler).chat(spec(), optional_fields=thinking_fields("off"))
        self.assertEqual((r.ok, r.error, len(hits)), (False, "server_error", 1))
        r = await make(handler).chat(spec())
        self.assertEqual((r.ok, r.error, len(hits)), (False, "server_error", 2))

    async def test_both_tries_rejected_is_server_error(self):
        hits = []

        def handler(req):
            hits.append(1)
            return httpx.Response(400)

        r = await make(handler).chat(spec(), optional_fields=thinking_fields("off"))
        self.assertEqual((r.ok, r.error, len(hits)), (False, "server_error", 2))


if __name__ == "__main__":
    unittest.main()
