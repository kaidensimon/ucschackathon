"""Tests for council.works.pipeline: the EXECUTING phase end to end, in mock mode."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from council.core.config import Config
from council.core.schemas import CallResult, Check, MicroTask, ModelEntry, Plan, TaskStatus
from council.gateway import mock_scenario
from council.gateway.gateway import Gateway
from council.gateway.mock import MockResponder
from council.works.pipeline import WorksPipeline


def run(coro):
    return asyncio.run(coro)


class ScenarioResponder:
    """MockResponder, but worker calls get the canned scenario output."""

    def __init__(self) -> None:
        self.inner = MockResponder(seed=1)
        self.worker_calls: list[tuple[str, int, str]] = []

    async def respond(self, spec, on_delta=None):
        if spec.purpose != "worker":
            return await self.inner.respond(spec, on_delta)
        tid, attempt = spec.meta["task_id"], int(spec.meta["attempt"])
        self.worker_calls.append((tid, attempt, spec.model_id))
        out = mock_scenario.worker_output_for(tid, attempt)
        return CallResult(call_id=spec.call_id, ok=True, model_id=spec.model_id,
                          content=json.dumps(out), parsed=out, finish_reason="stop",
                          tokens_in=10, tokens_out=20)


class FakeGateway:
    """Calls fn(task_id, attempt, spec) -> WorkerOutput dict (or None for a broken reply)."""

    def __init__(self, fn, delay: float = 0.0) -> None:
        self.fn = fn
        self.delay = delay
        self.calls: list[tuple[str, int, str]] = []
        self.specs: list = []
        self.active = 0
        self.peak = 0

    async def call(self, spec):
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            tid, attempt = spec.meta["task_id"], int(spec.meta["attempt"])
            self.calls.append((tid, attempt, spec.model_id))
            self.specs.append(spec)
            out = self.fn(tid, attempt, spec)
            if out is None:
                return CallResult(call_id=spec.call_id, ok=False, error="invalid_output")
            return CallResult(call_id=spec.call_id, ok=True, model_id=spec.model_id,
                              content=json.dumps(out), parsed=out)
        finally:
            self.active -= 1


def make_cfg(slots: int = 4) -> Config:
    cfg = Config()
    cfg.gateway.mock = True
    cfg.workers.slots = slots
    cfg.inspector.allowed_executables = ["python", "python3"]
    return cfg


def write(path: str, content: str) -> dict:
    return {"ops": [{"op": "write_file", "path": path, "content": content}], "notes": "", "blocked": None}


def task(tid: str, path: str, deps=(), checks=None) -> MicroTask:
    return MicroTask(
        id=tid, title=tid, goal=f"write {path}", write_set=[path], output_contract=f"{path} exists",
        acceptance=checks if checks is not None else [Check(type="exists", id=f"{tid}.exists", path=path)],
        deps=list(deps),
    )


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.workspace = root / "project"
        self.workspace.mkdir()
        self.run_dir = root / "runs" / "r1"
        self.events: list[tuple[str, dict]] = []

    def pipe(self, gateway, cfg=None, senior="senior-m", reviewer=None) -> WorksPipeline:
        return WorksPipeline(gateway, lambda t, p: self.events.append((t, p)), cfg or make_cfg(),
                             self.run_dir, "worker-m", senior, reviewer)

    def types(self) -> list[str]:
        return [t for t, _ in self.events]

    def of(self, type_: str) -> list[dict]:
        return [p for t, p in self.events if t == type_]


class TestEndToEnd(Base):
    def test_scenario_through_real_gateway(self) -> None:
        cfg = make_cfg()
        responder = ScenarioResponder()
        gw = Gateway(cfg, [ModelEntry(id="worker-m"), ModelEntry(id="senior-m")], None, None,
                     responder=responder)
        plan = Plan.model_validate(mock_scenario.plan_for(""))
        (self.workspace / "NOTES.txt").write_text("keep me", encoding="utf-8")
        pipe = self.pipe(gw, cfg)

        async def go():
            rep = await pipe.execute("r1", plan, self.workspace)
            before = sorted(p.name for p in self.workspace.iterdir())
            files = await pipe.integrate("r1", self.workspace)
            return rep, before, files

        rep, before, files = run(go())

        # every task passed, the buggy one on its second try
        self.assertEqual(rep.summary.passed, len(plan.tasks))
        self.assertEqual(rep.summary.failed + rep.summary.blocked + rep.summary.skipped, 0)
        attempts = {t.id: t.attempts for t in rep.tasks}
        for tid, n in attempts.items():
            self.assertEqual(n, 2 if tid == mock_scenario.BUGGY_TASK_ID else 1, tid)
        self.assertEqual(sum(1 for c in responder.worker_calls if c[0] == mock_scenario.BUGGY_TASK_ID), 2)
        self.assertEqual(len(pipe.attempts[mock_scenario.BUGGY_TASK_ID]), 2)
        self.assertFalse(pipe.attempts[mock_scenario.BUGGY_TASK_ID][0].ok)

        # integration passed and nothing is missing
        self.assertTrue(rep.integration)
        self.assertTrue(all(c.ok for c in rep.integration), [c.error for c in rep.integration])
        self.assertEqual(rep.deviations, [])
        self.assertEqual(rep.diff_stats.files_added + rep.diff_stats.files_changed, 9)
        self.assertGreater(rep.diff_stats.lines_added, 0)

        # the real workspace was untouched until integrate
        self.assertEqual(before, ["NOTES.txt"])
        self.assertEqual(len(files), 9)
        for rel in ("ratelimiter/token_bucket.py", "tests/test_factory.py", "README.md"):
            self.assertTrue((self.workspace / rel).is_file(), rel)
        self.assertEqual((self.workspace / "NOTES.txt").read_text(encoding="utf-8"), "keep me")

        # events
        types = self.types()
        self.assertEqual(types[0], "delegation.started")
        self.assertEqual(self.events[0][1]["task_count"], len(plan.tasks))
        self.assertEqual(types.count("task.queued"), len(plan.tasks))
        self.assertEqual(types.count("task.started"), len(plan.tasks))
        self.assertEqual(types.count("task.passed"), len(plan.tasks))
        self.assertEqual(types.count("task.attempt_completed"), len(plan.tasks) + 1)
        self.assertEqual(types.count("task.failed"), 0)
        self.assertEqual(types.count("check.started"), types.count("check.result"))
        self.assertGreater(types.count("check.result"), len(plan.tasks))
        bad = [p for p in self.of("task.attempt_completed") if not p["ok"]]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["task_id"], mock_scenario.BUGGY_TASK_ID)
        self.assertTrue(bad[0]["will_retry"])
        self.assertTrue(bad[0]["failing_check"])
        results = self.of("integration.result")
        self.assertEqual([r["stage"] for r in results], ["checks", "copy"])
        self.assertTrue(all(r["ok"] for r in results))
        # a task starts only after its deps passed
        order = [(t, p.get("task_id")) for t, p in self.events]
        self.assertLess(order.index(("task.passed", "t01_package_clock")),
                        order.index(("task.started", "t02_token_bucket")))
        # the retry carried the failing check back to the worker
        self.assertEqual([c[1] for c in responder.worker_calls if c[0] == mock_scenario.BUGGY_TASK_ID], [1, 2])


class TestFailures(Base):
    def test_exhausted_attempts_escalate_then_fail_and_skip_dependents(self) -> None:
        (self.workspace / "a.py").write_text("OLD = 1\n", encoding="utf-8")
        gw = FakeGateway(lambda tid, n, spec: write("a.py", "def broken(:\n"))
        plan = Plan(tasks=[task("a", "a.py"), task("b", "b.py", deps=["a"]), task("c", "c.py", deps=["b"])])
        pipe = self.pipe(gw)
        rep = run(pipe.execute("r1", plan, self.workspace))

        self.assertEqual([c[2] for c in gw.calls], ["worker-m", "worker-m", "senior-m"])
        self.assertEqual((rep.summary.failed, rep.summary.skipped), (1, 2))
        self.assertEqual(pipe.statuses["b"], TaskStatus.skipped)
        self.assertEqual(self.types().count("task.escalated"), 1)
        esc = self.of("task.escalated")[0]
        self.assertEqual((esc["from_model_id"], esc["to_model_id"]), ("worker-m", "senior-m"))
        self.assertEqual(len(self.of("task.failed")), 1)
        self.assertEqual(self.of("task.failed")[0]["attempts"], 3)
        skipped = {p["task_id"]: p for p in self.of("task.skipped")}
        self.assertEqual(sorted(skipped), ["b", "c"])
        self.assertEqual(skipped["b"]["blocked_by"], ["a"])
        # failed attempts were rolled back in the staged copy
        self.assertEqual((self.run_dir / "ws" / "a.py").read_text(encoding="utf-8"), "OLD = 1\n")
        # the retry prompt carried the failure
        self.assertIn("YOUR LAST ATTEMPT FAILED", gw.specs[1].messages[0]["content"])
        types = self.types()
        self.assertLess(types.index("task.escalated"), types.index("task.failed"))

    def test_no_senior_model_means_no_escalation(self) -> None:
        gw = FakeGateway(lambda tid, n, spec: None)
        pipe = self.pipe(gw, senior=None)
        rep = run(pipe.execute("r1", Plan(tasks=[task("a", "a.txt")]), self.workspace))
        self.assertEqual(rep.summary.failed, 1)
        self.assertEqual(len(gw.calls), 3)
        self.assertEqual(self.types().count("task.escalated"), 0)

    def test_op_outside_write_set_fails_the_attempt(self) -> None:
        gw = FakeGateway(lambda tid, n, spec: write("other.txt" if n == 1 else "a.txt", "x"))
        pipe = self.pipe(gw)
        rep = run(pipe.execute("r1", Plan(tasks=[task("a", "a.txt")]), self.workspace))
        self.assertEqual(rep.summary.passed, 1)
        self.assertEqual(rep.tasks[0].attempts, 2)
        self.assertFalse((self.run_dir / "ws" / "other.txt").exists())

    def test_blocked_output_is_retried_then_blocks(self) -> None:
        # A model that keeps saying "blocked" gets every attempt before the task is given up.
        gw = FakeGateway(lambda tid, n, spec: {"ops": [], "notes": "", "blocked": "spec is impossible"})
        plan = Plan(tasks=[task("a", "a.txt"), task("b", "b.txt", deps=["a"])])
        pipe = self.pipe(gw)
        rep = run(pipe.execute("r1", plan, self.workspace))
        self.assertGreater(len(gw.calls), 1)
        self.assertEqual((rep.summary.blocked, rep.summary.skipped), (1, 1))
        self.assertEqual(self.of("task.blocked")[0]["reason"], "spec is impossible")
        self.assertEqual(self.types().count("task.failed"), 0)

    def test_install_command_asks_the_user_and_fails_as_environment(self) -> None:
        checks = [Check(type="command", id="a.cmd", cmd="python -m pip install requests")]
        gw = FakeGateway(lambda tid, n, spec: write("a.txt", "x"))
        pipe = self.pipe(gw)
        rep = run(pipe.execute("r1", Plan(tasks=[task("a", "a.txt", checks=checks)]), self.workspace))
        self.assertEqual(rep.summary.failed, 1)
        self.assertEqual(len(gw.calls), 1)  # a retry cannot help
        asked = self.of("user.input_requested")
        self.assertEqual(len(asked), 1)
        self.assertIn("pip install requests", asked[0]["question"])
        self.assertEqual(self.of("task.failed")[0]["reason"], "environment")
        self.assertEqual(pipe.failure_kinds["a"], "environment")
        self.assertFalse((self.run_dir / "ws" / "a.txt").exists())

    def test_failed_integration_is_reported(self) -> None:
        gw = FakeGateway(lambda tid, n, spec: write("a.txt", "x"))
        plan = Plan(tasks=[task("a", "a.txt")],
                    global_acceptance=[Check(type="exists", id="g1", path="missing.txt")])
        rep = run(self.pipe(gw).execute("r1", plan, self.workspace))
        self.assertEqual(rep.summary.passed, 1)
        self.assertFalse(rep.integration[0].ok)
        res = self.of("integration.result")[0]
        self.assertFalse(res["ok"])
        self.assertEqual(res["files_written"], ["a.txt"])


class TestScheduling(Base):
    def test_slots_bound_concurrency(self) -> None:
        gw = FakeGateway(lambda tid, n, spec: write(f"{tid}.txt", "x"), delay=0.02)
        plan = Plan(tasks=[task(f"t{i}", f"t{i}.txt") for i in range(6)])
        rep = run(self.pipe(gw, make_cfg(slots=2)).execute("r1", plan, self.workspace))
        self.assertEqual(rep.summary.passed, 6)
        self.assertEqual(gw.peak, 2)

    def test_read_set_files_reach_the_worker(self) -> None:
        gw = FakeGateway(lambda tid, n, spec: write(f"{tid}.txt", "MARKER-123"))
        b = task("b", "b.txt", deps=["a"])
        b.read_set = ["a.txt"]
        run(self.pipe(gw).execute("r1", Plan(tasks=[task("a", "a.txt"), b]), self.workspace))
        prompt = [s for s in gw.specs if s.meta["task_id"] == "b"][0].messages[0]["content"]
        self.assertIn("MARKER-123", prompt)

    def test_cancel_before_start_skips_everything(self) -> None:
        gw = FakeGateway(lambda tid, n, spec: write(f"{tid}.txt", "x"))

        async def go():
            cancel = asyncio.Event()
            cancel.set()
            return await self.pipe(gw).execute("r1", Plan(tasks=[task("a", "a.txt")]), self.workspace, cancel)

        rep = run(go())
        self.assertEqual(rep.summary.skipped, 1)
        self.assertEqual(gw.calls, [])
        self.assertEqual(self.types().count("integration.result"), 0)

    def test_cancel_mid_run_stops_the_running_task(self) -> None:
        gw = FakeGateway(lambda tid, n, spec: write(f"{tid}.txt", "x"), delay=5.0)

        async def go():
            cancel = asyncio.Event()
            pipe = self.pipe(gw)
            plan = Plan(tasks=[task("a", "a.txt"), task("b", "b.txt", deps=["a"])])
            job = asyncio.ensure_future(pipe.execute("r1", plan, self.workspace, cancel))
            await asyncio.sleep(0.2)
            cancel.set()
            return await asyncio.wait_for(job, 5), pipe

        rep, pipe = run(go())
        self.assertEqual(pipe.statuses["a"], TaskStatus.failed)
        self.assertEqual(pipe.statuses["b"], TaskStatus.skipped)
        self.assertEqual(self.of("task.failed")[0]["reason"], "cancelled")

    def test_unknown_dependency_does_not_hang(self) -> None:
        gw = FakeGateway(lambda tid, n, spec: write(f"{tid}.txt", "x"))
        rep = run(self.pipe(gw).execute("r1", Plan(tasks=[task("a", "a.txt", deps=["ghost"])]), self.workspace))
        self.assertEqual(rep.summary.skipped, 1)


class TestFixCycle(Base):
    def test_fix_tasks_run_on_the_same_staged_copy(self) -> None:
        def fn(tid, n, spec):
            return write("a.txt", "fixed" if tid.startswith("fix") else "first")

        gw = FakeGateway(fn)
        plan = Plan(tasks=[task("a", "a.txt"), task("b", "b.txt", deps=["a"])])
        gw.fn = lambda tid, n, spec: write("a.txt" if tid != "b" else "b.txt",
                                           "fixed" if tid.startswith("fix") else "first")
        pipe = self.pipe(gw)
        fix = task("fix1_1", "a.txt", deps=["a"],
                   checks=[Check(type="contains", id="fx", path="a.txt", pattern="fixed")])

        async def go():
            first = await pipe.execute("r1", plan, self.workspace)
            n_events = len(self.events)
            second = await pipe.execute_fixes("r1", plan, [fix], self.workspace)
            files = await pipe.integrate("r1", self.workspace)
            return first, n_events, second, files

        first, n_events, second, files = run(go())
        self.assertEqual(first.summary.passed, 2)
        self.assertEqual(second.summary.passed, 3)
        self.assertEqual([t.id for t in second.tasks], ["a", "b", "fix1_1"])
        later = self.events[n_events:]
        self.assertEqual(later[0][0], "delegation.started")
        self.assertEqual(later[0][1]["cycle"], 1)
        self.assertEqual(later[0][1]["task_ids"], ["fix1_1"])
        self.assertEqual([t for t, _ in later].count("task.started"), 1)  # old tasks did not rerun
        self.assertEqual(sorted(files), ["a.txt", "b.txt"])
        self.assertEqual((self.workspace / "a.txt").read_text(encoding="utf-8"), "fixed")

    def test_fixes_need_a_staged_copy(self) -> None:
        pipe = self.pipe(FakeGateway(lambda *a: None))
        with self.assertRaises(RuntimeError):
            run(pipe.execute_fixes("r1", Plan(), [], self.workspace))


CODE = "def count_words(text):\n    return len(text.split())\n"
TEST_TMPL = (
    "import unittest\n"
    "from textstats import count_words\n\n\n"
    "class T(unittest.TestCase):\n"
    "    def test_count(self):\n"
    "        self.assertEqual(count_words('a b c'), %d)\n"
)
UNIT = "python -m unittest discover -s tests"
TEST_PATH = "tests/test_textstats.py"


class TestFinalVerification(Base):
    """The report describes the files as they are now, not as the first failed task left them."""

    def plan(self) -> Plan:
        t1 = task("t1", "textstats.py")
        t2 = task("t2", TEST_PATH, deps=[],
                  checks=[Check(type="command", id="t2.unit", cmd=UNIT)])
        return Plan(tasks=[t1, t2])

    def gateway(self) -> FakeGateway:
        def fn(tid, n, spec):
            if tid == "t1":
                return write("textstats.py", CODE)
            return write(TEST_PATH, TEST_TMPL % (3 if tid.startswith("fix") else 4))
        return FakeGateway(fn)

    def test_fix_task_rewrites_failed_file_and_report_shows_current_state(self) -> None:
        gw = self.gateway()
        cfg = make_cfg(slots=1)
        pipe = self.pipe(gw, cfg)
        plan = self.plan()
        fix = task("fix1_1", TEST_PATH, checks=[Check(type="command", id="fx.unit", cmd=UNIT)])

        async def go():
            first = await pipe.execute("r1", plan, self.workspace)
            second = await pipe.execute_fixes("r1", plan, [fix], self.workspace)
            return first, second

        first, second = run(go())

        # first run: t2 failed, its file was rolled back, the final check says so
        self.assertEqual((first.summary.passed, first.summary.failed), (1, 1))
        self.assertIn("textstats.py", first.files)
        self.assertNotIn(TEST_PATH, first.files)
        self.assertEqual(first.files["textstats.py"], CODE)
        unit = [c for c in first.final_checks if c.check is not None and c.check.cmd == UNIT]
        self.assertEqual(len(unit), 1)
        self.assertFalse(unit[0].ok and not unit[0].invalid)

        # after the fix: t2's old record is still "failed", the final checks pass on the new file
        self.assertEqual([t.id for t in second.tasks], ["t1", "t2", "fix1_1"])
        self.assertEqual(pipe.statuses["t2"], TaskStatus.failed)
        self.assertEqual(pipe.statuses["fix1_1"], TaskStatus.passed)
        self.assertTrue(second.final_checks)
        self.assertTrue(all(c.ok for c in second.final_checks),
                        [(c.check_id, c.error, c.output_tail) for c in second.final_checks])
        # same command in t2 and the fix task: run once
        unit = [c for c in second.final_checks if c.check is not None and c.check.cmd == UNIT]
        self.assertEqual(len(unit), 1)
        self.assertEqual(second.files[TEST_PATH], TEST_TMPL % 3)
        self.assertEqual(second.files["textstats.py"], CODE)

        # final checks are emitted like integration checks: no task, no attempt
        final_events = [p for p in self.of("check.result") if p.get("task_id") is None]
        self.assertGreaterEqual(len(final_events), len(first.final_checks) + len(second.final_checks))

    def test_failed_unittest_on_a_test_file_task_adds_the_hint(self) -> None:
        gw = self.gateway()
        run(self.pipe(gw, make_cfg(slots=1)).execute("r1", self.plan(), self.workspace))
        retries = [s.messages[0]["content"] for s in gw.specs
                   if s.meta["task_id"] == "t2" and int(s.meta["attempt"]) > 1]
        self.assertTrue(retries)
        for prompt in retries:
            self.assertIn("A failing test can mean the TEST is wrong.", prompt)
        firsts = [s.messages[0]["content"] for s in gw.specs if int(s.meta["attempt"]) == 1]
        for prompt in firsts:
            self.assertNotIn("A failing test can mean the TEST is wrong.", prompt)

    def test_hint_is_not_added_for_a_code_file_task(self) -> None:
        checks = [Check(type="contains", id="c", path="a.py", pattern="NEVER")]
        gw = FakeGateway(lambda tid, n, spec: write("a.py", "x = 1\n"))
        run(self.pipe(gw).execute("r1", Plan(tasks=[task("a", "a.py", checks=checks)]), self.workspace))
        self.assertGreater(len(gw.specs), 1)
        self.assertNotIn("TEST is wrong", gw.specs[1].messages[0]["content"])

    def test_two_fix_cycles_keep_every_task(self) -> None:
        gw = FakeGateway(lambda tid, n, spec: write("a.txt", tid))
        pipe = self.pipe(gw)
        plan = Plan(tasks=[task("a", "a.txt")])
        f1 = task("fix1_1", "a.txt", checks=[Check(type="contains", id="f1", path="a.txt", pattern="fix1_1")])
        f2 = task("fix2_1", "a.txt", checks=[Check(type="contains", id="f2", path="a.txt", pattern="fix2_1")])

        async def go():
            await pipe.execute("r1", plan, self.workspace)
            await pipe.execute_fixes("r1", plan, [f1], self.workspace)
            return await pipe.execute_fixes("r1", plan, [f2], self.workspace)

        rep = run(go())
        self.assertEqual([t.id for t in rep.tasks], ["a", "fix1_1", "fix2_1"])
        self.assertEqual(rep.summary.passed, 3)
        self.assertEqual(rep.files["a.txt"], "fix2_1")
        # the cycle 1 check is re-run on the current file and now fails: the record is honest
        by_id = {c.check_id: c.ok for c in rep.final_checks}
        self.assertEqual(by_id, {"a.exists": True, "f1": False, "f2": True})

    def test_review_checks_are_not_part_of_final_checks(self) -> None:
        checks = [Check(type="exists", id="e", path="a.txt"), Check(type="review", id="rv", rubric="good")]
        gw = FakeGateway(lambda tid, n, spec: write("a.txt", "x"))
        plan = Plan(tasks=[task("a", "a.txt", checks=checks)],
                    global_acceptance=[Check(type="exists", id="g", path="a.txt")])
        rep = run(self.pipe(gw).execute("r1", plan, self.workspace))
        # the global check equals the task check: one result, not two
        self.assertEqual([c.check_id for c in rep.final_checks], ["g"])
        self.assertEqual([c.check_id for c in rep.integration], ["g"])

    def test_snapshot_is_clipped_and_skips_binary(self) -> None:
        from council.works import pipeline as mod

        def fn(tid, n, spec):
            return write(f"{tid}.txt", tid * 9000)

        gw = FakeGateway(fn)
        tasks = [task(c, f"{c}.txt") for c in "abcde"] + [task("s", "s.txt")]
        gw.fn = lambda tid, n, spec: write(f"{tid}.txt", "small" if tid == "s" else tid * 9000)
        (self.workspace / "bin.dat").write_bytes(b"\xff\xfe\x00\x01")
        plan = Plan(tasks=tasks, deliverables=[
            {"id": "d1", "paths": ["bin.dat", "missing.txt", "../outside.txt", "s.txt"]}])
        rep = run(self.pipe(gw).execute("r1", plan, self.workspace))
        self.assertEqual(sorted(rep.files), ["a.txt", "b.txt", "c.txt", "d.txt", "e.txt", "s.txt"])
        self.assertEqual(rep.files["s.txt"], "small")
        mark = mod._CLIP_MARK
        bodies = 0
        for name in "abcde":
            text = rep.files[f"{name}.txt"]
            self.assertTrue(text.endswith(mark))
            body = text[:-len(mark)]
            self.assertLessEqual(len(body), 6000)
            bodies += len(body)
        self.assertLessEqual(bodies + len("small"), 24000)
        self.assertGreater(bodies, 23000)  # the budget is used, not wasted

    def test_clip_per_file_only_when_total_fits(self) -> None:
        from council.works import pipeline as mod
        out = mod._clip_all({"big": "x" * 7000, "ok": "y" * 100})
        self.assertEqual(out["ok"], "y" * 100)
        self.assertEqual(out["big"], "x" * 6000 + mod._CLIP_MARK)


class TestInvalidChecks(Base):
    ZERO = "python -m unittest discover -s tests -p nomatch_*.py"

    def test_invalid_check_does_not_fail_a_task_or_integration(self) -> None:
        checks = [Check(type="exists", id="e", path=TEST_PATH),
                  Check(type="command", id="zero", cmd=self.ZERO)]
        gw = FakeGateway(lambda tid, n, spec: write(TEST_PATH, "import unittest\n"))
        plan = Plan(tasks=[task("a", TEST_PATH, checks=checks)],
                    global_acceptance=[Check(type="command", id="gzero", cmd=self.ZERO + " -v")])
        pipe = self.pipe(gw)
        rep = run(pipe.execute("r1", plan, self.workspace))

        zero = [c for c in pipe.attempts["a"][0].checks if c.check_id == "zero"]
        self.assertEqual(len(zero), 1)
        self.assertTrue(zero[0].invalid, (zero[0].exit_code, zero[0].output_tail))
        self.assertEqual(len(gw.calls), 1)  # no retry
        self.assertEqual(rep.summary.passed, 1)
        self.assertEqual(self.types().count("task.failed"), 0)
        self.assertTrue(rep.integration[0].invalid)
        self.assertTrue(self.of("integration.result")[0]["ok"])
        self.assertTrue(any(c.invalid for c in rep.final_checks))

    def test_invalid_check_does_not_hide_a_real_failure(self) -> None:
        checks = [Check(type="contains", id="c", path=TEST_PATH, pattern="NEVER"),
                  Check(type="command", id="zero", cmd=self.ZERO)]
        gw = FakeGateway(lambda tid, n, spec: write(TEST_PATH, "import unittest\n"))
        pipe = self.pipe(gw)
        rep = run(pipe.execute("r1", Plan(tasks=[task("a", TEST_PATH, checks=checks)]), self.workspace))
        self.assertEqual(rep.summary.failed, 1)
        self.assertEqual(pipe.attempts["a"][-1].failing_check, "c")


class TestStagingSafety(Base):
    def test_task_id_that_is_a_path_cannot_touch_files_outside_the_run(self) -> None:
        victim = Path(self._tmp.name) / "victim"
        victim.mkdir()
        (victim / "keep.txt").write_text("precious", encoding="utf-8")
        for n, bad in enumerate(("../../victim", str(victim))):
            gw = FakeGateway(lambda tid, n, spec: write("a.txt", "x"))
            pipe = WorksPipeline(gw, lambda t, p: None, make_cfg(), self.run_dir, "worker-m", None)
            rep = run(pipe.execute("r1", Plan(tasks=[task(bad, "a.txt")]), self.workspace))
            self.assertEqual(rep.summary.passed, 1, bad)
            self.assertEqual([p.name for p in victim.iterdir()], ["keep.txt"], bad)
            self.assertEqual((victim / "keep.txt").read_text(encoding="utf-8"), "precious")

    def test_files_made_by_checks_stay_out_of_the_workspace(self) -> None:
        make_junk = ("import pathlib; pathlib.Path('.pytest_cache').mkdir(exist_ok=True); "
                     "pathlib.Path('.pytest_cache/x').write_text('c'); "
                     "pathlib.Path('junk.log').write_text('j')")
        checks = [Check(type="command", id="c1", cmd=f'python -c "{make_junk}"')]
        gw = FakeGateway(lambda tid, n, spec: write("a.txt", "x"))
        pipe = self.pipe(gw)
        rep = run(pipe.execute("r1", Plan(tasks=[task("a", "a.txt", checks=checks)]), self.workspace))
        self.assertEqual(rep.summary.passed, 1)
        self.assertTrue((self.run_dir / "ws" / "junk.log").is_file())  # the check did run
        self.assertEqual(self.of("integration.result")[0]["files_written"], ["a.txt"])
        self.assertEqual(run(pipe.integrate("r1", self.workspace)), ["a.txt"])
        self.assertEqual(sorted(p.name for p in self.workspace.iterdir()), ["a.txt"])

    def test_user_edit_during_the_run_is_kept_and_reported(self) -> None:
        (self.workspace / "a.txt").write_text("old", encoding="utf-8")
        (self.workspace / "notes.txt").write_text("n1", encoding="utf-8")
        gw = FakeGateway(lambda tid, n, spec: write(f"{tid}.txt", "from the task"))
        pipe = self.pipe(gw)
        plan = Plan(tasks=[task("a", "a.txt"), task("b", "b.txt")])
        run(pipe.execute("r1", plan, self.workspace))
        (self.workspace / "a.txt").write_text("user edit", encoding="utf-8")   # touched by a task too
        (self.workspace / "notes.txt").write_text("n2", encoding="utf-8")      # touched by no task
        self.assertEqual(run(pipe.integrate("r1", self.workspace)), ["b.txt"])
        self.assertEqual((self.workspace / "a.txt").read_text(encoding="utf-8"), "user edit")
        self.assertEqual((self.workspace / "notes.txt").read_text(encoding="utf-8"), "n2")
        self.assertEqual(pipe.conflicts, ["a.txt"])
        copy = [p for p in self.of("integration.result") if p["stage"] == "copy"][-1]
        self.assertFalse(copy["ok"])
        self.assertIn("a.txt", copy["error"])


if __name__ == "__main__":
    unittest.main()
