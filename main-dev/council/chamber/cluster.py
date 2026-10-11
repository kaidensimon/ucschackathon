"""Clerk step cluster_options (spec 10.5). Pure functions, no model calls here."""

from __future__ import annotations

from typing import Any, Callable, Optional

from council.core.schemas import CallSpec, Option

MAX_OPTIONS = 4

CLUSTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "options": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "holders": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["summary", "holders"],
            },
        }
    },
    "required": ["options"],
}


def _finish(groups: list[tuple[list[int], str, Optional[str]]]) -> list[Option]:
    """groups: (seats, summary, answer_key). Order, assign ids.

    More than MAX_OPTIONS distinct positions stay apart. Merging the tail into one option put
    seats that did not agree under the first tail seat's summary, and that option could then
    win the vote: an answer nobody else held, reported as the majority."""
    groups = [(sorted(s), sm, k) for s, sm, k in groups if s]
    groups.sort(key=lambda g: (-len(g[0]), g[0][0]))
    return [
        Option(id=f"o{i}", summary=sm, holders=list(s), answer_key=k)
        for i, (s, sm, k) in enumerate(groups, 1)
    ]


def cluster_closed(
    positions: dict[int, tuple[Optional[str], str]],
    answer_type: str,
    normalize: Callable[[str, str], str],
) -> list[Option]:
    by_key: dict[str, list[int]] = {}
    groups: list[tuple[list[int], str, Optional[str]]] = []
    for seat in sorted(positions):
        key, summary = positions[seat]
        if key is None:
            groups.append(([seat], summary, None))
            continue
        nk = normalize(key, answer_type)
        by_key.setdefault(nk, []).append(seat)
    for nk, seats in by_key.items():
        groups.append((seats, positions[seats[0]][1], nk))
    return _finish(groups)


def cluster_fallback(positions: dict[int, tuple[Optional[str], str]]) -> list[Option]:
    return _finish([([s], positions[s][1], positions[s][0]) for s in sorted(positions)])


def build_cluster_call(
    run_id: Optional[str],
    clerk_model_id: str,
    positions: dict[int, tuple[Optional[str], str]],
) -> CallSpec:
    lines = [f"Seat {s}: {positions[s][1]}" for s in sorted(positions)]
    prompt = (
        "Group these seat positions into at most 4 distinct options. Merge positions that "
        "give the same answer. Every seat must appear in exactly one option. Reply as JSON "
        '{"options": [{"summary": str, "holders": [seat numbers]}]}.\n\n' + "\n".join(lines)
    )
    return CallSpec(
        model_id=clerk_model_id,
        run_id=run_id,
        purpose="clerk.cluster_options",
        messages=[
            {"role": "system", "content": "You are the Clerk. You group positions. You add no opinion."},
            {"role": "user", "content": prompt},
        ],
        json_schema=CLUSTER_SCHEMA,
        reasoning="off",
        max_output_tokens=600,
        temperature=0.0,
    )


def parse_cluster_result(
    parsed: Optional[dict], positions: dict[int, tuple[Optional[str], str]]
) -> list[Option]:
    try:
        if not isinstance(parsed, dict):
            return cluster_fallback(positions)
        raw = parsed.get("options")
        if not isinstance(raw, list) or not raw:
            return cluster_fallback(positions)
        seen: set[int] = set()
        groups: list[tuple[list[int], str, Optional[str]]] = []
        for item in raw:
            if not isinstance(item, dict):
                return cluster_fallback(positions)
            holders = item.get("holders")
            if not isinstance(holders, list) or not holders:
                return cluster_fallback(positions)
            for h in holders:
                if isinstance(h, bool) or not isinstance(h, int) or h not in positions or h in seen:
                    return cluster_fallback(positions)
                seen.add(h)
            summary = item.get("summary")
            groups.append((list(holders), summary if isinstance(summary, str) else "", None))
        if seen != set(positions):
            return cluster_fallback(positions)
        return _finish(groups)
    except Exception:
        return cluster_fallback(positions)


def tally_from_options(options: list[Option]) -> dict[str, int]:
    return {o.id: len(o.holders) for o in options}


def share_of_top(options: list[Option], k: int) -> float:
    if not options or k <= 0:
        return 0.0
    return max(len(o.holders) for o in options) / k
