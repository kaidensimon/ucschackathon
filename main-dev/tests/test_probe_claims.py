import unittest

from council.core.schemas_v15 import ClaimSpan
from council.probe.claims import claims_from_draft, split_claims


class SplitClaimsTest(unittest.TestCase):
    def test_sentences_and_ids(self):
        a = "Paris is the capital of France. The Seine flows through it. Water boils at 100 degrees."
        cs = split_claims(a)
        self.assertEqual([c.claim_id for c in cs], ["c1", "c2", "c3"])
        self.assertTrue(all(isinstance(c, ClaimSpan) for c in cs))
        self.assertEqual(cs[0].text, "Paris is the capital of France.")

    def test_offsets_point_into_answer(self):
        a = "Intro line here.\n\n- Rust returns a Result type.\n- Python was released in 1991."
        for c in split_claims(a):
            self.assertEqual(a[c.start:c.end], c.text)

    def test_list_items(self):
        a = "- Alpha is first in order\n* Beta is second in order\n1. Gamma is third in order\n2) Delta is fourth in order"
        cs = split_claims(a)
        self.assertEqual(len(cs), 4)
        self.assertEqual(cs[2].text, "Gamma is third in order")

    def test_code_block_skipped(self):
        a = "Use this call.\n```python\nx = compute_something_long(1, 2)\nprint(x is None)\n```\nThe result is always an integer."
        texts = [c.text for c in split_claims(a)]
        self.assertFalse(any("compute_something" in t for t in texts))
        self.assertIn("The result is always an integer.", texts)

    def test_unclosed_fence_skips_rest(self):
        a = "The sky is blue today.\n```\nthe rest is code and is ignored entirely"
        texts = [c.text for c in split_claims(a)]
        self.assertEqual(texts, ["The sky is blue today."])

    def test_questions_skipped(self):
        a = "What is the capital of France? Paris is the capital of France."
        texts = [c.text for c in split_claims(a)]
        self.assertEqual(texts, ["Paris is the capital of France."])

    def test_meta_skipped(self):
        a = "Here is my answer:\nI think we should discuss this first.\nLet me explain further.\nThe boiling point of water is 100 C."
        texts = [c.text for c in split_claims(a)]
        self.assertEqual(texts, ["The boiling point of water is 100 C."])

    def test_duplicates_skipped(self):
        a = "The moon orbits the Earth. The  moon orbits   the earth.\n- The moon orbits the Earth"
        self.assertEqual(len(split_claims(a)), 1)

    def test_decimals_and_abbreviations_not_split(self):
        a = "Pi is about 3.14 in most uses. Some tools, e.g. numpy, return floats."
        cs = split_claims(a)
        self.assertEqual(len(cs), 2)
        self.assertIn("e.g. numpy", cs[1].text)

    def test_min_and_max_chars(self):
        self.assertEqual(split_claims("Too short."), [])
        long = "The value is " + "very " * 100 + "large."
        cs = split_claims(long, max_chars=60)
        self.assertEqual(len(cs), 1)
        self.assertLessEqual(len(cs[0].text), 60)
        self.assertEqual(long[cs[0].start:cs[0].end], cs[0].text)

    def test_cap_keeps_best_in_original_order(self):
        a = (
            "Maybe things will go well soon. "
            "Water boils at 100 degrees Celsius. "
            "Nice weather would help everyone. "
            "Python was released in 1991. "
            "Good things come to those who wait. "
            "The function returns 42."
        )
        cs = split_claims(a, max_claims=3)
        self.assertEqual(len(cs), 3)
        self.assertEqual([c.claim_id for c in cs], ["c1", "c2", "c3"])
        self.assertEqual(cs[0].text, "Water boils at 100 degrees Celsius.")
        self.assertEqual(cs[1].text, "Python was released in 1991.")
        self.assertEqual(cs[2].text, "The function returns 42.")
        self.assertLess(cs[0].start, cs[1].start)

    def test_empty_and_bad_input(self):
        self.assertEqual(split_claims(""), [])
        self.assertEqual(split_claims("   \n\n"), [])
        self.assertEqual(split_claims("Some fact here is true.", max_claims=0), [])

    def test_wrapped_paragraph_joins(self):
        a = "The engine is built from\nthree separate parts."
        cs = split_claims(a)
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0].text, "The engine is built from three separate parts.")


class ClaimsFromDraftTest(unittest.TestCase):
    def test_uses_listed_strings(self):
        d = {"answer": "Ignored sentence is here.", "claims": ["The sky is blue.", "Grass is green."]}
        cs = claims_from_draft(d)
        self.assertEqual([c.claim_id for c in cs], ["c1", "c2"])
        self.assertEqual(cs[1].text, "Grass is green.")

    def test_keeps_ids_and_fills_missing(self):
        d = {"claims": [{"id": "c2", "text": "Alpha is first."}, {"text": "Beta is second."}, "Gamma is third."]}
        cs = claims_from_draft(d)
        self.assertEqual([c.claim_id for c in cs], ["c2", "c1", "c3"])

    def test_offsets_found_in_answer(self):
        d = {"answer": "Intro. The sky is blue. Done.", "claims": ["The sky is blue."]}
        c = claims_from_draft(d)[0]
        self.assertEqual(d["answer"][c.start:c.end], "The sky is blue.")

    def test_falls_back_to_answer(self):
        d = {"answer": "Paris is the capital of France.", "claims": []}
        self.assertEqual(claims_from_draft(d)[0].text, "Paris is the capital of France.")
        self.assertEqual(len(claims_from_draft({"answer": "Paris is the capital of France."})), 1)

    def test_object_draft(self):
        class Draft:
            answer = "Water boils at 100 degrees."
            claims = None

        self.assertEqual(len(claims_from_draft(Draft())), 1)

    def test_object_claims(self):
        class Item:
            def __init__(self, i, t):
                self.id, self.text = i, t

        d = {"claims": [Item("x1", "Tea is hot."), Item("", "  ")]}
        cs = claims_from_draft(d)
        self.assertEqual([c.claim_id for c in cs], ["x1"])

    def test_empty_draft(self):
        self.assertEqual(claims_from_draft({}), [])


if __name__ == "__main__":
    unittest.main()
