"""Command runner for checks (spec 13.4). No shell, allowlist, no installs, scrubbed env.

What it does bound
- The executable: only names in `allowed`.
- Installs and downloads: refused from the PARSED argv, so quoting or `-mpip` does not pass.
- Wall time: on timeout the whole process tree is killed, not only the direct child.
- Output: read in a loop into a bounded tail. Past MAX_OUTPUT_BYTES the tree is killed.

What it does NOT bound: this is not a real sandbox. An allowed `python -c ...`, a check script
or a conftest.py is model-written code that runs with the user's rights: it can open files and
sockets or start other programs. The install guard only stops the plain, direct forms.
"""
from __future__ import annotations

import collections
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

DEFAULT_ALLOWED = ["python", "python3", "pytest"]

MAX_OUTPUT_BYTES = 8 * 1024 * 1024  # more than this from one command: it is killed
KEEP_BYTES = 256 * 1024  # how much of the end of the output is held in memory
OUTPUT_EXIT = -3  # exit code reported when the output cap was hit
_GRACE_S = 3.0  # wait for the pipe to close after a kill, then give up

_INSTALL_RE = re.compile(
    r"(?<![\w-])(?:"
    r"pip3?\s+install|-m\s*pip|npm\s+install|npm\s+i|yarn\s+add|pnpm\s+add"
    r"|apt|apt-get|brew|conda\s+install|cargo\s+install|curl|wget"
    r"|docker\s+pull|git\s+clone"
    r")(?![\w-])",
    re.IGNORECASE,
)

# `python -m <one of these>` installs, downloads or builds an environment.
_BANNED_MODULES = {
    "pip", "pip3", "ensurepip", "venv", "virtualenv", "easy_install", "uv", "pipx", "conda",
    "poetry", "pdm", "pipenv",
}
_CODE_RE = re.compile(
    r"\b(?:ensurepip|easy_install|import\s+pip\b|from\s+pip\b|pip\s*\.\s*(?:main|_internal)"
    r"|pip3?\s+install)",
    re.IGNORECASE,
)
_PY_OPTS_WITH_ARG = "WX"

_ENV_KEYS = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME")


def _result(code: int, output: str, ms: int, refused: str | None) -> dict:
    return {"exit_code": code, "output": output, "ms": ms, "refused": refused}


def _unquote(p: str) -> str:
    while len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'":
        p = p[1:-1]
    return p


def _split(cmd: str) -> list[str]:
    posix = os.name != "nt"
    parts = shlex.split(cmd, posix=posix)
    if not posix:
        parts = [p[1:-1] if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'" else p for p in parts]
    return parts


def _tail(text: str, n: int = 200) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n:])


