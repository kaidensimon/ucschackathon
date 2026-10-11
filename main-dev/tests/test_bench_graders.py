import json
import tempfile
import unittest
from pathlib import Path

from council.bench.graders import grade, load_tasks, normalize, split, write_results
from council.core.schemas import BenchResult, BenchTask


def T(answer, atype, grader=None, **kw):
    return BenchTask(id="t", prompt="p", answer=answer, answer_type=atype,
                     grader=grader if grader is not None else {}, **kw)


class NormalizeTests(unittest.TestCase):
    def test_mcq(self):
        for s in ["(b)", "B.", "Answer: B", "b", " B) ", "The answer is (b)", "answer: b"]:
            self.assertEqual(normalize(s, "mcq"), "B", s)

    def test_numeric(self):
        self.assertEqual(normalize("1,234.50", "numeric"), "1234.5")
        self.assertEqual(normalize("$1,000,000", "numeric"), "1000000")
        self.assertEqual(normalize("3.0", "numeric"), "3")
        self.assertEqual(normalize("100", "numeric"), "100")
        self.assertEqual(normalize("-0.50 m/s", "numeric"), "-0.5")
        self.assertEqual(normalize("0.00", "numeric"), "0")
        self.assertEqual(normalize("abc", "numeric"), "abc")

    def test_exact(self):
        self.assertEqual(normalize('  "Hello   World!" ', "exact"), "hello world")

    def test_other(self):
        self.assertEqual(normalize("  FooBar ", "freeform"), "foobar")


class GradeTests(unittest.TestCase):
    def test_exact(self):
        t = T("Paris", "exact", {"type": "exact"})
        self.assertTrue(grade(t, " paris. "))
        self.assertFalse(grade(t, "London"))

    def test_mcq(self):
        t = T("B", "mcq", {"type": "mcq"})
        self.assertTrue(grade(t, "Answer: (b)"))
        self.assertFalse(grade(t, "C."))

    def test_numeric(self):
        t = T("100", "numeric", {"type": "numeric_tolerance", "tolerance": 0.01})
        self.assertTrue(grade(t, "100.5"))
        self.assertFalse(grade(t, "102"))
        self.assertFalse(grade(t, "none"))
        d = T("1000", "numeric", {"type": "numeric_tolerance"})
        self.assertTrue(grade(d, "1,000.0"))
        self.assertFalse(grade(d, "1000.01"))

    def test_unsupported(self):
        for g in ("unit_tests", "rubric"):
            with self.assertRaises(NotImplementedError):
                grade(T("x", "code", {"type": g}), "y")


class IOTests(unittest.TestCase):
    def test_load_split_write(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "b.jsonl"
            rows = [{"id": "a", "prompt": "p", "split": "calibration"},
                    {"id": "b", "prompt": "q", "split": "test", "extra": 1}]
            src.write_text("\n".join(json.dumps(r) for r in rows) + "\n\n", encoding="utf-8")
            tasks = load_tasks(src)
            self.assertEqual([t.id for t in tasks], ["a", "b"])
            self.assertEqual([t.id for t in split(tasks, "test")], ["b"])
            out = Path(d) / "sub" / "r.jsonl"
            write_results(out, [BenchResult(id="a", mode="council", correct=True)])
            lines = out.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["id"], "a")


if __name__ == "__main__":
    unittest.main()
