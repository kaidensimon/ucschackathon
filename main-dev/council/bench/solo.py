"""Solo pass (spec 18.1, 18.2, 18.4). One model, max reasoning, same prompt in every mode.

The solo answer doubles as the council's round-0 draft (to_draft), so the cache hits.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Optional

from council.bench.graders import normalize
from council.core.schemas import BenchTask, CallResult, CallSpec, Draft, ModelEntry

FORMAT_INSTRUCTION: dict[str, str] = {
    "mcq": "Think it through, then end your reply with a final line exactly of the form "
           "\"ANSWER: <letter>\" (one letter, for example \"ANSWER: B\").",
    "numeric": "Think it through, then end your reply with a final line exactly of the form "
               "\"ANSWER: <value>\" (the number only, no units).",
    "exact": "Think it through, then end your reply with a final line exactly of the form "
             "\"ANSWER: <value>\" (the short final answer only).",
}
DEFAULT_INSTRUCTION = "End your reply with a final line of the form \"ANSWER: <your final answer>\"."

_ANSWER_LINE = re.compile(r"^\W*answer\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def format_instruction(answer_type: str) -> str:
    return FORMAT_INSTRUCTION.get(answer_type, DEFAULT_INSTRUCTION)


_HAS_LETTER = re.compile(r"^\s*\(?[A-Za-z][).:]\s")


def _lettered(choices: list) -> list[str]:
    """Options as "A. text". The answer is asked for as a letter, so every option must show one.
    (On the box the options were listed bare and a model answered with the option text.)"""
    texts = [str(c) for c in choices]
    if texts and all(_HAS_LETTER.match(t) for t in texts):
        return texts
    return [f"{chr(ord('A') + i)}. {t}" for i, t in enumerate(texts)]


def solo_prompt(task: BenchTask) -> list[dict]:
    """Messages are the same for every bench mode."""
    parts = [task.prompt.strip()]
    if task.choices:
        parts.append("\n".join(_lettered(task.choices)))
    parts.append(format_instruction(task.answer_type))
    return [{"role": "user", "content": "\n\n".join(parts)}]


def solo_schema() -> dict:
    return Draft.model_json_schema()


def build_solo_call(task: BenchTask, model: ModelEntry, bench_cfg, seed: int = 0,
                    sample: int = 0, mock_truth: bool = False) -> CallSpec:
    meta: dict[str, Any] = {"task_id": task.id, "answer_type": task.answer_type}
    if mock_truth:
        meta["mock_truth"] = task.answer
    sampling = model.sampling or {}
    return CallSpec(
        model_id=model.id,
        call_id=f"bench:{task.id}:{model.id}:{sample}",
        purpose="bench.solo",
        messages=solo_prompt(task),
        # No JSON schema: a schema makes a model without a thinking mode answer in a dozen tokens
        # with no working at all. Free text ending in the ANSWER line lets every model reason.
        json_schema=None,
        reasoning="max",
        max_output_tokens=bench_cfg.solo_max_output_tokens,
        max_reasoning_tokens=bench_cfg.solo_max_reasoning_tokens,
        temperature=sampling.get("temperature"),
        top_p=sampling.get("top_p"),
        seed=seed + sample,
        priority="batch",
        cacheable=True,
        meta=meta,
    )


def _last_answer_line(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    found = _ANSWER_LINE.findall(text)
    return found[-1].strip() if found else None


def _parsed_dict(result: CallResult) -> Optional[dict]:
    p = result.parsed
    if isinstance(p, Draft):
        return p.model_dump()
    return p if isinstance(p, dict) else None


def _raw_answer(result: CallResult) -> Optional[str]:
    """Un-normalized answer text, or None."""
    p = _parsed_dict(result)
    if p:
        key = p.get("answer_key")
        if isinstance(key, str) and key.strip():
            return key.strip()
    raw = _last_answer_line(result.content)
    if raw:
        return raw
    if p and isinstance(p.get("answer"), str):
        return _last_answer_line(p["answer"])
    return None


def extract_answer(result: CallResult, answer_type: str) -> Optional[str]:
    """Normalized answer key: parsed answer_key first, else the last ANSWER: line."""
    if result is None or not result.ok:
        return None
    raw = _raw_answer(result)
    if raw is None:
        return None
    key = normalize(raw, answer_type)
    return key or None


def to_draft(result: CallResult) -> Optional[Draft]:
    """Use a solo output as a round-0 draft (18.4). None when there is no usable answer."""
    if result is None or not result.ok:
        return None
    p = _parsed_dict(result)
    if p is not None:
        try:
            draft = Draft.model_validate(p)
            if draft.answer.strip():
                return draft
        except Exception:
            pass
    raw = _raw_answer(result)
    if raw is None:
        return None
    return Draft(answer=raw, answer_key=raw)


def majority_answer(keys: list[Optional[str]]) -> Optional[str]:
    """Most common non-null key. Ties go to the one seen first."""
    valid = [k for k in keys if k]
    if not valid:
        return None
    counts = Counter(valid)
    best = max(counts.values())
    for k in valid:
        if counts[k] == best:
            return k
    return None
