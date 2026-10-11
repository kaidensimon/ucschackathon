"""RunPipeline wiring: adaptive effort, the drawn chair, and the review loop with its
argument round and final say. Mock mode only."""

import json
import random
import unittest
from unittest import mock

from council.api import run_pipeline as rp
from council.core import event_types as ET
from council.core.schemas import CheckResult, LineupRecord, RunState, WorkReport

try:  # "discover -s tests" imports the test modules top-level
    from test_api_run_pipeline import ANSWER_TASK, BUILD_TASK, SEATS, Base, FakeControl
except ImportError:  # "python -m unittest tests.test_..."
    from tests.test_api_run_pipeline import ANSWER_TASK, BUILD_TASK, SEATS, Base, FakeControl

FIX = {"verdict": "fix", "reason": "one caveat is missing",
       "fixes": [{"problem": "The README misses a caveat.", "task_id": None,
                  "proposed_change": "Add the caveat."}]}
ACCEPT = {"verdict": "accept", "fixes": [], "reason": "the checks pass on the current files"}
ASK = {"verdict": "ask_user", "fixes": [], "reason": "cannot tell"}


def phase_of(call_id: str) -> str:
    part = call_id.split(":")[-2]
    return "final" if part.startswith("rvf") else "debate" if part.startswith("rvd") else "blind"


class ReviewScript:
    """Wraps the rig's responder: review calls get the ballot `script(phase, seat_no, cycle)`
    returns (None = the mock's own ballot)."""

    def __init__(self, rig, script) -> None:
        self.inner = rig.responder
        self.script = script
        self.calls: list = []
        rig.gateway.responder = self
        rig.responder = self

    @property
    def specs(self):
        return self.inner.specs

    async def respond(self, spec, on_delta=None):
        res = await self.inner.respond(spec, on_delta)
        if spec.purpose != "review":
            return res
        phase = phase_of(spec.call_id)
        cycle = int("".join(ch for ch in spec.call_id.split(":")[-2] if ch.isdigit()) or 1)
        seat = int((spec.meta or {}).get("seat_no", 0))
        self.calls.append((phase, seat, cycle, spec))
        ballot = self.script(phase, seat, cycle)
        if ballot is None:
            return res
        return res.model_copy(update={"parsed": ballot, "content": json.dumps(ballot)})


def install(rig, script) -> ReviewScript:
    if not hasattr(rig.gateway, "responder"):
        raise unittest.SkipTest("gateway keeps its responder under another name")
    return ReviewScript(rig, script)


