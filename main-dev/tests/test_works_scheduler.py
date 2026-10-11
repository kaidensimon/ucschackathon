import unittest

from council.core.schemas import MicroTask, TaskStatus
from council.works.scheduler import Scheduler

Q, R, P = TaskStatus.queued, TaskStatus.running, TaskStatus.passed
F, B, S = TaskStatus.failed, TaskStatus.blocked, TaskStatus.skipped


def T(i, deps=(), ws=()):
    return MicroTask(id=i, deps=list(deps), write_set=list(ws))


class SchedulerTests(unittest.TestCase):
    def test_chain_length(self):
        s = Scheduler([T("a"), T("b", ["a"]), T("c", ["b"]), T("d", ["a"]), T("e")])
        self.assertEqual(s.chain_length("a"), 2)
        self.assertEqual(s.chain_length("b"), 1)
        self.assertEqual(s.chain_length("c"), 0)
        self.assertEqual(s.chain_length("e"), 0)

    def test_runnable_deps_and_order(self):
        s = Scheduler([T("a"), T("b", ["a"]), T("z"), T("c", ["b"])])
        st = {"a": Q, "b": Q, "c": Q, "z": Q}
        self.assertEqual(s.runnable(st, 5), ["a", "z"])
        st["a"] = P
        self.assertEqual(s.runnable(st, 5), ["b", "z"])

    def test_free_slots(self):
        s = Scheduler([T("a"), T("b"), T("c")])
        st = {k: Q for k in "abc"}
        self.assertEqual(s.runnable(st, 2), ["a", "b"])
        self.assertEqual(s.runnable(st, 0), [])

    def test_lock_vs_running(self):
        s = Scheduler([T("a", ws=["x"]), T("b", ws=["x"]), T("c", ws=["y"])])
        self.assertEqual(s.runnable({"a": R, "b": Q, "c": Q}, 5), ["c"])

    def test_lock_among_chosen(self):
        s = Scheduler([T("a", ws=["x"]), T("b", ws=["x", "y"]), T("c", ws=["y"])])
        st = {k: Q for k in "abc"}
        self.assertEqual(s.runnable(st, 5), ["a", "c"])

    def test_unknown_dep_not_runnable(self):
        s = Scheduler([T("a", ["ghost"])])
        self.assertEqual(s.runnable({"a": Q}, 3), [])

    def test_to_skip_transitive(self):
        s = Scheduler([T("a"), T("b", ["a"]), T("c", ["b"]), T("d"), T("e", ["d"])])
        st = {"a": F, "b": Q, "c": Q, "d": Q, "e": Q}
        self.assertEqual(s.to_skip(st), ["b", "c"])

    def test_to_skip_blocked_and_skipped(self):
        s = Scheduler([T("a"), T("b"), T("c", ["a"]), T("d", ["b"])])
        st = {"a": B, "b": S, "c": Q, "d": Q}
        self.assertEqual(s.to_skip(st), ["c", "d"])

    def test_to_skip_ignores_non_queued(self):
        s = Scheduler([T("a"), T("b", ["a"])])
        self.assertEqual(s.to_skip({"a": F, "b": R}), [])

    def test_done(self):
        s = Scheduler([T("a"), T("b", ["a"])])
        self.assertFalse(s.done({"a": P, "b": Q}))
        self.assertFalse(s.done({"a": P, "b": R}))
        self.assertTrue(s.done({"a": F, "b": S}))


if __name__ == "__main__":
    unittest.main()
