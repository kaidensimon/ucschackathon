import asyncio
import copy
import tempfile
import unittest
from pathlib import Path

from council.core import event_types as ET
from council.core.config import ForemanConfig
from council.core.schemas import CallResult, Check, Deliverable, MicroTask, Plan
from council.works.foreman import Foreman, PlanError, auto_fix, canonical_test_cmd, repair_test_commands
from council.works.lint import lint_plan

IFACE = {"name": "take", "kind": "function", "definition": "def take(key: str, cost: int) -> bool"}
NO_PATCH = {"add_tasks": [], "remove_task_ids": [], "edits": []}


def task(id, write, deps=(), acceptance="exists", **more):
    out = {
        "id": id, "title": f"task {id}", "kind": "create_file", "goal": f"write {write}",
        "write_set": list(write), "output_contract": "files exist", "deps": list(deps),
    }
    if acceptance == "exists":
        out["acceptance"] = [{"type": "exists", "path": write[0]}]
    out.update(more)
    return out


def outline(milestones=1, deliverable_paths=("a.py",)):
    return {
        "interfaces": [IFACE],
        "deliverables": [{"id": "D1", "description": "the code", "paths": list(deliverable_paths)}],
        "global_acceptance": [{"type": "command", "cmd": "python -m unittest"}],
        "milestones": [{"id": f"M{n}", "title": f"part {n}"} for n in range(1, milestones + 1)],
        "out_of_scope": ["docs"],
        "risks": ["time"],
    }


class FakeGateway:
    """Hands out canned dicts in order, one queue per purpose. None means a failed call."""

    def __init__(self, decompose, review=()):
        self.queues = {"foreman.decompose": list(decompose), "foreman.review": list(review)}
        self.specs = []

    async def call(self, spec):
        self.specs.append(spec)
        queue = self.queues[spec.purpose]
        reply = queue.pop(0) if queue else None
        if reply is None:
            return CallResult(call_id=spec.call_id, ok=False, error="invalid_output")
        return CallResult(call_id=spec.call_id, ok=True, model_id=spec.model_id, parsed=copy.deepcopy(reply))

    def count(self, purpose):
        return sum(1 for s in self.specs if s.purpose == purpose)


class ForemanCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name)
        self.events = []

    def foreman(self, gateway, cfg=None):
        return Foreman(gateway, lambda t, p: self.events.append((t, p)), cfg or ForemanConfig(), self.ws)

    def make(self, gateway, reviewer="rev", cfg=None):
        f = self.foreman(gateway, cfg)
        return asyncio.run(f.make_plan("run1", "build a limiter", "token bucket", "empty", "dec", reviewer))

    def types(self):
        return [t for t, _ in self.events]

    def payloads(self, type_):
        return [p for t, p in self.events if t == type_]


