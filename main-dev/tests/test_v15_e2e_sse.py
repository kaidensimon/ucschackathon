"""1.5 end to end: effort.planned, lie.report and memory.planned over the real SSE endpoint.

Real RunController (mock build), real FastAPI app, real EventBus and stream_frames. Each frame is
parsed back from the wire text and its payload checked against the model in event_types.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from council.api.controller import RunController
from council.api.server import create_app
from council.core import event_types as ET
from council.core.schemas import RunRequest, RunState
from council.core.schemas_v15 import LieReport, MemoryPlan
from tests.test_api_run_pipeline import ANSWER_TASK

HOME = Path(__file__).resolve().parents[1]
V15 = (ET.EFFORT_PLANNED, ET.LIE_REPORT, ET.MEMORY_PLANNED)


def parse_sse(text):
    """Wire text -> list of (id, event name, envelope dict). Comment frames are skipped."""
    out = []
    for frame in text.split("\n\n"):
        lines = frame.split("\n")
        data = [ln[len("data: "):] for ln in lines if ln.startswith("data: ")]
        if not data:
            continue
        fid = [ln[len("id: "):] for ln in lines if ln.startswith("id: ")]
        name = [ln[len("event: "):] for ln in lines if ln.startswith("event: ")]
        out.append((fid[0] if fid else None, name[0] if name else None, json.loads(data[0])))
    return out


class SseV15(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="council_sse_e2e_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ctrl = RunController.build_mock(home=HOME, speed=100000.0, data_home=self.tmp)
        self.addCleanup(self.ctrl.store.close)

    def run_and_stream(self, client, k=3, options=None):
        opts = {"k": k, "auto_input": True}
        opts.update(options or {})
        r = client.post("/runs", json={"task": ANSWER_TASK, "deliverable": "answer", "options": opts})
        self.assertEqual(r.status_code, 200, r.text)
        rid = r.json()["run_id"]
        with client.stream("GET", f"/runs/{rid}/events") as resp:
            self.assertTrue(resp.headers["content-type"].startswith("text/event-stream"))
            body = "".join(resp.iter_text())
        return rid, parse_sse(body), body

    def test_three_events_stream_in_order_with_valid_payloads(self):
        with TestClient(create_app(self.ctrl)) as c:
            rid, evs, _ = self.run_and_stream(c)
            self.assertEqual(c.get(f"/runs/{rid}").json()["state"], "DONE")
        names = [n for _, n, _ in evs]
        for t in V15:
            self.assertEqual(names.count(t), 1, f"{t} x{names.count(t)} in {names}")
        # real run order: memory plan at convening, effort plan after the lineup, lie report last
        self.assertLess(names.index(ET.MEMORY_PLANNED), names.index(ET.ROUTER_LINEUP_SELECTED))
        self.assertLess(names.index(ET.ROUTER_LINEUP_SELECTED), names.index(ET.EFFORT_PLANNED))
        self.assertLess(names.index(ET.EFFORT_PLANNED), names.index(ET.LIE_REPORT))
        for _, name, env in evs:
            if name in V15:
                model = ET.validate_payload(name, env["payload"])
                self.assertIsInstance(model, ET.PAYLOADS[name])
        by = {n: env["payload"] for _, n, env in evs if n in V15}
        effort = ET.EffortPlannedPayload.model_validate(by[ET.EFFORT_PLANNED])
        self.assertIn(effort.level, ("light", "normal", "heavy"))
        self.assertTrue(effort.rounds)
        self.assertGreater(effort.deadline_s, 0.0)
        plan = MemoryPlan.model_validate(ET.MemoryPlannedPayload.model_validate(by[ET.MEMORY_PLANNED]).plan)
        self.assertTrue(plan.model_dump())
        lie = ET.LieReportPayload.model_validate(by[ET.LIE_REPORT])
        report = LieReport.model_validate(lie.report)
        self.assertEqual(report.run_id, rid)
        self.assertEqual(len(report.seats), 3)

    def test_envelope_is_consistent_with_frame_headers(self):
        with TestClient(create_app(self.ctrl)) as c:
            rid, evs, body = self.run_and_stream(c)
        self.assertTrue(evs)
        seqs = []
        for fid, name, env in evs:
            self.assertEqual(env["type"], name)
            self.assertEqual(env["run_id"], rid)
            self.assertEqual(str(env["seq"]), fid)
            seqs.append(env["seq"])
        self.assertEqual(seqs, sorted(seqs))
        # ephemeral events (turn.delta) reuse the last stored seq; stored ones are unique
        kept = [env["seq"] for _, n, env in evs if n not in ET.EPHEMERAL_EVENTS]
        self.assertEqual(len(kept), len(set(kept)))
        self.assertEqual(evs[-1][1], ET.RUN_COMPLETED)
        # every streamed event is a known type with a valid payload
        for _, name, env in evs:
            self.assertIn(name, ET.EVENT_TYPES)
            ET.validate_payload(name, env["payload"])

    def test_resume_cursor_replays_only_later_v15_events(self):
        with TestClient(create_app(self.ctrl)) as c:
            rid, evs, _ = self.run_and_stream(c)
            pos = {n: env["seq"] for _, n, env in evs if n in V15}
            self.assertEqual(set(pos), set(V15))
            # cut right after effort.planned (memory.planned came first): only lie.report is left
            cut = pos[ET.EFFORT_PLANNED]
            self.assertLess(pos[ET.MEMORY_PLANNED], cut)
            with c.stream("GET", f"/runs/{rid}/events?since={cut}") as resp:
                later = parse_sse("".join(resp.iter_text()))
            self.assertTrue(all(env["seq"] > cut for _, _, env in later))
            later_v15 = [n for _, n, _ in later if n in V15]
            self.assertEqual(later_v15, [ET.LIE_REPORT])
            # Last-Event-ID works the same as ?since=
            with c.stream("GET", f"/runs/{rid}/events", headers={"Last-Event-ID": str(cut)}) as resp:
                via_header = parse_sse("".join(resp.iter_text()))
            self.assertEqual([e["seq"] for _, _, e in via_header], [e["seq"] for _, _, e in later])
            # cut at the start: all three
            with c.stream("GET", f"/runs/{rid}/events?since=0") as resp:
                full = parse_sse("".join(resp.iter_text()))
            self.assertEqual([n for _, n, _ in full if n in V15],
                             [n for _, n, _ in evs if n in V15])

    def test_stream_matches_stored_events(self):
        with TestClient(create_app(self.ctrl)) as c:
            rid, evs, _ = self.run_and_stream(c)
        stored = [e for e in self.ctrl.store.events_for_run(rid)]
        streamed = {env["seq"]: (n, env["payload"]) for _, n, env in evs}
        for e in stored:
            if e.type in V15:
                self.assertIn(e.seq, streamed, f"{e.type} stored but not streamed")
                self.assertEqual(streamed[e.seq][0], e.type)
                self.assertEqual(streamed[e.seq][1], json.loads(json.dumps(e.payload)))

    def test_trained_probe_lie_report_streams_probe_models(self):
        import asyncio

        async def train():
            for m in self.ctrl.registry:
                await self.ctrl.reliability.train_statements(m.id, now=1000.0, seed=1)

        asyncio.run(train())
        with TestClient(create_app(self.ctrl)) as c:
            rid, evs, _ = self.run_and_stream(c)
        reports = [env["payload"] for _, n, env in evs if n == ET.LIE_REPORT]
        self.assertEqual(len(reports), 1)
        p = ET.validate_payload(ET.LIE_REPORT, reports[0])
        report = LieReport.model_validate(p.report)
        self.assertTrue(report.probe_models)
        self.assertEqual(report.note, "")
        # watched counts the flags at level "watch" (see probe/lie_report.py), not the seats
        self.assertEqual(p.watched, sum(1 for f in report.flags if f.level == "watch"))

    def test_forced_effort_level_shows_in_streamed_event(self):
        levels = {}
        with TestClient(create_app(self.ctrl)) as c:
            for lvl in ("light", "heavy"):
                rid, evs, _ = self.run_and_stream(c, options={"effort": lvl})
                got = [env["payload"] for _, n, env in evs if n == ET.EFFORT_PLANNED]
                self.assertEqual(len(got), 1, lvl)
                levels[lvl] = ET.EffortPlannedPayload.model_validate(got[0])
        self.assertEqual(levels["light"].level, "light")
        self.assertEqual(levels["heavy"].level, "heavy")
        self.assertLessEqual(len(levels["light"].rounds), len(levels["heavy"].rounds))

    def test_demo_run_streams_the_same_three_events(self):
        with TestClient(create_app(self.ctrl)) as c:
            r = c.post("/runs", json={"task": "pick a db", "mode": "standard", "options": {
                "demo": True, "auto_delegate": True, "k": 3}})
            self.assertEqual(r.status_code, 200)
            rid = r.json()["run_id"]
            with c.stream("GET", f"/runs/{rid}/events") as resp:
                evs = parse_sse("".join(resp.iter_text()))
        names = [n for _, n, _ in evs]
        for t in V15:
            self.assertEqual(names.count(t), 1, t)
            ET.validate_payload(t, [env["payload"] for _, n, env in evs if n == t][0])
        self.assertLess(names.index(ET.MEMORY_PLANNED), names.index(ET.LIE_REPORT))
        self.assertLess(names.index(ET.EFFORT_PLANNED), names.index(ET.LIE_REPORT))


if __name__ == "__main__":
    unittest.main()
