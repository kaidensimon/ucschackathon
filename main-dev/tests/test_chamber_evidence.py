import asyncio
import tempfile
import unittest
from pathlib import Path

from council.chamber.evidence import EvidenceRunner
from council.core.schemas import CheckRequest


def run(r, **kw):
    return asyncio.run(r.run(CheckRequest(**kw)))


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.ws = Path(self._td.name)
        (self.ws / "a.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
        (self.ws / "sub").mkdir()
        (self.ws / "sub" / "b.py").write_text("x = 1\nneedle here\n", encoding="utf-8")
        (self.ws / "node_modules").mkdir()
        (self.ws / "node_modules" / "c.js").write_text("needle\n", encoding="utf-8")

    def test_python_real(self):
        r = run(EvidenceRunner(self.ws), kind="python", spec="print(6*7)")
        self.assertTrue(r.ok)
        self.assertIn("42", r.output)
        self.assertEqual(r.exit_code, 0)

    def test_python_fake_and_timeout(self):
        seen = {}

        def fake(cmd, cwd, timeout_s=60, allowed=None):
            seen.update(cmd=cmd, cwd=cwd, t=timeout_s, text=(Path(cwd) / "check.py").read_text())
            return {"exit_code": -2, "output": "partial", "ms": 1, "refused": None}

        r = run(EvidenceRunner(None, sandbox_run=fake, python_timeout_s=3), kind="python", spec="while 1: pass")
        self.assertFalse(r.ok)
        self.assertIn("timed out", r.output)
        self.assertEqual(seen["t"], 3)
        self.assertEqual(seen["text"], "while 1: pass")

    def test_python_refused(self):
        fake = lambda *a, **k: {"exit_code": -1, "output": "", "ms": 0, "refused": "nope"}
        r = run(EvidenceRunner(None, sandbox_run=fake), kind="python", spec="x")
        self.assertFalse(r.ok)
        self.assertIn("nope", r.output)

    def test_sandbox_raises(self):
        def boom(*a, **k):
            raise RuntimeError("bang")
        r = run(EvidenceRunner(None, sandbox_run=boom), kind="python", spec="x")
        self.assertFalse(r.ok)

    def test_read_file_whole_and_range(self):
        rn = EvidenceRunner(self.ws)
        r = run(rn, kind="read_file", spec="a.txt")
        self.assertTrue(r.ok)
        self.assertIn("four", r.output)
        r = run(rn, kind="read_file", spec="a.txt:2-3")
        self.assertIn("2: two", r.output)
        self.assertIn("3: three", r.output)
        self.assertNotIn("one", r.output)
        self.assertNotIn("four", r.output)

    def test_read_file_escape_and_missing(self):
        rn = EvidenceRunner(self.ws)
        self.assertFalse(run(rn, kind="read_file", spec="../x.txt").ok)
        self.assertFalse(run(rn, kind="read_file", spec="sub/../../x").ok)
        r = run(rn, kind="read_file", spec="nope.txt")
        self.assertFalse(r.ok)
        self.assertIn("not found", r.output)

    def test_grep(self):
        r = run(EvidenceRunner(self.ws), kind="grep", spec="needle")
        self.assertTrue(r.ok)
        self.assertIn("sub/b.py:2: needle here", r.output)
        self.assertNotIn("node_modules", r.output)

    def test_grep_cap_and_bad_regex(self):
        (self.ws / "big.txt").write_text("hit\n" * 100, encoding="utf-8")
        r = run(EvidenceRunner(self.ws, max_output_chars=100000), kind="grep", spec="hit")
        self.assertEqual(len(r.output.splitlines()), 40)
        self.assertFalse(run(EvidenceRunner(self.ws), kind="grep", spec="(").ok)

    def test_truncate(self):
        r = run(EvidenceRunner(self.ws, max_output_chars=5), kind="read_file", spec="a.txt")
        self.assertTrue(r.truncated)
        self.assertEqual(len(r.output), 5)

    def test_no_workspace_and_unknown_kind(self):
        rn = EvidenceRunner(None)
        for k in ("read_file", "grep"):
            r = run(rn, kind=k, spec="x")
            self.assertFalse(r.ok)
            self.assertIn("workspace", r.output)
        r = asyncio.run(rn.run(type("C", (), {"kind": "bogus", "spec": "", "settles": None})()))
        self.assertFalse(r.ok)
        self.assertIn("unknown", r.output)


class GrepBounds(unittest.TestCase):
    def test_catastrophic_regex_from_a_seat_times_out(self):
        import time
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "f.txt").write_text("a" * 60 + "!\nplain line\n", encoding="utf-8")
            runner = EvidenceRunner(ws, grep_timeout_s=1.0)
            t0 = time.monotonic()
            res = asyncio.run(runner.run(CheckRequest(kind="grep", spec="(a+)+$")))
            self.assertLess(time.monotonic() - t0, 15)
            self.assertFalse(res.ok)
            self.assertEqual(res.error, "timeout")
            self.assertIn("timed out", res.output)
            # the runner is still usable, and a normal backtracking pattern works in the child
            res = asyncio.run(runner.run(CheckRequest(kind="grep", spec=r"pl\w+ line")))
            self.assertTrue(res.ok)
            self.assertIn("f.txt:2: plain line", res.output)


if __name__ == "__main__":
    unittest.main()
