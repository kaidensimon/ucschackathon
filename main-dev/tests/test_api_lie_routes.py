import unittest
from typing import Optional

from fastapi import FastAPI
from fastapi.testclient import TestClient

from council.api.lie_routes import CAVEAT, LieProvider, make_router
from council.core.schemas_v15 import LieFlag, LieReport, ProbeCard


class FakeProvider:
    def __init__(self, with_text: bool = False):
        self.cards = {
            "qwen3:8b": ProbeCard(model_id="qwen3:8b", auroc=0.8, active=False),
            "org/model:1b": ProbeCard(model_id="org/model:1b", active=True),
        }
        self.trained: list[str] = []
        if with_text:
            self.report_text = lambda run_id: f"TEXT for {run_id}"

    def lie_report(self, run_id: str) -> Optional[LieReport]:
        if run_id != "r1":
            return None
        return LieReport(run_id="r1", flags=[LieFlag(claim_id="c1", level="flag")], note="n")

    def probe_cards(self) -> list[ProbeCard]:
        return list(self.cards.values())

    async def train(self, model_id: str) -> ProbeCard:
        self.trained.append(model_id)
        return self.cards.get(model_id) or ProbeCard(model_id=model_id, version=2)

    async def train_all(self) -> list[ProbeCard]:
        self.trained.append("*")
        return list(self.cards.values())

    def set_active(self, model_id: str, active: bool) -> Optional[ProbeCard]:
        card = self.cards.get(model_id)
        if card is None:
            return None
        card.active = active
        return card


def client(provider) -> TestClient:
    app = FastAPI()
    app.include_router(make_router(provider))
    return TestClient(app)


class LieRoutesTest(unittest.TestCase):
    def test_protocol_matches_fake(self):
        self.assertIsInstance(FakeProvider(), LieProvider)

    def test_report_ok_has_caveat(self):
        r = client(FakeProvider()).get("/lies/r1")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["run_id"], "r1")
        self.assertEqual(body["flags"][0]["level"], "flag")
        self.assertEqual(body["caveat"], CAVEAT)

    def test_report_404(self):
        self.assertEqual(client(FakeProvider()).get("/lies/nope").status_code, 404)

    def test_text_fallback_is_json(self):
        r = client(FakeProvider()).get("/lies/r1/text")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers["content-type"].startswith("text/plain"))
        self.assertIn('"run_id": "r1"', r.text)

    def test_text_uses_provider(self):
        r = client(FakeProvider(with_text=True)).get("/lies/r1/text")
        self.assertEqual(r.text, "TEXT for r1")

    def test_text_404(self):
        self.assertEqual(client(FakeProvider()).get("/lies/nope/text").status_code, 404)

    def test_cards_list(self):
        r = client(FakeProvider()).get("/probes/cards")
        self.assertEqual([c["model_id"] for c in r.json()], ["qwen3:8b", "org/model:1b"])

    def test_train_one_with_slash_id(self):
        p = FakeProvider()
        r = client(p).post("/probes/cards/org/model:1b/train")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["model_id"], "org/model:1b")
        self.assertEqual(p.trained, ["org/model:1b"])

    def test_train_all(self):
        p = FakeProvider()
        r = client(p).post("/probes/train_all")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 2)
        self.assertEqual(p.trained, ["*"])

    def test_patch_active(self):
        p = FakeProvider()
        r = client(p).patch("/probes/cards/qwen3:8b", json={"active": True})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["active"])
        self.assertTrue(p.cards["qwen3:8b"].active)

    def test_patch_slash_id(self):
        r = client(FakeProvider()).patch("/probes/cards/org/model:1b", json={"active": False})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["active"])

    def test_patch_404(self):
        r = client(FakeProvider()).patch("/probes/cards/ghost", json={"active": True})
        self.assertEqual(r.status_code, 404)

    def test_patch_bad_body(self):
        c = client(FakeProvider())
        self.assertEqual(c.patch("/probes/cards/qwen3:8b", json={}).status_code, 422)
        self.assertEqual(c.patch("/probes/cards/qwen3:8b", json={"active": "yes"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
