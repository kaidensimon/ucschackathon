"""Check size and sha256 of the blobs behind the council's models in the Ollama store. Standard library only.

  python3 verify_models.py [--all]

By default only the council's models (COUNCIL_TAGS) are checked. --all checks every model in the store.
"""
import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from functools import partial

R = "/usr/share/ollama/.ollama/models"
# Same list as COUNCIL_TAGS in check_models.py (kept in step by tests/test_tools_box.py).
COUNCIL_TAGS = frozenset({
    "gemma4:12b-it-q8_0", "gpt-oss:20b", "qwen3.5:9b-q8_0", "phi4:14b", "ministral-3:14b",
    "granite4.1:8b-q8_0", "qwen3:14b", "deepseek-r1:14b", "phi4-reasoning:plus",
    "mistral-small3.2:24b", "falcon3:10b-instruct-q8_0",
})


def model_files(root):
    """{tag: [(digest, size), ...]} for every manifest under root/manifests and root/manifests-v2."""
    models = {}
    for base in ("manifests", "manifests-v2"):
        for dp, _, fs in os.walk(os.path.join(root, base)):
            for f in fs:
                try:
                    with open(os.path.join(dp, f)) as fh:
                        m = json.load(fh)
                except Exception:
                    continue
                if not isinstance(m, dict):
                    continue
                layers = [m.get("config", {})] + (m.get("layers") or [])
                layers = [l for l in layers if isinstance(l, dict) and l.get("digest")]
                if not layers:
                    continue
                name = os.path.basename(dp) + ":" + f
                models.setdefault(name, []).extend((l["digest"], int(l.get("size", 0))) for l in layers)
    return models


def select_models(models, all_models=False):
    """All models, or only those whose tag is in COUNCIL_TAGS."""
    if all_models:
        return models
    return {n: v for n, v in models.items() if n in COUNCIL_TAGS}


def check_blob(root, item):
    """(digest, status) for one blob: OK, MISSING, SIZE ..., or HASH MISMATCH."""
    d, size = item
    p = os.path.join(root, "blobs", d.replace(":", "-"))
    if not os.path.exists(p):
        return d, "MISSING"
    if size and os.path.getsize(p) != size:
        return d, f"SIZE {os.path.getsize(p)} != {size}"
    x = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(1 << 24)
            if not b:
                break
            x.update(b)
    return d, ("OK" if "sha256:" + x.hexdigest() == d else "HASH MISMATCH")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Verify the Ollama blobs of the council's models.")
    ap.add_argument("--all", action="store_true", help="verify every model in the store, not only the council's")
    a = ap.parse_args(argv)
    found = model_files(R)
    models = select_models(found, a.all)
    if not a.all:
        missing = sorted(COUNCIL_TAGS - set(found))
        if missing:
            print("not in the store, not checked:", ", ".join(missing))
    blobs = {}
    for n, ls in models.items():
        for d, s in ls:
            blobs[d] = s
    t = time.time()
    with ProcessPoolExecutor(8) as ex:
        res = dict(ex.map(partial(check_blob, R), sorted(blobs.items(), key=lambda kv: -kv[1])))
    tot = sum(blobs.values()) / 2**30
    for n in sorted(models):
        st = [res[d] for d, _ in models[n]]
        bad = [s for s in st if s != "OK"]
        print(f"{n:32s} {sum(s for _, s in models[n]) / 2**30:6.1f} GiB  {len(st)} files  "
              f"{'OK' if not bad else 'BAD: ' + '; '.join(bad)}")
    blobs_dir = os.path.join(R, "blobs")
    partial_n = sum(1 for f in os.listdir(blobs_dir) if "partial" in f) if os.path.isdir(blobs_dir) else 0
    print(f"checked {len(blobs)} files, {tot:.0f} GiB in {time.time() - t:.0f}s; partial files: {partial_n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
