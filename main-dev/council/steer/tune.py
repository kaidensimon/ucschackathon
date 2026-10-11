"""Pick the strength for one steering vector.

Pure module. No I/O of its own: the caller supplies `generate`, which runs the
model with the vector at a given strength and returns its replies to a few fixed
test prompts.

Scales are walked in ascending order. A scale is USABLE when the share of broken
replies is <= max_broken. The walk stops at the first unusable scale, because
stronger ones are worse.
"""

from __future__ import annotations

import math
import zlib
from typing import Awaitable, Callable, Optional

__all__ = ["default_is_broken", "pick_scale"]

_EPS = 1e-9
_WORD_MIN = 8
_WORD_UNIQUE_MIN = 0.30
_ZLIB_MIN_BYTES = 60
_ZLIB_RATIO_MIN = 0.15
_EFFECT_TOLERANCE = 0.10


def default_is_broken(text: str) -> tuple[bool, str]:
    """Tiny check for a reply gone bad: empty, or heavily repeated.

    Returns (broken, reason). reason is "" when the reply is fine.
    """
    if not isinstance(text, str) or not text.strip():
        return True, "empty"
    words = text.split()
    if len(words) >= _WORD_MIN:
        lowered = [w.lower() for w in words]
        if len(set(lowered)) / len(lowered) < _WORD_UNIQUE_MIN:
            return True, "repeated words"
    raw = text.encode("utf-8", errors="replace")
    if len(raw) >= _ZLIB_MIN_BYTES:
        if len(zlib.compress(raw)) / len(raw) < _ZLIB_RATIO_MIN:
            return True, "repeated text"
    return False, ""


def _broken_share(replies: list[str], is_broken: Callable[[str], tuple[bool, str]]) -> float:
    """Share of replies flagged broken. No replies at all counts as fully broken."""
    if not replies:
        return 1.0
    bad = sum(1 for r in replies if is_broken(r)[0])
    return bad / len(replies)


def _clean_scales(scales: list[float]) -> list[float]:
    """Ascending, de-duplicated, finite scales only."""
    out = {float(s) for s in scales if s is not None and math.isfinite(float(s))}
    return sorted(out)


async def pick_scale(
    scales: list[float],
    generate: Callable[[float], Awaitable[list[str]]],
    effect: Optional[Callable[[list[str]], float]] = None,
    baseline: Optional[list[str]] = None,
    is_broken: Optional[Callable[[str], tuple[bool, str]]] = None,
    max_broken: float = 0.0,
) -> dict:
    """Walk `scales` upward and choose one strength.

    effect: higher = more of the wanted behaviour. When `baseline` (replies with no
    vector) is also given, each recorded effect is the gain over effect(baseline).
    Choice with effect: the smallest usable scale whose effect is within 10% of the
    best usable effect. Without effect: the largest usable scale that is not the
    last one before breaking when 2+ are usable (one step of safety margin); when
    the walk never broke, the largest usable; the only usable one if just one.

    Returns {"scale": float | None, "tried": [{"scale", "broken_share", "effect"}],
    "reason": str}. scale is None when nothing is usable.
    """
    check = is_broken or default_is_broken
    grid = _clean_scales(scales)
    tried: list[dict] = []
    if not grid:
        return {"scale": None, "tried": tried, "reason": "no scales given"}

    base_effect = 0.0
    if effect is not None and baseline is not None:
        base_effect = float(effect(baseline))

    usable: list[dict] = []
    broke = False
    for s in grid:
        replies = list(await generate(s) or [])
        share = _broken_share(replies, check)
        ok = share <= max_broken + _EPS
        eff: Optional[float] = None
        if effect is not None and ok:
            eff = float(effect(replies)) - base_effect
        row = {"scale": s, "broken_share": share, "effect": eff}
        tried.append(row)
        if not ok:
            broke = True
            break
        usable.append(row)

    if not usable:
        return {
            "scale": None,
            "tried": tried,
            "reason": f"nothing usable: scale {grid[0]} already broken "
            f"(share {tried[0]['broken_share']:.2f} > {max_broken:.2f})",
        }

    where = f"broke at {tried[-1]['scale']}" if broke else "never broke"

    if effect is not None:
        scored = [r for r in usable if r["effect"] is not None and math.isfinite(r["effect"])]
        if scored:
            best = max(r["effect"] for r in scored)
            floor = best - _EFFECT_TOLERANCE * abs(best)
            pick = next(r for r in scored if r["effect"] >= floor - _EPS)
            return {
                "scale": pick["scale"],
                "tried": tried,
                "reason": f"smallest usable scale within 10% of best effect {best:.4g} ({where})",
            }
        # effect gave no finite numbers: fall through to the safety-margin rule

    if len(usable) == 1:
        return {"scale": usable[0]["scale"], "tried": tried, "reason": f"only usable scale ({where})"}
    if broke:
        return {
            "scale": usable[-2]["scale"],
            "tried": tried,
            "reason": f"one step below the last usable scale as safety margin ({where})",
        }
    return {"scale": usable[-1]["scale"], "tried": tried, "reason": f"largest usable scale ({where})"}
