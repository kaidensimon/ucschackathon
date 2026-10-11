"""End to end, mock mode: a BUILD run goes plan -> workers -> checks -> review accepts ->
files integrated. Uses the real RunPipeline, Host, Gateway, Store and bus (rig from
test_api_run_pipeline)."""

import subprocess
import sys
import unittest

from council.core import event_types as ET
from council.core.schemas import Plan, RunState, TaskStatus

try:  # "discover -s tests" imports the test modules top-level
    from test_api_run_pipeline import BUILD_TASK, SEATS, Base
except ImportError:  # "python -m unittest tests.test_..."
    from tests.test_api_run_pipeline import BUILD_TASK, SEATS, Base

EXPECTED = ("ratelimiter/__init__.py", "ratelimiter/token_bucket.py",
            "ratelimiter/sliding_window.py", "tests/test_token_bucket.py", "README.md")


class BuildAccept(Base):
    OPTS = {"auto_delegate": True, "seed": 11}

    async def _build(self):
        return await self.rig.run(BUILD_TASK, deliverable="build", options=dict(self.OPTS))

    async def test_review_accepts_and_files_are_written(self):
        run_id, result, ctl = await self._build()
        rig = self.rig
        verdicts = rig.events(run_id, ET.REVIEW_VERDICT)
        self.assertTrue(verdicts, "no review.verdict event")
        self.assertEqual(verdicts[-1].payload["verdict"], "accept")
        self.assertTrue(result.accepted)
        self.assertTrue(result.files_written)
        for rel in EXPECTED:
            self.assertIn(rel, result.files_written)
            self.assertTrue((rig.workspace / rel).is_file(), rel)
        self.assertEqual(ctl.states[-1], RunState.DONE)
        self.assertEqual(ctl.questions, [])
        self.assertEqual(ctl.delegate_waits, 0)

    async def test_plan_is_made_and_every_worker_task_passes(self):
        run_id, result, _ = await self._build()
        rig = self.rig
        plan = Plan.model_validate(rig.store.get_json("plans", run_id))
        self.assertTrue(plan.tasks)
        self.assertIsNotNone(result.plan)
        self.assertEqual([t.id for t in result.plan.tasks], [t.id for t in plan.tasks])
        ready = rig.events(run_id, ET.PLAN_READY)
        self.assertTrue(ready)
        self.assertEqual(ready[-1].payload["task_count"], len(plan.tasks))
        self.assertTrue(rig.events(run_id, ET.DELEGATION_STARTED))
        passed = {e.payload["task_id"] for e in rig.events(run_id, ET.TASK_PASSED)}
        self.assertEqual(passed, {t.id for t in plan.tasks})
        self.assertEqual(rig.events(run_id, ET.TASK_FAILED), [])
        rep = result.report
        self.assertIsNotNone(rep)
        self.assertEqual((rep.summary.passed, rep.summary.failed, rep.summary.blocked),
                         (len(plan.tasks), 0, 0))
        self.assertTrue(all(t.status == TaskStatus.passed for t in rep.tasks))

    async def test_checks_run_and_pass_with_no_deviation(self):
        run_id, result, _ = await self._build()
        rig = self.rig
        self.assertTrue(rig.events(run_id, ET.CHECK_RESULT), "no check ever ran")
        rep = result.report
        self.assertTrue(rep.final_checks, "no final check")
        real = [c for c in rep.final_checks if not c.invalid]
        self.assertTrue(real)
        self.assertTrue(all(c.ok for c in real), [c.output_tail for c in real if not c.ok])
        self.assertEqual(rep.deviations, [])
        self.assertTrue(rig.pipeline._checks_pass(rep))

    async def test_integration_checks_then_copy_into_the_workspace(self):
        run_id, result, _ = await self._build()
        rig = self.rig
        integ = rig.events(run_id, ET.INTEGRATION_RESULT)
        stages = [e.payload["stage"] for e in integ]
        self.assertIn("checks", stages)
        self.assertIn("copy", stages)
        self.assertLess(stages.index("checks"), len(stages) - 1 - stages[::-1].index("copy"))
        self.assertTrue(all(e.payload["ok"] for e in integ), [e.payload for e in integ])
        copy = [e for e in integ if e.payload["stage"] == "copy"][-1].payload
        self.assertEqual(sorted(copy["files_written"]), sorted(result.files_written))
        types = [e.type for e in rig.events(run_id)]
        self.assertLess(max(i for i, t in enumerate(types) if t == ET.REVIEW_VERDICT),
                        max(i for i, t in enumerate(types) if t == ET.INTEGRATION_RESULT))
        completed = rig.events(run_id, ET.RUN_COMPLETED)
        self.assertEqual(len(completed), 1)
        self.assertEqual(sorted(completed[0].payload["files_written"]), sorted(result.files_written))
        self.assertEqual(types[-1], ET.RUN_COMPLETED)

    async def test_whole_council_reviews_and_the_vote_is_accept(self):
        run_id, result, _ = await self._build()
        rig = self.rig
        self.assertTrue(rig.events(run_id, ET.REVIEW_STARTED))
        ballots = rig.events(run_id, ET.REVIEW_BALLOT)
        self.assertGreaterEqual(len(ballots), len(SEATS))
        first = ballots[:len(SEATS)]
        self.assertEqual(sorted(b.payload["seat_no"] for b in first), list(range(len(SEATS))))
        last = rig.events(run_id, ET.REVIEW_VERDICT)[-1].payload
        self.assertEqual(last["verdict"], "accept")
        self.assertGreater(last["tally"].get("accept", 0), len(SEATS) // 2)
        self.assertEqual(last["next_state"], RunState.INTEGRATING.value)
        self.assertEqual(rig.events(run_id, ET.REVIEW_FINAL_SAY), [])

    async def test_built_package_works_on_disk(self):
        _, result, _ = await self._build()
        ws = self.rig.workspace
        done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                              cwd=str(ws), capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        code = ("from ratelimiter.token_bucket import TokenBucket as T;"
                "from ratelimiter import sliding_window;print('ok')")
        probe = subprocess.run([sys.executable, "-c", code], cwd=str(ws), capture_output=True,
                               text=True, timeout=60)
        if probe.returncode != 0:  # class names are the mock worker's choice: import only
            probe = subprocess.run(
                [sys.executable, "-c", "import ratelimiter.token_bucket, ratelimiter.sliding_window"],
                cwd=str(ws), capture_output=True, text=True, timeout=60)
        self.assertEqual(probe.returncode, 0, probe.stderr[-1000:])

    async def test_run_is_cleaned_up_and_recorded(self):
        run_id, result, _ = await self._build()
        rig = self.rig
        self.assertFalse(rig.host._seats.get(run_id), "seats not released")
        self.assertIsNotNone(rig.store.get_json("plans", run_id))
        self.assertIsNotNone(rig.store.get_json("lineups", run_id))
        self.assertTrue(rig.events(run_id, ET.MEMORY_CANDIDATE))
        self.assertEqual(rig.events(run_id, ET.RUN_FAILED), [])


if __name__ == "__main__":
    unittest.main()
