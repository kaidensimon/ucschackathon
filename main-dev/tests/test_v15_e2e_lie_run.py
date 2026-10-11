"""1.5 end to end: the lie detector inside a mock run, through the real classes.

Pipeline tests use the same rig as test_api_run_pipeline (real RunPipeline, Gateway, Host with a
mock driver, ReliabilityService with the mock activation source). The route test uses the real
RunController and the real FastAPI app.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from council.api.controller import RunController
from council.api.server import create_app
from council.core import event_types as ET
from council.core.schemas import RunRequest, RunState
from council.core.schemas_v15 import LieReport
from council.probe.lie_report import NO_PROBE_NOTE
from tests.test_api_run_pipeline import ANSWER_TASK, SEATS, Base

HOME = Path(__file__).resolve().parents[1]
TRAIN_N = 120  # statement pairs: enough to validate the mock probe, about 2 s per model


class ThrowingSource:
    """An activation source that always fails, like a dead llama.cpp tool."""

    def __init__(self) -> None:
        self.calls = 0

    async def capture(self, model_id, messages, layers):
        self.calls += 1
        raise RuntimeError("activation tool died")


def reports_of(rig, run_id):
    return rig.events(run_id, ET.LIE_REPORT)


class LieInRun(Base):
    async def train_all_seats(self):
        for mid in SEATS:
            card = await self.rig.reliability.train_statements(mid, now=1000.0, seed=1, n=TRAIN_N)
            self.assertTrue(card.active, f"{mid}: {card.reason}")

    async def test_trained_probe_gives_one_honesty_row_per_seat(self):
        rig = self.rig
        await self.train_all_seats()
        run_id, _, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-1], RunState.DONE)
        events = reports_of(rig, run_id)
        self.assertEqual(len(events), 1)
        report = LieReport.model_validate(events[0].payload["report"])
        self.assertEqual(report.run_id, run_id)
        self.assertEqual([s.seat_no for s in report.seats], list(range(len(SEATS))))
        self.assertEqual({s.model_id for s in report.seats}, set(SEATS))
        self.assertEqual(set(report.probe_models), set(SEATS))
        self.assertEqual(report.note, "")
        for seat in report.seats:
            self.assertGreater(seat.claims, 0, seat)
            self.assertIsNotNone(seat.mean_probe, seat)  # the probe really scored the seat
        self.assertTrue(any(f.probe_score is not None for f in report.flags))
        for f in report.flags:
            if f.probe_score is not None:
                self.assertTrue(0.0 <= f.probe_score <= 1.0, f)

    async def test_no_probe_report_says_behaviour_only(self):
        rig = self.rig
        self.assertEqual(rig.reliability.cards(), [])
        run_id, _, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-1], RunState.DONE)
        events = reports_of(rig, run_id)
        self.assertEqual(len(events), 1)
        report = LieReport.model_validate(events[0].payload["report"])
        self.assertEqual(report.note, NO_PROBE_NOTE)
        self.assertEqual(report.probe_models, [])
        self.assertEqual(len(report.seats), len(SEATS))
        self.assertTrue(report.flags)
        for f in report.flags:
            self.assertIsNone(f.probe_score, f)
            self.assertIsNotNone(f.behaviour_score, f)
        self.assertEqual(rig.reliability.last_report(run_id), report)

    async def test_a_source_that_throws_never_breaks_the_run(self):
        rig = self.rig
        await self.train_all_seats()
        dead = ThrowingSource()
        rig.reliability.source = dead
        run_id, result, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-1], RunState.DONE)
        self.assertTrue(result.final_text)
        self.assertGreater(dead.calls, 0)  # the detector really tried the source
        events = reports_of(rig, run_id)
        self.assertEqual(len(events), 1)  # and still said something
        report = LieReport.model_validate(events[0].payload["report"])
        self.assertEqual(report.run_id, run_id)
        self.assertEqual(len(report.seats), len(SEATS))
        self.assertTrue(all(f.probe_score is None for f in report.flags))

    async def test_lie_report_call_does_not_raise_on_a_throwing_source(self):
        rig = self.rig
        await self.train_all_seats()
        # a finished mock run gives real seats and drafts to feed the service directly
        captured = {}
        from council.api import run_pipeline as rp
        from unittest import mock
        real = rp.Deliberation.drafts

        def spy(self_):
            out = real(self_)
            if out:
                captured["drafts"] = dict(out)
            return out

        with mock.patch.object(rp.Deliberation, "drafts", spy):
            run_id, _, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertTrue(captured.get("drafts"))
        from council.core.schemas import SeatAssignment
        seats = [SeatAssignment(seat_no=i, model_id=m) for i, m in enumerate(SEATS)]
        rig.reliability.source = ThrowingSource()
        report = await rig.reliability.lie_report("direct", ANSWER_TASK, seats, captured["drafts"])
        self.assertIsInstance(report, LieReport)
        self.assertEqual(report.run_id, "direct")
        self.assertTrue(report.seats)
        self.assertIsNotNone(rig.reliability.last_report("direct"))


class LieRoute(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="council_lie_e2e_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ctrl = RunController.build_mock(home=HOME, speed=100000.0, data_home=self.tmp)
        self.addCleanup(self.ctrl.store.close)
        self.client = TestClient(create_app(self.ctrl))

    async def asyncTearDown(self) -> None:
        await self.ctrl.shutdown()

    async def run_one(self, k: int = 3) -> str:
        run_id = await self.ctrl.start(RunRequest(
            task=ANSWER_TASK, deliverable="answer", options={"k": k, "auto_input": True}))
        snap = await self.ctrl.wait(run_id, 120.0)
        self.assertEqual(snap.state, RunState.DONE, snap.error)
        return run_id

    async def test_get_lies_returns_the_report_of_a_trained_run(self):
        ctrl = self.ctrl
        for m in ctrl.registry:
            await ctrl.reliability.train_statements(m.id, now=1000.0, seed=1, n=TRAIN_N)
        run_id = await self.run_one(3)
        ev = [e for e in ctrl.store.events_for_run(run_id) if e.type == ET.LIE_REPORT]
        self.assertEqual(len(ev), 1)
        sent = ev[0].payload["report"]
        self.assertEqual(len(sent["seats"]), 3)
        r = self.client.get(f"/lies/{run_id}")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("caveat", body)
        self.assertEqual(body["run_id"], run_id)
        self.assertEqual(body["seats"], sent["seats"])
        self.assertEqual(body["flags"], sent["flags"])
        self.assertTrue(body["probe_models"])
        self.assertEqual(body["note"], "")
        text = self.client.get(f"/lies/{run_id}/text")
        self.assertEqual(text.status_code, 200)
        self.assertTrue(text.text.strip())

    async def test_get_lies_without_a_probe_has_the_behaviour_note(self):
        run_id = await self.run_one(3)
        r = self.client.get(f"/lies/{run_id}")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["note"], NO_PROBE_NOTE)
        self.assertEqual(len(body["seats"]), 3)
        self.assertEqual(body["probe_models"], [])
        self.assertEqual(self.client.get("/lies/no_such_run").status_code, 404)


if __name__ == "__main__":
    unittest.main()