class TestHappyPath(ForemanCase):
    def test_plan_events_and_calls(self):
        gw = FakeGateway(
            [outline(milestones=2),
             {"tasks": [task("T1", ["a.py"], interfaces=["take"])]},
             {"tasks": [task("T2", ["test_a.py"], deps=["T1"])]}],
            [NO_PATCH],
        )
        plan = self.make(gw)

        self.assertIsInstance(plan, Plan)
        self.assertEqual([t.id for t in plan.tasks], ["T1", "T2"])
        self.assertEqual((plan.goal, plan.approach), ("build a limiter", "token bucket"))
        self.assertEqual(plan.out_of_scope, ["docs"])
        self.assertEqual(plan.global_acceptance[0].cmd, "python -m unittest")
        # interface copied word for word into the task that names it
        self.assertEqual(plan.tasks[0].context.interfaces, plan.interfaces)
        self.assertEqual(plan.tasks[1].context.interfaces, [])
        self.assertEqual(plan.tasks[0].budget.max_output_tokens, 1500)

        self.assertEqual(self.types(), [ET.PLAN_DRAFTED, ET.PLAN_LINTED, ET.PLAN_REVIEWED, ET.PLAN_READY])
        self.assertEqual(gw.count("foreman.decompose"), 3)  # outline + one per milestone
        self.assertEqual(gw.count("foreman.review"), 1)
        self.assertEqual([s.model_id for s in gw.specs], ["dec", "dec", "dec", "rev"])
        self.assertEqual(len({s.call_id for s in gw.specs}), 4)
        self.assertTrue(all(s.run_id == "run1" and s.json_schema for s in gw.specs))

        drafted = self.payloads(ET.PLAN_DRAFTED)[0]
        self.assertEqual((drafted["task_count"], drafted["model_id"]), (2, "dec"))
        linted = self.payloads(ET.PLAN_LINTED)[0]
        self.assertTrue(linted["ok"])
        self.assertEqual(linted["errors"], [])
        ready = self.payloads(ET.PLAN_READY)[0]
        self.assertEqual((ready["task_count"], ready["micro_count"], ready["senior_count"]), (2, 2, 0))
        self.assertEqual(ready["plan"]["tasks"][1]["deps"], ["T1"])
        for type_, payload in self.events:
            ET.validate_payload(type_, payload)

    def test_prompts_carry_the_inputs(self):
        gw = FakeGateway([outline(), {"tasks": [task("T1", ["a.py"])]}], [NO_PATCH])
        self.make(gw)
        first, second, review = gw.specs
        self.assertIn("token bucket", first.messages[0]["content"])
        self.assertIn("build a limiter", first.messages[1]["content"])
        self.assertIn("def take(key: str, cost: int) -> bool", second.messages[1]["content"])
        self.assertEqual(second.json_schema["properties"]["tasks"]["maxItems"], 12)
        iface_items = second.json_schema["$defs"]["_TaskDraft"]["properties"]["interfaces"]["items"]
        self.assertEqual(iface_items["enum"], ["take"])
        self.assertIn('"id":"T1"', review.messages[1]["content"])

    def test_no_reviewer_skips_the_second_key(self):
        gw = FakeGateway([outline(), {"tasks": [task("T1", ["a.py"])]}])
        plan = self.make(gw, reviewer=None)
        self.assertEqual(len(plan.tasks), 1)
        self.assertEqual(gw.count("foreman.review"), 0)
        self.assertEqual(self.types(), [ET.PLAN_DRAFTED, ET.PLAN_LINTED, ET.PLAN_READY])

    def test_no_milestones_still_asks_for_tasks(self):
        head = outline()
        head["milestones"] = []
        gw = FakeGateway([head, {"tasks": [task("T1", ["a.py"])]}], [NO_PATCH])
        self.assertEqual(len(self.make(gw).tasks), 1)

    def test_task_cap_per_call(self):
        many = {"tasks": [task(f"T{n}", [f"f{n}.py"]) for n in range(5)]}
        gw = FakeGateway([outline(deliverable_paths=["f0.py"]), many], [NO_PATCH])
        plan = self.make(gw, cfg=ForemanConfig(max_tasks_per_decompose_call=3))
        self.assertEqual([t.id for t in plan.tasks], ["T0", "T1", "T2"])
        self.assertEqual(gw.specs[1].json_schema["properties"]["tasks"]["maxItems"], 3)

    def test_same_id_in_two_milestones(self):
        gw = FakeGateway(
            [outline(milestones=2),
             {"tasks": [task("T1", ["a.py"])]},
             {"tasks": [task("T1", ["b.py"]), task("T2", ["c.py"], deps=["T1"])]}],
            [NO_PATCH],
        )
        plan = self.make(gw)
        self.assertEqual([t.id for t in plan.tasks], ["T1", "T1_2", "T2"])
        self.assertEqual(plan.tasks[2].deps, ["T1_2"])  # the dep follows its own milestone's task
        self.assertIn('["T1"]', gw.specs[2].messages[1]["content"])  # used ids are shown


