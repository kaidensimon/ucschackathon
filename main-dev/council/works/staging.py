"""Staged workspace (spec 13.3): copy, preimage save/restore, integrate, undo.

Safety rules of this module
- A task id is written by a model. It never becomes a path as it is: `safe_task_id` keeps a
  plain id and turns any other one into a hash, and the preimage folder must resolve to a
  place under run_dir/preimage before anything is removed or written.
- Every relative path is resolved and must stay under its root. One that leaves is skipped.
- stage_workspace writes a hash manifest of the source. "Changed" means: differs from the
  staged original. A real file that no longer matches that original was edited by the user
  during the run: integrate() leaves it alone and lists it in run_dir/conflicts.json.
- Files made by checks (.pytest_cache and the like) are never staged, listed or integrated.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
import shutil
from pathlib import Path
from typing import Iterable, Optional

IGNORE = {
    ".git", "node_modules", "__pycache__", ".venv", "runs",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".hypothesis", ".coverage", "htmlcov",
}

STAGE_MANIFEST = "stage_manifest.json"
CONFLICTS = "conflicts.json"

_ID_OK = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,63}\Z")
_WIN_RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {
    f"lpt{i}" for i in range(1, 10)}


def valid_task_id(task_id: str) -> bool:
    """True for an id that is safe as one folder name on every platform."""
    if not isinstance(task_id, str) or not _ID_OK.match(task_id):
        return False
    if task_id.endswith(".") or ".." in task_id:
        return False
    return task_id.split(".")[0].lower() not in _WIN_RESERVED


def safe_task_id(task_id: str) -> str:
    """The folder name used for a task id. A plain id is kept; any other becomes a hash."""
    if valid_task_id(task_id):
        return task_id
    return "id_" + hashlib.sha256(str(task_id).encode("utf-8", "replace")).hexdigest()[:24]


def _under(base: Path, rel: str) -> Optional[Path]:
    """base/rel, or None when rel is empty, absolute, or resolves to a place outside base."""
    if not isinstance(rel, str) or not rel.strip():
        return None
    try:
        root = base.resolve()
        target = (root / rel).resolve()
        target.relative_to(root)
    except (ValueError, OSError):
        return None
    return None if target == root else target


def _norm(rel: str) -> str:
    return posixpath.normpath(str(rel).replace("\\", "/"))


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk(root: Path):
    """Yield relative posix paths of files under root, skipping IGNORE dirs."""
    stack = [root]
    while stack:
        d = stack.pop()
        for p in sorted(d.iterdir()):
            if p.name in IGNORE:
                continue
            if p.is_dir() and not p.is_symlink():
                stack.append(p)
            elif p.is_file():
                yield p.relative_to(root).as_posix()


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def stage_workspace(src: Path, run_dir: Path) -> Path:
    src, run_dir = Path(src), Path(run_dir)
    ws = run_dir / "ws"
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    manifest: dict[str, str] = {}
    for rel in _walk(src):
        _copy(src / rel, ws / rel)
        manifest[rel] = _hash(ws / rel)
    (run_dir / STAGE_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    for old in (CONFLICTS,):
        try:
            (run_dir / old).unlink()
        except OSError:
            pass
    return ws


def _manifest(run_dir: Path) -> Optional[dict[str, str]]:
    """The hashes of the staged originals, or None for a run staged without a manifest."""
    try:
        data = json.loads((run_dir / STAGE_MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _save(base: Path, root: Path, paths: list[str], within: Optional[Path] = None) -> None:
    """Copy root/<path> to base/files/<path> for every path. `within`: base must be under it."""
    if within is not None:
        try:
            base.resolve().relative_to(within.resolve())
        except (ValueError, OSError):
            raise ValueError(f"refusing to save outside {within}: {base}") from None
        if base.resolve() == within.resolve():
            raise ValueError(f"refusing to save into {within} itself")
    if base.exists():
        shutil.rmtree(base)
    files = base / "files"
    files.mkdir(parents=True)
    missing, kept = [], []
    for rel in paths:
        f, saved = _under(root, rel), _under(files, rel)
        if f is None or saved is None:
            continue  # leaves the root: never read, never written
        kept.append(rel)
        if f.is_file():
            _copy(f, saved)
        else:
            missing.append(rel)
    (base / "manifest.json").write_text(
        json.dumps({"missing": missing, "paths": kept}), encoding="utf-8")


def _restore(base: Path, root: Path) -> None:
    if not (base / "manifest.json").is_file():
        return
    man = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    for rel in man["paths"]:
        target, saved = _under(root, rel), _under(base / "files", rel)
        if target is None or saved is None:
            continue
        if rel in man["missing"]:
            if target.is_file():
                target.unlink()
        elif saved.is_file():
            _copy(saved, target)


def _preimage_dir(run_dir: Path, task_id: str) -> Path:
    return run_dir / "preimage" / safe_task_id(task_id)


def save_preimage(run_dir: Path, task_id: str, paths: list[str]) -> None:
    run_dir = Path(run_dir)
    _save(_preimage_dir(run_dir, task_id), run_dir / "ws", paths, within=run_dir / "preimage")


def restore_preimage(run_dir: Path, task_id: str) -> None:
    run_dir = Path(run_dir)
    _restore(_preimage_dir(run_dir, task_id), run_dir / "ws")


def changed_files(run_dir: Path, src: Path, only: Optional[Iterable[str]] = None) -> list[str]:
    """Files of the staged copy that differ from the staged original (new files included).

    `only`: keep just these paths (the files the tasks wrote). A run staged without a manifest
    falls back to comparing with `src` as it is now.
    """
    run_dir, src = Path(run_dir), Path(src)
    ws = run_dir / "ws"
    manifest = _manifest(run_dir)
    keep = None if only is None else {_norm(p) for p in only}
    out = []
    for rel in _walk(ws):
        if keep is not None and rel not in keep:
            continue
        if manifest is not None:
            if manifest.get(rel) != _hash(ws / rel):
                out.append(rel)
        else:
            orig = src / rel
            if not orig.is_file() or orig.read_bytes() != (ws / rel).read_bytes():
                out.append(rel)
    return sorted(out)


def conflicts(run_dir: Path, dst: Path, only: Optional[Iterable[str]] = None) -> list[str]:
    """Changed files whose real copy no longer matches the staged original: the user (or
    another program) edited, made or removed it during the run. Empty without a manifest."""
    run_dir, dst = Path(run_dir), Path(dst)
    manifest = _manifest(run_dir)
    if manifest is None:
        return []
    out = []
    for rel in changed_files(run_dir, dst, only):
        real = dst / rel
        was = manifest.get(rel)
        if real.is_file():
            now = _hash(real)
            if now != was and now != _hash(run_dir / "ws" / rel):
                out.append(rel)
        elif was is not None:
            out.append(rel)  # the user removed it
    return sorted(out)


def last_conflicts(run_dir: Path) -> list[str]:
    """The files the last integrate() left alone."""
    try:
        data = json.loads((Path(run_dir) / CONFLICTS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(p) for p in data] if isinstance(data, list) else []


def integrate(run_dir: Path, dst: Path, only: Optional[Iterable[str]] = None) -> list[str]:
    """Copy the changed files into dst and return them. The old copies go to run_dir/backup.

    A file the user changed during the run is not overwritten; see last_conflicts().
    """
    run_dir, dst = Path(run_dir), Path(dst)
    only = None if only is None else list(only)
    skip = set(conflicts(run_dir, dst, only))
    files = [f for f in changed_files(run_dir, dst, only) if f not in skip]
    (run_dir / CONFLICTS).write_text(json.dumps(sorted(skip)), encoding="utf-8")
    _save(run_dir / "backup", dst, files, within=run_dir)
    done = []
    for rel in files:
        target = _under(dst, rel)
        if target is None:
            continue
        _copy(run_dir / "ws" / rel, target)
        done.append(rel)
    return done


def undo_integrate(run_dir: Path, dst: Path) -> None:
    run_dir, dst = Path(run_dir), Path(dst)
    _restore(run_dir / "backup", dst)
