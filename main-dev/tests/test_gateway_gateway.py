import asyncio
import json
import unittest

import httpx

from council.core import event_types as ev
from council.core.config import Config
from council.core.events import EventBus
from council.core.schemas import CallResult, CallSpec, ModelEntry, ServeConfig, ServeProfile
from council.core.store import Store
from council.gateway.gateway import Gateway
from council.gateway.mock import MockResponder

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "confidence": {"type": "number"}},
    "required": ["answer", "confidence"],
}


def entry(model_id, parallel=2, **kw):
    return ModelEntry(id=model_id, serve=ServeConfig(live=ServeProfile(ctx=4096, parallel=parallel)), **kw)


def spec(model_id="m1", **kw):
    base = dict(model_id=model_id, run_id="run1", purpose="seat.r0",
                messages=[{"role": "user", "content": "pick a rate limiter"}], json_schema=SCHEMA)
    base.update(kw)
    return CallSpec(**base)


class CountingResponder:
    """Wraps a responder and tracks how many calls run at once, in total and per model."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0
        self.live = {}
        self.max_per_model = 0
        self.max_models = 0

    async def respond(self, s, on_delta=None):
        self.calls += 1
        self.live[s.model_id] = self.live.get(s.model_id, 0) + 1
        self.max_per_model = max(self.max_per_model, self.live[s.model_id])
        self.max_models = max(self.max_models, len(self.live))
        try:
            return await self.inner.respond(s, on_delta)
        finally:
            self.live[s.model_id] -= 1
            if not self.live[s.model_id]:
                del self.live[s.model_id]


class BadResponder:
    async def respond(self, s, on_delta=None):
        return CallResult(call_id=s.call_id, ok=True, model_id=s.model_id, content="no json here",
                          tokens_in=3, tokens_out=3)


class FakeClient:
    def __init__(self, content):
        self.content = content
        self.seen = []

    async def chat(self, s, extra_fields=None, mode="grammar", on_delta=None):
        self.seen.append((mode, dict(extra_fields or {})))
        return CallResult(call_id=s.call_id, ok=True, model_id=s.model_id, content=self.content,
                          tokens_in=5, tokens_out=10, gen_ms=500.0)


class FakeOllama:
    """Same surface as OllamaClient: chat takes model_tag, embed takes (tag, inputs)."""

    def __init__(self, content='{"answer": "x", "confidence": 0.7}', logprobs=None):
        self.content = content
        self.logprobs = logprobs
        self.chats = []
        self.embeds = []

    async def chat(self, s, extra_fields=None, mode="grammar", on_delta=None, model_tag=None,
                   options=None):
        self.chats.append({"spec": s, "extra": dict(extra_fields or {}), "mode": mode, "tag": model_tag,
                           "options": dict(options or {})})
        return CallResult(call_id=s.call_id, ok=True, model_id=s.model_id, content=self.content,
                          tokens_in=5, tokens_out=10, gen_ms=500.0, logprobs=self.logprobs)

    async def embed(self, model_tag, inputs):
        self.embeds.append((model_tag, list(inputs)))
        return [[float(len(t)), 1.0] for t in inputs]


ANSWER = '{"answer": "x", "confidence": 0.7}'
LONG = "HEAD " + "filler words " * 4000 + " TAIL what is the answer?"


def llama_reply(content=ANSWER, reasoning=None):
    message = {"content": content}
    if reasoning:
        message["reasoning_content"] = reasoning
    return httpx.Response(200, json={
        "choices": [{"message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 10},
        "timings": {"predicted_ms": 500.0, "predicted_per_second": 20.0, "predicted_n": 10, "prompt_n": 5},
    })


def llama_client(handler):
    from council.gateway.llamacpp_client import LlamaCppClient

    bodies = []

    def wrapped(req):
        bodies.append(json.loads(req.content))
        return handler(req)

    client = LlamaCppClient("http://box:18101", client=httpx.AsyncClient(transport=httpx.MockTransport(wrapped)))
    return client, bodies


class GatewayTest(unittest.IsolatedAsyncioTestCase):
    def make(self, responder=None, registry=None, mock=True, max_models=2, driver=None,
             server_parallel=None, **kw):
        cfg = Config()
        if driver is not None:
            cfg.host.driver = driver
        if server_parallel is not None:
            cfg.llamacpp.parallel = server_parallel  # the slots llama-server is started with
        cfg.gateway.mock = mock
        cfg.gateway.max_concurrent_models = max_models
        self.store = Store(":memory:")
        self.bus = EventBus(self.store)
        self.events = []
        self.bus.add_listener(self.events.append)
        if mock and responder is None:
            responder = MockResponder(seed=1)
        return Gateway(cfg, registry if registry is not None else [entry("m1")], self.store, self.bus,
                       responder=responder, **kw)

    def types(self):
        return [e.type for e in self.events]

    async def test_mock_needs_responder(self):
        cfg = Config()
        cfg.gateway.mock = True
        with self.assertRaises(ValueError):
            Gateway(cfg, [], Store(":memory:"), None)

    async def test_structured_success(self):
        gw = self.make()
        res = await gw.call(spec(), seat_no=2, round=1)
        self.assertTrue(res.ok)
        self.assertIsNone(res.error)
        self.assertIsInstance(res.parsed, dict)
        self.assertIn("answer", res.parsed)
        self.assertFalse(res.cached)
        turns = self.store.list_turns("run1")
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["seat_no"], 2)
        self.assertEqual(turns[0]["round"], 1)
        self.assertTrue(turns[0]["ok"])
        st = gw.stats()
        self.assertEqual(st["tokens_out"], res.tokens_out)
        self.assertEqual(st["tokens_in"], res.tokens_in)
        self.assertGreater(st["tps_by_model"]["m1"], 0)
        self.assertEqual(st["tps_total"], st["tps_by_model"]["m1"])
        self.assertEqual(st["in_flight"], {})
        self.assertEqual(st["queue_depth"], 0)

    async def test_plain_text_call(self):
        gw = self.make()
        res = await gw.call(spec(json_schema=None))
        self.assertTrue(res.ok)
        self.assertTrue(res.content)
        self.assertIsNone(res.parsed)

    async def test_cache_hit(self):
        counting = CountingResponder(MockResponder(seed=1))
        gw = self.make(responder=counting)
        first = await gw.call(spec(cacheable=True, seed=7))
        second = await gw.call(spec(cacheable=True, seed=7))
        self.assertTrue(first.ok and second.ok)
        self.assertFalse(first.cached)
        self.assertTrue(second.cached)
        self.assertNotEqual(first.call_id, second.call_id)
        self.assertEqual(second.parsed, first.parsed)
        self.assertEqual(counting.calls, 1)
        self.assertEqual(gw.stats()["cache_hits"], 1)
        self.assertEqual(gw.stats()["tokens_out"], first.tokens_out)  # cached tokens not counted twice
        done = [e for e in self.events if e.type == ev.TURN_COMPLETED]
        self.assertEqual([e.payload["cached"] for e in done], [False, True])

    async def test_no_cache_without_seed(self):
        counting = CountingResponder(MockResponder(seed=1))
        gw = self.make(responder=counting)
        await gw.call(spec(cacheable=True))
        res = await gw.call(spec(cacheable=True))
        self.assertFalse(res.cached)
        self.assertEqual(counting.calls, 2)

    async def test_timeout(self):
        gw = self.make(responder=MockResponder(seed=1, delay=(0.5, 0.5)))
        res = await gw.call(spec(timeout_s=0.05))
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "timeout")
        self.assertEqual(self.types(), [ev.TURN_STARTED, ev.TURN_TIMEOUT])
        self.assertEqual(gw.stats()["in_flight"], {})
        self.assertEqual(gw.stats()["calls_failed"], 1)
        self.assertEqual(self.store.list_turns("run1")[0]["error"], "timeout")

    async def test_invalid_output(self):
        gw = self.make(responder=BadResponder())
        res = await gw.call(spec())
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "invalid_output")
        self.assertIsNone(res.parsed)
        self.assertEqual(self.types(), [ev.TURN_STARTED, ev.TURN_INVALID])
        self.assertEqual(self.events[-1].payload["error"], "invalid_output")

    async def test_governor_per_model_limit(self):
        counting = CountingResponder(MockResponder(seed=1, delay=(0.02, 0.02)))
        gw = self.make(responder=counting, registry=[entry("m1", parallel=2)])
        results = await gw.call_many([spec() for _ in range(7)])
        self.assertEqual(len(results), 7)
        self.assertTrue(all(r.ok for r in results))
        self.assertEqual(counting.max_per_model, 2)

    async def test_governor_distinct_model_limit(self):
        counting = CountingResponder(MockResponder(seed=1, delay=(0.02, 0.02)))
        gw = self.make(responder=counting, registry=[entry("m1"), entry("m2"), entry("m3")], max_models=1)
        specs = [spec(model_id=m) for m in ("m1", "m2", "m3", "m1", "m2", "m3")]
        results = await gw.call_many(specs)
        self.assertEqual([r.model_id for r in results], [s.model_id for s in specs])
        self.assertTrue(all(r.ok for r in results))
        self.assertEqual(counting.max_models, 1)

    async def test_events_in_order(self):
        gw = self.make()
        s = spec(stream=True)
        res = await gw.call(s, seat_no=0, round=0)
        types = self.types()
        self.assertEqual(types[0], ev.TURN_STARTED)
        self.assertEqual(types[-1], ev.TURN_COMPLETED)
        self.assertGreater(len(types), 2)
        self.assertTrue(all(t == ev.TURN_DELTA for t in types[1:-1]))
        self.assertTrue(all(e.payload["call_id"] == s.call_id for e in self.events))
        self.assertEqual("".join(e.payload["text"] for e in self.events[1:-1]), res.content)
        done = self.events[-1].payload
        self.assertEqual(done["tokens"], res.tokens_out)
        self.assertEqual(done["parsed"], res.parsed)
        self.assertGreater(done["tps"], 0)
        # deltas are live only, never stored
        stored = [e.type for e in self.store.events_since("run1", 0)]
        self.assertEqual(stored, [ev.TURN_STARTED, ev.TURN_COMPLETED])

    async def test_no_deltas_without_stream(self):
        gw = self.make()
        await gw.call(spec())
        self.assertEqual(self.types(), [ev.TURN_STARTED, ev.TURN_COMPLETED])

    async def test_real_client_strips_reasoning(self):
        client = FakeClient('<think>hidden thoughts</think>{"answer": "x", "confidence": 0.7}')
        reg = [entry("m1", reasoning={"kind": "toggle", "council": {"enable_thinking": True}},
                     sampling={"temperature": 0.6})]
        gw = self.make(mock=False, registry=reg, clients={"m1": client})
        res = await gw.call(spec(reasoning="council", max_reasoning_tokens=100, max_output_tokens=200))
        self.assertTrue(res.ok)
        self.assertEqual(res.parsed, {"answer": "x", "confidence": 0.7})
        self.assertNotIn("think", res.content)
        self.assertEqual(res.reasoning_text, "hidden thoughts")
        self.assertEqual(res.tps, 20.0)
        mode, extra = client.seen[0]
        self.assertEqual(mode, "grammar")
        self.assertEqual(extra["enable_thinking"], True)
        self.assertEqual(extra["temperature"], 0.6)
        self.assertEqual(extra["max_tokens"], 300)

    async def test_no_endpoint_is_server_error(self):
        gw = self.make(mock=False, endpoint_for=lambda m: None)
        res = await gw.call(spec())
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "server_error")

    async def test_never_raises(self):
        class Boom:
            async def respond(self, s, on_delta=None):
                raise RuntimeError("boom")

        gw = self.make(responder=Boom())
        res = await gw.call(spec())
        self.assertFalse(res.ok)
        self.assertIn(res.error, ("invalid_output", "server_error"))
        res2 = await gw.call(spec(json_schema=None))
        self.assertFalse(res2.ok)
        self.assertEqual(res2.error, "server_error")

    # ------------------------------------------------------------------ ollama driver

    async def test_ollama_driver_builds_client_from_config(self):
        from council.gateway.ollama_client import OllamaClient

        gw = self.make(mock=False, driver="ollama")
        gw.config.ollama.base_url = "http://box:11434/"
        gw.config.ollama.keep_alive = "-1"
        gw.config.ollama.num_ctx_live = 4096
        client = gw._client("m1")
        self.assertIsInstance(client, OllamaClient)
        self.assertEqual(client.base_url, "http://box:11434")
        self.assertEqual(client.keep_alive, -1)
        self.assertEqual(client.num_ctx, 4096)
        self.assertIs(gw._client("m2"), client)  # one Ollama server, one client

    async def test_ollama_keep_alive_duration_string_kept(self):
        gw = self.make(mock=False, driver="ollama")
        gw.config.ollama.keep_alive = "5m"
        self.assertEqual(gw._client("m1").keep_alive, "5m")

    async def test_ollama_tag_and_override(self):
        fake = FakeOllama()
        reg = [entry("m1", ollama_tag="gemma3:12b"), entry("m2")]
        gw = self.make(mock=False, driver="ollama", registry=reg, clients={"m1": fake, "m2": fake})
        self.assertTrue((await gw.call(spec())).ok)
        self.assertEqual(fake.chats[-1]["tag"], "gemma3:12b")
        await gw.call(spec(model_id="m2"))
        self.assertEqual(fake.chats[-1]["tag"], "m2")  # no tag: fall back to the id
        gw.set_model_tag("m1", "gemma3:12b-council-v2")
        await gw.call(spec())
        self.assertEqual(fake.chats[-1]["tag"], "gemma3:12b-council-v2")
        gw.set_model_tag("m1", None)
        await gw.call(spec())
        self.assertEqual(fake.chats[-1]["tag"], "gemma3:12b")

    async def test_ollama_options_merge_order(self):
        fake = FakeOllama()
        reg = [entry("plain", ollama_options={"x": 1, "unknown_opt": "keep"}),
               entry("spec", speculative="mtp"),
               entry("both", speculative="draft", ollama_options={"draft_num_predict": 2})]
        gw = self.make(mock=False, driver="ollama", registry=reg,
                       clients={m: fake for m in ("plain", "spec", "both")})
        gw.config.ollama.default_draft_num_predict = 4
        await gw.call(spec(model_id="plain"))
        self.assertEqual(fake.chats[-1]["options"], {"x": 1, "unknown_opt": "keep"})  # no default: not speculative
        await gw.call(spec(model_id="spec"))
        self.assertEqual(fake.chats[-1]["options"], {"draft_num_predict": 4})
        await gw.call(spec(model_id="both"))
        self.assertEqual(fake.chats[-1]["options"], {"draft_num_predict": 2})  # entry value wins
        await gw.call(spec(model_id="both", meta={"ollama_options": {"draft_num_predict": 8}}))
        self.assertEqual(fake.chats[-1]["options"], {"draft_num_predict": 8})  # per-call wins
        gw.config.ollama.default_draft_num_predict = 0
        await gw.call(spec(model_id="spec"))
        self.assertEqual(fake.chats[-1]["options"], {})

    async def test_ollama_sampling_and_reasoning_fields(self):
        fake = FakeOllama()
        reg = [entry("m1", reasoning={"kind": "toggle", "council": {"think": True}},
                     sampling={"temperature": 0.6, "top_p": 0.9})]
        gw = self.make(mock=False, driver="ollama", registry=reg, clients={"m1": fake})
        await gw.call(spec(reasoning="council", max_reasoning_tokens=100, top_p=0.5))
        sent = fake.chats[0]
        self.assertEqual(sent["extra"], {"think": True})  # no OpenAI max_tokens / sampling keys
        self.assertEqual(sent["spec"].temperature, 0.6)   # card value fills the gap
        self.assertEqual(sent["spec"].top_p, 0.5)         # caller value wins

    async def test_logprobs_pass_through(self):
        fake = FakeOllama(logprobs=[-0.1, -0.2, -0.3])
        gw = self.make(mock=False, driver="ollama", clients={"m1": fake})
        res = await gw.call(spec())
        self.assertTrue(res.ok)
        self.assertEqual(res.logprobs, [-0.1, -0.2, -0.3])
        plain = await gw.call(spec(json_schema=None))
        self.assertEqual(plain.logprobs, [-0.1, -0.2, -0.3])

    async def test_logprobs_from_mock_responder(self):
        class WithLogprobs:
            async def respond(self, s, on_delta=None):
                return CallResult(call_id=s.call_id, ok=True, model_id=s.model_id,
                                  content='{"answer": "x", "confidence": 0.7}', logprobs=[-0.5, -0.25])

        gw = self.make(responder=WithLogprobs(), driver="ollama")
        res = await gw.call(spec())
        self.assertTrue(res.ok)
        self.assertEqual(res.logprobs, [-0.5, -0.25])

    async def test_other_driver_keeps_openai_path(self):
        client = FakeClient('{"answer": "x", "confidence": 0.7}')  # chat() has no model_tag
        gw = self.make(mock=False, clients={"m1": client})
        self.assertFalse(gw.uses_ollama)
        self.assertTrue((await gw.call(spec())).ok)

    # ------------------------------------------------------------------ llamacpp driver

    async def test_llamacpp_client_from_resolver(self):
        from council.gateway.llamacpp_client import LlamaCppClient

        urls = {"m1": "http://127.0.0.1:18101/", "m2": "http://127.0.0.1:18102"}
        asked = []

        def endpoint_for(model_id):
            asked.append(model_id)
            return urls.get(model_id)

        gw = self.make(mock=False, driver="llamacpp", endpoint_for=endpoint_for)
        self.assertTrue(gw.uses_llamacpp)
        self.assertFalse(gw.uses_ollama)
        c1 = gw._client("m1")
        self.assertIsInstance(c1, LlamaCppClient)
        self.assertEqual(c1.base_url, "http://127.0.0.1:18101")
        self.assertIs(gw._client("m1"), c1)
        self.assertEqual(gw._client("m2").base_url, "http://127.0.0.1:18102")
        urls["m1"] = "http://127.0.0.1:18109"  # the host restarted the model on another port
        self.assertEqual(gw._client("m1").base_url, "http://127.0.0.1:18109")
        self.assertEqual(asked, ["m1", "m1", "m2", "m1"])  # resolved per call
        self.assertIsNone(gw._client("m3"))

    async def test_llamacpp_no_endpoint_is_server_error(self):
        for resolver in (None, lambda m: None):
            gw = self.make(mock=False, driver="llamacpp", endpoint_for=resolver)
            res = await gw.call(spec())
            self.assertFalse(res.ok)
            self.assertEqual(res.error, "server_error")

    async def test_llamacpp_structured_call(self):
        client, bodies = llama_client(lambda req: llama_reply(reasoning="hmm"))
        reg = [entry("m1", sampling={"temperature": 0.6})]
        gw = self.make(mock=False, driver="llamacpp", registry=reg, clients={"m1": client})
        res = await gw.call(spec(), seat_no=1, round=0)
        self.assertTrue(res.ok)
        self.assertEqual(res.parsed, {"answer": "x", "confidence": 0.7})
        self.assertEqual(res.reasoning_text, "hmm")
        self.assertEqual((res.tokens_in, res.tokens_out, res.tps), (5, 10, 20.0))
        self.assertEqual(res.extra["trimmed"], False)
        body = bodies[0]
        self.assertEqual(body["response_format"]["json_schema"]["schema"], SCHEMA)
        self.assertEqual(body["temperature"], 0.6)
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})  # reasoning off
        self.assertNotIn("reasoning_format", body)
        self.assertEqual(body["messages"], [{"role": "user", "content": "pick a rate limiter"}])
        self.assertEqual(self.types(), [ev.TURN_STARTED, ev.TURN_COMPLETED])
        self.assertEqual(self.store.list_turns("run1")[0]["seat_no"], 1)
        self.assertEqual(gw.stats()["tps_by_model"]["m1"], 20.0)

    async def test_llamacpp_reasoning_levels(self):
        client, bodies = llama_client(lambda req: llama_reply())
        reg = [entry("m1"),
               entry("m2", reasoning={"kind": "toggle",
                                      "off": {"chat_template_kwargs": {"enable_thinking": False, "x": 1}}})]
        gw = self.make(mock=False, driver="llamacpp", registry=reg, clients={"m1": client, "m2": client})
        await gw.call(spec(reasoning="council", max_reasoning_tokens=100, max_output_tokens=200))
        self.assertEqual(bodies[-1]["chat_template_kwargs"], {"enable_thinking": True})
        self.assertEqual(bodies[-1]["reasoning_format"], "deepseek")
        self.assertEqual(bodies[-1]["max_tokens"], 300)
        await gw.call(spec(model_id="m2"))
        self.assertEqual(bodies[-1]["chat_template_kwargs"], {"enable_thinking": False, "x": 1})  # card wins
        await gw.call(spec(meta={"llamacpp_options": {"top_k": 40}}))
        self.assertEqual(bodies[-1]["top_k"], 40)

    async def test_llamacpp_thinking_switch_never_fails_a_call(self):
        def handler(req):
            if "chat_template_kwargs" in json.loads(req.content):
                return httpx.Response(400, json={"error": "unsupported"})
            return llama_reply()

        client, bodies = llama_client(handler)
        gw = self.make(mock=False, driver="llamacpp", clients={"m1": client})
        res = await gw.call(spec())
        self.assertTrue(res.ok)
        self.assertEqual(res.attempts, 1)
        self.assertEqual(len(bodies), 2)
        self.assertNotIn("chat_template_kwargs", bodies[1])

    async def test_llamacpp_streaming_deltas(self):
        chunks = [
            {"choices": [{"delta": {"reasoning_content": "think"}}]},
            {"choices": [{"delta": {"content": '{"answer": "x",'}}]},
            {"choices": [{"delta": {"content": ' "confidence": 0.7}'}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 4, "completion_tokens": 6},
             "timings": {"predicted_per_second": 12.0, "predicted_ms": 500.0}},
        ]
        text = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        client, bodies = llama_client(lambda req: httpx.Response(200, text=text))
        gw = self.make(mock=False, driver="llamacpp", clients={"m1": client})
        s = spec(stream=True)
        res = await gw.call(s, seat_no=0, round=0)
        self.assertTrue(bodies[0]["stream"])
        self.assertTrue(res.ok)
        self.assertEqual(res.parsed, {"answer": "x", "confidence": 0.7})
        self.assertEqual(res.reasoning_text, "think")
        self.assertEqual(self.types(), [ev.TURN_STARTED, ev.TURN_REASONING_DELTA, ev.TURN_DELTA,
                                        ev.TURN_DELTA, ev.TURN_COMPLETED])
        self.assertEqual("".join(e.payload["text"] for e in self.events if e.type == ev.TURN_DELTA),
                         res.content)
        self.assertTrue(all(e.payload["call_id"] == s.call_id for e in self.events))

    async def test_llamacpp_invalid_output_walks_the_ladder(self):
        client, bodies = llama_client(lambda req: llama_reply(content="no json here"))
        gw = self.make(mock=False, driver="llamacpp", clients={"m1": client})
        res = await gw.call(spec())
        self.assertFalse(res.ok)
        self.assertEqual(res.error, "invalid_output")
        self.assertGreater(len(bodies), 1)
        self.assertEqual(self.types()[-1], ev.TURN_INVALID)

    async def test_llamacpp_timeout_and_server_error(self):
        def slow(req):
            raise httpx.ReadTimeout("slow", request=req)

        client, _ = llama_client(slow)
        gw = self.make(mock=False, driver="llamacpp", clients={"m1": client})
        res = await gw.call(spec())
        self.assertEqual((res.ok, res.error), (False, "timeout"))
        self.assertEqual(self.types()[-1], ev.TURN_TIMEOUT)
        client, _ = llama_client(lambda req: httpx.Response(500))
        gw = self.make(mock=False, driver="llamacpp", clients={"m1": client})
        res = await gw.call(spec())
        self.assertEqual((res.ok, res.error), (False, "server_error"))

    async def test_llamacpp_gateway_timeout(self):
        async def hang(req):
            await asyncio.sleep(1.0)
            return llama_reply()

        from council.gateway.llamacpp_client import LlamaCppClient

        client = LlamaCppClient(client=httpx.AsyncClient(transport=httpx.MockTransport(hang)))
        gw = self.make(mock=False, driver="llamacpp", clients={"m1": client})
        res = await gw.call(spec(timeout_s=0.05))
        self.assertEqual((res.ok, res.error), (False, "timeout"))
        self.assertEqual(gw.stats()["in_flight"], {})

    async def test_llamacpp_cache(self):
        client, bodies = llama_client(lambda req: llama_reply())
        gw = self.make(mock=False, driver="llamacpp", clients={"m1": client})
        first = await gw.call(spec(cacheable=True, seed=7))
        second = await gw.call(spec(cacheable=True, seed=7))
        self.assertTrue(first.ok and second.ok)
        self.assertEqual((first.cached, second.cached), (False, True))
        self.assertEqual(second.parsed, first.parsed)
        self.assertEqual(len(bodies), 1)

    async def test_llamacpp_governor_limit(self):
        live = {"now": 0, "max": 0}

        async def handler(req):
            live["now"] += 1
            live["max"] = max(live["max"], live["now"])
            await asyncio.sleep(0.02)
            live["now"] -= 1
            return llama_reply()

        from council.gateway.llamacpp_client import LlamaCppClient

        client = LlamaCppClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        gw = self.make(mock=False, driver="llamacpp", registry=[entry("m1", parallel=2)],
                       clients={"m1": client}, server_parallel=2)
        results = await gw.call_many([spec() for _ in range(6)])
        self.assertTrue(all(r.ok for r in results))
        self.assertEqual(live["max"], 2)
        # the server's own slot count caps it: 1 slot (the default), 1 call at a time
        live["max"] = 0
        gw = self.make(mock=False, driver="llamacpp", registry=[entry("m1", parallel=2)],
                       clients={"m1": client})
        results = await gw.call_many([spec() for _ in range(4)])
        self.assertTrue(all(r.ok for r in results))
        self.assertEqual(live["max"], 1)

    # ------------------------------------------------------------------ context guard

    async def test_ctx_guard_trims_llamacpp_call(self):
        client, bodies = llama_client(lambda req: llama_reply())
        gw = self.make(mock=False, driver="llamacpp", clients={"m1": client})
        gw.config.llamacpp.ctx = 2048
        msgs = [{"role": "system", "content": "You are seat one."}, {"role": "user", "content": LONG}]
        s = spec(messages=msgs, max_output_tokens=256)
        res = await gw.call(s)
        self.assertTrue(res.ok)
        sent = bodies[0]["messages"]
        self.assertEqual(sent[0], msgs[0])
        self.assertLess(len(sent[1]["content"]), len(LONG))
        self.assertIn("to fit the context window", sent[1]["content"])
        self.assertTrue(sent[1]["content"].endswith("TAIL what is the answer?"))
        self.assertTrue(res.extra["trimmed"])
        self.assertTrue(res.extra["ctx_fit"]["fits"])
        self.assertGreater(res.extra["ctx_fit"]["before"], res.extra["ctx_fit"]["after"])
        self.assertEqual(gw.ctx_trims, 1)
        self.assertEqual(s.messages[1]["content"], LONG)  # the caller's spec is not changed

    async def test_ctx_guard_ctx_for_overrides_config(self):
        client, bodies = llama_client(lambda req: llama_reply())
        gw = self.make(mock=False, driver="llamacpp", clients={"m1": client},
                       ctx_for=lambda m: 65536 if m == "m1" else None)
        gw.config.llamacpp.ctx = 2048
        res = await gw.call(spec(messages=[{"role": "user", "content": LONG}]))
        self.assertEqual(bodies[0]["messages"][0]["content"], LONG)
        self.assertFalse(res.extra["trimmed"])
        self.assertEqual(gw._num_ctx("other"), 2048)
        gw.ctx_for = lambda m: 1 / 0
        self.assertEqual(gw._num_ctx("m1"), 2048)

    async def test_ctx_guard_ollama_uses_num_ctx_live(self):
        fake = FakeOllama()
        gw = self.make(mock=False, driver="ollama", clients={"m1": fake})
        gw.config.ollama.num_ctx_live = 2048
        res = await gw.call(spec(messages=[{"role": "user", "content": LONG}], max_output_tokens=256))
        self.assertTrue(res.ok)
        self.assertIn("to fit the context window", fake.chats[0]["spec"].messages[0]["content"])
        self.assertEqual(gw.ctx_trims, 1)
        gw.config.ollama.num_ctx_live = 0  # unknown size: guard off
        await gw.call(spec(messages=[{"role": "user", "content": LONG}]))
        self.assertEqual(fake.chats[-1]["spec"].messages[0]["content"], LONG)

    async def test_ctx_guard_not_run_in_mock_mode(self):
        seen = []

        class Echo:
            async def respond(self, s, on_delta=None):
                seen.append(s.messages)
                return CallResult(call_id=s.call_id, ok=True, model_id=s.model_id, content=ANSWER)

        gw = self.make(responder=Echo(), driver="llamacpp")
        gw.config.llamacpp.ctx = 2048
        await gw.call(spec(messages=[{"role": "user", "content": LONG}]))
        self.assertEqual(seen[0][0]["content"], LONG)
        self.assertEqual(gw.ctx_trims, 0)

    # ------------------------------------------------------------------ embed

    async def test_embed_mock(self):
        gw = self.make()
        self.assertEqual(await gw.embed([]), [])
        a = await gw.embed(["rate limiter", "token bucket"])
        b = await gw.embed(["rate limiter", "token bucket"])
        self.assertEqual(len(a), 2)
        self.assertEqual(a, b)
        self.assertTrue(all(isinstance(x, float) for x in a[0]))
        self.assertEqual(len(a[0]), len(a[1]))

    async def test_embed_ollama_uses_embed_role_model(self):
        fake = FakeOllama()
        reg = [entry("m1"), entry("emb", roles=["embed"], ollama_tag="nomic-embed-text")]
        gw = self.make(mock=False, driver="ollama", registry=reg, clients={"emb": fake})
        out = await gw.embed(["ab", "abcd"])
        self.assertEqual(out, [[2.0, 1.0], [4.0, 1.0]])
        self.assertEqual(fake.embeds, [("nomic-embed-text", ["ab", "abcd"])])

    async def test_embed_never_raises(self):
        class Boom:
            async def embed(self, model_tag, inputs):
                raise RuntimeError("boom")

        reg = [entry("emb", roles=["embed"])]
        gw = self.make(mock=False, driver="ollama", registry=reg, clients={"emb": Boom()})
        out = await gw.embed(["a", "b"])
        self.assertEqual(len(out), 2)
        self.assertTrue(all(v == 0.0 for vec in out for v in vec))

    async def test_embed_without_embed_model_falls_back(self):
        gw = self.make(mock=False, driver="ollama")
        out = await gw.embed(["a b c"])
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0])

    async def test_embed_injected_embedder(self):
        class Fixed:
            async def embed(self, texts):
                return [[1.0] for _ in texts]

        gw = self.make(embedder=Fixed())
        self.assertEqual(await gw.embed(["a", "b"]), [[1.0], [1.0]])


if __name__ == "__main__":
    unittest.main()