class TestAutoFix(ForemanCase):
    def test_plan_that_needs_every_fix(self):
        tasks = [
            task("T1", ["a.py"]),
            task("T1", ["b.py"]),                              # duplicate id, different task
            task("T2", ["c.py"], deps=["ghost", "T2", "T1"]),  # unknown dep and self dep
            task("T3", ["a.py"]),                              # same file as T1, no order
            task("T4", ["d.py"], acceptance=None),             # no acceptance
            task("T4", ["d.py"], acceptance=None),             # exact copy
        ]
        gw = FakeGateway([outline(), {"tasks": tasks}], [NO_PATCH])
        plan = self.make(gw)

        by_id = {t.id: t for t in plan.tasks}
        # T3 wrote the same file as T1, so the two became one task (workers write whole files).
        self.assertEqual(list(by_id), ["T1", "T1_2", "T2", "T4"])
        self.assertEqual(by_id["T1_2"].write_set, ["b.py"])
        self.assertEqual(by_id["T2"].deps, ["T1"])
        self.assertEqual([(c.type, c.path) for c in by_id["T4"].acceptance], [("exists", "d.py")])
        self.assertEqual(lint_plan(plan, self.ws), [])

        linted = self.payloads(ET.PLAN_LINTED)[0]
        self.assertTrue(linted["ok"])
        text = " | ".join(linted["warnings"])
        for needle in ("'T1_2'", "dropped dep 'ghost'", "dropped dep 'T2'", "'T3' now depends on 'T1'",
                       "added an exists check on 'd.py'", "exact copy of task 'T4'"):
            self.assertIn(needle, text)
        self.assertEqual(self.types()[-1], ET.PLAN_READY)

    def test_overlap_already_ordered_is_left_alone(self):
        plan = Plan(tasks=[
            MicroTask(id="A", write_set=["x.py"], acceptance=[Check(type="exists", path="x.py")]),
            MicroTask(id="B", write_set=["y.py"], deps=["A"], acceptance=[Check(type="exists", path="y.py")]),
            MicroTask(id="C", write_set=["./x.py"], deps=["B"], acceptance=[Check(type="exists", path="x.py")]),
        ])
        self.assertEqual(auto_fix(plan), [])
        self.assertEqual(plan.tasks[2].deps, ["B"])

    def test_three_writers_of_one_file_form_a_chain(self):
        plan = Plan(tasks=[MicroTask(id=i, write_set=["x.py"]) for i in ("A", "B", "C")])
        auto_fix(plan)
        self.assertEqual([t.deps for t in plan.tasks], [[], ["A"], ["A", "B"]])
        self.assertEqual([i.code for i in lint_plan(plan, self.ws)], [])

    def test_output_cap_and_stale_interface(self):
        plan = Plan.model_validate({
            "interfaces": [IFACE],
            "tasks": [{
                "id": "A", "write_set": ["x.py"], "budget": {"max_output_tokens": 9000},
                "context": {"interfaces": [{"name": "take", "definition": "def take()"}]},
            }],
        })
        auto_fix(plan, max_out_tokens=1500)
        self.assertEqual(plan.tasks[0].budget.max_output_tokens, 1500)
        self.assertEqual(plan.tasks[0].context.interfaces[0].definition, IFACE["definition"])

    def test_no_acceptance_and_no_write_set_cannot_be_fixed(self):
        plan = Plan(tasks=[MicroTask(id="A")])
        auto_fix(plan)
        self.assertEqual([i.code for i in lint_plan(plan, self.ws)], ["no_acceptance"])


