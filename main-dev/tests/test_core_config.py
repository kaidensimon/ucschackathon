import json
import os
import tempfile
import unittest
from pathlib import Path

from council.core import config as C


class TestConfig(unittest.TestCase):
    def test_missing_file_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = C.load_config(Path(d) / "nope.toml")
        self.assertEqual(cfg.host.driver, "llama_router")
        self.assertEqual(cfg.router.k, 6)
        self.assertEqual(cfg.router.weights_tier_b.cover, 0.15)
        self.assertEqual(cfg.workers.slots, 16)
        self.assertEqual(cfg.inspector.allowed_executables, ["python3", "pytest"])
        self.assertEqual(cfg.mode("quick").k, 3)
        self.assertEqual(cfg.mode("deep").rounds, ["r0", "r1", "r2", "r3", "r3"])
        with self.assertRaises(KeyError):
            cfg.mode("zzz")

    def test_toml_override(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.toml"
            p.write_text('[router]\nk = 7\n[chamber.modes.quick]\nk = 4\n[chamber]\nchair_external = true\n')
            cfg = C.load_config(p)
        self.assertEqual(cfg.router.k, 7)
        self.assertEqual(cfg.router.max_per_lab, 1)
        self.assertEqual(cfg.mode("quick").k, 4)
        self.assertEqual(cfg.mode("quick").deadline_s, 60.0)
        self.assertTrue(cfg.chamber.chair_external)
        self.assertEqual(cfg.mode("standard").k, 6)

    def test_registry_and_lenses(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d) / "m.json"
            r.write_text(json.dumps([{"id": "a", "lab": "x"}, {"id": "b"}]))
            reg = C.load_registry(r)
            self.assertEqual([m.id for m in reg], ["a", "b"])
            lp = Path(d) / "l.json"
            lp.write_text(json.dumps({"builder": "Build it."}))
            self.assertEqual(C.load_lenses(lp), {"builder": "Build it."})
            self.assertEqual(C.load_registry(Path(d) / "none.json"), [])
            self.assertEqual(C.load_lenses(Path(d) / "none.json"), {})

    def test_home_env(self):
        old = os.environ.get("COUNCIL_HOME")
        try:
            os.environ["COUNCIL_HOME"] = "/tmp/xyz"
            self.assertEqual(C.home(), Path("/tmp/xyz"))
            del os.environ["COUNCIL_HOME"]
            self.assertTrue((C.home() / "council").is_dir())
        finally:
            if old is not None:
                os.environ["COUNCIL_HOME"] = old

    def test_new_section_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = C.load_config(Path(d) / "nope.toml")
        self.assertEqual(cfg.tribunal.model_dump(),
                         {"enabled": True, "questions": 3, "min_agreement": 0.80,
                          "in_bench": False})
        self.assertEqual(cfg.probe.model_dump(),
                         {"enabled": True, "min_auroc": 0.80, "min_labelled": 50,
                          "layers": [8, 12, 16, 20], "show_to_council": True, "source": "mock",
                          "actdump_path": "~/council/tap-build/actdump",
                          "ollama_models_dir": "", "max_models": 1, "pool": "last"})
        self.assertEqual(cfg.bench.model_dump(),
                         {"default_split": "test", "calibration_split": "calibration",
                          "self_consistency_k": 5, "solo_max_output_tokens": 1200,
                          "solo_max_reasoning_tokens": 4000})
        self.assertEqual(cfg.ollama.model_dump(),
                         {"base_url": "http://127.0.0.1:11434", "keep_alive": "-1",
                          "num_ctx_live": 16384, "num_ctx_batch": 8192,
                          "default_draft_num_predict": 0})
        self.assertIsInstance(cfg.ollama.keep_alive, str)

    def test_new_section_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.toml"
            p.write_text(
                '[host]\ndriver = "ollama"\n'
                '[tribunal]\nenabled = false\nquestions = 2\n'
                '[probe]\nlayers = [4]\nsource = "torch"\n'
                '[bench]\nself_consistency_k = 7\n'
                '[ollama]\nbase_url = "http://box:11434"\nnum_ctx_live = 32768\n'
            )
            cfg = C.load_config(p)
        self.assertEqual(cfg.host.driver, "ollama")
        self.assertEqual(cfg.host.headroom_gib, 12)
        self.assertEqual((cfg.tribunal.enabled, cfg.tribunal.questions), (False, 2))
        self.assertEqual(cfg.tribunal.min_agreement, 0.80)
        self.assertEqual((cfg.probe.layers, cfg.probe.source), ([4], "torch"))
        self.assertEqual(cfg.bench.self_consistency_k, 7)
        self.assertEqual(cfg.bench.default_split, "test")
        self.assertEqual(cfg.ollama.base_url, "http://box:11434")
        self.assertEqual((cfg.ollama.num_ctx_live, cfg.ollama.num_ctx_batch), (32768, 8192))

    def test_host_drivers(self):
        self.assertEqual(C.HOST_DRIVERS, ("llama_router", "llama_process", "ollama", "llamacpp"))
        self.assertIn(C.HostConfig().driver, C.HOST_DRIVERS)
        for name in C.HOST_DRIVERS:
            self.assertEqual(C.HostConfig(driver=name).driver, name)

    def test_layer_defaults_are_not_shared(self):
        a, b = C.ProbeConfig(), C.ProbeConfig()
        a.layers.append(99)
        self.assertEqual(b.layers, [8, 12, 16, 20])

    def test_probe_llamacpp_settings(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.toml"
            p.write_text('[probe]\nsource = "llamacpp"\nlayers = []\nactdump_path = "/opt/actdump"\n'
                         'ollama_models_dir = "/data/ollama"\nmax_models = 2\npool = "mean"\n')
            probe = C.load_config(p).probe
        self.assertEqual((probe.source, probe.layers), ("llamacpp", []))  # [] = pick from depth
        self.assertEqual((probe.actdump_path, probe.ollama_models_dir), ("/opt/actdump", "/data/ollama"))
        self.assertEqual((probe.max_models, probe.pool), (2, "mean"))

    def test_shipped_toml_documents_the_llamacpp_source(self):
        root = Path(C.__file__).resolve().parents[2]
        text = (root / "config" / "council.toml").read_text(encoding="utf-8")
        for word in ('"llamacpp"', "actdump_path", "ollama_models_dir", "max_models", "pool"):
            self.assertIn(word, text)
        self.assertEqual(C.load_config(root / "config" / "council.toml").probe.source, "mock")

    def test_shipped_toml_matches_defaults(self):
        root = Path(C.__file__).resolve().parents[2]
        toml = root / "config" / "council.toml"
        cfg = C.load_config(toml)
        base = C.Config()
        for section in ("tribunal", "probe", "bench", "ollama",
                        "llamacpp", "steer", "lie", "memory"):
            self.assertEqual(getattr(cfg, section), getattr(base, section), section)
        self.assertEqual(cfg.chamber.modes, base.chamber.modes)
        self.assertTrue(cfg.gateway.mock)  # the repo runs in mock mode
        self.assertEqual(cfg.host.driver, "llama_router")  # the default stays
        text = toml.read_text(encoding="utf-8")
        for section in ("[tribunal]", "[probe]", "[bench]", "[ollama]",
                        "[llamacpp]", "[steer]", "[lie]", "[memory]"):
            self.assertIn(section, text)
        self.assertIn('driver = "ollama"', text)  # the comment about the box

    def test_shipped_registry_has_ollama_tags(self):
        root = Path(C.__file__).resolve().parents[2]
        reg = C.load_registry(root / "config" / "models.json")
        self.assertGreaterEqual(len(reg), 12)
        for m in reg:
            self.assertTrue(m.ollama_tag, m.id)
            self.assertNotIn(" ", m.ollama_tag)
        tags = {m.id: m.ollama_tag for m in reg}
        self.assertEqual(tags["gpt-oss-20b"], "gpt-oss:20b")
        self.assertEqual(len(set(tags.values())), len(tags))

    def test_v15_section_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = C.load_config(Path(d) / "nope.toml")
        self.assertEqual(cfg.llamacpp.model_dump(),
                         {"server_bin": "~/llama.cpp/build/bin/llama-server", "base_port": 18100,
                          "ctx": 8192, "parallel": 1, "health_timeout_s": 240,
                          "ollama_models_dir": "", "extra_args": []})
        self.assertEqual(cfg.steer.model_dump(),
                         {"enabled": True, "layers": "auto", "target_fraction": 0.06,
                          "scales": [0.5, 1.0, 1.5, 2.0], "min_examples": 6,
                          "max_tokens_probe": 80})
        self.assertEqual(cfg.lie.model_dump(),
                         {"enabled": True, "show_to_council": True, "max_claims": 8,
                          "flag_below": 0.30, "watch_below": 0.45, "gap_flag": 0.45,
                          "gap_watch": 0.30, "timeout_s": 20})
        self.assertEqual(cfg.memory.model_dump(),
                         {"reserve_gib": 10.0, "overhead": 1.35, "share_roles": "auto",
                          "measured_file": ""})
        a, b = C.SteerConfig(), C.SteerConfig()
        a.scales.append(9.0)
        self.assertEqual(b.scales, [0.5, 1.0, 1.5, 2.0])

    def test_v15_section_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.toml"
            p.write_text('[host]\ndriver = "llamacpp"\n'
                         '[llamacpp]\nbase_port = 19000\nextra_args = ["--mlock"]\n'
                         '[steer]\nlayers = "14-26"\nscales = [1.0]\n'
                         '[lie]\nenabled = false\nflag_below = 0.2\n'
                         '[memory]\nshare_roles = "never"\nreserve_gib = 4\n')
            cfg = C.load_config(p)
            self.assertEqual(cfg.host.driver, "llamacpp")
            self.assertEqual((cfg.llamacpp.base_port, cfg.llamacpp.extra_args, cfg.llamacpp.ctx),
                             (19000, ["--mlock"], 8192))
            self.assertEqual((cfg.steer.layers, cfg.steer.scales, cfg.steer.min_examples),
                             ("14-26", [1.0], 6))
            self.assertEqual((cfg.lie.enabled, cfg.lie.flag_below, cfg.lie.gap_flag),
                             (False, 0.2, 0.45))
            self.assertEqual((cfg.memory.share_roles, cfg.memory.reserve_gib), ("never", 4.0))
            p.write_text('[memory]\nshare_roles = "sometimes"\n')
            with self.assertRaises(Exception):
                C.load_config(p)

    def test_every_mode_offers_sizes_two_to_six(self):
        cfg = C.Config()
        for name in ("quick", "standard"):
            self.assertEqual(cfg.mode(name).k_options, [2, 3, 4, 5, 6])
        self.assertEqual(cfg.mode("deep").k_options, [2, 3, 4, 5, 6, 7])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.toml"
            p.write_text('[chamber.modes.quick]\nk = 4\n')
            self.assertEqual(C.load_config(p).mode("quick").k_options, [2, 3, 4, 5, 6])

    def test_exports(self):
        for name in ("TribunalConfig", "ProbeConfig", "BenchConfig",
                     "OllamaConfig", "LlamaCppConfig", "SteerConfig", "LieConfig",
                     "MemoryConfig", "HOST_DRIVERS"):
            self.assertIn(name, C.__all__)
            self.assertTrue(hasattr(C, name))


if __name__ == "__main__":
    unittest.main()
