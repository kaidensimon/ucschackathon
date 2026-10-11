"""1.5 end to end, mock mode: the lie-detector probe lifecycle through the real classes.

train (builtin statement pairs) -> gate -> ProbeFiles save -> load -> LiveScorer.
Checks: a true statement scores above a false one, the shuffled-label control sits near 0.5,
training text layout == live layout (same function), a noise source is refused by the gate,
and a probe file of another layout is retired.
"""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from council.core.config import ProbeConfig
from council.core.schemas_v15 import ClaimSpan, ProbeCard
from council.core.store import Store
from council.probe import layout, trainer
from council.probe.activations import MockActivationSource
from council.probe.gate import card_with_gate, decide_active
from council.probe.ledger import ClaimLedger
from council.probe.logreg import auroc
from council.probe.probe_files import ProbeFiles
from council.probe.scorer import LiveScorer, default_text_for
from council.probe.service import ReliabilityService

MODEL = "m-e2e"
LAYERS = [1, 2, 3]  # three layers: the mock plants full signal only on the middle one
N_PAIRS = 120


def run(coro):
    return asyncio.run(coro)


class RecordingSource:
    """Wraps a source and keeps every message list it was asked to capture."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    async def capture(self, model_id, messages, layers):
        self.calls.append(messages)
        return await self.inner.capture(model_id, messages, layers)


def build(home, signal):
    store = Store(":memory:")
    rec = RecordingSource(MockActivationSource(dim=16, signal=signal, seed=0))
    svc = ReliabilityService(ClaimLedger(store, lambda: 1.0), store, rec,
                             ProbeConfig(layers=LAYERS), lambda t, p: None, home=home)
    return svc, store, rec


def lie_marking_text_for(false_texts):
    """Live layout text; the mock source needs a meta mark to know a statement is false.
    The mark is not text (no real source reads it), so the content stays the layout's."""
    def text_for(task, statement):
        msgs = default_text_for(task, statement)
        if statement in false_texts:
            msgs[-1]["meta"] = {"lie": True}
        return msgs
    return text_for


class Trained:
    """One trained model, shared by the tests that only read it."""
    svc = store = rec = card = home = None
    train_calls = 0
    _tmp = None

    @classmethod
    def get(cls):
        if cls.card is None:
            cls._tmp = tempfile.TemporaryDirectory()
            cls.home = Path(cls._tmp.name)
            cls.svc, cls.store, cls.rec = build(cls.home, signal=3.0)
            cls.card = run(cls.svc.train_statements(MODEL, now=1.0, seed=0, n=N_PAIRS))
            cls.train_calls = len(cls.rec.calls)
        return cls


def tearDownModule():
    if Trained._tmp is not None:
        Trained._tmp.cleanup()
    if Trained.store is not None:
        Trained.store.close()