class Effort(Base):
    async def test_standard_run_plans_its_effort_and_passes_it_on(self):
        rig = self.rig
        seen = {}
        real = rp.RunPipeline._deliberate

        async def spy(self_, run_id, delib, lineup, mode, *a, **kw):
            seen["mode"], seen["extra"] = mode, delib.max_extra_rounds
            return await real(self_, run_id, delib, lineup, mode, *a, **kw)

        with mock.patch.object(rp.RunPipeline, "_deliberate", spy):
            run_id, _, _ = await rig.run(ANSWER_TASK, options={"effort": "heavy"})
        ev = rig.events(run_id, ET.EFFORT_PLANNED)
        self.assertEqual(len(ev), 1)
        p = ev[0].payload
        self.assertEqual((p["level"], p["difficulty"]), ("heavy", "hard"))
        self.assertEqual(p["max_extra_rounds"], rig.config.chamber.max_extra_rounds)
        self.assertEqual(seen["extra"], p["max_extra_rounds"])
        self.assertEqual(float(seen["mode"].deadline_s), p["deadline_s"])
        self.assertEqual(list(seen["mode"].rounds), p["rounds"])
        self.assertGreaterEqual(p["deadline_s"], rig.config.chamber.min_deadline_s)
        self.assertLessEqual(p["deadline_s"], rig.config.chamber.max_deadline_s)
        types = [e.type for e in rig.events(run_id)]
        self.assertLess(types.index(ET.ROUTER_LINEUP_SELECTED), types.index(ET.EFFORT_PLANNED))

    async def test_light_is_cheaper_than_heavy(self):
        rig = self.rig
        a, _, _ = await rig.run(ANSWER_TASK, options={"effort": "light"})
        b, _, _ = await rig.run(ANSWER_TASK, options={"effort": "heavy"})
        light = rig.events(a, ET.EFFORT_PLANNED)[0].payload
        heavy = rig.events(b, ET.EFFORT_PLANNED)[0].payload
        self.assertEqual(light["level"], "light")
        self.assertLess(light["deadline_s"], heavy["deadline_s"])
        self.assertLessEqual(len(light["rounds"]), len(heavy["rounds"]))

    async def test_fixed_quick_and_adaptive_off_keep_the_mode(self):
        rig = self.rig
        base = rig.config.mode("standard").deadline_s
        seen = []
        real = rp.RunPipeline._deliberate

        async def spy(self_, run_id, delib, lineup, mode, *a, **kw):
            seen.append((float(mode.deadline_s), delib.max_extra_rounds))
            return await real(self_, run_id, delib, lineup, mode, *a, **kw)

        with mock.patch.object(rp.RunPipeline, "_deliberate", spy):
            a, _, _ = await rig.run(ANSWER_TASK, options={"effort": "fixed"})
            b, _, _ = await rig.run(ANSWER_TASK, mode="quick")
            rig.config.chamber.adaptive = False
            c, _, _ = await rig.run(ANSWER_TASK)
        for run_id in (a, b, c):
            self.assertEqual(rig.events(run_id, ET.EFFORT_PLANNED), [])
        self.assertEqual(seen[0], (float(base), 0))
        self.assertEqual(seen[2], (float(base), 0))

    async def test_explicit_deadline_wins(self):
        rig = self.rig
        run_id, _, _ = await rig.run(ANSWER_TASK, options={"deadline_s": 77})
        self.assertEqual(rig.events(run_id, ET.EFFORT_PLANNED)[0].payload["deadline_s"], 77.0)


class Chair(Base):
    async def test_random_chair_is_drawn_from_the_seed(self):
        rig = self.rig
        rig.config.chamber.chair_pick = "random"
        run_id, _, _ = await rig.run(ANSWER_TASK, options={"seed": 7})
        lineup = rig.events(run_id, ET.ROUTER_LINEUP_SELECTED)[-1].payload["lineup"]
        seats = sorted(lineup["seats"], key=lambda s: s["seat_no"])
        want = random.Random("7:chair").choice(seats)
        self.assertEqual(lineup["chair_model_id"], want["model_id"])
        self.assertEqual([s["seat_no"] for s in seats if s["is_chair"]], [want["seat_no"]])
        assigned = rig.events(run_id, ET.SEAT_ASSIGNED)
        self.assertEqual([e.payload["seat_no"] for e in assigned if e.payload["is_chair"]],
                         [want["seat_no"]])
        self.assertEqual(rig.store.get_json("lineups", run_id)["chair_model_id"], want["model_id"])

    async def test_seeds_do_not_all_pick_the_same_seat(self):
        rig = self.rig
        rig.config.chamber.chair_pick = "random"
        chairs = set()
        for seed in range(8):
            run_id, _, _ = await rig.run(ANSWER_TASK, mode="quick", options={"seed": seed})
            chairs.add(rig.events(run_id, ET.ROUTER_LINEUP_SELECTED)[-1].payload["chair_model_id"])
        self.assertGreater(len(chairs), 1)
        self.assertLessEqual(chairs, set(SEATS))

    async def test_router_keeps_the_picked_chair(self):
        rig = self.rig
        rig.config.chamber.chair_pick = "router"
        with mock.patch.object(rp.RunPipeline, "_plan", side_effect=AssertionError("answer run")):
            run_id, _, _ = await rig.run(ANSWER_TASK, mode="quick", options={"seed": 7})
        lineup = LineupRecord.model_validate(rig.store.get_json("lineups", run_id))
        self.assertEqual(sum(1 for s in lineup.seats if s.is_chair), 1)
        self.assertIs(rig.pipeline._pick_chair(lineup, 7), lineup)
        best = max(lineup.seats, key=lambda s: (s.q, -s.seat_no))
        self.assertEqual(lineup.chair_model_id, best.model_id)  # the router's rule: best q
        rig.config.chamber.chair_pick = "random"
        drawn = {rig.pipeline._pick_chair(lineup, seed).chair_model_id for seed in range(12)}
        self.assertGreater(len(drawn), 1)


