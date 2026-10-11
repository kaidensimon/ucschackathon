"""Acceptance checks (spec 11.2, 13.1). In-process, no model calls."""

from __future__ import annotations

import ast
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

from council.core.schemas import Check, CheckResult
from council.works import safe_regex

CommandRunner = Callable[[str, Path, float], dict]

_TAIL = 2000
MAX_FILE_BYTES = 2_000_000  # a larger file is not read: the check fails
PATTERN_TIMEOUT_S = 5.0


INVALID_ZERO_TESTS = "invalid check: the command ran zero tests"
_ZERO_TEST_RE = re.compile(
    r"\bRan 0 tests?\b|\bNO TESTS RAN\b|\bcollected 0 items\b|\bno tests ran\b",
    re.IGNORECASE,
)


_NO_TEST_DIR_RE = re.compile(r"Start directory is not importable", re.IGNORECASE)
# The runner's own summary of a real failure. Text inside an assert message does not match.
_REAL_FAIL_RE = re.compile(
    r"^FAILED \((?:failures|errors|unexpected successes)=|^=+ .*\d+ (?:failed|errors?)",
    re.MULTILINE,
)
_RAN_RE = re.compile(r"^Ran (\d+) tests?|collected (\d+) items?", re.MULTILINE)
_ZERO_EXITS = (0, 5, None)  # unittest: 0 (5 from Python 3.12), pytest: 5


def is_zero_test_output(text: str, exit_code: Optional[int] = None) -> bool:
    """True if test-runner output says no test ran (unittest "Ran 0 tests", "NO TESTS RAN";
    pytest "collected 0 items", "no tests ran"), or the test directory does not exist yet. Pure.

    Not zero-test: the runner reports failures or errors (a setUpModule that raises gives
    "Ran 0 tests" and "FAILED (errors=1)"), or it counted tests that ran. With `exit_code`
    given, a plain zero-test run must also have exited 0 or 5."""
    text = text or ""
    if _NO_TEST_DIR_RE.search(text):
        return True  # no tests/ directory yet: the command could not run any test
    if not _ZERO_TEST_RE.search(text):
        return False
    if _REAL_FAIL_RE.search(text):
        return False
    if any(int(a or b) > 0 for a, b in _RAN_RE.findall(text)):
        return False
    return exit_code in _ZERO_EXITS


def _result(check: Check, ok: bool, started: float, error: Optional[str] = None,
            output: str = "", exit_code: Optional[int] = None, level: Optional[str] = None,
            score: Optional[float] = None) -> CheckResult:
    return CheckResult(
        ok=ok,
        type=check.type,
        check=check,
        check_id=check.id,
        level=level,
        exit_code=exit_code,
        output_tail=output[-_TAIL:],
        score=score,
        error=None if ok and error is None else error,
        duration_ms=(time.perf_counter() - started) * 1000.0,
    )


def _resolve(root: Path, rel: Optional[str]) -> Optional[Path]:
    """Return the path under root, or None if it is empty or escapes root."""
    if not rel:
        return None
    try:
        base = Path(root).resolve()
        target = (base / rel).resolve()
        target.relative_to(base)
    except (ValueError, OSError):
        return None
    return target


def _parse_text(text: str, language: str, label: str) -> Optional[str]:
    """Return an error string, or None if the text parses for the language."""
    lang = (language or "").lower()
    if lang in ("python", "py"):
        try:
            ast.parse(text)
        except (SyntaxError, ValueError) as e:
            return f"python syntax error in {label}: {e}"
    elif lang == "json":
        try:
            json.loads(text)
        except ValueError as e:
            return f"json error in {label}: {e}"
    elif not text.strip():
        return f"{label} is empty"
    return None


def _language_for(path: str, language: Optional[str]) -> str:
    if language:
        return language
    ext = Path(path).suffix.lower()
    return {".py": "python", ".json": "json"}.get(ext, ext.lstrip("."))


def _read(target: Path) -> tuple[Optional[str], Optional[str]]:
    try:
        size = target.stat().st_size
        if size > MAX_FILE_BYTES:
            return None, f"file too large to check: {size} bytes, max {MAX_FILE_BYTES}"
        with target.open("rb") as f:
            return f.read(MAX_FILE_BYTES + 1).decode("utf-8"), None
    except UnicodeDecodeError:
        return None, "file is not valid UTF-8"
    except OSError as e:
        return None, f"cannot read file: {e}"


