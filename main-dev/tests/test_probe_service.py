import asyncio
import unittest

from council.core.config import LieConfig, ProbeConfig
from council.core.schemas import BenchTask, CallResult, Claim, Draft, SeatAssignment
from council.core.schemas_v15 import LieReport, ProbeCard
from council.core.store import Store
from council.probe import trainer
from council.probe.activations import LIE_MARKER, MockActivationSource, OllamaEmbedSource
from council.probe.layout import LAYOUT_VERSION, TAIL, probe_messages
from council.probe.lie_report import NO_PROBE_NOTE
from council.probe.probe_files import ProbeFiles
from council.probe.ledger import ClaimLedger
from council.probe.llamacpp_source import ActivationError, LlamaCppActivationSource, pick_layers
from council.probe.service import OLD_LAYOUT_REASON, ReliabilityService, build_source


def run(c):
    return asyncio.run(c)


def tasks(n=48):
    return [BenchTask(id=f"t{i}", prompt=f"question {i}", answer_type="mcq",
                      choices=["a", "b", "c", "d"], answer="A") for i in range(n)]


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.s = Store(":memory:")
        self.events = []
        self.cfg = ProbeConfig(layers=[1, 2, 3])
        self.src = MockActivationSource(dim=16, signal=3.0)
        self.svc = ReliabilityService(ClaimLedger(self.s, lambda: 1.0), self.s, self.src,
                                      self.cfg, lambda t, p: self.events.append((t, p)))
        self.seats = [SeatAssignment(seat_no=1, model_id="m1"), SeatAssignment(seat_no=2, model_id="m2")]
        d = Draft(answer="x", confidence=0.8, claims=[Claim(id="c1", text="t")])
        self.drafts = {1: d, 2: d}
        self.results = {1: CallResult(call_id="a", ok=True, logprobs=[-0.1, -0.2]),
                        2: CallResult(call_id="b", ok=True)}

    def tearDown(self):
        self.s.close()

    def test_no_probe(self):
        sc = run(self.svc.score_round0("r1", "p", self.seats, self.drafts, self.results))
        self.assertEqual(len(sc), 4)
        self.assertTrue(all(x.probe is None and x.probe_auroc is None for x in sc))
        self.assertTrue(all(0 <= x.reliability <= 1 for x in sc))
        self.assertEqual(len(self.s.claims_list()), 4)
        self.assertEqual([t for t, _ in self.events], ["probe.scores"] * 2 + ["lie.report"])
        self.assertIsNone(self.events[0][1]["probe_status"])
        self.assertEqual(self.events[-1][1]["report"]["note"], NO_PROBE_NOTE)
        self.assertEqual(self.svc.last_report("r1").run_id, "r1")
        self.assertIsNotNone(self.s.kv_get("lie_reports", "r1"))

    def test_train_and_score(self):
        p = run(self.svc.train_for("m1", tasks(), 5.0))
        self.assertEqual(p.status, "validated")
        self.assertEqual(self.svc.get_probe("m1").layer, p.layer)
        self.assertIsNone(self.svc.get_probe("zz"))
        self.assertEqual(self.events[-1][0], "probe.trained")
        self.assertTrue(self.events[-1][1]["validated"])
        self.assertEqual(set(self.events[-1][1]["auroc_by_layer"]), {"1", "2", "3"})
        sc = run(self.svc.score_round0("r1", "p", self.seats, self.drafts, self.results,
                                       lambda n: [{"role": "assistant", "content": "hi"}]))
        m1 = [x for x in sc if x.seat_no == 1]
        m2 = [x for x in sc if x.seat_no == 2]
        self.assertTrue(all(x.probe is not None and x.probe_auroc == p.auroc for x in m1))
        self.assertTrue(all(x.probe is None for x in m2))
        self.assertEqual([t for t, _ in self.events[-3:]], ["probe.scores", "probe.scores", "lie.report"])
        self.assertEqual(self.events[-3][1]["probe_status"], "validated")
        self.assertEqual(self.events[-1][1]["report"]["probe_models"], ["m1"])

    def test_probe_score_reads_like_reliability(self):
        # ClaimScore.probe is shown as "0 = likely wrong, 1 = likely right": a marked lie must
        # score LOW and an honest answer HIGH. (It used to hold P(lie), the other way round.)
        run(self.svc.train_for("m1", tasks(), 5.0))
        seats = self.seats[:1]

        def score_of(statement):
            # the probe reads the claim text in the probe layout; the mock knows a lie by its mark
            drafts = {1: Draft(answer="x", confidence=0.8, claims=[Claim(id="c1", text=statement)])}
            sc = run(self.svc.score_round0("r", "p", seats, drafts, self.results,
                                           lambda n: [{"role": "user", "content": "q"}]))
            self.assertEqual(sc[0].probe, sc[1].probe)  # one claim: the answer reads the same
            return sc[1].probe

        honest = score_of("a")
        lie = score_of("a " + LIE_MARKER)
        self.assertGreater(honest, 0.5)
        self.assertLess(lie, 0.5)

    def test_mock_bootstrap_carries_the_lie_signal(self):
        # The bootstrap prompts must reach the mock's planted direction: every layer separates.
        self.svc.cfg = ProbeConfig(layers=[8, 12, 16, 20])
        self.svc.source = MockActivationSource()
        p = run(self.svc.train_for("m1", tasks(), 5.0))
        self.assertEqual(p.status, "validated")
        self.assertIn(p.layer, (12, 16))  # the planted signal is strongest in the middle
        self.assertGreater(max(self.events[-1][1]["auroc_by_layer"].values()), 0.8)

    def test_too_few_tasks_is_never_validated(self):
        p = run(self.svc.train_for("m1", tasks(8), 5.0))
        self.assertNotEqual(p.status, "validated")
        sc = run(self.svc.score_round0("r1", "p", self.seats, self.drafts, self.results,
                                       lambda n: [{"role": "assistant", "content": "hi"}]))
        self.assertTrue(all(x.probe is None for x in sc))

    def test_no_source(self):
        svc = ReliabilityService(ClaimLedger(self.s, lambda: 1.0), self.s, None, self.cfg,
                                 lambda t, p: None)
        with self.assertRaises(ValueError):
            run(svc.train_for("m1", tasks(), 1.0))

    def test_refit(self):
        w = self.svc.refit_behaviour("m1")
        self.assertIn("bias", w)

    def test_build_source(self):
        self.assertIsInstance(build_source(ProbeConfig(source="mock"), None), MockActivationSource)
        self.assertIsNone(build_source(ProbeConfig(source="none"), None))

        class C:
            async def embed(self, tag, xs):
                return [[1.0]]

        class G:
            client = C()
        src = build_source(ProbeConfig(source="ollama_embed"), G())
        self.assertIsInstance(src, OllamaEmbedSource)
        self.assertIsNone(build_source(ProbeConfig(source="ollama_embed"), object()))


