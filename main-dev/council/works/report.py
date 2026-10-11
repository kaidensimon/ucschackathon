"""Work report (spec 14.1). Pure: no I/O, no model calls.

The Clerk builds a WorkReport from Inspector records. Seats read report_text(),
never raw task output.

report_text() puts the CURRENT STATE first (checks re-run on the files as they are
now, plus the file contents). Earlier attempts come last as HISTORY. A failed task
whose files a later passed task rewrote is "superseded": its old error text is
stale, so the text shows one line and no error.

Invalid checks (the check itself is broken) never count as failing in this module.
"""

from __future__ import annotations

from typing import Optional

from council.core.schemas import (
    AttemptRecord,
    CheckResult,
    DiffStats,
    Plan,
    TaskStatus,
    WorkReport,
    WorkReportTask,
    WorkSummary,
)

_TRUNC_MARK = "\n...[truncated]"
_CHECK_CLIP = 1200
_HISTORY_HEAD = "HISTORY (earlier attempts, for context only)"
_INVALID_LABEL = "INVALID CHECK (the check is broken, ignore it)"


def _norm(path: str) -> str:
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = _norm(item)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _superseded_by(plan: Plan, index: int, statuses: dict[str, TaskStatus]) -> Optional[str]:
    """Id of the last LATER passed task whose write_set holds every path of this task's write_set."""
    task = plan.tasks[index]
    mine = {_norm(p) for p in task.write_set}
    if not mine:
        return None
    found: Optional[str] = None
    for later in plan.tasks[index + 1:]:
        if TaskStatus(statuses.get(later.id, TaskStatus.queued)) != TaskStatus.passed:
            continue
        if mine <= {_norm(p) for p in later.write_set}:
            found = later.id
    return found


def build_report(
    plan: Plan,
    statuses: dict[str, TaskStatus],
    attempts: dict[str, list[AttemptRecord]],
    integration: list[CheckResult],
    changed: list[str],
    line_stats: tuple[int, int] = (0, 0),
    final_checks: Optional[list[CheckResult]] = None,
    files: Optional[dict[str, str]] = None,
) -> WorkReport:
    """Summarise one run. Tasks follow plan order; the last attempt supplies the failure details."""
    rows: list[WorkReportTask] = []
    counts = WorkSummary()
    file_map: dict[str, str] = dict(files or {})
    written = {_norm(p) for p in changed} | {_norm(p) for p in file_map}
    changed_norm = {_norm(p) for p in changed}
    added_paths: set[str] = set()
    kind_by_task: dict[str, str] = {t.id: t.kind for t in plan.tasks}

    for idx, task in enumerate(plan.tasks):
        status = TaskStatus(statuses.get(task.id, TaskStatus.queued))
        recs = attempts.get(task.id, [])
        last: Optional[AttemptRecord] = recs[-1] if recs else None

        sup: Optional[str] = None
        if status != TaskStatus.passed:
            sup = _superseded_by(plan, idx, statuses)

        if status == TaskStatus.passed:
            counts.passed += 1
        elif sup is not None:
            counts.superseded += 1
        elif status == TaskStatus.failed:
            counts.failed += 1
        elif status == TaskStatus.blocked:
            counts.blocked += 1
        elif status == TaskStatus.skipped:
            counts.skipped += 1

        if kind_by_task.get(task.id) == "create_file":
            for p in task.write_set:
                if _norm(p) in changed_norm:
                    added_paths.add(_norm(p))

        rows.append(WorkReportTask(
            id=task.id,
            title=task.title,
            status=status,
            attempts=len(recs),
            model=last.model_id if last else None,
            failing_check=last.failing_check if last else None,
            error_tail=last.error_tail if last else "",
            files_changed=list(last.files_changed) if last else [],
            superseded_by=sup,
        ))

    # Work that is missing: a failed or blocked task whose files no passed task wrote.
    done: set[str] = set()
    for task in plan.tasks:
        if TaskStatus(statuses.get(task.id, TaskStatus.queued)) == TaskStatus.passed:
            done |= {_norm(p) for p in task.write_set}
    for task, row in zip(plan.tasks, rows):
        if row.status in (TaskStatus.failed, TaskStatus.blocked) and row.superseded_by is None:
            mine = {_norm(p) for p in task.write_set}
            if not mine or not mine <= done:
                counts.unfinished += 1

    unique_changed = _unique(changed)
    files_added = sum(1 for p in unique_changed if _norm(p) in added_paths)
    diff = DiffStats(
        files_added=files_added,
        files_changed=len(unique_changed) - files_added,
        lines_added=int(line_stats[0]),
        lines_removed=int(line_stats[1]),
    )

    deviations: list[str] = []
    for deliv in plan.deliverables:
        for path in deliv.paths:
            if _norm(path) not in written:
                deviations.append(f"{deliv.id}: {path} not written")

    return WorkReport(
        summary=counts,
        tasks=rows,
        integration=list(integration),
        diff_stats=diff,
        deviations=deviations,
        final_checks=list(final_checks or []),
        files=file_map,
    )


def _check_name(c: CheckResult) -> str:
    if c.check_id:
        return c.check_id
    if c.check is not None:
        if c.check.id:
            return c.check.id
        if c.check.cmd:
            return c.check.cmd[:80]
    return "check"


