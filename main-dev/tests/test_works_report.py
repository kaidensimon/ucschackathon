import unittest

from council.core.schemas import (
    AttemptRecord,
    CheckResult,
    Check,
    Deliverable,
    MicroTask,
    Plan,
    TaskStatus,
    WorkReport,
)
from council.works.report import build_report, report_text


def _plan() -> Plan:
    return Plan(
        goal="g",
        deliverables=[
            Deliverable(id="d1", paths=["src/a.py"]),
            Deliverable(id="d2", paths=["src/b.py", "docs/x.md"]),
        ],
        tasks=[
            MicroTask(id="T1", title="make a", kind="create_file", write_set=["src/a.py"]),
            MicroTask(id="T2", title="make b", kind="create_file", write_set=["src/b.py"]),
            MicroTask(id="T3", title="doc", kind="write_doc", write_set=["docs/x.md"]),
            MicroTask(id="T4", title="edit", kind="edit_file", write_set=["src/a.py"]),
        ],
    )


def _rec(task_id, attempt, ok=False, model="m1", failing=None, tail="", files=None):
    return AttemptRecord(
        task_id=task_id,
        attempt=attempt,
        model_id=model,
        ok=ok,
        failing_check=failing,
        error_tail=tail,
        files_changed=files or [],
    )


class BuildReportTest(unittest.TestCase):
    def setUp(self):
        self.plan = _plan()
        self.statuses = {
            "T1": TaskStatus.passed,
            "T2": TaskStatus.failed,
            "T3": TaskStatus.blocked,
            "T4": TaskStatus.skipped,
        }
        self.attempts = {
            "T1": [_rec("T1", 1, ok=True, files=["src/a.py"])],
            "T2": [
                _rec("T2", 1, failing="c1", tail="old"),
                _rec("T2", 2, model="m2", failing="c2", tail="assert failed", files=["src/b.py"]),
            ],
            "T3": [],
        }
        self.integ = [CheckResult(ok=False, check_id="g1", output_tail="boom")]

    def build(self, **kw):
        args = dict(
            plan=self.plan,
            statuses=self.statuses,
            attempts=self.attempts,
            integration=self.integ,
            changed=["src/a.py", "./src/a.py"],
            line_stats=(12, 3),
        )
        args.update(kw)
        return build_report(**args)

    def test_summary_counts(self):
        r = self.build()
        self.assertIsInstance(r, WorkReport)
        self.assertEqual((r.summary.passed, r.summary.failed, r.summary.blocked, r.summary.skipped), (1, 1, 1, 1))

    def test_rows_follow_plan_order_and_last_attempt(self):
        r = self.build()
        self.assertEqual([t.id for t in r.tasks], ["T1", "T2", "T3", "T4"])
        t2 = r.tasks[1]
        self.assertEqual(t2.status, TaskStatus.failed)
        self.assertEqual(t2.attempts, 2)
        self.assertEqual(t2.model, "m2")
        self.assertEqual(t2.failing_check, "c2")
        self.assertEqual(t2.error_tail, "assert failed")
        self.assertEqual(t2.files_changed, ["src/b.py"])

    def test_task_without_attempts(self):
        r = self.build()
        t4 = r.tasks[3]
        self.assertEqual(t4.attempts, 0)
        self.assertIsNone(t4.model)
        self.assertIsNone(t4.failing_check)
        self.assertEqual(t4.error_tail, "")

    def test_missing_status_defaults_to_queued(self):
        r = self.build(statuses={})
        self.assertEqual(r.summary.passed + r.summary.failed + r.summary.blocked + r.summary.skipped, 0)
        self.assertTrue(all(t.status == TaskStatus.queued for t in r.tasks))

    def test_integration_passed_through(self):
        r = self.build()
        self.assertEqual(r.integration, self.integ)

    def test_diff_stats(self):
        r = self.build()
        # changed dedupes "./src/a.py" with "src/a.py"; a.py comes from a create_file task
        self.assertEqual(r.diff_stats.files_added, 1)
        self.assertEqual(r.diff_stats.files_changed, 0)
        self.assertEqual(r.diff_stats.lines_added, 12)
        self.assertEqual(r.diff_stats.lines_removed, 3)

    def test_diff_stats_edit_counts_as_changed(self):
        r = self.build(changed=["src/a.py", "docs/x.md"])
        self.assertEqual(r.diff_stats.files_added, 1)
        self.assertEqual(r.diff_stats.files_changed, 1)

    def test_deviations_for_unwritten_deliverables(self):
        r = self.build()
        self.assertEqual(r.deviations, ["d2: src/b.py not written", "d2: docs/x.md not written"])

    def test_no_deviations_when_all_written(self):
        r = self.build(changed=["src\\a.py", "src/b.py", "docs/x.md"])
        self.assertEqual(r.deviations, [])

    def test_default_line_stats(self):
        r = self.build(line_stats=(0, 0))
        self.assertEqual((r.diff_stats.lines_added, r.diff_stats.lines_removed), (0, 0))


