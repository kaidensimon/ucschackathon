import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from council.bench import compare_cli
from council.core.schemas_v15 import CompareReport, SoloScore


def _fake_modules(solo_rows=None, meta=None):
    """Stand-ins for the sibling modules another agent is writing."""
    solo_rows = [SoloScore(model_id="m1", task_id="t1", correct=True)] if solo_rows is None else solo_rows
    solo_import = types.ModuleType("council.bench.solo_import")
    solo_import.load_solo_report = mock.Mock(return_value=(solo_rows, meta or {}))
    compare = types.ModuleType("council.bench.compare")
    compare.compare = mock.Mock(return_value=CompareReport(n_tasks=1))
    text = types.ModuleType("council.bench.compare_text")
    text.table = mock.Mock(return_value="TABLE TEXT")
    text.markdown = mock.Mock(return_value="| md |")
    return solo_import, compare, text


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, name, data):
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return p

    def jsonl(self, name, rows):
        return self.write(name, "\n".join(json.dumps(r) for r in rows) + "\n")


class LoadCouncilTest(_Base):
    def test_plain_object(self):
        p = self.write("c.json", {"a": True, "b": False})
        correct, cats = compare_cli.load_council(p)
        self.assertEqual(correct, {"a": True, "b": False})
        self.assertEqual(cats, {})

    def test_list_with_task_id_and_id(self):
        p = self.write("c.json", [
            {"task_id": "a", "correct": True, "category": "math"},
            {"id": "b", "correct": False},
            {"id": "c"},  # no verdict: skipped
        ])
        correct, cats = compare_cli.load_council(p)
        self.assertEqual(correct, {"a": True, "b": False})
        self.assertEqual(cats, {"a": "math"})

    def test_results_wrapper(self):
        p = self.write("c.json", {"results": [{"id": "a", "correct": True}]})
        self.assertEqual(compare_cli.load_council(p)[0], {"a": True})

    def test_bench_jsonl_picks_council_mode(self):
        p = self.jsonl("results.jsonl", [
            {"id": "a", "mode": "solo:m1", "correct": False},
            {"id": "a", "mode": "council", "correct": True},
            {"id": "b", "mode": "council", "correct": None},
            {"id": "a", "mode": "random_council", "correct": False},
        ])
        correct, _ = compare_cli.load_council(p)
        self.assertEqual(correct, {"a": True, "b": False})

    def test_bench_jsonl_falls_back_to_council_variant(self):
        p = self.jsonl("results.jsonl", [
            {"id": "a", "mode": "solo:m1", "correct": True},
            {"id": "a", "mode": "random_council", "correct": True},
            {"id": "a", "mode": "council_vote_only", "correct": False},
        ])
        self.assertEqual(compare_cli.load_council(p)[0], {"a": False})

    def test_jsonl_without_council_rows(self):
        p = self.jsonl("results.jsonl", [{"id": "a", "mode": "solo:m1", "correct": True}])
        with self.assertRaises(compare_cli.InputError):
            compare_cli.load_council(p)

    def test_bench_folder(self):
        self.jsonl("run/results.jsonl", [{"id": "a", "mode": "council", "correct": True}])
        self.assertEqual(compare_cli.load_council(self.dir / "run")[0], {"a": True})

    def test_report_json_points_at_council_file(self):
        self.jsonl("run/council/results.jsonl", [{"id": "z", "mode": "council", "correct": True}])
        rep = self.write("run/report.json", {
            "rows": [], "extra": {"results_files": {"council": "council/results.jsonl"}},
        })
        self.assertEqual(compare_cli.load_council(rep)[0], {"z": True})

    def test_empty_and_missing(self):
        with self.assertRaises(compare_cli.InputError):
            compare_cli.load_council(self.write("e.json", []))
        with self.assertRaises(compare_cli.InputError):
            compare_cli.load_council(self.dir / "nope.json")
        with self.assertRaises(compare_cli.InputError):
            compare_cli.load_council(self.write("bad.json", "{not json"))
        with self.assertRaises(compare_cli.InputError):
            compare_cli.load_council(self.dir)  # folder with nothing in it

    def test_tags(self):
        self.assertEqual(compare_cli.load_tags(self.write("t.json", {"a": "math"})), {"a": "math"})
        rows = [{"task_id": "a", "category": "code"}, {"id": "b", "category": "math"}]
        self.assertEqual(compare_cli.load_tags(self.write("t2.json", rows)), {"a": "code", "b": "math"})
        with self.assertRaises(compare_cli.InputError):
            compare_cli.load_tags(self.write("t3.json", {}))


