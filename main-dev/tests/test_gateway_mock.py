import asyncio
import unittest

from council.core.schemas import Ballot, CallSpec, Draft
from council.gateway.mock import MockResponder


def run(coro):
    return asyncio.run(coro)


def spec(purpose, schema=None, seat=0, cid="c", **kw):
    return CallSpec(model_id="m", call_id=cid, purpose=purpose, json_schema=schema,
                    meta={"seat_no": seat, "k": 5}, **kw)


def ballot_schema():
    s = Ballot.model_json_schema()
    s["properties"]["choice"] = {"type": "string", "enum": ["o1", "o2"]}
    return s


class MockTests(unittest.TestCase):
    def test_draft_valid_and_split(self):
        m = MockResponder(seed=1)
        keys = []
        for seat in range(5):
            r = run(m.respond(spec("seat.r0", Draft.model_json_schema(), seat, cid="d%d" % seat)))
            self.assertTrue(r.ok)
            d = Draft.model_validate(r.parsed)
            self.assertTrue(0.6 <= d.confidence <= 0.95)
            keys.append(d.answer_key)
        self.assertEqual(keys, ["token-bucket"] * 3 + ["sliding-window"] * 2)

    def test_no_split(self):
        m = MockResponder(seed=1, split=False)
        r = run(m.respond(spec("seat.r0", Draft.model_json_schema(), 4)))
        self.assertIn(r.parsed["answer_key"], ("token-bucket", "sliding-window"))

    def test_ballot_converges(self):
        m = MockResponder(seed=2)
        choices = []
        for seat in range(5):
            r = run(m.respond(spec("seat.r2", ballot_schema(), seat, cid="b%d" % seat)))
            Ballot.model_validate(r.parsed)
            choices.append(r.parsed["choice"])
        self.assertEqual(choices, ["o1"] * 4 + ["o2"])

    def test_deterministic(self):
        a = run(MockResponder(seed=3).respond(spec("seat.r0", Draft.model_json_schema())))
        b = run(MockResponder(seed=3).respond(spec("seat.r0", Draft.model_json_schema())))
        self.assertEqual(a.content, b.content)

    def test_prose_and_tokens(self):
        r = run(MockResponder().respond(spec("chair", None, reasoning="council")))
        self.assertTrue(r.ok and r.content and r.parsed is None)
        self.assertGreater(r.tokens_out, 0)
        self.assertGreater(r.tokens_reasoning, 0)
        self.assertGreater(r.gen_ms, 0)

    def test_stream(self):
        got = []
        r = run(MockResponder(delay=(0.001, 0.002), tps=100000).respond(
            spec("seat.r0", Draft.model_json_schema(), stream=True),
            lambda k, c: got.append((k, c))))
        self.assertTrue(got and all(k == "content" for k, _ in got))
        self.assertEqual("".join(c for _, c in got), r.content)

    def test_fail(self):
        r = run(MockResponder(fail_rate=1.0).respond(spec("seat.r0", Draft.model_json_schema())))
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "invalid_output")


class ScenarioRoutingTests(unittest.TestCase):
    def go(self, purpose, schema=None, cid="r:x", meta=None, mid="m", **kw):
        sp = CallSpec(model_id=mid, call_id=cid, purpose=purpose,
                      json_schema=schema or {"type": "object"}, meta=meta or {}, **kw)
        return run(MockResponder(seed=1, **kw.pop("mk", {})).respond(sp))

    def test_foreman_and_worker(self):
        r = self.go("foreman.decompose", cid="r:foreman:decompose")
        self.assertIn("milestones", r.parsed)
        r = self.go("foreman.decompose", cid="r:foreman:tasks:1")
        self.assertTrue(r.parsed["tasks"])
        r = self.go("foreman.review", cid="r:foreman:review:1")
        self.assertEqual(r.parsed["patches"], [])
        r = self.go("worker", meta={"task_id": "t01_package_clock", "attempt": 1})
        self.assertEqual(r.parsed["ops"][0]["op"], "write_file")
        r = self.go("worker", meta={"task_id": "zzz", "attempt": 1, "write_set": ["a/b.py", "c.md"]})
        self.assertEqual([o["path"] for o in r.parsed["ops"]], ["a/b.py", "c.md"])
        compile(r.parsed["ops"][0]["content"], "b.py", "exec")

    def test_review_memory(self):
        r = self.go("review", cid="r:rv1:3", meta={"seat_no": 3})
        self.assertEqual(r.parsed["verdict"], "fix")
        r = self.go("review", cid="r:rv2:3", meta={"seat_no": 3})
        self.assertEqual(r.parsed["verdict"], "accept")
        r = self.go("memory.judge", meta={"seat_no": 0, "candidate_id": "c0"})
        self.assertIn("durable", r.parsed)

    def test_tribunal(self):
        r = self.go("tribunal.question", meta={"index": 0})
        self.assertIn("question", r.parsed)
        r = self.go("tribunal.answer", meta={"index": 0})
        self.assertFalse(r.parsed["concedes"])
        sp = CallSpec(model_id="m", call_id="r:tr", purpose="tribunal.answer",
                      json_schema={"type": "object"}, meta={"index": 0})
        r = run(MockResponder(tribunal_concede=True).respond(sp))
        self.assertTrue(r.parsed["concedes"])
        held = []
        for seat in range(5):
            r = self.go("tribunal.verdict", meta={"seat_no": seat})
            held.append(r.parsed["held"])
            if not r.parsed["held"]:
                self.assertEqual(r.parsed["error_kind"], "logic")
        self.assertEqual(held.count(True), 1)

    def test_solo_accuracy_and_logprobs(self):
        schema = Draft.model_json_schema()

        def solo(model, task, acc=None):
            sp = CallSpec(model_id=model, call_id="b:%s:%s" % (task, model), purpose="bench.solo",
                          json_schema=schema, meta={"task_id": task, "mock_truth": "42"})
            return run(MockResponder(seed=2, accuracy=acc).respond(sp))

        self.assertEqual(solo("a", "t1", {"a": 1.0}).parsed["answer_key"], "42")
        w = solo("a", "t1", {"a": 0.0})
        self.assertNotEqual(w.parsed["answer_key"], "42")
        self.assertEqual(w.parsed["answer_key"], solo("a", "t1", {"a": 0.0}).parsed["answer_key"])
        good = solo("a", "t1", {"a": 1.0}).logprobs
        self.assertGreater(sum(good) / len(good), sum(w.logprobs) / len(w.logprobs))
        right = sum(solo("m", "t%d" % i).parsed["answer_key"] == "42" for i in range(60))
        self.assertTrue(25 < right < 58)
        wrong_a = {i for i in range(30) if solo("a", "t%d" % i, {"a": 0.0}).parsed["answer_key"] == "42"}
        self.assertEqual(wrong_a, set())

    def test_cruxes(self):
        schema = {"type": "object", "properties": {"cruxes": {"type": "array", "items": {
            "type": "object", "properties": {"statement": {"type": "string"},
            "between": {"type": "array", "items": {"type": "string", "enum": ["o1", "o2", "o3"]}},
            "kind": {"type": "string", "enum": ["factual", "checkable", "value"]}}}}}}
        r = self.go("clerk.extract_cruxes", schema=schema)
        self.assertEqual([c["kind"] for c in r.parsed["cruxes"]], ["checkable", "value"])
        self.assertEqual(r.parsed["cruxes"][0]["between"], ["o1", "o2"])
        self.assertTrue(r.logprobs)


if __name__ == "__main__":
    unittest.main()
