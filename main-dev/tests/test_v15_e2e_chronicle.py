"""1.5 end to end, mock mode: a standing rule in the task text becomes one ACTIVE Chronicle entry,
a repeat does not duplicate it, and recall without an embedding finds it through BM25."""

import asyncio
import shutil
import tempfile
import unittest
from pathlib import Path

from council.api.run_pipeline import RunDeps, RunPipeline
from council.chronicle import recall
from council.chronicle.collect import collect_candidates
from council.chronicle.corrections import CorrectionBook
from council.chronicle.reflect import USER_SOURCE, Reflector
from council.chronicle.service import Chronicle
from council.core import config as config_mod
from council.core import event_types as ET
from council.core.events import EventBus
from council.core.schemas import Event, MemoryCandidate, RunRequest, RunState, UserInput
from council.core.store import Store
from council.core.workspace import project_id
from council.gateway.gateway import Gateway
from council.gateway.mock import MockResponder
from council.host.drivers import MockDriver
from council.host.host import Host
from council.host.ram import RamBudget
from council.probe.activations import MockActivationSource
from council.probe.ledger import ClaimLedger
from council.probe.service import ReliabilityService

REPO = Path(__file__).resolve().parents[1]
TIMEOUT = 120.0
SEATS = ["gpt-oss-20b", "qwen38-27b-q4", "gemma4-26b-a4b", "ministral-mid", "phi-next-14b"]
RULE = "From now on, always use tabs for indentation in this project."
TASK = RULE + " Which rate limiter should a small API use: a token bucket or a sliding window? Say why."


class FakeControl:
    def __init__(self) -> None:
        self.states: list[RunState] = []

    async def set_state(self, state, reason=""):
        self.states.append(RunState(state))

    async def wait_delegate(self):
        return None

    async def ask_user(self, question):
        choice = question.options[0] if question.options else "go"
        return UserInput(request_id=question.request_id or "", choice=choice)

    def cancelled(self) -> bool:
        return False


class Rig:
    def __init__(self, root: Path) -> None:
        self.home = root / "home"
        self.home.mkdir(parents=True, exist_ok=True)
        self.workspace = root / "project"
        self.workspace.mkdir(exist_ok=True)
        cfg = config_mod.load_config(REPO / "config" / "council.toml")
        cfg.gateway.mock = True
        cfg.inspector.allowed_executables = ["python", "python3"]
        self.config = cfg
        self.registry = config_mod.load_registry(REPO / "config" / "models.json")
        self.store = Store(":memory:")
        self.bus = EventBus(self.store)
        foot = {}
        for m in self.registry:
            if m.measured.ram_gb_live is not None:
                foot[(m.id, "live")] = float(m.measured.ram_gb_live)
                foot[(m.id, "batch")] = float(m.measured.ram_gb_batch or m.measured.ram_gb_live)
        self.host = Host(MockDriver(), RamBudget(lambda: 400.0, 12.0, set(), foot), self.registry, self.bus)
        self.gateway = Gateway(cfg, self.registry, self.store, self.bus,
                               responder=MockResponder(seed=0, tribunal_concede=True),
                               endpoint_for=self.host.endpoint)
        self.deps = RunDeps(
            config=cfg, store=self.store, bus=self.bus, gateway=self.gateway, host=self.host,
            registry=self.registry, chronicle=Chronicle(self.store, self.gateway.embed, cfg.chronicle),
            corrections=CorrectionBook(self.store, self.home),
            reliability=ReliabilityService(
                ClaimLedger(self.store, lambda: 1000.0), self.store, MockActivationSource(), cfg.probe,
                lambda t, p: None),
            home=self.home, now=lambda: 1000.0,
            lens_texts=config_mod.load_lenses(REPO / "config" / "lenses.json"))
        self.pipeline = RunPipeline(self.deps)
        self._n = 0

    async def run(self, task: str, workspace: Path | None = None) -> tuple[str, FakeControl]:
        self._n += 1
        run_id = f"run_{self._n:03d}"
        ws = str(workspace or self.workspace)
        request = RunRequest(task=task, workspace=ws, lineup_override=list(SEATS), deliverable="answer")
        self.store.create_run(run_id, task, ws, request.mode, RunState.INTAKE)
        ctl = FakeControl()
        await asyncio.wait_for(self.pipeline.run(run_id, request, ctl), TIMEOUT)
        return run_id, ctl

    def events(self, run_id: str, type_: str | None = None) -> list:
        return [e for e in self.store.events_for_run(run_id) if type_ is None or e.type == type_]

    def rule_entries(self) -> list:
        return [e for e in self.store.chronicle_list() if "tabs for indentation" in e.statement]

    def close(self) -> None:
        self.store.close()


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="council_v15_chr_")
        self.addCleanup(shutil.rmtree, self._tmp, True)
        self.rig = Rig(Path(self._tmp))
        self.addCleanup(self.rig.close)


async def _no_embedding(texts):
    return [[] for _ in texts]


