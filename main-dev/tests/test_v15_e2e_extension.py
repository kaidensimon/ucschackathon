"""End to end, mock mode: the dynamic extension of the deliberation (round.extended).

The whole RunPipeline runs (router, host, gateway, deliberation, review is off by the answer task).
Only the ballots of rounds 2 and 3 are scripted, so the tallies are exact. Everything else is the
mock's own output."""

import asyncio
import json
import unittest

from council.core import event_types as ET
from council.core.schemas import RunRequest, RunState

try:  # "discover -s tests" imports the test modules top-level
    from test_api_run_pipeline import ANSWER_TASK, SEATS, Base, FakeControl
except ImportError:  # "python -m unittest tests.test_..."
    from tests.test_api_run_pipeline import ANSWER_TASK, SEATS, Base, FakeControl

BALLOT_PURPOSES = ("seat.r2", "seat.r3")


class BallotScript:
    """Wraps the rig's responder. Ballot round n (0 = the r2 ballot, 1 = the next, ...) gets the
    choices `rounds[n]`: one option index per seat (0 = o1, 1 = o2, ...). The mock's own
    ballot is used for everything else. `r0_minority` seats get a different answer_key at round 0."""

    def __init__(self, rig, rounds, r0_minority=()) -> None:
        self.inner = rig.responder
        self.rounds = rounds
        self.r0_minority = set(r0_minority)
        self.seen: dict[int, int] = {}  # seat_no -> ballots it has cast
        self.log: list = []  # (ballot round, seat, choice)
        rig.gateway.responder = self
        rig.responder = self

    @property
    def specs(self):
        return self.inner.specs

    async def respond(self, spec, on_delta=None):
        res = await self.inner.respond(spec, on_delta)
        seat = int((spec.meta or {}).get("seat_no", 0))
        if spec.purpose == "seat.r0" and seat in self.r0_minority and isinstance(res.parsed, dict):
            parsed = dict(res.parsed, answer_key="sliding-window")
            return res.model_copy(update={"parsed": parsed, "content": json.dumps(parsed)})
        if spec.purpose not in BALLOT_PURPOSES or not isinstance(res.parsed, dict):
            return res
        n = self.seen.get(seat, 0)
        self.seen[seat] = n + 1
        row = self.rounds[min(n, len(self.rounds) - 1)]
        options = list(spec.json_schema["properties"]["choice"]["enum"])
        choice = options[min(row[seat], len(options) - 1)]
        self.log.append((n, seat, choice))
        parsed = dict(res.parsed, choice=choice, ranking=[choice], blocking_objection=None,
                      crux_votes=[], changed_because=[])
        return res.model_copy(update={"parsed": parsed, "content": json.dumps(parsed)})


def types_of(rig, run_id):
    return [e.type for e in rig.events(run_id)]


