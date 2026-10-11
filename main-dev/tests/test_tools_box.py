import hashlib
import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

BOX = Path(__file__).resolve().parent.parent / "tools" / "box"


def load(name):
    spec = importlib.util.spec_from_file_location("box_" + name, BOX / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cm = load("check_models")
mr = load("make_registry")
sd = load("specdec_test")
vm = load("verify_models")
mc = load("make_config")

PS = {"models": [{"name": "a:1", "model": "a:1", "size": 10 * 2**30},
                 {"name": "b:2", "model": "b:2", "size": "bad"}]}


class CheckModelsHelpers(unittest.TestCase):
    def test_parse_ps(self):
        self.assertEqual(cm.parse_ps(PS, "a:1"), 10.0)
        self.assertIsNone(cm.parse_ps(PS, "b:2"))
        self.assertIsNone(cm.parse_ps(PS, "zzz"))
        self.assertIsNone(cm.parse_ps("junk", "a:1"))
        self.assertIsNone(cm.parse_ps({}, "a:1"))

    def test_ram_factor(self):
        self.assertEqual(cm.ram_from_size(10.0), 11.6)
        self.assertIsNone(cm.ram_from_size(None))

    def test_parse_tags(self):
        self.assertEqual(cm.parse_tags({"models": [{"name": "b"}, {"name": "a"}, {}]}), ["a", "b"])
        self.assertEqual(cm.parse_tags(None), [])

    def test_tps(self):
        self.assertEqual(cm.tokens_per_second({"eval_count": 200, "eval_duration": 4 * 10**9}), 50.0)
        self.assertIsNone(cm.tokens_per_second({"eval_count": 0, "eval_duration": 5}))
        self.assertIsNone(cm.tokens_per_second("x"))

    def test_think_unsupported(self):
        self.assertTrue(cm.think_unsupported(400, {"error": "model does not support thinking"}))
        self.assertFalse(cm.think_unsupported(200, {}))
        self.assertFalse(cm.think_unsupported(500, {"error": "thinking boom"}))
        self.assertFalse(cm.think_unsupported(400, {"error": "bad json"}))

    def test_load_existing_and_table(self):
        self.assertEqual(cm.load_existing("/nonexistent/file.json"), {})
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text(json.dumps({"a": {"ok": True}}))
            self.assertEqual(cm.load_existing(p), {"a": {"ok": True}})
            p.write_text("[1]")
            self.assertEqual(cm.load_existing(p), {})
        t = cm.table({"a:1": {"ok": True, "size_gib": 1.0, "ram_gib": 1.16, "tps": 9.5, "json_ok": True, "think_ok": False},
                      "b:2": {"ok": False, "error": "HTTP 500: unknown model architecture"}})
        self.assertIn("a:1", t)
        self.assertIn("unknown model architecture", t)

    def test_council_tags_are_the_eleven(self):
        self.assertEqual(len(cm.COUNCIL_TAGS), 11)
        self.assertNotIn("llama3.2-vision:11b-instruct-q8_0", cm.COUNCIL_TAGS)
        self.assertNotIn("gemma4:12b-it-q4_K_M", cm.COUNCIL_TAGS)

    def test_council_tags_match_registry(self):
        registry = {r[1] for r in mr.L}
        self.assertEqual(cm.COUNCIL_TAGS, registry - {"gemma4:12b-it-q4_K_M"})
        self.assertEqual(vm.COUNCIL_TAGS, cm.COUNCIL_TAGS)

    def test_select_tags_default_is_council_only(self):
        installed = ["gemma4:26b", "qwen3:14b", "nemotron3:33b", "gpt-oss:20b", "qwen3.6:35b"]
        tags, missing = cm.select_tags(installed)
        self.assertEqual(tags, ["gpt-oss:20b", "qwen3:14b"])
        self.assertEqual(sorted(missing), sorted(cm.COUNCIL_TAGS - {"qwen3:14b", "gpt-oss:20b"}))

    def test_select_tags_all_and_explicit(self):
        installed = ["gemma4:26b", "qwen3:14b"]
        self.assertEqual(cm.select_tags(installed, "", True), (["gemma4:26b", "qwen3:14b"], []))
        self.assertEqual(cm.select_tags(installed, "x:1,,y:2"), (["x:1", "y:2"], []))
        self.assertEqual(cm.select_tags(installed, "qwen3:14b", True), (["qwen3:14b"], []))


class MakeRegistry(unittest.TestCase):
    ROW = next(r for r in mr.L if r[1] == "qwen3:14b")

    def test_vision_is_purged(self):
        self.assertFalse(any("llama" in r[0] or "llama" in r[1] for r in mr.L))

    def test_no_checks_uses_estimates(self):
        e = mr.build_entry(self.ROW, None)
        self.assertEqual(e["measured"]["ram_gb_live"], 12.0)
        self.assertEqual(e["status"], "active")

    def test_checks_override(self):
        checks = {"qwen3:14b": {"ok": True, "ram_gib": 17.5, "tps": 31.2, "think_ok": True}}
        notes = []
        e = mr.build_entry(self.ROW, checks, notes)
        self.assertEqual(e["measured"]["ram_gb_live"], 17.5)
        self.assertEqual(e["measured"]["tps_1"], 31.2)
        self.assertEqual(e["reasoning"]["kind"], "toggle")
        self.assertTrue(any("measured" in n for n in notes))

    def test_failed_check_quarantines(self):
        checks = {"qwen3:14b": {"ok": False, "error": "HTTP 500"}}
        self.assertEqual(mr.build_entry(self.ROW, checks)["status"], "quarantined")
        ok = {"qwen3:14b": {"ok": True}}
        self.assertEqual(mr.build_entry(self.ROW, ok)["status"], "active")
        self.assertEqual(mr.build_entry(self.ROW, {})["status"], "active")

    def test_think_false_sets_kind_none(self):
        e = mr.build_entry(self.ROW, {"qwen3:14b": {"ok": True, "think_ok": False}})
        self.assertEqual(e["reasoning"]["kind"], "none")
        self.assertEqual(e["reasoning"]["max"], {})

    def test_build_registry_filters_installed(self):
        out, _ = mr.build_registry({"qwen3:14b"}, None)
        self.assertEqual([m["id"] for m in out], ["qwen3-14b"])

    def test_the_eight_recommended_give_the_same_entries_as_the_table(self):
        eight = list(mr.discover.RECOMMENDED_TAGS)
        self.assertEqual(len(eight), 8)
        out, notes = mr.build_registry(set(eight), None)
        self.assertEqual([m["ollama_tag"] for m in out], eight)
        rows = {r[1]: r for r in mr.L}
        for m in out:
            old = mr.build_entry(rows[m["ollama_tag"]], None)
            self.assertEqual({k: v for k, v in m.items() if k not in ("recommended", "note")}, old)
            self.assertTrue(m["recommended"])
            self.assertEqual(m["status"], "active")
        self.assertIn("8 of the 8 recommended present", notes[0])

    def test_any_other_model_is_registered_after_the_recommended(self):
        found = [{"tag": "llama3.3:70b", "size_gb": 42.0}, {"tag": "qwen3:14b", "size_gb": 9.3},
                 {"tag": "bge-m3:567m", "size_gb": 1.2}]
        out, notes = mr.build_registry(found, None)
        self.assertEqual([m["id"] for m in out], ["qwen3-14b", "bge-m3-567m", "llama3-3-70b"])
        self.assertEqual([m["status"] for m in out], ["active", "quarantined", "active"])
        self.assertEqual(out[2]["lab"], "meta")
        self.assertTrue(any("The council seats 2 to 6 models: 2 usable" in n for n in notes))
        only, notes = mr.build_registry(found, None, only_recommended=True)
        self.assertEqual([m["id"] for m in only], ["qwen3-14b"])

    def test_known_bad_models_are_not_seated_under_llamacpp(self):
        tags = {"mistral-small3.2:24b", "qwen3:14b"}
        out, notes = mr.build_registry(tags, None, llamacpp={})
        self.assertEqual({m["ollama_tag"]: m["status"] for m in out},
                         {"qwen3:14b": "active", "mistral-small3.2:24b": "quarantined"})
        self.assertTrue(any("cannot run under llama.cpp" in n for n in notes))
        out, _ = mr.build_registry(tags, None, llamacpp=None)  # served by Ollama: it runs
        self.assertTrue(all(m["status"] == "active" for m in out))

    def test_memory_budget_env(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"COUNCIL_BUDGET_GIB": "64"}):
            self.assertEqual(mr.memory_budget_gib(), 64.0)

    def test_load_checks(self):
        self.assertIsNone(mr.load_checks("/nonexistent/x.json"))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text('{"a": {"ok": true}}')
            self.assertEqual(mr.load_checks(p), {"a": {"ok": True}})


