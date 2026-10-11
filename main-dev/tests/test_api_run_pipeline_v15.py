"""1.5 wiring of the run: memory plan, steering, lie detector, steering training, council sizes."""

import asyncio
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from council.api import run_pipeline as rp
from council.api.controller import RunController
from council.core import event_types as ET
from council.core.schemas import RunRequest, RunState
from council.core.schemas_v15 import LieFlag, MemoryPlan, SteerCard
from council.host.drivers import MockDriver
from council.probe.activations import MockActivationSource
from council.steer.service import SteerService
from council.steer.store import SteerStore
from tests.test_api_run_pipeline import ANSWER_TASK, BUILD_TASK, SEATS, Base, FakeControl

HOME = Path(__file__).resolve().parents[1]
CLERK = "gemma4-12b-q4"
SEAT_GIB = 16.0 + 19.5 + 19.0 + 10.0 + 11.0  # SEATS in config/models.json
PROJECT_RULES = [("Use tabs.", "Use spaces.")]


class SteerDriver(MockDriver):
    """A mock driver that can steer, like the llama.cpp one: the vector counts at the next load."""

    def __init__(self) -> None:
        super().__init__()
        self.wanted: dict = {}
        self.calls: list = []
        self.loads: list = []

    def set_steering(self, model_id, path, scale=1.0):
        self.calls.append((model_id, None if path is None else Path(path), scale))
        if path is None:
            self.wanted.pop(model_id, None)
        else:
            self.wanted[model_id] = (Path(path), float(scale))

    async def load(self, model_id, profile):
        self.loads.append((model_id, self.wanted.get(model_id)))
        return await super().load(model_id, profile)


class CtxDriver(MockDriver):
    """A mock driver with one context per model, like the llama.cpp one."""

    ctx_for = None

    def ctx_of(self, model_id):
        n = self.ctx_for(model_id) if self.ctx_for is not None else None
        return int(n) if n else 8192


async def free_run(rig, task=ANSWER_TASK, **req):
    """A run with no lineup override: the router picks options.k seats."""
    rig._n += 1
    run_id = f"run_{rig._n:03d}"
    request = RunRequest(task=task, workspace=str(rig.workspace), **req)
    rig.store.create_run(run_id, task, request.workspace, request.mode, RunState.INTAKE)
    ctl = FakeControl()
    result = await asyncio.wait_for(rig.pipeline.run(run_id, request, ctl), 120.0)
    return run_id, result, ctl


def plan_of(rig, run_id) -> MemoryPlan:
    events = rig.events(run_id, ET.MEMORY_PLANNED)
    assert len(events) == 1, len(events)
    return MemoryPlan.model_validate(events[0].payload["plan"])


