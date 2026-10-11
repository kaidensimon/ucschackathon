import json
import random
import unittest

from council.core.schemas import BenchTask
from council.probe.trainer import (
    attribution,
    bootstrap_dataset,
    default_false_answer,
    score,
    train_probe,
)

MARK = "ZZLIEZZ"


class FakeSource:
    def __init__(self, signal=True, dim=8):
        self.signal = signal
        self.dim = dim
        self.n = 0

    async def capture(self, model_id, messages, layers):
        self.n += 1
        rng = random.Random(self.n)
        lie = MARK in json.dumps(messages)
        out = {}
        for l in layers:
            v = [rng.gauss(0, 1) for _ in range(self.dim)]
            if self.signal and l == layers[-1]:
                v[3] += 4.0 if lie else -4.0
                v[3] += 100.0  # offset exercises standardisation
            out[l] = v
        return out


def tasks(n=40):
    return [BenchTask(id=f"t{i}", prompt=f"q{i}", answer_type="exact", answer=f"a{i}") for i in range(n)]


def run(coro):
    import asyncio
    return asyncio.run(coro)


class TrainerTests(unittest.TestCase):
    def build(self, signal):
        src = FakeSource(signal)
        data = run(bootstrap_dataset(src, "m", tasks(), [4, 8], false_answer=lambda t: MARK))
        return data

    def test_dataset_shape(self):
        data = self.build(True)
        X, y = data[4]
        self.assertEqual(len(X), 80)
        self.assertEqual(sum(y), 40)

    def test_signal_validates(self):
        p = train_probe("m", self.build(True), 0.8, 123.0)
        self.assertEqual(p.status, "validated")
        self.assertEqual(p.layer, 8)
        self.assertGreaterEqual(p.auroc, 0.8)
        self.assertEqual(attribution(p, 1)[0][0], 3)
        raw = FakeSource(True)
        lie = run(raw.capture("m", [{"content": MARK}], [4, 8]))
        hon = run(raw.capture("m", [{"content": "x"}], [4, 8]))
        self.assertGreater(score(p, lie), score(p, hon))

    def test_no_signal_rejected(self):
        p = train_probe("m", self.build(False), 0.8, 1.0)
        self.assertEqual(p.status, "rejected")
        self.assertIsNone(score(p, {4: [0.0] * 8, 8: [0.0] * 8}))

    def test_empty_rejected(self):
        self.assertEqual(train_probe("m", {}, 0.8, 1.0).status, "rejected")

    def test_default_false_answers(self):
        m = BenchTask(id="a", prompt="p", answer_type="mcq", answer="A", choices=["x", "y"])
        self.assertEqual(default_false_answer(m), "B")
        n = BenchTask(id="b", prompt="p", answer_type="numeric", answer="41")
        self.assertEqual(default_false_answer(n), "42")
        e = BenchTask(id="c", prompt="p", answer_type="exact", answer="cat")
        self.assertNotEqual(default_false_answer(e), "cat")


