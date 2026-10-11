import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from council.core.schemas import Probe
from council.core.store import Store
from council.probe import train_cli
from council.probe.activations import MockActivationSource

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "bench" / "tasks" / "sample.jsonl"


class InfoSource(MockActivationSource):
    """A mock that knows the model depth, like the llama.cpp source."""

    def __init__(self, n_layer=40):
        super().__init__(dim=8, signal=3.0)
        self.n_layer, self.closed, self.layers_seen = n_layer, 0, set()

    async def info(self, model_id):
        return {"n_layer": self.n_layer, "n_embd": 8, "architecture": "mock"}

    async def capture(self, model_id, messages, layers):
        self.layers_seen.update(layers)
        return await super().capture(model_id, messages, layers)

    async def close(self, model_id=None):
        self.closed += 1


class TrainCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        patch = mock.patch.dict(os.environ, {"COUNCIL_HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)

    def run_cli(self, *argv, **kw):
        out, err = io.StringIO(), io.StringIO()
        code = train_cli.main(list(argv), out=out, err=err, **kw)
        return code, out.getvalue(), err.getvalue()

    def stored(self, model_id):
        store = Store(self.home / "db" / "council.db")
        try:
            return store.kv_get("probes", model_id)
        finally:
            store.close()

    def test_mock_run_prints_the_table_stores_the_probe_and_writes_the_report(self):
        code, out, err = self.run_cli("--model", "m1", "--source", "mock", "--limit", "60",
                                      "--layers", "8,12,16")
        self.assertEqual(code, 0, err)
        for word in ("layer", "n_train", "n_test", "AUROC", "shuffled", "cheap", "verdict:"):
            self.assertIn(word, out)
        self.assertIn("built-in statements", out)
        rows = [l.split() for l in out.splitlines() if l.strip()[:2].strip().isdigit()]
        self.assertEqual([r[0] for r in rows], ["8", "12", "16"])
        self.assertEqual(sum(1 for r in rows if r[-1] == "*"), 1)

        report_path = self.home / "bench" / "results" / "probe_m1.json"
        self.assertIn(str(report_path), out)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["model_id"], "m1")
        self.assertEqual(report["source"], "mock")
        self.assertEqual(report["n_pairs"], 60)
        self.assertEqual(len(report["layers"]), 3)
        self.assertIn(report["status"].upper(), out)

        raw = self.stored("m1")
        probe = Probe.model_validate(raw)  # the way ReliabilityService.get_probe reads it
        self.assertEqual(probe.model_id, "m1")
        self.assertEqual(probe.status, report["status"])
        self.assertEqual(probe.layer, report["best_layer"])
        self.assertEqual(len(probe.weights), 32)

        # 1.5: the layout, the gate and the calibration are in the report, the probe is a file too
        from council.probe import trainer
        from council.probe.probe_files import ProbeFiles
        self.assertEqual((report["layout"], raw["layout"]), (trainer.LAYOUT, trainer.LAYOUT))
        self.assertEqual(report["active"], report["status"] == "validated")
        for key in ("gate_reason", "accuracy", "ece", "platt", "card"):
            self.assertIn(key, report)
        self.assertIn("live scoring:", out)
        files = ProbeFiles(self.home)
        from council.probe.layout import LAYOUT_VERSION
        self.assertEqual(files.layout_version("m1", 1), LAYOUT_VERSION)
        card, probes, platt = files.load("m1", 1)
        self.assertEqual((card.model_id, card.version), ("m1", 1))
        self.assertEqual(card.control_auroc, report["shuffled_auroc"])
        self.assertEqual(card.baseline_auroc, report["cheap_auroc"])
        self.assertEqual(probes[0].model_dump(), probe.model_dump())
        self.assertEqual(list(platt) if platt else None, report["platt"])
        self.assertIn("captured 60/60", err)

    def test_reliability_service_reads_the_stored_probe(self):
        from council.probe.service import ReliabilityService
        store = Store(":memory:")
        self.addCleanup(store.close)
        code, out, err = self.run_cli("--model", "m2", "--limit", "40", "--layers", "8",
                                      "--out", str(self.home / "r.json"), store=store)
        self.assertEqual(code, 0, err)
        svc = ReliabilityService(None, store, None, {}, lambda *a: None)
        self.assertEqual(svc.get_probe("m2").layer, 8)
        self.assertEqual([p.layer for p in svc.active_probes("m2")], [8])  # usable for live scores
        empty = Store(":memory:")
        self.addCleanup(empty.close)
        with_files = ReliabilityService(None, empty, None, {}, lambda *a: None, home=self.home)
        self.assertEqual([p.layer for p in with_files.active_probes("m2")], [8])
        self.assertEqual([c.model_id for c in with_files.cards()], ["m2"])
        self.assertTrue((self.home / "r.json").is_file())
        self.assertFalse((self.home / "db").exists())  # the given store was used

    def test_tasks_file_and_limit(self):
        code, out, err = self.run_cli("--model", "m", "--tasks", str(SAMPLE), "--limit", "30",
                                      "--layers", "8")
        self.assertEqual(code, 0, err)
        report = json.loads((self.home / "bench" / "results" / "probe_m.json").read_text("utf-8"))
        self.assertEqual(report["n_pairs"], 30)
        self.assertEqual(report["pairs_from"], str(SAMPLE))
        self.assertEqual(report["n_test_pairs"], 9)
        self.assertNotEqual(report["status"], "validated")  # 9 held-out questions: too few

    def test_a_run_that_does_not_validate_still_exits_zero(self):
        code, out, err = self.run_cli("--model", "m", "--limit", "40", "--layers", "8",
                                      source=MockActivationSource(dim=8, signal=0.0))
        self.assertEqual(code, 0, err)
        self.assertIn("verdict: REJECTED", out)
        self.assertIn("why:", out)
        self.assertEqual(self.stored("m")["status"], "rejected")

    def test_auto_layers_come_from_the_model_depth_and_the_source_is_closed(self):
        src = InfoSource(40)
        code, out, err = self.run_cli("--model", "m", "--limit", "30", source=src)
        self.assertEqual(code, 0, err)
        self.assertEqual(src.layers_seen, {10, 17, 23, 30})
        self.assertEqual(src.closed, 1)
        src = InfoSource(12)
        code, out, err = self.run_cli("--model", "m", "--limit", "30", "--layers", "4,8,40", source=src)
        self.assertEqual(code, 0, err)
        self.assertEqual(src.layers_seen, {4, 8})  # layer 40 does not exist in a 12-layer model
        src = InfoSource(12)
        code, out, err = self.run_cli("--model", "m", "--limit", "30", "--layers", "40", source=src)
        self.assertEqual(code, 1)
        self.assertIn("0..11", err)
        self.assertEqual(src.closed, 1)

    def test_auto_layers_without_depth_use_the_config(self):
        (self.home / "config").mkdir()
        (self.home / "config" / "council.toml").write_text(
            '[probe]\nlayers = [3, 5]\nmin_auroc = 0.99\nsource = "ollama_embed"\n', encoding="utf-8")
        code, out, err = self.run_cli("--model", "m", "--limit", "30")
        self.assertEqual(code, 0, err)
        report = json.loads((self.home / "bench" / "results" / "probe_m.json").read_text("utf-8"))
        self.assertEqual([r["layer"] for r in report["layers"]], [3, 5])
        self.assertEqual(report["min_auroc"], 0.99)
        self.assertEqual(report["source"], "mock")  # only mock and llamacpp are offered here
        code, out, err = self.run_cli("--model", "m", "--limit", "30", "--min-auroc", "0.6")
        report = json.loads((self.home / "bench" / "results" / "probe_m.json").read_text("utf-8"))
        self.assertEqual(report["min_auroc"], 0.6)

    def test_errors_exit_one(self):
        for argv in (["--model", "m", "--tasks", str(self.home / "none.jsonl")],
                     ["--model", "m", "--layers", "a,b"],
                     ["--model", "m", "--limit", "0"],
                     ["--model", "m", "--source", "torch"],
                     []):
            with mock.patch("sys.stderr", io.StringIO()):
                code, out, err = self.run_cli(*argv)
            self.assertEqual(code, 1, argv)
            self.assertEqual(out, "")
        self.assertIsNone(self.stored("m") if (self.home / "db").exists() else None)

    def test_llamacpp_source_without_the_tool_is_an_error_not_a_crash(self):
        (self.home / "config").mkdir()
        (self.home / "config" / "council.toml").write_text(
            f'[probe]\nactdump_path = "{(self.home / "no-actdump").as_posix()}"\n'
            f'ollama_models_dir = "{(self.home / "models").as_posix()}"\n', encoding="utf-8")
        code, out, err = self.run_cli("--model", "m", "--source", "llamacpp", "--limit", "5")
        self.assertEqual(code, 1)
        self.assertIn("error:", err)

    def test_model_id_becomes_a_safe_file_name(self):
        code, out, err = self.run_cli("--model", "qwen3:14b/x", "--limit", "20", "--layers", "8")
        self.assertEqual(code, 0, err)
        self.assertTrue((self.home / "bench" / "results" / "probe_qwen3_14b_x.json").is_file())
        self.assertIsNotNone(self.stored("qwen3:14b/x"))

    def test_default_pairs_mix_both_built_in_sets(self):
        pairs, where = train_cli.build_pairs(None, None, 0)
        self.assertEqual((len(pairs), where), (600, "built-in statements"))
        self.assertEqual(len({p.task_id for p in pairs}), 600)
        heads = {p.task_id.split("-")[0] for p in pairs}
        self.assertEqual(heads, {"stmt", "tset"})
        self.assertEqual(len(train_cli.build_pairs(None, 30, 0)[0]), 30)

    def test_helpers(self):
        self.assertIsNone(train_cli.parse_layers("auto"))
        self.assertEqual(train_cli.parse_layers("8, 16,8"), [8, 16])
        text = train_cli.format_report({"model_id": "m", "layers": [], "status": "rejected",
                                        "best_layer": None, "reasons": ["too few"]})
        self.assertIn("verdict: REJECTED", text)
        self.assertIn("why: too few", text)

    def test_runs_as_a_module(self):
        env = dict(os.environ, COUNCIL_HOME=str(self.home), PYTHONIOENCODING="utf-8")
        res = subprocess.run(
            [sys.executable, "-m", "council.probe.train_cli", "--model", "m", "--source", "mock",
             "--limit", "24", "--layers", "8"],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("verdict:", res.stdout)
        bad = subprocess.run(
            [sys.executable, "-m", "council.probe.train_cli", "--model", "m", "--tasks", "nope.jsonl"],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("error:", bad.stderr)


if __name__ == "__main__":
    unittest.main()
