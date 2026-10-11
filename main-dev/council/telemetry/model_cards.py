"""Model cards for the UI model page. Pure: all inputs are passed in."""

from __future__ import annotations

import math
from typing import Any, Optional

from council.core.schemas import ModelEntry
from council.core.schemas_v15 import MeasuredModel, ProbeCard


def _num(value: Any) -> Optional[float]:
    """Finite float or None. Keeps the card JSON-safe (no NaN, no inf)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return round(out, 3)


def _count(value: Any) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return 0
    return max(out, 0)


def _first(*values: Any) -> Optional[float]:
    for v in values:
        n = _num(v)
        if n is not None:
            return n
    return None


def _json_ok(m: Optional[MeasuredModel], entry: ModelEntry) -> Optional[bool]:
    if m is not None and m.json_ok is not None:
        return bool(m.json_ok)
    rate = _num(entry.measured.structured_valid_rate)
    if rate is not None:
        return rate >= 0.9
    return None


def _best_probes(probe_cards: Optional[list[ProbeCard]]) -> dict[str, ProbeCard]:
    """Newest version per model wins; on a tie an active card wins."""
    best: dict[str, ProbeCard] = {}
    for pc in probe_cards or []:
        cur = best.get(pc.model_id)
        if cur is None or (pc.version, pc.active) > (cur.version, cur.active):
            best[pc.model_id] = pc
    return best


def build_cards(
    registry: list[ModelEntry],
    measured: Optional[dict[str, MeasuredModel]] = None,
    stats: Optional[dict[str, dict]] = None,
    probe_cards: Optional[list[ProbeCard]] = None,
    resident: Optional[set[str]] = None,
) -> list[dict]:
    measured = measured or {}
    stats = stats or {}
    resident = resident or set()
    probes = _best_probes(probe_cards)

    cards: list[dict] = []
    for entry in registry:
        m = measured.get(entry.id)
        st = stats.get(entry.id) or {}
        runs = _count(st.get("runs"))
        wins = _count(st.get("on_winning_side"))
        pc = probes.get(entry.id)
        cards.append(
            {
                "id": entry.id,
                "display": entry.display or entry.id,
                "lab": entry.lab,
                "lineage": entry.lineage,
                "params_b": _num(entry.params_b),
                "quant": entry.quant,
                "roles": [str(r) for r in entry.roles],
                "status": str(entry.status),
                "ollama_tag": entry.ollama_tag,
                "resident": entry.id in resident,
                "memory_gib": _first(
                    m.ram_gib if m else None,
                    entry.measured.ram_gb_live,
                    entry.measured.ram_gb_batch,
                ),
                "tps": _first(m.tps if m else None, entry.measured.tps_1),
                "json_ok": _json_ok(m, entry),
                "think_ok": bool(m.think_ok) if m is not None and m.think_ok is not None else None,
                "runs": runs,
                "wins": wins,
                "chaired": _count(st.get("chaired")),
                "win_rate": round(wins / runs, 3) if runs else 0.0,
                "probe": (
                    {"active": bool(pc.active), "auroc": _num(pc.auroc), "version": int(pc.version)}
                    if pc is not None
                    else None
                ),
            }
        )
    cards.sort(key=lambda c: (not c["resident"], c["lab"], c["id"]))
    return cards


def _cell(value: Any, fmt: str = "{}") -> str:
    return "-" if value is None else fmt.format(value)


def _yn(value: Optional[bool]) -> str:
    return "-" if value is None else ("yes" if value else "no")


def cards_text(cards: list[dict]) -> str:
    """Plain terminal table, one row per card."""
    header = ["model", "lab", "params_b", "quant", "res", "mem_gib", "tps", "json", "think",
              "runs", "wins", "chair", "win%", "probe"]
    rows: list[list[str]] = []
    for c in cards:
        p = c.get("probe")
        if p is None:
            probe = "-"
        else:
            probe = ("on" if p.get("active") else "off") + _cell(p.get("auroc"), " {:.2f}")
        rows.append(
            [
                str(c.get("id", "")),
                str(c.get("lab", "")) or "-",
                _cell(c.get("params_b"), "{:g}"),
                str(c.get("quant", "")) or "-",
                "yes" if c.get("resident") else "no",
                _cell(c.get("memory_gib"), "{:.1f}"),
                _cell(c.get("tps"), "{:.1f}"),
                _yn(c.get("json_ok")),
                _yn(c.get("think_ok")),
                str(c.get("runs", 0)),
                str(c.get("wins", 0)),
                str(c.get("chaired", 0)),
                "{:.0f}".format(100 * (c.get("win_rate") or 0.0)),
                probe,
            ]
        )
    widths = [max(len(header[i]), *(len(r[i]) for r in rows)) if rows else len(header[i])
              for i in range(len(header))]

    def line(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)).rstrip()

    out = [line(header), line(["-" * w for w in widths])]
    out.extend(line(r) for r in rows)
    return "\n".join(out)


__all__ = ["build_cards", "cards_text"]
