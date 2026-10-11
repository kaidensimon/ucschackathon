"""Task profiler (spec section 8): heuristic, nearest-neighbour and clerk profiles, plus merge."""

from __future__ import annotations

import math
import re
from typing import Any, Optional

from council.core.schemas import (
    CATEGORIES,
    DIFFICULTIES,
    NEEDS,
    CallSpec,
    TaskProfile,
)

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "code": ("code", "function", "bug", "python", "javascript", "typescript", "implement", "compile",
             "api", "script", "class", "refactor", "debug", "program", "sql", "regex", "react"),
    "math": ("math", "equation", "integral", "derivative", "prove", "proof", "calculate", "sum",
             "probability", "algebra", "geometry", "theorem", "solve", "matrix", "number"),
    "logic": ("logic", "puzzle", "deduce", "riddle", "if and only if", "syllogism", "paradox",
              "constraint", "truth", "valid argument"),
    "science": ("physics", "chemistry", "biology", "molecule", "energy", "cell", "quantum",
                "experiment", "reaction", "astronomy", "science"),
    "knowledge": ("who", "when", "where", "history", "capital", "define", "explain", "fact",
                  "what is", "country", "founded"),
    "reading": ("passage", "article", "summarize", "summary", "document", "text below", "read",
                "paragraph", "excerpt", "comprehension"),
    "writing": ("write", "essay", "poem", "story", "email", "draft", "rewrite", "blog", "letter",
                "tone", "edit"),
    "planning": ("plan", "design", "architecture", "roadmap", "strategy", "schedule", "steps",
                 "outline", "organize", "milestone"),
}

_HARD_CUES = ("prove", "optimize", "complex", "architecture", "distributed", "rigorous", "formal",
              "edge case", "tradeoff", "trade-off", "from scratch", "multi-step", "hard")
_EASY_CUES = ("simple", "quick", "basic", "just", "easy", "briefly", "short")

_BUILD_CUES = ("build", "implement", "create files", "create a file", "create the files", "scaffold",
               "generate files", "write the code", "make an app", "develop")
_PLAN_CUES = ("plan", "design", "architecture", "roadmap", "blueprint", "strategy")

_VISION_CUES = ("image", "screenshot", "photo", "picture", "diagram", "figure", "png", "jpg")
_LONG_CUES = ("long document", "entire document", "whole document", "full document", "long text",
              "entire codebase", "whole codebase", "long transcript", "book")
_MULTI_CUES = ("translate", "translation", "in french", "in spanish", "in german", "in chinese",
               "in japanese", "multilingual", "in hindi", "in arabic")
_EXEC_CUES = ("run the code", "execute", "run this", "run it", "compute exactly", "unit test",
              "run tests")


def _count(text: str, words: tuple[str, ...]) -> int:
    n = 0
    for w in words:
        if " " in w or "-" in w:
            n += text.count(w)
        else:
            n += len(re.findall(r"\b" + re.escape(w) + r"\w*", text))
    return n


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    clean = {k: float(v) for k, v in weights.items() if k in CATEGORIES and v and v > 0}
    total = sum(clean.values())
    if total <= 0:
        return {"knowledge": 1.0}
    return {k: v / total for k, v in clean.items()}


def heuristic_profile(task: str) -> TaskProfile:
    text = (task or "").lower()
    raw = {cat: float(_count(text, words)) for cat, words in _KEYWORDS.items()}
    categories = _normalize(raw)

    n_words = len(text.split())
    score = 0
    if n_words > 200:
        score += 2
    elif n_words > 60:
        score += 1
    score += min(2, _count(text, _HARD_CUES))
    score -= min(2, _count(text, _EASY_CUES))
    if n_words < 12:
        score -= 1
    difficulty = "hard" if score >= 2 else "easy" if score <= -1 else "medium"

    needs: list[str] = []
    if any(c in text for c in _VISION_CUES):
        needs.append("vision")
    if any(c in text for c in _EXEC_CUES):
        needs.append("code_execution")
    if n_words > 1500 or any(c in text for c in _LONG_CUES):
        needs.append("long_context")
    if any(c in text for c in _MULTI_CUES):
        needs.append("multilingual")

    if any(c in text for c in _BUILD_CUES):
        deliverable = "build"
    elif any(c in text for c in _PLAN_CUES):
        deliverable = "plan"
    else:
        deliverable = "answer"

    top = max(categories, key=categories.get)
    return TaskProfile(
        categories=categories,
        difficulty=difficulty,
        needs=needs,
        deliverable=deliverable,
        rationale=f"heuristic: {top}, {difficulty}, {deliverable}",
    )


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def knn(embedding: list[float], calibration: list[dict], k: int = 30) -> list[tuple[float, dict]]:
    scored = []
    for item in calibration or []:
        emb = item.get("embedding") or []
        scored.append((cosine(embedding, emb), item))
    scored.sort(key=lambda p: p[0], reverse=True)
    return scored[: max(0, k)]