class GateTests(unittest.TestCase):
    def data(self, n, signal, layers=(4, 8)):
        return run(bootstrap_dataset(FakeSource(signal), "m", tasks(n), list(layers),
                                     false_answer=lambda t: MARK))

    def test_noise_on_a_few_tasks_is_never_validated(self):
        # Reviewer repro: with 3 to 5 tasks the held-out set was 2 rows and AUROC 0 or 1.
        for n in (3, 4, 5, 8):
            data = self.data(n, False)
            for seed in range(20):
                p = train_probe("m", data, 0.8, 1.0, seed=seed)
                self.assertNotEqual(p.status, "validated", (n, seed))
                self.assertIsNone(score(p, {4: [0.0] * 8, 8: [0.0] * 8}))

    def test_real_signal_on_too_few_tasks_is_only_a_candidate(self):
        p = train_probe("m", self.data(12, True), 0.8, 1.0)
        self.assertEqual(p.status, "candidate")
        self.assertGreaterEqual(p.auroc, 0.8)
        self.assertIsNone(score(p, {8: [0.0] * 8}))  # no live score from a candidate
        ok = train_probe("m", self.data(12, True), 0.8, 1.0, min_gate_per_class=2)
        self.assertEqual(ok.status, "validated")

    def test_rows_are_split_by_task_into_three_parts(self):
        from council.probe import trainer as T
        data = self.data(40, True)
        X, y = data[8]
        groups = T._groups(data[8], len(X))
        self.assertEqual(groups[:4], [0, 0, 1, 1])  # the honest and the lie row of a task stay together
        train, select, gate = T._split_groups(groups, 0, True)
        self.assertEqual(len(train | select | gate), 40)
        self.assertEqual(len(train) + len(select) + len(gate), 40)  # disjoint
        self.assertGreaterEqual(len(gate), T.MIN_GATE_PER_CLASS)
        self.assertTrue(select)
        train, select, gate = T._split_groups(groups, 0, False)  # one layer: nothing to pick
        self.assertEqual(select, set())
        self.assertIsNone(T._split_groups([0, 0], 0, False))

    def test_reported_auroc_is_measured_on_the_gate_rows_only(self):
        from council.probe import trainer as T
        from council.probe.logreg import auroc, predict_proba
        data = self.data(40, True)
        probe, picked = T.evaluate("m", data, 0.8, 1.0)
        self.assertEqual(set(picked), {4, 8})
        self.assertEqual(probe.layer, 8)
        X, y = data[8]
        groups = T._groups(data[8], len(X))
        _, _, gate = T._split_groups(groups, 0, True)
        rows = [i for i, g in enumerate(groups) if g in gate]
        want = auroc([predict_proba(probe.weights, probe.bias, X[i]) for i in rows], [y[i] for i in rows])
        self.assertAlmostEqual(probe.auroc, want)
        self.assertEqual(probe.n_train, 2 * (40 - len(gate) - 6))


class LengthSource:
    """Activations that know only how long the text is: a probe on them reads the wording."""

    async def capture(self, model_id, messages, layers):
        n = float(len(messages[-1]["content"]))
        return {l: [n, n * 0.5, 1.0, -n] for l in layers}


class FlakySource:
    def __init__(self, inner, bad):
        self.inner, self.bad, self.texts = inner, bad, []

    async def capture(self, model_id, messages, layers):
        text = messages[-1]["content"]
        self.texts.append(text)
        if any(b in text for b in self.bad):
            raise RuntimeError("boom")
        return await self.inner.capture(model_id, messages, layers)


