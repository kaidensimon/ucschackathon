#!/usr/bin/env python3
"""Load every model one at a time and record what works. Standard library only.

  python3 check_models.py [--tags a,b] [--all] [--skip-existing] [--url URL] [--out FILE]

By default only the council's tags (COUNCIL_TAGS) that Ollama has installed are checked.
--all checks every installed tag. --tags checks exactly the tags given.

Writes ~/council/box/model_checks.json:
  {tag: {ok, error, size_gib, ram_gib, tps, json_ok, think_ok, checked_at}}
"""
import argparse
import json
import pathlib
import time
import urllib.error
import urllib.request

URL = "http://127.0.0.1:11435"
OUT = pathlib.Path.home() / "council/box/model_checks.json"
RAM_FACTOR = 1.16  # measured: real memory is about 16% above the size /api/ps reports
PROMPT = ("Write a clear, plain explanation of how a bicycle stays upright while moving, "
          "covering steering, speed and balance, in about 200 words.")
SCHEMA = {"type": "object", "properties": {"answer": {"type": "integer"}}, "required": ["answer"]}
# The council's eleven models: every registry tag in make_registry.py except gemma4-12b-q4
# (not in the eleven, see train_probes.sh) and llama3.2-vision (purged). Other tags on the box are not ours.
COUNCIL_TAGS = frozenset({
    "gemma4:12b-it-q8_0", "gpt-oss:20b", "qwen3.5:9b-q8_0", "phi4:14b", "ministral-3:14b",
    "granite4.1:8b-q8_0", "qwen3:14b", "deepseek-r1:14b", "phi4-reasoning:plus",
    "mistral-small3.2:24b", "falcon3:10b-instruct-q8_0",
})


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


def parse_ps(payload, tag):
    """Size in GiB of `tag` from a /api/ps payload, or None if it is not listed."""
    if not isinstance(payload, dict):
        return None
    for m in payload.get("models") or []:
        if tag in (m.get("name"), m.get("model")):
            size = m.get("size")
            return round(size / 2**30, 2) if isinstance(size, (int, float)) else None
    return None


def parse_tags(payload):
    if not isinstance(payload, dict):
        return []
    return sorted(m["name"] for m in payload.get("models") or [] if m.get("name"))


def select_tags(installed, tags_arg="", all_models=False):
    """(tags to check, council tags not installed). Explicit --tags win; then --all; else COUNCIL_TAGS only."""
    explicit = [t for t in tags_arg.split(",") if t]
    if explicit:
        return explicit, []
    if all_models:
        return sorted(installed), []
    have = set(installed)
    return sorted(t for t in have if t in COUNCIL_TAGS), sorted(COUNCIL_TAGS - have)


def tokens_per_second(payload):
    """eval_count / eval_duration (ns) from a generate response, or None."""
    if not isinstance(payload, dict):
        return None
    n, d = payload.get("eval_count"), payload.get("eval_duration")
    if not n or not d:
        return None
    return round(n / (d / 1e9), 2)


def think_unsupported(status, payload):
    return status == 400 and "think" in error_text(payload).lower()


def ram_from_size(size_gib):
    return None if size_gib is None else round(size_gib * RAM_FACTOR, 2)


def load_existing(path):
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def unload(url, tag):
    call(url, "/api/generate", {"model": tag, "keep_alive": 0}, timeout=120)


def check_one(url, tag):
    r = {"ok": False, "error": None, "size_gib": None, "ram_gib": None, "tps": None,
         "json_ok": None, "think_ok": None, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    st, p = call(url, "/api/generate", {"model": tag, "keep_alive": -1, "options": {"num_ctx": 16384}})
    if st != 200:
        r["error"] = f"HTTP {st}: {error_text(p)}"[:400]
        return r
    r["ok"] = True
    _, ps = call(url, "/api/ps", timeout=30)
    r["size_gib"] = parse_ps(ps, tag)
    r["ram_gib"] = ram_from_size(r["size_gib"])
    opts = {"num_ctx": 16384, "num_predict": 200, "temperature": 0}
    st, p = call(url, "/api/generate", {"model": tag, "prompt": PROMPT, "stream": False,
                                        "keep_alive": -1, "options": opts})
    if st == 200:
        r["tps"] = tokens_per_second(p)
    else:
        r["error"] = f"speed test HTTP {st}: {error_text(p)}"[:400]
    st, p = call(url, "/api/generate", {"model": tag, "prompt": "Reply with JSON giving answer = 7.",
                                        "stream": False, "keep_alive": -1, "format": SCHEMA,
                                        "options": {"num_ctx": 16384, "num_predict": 100, "temperature": 0}})
    r["json_ok"] = False
    if st == 200 and isinstance(p, dict):
        try:
            r["json_ok"] = isinstance(json.loads(p.get("response", "")), dict)
        except ValueError:
            pass
    st, p = call(url, "/api/generate", {"model": tag, "prompt": "Say hi.", "stream": False,
                                        "keep_alive": -1, "think": True,
                                        "options": {"num_ctx": 16384, "num_predict": 20}})
    r["think_ok"] = st == 200 and not think_unsupported(st, p)
    return r


def _f(v):
    return "-" if v is None else str(v)


def _yn(v):
    return "-" if v is None else ("yes" if v else "no")


def table(results):
    lines = [f"{'tag':38s} {'ok':3s} {'GiB':>6s} {'RAM':>6s} {'tok/s':>7s} json think"]
    for tag, r in sorted(results.items()):
        lines.append(f"{tag:38s} {_yn(r.get('ok')):3s} {_f(r.get('size_gib')):>6s} {_f(r.get('ram_gib')):>6s} "
                     f"{_f(r.get('tps')):>7s} {_yn(r.get('json_ok')):4s} {_yn(r.get('think_ok'))}"
                     + ("" if r.get("ok") else "  ERR " + str(r.get("error"))[:80]))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check every model on the box, one at a time.")
    ap.add_argument("--tags", default="", help="comma list; default: the council's tags that Ollama lists")
    ap.add_argument("--all", action="store_true", help="check every tag Ollama lists, not only the council's")
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--url", default=URL)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out)
    st, p = call(a.url, "/api/tags", timeout=30)
    if st != 200:
        print("cannot reach Ollama at", a.url, error_text(p))
        return 1
    tags, missing = select_tags(parse_tags(p), a.tags, a.all)
    if missing:
        print("not installed, not checked:", ", ".join(missing))
    results = load_existing(out)
    for tag in tags:
        if a.skip_existing and tag in results:
            print("skip", tag)
            continue
        print("checking", tag, flush=True)
        try:
            results[tag] = check_one(a.url, tag)
        finally:
            unload(a.url, tag)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(results, f, indent=1)
    print(table({t: results[t] for t in tags if t in results}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