class TestSecondKey(ForemanCase):
    def test_patches_close_a_gap(self):
        # D1 needs a.py and b.py; the draft only writes a.py. The reviewer adds, edits and removes.
        patch = {
            "add_tasks": [task("T9", ["b.py"], deps=["T1"], interfaces=["take"])],
            "remove_task_ids": ["T2", "nobody"],
            "edits": [
                {"task_id": "T1", "field": "tier", "value": "senior"},
                {"task_id": "T1", "field": "notes", "value": "keep it small"},
                {"task_id": "T1", "field": "interfaces", "value": ["take"]},
                {"task_id": "T1", "field": "tier", "value": "giant"},      # not a tier: skipped
                {"task_id": "ghost", "field": "goal", "value": "x"},       # no such task: skipped
            ],
        }
        gw = FakeGateway(
            [outline(deliverable_paths=["a.py", "b.py"]),
             {"tasks": [task("T1", ["a.py"]), task("T2", ["junk.py"]), task("T3", ["c.py"], deps=["T2"])]}],
            [patch],
        )
        plan = self.make(gw)

        self.assertEqual([t.id for t in plan.tasks], ["T1", "T3", "T9"])
        self.assertEqual(plan.tasks[0].tier, "senior")
        self.assertEqual(plan.tasks[0].context.notes, "keep it small")
        self.assertEqual(plan.tasks[0].context.interfaces, plan.interfaces)
        self.assertEqual(plan.tasks[1].deps, [])  # dep on the removed task was dropped
        self.assertEqual(plan.tasks[2].context.interfaces, plan.interfaces)
        self.assertEqual(gw.count("foreman.review"), 1)  # clean after one pass

        self.assertEqual(self.types(), [ET.PLAN_DRAFTED, ET.PLAN_LINTED, ET.PLAN_LINTED,
                                        ET.PLAN_REVIEWED, ET.PLAN_READY])
        first, second = self.payloads(ET.PLAN_LINTED)
        self.assertFalse(first["ok"])
        self.assertTrue(first["will_retry"])
        self.assertIn("b.py", first["errors"][0])
        self.assertTrue(second["ok"])
        self.assertEqual(second["version"], 2)
        reviewed = self.payloads(ET.PLAN_REVIEWED)[0]
        self.assertTrue(reviewed["ok"])
        self.assertEqual(reviewed["reviewer_model_id"], "rev")
        self.assertEqual(reviewed["changes"], [
            "removed task 'T2'", "task 'T1': tier changed", "task 'T1': notes changed",
            "task 'T1': interfaces changed", "added task 'T9'",
        ])
        ready = self.payloads(ET.PLAN_READY)[0]
        self.assertEqual((ready["version"], ready["micro_count"], ready["senior_count"]), (2, 2, 1))
        # the reviewer saw the open lint problem
        self.assertIn("deliverable_uncovered", gw.specs[2].messages[1]["content"])

    def test_two_passes_at_most_then_plan_error(self):
        bad = task("T1", ["../outside.py"])
        retitle = lambda n: {**NO_PATCH, "edits": [{"task_id": "T1", "field": "title", "value": f"try {n}"}]}
        gw = FakeGateway([outline(deliverable_paths=[]), {"tasks": [bad]}],
                         [retitle(1), retitle(2), retitle(3)])
        with self.assertRaises(PlanError) as ctx:
            self.make(gw)
        self.assertEqual(gw.count("foreman.review"), 2)
        self.assertEqual([i.code for i in ctx.exception.issues], ["path_escape"])
        self.assertIn("../outside.py", str(ctx.exception))
        self.assertNotIn(ET.PLAN_READY, self.types())
        self.assertEqual(len(self.payloads(ET.PLAN_REVIEWED)), 2)
        self.assertFalse(self.payloads(ET.PLAN_REVIEWED)[-1]["ok"])

    def test_second_pass_can_finish_the_job(self):
        fix = {**NO_PATCH, "edits": [
            {"task_id": "T1", "field": "write_set", "value": ["a.py"]},
            {"task_id": "T1", "field": "acceptance", "value": [{"type": "exists", "path": "a.py"}]},
        ]}
        half = {**NO_PATCH, "edits": [{"task_id": "T1", "field": "goal", "value": "write a.py"}]}
        gw = FakeGateway([outline(), {"tasks": [task("T1", ["/abs/a.py"])]}], [half, fix])
        plan = self.make(gw)
        self.assertEqual(plan.tasks[0].write_set, ["a.py"])
        self.assertEqual(gw.count("foreman.review"), 2)
        self.assertEqual(self.payloads(ET.PLAN_READY)[0]["version"], 3)

    def test_empty_patch_with_open_errors_stops_early(self):
        gw = FakeGateway([outline(deliverable_paths=["missing.py"]), {"tasks": [task("T1", ["a.py"])]}],
                         [NO_PATCH, NO_PATCH])
        # The review stops after one empty patch; the uncovered deliverable is then repaired by
        # adding a task for it, not by failing the plan.
        plan = self.make(gw)
        self.assertEqual(gw.count("foreman.review"), 1)
        self.assertIn(["missing.py"], [t.write_set for t in plan.tasks])

    def test_failed_review_call_keeps_a_clean_plan(self):
        gw = FakeGateway([outline(), {"tasks": [task("T1", ["a.py"])]}], [None])
        plan = self.make(gw)
        self.assertEqual(len(plan.tasks), 1)
        reviewed = self.payloads(ET.PLAN_REVIEWED)[0]
        self.assertFalse(reviewed["ok"])
        self.assertEqual(reviewed["issues"], ["the review call failed"])
        self.assertEqual(self.types()[-1], ET.PLAN_READY)

    def test_cycle_is_not_fixable(self):
        gw = FakeGateway(
            [outline(), {"tasks": [task("T1", ["a.py"], deps=["T2"]), task("T2", ["b.py"], deps=["T1"])]}],
            [NO_PATCH],
        )
        with self.assertRaises(PlanError) as ctx:
            self.make(gw)
        self.assertEqual([i.code for i in ctx.exception.issues], ["cycle"])


