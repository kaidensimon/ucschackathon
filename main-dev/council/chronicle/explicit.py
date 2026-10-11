"""Chronicle: detect explicit standing instructions in the user's text. Pure, no I/O.

When the user states a standing rule ("always ...", "from now on ...") it should be
remembered without the panel debating whether it matters. This module only finds the
rules; the caller turns them into MemoryCandidate objects.
"""

from __future__ import annotations

import re
from typing import Optional

_MAX_TEXT = 200

# (label, regex). Strong markers give confidence 0.9, the rest 0.7.
_STRONG: tuple[tuple[str, str], ...] = (
    ("from now on", r"\bfrom now on\b"),
    ("remember that", r"\bremember that\b"),
    ("going forward", r"\bgoing forward\b"),
    ("always", r"\balways\b"),
    # "we never" is its own weaker marker, so plain "never" must not follow "we ".
    ("never", r"(?<!we )\bnever\b"),
)
_WEAK: tuple[tuple[str, str], ...] = (
    ("in this project", r"\bin this project\b"),
    ("every time", r"\bevery time\b"),
    ("by default", r"\bby default\b"),
    ("do not ever", r"\b(?:do not|don't|don’t) ever\b"),
    ("we use", r"\bwe use\b"),
    ("we never", r"\bwe never\b"),
    ("prefer over", r"\bprefer\b[^.!?;\n]{1,80}?\bover\b"),
)
_STRONG_RE = tuple((label, re.compile(rx, re.IGNORECASE)) for label, rx in _STRONG)
_WEAK_RE = tuple((label, re.compile(rx, re.IGNORECASE)) for label, rx in _WEAK)

_LOCAL_RE = re.compile(
    r"\bthis (?:function|file|task)\b|(?<![\w'’])here(?![\w'’])", re.IGNORECASE
)
_SCOPE_RE = re.compile(r"\b(?:project|repo|repository|codebase|we)\b", re.IGNORECASE)
_MASK_RE = re.compile(
    r"```.*?(?:```|\Z)"  # fenced code block
    r"|`[^`\n]*`"  # inline code
    r'|"[^"\n]*"'  # straight double quotes
    r"|“[^”\n]*”"  # curly double quotes
    r"|^[ \t]*>.*$",  # block quote line
    re.DOTALL | re.MULTILINE,
)
_BOUNDARY_RE = re.compile(r"(?<=[.!?;])\s+|\n+")
_BULLET_RE = re.compile(r"^[\s\-*#>•]+")


def _mask(text: str) -> str:
    """Blank out code and quoted spans, keeping length and newlines so offsets line up."""
    return _MASK_RE.sub(lambda m: "".join(c if c == "\n" else " " for c in m.group(0)), text or "")


def _marker(masked: str) -> Optional[tuple[str, float]]:
    """Return (marker, confidence) for one masked sentence, or None if it is not a standing rule."""
    s = masked.strip()
    if not s or "?" in s or _LOCAL_RE.search(s):
        return None
    for group, conf in ((_STRONG_RE, 0.9), (_WEAK_RE, 0.7)):
        best: Optional[tuple[int, str]] = None
        for label, rx in group:
            m = rx.search(s)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), label)
        if best:
            return best[1], conf
    return None


def _clean(text: str) -> str:
    text = " ".join(_BULLET_RE.sub("", text.strip()).split())
    return text if len(text) <= _MAX_TEXT else text[: _MAX_TEXT - 3].rstrip() + "..."


def is_standing(sentence: str) -> bool:
    """True when the sentence states a standing rule (marker present, not a question,
    not task-local, marker not inside quoted text or code)."""
    return _marker(_mask(sentence)) is not None


def find_rules(task_text: str, max_rules: int = 3) -> list[dict]:
    """Find explicit standing instructions in the user's text, in order of appearance."""
    if max_rules <= 0 or not task_text:
        return []
    masked = _mask(task_text)
    rules: list[dict] = []
    seen: set[str] = set()
    start = 0
    spans: list[tuple[int, int]] = []
    for b in _BOUNDARY_RE.finditer(masked):
        spans.append((start, b.start()))
        start = b.end()
    spans.append((start, len(masked)))
    for lo, hi in spans:
        found = _marker(masked[lo:hi])
        if not found:
            continue
        text = _clean(task_text[lo:hi])
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        marker, conf = found
        rules.append(
            {
                "text": text,
                "marker": marker,
                "scope": "project" if _SCOPE_RE.search(masked[lo:hi]) else "user",
                "kind": "preference",
                "confidence": conf,
            }
        )
        if len(rules) >= max_rules:
            break
    return rules
