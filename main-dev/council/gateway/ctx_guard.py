"""Context window guard (pure).

Ollama silently truncates from the top when a prompt overflows num_ctx, which cuts the system
prompt. This module trims the middle of the longest messages first so the system prompt head and
the final question survive. No I/O, no clock, no randomness.
"""

from __future__ import annotations

import math

PROTECT_CHARS = 1500
PER_MESSAGE_OVERHEAD = 4
CHARS_PER_TOKEN = 3.6


def est_tokens(text: str) -> int:
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def _content(message: dict) -> str:
    content = message.get("content", "")
    return content if isinstance(content, str) else str(content or "")


def messages_tokens(messages: list[dict]) -> int:
    return sum(est_tokens(_content(m)) + PER_MESSAGE_OVERHEAD for m in messages)


def _budget(num_ctx: int, max_output: int, reserve: int) -> int:
    return num_ctx - max_output - reserve


def overflow(messages: list[dict], num_ctx: int, max_output: int, reserve: int = 256) -> int:
    """Tokens over budget, 0 if the messages fit."""
    return max(0, messages_tokens(messages) - _budget(num_ctx, max_output, reserve))


def _marker(n: int) -> str:
    return f"\n...[cut {n} characters to fit the context window]...\n"


def _protection(messages: list[dict]) -> list[tuple[int, int]]:
    """Per message: (protected head chars, protected tail chars)."""
    last_user = -1
    for i, m in enumerate(messages):
        if m.get("role") == "user":
            last_user = i
    out: list[tuple[int, int]] = []
    for i, m in enumerate(messages):
        if m.get("role") == "system":
            out.append((PROTECT_CHARS, 0))
        elif i == last_user:
            out.append((0, PROTECT_CHARS))
        else:
            out.append((0, 0))
    return out


def _render(orig: str, head: int, tail: int, removed: int) -> str:
    """Original with `removed` chars cut from the middle of its unprotected region."""
    if removed <= 0:
        return orig
    region = len(orig) - head - tail
    keep = region - removed
    keep_a = keep // 2
    keep_b = keep - keep_a
    start_b = len(orig) - tail - keep_b
    return orig[: head + keep_a] + _marker(removed) + orig[start_b:]


def fit_messages(
    messages: list[dict], num_ctx: int, max_output: int, reserve: int = 256
) -> tuple[list[dict], dict]:
    budget = _budget(num_ctx, max_output, reserve)
    before = messages_tokens(messages)
    if before <= budget:
        return [dict(m) for m in messages], {
            "trimmed": False,
            "before": before,
            "after": before,
            "budget": budget,
            "fits": True,
            "cuts": [],
        }

    orig = [_content(m) if isinstance(m.get("content", ""), str) else None for m in messages]
    prot = _protection(messages)
    # region length per message; None content (non-text) is never cut
    region = [
        0 if orig[i] is None else max(0, len(orig[i]) - prot[i][0] - prot[i][1])  # type: ignore[arg-type]
        for i in range(len(messages))
    ]
    removed = [0] * len(messages)
    current = [o if o is not None else _content(m) for o, m in zip(orig, messages)]

    def total() -> int:
        return sum(est_tokens(c) + PER_MESSAGE_OVERHEAD for c in current)

    while True:
        over = total() - budget
        if over <= 0:
            break
        # candidates: room left and cutting it would actually save characters
        cands = [
            i
            for i in range(len(messages))
            if orig[i] is not None
            and removed[i] < region[i]
            and region[i] - removed[i] > 0
            and region[i] > len(_marker(region[i]))
        ]
        if not cands:
            break
        i = max(cands, key=lambda k: (len(current[k]), -k))
        need = math.ceil(over * CHARS_PER_TOKEN) + 8
        if removed[i] == 0:
            need += len(_marker(need))
        removed[i] = min(region[i], removed[i] + max(1, need))
        current[i] = _render(orig[i], prot[i][0], prot[i][1], removed[i])  # type: ignore[arg-type]

    out = []
    for i, m in enumerate(messages):
        nm = dict(m)
        if removed[i] > 0:
            nm["content"] = current[i]
        out.append(nm)
    after = total()
    return out, {
        "trimmed": True,
        "before": before,
        "after": after,
        "budget": budget,
        "fits": after <= budget,
        "cuts": [{"index": i, "removed_chars": removed[i]} for i in range(len(messages)) if removed[i] > 0],
    }
