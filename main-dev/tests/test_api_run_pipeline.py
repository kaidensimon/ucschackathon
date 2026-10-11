import asyncio
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from council.api.run_pipeline import RunDeps, RunPipeline, RunResult
from council.chamber.deliberation import SCORES_HEADING
from council.chronicle.collect import collect_candidates
from council.chronicle.corrections import CorrectionBook
from council.chronicle.service import Chronicle
from council.core import config as config_mod
from council.core import event_types as ET
from council.core.events import EventBus
from council.core.schemas import (
    CallResult,
    Event,
    MicroTask,
    Plan,
    RunRequest,
    RunState,
    UserInput,
)
from council.core.store import Store
from council.core.workspace import project_id
from council.gateway.gateway import Gateway
from council.gateway.mock import MockResponder
from council.host.drivers import MockDriver
from council.host.host import Host, HostError
from council.host.ram import RamBudget
from council.probe.activations import MockActivationSource
from council.probe.ledger import ClaimLedger
from council.probe.service import ReliabilityService

REPO = Path(__file__).resolve().parents[1]
TIMEOUT = 120.0
SEATS = ["gpt-oss-20b", "qwen38-27b-q4", "gemma4-26b-a4b", "ministral-mid", "phi-next-14b"]
ANSWER_TASK = "Which rate limiter should a small API use: a token bucket or a sliding window? Say why."
BUILD_TASK = "Build a small Python package 'ratelimiter' with a token bucket and a sliding window."
NOTES_HEADING = "Corrections from earlier sessions in this project"


class Recorder:
    """MockResponder that keeps every CallSpec it was asked."""

    def __init__(self, **kw) -> None:
        self.inner = MockResponder(**kw)
        self.specs: list = []

    async def respond(self, spec, on_delta=None):
        self.specs.append(spec)
        return await self.inner.respond(spec, on_delta)


class FakeControl:
    def __init__(self, answer: str = "", cancel_at: RunState | None = None) -> None:
        self.states: list[RunState] = []
        self.questions: list = []
        self.delegate_waits = 0
        self.answer = answer
        self.cancel_at = cancel_at
        self.on_wait = None

    async def set_state(self, state, reason=""):
        self.states.append(RunState(state))

    async def wait_delegate(self):
        self.delegate_waits += 1
        if self.on_wait is not None:
            self.on_wait()

    async def ask_user(self, question):
        self.questions.append(question)
        choice = self.answer or (question.options[0] if question.options else "go")
        return UserInput(request_id=question.request_id or "", choice=choice)

    def cancelled(self) -> bool:
        return self.cancel_at is not None and self.cancel_at in self.states


class Rig:
    def __init__(self, root: Path, **responder_kw) -> None:
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
        self.responder = Recorder(seed=0, **responder_kw)
        self.gateway = Gateway(cfg, self.registry, self.store, self.bus, responder=self.responder,
                               endpoint_for=self.host.endpoint)
        self.corrections = CorrectionBook(self.store, self.home)
        self.reliability = ReliabilityService(
            ClaimLedger(self.store, lambda: 1000.0), self.store, MockActivationSource(), cfg.probe,
            lambda t, p: None)
        self.deps = RunDeps(
            config=cfg, store=self.store, bus=self.bus, gateway=self.gateway, host=self.host,
            registry=self.registry, chronicle=Chronicle(self.store, self.gateway.embed, cfg.chronicle),
            corrections=self.corrections,
            reliability=self.reliability, home=self.home, now=lambda: 1000.0,
            lens_texts=config_mod.load_lenses(REPO / "config" / "lenses.json"))
        self.pipeline = RunPipeline(self.deps)
        self._n = 0

    async def run(self, task: str, ctl: FakeControl | None = None, **req) -> tuple[str, RunResult, FakeControl]:
        self._n += 1
        run_id = f"run_{self._n:03d}"
        request = RunRequest(task=task, workspace=str(self.workspace), lineup_override=list(SEATS), **req)
        self.store.create_run(run_id, task, request.workspace, request.mode, RunState.INTAKE)
        ctl = ctl or FakeControl()
        result = await asyncio.wait_for(self.pipeline.run(run_id, request, ctl), TIMEOUT)
        return run_id, result, ctl

    def events(self, run_id: str, type_: str | None = None) -> list:
        return [e for e in self.store.events_for_run(run_id) if type_ is None or e.type == type_]

    def close(self) -> None:
        self.store.close()


