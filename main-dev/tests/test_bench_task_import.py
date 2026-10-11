import json
import tempfile
import unittest
from pathlib import Path

from council.bench.graders import grade
from council.bench.task_import import load_tasks


class TaskImportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, text):
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_jsonl_mcq_and_numeric(self):
        lines = [
            {"qid": "a1", "question": "Pick one", "options": ["red", "blue"], "gold": "blue",
             "subject": "Chemistry", "difficulty": "HARD"},
            {"id": "a2", "prompt": "2+2?", "answer": "4", "topic": "algebra"},
            {"prompt": "Name a river", "answer": "Nile"},
            {"id": "a4", "answer": "x"},
        ]
        p = self._write("t.jsonl", "\n".join(json.dumps(x) for x in lines) + "\n")
        tasks, rep = load_tasks(p)
        self.assertEqual(rep["tasks"], 3)
        self.assertEqual(rep["skipped"], 1)
        t1, t2, t3 = tasks
        self.assertEqual((t1.answer_type, t1.answer, t1.category, t1.difficulty), ("mcq", "B", "science", "hard"))
        self.assertEqual(t1.grader, {"type": "mcq"})
        self.assertTrue(grade(t1, "The answer is B"))
        self.assertEqual((t2.answer_type, t2.category), ("numeric", "math"))
        self.assertTrue(grade(t2, "4.0"))
        self.assertEqual(t3.id, "t3")
        self.assertEqual((t3.answer_type, t3.category, t3.grader["type"]), ("freeform", "knowledge", "rubric"))
        self.assertEqual(rep["by_category"], {"science": 1, "math": 1, "knowledge": 1})

    def test_difficulty_valid(self):
        p = self._write("d.jsonl", json.dumps({"prompt": "q", "answer": "a", "difficulty": "Hard"}) + "\n")
        tasks, _ = load_tasks(p)
        self.assertEqual(tasks[0].difficulty, "hard")

    def test_json_list_and_wrappers(self):
        rows = [{"id": "x", "text": "hi", "target": "1,000"}]
        for name, data in (("a.json", rows), ("b.json", {"tasks": rows}), ("c.json", {"questions": rows})):
            p = self._write(name, json.dumps(data))
            tasks, rep = load_tasks(p)
            self.assertEqual(rep["tasks"], 1)
            self.assertEqual(tasks[0].answer, "1000")
            self.assertEqual(tasks[0].answer_type, "numeric")

    def test_csv_letter_columns(self):
        p = self._write("t.csv", "question,A,B,C,D,answer,category\nWhich?,one,two,three,four,C,code\n,x,y,,,A,\n")
        tasks, rep = load_tasks(p)
        self.assertEqual(rep["tasks"], 1)
        self.assertEqual(rep["skipped"], 1)
        t = tasks[0]
        self.assertEqual(t.choices, ["one", "two", "three", "four"])
        self.assertEqual((t.answer, t.answer_type, t.category, t.id), ("C", "mcq", "code", "t1"))

    def test_pipe_choices_and_text_answer(self):
        p = self._write("p.csv", "id,prompt,choices,answer\nq,Pick,cat|dog|bird,dog\n")
        tasks, _ = load_tasks(p)
        self.assertEqual(tasks[0].choices, ["cat", "dog", "bird"])
        self.assertEqual(tasks[0].answer, "B")

    def test_warnings(self):
        p = self._write("w.jsonl", json.dumps({"id": "w", "prompt": "p", "choices": ["a", "b"], "answer": "zzz"}) + "\n{bad\n")
        _, rep = load_tasks(p)
        self.assertTrue(any("does not match" in w for w in rep["warnings"]))
        self.assertTrue(any("bad json" in w for w in rep["warnings"]))

    def test_unsupported(self):
        with self.assertRaises(ValueError):
            load_tasks(self._write("x.txt", "hi"))


if __name__ == "__main__":
    unittest.main()
