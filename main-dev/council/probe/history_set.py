"""Probe training rows from the council's own labelled claims (ARCHITECTURE 28.2, 28.4).

A dataset.Pair is an honest/lie twin. A ledger record is one claim with one label, so it
cannot be a Pair. Each labelled record becomes one Row instead.

Pure: no I/O, no clock, randomness only from the seed.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from typing import Any

from council.probe.ledger import ANSWER_ID


@dataclass(frozen=True)
class Row:
    text: str
    label: int  # 1 = true claim, 0 = false claim
    group: str  # run id, so a split can keep one run on one side
    kind: str  # "answer" or "claim"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_LABELS = {"true": 1, "false": 0}


def records_to_pairs(records: list, min_text: int = 12) -> list[Row]:
    """One Row per labelled record. Unknown labels and too-short text are dropped.

    Same text with same label in the same run is kept once.
    """
    out: list[Row] = []
    seen: set[tuple[str, str, int]] = set()
    for r in records or []:
        label = _LABELS.get(str(getattr(r, "label", "unknown")))
        if label is None:
            continue
        text = (getattr(r, "text", "") or "").strip()
        if len(text) < int(min_text):
            continue
        group = getattr(r, "run_id", None) or ""
        key = (group, text, label)
        if key in seen:
            continue
        seen.add(key)
        kind = "answer" if getattr(r, "claim_id", "") == ANSWER_ID else "claim"
        out.append(Row(text=text, label=label, group=group, kind=kind))
    return out


def balance(rows, seed: int = 0) -> list:
    """Downsample the larger class to the size of the smaller. Original order is kept."""
    rows = list(rows)
    pos = [i for i, r in enumerate(rows) if int(r.label) == 1]
    neg = [i for i, r in enumerate(rows) if int(r.label) != 1]
    n = min(len(pos), len(neg))
    rng = random.Random(seed)
    keep: set[int] = set()
    for side in (pos, neg):
        picked = list(side)
        if len(picked) > n:
            picked = rng.sample(picked, n)
        keep.update(picked)
    return [r for i, r in enumerate(rows) if i in keep]


def enough(rows, min_labelled: int = 50, min_each: int = 15) -> tuple[bool, str]:
    """Is there enough to train? Returns (ok, reason)."""
    rows = list(rows)
    n_true = sum(1 for r in rows if int(r.label) == 1)
    n_false = len(rows) - n_true
    total = len(rows)
    if total < min_labelled:
        return False, f"need {min_labelled} labelled rows, have {total}"
    if n_true < min_each:
        return False, f"need {min_each} true rows, have {n_true}"
    if n_false < min_each:
        return False, f"need {min_each} false rows, have {n_false}"
    return True, f"ok: {total} rows, {n_true} true, {n_false} false"


__all__ = ["Row", "balance", "enough", "records_to_pairs"]
