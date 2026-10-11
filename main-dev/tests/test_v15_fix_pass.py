"""Regression tests for the 1.5 fix pass: one test (or more) per reviewer bug that was fixed."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from council.api.providers import LieProviderImpl
from council.api.run_pipeline import RunPipeline
from council.chamber.cluster import cluster_fallback
from council.core import event_types as ET
from council.core.schemas import (
    Check,
    CheckResult,
    MicroTask,
    ModelEntry,
    Plan,
    RunState,
    TaskStatus,
)
from council.host.drivers import MockDriver
from council.host.host import Host, HostError
from council.host.llamacpp_server import LlamaServerDriver
from council.host.ram import RamBudget
from council.probe.llamacpp_source import LlamaCppActivationSource
from council.probe.scorer import LiveScorer
from council.works.checks import is_zero_test_output, run_check
from council.works.report import build_report, report_text

try:  # discover -s tests puts tests/ on the path; `-m unittest tests.x` does not
    from test_api_run_pipeline import BUILD_TASK, Base as PipelineBase
    from test_chamber_deliberation import CouncilSizes
    from test_host_llamacpp_server import BIN, BLOBS, Rig as ServerRig, make_registry
    from test_probe_llamacpp_source import MSGS, Runner
except ImportError:  # pragma: no cover
    from tests.test_api_run_pipeline import BUILD_TASK, Base as PipelineBase
    from tests.test_chamber_deliberation import CouncilSizes
    from tests.test_host_llamacpp_server import BIN, BLOBS, Rig as ServerRig, make_registry
    from tests.test_probe_llamacpp_source import MSGS, Runner


def run(coro):
    return asyncio.run(coro)


UNIT = "python -m unittest discover -s tests"

SETUP_ERROR = (
    "E\n======================================================================\n"
    "ERROR: setUpModule (test_x)\n----------------------------------------------------------------------\n"
    "RuntimeError: boom\n\n----------------------------------------------------------------------\n"
    "Ran 0 tests in 0.001s\n\nFAILED (errors=1)\n")
REAL_FAIL = (
    "F\n======================================================================\n"
    "FAIL: test_a (test_x.T.test_a)\n"
    "AssertionError: 1 != 2 : no tests ran on the empty list\n\n"
    "----------------------------------------------------------------------\n"
    "Ran 1 test in 0.001s\n\nFAILED (failures=1)\n")
NO_DIR = "ImportError: Start directory is not importable: 'tests'\n"
ZERO = "\n----------------------------------------------------------------------\nRan 0 tests in 0.000s\n\nNO TESTS RAN\n"


class ZeroTestRule(unittest.TestCase):
    """works/checks.py: only a run that really ran nothing is an invalid check."""

    def check(self, output: str, code: int) -> CheckResult:
        return run_check(Check(type="command", id="u", cmd=UNIT), Path("."),
                         lambda cmd, root, timeout: {"exit_code": code, "output": output})

    def test_setup_error_is_a_real_failure(self):
        self.assertFalse(is_zero_test_output(SETUP_ERROR, 1))
        res = self.check(SETUP_ERROR, 1)
        self.assertFalse(res.invalid)
        self.assertFalse(res.ok)

    def test_failed_test_whose_message_says_no_tests_ran_is_a_real_failure(self):
        self.assertFalse(is_zero_test_output(REAL_FAIL, 1))
        res = self.check(REAL_FAIL, 1)
        self.assertFalse(res.invalid)
        self.assertFalse(res.ok)

    def test_plain_zero_test_run_is_still_invalid(self):
        for code in (0, 5):
            res = self.check(ZERO, code)
            self.assertTrue(res.invalid, code)
        self.assertFalse(is_zero_test_output(ZERO, 1))  # exit 1 with no summary: not a clean zero run
        self.assertTrue(is_zero_test_output("collected 0 items\n", 5))

    def test_missing_tests_directory_is_invalid_not_a_failure(self):
        # A code task carries the whole-suite command before any test file exists.
        res = self.check(NO_DIR, 1)
        self.assertTrue(res.invalid)


def _task(tid: str, path: str) -> MicroTask:
    return MicroTask(id=tid, title=tid, goal=f"write {path}", write_set=[path],
                     output_contract=f"{path} exists",
                     acceptance=[Check(type="exists", id=f"{tid}.exists", path=path)])


class FailedTaskVerdict(unittest.TestCase):
    """works/report.py and RunPipeline._checks_pass: a failed task is never 'all checks pass'."""

    def report(self, t2: TaskStatus):
        plan = Plan(tasks=[_task("t1", "a.py"), _task("t2", "tests/test_a.py")])
        ok = CheckResult(ok=True, type="exists", check_id="t1.exists")
        broken = CheckResult(ok=False, type="command", check_id="t2.unit", invalid=True)
        return build_report(plan, {"t1": TaskStatus.passed, "t2": t2}, {}, [], ["a.py"],
                            final_checks=[ok, broken], files={"a.py": "x = 1\n"})

    def test_failed_task_is_named_in_the_current_state(self):
        rep = self.report(TaskStatus.failed)
        head = report_text(rep).split("HISTORY")[0]
        self.assertNotIn("All current checks pass.", head)
        self.assertIn("1 task(s) FAILED", head)
        self.assertEqual(rep.summary.unfinished, 1)
        self.assertFalse(RunPipeline._checks_pass(rep))

    def test_failed_fix_on_files_that_already_passed_is_not_missing_work(self):
        # The fix task failed and was rolled back: the file t1 wrote is as it was, and right.
        fix = _task("fix1_1", "a.py")
        plan = Plan(tasks=[_task("t1", "a.py"), fix])
        ok = CheckResult(ok=True, type="exists", check_id="t1.exists")
        rep = build_report(plan, {"t1": TaskStatus.passed, "fix1_1": TaskStatus.failed}, {}, [],
                           ["a.py"], final_checks=[ok], files={"a.py": "x = 1" + chr(10)})
        self.assertEqual((rep.summary.failed, rep.summary.unfinished), (1, 0))
        self.assertIn("All current checks pass.", report_text(rep))
        self.assertTrue(RunPipeline._checks_pass(rep))

    def test_all_passed_still_says_all_checks_pass(self):
        rep = self.report(TaskStatus.passed)
        rep.deviations = []
        self.assertIn("All current checks pass.", report_text(rep))
        self.assertTrue(RunPipeline._checks_pass(rep))


class ClusterAndSplit(CouncilSizes):
    """chamber: unlike positions are not merged; two valid votes 1-1 go to the Chair."""

    def test_six_different_answers_give_six_options(self):
        opts = cluster_fallback({i: (None, f"answer {i}") for i in range(1, 7)})
        self.assertEqual(len(opts), 6)
        self.assertTrue(all(len(o.holders) == 1 for o in opts))

    def test_three_seats_one_silent_one_one_goes_to_the_chair(self):
        # seat 2 gives no draft; seats 0 and 1 split. The weights must not call it a majority.
        d, drv, seen = self.run_all(3, ["B", "C", None], {0: "o1", 1: "o2", 2: "o1"})
        dec = d.decision()
        self.assertEqual(dict(dec.tally), {"o1": 1, "o2": 1})
        self.assertEqual(dec.outcome, "chair")


# The inherited size tests already run in test_chamber_deliberation.
for _name in [n for n in dir(CouncilSizes) if n.startswith("test_")]:
    setattr(ClusterAndSplit, _name, None)
del CouncilSizes


class _Bus:
    def __init__(self):
        self.events = []

    def emit(self, type_, run_id, payload=None):
        self.events.append((type_, run_id, payload))


class _DyingDriver(MockDriver):
    """A driver whose servers can die by themselves, as llama-server does."""

    def __init__(self):
        super().__init__()
        self.dead: set[str] = set()
        self.loads: list[str] = []
        self.stopped = 0

    async def load(self, model_id, profile):
        self.loads.append(model_id)
        self.dead.discard(model_id)
        return await super().load(model_id, profile)

    def dead_models(self):
        return list(self.dead)

    async def stop(self):
        self.stopped += 1
        await super().stop()


def _host():
    reg = [ModelEntry(id=i) for i in ("a", "b")]
    fp = {(i, p): 10.0 for i in ("a", "b") for p in ("live", "batch")}
    driver = _DyingDriver()
    bus = _Bus()
    return Host(driver, RamBudget(lambda: 100.0, 0.0, set(), fp), reg, bus), driver, bus


class HostFixes(unittest.IsolatedAsyncioTestCase):
    async def test_dead_server_is_loaded_again(self):
        host, driver, bus = _host()
        await host.ensure_resident(["a", "b"], "live", "r1")
        self.assertEqual(driver.loads, ["a", "b"])
        driver.dead.add("a")  # OOM kill
        out = await host.ensure_resident(["a", "b"], "live", "r1")
        self.assertEqual(driver.loads, ["a", "b", "a"])
        self.assertEqual(set(out), {"a", "b"})
        self.assertIn((ET.MODEL_UNLOADED, "r1", {"model_id": "a"}), bus.events)

    async def test_is_seated_and_stop(self):
        host, driver, _ = _host()
        await host.ensure_resident(["a"], "live", "r1")
        self.assertTrue(host.is_seated("a"))
        self.assertFalse(host.is_seated("b"))
        host.release("r1")
        self.assertFalse(host.is_seated("a"))
        await host.stop()
        self.assertEqual(driver.stopped, 1)
        self.assertEqual(host.status(), [])


class LlamaServerFixes(unittest.TestCase):
    def test_port_already_in_use_refuses_to_spawn(self):
        rig = ServerRig()
        d = rig.driver(port_busy=lambda port: True)

        async def go():
            with self.assertRaisesRegex(RuntimeError, "already in use"):
                await d.load("tiny", "live")
            return await d.status()

        self.assertEqual(run(go())["tiny"], "failed")
        self.assertEqual(rig.argvs, [])  # nothing was started on the taken port

    def test_free_port_spawns(self):
        rig = ServerRig()
        seen = []
        d = rig.driver(port_busy=lambda port: seen.append(port) or False)
        run(d.load("tiny", "live"))
        self.assertEqual(seen, [d.port_for("tiny")])
        self.assertEqual(len(rig.argvs), 1)

    def test_dead_models_lists_a_child_that_exited(self):
        rig = ServerRig()
        d = rig.driver()

        async def go():
            await d.load("tiny", "live")
            self.assertEqual(d.dead_models(), [])
            rig.procs[-1].returncode = 137
            return d.dead_models()

        self.assertEqual(run(go()), ["tiny"])

    def test_host_reloads_a_llama_server_that_died(self):
        rig = ServerRig()
        d = rig.driver(drafts={})
        reg = list(d.registry.values())
        fp = {(m.id, p): 1.0 for m in reg for p in ("live", "batch")}
        host = Host(d, RamBudget(lambda: 100.0, 0.0, set(), fp), reg, _Bus())

        async def go():
            await host.ensure_resident(["tiny"], "live", "r1")
            rig.procs[-1].returncode = 137
            await host.ensure_resident(["tiny"], "live", "r1")

        run(go())
        self.assertEqual(len(rig.argvs), 2)


class ActivationSourceFixes(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.binary = self.dir / "actdump"
        self.binary.write_bytes(b"x")
        self.blob = self.dir / "blob.gguf"
        self.blob.write_bytes(b"x")

    def source(self, mode="ok", **kw):
        self.runner = Runner(mode)
        return LlamaCppActivationSource(self.binary, lambda tag: self.blob, runner=self.runner, **kw)

    async def test_cancel_mid_request_kills_the_process(self):
        src = self.source("silent")
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(src.capture("m1", MSGS, [1]), 0.05)
        (proc,) = self.runner.workers
        self.assertIsNotNone(proc.returncode)  # not left with an unread reply
        self.assertEqual(src.alive(), [])
        # the next request starts a fresh process and is answered
        self.runner.mode = "ok"
        out = await src.capture("m1", MSGS, [1])
        self.assertEqual(sorted(out), [1])
        self.assertEqual(len(self.runner.workers), 2)

    async def test_cancelled_eviction_leaves_no_running_process(self):
        src = self.source("silent", max_models=1)
        first = asyncio.ensure_future(src.capture("m1", MSGS, [1]))  # holds m1's lock for good
        await asyncio.sleep(0.02)
        with self.assertRaises(asyncio.TimeoutError):  # m2 must evict m1 and waits on its lock
            await asyncio.wait_for(src.capture("m2", MSGS, [1]), 0.05)
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        await src.close()
        self.assertTrue(all(p.returncode is not None for p in self.runner.workers),
                        [p.returncode for p in self.runner.workers])
        self.assertEqual(src.alive(), [])


class _OrderSource:
    """Records how many captures overlap."""

    def __init__(self, max_models=None):
        if max_models is not None:
            self.max_models = max_models
        self.now: set[str] = set()
        self.most = 0

    async def capture(self, model_id, messages, layers):
        self.now.add(model_id)
        self.most = max(self.most, len(self.now))
        await asyncio.sleep(0.01)
        self.now.discard(model_id)
        return {int(n): [1.0, 0.0] for n in layers}


class ScorerOrder(unittest.IsolatedAsyncioTestCase):
    def scorer(self, source):
        from council.core.schemas import Probe

        probe = Probe(model_id="m", layer=1, weights=[1.0, 0.0], bias=0.0, status="validated")
        return LiveScorer(source, lambda mid: [probe])

    def seats(self):
        from council.core.schemas_v15 import ClaimSpan

        claim = ClaimSpan(claim_id="c1", text="water is wet", start=0, end=12)
        return {0: ("m1", [claim]), 1: ("m2", [claim])}

    async def test_one_model_at_a_time_when_the_source_holds_one(self):
        src = _OrderSource(max_models=1)
        out = await self.scorer(src).score_seats("task", self.seats())
        self.assertEqual(src.most, 1)
        self.assertEqual(set(out), {0, 1})

    async def test_models_still_run_together_when_there_is_room(self):
        src = _OrderSource()
        await self.scorer(src).score_seats("task", self.seats())
        self.assertEqual(src.most, 2)


class TrainGuard(unittest.IsolatedAsyncioTestCase):
    class _Service:
        source = object()

        async def train_for(self, model_id, tasks, now):
            raise AssertionError("training must not start while a run is active")

    async def test_real_source_refuses_training_while_a_run_is_active(self):
        prov = LieProviderImpl(self._Service(), registry=[ModelEntry(id="a")], source="llamacpp",
                               busy=lambda: True)
        with self.assertRaises(HTTPException) as cm:
            await prov.train("a")
        self.assertEqual(cm.exception.status_code, 409)
        self.assertIn("run is active", cm.exception.detail)


class ApiModelRoutes(unittest.TestCase):
    """server.py: the load and unload buttons must not pull a model from under a run or a bench."""

    def setUp(self):
        from fastapi.testclient import TestClient

        from council.api.controller import RunController
        from council.api.server import create_app

        self.ctrl = RunController.build_mock(speed=500.0)
        self.mid = self.ctrl.registry[0].id
        self.other = self.ctrl.registry[1].id
        self.client = TestClient(create_app(self.ctrl))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def portal(self, coro_fn, *a):
        return self.client.portal.call(coro_fn, *a)

    def test_unload_of_a_seated_model_is_refused(self):
        host = self.ctrl.host
        self.portal(host.ensure_resident, [self.mid], "live", "run_x")
        r = self.client.post(f"/models/{self.mid}/unload")
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn(self.mid, {s["model_id"] for s in host.status()})
        host.release("run_x")
        self.assertEqual(self.client.post(f"/models/{self.mid}/unload").status_code, 200)
        self.assertNotIn(self.mid, {s["model_id"] for s in host.status()})

    def test_load_button_leaves_the_bench_seat_and_profile_alone(self):
        host = self.ctrl.host
        self.portal(host.ensure_resident, [self.mid], "batch", "manual")  # what the bench does
        self.assertEqual(self.client.post(f"/models/{self.mid}/load").status_code, 200)
        self.assertEqual(self.client.post(f"/models/{self.other}/load").status_code, 200)
        self.assertTrue(host.is_seated(self.mid))  # the bench still holds its model
        profile = {s["model_id"]: s["profile"] for s in host.status()}
        self.assertEqual(profile[self.mid], "batch")  # not reloaded as "live" under the bench
        self.assertFalse(host.is_seated(self.other))

    def test_question_is_auto_answered_when_the_config_says_unattended(self):
        from council.api.controller import _Run
        from council.core.schemas import RunRequest, UserQuestion

        ctrl = self.ctrl
        ctrl.config.foreman.auto_delegate = True  # the pipeline skips the delegate wait on this

        async def ask():
            req = RunRequest(task="t")
            rid = "run_ask"
            ctrl.store.create_run(rid, "t", None, req.mode, RunState.INTAKE)
            run = _Run(run_id=rid, req=req, demo=False)
            ctrl._runs[rid] = run
            q = UserQuestion(question="Accept?", options=["accept", "discard"])
            try:
                return await asyncio.wait_for(ctrl._ask_user(run, q), 5.0)
            finally:
                run.terminal = True

        answer = self.portal(ask)
        self.assertEqual(answer.choice, "accept")


class GatewaySlots(unittest.TestCase):
    def test_llamacpp_slots_follow_the_server_not_the_registry(self):
        from council.core.config import Config
        from council.gateway.gateway import Gateway

        entry = ModelEntry(id="a")
        entry.serve.live.parallel = 4
        cfg = Config()
        cfg.gateway.mock = False
        cfg.host.driver = "llamacpp"
        cfg.llamacpp.parallel = 1
        seen = {}

        import council.gateway.gateway as gw_mod

        real = gw_mod.Governor

        def spy(slots, max_models):
            seen.update(slots)
            return real(slots, max_models)

        gw_mod.Governor = spy
        try:
            Gateway(cfg, [entry], None, None)
            self.assertEqual(seen, {"a": 1})
            seen.clear()
            cfg.host.driver = "ollama"
            Gateway(cfg, [entry], None, None)
            self.assertEqual(seen, {"a": 4})
        finally:
            gw_mod.Governor = real


class ReviewSurvivesModelLoss(PipelineBase):
    """run_pipeline: a seat that does not come back, or a reflection that breaks, must not
    throw away built work."""

    async def test_reflection_error_after_integration_does_not_fail_the_build(self):
        rig = self.rig

        async def boom(*a, **kw):
            raise RuntimeError("judge would not load")

        rig.pipeline._reflect = boom
        run_id, result, ctl = await rig.run(BUILD_TASK, deliverable="build",
                                            options={"auto_delegate": True})
        self.assertEqual(ctl.states[-1], RunState.DONE)
        self.assertTrue(result.accepted)
        self.assertTrue(result.files_written)

    async def test_one_seat_missing_at_the_review_still_reviews(self):
        rig = self.rig
        host = rig.host
        real = host.ensure_resident
        state = {"executing": False}
        lost = "phi-next-14b"

        async def flaky(model_ids, profile, run_id, project=None):
            if state["executing"] and lost in model_ids:
                host._seats.get(run_id, set()).difference_update(model_ids)
                raise HostError(f"load failed for {lost} after retry: out of memory")
            return await real(model_ids, profile, run_id, project=project)

        host.ensure_resident = flaky

        ctl = await self._ctl()
        orig = ctl.set_state

        async def set_state(s, reason=""):
            if RunState(s) == RunState.EXECUTING:
                state["executing"] = True
            await orig(s, reason)

        ctl.set_state = set_state
        run_id, result, ctl = await rig.run(BUILD_TASK, ctl=ctl, deliverable="build",
                                            options={"auto_delegate": True})
        self.assertEqual(ctl.states[-1], RunState.DONE)
        self.assertTrue(result.accepted)
        self.assertTrue(result.files_written)
        ballots = rig.events(run_id, ET.REVIEW_BALLOT)
        self.assertTrue(ballots)
        self.assertNotIn(lost, {e.payload.get("model_id") for e in ballots})
        failed = [e for e in rig.events(run_id, ET.MODEL_FAILED) if e.payload.get("model_id") == lost]
        self.assertTrue(failed)

    async def _ctl(self):
        try:
            from test_api_run_pipeline import FakeControl
        except ImportError:  # pragma: no cover
            from tests.test_api_run_pipeline import FakeControl
        return FakeControl()


if __name__ == "__main__":
    unittest.main()
