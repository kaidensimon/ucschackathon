"""Foreman plan lint (spec 11.3, 11.4 step 2). Pure code, no model calls."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Optional

from council.core.schemas import MicroTask, Plan


@dataclass
class LintIssue:
    code: str
    task_id: Optional[str]
    message: str


_ID_OK = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,63}\Z")
_RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {
    f"lpt{i}" for i in range(1, 10)}


def valid_task_id(task_id: str) -> bool:
    """A task id becomes a folder name (runs/<id>/preimage/<task id>): letters, digits, . _ -
    only, no leading dot or dash, no "..", at most 64 characters, no Windows device name."""
    if not isinstance(task_id, str) or not _ID_OK.match(task_id):
        return False
    if task_id.endswith(".") or ".." in task_id:
        return False
    return task_id.split(".")[0].lower() not in _RESERVED


def _dep_map(tasks: list[MicroTask]) -> dict[str, list[str]]:
    """id -> known deps (unknown deps dropped, first task wins on duplicate ids)."""
    ids = {t.id for t in tasks}
    out: dict[str, list[str]] = {}
    for t in tasks:
        if t.id in out:
            continue
        out[t.id] = [d for d in t.deps if d in ids]
    return out


def topo_order(tasks: list[MicroTask]) -> list[str]:
    """Task ids, deps first, stable by input order. Raises ValueError on a cycle."""
    deps = _dep_map(tasks)
    indeg = {i: len(set(ds)) for i, ds in deps.items()}
    children: dict[str, list[str]] = {i: [] for i in deps}
    for i, ds in deps.items():
        for d in set(ds):
            children[d].append(i)
    order: list[str] = []
    ready = [i for i in deps if indeg[i] == 0]
    while ready:
        cur = ready.pop(0)
        order.append(cur)
        for c in children[cur]:
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
    if len(order) != len(deps):
        stuck = [i for i in deps if i not in set(order)]
        raise ValueError("dependency cycle among tasks: " + ", ".join(stuck))
    return order


def reachable(tasks: list[MicroTask]) -> dict[str, set[str]]:
    """id -> set of ids it depends on, directly or through other deps. Safe on cycles."""
    deps = _dep_map(tasks)
    result: dict[str, set[str]] = {}
    for start in deps:
        seen: set[str] = set()
        stack = list(deps[start])
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(deps.get(cur, []))
        result[start] = seen
    return result


def _norm(path: str) -> str:
    return posixpath.normpath(path.replace("\\", "/"))


def _escapes(path: str, workspace: Path) -> bool:
    if not path:
        return False
    if PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute():
        return True
    if path.startswith(("/", "\\")):
        return True
    n = _norm(path)
    if n == ".." or n.startswith("../"):
        return True
    try:
        (Path(workspace) / n).resolve().relative_to(Path(workspace).resolve())
    except ValueError:
        return True
    return False


def _input_chars(t: MicroTask) -> int:
    n = len(t.goal) + len(t.output_contract) + len(t.context.notes)
    n += sum(len(f.content) for f in t.context.files)
    n += sum(len(i.definition) + len(i.name) for i in t.context.interfaces)
    return n


def lint_plan(
    plan: Plan,
    workspace: Path,
    max_in_tokens: int = 4000,
    max_out_tokens: int = 1500,
    max_files: int = 2,
) -> list[LintIssue]:
    issues: list[LintIssue] = []
    tasks = plan.tasks

    seen: set[str] = set()
    dup_reported: set[str] = set()
    bad_reported: set[str] = set()
    for t in tasks:
        if not valid_task_id(t.id) and t.id not in bad_reported:
            bad_reported.add(t.id)
            issues.append(LintIssue(
                "bad_id", t.id,
                f"task id {t.id!r} is not a plain name (letters, digits, '.', '_', '-'; max 64)"))
        if t.id in seen and t.id not in dup_reported:
            dup_reported.add(t.id)
            issues.append(LintIssue("duplicate_id", t.id, f"task id '{t.id}' used more than once"))
        seen.add(t.id)

    ids = {t.id for t in tasks}
    for t in tasks:
        for d in t.deps:
            if d not in ids:
                issues.append(LintIssue("unknown_dep", t.id, f"task '{t.id}' depends on unknown task '{d}'"))

    try:
        topo_order(tasks)
    except ValueError as e:
        issues.append(LintIssue("cycle", None, str(e)))

    reach = reachable(tasks)
    for i, a in enumerate(tasks):
        wa = {_norm(p) for p in a.write_set}
        for b in tasks[i + 1:]:
            if a.id == b.id:
                continue
            common = wa & {_norm(p) for p in b.write_set}
            if not common:
                continue
            if b.id in reach.get(a.id, set()) or a.id in reach.get(b.id, set()):
                continue
            issues.append(LintIssue(
                "write_overlap", a.id,
                f"tasks '{a.id}' and '{b.id}' both write {sorted(common)} with no dep order",
            ))

    iface_names = {i.name for i in plan.interfaces}
    for t in tasks:
        if not t.acceptance:
            issues.append(LintIssue("no_acceptance", t.id, f"task '{t.id}' has no acceptance check"))
        for p in list(t.read_set) + list(t.write_set):
            if _escapes(p, Path(workspace)):
                issues.append(LintIssue("path_escape", t.id, f"path '{p}' leaves the workspace"))
        if len(t.write_set) > max_files:
            issues.append(LintIssue(
                "too_many_files", t.id, f"task '{t.id}' writes {len(t.write_set)} files, max {max_files}"))
        est = _input_chars(t) // 4
        if est > max_in_tokens:
            issues.append(LintIssue(
                "input_too_large", t.id, f"task '{t.id}' input about {est} tokens, max {max_in_tokens}"))
        if t.budget.max_output_tokens > max_out_tokens:
            issues.append(LintIssue(
                "output_cap_too_large", t.id,
                f"task '{t.id}' output cap {t.budget.max_output_tokens}, max {max_out_tokens}"))
        for i in t.context.interfaces:
            if i.name not in iface_names:
                issues.append(LintIssue(
                    "interface_undefined", t.id, f"task '{t.id}' uses undefined interface '{i.name}'"))

    written = {_norm(p) for t in tasks for p in t.write_set}
    for d in plan.deliverables:
        for p in d.paths:
            if _norm(p) not in written:
                issues.append(LintIssue(
                    "deliverable_uncovered", None, f"deliverable '{d.id}' path '{p}' is written by no task"))

    return issues
