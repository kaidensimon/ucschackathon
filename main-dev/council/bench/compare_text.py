"""Render a CompareReport as text.

Three views: a fixed-width terminal table, the same content as a GitHub-style
markdown table, and a per-category accuracy table. Pure: no I/O, no clock, no
randomness. Output is ASCII only.
"""

from __future__ import annotations

from typing import Optional, Sequence

from council.core.schemas_v15 import CompareReport, CompareRow

MISSING = "-"
COUNCIL_MARK = "<<"
HEADERS = ["system", "kind", "n", "accuracy %", "latency"]
# "l" = left aligned, "r" = right aligned. One entry per header.
ALIGN = ["l", "l", "r", "r", "r"]


def _ascii(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def _sorted_rows(report: CompareReport) -> list[CompareRow]:
    return sorted(report.rows, key=lambda r: (-r.accuracy, r.name))


def _system_cell(row: CompareRow) -> str:
    if row.kind == "council":
        return f"{row.name} {COUNCIL_MARK}"
    return row.name


def _pct(value: float) -> str:
    return f"{value * 100:.1f}"


def _latency(value: Optional[float]) -> str:
    return MISSING if value is None else f"{value:.2f}s"


def _points(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    points = round(value * 100, 1) + 0.0  # + 0.0 turns -0.0 into 0.0
    return f"{points:+.1f} points"


def _summary_lines(report: CompareReport) -> list[str]:
    best = report.best_solo or "none"
    lines = [
        f"council vs best solo ({best}): {_points(report.council_minus_best)}",
        f"council vs mean solo: {_points(report.council_minus_mean)}",
        f"council vs plain majority vote: {_points(report.council_minus_vote)}",
        f"council only right: {len(report.council_only_right)}",
        f"council only wrong: {len(report.council_only_wrong)}",
    ]
    lines.extend(f"note: {note}" for note in report.notes)
    return lines


def _grid(header: Sequence[str], body: list[list[str]], align: Sequence[str]) -> list[str]:
    """Fixed-width text grid: header, dash rule, body rows."""
    widths = [
        max([len(header[i])] + [len(row[i]) for row in body])
        for i in range(len(header))
    ]

    def fmt(cells: Sequence[str]) -> str:
        parts = []
        for cell, width, how in zip(cells, widths, align):
            parts.append(cell.rjust(width) if how == "r" else cell.ljust(width))
        return "  ".join(parts).rstrip()

    rule = "  ".join("-" * w for w in widths)
    return [fmt(header), rule] + [fmt(row) for row in body]


def table(report: CompareReport) -> str:
    """Terminal table sorted by accuracy desc, then the summary lines."""
    body = [
        [
            _system_cell(row),
            row.kind,
            str(row.n),
            _pct(row.accuracy),
            _latency(row.mean_latency_s),
        ]
        for row in _sorted_rows(report)
    ]
    lines = _grid(HEADERS, body, ALIGN)
    lines.append("")
    lines.extend(_summary_lines(report))
    return _ascii("\n".join(lines))


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def markdown(report: CompareReport) -> str:
    """Same content as table(): a GitHub-style table, then the summary as bullets."""
    lines = [
        "| " + " | ".join(HEADERS) + " |",
        "| " + " | ".join("---:" if how == "r" else "---" for how in ALIGN) + " |",
    ]
    for row in _sorted_rows(report):
        cells = [
            _system_cell(row),
            row.kind,
            str(row.n),
            _pct(row.accuracy),
            _latency(row.mean_latency_s),
        ]
        lines.append("| " + " | ".join(_md_cell(c) for c in cells) + " |")
    lines.append("")
    lines.extend(f"- {line}" for line in _summary_lines(report))
    return _ascii("\n".join(lines))


def by_category_table(report: CompareReport) -> str:
    """Rows = systems, columns = categories. Returns "" when no row has by_category."""
    rows = _sorted_rows(report)
    if not any(row.by_category for row in rows):
        return ""
    categories = sorted({c for row in rows for c in row.by_category})
    header = ["system"] + [c or "(none)" for c in categories]
    body = []
    for row in rows:
        cells = [_system_cell(row)]
        for c in categories:
            cells.append(_pct(row.by_category[c]) if c in row.by_category else MISSING)
        body.append(cells)
    align = ["l"] + ["r"] * len(categories)
    return _ascii("\n".join(_grid(header, body, align)))


__all__ = ["table", "markdown", "by_category_table"]