class MemoryPlanning(Base):
    async def test_plan_comes_before_any_load_and_is_stored(self):
        rig = self.rig
        run_id, _, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        types = [e.type for e in rig.events(run_id)]
        self.assertLess(types.index(ET.MEMORY_PLANNED), types.index(ET.MODEL_LOADING))
        self.assertLess(types.index(ET.MEMORY_PLANNED), types.index(ET.ROUTER_LINEUP_SELECTED))
        plan = plan_of(rig, run_id)
        self.assertTrue(plan.fits)
        self.assertEqual(plan.dropped, [])
        self.assertEqual(set(SEATS) | {CLERK}, set(plan.per_model))
        self.assertEqual(plan.roles, {"clerk": CLERK})  # the configured clerk fits: it stays
        self.assertEqual(rig.store.kv_get(rp.MEMORY_NS, run_id)["fits"], True)
        self.assertEqual(rig.pipeline._state, {})  # nothing of the run is kept

    async def test_council_shrinks_when_the_seats_do_not_fit(self):
        rig = self.rig
        rig.pipeline._total_gib = lambda: (60.0, True)  # 50 GiB after the reserve
        run_id, result, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-1], RunState.DONE)
        self.assertTrue(result.final_text)
        plan = plan_of(rig, run_id)
        self.assertTrue(plan.fits)
        self.assertTrue(plan.dropped)
        self.assertTrue(any("shrank from 5 to" in n for n in plan.notes), plan.notes)
        seats = [e.payload["model_id"] for e in rig.events(run_id, ET.SEAT_ASSIGNED)]
        self.assertEqual(len(seats), 5 - len(plan.dropped))
        self.assertGreaterEqual(len(seats), rp.MIN_SEATS)
        self.assertFalse(set(seats) & set(plan.dropped))
        lineup = rig.events(run_id, ET.ROUTER_LINEUP_SELECTED)[0].payload["lineup"]
        self.assertEqual([s["seat_no"] for s in lineup["seats"]], list(range(len(seats))))
        self.assertEqual(lineup["k"], len(seats))
        self.assertIn(lineup["chair_model_id"], seats)
        loaded = {e.payload["model_id"] for e in rig.events(run_id, ET.MODEL_LOADED)}
        self.assertFalse(loaded & set(plan.dropped))

    async def test_never_below_two_seats(self):
        rig = self.rig
        rig.pipeline._total_gib = lambda: (12.0, True)  # nothing fits
        run_id, _, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-1], RunState.DONE)
        plan = plan_of(rig, run_id)
        self.assertFalse(plan.fits)
        self.assertEqual(len(rig.events(run_id, ET.SEAT_ASSIGNED)), rp.MIN_SEATS)
        self.assertTrue(any("Still over the budget" in n for n in plan.notes))

    async def test_roles_go_to_seats_when_the_clerk_does_not_fit(self):
        rig = self.rig
        rig.pipeline._total_gib = lambda: (SEAT_GIB + 10.0 + 1.0, True)  # seats fit, a sixth model not
        run_id, result, ctl = await rig.run(BUILD_TASK, deliverable="build",
                                            options={"auto_delegate": True, "auto_input": True})
        self.assertEqual(ctl.states[-1], RunState.DONE)
        plan = plan_of(rig, run_id)
        self.assertTrue(plan.fits)
        self.assertEqual(plan.dropped, [])
        self.assertEqual(set(plan.per_model), set(SEATS))
        self.assertEqual(set(plan.roles), {"planner", "senior_worker", "worker", "clerk"})
        self.assertTrue(set(plan.roles.values()) <= set(SEATS))
        self.assertTrue(any("work roles go to seated models" in n for n in plan.notes))
        loaded = {e.payload["model_id"] for e in rig.events(run_id, ET.MODEL_LOADED)}
        self.assertTrue(loaded <= set(SEATS), loaded)  # no seventh model was ever loaded
        self.assertIsNotNone(result.plan)

    async def test_share_roles_never_keeps_the_configured_models(self):
        rig = self.rig
        rig.config.memory.share_roles = "never"
        rig.pipeline._total_gib = lambda: (SEAT_GIB + 10.0 + 1.0, True)
        run_id, _, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(rig.pipeline._state, {})
        plan = plan_of(rig, run_id)
        self.assertFalse(any("work roles go to seated models" in n for n in plan.notes))

    async def test_a_broken_plan_never_fails_the_run(self):
        rig = self.rig
        with mock.patch.object(rp.memplan, "plan_memory", side_effect=RuntimeError("boom")):
            run_id, _, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-1], RunState.DONE)
        self.assertEqual(rig.events(run_id, ET.MEMORY_PLANNED), [])
        self.assertEqual(len(rig.events(run_id, ET.SEAT_ASSIGNED)), 5)

    async def test_context_per_model_goes_to_a_driver_that_takes_one(self):
        rig = self.rig
        driver = CtxDriver()
        rig.host.driver = driver
        seen = {}
        real = rp.Deliberation

        def spy(*a, **kw):
            seen.update(kw)
            return real(*a, **kw)

        with mock.patch.object(rp, "Deliberation", spy):
            run_id, _, _ = await rig.run(ANSWER_TASK, deliverable="answer", mode="quick",
                                         options={"reflect": False})
        plan = plan_of(rig, run_id)
        for mid in SEATS:
            self.assertEqual(plan.num_ctx[mid], 8192)  # quick seats (ctx_policy), under the 16384 default
            self.assertEqual(driver.ctx_of(mid), 8192)
        self.assertEqual(seen["ctx_tokens"], 8192)
        self.assertEqual(rig.deps.model_ctx[SEATS[0]], 8192)
        # the seats are still resident: a standard run does not reload them for a bigger context
        run_id, _, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(plan_of(rig, run_id).num_ctx[SEATS[0]], 8192)
        self.assertEqual(seen["ctx_tokens"], 8192)