class TrainFromPairsTests(unittest.TestCase):
    def setUp(self):
        from council.probe import trainer as T
        from council.probe.activations import MockActivationSource
        from council.probe.dataset import Pair, statement_pairs
        self.T, self.Mock, self.Pair = T, MockActivationSource, Pair
        self.pairs = statement_pairs(0, 80)

    def train(self, source, pairs=None, layers=(4, 8, 12), **kw):
        return run(self.T.train_from_pairs(source, "m", self.pairs if pairs is None else pairs,
                                           list(layers), 0.8, 5.0, **kw))

    def test_planted_signal_validates_with_both_controls(self):
        from council.core.schemas import Probe
        rep = self.train(self.Mock(dim=16, signal=3.0))
        self.assertEqual(rep["status"], "validated")
        self.assertTrue(rep["validated"])
        self.assertEqual([r["layer"] for r in rep["layers"]], [4, 8, 12])
        self.assertEqual(rep["best_layer"], 8)  # the mock plants most signal in the middle layer
        self.assertEqual(sum(1 for r in rep["layers"] if r["picked"]), 1)
        self.assertGreaterEqual(rep["auroc"], 0.9)
        self.assertLess(abs(rep["shuffled_auroc"] - 0.5), 0.25)
        self.assertLess(rep["cheap_auroc"], 0.7)
        self.assertGreaterEqual(rep["auroc"], rep["cheap_auroc"] + 0.1)
        self.assertEqual(rep["n_train_pairs"] + rep["n_select_pairs"] + rep["n_test_pairs"], 80)
        self.assertEqual(rep["n_test_pairs"], 24)
        for r in rep["layers"]:
            self.assertEqual(r["n_train"], 2 * rep["n_train_pairs"])
            self.assertEqual(r["n_test"], 48)
            self.assertEqual(r["cheap_auroc"], rep["cheap_auroc"])
            for key in ("auroc", "select_auroc", "shuffled_auroc"):
                self.assertTrue(0.0 <= r[key] <= 1.0)
        probe = Probe.model_validate(rep["probe"])
        self.assertEqual((probe.status, probe.layer, probe.trained_at), ("validated", 8, 5.0))
        self.assertEqual(probe.auroc, rep["auroc"])
        self.assertEqual(probe.n_train, 2 * rep["n_train_pairs"])
        self.assertEqual(len(probe.weights), 16)
        json.dumps(rep)  # the report is plain data
        # the stored probe scores a fresh lie above a fresh honest text
        src = self.Mock(dim=16, signal=3.0)
        lie = run(src.capture("m", self.T.pair_messages("2 + 2 = 5.", True), [4, 8, 12]))
        hon = run(src.capture("m", self.T.pair_messages("2 + 2 = 4."), [4, 8, 12]))
        self.assertGreater(score(probe, lie), score(probe, hon))

    def test_deterministic(self):
        a = self.train(self.Mock(dim=8, signal=3.0), layers=(8,))
        b = self.train(self.Mock(dim=8, signal=3.0), layers=(8,))
        self.assertEqual(a, b)

    def test_no_signal_is_rejected(self):
        rep = self.train(self.Mock(dim=16, signal=0.0))
        self.assertEqual(rep["status"], "rejected")
        self.assertFalse(rep["validated"])
        self.assertTrue(rep["reasons"])
        self.assertIsNone(score(Probe_(rep), {rep["best_layer"]: [0.0] * 16}))

    def test_probe_that_only_reads_length_is_rejected_by_the_cheap_baseline(self):
        pairs = [self.Pair(f"t{i}", "logic", f"Question: q{i}?\nAnswer: yes",
                           f"Question: q{i}?\nAnswer: certainly not at all", "yes",
                           "certainly not at all") for i in range(60)]
        rep = self.train(LengthSource(), pairs, layers=(3,))
        self.assertGreaterEqual(rep["auroc"], 0.95)  # a great number ...
        self.assertGreaterEqual(rep["cheap_auroc"], 0.95)  # ... that length alone explains
        self.assertEqual(rep["status"], "rejected")
        self.assertIn("cheap-feature baseline", rep["reasons"][0])

    def test_good_signal_on_few_questions_is_only_a_candidate(self):
        rep = self.train(self.Mock(dim=8, signal=4.0), self.pairs[:20], layers=(8,))
        self.assertEqual(rep["n_test_pairs"], 6)
        self.assertEqual(rep["status"], "candidate")
        self.assertIn("held-out questions", rep["reasons"][0])
        ok = self.train(self.Mock(dim=8, signal=4.0), self.pairs[:20], layers=(8,),
                        min_test_per_class=5)
        self.assertEqual(ok["status"], "validated")

    def test_too_few_pairs_is_rejected_without_a_crash(self):
        for n in (0, 1, 2):
            rep = self.train(self.Mock(dim=8), self.pairs[:n])
            self.assertEqual(rep["status"], "rejected")
            self.assertEqual(rep["layers"], [])
            self.assertEqual(rep["probe"]["status"], "rejected")
        rep = self.train(self.Mock(dim=8), self.pairs[:4])  # too few to hold out a select part
        self.assertNotEqual(rep["status"], "validated")

    def test_one_layer_has_no_select_part(self):
        rep = self.train(self.Mock(dim=8, signal=3.0), layers=(8,))
        self.assertEqual(rep["n_select_pairs"], 0)
        self.assertEqual(rep["layers"][0]["select_auroc"], rep["layers"][0]["auroc"])
        many = self.train(self.Mock(dim=8, signal=3.0), layers=(4, 8))
        self.assertGreater(many["n_select_pairs"], 0)

    def test_both_texts_are_captured_and_no_instruction_is_sent(self):
        src = FlakySource(self.Mock(dim=8, signal=3.0), bad=[])
        pairs = self.pairs[:12]
        self.train(src, pairs, layers=(8,))
        self.assertEqual(len(src.texts), 24)
        from council.probe.layout import TAIL, probe_text
        self.assertEqual(set(src.texts), {probe_text(self.T.STATEMENT_TASK, t)
                                          for p in pairs for t in (p.honest_text, p.lie_text)})
        self.assertTrue(all(t.endswith(TAIL) for t in src.texts))
        msgs = self.T.pair_messages("x", True)
        self.assertEqual([m["role"] for m in msgs], ["user"])  # no system instruction at all
        self.assertEqual(msgs[0]["content"], probe_text(self.T.STATEMENT_TASK, "x"))
        self.assertNotIn("meta", self.T.pair_messages("x")[0])

    def test_failed_captures_are_skipped_and_counted(self):
        bad = [self.pairs[0].honest_text, self.pairs[5].lie_text]
        seen = []
        rep = self.train(FlakySource(self.Mock(dim=8, signal=3.0), bad), layers=(8,),
                         progress=lambda done, total: seen.append((done, total)))
        self.assertEqual(rep["n_capture_errors"], 2)
        self.assertEqual(rep["n_used"], 78)
        self.assertIn("boom", rep["capture_errors"][0])
        self.assertEqual(seen[-1], (80, 80))
        with self.assertRaises(RuntimeError):
            self.train(FlakySource(self.Mock(dim=8), bad=[""]), layers=(8,))

    def test_wide_activations_use_the_gram_path_and_match_plain_descent(self):
        from council.probe.logreg import standardize, train_logreg
        rng = random.Random(1)
        X = [[rng.gauss(0, 1) for _ in range(40)] for _ in range(12)]
        y = [i % 2 for i in range(12)]
        for row, label in zip(X, y):
            row[7] += 3.0 * label
        Xs, _, _ = standardize(X)
        K = [[sum(a * b for a, b in zip(r, s)) for s in Xs] for r in Xs]
        w, b = self.T._fit_dual(K, Xs, y)
        w2, b2 = train_logreg(Xs, y, seed=0)
        self.assertAlmostEqual(b, b2, places=2)
        self.assertLess(max(abs(p - q) for p, q in zip(w, w2)), 0.02)
        rep = self.train(self.Mock(dim=300, signal=6.0), self.pairs[:60], layers=(8,))
        self.assertGreater(300, rep["layers"][0]["n_train"])  # more dimensions than rows
        self.assertEqual(rep["status"], "validated")

    def test_cheap_features(self):
        self.assertEqual(self.T.cheap_features("Answer: 4.", "4."), [2.0, 2.0, 10.0, 4.0])


