"""Speculative decoding pairs. Pure: no I/O, no clock, no randomness.

A small draft model guesses tokens, the big target model verifies them. Both must share a
tokenizer, so only same-lineage pairs are proposed. Speedup is measured on the box later and
fed back in through apply_measurements.
"""

from __future__ import annotations

from typing import Optional

from council.core.schemas import ModelEntry
from council.core.schemas_v15 import DraftPair


def _family_prefix(model_id: str) -> str:
    """Id up to the first digit, trailing separators stripped. "gemma4-12b" -> "gemma"."""
    out = []
    for ch in model_id:
        if ch.isdigit():
            break
        out.append(ch)
    return "".join(out).rstrip("-_. ").lower()


def _same_family(a: ModelEntry, b: ModelEntry) -> bool:
    la, lb = (a.lineage or "").strip().lower(), (b.lineage or "").strip().lower()
    if la and lb:
        return la == lb
    # Lineage missing on either side: same lab AND same id prefix.
    lab_a, lab_b = (a.lab or "").strip().lower(), (b.lab or "").strip().lower()
    if not lab_a or lab_a != lab_b:
        return False
    pa = _family_prefix(a.id)
    return bool(pa) and pa == _family_prefix(b.id)


def _family_name(target: ModelEntry) -> str:
    return (target.lineage or "").strip() or _family_prefix(target.id)


def propose_pairs(models: list[ModelEntry], max_ratio: float = 0.5) -> list[DraftPair]:
    """For each model, pair it with the smallest same-family model at most max_ratio its size."""
    pairs: list[DraftPair] = []
    for target in models:
        if target.params_b is None or target.params_b <= 0:
            continue
        limit = max_ratio * target.params_b
        candidates = [
            m
            for m in models
            if m.id != target.id
            and m.params_b is not None
            and m.params_b > 0
            and m.params_b <= limit
            and _same_family(target, m)
        ]
        if not candidates:
            continue
        draft = min(candidates, key=lambda m: (m.params_b, m.id))
        pairs.append(
            DraftPair(
                target_id=target.id,
                draft_id=draft.id,
                family=_family_name(target),
                size_ratio=round(draft.params_b / target.params_b, 4),
                verified=False,
            )
        )
    return pairs


def apply_measurements(pairs: list[DraftPair], measured: dict[str, float]) -> list[DraftPair]:
    """Return new pairs with speedup set where measured["target|draft"] exists."""
    out: list[DraftPair] = []
    for p in pairs:
        key = f"{p.target_id}|{p.draft_id}"
        if key not in measured:
            out.append(p.model_copy())
            continue
        speedup = float(measured[key])
        note = "slower with draft" if speedup < 1.0 else p.note
        out.append(p.model_copy(update={"verified": True, "speedup": speedup, "note": note}))
    return out


def worth_it(pair: DraftPair, min_speedup: float = 1.15) -> bool:
    """True only for a measured pair whose speedup reaches min_speedup."""
    return bool(pair.verified) and pair.speedup is not None and pair.speedup >= min_speedup


def _fmt_speedup(s: Optional[float]) -> str:
    return "unmeasured" if s is None else f"{s:.2f}x"


def pairs_text(pairs: list[DraftPair]) -> str:
    """One line per pair, plain text."""
    if not pairs:
        return "no draft pairs"
    lines = []
    for p in pairs:
        state = "verified" if p.verified else "unverified"
        line = (
            f"{p.target_id} <- {p.draft_id} [{p.family or '-'}] "
            f"ratio {p.size_ratio:.2f} {state} {_fmt_speedup(p.speedup)}"
        )
        if p.note:
            line += f" ({p.note})"
        lines.append(line)
    return "\n".join(lines)