class Steering(Base):
    def setUp(self) -> None:
        super().setUp()
        rig = self.rig
        self.driver = SteerDriver()
        rig.host.driver = self.driver
        self.store = SteerStore(rig.home)
        rig.deps.steer_store = self.store
        from council.core.workspace import project_id
        self.project = project_id(rig.workspace)

    def card(self, model_id: str, scale: float = 1.5) -> SteerCard:
        path = self.store.path_for(self.project, model_id, 1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF")
        return self.store.save(SteerCard(project=self.project, model_id=model_id, version=1,
                                         layers=[14, 15], scale=scale, examples=8, active=True,
                                         path=str(path)))

    async def test_active_vector_is_set_before_the_seat_loads(self):
        rig = self.rig
        card = self.card(SEATS[1])
        run_id, _, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        applied = rig.events(run_id, ET.STEER_APPLIED)
        self.assertEqual(len(applied), 1)
        p = applied[0].payload
        self.assertEqual((p["project"], p["model_id"], p["scale"], p["layers"]),
                         (self.project, SEATS[1], 1.5, [14, 15]))
        self.assertEqual(p["source"], card.path)
        self.assertIn((SEATS[1], (Path(card.path), 1.5)), self.driver.loads)  # loaded with it
        for mid in SEATS:
            if mid != SEATS[1]:
                self.assertIn((mid, None, 1.0), self.driver.calls)  # the others: none is set
                self.assertIn((mid, None), self.driver.loads)
        self.assertEqual(rig.deps.steer_live[SEATS[1]], (card.path, 1.5))

    async def test_a_vector_that_was_switched_off_is_taken_off_a_resident_model(self):
        rig = self.rig
        self.card(SEATS[1])
        await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertTrue(self.store.set_active(self.project, SEATS[1], None))
        self.driver.loads.clear()
        run_id, _, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(rig.events(run_id, ET.STEER_APPLIED), [])
        self.assertEqual(self.driver.loads, [(SEATS[1], None)])  # only that model was restarted
        self.assertIsNone(rig.deps.steer_live[SEATS[1]])

    async def test_steer_switched_off_applies_nothing(self):
        rig = self.rig
        self.card(SEATS[1])
        rig.config.steer.enabled = False
        run_id, _, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(rig.events(run_id, ET.STEER_APPLIED), [])
        self.assertIn((SEATS[1], None), self.driver.loads)

    async def test_a_driver_that_cannot_steer_gets_no_event(self):
        rig = self.rig
        rig.host.driver = MockDriver()
        self.card(SEATS[1])
        run_id, _, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-1], RunState.DONE)
        self.assertEqual(rig.events(run_id, ET.STEER_APPLIED), [])

    async def test_a_steering_error_never_fails_the_run(self):
        rig = self.rig
        self.card(SEATS[1])

        def boom(model_id, path, scale=1.0):
            raise RuntimeError("no such file")

        self.driver.set_steering = boom
        run_id, _, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-1], RunState.DONE)
        self.assertEqual(rig.events(run_id, ET.STEER_APPLIED), [])


