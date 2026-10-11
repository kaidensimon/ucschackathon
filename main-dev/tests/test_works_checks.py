import json
import tempfile
import unittest
import re
from pathlib import Path

from council.core.schemas import Check
from council.works.checks import is_zero_test_output, l0_structure, run_check


class ChecksTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        (self.root / "a.py").write_text("x = 1\n", encoding="utf-8")
        (self.root / "bad.py").write_text("def (:\n", encoding="utf-8")
        (self.root / "d.json").write_text('{"n": 3}', encoding="utf-8")
        (self.root / "bad.json").write_text("{nope", encoding="utf-8")
        (self.root / "n.md").write_text("hello", encoding="utf-8")
        (self.root / "empty.md").write_text("", encoding="utf-8")
        (self.root / "bin.txt").write_bytes(b"\xff\xfe\x00\xff")

    def tearDown(self):
        self._td.cleanup()

    def run_(self, **kw):
        return run_check(Check(**kw), self.root)

    def test_exists(self):
        self.assertTrue(self.run_(type="exists", path="a.py").ok)
        self.assertFalse(self.run_(type="exists", path="nope.py").ok)

    def test_escape(self):
        r = self.run_(type="exists", path="../outside.txt")
        self.assertFalse(r.ok)
        self.assertIn("escapes", r.error)
        self.assertFalse(self.run_(type="contains", path="../x", pattern="a").ok)

    def test_parses(self):
        self.assertTrue(self.run_(type="parses", path="a.py", language="python").ok)
        self.assertFalse(self.run_(type="parses", path="bad.py", language="python").ok)
        self.assertTrue(self.run_(type="parses", path="d.json", language="json").ok)
        self.assertFalse(self.run_(type="parses", path="bad.json", language="json").ok)
        self.assertTrue(self.run_(type="parses", path="n.md", language="markdown").ok)
        self.assertFalse(self.run_(type="parses", path="empty.md", language="markdown").ok)
        self.assertFalse(self.run_(type="parses", path="bin.txt", language="text").ok)
        self.assertFalse(self.run_(type="parses", path="gone.py", language="python").ok)

    def test_contains(self):
        self.assertTrue(self.run_(type="contains", path="a.py", pattern=r"x\s*=\s*1").ok)
        self.assertFalse(self.run_(type="contains", path="a.py", pattern="zzz").ok)
        self.assertFalse(self.run_(type="contains", path="a.py", pattern="(").ok)

    def test_schema(self):
        good = {"type": "object", "required": ["n"], "properties": {"n": {"type": "integer"}}}
        bad = {"type": "object", "required": ["m"]}
        self.assertTrue(self.run_(type="schema", path="d.json", json_schema=good).ok)
        self.assertFalse(self.run_(type="schema", path="d.json", json_schema=bad).ok)
        self.assertFalse(self.run_(type="schema", path="bad.json", json_schema=good).ok)

    def test_command(self):
        r = self.run_(type="command", cmd="echo hi")
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "no runner")
        calls = []

        def runner(cmd, root, timeout):
            calls.append((cmd, root, timeout))
            return {"exit_code": 0, "output": "fine", "ms": 12.0, "refused": False}

        r = run_check(Check(type="command", cmd="x", timeout_s=5), self.root, runner)
        self.assertTrue(r.ok)
        self.assertEqual(calls[0][2], 5)
        self.assertEqual(r.output_tail, "fine")
        r = run_check(Check(type="command", cmd="x", expect_exit=1), self.root, runner)
        self.assertFalse(r.ok)
        refuse = lambda c, r_, t: {"exit_code": None, "output": "no", "ms": 0, "refused": True}
        self.assertFalse(run_check(Check(type="command", cmd="pip install x"), self.root, refuse).ok)

    def _cmd(self, code, output, expect_exit=0):
        runner = lambda c, r_, t: {"exit_code": code, "output": output, "ms": 1.0, "refused": False}
        return run_check(Check(type="command", cmd="x", expect_exit=expect_exit), self.root, runner)

    def test_command_zero_tests_invalid(self):
        r = self._cmd(5, "\n----\nNO TESTS RAN\n")
        self.assertTrue(r.invalid)
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "invalid check: the command ran zero tests")
        r = self._cmd(0, "Ran 0 tests in 0.000s\n\nOK\n")
        self.assertTrue(r.invalid)
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "invalid check: the command ran zero tests")
        r = self._cmd(5, "collected 0 items\n\nno tests ran in 0.01s", expect_exit=5)
        self.assertTrue(r.invalid)
        self.assertFalse(r.ok)

    def test_command_real_tests_not_invalid(self):
        r = self._cmd(1, "Ran 3 tests in 0.1s\n\nFAILED (failures=1)")
        self.assertFalse(r.invalid)
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "exit 1, expected 0")
        r = self._cmd(0, "Ran 3 tests in 0.1s\n\nOK")
        self.assertFalse(r.invalid)
        self.assertTrue(r.ok)

    def test_is_zero_test_output(self):
        for s in ("Ran 0 tests in 0.0s", "NO TESTS RAN", "collected 0 items", "no tests ran in 0.1s"):
            self.assertTrue(is_zero_test_output(s), s)
        for s in ("", "Ran 10 tests in 1s", "Ran 1 test in 1s", "collected 5 items"):
            self.assertFalse(is_zero_test_output(s), s)

    def test_review_skipped(self):
        r = self.run_(type="review", rubric="good?")
        self.assertIn("needs_model", r.error)

    def test_l0(self):
        res = l0_structure(["a.py", "d.json", "n.md"], self.root)
        self.assertTrue(all(r.ok for r in res))
        res = l0_structure(["a.py", "bad.py", "gone.py", "../e.py"], self.root)
        self.assertEqual([r.ok for r in res], [True, False, False, False])
        self.assertTrue(all(r.level == "L0" for r in res))


