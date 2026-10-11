import asyncio
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from council.core.schemas import Check, CheckResult, MicroTask, Plan
from council.works import sandbox
from council.works.inspector import SKIPPED, Inspector


def cmd(code: str, **kw) -> Check:
    return Check(type="command", cmd=f'python -c "{code}"', **kw)


def task(acceptance, write_set=("a.py",), goal="make a", contract="a.py defines x", **kw) -> MicroTask:
    return MicroTask(id="t1", goal=goal, output_contract=contract, write_set=list(write_set),
                     acceptance=list(acceptance), **kw)


class InspectorTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        (self.root / "a.py").write_text("x = 1\n", encoding="utf-8")
        (self.root / "bad.py").write_text("def f(:\n", encoding="utf-8")
        (self.root / "cut.py").write_text("x = [1, 2,\n", encoding="utf-8")

    def tearDown(self):
        self._td.cleanup()

    def insp(self, **kw) -> Inspector:
        kw.setdefault("allowed_executables", ["python"])
        kw.setdefault("check_timeout_s", 30.0)
        return Inspector(self.root, **kw)

    def run_(self, coro):
        return asyncio.run(coro)

    # ---------------------------------------------------------------- inspect

    def test_all_pass(self):
        i = self.insp()
        t = task([cmd("import a; assert a.x == 1"), Check(type="exists", path="a.py"),
                  Check(type="contains", path="a.py", pattern=r"^x = 1")])
        res = self.run_(i.inspect(t, ["a.py"]))
        self.assertEqual([r.level for r in res], ["L0", "L1", "L1", "L1"])
        self.assertTrue(i.passed(res))
        self.assertIsNone(i.failing(res))
        self.assertTrue(all(r.task_id == "t1" for r in res))
        self.assertEqual(res[1].exit_code, 0)

    def test_order_kept(self):
        i = self.insp()
        checks = [cmd("import time; time.sleep(0.4)", id="slow"), cmd("pass", id="fast"),
                  Check(type="exists", path="a.py", id="e")]
        res = self.run_(i.inspect(task(checks), ["a.py"]))
        self.assertEqual([r.check_id for r in res[1:]], ["slow", "fast", "e"])

    def test_l0_fail_stops(self):
        i = self.insp()
        t = task([cmd("pass")], write_set=["bad.py"])
        with mock.patch.object(sandbox, "run_command") as rc:
            res = self.run_(i.inspect(t, ["bad.py"]))
        rc.assert_not_called()
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].level, "L0")
        self.assertFalse(i.passed(res))
        self.assertIs(i.failing(res), res[0])
        self.assertEqual(i.classify_failure(t, res), "retry")

    def test_l0_missing_file(self):
        i = self.insp()
        res = self.run_(i.inspect(task([cmd("pass")], write_set=["nope.py"]), ["nope.py"]))
        self.assertEqual(len(res), 1)
        self.assertIn("missing", res[0].error)

    def test_l0_outside_write_set(self):
        i = self.insp()
        res = self.run_(i.inspect(task([cmd("pass")], write_set=["other.py"]), ["a.py"]))
        self.assertEqual(len(res), 1)
        self.assertFalse(res[0].ok)
        self.assertIn("write_set", res[0].error)

    def test_command_fails(self):
        i = self.insp()
        t = task([cmd("pass"), cmd("import sys; print('boom'); sys.exit(3)", id="c2")])
        res = self.run_(i.inspect(t, ["a.py"]))
        self.assertFalse(i.passed(res))
        f = i.failing(res)
        self.assertEqual(f.check_id, "c2")
        self.assertEqual(f.exit_code, 3)
        self.assertIn("boom", f.output_tail)
        self.assertEqual(i.classify_failure(t, res), "retry")

    def test_expect_exit(self):
        i = self.insp()
        res = self.run_(i.inspect(task([cmd("import sys; sys.exit(2)", expect_exit=2)]), ["a.py"]))
        self.assertTrue(i.passed(res))

    def test_runs_in_root(self):
        i = self.insp()
        res = self.run_(i.inspect(task([cmd("open('a.py').read()")]), ["a.py"]))
        self.assertTrue(i.passed(res))

    # ---------------------------------------------------------------- environment

    def test_refused_executable(self):
        i = self.insp()
        t = task([Check(type="command", cmd="notallowed --version")])
        res = self.run_(i.inspect(t, ["a.py"]))
        self.assertIn("refused", i.failing(res).error)
        self.assertEqual(i.classify_failure(t, res), "environment")

    def test_refused_install(self):
        i = self.insp()
        t = task([Check(type="command", cmd="python -m pip install requests")])
        res = self.run_(i.inspect(t, ["a.py"]))
        self.assertIn("refused", i.failing(res).error)
        self.assertEqual(i.classify_failure(t, res), "environment")

    def test_timeout(self):
        i = self.insp(check_timeout_s=0.5)
        t = task([cmd("import time; time.sleep(20)")])
        t0 = time.monotonic()
        res = self.run_(i.inspect(t, ["a.py"]))
        self.assertLess(time.monotonic() - t0, 15)
        f = i.failing(res)
        self.assertEqual(f.exit_code, -2)
        self.assertTrue(f.error.startswith("timeout"))
        self.assertEqual(i.classify_failure(t, res), "environment")

    def test_check_timeout_is_capped(self):
        i = self.insp(check_timeout_s=5.0)
        seen = []

        def fake(c, cwd, timeout_s=60, allowed=None):
            seen.append((timeout_s, list(allowed)))
            return {"exit_code": 0, "output": "", "ms": 1, "refused": None}

        with mock.patch.object(sandbox, "run_command", fake):
            self.run_(i.inspect(task([cmd("pass", timeout_s=60), cmd("pass", timeout_s=2)]), ["a.py"]))
        self.assertEqual(sorted(s[0] for s in seen), [2.0, 5.0])
        self.assertEqual(seen[0][1], ["python"])

    # ---------------------------------------------------------------- parallel

    def test_semaphore_bounds_commands(self):
        i = self.insp(max_parallel=2)
        lock = threading.Lock()
        state = {"now": 0, "peak": 0}

        def fake(c, cwd, timeout_s=60, allowed=None):
            with lock:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.05)
            with lock:
                state["now"] -= 1
            return {"exit_code": 0, "output": "", "ms": 1, "refused": None}

        with mock.patch.object(sandbox, "run_command", fake):
            res = self.run_(i.inspect(task([cmd("pass") for _ in range(8)]), ["a.py"]))
        self.assertTrue(i.passed(res))
        self.assertEqual(len(res), 9)
        self.assertEqual(state["peak"], 2)

    def test_commands_run_in_parallel(self):
        i = self.insp(max_parallel=4)
        t = task([cmd("import time; time.sleep(1)") for _ in range(4)])
        t0 = time.monotonic()
        res = self.run_(i.inspect(t, ["a.py"]))
        self.assertTrue(i.passed(res))
        self.assertLess(time.monotonic() - t0, 3.5)

    # ---------------------------------------------------------------- review

    def test_review_skipped_without_call(self):
        i = self.insp()
        t = task([cmd("pass"), Check(type="review", rubric="is it clear", id="r")])
        res = self.run_(i.inspect(t, ["a.py"]))
        self.assertTrue(i.passed(res))
        r = res[-1]
        self.assertEqual((r.type, r.level, r.error, r.check_id), ("review", "L2", SKIPPED, "r"))
        self.assertEqual(i.skipped(res), [r])

    def test_review_call_used(self):
        calls = []

        async def review(t, written, rubric):
            calls.append((t.id, written, rubric))
            return CheckResult(ok=False, score=0.2, error="unclear")

        i = self.insp(review_call=review)
        t = task([Check(type="review", rubric="is it clear", id="r")])
        res = self.run_(i.inspect(t, ["a.py"]))
        self.assertEqual(calls, [("t1", ["a.py"], "is it clear")])
        f = i.failing(res)
        self.assertEqual((f.level, f.type, f.score, f.task_id, f.check_id), ("L2", "review", 0.2, "t1", "r"))
        self.assertEqual(i.classify_failure(t, res), "ambiguous")

    def test_review_pass(self):
        async def review(t, written, rubric):
            return CheckResult(ok=True, score=0.9)

        i = self.insp(review_call=review)
        res = self.run_(i.inspect(task([Check(type="review", rubric="r")]), ["a.py"]))
        self.assertTrue(i.passed(res))
        self.assertEqual(i.skipped(res), [])

    def test_review_error_is_environment(self):
        async def review(t, written, rubric):
            raise RuntimeError("model down")

        i = self.insp(review_call=review)
        t = task([Check(type="review", rubric="r")])
        res = self.run_(i.inspect(t, ["a.py"]))
        self.assertIn("model down", i.failing(res).error)
        self.assertEqual(i.classify_failure(t, res), "environment")

    # ---------------------------------------------------------------- classify

    def test_classify_no_failure(self):
        i = self.insp()
        t = task([cmd("pass")])
        self.assertEqual(i.classify_failure(t, self.run_(i.inspect(t, ["a.py"]))), "retry")

    def test_classify_truncated_is_too_big(self):
        i = self.insp()
        t = task([cmd("pass")], write_set=["cut.py"])
        res = self.run_(i.inspect(t, ["cut.py"]))
        self.assertFalse(i.passed(res))
        self.assertEqual(i.classify_failure(t, res), "too_big")

    def test_classify_many_files_is_too_big(self):
        i = self.insp()
        names = ["a.py", "b.py", "c.py", "d.py"]
        for n in names[1:]:
            (self.root / n).write_text("y = 2\n", encoding="utf-8")
        t = task([cmd("import sys; sys.exit(1)"), Check(type="contains", path="b.py", pattern="zzz")],
                 write_set=names)
        res = self.run_(i.inspect(t, names))
        self.assertEqual(i.classify_failure(t, res), "too_big")

    def test_classify_no_contract_is_ambiguous(self):
        i = self.insp()
        t = task([cmd("import sys; sys.exit(1)")], contract="")
        res = self.run_(i.inspect(t, ["a.py"]))
        self.assertEqual(i.classify_failure(t, res), "ambiguous")

    # ---------------------------------------------------------------- integration

    def test_integration(self):
        i = self.insp()
        plan = Plan(global_acceptance=[cmd("import a; assert a.x == 1", id="g1"),
                                       Check(type="exists", path="a.py", id="g2"),
                                       Check(type="review", rubric="whole thing good", id="g3")])
        res = self.run_(i.integration(plan))
        self.assertEqual([r.check_id for r in res], ["g1", "g2", "g3"])
        self.assertTrue(all(r.level == "L3" and r.task_id is None for r in res))
        self.assertTrue(i.passed(res))
        self.assertEqual(res[2].error, SKIPPED)

    def test_integration_fail(self):
        i = self.insp()
        plan = Plan(global_acceptance=[cmd("pass"), cmd("import nothere_xyz", id="g")])
        res = self.run_(i.integration(plan))
        self.assertFalse(i.passed(res))
        self.assertEqual(i.failing(res).check_id, "g")
        self.assertIn("nothere_xyz", i.failing(res).output_tail)

    def test_integration_empty(self):
        i = self.insp()
        res = self.run_(i.integration(Plan()))
        self.assertEqual(res, [])
        self.assertTrue(i.passed(res))

    def test_reuse_across_event_loops(self):
        i = self.insp()
        t = task([cmd("pass")])
        self.assertTrue(i.passed(self.run_(i.inspect(t, ["a.py"]))))
        self.assertTrue(i.passed(self.run_(i.inspect(t, ["a.py"]))))


class LoopStaysAlive(unittest.TestCase):
    def test_slow_pattern_does_not_freeze_the_event_loop(self):
        import tempfile
        from council.works import checks
        old = checks.PATTERN_TIMEOUT_S
        checks.PATTERN_TIMEOUT_S = 1.5
        self.addCleanup(setattr, checks, "PATTERN_TIMEOUT_S", old)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.py").write_text("x = '" + "a" * 60 + "!'\n", encoding="utf-8")
            insp = Inspector(root, allowed_executables=["python"], check_timeout_s=30.0)
            t = task([Check(type="contains", path="a.py", pattern="(a+)+$")])

            async def go():
                ticks = 0
                job = asyncio.ensure_future(insp.inspect(t, ["a.py"]))
                while not job.done():
                    await asyncio.sleep(0.05)
                    ticks += 1
                return ticks, job.result()

            ticks, results = asyncio.run(asyncio.wait_for(go(), 30))
        self.assertGreaterEqual(ticks, 5)  # the loop kept running while the pattern was matched
        self.assertFalse(results[-1].ok)
        self.assertIn("timed out", results[-1].error)
        self.assertEqual(insp.classify_failure(t, results), "retry")  # the plan's fault, not the machine's


if __name__ == "__main__":
    unittest.main()
