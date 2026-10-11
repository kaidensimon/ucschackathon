"""Chronicle recall (spec 15.6). Pure functions, no I/O.

Imports types from council.core.schemas; never redefines them.
"""

from __future__ import annotations

import hashlib
import math
import re

from council.chronicle import bm25
from council.core.schemas import ChronicleEntry

STATUS_WEIGHT: dict[str, float] = {"active": 1.0, "provisional": 0.6, "contested": 0.3}
_NEVER_STATUSES = frozenset({"superseded", "retracted"})
_NO_EMBEDDING_SIMILARITY = 0.5
_TOKEN = re.compile(r"\w+")


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. 0.0 on empty input, length mismatch, or a zero vector."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def in_scope(entry: ChronicleEntry, project: str | None, categories: list[str]) -> bool:
    """global always; project:<hash> must match the project; category:<cat> must be in categories."""
    scope = entry.scope
    if scope == "global":
        return True
    if scope.startswith("project:"):
        return project is not None and scope == f"project:{project}"
    if scope.startswith("category:"):
        return scope[len("category:"):] in categories
    return False


def rank(
    entries: list[ChronicleEntry],
    query_embedding: list[float],
    project: str | None,
    categories: list[str],
    k: int = 8,
) -> list[ChronicleEntry]:
    """Top k in-scope entries by cosine * status weight. Superseded and retracted never returned.

    Entries without an embedding get similarity 0.5.
    """
    scored: list[tuple[float, int, ChronicleEntry]] = []
    for idx, entry in enumerate(entries):
        if entry.status in _NEVER_STATUSES:
            continue
        weight = STATUS_WEIGHT.get(entry.status)
        if weight is None:
            continue
        if not in_scope(entry, project, categories):
            continue
        if entry.embedding:
            similarity = cosine(query_embedding, entry.embedding)
        else:
            similarity = _NO_EMBEDDING_SIMILARITY
        scored.append((similarity * weight, idx, entry))
    # Highest score first; original order breaks ties so the result is deterministic.
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [entry for _, _, entry in scored[: max(0, k)]]


def rank_text(
    entries: list[ChronicleEntry],
    query_text: str,
    project: str | None,
    categories: list[str],
    k: int = 8,
) -> list[ChronicleEntry]:
    """Word-match fallback for when no embedding exists: BM25 over the statements, times status weight.

    Same filters as `rank` (superseded and retracted never, scope must match). Entries that
    share no word with the query are not returned.
    """
    live: list[ChronicleEntry] = []
    for entry in entries:
        if entry.status in _NEVER_STATUSES or entry.status not in STATUS_WEIGHT:
            continue
        if in_scope(entry, project, categories):
            live.append(entry)
    pairs = [(str(i), entry.statement) for i, entry in enumerate(live)]
    hits = bm25.recall(query_text, pairs, k=k) if k > 0 else []
    scored = [(score * STATUS_WEIGHT[live[int(i)].status], int(i)) for i, score in hits]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [live[i] for _, i in scored[: max(0, k)]]


def render_record(entries: list[ChronicleEntry]) -> str:
    """One line per entry: "[ACTIVE 0.90] statement". "(no prior record)" when empty."""
    if not entries:
        return "(no prior record)"
    lines = []
    for entry in entries:
        lines.append(f"[{entry.status.upper()} {entry.confidence:.2f}] {entry.statement}")
    return "\n".join(lines)


def keyword_embedding(text: str, dim: int = 64) -> list[float]:
    """Deterministic hashed bag-of-words vector (mock mode). Uses sha256, so it is stable across runs."""
    if dim <= 0:
        return []
    vec = [0.0] * dim
    for token in _TOKEN.findall(text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:8], "big") % dim
        vec[bucket] += 1.0
    return vec
