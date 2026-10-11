"""End to end CLI smoke in mock mode: run --k 2, run --k 6, summary, lies, cards, memory.

Real classes only: council.cli.main + RunController.build_mock. Each command must exit 0
and print non-empty text.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import unittest

from council import cli
from council.api.controller import RunController
from council.core import event_types as ET

TASK = "Explain the difference between a mutex and a semaphore in two sentences."


def _go(argv, ctrl):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err):
        code = asyncio.run(cli.main(argv, out=out, controller=ctrl))
    return code, out.getvalue(), err.getvalue()


def _run_ctrl(k):
    """Run the council once at size k on a fresh mock controller. Returns (ctrl, code, out)."""
    ctrl = RunController.build_mock(speed=1000)
    code, out, _ = _go(["run", TASK, "--k", str(k), "--speed", "1000"], ctrl)
    return ctrl, code, out


class RunSizeSmoke(unittest.TestCase):
    def _check(self, k):
        ctrl, code, out = _run_ctrl(k)
        self.assertEqual(code, 0, out[-2000:])
        self.assertTrue(out.strip())
        self.assertIn(ET.RUN_COMPLETED, out)
        self.assertNotIn(ET.RUN_FAILED, out)
        return ctrl, out

    def test_run_k2_exit_0_prints_events(self):
        self._check(2)

    def test_run_k6_exit_0_prints_events(self):
        self._check(6)

    def test_run_k2_and_k6_seat_different_counts(self):
        ctrl2, _ = self._check(2)
        ctrl6, _ = self._check(6)

        def seated(ctrl):
            rid = ctrl.store.list_runs()[0].get("run_id") or ctrl.store.list_runs()[0].get("id")
            best = 0
            for ev in ctrl.store.events_for_run(str(rid)):
                ids = ev.payload.get("seats") or ev.payload.get("models") or ev.payload.get("lineup")
                if isinstance(ids, list):
                    best = max(best, len(ids))
            return best

        n2, n6 = seated(ctrl2), seated(ctrl6)
        self.assertGreater(n2, 0, "k=2 run stored no seat list")
        self.assertGreater(n6, 0, "k=6 run stored no seat list")
        self.assertLessEqual(n2, 2)
        self.assertLessEqual(n6, 6)
        self.assertGreater(n6, n2)


class StoredRunCommands(unittest.TestCase):
    """summary and lies read the run that `run` just stored (same controller, same store)."""

    @classmethod
    def setUpClass(cls):
        cls.ctrl, cls.code, cls.out = _run_ctrl(3)

    def test_run_before_stored_commands_ok(self):
        self.assertEqual(self.code, 0, self.out[-2000:])
        self.assertTrue(self.ctrl.store.list_runs())

    def test_summary_exit_0_non_empty(self):
        code, out, _ = _go(["summary"], self.ctrl)
        self.assertEqual(code, 0, out)
        self.assertTrue(out.strip())
        rid = self.ctrl.store.list_runs()[0].get("run_id") or self.ctrl.store.list_runs()[0].get("id")
        self.assertIn(str(rid), out)

    def test_lies_exit_0_non_empty(self):
        code, out, _ = _go(["lies"], self.ctrl)
        self.assertEqual(code, 0, out)
        self.assertTrue(out.strip())


class ColdCommands(unittest.TestCase):
    def test_cards_exit_0_one_line_per_model(self):
        ctrl = RunController.build_mock(speed=1000)
        n = len(ctrl.registry)
        code, out, _ = _go(["cards"], ctrl)
        self.assertEqual(code, 0, out)
        self.assertGreaterEqual(len(out.strip().splitlines()), n)

    def test_memory_exit_0_non_empty(self):
        code, out, _ = _go(["memory"], RunController.build_mock(speed=1000))
        self.assertEqual(code, 0, out)
        self.assertIn("seats:", out)
        self.assertIn("fits:", out)


if __name__ == "__main__":
    unittest.main()