class Base(unittest.IsolatedAsyncioTestCase):
    responder_kw: dict = {"tribunal_concede": True}

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="council_rp_")
        self.addCleanup(shutil.rmtree, self._tmp, True)
        self.rig = Rig(Path(self._tmp), **self.responder_kw)
        self.addCleanup(self.rig.close)


class AnswerRun(Base):
    async def test_split_council_gives_tribunal_outcome_and_correction(self):
        rig = self.rig
        run_id, result, ctl = await rig.run(ANSWER_TASK, deliverable="answer")

        self.assertEqual(ctl.states, [
            RunState.PROFILING, RunState.CONVENING, RunState.DELIBERATING, RunState.DECIDED,
            RunState.EXAMINING, RunState.REFLECTING, RunState.DONE])
        types = [e.type for e in rig.events(run_id)]
        for t in (ET.BRIEF_READY, ET.PROFILE_READY, ET.RECALL_READY, ET.ROUTER_LINEUP_SELECTED,
                  ET.SEAT_ASSIGNED, ET.DECISION_FINAL, ET.PROBE_SCORES, ET.TRIBUNAL_STARTED,
                  ET.TRIBUNAL_QUESTION, ET.TRIBUNAL_ANSWER, ET.TRIBUNAL_VERDICT, ET.TRIBUNAL_OUTCOME,
                  ET.CORRECTION_RECORDED, ET.RUN_COMPLETED):
            self.assertIn(t, types, t)
        self.assertLess(types.index(ET.TRIBUNAL_STARTED), types.index(ET.TRIBUNAL_OUTCOME))
        self.assertEqual(types[-1], ET.RUN_COMPLETED)

        self.assertIsNotNone(result.tribunal)
        self.assertEqual(result.tribunal.outcome, "conceded")
        c = result.correction
        self.assertIsNotNone(c)
        self.assertEqual(result.tribunal.correction_id, c.id)
        self.assertEqual(c.verified_by, "conceded")
        self.assertEqual(c.project, project_id(rig.workspace))
        self.assertEqual(c.model_id, result.tribunal.outlier_model_id)
        self.assertIn(c.model_id, SEATS)
        self.assertTrue(c.lesson)

        stored = rig.store.corrections_list(c.project, c.model_id)
        self.assertEqual([x.id for x in stored], [c.id])
        self.assertEqual(rig.corrections.dataset_size(c.project, c.model_id), 2)
        rec = rig.events(run_id, ET.CORRECTION_RECORDED)[0].payload
        self.assertEqual(rec["dataset_size"], 2)
        self.assertEqual(rec["model_id"], c.model_id)
        # the tribunal labelled the outlier's claims in the ledger
        labelled = [r for r in rig.store.claims_list(model_id=c.model_id, labelled_only=True)
                    if r.run_id == run_id]
        self.assertTrue(labelled)
        self.assertTrue(all(r.label == "false" and r.labelled_by == "tribunal" for r in labelled))
        # every seat was released
        self.assertFalse(rig.host._seats.get(run_id))
        self.assertEqual(rig.store.get_json("decisions", run_id)["outcome"], result.decision.outcome)

    async def test_scores_reach_round_one_and_brief_is_cached(self):
        rig = self.rig
        (rig.workspace / "main.py").write_text("print('hi')\n", encoding="utf-8")
        run_id, _, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        r1 = [s for s in rig.responder.specs if s.call_id.startswith(f"{run_id}:r1:")]
        self.assertTrue(r1)
        for spec in r1:
            self.assertIn(SCORES_HEADING, " ".join(str(m["content"]) for m in spec.messages))
        scores = rig.events(run_id, ET.PROBE_SCORES)
        self.assertEqual(sorted(e.payload["seat_no"] for e in scores), [0, 1, 2, 3, 4])
        brief = rig.events(run_id, ET.BRIEF_READY)[0].payload
        self.assertFalse(brief["cached"])
        self.assertEqual(brief["file_count"], 1)
        self.assertEqual(brief["languages"], ["Python"])

        second, _, _ = await rig.run(ANSWER_TASK, deliverable="answer", mode="quick")
        self.assertTrue(rig.events(second, ET.BRIEF_READY)[0].payload["cached"])
        # quick mode: no tribunal, but the ledger still has the drafts
        self.assertNotIn(ET.TRIBUNAL_STARTED, [e.type for e in rig.events(second)])
        self.assertTrue([r for r in rig.store.claims_list() if r.run_id == second])

    async def test_second_run_shows_the_correction_to_the_outlier_model(self):
        rig = self.rig
        first, result, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        c = result.correction
        self.assertIsNotNone(c)
        before = [s for s in rig.responder.specs if s.run_id == first and s.purpose.startswith("seat")]
        self.assertTrue(before)
        self.assertFalse(any(NOTES_HEADING in str(s.messages[0]["content"]) for s in before))

        second, _, _ = await rig.run(ANSWER_TASK, deliverable="answer")
        r0 = [s for s in rig.responder.specs if s.call_id.startswith(f"{second}:r0:")]
        self.assertEqual(len(r0), len(SEATS))
        for spec in r0:
            system = str(spec.messages[0]["content"])
            if spec.model_id == c.model_id:
                self.assertIn(NOTES_HEADING, system)
                self.assertIn(c.lesson, system)
            else:
                self.assertNotIn(NOTES_HEADING, system)

    async def test_cancel_between_steps_releases_the_host(self):
        rig = self.rig
        ctl = FakeControl(cancel_at=RunState.CONVENING)
        with self.assertRaises(asyncio.CancelledError):
            await rig.run(ANSWER_TASK, ctl, deliverable="answer")
        self.assertEqual(ctl.states, [RunState.PROFILING, RunState.CONVENING])
        self.assertFalse(rig.host._seats.get("run_001"))
        self.assertNotIn(ET.RUN_COMPLETED, [e.type for e in rig.events("run_001")])

    async def test_error_is_raised_after_release(self):
        rig = self.rig
        rig.host.driver.fail.update(m.id for m in rig.registry)  # nothing loads: no quorum
        with self.assertRaises(Exception):
            await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertFalse(rig.host._seats.get("run_001"))


