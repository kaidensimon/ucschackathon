import asyncio
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from council.api import controller as controller_mod
from council.api.controller import (
    NEXT_PHASE_NOTE,
    InvalidState,
    PlanRejected,
    RunController,
    RunNotFound,
    fold,
)
from council.api.run_pipeline import RunResult
from council.chronicle.corrections import CorrectionBook
from council.chronicle.reflect import Reflector
from council.chronicle.service import Chronicle
from council.core import event_types as ET
from council.core.schemas import (
    BenchRunRequest,
    ClaimScore,
    Correction,
    Decision,
    Event,
    LineupRecord,
    Plan,
    RunRequest,
    RunSnapshot,
    RunState,
    TribunalOutcome,
    UserInput,
    UserQuestion,
)
from council.probe.service import ReliabilityService

HOME = Path(__file__).resolve().parents[1]
SPEED = 100000.0
TIMEOUT = 60.0
SMALL = ["granite-next-8b", "glm-small", "ministral-mid"]  # seats that leave room for the workers


def build() -> RunController:
    return RunController.build_mock(home=HOME, speed=SPEED)


async def close(ctrl: RunController) -> None:
    await ctrl.shutdown()
    ctrl.store.close()


async def collect(ctrl: RunController, run_id: str, on_event=None) -> list:
    """Every event of the run up to its terminal event. Answers user questions on the way."""
    out = []

    async def pump() -> None:
        async for ev in ctrl.bus.subscribe(run_id, 0):
            out.append(ev)
            if ev.type == ET.USER_INPUT_REQUESTED and ctrl.is_active(run_id):
                try:
                    await ctrl.submit_input(run_id, UserInput(
                        request_id=ev.payload.get("request_id") or "", choice="go"))
                except InvalidState:
                    pass  # the demo script answers its own question
            if on_event is not None:
                await on_event(ev)

    await asyncio.wait_for(pump(), TIMEOUT)
    return out


def types(events: list) -> list:
    return [e.type for e in events]


def states(events: list) -> list:
    return [e.payload["to_state"] for e in events if e.type == ET.RUN_STATE_CHANGED]


class DemoRun(unittest.IsolatedAsyncioTestCase):
    async def test_demo_waits_for_delegate_then_completes(self):
        ctrl = build()
        run_id = await ctrl.start(RunRequest(task="Design a rate limiter", options={"demo": True}))
        seen_wait = []

        async def on_event(ev):
            if ev.type == ET.RUN_STATE_CHANGED and ev.payload["to_state"] == "AWAITING_DELEGATION":
                # give the player time to prove it really stops at the marker
                for _ in range(20):
                    await asyncio.sleep(0.005)
                snap = ctrl.snapshot(run_id)
                seen_wait.append(snap.state)
                self.assertIsNotNone(snap.plan)
                self.assertIsNotNone(snap.decision)
                self.assertTrue(ctrl.is_active(run_id))
                self.assertTrue(await ctrl.delegate(run_id))

        events = await collect(ctrl, run_id, on_event)
        await ctrl.wait(run_id, TIMEOUT)
        self.assertEqual(seen_wait, [RunState.AWAITING_DELEGATION])
        self.assertEqual(events[0].type, ET.RUN_CREATED)
        self.assertEqual(types(events).count(ET.RUN_CREATED), 1)
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED)
        got = states(events)
        self.assertLess(got.index("AWAITING_DELEGATION"), got.index("EXECUTING"))
        self.assertEqual(got[-1], "DONE")
        for ev in events:
            if ev.type == ET.RUN_STATE_CHANGED and ev.payload["phase_ms"] is not None:
                self.assertGreaterEqual(ev.payload["phase_ms"], 0)

        snap = ctrl.snapshot(run_id)
        self.assertEqual(snap.state, RunState.DONE)
        self.assertEqual(snap.deliverable, "plan")
        self.assertIsNotNone(snap.lineup)
        self.assertTrue(snap.task_statuses)
        self.assertEqual(snap.counters.tasks_total, len(snap.task_statuses))
        self.assertGreater(snap.counters.tasks_passed, 0)
        self.assertIsNone(snap.pending_input)
        self.assertEqual(ctrl.store.get_run(run_id)["state"], "DONE")
        self.assertFalse(ctrl.is_active(run_id))
        with self.assertRaises(InvalidState):
            await ctrl.delegate(run_id)
        await close(ctrl)

    async def test_demo_auto_delegate(self):
        ctrl = build()
        run_id = await ctrl.start(RunRequest(
            task="Design a rate limiter", options={"demo": True, "auto_delegate": True}))
        events = await collect(ctrl, run_id)
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED)
        self.assertEqual(ctrl.snapshot(run_id).state, RunState.DONE)
        await close(ctrl)

    async def test_delegate_too_early_is_refused(self):
        ctrl = build()
        run_id = await ctrl.start(RunRequest(task="x", options={"demo": True}))
        with self.assertRaises(InvalidState):
            await ctrl.delegate(run_id)
        with self.assertRaises(RunNotFound):
            await ctrl.delegate("run_nope")
        self.assertTrue(await ctrl.cancel(run_id))
        await close(ctrl)


