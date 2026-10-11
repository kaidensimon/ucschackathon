import json
import shutil
import tempfile
import unittest
from pathlib import Path

from council.api.controller import RunController
from council.core import event_types as ET
from council.core.config import load_registry
from council.core.schemas import ModelEntry, RunRequest, RunState, TaskProfile
from council.host import discover
from council.router.competence import SkillTable
from council.router.picker import eligible_models, pick_with_notes

REPO = Path(__file__).resolve().parents[1]
GB = 10**9
LIST_TEXT = """NAME                       ID              SIZE      MODIFIED
gpt-oss:20b                aa4295ac10c3    13 GB     2 weeks ago
llama3.3:70b               a6eb4748fd29    42 GB     3 days ago
smollm2:135m               9077fe9d2ae1    270 MB    5 weeks ago
"""
UNKNOWN_SIX = ["llama3.3:70b", "zorg7:12b", "blip9:8b", "mistral-nemo:12b", "kraken:7b-q8_0", "command-r:35b"]


def add_model(store: Path, name: str, tag: str, size: int, projector: bool = False,
              registry: str = "registry.ollama.ai", namespace: str = "library") -> None:
    digest = "sha256:" + f"{abs(hash((name, tag))):064x}"[:64]
    layers = [{"mediaType": "application/vnd.ollama.image.model", "digest": digest, "size": size},
              {"mediaType": "application/vnd.ollama.image.template", "digest": "sha256:" + "1" * 64, "size": 9}]
    if projector:
        layers.append({"mediaType": "application/vnd.ollama.image.projector", "digest": "sha256:" + "2" * 64,
                       "size": 5})
    path = store / "manifests" / registry / namespace / name / tag
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schemaVersion": 2, "config": {"digest": "sha256:" + "3" * 64}, "layers": layers}))


