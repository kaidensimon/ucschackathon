"""Regex matching with a time limit, for patterns written by a model.

`re` has no timeout and holds the interpreter lock while it matches, so a pattern with
catastrophic backtracking, such as (a+)+$, freezes every thread of the process, not only the
caller. A thread cannot be stopped either. So a pattern that can backtrack is matched in a
child process, which is killed at the time limit.

A pattern with none of * + { ? | cannot backtrack badly; it is matched in this process.

This file is also the child program: `python -I safe_regex.py` reads one JSON job on stdin
and writes one JSON answer on stdout. It imports the standard library only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

MAX_PATTERN_CHARS = 1000
MAX_TEXT_CHARS = 4_000_000
DEFAULT_TIMEOUT_S = 5.0
TIMEOUT = "pattern timed out"

_RISKY = set("*+{?|")


def is_simple(pattern: str) -> bool:
    """True when the pattern has no repeat and no alternation, so it runs in linear time."""
    return not (_RISKY & set(pattern))


def _check(pattern: str) -> Optional[str]:
    if not isinstance(pattern, str):
        return "bad pattern: not text"
    if len(pattern) > MAX_PATTERN_CHARS:
        return f"bad pattern: longer than {MAX_PATTERN_CHARS} characters"
    try:
        re.compile(pattern)
    except (re.error, RecursionError, OverflowError) as e:
        return f"bad pattern: {e}"
    return None


def _grep_walk(root: str, pattern: str, ignore: list[str], max_hits: int, max_bytes: int) -> list[str]:
    rx = re.compile(pattern)
    base = Path(root)
    skip = set(ignore)
    hits: list[str] = []
    stack = [base]
    while stack and len(hits) < max_hits:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir(), reverse=True)
        except OSError:
            continue
        for p in entries:
            if p.name in skip:
                continue
            if p.is_dir() and not p.is_symlink():
                stack.append(p)
            elif p.is_file():
                try:
                    with p.open("rb") as f:
                        raw = f.read(max_bytes)
                except OSError:
                    continue
                if b"\0" in raw[:2048]:
                    continue
                rel = p.relative_to(base).as_posix()
                for n, ln in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
                    if rx.search(ln):
                        hits.append(f"{rel}:{n}: {ln.strip()[:200]}")
                        if len(hits) >= max_hits:
                            break
            if len(hits) >= max_hits:
                break
    return hits


def _do(job: dict):
    if job["op"] == "search":
        return re.search(job["pattern"], job["text"], int(job.get("flags", 0))) is not None
    if job["op"] == "grep":
        return _grep_walk(job["root"], job["pattern"], job["ignore"], job["max_hits"], job["max_bytes"])
    raise ValueError(f"unknown op: {job.get('op')!r}")


def _in_child(job: dict, timeout_s: float):
    """(answer, error). Runs the job in a child interpreter and kills it at the time limit."""
    extra: dict = {}
    if os.name == "nt":
        extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME") if k in os.environ}
    try:
        proc = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).resolve())],
            input=json.dumps(job).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=max(0.1, float(timeout_s)), env=env, **extra,
        )
    except subprocess.TimeoutExpired:
        return None, TIMEOUT
    except (OSError, ValueError) as e:
        return None, f"cannot run the pattern: {e}"
    try:
        answer = json.loads(proc.stdout.decode("utf-8"))
    except ValueError:
        return None, "cannot run the pattern: the matcher gave no answer"
    if "error" in answer:
        return None, f"bad pattern: {answer['error']}"
    return answer.get("ok"), None


def search(pattern: str, text: str, flags: int = 0,
           timeout_s: float = DEFAULT_TIMEOUT_S) -> tuple[Optional[bool], Optional[str]]:
    """(found, None), or (None, error). The error starts with "bad pattern" or is TIMEOUT."""
    err = _check(pattern)
    if err:
        return None, err
    if len(text) > MAX_TEXT_CHARS:
        return None, f"text longer than {MAX_TEXT_CHARS} characters"
    if is_simple(pattern):
        return re.search(pattern, text, flags) is not None, None
    found, err = _in_child({"op": "search", "pattern": pattern, "text": text, "flags": int(flags)},
                           timeout_s)
    return (None, err) if err else (bool(found), None)


def grep(root: Path, pattern: str, ignore: Iterable[str] = (), max_hits: int = 40,
         max_bytes: int = 1_000_000, timeout_s: float = 10.0) -> tuple[Optional[list[str]], Optional[str]]:
    """Lines under root that match: (["rel:line: text", ...], None), or (None, error)."""
    err = _check(pattern)
    if err:
        return None, err
    job = {"op": "grep", "root": str(root), "pattern": pattern, "ignore": sorted(ignore),
           "max_hits": int(max_hits), "max_bytes": int(max_bytes)}
    if is_simple(pattern):
        return _do(job), None
    hits, err = _in_child(job, timeout_s)
    return (None, err) if err else (list(hits or []), None)


def _child_main() -> None:
    try:
        out = {"ok": _do(json.loads(sys.stdin.buffer.read().decode("utf-8")))}
    except Exception as e:  # noqa: BLE001 - the parent reports it
        out = {"error": str(e)}
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    _child_main()
