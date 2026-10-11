import tempfile
import unittest
from pathlib import Path

from council.works.sandbox import run_command


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.cwd = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_ok(self):
        r = run_command('python -c "print(42)"', self.cwd)
        self.assertEqual(r["exit_code"], 0)
        self.assertIn("42", r["output"])
        self.assertIsNone(r["refused"])
        self.assertIsInstance(r["ms"], int)

    def test_nonzero_and_stderr(self):
        r = run_command('python -c "import sys; sys.stderr.write(\'bad\'); sys.exit(3)"', self.cwd)
        self.assertEqual(r["exit_code"], 3)
        self.assertIn("bad", r["output"])

    def test_cwd(self):
        r = run_command('python -c "import os; print(os.getcwd())"', self.cwd)
        self.assertEqual(Path(r["output"].strip()).resolve(), self.cwd.resolve())

    def test_not_allowed(self):
        r = run_command("notepad foo.txt", self.cwd)
        self.assertEqual(r["exit_code"], -1)
        self.assertIsNotNone(r["refused"])

    def test_allowed_extend(self):
        r = run_command('python -c "print(1)"', self.cwd, allowed=["pytest"])
        self.assertEqual(r["exit_code"], -1)

    def test_install_refused(self):
        for c in ["python -m pip install requests", "python -c pip install x",
                  "pip install x", "python -m pip list"]:
            r = run_command(c, self.cwd)
            self.assertEqual(r["exit_code"], -1, c)
            self.assertIsNotNone(r["refused"], c)

    def test_install_in_allowed_exe(self):
        r = run_command("python3 -m pip install foo", self.cwd)
        self.assertEqual(r["exit_code"], -1)
        self.assertIn("install", r["refused"])

    def test_timeout(self):
        r = run_command('python -c "import time; time.sleep(30)"', self.cwd, timeout_s=1)
        self.assertEqual(r["exit_code"], -2)
        self.assertLess(r["ms"], 15000)

    def test_env_scrubbed(self):
        import os
        os.environ["COUNCIL_SECRET_TEST"] = "x"
        try:
            r = run_command('python -c "import os; print(os.environ.get(\'COUNCIL_SECRET_TEST\'), os.environ.get(\'PYTHONDONTWRITEBYTECODE\'))"', self.cwd)
        finally:
            del os.environ["COUNCIL_SECRET_TEST"]
        self.assertIn("None 1", r["output"])

    def test_tail_200(self):
        r = run_command('python -c "[print(i) for i in range(500)]"', self.cwd)
        lines = r["output"].splitlines()
        self.assertEqual(len(lines), 200)
        self.assertEqual(lines[-1], "499")

    def test_empty_and_bad(self):
        self.assertEqual(run_command("", self.cwd)["exit_code"], -1)


class InstallGuardTests(unittest.TestCase):
    """The guard reads the parsed argv: quoting or a joined -mNAME must not pass."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.cwd = Path(self._td.name)

    def test_install_forms_are_refused(self):
        for c in ['python -mpip install x', 'python -m "pip" install x', "python -m 'pip' install x",
                  "python -m ensurepip", "python -mensurepip --upgrade", "python -Bm pip list",
                  "python -I -m venv env", "python -X dev -m pip install x", "python -W ignore -mpip",
                  "python3 -m pip._internal install x", "python -m easy_install x", "python -m uv pip install x",
                  "python -m pipx install x", "python -m conda install x", "python -m virtualenv v",
                  'python -c "import pip"', 'python -c "import ensurepip; ensurepip.bootstrap()"']:
            r = run_command(c, self.cwd)
            self.assertEqual(r["exit_code"], -1, c)
            self.assertIsNotNone(r["refused"], c)
            self.assertIn("refused", r["refused"], c)

    def test_other_modules_and_scripts_still_run(self):
        (self.cwd / "pipeline.py").write_text("print('ran')", encoding="utf-8")
        for c in ['python -m json.tool --help', "python pipeline.py", 'python -c "print(\'pipes\')"']:
            r = run_command(c, self.cwd)
            self.assertIsNone(r["refused"], c)
            self.assertEqual(r["exit_code"], 0, c)

    def test_install_reason(self):
        from council.works.sandbox import install_reason
        self.assertIsNone(install_reason(["python", "-m", "unittest"]))
        self.assertIsNone(install_reason(["python", "script.py", "-m", "x"]))
        self.assertEqual(install_reason(["python", "-mpip"]), "python -m pip")
        self.assertEqual(install_reason(["C:\\Py\\python.exe", "-sBm", '"pip"']), "python -m pip")


class BoundsTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.cwd = Path(self._td.name)

    def test_output_flood_is_killed_and_memory_stays_bounded(self):
        import time
        from council.works import sandbox
        t0 = time.monotonic()
        r = run_command('python -c "while True: print(\'x\' * 1000)"', self.cwd, timeout_s=60,
                        max_output_bytes=1_000_000)
        self.assertLess(time.monotonic() - t0, 30)  # killed at the cap, not at the timeout
        self.assertEqual(r["exit_code"], sandbox.OUTPUT_EXIT)
        self.assertIn("output over", r["output"])
        self.assertLessEqual(len(r["output"]), sandbox.KEEP_BYTES + 200)

    def test_timeout_kills_the_whole_tree(self):
        import time
        # The child starts a grandchild that inherits the pipe and sleeps. Killing only the
        # child would leave the pipe open and the reader waiting for the grandchild.
        code = ("import subprocess, sys, time; "
                "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(40)']); "
                "print('started', flush=True); time.sleep(40)")
        t0 = time.monotonic()
        r = run_command(f'python -c "{code}"', self.cwd, timeout_s=1.5)
        took = time.monotonic() - t0
        self.assertEqual(r["exit_code"], -2)
        self.assertIn("started", r["output"])
        self.assertLess(took, 20)


if __name__ == "__main__":
    unittest.main()
