"""Tests for council.cli (unittest only)."""

from __future__ import annotations

import asyncio
import contextlib
import io
import tempfile
import unittest

from council import cli


class CliTests(unittest.TestCase):
    def test_demo_exits_zero_at_high_speed(self):
        out = io.StringIO()
        code = asyncio.run(cli.main(["demo", "--speed", "1000"], out=out))
        text = out.getvalue()
        self.assertEqual(code, 0, text[-2000:])
        self.assertIn("run.created", text)
        self.assertIn("run.completed", text)
        self.assertNotIn("run.failed", text)

    def test_demo_skips_delta_events_by_default(self):
        out = io.StringIO()
        asyncio.run(cli.main(["demo", "--speed", "1000"], out=out))
        for line in out.getvalue().splitlines():
            if line.startswith("run "):
                continue
            self.assertNotIn(".delta", line)

    def test_run_command_parses_flags(self):
        ns = cli.build_parser().parse_args(
            ["run", "hello world", "--mode", "quick", "--deliverable", "plan"])
        self.assertEqual(ns.task, "hello world")
        self.assertEqual(ns.mode, "quick")
        self.assertEqual(ns.deliverable, "plan")

    def test_bad_mode_is_rejected(self):
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["run", "x", "--mode", "nope"])

    def test_preview_truncates_long_payloads(self):
        text = cli._preview({"k": "x" * 500})
        self.assertLessEqual(len(text), cli.PREVIEW_CHARS)
        self.assertTrue(text.endswith("..."))


def _run(argv):
    out = io.StringIO()
    with contextlib.redirect_stderr(io.StringIO()):  # bench progress lines go to stderr
        code = asyncio.run(cli.main(argv, out=out))
    return code, out.getvalue()


class NewCommandTests(unittest.TestCase):
    def test_build_parses(self):
        ns = cli.build_parser().parse_args(["build", "t", "--workspace", "w", "--auto-delegate"])
        self.assertEqual((ns.task, ns.workspace, ns.auto_delegate), ("t", "w", True))

    def test_effort_flag(self):
        parse = cli.build_parser().parse_args
        self.assertEqual(parse(["run", "t"]).effort, "auto")
        self.assertEqual(cli._effort_options(parse(["run", "t"])), {})
        self.assertEqual(cli._effort_options(parse(["run", "t", "--effort", "heavy"])), {"effort": "heavy"})
        ns = parse(["build", "t", "--workspace", "w", "--effort", "fixed"])
        self.assertEqual(cli._effort_options(ns), {"effort": "fixed"})
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parse(["run", "t", "--effort", "huge"])

    def test_build_requires_workspace(self):
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["build", "t"])

    def test_bench_parses(self):
        ns = cli.build_parser().parse_args(
            ["bench", "--tasks", "p", "--modes", "a,b", "--split", "calibration", "--limit", "3"])
        self.assertEqual((ns.tasks, ns.modes, ns.split, ns.limit), ("p", "a,b", "calibration", 3))

    def test_build_runs_in_mock(self):
        with tempfile.TemporaryDirectory() as ws:
            code, text = _run(["build", "make a tiny script", "--workspace", ws,
                               "--auto-delegate", "--speed", "1000"])
        self.assertIn("run.created", text)
        self.assertIn(code, (0, 1))

    def test_pull_list_order_and_reminder(self):
        code, text = _run(["models", "pull-list"])
        lines = text.strip().splitlines()
        self.assertEqual(code, 0)
        pulls = [x for x in lines if x.startswith("ollama pull ")]
        self.assertGreater(len(pulls), 3)
        self.assertEqual(len(pulls), len(set(pulls)))
        self.assertIn("Supply-chain", lines[-1])

    def test_pull_list_sorted_smallest_first(self):
        from council.core.schemas import MeasuredStats, ModelEntry
        reg = [ModelEntry(id="big", ollama_tag="b:1", measured=MeasuredStats(ram_gb_live=40)),
               ModelEntry(id="small", ollama_tag="s:1", measured=MeasuredStats(ram_gb_live=2)),
               ModelEntry(id="notag")]
        lines = cli.pull_lines(reg)
        self.assertEqual(lines[:2], ["ollama pull s:1", "ollama pull b:1"])
        self.assertEqual(len(lines), 3)

    def test_bench_prints_markdown(self):
        code, text = _run(["bench", "--limit", "2", "--modes", "council_vote_only",
                           "--speed", "1000"])
        self.assertEqual(code, 0, text)
        self.assertIn("| mode |", text)

    def test_probe_needs_a_target(self):
        code, _ = _run(["probe"])
        self.assertEqual(code, 2)

    def test_probe_unknown_model(self):
        code, text = _run(["probe", "--model", "nope-xyz"])
        self.assertEqual(code, 1)
        self.assertIn("nope-xyz", text)

    def test_probe_model_prints_stats(self):
        code, text = _run(["probe", "--model", "gpt-oss-20b", "--speed", "1000"])
        self.assertEqual(code, 0, text)
        self.assertIn("tps_1", text)

    def test_probe_box(self):
        code, text = _run(["probe", "--box", "--speed", "1000"])
        self.assertEqual(code, 0, text)
        self.assertIn("recommended_max_concurrent_models", text)

    def test_train_probe_unknown_model(self):
        code, _ = _run(["train-probe", "--model", "nope-xyz"])
        self.assertEqual(code, 1)

    def test_chronicle_export_empty(self):
        code, text = _run(["chronicle", "export"])
        self.assertEqual(code, 0)
        self.assertIsInstance(text, str)


