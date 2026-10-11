"""End to end, mock mode: chamber.chair_pick "random" draws the chair from the seed,
"router" keeps what the router named. Runs go through the real RunPipeline."""

import unittest

from council.core import event_types as ET
from council.core.schemas import LineupRecord

try:  # "discover -s tests" imports the test modules top-level
    from test_api_run_pipeline import ANSWER_TASK, SEATS, Base
except ImportError:  # "python -m unittest tests.test_..."
    from tests.test_api_run_pipeline import ANSWER_TASK, SEATS, Base

SEEDS = list(range(20))


class RandomChairE2E(Base):
    async def chair_of(self, seed: int, pick: str) -> tuple[str, dict]:
        rig = self.rig
        rig.config.chamber.chair_pick = pick
        run_id, _, _ = await rig.run(ANSWER_TASK, mode="quick", options={"seed": seed})
        lineup = rig.events(run_id, ET.ROUTER_LINEUP_SELECTED)[-1].payload["lineup"]
        return lineup["chair_model_id"], lineup

    async def test_chair_is_one_seat_and_flag_matches(self):
        chair, lineup = await self.chair_of(5, "random")
        self.assertIn(chair, {s["model_id"] for s in lineup["seats"]})
        self.assertIn(chair, SEATS)
        flagged = [s["model_id"] for s in lineup["seats"] if s["is_chair"]]
        self.assertEqual(flagged, [chair])

    async def test_same_seed_same_chair(self):
        a, _ = await self.chair_of(11, "random")
        b, _ = await self.chair_of(11, "random")
        self.assertEqual(a, b)

    async def test_chair_changes_across_20_seeds(self):
        chairs = []
        for seed in SEEDS:
            chair, lineup = await self.chair_of(seed, "random")
            self.assertIn(chair, {s["model_id"] for s in lineup["seats"]})
            chairs.append(chair)
        self.assertGreater(len(set(chairs)), 1)
        self.assertGreaterEqual(len(set(chairs)), 3)  # 5 seats, 20 fair draws
        self.assertLessEqual(set(chairs), set(SEATS))

    async def test_router_choice_is_kept_whatever_the_seed(self):
        # The router names its best-q seat, whatever the seed. The q values themselves move from
        # run to run (the router learns from every run on this rig), so the check is per run.
        for seed in (0, 1, 2, 3, 4, 5, 6, 7):
            chair, lineup = await self.chair_of(seed, "router")
            self.assertEqual([s["model_id"] for s in lineup["seats"] if s["is_chair"]], [chair])
            top = max(s["q"] for s in lineup["seats"])
            self.assertIn(chair, [s["model_id"] for s in lineup["seats"] if s["q"] == top], seed)

    async def test_stored_lineup_agrees_with_the_event(self):
        rig = self.rig
        rig.config.chamber.chair_pick = "random"
        run_id, _, _ = await rig.run(ANSWER_TASK, mode="quick", options={"seed": 9})
        ev = rig.events(run_id, ET.ROUTER_LINEUP_SELECTED)[-1].payload["lineup"]
        stored = LineupRecord.model_validate(rig.store.get_json("lineups", run_id))
        self.assertEqual(stored.chair_model_id, ev["chair_model_id"])
        self.assertEqual([s.model_id for s in stored.seats if s.is_chair], [ev["chair_model_id"]])
        assigned = rig.events(run_id, ET.SEAT_ASSIGNED)
        self.assertEqual(sum(1 for e in assigned if e.payload["is_chair"]), 1)

    async def test_pick_chair_for_council_sizes_2_to_6(self):
        rig = self.rig
        _, lineup = await self.chair_of(1, "router")
        rig.config.chamber.chair_pick = "random"
        base = LineupRecord.model_validate(lineup)
        for size in range(2, 6):  # the rig's lineup holds 5 seats; 2..5 are cut from it
            seats = base.seats[:size]
            rec = base.model_copy(update=dict(seats=seats, chair_model_id=seats[0].model_id))
            drawn = {rig.pipeline._pick_chair(rec, s).chair_model_id for s in SEEDS}
            self.assertLessEqual(drawn, {s.model_id for s in seats})
            self.assertEqual(drawn, {s.model_id for s in seats}, f"size {size}: not every seat can chair")
            out = rig.pipeline._pick_chair(rec, 3)
            self.assertEqual(sum(1 for s in out.seats if s.is_chair), 1)
            self.assertEqual(out.chair_model_id, next(s.model_id for s in out.seats if s.is_chair))
        rig.config.chamber.chair_pick = "router"
        self.assertIs(rig.pipeline._pick_chair(rec, 3), rec)


if __name__ == "__main__":
    unittest.main()