class RegexAndSizeBounds(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = Path(self._td.name)

    def test_catastrophic_pattern_times_out_as_a_failed_check(self):
        import time
        from council.works import checks, safe_regex
        (self.root / "f.txt").write_text("a" * 60 + "!", encoding="utf-8")
        old = checks.PATTERN_TIMEOUT_S
        checks.PATTERN_TIMEOUT_S = 1.0
        self.addCleanup(setattr, checks, "PATTERN_TIMEOUT_S", old)
        t0 = time.monotonic()
        r = run_check(Check(type="contains", path="f.txt", pattern="(a+)+$"), self.root)
        self.assertLess(time.monotonic() - t0, 15)
        self.assertFalse(r.ok)
        self.assertEqual(r.error, safe_regex.TIMEOUT)

    def test_backtracking_pattern_that_is_fine_still_matches(self):
        (self.root / "f.py").write_text("def foo(a, b):\n    return a + b\n", encoding="utf-8")
        self.assertTrue(run_check(Check(type="contains", path="f.py", pattern=r"def\s+foo\(.*\):"), self.root).ok)
        self.assertTrue(run_check(Check(type="contains", path="f.py", pattern=r"^    return"), self.root).ok)
        self.assertFalse(run_check(Check(type="contains", path="f.py", pattern=r"class\s+\w+"), self.root).ok)

    def test_pattern_length_and_bad_pattern(self):
        (self.root / "f.txt").write_text("x", encoding="utf-8")
        r = run_check(Check(type="contains", path="f.txt", pattern="x" * 5000), self.root)
        self.assertFalse(r.ok)
        self.assertIn("bad pattern", r.error)
        r = run_check(Check(type="contains", path="f.txt", pattern="(unclosed"), self.root)
        self.assertIn("bad pattern", r.error)

    def test_file_size_cap(self):
        from council.works import checks
        old = checks.MAX_FILE_BYTES
        checks.MAX_FILE_BYTES = 100
        self.addCleanup(setattr, checks, "MAX_FILE_BYTES", old)
        (self.root / "big.txt").write_text("y" * 500, encoding="utf-8")
        r = run_check(Check(type="contains", path="big.txt", pattern="y"), self.root)
        self.assertFalse(r.ok)
        self.assertIn("too large", r.error)

    def test_safe_regex_units(self):
        from council.works import safe_regex
        self.assertTrue(safe_regex.is_simple(r"def foo\("))
        for risky in ("a+", "a*", "a{2}", "(a|b)", "a?"):
            self.assertFalse(safe_regex.is_simple(risky), risky)
        self.assertEqual(safe_regex.search("b+c", "abbbc"), (True, None))
        self.assertEqual(safe_regex.search("^b", "a\nb", re.MULTILINE), (True, None))
        self.assertEqual(safe_regex.search("z+", "abc"), (False, None))
        found, err = safe_regex.search("(a+)+$", "a" * 60 + "!", 0, 1.0)
        self.assertEqual((found, err), (None, safe_regex.TIMEOUT))


if __name__ == "__main__":
    unittest.main()
