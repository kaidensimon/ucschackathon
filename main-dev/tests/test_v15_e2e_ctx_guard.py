"""End to end: context guard through the real Gateway and the real LlamaCppClient (fake transport)."""

import json
import unittest

import httpx

from council.core.config import Config
from council.core.events import EventBus
from council.core.schemas import CallSpec, ModelEntry, ServeConfig, ServeProfile
from council.core.store import Store
from council.gateway import ctx_guard
from council.gateway.gateway import Gateway
from council.gateway.llamacpp_client import LlamaCppClient

ANSWER = '{"answer": "x", "confidence": 0.7}'
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "confidence": {"type": "number"}},
    "required": ["answer", "confidence"],
}
NUM_CTX = 2048
MAX_OUT = 256
SYS_HEAD = "SYSTEM-HEAD-MARKER you are seat three of the council. "
SYSTEM = SYS_HEAD + ("Follow the rules of the chamber carefully. " * 120)  # > PROTECT_CHARS
USER_TAIL = " FINAL-QUESTION-MARKER which rate limiter should we pick?"
BIG_USER = "USER-START " + ("background notes and context line. " * 1500) + USER_TAIL


def reply():
    return httpx.Response(200, json={
        "choices": [{"message": {"content": ANSWER}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 10},
        "timings": {"predicted_ms": 500.0, "predicted_per_second": 20.0, "predicted_n": 10, "prompt_n": 5},
    })


def make_gateway(ctx=NUM_CTX):
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return reply()

    client = LlamaCppClient("http://box:18101", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    cfg = Config()
    cfg.host.driver = "llamacpp"
    cfg.gateway.mock = False
    cfg.llamacpp.ctx = ctx
    store = Store(":memory:")
    reg = [ModelEntry(id="m1", serve=ServeConfig(live=ServeProfile(ctx=4096, parallel=2)))]
    gw = Gateway(cfg, reg, store, EventBus(store), clients={"m1": client})
    return gw, bodies


def spec(messages, **kw):
    base = dict(model_id="m1", run_id="run1", purpose="seat.r0", messages=messages,
                json_schema=SCHEMA, max_output_tokens=MAX_OUT)
    base.update(kw)
    return CallSpec(**base)


class CtxGuardE2ETest(unittest.IsolatedAsyncioTestCase):
    async def test_oversized_prompt_is_trimmed_to_fit(self):
        gw, bodies = make_gateway()
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": BIG_USER}]
        self.assertGreater(ctx_guard.messages_tokens(msgs), NUM_CTX)  # the premise
        res = await gw.call(spec(msgs))
        self.assertTrue(res.ok)
        self.assertEqual(len(bodies), 1)
        sent = bodies[0]["messages"]
        budget = NUM_CTX - MAX_OUT - 256
        self.assertLessEqual(ctx_guard.messages_tokens(sent), budget)
        self.assertLess(sum(len(m["content"]) for m in sent), sum(len(m["content"]) for m in msgs))
        self.assertEqual(gw.ctx_trims, 1)
        self.assertTrue(res.extra["trimmed"])
        self.assertTrue(res.extra["ctx_fit"]["fits"])

    async def test_trim_keeps_system_head_and_user_tail(self):
        gw, bodies = make_gateway()
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": BIG_USER}]
        await gw.call(spec(msgs))
        sent = bodies[0]["messages"]
        self.assertEqual([m["role"] for m in sent], ["system", "user"])
        # system prompt head is intact, byte for byte, for the protected span
        self.assertTrue(sent[0]["content"].startswith(SYSTEM[: ctx_guard.PROTECT_CHARS]))
        self.assertTrue(sent[0]["content"].startswith(SYS_HEAD))
        # the final question survives, byte for byte, for the protected span
        self.assertTrue(sent[1]["content"].endswith(BIG_USER[-ctx_guard.PROTECT_CHARS:]))
        self.assertTrue(sent[1]["content"].endswith(USER_TAIL))
        joined = "".join(m["content"] for m in sent)
        self.assertIn("to fit the context window", joined)

    async def test_normal_prompt_is_unchanged_byte_for_byte(self):
        gw, bodies = make_gateway()
        msgs = [
            {"role": "system", "content": "You are seat one. Be brief. é中\n\ttabs  and  spaces "},
            {"role": "user", "content": "pick a rate limiter\n\nline two  "},
        ]
        res = await gw.call(spec(msgs))
        self.assertTrue(res.ok)
        self.assertEqual(bodies[0]["messages"], msgs)
        self.assertEqual(
            [m["content"].encode("utf-8") for m in bodies[0]["messages"]],
            [m["content"].encode("utf-8") for m in msgs],
        )
        self.assertEqual(gw.ctx_trims, 0)
        self.assertFalse(res.extra["trimmed"])
        self.assertNotIn("ctx_fit", res.extra)

    async def test_multi_turn_cuts_middle_history_not_ends(self):
        gw, bodies = make_gateway()
        history = "OLD-TURN " + ("earlier debate line. " * 600)
        msgs = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "first ask"},
            {"role": "assistant", "content": history},
            {"role": "user", "content": "short context. " * 200 + USER_TAIL},
        ]
        self.assertGreater(ctx_guard.messages_tokens(msgs), NUM_CTX)
        res = await gw.call(spec(msgs))
        self.assertTrue(res.ok)
        sent = bodies[0]["messages"]
        self.assertEqual(len(sent), 4)
        self.assertLessEqual(ctx_guard.messages_tokens(sent), NUM_CTX - MAX_OUT - 256)
        self.assertTrue(sent[0]["content"].startswith(SYSTEM[: ctx_guard.PROTECT_CHARS]))
        self.assertTrue(sent[-1]["content"].endswith(USER_TAIL))
        self.assertEqual(sent[1]["content"], "first ask")  # small message untouched
        self.assertLess(len(sent[2]["content"]), len(history))  # the biggest one paid for it

    async def test_caller_spec_is_not_mutated_and_roles_preserved(self):
        gw, bodies = make_gateway()
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": BIG_USER}]
        s = spec(msgs)
        await gw.call(s)
        self.assertEqual(s.messages[0]["content"], SYSTEM)
        self.assertEqual(s.messages[1]["content"], BIG_USER)
        self.assertEqual([m["role"] for m in bodies[0]["messages"]], ["system", "user"])

    async def test_prompt_exactly_at_budget_is_not_trimmed(self):
        gw, bodies = make_gateway()
        budget = NUM_CTX - MAX_OUT - 256
        # one user message: tokens = round(n / 3.6) + 4 == budget
        n = int((budget - ctx_guard.PER_MESSAGE_OVERHEAD) * ctx_guard.CHARS_PER_TOKEN)
        text = "w" * n
        msgs = [{"role": "user", "content": text}]
        self.assertLessEqual(ctx_guard.messages_tokens(msgs), budget)
        await gw.call(spec(msgs))
        self.assertEqual(bodies[0]["messages"], msgs)
        self.assertEqual(gw.ctx_trims, 0)

    async def test_bigger_context_window_lets_same_prompt_through(self):
        gw, bodies = make_gateway(ctx=65536)
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": BIG_USER}]
        res = await gw.call(spec(msgs))
        self.assertTrue(res.ok)
        self.assertEqual(bodies[0]["messages"], msgs)
        self.assertEqual(gw.ctx_trims, 0)


if __name__ == "__main__":
    unittest.main()
