"""End to end, mock mode: adaptive effort through the real RunPipeline.

Easy task -> light plan with a shorter deadline than a hard task; options effort=fixed leaves
the mode alone; effort.planned carries the adapted deadline; slower seats give a longer one.
"""

import unittest
from unittest import mock

from council.api import run_pipeline as rp
from council.core import event_types as ET

try:  # "discover -s tests" imports the test modules top-level
    from test_api_run_pipeline import ANSWER_TASK, SEATS, Base
except ImportError:  # "python -m unittest tests.test_..."
    from tests.test_api_run_pipeline import ANSWER_TASK, SEATS, Base

EASY_TASK = "What is the capital of France?"
HARD_TASK = ("Design a distributed consensus protocol tolerating Byzantine faults, prove its "
             "safety and liveness, and compare it with Raft and PBFT under network partitions.")


class Spy:
    """Records the mode and extra rounds handed to the deliberation."""

    def __init__(self) -> None:
        self.seen: list = []
        self._real = rp.RunPipeline._deliberate

    def patch(self):
        spy = self

        async def wrapper(self_, run_id, delib, lineup, mode, *a, **kw):
            spy.seen.append((mode, delib.max_extra_rounds))
            return await spy._real(self_, run_id, delib, lineup, mode, *a, **kw)

        return mock.patch.object(rp.RunPipeline, "_deliberate", wrapper)


class EffortE2E(Base):
    async def _planned(self, task: str, **req) -> dict:
        run_id, _, _ = await self.rig.run(task, **req)
        ev = self.rig.events(run_id, ET.EFFORT_PLANNED)
        self.assertEqual(len(ev), 1, "exactly one effort.planned per standard run")
        return ev[0].payload

    async def test_easy_task_gets_light_plan_shorter_than_hard(self):
        easy = await self._planned(EASY_TASK)
        hard = await self._planned(HARD_TASK)
        self.assertEqual((easy["level"], easy["difficulty"]), ("light", "easy"))
        self.assertEqual((hard["level"], hard["difficulty"]), ("heavy", "hard"))
        self.assertLess(easy["deadline_s"], hard["deadline_s"])
        self.assertLessEqual(len(easy["rounds"]), len(hard["rounds"]))
        self.assertEqual(easy["reasoning"], "off")
        self.assertLessEqual(easy["max_extra_rounds"], hard["max_extra_rounds"])

    async def test_planned_event_deadline_is_the_one_the_deliberation_gets(self):
        spy = Spy()
        with spy.patch():
            payload = await self._planned(EASY_TASK)
        mode, extra = spy.seen[0]
        self.assertEqual(float(mode.deadline_s), payload["deadline_s"])
        self.assertEqual(list(mode.rounds), payload["rounds"])
        self.assertEqual(mode.reasoning, payload["reasoning"])
        self.assertEqual(extra, payload["max_extra_rounds"])
        chamber = self.rig.config.chamber
        self.assertGreaterEqual(payload["deadline_s"], chamber.min_deadline_s)
        self.assertLessEqual(payload["deadline_s"], chamber.max_deadline_s)
        # the adapted deadline differs from the untouched standard one for an easy task
        self.assertNotEqual(payload["deadline_s"], float(self.rig.config.mode("standard").deadline_s))

    async def test_effort_fixed_leaves_the_mode_untouched(self):
        base = self.rig.config.mode("standard")
        spy = Spy()
        with spy.patch():
            run_id, _, _ = await self.rig.run(EASY_TASK, options={"effort": "fixed"})
        self.assertEqual(self.rig.events(run_id, ET.EFFORT_PLANNED), [])
        mode, extra = spy.seen[0]
        self.assertEqual(float(mode.deadline_s), float(base.deadline_s))
        self.assertEqual(list(mode.rounds), list(base.rounds))
        self.assertEqual(mode.reasoning, base.reasoning)
        self.assertEqual(extra, 0)

    async def test_slower_seats_give_a_longer_deadline(self):
        fast = await self._planned(ANSWER_TASK, options={"effort": "normal"})
        by_id = {m.id: m for m in self.rig.registry}
        for mid in SEATS:
            m = by_id[mid]
            self.assertTrue(m.measured.tps_1, f"{mid} has no measured speed in models.json")
            m.measured.tps_1 = float(m.measured.tps_1) / 4.0
        slow = await self._planned(ANSWER_TASK, options={"effort": "normal"})
        self.assertEqual(fast["rounds"], slow["rounds"])
        chamber = self.rig.config.chamber
        self.assertLess(fast["deadline_s"], chamber.max_deadline_s, "cap hides the speed effect")
        self.assertGreater(slow["deadline_s"], fast["deadline_s"])

    async def test_forced_levels_and_explicit_deadline(self):
        light = await self._planned(HARD_TASK, options={"effort": "light"})
        heavy = await self._planned(EASY_TASK, options={"effort": "heavy"})
        self.assertEqual((light["level"], heavy["level"]), ("light", "heavy"))
        self.assertLess(light["deadline_s"], heavy["deadline_s"])
        pinned = await self._planned(EASY_TASK, options={"deadline_s": 77})
        self.assertEqual(pinned["deadline_s"], 77.0)

    async def test_quick_mode_and_adaptive_off_emit_no_plan(self):
        run_id, _, _ = await self.rig.run(EASY_TASK, mode="quick")
        self.assertEqual(self.rig.events(run_id, ET.EFFORT_PLANNED), [])
        self.rig.config.chamber.adaptive = False
        run_id, _, _ = await self.rig.run(EASY_TASK)
        self.assertEqual(self.rig.events(run_id, ET.EFFORT_PLANNED), [])


if __name__ == "__main__":
    unittest.main()