class ReportTextTest(unittest.TestCase):
    def setUp(self):
        self.report = build_report(
            _plan(),
            {"T1": TaskStatus.passed, "T2": TaskStatus.failed},
            {"T2": [_rec("T2", 1, model="m9", failing="cmd", tail="E: bad line")]},
            [CheckResult(ok=False, check=Check(type="command", id="g1"), check_id="g1", output_tail="nope")],
            ["src/a.py"],
            (5, 1),
        )

    def test_contains_key_facts(self):
        text = report_text(self.report)
        self.assertIn("passed=1", text)
        self.assertIn("failed=1", text)
        self.assertIn("T2 [failed]", text)
        self.assertIn("failing check: cmd", text)
        self.assertIn("E: bad line", text)
        self.assertIn("g1: FAILED", text)
        self.assertIn("d2: src/b.py not written", text)

    def test_truncates_history(self):
        big = self.report.model_copy(deep=True)
        big.tasks[1].error_tail = "x" * 5000
        text = report_text(big, max_chars=800)
        self.assertLessEqual(len(text), 800)
        self.assertIn("...[truncated]", text)
        self.assertIn("CURRENT STATE (judge this)", text)

    def test_no_truncation_when_short(self):
        text = report_text(self.report, max_chars=100000)
        self.assertNotIn("truncated", text)

    def test_default_limit_is_14000(self):
        big = self.report.model_copy(deep=True)
        big.tasks[1].error_tail = "x" * 30000
        text = report_text(big)
        self.assertLessEqual(len(text), 14000)


def _plan_fix() -> Plan:
    return Plan(
        goal="g",
        deliverables=[Deliverable(id="d1", paths=["src/a.py", "tests/test_a.py"])],
        tasks=[
            MicroTask(id="t1", title="make a", kind="create_file", write_set=["src/a.py"]),
            MicroTask(id="t2", title="make test", kind="create_file", write_set=["tests/test_a.py"]),
            MicroTask(id="fix1_2", title="fix test", kind="edit_file", write_set=["./tests/test_a.py"]),
            MicroTask(id="t4", title="no files", kind="research_note", write_set=[]),
        ],
    )


class SupersededTest(unittest.TestCase):
    def setUp(self):
        self.plan = _plan_fix()
        self.statuses = {
            "t1": TaskStatus.passed,
            "t2": TaskStatus.failed,
            "fix1_2": TaskStatus.passed,
            "t4": TaskStatus.failed,
        }
        self.attempts = {
            "t2": [_rec("t2", 1, failing="c1", tail="OLD STALE ERROR assert 3 == 4")],
            "t4": [_rec("t4", 1, failing="c9", tail="real failure")],
        }

    def build(self, **kw):
        args = dict(
            plan=self.plan, statuses=self.statuses, attempts=self.attempts,
            integration=[], changed=["src/a.py", "tests/test_a.py"],
        )
        args.update(kw)
        return build_report(**args)

    def test_superseded_marked_and_counted(self):
        r = self.build()
        by_id = {t.id: t for t in r.tasks}
        self.assertEqual(by_id["t2"].superseded_by, "fix1_2")
        self.assertIsNone(by_id["t1"].superseded_by)
        self.assertIsNone(by_id["fix1_2"].superseded_by)
        # empty write_set is never superseded
        self.assertIsNone(by_id["t4"].superseded_by)
        s = r.summary
        self.assertEqual((s.passed, s.failed, s.blocked, s.superseded), (2, 1, 0, 1))

    def test_last_later_passed_task_wins(self):
        self.plan.tasks.append(
            MicroTask(id="fix2_2", title="again", kind="edit_file", write_set=["tests/test_a.py", "x.py"])
        )
        self.statuses["fix2_2"] = TaskStatus.passed
        r = self.build()
        self.assertEqual({t.id: t for t in r.tasks}["t2"].superseded_by, "fix2_2")

    def test_not_superseded_when_later_task_not_passed(self):
        self.statuses["fix1_2"] = TaskStatus.failed
        r = self.build()
        self.assertIsNone({t.id: t for t in r.tasks}["t2"].superseded_by)
        self.assertEqual(r.summary.superseded, 0)

    def test_not_superseded_when_only_partial_overlap(self):
        self.plan.tasks[1].write_set = ["tests/test_a.py", "tests/other.py"]
        r = self.build()
        self.assertIsNone({t.id: t for t in r.tasks}["t2"].superseded_by)

    def test_earlier_task_does_not_supersede(self):
        self.statuses["t2"] = TaskStatus.passed
        self.statuses["fix1_2"] = TaskStatus.failed
        self.statuses["t1"] = TaskStatus.failed
        r = self.build()
        self.assertIsNone({t.id: t for t in r.tasks}["t1"].superseded_by)

    def test_stale_error_absent_from_text(self):
        text = report_text(self.build())
        self.assertNotIn("OLD STALE ERROR", text)
        self.assertIn("- t2 [failed, superseded by fix1_2: its files were rewritten later] make test", text)
        self.assertIn("real failure", text)

    def test_deviation_counts_files_arg(self):
        r = self.build(changed=[], files={"src/a.py": "x", "tests/test_a.py": "y"})
        self.assertEqual(r.deviations, [])
        r2 = self.build(changed=[])
        self.assertEqual(len(r2.deviations), 2)

    def test_new_args_stored(self):
        fc = [CheckResult(ok=True, check_id="u")]
        r = self.build(final_checks=fc, files={"src/a.py": "x"})
        self.assertEqual(r.final_checks, fc)
        self.assertEqual(r.files, {"src/a.py": "x"})