class RealRun(unittest.IsolatedAsyncioTestCase):
    async def test_answer_run_completes_with_decision(self):
        ctrl = build()
        ctrl.config.telemetry.tick_s = 0.01
        run_id = await ctrl.start(RunRequest(
            task="What is the capital of France? Answer briefly.", mode="standard",
            deliverable="answer"))
        events = await collect(ctrl, run_id)
        await ctrl.wait(run_id, TIMEOUT)
        got = types(events)
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
        self.assertEqual(got[0], ET.RUN_CREATED)
        for needed in (ET.PROFILE_READY, ET.BRIEF_READY, ET.RECALL_READY,
                       ET.ROUTER_CANDIDATES_SCORED, ET.ROUTER_LINEUP_SELECTED, ET.MODEL_LOADED,
                       ET.SEAT_ASSIGNED, ET.ROUND_STARTED, ET.TURN_COMPLETED, ET.DECISION_FINAL,
                       ET.TELEMETRY_TICK):
            self.assertIn(needed, got)
        order = [s for s in states(events) if s not in ("AWAITING_USER", "EXAMINING")]
        order = [s for i, s in enumerate(order) if i == 0 or order[i - 1] != s]
        self.assertEqual(
            order, ["INTAKE", "PROFILING", "CONVENING", "DELIBERATING", "DECIDED", "REFLECTING",
                    "DONE"])
        self.assertEqual(got.count(ET.RUN_COMPLETED), 1)
        self.assertLess(got.index(ET.ROUTER_LINEUP_SELECTED), got.index(ET.ROUND_STARTED))

        done = events[-1].payload
        self.assertIsNotNone(done["decision"])
        self.assertTrue(done["final_text"])
        self.assertNotIn(NEXT_PHASE_NOTE, done["final_text"])
        self.assertGreater(done["counters"]["calls"], 0)

        snap = ctrl.snapshot(run_id)
        self.assertEqual(snap.state, RunState.DONE)
        self.assertEqual(snap.decision.outcome, done["decision"]["outcome"])
        self.assertEqual(snap.lineup.k, len(snap.lineup.seats))
        self.assertEqual(got.count(ET.SEAT_ASSIGNED), snap.lineup.k)
        self.assertEqual(snap.deliverable, "answer")
        self.assertIsNotNone(ctrl.store.get_json("decisions", run_id))
        self.assertIsNotNone(ctrl.store.get_json("lineups", run_id))
        row = ctrl.store.get_run(run_id)
        self.assertEqual(row["state"], "DONE")
        self.assertEqual(row["outcome"], snap.decision.outcome)
        self.assertEqual(ctrl.host._seats, {})
        await close(ctrl)

    async def test_snapshot_is_consistent_with_events(self):
        ctrl = build()
        run_id = await ctrl.start(RunRequest(task="Compare quicksort and mergesort.", mode="quick"))
        events = await collect(ctrl, run_id)
        await ctrl.wait(run_id, TIMEOUT)
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
        snap = ctrl.snapshot(run_id)
        stored = [e for e in events if e.type not in ET.EPHEMERAL_EVENTS]
        self.assertEqual(snap.last_seq, stored[-1].seq)
        self.assertEqual(snap.run_id, run_id)
        self.assertEqual(snap.mode, "quick")
        self.assertEqual(snap.task, "Compare quicksort and mergesort.")
        turns_ok = [e for e in events if e.type == ET.TURN_COMPLETED]
        turns_bad = [e for e in events if e.type in (ET.TURN_INVALID, ET.TURN_TIMEOUT)]
        self.assertEqual(snap.counters.calls, len(turns_ok) + len(turns_bad))
        self.assertEqual(snap.counters.calls_failed, len(turns_bad))
        self.assertEqual(snap.counters.tokens_out, sum(e.payload["tokens_out"] for e in turns_ok))
        self.assertEqual(snap.counters.model_dump(), events[-1].payload["counters"] | {
            "wall_ms": snap.counters.wall_ms})
        lineup = next(e for e in events if e.type == ET.ROUTER_LINEUP_SELECTED).payload["lineup"]
        self.assertEqual(snap.lineup.model_dump(mode="json"), lineup)
        self.assertEqual(snap.lineup.k, 3)
        final = next(e for e in events if e.type == ET.DECISION_FINAL).payload
        self.assertEqual(snap.decision.option_id, final["decision"]["option_id"])
        self.assertEqual(snap.tally, final["decision"]["tally"] or snap.tally)
        self.assertEqual([o.id for o in snap.options], [o["id"] for o in final["options"]])
        self.assertIn("DELIBERATING", snap.counters.phase_ms)
        self.assertGreaterEqual(snap.counters.wall_ms, 0)
        self.assertIsNotNone(snap.finished_at)
        # persisted copy equals a fresh fold
        self.assertEqual(ctrl.store.get_run(run_id)["snapshot"], snap.model_dump(mode="json"))
        self.assertEqual(ctrl.snapshot(run_id), snap)
        with self.assertRaises(RunNotFound):
            ctrl.snapshot("run_nope")
        await close(ctrl)

    async def test_build_with_the_routed_lineup_fits_the_ram_budget(self):
        """Full five-seat lineup plus the senior worker is more than the box holds at once:
        the seats must go idle (and be evicted) while the workers build, then come back."""
        ctrl = build()
        tmp = Path(tempfile.mkdtemp(prefix="council-test-"))
        try:
            run_id = await ctrl.start(RunRequest(
                task="Build a small rate limiter package", deliverable="build", workspace=str(tmp),
                options={"auto_delegate": True}))
            events = await collect(ctrl, run_id)
            await ctrl.wait(run_id, TIMEOUT)
            self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
            types = [e.type for e in events]
            seats = {e.payload["model_id"] for e in events if e.type == ET.SEAT_ASSIGNED}
            self.assertEqual(len(seats), ctrl.config.router.k)
            evicted = {e.payload["model_id"] for e in events if e.type == ET.MODEL_EVICTED}
            self.assertTrue(evicted & seats)  # room was made for the workers
            review = types.index(ET.REVIEW_STARTED)
            resident: set[str] = set()
            for e in events[:review]:
                if e.type == ET.MODEL_LOADED:
                    resident.add(e.payload["model_id"])
                elif e.type == ET.MODEL_UNLOADED:
                    resident.discard(e.payload["model_id"])
            self.assertTrue(seats <= resident)  # every seat is back before it reviews
            self.assertTrue((tmp / "ratelimiter" / "__init__.py").is_file())
            self.assertEqual(ctrl.host._seats, {})
        finally:
            await close(ctrl)
            shutil.rmtree(tmp, ignore_errors=True)

    async def test_plan_run_waits_for_delegate_then_builds(self):
        ctrl = build()
        run_id = await ctrl.start(RunRequest(
            task="Plan a small CLI todo app.", mode="quick", deliverable="plan",
            lineup_override=SMALL, options={"seed": 3}))
        seen = []

        async def on_event(ev):
            if ev.type == ET.RUN_STATE_CHANGED and ev.payload["to_state"] == "AWAITING_DELEGATION":
                for _ in range(10):
                    await asyncio.sleep(0.005)
                snap = ctrl.snapshot(run_id)
                seen.append(snap.state)
                self.assertIsNotNone(snap.plan)
                self.assertTrue(await ctrl.delegate(run_id))

        events = await collect(ctrl, run_id, on_event)
        await ctrl.wait(run_id, TIMEOUT)
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
        self.assertEqual(seen, [RunState.AWAITING_DELEGATION])
        got = states(events)
        for a, b in zip(["DECIDED", "PLANNING", "AWAITING_DELEGATION", "EXECUTING", "REVIEWING"],
                        ["PLANNING", "AWAITING_DELEGATION", "EXECUTING", "REVIEWING", "REFLECTING"]):
            self.assertLess(got.index(a), got.index(b))
        self.assertEqual(got[-1], "DONE")
        self.assertNotIn(NEXT_PHASE_NOTE, events[-1].payload["final_text"])
        snap = ctrl.snapshot(run_id)
        self.assertEqual(snap.state, RunState.DONE)
        self.assertGreater(snap.counters.tasks_total, 0)
        self.assertEqual(snap.counters.tasks_total, len(snap.plan.tasks))
        self.assertIsNotNone(snap.work_report)
        self.assertGreater(events[-1].payload["counters"]["calls"], 0)
        self.assertEqual(ctrl.store.get_run(run_id)["snapshot"], snap.model_dump(mode="json"))
        self.assertEqual(ctrl.host._seats, {})
        await close(ctrl)

    async def test_plan_run_auto_delegate(self):
        ctrl = build()
        run_id = await ctrl.start(RunRequest(
            task="Plan a small CLI todo app.", mode="quick", deliverable="plan",
            lineup_override=SMALL, options={"seed": 3, "auto_delegate": True}))
        events = await collect(ctrl, run_id)
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
        self.assertIn("EXECUTING", states(events))
        await close(ctrl)

    async def test_lineup_override(self):
        ctrl = build()
        seats = [m.id for m in ctrl.registry if "seat" in m.roles][:3]
        run_id = await ctrl.start(RunRequest(task="2+2?", mode="quick", lineup_override=seats))
        events = await collect(ctrl, run_id)
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
        sel = next(e for e in events if e.type == ET.ROUTER_LINEUP_SELECTED).payload
        self.assertTrue(sel["overridden"])
        self.assertEqual([s["model_id"] for s in sel["lineup"]["seats"]], seats)
        await close(ctrl)

    async def test_model_that_cannot_load_is_replaced_and_listed_as_failed(self):
        ctrl = build()
        bad = SMALL[1]
        ctrl.host.driver.fail.add(bad)
        run_id = await ctrl.start(RunRequest(task="2+2?", mode="quick", lineup_override=list(SMALL)))
        events = await collect(ctrl, run_id)
        await ctrl.wait(run_id, TIMEOUT)
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
        gone = [e.payload for e in events if e.type == ET.MODEL_FAILED and e.payload.get("replaced_by")]
        self.assertEqual([p["model_id"] for p in gone], [bad])
        sub = gone[0]["replaced_by"]
        snap = ctrl.snapshot(run_id)
        self.assertEqual([s.model_id for s in snap.lineup.seats], [SMALL[0], sub, SMALL[2]])
        self.assertEqual(ctrl.store.get_json("lineups", run_id), snap.lineup.model_dump(mode="json"))
        swapped = [e.payload for e in events if e.type == ET.SEAT_ASSIGNED and e.payload["replaces_model_id"]]
        self.assertEqual([(p["seat_no"], p["model_id"], p["replaces_model_id"]) for p in swapped],
                         [(1, sub, bad)])
        # what GET /models lists (server: model_dump of every controller registry entry)
        self.assertEqual(list(ctrl.failed_models), [bad])
        rows = {m.id: m.model_dump(mode="json") for m in ctrl.registry}
        self.assertEqual(rows[bad]["status"], "failed")
        self.assertEqual(rows[SMALL[0]]["status"], "active")
        self.assertNotIn(bad, [s.model_id for s in ctrl.router_preview("2+2?", "standard").seats])
        again = await ctrl.start(RunRequest(task="3+3?", mode="quick"))
        more = await collect(ctrl, again)
        self.assertEqual(more[-1].type, ET.RUN_COMPLETED, more[-1].payload)
        self.assertNotIn(bad, [e.payload["model_id"] for e in more if e.type == ET.MODEL_LOADING])
        await close(ctrl)

    async def test_answer_run_does_not_reflect_when_told_not_to(self):
        ctrl = build()
        run_id = await ctrl.start(RunRequest(
            task="What is the capital of France? Answer briefly.", mode="standard",
            deliverable="answer", options={"reflect": False}))
        events = await collect(ctrl, run_id)
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
        self.assertNotIn("REFLECTING", states(events))
        await close(ctrl)

    async def test_failure_emits_run_failed(self):
        ctrl = build()
        run_id = await ctrl.start(RunRequest(task="2+2?", lineup_override=["no-such-model"]))
        events = await collect(ctrl, run_id)
        await ctrl.wait(run_id, TIMEOUT)
        self.assertEqual(events[-1].type, ET.RUN_FAILED)
        self.assertIn("override", events[-1].payload["error"])
        snap = ctrl.snapshot(run_id)
        self.assertEqual(snap.state, RunState.FAILED)
        self.assertTrue(snap.error)
        self.assertFalse(ctrl.is_active(run_id))
        # the server is still alive: another run works
        again = await ctrl.start(RunRequest(task="2+2?", mode="quick"))
        self.assertEqual((await collect(ctrl, again))[-1].type, ET.RUN_COMPLETED)
        await close(ctrl)