class _DepthSource(MockActivationSource):
    """A mock that knows its depth and holds a "process", like the llamacpp source."""

    def __init__(self, n_layer, **kw):
        super().__init__(**kw)
        self.n_layer = n_layer
        self.info_calls = 0
        self.closed = 0
        self.asked = set()

    async def info(self, model_id):
        self.info_calls += 1
        return {"n_layer": self.n_layer, "n_embd": self.dim, "architecture": "fake"}

    async def capture(self, model_id, messages, layers):
        self.asked.update(layers)
        return await super().capture(model_id, messages, layers)

    async def close(self, model_id=None):
        self.closed += 1


class LayerChoice(unittest.TestCase):
    def service(self, source, layers):
        store = Store(":memory:")
        self.addCleanup(store.close)
        self.events = []
        return ReliabilityService(ClaimLedger(store, lambda: 1.0), store, source,
                                  ProbeConfig(layers=layers), lambda t, p: self.events.append((t, p)))

    def test_empty_layers_are_picked_from_the_depth(self):
        src = _DepthSource(32, dim=16, signal=3.0)
        svc = self.service(src, [])
        self.assertEqual(run(svc.layers_for("m1")), pick_layers(32))
        p = run(svc.train_for("m1", tasks(), 1.0))
        self.assertEqual(self.events[-1][1]["layers_tried"], [8, 13, 19, 24])
        self.assertEqual(src.asked, {8, 13, 19, 24})
        self.assertIn(p.layer, (8, 13, 19, 24))
        self.assertEqual(src.closed, 1)  # the model copy is given back after training

    def test_configured_layers_the_model_lacks_are_dropped(self):
        svc = self.service(_DepthSource(12), [8, 12, 16, 20])
        self.assertEqual(run(svc.layers_for("m1")), [8])
        svc = self.service(_DepthSource(6), [8, 12, 16, 20])  # none fit: pick from the depth
        self.assertEqual(run(svc.layers_for("m1")), pick_layers(6))

    def test_configured_layers_win_when_they_fit(self):
        svc = self.service(_DepthSource(32), [4, 30])
        self.assertEqual(run(svc.layers_for("m1")), [4, 30])

    def test_source_without_depth(self):
        svc = self.service(MockActivationSource(), [])
        self.assertEqual(run(svc.layers_for("m1")), [8, 12, 16, 20])
        svc = self.service(MockActivationSource(), [1, 2])
        self.assertEqual(run(svc.layers_for("m1")), [1, 2])

    def test_info_failure_stops_training_and_releases(self):
        class Broken(_DepthSource):
            async def info(self, model_id):
                raise ActivationError("actdump binary is missing: /x")
        src = Broken(32)
        svc = self.service(src, [])
        with self.assertRaises(ActivationError):
            run(svc.train_for("m1", tasks(), 1.0))
        self.assertEqual(src.closed, 1)
        self.assertEqual(self.events, [])

    def test_score_releases_the_source_and_survives_a_dead_tool(self):
        src = _DepthSource(32, dim=16, signal=3.0)
        svc = self.service(src, [])
        run(svc.train_for("m1", tasks(), 1.0))
        seats = [SeatAssignment(seat_no=1, model_id="m1")]
        d = {1: Draft(answer="x", confidence=0.8, claims=[])}
        r = {1: CallResult(call_id="a", ok=True)}
        msgs = lambda n: [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
        sc = run(svc.score_round0("r", "p", seats, d, r, msgs))
        self.assertIsNotNone(sc[0].probe)
        self.assertEqual(src.closed, 2)

        async def dead(model_id, messages, layers):
            raise ActivationError("actdump for m1 died (no reply)")
        src.capture = dead
        sc = run(svc.score_round0("r2", "p", seats, d, r, msgs))
        self.assertIsNone(sc[0].probe)  # no score, no crash
        self.assertEqual(src.closed, 3)


class BuildLlamaCpp(unittest.TestCase):
    def test_build_from_config_and_registry(self):
        import json
        import tempfile
        from pathlib import Path
        from council.core.schemas import ModelEntry

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            digest = "sha256:" + "ab" * 32
            man = root / "manifests" / "registry.ollama.ai" / "library" / "gemma3" / "12b"
            man.parent.mkdir(parents=True)
            man.write_text(json.dumps({"layers": [
                {"mediaType": "application/vnd.ollama.image.model", "digest": digest}]}))
            blob = root / "blobs" / digest.replace(":", "-")
            blob.parent.mkdir()
            blob.write_bytes(b"GGUF")

            class G:
                registry = {"gemma-12b": ModelEntry(id="gemma-12b", ollama_tag="gemma3:12b")}

            cfg = ProbeConfig(source="llamacpp", actdump_path=str(root / "actdump"),
                              ollama_models_dir=str(root), max_models=2, pool="mean")
            src = build_source(cfg, G())
            self.assertIsInstance(src, LlamaCppActivationSource)
            self.assertEqual((src.binary, src.max_models, src.pool), (root / "actdump", 2, "mean"))
            self.assertEqual(src.blob_for("gemma-12b"), blob)
            self.assertIsNone(src.blob_for("not-in-registry"))
            # a registry given as a list works too, and no gateway means id = tag
            G.registry = list(G.registry.values())
            self.assertEqual(build_source(cfg, G()).blob_for("gemma-12b"), blob)
            self.assertEqual(build_source(cfg, None).blob_for("gemma3:12b"), blob)
            # the binary is absent: building is fine, the first use says so
            with self.assertRaisesRegex(ActivationError, "binary is missing"):
                run(src.capture("gemma-12b", [{"role": "user", "content": "q"}], [1]))

    def test_defaults(self):
        from pathlib import Path
        src = build_source(ProbeConfig(source="llamacpp"), None)
        self.assertIsInstance(src, LlamaCppActivationSource)
        self.assertEqual(src.binary, Path("~/council/tap-build/actdump").expanduser())
        self.assertEqual((src.max_models, src.pool), (1, "last"))
        self.assertIsNone(build_source(ProbeConfig(source="llamacpp", enabled=False), None))


class _Embedder:
    """Fake Ollama embed client. `mode` decides where the planted signal sits."""

    def __init__(self, mode):
        self.mode = mode
        self.texts = []

    async def embed(self, tag, inputs):
        import hashlib
        text = inputs[0]
        self.texts.append(text)
        raw = hashlib.sha256(text.encode()).digest()
        vec = [b / 255.0 - 0.5 for b in raw[:12]]
        if self.mode == "prompt_wording" and "deceive" in text:
            vec[0] += 5.0  # separates on the instruction text only
        if self.mode == "answer" and "WRONG" in text.split("Answer:")[-1]:
            vec[0] += 5.0  # a real signal in the answer span
        return [vec]


class OllamaSourceTraining(unittest.TestCase):
    def service(self, mode, layers=(8, 12, 16, 20)):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.client = _Embedder(mode)
        self.events = []
        src = OllamaEmbedSource(self.client, lambda m: m)
        return ReliabilityService(ClaimLedger(self.store, lambda: 1.0), self.store, src,
                                  ProbeConfig(layers=list(layers)), lambda t, p: self.events.append((t, p)))

    def test_pseudo_layer_is_used_whatever_the_config_layers_are(self):
        svc = self.service("answer")
        import council.probe.trainer as T
        orig = T.default_false_answer
        T.default_false_answer = lambda t: "WRONG " + t.id
        try:
            p = run(svc.train_for("m1", tasks(), 1.0))
        finally:
            T.default_false_answer = orig
        self.assertEqual(self.events[-1][1]["layers_tried"], [-1])  # not the empty set
        self.assertEqual((p.status, p.layer), ("validated", -1))

    def test_instruction_text_is_not_embedded(self):
        # A probe must not be able to separate honest from lie on the bootstrap instruction.
        svc = self.service("prompt_wording")
        p = run(svc.train_for("m1", tasks(), 1.0))
        self.assertTrue(self.client.texts)
        self.assertFalse(any("deceive" in t or "truthful" in t for t in self.client.texts))
        self.assertTrue(all("Question: question " in t and t.endswith(TAIL) for t in self.client.texts))
        self.assertNotEqual(p.status, "validated")


class LieDetector(unittest.TestCase):
    """1.5: one layout, probes in files and store, claims -> flags -> LieReport."""

    HONEST = "The capital of France is Paris."
    LIE = "The capital of France is Rome. " + LIE_MARKER

    def setUp(self):
        import tempfile
        from pathlib import Path
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.events = []
        self.src = _DepthSource(32, dim=16, signal=3.0)
        self.svc = self.service(self.store)
        self.seats = [SeatAssignment(seat_no=1, model_id="m1"), SeatAssignment(seat_no=2, model_id="m2")]
        draft = Draft(answer="x", confidence=0.9, claims=[Claim(id="c1", text=self.HONEST),
                                                          Claim(id="c2", text=self.LIE)])
        self.drafts = {1: draft, 2: draft}

    def service(self, store, **kw):
        kw.setdefault("home", self.home)
        return ReliabilityService(ClaimLedger(store, lambda: 1.0), store, self.src,
                                  ProbeConfig(layers=[]), lambda t, p: self.events.append((t, p)),
                                  lie_cfg=LieConfig(), **kw)

    def train(self, model_id="m1"):
        return run(self.svc.train_statements(model_id, now=5.0, n=150))

    def test_training_uses_both_statement_sets_the_gate_and_platt_and_saves_twice(self):
        texts = []
        orig = self.src.capture

        async def capture(model_id, messages, layers):
            texts.append(messages[-1]["content"])
            return await orig(model_id, messages, layers)
        self.src.capture = capture
        card = self.train()
        self.assertEqual(len(texts), 300)
        self.assertTrue(all(t.endswith(TAIL) and t.startswith("Question: ") for t in texts))
        pairs = trainer.builtin_pairs(0, 150)
        self.assertEqual(len(pairs), 150)
        self.assertTrue(any(p.task_id.startswith("stmt-") for p in pairs))
        self.assertTrue(any(p.task_id.startswith("tset-") for p in pairs))
        self.assertTrue(card.active, card.reason)
        self.assertEqual((card.model_id, card.version, card.source), ("m1", 1, "mock"))
        self.assertGreaterEqual(card.auroc, 0.9)
        self.assertLessEqual(card.control_auroc, trainer.MAX_CONTROL)
        self.assertLess(card.baseline_auroc, card.auroc)
        self.assertGreater(card.n_test, 0)
        self.assertIsNotNone(card.ece)
        self.assertIsNotNone(card.accuracy)
        # the files: probe, card, platt and the layout it was trained on
        files = ProbeFiles(self.home)
        self.assertTrue((self.home / "probes" / "m1" / "v1.json").is_file())
        self.assertEqual(files.layout_version("m1"), LAYOUT_VERSION)
        _, probes, platt = files.load("m1")
        self.assertEqual(probes[0].status, "validated")
        self.assertGreater(platt[0], 0)
        # the store: the same probe, readable as before, plus layout and platt
        raw = self.store.kv_get("probes", "m1")
        self.assertEqual(raw["layout"], trainer.LAYOUT)
        self.assertEqual(raw["platt"], list(platt))
        self.assertEqual(self.svc.get_probe("m1").layer, probes[0].layer)
        self.assertEqual(self.events[-1][0], "probe.trained")
        self.assertEqual(self.src.closed, 1)
        self.assertEqual([c.model_dump() for c in self.svc.cards()], [card.model_dump()])

    def test_lie_report_flags_the_false_claim_of_the_model_with_a_probe(self):
        self.train()
        self.events.clear()
        rep = run(self.svc.lie_report("r1", "What is the capital of France?", self.seats,
                                      self.drafts, {1: 0.9, 2: 0.4}))
        self.assertEqual((rep.run_id, rep.probe_models, rep.note), ("r1", ["m1"], ""))
        by = {(f.seat_no, f.claim_id): f for f in rep.flags}
        self.assertEqual(set(by), {(1, "c1"), (1, "c2"), (2, "c1"), (2, "c2")})
        self.assertGreater(by[(1, "c1")].probe_score, 0.5)
        self.assertEqual(by[(1, "c1")].level, "ok")
        self.assertLess(by[(1, "c2")].probe_score, 0.3)
        self.assertEqual(by[(1, "c2")].level, "flag")
        self.assertGreater(by[(1, "c2")].bluff_gap, 0.45)
        self.assertEqual(rep.flags[0].claim_id, "c2")  # worst first
        self.assertIsNone(by[(2, "c1")].probe_score)  # m2 has no probe
        self.assertEqual((by[(2, "c1")].stated_confidence, by[(1, "c1")].stated_confidence), (0.4, 0.9))
        self.assertTrue(all(0.0 <= f.behaviour_score <= 1.0 for f in rep.flags))
        self.assertTrue(all(f.track_record is None for f in rep.flags))  # nothing labelled yet
        seats = {s.seat_no: s for s in rep.seats}
        self.assertEqual((seats[1].claims, seats[1].flagged, seats[1].level), (2, 1, "flag"))
        self.assertEqual((seats[2].claims, seats[2].flagged), (2, 0))
        # event, memory, store
        self.assertEqual([t for t, _ in self.events], ["lie.report"])
        payload = self.events[0][1]
        self.assertEqual((payload["flagged"], payload["report"]["run_id"]), (1, "r1"))
        LieReport.model_validate(payload["report"])
        self.assertIs(self.svc.last_report("r1"), rep)
        self.assertIsNone(self.svc.last_report("nope"))
        fresh = self.service(self.store)  # nothing in memory: read back from the store
        self.assertEqual(fresh.last_report("r1").model_dump(), rep.model_dump())
        self.assertEqual(self.src.closed, 2)  # training, then the report

    def test_the_scored_text_is_the_training_layout(self):
        self.train()
        seen = []
        orig = self.src.capture

        async def capture(model_id, messages, layers):
            seen.append(messages)
            return await orig(model_id, messages, layers)
        self.src.capture = capture
        run(self.svc.lie_report("r", "  What is\n the capital? ", self.seats[:1], self.drafts))
        self.assertEqual([m for m in seen], [probe_messages("What is the capital?", self.HONEST),
                                             probe_messages("What is the capital?", self.LIE)])

    def test_no_active_probe_still_gives_a_report_from_behaviour(self):
        rep = run(self.svc.lie_report("r", "task", self.seats, self.drafts))
        self.assertEqual((rep.probe_models, rep.note), ([], NO_PROBE_NOTE))
        self.assertEqual(len(rep.flags), 4)
        self.assertTrue(all(f.probe_score is None and f.behaviour_score is not None for f in rep.flags))
        self.assertTrue(all(f.stated_confidence == 0.9 for f in rep.flags))  # from the draft
        off = self.service(self.store, )
        off.lie_cfg = LieConfig(enabled=False)
        self.train()
        self.assertEqual(run(off.lie_report("r2", "task", self.seats, self.drafts)).probe_models, [])

    def test_lie_report_never_raises(self):
        self.train()

        async def dead(model_id, messages, layers):
            raise ActivationError("actdump died")
        self.src.capture = dead
        rep = run(self.svc.lie_report("r", "task", self.seats, self.drafts))
        self.assertEqual(len(rep.flags), 4)
        self.assertTrue(all(f.probe_score is None for f in rep.flags))
        bad = run(self.svc.lie_report("r3", "task", None, None))  # nonsense in: a report out
        self.assertEqual((bad.run_id, bad.flags), ("r3", []))
        self.assertIn("lie report failed", bad.note)
        self.svc.emit = lambda t, p: 1 / 0
        self.svc.ledger = None
        self.assertEqual(len(run(self.svc.lie_report("r4", "t", self.seats, self.drafts)).flags), 4)
        empty = run(self.svc.lie_report("r5", "t", self.seats, {}))
        self.assertEqual((empty.flags, [s.claims for s in empty.seats]), ([], [0, 0]))

    def test_thresholds_come_from_the_lie_config(self):
        self.train()
        self.svc.lie_cfg = {"flag_below": 0.0, "watch_below": 0.0, "gap_flag": 2.0, "gap_watch": 2.0}
        rep = run(self.svc.lie_report("r", "task", self.seats[:1], self.drafts))
        self.assertEqual({f.level for f in rep.flags}, {"ok"})
        self.svc.lie_cfg = LieConfig(max_claims=1)
        rep = run(self.svc.lie_report("r", "task", self.seats[:1], self.drafts))
        self.assertEqual([f.probe_score is None for f in sorted(rep.flags, key=lambda f: f.claim_id)],
                         [False, True])  # only the first claim was scored

    def test_a_probe_of_an_old_layout_is_not_used(self):
        self.train()
        probe = self.svc.get_probe("m1")
        self.assertEqual(len(self.svc.active_probes("m1")), 1)
        # an old store record (no layout field) and a file of another layout
        old_home = self.home / "old"
        store = Store(":memory:")
        self.addCleanup(store.close)
        store.kv_put("probes", "m1", probe.model_dump())
        store.kv_put("probes", "m2", probe.model_copy(update={"model_id": "m2"}).model_dump())
        ProbeFiles(old_home).save(ProbeCard(model_id="m1", active=True), [probe], None,
                                  LAYOUT_VERSION + 7)
        svc = self.service(store, home=old_home)
        self.assertEqual(svc.active_probes("m2"), [])  # store only, written before 1.5
        self.assertEqual(svc.get_probe("m1").status, "validated")
        self.assertEqual(svc.active_probes("m1"), [])
        self.assertIsNone(svc.platt_for("m1"))
        rep = run(svc.lie_report("r", "task", self.seats[:1], self.drafts))
        self.assertEqual((rep.probe_models, rep.note), ([], NO_PROBE_NOTE))
        sc = run(svc.score_round0("r", "p", self.seats[:1], self.drafts, {}))
        self.assertTrue(all(x.probe is None for x in sc))
        cards = svc.cards()
        self.assertEqual([(c.model_id, c.active, c.reason) for c in cards],
                         [("m1", False, OLD_LAYOUT_REASON), ("m2", False, OLD_LAYOUT_REASON)])

    def test_probe_state(self):
        self.assertEqual(self.svc.probe_state("m1"), "none")
        self.train()
        self.assertEqual(self.svc.probe_state("m1"), "active")
        self.assertEqual(self.svc.probe_state("m2"), "none")
        self.assertTrue(ProbeFiles(self.home).set_active("m1", None))
        self.assertEqual(self.svc.probe_state("m1"), "untrusted")  # trained, switched off
        store = Store(":memory:")
        self.addCleanup(store.close)
        failed = self.svc.get_probe("m1").model_copy(update={"model_id": "m3", "status": "failed"})
        store.kv_put("probes", "m3", failed.model_dump())
        svc = self.service(store, home=self.home / "empty")
        self.assertEqual(svc.probe_state("m3"), "untrusted")  # trained, did not pass
        self.assertEqual(svc.probe_state("m4"), "none")

    def test_switching_the_file_off_switches_live_scoring_off(self):
        self.train()
        files = ProbeFiles(self.home)
        self.assertTrue(files.set_active("m1", None))  # what PATCH /probes/cards/m1 does
        self.assertEqual(self.svc.active_probes("m1"), [])  # the store copy does not bring it back
        self.assertEqual([c.active for c in self.svc.cards()], [False])
        rep = run(self.svc.lie_report("r", "task", self.seats[:1], self.drafts))
        self.assertEqual((rep.probe_models, rep.note), ([], NO_PROBE_NOTE))
        self.assertTrue(files.set_active("m1", 1))
        self.assertEqual(len(self.svc.active_probes("m1")), 1)
        self.assertEqual([c.active for c in self.svc.cards()], [True])
        # a file saved by someone else with the default layout stamp is the same layout
        probe = self.svc.get_probe("m1")
        files.save(ProbeCard(model_id="m1", active=True), [probe])
        self.assertEqual([p.model_dump() for p in self.svc.active_probes("m1")], [probe.model_dump()])

    def test_files_survive_a_database_reset_and_the_store_works_without_files(self):
        card = self.train()
        store = Store(":memory:")
        self.addCleanup(store.close)
        from_files = self.service(store)
        self.assertEqual(len(from_files.active_probes("m1")), 1)
        self.assertIsNotNone(from_files.platt_for("m1"))
        self.assertEqual([c.model_dump() for c in from_files.cards()], [card.model_dump()])
        no_files = ReliabilityService(None, self.store, self.src, ProbeConfig(), lambda t, p: None)
        self.assertIsNone(no_files.files)
        self.assertEqual(len(no_files.active_probes("m1")), 1)
        self.assertEqual(no_files.platt_for("m1"), from_files.platt_for("m1"))
        self.assertEqual([c.model_id for c in no_files.cards()], ["m1"])
        self.assertEqual(self.service(store, home=self.home / "none").cards(), [])

    def test_score_round0_gives_one_probe_score_per_claim_and_the_report(self):
        self.train()
        self.events.clear()
        seen = []
        orig = self.src.capture

        async def capture(model_id, messages, layers):
            seen.append(messages[-1]["content"])
            return await orig(model_id, messages, layers)
        self.src.capture = capture
        msgs = lambda n: [{"role": "system", "content": "s"}, {"role": "user", "content": "the task"},
                          {"role": "assistant", "content": "x"}]
        sc = run(self.svc.score_round0("r9", "p", self.seats, self.drafts, {}, msgs))
        self.assertEqual([(x.seat_no, x.claim_ref) for x in sc],
                         [(1, "answer"), (1, "c1"), (1, "c2"), (2, "answer"), (2, "c1"), (2, "c2")])
        answer, c1, c2 = sc[:3]
        self.assertGreater(c1.probe, 0.5)
        self.assertLess(c2.probe, 0.3)
        self.assertAlmostEqual(answer.probe, (c1.probe + c2.probe) / 2)
        self.assertEqual(c1.probe_auroc, self.svc.active_probes("m1")[0].auroc)
        self.assertTrue(all(x.probe is None and x.probe_auroc is None for x in sc[3:]))
        self.assertTrue(all(t.startswith("Question: the task") and t.endswith(TAIL) for t in seen))
        self.assertEqual([t for t, _ in self.events], ["probe.scores", "probe.scores", "lie.report"])
        rep = self.svc.last_report("r9")
        self.assertEqual(rep.probe_models, ["m1"])
        self.assertEqual({f.claim_id: f.probe_score for f in rep.flags if f.seat_no == 1},
                         {"c1": c1.probe, "c2": c2.probe})
        given = run(self.svc.score_round0("r10", "p", self.seats[:1], self.drafts, {}, None, task="other"))
        self.assertTrue(seen[-1].startswith("Question: other"))
        self.assertIsNotNone(given[1].probe)

    def test_train_for_saves_files_too(self):
        probe = run(self.svc.train_for("m3", tasks(), 5.0))
        self.assertEqual(probe.status, "validated")
        self.assertEqual(ProbeFiles(self.home).layout_version("m3"), LAYOUT_VERSION)
        self.assertEqual([c.model_id for c in self.svc.cards() if c.active], ["m3"])
        self.assertEqual(self.events[-1][1]["card"]["model_id"], "m3")


if __name__ == "__main__":
    unittest.main()
