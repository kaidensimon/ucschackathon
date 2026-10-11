"""1.5 end to end, mock mode: the memory plan inside a real run.

Real classes only (RunPipeline, Host, RamBudget, Gateway, Store). The machine memory is read the
way the pipeline reads it in mock mode: from the host RamBudget. The sizes come from the registry
(measured.ram_gb_live). The configured planner is a separate model (nemotron3-nano-30b, 26 GiB)
that is not one of the five seats."""

import unittest

from council.api import run_pipeline as rp
from council.core import event_types as ET
from council.core.schemas import RunState
from council.core.schemas_v15 import MemoryPlan
from tests.test_api_run_pipeline import ANSWER_TASK, BUILD_TASK, SEATS, Base

PLANNER = "nemotron3-nano-30b"  # not a seat; made the configured planner below
CLERK = "gemma4-12b-q4"  # configured clerk, not a seat
SEAT_GIB = 16.0 + 19.5 + 19.0 + 10.0 + 11.0  # the five SEATS in config/models.json
PLANNER_GIB = 26.0
CLERK_GIB = 9.5
EXTRAS_GIB = SEAT_GIB + PLANNER_GIB + CLERK_GIB  # 111.0 with both separate models
RESERVE = 10.0  # config memory.reserve_gib


def plan_of(rig, run_id) -> MemoryPlan:
    events = rig.events(run_id, ET.MEMORY_PLANNED)
    assert len(events) == 1, len(events)
    return MemoryPlan.model_validate(events[0].payload["plan"])


class MemPlanE2E(Base):
    def setUp(self) -> None:
        super().setUp()
        rig = self.rig
        # the planner becomes a separate model through the registry, as an operator would set it
        for i, m in enumerate(rig.registry):
            if m.id == PLANNER:
                rig.registry[i] = m.model_copy(update={"roles": ["seat", "planner"]})
        self.assertEqual(rig.pipeline._role("planner"), PLANNER)

    def machine(self, total_gib: float) -> None:
        """Set the memory the host sees (no resident model yet, so available == total)."""
        self.rig.host.ram.read_available_gib = lambda: total_gib

    async def test_tight_memory_gives_planner_to_a_seated_model(self):
        rig = self.rig
        self.machine(SEAT_GIB + RESERVE + 4.0)  # seats fit, seats + planner + clerk do not
        run_id, result, ctl = await rig.run(BUILD_TASK, deliverable="build",
                                            options={"auto_delegate": True, "auto_input": True})
        self.assertEqual(ctl.states[-1], RunState.DONE)
        plan = plan_of(rig, run_id)
        self.assertTrue(plan.fits)
        self.assertEqual(plan.dropped, [])
        self.assertEqual(plan.total_gib, round(SEAT_GIB + RESERVE + 4.0, 2))
        self.assertIn(plan.roles["planner"], SEATS)
        self.assertNotEqual(plan.roles["planner"], PLANNER)
        self.assertNotIn(PLANNER, plan.per_model)
        self.assertTrue(any("work roles go to seated models" in n for n in plan.notes), plan.notes)
        self.assertLessEqual(sum(plan.per_model.values()), plan.budget_gib + 1e-6)
        # the separate planner model was never loaded; the run still planned and built
        loaded = {e.payload["model_id"] for e in rig.events(run_id, ET.MODEL_LOADED)}
        self.assertNotIn(PLANNER, loaded)
        self.assertTrue(loaded <= set(SEATS), loaded)
        self.assertIsNotNone(result.plan)

    async def test_planned_event_comes_once_before_any_model_load(self):
        rig = self.rig
        self.machine(SEAT_GIB + RESERVE + 4.0)
        run_id, _, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        types = [e.type for e in rig.events(run_id)]
        self.assertEqual(types.count(ET.MEMORY_PLANNED), 1)
        self.assertLess(types.index(ET.MEMORY_PLANNED), types.index(ET.MODEL_LOADING))
        stored = rig.store.kv_get(rp.MEMORY_NS, run_id)
        self.assertEqual(stored["roles"], plan_of(rig, run_id).roles)
        self.assertEqual(rig.pipeline._state, {})  # nothing of the run is kept after it

    async def test_large_budget_shares_nothing(self):
        rig = self.rig
        self.machine(400.0)
        run_id, result, ctl = await rig.run(BUILD_TASK, deliverable="build",
                                            options={"auto_delegate": True, "auto_input": True})
        self.assertEqual(ctl.states[-1], RunState.DONE)
        plan = plan_of(rig, run_id)
        self.assertTrue(plan.fits)
        self.assertEqual(plan.shared_roles, [])
        self.assertEqual(plan.dropped, [])
        self.assertEqual(plan.roles.get("planner"), PLANNER)  # the configured planner stays separate
        self.assertEqual(plan.roles.get("clerk"), CLERK)
        self.assertEqual(set(plan.per_model), set(SEATS) | {PLANNER, CLERK})
        self.assertFalse(any("work roles go to seated models" in n for n in plan.notes), plan.notes)
        self.assertIsNotNone(result.plan)

    async def test_the_edge_of_the_budget_decides_the_sharing(self):
        # exactly enough room for seats + planner + clerk: nothing is shared
        rig = self.rig
        self.machine(EXTRAS_GIB + RESERVE)
        run_id, _, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        plan = plan_of(rig, run_id)
        self.assertTrue(plan.fits)
        self.assertEqual(plan.shared_roles, [])
        self.assertEqual(plan.roles.get("planner"), PLANNER)
        # one GiB less: the planner is handed to a seat. Unload first: the pipeline counts
        # resident models into the total it sees, so a warm host would hide the shortfall.
        for row in rig.host.status():
            await rig.host.unload(row["model_id"], "test")
        self.machine(EXTRAS_GIB + RESERVE - 1.0)
        run_id, _, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-1], RunState.DONE)
        plan = plan_of(rig, run_id)
        self.assertTrue(plan.fits)
        self.assertIn(plan.roles["planner"], SEATS)
        self.assertTrue(any("work roles go to seated models" in n for n in plan.notes), plan.notes)

    async def test_registry_sizes_drive_the_plan(self):
        # same machine, but a tiny planner and clerk in the registry: they fit beside the seats
        rig = self.rig
        total = SEAT_GIB + RESERVE + 4.0
        self.machine(total)
        for i, m in enumerate(rig.registry):
            if m.id in (PLANNER, CLERK):
                rig.registry[i] = m.model_copy(update={"measured": m.measured.model_copy(
                    update={"ram_gb_live": 1.0, "ram_gb_batch": 1.0})})
        run_id, _, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-1], RunState.DONE)
        plan = plan_of(rig, run_id)
        self.assertTrue(plan.fits)
        self.assertEqual(plan.shared_roles, [])
        self.assertEqual(plan.roles.get("planner"), PLANNER)
        self.assertEqual(plan.per_model[PLANNER], 1.0)


if __name__ == "__main__":
    unittest.main()
