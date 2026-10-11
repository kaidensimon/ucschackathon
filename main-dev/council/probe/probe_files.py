"""Probes saved as files, so a trained probe survives a database reset and can be copied between machines.

Layout:
    <home>/probes/<model slug>/v<N>.json   {"card", "probes", "platt", "layout_version"}
    <home>/probes/<model slug>/active.txt  holds N

File I/O only (pathlib). A corrupt file is skipped, never raised.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from council.core.schemas import Probe
from council.core.schemas_v15 import ProbeCard

_SLUG_BAD = re.compile(r"[^a-z0-9._-]")
_VER_FILE = re.compile(r"^v(\d+)\.json$")


def slug(model_id: str) -> str:
    s = _SLUG_BAD.sub("_", model_id.lower())
    # never let a slug climb out of the probes dir or be empty
    if s in ("", ".", ".."):
        s = "_" + s.replace(".", "_")
    return s


class ProbeFiles:
    def __init__(self, home: Path) -> None:
        self.home = Path(home)
        self.root = self.home / "probes"

    # ------------------------------------------------------------ paths

    def _dir(self, model_id: str) -> Path:
        return self.root / slug(model_id)

    def _versions(self, d: Path) -> list[int]:
        out: list[int] = []
        try:
            for p in d.iterdir():
                m = _VER_FILE.match(p.name)
                if m and p.is_file():
                    out.append(int(m.group(1)))
        except OSError:
            return []
        return sorted(out)

    def _read_active(self, d: Path) -> Optional[int]:
        try:
            txt = (d / "active.txt").read_text(encoding="utf-8").strip()
            n = int(txt)
        except (OSError, ValueError):
            return None
        return n if n > 0 else None

    def _write_atomic(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _read_blob(self, d: Path, version: int) -> Optional[dict[str, Any]]:
        try:
            data = json.loads((d / f"v{version}.json").read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            ProbeCard.model_validate(data["card"])
            return data
        except (OSError, ValueError, KeyError, TypeError):
            return None

    # ------------------------------------------------------------ api

    def save(
        self,
        card: ProbeCard,
        probes: list[Probe],
        platt: Optional[tuple[float, float]] = None,
        layout_version: int = 1,
    ) -> ProbeCard:
        d = self._dir(card.model_id)
        versions = self._versions(d)
        n = (versions[-1] if versions else 0) + 1
        saved = card.model_copy(update={"version": n})
        blob = {
            "card": saved.model_dump(mode="json"),
            "probes": [p.model_dump(mode="json") for p in probes],
            "platt": [float(platt[0]), float(platt[1])] if platt is not None else None,
            "layout_version": int(layout_version),
        }
        self._write_atomic(d / f"v{n}.json", json.dumps(blob, indent=2))
        if saved.active:
            self._write_atomic(d / "active.txt", str(n))
        return saved

    def load(
        self, model_id: str, version: Optional[int] = None
    ) -> Optional[tuple[ProbeCard, list[Probe], Optional[tuple[float, float]]]]:
        d = self._dir(model_id)
        if version is None:
            version = self._read_active(d)
            if version is None:
                return None
        data = self._read_blob(d, version)
        if data is None:
            return None
        try:
            card = ProbeCard.model_validate(data["card"])
            probes = [Probe.model_validate(p) for p in data.get("probes", [])]
            raw = data.get("platt")
            platt = (float(raw[0]), float(raw[1])) if raw else None
        except (ValueError, TypeError, IndexError):
            return None
        card.active = self._read_active(d) == card.version
        return card, probes, platt

    def layout_version(self, model_id: str, version: Optional[int] = None) -> Optional[int]:
        d = self._dir(model_id)
        if version is None:
            version = self._read_active(d)
            if version is None:
                return None
        data = self._read_blob(d, version)
        if data is None:
            return None
        try:
            return int(data.get("layout_version", 1))
        except (ValueError, TypeError):
            return None

    def cards(self) -> list[ProbeCard]:
        out: list[ProbeCard] = []
        try:
            dirs = sorted(p for p in self.root.iterdir() if p.is_dir())
        except OSError:
            return out
        for d in dirs:
            active = self._read_active(d)
            for v in reversed(self._versions(d)):
                data = self._read_blob(d, v)
                if data is None:
                    continue  # corrupt: fall back to the next newest
                try:
                    card = ProbeCard.model_validate(data["card"])
                except (ValueError, TypeError, KeyError):
                    continue
                card.active = active == card.version
                out.append(card)
                break
        return out

    def set_active(self, model_id: str, version: Optional[int]) -> bool:
        """version=None clears the active probe. False if the version file is missing or corrupt."""
        d = self._dir(model_id)
        if version is None:
            try:
                (d / "active.txt").unlink()
            except FileNotFoundError:
                pass
            except OSError:
                return False
            return True
        if self._read_blob(d, version) is None:
            return False
        self._write_atomic(d / "active.txt", str(int(version)))
        return True

    def delete(self, model_id: str) -> bool:
        d = self._dir(model_id)
        if not d.is_dir():
            return False
        try:
            shutil.rmtree(d)
        except OSError:
            return False
        return True


__all__ = ["ProbeFiles", "slug"]
