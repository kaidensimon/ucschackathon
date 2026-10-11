import asyncio
import sys
import types
import unittest

from council.core.schemas import CallResult, CallSpec

try:
    import council.gateway.jsonschema_lite  # noqa: F401
except ImportError:
    def _validate(inst, schema):
        errs = []
        for k in schema.get("required", []):
            if not isinstance(inst, dict) or k not in inst:
                errs.append("missing " + k)
        return errs

    _mod = types.ModuleType("council.gateway.jsonschema_lite")
    _mod.validate = _validate
    sys.modules["council.gateway.jsonschema_lite"] = _mod

from council.gateway.structured import extract_json, run_ladder

SCHEMA = {"type": "object", "required": ["a"]}


def res(spec, content, ok=True):
    return CallResult(call_id=spec.call_id, ok=ok, content=content)


def run(coro):
    return asyncio.run(coro)


class ExtractTests(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})

    def test_fence_and_prose(self):
        self.assertEqual(extract_json('Sure!\n```json\n{"a": [1,2]}\n```\nbye'), {"a": [1, 2]})

    def test_braces_in_string(self):
        self.assertEqual(extract_json('x {"a": "}{ \\" ]"} y'), {"a": '}{ " ]'})

    def test_array(self):
        self.assertEqual(extract_json("here [1, 2, 3]"), [1, 2, 3])

    def test_skips_bad_first(self):
        self.assertEqual(extract_json('{oops} then {"a": 2}'), {"a": 2})

    def test_none(self):
        self.assertIsNone(extract_json("no json"))
        self.assertIsNone(extract_json('{"a": 1'))


class LadderTests(unittest.TestCase):
    def test_no_schema(self):
        spec = CallSpec(model_id="m")
        calls = []

        async def attempt(s, m):
            calls.append(m)
            return res(s, "hi")

        r = run(run_ladder(spec, attempt, None, "grammar"))
        self.assertTrue(r.ok)
        self.assertEqual(len(calls), 1)

    def test_grammar_ok(self):
        spec = CallSpec(model_id="m", json_schema=SCHEMA)

        async def attempt(s, m):
            return res(s, '{"a": 1}')

        r = run(run_ladder(spec, attempt, None, "grammar"))
        self.assertTrue(r.ok)
        self.assertEqual(r.parsed, {"a": 1})
        self.assertEqual(r.attempts, 1)

    def test_grammar_error_falls_to_prompt(self):
        spec = CallSpec(model_id="m", json_schema=SCHEMA)
        modes = []

        async def attempt(s, m):
            modes.append(m)
            if m == "grammar":
                raise RuntimeError("boom")
            return res(s, 'ok: {"a": 2}')

        r = run(run_ladder(spec, attempt, None, "grammar"))
        self.assertTrue(r.ok)
        self.assertEqual(modes, ["grammar", "prompt"])
        self.assertEqual(r.attempts, 2)

    def test_prompt_only_skips_grammar(self):
        spec = CallSpec(model_id="m", json_schema=SCHEMA)
        modes = []

        async def attempt(s, m):
            modes.append(m)
            return res(s, '{"a": 1}')

        run(run_ladder(spec, attempt, None, "prompt_only"))
        self.assertEqual(modes, ["prompt"])

    def test_repair(self):
        spec = CallSpec(model_id="m", json_schema=SCHEMA)

        async def attempt(s, m):
            return res(s, "garbage")

        async def repair(text, schema):
            self.assertEqual(text, "garbage")
            return res(spec, '{"a": 3}')

        r = run(run_ladder(spec, attempt, repair, "grammar"))
        self.assertTrue(r.ok)
        self.assertEqual(r.parsed, {"a": 3})
        self.assertEqual(r.attempts, 3)

    def test_give_up(self):
        spec = CallSpec(model_id="m", json_schema=SCHEMA)

        async def attempt(s, m):
            return res(s, '{"b": 1}')

        async def repair(text, schema):
            raise RuntimeError("x")

        r = run(run_ladder(spec, attempt, repair, "grammar"))
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "invalid_output")

    def test_never_raises(self):
        spec = CallSpec(model_id="m", json_schema=SCHEMA)

        async def attempt(s, m):
            raise ValueError("x")

        r = run(run_ladder(spec, attempt, None, "grammar"))
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "invalid_output")


if __name__ == "__main__":
    unittest.main()
