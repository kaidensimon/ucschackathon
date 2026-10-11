"""Council against its own members. Pure: no I/O, no clock, no randomness.

The headline number: does the council beat the best solo model, the average
solo model, and a plain majority vote of the same models?
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Optional

from council.core.schemas_v15 import CompareReport, CompareRow, SoloScore

MIN_TASKS = 30
FEW_TASKS_NOTE = "too few tasks to call a difference real"
OTHER_CATEGORY = "other"


def _norm(answer: str) -> str:
    return " ".join(answer.strip().lower().split())


def _acc(flags: list[bool]) -> float:
    return sum(flags) / len(flags) if flags else 0.0


def _by_cat(task_ids: list[str], flags: dict[str, bool],
            categories: Optional[dict[str, str]]) -> dict[str, float]:
    if not categories:
        return {}
    groups: dict[str, list[bool]] = {}
    for t in task_ids:
        groups.setdefault(categories.get(t) or OTHER_CATEGORY, []).append(flags[t])
    return {c: _acc(v) for c, v in sorted(groups.items())}


def _vote_correct(task: str, voters: list[str], table: dict[str, dict[str, SoloScore]],
                  ranked: list[str]) -> bool:
    """One task, one majority vote. `ranked` = voters best first (tie-break order)."""
    rows = [table[m][task] for m in voters]
    if all(r.answer and r.answer.strip() for r in rows):
        counts = Counter(_norm(r.answer) for r in rows)
        top = max(counts.values())
        tied = {a for a, c in counts.items() if c == top}
        if len(tied) == 1:
            winner = next(iter(tied))
        else:
            winner = next(_norm(table[m][task].answer) for m in ranked
                          if _norm(table[m][task].answer) in tied)
        return any(_norm(r.answer) == winner and r.correct for r in rows)
    n_right = sum(1 for r in rows if r.correct)
    if 2 * n_right == len(rows):
        return bool(table[ranked[0]][task].correct)
    return 2 * n_right > len(rows)


def compare(solo: list[SoloScore], council: dict[str, bool],
            categories: Optional[dict[str, str]] = None,
            seat_models: Optional[list[str]] = None,
            latency: Optional[dict[str, float]] = None) -> CompareReport:
    latency = latency or {}
    table: dict[str, dict[str, SoloScore]] = {}
    for s in solo:
        table.setdefault(s.model_id, {})[s.task_id] = s
    models = sorted(table)
    notes: list[str] = []

    if not models:
        notes.append("no solo scores")
        return CompareReport(n_tasks=0, notes=notes + [FEW_TASKS_NOTE])

    answered_by_all: set[str] = set(council)
    seen_any: set[str] = set(council)
    for m in models:
        ok = {t for t, s in table[m].items() if s.correct is not None}
        answered_by_all &= ok
        seen_any |= set(table[m])
    tasks = sorted(answered_by_all)
    dropped = len(seen_any) - len(tasks)
    if dropped:
        notes.append(f"{dropped} task(s) dropped: not answered by the council and every solo model")

    flags = {m: {t: bool(table[m][t].correct) for t in tasks} for m in models}
    solo_acc = {m: _acc([flags[m][t] for t in tasks]) for m in models}
    ranked_all = sorted(models, key=lambda m: (-solo_acc[m], m))
    best = ranked_all[0]

    voters = [m for m in (seat_models or []) if m in table] or models
    voters = list(dict.fromkeys(voters))
    ranked_voters = [m for m in ranked_all if m in voters]

    vote = {t: _vote_correct(t, voters, table, ranked_voters) for t in tasks}
    oracle = {t: any(flags[m][t] for m in models) for t in tasks}
    council_f = {t: bool(council[t]) for t in tasks}

    def lat(name: str) -> Optional[float]:
        if name in latency:
            return latency[name]
        vals = [table[name][t].latency_s for t in tasks
                if name in table and table[name][t].latency_s is not None]
        return sum(vals) / len(vals) if vals else None

    rows: list[CompareRow] = []
    for m in models:
        rows.append(CompareRow(name=m, kind="solo", n=len(tasks), accuracy=solo_acc[m],
                               by_category=_by_cat(tasks, flags[m], categories),
                               mean_latency_s=lat(m)))
    mean_solo = sum(solo_acc.values()) / len(models)
    cat_maps = [_by_cat(tasks, flags[m], categories) for m in models]
    mean_cat = {c: sum(cm[c] for cm in cat_maps) / len(cat_maps)
                for c in (cat_maps[0] if cat_maps else {})}
    rows.append(CompareRow(name="mean_solo", kind="baseline", n=len(tasks), accuracy=mean_solo,
                           by_category=mean_cat, mean_latency_s=latency.get("mean_solo")))
    rows.append(CompareRow(name="majority_vote", kind="baseline", n=len(tasks),
                           accuracy=_acc(list(vote.values())),
                           by_category=_by_cat(tasks, vote, categories),
                           mean_latency_s=latency.get("majority_vote")))
    rows.append(CompareRow(name="oracle", kind="baseline", n=len(tasks),
                           accuracy=_acc(list(oracle.values())),
                           by_category=_by_cat(tasks, oracle, categories),
                           mean_latency_s=latency.get("oracle")))
    c_acc = _acc(list(council_f.values()))
    rows.append(CompareRow(name="council", kind="council", n=len(tasks), accuracy=c_acc,
                           by_category=_by_cat(tasks, council_f, categories),
                           mean_latency_s=latency.get("council")))

    if len(tasks) < MIN_TASKS:
        notes.append(FEW_TASKS_NOTE)

    have = bool(tasks)
    only_right = [t for t in tasks if council_f[t] and not any(flags[m][t] for m in models)]
    only_wrong = [t for t in tasks if not council_f[t] and flags[best][t]]
    vote_acc = rows[-3].accuracy
    return CompareReport(
        rows=rows, n_tasks=len(tasks), best_solo=best,
        council_minus_best=(c_acc - solo_acc[best]) if have else None,
        council_minus_mean=(c_acc - mean_solo) if have else None,
        council_minus_vote=(c_acc - vote_acc) if have else None,
        council_only_right=only_right, council_only_wrong=only_wrong, notes=notes,
    )


def sign_test(council: dict[str, bool], other: dict[str, bool]) -> dict:
    """Paired sign test on the tasks both answered. Two-sided exact binomial, p0 = 0.5."""
    wins = losses = ties = 0
    for t in set(council) & set(other):
        a, b = bool(council[t]), bool(other[t])
        if a and not b:
            wins += 1
        elif b and not a:
            losses += 1
        else:
            ties += 1
    n = wins + losses
    if n == 0:
        p = 1.0
    else:
        k = min(wins, losses)
        p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return {"wins": wins, "losses": losses, "ties": ties, "n": n, "p": p, "p_value": p}
