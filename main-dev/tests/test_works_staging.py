import tempfile
import unittest
from pathlib import Path

from council.works import staging


def w(p: Path, s: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s)


class StagingTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        root = Path(self._t.name)
        self.src, self.run = root / "src", root / "run"
        self.src.mkdir()
        self.run.mkdir()
        w(self.src / "a.txt", "A")
        w(self.src / "d" / "b.txt", "B")
        w(self.src / "node_modules" / "x.js", "x")
        w(self.src / ".git" / "cfg", "g")
        self.ws = staging.stage_workspace(self.src, self.run)

    def tearDown(self):
        self._t.cleanup()

    def test_stage_skips_ignore(self):
        self.assertEqual(self.ws, self.run / "ws")
        self.assertTrue((self.ws / "d" / "b.txt").is_file())
        self.assertFalse((self.ws / "node_modules").exists())
        self.assertFalse((self.ws / ".git").exists())

    def test_preimage_roundtrip(self):
        staging.save_preimage(self.run, "t1", ["a.txt", "new.txt"])
        w(self.ws / "a.txt", "CHANGED")
        w(self.ws / "new.txt", "N")
        staging.restore_preimage(self.run, "t1")
        self.assertEqual((self.ws / "a.txt").read_text(), "A")
        self.assertFalse((self.ws / "new.txt").exists())

    def test_changed_files(self):
        self.assertEqual(staging.changed_files(self.run, self.src), [])
        w(self.ws / "a.txt", "A2")
        w(self.ws / "n" / "c.txt", "C")
        self.assertEqual(staging.changed_files(self.run, self.src), ["a.txt", "n/c.txt"])

    def test_integrate_and_undo(self):
        w(self.ws / "a.txt", "A2")
        w(self.ws / "n" / "c.txt", "C")
        got = staging.integrate(self.run, self.src)
        self.assertEqual(got, ["a.txt", "n/c.txt"])
        self.assertEqual((self.src / "a.txt").read_text(), "A2")
        self.assertTrue((self.src / "n" / "c.txt").is_file())
        self.assertEqual((self.run / "backup" / "files" / "a.txt").read_text(), "A")
        staging.undo_integrate(self.run, self.src)
        self.assertEqual((self.src / "a.txt").read_text(), "A")
        self.assertFalse((self.src / "n" / "c.txt").exists())


