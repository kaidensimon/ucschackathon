"""1.5 end to end: the demo script emits every event type and every payload validates.

Real demo_events, real event_types, real RunController (mock build) with its EventBus and
store, real FastAPI SSE endpoint. Nothing is re-implemented here.
"""

import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from council.api.controller import RunController
from council.api.demo_script import BUILTIN_MODELS, WAIT_DELEGATE, demo_events
from council.api.server import create_app
from council.core import event_types as ET
from council.core.schemas import ModelEntry, RunRequest, RunState, UserInput

HOME = Path(__file__).resolve().parents[1]
TASK = "Design a rate limiter for our public API."
NEVER_IN_DEMO = {ET.RUN_FAILED, ET.RUN_CANCELLED}  # a demo run always completes
NEVER_IN_DEMO |= {  # the open council protocol is not in the demo script yet
    ET.MSG_STARTED, ET.MSG_DELTA, ET.MSG_THINKING, ET.MSG_ENDED, ET.MSG_CARD, ET.MSG_LIE,
    ET.TABLE_TALLY,
}
WANT = set(ET.EVENT_TYPES) - NEVER_IN_DEMO
TIMEOUT = 60.0


def script_types(events):
    return {t for _, t, _ in events if t != WAIT_DELEGATE}


def parse_sse(text):
    out = []
    for frame in text.split("\n\n"):
        data = [ln[len("data: "):] for ln in frame.split("\n") if ln.startswith("data: ")]
        if data:
            out.append(json.loads(data[0]))
    return out


class DemoScriptCoverage(unittest.TestCase):
    def test_every_event_type_is_emitted_and_every_payload_validates(self):
        events = demo_events(TASK, "run-e2e")
        self.assertEqual(WANT - script_types(events), set())
        self.assertEqual(script_types(events) - set(ET.EVENT_TYPES), set())
        for delay, type_, payload in events:
            self.assertGreaterEqual(delay, 0.0)
            if type_ == WAIT_DELEGATE:
                continue
            model = ET.validate_payload(type_, payload)
            self.assertIsInstance(model, ET.PAYLOADS[type_], type_)
            json.dumps(payload)

    def test_payloads_survive_a_validate_dump_round_trip(self):
        for _, type_, payload in demo_events(TASK, "run-rt"):
            if type_ == WAIT_DELEGATE:
                continue
            again = ET.validate_payload(type_, payload).model_dump(mode="json")
            self.assertEqual(again, ET.validate_payload(type_, again).model_dump(mode="json"), type_)
            # nothing the script wrote was dropped as an unknown key
            lost = set(payload) - set(again)
            self.assertEqual(lost, set(), f"{type_} lost keys {lost}")

    def test_coverage_holds_for_other_seeds_and_model_sets(self):
        labs = ["LabA", "LabB", "LabC", "LabD", "LabE", "LabF", "LabG"]
        models = [ModelEntry(id=f"m{i}", display=f"Model {i}", lab=lab, params_b=8.0 + i,
                             roles=["worker"] if i == 6 else ["seat"]) for i, lab in enumerate(labs)]
        cases = [
            dict(models=None, seed=0),
            dict(models=None, seed=11),
            dict(models=list(BUILTIN_MODELS), seed=5),
            dict(models=models, seed=7),
            dict(models=[ModelEntry(id="solo", lab="LabA")], seed=3),
        ]
        for case in cases:
            events = demo_events(TASK, "run-var", **case)
            self.assertEqual(WANT - script_types(events), set(), case["seed"])
            for _, type_, payload in events:
                if type_ != WAIT_DELEGATE:
                    ET.validate_payload(type_, payload)
            self.assertEqual(events[0][1], ET.RUN_CREATED)
            self.assertEqual(events[-1][1], ET.RUN_COMPLETED)

    def test_event_type_contract_is_consistent(self):
        self.assertEqual(len(ET.EVENT_TYPES), len(set(ET.EVENT_TYPES)))
        for t in ET.EVENT_TYPES:
            self.assertEqual(getattr(ET, ET.constant_name(t)), t)
            self.assertIn(ET.payload_class_name(t), dir(ET))
            self.assertIn(t, ET.PAYLOADS)
        self.assertEqual(set(ET.PAYLOADS), set(ET.EVENT_TYPES))
        self.assertTrue(set(ET.TERMINAL_EVENTS) <= set(ET.EVENT_TYPES))
        with self.assertRaises(ValueError):
            ET.validate_payload("no.such_event", {})


