"""Steering-vector experiment for the box. Standard library only (no numpy, no PyTorch).

Question it answers: can we push a model's behaviour in a direction WE choose by adding a vector
to its hidden state, using only the Ollama model file?

Method
1. Contrast prompts: the same user request under two opposite system instructions.
2. Read the hidden state at the last token of each prompt with actdump (tap/actdump.cpp).
3. Steering vector per layer = mean(positive) - mean(negative).
4. Write it as a llama.cpp control-vector file and serve the model with llama-server
   --control-vector-scaled at several strengths.
5. Ask held-out questions with NO system instruction and measure the behaviour.

Controls: strength 0 (baseline), a negative strength (must push the other way), and a random
vector of the same size (must do nothing useful).

Run on the box:  python3 tools/box/steer_test.py --tag granite4.1:8b-q8_0
"""
import argparse
import json
import math
import os
import pathlib
import random
import re
import struct
import subprocess
import sys
import time
import urllib.request

HOME = pathlib.Path.home()

GENERAL = [
    "How do plants make food?", "Why is the sky blue?", "What is a database index?",
    "Explain how a bicycle stays upright.", "What causes the seasons?", "How does a vaccine work?",
    "What is inflation?", "Describe how bread is made.", "Why do we sleep?",
    "What is the difference between weather and climate?", "How do airplanes fly?",
    "What is an operating system?", "Why is exercise good for you?", "How does a refrigerator work?",
    "What is photosynthesis used for?", "Explain what a compiler does.",
]
CODING = [
    "Write a Python function that sums a list of numbers.",
    "Write a Python function that reverses a string and counts its vowels.",
    "Write a Python class for a bank account with deposit and withdraw.",
    "Write Python code that reads a file and counts the lines.",
    "Write a Python function that finds the largest item in a list.",
    "Write a Python function that checks whether a number is prime.",
    "Write a Python function that merges two sorted lists.",
    "Write Python code that computes the average word length of a sentence.",
    "Write a Python function that removes duplicate items from a list.",
    "Write a Python function that converts minutes to hours and minutes.",
    "Write a Python class that tracks the items in a shopping cart.",
    "Write a Python function that counts how often each word appears in a text.",
    "Write a Python function that validates an email address.",
    "Write a Python function that returns the first n square numbers.",
    "Write a Python function that computes the total price with tax.",
    "Write a Python function that parses a date string into year, month, day.",
]

CONCEPTS = {
    "french": {
        "pos": "Always answer in French. Every word of your reply must be in French.",
        "neg": "Always answer in English. Every word of your reply must be in English.",
        "train": GENERAL,
        "test": ["What is the moon made of?", "How do bees make honey?", "Why do people need water?",
                 "What does a heart do?", "How is paper made?"],
    },
    "terse": {
        "pos": "Answer in one short sentence. Never more than fifteen words.",
        "neg": "Answer at great length, with full detail, many paragraphs and examples.",
        "train": GENERAL,
        "test": ["What is the moon made of?", "How do bees make honey?", "Why do people need water?",
                 "What does a heart do?", "How is paper made?"],
    },
    "camel": {
        "pos": "In this project every Python function and variable name is written in camelCase, "
               "like totalPrice and getUserName. Never use underscores in names.",
        "neg": "In this project every Python function and variable name is written in snake_case, "
               "like total_price and get_user_name. Never use capital letters in names.",
        "train": CODING,
        "test": ["Write a Python function that computes the area and perimeter of a rectangle.",
                 "Write a Python function that finds the longest word in a sentence.",
                 "Write a Python function that counts the even numbers in a list.",
                 "Write a Python function that joins a first name and a last name.",
                 "Write a Python function that returns the minimum and maximum of a list."],
    },
}

FR = set("le la les des est et un une du de en que qui dans pour pas sur avec il elle vous nous ce cette "
         "sont au aux se par plus être à ou mais comme ses leur leurs très aussi fait".split())
EN = set("the is and of to in that it for with as on are this be was by an or you which can from has have "
         "not a their they its also made".split())


def measure(concept, text):
    if concept == "french":
        words = re.findall(r"[a-zàâçéèêëîïôûùüÿœ]+", text.lower())
        fr = sum(w in FR for w in words)
        en = sum(w in EN for w in words)
        return fr / (fr + en) if fr + en else 0.0
    if concept == "terse":
        return float(len(text.split()))
    camel = len(set(re.findall(r"\b[a-z]+[A-Z][a-zA-Z0-9]*\b", text)))
    snake = len(set(re.findall(r"\b[a-z]+_[a-z0-9_]+\b", text)))
    return camel / (camel + snake) if camel + snake else 0.5


