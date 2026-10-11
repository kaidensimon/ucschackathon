"""Pure task scheduler (spec 11.5). No I/O, no clocks, no models."""

from __future__ import annotations

from council.core.schemas import MicroTask, TaskStatus

_BAD = (TaskStatus.failed, TaskStatus.blocked, TaskStatus.skipped)


def _st(statuses: dict[str, TaskStatus], tid: str) -> TaskStatus:
    """Missing status counts as queued."""
    s = statuses.get(tid, TaskStatus.queued)
    return s if isinstance(s, TaskStatus) else TaskStatus(s)


class Scheduler:
    def __init__(self, tasks: list[MicroTask]) -> None:
        self._tasks: dict[str, MicroTask] = {t.id: t for t in tasks}
        self._order: list[str] = [t.id for t in tasks]
        self._dependents: dict[str, list[str]] = {t.id: [] for t in tasks}
        for t in tasks:
            for d in t.deps:
                if d in self._dependents:
                    self._dependents[d].append(t.id)
        self._chain: dict[str, int] = {}

    def chain_length(self, task_id: str) -> int:
        """Longest path (in edges) through dependents. Leaf task is 0."""
        if task_id in self._chain:
            return self._chain[task_id]
        # iterative post-order DFS, cycle safe
        stack: list[tuple[str, bool]] = [(task_id, False)]
        visiting: set[str] = set()
        while stack:
            node, expanded = stack.pop()
            if node in self._chain:
                continue
            if expanded:
                visiting.discard(node)
                best = 0
                for c in self._dependents.get(node, []):
                    best = max(best, 1 + self._chain.get(c, 0))
                self._chain[node] = best
                continue
            if node in visiting:
                continue
            visiting.add(node)
            stack.append((node, True))
            for c in self._dependents.get(node, []):
                if c not in self._chain and c not in visiting:
                    stack.append((c, False))
        return self._chain.get(task_id, 0)

    def runnable(self, statuses: dict[str, TaskStatus], free_slots: int) -> list[str]:
        if free_slots <= 0:
            return []
        locked: set[str] = set()
        for tid, t in self._tasks.items():
            if _st(statuses, tid) == TaskStatus.running:
                locked.update(t.write_set)
        cands = []
        for tid in self._order:
            t = self._tasks[tid]
            if _st(statuses, tid) != TaskStatus.queued:
                continue
            if not all(d in self._tasks and _st(statuses, d) == TaskStatus.passed for d in t.deps):
                continue
            cands.append(tid)
        cands.sort(key=lambda i: (-self.chain_length(i), i))
        chosen: list[str] = []
        for tid in cands:
            if len(chosen) >= free_slots:
                break
            ws = set(self._tasks[tid].write_set)
            if ws & locked:
                continue
            chosen.append(tid)
            locked |= ws
        return chosen

    def to_skip(self, statuses: dict[str, TaskStatus]) -> list[str]:
        memo: dict[str, bool] = {}

        def doomed(tid: str) -> bool:
            # iterative to avoid recursion limits; cycles count as not doomed
            if tid in memo:
                return memo[tid]
            stack = [tid]
            on_path: set[str] = set()
            while stack:
                n = stack[-1]
                if n in memo:
                    stack.pop()
                    continue
                on_path.add(n)
                pending = False
                result = False
                for d in self._tasks[n].deps:
                    if d not in self._tasks:
                        continue
                    if _st(statuses, d) in _BAD:
                        result = True
                        continue
                    if _st(statuses, d) == TaskStatus.queued:
                        if d in memo:
                            result = result or memo[d]
                        elif d not in on_path:
                            stack.append(d)
                            pending = True
                if pending:
                    continue
                memo[n] = result
                on_path.discard(n)
                stack.pop()
            return memo[tid]

        return [
            tid
            for tid in self._order
            if _st(statuses, tid) == TaskStatus.queued and doomed(tid)
        ]

    def done(self, statuses: dict[str, TaskStatus]) -> bool:
        return not any(
            _st(statuses, tid) in (TaskStatus.queued, TaskStatus.running) for tid in self._order
        )
