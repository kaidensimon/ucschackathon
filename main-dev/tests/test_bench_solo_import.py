import json
import tempfile
import unittest
from pathlib import Path

from council.bench.solo_import import load_solo, load_solo_report, normalize_model


class SoloImportTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, text):
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_json_list(self):
        p = self.write("a.json", json.dumps([
            {"model": "Qwen3:14B", "task": "t1", "correct": True, "category": "math", "latency_ms": 1500, "tokens": 12},
            {"model_id": "m2", "task_id": 2, "score": 0.3, "answer": "x", "latency_s": 2},
        ]))
        s = load_solo(p)
        self.assertEqual(len(s), 2)
        self.assertEqual(s[0].model_id, "qwen3:14b")
        self.assertTrue(s[0].correct)
        self.assertEqual(s[0].latency_s, 1.5)
        self.assertEqual(s[0].tokens_out, 12)
        self.assertEqual(s[0].category, "math")
        self.assertEqual(s[1].task_id, "2")
        self.assertFalse(s[1].correct)
        self.assertEqual(s[1].score, 0.3)

    def test_json_results_wrapper(self):
        p = self.write("a.json", json.dumps({"results": [{"name": "m", "id": "q", "ok": "yes"}]}))
        s, info = load_solo_report(p)
        self.assertEqual(len(s), 1)
        self.assertTrue(s[0].correct)
        self.assertEqual(info["format"], "json:results")

    def test_json_by_model_lists(self):
        p = self.write("a.json", json.dumps({
            "A": [{"task": "t1", "correct": 1}, {"task": "t2", "correct": 0}],
            "B": [{"task": "t1", "is_correct": "true"}],
        }))
        s, info = load_solo_report(p)
        self.assertEqual(len(s), 3)
        self.assertEqual(info["models"], ["a", "b"])
        self.assertEqual(info["tasks"], 2)
        self.assertEqual(info["format"], "json:by_model")

    def test_json_by_model_task_map(self):
        p = self.write("a.json", json.dumps({
            "A": {"t1": True, "t2": {"score": 0.9, "answer": "yes"}, "t3": 0.2},
            "B": {"t1": False},
        }))
        s = {(x.model_id, x.task_id): x for x in load_solo(p)}
        self.assertEqual(len(s), 4)
        self.assertTrue(s[("a", "t1")].correct)
        self.assertTrue(s[("a", "t2")].correct)
        self.assertEqual(s[("a", "t2")].answer, "yes")
        self.assertFalse(s[("a", "t3")].correct)
        self.assertFalse(s[("b", "t1")].correct)

    def test_jsonl_and_bad_lines(self):
        p = self.write("a.jsonl", '{"model":"m","task":"1","passed":false}\n\nnot json\n{"task":"2"}\n[1]\n')
        s, info = load_solo_report(p)
        self.assertEqual(len(s), 1)
        self.assertFalse(s[0].correct)
        self.assertEqual(info["skipped"], 3)
        self.assertEqual(info["rows"], 4)
        self.assertEqual(info["format"], "jsonl")

    def test_csv(self):
        p = self.write("a.csv", "﻿Model,Task_ID,Correct,Score,Category,Latency,Completion_Tokens\n"
                                "m1,t1,yes,,bio,3.5,100\n"
                                "m1,t2,,0.7,bio,,\n"
                                ",t3,true,,,,\n"
                                "m2,,true,,,,\n")
        s, info = load_solo_report(p)
        self.assertEqual(len(s), 2)
        self.assertTrue(s[0].correct)
        self.assertEqual(s[0].latency_s, 3.5)
        self.assertEqual(s[0].tokens_out, 100)
        self.assertTrue(s[1].correct)
        self.assertEqual(s[1].score, 0.7)
        self.assertIsNone(s[1].latency_s)
        self.assertEqual(info["skipped"], 2)
        self.assertEqual(info["format"], "csv")

    def test_score_threshold(self):
        p = self.write("a.json", json.dumps([
            {"model": "m", "task": "a", "grade": 0.5},
            {"model": "m", "task": "b", "grade": 0.49},
            {"model": "m", "task": "c", "accuracy": "80%"},
        ]))
        c = [x.correct for x in load_solo(p)]
        self.assertEqual(c, [True, False, True])

    def test_correct_wins_over_score(self):
        p = self.write("a.json", json.dumps([{"model": "m", "task": "a", "correct": False, "score": 0.9}]))
        self.assertFalse(load_solo(p)[0].correct)

    def test_missing_correct_and_score_is_none(self):
        p = self.write("a.json", json.dumps([{"model": "m", "task": "a"}]))
        self.assertIsNone(load_solo(p)[0].correct)

    def test_known_map_on_load(self):
        p = self.write("a.json", json.dumps([{"model": "qwen3:14b", "task": "a", "correct": 1}]))
        self.assertEqual(load_solo(p, known={"qwen3:14b": "qwen3_14b"})[0].model_id, "qwen3_14b")

    def test_normalize_model(self):
        known = {"qwen3:14b": "qwen3_14b", "llama3.1:8b": "llama31_8b"}
        self.assertEqual(normalize_model("qwen3:14b", known), "qwen3_14b")
        self.assertEqual(normalize_model("QWEN3:14B", known), "qwen3_14b")
        self.assertEqual(normalize_model("ollama/qwen3:14b", known), "qwen3_14b")
        self.assertEqual(normalize_model("qwen3:14b:latest", known), "qwen3_14b")
        self.assertEqual(normalize_model("Mystery:7B", known), "mystery:7b")
        self.assertEqual(normalize_model("  Foo ", None), "foo")

    def test_bad_json_raises(self):
        p = self.write("a.json", "{nope")
        with self.assertRaises(ValueError):
            load_solo(p)

    def test_unknown_ext_falls_back_to_jsonl(self):
        p = self.write("a.txt", '{"model":"m","task":"1","correct":true}\n{"model":"m","task":"2","correct":false}\n')
        self.assertEqual(len(load_solo(p)), 2)


if __name__ == "__main__":
    unittest.main()
