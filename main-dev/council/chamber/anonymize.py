"""Clerk steps `compress_for_seat` and `anonymize` (spec 10.5).

Pure field selection. No model call. Model ids and lens names are never copied,
because only the fields listed here are read off a Draft.
"""

from __future__ import annotations

import random
from typing import Any

from council.core.schemas import Draft

OWN_PREFIX = "Y"


def _letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA, ..."""
    out = ""
    n = index
    while True:
        out = chr(ord("A") + n % 26) + out
        n = n // 26 - 1
        if n < 0:
            break
    return out


def compress_for_seat(draft: Draft, max_chars: int = 1000) -> dict[str, Any]:
    """Keep summary, claims (id, text) and risks. Total text is capped at max_chars.

    Budget order: summary, then claim texts in order, then risks in order.
    A piece that does not fit is cut to the remaining budget, and later pieces drop out.
    """
    budget = max(0, int(max_chars))

    def take(text: str) -> str:
        nonlocal budget
        text = text or ""
        cut = text[:budget]
        budget -= len(cut)
        return cut

    summary = take(draft.summary)

    claims: list[dict[str, str]] = []
    for claim in draft.claims:
        if budget <= 0:
            break
        claims.append({"id": claim.id, "text": take(claim.text)})

    risks: list[str] = []
    for risk in draft.risks:
        if budget <= 0:
            break
        risks.append(take(risk))

    return {"summary": summary, "claims": claims, "risks": risks}


def label_to_seat(seats: list[int] | dict[int, Any], recipient: int, seed: int) -> dict[str, int]:
    """Shuffle the OTHER seats for this recipient. Deterministic in (seed, recipient).

    Returns {label letter: seat_no}. Labels run A, B, C in shuffled order.
    """
    seat_list = list(seats)
    others = sorted(s for s in seat_list if s != recipient)
    rng = random.Random(f"{int(seed)}:{int(recipient)}")
    rng.shuffle(others)
    return {_letter(i): seat for i, seat in enumerate(others)}


def anonymize(drafts: dict[int, Draft], recipient: int, seed: int,
              max_chars: int = 1000) -> dict[str, Any]:
    """Build the anonymous view one recipient sees.

    Output:
      labels: {letter: seat_no} for the other seats
      others: [{"label", "summary", "claims", "risks"}] with claim ids like "A.c1"
      own:    {"summary", "claims", "risks"} for the recipient's draft, claim ids
              like "Y.c1", marked "yours": True
    """
    labels = label_to_seat(list(drafts.keys()), recipient, seed)

    others: list[dict[str, Any]] = []
    for label, seat in labels.items():
        comp = compress_for_seat(drafts[seat], max_chars=max_chars)
        for claim in comp["claims"]:
            claim["id"] = f"{label}.{claim['id']}"
        others.append({"label": label, **comp})

    own_comp = compress_for_seat(drafts[recipient], max_chars=max_chars)
    for claim in own_comp["claims"]:
        claim["id"] = f"{OWN_PREFIX}.{claim['id']}"
    own = {**own_comp, "yours": True}

    return {"labels": labels, "others": others, "own": own}


def label_of(view: dict[str, Any], seat: int) -> str | None:
    """Return the label for another seat in this view, or None."""
    for label, s in view["labels"].items():
        if s == seat:
            return label
    return None


def allowed_refs(view: dict[str, Any]) -> list[str]:
    """Every claim ref that appears in the view, in order: others first, then own."""
    refs: list[str] = []
    for entry in view["others"]:
        refs.extend(c["id"] for c in entry["claims"])
    refs.extend(c["id"] for c in view["own"]["claims"])
    return refs