class Cancel(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_real_run(self):
        ctrl = RunController.build_mock(home=HOME, speed=1.0)  # slow enough to catch mid-run
        run_id = await ctrl.start(RunRequest(task="Explain TCP slow start.", mode="standard"))

        async def on_event(ev):
            if ev.type == ET.ROUND_STARTED:
                self.assertTrue(await ctrl.cancel(run_id))

        events = await collect(ctrl, run_id, on_event)
        self.assertEqual(events[-1].type, ET.RUN_CANCELLED)
        self.assertEqual(events[-1].payload["from_state"], "DELIBERATING")
        snap = ctrl.snapshot(run_id)
        self.assertEqual(snap.state, RunState.CANCELLED)
        self.assertIsNotNone(snap.finished_at)
        self.assertEqual(ctrl.store.get_run(run_id)["state"], "CANCELLED")
        self.assertFalse(ctrl.is_active(run_id))
        self.assertEqual(ctrl.host._seats, {})
        self.assertFalse(await ctrl.cancel(run_id))
        self.assertNotIn(ET.RUN_COMPLETED, types(events))
        self.assertNotIn(ET.RUN_FAILED, types(events))
        await close(ctrl)

    async def test_cancel_demo_waiting_for_delegate(self):
        ctrl = build()
        run_id = await ctrl.start(RunRequest(task="x", options={"demo": True}))

        async def on_event(ev):
            if ev.type == ET.RUN_STATE_CHANGED and ev.payload["to_state"] == "AWAITING_DELEGATION":
                await asyncio.sleep(0.05)
                self.assertTrue(await ctrl.cancel(run_id))

        events = await collect(ctrl, run_id, on_event)
        self.assertEqual(events[-1].type, ET.RUN_CANCELLED)
        self.assertEqual(events[-1].payload["from_state"], "AWAITING_DELEGATION")
        self.assertEqual(ctrl.snapshot(run_id).state, RunState.CANCELLED)
        with self.assertRaises(RunNotFound):
            await ctrl.cancel("run_nope")
        await close(ctrl)


class Preview(unittest.IsolatedAsyncioTestCase):
    async def test_router_preview_loads_nothing(self):
        ctrl = build()
        lineup = ctrl.router_preview("Write a function that reverses a linked list.", "standard")
        self.assertIsInstance(lineup, LineupRecord)
        self.assertEqual(lineup.k, len(lineup.seats))
        self.assertGreaterEqual(lineup.k, 3)
        self.assertEqual(ctrl.router_preview("anything", "quick").k, 3)
        self.assertEqual(ctrl.host.status(), [])
        self.assertEqual(ctrl.store.list_runs(), [])
        self.assertEqual(ctrl.store.events_since(None, 0), [])
        self.assertGreaterEqual(ctrl.telemetry().mem_total_gib, 0)
        await close(ctrl)

    async def test_two_runs_at_once(self):
        ctrl = build()
        a = await ctrl.start(RunRequest(task="2+2?", mode="quick"))
        b = await ctrl.start(RunRequest(task="Design a cache", options={"demo": True, "auto_delegate": True}))
        ea, eb = await asyncio.gather(collect(ctrl, a), collect(ctrl, b))
        self.assertEqual(ea[-1].type, ET.RUN_COMPLETED, ea[-1].payload)
        self.assertEqual(eb[-1].type, ET.RUN_COMPLETED)
        self.assertTrue(all(e.run_id == a for e in ea))
        self.assertEqual(len(ctrl.list_runs()), 2)
        await close(ctrl)


class PlanEdit(unittest.IsolatedAsyncioTestCase):
    async def test_patch_plan_only_while_awaiting_delegation(self):
        ctrl = build()
        run_id = await ctrl.start(RunRequest(
            task="Plan a small CLI todo app.", mode="quick", deliverable="plan",
            lineup_override=SMALL, options={"seed": 3}))
        with self.assertRaises(InvalidState):
            ctrl.patch_plan(run_id, {"goal": "too early"})
        with self.assertRaises(RunNotFound):
            ctrl.patch_plan("run_nope", {"goal": "x"})
        got = {}

        async def on_event(ev):
            if ev.type == ET.RUN_STATE_CHANGED and ev.payload["to_state"] == "AWAITING_DELEGATION":
                await asyncio.sleep(0.02)
                before = ctrl.store.plan_version(run_id)
                with self.assertRaises(PlanRejected) as bad:
                    ctrl.patch_plan(run_id, {"tasks": []})
                self.assertTrue(bad.exception.issues)
                with self.assertRaises(PlanRejected):
                    ctrl.patch_plan(run_id, {"tasks": "not a list"})
                self.assertEqual(ctrl.store.plan_version(run_id), before)  # nothing stored
                plan = ctrl.patch_plan(run_id, {"goal": "Edited goal"})
                self.assertIsInstance(plan, Plan)
                self.assertEqual(ctrl.store.plan_version(run_id), before + 1)
                self.assertEqual(ctrl.snapshot(run_id).plan.goal, "Edited goal")
                self.assertEqual(ctrl.snapshot(run_id).state, RunState.AWAITING_DELEGATION)
                again = ctrl.patch_plan(run_id, plan.model_copy(update={"goal": "Edited twice"}))
                got["plan"] = again
                await ctrl.delegate(run_id)

        events = await collect(ctrl, run_id, on_event)
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
        ready = [e.payload for e in events if e.type == ET.PLAN_READY]
        self.assertTrue(ready[-1]["edited_by_user"])
        self.assertEqual(ready[-1]["plan"]["goal"], "Edited twice")
        snap = ctrl.snapshot(run_id)
        self.assertEqual(snap.plan.goal, "Edited twice")
        self.assertEqual(len(snap.plan.tasks), len(got["plan"].tasks))
        with self.assertRaises(InvalidState):
            ctrl.patch_plan(run_id, {"goal": "too late"})
        await close(ctrl)


class _FakePipeline:
    """Stands in for RunPipeline: drives the RunControl the controller hands it."""

    script = None  # async def script(run_id, req, ctl) -> None

    def __init__(self, deps, emit_completed=True):
        self.deps = deps
        self.emit_completed = emit_completed

    async def run(self, run_id, req, ctl):
        await type(self).script(run_id, req, ctl)
        return RunResult(decision=Decision(outcome="consensus", final_text="ok"), final_text="ok",
                         files_written=["a.py"])


def fake_pipeline(script):
    cls = type("_Scripted", (_FakePipeline,), {"script": staticmethod(script)})
    return mock.patch.object(controller_mod, "RunPipeline", cls)


class Control(unittest.IsolatedAsyncioTestCase):
    async def test_ask_user_goes_to_awaiting_user_and_back(self):
        answers = []

        async def script(run_id, req, ctl):
            await ctl.set_state(RunState.DELIBERATING, "go")
            self.assertFalse(ctl.cancelled())
            answers.append(await ctl.ask_user(UserQuestion(question="Tabs or spaces?", options=["a", "b"])))
            await ctl.set_state(RunState.DONE, "done")

        ctrl = build()
        events = []
        with fake_pipeline(script):
            run_id = await ctrl.start(RunRequest(task="x"))

            async def pump():
                async for ev in ctrl.bus.subscribe(run_id, 0):
                    events.append(ev)
                    if ev.type == ET.USER_INPUT_REQUESTED:
                        snap = ctrl.snapshot(run_id)
                        self.assertEqual(snap.state, RunState.AWAITING_USER)
                        self.assertEqual(snap.prev_state, RunState.DELIBERATING)
                        self.assertEqual(snap.pending_input.question, "Tabs or spaces?")
                        self.assertEqual(ctrl.store.get_run(run_id)["state"], "AWAITING_USER")
                        with self.assertRaises(InvalidState):
                            await ctrl.submit_input(run_id, UserInput(request_id="wrong", choice="a"))
                        with self.assertRaises(InvalidState):
                            await ctrl.delegate(run_id)
                        self.assertTrue(await ctrl.submit_input(run_id, UserInput(
                            request_id=ev.payload["request_id"], choice="b")))

            await asyncio.wait_for(pump(), TIMEOUT)
        self.assertEqual(answers[0].choice, "b")
        self.assertEqual(states(events), ["INTAKE", "DELIBERATING", "AWAITING_USER", "DELIBERATING", "DONE"])
        got = types(events)
        self.assertLess(got.index(ET.USER_INPUT_REQUESTED), got.index(ET.USER_INPUT_RECEIVED))
        asked = events[got.index(ET.USER_INPUT_REQUESTED)].payload
        self.assertTrue(asked["request_id"])
        self.assertEqual(events[got.index(ET.USER_INPUT_RECEIVED)].payload["choice"], "b")
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED)
        self.assertEqual(got.count(ET.RUN_COMPLETED), 1)
        self.assertEqual(events[-1].payload["final_text"], "ok")
        snap = ctrl.snapshot(run_id)
        self.assertEqual(snap.state, RunState.DONE)
        self.assertIsNone(snap.pending_input)
        self.assertIsNone(snap.prev_state)
        self.assertEqual(ctrl.store.get_run(run_id)["state"], "DONE")
        with self.assertRaises(InvalidState):
            await ctrl.submit_input(run_id, UserInput(request_id="x", choice="a"))
        await close(ctrl)

    async def test_wait_delegate_is_resolved_by_delegate(self):
        order = []

        async def script(run_id, req, ctl):
            await ctl.set_state(RunState.AWAITING_DELEGATION, "plan ready")
            order.append("waiting")
            await ctl.wait_delegate()
            order.append("delegated")
            await ctl.set_state(RunState.EXECUTING, "go")
            await ctl.set_state(RunState.DONE, "done")

        ctrl = build()
        with fake_pipeline(script):
            run_id = await ctrl.start(RunRequest(task="x"))
            for _ in range(20):
                await asyncio.sleep(0.005)
            self.assertEqual(order, ["waiting"])
            self.assertEqual(ctrl.snapshot(run_id).state, RunState.AWAITING_DELEGATION)
            self.assertTrue(await ctrl.delegate(run_id))
            snap = await ctrl.wait(run_id, TIMEOUT)
        self.assertEqual(order, ["waiting", "delegated"])
        self.assertEqual(snap.state, RunState.DONE)
        await close(ctrl)

    async def test_cancel_while_waiting_and_cancelled_flag(self):
        flags = []

        async def script(run_id, req, ctl):
            await ctl.set_state(RunState.AWAITING_DELEGATION, "plan ready")
            try:
                await ctl.wait_delegate()
            finally:
                flags.append(ctl.cancelled())

        ctrl = build()
        with fake_pipeline(script):
            run_id = await ctrl.start(RunRequest(task="x"))
            await asyncio.sleep(0.02)
            self.assertTrue(await ctrl.cancel(run_id))
        self.assertEqual(flags, [True])
        snap = ctrl.snapshot(run_id)
        self.assertEqual(snap.state, RunState.CANCELLED)
        last = ctrl.store.events_for_run(run_id)[-1]
        self.assertEqual(last.type, ET.RUN_CANCELLED)
        self.assertEqual(last.payload["from_state"], "AWAITING_DELEGATION")
        self.assertFalse(await ctrl.cancel(run_id))
        await close(ctrl)

    async def test_cancel_while_waiting_for_the_user(self):
        async def script(run_id, req, ctl):
            await ctl.ask_user(UserQuestion(question="?"))

        ctrl = build()
        with fake_pipeline(script):
            run_id = await ctrl.start(RunRequest(task="x"))
            await asyncio.sleep(0.02)
            self.assertEqual(ctrl.snapshot(run_id).state, RunState.AWAITING_USER)
            self.assertTrue(await ctrl.cancel(run_id))
        snap = ctrl.snapshot(run_id)
        self.assertEqual(snap.state, RunState.CANCELLED)
        self.assertIsNone(snap.pending_input)
        await close(ctrl)