class PreimageSafetyTest(unittest.TestCase):
    """A task id and a write_set are model-written: neither may reach outside the run dir."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = Path(self._t.name)
        self.src, self.run = self.root / "a" / "b" / "src", self.root / "a" / "b" / "c" / "run"
        self.src.mkdir(parents=True)
        self.run.mkdir(parents=True)
        self.victim = self.root / "victim"
        w(self.victim / "keep.txt", "precious")
        w(self.src / "a.txt", "A")
        self.ws = staging.stage_workspace(self.src, self.run)

    def assert_victim_untouched(self):
        self.assertEqual(sorted(p.name for p in self.victim.iterdir()), ["keep.txt"])
        self.assertEqual((self.victim / "keep.txt").read_text(), "precious")

    def test_task_id_with_dots_cannot_leave_the_run_dir(self):
        for bad in ("../../../../victim", "..\\..\\..\\..\\victim", str(self.victim), "..", ".",
                    "a/../../../../../victim", ""):
            staging.save_preimage(self.run, bad, ["a.txt"])
            self.assert_victim_untouched()
            w(self.ws / "a.txt", "CHANGED")
            staging.restore_preimage(self.run, bad)  # still works, under a safe folder name
            self.assertEqual((self.ws / "a.txt").read_text(), "A", bad)
        made = [p.name for p in (self.run / "preimage").iterdir()]
        self.assertTrue(made)
        self.assertTrue(all(staging.valid_task_id(n) for n in made), made)
        # nothing was written outside run/preimage either
        self.assertEqual(sorted(p.name for p in self.run.iterdir()),
                         ["preimage", staging.STAGE_MANIFEST, "ws"])

    def test_safe_task_id(self):
        for good in ("T1", "fix1_2", "a.b-c", "t" * 64):
            self.assertTrue(staging.valid_task_id(good), good)
            self.assertEqual(staging.safe_task_id(good), good)
        for bad in ("../x", "a/b", "a\\b", "C:/x", ".hidden", "-x", "", "a b", "t" * 65, "x..y", "NUL",
                    "con.txt", "x."):
            self.assertFalse(staging.valid_task_id(bad), bad)
            self.assertTrue(staging.valid_task_id(staging.safe_task_id(bad)), bad)
        self.assertNotEqual(staging.safe_task_id("a/b"), staging.safe_task_id("a\\b"))

    def test_write_set_entry_outside_the_root_is_skipped(self):
        outside = self.run / "outside.txt"
        w(outside, "OUT")
        escapes = ["../outside.txt", str(outside), "../../../../victim/keep.txt"]
        staging.save_preimage(self.run, "t1", escapes + ["a.txt", "new.txt"])
        files = self.run / "preimage" / "t1" / "files"
        self.assertEqual(sorted(p.name for p in files.iterdir()), ["a.txt"])
        self.assertFalse((self.run / "preimage" / "t1" / "outside.txt").exists())
        # a manifest that was tampered with cannot unlink or overwrite outside ws either
        man = self.run / "preimage" / "t1" / "manifest.json"
        man.write_text('{"paths": ["../outside.txt", "../../../../victim/keep.txt", "a.txt"], '
                       '"missing": ["../outside.txt", "../../../../victim/keep.txt"]}')
        staging.restore_preimage(self.run, "t1")
        self.assertEqual(outside.read_text(), "OUT")
        self.assert_victim_untouched()


class IntegrateTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        root = Path(self._t.name)
        self.src, self.run = root / "src", root / "run"
        self.src.mkdir()
        self.run.mkdir()
        w(self.src / "a.txt", "A")
        w(self.src / "b.txt", "B")
        self.ws = staging.stage_workspace(self.src, self.run)

    def test_user_edit_during_the_run_is_not_overwritten(self):
        w(self.ws / "a.txt", "TASK")      # a task changed a.txt
        w(self.src / "b.txt", "USER B")   # the user edited b.txt, no task touched it
        self.assertEqual(staging.changed_files(self.run, self.src), ["a.txt"])
        self.assertEqual(staging.integrate(self.run, self.src), ["a.txt"])
        self.assertEqual((self.src / "b.txt").read_text(), "USER B")  # not reverted to the stale copy
        self.assertEqual(staging.last_conflicts(self.run), [])

    def test_file_both_sides_changed_is_a_conflict_and_is_kept(self):
        w(self.ws / "a.txt", "TASK")
        w(self.ws / "b.txt", "TASK B")
        w(self.ws / "new.txt", "TASK NEW")
        w(self.src / "a.txt", "USER")          # edited during the run
        w(self.src / "new.txt", "USER NEW")    # made during the run
        self.assertEqual(staging.conflicts(self.run, self.src), ["a.txt", "new.txt"])
        self.assertEqual(staging.integrate(self.run, self.src), ["b.txt"])
        self.assertEqual((self.src / "a.txt").read_text(), "USER")
        self.assertEqual((self.src / "new.txt").read_text(), "USER NEW")
        self.assertEqual((self.src / "b.txt").read_text(), "TASK B")
        self.assertEqual(staging.last_conflicts(self.run), ["a.txt", "new.txt"])
        staging.undo_integrate(self.run, self.src)
        self.assertEqual((self.src / "b.txt").read_text(), "B")
        self.assertEqual((self.src / "a.txt").read_text(), "USER")

    def test_files_made_by_checks_are_not_integrated(self):
        w(self.ws / "a.txt", "TASK")
        w(self.ws / ".pytest_cache" / "v" / "cache" / "lastfailed", "{}")
        w(self.ws / ".mypy_cache" / "x.json", "{}")
        w(self.ws / "scratch_from_a_check.log", "noise")
        self.assertEqual(staging.changed_files(self.run, self.src), ["a.txt", "scratch_from_a_check.log"])
        # the pipeline passes the files its tasks wrote: nothing else is copied
        got = staging.integrate(self.run, self.src, only={"a.txt", "./never_written.py"})
        self.assertEqual(got, ["a.txt"])
        self.assertFalse((self.src / ".pytest_cache").exists())
        self.assertFalse((self.src / "scratch_from_a_check.log").exists())

    def test_same_content_both_sides_is_no_conflict(self):
        w(self.ws / "a.txt", "SAME")
        w(self.src / "a.txt", "SAME")
        self.assertEqual(staging.conflicts(self.run, self.src), [])

    def test_run_without_manifest_falls_back(self):
        (self.run / staging.STAGE_MANIFEST).unlink()
        w(self.ws / "a.txt", "A2")
        self.assertEqual(staging.changed_files(self.run, self.src), ["a.txt"])
        self.assertEqual(staging.integrate(self.run, self.src), ["a.txt"])


if __name__ == "__main__":
    unittest.main()