def _bench(argv, break_models=None):
    """Run `bench` on a throwaway mock controller. Returns (exit code, stdout, stderr)."""
    from council.api.controller import RunController

    ctrl = RunController.build_mock(speed=1000)
    if break_models is not None:
        real = ctrl.host.load

        async def load(model_id, profile, run_id="manual"):
            if break_models == "all" or model_id in break_models:
                raise RuntimeError(f"cannot load {model_id}: out of memory")
            return await real(model_id, profile, run_id)

        ctrl.host.load = load
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            code = asyncio.run(cli.main(["bench"] + argv, out=out, controller=ctrl))
    finally:
        ctrl.store.close()
    return code, out.getvalue(), err.getvalue()


class BenchFlagTests(unittest.TestCase):
    def parse(self, *argv):
        return cli.build_parser().parse_args(["bench", *argv])

    def test_new_flags_parse(self):
        ns = self.parse("--calibration-limit", "7", "--reasoning", "council", "--no-resume",
                        "--calibration-models", "all", "--max-output-tokens", "50",
                        "--max-reasoning-tokens", "60")
        req = cli.bench_request(ns)
        self.assertEqual((req.calibration_limit, req.reasoning, req.resume, req.calibration_models),
                         (7, "council", False, "all"))
        self.assertEqual((req.max_output_tokens, req.max_reasoning_tokens), (50, 60))
        with self.assertRaises(SystemExit):
            self.parse("--reasoning", "loud")

    def test_plain_bench_keeps_the_spec_settings(self):
        req = cli.bench_request(self.parse())
        self.assertEqual((req.reasoning, req.calibration_limit, req.limit, req.resume),
                         ("max", None, None, True))
        self.assertEqual(req.calibration_models, "lineup")
        self.assertEqual(req.modes, list(cli.DEFAULT_BENCH_MODES))
        self.assertTrue(req.progress)

    def test_fast(self):
        req = cli.bench_request(self.parse("--fast"))
        self.assertEqual((req.reasoning, req.calibration_limit, req.limit),
                         ("off", cli.FAST_CALIBRATION_LIMIT, cli.FAST_LIMIT))
        self.assertEqual((cli.FAST_CALIBRATION_LIMIT, cli.FAST_LIMIT), (6, 12))

    def test_fast_fills_only_what_was_not_given(self):
        req = cli.bench_request(self.parse("--fast", "--limit", "4", "--reasoning", "max",
                                           "--calibration-limit", "9", "--modes", "council"))
        self.assertEqual((req.reasoning, req.calibration_limit, req.limit, req.modes),
                         ("max", 9, 4, ["council"]))

    def test_no_calibration(self):
        self.assertEqual(cli.bench_request(self.parse("--no-calibration")).calibration_limit, 0)
        req = cli.bench_request(self.parse("--fast", "--no-calibration", "--calibration-limit", "5"))
        self.assertEqual(req.calibration_limit, 0)


class BenchRunTests(unittest.TestCase):
    MODES = "solo:gpt-oss-20b,council_vote_only,council"

    def test_fast_prints_progress_and_a_report_with_its_settings(self):
        code, out, err = _bench(["--fast", "--modes", self.MODES])
        self.assertEqual(code, 0, out + err)
        lines = [ln for ln in err.splitlines() if ln.startswith("bench: ")]
        self.assertIn("reasoning off", lines[0])
        self.assertTrue(any(ln.startswith("bench: calibration: model 1/") for ln in lines), err)
        solo = [ln for ln in lines if ln.startswith("bench: solo: model ")]
        self.assertTrue(solo, err)
        for part in ("calls ", "accuracy so far", "elapsed", "left in this pass ~"):
            self.assertIn(part, solo[0])
        self.assertTrue(any("council: 12/12 tasks done" in ln for ln in lines), err)
        self.assertIn("Settings used", out)
        self.assertIn("reasoning off", out)
        self.assertIn("limit 12", out)
        self.assertIn("6 tasks (limit 6)", out)
        self.assertIn("| mode |", out)
        self.assertIn("| council | 12 |", out)
        self.assertNotIn("NOT RUN", out)

    def test_no_calibration_is_stated(self):
        code, out, err = _bench(["--limit", "2", "--no-calibration", "--modes", "council_vote_only"])
        self.assertEqual(code, 0, out + err)
        self.assertIn("calibration: skipped", out)
        self.assertNotIn("bench: calibration:", err)
        self.assertIn("reasoning max", out)

    def test_a_model_that_fails_to_load_gives_exit_2_and_no_number(self):
        code, out, err = _bench(["--limit", "2", "--modes", "solo:gpt-oss-20b,solo:glm-small"],
                                break_models={"glm-small"})
        self.assertEqual(code, 2, out + err)
        self.assertIn("glm-small failed to load", err)
        self.assertIn("solo:glm-small NOT RUN", err)
        self.assertIn("NOT RUN", out)
        self.assertIn("| solo:gpt-oss-20b | 2 |", out)
        self.assertNotIn("| solo:glm-small |", out)

    def test_no_model_loads_prints_no_table_of_zeros(self):
        code, out, err = _bench(["--limit", "2", "--no-calibration", "--modes", self.MODES],
                                break_models="all")
        self.assertEqual(code, 2, out + err)
        self.assertIn("failed to load", err)
        self.assertIn("No results", out)
        self.assertNotIn("| mode |", out)
        self.assertNotIn("0.0%", out)
        for mode in self.MODES.split(","):
            self.assertIn(f"- {mode}: ", out)


if __name__ == "__main__":
    unittest.main()
