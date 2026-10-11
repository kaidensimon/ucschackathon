import unittest

from council.core.schemas import Ballot, Draft
from council.gateway.jsonschema_lite import is_valid, validate


class DraftBallotTests(unittest.TestCase):
    def setUp(self):
        self.draft = Draft.model_json_schema()
        self.ballot = Ballot.model_json_schema()

    def test_draft_good(self):
        inst = {
            "answer": "42",
            "answer_key": None,
            "claims": [{"id": "c1", "text": "t", "support": "s"}],
            "confidence": 0.7,
        }
        self.assertEqual(validate(inst, self.draft), [])
        self.assertTrue(is_valid({"answer": "x"}, self.draft))

    def test_draft_missing_required(self):
        errs = validate({}, self.draft)
        self.assertTrue(any("answer" in e for e in errs))

    def test_draft_wrong_type(self):
        errs = validate({"answer": 5}, self.draft)
        self.assertTrue(any("$.answer" in e for e in errs))

    def test_draft_confidence_range(self):
        self.assertFalse(is_valid({"answer": "x", "confidence": 1.5}, self.draft))
        self.assertFalse(is_valid({"answer": "x", "confidence": -0.1}, self.draft))
        self.assertTrue(is_valid({"answer": "x", "confidence": 1}, self.draft))

    def test_draft_nested_ref_path(self):
        errs = validate({"answer": "x", "claims": [{"id": "c1"}]}, self.draft)
        self.assertTrue(any("$.claims[0]" in e and "text" in e for e in errs), errs)

    def test_draft_bad_array_item(self):
        errs = validate({"answer": "x", "risks": ["ok", 3]}, self.draft)
        self.assertTrue(any("$.risks[1]" in e for e in errs), errs)

    def test_draft_nullable(self):
        self.assertTrue(is_valid({"answer": "x", "answer_key": "a"}, self.draft))
        self.assertFalse(is_valid({"answer": "x", "answer_key": 3}, self.draft))

    def test_not_object(self):
        self.assertFalse(is_valid([], self.draft))

    def test_ballot_good(self):
        inst = {
            "choice": "o1",
            "ranking": ["o1", "o2"],
            "crux_votes": [{"crux_id": "x1", "stance": "abstain"}],
            "blocking_objection": None,
        }
        self.assertEqual(validate(inst, self.ballot), [])

    def test_ballot_bad(self):
        self.assertFalse(is_valid({}, self.ballot))
        self.assertFalse(is_valid({"choice": "a", "ranking": "a"}, self.ballot))
        errs = validate({"choice": "a", "crux_votes": [{"crux_id": "x", "stance": "bogus"}]}, self.ballot)
        self.assertTrue(any("$.crux_votes[0].stance" in e for e in errs), errs)


class KeywordTests(unittest.TestCase):
    def test_types(self):
        self.assertTrue(is_valid(1, {"type": "integer"}))
        self.assertFalse(is_valid(True, {"type": "integer"}))
        self.assertFalse(is_valid(True, {"type": "number"}))
        self.assertTrue(is_valid(None, {"type": ["string", "null"]}))
        self.assertFalse(is_valid(1, {"type": ["string", "null"]}))
        self.assertFalse(is_valid(1.5, {"type": "integer"}))

    def test_enum_const(self):
        self.assertTrue(is_valid("a", {"enum": ["a", "b"]}))
        self.assertFalse(is_valid("c", {"enum": ["a", "b"]}))
        self.assertFalse(is_valid(1, {"enum": [True]}))
        self.assertTrue(is_valid("k", {"const": "k"}))
        self.assertFalse(is_valid("j", {"const": "k"}))

    def test_bounds(self):
        s = {"minimum": 1, "maximum": 3}
        self.assertTrue(is_valid(1, s) and is_valid(3, s))
        self.assertFalse(is_valid(0, s) or is_valid(4, s))
        e = {"exclusiveMinimum": 1, "exclusiveMaximum": 3}
        self.assertFalse(is_valid(1, e) or is_valid(3, e))
        self.assertTrue(is_valid(2, e))

    def test_lengths(self):
        self.assertFalse(is_valid("a", {"minLength": 2}))
        self.assertFalse(is_valid("abc", {"maxLength": 2}))
        self.assertFalse(is_valid([1], {"minItems": 2}))
        self.assertFalse(is_valid([1, 2, 3], {"maxItems": 2}))
        self.assertTrue(is_valid([1, 2], {"minItems": 2, "maxItems": 2}))

    def test_additional_properties(self):
        s = {"type": "object", "properties": {"a": {}}, "additionalProperties": False}
        self.assertTrue(is_valid({"a": 1}, s))
        errs = validate({"a": 1, "b": 2}, s)
        self.assertTrue(any("'b'" in e for e in errs))
        s2 = {"type": "object", "additionalProperties": {"type": "integer"}}
        self.assertTrue(is_valid({"x": 1}, s2))
        self.assertFalse(is_valid({"x": "s"}, s2))

    def test_prefix_items(self):
        s = {"type": "array", "prefixItems": [{"type": "string"}, {"type": "integer"}], "items": {"type": "boolean"}}
        self.assertTrue(is_valid(["a", 1, True], s))
        self.assertFalse(is_valid(["a", "b"], s))
        self.assertFalse(is_valid(["a", 1, 3], s))

    def test_combinators(self):
        any_of = {"anyOf": [{"type": "string"}, {"type": "null"}]}
        self.assertTrue(is_valid(None, any_of))
        self.assertFalse(is_valid(3, any_of))
        one_of = {"oneOf": [{"type": "integer"}, {"type": "number"}]}
        self.assertFalse(is_valid(1, one_of))  # matches both
        self.assertTrue(is_valid(1.5, one_of))
        all_of = {"allOf": [{"type": "integer"}, {"minimum": 5}]}
        self.assertTrue(is_valid(6, all_of))
        self.assertFalse(is_valid(4, all_of))

    def test_ref(self):
        s = {"$defs": {"N": {"type": "integer"}}, "type": "array", "items": {"$ref": "#/$defs/N"}}
        self.assertTrue(is_valid([1, 2], s))
        self.assertFalse(is_valid([1, "x"], s))
        self.assertTrue(any("unresolvable" in e for e in validate(1, {"$ref": "#/$defs/none"})))

    def test_returns_list_of_str(self):
        errs = validate("x", {"type": "integer"})
        self.assertIsInstance(errs, list)
        self.assertTrue(all(isinstance(e, str) for e in errs))


if __name__ == "__main__":
    unittest.main()