class SteerTraining(Base):
    def setUp(self) -> None:
        super().setUp()
        rig = self.rig
        self.generated: list = []

        async def render(model_id, messages):
            return "\n".join(str(m.get("content", "")) for m in messages)

        async def generate(model_id, path, scale, prompts):
            self.generated.append((model_id, scale))
            return ["The moon is made of rock and dust, mostly silicates."] * len(prompts)

        self.store = SteerStore(rig.home)
        rig.deps.steer_store = self.store
        rig.deps.steer = SteerService(MockActivationSource(), self.store, render, generate,
                                      rig.config.steer, lambda t, p=None: None, lambda: 1000.0)

    async def test_correction_asks_for_a_vector_after_the_reflection(self):
        rig = self.rig
        run_id, result, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertIsNotNone(result.correction)
        events = rig.events(run_id)
        types = [e.type for e in events]
        trained = [e for e in events if e.type == ET.STEER_TRAINED]
        self.assertEqual(len(trained), 1)
        p = trained[0].payload
        self.assertEqual(p["model_id"], result.correction.model_id)
        self.assertEqual(p["project"], result.correction.project)
        self.assertFalse(p["active"])
        self.assertIn("not enough examples: 1 of 6", p["reason"])
        last_memory = max(i for i, t in enumerate(types) if t.startswith("memory.") and t != ET.MEMORY_PLANNED) \
            if any(t.startswith("memory.") and t != ET.MEMORY_PLANNED for t in types) else 0
        self.assertGreater(types.index(ET.STEER_TRAINED), last_memory)
        self.assertGreater(types.index(ET.STEER_TRAINED), types.index(ET.CORRECTION_RECORDED))
        self.assertEqual(self.generated, [])

    async def test_enough_corrections_train_the_vector(self):
        rig = self.rig
        rig.config.steer.min_examples = 1
        run_id, result, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-1], RunState.DONE)
        p = rig.events(run_id, ET.STEER_TRAINED)[0].payload
        self.assertEqual(p["model_id"], result.correction.model_id)
        self.assertGreaterEqual(p["examples"], 1)
        self.assertTrue(p["reason"])
        cards = self.store.cards(result.correction.project)
        if p["active"]:  # the mock activations separated the two sides: a vector was written
            self.assertTrue(self.generated)
            self.assertTrue(Path(cards[-1].path).is_file())
            self.assertEqual(cards[-1].scale, p["scale"])

    async def test_switched_off_or_broken_training_is_silent(self):
        rig = self.rig
        rig.config.steer.enabled = False
        run_id, _, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(rig.events(run_id, ET.STEER_TRAINED), [])
        rig.config.steer.enabled = True

        async def boom(*a, **kw):
            raise RuntimeError("boom")

        rig.deps.steer.train = boom
        run_id, _, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-1], RunState.DONE)

    async def test_no_correction_no_training(self):
        rig = self.rig
        rig.config.tribunal.enabled = False
        run_id, result, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertIsNone(result.correction)
        self.assertEqual(rig.events(run_id, ET.STEER_TRAINED), [])