UNIT = {"french": "share of French words (0..1)", "terse": "words in the reply",
        "camel": "share of camelCase names (0..1)"}


def blob_for(tag, models_dir):
    name, _, ver = tag.partition(":")
    man = pathlib.Path(models_dir) / "manifests/registry.ollama.ai/library" / name / (ver or "latest")
    for layer in json.loads(man.read_text())["layers"]:
        if layer["mediaType"].endswith("image.model"):
            return pathlib.Path(models_dir) / "blobs" / layer["digest"].replace(":", "-")
    raise SystemExit("no model layer in " + str(man))


def http(url, body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


class Server:
    def __init__(self, binary, blob, port, extra=()):
        self.url = f"http://127.0.0.1:{port}"
        self.log = open(f"/tmp/steer_server_{port}.log", "w")
        argv = [str(binary), "-m", str(blob), "--port", str(port), "-c", "4096", "-ngl", "99", *extra]
        self.proc = subprocess.Popen(argv, stdout=self.log, stderr=subprocess.STDOUT)
        t0 = time.time()
        while time.time() - t0 < 240:
            if self.proc.poll() is not None:
                raise RuntimeError("llama-server exited, see " + self.log.name)
            try:
                if http(self.url + "/health", timeout=3).get("status") == "ok":
                    return
            except Exception:
                time.sleep(1)
        self.stop()
        raise RuntimeError("llama-server did not become ready")

    def chat(self, user, max_tokens):
        out = http(self.url + "/v1/chat/completions", {
            "messages": [{"role": "user", "content": user}], "temperature": 0, "seed": 1,
            "max_tokens": max_tokens})
        return out["choices"][0]["message"].get("content") or ""

    def render(self, system, user):
        out = http(self.url + "/apply-template", {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        return out["prompt"]

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except Exception:
            self.proc.kill()
        self.log.close()


def activations(actdump, blob, layers, texts):
    """texts: list of str -> list of {layer: vector}."""
    lines = "".join(json.dumps({"id": i, "text": t}) + "\n" for i, t in enumerate(texts))
    p = subprocess.run([str(actdump), "-m", str(blob), "--layers", ",".join(map(str, layers)), "--pool", "last"],
                       input=lines.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
    rows = {}
    for line in p.stdout.decode().splitlines():
        try:
            j = json.loads(line)
        except Exception:
            continue
        if "layers" in j and j.get("id") is not None:
            rows[j["id"]] = {int(k): v for k, v in j["layers"].items()}
    if len(rows) != len(texts):
        raise RuntimeError(f"actdump returned {len(rows)} of {len(texts)} rows: {p.stderr.decode()[-400:]}")
    return [rows[i] for i in range(len(texts))]


def mean(vectors):
    n = len(vectors)
    return [sum(col) / n for col in zip(*vectors)]


def norm(v):
    return math.sqrt(sum(x * x for x in v))


def gguf_string(s):
    b = s.encode()
    return struct.pack("<Q", len(b)) + b


def write_cvec(path, directions, hint):
    """directions: {layer: [floats]}. llama.cpp control vector: tensors named direction.<layer>, F32."""
    kvs = [("general.architecture", 8, gguf_string("controlvector")),
           ("controlvector.model_hint", 8, gguf_string(hint)),
           ("controlvector.layer_count", 5, struct.pack("<i", len(directions)))]
    head = b"GGUF" + struct.pack("<IQQ", 3, len(directions), len(kvs))
    for key, typ, val in kvs:
        head += gguf_string(key) + struct.pack("<I", typ) + val
    data, offset = b"", 0
    for layer in sorted(directions):
        vec = directions[layer]
        head += gguf_string(f"direction.{layer}") + struct.pack("<IQIQ", 1, len(vec), 0, offset)
        blob = struct.pack(f"<{len(vec)}f", *vec)
        blob += b"\0" * ((-len(blob)) % 32)
        data += blob
        offset += len(blob)
    head += b"\0" * ((-len(head)) % 32)
    pathlib.Path(path).write_bytes(head + data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="granite4.1:8b-q8_0")
    ap.add_argument("--models-dir", default="/usr/share/ollama/.ollama/models")
    ap.add_argument("--actdump", default=str(HOME / "council/tap-build/actdump"))
    ap.add_argument("--server", default=str(HOME / "llama.cpp/build/bin/llama-server"))
    ap.add_argument("--layers", default="14-26", help="range of layers that get the vector")
    ap.add_argument("--scales", default="-1,0.5,1,2")
    ap.add_argument("--concepts", default="french,terse,camel")
    ap.add_argument("--port", type=int, default=18300)
    ap.add_argument("--max-tokens", type=int, default=160)
    ap.add_argument("--out", default=str(HOME / "council/box/steer_test.json"))
    a = ap.parse_args()

    blob = blob_for(a.tag, a.models_dir)
    lo, hi = (int(x) for x in a.layers.split("-"))
    layers = list(range(lo, hi + 1))
    scales = [float(x) for x in a.scales.split(",")]
    names = [c for c in a.concepts.split(",") if c in CONCEPTS]
    work = pathlib.Path("/tmp/steer")
    work.mkdir(exist_ok=True)
    result = {"tag": a.tag, "layers": a.layers, "concepts": {}}
    t_start = time.time()

    # 1. baseline server: render the contrast prompts with the model's own chat template, and baseline replies
    print(f"model {a.tag}\nblob  {blob}\nbaseline server ...", flush=True)
    srv = Server(a.server, blob, a.port)
    rendered, base = {}, {}
    try:
        for c in names:
            spec = CONCEPTS[c]
            rendered[c] = ([srv.render(spec["pos"], q) for q in spec["train"]],
                           [srv.render(spec["neg"], q) for q in spec["train"]])
            base[c] = [srv.chat(q, a.max_tokens) for q in spec["test"]]
    finally:
        srv.stop()

    # 2. activations -> one vector per layer per concept
    for c in names:
        pos, neg = rendered[c]
        print(f"[{c}] reading activations of {len(pos) + len(neg)} prompts ...", flush=True)
        acts = activations(a.actdump, blob, layers, pos + neg)
        ap_, an_ = acts[:len(pos)], acts[len(pos):]
        direction, info = {}, []
        for layer in layers:
            mp, mn = mean([r[layer] for r in ap_]), mean([r[layer] for r in an_])
            d = [x - y for x, y in zip(mp, mn)]
            direction[layer] = d
            info.append((layer, norm(d), norm(mp)))
        write_cvec(work / f"{c}.gguf", direction, a.tag)
        rng = random.Random(7)
        rand = {}
        for layer in layers:
            r = [rng.gauss(0, 1) for _ in direction[layer]]
            k = norm(direction[layer]) / norm(r)
            rand[layer] = [x * k for x in r]
        write_cvec(work / f"{c}_random.gguf", rand, a.tag)
        mid = info[len(info) // 2]
        print(f"[{c}] layer {mid[0]}: vector size {mid[1]:.1f}, hidden state size {mid[2]:.1f} "
              f"({100 * mid[1] / mid[2]:.0f}% of it)", flush=True)

    # 3. steer
    for c in names:
        spec = CONCEPTS[c]
        rows = [{"condition": "baseline (no vector)", "scale": 0.0,
                 "value": sum(measure(c, t) for t in base[c]) / len(base[c]), "sample": base[c][0]}]
        runs = [(f"vector x {s:g}", s, f"{c}.gguf") for s in scales]
        runs.append((f"RANDOM vector x {max(scales):g}", max(scales), f"{c}_random.gguf"))
        for label, s, fname in runs:
            try:
                srv = Server(a.server, blob, a.port, ["--control-vector-scaled", f"{work / fname}:{s}"])
            except Exception as e:
                rows.append({"condition": label, "scale": s, "value": None, "sample": f"SERVER FAILED: {e}"})
                continue
            try:
                outs = [srv.chat(q, a.max_tokens) for q in spec["test"]]
            finally:
                srv.stop()
            rows.append({"condition": label, "scale": s,
                         "value": sum(measure(c, t) for t in outs) / len(outs), "sample": outs[0]})
            print(f"[{c}] {label}: {rows[-1]['value']:.2f}", flush=True)
        result["concepts"][c] = rows

    print("\n================ RESULT ================")
    for c in names:
        print(f"\n{c}: {UNIT[c]}   (positive strength should push it "
              f"{'DOWN' if c == 'terse' else 'UP'})")
        for r in result["concepts"][c]:
            v = "   -  " if r["value"] is None else f"{r['value']:6.2f}"
            sample = " ".join(r["sample"].split())[:110]
            print(f"  {r['condition']:<26} {v}   | {sample}")
    print(f"\ntook {time.time() - t_start:.0f} s")
    pathlib.Path(a.out).write_text(json.dumps(result, indent=1))
    print("saved", a.out)


if __name__ == "__main__":
    sys.exit(main())