class VerifyModels(unittest.TestCase):
    DATA = b"hello"
    DIGEST = "sha256:" + hashlib.sha256(DATA).hexdigest()

    def make_store(self, d):
        """Store with a council model (qwen3:14b) and a non-council one (gemma4:26b), both pointing at one blob."""
        root = Path(d)
        (root / "blobs").mkdir()
        (root / "blobs" / self.DIGEST.replace(":", "-")).write_bytes(self.DATA)
        for name, tag in (("qwen3", "14b"), ("gemma4", "26b")):
            p = root / "manifests" / "registry.ollama.ai" / "library" / name / tag
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"config": {"digest": self.DIGEST, "size": 5}, "layers": []}))
        return root

    def test_model_files_and_select(self):
        with tempfile.TemporaryDirectory() as d:
            self.make_store(d)
            files = vm.model_files(d)
            self.assertEqual(set(files), {"qwen3:14b", "gemma4:26b"})
            self.assertEqual(set(vm.select_models(files)), {"qwen3:14b"})
            self.assertEqual(set(vm.select_models(files, True)), {"qwen3:14b", "gemma4:26b"})

    def test_model_files_missing_store(self):
        self.assertEqual(vm.model_files("/nonexistent/store"), {})

    def test_check_blob(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.make_store(d)
            self.assertEqual(vm.check_blob(d, (self.DIGEST, 5)), (self.DIGEST, "OK"))
            self.assertEqual(vm.check_blob(d, (self.DIGEST, 9))[1], "SIZE 5 != 9")
            self.assertEqual(vm.check_blob(d, ("sha256:" + "0" * 64, 5))[1], "MISSING")
            bad = "sha256:" + "1" * 64
            (root / "blobs" / bad.replace(":", "-")).write_bytes(self.DATA)
            self.assertEqual(vm.check_blob(d, (bad, 5))[1], "HASH MISMATCH")


class SpecDec(unittest.TestCase):
    def test_mean_after_first(self):
        self.assertEqual(sd.mean_after_first([100, 10, 20]), 15.0)
        self.assertIsNone(sd.mean_after_first([5]))
        self.assertEqual(sd.mean_after_first([1, None, 4]), 4.0)


class MakeRegistryJson(unittest.TestCase):
    ROW = next(r for r in mr.L if r[1] == "qwen3:14b")

    def test_json_check_fills_valid_rate(self):
        self.assertEqual(mr.build_entry(self.ROW, {"qwen3:14b": {"ok": True, "json_ok": True}})["measured"]["structured_valid_rate"], 1.0)
        self.assertEqual(mr.build_entry(self.ROW, {"qwen3:14b": {"ok": True, "json_ok": False}})["measured"]["structured_valid_rate"], 0.0)
        self.assertIsNone(mr.build_entry(self.ROW, {"qwen3:14b": {"ok": True}})["measured"]["structured_valid_rate"])
        self.assertIsNone(mr.build_entry(self.ROW, None)["measured"]["structured_valid_rate"])


REPO_TOML = (Path(__file__).resolve().parent.parent / "config" / "council.toml").read_text()


class MakeConfig(unittest.TestCase):
    HOME = Path("/home/asus")

    def test_driver_default_and_validation(self):
        self.assertEqual(mc.chosen_driver({}), "llamacpp")
        self.assertEqual(mc.chosen_driver({"COUNCIL_DRIVER": " Ollama "}), "ollama")
        with self.assertRaises(SystemExit):
            mc.chosen_driver({"COUNCIL_DRIVER": "vllm"})

    def test_llamacpp_config(self):
        text, _ = mc.transform(REPO_TOML, "llamacpp", self.HOME)
        self.assertRegex(text, r'(?m)^driver = "llamacpp"')
        self.assertRegex(text, r"(?m)^mock = false")
        self.assertIn('server_bin = "/home/asus/llama.cpp/build/bin/llama-server"', text)
        self.assertIn('ollama_models_dir = "/usr/share/ollama/.ollama/models"', text)
        section = re.search(r"\[llamacpp\]\n(.*?)(?=^\[)", text, flags=re.M | re.S).group(1)
        self.assertIn("ctx = 8192", section)
        self.assertIn("base_port = 18100", section)

    def test_lie_reading_timeout_on_the_box(self):
        text, _ = mc.transform(REPO_TOML, "llamacpp", self.HOME)
        section = re.search(r"\[lie\]\n(.*?)(?=^\[)", text, flags=re.M | re.S).group(1)
        self.assertRegex(section, r"(?m)^timeout_s = 30$")

    def test_ollama_config_keeps_llamacpp_section(self):
        text, _ = mc.transform(REPO_TOML, "ollama", self.HOME)
        self.assertRegex(text, r'(?m)^driver = "ollama"')
        self.assertNotIn("/home/asus", text)

    def test_keeps_old_settings(self):
        text, _ = mc.transform(REPO_TOML, "llamacpp", self.HOME)
        self.assertIn('core_models = ["qwen35-9b"]', text)
        self.assertIn("default_timeout_s = 420", text)
        self.assertIn("http://127.0.0.1:11435", text)
        self.assertIn("min_deadline_s = 120", text)
        self.assertIn("max_deadline_s = 2400", text)

    def test_set_in_section(self):
        t = "[a]\nx = 1\n\n[llamacpp]\nctx = 1 # c\nother = 2\n\n[b]\nctx = 9\n"
        out = mc.set_in_section(t, "llamacpp", "ctx", "8192")
        self.assertIn("[llamacpp]\nctx = 8192 # c\nother = 2", out)
        self.assertIn("[b]\nctx = 9", out)
        out = mc.set_in_section(t, "llamacpp", "new", '"v"')
        self.assertIn('other = 2\nnew = "v"\n\n[b]', out)
        out = mc.set_in_section("[a]\nx = 1\n", "llamacpp", "ctx", "8192")
        self.assertTrue(out.endswith("[llamacpp]\nctx = 8192\n"))
        self.assertEqual(mc.set_in_section(out, "llamacpp", "ctx", "8192"), out)

    def test_missing_section_is_appended(self):
        base = REPO_TOML[:REPO_TOML.index("[llamacpp]")] + REPO_TOML[REPO_TOML.index("# Per-project steering"):]
        self.assertNotIn("[llamacpp]", base)
        text, _ = mc.transform(base, "llamacpp", self.HOME)
        self.assertIn("[llamacpp]", text)
        self.assertIn("ctx = 8192", text)


class BoxShellScripts(unittest.TestCase):
    def read(self, name):
        return (BOX / name).read_text()

    def test_sizes_test_content(self):
        s = self.read("sizes_test.sh")
        self.assertIn("set -u", s)
        self.assertNotIn("set -e", s)
        for k in ("2", "4", "6"):
            self.assertIn(f"run_size {k} ", s)
        self.assertIn("--k", s)
        self.assertIn("--mode standard", s)
        self.assertIn("COUNCIL_HOME=~/council/box", s)
        self.assertIn("summarize_run.py", s)
        self.assertIn("/tmp/size", s)
        self.assertIn("0.1 + 0.2 == 0.3", s)
        self.assertIn("PostgreSQL or MongoDB", s)
        self.assertIn("80,000-line Python 2", s)

    def test_stop_models_content(self):
        s = self.read("stop_models.sh")
        self.assertIn('pkill -f "[l]lama-server.*--port 181"', s)
        self.assertIn("11434", s)
        self.assertIn("11435", s)
        self.assertIn("keep_alive", s)
        self.assertIn(":0}", s)

    def test_bash_syntax(self):
        import shutil
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("no bash")
        for name in ("sizes_test.sh", "stop_models.sh"):
            r = subprocess.run([bash, "-n", str(BOX / name)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
