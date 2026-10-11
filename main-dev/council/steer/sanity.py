"""Steering sanity check (spec 1.5). Pure: no I/O, no clock, no randomness.

A control vector that is too strong makes the model repeat itself, print
dots or return nothing. looks_broken flags such replies so the strength
search can back off.
"""

from __future__ import annotations

import re
from collections import Counter

_WORD = re.compile(r"\w+")

MIN_WORDS = 12
MIN_DISTINCT = 3
PHRASE_LEN = 3
PHRASE_MAX_REPEATS = 4
SYMBOL_MIN_CHARS = 20
SYMBOL_SHARE_MAX = 0.5
DOMINANT_SHARE_MAX = 0.4


def looks_broken(text: str) -> tuple[bool, str]:
    """Return (True, reason) when a reply looks broken, else (False, "")."""
    if not text.strip():
        return True, "empty reply"
    words = _WORD.findall(text.lower())
    n = len(words)
    if n >= MIN_WORDS:
        distinct = len(set(words))
        if distinct < MIN_DISTINCT:
            return True, f"only {distinct} distinct words in {n}"
    phrases = Counter(
        tuple(words[i : i + PHRASE_LEN]) for i in range(n - PHRASE_LEN + 1)
    )
    if phrases:
        phrase, count = phrases.most_common(1)[0]
        if count >= PHRASE_MAX_REPEATS:
            return True, f"phrase {' '.join(phrase)!r} repeated {count} times"
    if len(text) > SYMBOL_MIN_CHARS:
        symbols = sum(1 for c in text if not c.isalnum() and not c.isspace())
        share = symbols / len(text)
        if share > SYMBOL_SHARE_MAX:
            return True, f"{share:.0%} of characters are symbols"
    if n >= MIN_WORDS:
        word, count = Counter(words).most_common(1)[0]
        if count / n > DOMINANT_SHARE_MAX:
            return True, f"word {word!r} is {count} of {n} words"
    return False, ""


def broken_share(texts: list[str]) -> float:
    """Fraction of replies that looks_broken flags. Empty list gives 0.0."""
    if not texts:
        return 0.0
    broken = sum(1 for t in texts if looks_broken(t)[0])
    return broken / len(texts)
