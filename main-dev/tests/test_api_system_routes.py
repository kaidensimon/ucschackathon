import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from council.api.system_routes import SystemProvider, make_router
from council.core.schemas_v15 import DraftPair, MeasuredModel, MemoryPlan


class FakeProvider:
    def __init__(self, fail=()):
        self.fail = set(fail)

    def _maybe(self, name):
        if name in self.fail:
            raise RuntimeError(f"{name} boom")

    def model_cards(self):
        self._maybe("model_cards")
        return [{"id": "m1", "size_gib": 4.5}, {"id": "m2", "size_gib": 9.0}]

    def memory_plan(self):
        self._maybe("memory_plan")
        return MemoryPlan(fits=True, budget_gib=100.0, total_gib=128.0, per_model={"m1": 5.0},
                          roles={"planner": "m1"}, notes=["ok"])

    def draft_pairs(self):
        self._maybe("draft_pairs")
        return [DraftPair(target_id="m2", draft_id="m1", family="f", size_ratio=0.5, verified=True, speedup=1.8)]

    def meminfo(self):
        self._maybe("meminfo")
        return {"total_gib": 128.0, "available_gib": 90.0, "used_gib": 38.0, "swap_used_gib": 0.0}

    def measured(self):
        self._maybe("measured")
        return {"m1": MeasuredModel(model_id="m1", tag="m1:q4", ram_gib=4.8, tps=55.0, json_ok=True)}


def client(fail=()):
    app = FastAPI()
    app.include_router(make_router(FakeProvider(fail)))
    return TestClient(app)


class TestSystemRoutes(unittest.TestCase):
    def test_protocol_matches_fake(self):
        self.assertIsInstance(FakeProvider(), SystemProvider)

    def test_models(self):
        r = client().get("/system/models")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([c["id"] for c in r.json()], ["m1", "m2"])

    def test_memory(self):
        r = client().get("/system/memory")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["meminfo"]["total_gib"], 128.0)
        self.assertEqual(body["plan"]["roles"], {"planner": "m1"})
        self.assertTrue(body["plan"]["fits"])

    def test_specdec(self):
        r = client().get("/system/specdec")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]["target_id"], "m2")
        self.assertEqual(r.json()[0]["speedup"], 1.8)

    def test_measured(self):
        r = client().get("/system/measured")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["m1"]["ram_gib"], 4.8)
        self.assertTrue(r.json()["m1"]["json_ok"])

    def test_failure_is_503_for_that_route_only(self):
        c = client(fail={"draft_pairs"})
        r = c.get("/system/specdec")
        self.assertEqual(r.status_code, 503)
        self.assertIn("draft_pairs", r.json()["detail"])
        self.assertIn("boom", r.json()["detail"])
        self.assertEqual(c.get("/system/models").status_code, 200)
        self.assertEqual(c.get("/system/measured").status_code, 200)

    def test_memory_failure_either_part(self):
        for part in ("meminfo", "memory_plan"):
            r = client(fail={part}).get("/system/memory")
            self.assertEqual(r.status_code, 503)
            self.assertIn("detail", r.json())

    def test_models_and_measured_failure(self):
        self.assertEqual(client(fail={"model_cards"}).get("/system/models").status_code, 503)
        self.assertEqual(client(fail={"measured"}).get("/system/measured").status_code, 503)


if __name__ == "__main__":
    unittest.main()
