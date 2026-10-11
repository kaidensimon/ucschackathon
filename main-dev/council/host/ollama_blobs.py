"""Find the GGUF file Ollama keeps for a tag.

Ollama stores each model as a manifest (JSON) plus content-addressed blobs. The layer whose
mediaType ends with ".model" is the weights, and that blob is a plain GGUF file, so llama.cpp
tools can open it as it is. Nothing here talks to the Ollama server: it only reads files.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Iterable

DEFAULT_REGISTRY = "registry.ollama.ai"
DEFAULT_NAMESPACE = "library"
SYSTEM_MODELS_DIR = "/usr/share/ollama/.ollama/models"  # the Linux service install
MANIFEST_DIRS = ("manifests", "manifests-v2")


def default_models_dir() -> Path:
    """OLLAMA_MODELS, else the Linux service directory if it exists, else ~/.ollama/models."""
    env = os.environ.get("OLLAMA_MODELS", "").strip()
    if env:
        return Path(env).expanduser()
    system = Path(SYSTEM_MODELS_DIR)
    if system.is_dir():
        return system
    return Path.home() / ".ollama" / "models"


def split_tag(tag: str) -> tuple[str, str, str, str] | None:
    """"name", "name:tag", "user/name:tag" or "host/user/name:tag" -> (host, namespace, name, tag)."""
    ref = (tag or "").strip()
    if not ref:
        return None
    parts = ref.split("/")
    last = parts[-1]
    name, sep, version = last.rpartition(":")
    if not sep:
        name, version = last, "latest"
    head = parts[:-1]
    if len(head) > 2:  # a namespace with slashes in it: keep the host, join the rest
        head = [head[0], "/".join(head[1:])]
    host = head[0] if len(head) == 2 else DEFAULT_REGISTRY
    namespace = head[-1] if head else DEFAULT_NAMESPACE
    pieces = (host, namespace, name, version or "latest")
    if any(not p or p in (".", "..") or "\\" in p for p in pieces):
        return None
    if ".." in namespace.split("/"):
        return None
    return pieces


def manifest_paths(tag: str, models_dir: Path) -> list[Path]:
    """Every place the manifest of this tag may sit, most likely first."""
    parsed = split_tag(tag)
    if parsed is None:
        return []
    host, namespace, name, version = parsed
    base = Path(models_dir)
    return [base / d / host / namespace / name / version for d in MANIFEST_DIRS]


def _model_digest(manifest: object) -> str | None:
    layers = manifest.get("layers") if isinstance(manifest, dict) else None
    if not isinstance(layers, list):
        return None
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        if str(layer.get("mediaType", "")).endswith(".model"):
            digest = str(layer.get("digest", "")).strip()
            if digest:
                return digest
    return None


def blob_for_tag(tag: str, models_dir: Path) -> Path | None:
    """The GGUF blob of an Ollama tag, or None when the tag is not pulled here."""
    base = Path(models_dir)
    for path in manifest_paths(tag, base):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        digest = _model_digest(manifest)
        if digest is None or "/" in digest or "\\" in digest or ".." in digest:
            continue
        blob = base / "blobs" / digest.replace(":", "-")
        if blob.is_file():
            return blob
    return None


def models_dir_from(configured: object = "") -> Path:
    """The configured models directory, or the usual search when it is empty."""
    text = str(configured or "").strip()
    return Path(text).expanduser() if text else default_models_dir()


def resolver(models_dir: Path | None = None) -> Callable[[str], Path | None]:
    """tag -> GGUF blob (or None) in one models directory. Read on each call, not cached,
    so a tag pulled later is found."""
    base = Path(models_dir) if models_dir is not None else default_models_dir()

    def blob_for(tag: str) -> Path | None:
        return blob_for_tag(tag, base)

    return blob_for


def blob_map(registry: Iterable[object], models_dir: Path | None = None) -> dict[str, Path]:
    """model id -> GGUF blob for every registry entry whose ollama_tag is pulled here."""
    find = resolver(models_dir)
    out: dict[str, Path] = {}
    for entry in registry:
        tag = getattr(entry, "ollama_tag", None)
        blob = find(tag) if tag else None
        if blob is not None:
            out[str(getattr(entry, "id"))] = blob
    return out


__all__ = [
    "blob_for_tag", "blob_map", "default_models_dir", "manifest_paths", "models_dir_from",
    "resolver", "split_tag",
]
