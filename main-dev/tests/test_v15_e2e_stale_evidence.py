"""Mini verification (1.5): stale evidence in the work report, end to end in mock mode.

Real box failure: the first version of a test file failed its unittest check, a fix task
rewrote the file and it passed. The review seats still read the old error. These tests drive the
real WorksPipeline (real Inspector, real sandbox, real report) and read the real report_text.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from council.api.run_pipeline import RunPipeline
from council.core.config import Config
from council.core.schemas import CallResult, Check, MicroTask, Plan, SeatAssignment, TaskStatus
from council.works import review as review_mod
from council.works.pipeline import WorksPipeline
from council.works.report import report_text

CODE = "def count_words(text):\n    return len(text.split())\n"
MARKER = "OLD_STALE_MARKER_7431"
BAD_TEST = (
    "import unittest\n"
    "from textstats import count_words\n\n\n"
    "class T(unittest.TestCase):\n"
    "    def test_count(self):\n"
    f"        self.assertEqual(count_words('a b c'), 4, '{MARKER}')\n"
)
GOOD_TEST = BAD_TEST.replace(", 4, '" + MARKER + "')", ", 3)")
EMPTY_TEST = "VALUE = 1\n"  # a file in tests/ that holds no test: unittest says "Ran 0 tests"
UNIT = "python -m unittest discover -s tests"
TEST_PATH = "tests/test_textstats.py"


def run(coro):
    return asyncio.run(coro)


def write(path: str, content: str) -> dict:
    return {"ops": [{"op": "write_file", "path": path, "content": content}], "notes": "", "blocked": None}


class FakeGateway:
    def __init__(self, fn) -> None:
        self.fn = fn
        self.calls: list[tuple[str, int]] = []

    async def call(self, spec):
        tid, attempt = spec.meta["task_id"], int(spec.meta["attempt"])
        self.calls.append((tid, attempt))
        out = self.fn(tid, attempt)
        return CallResult(call_id=spec.call_id, ok=True, model_id=spec.model_id,
                          content=json.dumps(out), parsed=out)


def make_cfg() -> Config:
    cfg = Config()
    cfg.gateway.mock = True
    cfg.workers.slots = 1
    cfg.inspector.allowed_executables = ["python", "python3"]
    return cfg


def task(tid: str, path: str, checks=None) -> MicroTask:
    return MicroTask(
        id=tid, title=tid, goal=f"write {path}", write_set=[path], output_contract=f"{path} exists",
        acceptance=checks if checks is not None else [Check(type="exists", id=f"{tid}.exists", path=path)],
    )


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.workspace = root / "project"
        self.workspace.mkdir()
        self.events: list[tuple[str, dict]] = []
        self.root = root

    def pipe(self, gateway) -> WorksPipeline:
        return WorksPipeline(gateway, lambda t, p: self.events.append((t, p)), make_cfg(),
                             self.root / "runs" / "r1", "worker-m", "senior-m", None)


class TestStaleEvidence(Base):
    """t1 writes the code, t2 writes a wrong test (fails 3 times), fix1_1 rewrites the test (passes)."""

    def go(self, fix_is_good: bool = True):
        def fn(tid, n):
            if tid == "t1":
                return write("textstats.py", CODE)
            if tid.startswith("fix"):
                return write(TEST_PATH, GOOD_TEST if fix_is_good else BAD_TEST)
            return write(TEST_PATH, BAD_TEST)

        gw = FakeGateway(fn)
        pipe = self.pipe(gw)
        plan = Plan(tasks=[
            task("t1", "textstats.py"),
            task("t2", TEST_PATH, [Check(type="command", id="t2.unit", cmd=UNIT)]),
        ])
        fix = task("fix1_1", TEST_PATH, [Check(type="command", id="fx.unit", cmd=UNIT)])

        async def both():
            first = await pipe.execute("r1", plan, self.workspace)
            second = await pipe.execute_fixes("r1", plan, [fix], self.workspace)
            return first, second

        first, second = run(both())
        return pipe, first, second

    def test_current_state_says_all_checks_pass_after_fix(self) -> None:
        pipe, first, second = self.go()
        # the first run really failed
        self.assertEqual(pipe.statuses["t2"], TaskStatus.failed)
        self.assertEqual(pipe.statuses["fix1_1"], TaskStatus.passed)
        text = report_text(second)
        self.assertTrue(text.startswith("CURRENT STATE (judge this)\nAll current checks pass."), text[:200])
        self.assertNotIn("FAILED", text)
        self.assertNotIn("check(s) FAIL", text)
        self.assertTrue(second.final_checks)
        self.assertTrue(all(c.ok for c in second.final_checks),
                        [(c.check_id, c.error, c.output_tail) for c in second.final_checks])

    def test_old_error_text_is_absent_from_the_report(self) -> None:
        pipe, first, second = self.go()
        # precondition: the old error really exists in the record and in the first report
        self.assertIn(MARKER, pipe.attempts["t2"][-1].error_tail)
        self.assertIn(MARKER, report_text(first))
        # after the fix it is gone from the text the seats read
        text = report_text(second)
        self.assertNotIn(MARKER, text)
        self.assertNotIn("AssertionError", text)
        self.assertNotIn("3 != 4", text)

    def test_failed_task_is_marked_superseded(self) -> None:
        pipe, first, second = self.go()
        by_id = {t.id: t for t in second.tasks}
        self.assertEqual(by_id["t2"].status, TaskStatus.failed)
        self.assertEqual(by_id["t2"].superseded_by, "fix1_1")
        self.assertIsNone(by_id["t1"].superseded_by)
        self.assertIsNone(by_id["fix1_1"].superseded_by)
        self.assertEqual((second.summary.passed, second.summary.failed, second.summary.superseded), (2, 0, 1))
        text = report_text(second)
        self.assertIn("- t2 [failed, superseded by fix1_1: its files were rewritten later]", text)
        self.assertIn("superseded=1", text)
        self.assertIn("failed=0", text)
        # the file the seats see is the fixed one
        self.assertEqual(second.files[TEST_PATH], GOOD_TEST)

    def test_control_unfixed_failure_is_not_marked_superseded(self) -> None:
        # The fix writes the same wrong test again: it fails too, so nothing is superseded
        # and the failures stay on record in HISTORY.
        pipe, first, second = self.go(fix_is_good=False)
        self.assertEqual(pipe.statuses["t2"], TaskStatus.failed)
        self.assertEqual(pipe.statuses["fix1_1"], TaskStatus.failed)
        by_id = {t.id: t for t in second.tasks}
        self.assertIsNone(by_id["t2"].superseded_by)
        self.assertEqual((second.summary.failed, second.summary.superseded), (2, 0))
        text = report_text(second)
        self.assertIn("failed=2", text)
        self.assertIn("- t2 [failed] t2", text)
        self.assertIn(MARKER, text)  # the real error is still shown
        self.assertNotIn("superseded by", text)

    def test_control_unfixed_failure_does_not_say_all_checks_pass(self) -> None:
        # Both test-writing tasks failed and their file was rolled back, so tests/ is empty and
        # the unittest check ran zero tests (INVALID). The only valid check left is
        # "textstats.py exists". CURRENT STATE must not tell the seats that everything passes.
        pipe, first, second = self.go(fix_is_good=False)
        self.assertFalse((self.root / "runs" / "r1" / "ws" / TEST_PATH).exists())
        text = report_text(second)
        self.assertNotIn("All current checks pass.", text.split("HISTORY")[0])
        self.assertFalse(RunPipeline._checks_pass(second) and second.summary.failed > 0)

    def test_review_prompt_carries_the_current_state_not_the_old_error(self) -> None:
        pipe, first, second = self.go()
        seat = SeatAssignment(seat_no=1, model_id="m1")
        spec = review_mod.build_review_call("r1", seat, report_text(second), "count words", 0)
        user = spec.messages[1]["content"]
        self.assertIn("CURRENT STATE (judge this)", user)
        self.assertIn("All current checks pass.", user)
        self.assertNotIn(MARKER, user)
        self.assertTrue(RunPipeline._checks_pass(second))


class TestZeroTestCheck(Base):
    def run_plan(self, with_valid_check: bool):
        checks = [Check(type="command", id="zero.unit", cmd=UNIT)]
        if with_valid_check:
            checks.insert(0, Check(type="exists", id="t1.exists", path=TEST_PATH))
        gw = FakeGateway(lambda tid, n: write(TEST_PATH, EMPTY_TEST))
        pipe = self.pipe(gw)
        rep = run(pipe.execute("r1", Plan(tasks=[task("t1", TEST_PATH, checks)]), self.workspace))
        return pipe, gw, rep

    def test_zero_test_check_is_invalid_and_fails_nothing(self) -> None:
        pipe, gw, rep = self.run_plan(with_valid_check=True)
        zero = [c for c in rep.final_checks if c.check_id == "zero.unit"]
        self.assertEqual(len(zero), 1)
        self.assertTrue(zero[0].invalid, (zero[0].output_tail, zero[0].error))
        # the task passed on the first try: an invalid check never fails the work
        self.assertEqual(pipe.statuses["t1"], TaskStatus.passed)
        self.assertEqual(len(gw.calls), 1)
        self.assertEqual((rep.summary.passed, rep.summary.failed), (1, 0))
        text = report_text(rep)
        self.assertIn("- zero.unit: INVALID CHECK (the check is broken, ignore it)", text)
        self.assertIn("All current checks pass.", text)
        self.assertNotIn("FAILED", text)
        self.assertNotIn("Ran 0 tests", text)
        self.assertNotIn("FAIL", text)
        # the controller's own gate agrees: the valid check ran and passed
        self.assertTrue(RunPipeline._checks_pass(rep))

    def test_only_invalid_checks_means_no_checks_ran(self) -> None:
        pipe, gw, rep = self.run_plan(with_valid_check=False)
        self.assertEqual(pipe.statuses["t1"], TaskStatus.passed)
        text = report_text(rep)
        self.assertIn("No checks were run on the current files.", text)
        self.assertIn("INVALID CHECK", text)
        self.assertNotIn("FAIL", text)
        self.assertNotIn("All current checks pass.", text)
        # nothing valid ran: this is not evidence for "pointless fix"
        self.assertFalse(RunPipeline._checks_pass(rep))


if __name__ == "__main__":
    unittest.main()
