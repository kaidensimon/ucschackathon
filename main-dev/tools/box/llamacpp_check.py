"""Check every council model under plain llama.cpp (llama-server), one after another.

For each Ollama tag: start llama-server on its blob, wait for /health, ask one short question three
ways (default, thinking off, thinking on) and record where the text lands (content or
reasoning_content), the speed, and any load error. Standard library only.

Run on the box:  python3 tools/box/llamacpp_check.py            (the 11 council tags)
Writes ~/council/box/llamacpp_checks.json
"""
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

HOME = pathlib.Path.home()
MODELS = pathlib.Path("/usr/share/ollama/.ollama/models")
SERVER = HOME / "llama.cpp/build/bin/llama-server"
TAGS = [
    "gpt-oss:20b", "qwen3.5:9b-q8_0", "phi4:14b", "ministral-3:14b", "granite4.1:8b-q8_0", "qwen3:14b",
    "deepseek-r1:14b", "phi4-reasoning:plus", "mistral-small3.2:24b", "falcon3:10b-instruct-q8_0",
    "gemma4:12b-it-q8_0",
]
Q = "A farmer has 17 sheep. All but 9 run away. How many are left? Reply with the number and one short sentence."


def blob(tag):
    name, _, ver = tag.partition(":")
    man = MODELS / "manifests/registry.ollama.ai/library" / name / (ver or "latest")
    for layer in json.loads(man.read_text())["layers"]:
        if layer["mediaType"].endswith("image.model"):
            return MODELS / "blobs" / layer["digest"].replace(":", "-")
    raise RuntimeError("no model layer")


def post(url, body, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def ask(url, extra):
    body = {"messages": [{"role": "user", "content": Q}], "max_tokens": 400, "temperature": 0}
    body.update(extra)
    try:
        out = post(url + "/v1/chat/completions", body)
    except Exception as e:
        return {"error": str(e)[:200]}
    msg = out["choices"][0]["message"]
    t = out.get("timings") or {}
    return {"content": (msg.get("content") or "")[:160], "content_len": len(msg.get("content") or ""),
            "reasoning_len": len(msg.get("reasoning_content") or ""),
            "tokens": (out.get("usage") or {}).get("completion_tokens"),
            "tps": round(t.get("predicted_per_second") or 0, 1), "finish": out["choices"][0].get("finish_reason")}


def check(tag, port):
    row = {"tag": tag}
    try:
        path = blob(tag)
    except Exception as e:
        row["load_error"] = f"no blob: {e}"
        return row
    log = open(f"/tmp/lcc_{port}.log", "w")
    t0 = time.time()
    proc = subprocess.Popen([str(SERVER), "-m", str(path), "--port", str(port), "-c", "8192", "-ngl", "99",
                             "--jinja", "--parallel", "1"], stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        ok = False
        while time.time() - t0 < 180:
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(url + "/health", timeout=3) as r:
                    if json.loads(r.read().decode()).get("status") == "ok":
                        ok = True
                        break
            except Exception:
                time.sleep(1)
        if not ok:
            log.flush()
            lines = [ln for ln in open(log.name, errors="replace").read().splitlines() if "error" in ln.lower()]
            row["load_error"] = (lines[0] if lines else "did not become healthy")[:220]
            return row
        row["load_s"] = round(time.time() - t0, 1)
        row["default"] = ask(url, {})
        row["think_off"] = ask(url, {"chat_template_kwargs": {"enable_thinking": False}})
        row["think_low"] = ask(url, {"reasoning_effort": "low", "chat_template_kwargs": {"reasoning_effort": "low"}})
        row["json"] = ask(url, {"response_format": {"type": "json_schema", "json_schema": {
            "name": "out", "strict": True, "schema": {"type": "object", "properties": {
                "answer": {"type": "string"}}, "required": ["answer"]}}}})
        return row
    finally:
        proc.terminate()
        try:
            proc.wait(15)
        except Exception:
            proc.kill()
        log.close()


def main():
    tags = sys.argv[1:] or TAGS
    rows = []
    for i, tag in enumerate(tags):
        row = check(tag, 18400 + i)
        rows.append(row)
        if "load_error" in row:
            print(f"{tag:<28} LOAD FAILED: {row['load_error']}", flush=True)
            continue
        d, o, lo, j = row["default"], row["think_off"], row["think_low"], row["json"]
        print(f"{tag:<28} load {row['load_s']:>5}s | default: text {d.get('content_len')} think {d.get('reasoning_len')} "
              f"tok {d.get('tokens')} {d.get('tps')} t/s | off: text {o.get('content_len')} think {o.get('reasoning_len')} "
              f"tok {o.get('tokens')} | low: text {lo.get('content_len')} think {lo.get('reasoning_len')} tok {lo.get('tokens')} "
              f"| json: {str(j.get('content') or j.get('error'))[:40]!r}", flush=True)
        print(f"{'':<28} says: {str(o.get('content') or d.get('content'))[:110]!r}", flush=True)
    out = HOME / "council/box/llamacpp_checks.json"
    out.write_text(json.dumps(rows, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
