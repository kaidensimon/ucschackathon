"""Steer store: trained steering vectors on disk, one folder per project and model.

Layout under <home>:  steer/<project slug>/<model slug>/v<N>.gguf, v<N>.json, active.txt

The json is a SteerCard dump. active.txt holds the active version number. The card's
`active` flag is always taken from active.txt on read, so a stale json never lies.
Corrupt or unreadable files are skipped, never raised.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Optional

from council.core.schemas_v15 import SteerCard

__all__ = ["SteerStore", "slug"]

_BAD = re.compile(r"[^a-z0-9._-]+")
_VERSION_FILE = re.compile(r"^v(\d+)\.(?:json|gguf)$")
_ACTIVE_FILE = "active.txt"


def slug(text: str) -> str:
    """Folder-safe name. Never empty, never a path climb."""
    s = _BAD.sub("_", str(text).lower())
    if s in ("", ".", ".."):
        s = "_" + s.replace(".", "_")
    return s


def _write_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class SteerStore:
    def __init__(self, home: Path):
        self.home = Path(home)
        self.root = self.home / "steer"

    # ---- paths ---------------------------------------------------------------------

    def _dir(self, project: str, model_id: str) -> Path:
        return self.root / slug(project) / slug(model_id)

    def path_for(self, project: str, model_id: str, version: int) -> Path:
        """The control-vector GGUF of one version."""
        return self._dir(project, model_id) / f"v{int(version)}.gguf"

    def _json_for(self, project: str, model_id: str, version: int) -> Path:
        return self._dir(project, model_id) / f"v{int(version)}.json"

    # ---- versions ------------------------------------------------------------------

    def next_version(self, project: str, model_id: str) -> int:
        top = 0
        try:
            for p in self._dir(project, model_id).iterdir():
                m = _VERSION_FILE.match(p.name)
                if m:
                    top = max(top, int(m.group(1)))
        except OSError:
            pass
        return top + 1

    # ---- read ----------------------------------------------------------------------

    @staticmethod
    def _read_active_version(folder: Path) -> Optional[int]:
        try:
            text = (folder / _ACTIVE_FILE).read_text(encoding="utf-8").strip()
            return int(text) if text else None
        except (OSError, ValueError):
            return None

    @staticmethod
    def _load(json_path: Path, active_version: Optional[int]) -> Optional[SteerCard]:
        try:
            card = SteerCard.model_validate_json(json_path.read_text(encoding="utf-8"))
        except Exception:  # corrupt json, bad fields, unreadable file
            return None
        card.active = active_version is not None and card.version == active_version
        return card

    def active(self, project: str, model_id: str) -> Optional[SteerCard]:
        folder = self._dir(project, model_id)
        version = self._read_active_version(folder)
        if version is None:
            return None
        return self._load(folder / f"v{version}.json", version)

    def _cards_in(self, folder: Path) -> list[SteerCard]:
        active_version = self._read_active_version(folder)
        out: list[SteerCard] = []
        try:
            files = list(folder.iterdir())
        except OSError:
            return out
        for p in files:
            m = _VERSION_FILE.match(p.name)
            if not m or p.suffix != ".json":
                continue
            card = self._load(p, active_version)
            if card is not None:
                out.append(card)
        out.sort(key=lambda c: c.version)
        return out

    def cards(self, project: Optional[str] = None) -> list[SteerCard]:
        """All cards, or one project's. Sorted by project, model, version."""
        if project is not None:
            project_dirs = [self.root / slug(project)]
        else:
            try:
                project_dirs = sorted(p for p in self.root.iterdir() if p.is_dir())
            except OSError:
                return []
        out: list[SteerCard] = []
        for pdir in project_dirs:
            try:
                model_dirs = sorted(p for p in pdir.iterdir() if p.is_dir())
            except OSError:
                continue
            for mdir in model_dirs:
                out.extend(self._cards_in(mdir))
        if project is not None:
            out = [c for c in out if c.project == project]
        out.sort(key=lambda c: (c.project, c.model_id, c.version))
        return out

    # ---- write ---------------------------------------------------------------------

    def save(self, card: SteerCard) -> SteerCard:
        """Write the card json. When card.active, make it the active version."""
        folder = self._dir(card.project, card.model_id)
        folder.mkdir(parents=True, exist_ok=True)
        saved = card.model_copy()
        if not saved.path:
            saved.path = str(self.path_for(card.project, card.model_id, card.version))
        if saved.active:
            _write_text(folder / _ACTIVE_FILE, str(saved.version))
        else:
            # saving a version that is not active must not leave a stale claim on it
            current = self._read_active_version(folder)
            if current == saved.version:
                (folder / _ACTIVE_FILE).unlink(missing_ok=True)
        _write_text(self._json_for(card.project, card.model_id, card.version),
                    saved.model_dump_json(indent=2))
        return saved

    def set_active(self, project: str, model_id: str, version: Optional[int]) -> bool:
        """Pick the active version, or None to switch steering off for this model.

        False when the model has no folder, or the version has no readable card.
        """
        folder = self._dir(project, model_id)
        if not folder.is_dir():
            return False
        if version is None:
            try:
                (folder / _ACTIVE_FILE).unlink(missing_ok=True)
            except OSError:
                return False
            return True
        if self._load(self._json_for(project, model_id, version), None) is None:
            return False
        try:
            _write_text(folder / _ACTIVE_FILE, str(int(version)))
        except OSError:
            return False
        return True

    def delete(self, project: str, model_id: str) -> bool:
        """Remove every version of one model in one project."""
        folder = self._dir(project, model_id)
        if not folder.is_dir():
            return False
        try:
            shutil.rmtree(folder)
        except OSError:
            return False
        try:
            folder.parent.rmdir()  # only succeeds when the project folder is now empty
        except OSError:
            pass
        return True
