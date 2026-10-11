"""Workspace brief (spec section 2 step 2). Pure reads only."""

from __future__ import annotations

import hashlib
import os
from collections import Counter
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "runs", "dist", "build"}
BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".pdf", ".zip", ".gz", ".tar",
    ".7z", ".exe", ".dll", ".so", ".dylib", ".pyc", ".pyo", ".bin", ".class", ".jar", ".woff",
    ".woff2", ".ttf", ".otf", ".mp3", ".mp4", ".wav", ".mov", ".sqlite", ".db", ".gguf",
}
LANGS = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".rs": "Rust", ".go": "Go", ".java": "Java", ".c": "C",
    ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".cs": "C#", ".rb": "Ruby",
    ".php": "PHP", ".sh": "Shell", ".html": "HTML", ".css": "CSS", ".md": "Markdown",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML", ".sql": "SQL",
    ".kt": "Kotlin", ".swift": "Swift",
}
KEY_NAMES = {"pyproject.toml", "package.json", "requirements.txt", "main.py", "app.py",
             "__main__.py", "index.js", "main.js", "index.ts", "main.ts", "main.go",
             "main.rs", "cli.py", "server.py", "manage.py"}
HEAD_LINES = 40
EMPTY = "(empty workspace)"


def _is_binary_name(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in BINARY_EXTS


def _walk(workspace: Path, max_files: int) -> list[tuple[str, int, float]]:
    """Sorted (relpath, size, mtime) for text files; stops at max_files."""
    out: list[tuple[str, int, float]] = []
    try:
        for root, dirs, files in os.walk(workspace):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for f in sorted(files):
                if _is_binary_name(f):
                    continue
                p = Path(root) / f
                try:
                    st = p.stat()
                except OSError:
                    continue
                rel = p.relative_to(workspace).as_posix()
                out.append((rel, st.st_size, st.st_mtime))
                if len(out) >= max_files:
                    return out
    except OSError:
        pass
    return out


def _head(path: Path, n: int = HEAD_LINES) -> str:
    try:
        with open(path, "rb") as fh:
            raw = fh.read(8192)
    except OSError:
        return ""
    if b"\x00" in raw:
        return ""
    return "\n".join(raw.decode("utf-8", errors="replace").splitlines()[:n])


def _is_key(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    low = name.lower()
    return low.startswith("readme") or name in KEY_NAMES


def build_brief(workspace: Path, max_chars: int = 9000, max_files: int = 400) -> str:
    workspace = Path(workspace)
    if not workspace.is_dir():
        return EMPTY
    files = _walk(workspace, max_files)
    if not files:
        return EMPTY

    exts = Counter(LANGS[os.path.splitext(r)[1].lower()] for r, _, _ in files
                   if os.path.splitext(r)[1].lower() in LANGS)
    parts: list[str] = []
    langs = ", ".join(f"{k} ({v})" for k, v in exts.most_common())
    parts.append("Languages: " + (langs or "unknown"))
    parts.append("Files:\n" + "\n".join(f"  {r}" for r, _, _ in files))

    # Key files: shallow first.
    keys = sorted((r for r, _, _ in files if _is_key(r)), key=lambda r: (r.count("/"), r))
    for rel in keys:
        head = _head(workspace / rel)
        if head:
            parts.append(f"--- {rel} (head) ---\n{head}")

    text = "\n\n".join(parts)
    if len(text) > max_chars:
        cut = max(0, max_chars - 15)
        text = text[:cut] + "\n...(truncated)"
    return text[:max_chars] if max_chars > 0 else ""


def brief_hash(workspace: Path) -> str:
    workspace = Path(workspace)
    h = hashlib.sha256()
    if not workspace.is_dir():
        return h.hexdigest()
    for rel, size, mtime in _walk(workspace, 100000):
        h.update(f"{rel}|{size}|{int(mtime * 1000)}\n".encode("utf-8"))
    return h.hexdigest()