class LayoutAndGate(unittest.TestCase):
    """1.5: one text layout for every row, the gate decides, Platt calibrates."""

    def setUp(self):
        from council.probe import trainer as T
        from council.probe.activations import MockActivationSource
        from council.probe.dataset import statement_pairs
        self.T, self.Mock = T, MockActivationSource
        self.pairs = statement_pairs(0, 80)

    def test_every_training_text_is_the_probe_layout(self):
        from council.probe.layout import LAYOUT_VERSION, TAIL, probe_messages
        T = self.T
        self.assertGreater(T.LAYOUT, 1)  # layout 1 probes are refused
        self.assertEqual(T.LAYOUT, LAYOUT_VERSION + 1)
        self.assertEqual(T.honest_messages("q", "a"), probe_messages("q", "a"))
        lie = T.lie_messages("q", "b")
        self.assertEqual(lie[0]["meta"], {"lie": True})
        self.assertEqual([(m["role"], m["content"]) for m in lie],
                         [(m["role"], m["content"]) for m in probe_messages("q", "b")])
        self.assertEqual(T.pair_messages("Paris is in France."),
                         probe_messages(T.STATEMENT_TASK, "Paris is in France."))
        self.assertEqual(T.split_pair_text("Question: 2+2?" + chr(10) + "Answer: 4"), ("2+2?", "4"))
        self.assertEqual(T.pair_messages("Question: 2+2?" + chr(10) + "Answer: 4"),
                         probe_messages("2+2?", "4"))
        for msgs in (T.honest_messages("q", "a"), lie, T.pair_messages("x", True)):
            self.assertEqual(len(msgs), 1)
            self.assertTrue(msgs[0]["content"].endswith(TAIL))
        src = FlakySource(self.Mock(dim=8), bad=[])
        run(bootstrap_dataset(src, "m", tasks(3), [4]))
        self.assertEqual(len(src.texts), 6)
        self.assertTrue(all(t.startswith("Question: q") and t.endswith(TAIL) for t in src.texts))

    def test_builtin_pairs_mix_both_sets_and_keep_groups_apart(self):
        from council.probe.dataset import split_by_task
        pairs = self.T.builtin_pairs(0, 300)
        self.assertEqual(len(pairs), 300)
        self.assertEqual(len({p.task_id for p in pairs}), 300)
        self.assertEqual(sum(1 for p in pairs if p.task_id.startswith("stmt-")), 100)
        self.assertEqual(sum(1 for p in pairs if p.task_id.startswith("tset-")), 200)
        self.assertEqual(self.T.builtin_pairs(0, 300), pairs)
        self.assertEqual(self.T.builtin_pairs(0, 0), [])
        train, test = split_by_task(pairs, 0.3, 0)
        self.assertFalse({p.task_id for p in train} & {p.task_id for p in test})

    def test_report_has_the_gate_the_accuracy_and_a_platt_pair(self):
        from council.probe import calibration
        rep = run(self.T.train_from_pairs(self.Mock(dim=16, signal=3.0), "m", self.pairs,
                                          [4, 8, 12], 0.8, 5.0))
        self.assertEqual((rep["layout"], rep["active"], rep["status"]), (self.T.LAYOUT, True, "validated"))
        self.assertIn("auroc", rep["gate_reason"])
        self.assertGreaterEqual(rep["accuracy"], 0.9)
        self.assertEqual(rep["platt_on"], "select")
        a, b = rep["platt"]
        self.assertGreater(a, 0)
        # the pair maps the truth score 1 - P(lie): a sure lie low, a sure truth high
        self.assertLess(calibration.apply_platt(0.0, (a, b)), 0.3)
        self.assertGreater(calibration.apply_platt(1.0, (a, b)), 0.7)
        self.assertLess(rep["ece"], 0.2)
        one = run(self.T.train_from_pairs(self.Mock(dim=8, signal=3.0), "m", self.pairs, [8], 0.8, 5.0))
        self.assertEqual(one["platt_on"], "test")  # no select part with one layer

    def test_a_control_that_finds_signal_rejects_the_probe(self):
        rep = run(self.T.train_from_pairs(self.Mock(dim=16, signal=3.0), "m", self.pairs,
                                          [4, 8, 12], 0.8, 5.0, max_control=0.0))
        self.assertEqual((rep["status"], rep["active"], rep["validated"]), ("rejected", False, False))
        self.assertIn("shuffled-label control", rep["reasons"][0])
        self.assertIn("leak", rep["gate_reason"])
        self.assertIsNone(score(Probe_(rep), {rep["best_layer"]: [0.0] * 16}))

    def test_inactive_reports_say_why(self):
        few = run(self.T.train_from_pairs(self.Mock(dim=8, signal=4.0), "m", self.pairs[:20], [8], 0.8, 5.0))
        self.assertEqual((few["status"], few["active"]), ("candidate", False))
        self.assertIn("held-out", few["gate_reason"])
        none = run(self.T.train_from_pairs(self.Mock(dim=8), "m", [], [8], 0.8, 5.0))
        self.assertEqual((none["active"], none["platt"], none["accuracy"]), (False, None, None))


def Probe_(rep):
    from council.core.schemas import Probe
    return Probe.model_validate(rep["probe"])


if __name__ == "__main__":
    unittest.main()
