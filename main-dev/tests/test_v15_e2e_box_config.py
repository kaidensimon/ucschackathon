"""End to end, mock mode: the box tooling writes a council.toml the real config loader reads.

tools/box/make_config.py runs as a subprocess with HOME/USERPROFILE pointed at a temp dir, once per
COUNCIL_DRIVER. The file it writes is read back with council.core.config.load_config (real class), and
tools/box/make_registry.py output is checked against ModelEntry and load_registry.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from council.core.config import load_config, load_lenses, load_registry
from council.core.schemas import ModelEntry

ROOT = Path(__file__).resolve().parent.parent
BOX = ROOT / "tools" / "box"
MAKE_CONFIG = BOX / "make_config.py"


def load_tool(name):
    spec = importlib.util.spec_from_file_location("e2e_box_" + name, BOX / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mr = load_tool("make_registry")
cm = load_tool("check_models")
mc = load_tool("make_config")


def run_make_config(home: Path, driver: str | None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env.pop("COUNCIL_DRIVER", None)
    if driver is not None:
        env["COUNCIL_DRIVER"] = driver
    return subprocess.run(
        [sys.executable, str(MAKE_CONFIG)], env=env, cwd=str(ROOT),
        capture_output=True, text=True, timeout=60,
    )


class BoxConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = {}
        for driver in ("llamacpp", "ollama", None):
            home = Path(cls._tmp.name) / (driver or "default")
            home.mkdir()
            proc = run_make_config(home, driver)
            cls.out[driver] = (home, proc)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def config_path(self, driver):
        home, proc = self.out[driver]
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        path = home / "council" / "box" / "config" / "council.toml"
        self.assertTrue(path.is_file(), proc.stdout)
        return home, path, proc

    def test_llamacpp_driver_config_loads(self):
        home, path, proc = self.config_path("llamacpp")
        self.assertNotIn("warning:", proc.stdout)
        self.assertIn("driver: llamacpp", proc.stdout)
        cfg = load_config(path)
        self.assertEqual(cfg.host.driver, "llamacpp")
        self.assertFalse(cfg.gateway.mock)
        self.assertEqual(cfg.host.core_models, ["qwen35-9b"])
        self.assertEqual(cfg.gateway.default_timeout_s, 420)
        self.assertEqual(cfg.ollama.base_url, "http://127.0.0.1:11435")
        # [llamacpp] section: the box binary under HOME, ctx, the Ollama blob store.
        expected_bin = (home / "llama.cpp" / "build" / "bin" / "llama-server").as_posix()
        self.assertEqual(cfg.llamacpp.server_bin, expected_bin)
        self.assertEqual(cfg.llamacpp.ctx, 8192)
        self.assertEqual(cfg.llamacpp.ollama_models_dir, "/usr/share/ollama/.ollama/models")
        self.assertEqual(cfg.llamacpp.base_port, 18100)  # untouched defaults survive
        # The keys must sit in the right sections of the raw file (Config ignores unknown keys silently).
        raw = tomllib.loads(path.read_text())
        self.assertEqual(raw["llamacpp"]["server_bin"], expected_bin)
        # same key name in [probe]: the lie detector reads the same blob store on the box
        self.assertEqual(raw["probe"]["ollama_models_dir"], "/usr/share/ollama/.ollama/models")
        self.assertTrue(load_lenses(path.parent / "lenses.json"))

    def test_ollama_driver_config_loads_and_leaves_llamacpp_section_alone(self):
        home, path, proc = self.config_path("ollama")
        self.assertIn("driver: ollama", proc.stdout)
        cfg = load_config(path)
        self.assertEqual(cfg.host.driver, "ollama")
        self.assertFalse(cfg.gateway.mock)
        self.assertEqual(cfg.ollama.base_url, "http://127.0.0.1:11435")
        repo_default = load_config(ROOT / "config" / "council.toml")
        self.assertEqual(cfg.llamacpp, repo_default.llamacpp)
        self.assertNotIn(home.as_posix(), cfg.llamacpp.server_bin)

    def test_default_driver_is_llamacpp_and_bad_driver_is_refused(self):
        _, path, proc = self.config_path(None)
        self.assertEqual(load_config(path).host.driver, "llamacpp")
        with tempfile.TemporaryDirectory() as d:
            bad = run_make_config(Path(d), "vllm")
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("COUNCIL_DRIVER", bad.stderr + bad.stdout)
            self.assertFalse((Path(d) / "council" / "box" / "config" / "council.toml").exists())

    def test_deadlines_and_k_options(self):
        for driver in ("llamacpp", "ollama"):
            with self.subTest(driver=driver):
                _, path, _ = self.config_path(driver)
                cfg = load_config(path)
                self.assertEqual(cfg.mode("quick").deadline_s, 180)
                self.assertEqual(cfg.mode("standard").deadline_s, 900)
                self.assertEqual(cfg.mode("deep").deadline_s, 2400)
                self.assertEqual(cfg.chamber.min_deadline_s, 120)
                self.assertEqual(cfg.chamber.max_deadline_s, 2400)
                # Council sizes stay 2 to 6 for quick and standard; deep also offers 7.
                self.assertEqual(cfg.mode("quick").k_options, [2, 3, 4, 5, 6])
                self.assertEqual(cfg.mode("standard").k_options, [2, 3, 4, 5, 6])
                self.assertEqual(cfg.mode("deep").k_options, [2, 3, 4, 5, 6, 7])
                for name in ("quick", "standard", "deep"):
                    self.assertIn(cfg.mode(name).k, cfg.mode(name).k_options)
                self.assertGreater(cfg.chamber.max_deadline_s, cfg.chamber.min_deadline_s)
                self.assertGreaterEqual(cfg.mode("standard").deadline_s, cfg.chamber.min_deadline_s)
                self.assertLessEqual(cfg.mode("deep").deadline_s, cfg.chamber.max_deadline_s)
                # Unrelated settings are not disturbed.
                self.assertEqual(cfg.router.k, 6)
                self.assertEqual(cfg.review.deadline_s, 900)

    def test_transform_is_idempotent_and_has_no_warnings(self):
        text = (ROOT / "config" / "council.toml").read_text()
        home = Path("/home/box")
        for driver in ("llamacpp", "ollama"):
            once, warnings = mc.transform(text, driver, home)
            self.assertEqual(warnings, [])
            # A second pass finds nothing left to change (the mock and base_url patterns no longer match).
            twice, _ = mc.transform(once, driver, home)
            self.assertEqual(once, twice)
            tomllib.loads(once)  # valid TOML
        # set_in_section adds a missing section and a missing key.
        added = mc.set_in_section("[a]\nx = 1\n", "llamacpp", "ctx", "4096")
        self.assertEqual(tomllib.loads(added)["llamacpp"]["ctx"], 4096)
        added = mc.set_in_section("[llamacpp]\nbase_port = 1\n\n[steer]\nenabled = true\n", "llamacpp", "ctx", "4096")
        parsed = tomllib.loads(added)
        self.assertEqual(parsed["llamacpp"], {"base_port": 1, "ctx": 4096})
        self.assertEqual(parsed["steer"], {"enabled": True})

    def test_registry_has_the_eleven_council_models_and_no_vision(self):
        installed = set(cm.COUNCIL_TAGS)
        out, notes = mr.build_registry(installed, None)
        self.assertEqual(len(out), 11, [m["id"] for m in out])
        self.assertEqual(len({m["id"] for m in out}), 11)
        self.assertEqual({m["ollama_tag"] for m in out}, installed)
        for m in out:
            self.assertNotIn("llama", m["id"])
            self.assertNotIn("llama", m["ollama_tag"])
            self.assertNotIn("vision", m["id"] + m["ollama_tag"] + m["display"].lower())
            self.assertEqual(m["modalities"], ["text"])
            self.assertEqual(m["status"], "active")
        # Through the real loader: every entry validates as a ModelEntry.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "models.json"
            p.write_text(json.dumps(out))
            reg = load_registry(p)
        self.assertEqual(len(reg), 11)
        self.assertTrue(all(isinstance(e, ModelEntry) for e in reg))
        self.assertEqual(len({e.lab for e in reg}) >= 6, True)
        # Seats exist for a size-6 council, and the core model of the box config is registered.
        self.assertGreaterEqual(sum("seat" in e.roles for e in reg), 6)
        self.assertIn("qwen35-9b", {e.id for e in reg})


if __name__ == "__main__":
    unittest.main()