class CurrentStateTest(unittest.TestCase):
    def report(self, final, integ=None, files=None):
        return build_report(
            _plan_fix(), {"t1": TaskStatus.passed}, {}, integ or [], [], final_checks=final, files=files,
        )

    def test_verdicts(self):
        ok = CheckResult(ok=True, check_id="u")
        bad = CheckResult(ok=False, check_id="v", output_tail="boom")
        self.assertIn("All current checks pass.", report_text(self.report([ok])))
        t = report_text(self.report([ok, bad, bad]))
        self.assertIn("2 current check(s) FAIL.", t)
        self.assertIn("- v: FAILED", t)
        self.assertIn("boom", t)
        self.assertIn("No checks were run on the current files.", report_text(self.report([])))

    def test_invalid_label_and_not_failing(self):
        inv = CheckResult(ok=False, check_id="bad", invalid=True, output_tail="Ran 0 tests")
        ok = CheckResult(ok=True, check_id="u")
        t = report_text(self.report([ok, inv]))
        self.assertIn("- bad: INVALID CHECK (the check is broken, ignore it)", t)
        self.assertIn("All current checks pass.", t)
        self.assertNotIn("Ran 0 tests", t)
        self.assertNotIn("FAIL", t)
        t2 = report_text(self.report([inv]))
        self.assertIn("No checks were run on the current files.", t2)

    def test_check_name_fallbacks(self):
        c1 = CheckResult(ok=True, check=Check(type="command", id="cid"))
        c2 = CheckResult(ok=True, check=Check(type="command", cmd="p" * 200))
        c3 = CheckResult(ok=True)
        t = report_text(self.report([c1, c2, c3]))
        self.assertIn("- cid: ok", t)
        self.assertIn("- " + "p" * 80 + ": ok", t)
        self.assertNotIn("p" * 81, t)
        self.assertIn("- check: ok", t)

    def test_failed_output_clipped_to_1200(self):
        bad = CheckResult(ok=False, check_id="v", output_tail="a" * 5000 + "END")
        t = report_text(self.report([bad]))
        self.assertIn("END", t)
        self.assertLess(t.count("a"), 1300)

    def test_layout_order(self):
        final = [CheckResult(ok=True, check_id="u")]
        integ = [CheckResult(ok=True, check_id="u"), CheckResult(ok=False, check_id="g9", output_tail="no")]
        t = report_text(self.report(final, integ, files={"src/a.py": "print(1)"}))
        order = [
            t.index("CURRENT STATE (judge this)"),
            t.index("Files now:"),
            t.index("--- src/a.py ---"),
            t.index("print(1)"),
            t.index("- g9: FAILED"),
            t.index("HISTORY (earlier attempts, for context only)"),
            t.index("Deviations:"),
        ]
        self.assertEqual(order, sorted(order))
        # "u" is already in final_checks, so it is not repeated in the integration block
        self.assertEqual(t.count("- u: ok"), 1)

    def test_truncation_keeps_current_state(self):
        final = [CheckResult(ok=False, check_id="v", output_tail="short")]
        files = {"a.py": "A" * 3000, "b.py": "B" * 3000}
        r = self.report(final, files=files)
        r.tasks[0].error_tail = "h" * 8000
        text = report_text(r, max_chars=2000)
        self.assertLessEqual(len(text), 2000)
        self.assertIn("1 current check(s) FAIL.", text)
        self.assertIn("- v: FAILED", text)
        self.assertIn("...[truncated]", text)
        # history cut first: both file heads survive
        self.assertIn("--- a.py ---", text)
        self.assertIn("--- b.py ---", text)
        self.assertIn("AAAA", text)
        self.assertIn("BBBB", text)

    def test_history_cut_before_files(self):
        files = {"a.py": "A" * 500}
        r = self.report([CheckResult(ok=True, check_id="u")], files=files)
        r.tasks[0].error_tail = "h" * 600
        full = report_text(r, max_chars=100000)
        text = report_text(r, max_chars=len(full) - 300)
        self.assertLessEqual(len(text), len(full) - 300)
        self.assertIn("A" * 500, text)
        self.assertIn("...[truncated]", text)
        self.assertIn("Deviations:", text)

    def test_tiny_limit_never_cuts_verdict(self):
        bad = CheckResult(ok=False, check_id="v", output_tail="x")
        text = report_text(self.report([bad], files={"a.py": "A" * 100}), max_chars=10)
        self.assertIn("1 current check(s) FAIL.", text)
        self.assertIn("- v: FAILED", text)
        self.assertIn("...[truncated]", text)


if __name__ == "__main__":
    unittest.main()
