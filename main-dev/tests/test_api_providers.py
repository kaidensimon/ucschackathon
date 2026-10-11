import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException

from council.api import providers
from council.api.controller import RunController
from council.core import event_types as ET
from council.core.schemas import Event, ModelEntry, Probe
from council.core.schemas_v15 import LieFlag, LieReport, ProbeCard
from council.probe.probe_files import ProbeFiles


def run(coro):
    return asyncio.run(coro)


class FakeService:
    source = object()

    def __init__(self, report=None, cards=None):
        self._report, self._cards, self.trained = report, cards, []

    def last_report(self, run_id):
        return self._report

    def cards(self):
        if self._cards is None:
            raise RuntimeError("boom")
        return self._cards

    async def train_for(self, model_id, tasks, now):
        self.trained.append((model_id, len(tasks)))
        return Probe(model_id=model_id, layer=12, auroc=0.9, n_train=40, trained_at=now, status="validated")


class FakeStore:
    def __init__(self, events):
        self.events = events

    def events_since(self, run_id, since, limit=5000):
        return [e for e in self.events if e.seq > since][:limit]


def entry(mid, **kw):
    return ModelEntry(id=mid, ollama_tag=mid + ":tag", roles=["seat"], **kw)


class LieProviderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.files = ProbeFiles(Path(self.tmp.name))

    def test_report_from_service(self):
        rep = LieReport(run_id="r1", flags=[LieFlag(claim_id="c1")])
        p = providers.LieProviderImpl(FakeService(report=rep))
        self.assertEqual(p.lie_report("r1").run_id, "r1")
        self.assertIn("lie report r1", p.report_text("r1"))

    def test_report_service_without_method_uses_events(self):
        rep = LieReport(run_id="r2", note="n")
        ev = Event(type=ET.LIE_REPORT, seq=1, run_id="r2", payload={"report": rep.model_dump(mode="json")})
        p = providers.LieProviderImpl(SimpleNamespace(), store=FakeStore([ev]))
        self.assertEqual(p.lie_report("r2").note, "n")
        self.assertIsNone(providers.LieProviderImpl(SimpleNamespace()).lie_report("r2"))
        self.assertIsNone(providers.LieProviderImpl(None, store=FakeStore([])).lie_report("r2"))

    def test_report_service_raises_gives_none(self):
        class Bad:
            def last_report(self, run_id):
                raise RuntimeError("x")

        self.assertIsNone(providers.LieProviderImpl(Bad()).lie_report("r"))

    def test_cards_service_then_files(self):
        c = ProbeCard(model_id="a", active=True)
        self.assertEqual(providers.LieProviderImpl(FakeService(cards=[c])).probe_cards(), [c])
        self.files.save(ProbeCard(model_id="b", active=True), [])
        got = providers.LieProviderImpl(FakeService(cards=None), probe_files=self.files).probe_cards()
        self.assertEqual([x.model_id for x in got], ["b"])
        self.assertEqual(providers.LieProviderImpl(None).probe_cards(), [])

    def test_train_saves_card(self):
        svc = FakeService()
        p = providers.LieProviderImpl(svc, probe_files=self.files, registry=[entry("m1")])
        card = run(p.train("m1"))
        self.assertEqual((card.model_id, card.active, card.version, card.layers), ("m1", True, 1, [12]))
        self.assertEqual(svc.trained[0][0], "m1")
        self.assertGreater(svc.trained[0][1], 0)
        self.assertEqual([c.model_id for c in self.files.cards()], ["m1"])

    def test_train_errors(self):
        p = providers.LieProviderImpl(FakeService(), registry=[entry("m1")])
        with self.assertRaises(HTTPException) as cm:
            run(p.train("zzz"))
        self.assertEqual(cm.exception.status_code, 404)
        off = providers.LieProviderImpl(None, registry=[entry("m1")])
        with self.assertRaises(HTTPException) as cm:
            run(off.train("m1"))
        self.assertEqual(cm.exception.status_code, 409)

    def test_train_all_failure_becomes_inactive_card(self):
        p = providers.LieProviderImpl(FakeService(), probe_files=self.files,
                                      registry=[entry("m1"), entry("m2")])

        async def flaky(model_id):
            if model_id == "m2":
                raise RuntimeError("no gpu")
            return ProbeCard(model_id=model_id, active=True)

        p.train = flaky
        cards = run(p.train_all())
        self.assertEqual([(c.model_id, c.active) for c in cards], [("m1", True), ("m2", False)])
        self.assertTrue(cards[1].reason.startswith("training failed"))

    def test_set_active(self):
        p = providers.LieProviderImpl(FakeService(), probe_files=self.files)
        self.assertIsNone(p.set_active("a", True))
        self.files.save(ProbeCard(model_id="a", active=True), [])
        off = p.set_active("a", False)
        self.assertFalse(off.active)
        self.assertFalse(self.files.cards()[0].active)
        self.assertTrue(p.set_active("a", True).active)
        self.assertTrue(self.files.cards()[0].active)
        self.assertIsNone(providers.LieProviderImpl(FakeService()).set_active("a", True))


class SystemProviderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

    def deps(self, registry, resident=(), memory=None):
        status = [{"model_id": m, "footprint_gib": 12.0, "profile": "live", "idle": True, "endpoint": None}
                  for m in resident]
        cfg = RunController.build_mock(speed=500.0).config
        if memory:
            cfg.memory = cfg.memory.model_copy(update=memory)
        return SimpleNamespace(host=SimpleNamespace(status=lambda: status), registry=registry,
                               config=cfg, data_home=self.home)

    def test_measured_cards_and_resident(self):
        (self.home / "model_checks.json").write_text(json.dumps(
            {"m1:tag": {"ok": True, "ram_gib": 16.5, "tps": 30.0, "json_ok": True, "think_ok": False}}))
        s = providers.SystemProviderImpl(self.deps([entry("m1"), entry("m2")], resident=["m2"]))
        self.assertEqual(list(s.measured()), ["m1"])
        cards = {c["id"]: c for c in s.model_cards()}
        self.assertEqual(cards["m1"]["memory_gib"], 16.5)
        self.assertEqual(cards["m1"]["tps"], 30.0)
        self.assertTrue(cards["m2"]["resident"])
        self.assertFalse(cards["m1"]["resident"])
        self.assertIsNone(cards["m1"]["probe"])

    def test_measured_file_from_config(self):
        other = self.home / "elsewhere.json"
        other.write_text(json.dumps({"m1:tag": {"ok": True, "ram_gib": 9.0}}))
        s = providers.SystemProviderImpl(self.deps([entry("m1")], memory={"measured_file": str(other)}))
        self.assertEqual(s.measured()["m1"].ram_gib, 9.0)
        self.assertEqual(providers.SystemProviderImpl(self.deps([entry("m1")])).measured(), {})

    def test_probe_cards_callable_feeds_cards(self):
        pc = ProbeCard(model_id="m1", auroc=0.91, active=True)
        s = providers.SystemProviderImpl(self.deps([entry("m1")]), lambda: [pc])
        self.assertEqual(s.model_cards()[0]["probe"]["auroc"], 0.91)

    def test_memory_plan_for_residents(self):
        reg = [entry(f"m{i}") for i in range(3)]
        s = providers.SystemProviderImpl(self.deps(reg, resident=["m0", "m1", "m2"]))
        plan = s.memory_plan()
        self.assertTrue(plan.fits)
        self.assertEqual(set(plan.per_model), {"m0", "m1", "m2"})
        self.assertIn("planner", plan.roles)
        self.assertEqual(plan.total_gib, s.meminfo()["total_gib"])

    def test_memory_plan_empty_and_meminfo(self):
        s = providers.SystemProviderImpl(self.deps([entry("m1")]))
        plan = s.memory_plan()
        self.assertEqual(plan.per_model, {})
        self.assertTrue(any("No model is resident" in n for n in plan.notes))
        info = s.meminfo()
        self.assertEqual(set(info), {"total_gib", "available_gib", "used_gib", "swap_used_gib"})
        self.assertGreater(info["total_gib"], 0)

    def test_memory_plan_does_not_fit(self):
        reg = [entry(f"m{i}") for i in range(2)]
        deps = self.deps(reg, resident=["m0", "m1"])
        deps.host.status = lambda: [{"model_id": m, "footprint_gib": 500.0} for m in ("m0", "m1")]
        self.assertFalse(providers.SystemProviderImpl(deps).memory_plan().fits)

    def test_draft_pairs_same_family(self):
        reg = [entry("big", params_b=32.0, lineage="qwen"), entry("small", params_b=4.0, lineage="qwen"),
               entry("other", params_b=3.0, lineage="llama")]
        pairs = providers.SystemProviderImpl(self.deps(reg)).draft_pairs()
        self.assertEqual([(p.target_id, p.draft_id) for p in pairs], [("big", "small")])

    def test_steer_cards_without_module_is_empty(self):
        self.assertIsInstance(providers.steer_cards(SimpleNamespace(data_home=self.home)), list)


if __name__ == "__main__":
    unittest.main()