class StandingRuleMemory(Base):
    async def test_run_commits_one_active_entry(self):
        rig = self.rig
        run_id, ctl = await rig.run(TASK)
        self.assertEqual(ctl.states[-2:], [RunState.REFLECTING, RunState.DONE])
        entries = rig.rule_entries()
        self.assertEqual(len(entries), 1, [e.statement for e in rig.store.chronicle_list()])
        e = entries[0]
        self.assertEqual(e.status, "active")
        self.assertEqual(e.statement, RULE)
        self.assertEqual(e.kind, "preference")
        self.assertEqual(e.scope, f"project:{project_id(rig.workspace)}")
        self.assertGreaterEqual(e.confidence, 0.9)
        self.assertEqual(e.support_count, 1)
        self.assertTrue(e.evidence)
        # the user said it: no panel vote for this candidate
        cands = [x.payload["candidate"] for x in rig.events(run_id, ET.MEMORY_CANDIDATE)
                 if x.payload["candidate"]["text"] == RULE]
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["source"], USER_SOURCE)
        verdict_ids = {x.payload["candidate_id"] for x in rig.events(run_id, ET.MEMORY_VERDICT)}
        self.assertNotIn(cands[0]["id"], verdict_ids)
        # one committed event for it, action adopt, carrying the stored entry
        committed = [x.payload for x in rig.events(run_id, ET.MEMORY_COMMITTED)
                     if x.payload["candidate_id"] == cands[0]["id"]]
        self.assertEqual(len(committed), 1)
        self.assertEqual(committed[0]["action"], "adopt")
        self.assertEqual(committed[0]["entry"]["id"], e.id)
        self.assertEqual(committed[0]["entry"]["status"], "active")

    async def test_second_identical_run_does_not_duplicate(self):
        rig = self.rig
        await rig.run(TASK)
        first = rig.rule_entries()
        self.assertEqual(len(first), 1)
        run2, _ = await rig.run(TASK)
        after = rig.rule_entries()
        self.assertEqual(len(after), 1, [e.statement for e in rig.store.chronicle_list()])
        self.assertEqual(after[0].id, first[0].id)
        self.assertEqual(after[0].status, "active")
        # an independent run saying it again is support, not a new row
        self.assertEqual(after[0].support_count, 2)
        self.assertEqual(len({ev.run_id for ev in after[0].evidence}), 2)
        merges = [x.payload for x in rig.events(run2, ET.MEMORY_COMMITTED)
                  if x.payload["action"].startswith("merge:")]
        self.assertTrue(any(m["merged_into_id"] == first[0].id for m in merges), merges)
        # run 2 already recalled the rule before deliberating
        recalled = rig.events(run2, ET.RECALL_READY)[0].payload
        self.assertIn("tabs for indentation", recalled["record_block"])

    async def test_same_run_saying_it_twice_adds_nothing(self):
        rig = self.rig
        reflector = Reflector(rig.gateway, rig.store, lambda t, p: None, rig.gateway.embed,
                              rig.config.chronicle, lambda: 1000.0)
        project = project_id(rig.workspace)
        events = [Event(type=ET.RUN_COMPLETED, seq=1, run_id="r1", payload={})]
        cands = [c for c in collect_candidates(events, TASK) if c.source == USER_SOURCE]
        self.assertEqual(len(cands), 1, cands)
        self.assertEqual(cands[0].text, RULE)
        first = await reflector.reflect("r1", cands, [], project, [])
        self.assertEqual(len(first), 1)
        again = await reflector.reflect("r1", cands, [], project, [])
        self.assertEqual(again, [])
        self.assertEqual(len(rig.rule_entries()), 1)
        self.assertEqual(rig.rule_entries()[0].support_count, 1)


class BM25Recall(Base):
    async def _stored_rig(self) -> Rig:
        await self.rig.run(TASK)
        self.assertEqual(len(self.rig.rule_entries()), 1)
        return self.rig

    async def test_recall_without_embedding_returns_it_via_bm25(self):
        rig = await self._stored_rig()
        chron = Chronicle(rig.store, _no_embedding, rig.config.chronicle)  # embedder gives nothing
        block, top = await chron.record_for("indentation tabs", rig.workspace, [])
        self.assertEqual([e.statement for e in top][:1], [RULE], block)
        self.assertEqual(top[0].status, "active")
        self.assertIn(RULE, block)
        self.assertTrue(block.startswith("[ACTIVE"))

    async def test_recall_with_failing_embedder_falls_back_to_bm25(self):
        rig = await self._stored_rig()

        async def broken(texts):
            raise RuntimeError("embedding model is down")

        chron = Chronicle(rig.store, broken, rig.config.chronicle)
        _, top = await chron.record_for("indentation tabs", rig.workspace, [])
        self.assertEqual([e.statement for e in top][:1], [RULE])

    async def test_bm25_recall_is_scoped_and_needs_a_shared_word(self):
        rig = await self._stored_rig()
        chron = Chronicle(rig.store, _no_embedding, rig.config.chronicle)
        # no shared word: nothing back, never the whole store
        block, top = await chron.record_for("zebra giraffe habitat", rig.workspace, [])
        self.assertEqual(top, [])
        self.assertEqual(block, "(no prior record)")
        # another project does not see this project's rule
        other = Path(self._tmp) / "other_project"
        other.mkdir()
        _, top = await chron.record_for("indentation tabs", other, [])
        self.assertEqual([e for e in top if e.statement == RULE], [])
        # the pure ranker agrees
        mine = recall.rank_text(rig.store.chronicle_list(), "indentation tabs",
                                project_id(rig.workspace), [], k=8)
        self.assertIn(RULE, [e.statement for e in mine])


if __name__ == "__main__":
    unittest.main()