class MainTest(_Base):
    def run_main(self, argv, mods=None, meta=None, solo_rows=None):
        solo_import, compare, text = mods or _fake_modules(solo_rows, meta)
        patches = {
            "council.bench.solo_import": solo_import,
            "council.bench.compare": compare,
            "council.bench.compare_text": text,
        }
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(sys.modules, patches), contextlib.redirect_stderr(err):
            code = compare_cli.main(argv, out=out)
        return code, out.getvalue(), err.getvalue(), (solo_import, compare, text)

    def test_prints_table(self):
        solo = self.write("solo.json", {})
        council = self.write("council.json", {"t1": True})
        code, out, err, (si, cmp_, txt) = self.run_main(["--solo", str(solo), "--council", str(council)])
        self.assertEqual(code, 0, err)
        self.assertIn("TABLE TEXT", out)
        si.load_solo_report.assert_called_once_with(solo)
        args, kwargs = cmp_.compare.call_args
        self.assertEqual(args[1], {"t1": True})
        self.assertEqual(kwargs, {})
        txt.markdown.assert_not_called()

    def test_tags_and_md(self):
        solo = self.write("solo.json", {})
        council = self.write("council.json", [{"id": "t1", "correct": True, "category": "old"},
                                              {"id": "t2", "correct": False, "category": "keep"}])
        tags = self.write("tags.json", {"t1": "new"})
        md = self.dir / "sub" / "out.md"
        code, out, err, (_, cmp_, _) = self.run_main(
            ["--solo", str(solo), "--council", str(council), "--tags", str(tags), "--md", str(md)])
        self.assertEqual(code, 0, err)
        self.assertEqual(cmp_.compare.call_args.kwargs["categories"], {"t1": "new", "t2": "keep"})
        self.assertEqual(md.read_text(encoding="utf-8"), "| md |")
        self.assertIn("markdown written", out)

    def test_meta_passed_through(self):
        solo = self.write("solo.json", {})
        council = self.write("council.json", {"t1": True})
        meta = {"seat_models": {"1": "m1"}, "latency": {"m1": 2.0}, "other": 1}
        _, _, _, (_, cmp_, _) = self.run_main(
            ["--solo", str(solo), "--council", str(council)], meta=meta)
        # compare() takes seat_models as a list of model ids
        self.assertEqual(cmp_.compare.call_args.kwargs["seat_models"], ["m1"])
        self.assertEqual(cmp_.compare.call_args.kwargs["latency"], {"m1": 2.0})

    def test_seat_models_list_passed(self):
        solo = self.write("solo.json", {})
        council = self.write("council.json", {"t1": True})
        _, _, _, (_, cmp_, _) = self.run_main(
            ["--solo", str(solo), "--council", str(council)], meta={"seat_models": ["m1", "m2"]})
        self.assertEqual(cmp_.compare.call_args.kwargs["seat_models"], ["m1", "m2"])

    def test_real_modules_end_to_end(self):
        rows = [{"model": m, "task": t, "correct": c}
                for m, cs in {"a": [True, False, True], "b": [False, False, True]}.items()
                for t, c in zip(("t1", "t2", "t3"), cs)]
        solo = self.write("solo.json", rows)
        council = self.write("council.json", {"t1": True, "t2": True, "t3": False})
        tags = self.write("tags.json", {"t1": "math", "t2": "code", "t3": "math"})
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err):
            code = compare_cli.main(
                ["--solo", str(solo), "--council", str(council), "--tags", str(tags)], out=out)
        self.assertEqual(code, 0, err.getvalue())
        text = out.getvalue()
        for word in ("council", "majority_vote", "council vs best solo (a)", "math", "code"):
            self.assertIn(word, text)

    def test_missing_solo_file(self):
        council = self.write("council.json", {"t1": True})
        code, out, err, _ = self.run_main(["--solo", str(self.dir / "no.json"), "--council", str(council)])
        self.assertEqual(code, 2)
        self.assertIn("not found", err)
        self.assertEqual(out, "")

    def test_missing_council_file(self):
        solo = self.write("solo.json", {})
        code, _, err, _ = self.run_main(["--solo", str(solo), "--council", str(self.dir / "no.json")])
        self.assertEqual(code, 2)
        self.assertIn("council file not found", err)

    def test_missing_tags_file(self):
        solo = self.write("solo.json", {})
        council = self.write("council.json", {"t1": True})
        code, _, err, _ = self.run_main(
            ["--solo", str(solo), "--council", str(council), "--tags", str(self.dir / "x.json")])
        self.assertEqual(code, 2)
        self.assertIn("tags file not found", err)

    def test_empty_council_rows(self):
        solo = self.write("solo.json", {})
        council = self.write("council.json", [])
        code, _, err, _ = self.run_main(["--solo", str(solo), "--council", str(council)])
        self.assertEqual(code, 2)
        self.assertIn("no usable", err)

    def test_empty_solo_rows(self):
        solo = self.write("solo.json", {})
        council = self.write("council.json", {"t1": True})
        code, _, err, _ = self.run_main(
            ["--solo", str(solo), "--council", str(council)], solo_rows=[])
        self.assertEqual(code, 2)
        self.assertIn("no usable rows", err)

    def test_solo_loader_raises(self):
        solo = self.write("solo.json", {})
        council = self.write("council.json", {"t1": True})
        mods = _fake_modules()
        mods[0].load_solo_report.side_effect = ValueError("bad shape")
        code, _, err, _ = self.run_main(["--solo", str(solo), "--council", str(council)], mods=mods)
        self.assertEqual(code, 2)
        self.assertIn("bad shape", err)

    def test_missing_required_args(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = compare_cli.main([], out=io.StringIO())
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
