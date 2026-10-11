"""Word-based memory recall fallback (BM25). Pure: no I/O, no clock, no randomness.

Used when no embedding model is installed. Stdlib only.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_WORD = re.compile(r"\w+")

STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
        "has", "have", "in", "is", "it", "its", "of", "on", "or", "that", "the",
        "this", "to", "was", "were", "will", "with", "not", "no", "so", "if",
        "then", "than", "do", "does", "did", "we", "you", "they", "he", "she",
    }
)


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens. Identifiers like snake_case yield the whole and its parts.

    Stop words and 1-char tokens are dropped. Order follows the text; duplicates kept.
    """
    if not text:
        return []
    out: list[str] = []
    for word in _WORD.findall(text.lower()):
        candidates = [word]
        if "_" in word:
            candidates.extend(p for p in word.split("_") if p)
        for tok in candidates:
            if len(tok) < 2 or tok in STOP_WORDS:
                continue
            if tok.strip("_") == "":
                continue
            out.append(tok)
    return out


class BM25:
    """Okapi BM25 over a fixed list of documents."""

    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._tfs: list[Counter[str]] = [Counter(tokenize(d)) for d in docs]
        self._lens: list[int] = [sum(tf.values()) for tf in self._tfs]
        n = len(self._tfs)
        self._avgdl: float = (sum(self._lens) / n) if n else 0.0
        df: Counter[str] = Counter()
        for tf in self._tfs:
            df.update(tf.keys())
        self._idf: dict[str, float] = {
            term: math.log(1.0 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()
        }

    def __len__(self) -> int:
        return len(self._tfs)

    def score(self, query: str) -> list[float]:
        """One score per doc, same order as docs. 0.0 when nothing matches."""
        scores = [0.0] * len(self._tfs)
        terms = set(tokenize(query))
        if not terms or not self._tfs:
            return scores
        for term in terms:
            idf = self._idf.get(term)
            if idf is None:
                continue
            for i, tf in enumerate(self._tfs):
                f = tf.get(term, 0)
                if f == 0:
                    continue
                norm = 1.0
                if self._avgdl > 0:
                    norm = 1.0 - self.b + self.b * (self._lens[i] / self._avgdl)
                scores[i] += idf * (f * (self.k1 + 1.0)) / (f + self.k1 * norm)
        return scores

    def top(self, query: str, k: int = 8, min_score: float = 0.0) -> list[tuple[int, float]]:
        """(doc index, score), best first, ties by lower index. Zero-score docs never returned."""
        if k <= 0:
            return []
        ranked = [
            (i, s) for i, s in enumerate(self.score(query)) if s > 0.0 and s >= min_score
        ]
        ranked.sort(key=lambda t: (-t[1], t[0]))
        return ranked[:k]


def recall(query: str, entries: list[tuple[str, str]], k: int = 8) -> list[tuple[str, float]]:
    """Top k (entry_id, score) with score scaled to 0..1 by the best score. Empty on no match."""
    if not entries or k <= 0:
        return []
    hits = BM25([text for _, text in entries]).top(query, k=k)
    if not hits:
        return []
    best = hits[0][1]
    if best <= 0.0:
        return []
    return [(entries[i][0], s / best) for i, s in hits]
