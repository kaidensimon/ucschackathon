#!/usr/bin/env python3
"""Two-minute smoke test: do real activations separate true from false statements?

Standalone (stdlib only). Starts the actdump tool (tap/actdump.cpp) on the GGUF blob of an
Ollama tag, sends 12 true and 12 false twin statements, and for each layer prints the
leave-one-pair-out accuracy of a difference-of-means direction and the AUROC.

Usage:
  python3 tools/box/probe_smoke.py --tag granite4.1:8b-q8_0 \
      [--actdump ~/council/tap-build/actdump] \
      [--models-dir /usr/share/ollama/.ollama/models] [--layers 8,16,24,32]

Protocol of actdump: argv "-m BLOB --layers L1,L2|all --pool last -ngl N -c CTX"; stdin gets
one JSON line {"id","text"} per request; stdout gives one JSON line
{"id","n_tokens","n_embd","layers":{"<n>":[floats]}} (or {"id","error"}).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path

THRESHOLD = 0.75
MAX_SHOWN_ALL = 12  # when every layer comes back, print this many, spread over the depth

# (true, false) twins.
TWINS = [
    ("The capital of France is Paris.", "The capital of France is Rome."),
    ("Water freezes at zero degrees Celsius.", "Water freezes at fifty degrees Celsius."),
    ("The Earth orbits the Sun.", "The Sun orbits the Earth."),
    ("A week has seven days.", "A week has nine days."),
    ("Dogs are mammals.", "Dogs are reptiles."),
    ("The Pacific is the largest ocean.", "The Pacific is the smallest ocean."),
    ("Two plus two equals four.", "Two plus two equals five."),
    ("The Moon is smaller than the Earth.", "The Moon is larger than the Earth."),
    ("Fire is hot and ice is cold.", "Fire is cold and ice is hot."),
    ("Spiders have eight legs.", "Spiders have four legs."),
    ("The capital of Japan is Tokyo.", "The capital of Japan is Cairo."),
    ("Humans breathe oxygen.", "Humans breathe helium."),
]


def layout(statement: str) -> str:
    return f"Statement: {statement}\nThe statement above is"


# ------------------------------------------------------------------ finding the blob

def default_models_dir() -> Path:
    env = os.environ.get("OLLAMA_MODELS", "").strip()
    if env:
        return Path(env).expanduser()
    system = Path("/usr/share/ollama/.ollama/models")
    if system.is_dir():
        return system
    return Path.home() / ".ollama" / "models"


def split_tag(tag: str):
    """"name", "name:tag", "user/name:tag", "host/user/name:tag" -> (host, ns, name, version)."""
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
    ns = head[-1] if head else "library"
    pieces = (host, ns, name, version or "latest")
    if any(not p or p in (".", "..") or "\\" in p for p in pieces):
        return None
    return pieces


def find_blob(tag: str, models_dir: Path) -> Path:
    parsed = split_tag(tag)
    if parsed is None:
        raise SystemExit(f"ERROR: bad Ollama tag: {tag!r}")
    host, ns, name, version = parsed
    tried = []
    for sub in ("manifests", "manifests-v2"):
        mpath = models_dir / sub / host / ns / name / version
        tried.append(str(mpath))
        try:
            manifest = json.loads(mpath.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for layer in manifest.get("layers", []) if isinstance(manifest, dict) else []:
            if isinstance(layer, dict) and str(layer.get("mediaType", "")).endswith(".model"):
                digest = str(layer.get("digest", "")).strip()
                if not digest or "/" in digest or "\\" in digest or ".." in digest:
                    continue
                blob = models_dir / "blobs" / digest.replace(":", "-")
                if blob.is_file():
                    return blob
                raise SystemExit(f"ERROR: manifest found but blob file is missing: {blob}")
    raise SystemExit(
        f"ERROR: tag {tag!r} is not pulled under {models_dir}. Looked for manifest at:\n  "
        + "\n  ".join(tried) + "\nRun `ollama pull` first or pass --models-dir.")


# ------------------------------------------------------------------ actdump

class Actdump:
    def __init__(self, binary: Path, blob: Path, layers_arg: str, ngl: int, ctx: int) -> None:
        argv = [str(binary), "-m", str(blob), "--layers", layers_arg, "--pool", "last",
                "-ngl", str(ngl), "-c", str(ctx)]
        try:
            self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
        except OSError as e:
            raise SystemExit(f"ERROR: cannot start actdump ({binary}): {e}")
        self.err: deque[str] = deque(maxlen=20)
        self.seq = 0
        threading.Thread(target=self._drain, daemon=True).start()

    def _drain(self) -> None:
        for raw in self.proc.stderr:
            text = raw.decode("utf-8", "replace").strip()
            if text:
                self.err.append(text)

    def _die(self, why: str) -> SystemExit:
        code = self.proc.poll()
        tail = " | ".join(self.err)
        return SystemExit(f"ERROR: actdump {why}" + (f" (exit code {code})" if code is not None else "")
                          + (f": {tail}" if tail else ""))

    def ask(self, text: str) -> dict:
        self.seq += 1
        rid = f"smoke#{self.seq}"
        line = json.dumps({"id": rid, "text": text}, ensure_ascii=False) + "\n"
        try:
            self.proc.stdin.write(line.encode("utf-8"))
            self.proc.stdin.flush()
        except OSError as e:
            raise self._die(f"died before the request was sent ({e})")
        raw = self.proc.stdout.readline()
        if not raw:
            raise self._die("died (no reply)")
        try:
            reply = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            raise self._die("sent a reply that is not JSON")
        if not isinstance(reply, dict) or reply.get("id") != rid:
            raise self._die("sent a reply for another request")
        if reply.get("error"):
            raise SystemExit(f"ERROR: actdump: {reply['error']} (text: {text!r})")
        if not isinstance(reply.get("layers"), dict):
            raise SystemExit("ERROR: actdump reply has no layers")
        return reply["layers"]

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


# ------------------------------------------------------------------ math

def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def auroc(scores: list[float], labels: list[int]) -> float:
    """P(score of a random positive > score of a random negative); ties count half."""
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return float("nan")
    wins = 0.0
    for p in pos:
        for n in neg:
            wins += 1.0 if p > n else 0.5 if p == n else 0.0
    return wins / (len(pos) * len(neg))


def lopo(true_vecs: list[list[float]], false_vecs: list[list[float]]) -> tuple[float, float]:
    """Leave-one-pair-out: difference-of-means direction from the other pairs, threshold at
    the midpoint of the two class means; both held-out vectors are scored. -> (accuracy, auroc)."""
    n, d = len(true_vecs), len(true_vecs[0])
    sum_t = [sum(v[k] for v in true_vecs) for k in range(d)]
    sum_f = [sum(v[k] for v in false_vecs) for k in range(d)]
    scores: list[float] = []
    labels: list[int] = []
    correct = 0
    for i in range(n):
        m = n - 1
        mu_t = [(sum_t[k] - true_vecs[i][k]) / m for k in range(d)]
        mu_f = [(sum_f[k] - false_vecs[i][k]) / m for k in range(d)]
        w = [a - b for a, b in zip(mu_t, mu_f)]
        thr = dot(w, [(a + b) / 2 for a, b in zip(mu_t, mu_f)])
        for vec, y in ((true_vecs[i], 1), (false_vecs[i], 0)):
            s = dot(w, vec) - thr
            scores.append(s)
            labels.append(y)
            if (s > 0) == (y == 1):
                correct += 1
    return correct / (2 * n), auroc(scores, labels)


def spread(items: list[int], k: int) -> list[int]:
    if len(items) <= k:
        return items
    return sorted({items[round(i * (len(items) - 1) / (k - 1))] for i in range(k)})


# ------------------------------------------------------------------ main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="True/false activation separation smoke test.")
    ap.add_argument("--tag", required=True, help="Ollama tag, e.g. granite4.1:8b-q8_0")
    ap.add_argument("--actdump", default="~/council/tap-build/actdump")
    ap.add_argument("--models-dir", default=None)
    ap.add_argument("--layers", default="", help="comma list, e.g. 8,16,24,32 (default: all, sampled)")
    ap.add_argument("--ngl", type=int, default=99)
    ap.add_argument("--ctx", type=int, default=512)
    args = ap.parse_args(argv)

    binary = Path(args.actdump).expanduser()
    if not binary.is_file():
        print(f"ERROR: actdump binary is missing: {binary}\n"
              f"Build it from tap/actdump.cpp or pass --actdump PATH.", file=sys.stderr)
        return 2
    models_dir = Path(args.models_dir).expanduser() if args.models_dir else default_models_dir()
    if not models_dir.is_dir():
        print(f"ERROR: models dir is missing: {models_dir} (pass --models-dir)", file=sys.stderr)
        return 2
    try:
        blob = find_blob(args.tag, models_dir)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2

    wanted: list[int] = []
    if args.layers.strip():
        try:
            wanted = sorted({int(x) for x in args.layers.split(",") if x.strip()})
        except ValueError:
            print(f"ERROR: --layers must be comma separated integers, got {args.layers!r}",
                  file=sys.stderr)
            return 2

    print(f"model {args.tag}\nblob  {blob}\nbinary {binary}")
    act = Actdump(binary, blob, ",".join(map(str, wanted)) if wanted else "all", args.ngl, args.ctx)
    try:
        true_by_layer: dict[int, list[list[float]]] = {}
        false_by_layer: dict[int, list[list[float]]] = {}
        for idx, (t, f) in enumerate(TWINS, 1):
            for text, store in ((t, true_by_layer), (f, false_by_layer)):
                layers = act.ask(layout(text))
                for key, vec in layers.items():
                    try:
                        store.setdefault(int(key), []).append([float(x) for x in vec])
                    except (TypeError, ValueError):
                        raise SystemExit(f"ERROR: layer {key} holds a value that is not a number")
            print(f"  pair {idx}/{len(TWINS)} done", end="\r", flush=True)
        print()
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 3
    finally:
        act.close()

    have = sorted(set(true_by_layer) & set(false_by_layer))
    if not have:
        print("ERROR: actdump returned no layers", file=sys.stderr)
        return 3
    if wanted:
        missing = [x for x in wanted if x not in have]
        if missing:
            print(f"warning: layers not in the reply, skipped: {missing} (model has {have[0]}..{have[-1]})")
        show = [x for x in wanted if x in have]
    else:
        show = spread(have, MAX_SHOWN_ALL)
    if not show:
        print("ERROR: none of the requested layers came back", file=sys.stderr)
        return 3

    print(f"\n{'layer':>5}  {'LOPO acc':>8}  {'AUROC':>6}")
    best = (-1.0, -1)
    for layer in show:
        tv, fv = true_by_layer[layer], false_by_layer[layer]
        if len(tv) != len(TWINS) or len(fv) != len(TWINS):
            print(f"{layer:>5}  (incomplete: {len(tv)} true, {len(fv)} false)")
            continue
        acc, auc = lopo(tv, fv)
        auc_s = "nan" if math.isnan(auc) else f"{auc:.3f}"
        print(f"{layer:>5}  {acc:>8.3f}  {auc_s:>6}")
        if acc > best[0]:
            best = (acc, layer)
    print()
    if best[0] >= THRESHOLD:
        print(f"SIGNAL (best layer {best[1]}, accuracy {best[0]:.3f} >= {THRESHOLD})")
    else:
        print(f"NO CLEAR SIGNAL (best layer {best[1]}, accuracy {best[0]:.3f} < {THRESHOLD})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
