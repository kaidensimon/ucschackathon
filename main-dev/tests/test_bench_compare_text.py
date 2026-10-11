"""Tests for council/bench/compare_text.py. Standard library unittest only."""

from __future__ import annotations

import unittest

from council.bench.compare_text import by_category_table, markdown, table
from council.core.schemas_v15 import CompareReport, CompareRow


def _rows() -> list[CompareRow]:
    return [
        CompareRow(name="gemma", kind="solo", n=10, accuracy=0.6, mean_latency_s=1.2345),
        CompareRow(name="qwen", kind="solo", n=10, accuracy=0.7, mean_latency_s=None),
        CompareRow(name="council", kind="council", n=10, accuracy=0.73, mean_latency_s=4.0),
        CompareRow(name="majority_vote", kind="baseline", n=10, accuracy=0.65),
    ]


def _report(**overrides) -> CompareReport:
    base = dict(
        rows=_rows(),
        n_tasks=10,
        best_solo="qwen",
        council_minus_best=0.03,
        council_minus_mean=0.10,
        council_minus_vote=0.08,
        council_only_right=["t1", "t2"],
        council_only_wrong=["t3"],
        notes=["small sample"],
    )
    base.update(overrides)
    return CompareReport(**base)


def _body_rows(text: str, n: int) -> list[str]:
    """Body rows of the terminal table: skip header and rule, take n lines."""
    return text.splitlines()[2:2 + n]


class TableTests(unittest.TestCase):
    def test_header_has_all_columns(self):
        header = table(_report()).splitlines()[0]
        for word in ("system", "kind", "n", "accuracy %", "latency"):
            self.assertIn(word, header)

    def test_rows_sorted_by_accuracy_desc(self):
        names = [line.split()[0] for line in _body_rows(table(_report()), 4)]
        self.assertEqual(names, ["council", "qwen", "majority_vote", "gemma"])

    def test_council_row_marked_only_once(self):
        out = table(_report())
        marked = [line for line in out.splitlines() if "<<" in line]
        self.assertEqual(len(marked), 1)
        self.assertTrue(marked[0].startswith("council"))

    def test_accuracy_one_decimal_percent(self):
        out = table(_report(rows=[
            CompareRow(name="a", kind="solo", n=4, accuracy=0.7254),
            CompareRow(name="b", kind="solo", n=2, accuracy=0.5),
        ]))
        self.assertIn("72.5", out)
        self.assertIn("50.0", out)

    def test_latency_formatting(self):
        out = table(_report())
        self.assertIn("1.23s", out)
        self.assertIn("4.00s", out)
        qwen_line = [l for l in out.splitlines() if l.startswith("qwen")][0]
        self.assertTrue(qwen_line.rstrip().endswith("-"))

    def test_fixed_width_header_and_rule_match(self):
        lines = table(_report()).splitlines()
        self.assertEqual(len(lines[0]), len(lines[1]))

    def test_summary_lines_present(self):
        out = table(_report())
        self.assertIn("council vs best solo (qwen): +3.0 points", out)
        self.assertIn("council vs mean solo: +10.0 points", out)
        self.assertIn("council vs plain majority vote: +8.0 points", out)

    def test_negative_points_explicit_sign(self):
        out = table(_report(council_minus_best=-0.05))
        self.assertIn("council vs best solo (qwen): -5.0 points", out)

    def test_zero_points_explicit_sign(self):
        out = table(_report(council_minus_best=0.0))
        self.assertIn("council vs best solo (qwen): +0.0 points", out)
        out = table(_report(council_minus_best=-0.00001))
        self.assertIn("council vs best solo (qwen): +0.0 points", out)

    def test_none_points_render_na(self):
        out = table(_report(council_minus_best=None, council_minus_mean=None,
                            council_minus_vote=None, best_solo=""))
        self.assertIn("council vs best solo (none): n/a", out)
        self.assertIn("council vs mean solo: n/a", out)
        self.assertIn("council vs plain majority vote: n/a", out)

    def test_counts_listed(self):
        out = table(_report())
        self.assertIn("council only right: 2", out)
        self.assertIn("council only wrong: 1", out)

    def test_notes_listed(self):
        out = table(_report(notes=["small sample", "no probe"]))
        self.assertIn("note: small sample", out)
        self.assertIn("note: no probe", out)

    def test_empty_report_does_not_crash(self):
        out = table(CompareReport())
        self.assertIn("accuracy %", out)
        self.assertIn("council only right: 0", out)

    def test_deterministic(self):
        self.assertEqual(table(_report()), table(_report()))

    def test_ascii_only(self):
        report = _report(
            rows=[CompareRow(name="café", kind="solo", n=1, accuracy=1.0)],
            notes=["delta — check ✓"],
        )
        out = table(report)
        self.assertTrue(all(ord(ch) < 128 for ch in out))
        self.assertIn("note: delta", out)