def _scrub_env(cwd: Optional[Path] = None) -> dict:
    env = {k: os.environ[k] for k in _ENV_KEYS if k in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if cwd is not None:
        # The work being checked must be importable from where it was written: the workspace
        # itself, and a "src" folder when the plan chose that layout. Nothing outside it.
        root = Path(cwd)
        env["PYTHONPATH"] = os.pathsep.join([str(root), str(root / "src")])
    return env


def _exe_name(arg: str) -> str:
    base = os.path.basename(_unquote(arg).replace("\\", "/")).lower()
    return base[:-4] if base.endswith(".exe") else base


def _python_target(args: list[str]) -> tuple[str | None, str | None]:
    """(module of -m, code of -c) of a python command line. Reads interpreter options only."""
    i = 0
    while i < len(args):
        tok = _unquote(args[i])
        if tok == "--" or not tok.startswith("-") or tok == "-":
            return None, None  # a script path (or stdin): the interpreter options are over
        if tok.startswith("--"):
            i += 2 if tok == "--check-hash-based-pycs" else 1
            continue
        j = 1
        while j < len(tok):
            ch = tok[j]
            if ch in "mc" or ch in _PY_OPTS_WITH_ARG:
                rest = tok[j + 1:]
                if not rest:
                    i += 1
                    rest = _unquote(args[i]) if i < len(args) else ""
                if ch == "m":
                    return _unquote(rest.strip()), None
                if ch == "c":
                    return None, rest
                break
            j += 1
        i += 1
    return None, None


def install_reason(argv: list[str]) -> str | None:
    """Why this argv is an install or a download, or None. Works on the parsed arguments."""
    if not argv:
        return None
    clean = [_unquote(a) for a in argv]
    base = _exe_name(clean[0])
    if base in ("python", "python3", "py") or re.fullmatch(r"python\d(\.\d+)?", base):
        module, code = _python_target(clean[1:])
        if module is not None:
            root = module.split(".")[0].strip().lower().replace("-", "_")
            if root in _BANNED_MODULES:
                return f"python -m {module}"
        if code is not None:
            m = _CODE_RE.search(code)
            if m:
                return m.group(0)
    m = _INSTALL_RE.search(" ".join(clean))
    return m.group(0) if m else None


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the process and everything it started. Never raises."""
    try:
        if os.name == "nt":
            root = os.environ.get("SYSTEMROOT") or os.environ.get("SystemRoot") or r"C:\Windows"
            exe = os.path.join(root, "System32", "taskkill.exe")
            try:
                subprocess.run(
                    [exe if os.path.isfile(exe) else "taskkill", "/T", "/F", "/PID", str(proc.pid)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.SubprocessError):
                pass
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (OSError, AttributeError):
                pass
    finally:
        try:
            proc.kill()
        except OSError:
            pass


class _Reader(threading.Thread):
    """Drains a pipe into a bounded tail. Sets `over` and kills the tree past the cap."""

    def __init__(self, proc: subprocess.Popen, cap: int, keep: int) -> None:
        super().__init__(daemon=True)
        self.proc, self.cap, self.keep = proc, cap, keep
        self.chunks: collections.deque[bytes] = collections.deque()
        self.held = 0
        self.total = 0
        self.over = False

    def run(self) -> None:
        stream = self.proc.stdout
        try:
            while True:
                chunk = stream.read1(65536) if hasattr(stream, "read1") else stream.read(65536)
                if not chunk:
                    return
                self.total += len(chunk)
                self.chunks.append(chunk)
                self.held += len(chunk)
                while self.held - len(self.chunks[0]) >= self.keep:
                    self.held -= len(self.chunks.popleft())
                if self.total > self.cap and not self.over:
                    self.over = True
                    _kill_tree(self.proc)
        except (OSError, ValueError):
            return

    def text(self) -> str:
        data = b"".join(list(self.chunks))[-self.keep:]
        return data.decode("utf-8", "replace")


def run_command(cmd: str, cwd: Path, timeout_s: float = 60,
                allowed: list[str] = DEFAULT_ALLOWED,
                max_output_bytes: int = MAX_OUTPUT_BYTES) -> dict:
    t0 = time.monotonic()

    def ms() -> int:
        return int((time.monotonic() - t0) * 1000)

    try:
        argv = _split(cmd)
    except ValueError as e:
        return _result(-1, "", ms(), f"cannot parse command: {e}")
    if not argv:
        return _result(-1, "", ms(), "empty command")

    base = _exe_name(argv[0])
    if base not in [a.lower() for a in allowed]:
        return _result(-1, "", ms(), f"executable not allowed: {base}")

    why = install_reason(argv)
    if why is None:
        m = _INSTALL_RE.search(cmd)
        why = m.group(0) if m else None
    if why:
        return _result(-1, "", ms(), f"install or download refused: {why}")

    if base in ("python", "python3"):
        argv[0] = sys.executable

    extra: dict = {}
    if os.name == "nt":
        extra["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        extra["start_new_session"] = True
    try:
        proc = subprocess.Popen(
            argv, cwd=str(cwd), env=_scrub_env(Path(cwd)), shell=False,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **extra,
        )
    except (OSError, ValueError) as e:
        return _result(-1, str(e), ms(), None)

    reader = _Reader(proc, max(1, int(max_output_bytes)), KEEP_BYTES)
    reader.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout_s if timeout_s and timeout_s > 0 else None)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
    except BaseException:
        _kill_tree(proc)
        raise
    # The pipe closes when the last holder exits. A grandchild that outlived the kill may hold
    # it open: wait a short time, then stop waiting. The reader is a daemon thread.
    reader.join(_GRACE_S)
    if reader.is_alive():
        _kill_tree(proc)
        reader.join(_GRACE_S)
    try:
        code = proc.wait(timeout=_GRACE_S)
    except subprocess.TimeoutExpired:
        code = -1
    if not reader.is_alive():
        try:
            proc.stdout.close()
        except OSError:
            pass

    out = _tail(reader.text())
    if reader.over:
        note = f"[output over {reader.cap} bytes: the command was killed]"
        return _result(OUTPUT_EXIT, (out + "\n" + note).strip(), ms(), None)
    if timed_out:
        return _result(-2, out, ms(), None)
    return _result(code, out, ms(), None)
