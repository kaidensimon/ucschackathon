#!/usr/bin/env python3
"""Does speculative decoding help? Same 200-token prompt with options.draft_num_predict 0, 4, 8.

Three runs each, the first discarded. Standard library only.

  python3 specdec_test.py --tag gpt-oss:20b [--url URL]
"""
import argparse
import json
import statistics
import urllib.error
import urllib.request

URL = "http://127.0.0.1:11435"
PROMPT = ("Write a clear, plain explanation of how a bicycle stays upright while moving, "
          "covering steering, speed and balance, in about 200 words.")


def tps(payload):
    n, d = payload.get("eval_count"), payload.get("eval_duration")
    return round(n / (d / 1e9), 2) if n and d else None


def mean_after_first(values):
    """Drop the first run (warm-up); mean of the rest, or None if nothing usable."""
    rest = [v for v in values[1:] if v is not None]
    return round(statistics.mean(rest), 2) if rest else None


def run_once(url, tag, draft):
    body = {"model": tag, "prompt": PROMPT, "stream": False, "keep_alive": -1,
            "options": {"num_ctx": 16384, "num_predict": 200, "temperature": 0, "draft_num_predict": draft}}
    req = urllib.request.Request(url + "/api/generate", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return tps(json.loads(r.read())), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %d: %s" % (e.code, e.read().decode("utf-8", "replace")[:200])
    except Exception as e:
        return None, str(e)[:200]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--url", default=URL)
    a = ap.parse_args(argv)
    res = {}
    for draft in (0, 4, 8):
        vals, err = [], None
        for _ in range(3):
            v, err = run_once(a.url, a.tag, draft)
            if err:
                break
            vals.append(v)
        res[draft] = mean_after_first(vals)
        print("draft_num_predict=%d: %s" % (draft, "not available (%s)" % err if err else "%s tok/s" % res[draft]))
    base = res[0]
    for d in (4, 8):
        if base and res[d]:
            print("draft %d vs 0: %.2fx (%s)" % (d, res[d] / base, "helps" if res[d] > base * 1.05 else "no gain"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