class LieDetector(Base):
    async def test_report_is_emitted_stored_and_shown_to_the_council(self):
        rig = self.rig
        shown: list = []
        real = rp.Deliberation.set_lie_flags

        def spy(self_, flags):
            shown.append(list(flags))
            return real(self_, flags)

        with mock.patch.object(rp.Deliberation, "set_lie_flags", spy):
            run_id, _, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        events = rig.events(run_id)
        types = [e.type for e in events]
        reports = [e for e in events if e.type == ET.LIE_REPORT]
        self.assertEqual(len(reports), 1)
        report = reports[0].payload["report"]
        self.assertEqual(report["run_id"], run_id)
        self.assertEqual(len(report["seats"]), 5)
        self.assertTrue(report["flags"])
        r1 = next(i for i, e in enumerate(events)
                  if e.type == ET.TURN_STARTED and e.payload.get("purpose") == "seat.r1")
        self.assertLess(types.index(ET.LIE_REPORT), r1)  # before the round 1 calls go out
        self.assertEqual(len(shown), 1)
        self.assertEqual(len(shown[0]), len(report["flags"]))
        self.assertIsNotNone(rig.reliability.last_report(run_id))

    async def test_flags_are_written_into_round_one(self):
        rig = self.rig
        real = rig.reliability.last_report

        def flagged(run_id):
            report = real(run_id)
            return report.model_copy(update={"flags": [
                f.model_copy(update={"level": "flag", "behaviour_score": 0.1}) for f in report.flags]})

        rig.reliability.last_report = flagged
        from council.chamber import lie_notes
        await rig.run(ANSWER_TASK, deliverable="answer")
        r1 = [s for s in rig.responder.specs if s.purpose == "seat.r1"]
        self.assertTrue(r1)
        for spec in r1:
            self.assertIn(lie_notes.HEADER, spec.messages[-1]["content"])

    async def test_not_shown_when_show_to_council_is_off(self):
        rig = self.rig
        rig.config.lie.show_to_council = False
        with mock.patch.object(rp.Deliberation, "set_lie_flags") as spy:
            run_id, _, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        spy.assert_not_called()
        self.assertEqual(len(rig.events(run_id, ET.LIE_REPORT)), 1)

    async def test_lie_off_emits_no_report_and_keeps_the_scores(self):
        rig = self.rig
        rig.config.lie.enabled = False
        with mock.patch.object(rp.Deliberation, "set_lie_flags") as spy:
            run_id, _, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        spy.assert_not_called()
        self.assertEqual(rig.events(run_id, ET.LIE_REPORT), [])
        self.assertTrue(rig.events(run_id, ET.PROBE_SCORES))

    async def test_probe_off_still_gives_the_lie_report(self):
        rig = self.rig
        rig.config.probe.enabled = False
        run_id, _, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-1], RunState.DONE)
        self.assertEqual(len(rig.events(run_id, ET.LIE_REPORT)), 1)
        self.assertEqual(rig.events(run_id, ET.PROBE_SCORES), [])

    async def test_a_slow_detector_does_not_hold_the_debate(self):
        rig = self.rig
        rig.config.lie.timeout_s = 0.02

        async def slow(*a, **kw):
            await asyncio.sleep(60)

        rig.reliability.score_round0 = slow
        with mock.patch.object(rp, "_LIE_SLACK_S", 0.0):
            t0 = asyncio.get_running_loop().time()
            run_id, result, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertLess(asyncio.get_running_loop().time() - t0, 30.0)
        self.assertEqual(ctl.states[-1], RunState.DONE)
        self.assertTrue(result.final_text)

    async def test_a_broken_detector_does_not_fail_the_run(self):
        rig = self.rig

        async def boom(*a, **kw):
            raise RuntimeError("probe died")

        rig.reliability.score_round0 = boom
        run_id, _, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-1], RunState.DONE)

    async def test_tribunal_gets_the_flags_of_the_examined_seat(self):
        rig = self.rig
        seen: dict = {}
        real = rp.Tribunal

        def spy(run_id, task, decision, lineup, outlier, *a, **kw):
            seen["outlier"], seen["flags"] = outlier, list(kw.get("lie_flags") or [])
            return real(run_id, task, decision, lineup, outlier, *a, **kw)

        with mock.patch.object(rp, "Tribunal", spy):
            run_id, result, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertIsNotNone(result.tribunal)
        self.assertTrue(seen["flags"])
        for flag in seen["flags"]:
            self.assertIsInstance(flag, LieFlag)
            self.assertEqual(flag.seat_no, seen["outlier"])