class Vindicated(Base):
    responder_kw: dict = {"tribunal_concede": False}

    async def test_no_tribunal_when_disabled(self):
        rig = self.rig
        rig.config.tribunal.enabled = False
        run_id, result, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertIsNone(result.tribunal)
        self.assertNotIn(RunState.EXAMINING, ctl.states)
        self.assertEqual(ctl.states[-1], RunState.DONE)

    async def test_outcome_without_concession_follows_the_judges(self):
        rig = self.rig
        run_id, result, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        out = result.tribunal
        self.assertIsNotNone(out)
        self.assertIn(out.outcome, ("failed", "vindicated"))
        if out.outcome == "vindicated":
            self.assertTrue(result.decision.contested_after_review)
            self.assertIsNone(result.correction)
            self.assertEqual(result.decision.minority_report[0].seats, [out.outlier_seat])
        else:
            self.assertFalse(result.decision.contested_after_review)


class BuildRun(Base):
    async def test_auto_delegate_builds_the_ratelimiter(self):
        rig = self.rig
        run_id, result, ctl = await rig.run(BUILD_TASK, deliverable="build",
                                            options={"auto_delegate": True})
        self.assertEqual(ctl.delegate_waits, 0)
        self.assertEqual(ctl.states[-1], RunState.DONE)
        order = [s for i, s in enumerate(ctl.states) if i == 0 or ctl.states[i - 1] != s]
        for a, b in [(RunState.DECIDED, RunState.PLANNING),
                     (RunState.PLANNING, RunState.AWAITING_DELEGATION),
                     (RunState.AWAITING_DELEGATION, RunState.EXECUTING),
                     (RunState.EXECUTING, RunState.REVIEWING),
                     (RunState.REVIEWING, RunState.INTEGRATING),
                     (RunState.INTEGRATING, RunState.REFLECTING),
                     (RunState.REFLECTING, RunState.DONE)]:
            self.assertIn(a, order)
            self.assertIn(b, order)
            self.assertLess(order.index(a), len(order) - 1 - order[::-1].index(b), (a, b))
        self.assertTrue(result.accepted)
        self.assertIsNotNone(result.plan)
        self.assertLessEqual(ctl.states.count(RunState.REVIEWING), rig.config.review.max_cycles + 1)

        ws = rig.workspace
        for rel in ("ratelimiter/__init__.py", "ratelimiter/token_bucket.py",
                    "ratelimiter/sliding_window.py", "tests/test_token_bucket.py", "README.md"):
            self.assertTrue((ws / rel).is_file(), rel)
            self.assertIn(rel, result.files_written)
        self.assertIn("min(self.capacity", (ws / "ratelimiter" / "token_bucket.py").read_text("utf-8"))
        done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                              cwd=str(ws), capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])

        types = [e.type for e in rig.events(run_id)]
        for t in (ET.PLAN_READY, ET.DELEGATION_STARTED, ET.TASK_PASSED, ET.REVIEW_STARTED,
                  ET.REVIEW_BALLOT, ET.REVIEW_VERDICT, ET.INTEGRATION_RESULT, ET.MEMORY_CANDIDATE,
                  ET.RUN_COMPLETED):
            self.assertIn(t, types, t)
        verdicts = [e.payload["verdict"] for e in rig.events(run_id, ET.REVIEW_VERDICT)]
        self.assertEqual(verdicts[-1], "accept")
        completed = rig.events(run_id, ET.RUN_COMPLETED)[0].payload
        self.assertIn("ratelimiter/token_bucket.py", completed["files_written"])
        self.assertIsNotNone(rig.store.get_json("plans", run_id))
        self.assertFalse(rig.host._seats.get(run_id))

    async def test_waits_for_delegate_and_rereads_an_edited_plan(self):
        rig = self.rig
        ctl = FakeControl()

        def edit() -> None:
            plan = Plan.model_validate(rig.store.get_json("plans", "run_001"))
            plan.tasks = [MicroTask.model_validate(
                t.model_dump() | {"title": t.title + " (edited)"}) for t in plan.tasks]
            rig.store.put_json("plans", "run_001", plan)

        ctl.on_wait = edit
        run_id, result, _ = await rig.run(BUILD_TASK, ctl, deliverable="build")
        self.assertEqual(ctl.delegate_waits, 1)
        self.assertTrue(all(t.title.endswith("(edited)") for t in result.plan.tasks))
        ready = rig.events(run_id, ET.PLAN_READY)
        self.assertTrue(ready[-1].payload["edited_by_user"])
        self.assertTrue(result.accepted)


