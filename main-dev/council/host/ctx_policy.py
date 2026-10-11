"""Context window policy per job role, plus sizing helpers.

Pure module: no I/O, no clock, no randomness.

- ctx_for(role, mode, overrides)  -> context window in tokens for a job role
- needed_ctx(prompt, out, reason) -> smallest standard window that holds the request
- est_tokens(text)                -> rough token count from character length
"""

from __future__ import annotations

from typing import Optional

# Standard window sizes, smallest first. needed_ctx picks from these only.
CTX_BUCKETS: tuple[int, ...] = (2048, 4096, 8192, 12288, 16384, 24576, 32768)

DEFAULT_CTX = 8192

# Base window per role. "seat" is mode-dependent, see _SEAT_BY_MODE.
_ROLE_CTX: dict[str, int] = {
    "seat": 16384,
    "chair": 16384,
    "planner": 16384,
    "worker": 8192,
    "senior_worker": 12288,
    "clerk": 8192,
    "review": 16384,
    "probe": 2048,
}

_SEAT_BY_MODE: dict[str, int] = {
    "standard": 16384,
    "deep": 24576,
    "quick": 8192,
}

# Characters per token used by est_tokens.
_CHARS_PER_TOKEN = 3.6


def ctx_for(
    role: str,
    mode: str = "standard",
    overrides: Optional[dict[str, int]] = None,
) -> int:
    """Return the context window (tokens) for a job role.

    - An entry in `overrides` keyed by `role` wins over everything else.
    - "seat" depends on `mode`: standard 16384, deep 24576, quick 8192.
      An unknown mode is treated as standard.
    - Other roles ignore `mode`.
    - Unknown roles get DEFAULT_CTX (8192).
    """
    if overrides is not None and role in overrides:
        return int(overrides[role])
    if role == "seat":
        return _SEAT_BY_MODE.get(mode, _SEAT_BY_MODE["standard"])
    return _ROLE_CTX.get(role, DEFAULT_CTX)


def needed_ctx(
    prompt_tokens: int,
    max_output: int,
    reasoning: int = 0,
    margin: float = 1.15,
) -> int:
    """Smallest bucket in CTX_BUCKETS holding (prompt + output + reasoning) * margin.

    Returns 32768 when even the largest bucket is too small.
    """
    need = (max(0, prompt_tokens) + max(0, max_output) + max(0, reasoning)) * margin
    for bucket in CTX_BUCKETS:
        if need <= bucket:
            return bucket
    return CTX_BUCKETS[-1]


def est_tokens(text: str) -> int:
    """Rough token estimate: len(text) / 3.6, rounded, never below 1."""
    return max(1, round(len(text) / _CHARS_PER_TOKEN))
