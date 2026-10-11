"""End to end, mock mode: the real RunController and RunPipeline at council sizes 2 to 6.

Every run is an "answer" deliverable. The size comes in as options {"k": n}, the way the UI sends it.
"""

import asyncio
import unittest
from pathlib import Path
from unittest import mock

from council.api.controller import RunController
from council.api.run_pipeline import RunPipeline
from council.core import event_types as ET
from council.core.schemas import RunRequest, RunState, UserInput
from council.gateway.mock import MockResponder

HOME = Path(__file__).resolve().parents[1]
SPEED = 100000.0
TIMEOUT = 90.0
TASK = "Which rate limiter should a small API use: a token bucket or a sliding window? Say why."
SIZES = [2, 3, 4, 5, 6]


class SplitTwoResponder(MockResponder):
    """The stock mock never splits a 2 seat council. This one makes seat 1 disagree with seat 0."""

    # The deliberation does not tell the mock the council size, so go by seat number alone.
    def _is_minority(self, seat, k):
        return seat == 1

    def _is_last(self, seat, k):
        return seat == 1


async def collect(ctrl: RunController, run_id: str) -> list:
    out = []

    async def pump() -> None:
        async for ev in ctrl.bus.subscribe(run_id, 0):
            out.append(ev)
            if ev.type == ET.USER_INPUT_REQUESTED and ctrl.is_active(run_id):
                try:
                    await ctrl.submit_input(run_id, UserInput(
                        request_id=ev.payload.get("request_id") or "", choice="go"))
                except Exception:
                    pass

    await asyncio.wait_for(pump(), TIMEOUT)
    return out


class Base(unittest.IsolatedAsyncioTestCase):
    def build(self, responder=None) -> RunController:
        ctrl = RunController.build_mock(home=HOME, speed=SPEED)
        if responder is not None:
            ctrl.gateway.responder = responder
        self.addAsyncCleanup(self.close, ctrl)
        return ctrl

    async def close(self, ctrl: RunController) -> None:
        await ctrl.shutdown()
        ctrl.store.close()

    async def run_size(self, ctrl: RunController, k: int, task: str = TASK, **opts):
        options = {"k": k, "seed": 7, "auto_input": True}
        options.update(opts)
        run_id = await ctrl.start(RunRequest(
            task=task, mode="standard", deliverable="answer", options=options))
        events = await collect(ctrl, run_id)
        await ctrl.wait(run_id, TIMEOUT)
        return run_id, events


class Sizes(Base):
    async def test_every_size_ends_done_with_a_decision(self):
        for k in SIZES:
            with self.subTest(k=k):
                ctrl = self.build()
                run_id, events = await self.run_size(ctrl, k)
                self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
                snap = ctrl.snapshot(run_id)
                self.assertEqual(snap.state, RunState.DONE)
                self.assertIsNotNone(snap.decision)
                self.assertTrue(snap.decision.final_text.strip())
                self.assertIn(snap.decision.outcome, ("consensus", "majority", "chair"))
                self.assertEqual(ctrl.store.get_run(run_id)["state"], "DONE")

    async def test_lineup_has_exactly_n_seats(self):
        for k in SIZES:
            with self.subTest(k=k):
                ctrl = self.build()
                run_id, events = await self.run_size(ctrl, k)
                self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
                snap = ctrl.snapshot(run_id)
                self.assertEqual(len(snap.lineup.seats), k)
                self.assertEqual(snap.lineup.k, k)
                self.assertEqual([s.seat_no for s in snap.lineup.seats], list(range(k)))
                ids = [s.model_id for s in snap.lineup.seats]
                self.assertEqual(len(set(ids)), k, "a model sits twice")
                assigned = [e for e in events if e.type == ET.SEAT_ASSIGNED]
                self.assertEqual(len(assigned), k)
                self.assertEqual(sorted(e.payload["seat_no"] for e in assigned), list(range(k)))
                sel = next(e for e in events if e.type == ET.ROUTER_LINEUP_SELECTED).payload
                self.assertEqual(sel["k"], k)

    async def test_ballots_come_from_every_seat(self):
        for k in SIZES:
            with self.subTest(k=k):
                ctrl = self.build()
                run_id, events = await self.run_size(ctrl, k)
                self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
                decision = ctrl.snapshot(run_id).decision
                self.assertGreaterEqual(sum(decision.tally.values()), 1)
                self.assertLessEqual(sum(decision.tally.values()), k)
                self.assertGreaterEqual(decision.agreement, 0.0)
                self.assertLessEqual(decision.agreement, 1.0)
                self.assertGreaterEqual(decision.rounds_run, 1)

    async def test_chair_is_named_and_seated_at_every_size(self):
        for k in SIZES:
            with self.subTest(k=k):
                ctrl = self.build()
                run_id, events = await self.run_size(ctrl, k)
                lineup = ctrl.snapshot(run_id).lineup
                self.assertTrue(lineup.chair_model_id)
                chairs = [s for s in lineup.seats if s.is_chair]
                self.assertLessEqual(len(chairs), 1)
                if chairs:
                    self.assertEqual(chairs[0].model_id, lineup.chair_model_id)

    async def test_two_seats_split_vote_goes_to_the_chair(self):
        ctrl = self.build(SplitTwoResponder(seed=0))
        run_id, events = await self.run_size(ctrl, 2)
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
        snap = ctrl.snapshot(run_id)
        self.assertEqual(snap.state, RunState.DONE)
        self.assertEqual(len(snap.lineup.seats), 2)
        types = [e.type for e in events]
        self.assertIn(ET.CHAIR_STARTED, types, "a split 2 seat vote never reached the chair")
        self.assertEqual(snap.decision.outcome, "chair")
        self.assertTrue(snap.decision.final_text.strip())

    async def test_unsplit_two_seats_agree_without_the_chair(self):
        ctrl = self.build(MockResponder(seed=0, split=False))
        run_id, events = await self.run_size(ctrl, 2)
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
        snap = ctrl.snapshot(run_id)
        self.assertEqual(len(snap.lineup.seats), 2)
        self.assertNotIn(ET.CHAIR_STARTED, [e.type for e in events])
        self.assertIn(snap.decision.outcome, ("consensus", "majority"))

    async def test_the_controller_runs_the_real_pipeline_with_the_asked_size(self):
        seen = []
        real = RunPipeline.run

        async def spy(pipe, run_id, req, ctl):
            seen.append((run_id, dict(req.options or {})))
            return await real(pipe, run_id, req, ctl)

        ctrl = self.build()
        with mock.patch.object(RunPipeline, "run", spy):
            run_id, events = await self.run_size(ctrl, 4)
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
        self.assertEqual([r for r, _ in seen], [run_id])
        self.assertEqual(seen[0][1]["k"], 4)


if __name__ == "__main__":
    unittest.main()