class EvidenceSupport(unittest.TestCase):
    """27.5: 'verified by evidence' needs a check that positively supports the chosen option."""

    def test_only_a_passing_python_check_on_the_chosen_side_counts(self):
        from council.api.run_pipeline import evidence_supports
        from council.core.schemas import EvidenceResult as R
        yes = R(kind="python", id="k1", ok=True, exit_code=0, supports="o1")
        self.assertTrue(evidence_supports([yes], "o1"))
        for no in (
            R(kind="python", id="k1", ok=True, exit_code=0),                    # side not known
            R(kind="python", id="k1", ok=True, exit_code=0, supports="o2"),     # supports the outlier
            R(kind="python", id="k1", ok=True, exit_code=1, supports="o1"),     # the check refuted it
            R(kind="python", id="k1", ok=False, exit_code=0, supports="o1"),    # did not finish
            R(kind="python", id="k1", ok=True, supports="o1"),                  # no exit code
            R(kind="grep", id="k1", ok=True, supports="o1"),                    # a grep proves nothing
        ):
            self.assertFalse(evidence_supports([no], "o1"), no)
        self.assertFalse(evidence_supports([yes], None))
        self.assertFalse(evidence_supports([], "o1"))


class ProbeFraming(Base):
    async def test_live_probe_text_is_framed_like_the_training_rows(self):
        rig = self.rig
        seen: list[list[dict]] = []

        class Source(MockActivationSource):
            async def capture(self, model_id, messages, layers):
                seen.append(list(messages))
                return await super().capture(model_id, messages, layers)

        rig.reliability.source = Source()
        from council.bench import sample_tasks
        from council.core.schemas import BenchTask
        tasks = [BenchTask.model_validate(r) for r in sample_tasks.generate()]
        probe = await rig.reliability.train_for(SEATS[0], tasks, 1.0)
        self.assertEqual(probe.status, "validated")
        seen.clear()
        await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertTrue(seen)
        from council.probe.layout import TAIL, probe_text
        head = probe_text(ANSWER_TASK, "x").split("x")[0]  # "Question: <task>\nStatement: "
        for messages in seen:
            # 1.5: one user message in the probe layout (probe/layout.py), as in training:
            # the bare task as the question, one claim of the draft, the open sentence.
            self.assertEqual([m["role"] for m in messages], ["user"])
            text = messages[0]["content"]
            self.assertTrue(text.startswith(head), text)
            self.assertTrue(text.endswith(TAIL))


