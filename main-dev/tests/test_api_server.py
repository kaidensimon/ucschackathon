import json
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from council.api.controller import RunController
from council.api.server import create_app


HOME = Path(__file__).resolve().parents[1]
SMALL = ["granite-next-8b", "glm-small", "ministral-mid"]  # seats that leave room for the workers


def parse_sse(text):
    out = []
    for frame in text.split("\n\n"):
        data = [ln[6:] for ln in frame.split("\n") if ln.startswith("data: ")]
        if data:
            out.append(json.loads(data[0]))
    return out


class ApiServerTest(unittest.TestCase):
    def test_all(self):
        ctrl = RunController.build_mock(speed=500.0)
        with TestClient(create_app(ctrl)) as c:
            self.assertEqual(c.get("/health").json(), {"ok": True, "mock": True, "driver": "mock"})
            self.assertEqual(c.get("/runs/nope").status_code, 404)
            self.assertEqual(c.get("/runs/nope/events").status_code, 404)
            self.assertEqual(c.post("/runs/nope/cancel").status_code, 404)

            r = c.post("/runs", json={"task": "pick a db", "mode": "standard",
                                      "options": {"demo": True, "auto_delegate": True}})
            self.assertEqual(r.status_code, 200)
            rid = r.json()["run_id"]
            with c.stream("GET", f"/runs/{rid}/events") as resp:
                self.assertTrue(resp.headers["content-type"].startswith("text/event-stream"))
                body = "".join(resp.iter_text())
            evs = parse_sse(body)
            self.assertTrue(evs)
            self.assertEqual(evs[-1]["type"], "run.completed")
            seqs = [e["seq"] for e in evs]
            self.assertEqual(seqs, sorted(seqs))

            snap = c.get(f"/runs/{rid}").json()
            self.assertEqual(snap["run_id"], rid)
            self.assertEqual(snap["state"], "DONE")

            mid = seqs[len(seqs) // 2]
            with c.stream("GET", f"/runs/{rid}/events?since={mid}") as resp:
                again = parse_sse("".join(resp.iter_text()))
            self.assertTrue(all(e["seq"] > mid for e in again))

            self.assertEqual(c.get("/router/preview", params={"task": "x"}).status_code, 200)
            models = c.get("/models").json()
            self.assertTrue(models)
            self.assertIn(c.post(f"/models/{models[0]['id']}/load").status_code, (200, 409))
            self.assertEqual(c.post("/models/zzz/load").status_code, 404)
            self.assertEqual(c.get("/chronicle").status_code, 200)
            self.assertEqual(c.get("/telemetry").status_code, 200)


class ApiServerExtraTest(unittest.TestCase):
    def test_new_endpoints(self):
        ctrl = RunController.build_mock(speed=500.0)
        with TestClient(create_app(ctrl)) as c:
            self.assertIsInstance(c.get("/runs").json(), list)
            self.assertIn("gateway", c.get("/config").json())
            self.assertEqual(c.get("/corrections", params={"project": "p"}).json(), [])
            self.assertIsInstance(c.get("/probes").json(), list)
            self.assertEqual(c.post("/probes/zzz/train").status_code, 404)
            r = c.get("/chronicle/export", params={"project": "p"})
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.headers["content-type"].startswith("text/markdown"))
            self.assertEqual(c.get("/bench/runs/nope").status_code, 404)
            mid = c.get("/models").json()[0]["id"]
            self.assertEqual(c.post(f"/models/{mid}/load").status_code, 200)
            self.assertEqual(c.post(f"/models/{mid}/unload").status_code, 200)
            r = c.post("/bench/runs", json={"limit": 1})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(c.get(f"/bench/runs/{r.json()['bench_id']}").status_code, 200)

    def test_default_controller_follows_config(self):
        import council.api.server as srv
        seen = {}

        def fake(cls, **kw):
            seen.update(kw)
            return "ctrl"

        with mock.patch.object(RunController, "build_from_config", classmethod(fake)):
            self.assertEqual(srv._default_controller(), "ctrl")
        self.assertTrue(str(seen["db_path"]).endswith("council.db"))

    def test_health_reports_real_driver(self):
        ctrl = RunController.build_mock(speed=500.0)
        with TestClient(create_app(ctrl)) as c:
            ctrl.mock = False
            ctrl.config.host.driver = "ollama"
            self.assertEqual(c.get("/health").json(),
                             {"ok": True, "mock": False, "driver": "ollama"})
            ctrl.mock = True


