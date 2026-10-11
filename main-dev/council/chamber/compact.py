"""Shrink pasted drafts and critiques so later debate rounds fit small context windows. Pure.

No I/O, no clock, no randomness. Inputs are never mutated; copies are returned.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Tuple

CUT_MARKER = "\n...[cut]...\n"
HEAD_FRACTION = 0.7
MIN_ANSWER_CHARS = 400
MAX_CLAIM_CHARS = 200
MAX_CLAIMS = 5
MAX_RISKS = 2
MAX_CRITIQUE_CHARS = 300
MIN_BUDGET = 1500
CHARS_PER_TOKEN = 3.6

DEFAULT_KEEP_FIELDS: Tuple[str, ...] = ("answer", "claims", "confidence", "risks", "assumptions")
_SEVERITY_RANK = {"blocking": 0, "major": 1, "minor": 2}


def _size(obj: Any) -> int:
    return len(json.dumps(obj, ensure_ascii=False, default=str))


def clip_text(text: str, max_chars: int) -> str:
    """Keep head 70% and tail 30% with a cut marker between. Short text is returned unchanged."""
    if len(text) <= max_chars:
        return text
    keep = max_chars - len(CUT_MARKER)
    if keep <= 0:
        return text[: max(0, max_chars)]
    head = int(keep * HEAD_FRACTION)
    tail = keep - head
    return text[:head] + CUT_MARKER + (text[len(text) - tail :] if tail > 0 else "")


def _clip_claim(claim: Any) -> Any:
    if isinstance(claim, str):
        return clip_text(claim, MAX_CLAIM_CHARS)
    if isinstance(claim, dict) and isinstance(claim.get("text"), str):
        claim["text"] = clip_text(claim["text"], MAX_CLAIM_CHARS)
    return claim


def _shrink_one(draft: Dict[str, Any], share: int, keep_fields: Tuple[str, ...]) -> Dict[str, Any]:
    """Cut one draft until it fits share. Steps only touch fields named in keep_fields."""
    d = copy.deepcopy(draft)
    if _size(d) <= share:
        return d
    if "assumptions" in keep_fields:
        d.pop("assumptions", None)
        if _size(d) <= share:
            return d
    if "risks" in keep_fields and isinstance(d.get("risks"), list):
        d["risks"] = d["risks"][:MAX_RISKS]
        if _size(d) <= share:
            return d
    if "claims" in keep_fields and isinstance(d.get("claims"), list):
        d["claims"] = [_clip_claim(c) for c in d["claims"][:MAX_CLAIMS]]
        if _size(d) <= share:
            return d
    if "answer" in keep_fields and isinstance(d.get("answer"), str):
        answer = d["answer"]
        target = len(answer)
        for _ in range(3):  # the JSON-escaped cut marker is longer than its raw form; re-check
            target = max(MIN_ANSWER_CHARS, target - (_size(d) - share))
            d["answer"] = clip_text(answer, target)
            if _size(d) <= share or target == MIN_ANSWER_CHARS:
                break
    return d


def compact_drafts(
    drafts: List[Dict[str, Any]],
    budget_chars: int,
    keep_fields: Tuple[str, ...] = DEFAULT_KEEP_FIELDS,
) -> List[Dict[str, Any]]:
    """Fit drafts into budget_chars of JSON. Equal shares; small drafts lend spare room (two passes)."""
    if not drafts or _size(drafts) <= budget_chars:
        return copy.deepcopy(list(drafts))
    n = len(drafts)
    usable = max(0, budget_chars - 2 - 2 * (n - 1))  # brackets and ", " separators
    sizes = [_size(d) for d in drafts]
    share = usable // n
    for _ in range(2):
        small = [s for s in sizes if s <= share]
        big_count = n - len(small)
        if big_count == 0 or not small:
            break
        share = (usable - sum(small)) // big_count
    return [_shrink_one(d, share, keep_fields) for d in drafts]


def _severity_rank(c: Dict[str, Any]) -> int:
    sev = c.get("severity")
    if isinstance(sev, str):
        return _SEVERITY_RANK.get(sev.lower(), 3)
    return 3


def compact_critiques(critiques: List[Dict[str, Any]], budget_chars: int) -> List[Dict[str, Any]]:
    """Most serious first (blocking > major > minor), clip text, drop from the end until it fits."""
    out = [copy.deepcopy(c) for c in critiques]
    out.sort(key=_severity_rank)  # stable: equal severity keeps input order
    for c in out:
        for key in ("text", "flaw"):
            if isinstance(c.get(key), str):
                c[key] = clip_text(c[key], MAX_CRITIQUE_CHARS)
    while out and _size(out) > budget_chars:
        out.pop()
    return out


def budget_chars(num_ctx: int, max_output: int, fixed_prompt_chars: int, share: float = 0.6) -> int:
    """Characters available for pasted material, floor 1500."""
    raw = ((num_ctx - max_output) * CHARS_PER_TOKEN - fixed_prompt_chars) * share
    return max(MIN_BUDGET, int(raw))
