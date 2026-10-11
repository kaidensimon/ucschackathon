#!/usr/bin/env python3
"""Measure real memory per model at different context sizes and mmap settings. Standard library only.

  python3 mem_test.py --tags qwen3:14b,gpt-oss:20b [--base URL] [--ctx 4096,8192,16384] [--mmap both|true|false]

For each tag, ctx and use_mmap value: unload everything, let MemAvailable settle, load the model,
let it settle again, read /api/ps, time a 120-token generation. Writes ~/council/box/mem_test.json.
Row: {tag, ctx, mmap, reported_gib, real_gib, tps, load_s, error}
"""
import argparse
import json
import pathlib
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:11435"
OUT = pathlib.Path.home() / "council/box/mem_test.json"
MEMINFO = "/proc/meminfo"
PROMPT = ("Write a clear, plain explanation of how a bicycle stays upright while moving, "
          "covering steering, speed and balance. Keep going until told to stop.")
SETTLE_MAX_S = 30
SETTLE_EQUAL = 3


def call(url, path, body=None, timeout=900):
    """GET or POST JSON. Returns (http_status, parsed_json_or_text). Never raises."""
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status = e.code
    except Exception as e:  # connection refused, timeout
        return 0, str(e)
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


def error_text(payload):
    if isinstance(payload, dict):
        return str(payload.get("error", payload))
    return str(payload)


def mem_available_gib():
    """MemAvailable in GiB from /proc/meminfo, or None if unreadable (not Linux)."""
    try:
        with open(MEMINFO) as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 2**20  # kB -> GiB
    except (OSError, ValueError, IndexError):
        pass
    return None


def settle():
    """Wait for 3 equal MemAvailable readings (to the MiB) 1 s apart, max 30 s. Returns the last reading."""
    last, equal, start = None, 0, time.monotonic()
    while True:
        cur = mem_available_gib()
        if cur is None:
            return None
        key = round(cur * 1024)
        equal = equal + 1 if key == last else 1
        last = key
        if equal >= SETTLE_EQUAL or time.monotonic() - start >= SETTLE_MAX_S:
            return cur
        time.sleep(1)


def loaded_models(base):
    st, p = call(base, "/api/ps", timeout=30)
    if st != 200 or not isinstance(p, dict):
        return []
    return [m.get("name") or m.get("model") for m in p.get("models") or [] if m.get("name") or m.get("model")]


def unload_all(base):
    for tag in loaded_models(base):
        call(base, "/api/generate", {"model": tag, "keep_alive": 0}, timeout=120)


def reported_gib(base, tag):
    """Size in GiB that /api/ps reports for `tag`, or None."""
    st, p = call(base, "/api/ps", timeout=30)
    if st != 200 or not isinstance(p, dict):
        return None
    for m in p.get("models") or []:
        if tag in (m.get("name"), m.get("model")):
            size = m.get("size")
            return round(size / 2**30, 2) if isinstance(size, (int, float)) else None
    return None


def tokens_per_second(payload):
    if not isinstance(payload, dict):
        return None
    n, d = payload.get("eval_count"), payload.get("eval_duration")
    if not n or not d:
        return None
    return round(n / (d / 1e9), 2)


def measure(base, tag, ctx, mmap):
    row = {"tag": tag, "ctx": ctx, "mmap": mmap, "reported_gib": None, "real_gib": None,
           "tps": None, "load_s": None, "error": None}
    opts = {"num_ctx": ctx, "use_mmap": mmap}
    unload_all(base)
    before = settle()
    t0 = time.monotonic()
    st, p = call(base, "/api/generate", {"model": tag, "prompt": "Hi", "stream": False, "keep_alive": -1,
                                         "options": dict(opts, num_predict=1)})
    row["load_s"] = round(time.monotonic() - t0, 2)
    if st != 200:
        row["error"] = f"load HTTP {st}: {error_text(p)}"[:300]
        return row
    after = settle()
    if before is not None and after is not None:
        row["real_gib"] = round(before - after, 2)
    row["reported_gib"] = reported_gib(base, tag)
    st, p = call(base, "/api/generate", {"model": tag, "prompt": PROMPT, "stream": False, "keep_alive": -1,
                                         "options": dict(opts, num_predict=120, temperature=0)})
    if st == 200:
        row["tps"] = tokens_per_second(p)
    else:
        row["error"] = f"speed HTTP {st}: {error_text(p)}"[:300]
    return row


def _f(v):
    return "-" if v is None else str(v)


def table(rows):
    lines = [f"{'tag':30s} {'ctx':>6s} {'mmap':5s} {'reported':>8s} {'real':>7s} {'tok/s':>7s} {'load_s':>7s}"]
    for r in rows:
        lines.append(f"{r['tag']:30s} {r['ctx']:>6d} {str(r['mmap']).lower():5s} {_f(r['reported_gib']):>8s} "
                     f"{_f(r['real_gib']):>7s} {_f(r['tps']):>7s} {_f(r['load_s']):>7s}"
                     + ("  ERR " + r["error"][:80] if r.get("error") else ""))
    return "\n".join(lines)


def parse_ctx(text):
    return [int(x) for x in text.split(",") if x.strip()]


def mmap_values(mode):
    return {"both": [True, False], "true": [True], "false": [False]}[mode]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Measure real memory per model, ctx and mmap setting.")
    ap.add_argument("--tags", required=True, help="comma list of model tags")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--ctx", default="4096,8192,16384", help="comma list of num_ctx values")
    ap.add_argument("--mmap", default="both", choices=["both", "true", "false"])
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    try:
        ctxs = parse_ctx(a.ctx)
    except ValueError:
        print("bad --ctx, want comma list of integers:", a.ctx)
        return 2
    tags = [t.strip() for t in a.tags.split(",") if t.strip()]
    if not tags or not ctxs:
        print("need at least one tag and one ctx")
        return 2
    st, p = call(a.base, "/api/tags", timeout=30)
    if st != 200:
        print(f"cannot reach Ollama at {a.base}: HTTP {st} {error_text(p)}")
        return 1
    if mem_available_gib() is None:
        print(f"warning: cannot read {MEMINFO}; real GiB will be empty (run this on the box)")
    out = pathlib.Path(a.out)
    rows = []
    try:
        for tag in tags:
            for ctx in ctxs:
                for mmap in mmap_values(a.mmap):
                    print(f"measuring {tag} ctx={ctx} mmap={str(mmap).lower()}", flush=True)
                    try:
                        row = measure(a.base, tag, ctx, mmap)
                    except Exception as e:  # one bad combo must not stop the rest
                        row = {"tag": tag, "ctx": ctx, "mmap": mmap, "reported_gib": None, "real_gib": None,
                               "tps": None, "load_s": None, "error": f"crash: {e}"[:300]}
                    if row["error"]:
                        print("  problem:", row["error"], flush=True)
                    rows.append(row)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    with open(out, "w") as f:
                        json.dump({"measured_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "rows": rows}, f, indent=1)
    finally:
        unload_all(a.base)
    print(table(rows))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