class TestFailures(ForemanCase):
    def test_failed_outline_call(self):
        gw = FakeGateway([None])
        with self.assertRaises(PlanError):
            self.make(gw)
        self.assertEqual(self.events, [])

    def test_failed_milestone_call_is_retried_then_skipped(self):
        # Milestone 2 fails twice (first try and the retry): the plan keeps milestone 1's task.
        gw = FakeGateway([outline(milestones=2), {"tasks": [task("T1", ["a.py"])]}, None, None], [NO_PATCH])
        plan = self.make(gw)
        self.assertEqual([t.id for t in plan.tasks], ["T1"])

    def test_every_milestone_failing_is_an_error(self):
        gw = FakeGateway([outline(milestones=1), None, None])
        with self.assertRaises(PlanError):
            self.make(gw)

    def test_no_tasks_at_all(self):
        gw = FakeGateway([outline(deliverable_paths=[]), {"tasks": []}], [NO_PATCH])
        with self.assertRaises(PlanError) as ctx:
            self.make(gw)
        self.assertIn("no tasks", str(ctx.exception))

    def test_reply_as_text_only(self):
        import json

        class TextGateway(FakeGateway):
            async def call(self, spec):
                result = await super().call(spec)
                if result.ok:
                    result = result.model_copy(update={"content": json.dumps(result.parsed), "parsed": None})
                return result

        gw = TextGateway([outline(), {"tasks": [task("T1", ["a.py"])]}], [NO_PATCH])
        self.assertEqual(len(self.make(gw).tasks), 1)

    def test_cfg_may_be_a_plain_dict(self):
        gw = FakeGateway([outline(), {"tasks": [task("T1", ["a.py"])]}], [NO_PATCH])
        plan = self.make(gw, cfg={"max_task_output_tokens": 800})
        self.assertEqual(plan.tasks[0].budget.max_output_tokens, 800)


class TestUserEdit(ForemanCase):
    def base(self):
        return Plan.model_validate({
            "goal": "g", "approach": "a", "interfaces": [IFACE],
            "deliverables": [{"id": "D1", "paths": ["a.py"]}],
            "tasks": [task("T1", ["a.py"])],
        })

    def test_clean_edit(self):
        plan = self.base()
        edited = plan.model_copy(deep=True)
        edited.tasks[0].title = "renamed"
        out, issues = self.foreman(FakeGateway([])).apply_user_edit(plan, edited)
        self.assertEqual(issues, [])
        self.assertEqual(out.tasks[0].title, "renamed")
        self.assertEqual(self.events, [])

    def test_edit_is_fixed_and_the_rest_is_reported(self):
        plan = self.base()
        edited = plan.model_copy(deep=True)
        edited.goal = ""
        edited.tasks.append(MicroTask(id="T2", write_set=["a.py"], deps=["gone"]))
        edited.tasks.append(MicroTask(id="T3", write_set=["../x.py"]))
        before = edited.model_dump()
        out, issues = self.foreman(FakeGateway([])).apply_user_edit(plan, edited)

        self.assertEqual(out.goal, "g")
        self.assertEqual(out.tasks[1].deps, ["T1"])
        self.assertEqual(out.tasks[1].acceptance[0].type, "exists")
        self.assertEqual([i.code for i in issues], ["path_escape"])
        self.assertEqual(edited.model_dump(), before)  # the caller's object is not touched


