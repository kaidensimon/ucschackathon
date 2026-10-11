"""Tests for the 1.5 subcommands of council.cli (unittest only, mock mode)."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from council import cli
from council.api.controller import RunController
from council.core import event_types as ET
from council.core.schemas import RunState
from council.probe import lie_report


def _go(argv, ctrl=None):
    out, err = io.StringIO(), io.StringIO()
    ctrl = ctrl or RunController.build_mock(speed=1000)
    with contextlib.redirect_stderr(err):
        code = asyncio.run(cli.main(argv, out=out, controller=ctrl))
    return code, out.getvalue(), err.getvalue()


def _ctrl_with_run():
    ctrl = RunController.build_mock(speed=1000)
    ctrl.store.create_run("r1", "task one", None, "standard", RunState.INTAKE)
    ctrl.store.append_event("r1", ET.RUN_CREATED, {"task": "task one"})
    return ctrl


class ParserTests(unittest.TestCase):
    def test_new_commands_parse(self):
        parse = cli.build_parser().parse_args
        self.assertEqual(parse(["summary", "--run", "x"]).run, "x")
        self.assertIsNone(parse(["lies"]).run)
        parse(["cards"])
        parse(["memory"])
        ns = parse(["compare", "--solo", "a", "--council", "b", "--md", "c"])
        self.assertEqual((ns.solo, ns.council, ns.md), ("a", "b", "c"))
        ns = parse(["steer", "--project", "p", "--model", "m", "--rule", "r", "--opposite", "o"])
        self.assertEqual((ns.project, ns.model, ns.rule, ns.opposite), ("p", "m", "r", "o"))

    def test_required_flags(self):
        for argv in (["compare", "--solo", "a"], ["steer", "--model", "m", "--rule", "r"]):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                cli.build_parser().parse_args(argv)

    def test_run_keeps_k_and_effort(self):
        ns = cli.build_parser().parse_args(["run", "t", "--k", "2", "--effort", "light"])
        self.assertEqual((ns.k, ns.effort), (2, "light"))


class SummaryTests(unittest.TestCase):
    def test_no_runs(self):
        code, out, _ = _go(["summary"])
        self.assertEqual(code, 1)
        self.assertIn("no runs", out)

    def test_unknown_run(self):
        code, out, _ = _go(["summary", "--run", "nope"], _ctrl_with_run())
        self.assertEqual(code, 1)
        self.assertIn("nope", out)

    def test_default_is_last_run(self):
        code, out, _ = _go(["summary"], _ctrl_with_run())
        self.assertEqual(code, 0, out)
        self.assertIn("r1", out)

    def test_named_run(self):
        code, out, _ = _go(["summary", "--run", "r1"], _ctrl_with_run())
        self.assertEqual(code, 0, out)
        self.assertIn("RUN r1", out)


class LiesTests(unittest.TestCase):
    def test_missing_report_is_said(self):
        code, out, _ = _go(["lies", "--run", "r1"], _ctrl_with_run())
        self.assertEqual(code, 0)
        self.assertIn("no lie report", out)

    def test_stored_report_is_printed(self):
        ctrl = _ctrl_with_run()
        report = lie_report.build_report("r1", [], [(0, "gpt-oss-20b")], [])
        ctrl.store.kv_put("lie_reports", "r1", report.model_dump(mode="json"))
        code, out, _ = _go(["lies"], ctrl)
        self.assertEqual(code, 0, out)
        self.assertNotIn("no lie report", out)
        self.assertIn("gpt-oss-20b", out)

    def test_report_from_event(self):
        ctrl = _ctrl_with_run()
        report = lie_report.build_report("r1", [], [(0, "glm-small")], [])
        ctrl.store.append_event("r1", ET.LIE_REPORT, {"report": report.model_dump(mode="json")})
        code, out, _ = _go(["lies", "--run", "r1"], ctrl)
        self.assertEqual(code, 0, out)
        self.assertIn("glm-small", out)


class CardsMemoryTests(unittest.TestCase):
    def test_cards_one_row_per_model(self):
        ctrl = RunController.build_mock(speed=1000)
        n = len(ctrl.registry)
        code, out, _ = _go(["cards"], ctrl)
        self.assertEqual(code, 0, out)
        self.assertIn("gpt-oss-20b", out)
        self.assertGreaterEqual(len(out.strip().splitlines()), n)

    def test_memory_prints_plan(self):
        code, out, _ = _go(["memory"])
        self.assertEqual(code, 0, out)
        self.assertIn("seats: ", out)
        self.assertIn("fits: ", out)
        self.assertIn("GiB", out)
        self.assertLessEqual(len(out.splitlines()[0].split(": ", 1)[1].split(", ")), cli.MEMORY_SEATS)


class CompareTests(unittest.TestCase):
    def test_missing_file_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            code, _, err = _go(["compare", "--solo", str(Path(d) / "a.json"),
                                "--council", str(Path(d) / "b.json")])
        self.assertNotEqual(code, 0)
        self.assertIn("not found", err)


class SteerTests(unittest.TestCase):
    def test_mock_mode_says_so(self):
        code, out, _ = _go(["steer", "--project", ".", "--model", "m", "--rule", "be brief"])
        self.assertEqual(code, 2)
        self.assertIn("mock mode", out)

    def test_no_service_wired_is_clear(self):
        ctrl = RunController.build_mock(speed=1000)
        ctrl.config.gateway.mock = False
        ctrl.steer = None  # the controller wires one when there is an activation source
        code, out, _ = _go(["steer", "--project", ".", "--model", "m", "--rule", "r"], ctrl)
        self.assertEqual(code, 2)
        self.assertIn("no steer service", out)

    def test_fake_service_trains(self):
        from council.core.schemas_v15 import SteerCard

        calls = []

        class Fake:
            async def train(self, project, model_id, rule_pairs, n_layer=None):
                calls.append((project, model_id, rule_pairs))
                return SteerCard(project=project, model_id=model_id, active=True, scale=0.5,
                                 examples=len(rule_pairs), reason="ok")

        ctrl = RunController.build_mock(speed=1000)
        ctrl.config.gateway.mock = False
        ctrl.steer = Fake()
        code, out, _ = _go(["steer", "--project", "proj", "--model", "m1", "--rule", "be brief",
                            "--opposite", "be long"], ctrl)
        self.assertEqual(code, 0, out)
        self.assertEqual(calls[0][:2], ("proj", "m1"))
        self.assertIn("be long", calls[0][2][0][1])
        self.assertEqual(json.loads(out)["model_id"], "m1")

    def test_inactive_card_exits_1(self):
        from council.core.schemas_v15 import SteerCard

        class Fake:
            async def train(self, project, model_id, rule_pairs, n_layer=None):
                return SteerCard(project=project, model_id=model_id, active=False, reason="no layer")

        ctrl = RunController.build_mock(speed=1000)
        ctrl.config.gateway.mock = False
        ctrl.steer = Fake()
        code, out, _ = _go(["steer", "--project", "p", "--model", "m", "--rule", "r"], ctrl)
        self.assertEqual(code, 1)
        self.assertIn("no layer", out)


if __name__ == "__main__":
    unittest.main()
