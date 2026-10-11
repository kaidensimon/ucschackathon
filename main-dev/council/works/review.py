"""Review vote helpers (spec 14.2).

Build the review call, tally ballots, merge fix lists, turn fixes into micro-tasks.
"""

from __future__ import annotations

import random
import re
from typing import Optional

from council.core.schemas import (
    CallSpec,
    Check,
    MicroTask,
    Plan,
    ReviewBallot,
    ReviewFix,
    SeatAssignment,
)
from council.chamber.prompts import render

_VERDICTS = ("accept", "fix", "replan", "ask_user")


def _letter(i: int) -> str:
    return chr(ord("A") + i) if i < 26 else f"R{i + 1}"


def _meta(seat: SeatAssignment, rnd: str) -> dict:
    return {"seat_no": seat.seat_no, "round": rnd, "lens": seat.lens}


def build_review_call(
    run_id: str,
    seat: SeatAssignment,
    report_text: str,
    plan_goal: str,
    cycle: int,
) -> CallSpec:
    return CallSpec(
        model_id=seat.model_id,
        call_id=f"{run_id}:rv{cycle}:{seat.seat_no}",
        run_id=run_id,
        purpose="review",
        messages=[
            {"role": "system", "content": render("review_system")},
            {"role": "user", "content": render("review", goal=plan_goal, cycle=cycle, work_report=report_text)},
        ],
        json_schema=ReviewBallot.model_json_schema(),
        reasoning="off",
        max_output_tokens=900,
        priority="interactive",
        meta=_meta(seat, f"rv{cycle}"),
    )


def _compact(b: ReviewBallot, reviewer: Optional[str] = None) -> dict:
    d: dict = {}
    if reviewer is not None:
        d["reviewer"] = reviewer
    d["verdict"] = b.verdict
    d["reason"] = b.reason
    d["fixes"] = [fx.problem for fx in b.fixes] if reviewer is not None else [
        {"task_id": fx.task_id, "problem": fx.problem, "proposed_change": fx.proposed_change}
        for fx in b.fixes
    ]
    return d


def build_rebuttal_call(
    run_id: str,
    seat: SeatAssignment,
    report_text: str,
    plan_goal: str,
    cycle: int,
    own: Optional[ReviewBallot],
    others: list[ReviewBallot],
) -> CallSpec:
    """Argument round: the seat sees its own first vote and the others' votes, lettered, no names."""
    own_ballot = _compact(own) if own is not None else "none"
    other_ballots = [_compact(b, _letter(i)) for i, b in enumerate(others)]
    user = render(
        "review_rebuttal",
        goal=plan_goal,
        work_report=report_text,
        own_ballot=own_ballot,
        other_ballots=other_ballots,
    )
    return CallSpec(
        model_id=seat.model_id,
        call_id=f"{run_id}:rvd{cycle}:{seat.seat_no}",
        run_id=run_id,
        purpose="review",
        messages=[
            {"role": "system", "content": render("review_system")},
            {"role": "user", "content": user},
        ],
        json_schema=ReviewBallot.model_json_schema(),
        reasoning="off",
        max_output_tokens=900,
        priority="interactive",
        meta=_meta(seat, f"rvd{cycle}"),
    )


def needs_debate(ballots, threshold: float = 0.8) -> bool:
    """True when at least 2 valid ballots and no single verdict holds >= threshold of them."""
    items = ballots.values() if isinstance(ballots, dict) else ballots
    valid = [b.verdict for b in items if b is not None]
    if len(valid) < 2:
        return False
    top = max(valid.count(v) for v in set(valid))
    return top / len(valid) < threshold


def pick_decider(seats: list[SeatAssignment], seed: int, cycle: int) -> SeatAssignment:
    """Deterministic random pick of the seat that casts the deciding vote."""
    if not seats:
        raise ValueError("no seats to pick a decider from")
    ordered = sorted(seats, key=lambda s: s.seat_no)
    return random.Random(f"{seed}:{cycle}").choice(ordered)


def build_final_call(
    run_id: str,
    seat: SeatAssignment,
    report_text: str,
    plan_goal: str,
    cycle: int,
    history: list[dict],
) -> CallSpec:
    user = render("review_final", goal=plan_goal, work_report=report_text, record=history)
    return CallSpec(
        model_id=seat.model_id,
        call_id=f"{run_id}:rvf{cycle}:{seat.seat_no}",
        run_id=run_id,
        purpose="review",
        messages=[
            {"role": "system", "content": render("review_system")},
            {"role": "user", "content": user},
        ],
        json_schema=ReviewBallot.model_json_schema(),
        reasoning="off",
        max_output_tokens=600,
        priority="interactive",
        meta=_meta(seat, f"rvf{cycle}"),
    )