class ProbeTrainLifecycle(unittest.TestCase):
    def test_gate_decides_and_card_is_active(self):
        t = Trained.get()
        card = t.card
        self.assertIsInstance(card, ProbeCard)
        self.assertTrue(card.active, card.reason)
        self.assertGreaterEqual(card.auroc, 0.80)
        self.assertGreaterEqual(card.n_test, 30)
        # the gate, run again on the card's own numbers, agrees
        again = card_with_gate(card)
        self.assertTrue(again.active, again.reason)
        # and it refuses a leaking control or a probe no better than surface features
        self.assertFalse(decide_active(card.auroc, card.n_test, 0.9, card.baseline_auroc)[0])
        self.assertFalse(decide_active(card.auroc, card.n_test, card.control_auroc,
                                       card.auroc)[0])
        self.assertFalse(card_with_gate(card.model_copy(update={"auroc": 0.6})).active)

    def test_save_then_load_roundtrip_through_files(self):
        t = Trained.get()
        files = ProbeFiles(t.home)
        got = files.load(MODEL)
        self.assertIsNotNone(got, "no active probe file after training")
        card, probes, platt = got
        self.assertTrue(card.active)
        self.assertEqual(card.version, t.card.version)
        self.assertEqual(files.layout_version(MODEL), layout.LAYOUT_VERSION)
        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0].status, "validated")
        self.assertEqual(len(probes[0].weights), 16)
        # the store copy and the file copy are the same probe
        stored = t.svc.get_probe(MODEL)
        self.assertEqual(stored.weights, probes[0].weights)
        self.assertEqual(stored.bias, probes[0].bias)
        self.assertIsNotNone(platt)
        self.assertGreater(platt[0], 0)
        # the file on disk is plain json and keeps its layout mark
        blob = json.loads((t.home / "probes" / MODEL / f"v{card.version}.json")
                          .read_text(encoding="utf-8"))
        self.assertEqual(blob["layout_version"], layout.LAYOUT_VERSION)
        # a fresh service on the same home (no store) serves the loaded probe
        svc2, store2, _ = build(t.home, 3.0)
        self.addCleanup(store2.close)
        self.assertEqual([p.weights for p in svc2.active_probes(MODEL)], [probes[0].weights])
        self.assertEqual(svc2.platt_for(MODEL), (platt[0], platt[1]))

    def test_live_scorer_true_above_false(self):
        t = Trained.get()
        pairs = trainer.builtin_pairs(7, 60)
        falses = {p.lie_text for p in pairs}
        scorer = LiveScorer(t.rec, t.svc.active_probes, text_for=lie_marking_text_for(falses),
                            platt_for=t.svc.platt_for)
        claims, truth = [], {}
        for i, p in enumerate(pairs):
            for kind, text in (("t", p.honest_text), ("f", p.lie_text)):
                cid = f"{kind}{i}"
                claims.append(ClaimSpan(claim_id=cid, text=text))
                truth[cid] = 1 if kind == "t" else 0
        scorer.max_claims = len(claims)
        scores = run(scorer.score_claims(MODEL, trainer.STATEMENT_TASK, claims))
        self.assertEqual(set(scores), set(truth))
        self.assertTrue(all(v is not None and 0.0 <= v <= 1.0 for v in scores.values()))
        ids = sorted(truth)
        area = auroc([scores[c] for c in ids], [truth[c] for c in ids])
        self.assertGreater(area, 0.9, f"live truth-score AUROC {area:.3f}")
        # pair by pair: the true twin is above the false twin almost always
        wins = sum(scores[f"t{i}"] > scores[f"f{i}"] for i in range(len(pairs)))
        self.assertGreaterEqual(wins / len(pairs), 0.85)
        mean = lambda kind: sum(v for c, v in scores.items() if c[0] == kind) / len(pairs)
        self.assertGreater(mean("t"), mean("f") + 0.3)

    def test_shuffled_label_control_near_half(self):
        t = Trained.get()
        card = t.card
        self.assertIsNotNone(card.control_auroc)
        self.assertLess(abs(card.control_auroc - 0.5), 0.15, card.control_auroc)
        self.assertLessEqual(card.control_auroc, trainer.MAX_CONTROL)
        # the real signal is far from that control, and the cheap baseline is not close either
        self.assertGreater(card.auroc - card.control_auroc, 0.3)
        self.assertGreaterEqual(card.auroc - card.baseline_auroc, trainer.BASELINE_MARGIN)
        # same numbers straight from the trainer, new run, same seed: a report, not a stub
        report = run(trainer.train_from_pairs(
            MockActivationSource(dim=16, signal=3.0, seed=0), MODEL,
            trainer.builtin_pairs(0, N_PAIRS), LAYERS, 0.8, 1.0, seed=0))
        self.assertEqual(report["status"], "validated")
        self.assertLess(abs(report["shuffled_auroc"] - 0.5), 0.15)
        self.assertAlmostEqual(report["shuffled_auroc"], card.control_auroc, places=9)
        self.assertEqual(report["layout"], trainer.LAYOUT)

    def test_training_layout_is_live_layout(self):
        t = Trained.get()
        task, statement = trainer.STATEMENT_TASK, "The capital of Peru is Lima."
        # one function builds both sides
        train_msgs = trainer.pair_messages(statement)
        live_msgs = default_text_for(task, statement)
        self.assertEqual(train_msgs[0]["content"], live_msgs[0]["content"])
        self.assertEqual(train_msgs[0]["content"], layout.probe_text(task, statement))
        self.assertTrue(train_msgs[0]["content"].endswith(layout.TAIL))
        # what training really sent to the source is all in that layout
        self.assertGreater(t.train_calls, 2 * N_PAIRS - 1)
        for msgs in t.rec.calls[:t.train_calls]:
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0]["role"], "user")
            content = msgs[0]["content"]
            self.assertTrue(content.startswith(f"Question: {trainer.STATEMENT_TASK}\nStatement: "))
            self.assertTrue(content.endswith("\n" + layout.TAIL))
        # a live claim of a trained statement reaches the source with byte-identical text
        pair = trainer.builtin_pairs(0, N_PAIRS)[0]
        before = len(t.rec.calls)
        run(LiveScorer(t.rec, t.svc.active_probes).score_claims(
            MODEL, task, [ClaimSpan(claim_id="c1", text=pair.honest_text)]))
        self.assertEqual(len(t.rec.calls), before + 1)
        live_sent = t.rec.calls[-1][0]["content"]
        trained_sent = {m[0]["content"] for m in t.rec.calls[:t.train_calls]}
        self.assertIn(live_sent, trained_sent)
        # the lie mark is meta, never text: both twins of a pair differ only in the statement
        lie_msgs = trainer.pair_messages(pair.lie_text, True)
        self.assertEqual(lie_msgs[0]["content"], layout.probe_text(task, pair.lie_text))
        self.assertNotIn("lie", lie_msgs[0]["content"].lower().split("statement:")[0])

    def test_noise_source_is_refused_and_not_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            svc, store, rec = build(home, signal=0.0)
            self.addCleanup(store.close)
            card = run(svc.train_statements("m-noise", now=1.0, seed=0, n=N_PAIRS))
            self.assertFalse(card.active, card.reason)
            self.assertTrue(card.reason)
            self.assertLess(card.auroc, 0.80)
            self.assertEqual(svc.active_probes("m-noise"), [])
            files = ProbeFiles(home)
            self.assertIsNone(files.load("m-noise"))  # no active.txt: nothing is switched on
            before = len(rec.calls)
            out = run(LiveScorer(rec, svc.active_probes).score_claims(
                "m-noise", "q", [ClaimSpan(claim_id="c1", text="x")]))
            self.assertEqual(out, {})
            self.assertEqual(len(rec.calls), before)  # no capture was made

    def test_probe_of_another_layout_is_retired(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            svc, store, _ = build(home, signal=3.0)
            self.addCleanup(store.close)
            run(svc.train_statements("m-old", now=1.0, seed=0, n=N_PAIRS))
            self.assertTrue(svc.active_probes("m-old"))
            blob_path = home / "probes" / "m-old" / "v1.json"
            blob = json.loads(blob_path.read_text(encoding="utf-8"))
            blob["layout_version"] = layout.LAYOUT_VERSION - 1
            blob_path.write_text(json.dumps(blob), encoding="utf-8")
            self.assertEqual(svc.active_probes("m-old"), [])
            old = [c for c in svc.cards() if c.model_id == "m-old"][0]
            self.assertFalse(old.active)


if __name__ == "__main__":
    unittest.main()
