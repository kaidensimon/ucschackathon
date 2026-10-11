import json
import unittest

from council.core.schemas import MeasuredStats, ModelEntry
from council.core.schemas_v15 import MeasuredModel, ProbeCard
from council.telemetry.model_cards import build_cards, cards_text


def _reg():
    return [
        ModelEntry(id="zeta", display="Zeta", lab="zlab", params_b=7, quant="q4",
                   ollama_tag="zeta:7b",
                   measured=MeasuredStats(ram_gb_live=5.0, tps_1=30.0, structured_valid_rate=0.95)),
        ModelEntry(id="alpha", display="Alpha", lab="alab", params_b=20, quant="q8",
                   ollama_tag="alpha:20b"),
        ModelEntry(id="beta", display="Beta", lab="alab", params_b=3),
    ]


class TestModelCards(unittest.TestCase):
    def test_sort_resident_then_lab_then_id(self):
        cards = build_cards(_reg(), resident={"zeta"})
        self.assertEqual([c["id"] for c in cards], ["zeta", "alpha", "beta"])
        self.assertTrue(cards[0]["resident"])
        self.assertFalse(cards[1]["resident"])

    def test_sort_no_resident(self):
        cards = build_cards(_reg())
        self.assertEqual([c["id"] for c in cards], ["alpha", "beta", "zeta"])

    def test_registry_fallback(self):
        z = [c for c in build_cards(_reg()) if c["id"] == "zeta"][0]
        self.assertEqual(z["memory_gib"], 5.0)
        self.assertEqual(z["tps"], 30.0)
        self.assertTrue(z["json_ok"])
        self.assertIsNone(z["think_ok"])
        self.assertEqual(z["ollama_tag"], "zeta:7b")

    def test_measured_wins(self):
        meas = {"zeta": MeasuredModel(model_id="zeta", ram_gib=6.5, tps=44.0, json_ok=False, think_ok=True)}
        z = [c for c in build_cards(_reg(), measured=meas) if c["id"] == "zeta"][0]
        self.assertEqual(z["memory_gib"], 6.5)
        self.assertEqual(z["tps"], 44.0)
        self.assertFalse(z["json_ok"])
        self.assertTrue(z["think_ok"])

    def test_measured_none_falls_back(self):
        meas = {"zeta": MeasuredModel(model_id="zeta", ram_gib=None, tps=None)}
        z = [c for c in build_cards(_reg(), measured=meas) if c["id"] == "zeta"][0]
        self.assertEqual(z["memory_gib"], 5.0)
        self.assertEqual(z["tps"], 30.0)

    def test_unknown_values_are_none(self):
        b = [c for c in build_cards(_reg()) if c["id"] == "beta"][0]
        self.assertIsNone(b["memory_gib"])
        self.assertIsNone(b["tps"])
        self.assertIsNone(b["json_ok"])
        self.assertIsNone(b["probe"])

    def test_stats(self):
        stats = {"alpha": {"runs": 10, "on_winning_side": 7, "chaired": 2}, "beta": {}}
        cards = {c["id"]: c for c in build_cards(_reg(), stats=stats)}
        self.assertEqual((cards["alpha"]["runs"], cards["alpha"]["wins"], cards["alpha"]["chaired"]), (10, 7, 2))
        self.assertEqual(cards["alpha"]["win_rate"], 0.7)
        self.assertEqual((cards["beta"]["runs"], cards["beta"]["wins"], cards["beta"]["chaired"]), (0, 0, 0))
        self.assertEqual(cards["beta"]["win_rate"], 0.0)
        self.assertEqual(cards["zeta"]["win_rate"], 0.0)

    def test_probe_newest_version(self):
        pcs = [
            ProbeCard(model_id="alpha", version=1, auroc=0.6, active=False),
            ProbeCard(model_id="alpha", version=2, auroc=0.81, active=True),
        ]
        a = [c for c in build_cards(_reg(), probe_cards=pcs) if c["id"] == "alpha"][0]
        self.assertEqual(a["probe"], {"active": True, "auroc": 0.81, "version": 2})

    def test_json_safe(self):
        meas = {"zeta": MeasuredModel(model_id="zeta", ram_gib=float("nan"), tps=float("inf"))}
        stats = {"zeta": {"runs": "bad", "on_winning_side": None}}
        cards = build_cards(_reg(), measured=meas, stats=stats,
                            probe_cards=[ProbeCard(model_id="zeta", auroc=0.7, active=True)],
                            resident={"zeta"})
        text = json.dumps(cards, allow_nan=False)
        self.assertIn("zeta", text)
        z = cards[0]
        self.assertEqual(z["memory_gib"], 5.0)
        self.assertEqual(z["runs"], 0)

    def test_empty(self):
        self.assertEqual(build_cards([]), [])
        self.assertIn("model", cards_text([]))

    def test_cards_text(self):
        pcs = [ProbeCard(model_id="alpha", version=1, auroc=0.8, active=True)]
        cards = build_cards(_reg(), stats={"alpha": {"runs": 4, "on_winning_side": 3, "chaired": 1}},
                            probe_cards=pcs, resident={"alpha"})
        text = cards_text(cards)
        lines = text.splitlines()
        self.assertEqual(len(lines), 2 + 3)
        self.assertTrue(lines[0].startswith("model"))
        self.assertTrue(lines[2].startswith("alpha"))
        self.assertIn("on 0.80", lines[2])
        self.assertIn("75", lines[2])


if __name__ == "__main__":
    unittest.main()
