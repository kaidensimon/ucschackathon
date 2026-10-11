import unittest

from council.bench.solo import (FORMAT_INSTRUCTION, build_solo_call, extract_answer,
                                majority_answer, solo_prompt, solo_schema, to_draft)
from council.core.config import BenchConfig
from council.core.schemas import BenchTask, CallResult, Draft, ModelEntry


def task(atype="mcq", **kw):
    base = dict(id="t1", prompt="Pick one.", answer_type=atype, answer="B",
                choices=["A one", "B two"] if atype == "mcq" else None)
    base.update(kw)
    return BenchTask(**base)


def res(content="", parsed=None, ok=True):
    return CallResult(call_id="c", ok=ok, content=content, parsed=parsed)


class PromptTests(unittest.TestCase):
    def test_instructions(self):
        self.assertIn("ANSWER: <letter>", FORMAT_INSTRUCTION["mcq"])
        self.assertIn("ANSWER: <value>", FORMAT_INSTRUCTION["numeric"])
        self.assertIn("ANSWER: <value>", FORMAT_INSTRUCTION["exact"])

    def test_prompt(self):
        m = solo_prompt(task())
        self.assertEqual(len(m), 1)
        self.assertIn("B two", m[0]["content"])
        self.assertIn("ANSWER: <letter>", m[0]["content"])
        self.assertEqual(m, solo_prompt(task()))
        self.assertIn("ANSWER: <value>", solo_prompt(task("numeric"))[0]["content"])

    def test_schema(self):
        self.assertEqual(solo_schema(), Draft.model_json_schema())


class CallTests(unittest.TestCase):
    def setUp(self):
        self.model = ModelEntry(id="m1", sampling={"temperature": 0.6, "top_p": 0.95})
        self.cfg = BenchConfig()

    def test_spec(self):
        s = build_solo_call(task(), self.model, self.cfg, seed=10, sample=3)
        self.assertEqual(s.purpose, "bench.solo")
        self.assertEqual(s.reasoning, "max")
        self.assertEqual(s.call_id, "bench:t1:m1:3")
        self.assertEqual(s.seed, 13)
        self.assertTrue(s.cacheable)
        self.assertEqual(s.temperature, 0.6)
        self.assertEqual(s.top_p, 0.95)
        self.assertEqual(s.max_output_tokens, self.cfg.solo_max_output_tokens)
        self.assertEqual(s.max_reasoning_tokens, self.cfg.solo_max_reasoning_tokens)
        self.assertEqual(s.meta, {"task_id": "t1", "answer_type": "mcq"})
        self.assertIsNone(s.json_schema)  # free text: every model may reason before the ANSWER line

    def test_mock_truth(self):
        s = build_solo_call(task(), self.model, self.cfg, mock_truth=True)
        self.assertEqual(s.meta["mock_truth"], "B")

    def test_no_sampling(self):
        s = build_solo_call(task(), ModelEntry(id="x"), self.cfg)
        self.assertIsNone(s.temperature)


class ExtractTests(unittest.TestCase):
    def test_parsed_key(self):
        r = res("ANSWER: C", parsed={"answer": "x", "answer_key": "(b)"})
        self.assertEqual(extract_answer(r, "mcq"), "B")

    def test_last_line(self):
        r = res("ANSWER: A\nhmm wait\nAnswer: 1,234.0")
        self.assertEqual(extract_answer(r, "numeric"), "1234")

    def test_parsed_without_key(self):
        r = res("ANSWER: d", parsed={"answer": "stuff", "answer_key": None})
        self.assertEqual(extract_answer(r, "mcq"), "D")

    def test_none(self):
        self.assertIsNone(extract_answer(res("no idea"), "mcq"))
        self.assertIsNone(extract_answer(res("ANSWER: B", ok=False), "mcq"))


class DraftTests(unittest.TestCase):
    def test_from_parsed(self):
        r = res(parsed={"answer": "It is B", "answer_key": "B", "confidence": 0.8})
        d = to_draft(r)
        self.assertEqual(d.answer_key, "B")
        self.assertEqual(d.confidence, 0.8)

    def test_from_text(self):
        d = to_draft(res("long work\nANSWER: 42"))
        self.assertEqual(d.answer, "42")

    def test_none(self):
        self.assertIsNone(to_draft(res("nothing")))
        self.assertIsNone(to_draft(res("ANSWER: 1", ok=False)))

    def test_bad_parsed_falls_back(self):
        d = to_draft(res("ANSWER: 7", parsed={"nope": 1}))
        self.assertEqual(d.answer, "7")


class MajorityTests(unittest.TestCase):
    def test_majority(self):
        self.assertEqual(majority_answer(["A", None, "B", "B"]), "B")

    def test_tie_first_seen(self):
        self.assertEqual(majority_answer(["A", "B", "B", "A"]), "A")

    def test_empty(self):
        self.assertIsNone(majority_answer([]))
        self.assertIsNone(majority_answer([None, None]))


if __name__ == "__main__":
    unittest.main()