def final_verdict(ballot: Optional[ReviewBallot]) -> bool:
    """True = accept. A failed call (None) must not discard finished work."""
    return ballot is None or ballot.verdict == "accept"


def ballot_record(
    ballots: dict[int, Optional[ReviewBallot]],
    cycle: int,
    counts: dict[str, int],
) -> dict:
    """One history item for the final-say prompt. Letters by sorted seat_no; failed ballots skipped."""
    rows = []
    for seat_no in sorted(ballots):
        b = ballots[seat_no]
        if b is None:
            continue
        rows.append({"reviewer": _letter(len(rows)), "verdict": b.verdict, "reason": b.reason})
    return {"cycle": cycle, "tally": dict(counts), "ballots": rows}


def decide_review(
    ballots: dict[int, Optional[ReviewBallot]],
    threshold: float = 0.80,
) -> tuple[str, dict[str, int]]:
    """Return (decision, counts). Decision: accept, fix, replan or ask_user."""
    counts = {v: 0 for v in _VERDICTS}
    for b in ballots.values():
        if b is not None and b.verdict in counts:
            counts[b.verdict] += 1
    valid = sum(counts.values())
    if valid == 0:
        return "ask_user", counts
    if counts["accept"] / valid >= threshold:
        return "accept", counts
    if (counts["fix"] + counts["accept"]) * 2 > valid:
        return "fix", counts
    if counts["replan"] * 2 > valid:
        return "replan", counts
    return "ask_user", counts


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def merge_fixes(ballots: dict[int, Optional[ReviewBallot]]) -> list[ReviewFix]:
    """All fixes from all valid ballots, de-duplicated by (task_id, normalized problem)."""
    seen: set[tuple[Optional[str], str]] = set()
    out: list[ReviewFix] = []
    for seat_no in sorted(ballots):
        b = ballots[seat_no]
        if b is None:
            continue
        for fx in b.fixes:
            key = (fx.task_id, _norm(fx.problem))
            if key in seen:
                continue
            seen.add(key)
            out.append(fx)
    return out


def fixes_to_tasks(
    fixes: list[ReviewFix], plan: Plan, cycle: int, test_cmd: Optional[str] = None
) -> list[MicroTask]:
    """One revise task per file, ids fix<cycle>_<n>, each carrying every problem that touches it.

    Workers write whole files. A task per problem would have several workers rewriting the same
    file at once, each undoing the others, and a problem tied to no task would have nowhere to
    write at all. So the problems are gathered per file: those raised against a task that writes
    the file, plus every problem raised against no particular task.
    """
    if not fixes:
        return []
    by_id = {t.id: t for t in plan.tasks}
    files: list[str] = list(dict.fromkeys(p for t in plan.tasks for p in t.write_set))
    if not files:
        files = list(dict.fromkeys(p for d in plan.deliverables for p in d.paths))
    general: list[str] = []
    per_file: dict[str, list[str]] = {f: [] for f in files}
    for fx in fixes:
        text = fx.problem if not fx.proposed_change else f"{fx.problem} Change: {fx.proposed_change}"
        orig = by_id.get(fx.task_id) if fx.task_id else None
        targets = [p for p in (orig.write_set if orig is not None else []) if p in per_file]
        if targets:
            for p in targets:
                per_file[p].append(text)
        else:
            general.append(text)

    def is_test(path: str) -> bool:
        return "test" in path.lower()

    tasks: list[MicroTask] = []
    code_ids: list[str] = []
    ordered = [f for f in files if not is_test(f)] + [f for f in files if is_test(f)]
    for path in ordered:
        problems = list(dict.fromkeys(per_file[path] + general))
        if not problems:
            continue
        tid = f"fix{cycle}_{len(tasks) + 1}"
        checks = [Check(type="exists", path=path)]
        if path.endswith(".py"):
            checks.append(Check(type="parses", path=path, language="python"))
        tasks.append(
            MicroTask(
                id=tid,
                title=f"Revise {path}",
                kind="edit_file",
                goal=(f"Rewrite {path} completely so that it is correct and complete for the overall goal: "
                      f"{plan.goal} Problems the reviewers found (fix those that concern this file): "
                      + " | ".join(problems)),
                read_set=list(files),
                write_set=[path],
                output_contract=f"{path} is complete, correct and consistent with the other files.",
                acceptance=checks,
                deps=list(code_ids) if is_test(path) else [],
                tier="senior",
            )
        )
        if not is_test(path):
            code_ids.append(tid)
    if test_cmd:
        for t in tasks:
            if is_test(t.write_set[0]) or t is tasks[-1]:
                t.acceptance.append(Check(type="command", cmd=test_cmd, timeout_s=120))
    return tasks
