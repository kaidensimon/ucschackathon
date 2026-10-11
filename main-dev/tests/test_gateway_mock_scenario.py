import tempfile
import unittest
from pathlib import Path

from council.core.schemas import (
    DefenseVerdict,
    Deliverable,
    InterfaceDef,
    MemoryVerdict,
    MicroTask,
    Plan,
    ReviewBallot,
    TribunalAnswer,
    TribunalQuestion,
    WorkerOutput,
)
from council.gateway import mock_scenario as ms
from council.works.checks import l0_structure, run_check
from council.works.lint import lint_plan, topo_order
from council.works.ops import apply_ops
from council.works.sandbox import run_command


class _Workspace(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = Path(self._t.name)
        self.plan = Plan.model_validate(ms.plan_for("Build the ratelimiter package"))
        self.tasks = {t.id: t for t in self.plan.tasks}

    def apply(self, task_id, attempt):
        out = WorkerOutput.model_validate(ms.worker_output_for(task_id, attempt))
        res = apply_ops(out, self.root, self.tasks[task_id].write_set)
        self.assertTrue(res.ok, res.error)
        return res

    def check_task(self, task_id):
        return [run_check(c, self.root, run_command) for c in self.tasks[task_id].acceptance]


class TestPlan(_Workspace):
    def test_plan_is_valid_and_lints_clean(self):
        self.assertEqual(self.plan.goal, "Build the ratelimiter package")
        self.assertIn(len(self.plan.tasks), (7, 8))
        self.assertTrue(self.plan.interfaces)
        self.assertTrue(self.plan.deliverables)
        issues = lint_plan(self.plan, self.root)
        self.assertEqual(issues, [], [f"{i.code}: {i.message}" for i in issues])

    def test_empty_task_uses_topic(self):
        self.assertEqual(ms.plan_for("")["goal"], ms.TOPIC)

    def test_dependency_graph_is_real(self):
        order = topo_order(self.plan.tasks)
        self.assertEqual(set(order), set(ms.TASK_IDS))
        with_deps = [t for t in self.plan.tasks if t.deps]
        self.assertGreaterEqual(len(with_deps), 5)
        self.assertTrue(any(len(t.deps) >= 2 for t in self.plan.tasks))
        roots = [t for t in self.plan.tasks if not t.deps]
        self.assertEqual(len(roots), 1)

    def test_write_sets_are_disjoint(self):
        seen = set()
        for t in self.plan.tasks:
            self.assertTrue(t.write_set)
            self.assertLessEqual(len(t.write_set), 2)
            for p in t.write_set:
                self.assertNotIn(p, seen)
                seen.add(p)

    def test_every_task_has_exists_and_parses_checks(self):
        n_cmd = 0
        for t in self.plan.tasks:
            types = [c.type for c in t.acceptance]
            for p in t.write_set:
                self.assertTrue(any(c.type == "exists" and c.path == p for c in t.acceptance), t.id)
                self.assertTrue(any(c.type == "parses" and c.path == p for c in t.acceptance), t.id)
            n_cmd += "command" in types
            ids = [c.id for c in t.acceptance]
            self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(n_cmd, 6)

    def test_global_acceptance_runs_unittest_discover(self):
        cmds = [c.cmd for c in self.plan.global_acceptance if c.type == "command"]
        self.assertIn("python -m unittest discover -s tests", cmds)

    def test_no_command_is_refused_by_the_sandbox(self):
        checks = list(self.plan.global_acceptance)
        for t in self.plan.tasks:
            checks.extend(t.acceptance)
        for c in checks:
            if c.type != "command":
                continue
            r = run_command(c.cmd, self.root, c.timeout_s)
            self.assertIsNone(r["refused"], f"{c.id}: {r['refused']}")

    def test_returns_fresh_copies(self):
        a = ms.plan_for("x")
        a["tasks"][0]["write_set"].append("junk.py")
        a["interfaces"].clear()
        b = ms.plan_for("x")
        self.assertNotIn("junk.py", b["tasks"][0]["write_set"])
        self.assertTrue(b["interfaces"])


class TestDecompose(unittest.TestCase):
    def test_first_call(self):
        r = ms.decompose_reply(0)
        self.assertTrue(r["interfaces"] and r["deliverables"] and r["milestones"])
        self.assertNotIn("tasks", r)
        for i in r["interfaces"]:
            InterfaceDef.model_validate(i)
        for d in r["deliverables"]:
            Deliverable.model_validate(d)
        for m in r["milestones"]:
            self.assertTrue(m["id"] and m["title"])

    def test_later_calls_rebuild_the_plan(self):
        first = ms.decompose_reply(0)
        tasks = []
        for n, m in enumerate(first["milestones"], start=1):
            r = ms.decompose_reply(n)
            self.assertEqual(r["milestone"], m["id"])
            self.assertTrue(r["tasks"])
            self.assertLessEqual(len(r["tasks"]), 12)
            tasks.extend(r["tasks"])
        for t in tasks:
            MicroTask.model_validate(t)
        self.assertEqual(tasks, ms.plan_for("")["tasks"])
        plan = Plan.model_validate({**first, "tasks": tasks})
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(lint_plan(plan, Path(d)), [])

    def test_past_the_end_is_empty(self):
        n = len(ms.decompose_reply(0)["milestones"])
        self.assertEqual(ms.decompose_reply(n + 1)["tasks"], [])
        self.assertEqual(ms.decompose_reply(99)["tasks"], [])


class TestWorkerOutputs(_Workspace):
    def test_every_task_has_an_output_inside_its_write_set(self):
        for tid, task in self.tasks.items():
            for attempt in (1, 2, 3):
                out = WorkerOutput.model_validate(ms.worker_output_for(tid, attempt))
                self.assertIsNone(out.blocked)
                self.assertEqual(sorted(o.path for o in out.ops), sorted(task.write_set))
                for o in out.ops:
                    self.assertTrue(o.content.strip())
                    # about 4 chars per token, cap 1500 tokens
                    self.assertLess(len(o.content) // 4, task.budget.max_output_tokens)

    def test_unknown_task_is_blocked(self):
        out = WorkerOutput.model_validate(ms.worker_output_for("nope", 1))
        self.assertTrue(out.blocked)
        self.assertEqual(out.ops, [])

    def test_only_the_designated_task_changes_between_attempts(self):
        self.assertIn(ms.BUGGY_TASK_ID, ms.TASK_IDS)
        for tid in ms.TASK_IDS:
            same = ms.worker_output_for(tid, 1)["ops"] == ms.worker_output_for(tid, 2)["ops"]
            self.assertEqual(same, tid != ms.BUGGY_TASK_ID, tid)
            self.assertEqual(ms.worker_output_for(tid, 2), ms.worker_output_for(tid, 3))

    def test_whole_build_passes_on_attempt_2(self):
        """The important one: apply every output, run every check, run the global acceptance."""
        for tid in topo_order(self.plan.tasks):
            res = self.apply(tid, 2)
            for r in l0_structure(res.written, self.root):
                self.assertTrue(r.ok, f"{tid} L0: {r.error}")
            for r in self.check_task(tid):
                self.assertTrue(r.ok, f"{tid} {r.check_id}: {r.error}\n{r.output_tail}")
        ran_command = False
        for c in self.plan.global_acceptance:
            r = run_check(c, self.root, run_command)
            self.assertTrue(r.ok, f"global {c.id}: {r.error}\n{r.output_tail}")
            if c.type == "command":
                ran_command = True
                self.assertRegex(r.output_tail, r"Ran \d+ tests")
                self.assertNotIn("Ran 0 tests", r.output_tail)
        self.assertTrue(ran_command)

    def test_designated_task_fails_its_command_check_on_attempt_1(self):
        for dep in self.tasks[ms.BUGGY_TASK_ID].deps:
            self.apply(dep, 2)
        self.apply(ms.BUGGY_TASK_ID, 1)
        results = self.check_task(ms.BUGGY_TASK_ID)
        failed = [r for r in results if not r.ok]
        self.assertEqual([r.type for r in failed], ["command"])
        self.assertEqual(failed[0].check_id, ms.BUGGY_TASK_ID + ".cmd")
        self.assertEqual(failed[0].exit_code, 1)
        self.assertIn("AssertionError", failed[0].output_tail)
        # file checks still pass: the bug is in behavior, not in syntax
        self.assertTrue(all(r.ok for r in results if r.type in ("exists", "parses")))

        self.apply(ms.BUGGY_TASK_ID, 2)
        for r in self.check_task(ms.BUGGY_TASK_ID):
            self.assertTrue(r.ok, f"{r.check_id}: {r.error}\n{r.output_tail}")

    def test_buggy_code_also_fails_the_global_acceptance(self):
        for tid in topo_order(self.plan.tasks):
            self.apply(tid, 1)
        cmd = next(c for c in self.plan.global_acceptance if c.type == "command")
        r = run_check(cmd, self.root, run_command)
        self.assertFalse(r.ok)
        self.assertEqual(r.exit_code, 1)


class TestOtherReplies(unittest.TestCase):
    def test_second_key_patches(self):
        r = ms.second_key_patches()
        self.assertIsInstance(r["patches"], list)
        self.assertLessEqual(len(r["patches"]), 2)

    def test_review_ballots_accept_from_at_least_4_of_5(self):
        for seats in (range(0, 5), range(1, 6)):
            for cycle in (1, 2, 3):
                ballots = [ReviewBallot.model_validate(ms.review_ballot_for(s, cycle)) for s in seats]
                accepts = sum(b.verdict == "accept" for b in ballots)
                self.assertGreaterEqual(accepts, 4)
                for b in ballots:
                    self.assertTrue(b.reason)
                    if b.verdict == "fix":
                        self.assertTrue(b.fixes)
                        self.assertIn(b.fixes[0].task_id, ms.TASK_IDS)

    def test_memory_verdicts(self):
        durable_by_candidate = []
        for c in range(6):
            vs = [MemoryVerdict.model_validate(ms.memory_verdict_for(c, j)) for j in range(5)]
            for v in vs:
                self.assertTrue(v.reason)
                self.assertEqual(v.durable, v.action != "reject")
                self.assertEqual(bool(v.statement_rewrite), v.durable)
            durable_by_candidate.append(sum(v.durable for v in vs))
        self.assertIn(4, durable_by_candidate)
        self.assertIn(0, durable_by_candidate)
        self.assertEqual(ms.memory_verdict_for(0, 0), ms.memory_verdict_for(0, 0))

    def test_tribunal_replies(self):
        for i in range(5):
            q = TribunalQuestion.model_validate(ms.tribunal_reply("tribunal.question", i))
            self.assertTrue(q.question)
            a = TribunalAnswer.model_validate(ms.tribunal_reply("tribunal.answer", i))
            self.assertTrue(a.answer)
            self.assertFalse(a.concedes)
            v = DefenseVerdict.model_validate(ms.tribunal_reply("tribunal.verdict", i))
            self.assertTrue(v.decisive_point and v.lesson)
        held = [ms.tribunal_reply("tribunal.verdict", i)["held"] for i in range(3)]
        self.assertLess(sum(held), 2)  # the defence does not hold by majority

    def test_tribunal_concede(self):
        for i in range(5):
            a = TribunalAnswer.model_validate(ms.tribunal_reply("tribunal.answer", i, concede=True))
            self.assertTrue(a.concedes)
            v = DefenseVerdict.model_validate(ms.tribunal_reply("tribunal.verdict", i, concede=True))
            self.assertFalse(v.held)
            self.assertNotIn(v.error_kind, ("preference", "none"))

    def test_tribunal_bare_purpose_and_unknown(self):
        self.assertIn("question", ms.tribunal_reply("question", 0))
        with self.assertRaises(ValueError):
            ms.tribunal_reply("tribunal.nope", 0)


if __name__ == "__main__":
    unittest.main()
