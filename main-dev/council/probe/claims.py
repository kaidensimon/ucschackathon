"""Cut a seat's answer into checkable claims for the lie detector. Pure: no I/O, no clock, no randomness."""

from __future__ import annotations

import re
from typing import Any

from council.core.schemas_v15 import ClaimSpan

_FENCE = re.compile(r"^\s*(```|~~~)")
_LIST_ITEM = re.compile(r"^(\s*)([-*+•]|\d+[.)])\s+")
_SENT_BREAK = re.compile(r"(?<=[.!?])[\"')\]*_]*(\s+)(?=[\"'(\[`*_]?[A-Z0-9])")
_ABBREV = {"e.g", "i.e", "etc", "vs", "dr", "mr", "mrs", "ms", "fig", "no", "approx", "cf", "al"}
_TRAIL_MARKUP = "*_\"')] \t"

# Meta talk and pure hedges: nothing to fact-check in these.
_META = [
    re.compile(p, re.I)
    for p in (
        r"^(here is|here's|here are|below is|below are)\b",
        r"^(let me|let's|lets|allow me to)\b",
        r"^(i|we)\s+(think|believe|feel|suggest|propose|guess)\s+(that\s+)?we\s+(should|could|need to|must)\s+(discuss|talk|consider|look|think|review|decide)",
        r"^(i|we)\s+(will|shall|am going to|are going to|'ll)\s+(now\s+)?(discuss|explain|describe|outline|summari[sz]e|walk|go)",
        r"^(in summary|in conclusion|to summari[sz]e|to conclude|overall|hope this helps|i hope this helps)\b",
        r"^(as an ai|sure|certainly|of course|okay|ok|great question)\b[,!. ]*$",
        r"^(as an ai|sure|certainly|of course|great question)[,!]",
        r"^(thanks|thank you)\b",
    )
]

_FACT_VERB = re.compile(
    r"\b(is|are|was|were|returns?|equals?|equal|has|have|had|contains?|means?|requires?|causes?|produces?)\b", re.I
)
_NUMBER = re.compile(r"\d")
_NAMED = re.compile(r"`[^`]+`|\b[A-Z][a-z]+[A-Z]\w*|\b[a-z]+_[a-z_]+\b|\w+\(\)")


def _norm_key(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(".!;:,").lower()


def _units(answer: str) -> list[tuple[int, int]]:
    """Paragraphs and list items as (start, end) spans in the answer. Fenced code, headings and tables dropped."""
    units: list[tuple[int, int]] = []
    cur: list[Any] | None = None  # [start, end, is_list]
    in_code = False

    def close() -> None:
        nonlocal cur
        if cur is not None:
            units.append((cur[0], cur[1]))
        cur = None

    pos = 0
    for raw in answer.splitlines(keepends=True):
        ls = pos
        pos += len(raw)
        line = raw.rstrip("\r\n")
        body = line.rstrip()
        if _FENCE.match(line):
            close()
            in_code = not in_code
            continue
        if in_code:
            continue
        stripped = body.lstrip()
        if not stripped:
            close()
            continue
        if stripped.startswith("#") or stripped.startswith("|"):
            close()
            continue
        m = _LIST_ITEM.match(body)
        if m:
            close()
            cur = [ls + m.end(), ls + len(body), True]
            continue
        indented = body != stripped
        if cur is not None and (not cur[2] or indented):
            cur[1] = ls + len(body)
        else:
            close()
            cur = [ls + (len(body) - len(stripped)), ls + len(body), False]
    close()
    return units


def _sentences(answer: str, us: int, ue: int) -> list[tuple[int, int]]:
    seg = answer[us:ue]
    spans: list[tuple[int, int]] = []
    last = 0
    for m in _SENT_BREAK.finditer(seg):
        head = seg[last : m.start(1)]
        word = re.findall(r"[A-Za-z.]+", head[-12:])
        if word and word[-1].rstrip(".").lower() in _ABBREV:
            continue
        spans.append((us + last, us + m.start(1)))
        last = m.end(1)
    spans.append((us + last, ue))
    return spans


def _is_meta(text: str) -> bool:
    t = text.strip().lstrip("*_ ").strip()
    if t.endswith(":"):
        return True
    return any(p.search(t) for p in _META)


def _score(text: str) -> float:
    s = 0.0
    if _NUMBER.search(text):
        s += 2.0
    if _NAMED.search(text) or re.search(r"(?<=[a-z,] )[A-Z][a-z]{2,}", text):
        s += 1.0
    if _FACT_VERB.search(text):
        s += 1.5
    return s


def split_claims(answer: str, max_claims: int = 8, min_chars: int = 12, max_chars: int = 300) -> list[ClaimSpan]:
    if not answer or not isinstance(answer, str) or max_claims <= 0:
        return []
    found: list[tuple[str, int, int]] = []
    seen: set[str] = set()
    for us, ue in _units(answer):
        for a, b in _sentences(answer, us, ue):
            raw = answer[a:b]
            lead = len(raw) - len(raw.lstrip())
            a += lead
            b = a + len(raw.strip())
            if b <= a:
                continue
            if answer[b - 1 : b] in "?" or answer[a:b].rstrip(_TRAIL_MARKUP).endswith("?"):
                continue
            if len(answer[a:b]) > max_chars:
                cut = answer.rfind(" ", a, a + max_chars + 1)
                if cut <= a:
                    cut = a + max_chars
                b = a + len(answer[a:cut].rstrip(" ,;\t\n"))
            text = re.sub(r"\s+", " ", answer[a:b]).strip()
            if len(text) < min_chars or _is_meta(text):
                continue
            key = _norm_key(text)
            if key in seen:
                continue
            seen.add(key)
            found.append((text, a, b))

    if len(found) > max_claims:
        ranked = sorted(range(len(found)), key=lambda i: (-_score(found[i][0]), i))
        keep = sorted(ranked[:max_claims])
        found = [found[i] for i in keep]
    return [ClaimSpan(claim_id=f"c{n}", text=t, start=a, end=b) for n, (t, a, b) in enumerate(found, 1)]


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def claims_from_draft(draft: dict | object) -> list[ClaimSpan]:
    """Use the seat's own claims list when it has one; otherwise split its answer."""
    answer = _get(draft, "answer", "") or ""
    if not isinstance(answer, str):
        answer = str(answer)
    listed = _get(draft, "claims", None)
    out: list[ClaimSpan] = []
    if isinstance(listed, (list, tuple)) and listed:
        used: set[str] = set()
        pending: list[tuple[str, str]] = []
        for item in listed:
            if isinstance(item, str):
                text, cid = item, ""
            else:
                text = _get(item, "text", "") or ""
                cid = _get(item, "id", "") or _get(item, "claim_id", "") or ""
            text = re.sub(r"\s+", " ", str(text)).strip()
            if text:
                pending.append((str(cid), text))
                if cid:
                    used.add(str(cid))
        seen: set[str] = set()
        n = 0
        for cid, text in pending:
            key = _norm_key(text)
            if key in seen:
                continue
            seen.add(key)
            if not cid:
                while True:
                    n += 1
                    if f"c{n}" not in used:
                        break
                cid = f"c{n}"
                used.add(cid)
            start = answer.find(text)
            end = start + len(text) if start >= 0 else 0
            out.append(ClaimSpan(claim_id=cid, text=text, start=max(start, 0), end=end))
        if out:
            return out
    return split_claims(answer)
