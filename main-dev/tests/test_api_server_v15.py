import unittest

from fastapi.testclient import TestClient

from council.api.controller import RunController
from council.api.server import create_app


class ApiServerV15Test(unittest.TestCase):
    def test_summary_and_system_routes(self):
        ctrl = RunController.build_mock(speed=500.0)
        with TestClient(create_app(ctrl)) as c:
            self.assertEqual(c.get("/runs/nope/summary").status_code, 404)
            r = c.post("/runs", json={"task": "pick a db", "mode": "standard", "options": {
                "demo": True, "auto_delegate": True, "k": 3, "effort": "low"}})
            self.assertEqual(r.status_code, 200)
            rid = r.json()["run_id"]
            with c.stream("GET", f"/runs/{rid}/events") as resp:
                "".join(resp.iter_text())
            s = c.get(f"/runs/{rid}/summary")
            self.assertEqual(s.status_code, 200)
            body = s.json()
            for key in ("run_id", "lineup", "rounds", "decision", "tasks", "failures", "tokens", "wall_s"):
                self.assertIn(key, body)
            self.assertEqual(body["run_id"], rid)
            self.assertTrue(body["lineup"])
            self.assertEqual(body["state"], "DONE")

            self.assertEqual(c.get("/steer").json(), [])
            models = c.get("/system/models")
            self.assertEqual(models.status_code, 200)
            self.assertTrue(models.json())
            mem = c.get("/system/memory").json()
            self.assertIn("total_gib", mem["meminfo"])
            self.assertIn("fits", mem["plan"])
            self.assertIsInstance(c.get("/system/specdec").json(), list)
            self.assertIsInstance(c.get("/system/measured").json(), dict)

    def test_lie_routes_mounted_before_old_probe_route(self):
        ctrl = RunController.build_mock(speed=500.0)
        with TestClient(create_app(ctrl)) as c:
            self.assertEqual(c.get("/probes/cards").status_code, 200)
            self.assertIsInstance(c.get("/probes/cards").json(), list)
            self.assertEqual(c.get("/lies/nope").status_code, 404)
            self.assertEqual(c.patch("/probes/cards/zzz", json={"active": True}).status_code, 404)
            self.assertEqual(c.patch("/probes/cards/zzz", json={"active": "x"}).status_code, 422)
            # not swallowed by /probes/{model_id:path}/train: an unknown model is the lie route's 404
            r = c.post("/probes/cards/zzz/train")
            self.assertEqual(r.status_code, 404)
            self.assertIn("model not found", r.json()["detail"])
            # the older route still answers
            self.assertEqual(c.post("/probes/zzz/train").status_code, 404)
            self.assertIsInstance(c.get("/probes").json(), list)

    def test_train_and_toggle_card(self):
        ctrl = RunController.build_mock(speed=500.0)
        mid = ctrl.registry[0].id
        with TestClient(create_app(ctrl)) as c:
            r = c.post(f"/probes/cards/{mid}/train")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["model_id"], mid)
            cards = c.get("/probes/cards").json()
            self.assertEqual([x["model_id"] for x in cards], [mid])
            off = c.patch(f"/probes/cards/{mid}", json={"active": False})
            self.assertEqual(off.status_code, 200)
            self.assertFalse(off.json()["active"])
            self.assertFalse(c.get("/probes/cards").json()[0]["active"])
            on = c.patch(f"/probes/cards/{mid}", json={"active": True})
            self.assertTrue(on.json()["active"])
            cards = c.get("/system/models").json()
            row = next(x for x in cards if x["id"] == mid)
            self.assertIsNotNone(row["probe"])


if __name__ == "__main__":
    unittest.main()