def picker_eligible(rig):
    from council.router import picker
    from council.router.profiler import heuristic_profile
    return picker.eligible_models(heuristic_profile(ANSWER_TASK), rig.registry)


class SeatLoadFailure(Base):
    """A seat model the server cannot load is replaced; the run only fails below the quorum."""

    async def test_failed_seat_is_replaced_and_never_picked_again(self):
        rig = self.rig
        bad = SEATS[1]
        rig.host.driver.fail.add(bad)
        run_id, result, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-1], RunState.DONE)
        self.assertTrue(result.final_text)

        failed = [e.payload for e in rig.events(run_id, ET.MODEL_FAILED) if e.payload.get("replaced_by")]
        self.assertEqual(len(failed), 1)
        self.assertEqual((failed[0]["model_id"], failed[0]["stage"]), (bad, "load"))
        sub = failed[0]["replaced_by"]
        self.assertNotIn(sub, SEATS)

        stored = rig.store.get_json("lineups", run_id)
        ids = [s["model_id"] for s in stored["seats"]]
        self.assertEqual(ids, [SEATS[0], sub] + SEATS[2:])
        self.assertEqual(stored["k"], len(SEATS))
        self.assertNotIn(sub, stored["alternates"])
        selected = rig.events(run_id, ET.ROUTER_LINEUP_SELECTED)
        self.assertEqual(len(selected), 2)  # the pick, then the final lineup
        self.assertEqual([s["model_id"] for s in selected[0].payload["lineup"]["seats"]], SEATS)
        self.assertEqual([s["model_id"] for s in selected[-1].payload["lineup"]["seats"]], ids)

        seats = {e.payload["seat_no"]: e.payload for e in rig.events(run_id, ET.SEAT_ASSIGNED)}
        self.assertEqual(sorted(seats), [0, 1, 2, 3, 4])
        self.assertEqual((seats[1]["model_id"], seats[1]["replaces_model_id"]), (sub, bad))
        self.assertTrue(seats[1]["display"])
        self.assertIsNone(seats[0]["replaces_model_id"])
        types = [e.type for e in rig.events(run_id)]
        self.assertLess(types.index(ET.SEAT_ASSIGNED), types.index(ET.ROUND_STARTED))
        r0 = {s.model_id for s in rig.responder.specs if s.call_id.startswith(f"{run_id}:r0:")}
        self.assertEqual(r0, set(ids))

        # out for the process: on the deps, and in the registry GET /models dumps
        self.assertIn(bad, rig.deps.failed_models)
        entry = next(m for m in rig.registry if m.id == bad)
        self.assertEqual(entry.model_dump(mode="json")["status"], "failed")
        self.assertNotIn(bad, [m.id for m in picker_eligible(rig)])

        # second run, lineup named by the user again: the model is not even tried
        second, _, _ = await rig.run(ANSWER_TASK, deliverable="answer", mode="quick")
        loading = [e.payload["model_id"] for e in rig.events(second, ET.MODEL_LOADING)]
        self.assertNotIn(bad, loading)
        self.assertNotIn(bad, [s["model_id"] for s in rig.store.get_json("lineups", second)["seats"]])
        # routed run: the picker leaves it out
        rig._n += 1
        third = f"run_{rig._n:03d}"
        rig.store.create_run(third, ANSWER_TASK, None, "quick", RunState.INTAKE)
        await asyncio.wait_for(rig.pipeline.run(
            third, RunRequest(task=ANSWER_TASK, mode="quick", deliverable="answer"), FakeControl()), TIMEOUT)
        self.assertNotIn(bad, [s["model_id"] for s in rig.store.get_json("lineups", third)["seats"]])
        scored = rig.events(third, ET.ROUTER_CANDIDATES_SCORED)[0].payload["candidates"]
        row = next(c for c in scored if c["model_id"] == bad)
        self.assertEqual((row["eligible"], row["reason"]), (False, "failed to load"))

    async def test_seat_without_substitute_is_dropped_above_quorum(self):
        rig = self.rig
        keep = set(SEATS[:2] + SEATS[3:]) | {m.id for m in rig.registry if "seat" not in m.roles}
        rig.host.driver.fail.update(m.id for m in rig.registry if m.id not in keep)
        run_id, result, ctl = await rig.run(ANSWER_TASK, deliverable="answer", mode="quick")
        self.assertEqual(ctl.states[-1], RunState.DONE)
        stored = rig.store.get_json("lineups", run_id)
        self.assertEqual([s["model_id"] for s in stored["seats"]], SEATS[:2] + SEATS[3:])
        self.assertEqual([s["seat_no"] for s in stored["seats"]], [0, 1, 2, 3])
        self.assertEqual(stored["k"], 4)
        self.assertEqual(sum(1 for s in stored["seats"] if s["is_chair"]), 1)
        self.assertIn(stored["chair_model_id"], [s["model_id"] for s in stored["seats"]])
        self.assertEqual(len(rig.events(run_id, ET.SEAT_ASSIGNED)), 4)
        last = [e.payload for e in rig.events(run_id, ET.MODEL_FAILED) if e.payload.get("stage") == "load"]
        self.assertIsNone(last[-1]["replaced_by"])
        self.assertIn(SEATS[2], rig.deps.failed_models)

    async def test_run_fails_below_the_quorum_and_releases(self):
        rig = self.rig
        rig.host.driver.fail.update(m.id for m in rig.registry if m.id not in SEATS[:2])
        with self.assertRaises(HostError) as caught:
            await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertIn("quorum 3", str(caught.exception))
        self.assertFalse(rig.host._seats.get("run_001"))
        self.assertNotIn(ET.RUN_COMPLETED, [e.type for e in rig.events("run_001")])

    async def test_no_room_substitutes_but_does_not_mark_the_model(self):
        rig = self.rig
        real = rig.host._admit

        async def admit(mid, profile, run_id):
            if mid == SEATS[0]:
                raise HostError(f"cannot admit {mid}: not enough memory")
            return await real(mid, profile, run_id)

        rig.host._admit = admit
        run_id, _, ctl = await rig.run(ANSWER_TASK, deliverable="answer", mode="quick")
        self.assertEqual(ctl.states[-1], RunState.DONE)
        self.assertNotIn(SEATS[0], [s["model_id"] for s in rig.store.get_json("lineups", run_id)["seats"]])
        self.assertEqual(rig.deps.failed_models, {})
        self.assertEqual(next(m for m in rig.registry if m.id == SEATS[0]).status, "active")


