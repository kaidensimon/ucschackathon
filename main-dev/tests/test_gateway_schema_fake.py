import unittest
from typing import Literal, Optional

from council.gateway.schema_fake import fake_instance


class TestFake(unittest.TestCase):
    def test_basic_types(self):
        s = {"type": "object", "properties": {
            "a": {"type": "string"}, "b": {"type": "integer", "minimum": 5, "maximum": 7},
            "c": {"type": "number"}, "d": {"type": "boolean"}, "e": {"type": "null"},
            "f": {"type": "array", "items": {"type": "string"}}},
            "required": ["a"]}
        v = fake_instance(s, 1)
        self.assertIsInstance(v["a"], str)
        self.assertTrue(5 <= v["b"] <= 7)
        self.assertIsInstance(v["c"], (int, float))
        self.assertIsInstance(v["d"], bool)
        self.assertIsNone(v["e"])
        self.assertTrue(1 <= len(v["f"]) <= 2)

    def test_deterministic(self):
        s = {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "string"}}}
        self.assertEqual(fake_instance(s, 3), fake_instance(s, 3))

    def test_enum_const_hint(self):
        s = {"type": "object", "properties": {
            "k": {"enum": ["a", "b", "c"]}, "z": {"const": "q"}}}
        self.assertEqual(fake_instance(s, 0, {"enum_index": 4})["k"], "b")
        self.assertEqual(fake_instance(s)["z"], "q")
        self.assertIn(fake_instance(s, 9)["k"], ["a", "b", "c"])

    def test_anyof_prefers_non_null(self):
        s = {"anyOf": [{"type": "null"}, {"type": "integer"}]}
        self.assertIsInstance(fake_instance(s), int)

    def test_ref_and_hints(self):
        s = {"$defs": {"Inner": {"type": "object", "properties": {
            "name": {"type": "string"}, "n": {"type": "integer"}}, "required": ["name"]}},
            "type": "object", "properties": {"items": {"type": "array", "items": {"$ref": "#/$defs/Inner"}, "minItems": 3}}}
        v = fake_instance(s, 0, {"strings": {"name": "bob"}, "numbers": {"n": 42}})
        self.assertGreaterEqual(len(v["items"]), 3)
        for it in v["items"]:
            self.assertEqual(it, {"name": "bob", "n": 42})

    def test_default(self):
        s = {"type": "object", "properties": {"w": {"type": "integer", "default": 77}}}
        self.assertEqual(fake_instance(s)["w"], 77)

    def test_recursive_depth(self):
        s = {"$defs": {"Node": {"type": "object", "properties": {
            "v": {"type": "integer"},
            "kids": {"type": "array", "items": {"$ref": "#/$defs/Node"}},
            "nxt": {"anyOf": [{"$ref": "#/$defs/Node"}, {"type": "null"}]}},
            "required": ["v"]}}, "$ref": "#/$defs/Node"}
        v = fake_instance(s, 2)
        self.assertIn("v", v)

    def test_pydantic_roundtrip(self):
        try:
            from pydantic import BaseModel, Field
        except ImportError:
            self.skipTest("no pydantic")

        class Sub(BaseModel):
            tag: Literal["x", "y"]
            n: int = Field(ge=1, le=3)

        class M(BaseModel):
            name: str
            opt: Optional[int] = None
            subs: list[Sub]
            one: Sub
            m: dict[str, int] = {}

        for seed in range(5):
            v = fake_instance(M.model_json_schema(), seed)
            M.model_validate(v)


if __name__ == "__main__":
    unittest.main()