def _check_lines(c: CheckResult) -> list[str]:
    name = _check_name(c)
    if c.invalid:
        return [f"- {name}: {_INVALID_LABEL}"]
    if c.ok:
        return [f"- {name}: ok"]
    lines = [f"- {name}: FAILED"]
    tail = (c.output_tail or "").strip()
    if tail:
        if len(tail) > _CHECK_CLIP:
            tail = tail[-_CHECK_CLIP:]
        lines.append(f"    output: {tail}")
    return lines


def _verdict(checks: list[CheckResult], summary: Optional[WorkSummary] = None) -> str:
    valid = [c for c in checks if not c.invalid]
    if not valid:
        return "No checks were run on the current files."
    failing = sum(1 for c in valid if not c.ok)
    if failing:
        return f"{failing} current check(s) FAIL."
    # A failed task's files are rolled back, so its own check may have nothing left to fail on.
    undone = int(getattr(summary, "unfinished", 0) or 0) if summary is not None else 0
    if undone:
        return (f"The checks that ran pass, but {undone} task(s) FAILED and were not fixed: "
                "their work is missing.")
    return "All current checks pass."


def _history_lines(report: WorkReport) -> list[str]:
    s = report.summary
    d = report.diff_stats
    lines = [
        _HISTORY_HEAD,
        f"Summary: passed={s.passed} failed={s.failed} blocked={s.blocked} "
        f"skipped={s.skipped} superseded={s.superseded}",
        f"Diff: files added={d.files_added} changed={d.files_changed} "
        f"lines +{d.lines_added} -{d.lines_removed}",
        "Tasks:",
    ]
    for t in report.tasks:
        if t.superseded_by:
            lines.append(
                f"- {t.id} [{_status_value(t.status)}, superseded by {t.superseded_by}: "
                f"its files were rewritten later] {t.title}"
            )
            continue
        head = f"- {t.id} [{_status_value(t.status)}] {t.title} (attempts={t.attempts}"
        if t.model:
            head += f", model={t.model}"
        head += ")"
        lines.append(head)
        if t.failing_check:
            lines.append(f"    failing check: {t.failing_check}")
        if t.error_tail:
            lines.append(f"    error: {t.error_tail.strip()}")
        if t.files_changed:
            lines.append(f"    files: {', '.join(t.files_changed)}")
    return lines


def _clip_files(files: dict[str, str], budget: Optional[int]) -> list[str]:
    """Lines for the 'Files now:' block. budget = total chars allowed for contents (None = no limit).

    Short files stay whole; the rest share what is left equally. Each clipped file keeps its head.
    """
    if not files:
        return []
    lengths = {p: len(c) for p, c in files.items()}
    allot: dict[str, Optional[int]] = {p: None for p in files}
    if budget is not None and sum(lengths.values()) > budget:
        left = max(0, budget)
        pending = sorted(files, key=lambda p: lengths[p])
        while pending:
            share = left // len(pending)
            p = pending[0]
            if lengths[p] <= share:
                left -= lengths[p]
                pending.pop(0)
                continue
            for q in pending:
                allot[q] = share
            break
    lines: list[str] = ["Files now:"]
    for path, content in files.items():
        lines.append(f"--- {path} ---")
        cap = allot[path]
        if cap is not None and len(content) > cap:
            keep = max(0, cap - len(_TRUNC_MARK))
            content = content[:keep] + _TRUNC_MARK
        lines.append(content)
    return lines


def report_text(report: WorkReport, max_chars: int = 14000) -> str:
    """Plain text of a report for prompts: CURRENT STATE, integration, HISTORY, deviations.

    Over max_chars: HISTORY goes first, then file contents (head of each file is kept).
    The check verdict lines are never cut, so the result can exceed a tiny max_chars.
    """
    final = list(report.final_checks)
    head: list[str] = ["CURRENT STATE (judge this)", _verdict(final, report.summary)]
    for c in final:
        head.extend(_check_lines(c))

    seen = {_check_name(c) for c in final}
    extra = [c for c in report.integration if _check_name(c) not in seen]
    integ: list[str] = []
    if extra:
        integ.append("Integration checks:")
        for c in extra:
            integ.extend(_check_lines(c))

    history = _history_lines(report)
    devs: list[str] = []
    if report.deviations:
        devs.append("Deviations:")
        devs.extend(f"- {dev}" for dev in report.deviations)

    def join(files_lines: list[str], hist: list[str]) -> str:
        return "\n".join(head + files_lines + integ + hist + devs)

    full_files = _clip_files(report.files, None)
    text = join(full_files, history)
    if max_chars is None or len(text) <= max_chars:
        return text

    # 1. cut HISTORY first.
    stub = [_HISTORY_HEAD + _TRUNC_MARK]
    without_hist = join(full_files, [])
    room = max_chars - len(without_hist) - 1  # 1 for the joining newline
    if room >= len(_HISTORY_HEAD) + len(_TRUNC_MARK) + 20:
        keep = room - len(_TRUNC_MARK)
        return join(full_files, ["\n".join(history)[:keep] + _TRUNC_MARK])
    text = join(full_files, stub)
    if len(text) <= max_chars:
        return text

    # 2. cut file contents. Budget = what is left after everything but the contents.
    shell_len = len(join(_clip_files({p: "" for p in report.files}, None), stub))
    budget = max_chars - shell_len
    clipped = _clip_files(report.files, budget)
    return join(clipped, stub)


def _status_value(status: object) -> str:
    return status.value if isinstance(status, TaskStatus) else str(status)