class ChecksPass(unittest.TestCase):
    def test_needs_a_real_passing_check_and_no_deviation(self):
        f = rp.RunPipeline._checks_pass
        ok, bad = CheckResult(ok=True), CheckResult(ok=False)
        invalid = CheckResult(ok=False, invalid=True)
        self.assertFalse(f(WorkReport()))
        self.assertFalse(f(WorkReport(final_checks=[invalid])))
        self.assertTrue(f(WorkReport(final_checks=[ok, invalid])))
        self.assertFalse(f(WorkReport(final_checks=[ok, bad])))
        self.assertFalse(f(WorkReport(final_checks=[ok], deviations=["x"])))


class ReviewLoop(Base):
    OPTS = {"auto_delegate": True, "seed": 3}

    async def _build(self, script, ctl=None, **cfg):
        rig = self.rig
        for key, value in cfg.items():
            setattr(rig.config.review, key, value)
        tap = install(rig, script)
        run_id, result, ctl = await rig.run(BUILD_TASK, ctl, deliverable="build", options=dict(self.OPTS))
        return run_id, result, ctl, tap

    async def test_split_vote_is_argued_once_and_can_agree(self):
        def script(phase, seat, cycle):
            if phase == "blind":
                return FIX if seat < 3 else ACCEPT
            return ACCEPT

        run_id, result, ctl, tap = await self._build(script)
        rig = self.rig
        self.assertTrue(result.accepted)
        debate = rig.events(run_id, ET.REVIEW_DEBATE)
        self.assertEqual(len(debate), 1)
        self.assertEqual(debate[0].payload["tally_before"]["fix"], 3)
        self.assertEqual(debate[0].payload["tally_after"]["accept"], len(SEATS))
        self.assertEqual(len(rig.events(run_id, ET.REVIEW_BALLOT)), 2 * len(SEATS))
        self.assertEqual(rig.events(run_id, ET.REVIEW_FINAL_SAY), [])
        self.assertEqual([e.payload["verdict"] for e in rig.events(run_id, ET.REVIEW_VERDICT)], ["accept"])
        self.assertEqual(ctl.questions, [])
        # the argument round shows a seat its own vote and the others', without names
        spec = next(s for ph, seat, _, s in tap.calls if ph == "debate" and seat == 0)
        text = spec.messages[-1]["content"]
        self.assertIn("one caveat is missing", text)
        for model_id in SEATS:
            self.assertNotIn(model_id, text)

    async def test_agreed_vote_is_not_argued(self):
        run_id, result, _, tap = await self._build(lambda phase, seat, cycle: ACCEPT)
        self.assertTrue(result.accepted)
        self.assertEqual(self.rig.events(run_id, ET.REVIEW_DEBATE), [])
        self.assertEqual({ph for ph, *_ in tap.calls}, {"blind"})

    async def test_debate_off(self):
        def script(phase, seat, cycle):
            return (FIX if seat < 3 else ACCEPT) if cycle == 1 else ACCEPT

        run_id, result, _, tap = await self._build(script, debate=False)
        self.assertTrue(result.accepted)
        self.assertEqual(self.rig.events(run_id, ET.REVIEW_DEBATE), [])
        self.assertNotIn("debate", {ph for ph, *_ in tap.calls})

    async def test_second_fix_on_passing_work_goes_to_a_random_seat(self):
        def script(phase, seat, cycle):
            return ACCEPT if phase == "final" else FIX

        with mock.patch.object(rp.review_mod, "fixes_to_tasks", wraps=rp.review_mod.fixes_to_tasks) as to_tasks:
            run_id, result, ctl, tap = await self._build(script)
        rig = self.rig
        self.assertEqual(to_tasks.call_count, 1)  # one fix cycle, with the plan's own test command
        self.assertEqual(to_tasks.call_args.kwargs["test_cmd"], "python -m unittest discover -s tests -v")
        self.assertTrue(self.rig.pipeline._checks_pass(result.report), "mock build must pass its checks")
        verdicts = rig.events(run_id, ET.REVIEW_VERDICT)
        self.assertEqual([e.payload["verdict"] for e in verdicts], ["fix", "fix"])
        self.assertEqual(verdicts[0].payload["next_state"], RunState.EXECUTING.value)
        self.assertEqual(verdicts[1].payload["next_state"], RunState.REVIEWING.value)
        self.assertIn("every current check passes", verdicts[1].payload["reason"])
        self.assertEqual(ctl.states.count(RunState.REVIEWING), 2)
        say = rig.events(run_id, ET.REVIEW_FINAL_SAY)
        self.assertEqual(len(say), 1)
        seats = rig.store.get_json("lineups", run_id)["seats"]
        want = random.Random("3:2").choice(sorted(seats, key=lambda s: s["seat_no"]))
        self.assertEqual((say[0].payload["seat_no"], say[0].payload["model_id"]),
                         (want["seat_no"], want["model_id"]))
        self.assertEqual(say[0].payload["verdict"], "accept")
        self.assertTrue(result.accepted)
        self.assertEqual(ctl.questions, [])
        self.assertTrue(result.files_written)
        finals = [s for ph, _, _, s in tap.calls if ph == "final"]
        self.assertEqual(len(finals), 1)
        self.assertIn("one caveat is missing", finals[0].messages[-1]["content"])  # the record

    async def test_random_seat_can_discard(self):
        run_id, result, ctl, _ = await self._build(lambda phase, seat, cycle: FIX)
        say = self.rig.events(run_id, ET.REVIEW_FINAL_SAY)
        self.assertEqual(say[0].payload["verdict"], "fix")
        self.assertFalse(result.accepted)
        self.assertEqual(result.files_written, [])
        self.assertEqual(ctl.questions, [])
        self.assertEqual(ctl.states[-1], RunState.DONE)

    async def test_failed_deciding_call_keeps_the_work(self):
        def script(phase, seat, cycle):
            return "not a ballot" if phase == "final" else FIX

        run_id, result, _, _ = await self._build(script)
        say = self.rig.events(run_id, ET.REVIEW_FINAL_SAY)
        self.assertEqual(say[0].payload["verdict"], "accept")
        self.assertTrue(result.accepted)

    async def test_time_limit_skips_the_fix_cycles(self):
        def script(phase, seat, cycle):
            return ACCEPT if phase == "final" else FIX

        run_id, result, ctl, _ = await self._build(script, deadline_s=1e-9)
        rig = self.rig
        verdicts = rig.events(run_id, ET.REVIEW_VERDICT)
        self.assertEqual(len(verdicts), 1)
        self.assertIn("time limit", verdicts[0].payload["reason"])
        self.assertEqual(len(rig.events(run_id, ET.REVIEW_FINAL_SAY)), 1)
        self.assertEqual(ctl.states.count(RunState.REVIEWING), 1)
        self.assertTrue(result.accepted)

    async def test_final_say_user_asks_the_user(self):
        ctl = FakeControl(answer="discard")
        run_id, result, ctl, tap = await self._build(lambda phase, seat, cycle: FIX, ctl, final_say="user")
        self.assertEqual(self.rig.events(run_id, ET.REVIEW_FINAL_SAY), [])
        self.assertEqual(len(ctl.questions), 1)
        self.assertEqual(ctl.questions[0].options, ["accept", "discard"])
        self.assertFalse(result.accepted)
        self.assertNotIn("final", {ph for ph, *_ in tap.calls})
        last = self.rig.events(run_id, ET.REVIEW_VERDICT)[-1].payload
        self.assertEqual(last["next_state"], RunState.AWAITING_USER.value)

    async def test_ask_user_vote_unattended_goes_to_the_random_seat(self):
        def script(phase, seat, cycle):
            return ACCEPT if phase == "final" else ASK

        run_id, result, ctl, _ = await self._build(script)
        self.assertEqual(len(self.rig.events(run_id, ET.REVIEW_FINAL_SAY)), 1)
        self.assertEqual(ctl.questions, [])
        self.assertTrue(result.accepted)


if __name__ == "__main__":
    unittest.main()
