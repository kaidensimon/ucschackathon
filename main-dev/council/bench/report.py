"""Bench report (ARCHITECTURE 18.7): summary rows, markdown table, council vs best, agreement curve."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from council.core.schemas import BenchResult, BenchSummaryRow, BenchTask

_DIFFICULTIES = ("easy", "medium", "hard")


def _is_council(mode: str) -> bool:
    return mode == "council" or mode.startswith("council")


def _is_solo(mode: str) -> bool:
    return mode.startswith("solo")


def _acc(items: list[BenchResult]) -> float:
    if not items:
        return 0.0
    return sum(1 for r in items if r.correct is True) / len(items)


def summarize(results: list[BenchResult], tasks: list[BenchTask]) -> list[BenchSummaryRow]:
    """One row per mode, in first-seen order. Ungraded results count as wrong."""
    by_id = {t.id: t for t in tasks}
    groups: dict[str, list[BenchResult]] = {}
    for r in results:
        groups.setdefault(r.mode, []).append(r)
    rows: list[BenchSummaryRow] = []
    for mode, items in groups.items():
        diff: dict[str, list[BenchResult]] = {}
        cat: dict[str, list[BenchResult]] = {}
        for r in items:
            t = by_id.get(r.id)
            if t is None:
                continue
            diff.setdefault(t.difficulty, []).append(r)
            cat.setdefault(t.category, []).append(r)
        n = len(items)
        rows.append(
            BenchSummaryRow(
                mode=mode,
                n=n,
                accuracy=_acc(items),
                by_difficulty={k: _acc(v) for k, v in sorted(diff.items())},
                by_category={k: _acc(v) for k, v in sorted(cat.items())},
                mean_tokens=sum(r.tokens_in + r.tokens_out + r.tokens_reasoning for r in items) / n,
                mean_wall_ms=sum(r.wall_ms for r in items) / n,
            )
        )
    return rows


def _pct(x: Optional[float]) -> str:
    return "-" if x is None else f"{x * 100:.1f}%"


def to_markdown(rows: list[BenchSummaryRow]) -> str:
    diffs = [d for d in _DIFFICULTIES if any(d in r.by_difficulty for r in rows)]
    cats = sorted({c for r in rows for c in r.by_category})
    head = ["mode", "n", "accuracy"] + diffs + cats + ["mean tokens", "mean ms"]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for r in rows:
        cells = [r.mode, str(r.n), _pct(r.accuracy)]
        cells += [_pct(r.by_difficulty.get(d)) for d in diffs]
        cells += [_pct(r.by_category.get(c)) for c in cats]
        cells += [f"{r.mean_tokens:.0f}", f"{r.mean_wall_ms:.0f}"]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def council_vs_best(rows: list[BenchSummaryRow]) -> dict[str, Any]:
    """Best solo mode vs best council mode. Delta is council minus best solo."""
    solos = [r for r in rows if _is_solo(r.mode)]
    councils = [r for r in rows if _is_council(r.mode)]
    out: dict[str, Any] = {
        "best_solo": None,
        "council": None,
        "best_solo_accuracy": None,
        "council_accuracy": None,
        "delta_overall": None,
        "delta_by_difficulty": {},
    }
    if solos:
        best = max(solos, key=lambda r: r.accuracy)
        out["best_solo"] = best.mode
        out["best_solo_accuracy"] = best.accuracy
    if councils:
        c = max(councils, key=lambda r: r.accuracy)
        out["council"] = c.mode
        out["council_accuracy"] = c.accuracy
    if solos and councils:
        best = max(solos, key=lambda r: r.accuracy)
        c = max(councils, key=lambda r: r.accuracy)
        out["delta_overall"] = c.accuracy - best.accuracy
        out["delta_by_difficulty"] = {
            d: c.by_difficulty[d] - best.by_difficulty[d]
            for d in sorted(set(c.by_difficulty) & set(best.by_difficulty))
        }
    return out


def agreement_curve(results: list[BenchResult], buckets: int = 5) -> list[tuple[float, float, int]]:
    """For council results with an agreement value: (bucket midpoint, accuracy, count). Empty buckets skipped."""
    if buckets < 1:
        buckets = 1
    hits = [0] * buckets
    counts = [0] * buckets
    for r in results:
        if not _is_council(r.mode) or r.agreement is None:
            continue
        a = min(max(r.agreement, 0.0), 1.0)
        i = min(int(a * buckets), buckets - 1)
        counts[i] += 1
        if r.correct is True:
            hits[i] += 1
    return [((i + 0.5) / buckets, hits[i] / counts[i], counts[i]) for i in range(buckets) if counts[i]]


def write_report(dir: Path, rows: list[BenchSummaryRow], extra: dict) -> None:
    """Write report.md and report.json into dir."""
    dir = Path(dir)
    dir.mkdir(parents=True, exist_ok=True)
    extra = dict(extra or {})
    cvb = council_vs_best(rows)
    md = ["# Bench report", "", to_markdown(rows)]
    if cvb["best_solo"] and cvb["council"]:
        md.append(f"Council ({cvb['council']}) vs best solo ({cvb['best_solo']}): {cvb['delta_overall'] * 100:+.1f} points overall.")
        md.append("")
    curve = extra.get("agreement_curve")
    if curve:
        md += ["| agreement | accuracy | n |", "|---|---|---|"]
        md += [f"| {a:.2f} | {_pct(acc)} | {n} |" for a, acc, n in curve]
        md.append("")
    (dir / "report.md").write_text("\n".join(md), encoding="utf-8")
    payload = {
        "rows": [r.model_dump() for r in rows],
        "council_vs_best": cvb,
        "extra": extra,
    }
    (dir / "report.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
