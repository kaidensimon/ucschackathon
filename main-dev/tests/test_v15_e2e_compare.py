"""End to end, mock mode: council against solo models through council.bench.compare_cli.main.

Real classes only: compare_cli -> solo_import -> compare -> compare_text. Files go to a temp dir.
Data: 3 solo models x 12 tasks. alpha right on t00-t08, beta on t00-t05, gamma on t04-t09,
all wrong answers are the same string so a plain vote is "right iff at least 2 right".
Council right on t00-t10 (11 of 12).
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from council.bench import compare_cli

TASKS = [f"t{i:02d}" for i in range(12)]
RIGHT = {
    "alpha": set(TASKS[0:9]),
    "beta": set(TASKS[0:6]),
    "gamma": set(TASKS[4:10]),
}
COUNCIL_RIGHT = set(TASKS[0:11])


def solo_rows(tasks: list[str], right: dict[str, set[str]]) -> list[dict]:
    rows = []
    for model, ok in right.items():
        for t in tasks:
            hit = t in ok
            rows.append({
                "model": model, "task_id": t, "correct": hit,
                "answer": f"ans-{t}" if hit else "wrong",
                "latency_s": 1.0 if model == "alpha" else 2.0,
            })
    return rows


class CompareE2E(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.solo = self.dir / "solo.json"
        self.council = self.dir / "council.json"
        self.solo.write_text(json.dumps(solo_rows(TASKS, RIGHT)), encoding="utf-8")
        self.council.write_text(
            json.dumps({t: (t in COUNCIL_RIGHT) for t in TASKS}), encoding="utf-8")

    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stderr(err):
            code = compare_cli.main(argv, out=out)
        return code, out.getvalue(), err.getvalue()

    def test_table_rows_and_exit_zero(self) -> None:
        code, out, err = self.run_cli(["--solo", str(self.solo), "--council", str(self.council)])
        self.assertEqual(code, 0, err)
        for name in ("alpha", "beta", "gamma", "mean_solo", "majority_vote", "oracle"):
            self.assertIn(name, out)
        self.assertIn("council <<", out)
        self.assertIn("council", [ln.split()[0] for ln in out.splitlines() if ln.strip()])

    def test_accuracy_numbers(self) -> None:
        code, out, err = self.run_cli(["--solo", str(self.solo), "--council", str(self.council)])
        self.assertEqual(code, 0, err)
        by_name = {}
        for ln in out.split("\n\n")[0].splitlines():  # grid only, not the summary lines
            parts = ln.split()
            if len(parts) >= 4 and parts[0] in ("alpha", "beta", "gamma", "oracle",
                                                 "majority_vote", "mean_solo", "council"):
                by_name[parts[0]] = [p for p in parts if p.replace(".", "", 1).isdigit()]
        self.assertIn("75.0", by_name["alpha"])
        self.assertIn("50.0", by_name["beta"])
        self.assertIn("50.0", by_name["gamma"])
        self.assertIn("83.3", by_name["oracle"])
        self.assertIn("75.0", by_name["majority_vote"])
        self.assertIn("58.3", by_name["mean_solo"])
        self.assertIn("91.7", by_name["council"])

    def test_signed_difference_lines(self) -> None:
        _, out, _ = self.run_cli(["--solo", str(self.solo), "--council", str(self.council)])
        self.assertIn("council vs best solo (alpha): +16.7 points", out)
        self.assertIn("council vs mean solo: +33.3 points", out)
        self.assertIn("council vs plain majority vote: +16.7 points", out)
        self.assertIn("council only right: 1", out)
        self.assertIn("council only wrong: 0", out)

    def test_negative_difference_is_signed(self) -> None:
        bad = self.dir / "bad_council.json"
        bad.write_text(json.dumps({t: False for t in TASKS}), encoding="utf-8")
        code, out, err = self.run_cli(["--solo", str(self.solo), "--council", str(bad)])
        self.assertEqual(code, 0, err)
        self.assertIn("council vs best solo (alpha): -75.0 points", out)
        self.assertIn("council only wrong: 9", out)

    def test_under_30_tasks_note(self) -> None:
        _, out, _ = self.run_cli(["--solo", str(self.solo), "--council", str(self.council)])
        self.assertIn("note: too few tasks to call a difference real", out)

    def test_30_or_more_tasks_has_no_note(self) -> None:
        many = [f"q{i:02d}" for i in range(36)]
        right = {"alpha": set(many[:20]), "beta": set(many[:10]), "gamma": set(many[10:25])}
        solo = self.dir / "solo36.json"
        council = self.dir / "council36.json"
        solo.write_text(json.dumps(solo_rows(many, right)), encoding="utf-8")
        council.write_text(json.dumps({t: i < 22 for i, t in enumerate(many)}), encoding="utf-8")
        code, out, err = self.run_cli(["--solo", str(solo), "--council", str(council)])
        self.assertEqual(code, 0, err)
        self.assertNotIn("too few tasks", out)
        self.assertIn("council vs best solo (alpha): +5.6 points", out)

    def test_missing_files_exit_two(self) -> None:
        code, _, err = self.run_cli(["--solo", str(self.dir / "nope.json"),
                                     "--council", str(self.council)])
        self.assertEqual(code, 2)
        self.assertIn("not found", err)
        code, _, err = self.run_cli(["--solo", str(self.solo),
                                     "--council", str(self.dir / "nope.json")])
        self.assertEqual(code, 2)
        self.assertIn("not found", err)

    def test_markdown_and_category_tags(self) -> None:
        tags = self.dir / "tags.json"
        tags.write_text(json.dumps({t: ("math" if i % 2 else "code") for i, t in enumerate(TASKS)}),
                        encoding="utf-8")
        md = self.dir / "out" / "table.md"
        code, out, err = self.run_cli(["--solo", str(self.solo), "--council", str(self.council),
                                       "--tags", str(tags), "--md", str(md)])
        self.assertEqual(code, 0, err)
        self.assertIn("math", out)
        self.assertIn("code", out)
        text = md.read_text(encoding="utf-8")
        self.assertIn("| system | kind | n | accuracy % | latency |", text)
        self.assertIn("council <<", text)
        self.assertIn("- council vs best solo (alpha): +16.7 points", text)


if __name__ == "__main__":
    unittest.main()
