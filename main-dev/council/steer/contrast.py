"""Contrast prompts a steering vector is made from. Pure: no I/O, no clock, no randomness.

A rule is one thing the project wants. Each rule becomes a (positive, negative) pair of system
instructions. `prompts_for` asks the same user request on both sides, so the only difference
between the two chats is the rule.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["GENERAL", "CODING", "rule_pair", "prompts_for", "from_corrections", "enough"]

# Same lists as tools/box/steer_test.py, where steering was proven on the box.
GENERAL = [
    "How do plants make food?", "Why is the sky blue?", "What is a database index?",
    "Explain how a bicycle stays upright.", "What causes the seasons?", "How does a vaccine work?",
    "What is inflation?", "Describe how bread is made.", "Why do we sleep?",
    "What is the difference between weather and climate?", "How do airplanes fly?",
    "What is an operating system?", "Why is exercise good for you?", "How does a refrigerator work?",
    "What is photosynthesis used for?", "Explain what a compiler does.",
]
CODING = [
    "Write a Python function that sums a list of numbers.",
    "Write a Python function that reverses a string and counts its vowels.",
    "Write a Python class for a bank account with deposit and withdraw.",
    "Write Python code that reads a file and counts the lines.",
    "Write a Python function that finds the largest item in a list.",
    "Write a Python function that checks whether a number is prime.",
    "Write a Python function that merges two sorted lists.",
    "Write Python code that computes the average word length of a sentence.",
    "Write a Python function that removes duplicate items from a list.",
    "Write a Python function that converts minutes to hours and minutes.",
    "Write a Python class that tracks the items in a shopping cart.",
    "Write a Python function that counts how often each word appears in a text.",
    "Write a Python function that validates an email address.",
    "Write a Python function that returns the first n square numbers.",
    "Write a Python function that computes the total price with tax.",
    "Write a Python function that parses a date string into year, month, day.",
]

CODE_WORDS = ("function", "variable", "name", "class", "test", "import", "python")
_CODE_RE = re.compile(r"\b(?:" + "|".join(CODE_WORDS) + r")s?\b", re.IGNORECASE)
TEXT_LIMIT = 600  # a correction can carry a long position; the instruction stays short


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def _bare(text: str) -> str:
    """Rule text without its trailing full stop, so the template does not double it."""
    return text.rstrip().rstrip(".").rstrip()


def _clip(text: str, n: int = TEXT_LIMIT) -> str:
    return text if len(text) <= n else text[: n - 3].rstrip() + "..."


def rule_pair(rule: str, opposite: str | None = None) -> tuple[str, str]:
    """(positive system instruction, negative system instruction) for one rule."""
    rule = _bare(_clean(rule))
    opp = _bare(_clean(opposite)) if opposite is not None else ""
    positive = f"In this project: {rule}. Always follow this."
    if opp:
        negative = f"In this project: {opp}. Always follow this."
    else:
        negative = f"In this project the opposite holds: do NOT do this: {rule}."
    return positive, negative


def _is_coding(rule_pairs: list[tuple[str, str]]) -> bool:
    return any(_CODE_RE.search(pos or "") for pos, _neg in rule_pairs)


def prompts_for(
    rule_pairs: list[tuple[str, str]],
    requests: list[str] | None = None,
    per_rule: int = 16,
) -> tuple[list[list[dict]], list[list[dict]]]:
    """(pos chats, neg chats). Each chat is [system, user]; both sides share the user request.

    Default requests: coding first when the rule mentions code words, else general first.
    Requests are cycled when `per_rule` exceeds the list.
    """
    pos_chats: list[list[dict]] = []
    neg_chats: list[list[dict]] = []
    if per_rule <= 0 or not rule_pairs:
        return pos_chats, neg_chats
    custom = [r for r in (requests or []) if _clean(r)]
    for pos, neg in rule_pairs:
        if custom:
            pool = custom
        elif _is_coding([(pos, neg)]):
            pool = CODING + GENERAL
        else:
            pool = GENERAL + CODING
        for i in range(per_rule):
            req = pool[i % len(pool)]
            pos_chats.append(
                [{"role": "system", "content": pos}, {"role": "user", "content": req}]
            )
            neg_chats.append(
                [{"role": "system", "content": neg}, {"role": "user", "content": req}]
            )
    return pos_chats, neg_chats


def _field(obj: Any, name: str) -> str:
    value = obj.get(name, "") if isinstance(obj, dict) else getattr(obj, name, "")
    return _clean(value)


def from_corrections(corrections: list) -> list[tuple[str, str]]:
    """One pair per correction.

    Positive = the corrected behaviour (council_position, else lesson). Negative = the original
    wrong behaviour when the correction records one, else the generic "do NOT" form.
    Corrections with no corrected text are skipped.
    """
    pairs: list[tuple[str, str]] = []
    for c in corrections or []:
        good = _field(c, "council_position") or _field(c, "lesson")
        if not good:
            continue
        wrong = _field(c, "wrong_position")
        pairs.append(rule_pair(_clip(good), _clip(wrong) if wrong else None))
    return pairs


def enough(rule_pairs, min_examples: int) -> bool:
    """True when at least `min_examples` usable pairs exist (both sides non-empty text)."""
    usable = 0
    for pair in rule_pairs or []:
        try:
            pos, neg = pair
        except (TypeError, ValueError):
            continue
        if _clean(pos) and _clean(neg):
            usable += 1
    return usable >= max(0, int(min_examples))
