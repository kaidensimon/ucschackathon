"""1.5 end to end, API smoke in mock mode: the real app, real controller, TestClient."""

import unittest

from fastapi.testclient import TestClient

from council.api.controller import RunController
from council.api.server import create_app


def _run_to_end(c: TestClient, options: dict) -> str:
    r = c.post("/runs", json={"task": "pick a database for a small app", "mode": "standard", "options": options})
    assert r.status_code == 200, r.text
    rid = r.json()["run_id"]
    with c.stream("GET", f"/runs/{rid}/events") as resp:
        "".join(resp.iter_text())
    return rid


class ApiRoutesE2ETest(unittest.TestCase):
    def test_every_plain_get_route_answers_200(self):
        ctrl = RunController.build_mock(speed=500.0)
        paths = [
            "/health", "/runs", "/models", "/chronicle", "/telemetry", "/corrections",
            "/probes", "/probes/cards", "/steer", "/chronicle/export", "/config",
            "/system/models", "/system/memory", "/system/specdec", "/system/measured",
            "/router/preview?task=pick%20a%20database",
        ]
        with TestClient(create_app(ctrl)) as c:
            for p in paths:
                r = c.get(p)
                self.assertEqual(r.status_code, 200, f"{p} -> {r.status_code} {r.text[:200]}")
            self.assertTrue(c.get("/health").json()["mock"])
            self.assertTrue(c.get("/models").json())
            self.assertIsInstance(c.get("/steer").json(), list)
            self.assertIsInstance(c.get("/probes/cards").json(), list)

    def test_unknown_ids_are_404(self):
        ctrl = RunController.build_mock(speed=500.0)
        with TestClient(create_app(ctrl)) as c:
            for p in ("/runs/nope", "/runs/nope/summary", "/runs/nope/events", "/lies/nope",
                      "/bench/runs/nope"):
                self.assertEqual(c.get(p).status_code, 404, p)

    def test_post_run_with_k3_reaches_done_with_three_seats(self):
        ctrl = RunController.build_mock(speed=500.0)
        with TestClient(create_app(ctrl)) as c:
            rid = _run_to_end(c, {"auto_delegate": True, "k": 3, "effort": "low"})
            snap = c.get(f"/runs/{rid}")
            self.assertEqual(snap.status_code, 200)
            body = snap.json()
            self.assertEqual(body["state"], "DONE")
            seats = body["lineup"]["seats"]
            self.assertEqual(len(seats), 3, seats)
            ids = [s["model_id"] for s in seats]
            self.assertEqual(len(set(ids)), 3)
            known = {m["id"] for m in c.get("/models").json()}
            self.assertTrue(set(ids) <= known)

    def test_summary_route_matches_run(self):
        ctrl = RunController.build_mock(speed=500.0)
        with TestClient(create_app(ctrl)) as c:
            rid = _run_to_end(c, {"auto_delegate": True, "k": 3, "effort": "low"})
            s = c.get(f"/runs/{rid}/summary")
            self.assertEqual(s.status_code, 200)
            body = s.json()
            for key in ("run_id", "lineup", "rounds", "decision", "tasks", "failures", "tokens", "wall_s"):
                self.assertIn(key, body)
            self.assertEqual(body["run_id"], rid)
            self.assertEqual(body["state"], "DONE")
            self.assertEqual(len(body["lineup"]), 3, body["lineup"])

    def test_k_sizes_2_and_6_give_that_many_seats(self):
        for k in (2, 6):
            ctrl = RunController.build_mock(speed=500.0)
            with TestClient(create_app(ctrl)) as c:
                rid = _run_to_end(c, {"auto_delegate": True, "k": k, "effort": "low"})
                body = c.get(f"/runs/{rid}").json()
                self.assertEqual(body["state"], "DONE", f"k={k}")
                self.assertEqual(len(body["lineup"]["seats"]), k, f"k={k}")

    def test_system_and_probe_card_shapes(self):
        ctrl = RunController.build_mock(speed=500.0)
        with TestClient(create_app(ctrl)) as c:
            mem = c.get("/system/memory").json()
            self.assertIn("meminfo", mem)
            self.assertIn("plan", mem)
            self.assertIsInstance(c.get("/system/specdec").json(), list)
            self.assertIsInstance(c.get("/system/measured").json(), dict)
            rows = c.get("/system/models").json()
            self.assertEqual(len(rows), len(c.get("/models").json()))
            mid = ctrl.registry[0].id
            self.assertEqual(c.post(f"/probes/cards/{mid}/train").status_code, 200)
            self.assertEqual([x["model_id"] for x in c.get("/probes/cards").json()], [mid])


if __name__ == "__main__":
    unittest.main()
