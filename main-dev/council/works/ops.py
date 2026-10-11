"""Apply WorkerOutput ops to disk (spec 12.1). Atomic: validate all ops in memory, then write."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath

from council.core.schemas import WorkerOp, WorkerOutput


@dataclass
class ApplyResult:
    ok: bool
    error: str | None = None
    written: list[str] = field(default_factory=list)


class _OpError(Exception):
    pass


def _is_absolute(p: str) -> bool:
    if not p:
        return True
    return (
        PurePosixPath(p).is_absolute()
        or PureWindowsPath(p).is_absolute()
        or p.startswith(("/", "\\"))
        or (len(p) > 1 and p[1] == ":")
    )


def _resolve(root: Path, rel: str) -> Path:
    if _is_absolute(rel):
        raise _OpError(f"absolute or empty path: {rel!r}")
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise _OpError(f"path escapes root: {rel!r}") from None
    return target


def _read(path: Path) -> str:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _line_body(line: str) -> str:
    return line.rstrip("\r\n")


def _replace_block(text: str, op: WorkerOp) -> str:
    if op.start_anchor is None or op.end_anchor is None:
        raise _OpError(f"replace_block needs both anchors: {op.path}")
    start_a = _line_body(op.start_anchor)
    end_a = _line_body(op.end_anchor)
    lines = text.splitlines(keepends=True)
    starts = [i for i, ln in enumerate(lines) if _line_body(ln) == start_a]
    ends = [i for i, ln in enumerate(lines) if _line_body(ln) == end_a]
    if len(starts) != 1:
        raise _OpError(f"start_anchor found {len(starts)} times in {op.path}")
    if len(ends) != 1:
        raise _OpError(f"end_anchor found {len(ends)} times in {op.path}")
    s, e = starts[0], ends[0]
    if s >= e:
        raise _OpError(f"anchors out of order in {op.path}")
    new = op.content
    if new:
        nl = "\r\n" if "\r\n" in lines[s] else "\n"
        if not new.endswith(("\n", "\r")):
            new += nl
    return "".join(lines[: s + 1]) + new + "".join(lines[e:])


def apply_ops(output: WorkerOutput, root: Path, write_set: list[str]) -> ApplyResult:
    if output.blocked:
        return ApplyResult(ok=False, error=f"blocked: {output.blocked}", written=[])

    try:
        root = Path(root).resolve()
        allowed: set[Path] = set()
        for w in write_set:
            if _is_absolute(w):
                continue
            allowed.add((root / w).resolve())

        state: dict[Path, str] = {}  # pending file contents
        order: list[tuple[Path, str]] = []  # (target, rel) first-touch order

        def current(target: Path, rel: str) -> str | None:
            if target in state:
                return state[target]
            if target.is_file():
                return _read(target)
            return None

        def touch(target: Path, rel: str) -> None:
            if all(t != target for t, _ in order):
                order.append((target, rel))

        by_name: dict[str, list[Path]] = {}
        for a in allowed:
            by_name.setdefault(a.name, []).append(a)

        for op in output.ops:
            target = _resolve(root, op.path)  # absolute paths and escapes are refused here
            if target not in allowed:
                # Small models often get the folder wrong but the file name right ("ops/x.py"
                # for "tests/x.py"). When the name points at exactly one allowed file, that file
                # is clearly what was meant. The write still lands only on an allowed path.
                same = by_name.get(target.name, [])
                if len(same) != 1:
                    raise _OpError(f"path not in write_set: {op.path!r}")
                target = same[0]
            if op.op == "write_file":
                state[target] = op.content
            elif op.op == "append":
                base = current(target, op.path)
                state[target] = (base or "") + op.content
            elif op.op == "replace_block":
                base = current(target, op.path)
                if base is None:
                    raise _OpError(f"replace_block on missing file: {op.path}")
                state[target] = _replace_block(base, op)
            else:
                raise _OpError(f"unknown op: {op.op!r}")
            touch(target, target.relative_to(root).as_posix())

        for target, _ in order:
            if target.exists() and not target.is_file():
                raise _OpError(f"target is not a file: {target}")
    except _OpError as e:
        return ApplyResult(ok=False, error=str(e), written=[])
    except (OSError, UnicodeError) as e:
        return ApplyResult(ok=False, error=f"io error: {e}", written=[])

    written: list[str] = []
    try:
        for target, rel in order:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="") as f:
                f.write(state[target])
            written.append(rel)
    except OSError as e:
        return ApplyResult(ok=False, error=f"io error: {e}", written=written)
    return ApplyResult(ok=True, error=None, written=written)
