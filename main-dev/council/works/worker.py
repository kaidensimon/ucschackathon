"""Worker calls (spec 12.1, 12.2).

One generation per attempt. The engine writes files and runs checks; this module only
plans the attempt, builds the call, parses the reply and words the retry feedback.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from council.chamber.prompts import render
from council.core.schemas import CallResult, CallSpec, CheckResult, MicroTask, WorkerOutput

_FIRST_TEMP = 0.2
_RETRY_TEMP = 0.6
_SENIOR_TEMP = 0.2
_MAX_PREVIOUS_CHARS = 6000


def attempt_plan(attempt: int, worker_model: str, senior_model: Optional[str]) -> tuple[str, float]:
    """(model id, temperature) for an attempt number, per the 12.2 table."""
    if attempt <= 1:
        return (worker_model, _FIRST_TEMP)
    if attempt == 2:
        return (worker_model, _RETRY_TEMP)
    return (senior_model or worker_model, _SENIOR_TEMP)


def _plain(item: Any) -> Any:
    if hasattr(item, "model_dump"):
        return item.model_dump(exclude_none=True)
    return item


def _check_text(check: Any) -> str:
    data = _plain(check)
    if not isinstance(data, dict):
        return str(data)
    keep = {k: v for k, v in data.items() if k in ("type", "cmd", "path", "pattern", "language", "rubric", "expect_exit")}
    return json.dumps(keep, separators=(",", ":"), ensure_ascii=False)


def _check_label(res: CheckResult) -> str:
    parts = []
    if res.type:
        parts.append(str(res.type))
    elif res.check is not None:
        parts.append(str(res.check.type))
    if res.check is not None:
        c = res.check
        detail = c.cmd or c.path or c.rubric or ""
        if c.pattern:
            detail = f"{detail} /{c.pattern}/".strip()
        if detail:
            parts.append(detail)
    if res.check_id:
        parts.append(f"[{res.check_id}]")
    return " ".join(parts) or "check"


def feedback_text(failed: list[CheckResult], max_lines: int = 60) -> str:
    """Words for the retry prompt: each failing check, then the tail of its output, capped by lines."""
    if not failed:
        return ""
    lines: list[str] = []
    for res in failed:
        head = f"FAILED: {_check_label(res)}"
        if res.exit_code is not None:
            head += f" (exit {res.exit_code})"
        lines.append(head)
        if res.error:
            lines.append(f"error: {res.error}")
        if res.output_tail:
            lines.extend(res.output_tail.splitlines())
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return "\n".join(lines)


def build_worker_call(
    run_id: str,
    task: MicroTask,
    attempt: int,
    model_id: str,
    temperature: float,
    feedback: Optional[str],
    previous_output: Optional[str],
    interfaces: list,
) -> CallSpec:
    retry = ""
    if attempt > 1 and (feedback or previous_output):
        bits = []
        if feedback:
            bits.append(f"YOUR LAST ATTEMPT FAILED THESE CHECKS:\n{feedback}")
        if previous_output:
            prev = previous_output
            if len(prev) > _MAX_PREVIOUS_CHARS:
                prev = prev[:_MAX_PREVIOUS_CHARS] + "\n...(cut)"
            bits.append(f"YOUR LAST OUTPUT:\n{prev}")
        bits.append("Fix the problems. Reply with the full JSON object again.")
        retry = "\n".join(bits)

    ifaces = interfaces if interfaces else task.context.interfaces
    files = [
        {"path": f.path, "content": f.content, "excerpt": f.is_excerpt}
        for f in task.context.files
    ]
    prompt = render(
        "worker",
        write_set=task.write_set,
        goal=task.goal,
        interfaces=[_plain(i) for i in ifaces],
        context_files=files,
        output_contract=task.output_contract,
        acceptance=[_plain(c) if not hasattr(c, "type") else json.loads(_check_text(c)) for c in task.acceptance],
        retry_feedback=retry,
    )
    return CallSpec(
        model_id=model_id,
        call_id=f"{run_id}:w:{task.id}:{attempt}",
        run_id=run_id,
        purpose="worker",
        messages=[{"role": "user", "content": prompt}],
        json_schema=WorkerOutput.model_json_schema(),
        max_output_tokens=int(task.budget.max_output_tokens),
        temperature=temperature,
        priority="interactive",
        stream=True,
        meta={"task_id": task.id, "attempt": attempt},
    )


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


_NOT_A_REASON = {"", "true", "false", "none", "null", "no", "yes", "n/a", "na", "0", "1", "-"}


def _clean_blocked(output: WorkerOutput) -> WorkerOutput:
    """Small models fill every field of a forced JSON shape, so "blocked" arrives as "true" or
    "none" next to perfectly good files. Work that was delivered is not blocked, and a word
    that explains nothing is not a reason."""
    blocked = output.blocked
    if blocked is None:
        return output
    if output.ops or str(blocked).strip().lower() in _NOT_A_REASON:
        return output.model_copy(update={"blocked": None})
    return output


def parse_output(result: CallResult) -> Optional[WorkerOutput]:
    """WorkerOutput from a call result, or None when the reply is not usable."""
    if result is None or not result.ok:
        return None
    data = result.parsed
    if data is None:
        try:
            data = json.loads(_strip_fence(result.content or ""))
        except (ValueError, TypeError):
            return None
    if isinstance(data, WorkerOutput):
        return data
    if not isinstance(data, dict):
        return None
    try:
        return _clean_blocked(WorkerOutput.model_validate(data))
    except Exception:
        return None


__all__ = ["attempt_plan", "build_worker_call", "parse_output", "feedback_text"]