class SseLiveTest(unittest.TestCase):
    def test_stream_carries_deltas_and_resumes(self):
        ctrl = RunController.build_mock(speed=40.0)
        with TestClient(create_app(ctrl)) as c:
            rid = c.post("/runs", json={"task": "pick a db", "options": {
                "demo": True, "auto_delegate": True}}).json()["run_id"]
            with c.stream("GET", f"/runs/{rid}/events") as resp:
                evs = parse_sse("".join(resp.iter_text()))
            kinds = [e["type"] for e in evs]
            self.assertIn("turn.delta", kinds)  # never stored: it came through the bus
            self.assertEqual(kinds[-1], "run.completed")
            self.assertEqual(kinds.count("run.completed"), 1)
            seqs = [e["seq"] for e in evs]
            self.assertEqual(seqs, sorted(seqs))
            stored = [e for e in evs if not e["type"].endswith("delta")]
            self.assertEqual([e["seq"] for e in stored], list(range(1, len(stored) + 1)))

            # The run is over: a replay holds the stored events only, then closes.
            mid = stored[len(stored) // 2]["seq"]
            with c.stream("GET", f"/runs/{rid}/events?since={mid}") as resp:
                again = parse_sse("".join(resp.iter_text()))
            self.assertEqual([e["seq"] for e in again], list(range(mid + 1, len(stored) + 1)))
            self.assertNotIn("turn.delta", [e["type"] for e in again])
            with c.stream("GET", f"/runs/{rid}/events",
                          headers={"Last-Event-ID": str(len(stored) - 1)}) as resp:
                tail = parse_sse("".join(resp.iter_text()))
            self.assertEqual([e["type"] for e in tail], ["run.completed"])
            with c.stream("GET", f"/runs/{rid}/events?since={len(stored)}") as resp:
                self.assertEqual(parse_sse("".join(resp.iter_text())), [])


class PlanPatchTest(unittest.TestCase):
    def test_patch_goes_through_lint(self):
        ctrl = RunController.build_mock(home=HOME, speed=100000.0)
        with TestClient(create_app(ctrl)) as c:
            self.assertEqual(c.patch("/runs/nope/plan", json={"goal": "x"}).status_code, 404)
            rid = c.post("/runs", json={
                "task": "Plan a small CLI todo app.", "mode": "quick", "deliverable": "plan",
                "lineup_override": SMALL, "options": {"seed": 3}}).json()["run_id"]
            self.assertEqual(c.patch(f"/runs/{rid}/plan", json={"goal": "early"}).status_code, 409)

            snap = self._wait_state(c, rid, "AWAITING_DELEGATION")
            self.assertEqual(snap["state"], "AWAITING_DELEGATION", snap.get("error"))
            before = ctrl.store.plan_version(rid)

            bad = c.patch(f"/runs/{rid}/plan", json={"tasks": []})
            self.assertEqual(bad.status_code, 422)
            self.assertFalse(bad.json()["ok"])
            self.assertTrue(bad.json()["issues"])
            self.assertEqual(set(bad.json()["issues"][0]), {"code", "task_id", "message"})
            self.assertEqual(c.patch(f"/runs/{rid}/plan", json={"tasks": "x"}).status_code, 422)
            self.assertEqual(ctrl.store.plan_version(rid), before)  # nothing stored

            good = c.patch(f"/runs/{rid}/plan", json={"goal": "Edited goal"})
            self.assertEqual(good.status_code, 200)
            self.assertEqual(good.json()["issues"], [])
            self.assertEqual(good.json()["plan"]["goal"], "Edited goal")
            self.assertEqual(ctrl.store.plan_version(rid), before + 1)
            self.assertEqual(c.get(f"/runs/{rid}").json()["plan"]["goal"], "Edited goal")

            self.assertEqual(c.post(f"/runs/{rid}/delegate").status_code, 200)
            snap = self._wait_state(c, rid, "DONE")
            self.assertEqual(snap["state"], "DONE", snap.get("error"))
            self.assertEqual(c.patch(f"/runs/{rid}/plan", json={"goal": "late"}).status_code, 409)

    def _wait_state(self, c, rid, want, timeout=60.0):
        end = time.monotonic() + timeout
        snap = {}
        while time.monotonic() < end:
            snap = c.get(f"/runs/{rid}").json()
            if snap["state"] == want or snap["state"] in ("DONE", "FAILED", "CANCELLED"):
                break
            ask = snap.get("pending_input")
            if ask:
                c.post(f"/runs/{rid}/input",
                       json={"request_id": ask.get("request_id") or "", "choice": "go"})
            time.sleep(0.01)
        return snap


if __name__ == "__main__":
    unittest.main()