class TaskIdAutoFix(unittest.TestCase):
    def test_bad_ids_are_renamed_and_deps_follow(self):
        import tempfile
        plan = Plan(tasks=[
            MicroTask(id="../../victim", write_set=["x.py"], acceptance=[Check(type="exists", path="x.py")]),
            MicroTask(id="step two", write_set=["y.py"], deps=["../../victim"],
                      acceptance=[Check(type="exists", path="y.py")]),
            MicroTask(id="ok", write_set=["z.py"], deps=["step two"],
                      acceptance=[Check(type="exists", path="z.py")]),
        ])
        fixes = auto_fix(plan)
        ids = [t.id for t in plan.tasks]
        self.assertEqual(ids, ["victim", "step_two", "ok"])
        self.assertEqual([t.deps for t in plan.tasks], [[], ["victim"], ["step_two"]])
        self.assertEqual(len([f for f in fixes if "not a plain name" in f]), 2)
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual([i.code for i in lint_plan(plan, Path(td))], [])

    def test_renamed_id_does_not_collide(self):
        plan = Plan(tasks=[MicroTask(id="a b"), MicroTask(id="a_b")])
        auto_fix(plan)
        self.assertEqual(len({t.id for t in plan.tasks}), 2)


def cmd_plan(cmd, test_path="tests/test_textstats.py", global_cmd=None, extra_paths=()):
    t = MicroTask(id="T1", write_set=[test_path], acceptance=[Check(type="command", cmd=cmd)])
    return Plan(
        deliverables=[Deliverable(id="D1", paths=list(extra_paths))],
        global_acceptance=[Check(type="command", cmd=global_cmd)] if global_cmd else [],
        tasks=[t],
    )


class TestRepairTestCommands(unittest.TestCase):
    def fixed(self, cmd, **kw):
        plan = cmd_plan(cmd, **kw)
        out = repair_test_commands(plan)
        return out.tasks[0].acceptance[0].cmd

    def test_real_failing_case_pattern_removed(self):
        got = self.fixed("python -m unittest discover -s tests -p '*_test.py'")
        self.assertEqual(got, "python -m unittest discover -s tests")

    def test_global_acceptance_is_repaired_too(self):
        plan = cmd_plan("python -m unittest discover -s tests -v",
                        global_cmd="python -m unittest discover -s tests -p '*_test.py' -v")
        repair_test_commands(plan)
        self.assertEqual(plan.global_acceptance[0].cmd, "python -m unittest discover -s tests -v")

    def test_long_option_and_equals_forms(self):
        self.assertEqual(self.fixed("python -m unittest discover --start-directory tests --pattern '*_test.py' -v"),
                         "python -m unittest discover --start-directory tests -v")
        self.assertEqual(self.fixed("python -m unittest discover -s tests --pattern=check_*.py"),
                         "python -m unittest discover -s tests")

    def test_matching_pattern_is_kept_and_text_untouched(self):
        cmd = "python -m unittest discover -s tests -p 'test_*.py' -v"
        self.assertEqual(self.fixed(cmd), cmd)
        cmd = "python -m unittest discover   -s tests  -v"  # spacing kept: nothing to fix
        self.assertEqual(self.fixed(cmd), cmd)

    def test_suffix_style_test_file_matches_its_pattern(self):
        cmd = "python -m unittest discover -s tests -p '*_test.py'"
        self.assertEqual(self.fixed(cmd, test_path="tests/stats_test.py"), cmd)

    def test_wrong_start_dir_moves_to_the_test_folder(self):
        self.assertEqual(self.fixed("python -m unittest discover -s test -v"),
                         "python -m unittest discover -s tests -v")
        self.assertEqual(self.fixed("python -m unittest discover -s ./tests/ -v"),
                         "python -m unittest discover -s ./tests/ -v")

    def test_positional_start_dir(self):
        self.assertEqual(self.fixed("python -m unittest discover test"), "python -m unittest discover tests")

    def test_start_dir_removed_when_tests_are_at_the_root(self):
        got = self.fixed("python -m unittest discover -s tests -v", test_path="test_app.py")
        self.assertEqual(got, "python -m unittest discover -v")

    def test_both_fixes_together(self):
        got = self.fixed("python -m unittest discover -s test -p 'check_*.py' -v")
        self.assertEqual(got, "python -m unittest discover -s tests -v")

    def test_other_commands_untouched(self):
        for cmd in ["python -m pytest -q", "python main.py", "python -m unittest",
                    "python -m unittest tests.test_x -v",
                    "cd x && python -m unittest discover -s nope",
                    "python -m unittest discover -s 'unclosed",
                    "python -m unittest discover -s C:\\work\\tests",
                    "python -m unittest discover -s /abs/other -p 'test*.py'"]:
            self.assertEqual(self.fixed(cmd), cmd, cmd)

    def test_no_planned_test_file_changes_nothing(self):
        plan = cmd_plan("python -m unittest discover -s tests -p '*_test.py'", test_path="app/main.py")
        repair_test_commands(plan)
        self.assertEqual(plan.tasks[0].acceptance[0].cmd, "python -m unittest discover -s tests -p '*_test.py'")

    def test_test_file_taken_from_deliverable(self):
        plan = cmd_plan("python -m unittest discover -s tests -p '*_test.py'", test_path="app/main.py",
                        extra_paths=["tests/test_textstats.py"])
        repair_test_commands(plan)
        self.assertEqual(plan.tasks[0].acceptance[0].cmd, "python -m unittest discover -s tests")

    def test_non_command_checks_untouched(self):
        plan = cmd_plan("python -m unittest discover -s tests -p '*_test.py'")
        plan.tasks[0].acceptance.append(Check(type="exists", path="tests/test_textstats.py"))
        repair_test_commands(plan)
        self.assertEqual(plan.tasks[0].acceptance[1], Check(type="exists", path="tests/test_textstats.py"))

    def test_fix_pass_runs_it_on_reshape_and_plain_paths(self):
        bad = "python -m unittest discover -s tests -p '*_test.py'"
        with tempfile.TemporaryDirectory() as td:
            f = Foreman(None, lambda t, p: None, ForemanConfig(), Path(td))
            for reshape in (True, False):
                plan = cmd_plan(bad)
                fixes, _ = f._fix_and_lint(plan, reshape=reshape)
                self.assertEqual(plan.tasks[0].acceptance[0].cmd, "python -m unittest discover -s tests")
                self.assertTrue(any("test command" in x for x in fixes))
            out, _ = f.apply_user_edit(cmd_plan("python -m unittest discover -s tests -v"), cmd_plan(bad))
            self.assertEqual(out.tasks[0].acceptance[0].cmd, "python -m unittest discover -s tests")


