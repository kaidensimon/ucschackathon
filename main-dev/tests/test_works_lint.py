import unittest
from pathlib import Path

from council.core.schemas import (
    Check, ContextFile, Deliverable, InterfaceDef, MicroTask, Plan, TaskBudget, TaskContext,
)
from council.works.lint import lint_plan, reachable, topo_order

WS = Path(__file__).parent


def T(id, deps=(), write=(), read=(), acc=True, **kw):
    return MicroTask(
        id=id, deps=list(deps), write_set=list(write), read_set=list(read),
        acceptance=[Check(type="exists", path="x")] if acc else [], **kw,
    )


def codes(plan, **kw):
    return [i.code for i in lint_plan(plan, WS, **kw)]


class LintTest(unittest.TestCase):
    def test_clean(self):
        p = Plan(tasks=[T("a", write=["a.py"]), T("b", deps=["a"], write=["b.py"])],
                 deliverables=[Deliverable(id="d", paths=["a.py"])])
        self.assertEqual(codes(p), [])

    def test_duplicate(self):
        self.assertIn("duplicate_id", codes(Plan(tasks=[T("a"), T("a")])))

    def test_unknown_dep(self):
        self.assertIn("unknown_dep", codes(Plan(tasks=[T("a", deps=["zz"])])))

    def test_cycle(self):
        p = Plan(tasks=[T("a", deps=["b"]), T("b", deps=["a"])])
        self.assertIn("cycle", codes(p))
        with self.assertRaises(ValueError):
            topo_order(p.tasks)

    def test_topo_and_reachable(self):
        ts = [T("c", deps=["b"]), T("b", deps=["a"]), T("a")]
        self.assertEqual(topo_order(ts), ["a", "b", "c"])
        r = reachable(ts)
        self.assertEqual(r["c"], {"a", "b"})
        self.assertEqual(r["a"], set())

    def test_write_overlap(self):
        p = Plan(tasks=[T("a", write=["f.py"]), T("b", write=["./f.py"])])
        self.assertIn("write_overlap", codes(p))
        ok = Plan(tasks=[T("a", write=["f.py"]), T("c", deps=["a"]), T("b", deps=["c"], write=["f.py"])])
        self.assertNotIn("write_overlap", codes(ok))

    def test_no_acceptance(self):
        self.assertIn("no_acceptance", codes(Plan(tasks=[T("a", acc=False)])))

    def test_path_escape(self):
        for bad in ["../x.py", "/etc/passwd", "C:\\x\\y", "a/../../x"]:
            self.assertIn("path_escape", codes(Plan(tasks=[T("a", write=[bad])])), bad)
        self.assertIn("path_escape", codes(Plan(tasks=[T("a", read=["../r"])])))
        self.assertNotIn("path_escape", codes(Plan(tasks=[T("a", write=["sub/../x.py"])])))

    def test_too_many_files(self):
        self.assertIn("too_many_files", codes(Plan(tasks=[T("a", write=["1", "2", "3"])])))

    def test_input_too_large(self):
        ctx = TaskContext(files=[ContextFile(path="f", content="x" * 20000)])
        self.assertIn("input_too_large", codes(Plan(tasks=[T("a", context=ctx)])))

    def test_output_cap(self):
        t = T("a", budget=TaskBudget(max_output_tokens=9000))
        self.assertIn("output_cap_too_large", codes(Plan(tasks=[t])))

    def test_deliverable_uncovered(self):
        p = Plan(tasks=[T("a", write=["a.py"])], deliverables=[Deliverable(id="d", paths=["nope.py"])])
        self.assertIn("deliverable_uncovered", codes(p))

    def test_interface_undefined(self):
        ctx = TaskContext(interfaces=[InterfaceDef(name="Foo")])
        self.assertIn("interface_undefined", codes(Plan(tasks=[T("a", context=ctx)])))
        ok = Plan(tasks=[T("a", context=ctx)], interfaces=[InterfaceDef(name="Foo")])
        self.assertNotIn("interface_undefined", codes(ok))


class TaskIdLintTest(unittest.TestCase):
    def test_bad_ids_are_reported(self):
        for bad in ("../../victim", "a/b", "a\\b", "C:/Users/x", ".x", "", "two words", "x" * 65, "NUL"):
            self.assertIn("bad_id", codes(Plan(tasks=[T(bad)])), bad)

    def test_plain_ids_pass(self):
        for good in ("T1", "t_2", "fix1_1", "a.b-c"):
            self.assertNotIn("bad_id", codes(Plan(tasks=[T(good)])), good)

    def test_reported_once_per_id(self):
        self.assertEqual(codes(Plan(tasks=[T("a/b"), T("a/b")])).count("bad_id"), 1)


if __name__ == "__main__":
    unittest.main()
