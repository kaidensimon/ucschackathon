#!/usr/bin/env python3
"""Does speculative decoding help on this box? llama-server alone vs with a draft model.

Per pair: start llama-server with the target only, run fixed prompts at temperature 0, read
timings.predicted_per_second. Stop. Start again with -md <draft> --draft-max 16, same prompts,
read speed plus draft_n and draft_n_accepted. Print a table and a verdict.
Standard library only. The server is always killed on exit.

  python3 specdec_bench.py --target qwen3:14b --draft qwen3.5:9b-q8_0
  python3 specdec_bench.py --pairs-file pairs.json      # [["target", "draft"], ...]

Exit 0 ok, 1 bad setup (blob or server missing), 2 a draft was not compatible.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

SYSTEM_MODELS_DIR = "/usr/share/ollama/.ollama/models"
MANIFEST_DIRS = ("manifests", "manifests-v2")
PROMPTS = [
    ("code", "Write a Python function that merges overlapping intervals in a list of (start, end) "
             "tuples and returns them sorted. Include a short docstring and two examples."),
    ("math", "A train leaves at 3:15 pm going 80 km/h. A second train leaves the same station at "
             "4:00 pm going 110 km/h on the same track. At what time does the second catch the "
             "first? Think step by step."),
    ("prose", "Write a short, vivid paragraph about a lighthouse keeper who notices the sea has "
              "gone completely silent."),
    ("list", "List 12 practical tips for keeping a small home network secure, one per line, "
             "each with a one-sentence reason."),
]


# ---- blob lookup (stdlib copy of council/host/ollama_blobs.py) ----

def default_models_dir():
    env = os.environ.get("OLLAMA_MODELS", "").strip()
    if env:
        return Path(env).expanduser()
    if Path(SYSTEM_MODELS_DIR).is_dir():
        return Path(SYSTEM_MODELS_DIR)
    return Path.home() / ".ollama" / "models"


def split_tag(tag):
    ref = (tag or "").strip()
    if not ref:
        return None
    parts = ref.split("/")
    name, sep, version = parts[-1].rpartition(":")
    if not sep:
        name, version = parts[-1], "latest"
    head = parts[:-1]
    if len(head) > 2:
        head = [head[0], "/".join(head[1:])]
    host = head[0] if len(head) == 2 else "registry.ollama.ai"
    namespace = head[-1] if head else "library"
    pieces = (host, namespace, name, version or "latest")
    if any(not p or p in (".", "..") or "\\" in p for p in pieces) or ".." in namespace.split("/"):
        return None
    return pieces


def blob_for_tag(tag, models_dir):
    parsed = split_tag(tag)
    if parsed is None:
        return None
    host, namespace, name, version = parsed
    for d in MANIFEST_DIRS:
        path = Path(models_dir) / d / host / namespace / name / version
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for layer in manifest.get("layers", []) if isinstance(manifest, dict) else []:
            if isinstance(layer, dict) and str(layer.get("mediaType", "")).endswith("image.model"):
                digest = str(layer.get("digest", ""))
                if not digest or "/" in digest or "\\" in digest or ".." in digest:
                    continue
                blob = Path(models_dir) / "blobs" / digest.replace(":", "-")
                if blob.is_file():
                    return blob
    return None


# ---- server control ----

class Server:
    """One llama-server process. Stderr goes to a temp file so a full pipe never blocks it."""

    def __init__(self, binary, port, model, draft=None, ctx=4096):
        self.port = port
        self.log = tempfile.TemporaryFile()
        cmd = [str(binary), "-m", str(model), "--host", "127.0.0.1", "--port", str(port),
               "-c", str(ctx), "-ngl", "99"]
        if draft is not None:
            cmd += ["-md", str(draft), "--draft-max", "16", "-ngld", "99"]
        self.proc = subprocess.Popen(cmd, stdout=self.log, stderr=subprocess.STDOUT)

    def tail(self, n=5):
        try:
            self.log.flush()
            self.log.seek(0)
            lines = self.log.read().decode("utf-8", "replace").strip().splitlines()
        except (OSError, ValueError):
            return ""
        return "\n".join(lines[-n:])

    def wait_ready(self, timeout):
        """True when /health says ok. False when the process died first or time ran out."""
        url = "http://127.0.0.1:%d/health" % self.port
        end = time.time() + timeout
        while time.time() < end:
            if self.proc.poll() is not None:
                return False
            try:
                with urllib.request.urlopen(url, timeout=3) as r:
                    if r.status == 200:
                        return True
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(1)
        return False

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        try:
            self.log.close()
        except OSError:
            pass


def ask(port, prompt, tokens):
    body = {"messages": [{"role": "user", "content": prompt}], "temperature": 0,
            "max_tokens": tokens, "stream": False, "cache_prompt": False}
    req = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % port,
                                 json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read()).get("timings") or {}


def run_prompts(port, prompts, tokens):
    """-> list of (tok/s, draft_n, draft_n_accepted) per prompt."""
    out = []
    for _name, text in prompts:
        t = ask(port, text, tokens)
        out.append((float(t.get("predicted_per_second") or 0.0),
                    int(t.get("draft_n") or 0), int(t.get("draft_n_accepted") or 0)))
    return out


def mean(values):
    return sum(values) / len(values) if values else 0.0


def bench_pair(a, target, draft, models_dir):
    """-> dict row, or dict with 'error' / 'incompatible'."""
    row = {"target": target, "draft": draft}
    tblob, dblob = blob_for_tag(target, models_dir), blob_for_tag(draft, models_dir)
    if tblob is None or dblob is None:
        missing = target if tblob is None else draft
        row["error"] = "tag not found in %s: %s" % (models_dir, missing)
        return row
    prompts = PROMPTS[:max(1, min(a.prompts, len(PROMPTS)))]
    srv = Server(a.server, a.port, tblob)
    try:
        if not srv.wait_ready(a.start_timeout):
            row["error"] = "target server did not start: " + srv.tail()
            return row
        base = run_prompts(a.port, prompts, a.tokens)
    finally:
        srv.stop()
    srv = Server(a.server, a.port, tblob, draft=dblob)
    try:
        if not srv.wait_ready(a.start_timeout):
            if srv.proc.poll() is not None:
                row["incompatible"] = srv.tail()
            else:
                row["error"] = "draft server timed out: " + srv.tail()
            return row
        spec = run_prompts(a.port, prompts, a.tokens)
    finally:
        srv.stop()
    alone = mean([b[0] for b in base])
    withd = mean([s[0] for s in spec])
    drafted = sum(s[1] for s in spec)
    accepted = sum(s[2] for s in spec)
    row.update(alone=alone, withd=withd, speedup=(withd / alone if alone else 0.0),
               accept=(accepted / drafted if drafted else None))
    return row


def verdict(row):
    sp = row["speedup"]
    if sp >= 1.15:
        return "HELPS: %.2fx with draft." % sp
    if sp >= 0.95:
        return "NO GAIN: %.2fx, leave it off." % sp
    return "HURTS: %.2fx, leave it off." % sp


def print_table(rows):
    head = ("target", "draft", "alone tok/s", "draft tok/s", "speedup", "accept")
    lines = [head]
    for r in rows:
        if "alone" in r:
            acc = "n/a" if r["accept"] is None else "%.0f%%" % (r["accept"] * 100)
            lines.append((r["target"], r["draft"], "%.1f" % r["alone"], "%.1f" % r["withd"],
                          "%.2fx" % r["speedup"], acc))
        else:
            lines.append((r["target"], r["draft"], "-", "-", "-", "-"))
    widths = [max(len(l[i]) for l in lines) for i in range(len(head))]
    for i, l in enumerate(lines):
        print("  ".join(c.ljust(widths[j]) for j, c in enumerate(l)))
        if i == 0:
            print("  ".join("-" * w for w in widths))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Speculative decoding benchmark for llama-server.")
    ap.add_argument("--target")
    ap.add_argument("--draft")
    ap.add_argument("--pairs-file", help='JSON [["target", "draft"], ...]')
    ap.add_argument("--server", default=str(Path.home() / "llama.cpp" / "build" / "bin" / "llama-server"))
    ap.add_argument("--models-dir", default=None)
    ap.add_argument("--port", type=int, default=18200)
    ap.add_argument("--tokens", type=int, default=300)
    ap.add_argument("--prompts", type=int, default=4)
    ap.add_argument("--start-timeout", type=int, default=600)
    a = ap.parse_args(argv)

    if a.pairs_file:
        pairs = [tuple(p) for p in json.loads(Path(a.pairs_file).read_text(encoding="utf-8"))]
    elif a.target and a.draft:
        pairs = [(a.target, a.draft)]
    else:
        ap.error("give --target and --draft, or --pairs-file")
    if not Path(a.server).is_file():
        print("llama-server not found: %s" % a.server, file=sys.stderr)
        return 1
    models_dir = Path(a.models_dir).expanduser() if a.models_dir else default_models_dir()

    rows, code = [], 0
    for target, draft in pairs:
        row = bench_pair(a, target, draft, models_dir)
        rows.append(row)
        if "incompatible" in row:
            print("DRAFT NOT COMPATIBLE: %s" % row["incompatible"])
            code = 2
        elif "error" in row:
            print("ERROR (%s + %s): %s" % (target, draft, row["error"]), file=sys.stderr)
            code = code or 1
    done = [r for r in rows if "alone" in r]
    if done:
        print_table(rows)
        for r in done:
            print("%s + %s: %s" % (r["target"], r["draft"], verdict(r)))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
