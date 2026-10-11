"""How the council itself sees the lie detector. Pure: no I/O, no clock, no randomness.

Two uses:
  - advisory notes put in a seat's round 1 prompt (notes_for_seat)
  - targets for the cross-examiner (tribunal_targets, question_hint)

Notes never show seat numbers or model ids. Only the anonymous draft letters.
"""

from __future__ import annotations

import re

from council.core.schemas_v15 import LieFlag

CLIP = 160
_LEVEL_RANK = {"flag": 0, "watch": 1}

FOOTER = (
    "These are estimates by the engine, not facts and not votes. "
    "Check the claim, do not just trust the number."
)
HEADER = "Engine notes on the claims in the drafts (advisory):"


def _clip(text: str, limit: int = CLIP) -> str:
    one = re.sub(r"\s+", " ", text or "").strip().replace('"', "'")
    if len(one) <= limit:
        return one
    return one[: limit - 3].rstrip() + "..."


def _score(flag: LieFlag) -> float | None:
    """Best single number for how true the claim looks (0 false, 1 true)."""
    for value in (flag.probe_score, flag.behaviour_score, flag.track_record):
        if value is not None:
            return value
    return None


def _claim_no(claim_id: str) -> int:
    m = re.search(r"\d+", claim_id or "")
    return int(m.group()) if m else 0


def _sort_key(flag: LieFlag) -> tuple:
    s = _score(flag)
    return (
        _LEVEL_RANK.get(flag.level, 9),
        0.5 if s is None else s,
        flag.seat_no,
        _claim_no(flag.claim_id),
        flag.claim_id,
    )


def _live(flags: list[LieFlag]) -> list[LieFlag]:
    return [f for f in flags if f.level in _LEVEL_RANK]


def _estimate(flag: LieFlag) -> str:
    word = "shaky" if flag.level == "flag" else "a bit shaky"
    s = _score(flag)
    return f"engine reads it as {word} ({s:.2f})" if s is not None else f"engine reads it as {word}"


def notes_for_seat(
    flags: list[LieFlag],
    seat_no: int,
    letter_of: dict[int, str],
    max_lines: int = 6,
) -> str:
    """Text block for the prompt of seat `seat_no`. Empty when nothing is flagged or watched."""
    if max_lines <= 0:
        return ""
    lines: list[str] = []
    for f in sorted(_live(flags), key=_sort_key):
        if len(lines) >= max_lines:
            break
        if f.seat_no == seat_no:
            lines.append(f'Your claim {f.claim_id}: "{_clip(f.text)}" - {_estimate(f)}. Re-check it.')
            continue
        letter = letter_of.get(f.seat_no)
        if not letter:
            continue  # no anonymous letter: say nothing rather than leak a seat number
        lines.append(f'Draft {letter}, claim {f.claim_id}: "{_clip(f.text)}" - {_estimate(f)}.')
    if not lines:
        return ""
    return "\n".join([HEADER, *lines, FOOTER])


def tribunal_targets(flags: list[LieFlag], seat_no: int, k: int = 3) -> list[LieFlag]:
    """That seat's worst claims, flag before watch, for the cross-examiner to ask about."""
    if k <= 0:
        return []
    mine = [f for f in _live(flags) if f.seat_no == seat_no]
    return sorted(mine, key=_sort_key)[:k]


def question_hint(flag: LieFlag) -> str:
    return f'Ask for the evidence behind: "{_clip(flag.text)}"'
