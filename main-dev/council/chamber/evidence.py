"""Evidence checks (spec 10.6): python in the sandbox, read_file, grep. Never raises."""
from __future__ import annotations

import asyncio
import re
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from council.core.schemas import CheckRequest, EvidenceResult
from council.works import safe_regex, sandbox
from council.works.staging import IGNORE

MAX_GREP_HITS = 40
MAX_FILE_BYTES = 1_000_000
_RANGE_RE = re.compile(r"^(.*?):(\d+)(?:-(\d+))?$")


class EvidenceRunner:
    def __init__(self, workspace: Optional[Path] = None,
                 sandbox_run: Callable = sandbox.run_command,
                 max_output_chars: int = 4000, python_timeout_s: float = 10,
                 grep_timeout_s: float = 10):
        self.workspace = Path(workspace) if workspace is not None else None
        self.sandbox_run = sandbox_run
        self.max_output_chars = max_output_chars
        self.python_timeout_s = python_timeout_s
        self.grep_timeout_s = grep_timeout_s

    async def run(self, check: CheckRequest) -> EvidenceResult:
        t0 = time.monotonic()
        kind = getattr(check, "kind", "")
        spec = getattr(check, "spec", "") or ""
        base = dict(kind=kind, spec=spec, settles=getattr(check, "settles", None))
        try:
            if kind == "python":
                ok, out, code, err = await asyncio.to_thread(self._python, spec)
            elif kind in ("read_file", "grep"):
                if self.workspace is None or not self.workspace.is_dir():
                    ok, out, code, err = False, f"no workspace: cannot run {kind}", None, "no workspace"
                elif kind == "read_file":
                    ok, out, code, err = await asyncio.to_thread(self._read_file, spec)
                else:
                    ok, out, code, err = await asyncio.to_thread(self._grep, spec)
            else:
                ok, out, code, err = False, f"unknown check kind: {kind!r}", None, "unknown kind"
        except Exception as e:  # never raise
            ok, out, code, err = False, f"check failed: {e}", None, str(e)
        truncated = len(out) > self.max_output_chars
        if truncated:
            out = out[: self.max_output_chars]
        ms = (time.monotonic() - t0) * 1000
        if kind not in ("python", "read_file", "grep"):
            base["kind"] = "python"  # schema only allows known kinds; output says what happened
        try:
            return EvidenceResult(**base, ok=ok, output=out, truncated=truncated,
                                  exit_code=code, error=err, duration_ms=ms)
        except Exception as e:
            return EvidenceResult(kind="python", ok=False, output=f"bad result: {e}")

    def _python(self, spec: str):
        with tempfile.TemporaryDirectory(prefix="evidence_") as td:
            tmp = Path(td)
            (tmp / "check.py").write_text(spec, encoding="utf-8")
            res = self.sandbox_run("python check.py", tmp, self.python_timeout_s, ["python"])
        refused = res.get("refused")
        if refused:
            return False, f"refused: {refused}", res.get("exit_code"), refused
        code = res.get("exit_code")
        out = res.get("output", "") or ""
        if code == -2:
            return False, (out + "\n" if out else "") + f"timed out after {self.python_timeout_s}s", code, "timeout"
        return True, out, code, None

    def _resolve(self, rel: str) -> Optional[Path]:
        root = self.workspace.resolve()
        p = (root / rel).resolve()
        try:
            p.relative_to(root)
        except ValueError:
            return None
        return p

    def _read_file(self, spec: str):
        spec = spec.strip()
        path_s, start, end = spec, None, None
        m = _RANGE_RE.match(spec)
        if m:
            path_s = m.group(1)
            start = int(m.group(2))
            end = int(m.group(3)) if m.group(3) else start
        p = self._resolve(path_s)
        if p is None:
            return False, f"path outside workspace: {path_s}", None, "outside workspace"
        if not p.is_file():
            return False, f"file not found: {path_s}", None, "not found"
        with p.open("rb") as f:
            data = f.read(MAX_FILE_BYTES)
        lines = data.decode("utf-8", "replace").splitlines()
        if start is not None:
            if start < 1 or end < start:
                return False, f"bad line range: {spec}", None, "bad range"
            lo = start
            chosen = lines[start - 1:end]
        else:
            lo = 1
            chosen = lines
        return True, "\n".join(f"{lo + i}: {ln}" for i, ln in enumerate(chosen)), None, None

    def _grep(self, spec: str):
        # The pattern comes from a seat: matched with a time limit (see works/safe_regex.py).
        hits, err = safe_regex.grep(self.workspace.resolve(), spec, IGNORE, MAX_GREP_HITS,
                                    MAX_FILE_BYTES, self.grep_timeout_s)
        if err is not None:
            if err == safe_regex.TIMEOUT:
                return False, f"regex timed out after {self.grep_timeout_s}s", None, "timeout"
            return False, err.replace("bad pattern", "bad regex", 1), None, "bad regex"
        return True, "\n".join(hits) if hits else "no matches", None, None
