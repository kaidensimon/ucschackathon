import tempfile
import unittest
from pathlib import Path

from council.core.schemas import WorkerOp, WorkerOutput
from council.works.ops import apply_ops


def out(*ops, blocked=None):
    return WorkerOutput(ops=list(ops), blocked=blocked)


def rd(p):
    with open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


class TestOps(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = Path(self._t.name)

    def test_write_file_creates_dirs(self):
        r = apply_ops(out(WorkerOp(op="write_file", path="a/b/c.txt", content="hi\r\nyo")), self.root, ["a/b/c.txt"])
        self.assertTrue(r.ok, r.error)
        self.assertEqual(r.written, ["a/b/c.txt"])
        self.assertEqual(rd(self.root / "a/b/c.txt"), "hi\r\nyo")

    def test_append(self):
        (self.root / "f.txt").write_bytes("one\n".encode("utf-8"))
        r = apply_ops(out(WorkerOp(op="append", path="f.txt", content="two\n")), self.root, ["f.txt"])
        self.assertTrue(r.ok)
        self.assertEqual(rd(self.root / "f.txt"), "one\ntwo\n")

    def test_replace_block(self):
        (self.root / "f.txt").write_bytes(b"a\n# START\nold1\nold2\n# END\nz\n")
        op = WorkerOp(op="replace_block", path="f.txt", start_anchor="# START", end_anchor="# END", content="new\n")
        r = apply_ops(out(op), self.root, ["f.txt"])
        self.assertTrue(r.ok, r.error)
        self.assertEqual(rd(self.root / "f.txt"), "a\n# START\nnew\n# END\nz\n")

    def test_replace_block_anchor_twice_fails(self):
        (self.root / "f.txt").write_bytes("S\nx\nS\ny\nE\n".encode("utf-8"))
        op = WorkerOp(op="replace_block", path="f.txt", start_anchor="S", end_anchor="E", content="n\n")
        r = apply_ops(out(op), self.root, ["f.txt"])
        self.assertFalse(r.ok)
        self.assertEqual(rd(self.root / "f.txt"), "S\nx\nS\ny\nE\n")

    def test_replace_block_missing_and_order(self):
        (self.root / "f.txt").write_bytes("E\nx\nS\n".encode("utf-8"))
        bad = WorkerOp(op="replace_block", path="f.txt", start_anchor="S", end_anchor="E", content="n")
        self.assertFalse(apply_ops(out(bad), self.root, ["f.txt"]).ok)
        miss = WorkerOp(op="replace_block", path="f.txt", start_anchor="S", end_anchor="NOPE", content="n")
        self.assertFalse(apply_ops(out(miss), self.root, ["f.txt"]).ok)

    def test_anchor_must_be_full_line(self):
        (self.root / "f.txt").write_bytes("S extra\nx\nE\n".encode("utf-8"))
        op = WorkerOp(op="replace_block", path="f.txt", start_anchor="S", end_anchor="E", content="n\n")
        self.assertFalse(apply_ops(out(op), self.root, ["f.txt"]).ok)

    def test_reject_absolute(self):
        p = str((self.root / "x.txt").resolve())
        r = apply_ops(out(WorkerOp(op="write_file", path=p, content="x")), self.root, [p])
        self.assertFalse(r.ok)
        self.assertFalse((self.root / "x.txt").exists())

    def test_reject_escape(self):
        r = apply_ops(out(WorkerOp(op="write_file", path="../evil.txt", content="x")), self.root, ["../evil.txt"])
        self.assertFalse(r.ok)
        self.assertFalse((self.root.parent / "evil.txt").exists())

    def test_reject_outside_write_set(self):
        r = apply_ops(out(WorkerOp(op="write_file", path="b.txt", content="x")), self.root, ["a.txt"])
        self.assertFalse(r.ok)
        self.assertFalse((self.root / "b.txt").exists())

    def test_atomic(self):
        ops = [
            WorkerOp(op="write_file", path="a.txt", content="x"),
            WorkerOp(op="write_file", path="nope.txt", content="y"),
        ]
        r = apply_ops(out(*ops), self.root, ["a.txt"])
        self.assertFalse(r.ok)
        self.assertEqual(r.written, [])
        self.assertFalse((self.root / "a.txt").exists())

    def test_blocked(self):
        r = apply_ops(out(WorkerOp(op="write_file", path="a.txt", content="x"), blocked="spec bad"), self.root, ["a.txt"])
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "blocked: spec bad")
        self.assertFalse((self.root / "a.txt").exists())

    def test_utf8(self):
        r = apply_ops(out(WorkerOp(op="write_file", path="u.txt", content="héllo ✓\n")), self.root, ["u.txt"])
        self.assertTrue(r.ok)
        self.assertEqual((self.root / "u.txt").read_bytes(), "héllo ✓\n".encode("utf-8"))

    def test_write_then_append_same_file(self):
        ops = [
            WorkerOp(op="write_file", path="a.txt", content="1\n"),
            WorkerOp(op="append", path="a.txt", content="2\n"),
        ]
        r = apply_ops(out(*ops), self.root, ["a.txt"])
        self.assertTrue(r.ok)
        self.assertEqual(r.written, ["a.txt"])
        self.assertEqual(rd(self.root / "a.txt"), "1\n2\n")


if __name__ == "__main__":
    unittest.main()