class AnswerReflection(Base):
    """Answer runs reach the Chronicle: REFLECTING runs after the decision (and the tribunal)."""

    async def test_answer_run_reflects_and_sees_the_tribunal_lesson(self):
        rig = self.rig
        run_id, result, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-2:], [RunState.REFLECTING, RunState.DONE])
        self.assertIsNone(result.accepted)
        self.assertIsNone(result.plan)
        types = [e.type for e in rig.events(run_id)]
        self.assertEqual(types[-1], ET.RUN_COMPLETED)
        self.assertEqual(types.count(ET.RUN_COMPLETED), 1)
        cands = [e.payload["candidate"] for e in rig.events(run_id, ET.MEMORY_CANDIDATE)]
        self.assertTrue(cands)
        self.assertLess(types.index(ET.TRIBUNAL_OUTCOME), types.index(ET.MEMORY_CANDIDATE))
        self.assertLess(types.index(ET.MEMORY_CANDIDATE), types.index(ET.RUN_COMPLETED))
        lesson = " ".join(result.correction.lesson.split())
        mine = [c for c in cands if c["text"] == lesson]
        self.assertEqual(len(mine), 1)  # outcome and correction carry the same lesson: one candidate
        self.assertEqual(mine[0]["source"], "inferred")
        seqs = {e.seq for e in rig.events(run_id) if e.type in (ET.TRIBUNAL_OUTCOME, ET.CORRECTION_RECORDED)}
        self.assertTrue({ev["event_seq"] for ev in mine[0]["evidence"]} <= seqs)
        self.assertIn(ET.MEMORY_VERDICT, types)
        # the judges call at batch priority
        judged = [s for s in rig.responder.specs if s.run_id == run_id and s.priority == "batch"]
        self.assertTrue(judged)
        # nothing synthetic was stored: every stored ballot.cast is a seat's own
        self.assertTrue(all(e.payload.get("seat_no") is not None
                            for e in rig.events(run_id, ET.BALLOT_CAST)))
        self.assertFalse(rig.host._seats.get(run_id))

    async def test_reflect_false_and_quick_mode_skip_it(self):
        rig = self.rig
        first, _, ctl = await rig.run(ANSWER_TASK, deliverable="answer", options={"reflect": False})
        self.assertNotIn(RunState.REFLECTING, ctl.states)
        self.assertNotIn(ET.MEMORY_CANDIDATE, [e.type for e in rig.events(first)])
        second, _, ctl = await rig.run(ANSWER_TASK, deliverable="answer", mode="quick")
        self.assertNotIn(RunState.REFLECTING, ctl.states)
        self.assertEqual(ctl.states[-1], RunState.DONE)

    async def test_reflection_error_does_not_fail_the_answer(self):
        rig = self.rig

        def broken(emit):
            raise RuntimeError("reflector is down")

        rig.deps.reflector_factory = broken
        run_id, result, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        self.assertEqual(ctl.states[-2:], [RunState.REFLECTING, RunState.DONE])
        self.assertTrue(result.final_text)
        self.assertEqual(rig.events(run_id)[-1].type, ET.RUN_COMPLETED)

    async def test_lesson_events_are_what_collect_reads(self):
        outcome = Event(type=ET.TRIBUNAL_OUTCOME, seq=7, run_id="r", payload={
            "outcome": {"outcome": "failed", "lesson": "Check the unit before the number."}})
        held = Event(type=ET.TRIBUNAL_OUTCOME, seq=8, run_id="r", payload={
            "outcome": {"outcome": "vindicated", "lesson": "not a lesson"}})
        fix = Event(type=ET.CORRECTION_RECORDED, seq=9, run_id="r", payload={
            "correction": {"lesson": "Round only at the last step."}})
        extra = RunPipeline._lesson_events([outcome, held, fix])
        self.assertEqual([(e.type, e.seq) for e in extra], [(ET.BALLOT_CAST, 7), (ET.BALLOT_CAST, 9)])
        got = collect_candidates([outcome, held, fix] + extra, "task")
        self.assertEqual({c.text for c in got},
                         {"Check the unit before the number.", "Round only at the last step."})


