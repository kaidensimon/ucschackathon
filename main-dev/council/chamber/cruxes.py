"""Clerk step extract_cruxes (spec 10.5). Pure functions, no model calls here."""

from __future__ import annotations

from typing import Any, Optional

from council.chamber.prompts import render
from council.core.schemas import CallSpec, Critique, Crux, Option

MAX_CRUXES = 5
CRUX_KINDS = ("factual", "checkable", "value")


def _schema(option_ids: list[str]) -> dict[str, Any]:
    between_item: dict[str, Any] = {"type": "string"}
    if option_ids:
        between_item["enum"] = list(option_ids)
    return {
        "type": "object",
        "properties": {
            "cruxes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "statement": {"type": "string"},
                        "between": {"type": "array", "items": between_item},
                        "kind": {"type": "string", "enum": list(CRUX_KINDS)},
                    },
                    "required": ["statement", "between", "kind"],
                },
            }
        },
        "required": ["cruxes"],
    }


def _critique_lines(critiques: dict[int, Critique]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for seat in sorted(critiques):
        c = critiques[seat]
        for r in c.reviews:
            for f in r.flaws:
                out.append({"seat": seat, "target": r.target, "severity": f.severity, "kind": f.kind, "flaw": f.text})
    return out


def build_cruxes_call(
    run_id: Optional[str],
    clerk_model_id: str,
    options: list[Option],
    critiques: dict[int, Critique],
    max_cruxes: int = MAX_CRUXES,
) -> CallSpec:
    opts = [{"id": o.id, "summary": o.summary, "holders": o.holders} for o in options]
    prompt = render("clerk_cruxes", options=opts, critiques=_critique_lines(critiques))
    if max_cruxes != MAX_CRUXES:
        prompt = prompt.replace("at most 5", f"at most {max_cruxes}", 1)
    return CallSpec(
        model_id=clerk_model_id,
        run_id=run_id,
        purpose="clerk.extract_cruxes",
        messages=[
            {"role": "system", "content": "You are the Clerk. You list disagreements. You add no opinion."},
            {"role": "user", "content": prompt},
        ],
        json_schema=_schema([o.id for o in options]),
        reasoning="off",
        max_output_tokens=700,
        temperature=0.0,
    )


def parse_cruxes(
    parsed: Optional[dict], options: list[Option], max_cruxes: int = MAX_CRUXES
) -> list[Crux]:
    if not isinstance(parsed, dict):
        return []
    raw = parsed.get("cruxes")
    if not isinstance(raw, list):
        return []
    known = {o.id for o in options}
    out: list[Crux] = []
    for item in raw:
        if len(out) >= max_cruxes:
            break
        if not isinstance(item, dict):
            continue
        statement = item.get("statement")
        between = item.get("between")
        if not isinstance(statement, str) or not statement.strip():
            continue
        if not isinstance(between, list) or not between:
            continue
        if any(not isinstance(b, str) or b not in known for b in between):
            continue
        ids: list[str] = []
        for b in between:
            if b not in ids:
                ids.append(b)
        kind = item.get("kind")
        if kind not in CRUX_KINDS:
            kind = "factual"
        out.append(Crux(id=f"x{len(out) + 1}", statement=statement.strip(), between=ids, kind=kind))
    return out


def heuristic_cruxes(
    options: list[Option], critiques: dict[int, Critique], max_cruxes: int = MAX_CRUXES
) -> list[Crux]:
    """Fallback: one crux per distinct major or fatal flaw, fatal first."""
    ids = [o.id for o in options]
    if len(ids) < 2:
        return []
    found: list[tuple[int, str, str]] = []  # (rank, text, flaw kind)
    seen: set[str] = set()
    for seat in sorted(critiques):
        for r in critiques[seat].reviews:
            for f in r.flaws:
                if f.severity not in ("major", "fatal"):
                    continue
                text = f.text.strip()
                key = text.lower()
                if not text or key in seen:
                    continue
                seen.add(key)
                found.append((0 if f.severity == "fatal" else 1, text, f.kind))
    found.sort(key=lambda t: t[0])
    out: list[Crux] = []
    for _, text, fkind in found[:max_cruxes]:
        if fkind == "preference":
            kind = "value"
        elif fkind == "factual":
            kind = "factual"
        else:
            kind = "checkable"
        out.append(Crux(id=f"x{len(out) + 1}", statement=text, between=list(ids), kind=kind))
    return out


__all__ = ["build_cruxes_call", "parse_cruxes", "heuristic_cruxes", "MAX_CRUXES"]