class MarkdownTests(unittest.TestCase):
    def test_table_structure(self):
        lines = markdown(_report()).splitlines()
        self.assertEqual(lines[0], "| system | kind | n | accuracy % | latency |")
        self.assertEqual(lines[1], "| --- | --- | ---: | ---: | ---: |")
        body = [l for l in lines[2:] if l.startswith("|")]
        self.assertEqual(len(body), 4)
        self.assertTrue(body[0].startswith("| council <<"))

    def test_row_values(self):
        out = markdown(_report())
        self.assertIn("| qwen | solo | 10 | 70.0 | - |", out)
        self.assertIn("| council << | council | 10 | 73.0 | 4.00s |", out)

    def test_pipes_escaped(self):
        report = _report(rows=[CompareRow(name="a|b", kind="solo", n=1, accuracy=0.5)])
        self.assertIn("a\\|b", markdown(report))

    def test_summary_as_bullets(self):
        out = markdown(_report())
        self.assertIn("- council vs best solo (qwen): +3.0 points", out)
        self.assertIn("- council only wrong: 1", out)
        self.assertIn("- note: small sample", out)

    def test_same_summary_as_terminal_table(self):
        plain = table(_report())
        md = markdown(_report())
        for line in plain.splitlines():
            if line.startswith("council vs") or line.startswith("council only"):
                self.assertIn(f"- {line}", md)

    def test_ascii_only(self):
        report = _report(notes=["em dash —"])
        self.assertTrue(all(ord(ch) < 128 for ch in markdown(report)))


class ByCategoryTests(unittest.TestCase):
    def _cat_report(self) -> CompareReport:
        return _report(rows=[
            CompareRow(name="gemma", kind="solo", n=4, accuracy=0.5,
                       by_category={"math": 0.25, "code": 0.75}),
            CompareRow(name="council", kind="council", n=4, accuracy=0.75,
                       by_category={"math": 1.0, "logic": 0.5}),
        ])

    def test_empty_when_no_by_category(self):
        self.assertEqual(by_category_table(_report()), "")

    def test_columns_are_union_of_categories(self):
        header = by_category_table(self._cat_report()).splitlines()[0].split()
        self.assertEqual(header, ["system", "code", "logic", "math"])

    def test_missing_cells_dash(self):
        out = by_category_table(self._cat_report())
        gemma = [l for l in out.splitlines() if l.startswith("gemma")][0].split()
        self.assertEqual(gemma, ["gemma", "75.0", "-", "25.0"])

    def test_row_order_matches_table(self):
        out = by_category_table(self._cat_report()).splitlines()
        self.assertEqual(out[2].split()[0], "council")
        self.assertEqual(out[3].split()[0], "gemma")

    def test_council_marked(self):
        out = by_category_table(self._cat_report())
        self.assertIn("council <<", out)

    def test_ascii_only(self):
        report = _report(rows=[
            CompareRow(name="x", kind="solo", n=1, accuracy=0.5,
                       by_category={"café": 0.5}),
        ])
        self.assertTrue(all(ord(ch) < 128 for ch in by_category_table(report)))


if __name__ == "__main__":
    unittest.main()
