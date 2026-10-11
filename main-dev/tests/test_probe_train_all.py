import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path

from council.core.schemas_v15 import ProbeCard
from council.probe import train_all


def run(coro):
    return asyncio.run(coro)


class Fake:
    def __init__(self, fail=(), pause=0.01):
        self.fail = set(fail)
        self.pause = pause
        self.running = 0
        self.max_running = 0
        self.calls = []
        self.released = []

    async def train_one(self, mid):
        self.calls.append(mid)
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        try:
            await asyncio.sleep(self.pause)
            if mid in self.fail:
                raise RuntimeError("boom " + "x" * 500)
            return ProbeCard(model_id=mid, auroc=0.9, active=True, reason="validated", n_test=40)
        finally:
            self.running -= 1

    async def release(self, mid):
        self.released.append(mid)


class TrainModelsTest(unittest.TestCase):
    def test_sequential_in_order(self):
        f = Fake()
        cards = run(train_all.train_models(["a", "b", "c"], f.train_one, f.release))
        self.assertEqual([c.model_id for c in cards], ["a", "b", "c"])
        self.assertEqual(f.max_running, 1)
        self.assertEqual(f.released, ["a", "b", "c"])

    def test_failure_becomes_inactive_card_and_loop_continues(self):
        f = Fake(fail={"b"})
        cards = run(train_all.train_models(["a", "b", "c"], f.train_one, f.release))
        self.assertTrue(cards[0].active)
        self.assertFalse(cards[1].active)
        self.assertTrue(cards[1].reason.startswith("training failed: "))
        self.assertLessEqual(len(cards[1].reason), len("training failed: ") + 200)
        self.assertTrue(cards[2].active)
        self.assertEqual(f.released, ["a", "b", "c"])  # released after failure too

    def test_release_error_does_not_stop(self):
        f = Fake()

        async def bad_release(mid):
            raise OSError("cannot free")

        msgs = []
        cards = run(train_all.train_models(["a", "b"], f.train_one, bad_release,
                                           lambda m, s: msgs.append((m, s))))
        self.assertEqual(len(cards), 2)
        self.assertTrue(any("release failed" in s for _, s in msgs))

    def test_progress_called(self):
        f = Fake()
        msgs = []
        run(train_all.train_models(["a"], f.train_one, progress=lambda m, s: msgs.append((m, s))))
        self.assertIn(("a", "training"), msgs)
        self.assertIn(("a", "done"), msgs)

    def test_duplicate_ids_trained_once(self):
        f = Fake()
        cards = run(train_all.train_models(["a", "a"], f.train_one))
        self.assertEqual(f.calls, ["a"])
        self.assertEqual(len(cards), 1)

    def test_state_written_after_each_model(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "sub" / "state.json"
            seen = []

            f = Fake()

            async def rel(mid):
                seen.append([c["model_id"] for c in json.loads(sp.read_text())] if sp.exists() else [])

            run(train_all.train_models(["a", "b"], f.train_one, rel, state_path=sp))
            # release runs before the state write of the same model, so it sees the previous ones
            self.assertEqual(seen, [[], ["a"]])
            saved = json.loads(sp.read_text())
            self.assertEqual([c["model_id"] for c in saved], ["a", "b"])

    def test_resume_skips_done_retries_failed(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "state.json"
            f1 = Fake(fail={"b"})
            run(train_all.train_models(["a", "b"], f1.train_one, state_path=sp))
            f2 = Fake()
            cards = run(train_all.train_models(["a", "b", "c"], f2.train_one, f2.release, state_path=sp))
            self.assertEqual(f2.calls, ["b", "c"])
            self.assertEqual(f2.released, ["b", "c"])
            self.assertEqual([c.model_id for c in cards], ["a", "b", "c"])
            self.assertTrue(all(c.active for c in cards))
            saved = json.loads(sp.read_text())
            self.assertEqual({c["model_id"] for c in saved}, {"a", "b", "c"})

    def test_narrow_run_keeps_other_cards_in_state(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "state.json"
            f = Fake()
            run(train_all.train_models(["a", "b"], f.train_one, state_path=sp))
            run(train_all.train_models(["c"], f.train_one, state_path=sp))
            saved = json.loads(sp.read_text())
            self.assertEqual({c["model_id"] for c in saved}, {"a", "b", "c"})

    def test_corrupt_state_starts_over(self):
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "state.json"
            sp.write_text("not json", encoding="utf-8")
            f = Fake()
            cards = run(train_all.train_models(["a"], f.train_one, state_path=sp))
            self.assertEqual(len(cards), 1)
            self.assertEqual(f.calls, ["a"])


class SummaryTest(unittest.TestCase):
    def test_table(self):
        cards = [ProbeCard(model_id="m1", auroc=0.91234, control_auroc=0.5, baseline_auroc=0.6,
                           n_test=50, active=True, reason="validated"),
                 ProbeCard(model_id="m2", active=False, reason="training failed: x")]
        text = train_all.summary_text(cards)
        lines = text.splitlines()
        for word in ("model", "auroc", "control", "baseline", "n_test", "active", "reason"):
            self.assertIn(word, lines[0])
        self.assertIn("0.912", text)
        self.assertIn("m2", text)
        self.assertIn("training failed: x", text)
        self.assertIn("1 of 2 probes active", text)

    def test_empty(self):
        self.assertIn("0 of 0", train_all.summary_text([]))


class ReportTest(unittest.TestCase):
    def test_validated(self):
        rep = {"status": "validated", "best_layer": 16, "auroc": 0.93, "shuffled_auroc": 0.51,
               "cheap_auroc": 0.62, "reasons": [], "source": "llamacpp",
               "layers": [{"layer": 8, "n_train": 100, "n_test": 30},
                          {"layer": 16, "n_train": 120, "n_test": 40}]}
        c = train_all.card_from_report("m", rep, now=5.0)
        self.assertTrue(c.active)
        self.assertEqual((c.auroc, c.control_auroc, c.baseline_auroc), (0.93, 0.51, 0.62))
        self.assertEqual((c.n_train, c.n_test, c.layers), (120, 40, [8, 16]))
        self.assertEqual(c.source, "llamacpp")
        self.assertEqual(c.reason, "validated")

    def test_rejected_keeps_reasons(self):
        rep = {"status": "rejected", "best_layer": None, "reasons": ["auroc too low", "no beat"], "layers": []}
        c = train_all.card_from_report("m", rep)
        self.assertFalse(c.active)
        self.assertEqual(c.reason, "auroc too low; no beat")


class MainTest(unittest.TestCase):
    def test_main_with_fake(self):
        f = Fake(fail={"b"})
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            code = train_all.main(["--models", "a, b", "--state", str(Path(d) / "s.json")],
                                  train_one=f.train_one, release=f.release, out=out)
            self.assertTrue((Path(d) / "s.json").is_file())
        self.assertEqual(code, 0)
        self.assertEqual(f.calls, ["a", "b"])
        self.assertIn("1 of 2 probes active", out.getvalue())

    def test_bad_flag_returns_1(self):
        self.assertEqual(train_all.main(["--nope"]), 1)


if __name__ == "__main__":
    unittest.main()