def profile_from_neighbours(neigh: list[tuple[float, dict]]) -> dict:
    cat_w: dict[str, float] = {}
    diff_w: dict[str, float] = {}
    for sim, item in neigh or []:
        w = max(float(sim), 0.0)
        cat = item.get("category")
        if cat in CATEGORIES:
            cat_w[cat] = cat_w.get(cat, 0.0) + w
        diff = item.get("difficulty")
        if diff in DIFFICULTIES:
            diff_w[diff] = diff_w.get(diff, 0.0) + w
    if sum(cat_w.values()) <= 0 and neigh:
        # all similarities zero: fall back to equal weights
        for _, item in neigh:
            cat = item.get("category")
            if cat in CATEGORIES:
                cat_w[cat] = cat_w.get(cat, 0.0) + 1.0
            diff = item.get("difficulty")
            if diff in DIFFICULTIES:
                diff_w[diff] = diff_w.get(diff, 0.0) + 1.0
    categories = _normalize(cat_w) if cat_w else {}
    difficulty = max(diff_w, key=diff_w.get) if diff_w else "medium"
    return {"categories": categories, "difficulty": difficulty}


def build_profile_call(run_id: str, clerk_model_id: str, task: str, brief: Any = None) -> CallSpec:
    schema = {
        "type": "object",
        "properties": {
            "needs": {"type": "array", "items": {"type": "string", "enum": list(NEEDS)}},
            "deliverable": {"type": "string", "enum": ["answer", "plan", "build"]},
            "categories": {
                "type": "object",
                "properties": {c: {"type": "number"} for c in CATEGORIES},
            },
        },
        "required": ["needs", "deliverable", "categories"],
    }
    brief_text = ""
    if brief:
        brief_text = brief if isinstance(brief, str) else str(brief)
    user = f"Task:\n{task}\n"
    if brief_text:
        user += f"\nBrief:\n{brief_text}\n"
    user += (
        "\nClassify the task. Give needs (subset of "
        f"{list(NEEDS)}), deliverable (answer, plan or build), and category weights over "
        f"{list(CATEGORIES)} that sum to 1."
    )
    return CallSpec(
        model_id=clerk_model_id,
        run_id=run_id,
        purpose="profile",
        messages=[
            {"role": "system", "content": "You are a task classifier. Reply with JSON only."},
            {"role": "user", "content": user},
        ],
        json_schema=schema,
        reasoning="off",
        max_output_tokens=300,
        temperature=0.0,
        timeout_s=60.0,
    )


def _blend(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    keys = set(a) | set(b)
    return {k: 0.5 * a.get(k, 0.0) + 0.5 * b.get(k, 0.0) for k in keys}


def merge_profiles(
    heuristic: TaskProfile, clerk: Optional[dict], neighbour: Optional[dict]
) -> TaskProfile:
    clerk_cats = _normalize(clerk.get("categories") or {}) if clerk and clerk.get("categories") else None
    neigh_cats = (
        _normalize(neighbour.get("categories") or {})
        if neighbour and neighbour.get("categories")
        else None
    )
    sources = [c for c in (clerk_cats, neigh_cats) if c]
    if len(sources) == 2:
        cats = _blend(sources[0], sources[1])
    elif len(sources) == 1:
        cats = sources[0]
    else:
        cats = dict(heuristic.categories)
    cats = _normalize(cats)

    difficulty = heuristic.difficulty
    if neighbour and neighbour.get("difficulty") in DIFFICULTIES:
        idx = (DIFFICULTIES.index(heuristic.difficulty) + DIFFICULTIES.index(neighbour["difficulty"])) / 2
        difficulty = DIFFICULTIES[int(idx + 0.5)]

    needs = list(heuristic.needs)
    deliverable = heuristic.deliverable
    if clerk:
        for n in clerk.get("needs") or []:
            if n in NEEDS and n not in needs:
                needs.append(n)
        if clerk.get("deliverable") in ("answer", "plan", "build"):
            deliverable = clerk["deliverable"]

    parts = ["heuristic"]
    if clerk_cats or clerk:
        parts.append("clerk")
    if neigh_cats:
        parts.append("neighbours")
    return TaskProfile(
        categories=cats,
        difficulty=difficulty,
        needs=needs,
        deliverable=deliverable,
        embedding=list(heuristic.embedding),
        rationale="merged: " + "+".join(parts),
    )