def run_check(check: Check, root: Path, command_runner: Optional[CommandRunner] = None) -> CheckResult:
    started = time.perf_counter()
    root = Path(root)
    t = check.type

    if t == "review":
        return _result(check, True, started, error="skipped:needs_model", output="skipped needs_model",
                       level="L2")

    if t == "command":
        if command_runner is None:
            return _result(check, False, started, error="no runner")
        if not check.cmd:
            return _result(check, False, started, error="command check has no cmd")
        try:
            r: dict[str, Any] = command_runner(check.cmd, root, check.timeout_s) or {}
        except Exception as e:  # runner failure is a failed check, not a crash
            return _result(check, False, started, error=f"runner error: {e}")
        if r.get("refused"):
            return _result(check, False, started, error=f"refused: {r.get('refused')}",
                           output=str(r.get("output", "")), exit_code=r.get("exit_code"))
        code = r.get("exit_code")
        ok = code == check.expect_exit
        err = None if ok else f"exit {code}, expected {check.expect_exit}"
        res = _result(check, ok, started, error=err, output=str(r.get("output", "")), exit_code=code)
        # A test command that ran nothing proves nothing, whatever its exit code was.
        if is_zero_test_output(res.output_tail, code if isinstance(code, int) else None):
            res.invalid = True
            res.ok = False
            res.error = INVALID_ZERO_TESTS
        if r.get("ms") is not None:
            try:
                res.duration_ms = float(r["ms"])
            except (TypeError, ValueError):
                pass
        return res

    # file-based checks
    if not check.path:
        return _result(check, False, started, error=f"{t} check has no path")
    target = _resolve(root, check.path)
    if target is None:
        return _result(check, False, started, error=f"path escapes root: {check.path}")

    if t == "exists":
        ok = target.exists()
        return _result(check, ok, started, error=None if ok else f"missing: {check.path}")

    if not target.is_file():
        return _result(check, False, started, error=f"missing: {check.path}")

    text, err = _read(target)
    if text is None:
        return _result(check, False, started, error=err)

    if t == "parses":
        lang = _language_for(check.path, check.language)
        e = _parse_text(text, lang, check.path)
        return _result(check, e is None, started, error=e)

    if t == "contains":
        if check.pattern is None:
            return _result(check, False, started, error="contains check has no pattern")
        # The pattern is model-written: matched with a time limit (see works/safe_regex.py).
        # Models write the pattern as plain text as often as a regex ("def f(x: int) -> dict[str, int]:"
        # is not the regex they think it is), so a literal match counts too, ignoring spacing.
        squeeze = lambda v: " ".join(str(v).split())
        if check.pattern in text or squeeze(check.pattern) in squeeze(text):
            return _result(check, True, started, error=None)
        found, perr = safe_regex.search(check.pattern, text, re.MULTILINE, PATTERN_TIMEOUT_S)
        if perr is not None:
            return _result(check, False, started, error=perr)
        return _result(check, found, started, error=None if found else f"pattern not found: {check.pattern}")

    if t == "schema":
        if check.json_schema is None:
            return _result(check, False, started, error="schema check has no json_schema")
        try:
            instance = json.loads(text)
        except ValueError as e:
            return _result(check, False, started, error=f"not JSON: {e}")
        from council.gateway.jsonschema_lite import validate
        errs = validate(instance, check.json_schema)
        return _result(check, not errs, started, error="; ".join(errs[:5]) if errs else None,
                       output="\n".join(errs))

    return _result(check, False, started, error=f"unknown check type: {t}")


def l0_structure(written: list[str], root: Path) -> list[CheckResult]:
    """Every written file exists and parses for its extension."""
    out: list[CheckResult] = []
    for rel in written:
        started = time.perf_counter()
        check = Check(type="parses", path=rel, language=_language_for(rel, None))
        target = _resolve(Path(root), rel)
        if target is None:
            res = _result(check, False, started, error=f"path escapes root: {rel}")
        elif not target.is_file():
            res = _result(check, False, started, error=f"missing: {rel}")
        else:
            res = run_check(check, root)
        res.level = "L0"
        out.append(res)
    return out