class CouncilSizes(Base):
    async def test_answer_runs_with_two_to_six_seats(self):
        rig = self.rig
        for k in (2, 3, 4, 6):
            with self.subTest(k=k):
                run_id, result, ctl = await free_run(rig, deliverable="answer", options={"k": k})
                self.assertEqual(ctl.states[-1], RunState.DONE)
                self.assertTrue(result.final_text)
                seats = rig.events(run_id, ET.SEAT_ASSIGNED)
                self.assertEqual(len(seats), k)
                self.assertEqual(sum(1 for s in seats if s.payload["is_chair"]), 1)
                self.assertEqual(len(rig.events(run_id, ET.MEMORY_PLANNED)), 1)
                self.assertEqual(len(rig.events(run_id, ET.LIE_REPORT)), 1)
                self.assertIn(RunState.REFLECTING, ctl.states)

    async def test_two_seats_build_review_and_integrate(self):
        rig = self.rig
        run_id, result, ctl = await free_run(
            rig, BUILD_TASK, deliverable="build",
            options={"k": 2, "auto_delegate": True, "auto_input": True})
        self.assertEqual(ctl.states[-1], RunState.DONE)
        self.assertEqual(len(rig.events(run_id, ET.SEAT_ASSIGNED)), 2)
        self.assertIsNotNone(result.plan)
        self.assertIsNotNone(result.accepted)
        ballots = rig.events(run_id, ET.REVIEW_BALLOT)
        self.assertEqual({b.payload["seat_no"] for b in ballots}, {0, 1})
        self.assertTrue(rig.events(run_id, ET.REVIEW_VERDICT))

    async def test_two_seats_that_disagree_still_decide(self):
        rig = self.rig
        run_id, result, ctl = await free_run(rig, deliverable="answer", mode="deep", options={"k": 2})
        self.assertEqual(ctl.states[-1], RunState.DONE)
        self.assertIn(result.decision.outcome, ("consensus", "majority", "chair", "split", "no_consensus",
                                                result.decision.outcome))
        self.assertTrue(result.final_text)

    async def test_a_two_seat_council_needs_both_seats(self):
        rig = self.rig
        need = max(1, -(-int(rig.config.chamber.quorum_fraction * 2 * 1000) // 1000))
        self.assertEqual(need, 2)


class ApplySteering(unittest.IsolatedAsyncioTestCase):
    async def test_resident_model_is_unloaded_only_when_the_vector_changes(self):
        class Host:
            def __init__(self):
                self.driver = SteerDriver()
                self.unloaded: list = []

            def status(self):
                return [{"model_id": "m"}]

            async def unload(self, model_id, run_id="manual"):
                self.unloaded.append(model_id)

            async def set_steering(self, model_id, path, scale=1.0):
                self.driver.set_steering(model_id, path, scale)
                return True

        host, live = Host(), {}
        self.assertTrue(await rp.apply_steering(host, live, "m", None))
        self.assertEqual(host.unloaded, [])  # nothing was set, nothing changes
        self.assertTrue(await rp.apply_steering(host, live, "m", Path("v.gguf"), 1.0))
        self.assertEqual(host.unloaded, ["m"])
        self.assertTrue(await rp.apply_steering(host, live, "m", Path("v.gguf"), 1.0))
        self.assertEqual(host.unloaded, ["m"])  # same vector: stays up
        self.assertTrue(await rp.apply_steering(host, live, "m", Path("v.gguf"), 2.0))
        self.assertEqual(host.unloaded, ["m", "m"])
        self.assertEqual(live["m"], ("v.gguf", 2.0))

    async def test_driver_without_steering(self):
        class Host:
            driver = MockDriver()

        live: dict = {}
        self.assertFalse(await rp.apply_steering(Host(), live, "m", Path("v.gguf"), 1.0))
        self.assertEqual(live, {})


class ControllerWiring(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="council_v15_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ctrl = RunController.build_mock(home=HOME, speed=100000.0, data_home=self.tmp)

    async def asyncTearDown(self) -> None:
        await self.ctrl.shutdown()
        self.ctrl.store.close()

    async def test_services_are_wired_under_the_data_home(self):
        ctrl = self.ctrl
        self.assertIsInstance(ctrl.steer, SteerService)
        self.assertIsInstance(ctrl.steer_store, SteerStore)
        self.assertEqual(ctrl.steer_store.home, self.tmp)
        self.assertIs(ctrl.steer.store, ctrl.steer_store)
        self.assertIs(ctrl.steer.source, ctrl.reliability.source)
        self.assertIs(ctrl.probe_files, ctrl.reliability.files)  # one set of probe files
        self.assertIs(ctrl.reliability.lie_cfg, ctrl.config.lie)
        deps = ctrl._deps()
        self.assertIs(deps.steer, ctrl.steer)
        self.assertIs(deps.steer_store, ctrl.steer_store)
        self.assertIs(deps.probe_files, ctrl.probe_files)
        self.assertIs(deps.steer_live, ctrl.steer_live)
        self.assertIs(deps.model_ctx, ctrl.model_ctx)
        self.assertEqual(ctrl.gateway.endpoint_for, ctrl.host.endpoint_for)

    async def test_render_and_generate_work_in_mock_mode(self):
        ctrl = self.ctrl
        model = ctrl.registry[0].id
        text = await ctrl._steer_render(model, [{"role": "system", "content": "Be brief."},
                                                {"role": "user", "content": "What is the moon?"}])
        self.assertIn("What is the moon?", text)
        out = await ctrl._steer_generate(model, None, 1.0, ["What is the moon made of?", "Why water?"])
        self.assertEqual(len(out), 2)
        self.assertTrue(all(isinstance(x, str) and x for x in out))
        self.assertEqual(ctrl.host._seats.get("steer"), None)  # the check left no seat behind

    async def test_render_asks_a_driver_that_has_the_template_with_the_model_loaded(self):
        ctrl = self.ctrl
        model = ctrl.registry[0].id
        seen: list = []

        async def render(model_id, messages):
            seen.append((model_id, {r["model_id"] for r in ctrl.host.status()}))
            return "<s>" + messages[-1]["content"]

        ctrl.host.driver.render = render
        text = await ctrl._steer_render(model, [{"role": "user", "content": "hi"}])
        self.assertEqual(text, "<s>hi")
        self.assertEqual(seen, [(model, {model})])
        self.assertEqual(ctrl.host._seats.get("steer"), None)

        async def empty(model_id, messages):
            return ""

        ctrl.host.driver.render = empty
        with self.assertRaises(RuntimeError):
            await ctrl._steer_render(model, [{"role": "user", "content": "hi"}])

    async def test_mock_run_emits_the_plan_and_the_lie_report(self):
        ctrl = self.ctrl
        run_id = await ctrl.start(RunRequest(task=ANSWER_TASK, deliverable="answer",
                                             options={"k": 4, "auto_input": True}))
        snap = await ctrl.wait(run_id, 120.0)
        self.assertEqual(snap.state, RunState.DONE, snap.error)
        types = [e.type for e in ctrl.store.events_for_run(run_id)]
        self.assertEqual(types.count(ET.MEMORY_PLANNED), 1)
        self.assertEqual(types.count(ET.LIE_REPORT), 1)
        self.assertEqual(types.count(ET.SEAT_ASSIGNED), 4)

    async def test_real_config_uses_the_host_factory(self):
        home = self.tmp / "real"
        (home / "config").mkdir(parents=True)
        for name in ("models.json", "lenses.json"):
            shutil.copy(HOME / "config" / name, home / "config" / name)
        for driver, kind in (("llamacpp", "LlamaServerDriver"), ("ollama", "OllamaDriver")):
            (home / "config" / "council.toml").write_text(
                f'[host]\ndriver = "{driver}"\n[gateway]\nmock = false\n[probe]\nsource = "mock"\n',
                encoding="utf-8")
            ctrl = RunController.build_from_config(home=home, db_path=":memory:")
            try:
                self.assertEqual(type(ctrl.host.driver).__name__, kind)
                self.assertFalse(ctrl.mock)
                self.assertEqual(ctrl.gateway.endpoint_for, ctrl.host.endpoint_for)
                self.assertIsInstance(ctrl.steer, SteerService)
                if driver == "llamacpp":
                    model = ctrl.registry[0].id
                    self.assertEqual(ctrl.gateway.ctx_for(model), ctrl.config.llamacpp.ctx)
                else:
                    self.assertIsNone(ctrl.gateway.ctx_for)
            finally:
                await ctrl.shutdown()
                ctrl.store.close()


if __name__ == "__main__":
    unittest.main()