class DemoThroughController(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="council_demo_e2e_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ctrl = RunController.build_mock(home=HOME, speed=100000.0, data_home=self.tmp)
        self.addCleanup(self.ctrl.store.close)

    async def collect(self, run_id):
        out = []

        async def pump():
            async for ev in self.ctrl.bus.subscribe(run_id, 0):
                out.append(ev)
                if ev.type == ET.USER_INPUT_REQUESTED and self.ctrl.is_active(run_id):
                    try:
                        await self.ctrl.submit_input(run_id, UserInput(
                            request_id=ev.payload.get("request_id") or "", choice="go"))
                    except Exception:  # the demo script answers its own question
                        pass

        await asyncio.wait_for(pump(), TIMEOUT)
        return out

    async def run_demo(self, **opts):
        options = {"demo": True, "auto_delegate": True}
        options.update(opts)
        run_id = await self.ctrl.start(RunRequest(task=TASK, options=options))
        events = await self.collect(run_id)
        await self.ctrl.shutdown()
        return run_id, events

    async def test_bus_carries_every_event_type_with_valid_payloads(self):
        run_id, events = await self.run_demo()
        got = {e.type for e in events}
        self.assertEqual(WANT - got, set())
        self.assertEqual(got - set(ET.EVENT_TYPES), set())
        self.assertEqual(events[0].type, ET.RUN_CREATED)
        self.assertEqual(events[-1].type, ET.RUN_COMPLETED)
        for e in events:
            self.assertEqual(e.run_id, run_id)
            ET.validate_payload(e.type, e.payload)
        # start() owns run.created: the script's copy is dropped, so there is exactly one
        self.assertEqual([e.type for e in events].count(ET.RUN_CREATED), 1)
        self.assertEqual([e.type for e in events].count(ET.RUN_COMPLETED), 1)
        self.assertEqual(self.ctrl.snapshot(run_id).state, RunState.DONE)

    async def test_stored_events_exclude_ephemeral_and_replay_in_order(self):
        run_id, events = await self.run_demo()
        stored = self.ctrl.store.events_since(run_id, 0, limit=100000)
        stored_types = {e.type for e in stored}
        self.assertEqual(stored_types & set(ET.EPHEMERAL_EVENTS), set())
        self.assertEqual(WANT - set(ET.EPHEMERAL_EVENTS) - stored_types, set())
        seqs = [e.seq for e in stored]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(seqs), len(set(seqs)))
        for e in stored:
            ET.validate_payload(e.type, e.payload)
        live = [e.type for e in events if e.type not in ET.EPHEMERAL_EVENTS]
        self.assertEqual([e.type for e in stored], live)

    async def test_demo_without_auto_delegate_stops_until_delegated(self):
        run_id = await self.ctrl.start(RunRequest(task=TASK, options={"demo": True}))
        out = []

        async def pump():
            async for ev in self.ctrl.bus.subscribe(run_id, 0):
                out.append(ev)
                if ev.type == ET.RUN_STATE_CHANGED and ev.payload["to_state"] == "AWAITING_DELEGATION":
                    await asyncio.sleep(0.2)
                    self.assertNotIn(ET.DELEGATION_STARTED, [e.type for e in out])
                    await self.ctrl.delegate(run_id)
                if ev.type == ET.USER_INPUT_REQUESTED and self.ctrl.is_active(run_id):
                    try:
                        await self.ctrl.submit_input(run_id, UserInput(
                            request_id=ev.payload.get("request_id") or "", choice="go"))
                    except Exception:
                        pass

        await asyncio.wait_for(pump(), TIMEOUT)
        await self.ctrl.shutdown()
        self.assertEqual(WANT - {e.type for e in out}, set())
        self.assertEqual(out[-1].type, ET.RUN_COMPLETED)


class DemoOverSse(unittest.TestCase):
    def test_sse_stream_of_a_demo_run_covers_every_stored_type(self):
        tmp = Path(tempfile.mkdtemp(prefix="council_demo_sse_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        ctrl = RunController.build_mock(home=HOME, speed=100000.0, data_home=tmp)
        self.addCleanup(ctrl.store.close)
        with TestClient(create_app(ctrl)) as c:
            r = c.post("/runs", json={"task": TASK, "deliverable": "plan",
                                      "options": {"demo": True, "auto_delegate": True}})
            self.assertEqual(r.status_code, 200, r.text)
            rid = r.json()["run_id"]
            with c.stream("GET", f"/runs/{rid}/events") as resp:
                body = "".join(resp.iter_text())
            self.assertEqual(c.get(f"/runs/{rid}").json()["state"], "DONE")
        envs = parse_sse(body)
        names = {e["type"] for e in envs}
        # token deltas are live only (never stored): a client that connects after the burst of a
        # fast run replays just the stored events, so only those are required here
        self.assertEqual(WANT - set(ET.EPHEMERAL_EVENTS) - names, set())
        self.assertEqual(envs[-1]["type"], ET.RUN_COMPLETED)
        for env in envs:
            self.assertEqual(env["run_id"], rid)
            ET.validate_payload(env["type"], env["payload"])


if __name__ == "__main__":
    unittest.main()
