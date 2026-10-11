import json
import tempfile
import unittest
from pathlib import Path

from council.bench.report import agreement_curve, council_vs_best, summarize, to_markdown, write_report
from council.core.schemas import BenchResult, BenchTask


def _tasks():
    return [
        BenchTask(id="a", prompt="p", difficulty="easy", category="math"),
        BenchTask(id="b", prompt="p", difficulty="hard", category="code"),
    ]


def _results():
    return [
        BenchResult(id="a", mode="solo:m1", correct=True, tokens_in=10, tokens_out=5, tokens_reasoning=5, wall_ms=100),
        BenchResult(id="b", mode="solo:m1", correct=False, tokens_in=20, tokens_out=10, tokens_reasoning=0, wall_ms=300),
        BenchResult(id="a", mode="council", correct=True, agreement=0.9, wall_ms=10),
        BenchResult(id="b", mode="council", correct=True, agreement=0.3, wall_ms=10),
    ]


class BenchReportTests(unittest.TestCase):
    def test_summarize(self):
        rows = {r.mode: r for r in summarize(_results(), _tasks())}
        s = rows["solo:m1"]
        self.assertEqual(s.n, 2)
        self.assertAlmostEqual(s.accuracy, 0.5)
        self.assertEqual(s.by_difficulty, {"easy": 1.0, "hard": 0.0})
        self.assertEqual(s.by_category["code"], 0.0)
        self.assertAlmostEqual(s.mean_tokens, 25.0)
        self.assertAlmostEqual(s.mean_wall_ms, 200.0)

    def test_markdown(self):
        md = to_markdown(summarize(_results(), _tasks()))
        self.assertIn("solo:m1", md)
        self.assertIn("50.0%", md)

    def test_council_vs_best(self):
        d = council_vs_best(summarize(_results(), _tasks()))
        self.assertEqual(d["best_solo"], "solo:m1")
        self.assertAlmostEqual(d["delta_overall"], 0.5)
        self.assertAlmostEqual(d["delta_by_difficulty"]["hard"], 1.0)
        self.assertAlmostEqual(d["delta_by_difficulty"]["easy"], 0.0)

    def test_no_council(self):
        rows = summarize([r for r in _results() if r.mode != "council"], _tasks())
        self.assertIsNone(council_vs_best(rows)["delta_overall"])

    def test_agreement_curve(self):
        curve = agreement_curve(_results())
        self.assertEqual(len(curve), 2)
        self.assertEqual([c[2] for c in curve], [1, 1])
        self.assertEqual(agreement_curve([]), [])

    def test_write_report(self):
        with tempfile.TemporaryDirectory() as td:
            rows = summarize(_results(), _tasks())
            write_report(Path(td) / "out", rows, {"agreement_curve": agreement_curve(_results())})
            self.assertTrue((Path(td) / "out" / "report.md").read_text(encoding="utf-8"))
            data = json.loads((Path(td) / "out" / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(len(data["rows"]), 2)


if __name__ == "__main__":
    unittest.main()