def _ev(seq: int, type_: str, payload: dict) -> Event:
    return Event(type=type_, seq=seq, ts=100.0 + seq, run_id="r1", payload=payload)


class SnapshotFold(unittest.TestCase):
    def test_fold_tribunal_corrections_and_claim_scores(self):
        outcome = TribunalOutcome(outlier_seat=2, outlier_model_id="m2", outcome="failed", lesson="check units")
        fix = Correction(id="c1", project="p", model_id="m2", lesson="check units")
        s0 = [ClaimScore(claim_ref="answer", reliability=0.4, seat_no=0)]
        s1 = [ClaimScore(claim_ref="answer", reliability=0.7), ClaimScore(claim_ref="c1", reliability=0.7)]
        snap = fold(RunSnapshot(run_id="r1"), [
            _ev(1, ET.PROBE_SCORES, {"seat_no": 0, "scores": [x.model_dump() for x in s0]}),
            _ev(2, ET.PROBE_SCORES, {"seat_no": 1, "scores": [x.model_dump() for x in s1]}),
            _ev(3, ET.PROBE_SCORES, {"seat_no": 0, "scores": [x.model_dump() for x in s0]}),  # resent
            _ev(4, ET.TRIBUNAL_OUTCOME, {"outcome": outcome.model_dump(mode="json"), "seat_no": 2}),
            _ev(5, ET.CORRECTION_RECORDED, {"correction": fix.model_dump(mode="json")}),
            _ev(6, ET.CORRECTION_RECORDED, {"correction": fix.model_dump(mode="json")}),  # same id
            _ev(7, ET.TRIBUNAL_OUTCOME, {}),  # empty payload changes nothing
        ])
        self.assertEqual(snap.tribunal.outcome, "failed")
        self.assertEqual(snap.tribunal.outlier_seat, 2)
        self.assertEqual(snap.tribunal.correction_id, "c1")
        self.assertEqual([c.id for c in snap.corrections], ["c1"])
        self.assertEqual(sorted((c.seat_no, c.claim_ref) for c in snap.claim_scores),
                         [(0, "answer"), (1, "answer"), (1, "c1")])
        self.assertEqual(snap.last_seq, 7)
        empty = fold(RunSnapshot(run_id="r1"), [])
        self.assertIsNone(empty.tribunal)
        self.assertEqual((empty.corrections, empty.claim_scores), ([], []))