class InvalidRoundZeroSeat(Base):
    """A seat that answers round 0 off task (no valid draft) must not hold the tribunal up."""

    async def test_invalid_round_zero_seat_does_not_block_the_tribunal(self):
        rig = self.rig
        inner = rig.responder.inner
        bad_seat = 2
        junk: list = []

        class OffTask:
            async def respond(self, spec, on_delta=None):
                meta = spec.meta or {}
                if ":r0:" in spec.call_id and meta.get("seat_no") == bad_seat:
                    junk.append(spec.call_id)
                    return CallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id,
                                      content="I would rather talk about turtles.",
                                      error="invalid_output")
                return await inner.respond(spec, on_delta)

        rig.responder.inner = OffTask()
        t0 = time.monotonic()
        run_id, result, ctl = await rig.run(ANSWER_TASK, deliverable="answer")
        took = time.monotonic() - t0
        self.assertTrue(junk)
        self.assertEqual(ctl.states[-1], RunState.DONE)
        self.assertIn(RunState.EXAMINING, ctl.states)
        self.assertLess(took, 30.0)  # far below the mode deadline: nobody waited for the seat
        out = result.tribunal
        self.assertIsNotNone(out)
        self.assertNotEqual(out.outcome, "skipped")
        started = rig.events(run_id, ET.TRIBUNAL_STARTED)[0].payload
        self.assertNotEqual(started["outlier_seat"], bad_seat)
        self.assertNotEqual(out.outlier_seat, bad_seat)
        types = [e.type for e in rig.events(run_id)]
        self.assertIn(ET.TRIBUNAL_OUTCOME, types)
        self.assertEqual(types[-1], ET.RUN_COMPLETED)


if __name__ == "__main__":
    unittest.main()