class Extension(Base):
    async def go(self, rounds, seats=None, r0_minority=(), options=None):
        rig = self.rig
        script = BallotScript(rig, rounds, r0_minority)
        seats = list(seats or SEATS)
        rig._n += 1
        run_id = f"run_{rig._n:03d}"
        request = RunRequest(task=ANSWER_TASK, workspace=str(rig.workspace), deliverable="answer",
                             lineup_override=seats, options=dict(options or {}))
        rig.store.create_run(run_id, ANSWER_TASK, request.workspace, request.mode, RunState.INTAKE)
        ctl = FakeControl()
        result = await asyncio.wait_for(rig.pipeline.run(run_id, request, ctl), 120.0)
        return run_id, result, script

    def completed(self, run_id):
        return [e.payload for e in self.rig.events(run_id, ET.ROUND_COMPLETED)]

    def extended(self, run_id):
        return [e.payload for e in self.rig.events(run_id, ET.ROUND_EXTENDED)]

    async def test_sixty_percent_with_rising_agreement_adds_one_round_then_consensus(self):
        # light: planned rounds r0 r1 r2, one extra allowed. 3 of 5 (60%), then 4 of 5 (80%).
        run_id, result, script = await self.go(
            [[0, 0, 0, 1, 1], [0, 0, 0, 0, 1]], options={"effort": "light"})
        rig = self.rig
        plan = rig.events(run_id, ET.EFFORT_PLANNED)[0].payload
        self.assertEqual(plan["rounds"], ["r0", "r1", "r2"])
        self.assertEqual(plan["max_extra_rounds"], 1)
        ext = self.extended(run_id)
        self.assertEqual(len(ext), 1, ext)
        self.assertEqual(ext[0]["round"], 3)
        self.assertAlmostEqual(ext[0]["agreement"], 0.6)
        self.assertEqual((ext[0]["extra_used"], ext[0]["extra_max"]), (1, 1))
        self.assertTrue(ext[0]["reason"])
        # order: round 2 completes, the extension is announced, round 3 starts
        types = types_of(rig, run_id)
        i = types.index(ET.ROUND_EXTENDED)
        self.assertEqual(types[i - 1], ET.ROUND_COMPLETED)
        self.assertEqual(types[i + 1], ET.CONSENSUS_FAILED)
        self.assertEqual(types[i + 2], ET.ROUND_STARTED)
        started = [e.payload["round"] for e in rig.events(run_id, ET.ROUND_STARTED)]
        self.assertEqual(started, [0, 1, 2, 3])
        done = self.completed(run_id)
        self.assertEqual([c["round"] for c in done][-2:], [2, 3])
        self.assertTrue(done[-1]["converged"])
        # each seat voted twice, the second round is the extra one
        self.assertEqual(sorted(set(s for _, s, _ in script.log)), [0, 1, 2, 3, 4])
        self.assertEqual(len(script.log), 10)
        self.assertEqual(result.decision.outcome, "consensus")
        self.assertEqual(result.decision.rounds_run, 4)
        self.assertEqual(result.decision.tally, {"o1": 4, "o2": 1})

    async def test_stagnant_tally_after_a_planned_round_goes_to_the_fallback_without_extension(self):
        # standard-size effort (heavy): r0..r3 planned, two extra allowed. 3 of 5 twice.
        run_id, result, _ = await self.go(
            [[0, 0, 0, 1, 1], [0, 0, 0, 1, 1]], options={"effort": "heavy"})
        plan = self.rig.events(run_id, ET.EFFORT_PLANNED)[0].payload
        self.assertEqual(plan["rounds"], ["r0", "r1", "r2", "r3"])
        self.assertEqual(plan["max_extra_rounds"], self.rig.config.chamber.max_extra_rounds)
        self.assertGreaterEqual(plan["max_extra_rounds"], 2)
        self.assertEqual(self.extended(run_id), [])
        self.assertNotIn(ET.ROUND_EXTENDED, types_of(self.rig, run_id))
        self.assertEqual(result.decision.rounds_run, 4)
        self.assertNotEqual(result.decision.outcome, "consensus")
        self.assertEqual(result.decision.tally, {"o1": 3, "o2": 2})

    async def test_stagnation_stops_a_running_extension(self):
        # light: the 60% first ballot round is extended once, the same 60% again is not extended again.
        run_id, result, script = await self.go(
            [[0, 0, 0, 1, 1], [0, 0, 0, 1, 1], [0, 0, 0, 1, 1]], options={"effort": "light"})
        self.assertEqual(len(self.extended(run_id)), 1)
        self.assertEqual(result.decision.rounds_run, 4)
        self.assertEqual(len(script.log), 10)  # no third ballot round
        self.assertNotEqual(result.decision.outcome, "consensus")

    async def test_never_more_than_max_extra_rounds_even_when_agreement_keeps_rising(self):
        # light allows one extra round. 6 seats: 3 of 6, then 4 of 6 (rose), the cap is reached.
        rig = self.rig
        six = SEATS + [next(m.id for m in rig.registry if m.id not in SEATS)]
        run_id, result, script = await self.go(
            [[0, 0, 0, 1, 1, 1], [0, 0, 0, 0, 1, 1], [0, 0, 0, 0, 0, 1]], seats=six,
            options={"effort": "light"})
        self.assertEqual(len(self.extended(run_id)), 1)
        self.assertEqual(result.decision.rounds_run, 4)
        self.assertEqual(len(script.log), 12)
        self.assertEqual(result.decision.tally, {"o1": 4, "o2": 2})
        self.assertNotEqual(result.decision.outcome, "consensus")
        self.assertEqual(self.completed(run_id)[-1]["round"], 3)

    async def test_config_cap_zero_means_no_extension(self):
        self.rig.config.chamber.max_extra_rounds = 0
        run_id, result, _ = await self.go(
            [[0, 0, 0, 1, 1], [0, 0, 0, 0, 1]], options={"effort": "light"})
        plan = self.rig.events(run_id, ET.EFFORT_PLANNED)[0].payload
        self.assertEqual(plan["max_extra_rounds"], 0)
        self.assertEqual(self.extended(run_id), [])
        self.assertEqual(result.decision.rounds_run, 3)
        self.assertEqual(result.decision.outcome, "majority")

    async def test_fixed_effort_never_extends(self):
        run_id, result, _ = await self.go([[0, 0, 0, 1, 1]], options={"effort": "fixed"})
        self.assertEqual(self.rig.events(run_id, ET.EFFORT_PLANNED), [])
        self.assertEqual(self.extended(run_id), [])
        self.assertNotEqual(result.decision.outcome, "consensus")

    async def test_two_seat_council_splits_one_one_and_the_chair_decides_after_one_extension(self):
        # 1-1 is 50%: extended once (first ballot round), the same tally again: chair, no more rounds.
        run_id, result, _ = await self.go(
            [[0, 1], [0, 1]], seats=SEATS[:2], r0_minority=[1], options={"effort": "light"})
        self.assertEqual(len(self.extended(run_id)), 1)
        self.assertEqual(result.decision.outcome, "chair")
        self.assertEqual(result.decision.rounds_run, 4)
        self.assertEqual(types_of(self.rig, run_id)[-1], ET.RUN_COMPLETED)


if __name__ == "__main__":
    unittest.main()