class Extras(unittest.IsolatedAsyncioTestCase):
    async def test_standard_run_snapshot_has_scores_tribunal_and_corrections(self):
        ctrl = build()
        run_id = await ctrl.start(RunRequest(
            task="What is the capital of France? Answer briefly.", mode="standard",
            deliverable="answer", options={"seed": 1}))
        events = await collect(ctrl, run_id)
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED, events[-1].payload)
        snap = ctrl.snapshot(run_id)
        scored = [e for e in events if e.type == ET.PROBE_SCORES]
        self.assertEqual(len(scored), snap.lineup.k)
        self.assertEqual(len(snap.claim_scores), sum(len(e.payload["scores"]) for e in scored))
        self.assertEqual({c.seat_no for c in snap.claim_scores}, {s.seat_no for s in snap.lineup.seats})
        outcomes = [e.payload["outcome"] for e in events if e.type == ET.TRIBUNAL_OUTCOME]
        if outcomes:
            self.assertIn("EXAMINING", states(events))
            self.assertEqual(snap.tribunal.outcome, outcomes[-1]["outcome"])
        else:
            self.assertIsNone(snap.tribunal)
        fixes = [e.payload["correction"]["id"] for e in events if e.type == ET.CORRECTION_RECORDED]
        self.assertEqual([c.id for c in snap.corrections], fixes)
        self.assertEqual([c.id for c in ctrl.corrections()], fixes)
        self.assertEqual(ctrl.corrections("no-such-project"), [])
        if fixes:
            self.assertEqual(snap.tribunal.correction_id, fixes[-1])
            self.assertEqual([c.id for c in ctrl.corrections(snap.corrections[0].project)], fixes)
        self.assertEqual(ctrl.store.get_run(run_id)["snapshot"], snap.model_dump(mode="json"))
        self.assertEqual(len(ctrl.list_runs()), 1)
        await close(ctrl)

    async def test_build_mock_wires_every_service(self):
        ctrl = build()
        self.assertTrue(ctrl.mock)
        self.assertIsInstance(ctrl.chronicle, Chronicle)
        self.assertIsInstance(ctrl.reflector, Reflector)
        self.assertIsInstance(ctrl.corrections_book, CorrectionBook)
        self.assertIsInstance(ctrl.reliability, ReliabilityService)
        self.assertIsNotNone(ctrl.reliability.source)
        self.assertEqual(len((await ctrl.gateway.embed(["hello"]))[0]), 64)
        deps = ctrl._deps()
        self.assertIs(deps.chronicle, ctrl.chronicle)
        self.assertIs(deps.corrections, ctrl.corrections_book)
        self.assertIs(deps.reliability, ctrl.reliability)
        self.assertEqual(deps.home, ctrl.data_home)
        # an in-memory run keeps its files in a throwaway folder, never in the repo
        tmp = ctrl.data_home
        self.assertTrue(tmp.is_dir())
        self.assertNotEqual(tmp.resolve(), HOME.resolve())
        self.assertEqual(ctrl.corrections_book.home, tmp)
        await close(ctrl)
        self.assertFalse(tmp.exists())

    async def test_data_home_is_kept_when_given(self):
        tmp = Path(tempfile.mkdtemp(prefix="council-test-"))
        try:
            ctrl = RunController.build_mock(home=HOME, speed=SPEED, data_home=tmp)
            self.assertEqual(ctrl.data_home, tmp)
            await close(ctrl)
            self.assertTrue(tmp.is_dir())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    async def test_build_from_config_mock_and_real(self):
        ctrl = RunController.build_from_config(home=HOME, db_path=":memory:", speed=SPEED)
        self.assertTrue(ctrl.mock)  # the repo config is in mock mode
        await close(ctrl)

        tmp = Path(tempfile.mkdtemp(prefix="council-test-"))
        try:
            (tmp / "config").mkdir()
            (tmp / "config" / "council.toml").write_text(
                '[host]\ndriver = "ollama"\n[gateway]\nmock = false\n[probe]\nsource = "ollama_embed"\n',
                encoding="utf-8")
            shutil.copy(HOME / "config" / "models.json", tmp / "config" / "models.json")
            real = RunController.build_from_config(home=tmp)
            self.assertFalse(real.mock)
            self.assertEqual(type(real.host.driver).__name__, "OllamaDriver")
            self.assertTrue(real.gateway.uses_ollama)
            self.assertIsNone(real.gateway.responder)
            self.assertEqual(real.data_home, tmp)
            self.assertTrue((tmp / "db" / "council.db").is_file())
            self.assertTrue(real.registry)
            self.assertIsInstance(real.reliability, ReliabilityService)
            self.assertIsInstance(real.router_preview("2+2?", "quick"), LineupRecord)  # no model call
            await close(real)
            self.assertTrue(tmp.is_dir())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    async def test_bench_runs_in_the_background(self):
        ctrl = build()
        bench_id = await ctrl.start_bench(BenchRunRequest(modes=["council_vote_only"], limit=2))
        self.assertIn(ctrl.bench_status(bench_id)["state"], ("queued", "running"))
        with self.assertRaises(InvalidState):
            await ctrl.start_bench(BenchRunRequest(modes=["council"], limit=1))
        with self.assertRaises(RunNotFound):
            ctrl.bench_status("bench_nope")
        for _ in range(int(TIMEOUT / 0.01)):
            if ctrl.bench_status(bench_id)["state"] not in ("queued", "running"):
                break
            await asyncio.sleep(0.01)
        status = ctrl.bench_status(bench_id)
        self.assertEqual(status["state"], "done", status["error"])
        self.assertIsNone(status["error"])
        self.assertEqual((status["done"], status["total"]), (2, 2))
        self.assertEqual([r["mode"] for r in status["summary"]], ["council_vote_only"])
        self.assertTrue(Path(status["results_path"]).is_file())
        self.assertTrue(Path(status["out_dir"]).is_relative_to(ctrl.data_home))
        self.assertTrue(status["request"]["tasks_path"])
        got = [e.type for e in ctrl.store.events_since(bench_id, 0)]
        self.assertEqual((got[0], got[-1]), (ET.BENCH_STARTED, ET.BENCH_COMPLETED))
        self.assertEqual(ctrl.list_runs(), [])  # a bench is not a run

        bad = await ctrl.start_bench(BenchRunRequest(modes=["no_such_mode"]))
        await asyncio.wait([ctrl._benches[bad].task], timeout=TIMEOUT)
        self.assertEqual(ctrl.bench_status(bad)["state"], "failed")
        self.assertIn("no_such_mode", ctrl.bench_status(bad)["error"])
        await close(ctrl)

    async def test_train_probe_and_list_probes(self):
        ctrl = build()
        self.assertEqual(ctrl.probes(), [])
        model = ctrl.registry[0].id
        probe = await ctrl.train_probe(model)
        self.assertEqual(probe.model_id, model)
        self.assertEqual(probe.status, "validated")
        self.assertGreaterEqual(probe.auroc, ctrl.config.probe.min_auroc)
        ctrl.store.kv_put("probes", "behaviour_weights:" + model, {"weights": {"x": 1.0}})
        self.assertEqual([p.model_id for p in ctrl.probes()], [model])  # weights are not probes
        trained = [e for e in ctrl.store.events_since(None, 0) if e.type == ET.PROBE_TRAINED]
        self.assertEqual(len(trained), 1)
        self.assertTrue(trained[0].payload["validated"])
        with self.assertRaises(RunNotFound):
            await ctrl.train_probe("no-such-model")
        ctrl.reliability = None
        with self.assertRaises(InvalidState):
            await ctrl.train_probe(model)
        await close(ctrl)

    async def test_export_chronicle(self):
        ctrl = build()
        text = ctrl.export_chronicle()
        self.assertTrue(text.startswith("# Chronicle"))
        self.assertIn("(no entries)", text)
        self.assertIsInstance(ctrl.export_chronicle("some-project"), str)
        await close(ctrl)


if __name__ == "__main__":
    unittest.main()