class TestCanonicalTestCmd(unittest.TestCase):
    def test_folder_of_first_test_file(self):
        self.assertEqual(canonical_test_cmd(cmd_plan("x")), "python -m unittest discover -s tests -v")

    def test_root_test_file(self):
        self.assertEqual(canonical_test_cmd(cmd_plan("x", test_path="test_app.py")),
                         "python -m unittest discover -v")

    def test_nested_folder(self):
        self.assertEqual(canonical_test_cmd(cmd_plan("x", test_path="./pkg/tests/app_test.py")),
                         "python -m unittest discover -s pkg/tests -v")

    def test_no_test_file_is_none(self):
        self.assertIsNone(canonical_test_cmd(cmd_plan("x", test_path="app/main.py")))
        self.assertIsNone(canonical_test_cmd(Plan()))

    def test_deliverable_that_looks_like_a_test(self):
        plan = cmd_plan("x", test_path="app/main.py", extra_paths=["tests/check_stats.py"])
        self.assertEqual(canonical_test_cmd(plan), "python -m unittest discover -s tests -v")


class TestPlannerPromptLine(ForemanCase):
    def test_decompose_prompts_carry_the_test_command_rule(self):
        gw = FakeGateway([outline(), {"tasks": [task("T1", ["a.py"])]}], [NO_PATCH])
        self.make(gw)
        users = [s.messages[-1]["content"] for s in gw.specs if s.purpose == "foreman.decompose"]
        self.assertEqual(len(users), 2)
        for u in users:
            self.assertIn('"python -m unittest discover -s <tests folder> -v" with no -p pattern', u)
            self.assertIn("computed from the task text", u)


if __name__ == "__main__":
    unittest.main()
