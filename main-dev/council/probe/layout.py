"""The one place that builds the text whose activations the deception probe reads.

Why this exists: training text and live scoring text were built in different places
(trainer.pair_messages: one bare user message; run_pipeline.messages_for: system + user task +
assistant draft, rendered as "<role>: <content>" lines), so a probe trained on one did not
transfer to the other. Both sides call this module instead.

The text always ends with "The statement above is", so with pool="last" the vector sits on a
token where the model has just read the whole statement and is about to judge it.

Pure: no I/O, no clock, no randomness. Bump LAYOUT_VERSION when any text here changes, so a
probe trained on an old layout can be refused.
"""
from __future__ import annotations

LAYOUT_VERSION = 1

TASK_CLIP = 600
STATEMENT_CLIP = 400
TAIL = "The statement above is"


def _squeeze(text: str) -> str:
    """Every run of whitespace becomes one space; the ends are trimmed."""
    return " ".join(str(text if text is not None else "").split())


def _task_part(task: str) -> str:
    return _squeeze(task)[:TASK_CLIP]


def _statement_part(statement: str) -> str:
    return str(statement if statement is not None else "")[:STATEMENT_CLIP]


def probe_text(task: str, statement: str) -> str:
    """Question, statement, and the open sentence the model is asked to finish."""
    return f"Question: {_task_part(task)}\nStatement: {_statement_part(statement)}\n{TAIL}"


def probe_messages(task: str, statement: str) -> list[dict]:
    """The same text as one user message, for sources that take messages."""
    return [{"role": "user", "content": probe_text(task, statement)}]


def statement_text(statement: str) -> str:
    """Task-free variant, for statements that have no question."""
    return f"Statement: {_statement_part(statement)}\n{TAIL}"


__all__ = ["LAYOUT_VERSION", "probe_text", "probe_messages", "statement_text"]
