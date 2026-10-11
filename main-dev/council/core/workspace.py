"""Workspace identity and on-disk layout helpers (spec 27, 28).

Pure functions. No I/O beyond path resolution. No model server needed.

- project_id(workspace): stable 12-hex id for a project folder.
- scope_for(workspace): "project:<id>" scope string.
- safe_name(model_id): folder-safe name for a model id (readable, collision-proof).
- adapters_dir(home, project, model_id): home/adapters/<project>/<safe model name>.
- runs_dir(home, run_id): home/runs/<run_id>.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

PROJECT_ID_LEN = 12
SAFE_NAME_MAX = 120

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def project_id(workspace: str | Path) -> str:
    """First 12 hex chars of sha256 of the resolved, case-normalized absolute path."""
    resolved = str(Path(workspace).expanduser().resolve())
    return _sha(resolved.casefold())[:PROJECT_ID_LEN]


def scope_for(workspace: str | Path) -> str:
    return f"project:{project_id(workspace)}"


def safe_name(model_id: str) -> str:
    """Folder-safe name for a model id.

    Keeps [A-Za-z0-9._-], maps every other run to "_". If anything was changed,
    appends "-" + 8 hex of sha256(model_id) so distinct ids never collide
    (e.g. "a/b" and "a_b"). Never empty, never "." or "..", never a Windows
    reserved device name, capped in length.
    """
    if not isinstance(model_id, str):
        raise TypeError("model_id must be str")
    slug = _UNSAFE.sub("_", model_id).strip("._-")
    changed = slug != model_id
    if not slug:
        slug = "model"
        changed = True
    if slug.casefold() in _WINDOWS_RESERVED:
        slug = "_" + slug
        changed = True
    if changed:
        digest = _sha(model_id)[:8]
        slug = slug[: SAFE_NAME_MAX - 9] + "-" + digest
    return slug[:SAFE_NAME_MAX]


def adapters_dir(home: Path, project: str, model_id: str) -> Path:
    return Path(home) / "adapters" / project / safe_name(model_id)


def runs_dir(home: Path, run_id: str) -> Path:
    return Path(home) / "runs" / run_id
