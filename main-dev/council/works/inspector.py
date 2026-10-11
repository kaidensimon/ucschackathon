"""Inspector (spec 13.1, 13.2). L0 structure, L1 acceptance, L2 review, L3 integration."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional

from council.core.schemas import Check, CheckResult, MicroTask, Plan
from council.works import sandbox
from council.works.checks import l0_structure, run_check

ReviewCall = Callable[[MicroTask, list[str], str], Awaitable[CheckResult]]

SKIPPED = "skipped:needs_model"

_TIMEOUT_EXIT = -2  # sandbox.run_command: wall-clock timeout
_SPAWN_EXIT = -1  # sandbox.run_command: refused or could not start

# parse errors that mean the output was cut off: the task was too big for one generation
_TRUNCATION_MARKS = (
    "was never closed",
    "unexpected eof",
    "unterminated",
    "expecting value",
    "expected an indented block",
    "is empty",
)
_TOO_MANY_FILES = 3


def _norm(rel: str) -> str:
    rel = rel.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _is_skipped(r: CheckResult) -> bool:
    return bool(r.ok and r.error and r.error.startswith("skipped"))


def _is_environment(r: CheckResult) -> bool:
    if r.ok:
        return False
    err = (r.error or "").lower()
    if err.startswith(("refused", "timeout", "environment", "runner error", "no runner", "review error")):
        return True
    return r.type == "command" and r.exit_code in (_TIMEOUT_EXIT, _SPAWN_EXIT)


class Inspector:
    def __init__(
        self,
        root: Path,
        allowed_executables: list[str],
        check_timeout_s: float,
        review_call: Optional[ReviewCall] = None,
        max_parallel: int = 8,
    ) -> None:
        self.root = Path(root)
        self.allowed_executables = list(allowed_executables)
        self.check_timeout_s = float(check_timeout_s)
        self.review_call = review_call
        self.max_parallel = max(1, int(max_parallel))
        self._sem: Optional[asyncio.Semaphore] = None
        self._sem_loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------ internals

    def _semaphore(self) -> asyncio.Semaphore:
        """One semaphore per event loop, so the bound holds across concurrent inspect() calls."""
        loop = asyncio.get_running_loop()
        if self._sem is None or self._sem_loop is not loop:
            self._sem = asyncio.Semaphore(self.max_parallel)
            self._sem_loop = loop
        return self._sem

    def _runner(self, cmd: str, cwd: Path, timeout_s: float) -> dict:
        limit = self.check_timeout_s
        if timeout_s and timeout_s > 0:
            limit = min(float(timeout_s), limit) if limit > 0 else float(timeout_s)
        return sandbox.run_command(cmd, cwd, timeout_s=limit, allowed=self.allowed_executables)

    async def _run_plain(self, check: Check, level: str) -> CheckResult:
        if check.type == "command":
            async with self._semaphore():
                res = await asyncio.to_thread(run_check, check, self.root, self._runner)
            if not res.ok and not (res.error or "").startswith("refused"):
                if res.exit_code == _TIMEOUT_EXIT:
                    res.error = f"timeout: {check.cmd}"
                elif res.exit_code == _SPAWN_EXIT:
                    res.error = f"environment: could not run: {res.output_tail or check.cmd}"
        else:
            # Off the event loop: a file check reads a file and may wait for a regex child.
            async with self._semaphore():
                res = await asyncio.to_thread(run_check, check, self.root)
        res.level = level
        return res

    async def _run_review(self, task: MicroTask, written: list[str], check: Check) -> CheckResult:
        started = time.perf_counter()
        if self.review_call is None:
            res = run_check(check, self.root)  # skipped, ok
            res.error = SKIPPED
        else:
            try:
                res = await self.review_call(task, list(written), check.rubric or "")
                if not isinstance(res, CheckResult):
                    raise TypeError(f"review_call returned {type(res).__name__}")
            except Exception as e:  # a broken reviewer is a failed check, not a crash
                res = CheckResult(ok=False, error=f"review error: {e}")
            if not res.duration_ms:
                res.duration_ms = (time.perf_counter() - started) * 1000.0
        res.type = "review"
        res.check = check
        res.check_id = check.id
        res.level = "L2"
        return res

    # ------------------------------------------------------------------ public

    async def inspect(self, task: MicroTask, written: list[str]) -> list[CheckResult]:
        written = list(written)
        results = l0_structure(written, self.root)
        if task.write_set:
            allowed = {_norm(w) for w in task.write_set}
            for rel, res in zip(written, results):
                if res.ok and _norm(rel) not in allowed:
                    res.ok = False
                    res.error = f"path not in write_set: {rel}"
        for res in results:
            res.task_id = task.id
        if not self.passed(results):
            return results

        async def one(check: Check) -> CheckResult:
            if check.type == "review":
                res = await self._run_review(task, written, check)
            else:
                res = await self._run_plain(check, "L1")
            res.task_id = task.id
            return res

        results.extend(await asyncio.gather(*(one(c) for c in task.acceptance)))
        return results

    async def integration(self, plan: Plan) -> list[CheckResult]:
        async def one(check: Check) -> CheckResult:
            if check.type == "review":
                res = run_check(check, self.root)  # no single task to review: skipped, ok
                res.error = SKIPPED
                res.level = "L3"
                return res
            return await self._run_plain(check, "L3")

        return list(await asyncio.gather(*(one(c) for c in plan.global_acceptance)))

    @staticmethod
    def passed(results: list[CheckResult]) -> bool:
        return all(r.ok for r in results)

    @staticmethod
    def failing(results: list[CheckResult]) -> Optional[CheckResult]:
        for r in results:
            if not r.ok:
                return r
        return None

    @staticmethod
    def skipped(results: list[CheckResult]) -> list[CheckResult]:
        return [r for r in results if _is_skipped(r)]

    def classify_failure(self, task: MicroTask, results: list[CheckResult]) -> str:
        """"retry" | "too_big" | "ambiguous" | "environment" (spec 13.2)."""
        bad = [r for r in results if not r.ok]
        if not bad:
            return "retry"
        if any(_is_environment(r) for r in bad):
            return "environment"
        l0 = [r for r in bad if r.level == "L0"]
        if l0:
            for r in l0:
                err = (r.error or "").lower()
                if any(m in err for m in _TRUNCATION_MARKS):
                    return "too_big"
            if len(l0) > 1 and len(task.write_set) > _TOO_MANY_FILES:
                return "too_big"
            return "retry"
        if len(task.write_set) > _TOO_MANY_FILES and len(bad) > 1:
            return "too_big"
        if all(r.type == "review" for r in bad):
            return "ambiguous"
        if not task.goal.strip() or not task.output_contract.strip():
            return "ambiguous"
        return "retry"