class Store(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="council_discover_"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        add_model(self.dir, "qwen3", "14b", int(9.3 * GB))
        add_model(self.dir, "gpt-oss", "20b", 13 * GB)
        add_model(self.dir, "llama3.3", "70b", 42 * GB)
        add_model(self.dir, "llava", "13b", 8 * GB, projector=True)
        add_model(self.dir, "nomic-embed-text", "latest", GB // 4)
        add_model(self.dir, "Odd-Model", "7b", 5 * GB, registry="hf.co", namespace="someone")
        (self.dir / "manifests" / "registry.ollama.ai" / "library" / "qwen3" / "broken").write_text("{not json")

    def test_reads_the_manifests_folder(self):
        found = {t["tag"]: t for t in discover.installed_tags(self.dir, "")}
        self.assertEqual(set(found), {"qwen3:14b", "gpt-oss:20b", "llama3.3:70b", "llava:13b",
                                      "nomic-embed-text:latest", "hf.co/someone/Odd-Model:7b"})
        q = found["qwen3:14b"]
        self.assertEqual(q["size_gb"], 9.3)
        self.assertEqual(q["source"], "store")
        self.assertFalse(q["has_projector"])
        self.assertTrue(Path(q["blob"]).name.startswith("sha256-"))
        self.assertEqual(Path(q["blob"]).parent, self.dir / "blobs")
        self.assertTrue(found["llava:13b"]["has_projector"])

    def test_list_text_adds_what_the_folder_lacks(self):
        found = {t["tag"]: t for t in discover.installed_tags(self.dir, LIST_TEXT)}
        self.assertEqual(found["smollm2:135m"]["source"], "ollama list")
        self.assertEqual(found["gpt-oss:20b"]["source"], "store")  # the folder wins

    def test_missing_folder_never_raises(self):
        self.assertEqual(discover.installed_tags(self.dir / "nope", ""), [])
        self.assertEqual([t["tag"] for t in discover.installed_tags(self.dir / "nope", LIST_TEXT)],
                         ["gpt-oss:20b", "llama3.3:70b", "smollm2:135m"])

    def test_registry_from_the_folder(self):
        entries, notes = discover.build_registry(discover.installed_tags(self.dir, ""), None, {})
        by = {e["ollama_tag"]: e for e in entries}
        self.assertEqual([e["ollama_tag"] for e in entries[:2]], ["gpt-oss:20b", "qwen3:14b"])  # recommended first
        self.assertTrue(by["qwen3:14b"]["recommended"])
        self.assertFalse(by["llama3.3:70b"]["recommended"])
        self.assertEqual(by["llama3.3:70b"]["status"], "active")
        self.assertEqual(by["llava:13b"]["status"], "quarantined")
        self.assertIn("llama.cpp", by["llava:13b"]["note"])
        self.assertEqual(by["nomic-embed-text:latest"]["status"], "quarantined")
        self.assertIn("embedding", by["nomic-embed-text:latest"]["note"])
        text = "\n".join(notes)
        self.assertIn("6 models installed, 2 of the 8 recommended present", text)
        self.assertIn("recommended models not installed: qwen3.5:9b-q8_0", text)
        self.assertIn("The council seats 2 to 6 models: 4 usable", text)
        self.assertNotIn("at least 2 usable", text)
        self.assertEqual(len({e["id"] for e in entries}), len(entries))
        table = discover.table_text(entries, {"qwen3:14b": 9.3})
        self.assertIn("9.3 GB", table)
        self.assertIn("not seated", table)


class ListText(unittest.TestCase):
    def test_parse(self):
        rows = discover.parse_ollama_list(LIST_TEXT)
        self.assertEqual([r["tag"] for r in rows], ["gpt-oss:20b", "llama3.3:70b", "smollm2:135m"])
        self.assertEqual([r["size_gb"] for r in rows], [13.0, 42.0, 0.27])
        self.assertTrue(all(r["blob"] is None and r["has_projector"] is False for r in rows))
        self.assertEqual(discover.parse_ollama_list(""), [])
        self.assertEqual(discover.parse_ollama_list("NAME ID SIZE MODIFIED\n"), [])


class Entries(unittest.TestCase):
    def test_generic_entry(self):
        e = discover.entry_for({"tag": "llama3.3:70b", "size_gb": 42.0, "blob": None, "has_projector": False})
        self.assertEqual(e["id"], "llama3-3-70b")
        self.assertEqual(e["display"], "Llama 3.3 70B")
        self.assertEqual((e["lab"], e["lineage"]), ("meta", "llama3.3"))
        self.assertEqual(e["params_b"], 70.0)
        self.assertEqual(e["measured"]["ram_gb_live"], 54.0)
        self.assertIsNone(e["measured"]["tps_1"])
        self.assertEqual(e["roles"], ["seat"])
        self.assertEqual(e["reasoning"]["kind"], "none")
        self.assertEqual(e["structured"], "grammar")
        self.assertEqual(set(e["priors"].values()), {0.52})
        self.assertEqual((e["status"], e["recommended"], e["note"]), ("active", False, ""))
        m = ModelEntry.model_validate(e)
        self.assertEqual(m.ollama_tag, "llama3.3:70b")

    def test_generic_entry_has_the_shape_of_a_recommended_one(self):
        rec = discover.entry_for({"tag": "qwen3:14b"})
        gen = discover.entry_for({"tag": "zorg7:12b", "size_gb": 8.0})
        self.assertEqual(set(rec), set(gen))
        self.assertEqual(set(rec["measured"]), set(gen["measured"]))

    def test_guesses(self):
        lab = lambda t: discover.lab_of(t)[0]
        self.assertEqual([lab(t) for t in ("qwq:32b", "gemma3:4b", "phi3:mini", "mixtral:8x7b", "granite3:2b",
                                           "deepseek-coder:6b", "falcon2:11b", "command-r:35b", "aya:8b",
                                           "nemotron-mini:4b", "glm4:9b", "codellama:7b")],
                         ["alibaba", "google", "microsoft", "mistral", "ibm", "deepseek", "tii", "cohere",
                          "cohere", "nvidia", "zhipu", "meta"])
        self.assertEqual(discover.lab_of("zorg7:12b"), ("unknown:zorg", "zorg"))
        self.assertEqual(discover.params_of("gemma3n:e2b"), 2.0)
        self.assertEqual(discover.params_of("smollm2:135m"), 0.135)
        self.assertEqual(discover.params_of("thing:latest", 7.0), 10.0)       # 4-bit: GB / 0.7
        self.assertEqual(discover.params_of("thing:q8_0", 11.0), 10.0)        # 8-bit: GB / 1.1
        self.assertIsNone(discover.params_of("thing:latest"))
        self.assertEqual(discover.entry_for({"tag": "deepseek-r1:32b", "size_gb": 20})["reasoning"]["kind"], "always")
        self.assertEqual(discover.entry_for({"tag": "qwen3:32b", "size_gb": 20})["reasoning"]["kind"], "toggle")
        self.assertEqual(discover.entry_for({"tag": "gpt-oss:120b", "size_gb": 65})["reasoning"]["kind"], "effort")
        self.assertEqual(discover.entry_for({"tag": "thing:latest"})["status"], "quarantined")  # size unknown
        cloud = discover.entry_for({"tag": "gemma4:31b-cloud"})
        self.assertEqual(cloud["status"], "quarantined")
        self.assertIn("cloud", cloud["note"])

    def test_recommended_row_is_unchanged(self):
        e = discover.entry_for({"tag": "gpt-oss:20b", "size_gb": 13.0})
        self.assertEqual((e["id"], e["lab"], e["arch"], e["active_params_b"]), ("gpt-oss-20b", "openai", "moe", 3.6))
        self.assertEqual(e["measured"]["ram_gb_live"], 13.9)
        self.assertEqual(e["measured"]["tps_1"], 58.8)
        self.assertEqual(e["roles"], ["seat", "planner"])
        self.assertEqual(e["priors"]["logic"], .75)
        self.assertTrue(e["recommended"])
        self.assertEqual(discover.entry_for({"tag": "gpt-oss:20b"}, None, {})["structured"], "prompt_only")
        self.assertEqual(len(discover.RECOMMENDED), 8)
        # with equal fit the router prefers the recommended: every prior of theirs beats a generic one
        self.assertTrue(all(min({**discover.P, **r[11]}.values()) > 0.52 for r in discover.RECOMMENDED))

    def test_checks_and_llamacpp(self):
        gen = {"tag": "zorg7:12b", "size_gb": 8.0}
        e = discover.entry_for(gen, {"zorg7:12b": {"ok": True, "ram_gib": 9.9, "tps": 31.0, "json_ok": True}})
        self.assertEqual((e["measured"]["ram_gb_live"], e["measured"]["tps_1"]), (9.9, 31.0))
        self.assertEqual(e["measured"]["structured_valid_rate"], 1.0)
        bad = discover.entry_for(gen, None, {"zorg7:12b": {"load_error": "unknown architecture"}})
        self.assertEqual(bad["status"], "quarantined")
        self.assertIn("cannot load", bad["note"])
        failed = discover.entry_for(gen, {"zorg7:12b": {"ok": False, "error": "HTTP 500"}})
        self.assertEqual(failed["status"], "quarantined")

    def test_known_bad(self):
        tag = "mistral-small3.2:24b"
        under_llamacpp = discover.entry_for({"tag": tag}, None, {})
        self.assertEqual(under_llamacpp["status"], "quarantined")
        self.assertIn("cannot run under llama.cpp", under_llamacpp["note"])
        self.assertFalse(under_llamacpp["recommended"])
        self.assertEqual(discover.entry_for({"tag": tag}, None, None)["status"], "active")  # Ollama serves it
        self.assertEqual({r[1] for r, _ in discover.KNOWN_BAD},
                         {"mistral-small3.2:24b", "ministral-3:14b", "phi4-reasoning:plus"})


class Registry(unittest.TestCase):
    def test_recommended_first_and_all_eight(self):
        tags = ["zorg7:12b", "llama3.3:70b"] + list(reversed(discover.RECOMMENDED_TAGS))
        entries, notes = discover.build_registry(tags, None, {})
        self.assertEqual([e["ollama_tag"] for e in entries[:8]], list(discover.RECOMMENDED_TAGS))
        self.assertEqual([e["recommended"] for e in entries], [True] * 8 + [False] * 2)
        self.assertIn("10 models installed, 8 of the 8 recommended present", notes[0])
        self.assertFalse(any("not installed" in n for n in notes))
        self.assertTrue(any("The council seats 2 to 6 models: 10 usable" in n for n in notes))

    def test_fewer_than_two_usable(self):
        for tags in ([], ["zorg7:12b"], ["zorg7:12b", "bge-m3:567m"]):
            _, notes = discover.build_registry(tags)
            self.assertTrue(any("at least 2 usable models are needed; run tools/box/pull_models.sh" in n
                                for n in notes), tags)
        _, notes = discover.build_registry(["zorg7:12b", "blip9:8b"])
        self.assertFalse(any("at least 2" in n for n in notes))

    def test_memory_budget(self):
        tags = [{"tag": "llama3.3:70b", "size_gb": 42.0}, {"tag": "zorg7:12b", "size_gb": 8.0}]
        entries, notes = discover.build_registry(tags, budget_gib=30.0)
        by = {e["ollama_tag"]: e for e in entries}
        self.assertEqual(by["llama3.3:70b"]["status"], "quarantined")
        self.assertIn("memory budget", by["llama3.3:70b"]["note"])
        self.assertEqual(by["zorg7:12b"]["status"], "active")
        self.assertTrue(any("llama3.3:70b: not seated" in n for n in notes))

    def test_same_lab_note_and_unique_ids(self):
        entries, notes = discover.build_registry(["llama3.1:8b", "llama3.2:3b", "llama3.3:70b", "a.b:1b", "a-b:1b"])
        # three Meta models (two may sit together) plus two unknown families, one seat each
        self.assertTrue(any("5 usable, 4 can sit together" in n for n in notes), notes)
        self.assertEqual(len({e["id"] for e in entries}), 5)


def generic_registry(tags) -> list[ModelEntry]:
    entries, _ = discover.build_registry([{"tag": t, "size_gb": 8.0} for t in tags])
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "models.json"
        p.write_text(json.dumps(entries))
        return load_registry(p)


class RouterOnUnknownModels(unittest.TestCase):
    PROFILE = TaskProfile(categories={"logic": 1.0})

    def pick(self, registry, k):
        table = SkillTable({m.id: dict(m.priors) for m in registry})
        return pick_with_notes(self.PROFILE, k, registry, table, 400.0)

    def test_six_unknown_models_fill_six_seats(self):
        reg = generic_registry(UNKNOWN_SIX)
        self.assertEqual(len(eligible_models(self.PROFILE, reg)), 6)
        self.assertTrue(all(m.measured.tps_1 is None for m in reg))
        for k in (2, 6):
            record, notes = self.pick(reg, k)
            self.assertEqual(record.k, k, notes)

    def test_two_models_of_one_unknown_family_sit_together(self):
        record, notes = self.pick(generic_registry(["zorg7:12b", "zorg7:30b"]), 2)
        self.assertEqual(record.k, 2)
        self.assertTrue(any("max_per_lab relaxed" in n for n in notes))

    def test_recommended_are_preferred(self):
        reg = generic_registry(list(discover.RECOMMENDED_TAGS) + UNKNOWN_SIX)
        rec_ids = {r[0] for r in discover.RECOMMENDED}
        for seed in range(5):
            table = SkillTable({m.id: dict(m.priors) for m in reg})
            record, _ = pick_with_notes(self.PROFILE, 4, reg, table, 400.0, seed=seed)
            merit = [s.model_id for s in record.seats if not s.is_wildcard]
            self.assertTrue(set(merit) <= rec_ids, merit)


class CouncilOnUnknownModels(unittest.IsolatedAsyncioTestCase):
    """A full mock council run over a registry made only of generic, unknown models."""

    async def asyncSetUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="council_discover_run_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        cfg = self.tmp / "home" / "config"
        cfg.mkdir(parents=True)
        for name in ("council.toml", "lenses.json"):
            shutil.copy(REPO / "config" / name, cfg / name)
        entries, _ = discover.build_registry([{"tag": t, "size_gb": 8.0} for t in UNKNOWN_SIX])
        self.assertTrue(all(e["status"] == "active" and not e["recommended"] for e in entries))
        (cfg / "models.json").write_text(json.dumps(entries))
        self.ctrl = RunController.build_mock(home=self.tmp / "home", speed=100000.0, data_home=self.tmp / "data")
        self.addCleanup(self.ctrl.store.close)

    async def asyncTearDown(self) -> None:
        await self.ctrl.shutdown()

    async def run_k(self, k: int) -> None:
        run_id = await self.ctrl.start(RunRequest(
            task="Should a small API use a token bucket or a sliding window? Say why.",
            deliverable="answer", options={"k": k, "auto_input": True}))
        snap = await self.ctrl.wait(run_id, 120.0)
        self.assertEqual(snap.state, RunState.DONE, snap.error)
        events = self.ctrl.store.events_for_run(run_id)
        types = [e.type for e in events]
        self.assertIn(ET.DECISION_FINAL, types)
        seated = [e for e in events if e.type == ET.SEAT_ASSIGNED]
        self.assertEqual(len({e.payload.get("seat_no") for e in seated}), k)
        ids = {m.id for m in self.ctrl.registry}
        self.assertTrue(all(e.payload.get("model_id") in ids for e in seated))

    async def test_k2_reaches_a_decision(self):
        await self.run_k(2)

    async def test_k6_reaches_a_decision(self):
        await self.run_k(6)


if __name__ == "__main__":
    unittest.main()
