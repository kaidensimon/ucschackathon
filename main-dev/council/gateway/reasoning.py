"""Reasoning normalization (spec 7.4).

- request_fields: registry request fields for a reasoning level.
- strip_reasoning: split a reply into (content, reasoning).
- apply_caps: token caps for a call, server-enforced or not.

No I/O. Imports types from council.core.schemas only.
"""

from __future__ import annotations

import re
from typing import Any

from council.core.schemas import ModelEntry

LEVELS: tuple[str, ...] = ("off", "council", "max")

# <think>...</think> and <thinking>...</thinking>, matched as single tags.
_TAG_RE = re.compile(r"<(/?)(think|thinking)\s*>", re.IGNORECASE)

# Harmony-style channel markers: <|channel|>analysis<|message|>...<|end|>...
_CHANNEL_MARK = "<|channel|>"
_CHANNEL_CUT_RE = re.compile(r"<\|end\|>|<\|return\|>|<\|call\|>|<\|start\|>")
_CHANNEL_NAME_RE = re.compile(r"\s*([A-Za-z_]+)")


def request_fields(entry: ModelEntry, level: str) -> dict[str, Any]:
    """Registry request fields that produce `level` for this model. Empty dict if not defined."""
    if level not in LEVELS:
        raise ValueError(f"unknown reasoning level: {level!r}")
    fields = getattr(entry.reasoning, level, None)
    return dict(fields) if fields else {}


def _split_tags(text: str) -> list[tuple[bool, str]]:
    """Ordered (is_reasoning, text) segments split on think tags.

    Unclosed opening tag: the rest is reasoning.
    Closing tag with no opening tag: everything before it is reasoning.
    """
    segments: list[tuple[bool, str]] = []
    inside = False
    pos = 0
    for m in _TAG_RE.finditer(text):
        seg = text[pos:m.start()]
        if seg:
            segments.append((inside, seg))
        is_close = m.group(1) == "/"
        if not is_close:
            inside = True  # a repeated opening tag inside a block is dropped
        elif inside:
            inside = False
        else:
            # Stray closing tag: all text before it was reasoning.
            segments = [(True, s) if not r else (r, s) for r, s in segments]
        pos = m.end()
    tail = text[pos:]
    if tail:
        segments.append((inside, tail))
    return segments


def _split_channels(text: str) -> tuple[str, str]:
    """Split harmony channel markers. Returns (content, reasoning). Text with no marker is content."""
    if _CHANNEL_MARK not in text:
        return text, ""
    head, *chunks = text.split(_CHANNEL_MARK)
    content_parts = [head]
    reasoning_parts: list[str] = []
    for chunk in chunks:
        name_m = _CHANNEL_NAME_RE.match(chunk)
        name = name_m.group(1).lower() if name_m else ""
        body = chunk
        if "<|message|>" in chunk:
            body = chunk.split("<|message|>", 1)[1]
        elif name_m:
            body = chunk[name_m.end():]
        body = _CHANNEL_CUT_RE.split(body, maxsplit=1)[0]
        if name == "final":
            content_parts.append(body)
        else:
            reasoning_parts.append(body)
    return "".join(content_parts), "".join(reasoning_parts)


def strip_reasoning(text: str) -> tuple[str, str]:
    """Return (content, reasoning) for a raw model reply. Both stripped of outer whitespace."""
    if not text:
        return "", ""

    segments = _split_tags(text)
    tag_content = "".join(s for r, s in segments if not r)
    tag_reasoning = [s for r, s in segments if r]

    channel_content, channel_reasoning = _split_channels(tag_content)

    reasoning_pieces = [p.strip() for p in tag_reasoning + [channel_reasoning] if p and p.strip()]
    return channel_content.strip(), "\n\n".join(reasoning_pieces)


def apply_caps(max_output_tokens: int, max_reasoning_tokens: int, server_enforces: bool) -> dict[str, int]:
    """Token caps for one request.

    server_enforces=True: the runtime takes a separate reasoning budget.
        {"max_tokens": max_output_tokens, "reasoning_budget": max_reasoning_tokens}
    server_enforces=False: one cap covers reasoning and answer together.
        {"max_tokens": max_output_tokens}
    """
    if max_output_tokens < 0 or max_reasoning_tokens < 0:
        raise ValueError("token caps must be non-negative")
    if server_enforces:
        return {"max_tokens": max_output_tokens, "reasoning_budget": max_reasoning_tokens}
    return {"max_tokens": max_output_tokens}


__all__ = ["LEVELS", "request_fields", "strip_reasoning", "apply_caps"]
