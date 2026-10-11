"""Find the chat models Ollama has downloaded and turn them into registry entries.

The council is not tied to a model list. Whatever Ollama has is read from its store (no running
Ollama needed), each model becomes a registry entry, and the router seats 2 to 6 of them.

RECOMMENDED holds the eight models tuned on the ASUS Ascent GX10. When one is installed it gets its
measured row; every other model gets a generic entry whose priors sit GENERIC_PENALTY lower, so with
equal fit the router prefers the recommended eight. ModelEntry ignores unknown fields, so the
"recommended" and "note" keys of an entry are for people and the CLI; the preference is the priors.

Standard library only (tools/box/make_registry.py loads this file by path with the system Python).
Pure except installed_tags (reads the store, may run "ollama list" once).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

MIN_SEATS = 2
MAX_SEATS = 6
MAX_PER_LAB = 2  # the router allows two models of one lab once it has relaxed its lab rule
GENERIC_PENALTY = 0.08
OLLAMA_LIST_TIMEOUT_S = 10
SYSTEM_STORE = Path("/usr/share/ollama/.ollama/models")

P = {"math": .6, "logic": .6, "code": .6, "science": .6, "knowledge": .6, "reading": .6, "writing": .6,
     "planning": .6}
GENERIC_PRIORS = {k: round(v - GENERIC_PENALTY, 4) for k, v in P.items()}
T = {"kind": "toggle", "off": {"think": False}, "council": {"think": False}, "max": {"think": True}}
N = {"kind": "none", "off": {}, "council": {}, "max": {}}
E = {"kind": "effort", "off": {"think": "low"}, "council": {"think": "medium"}, "max": {"think": "high"}}
A = {"kind": "always", "off": {"think": True}, "council": {"think": True}, "max": {"think": True}}

# Row: id, tag, display, lab, lineage, arch, params_b, ram GiB, tokens/s, reasoning, roles, priors.
RECOMMENDED = [
    ("gpt-oss-20b", "gpt-oss:20b", "gpt-oss 20B", "openai", "gpt-oss", "moe", 21, 13.9, 58.8, E, ["seat", "planner"], {"logic": .75, "math": .72, "planning": .68}),
    ("qwen35-9b", "qwen3.5:9b-q8_0", "Qwen3.5 9B", "alibaba", "qwen3.5", "dense", 9, 10.3, 25.8, T, ["seat", "worker", "clerk"], {"code": .64}),
    ("qwen3-14b", "qwen3:14b", "Qwen3 14B", "alibaba", "qwen3", "dense", 14, 12.0, 25, T, ["seat", "senior_worker"], {"code": .7, "math": .66}),
    ("phi4-14b", "phi4:14b", "Phi-4 14B", "microsoft", "phi4", "dense", 14, 12.0, 25, N, ["seat"], {"math": .7, "logic": .7, "science": .66}),
    ("granite41-8b", "granite4.1:8b-q8_0", "Granite 4.1 8B", "ibm", "granite4", "dense", 8, 12.0, 25, N, ["seat"], {"knowledge": .64, "reading": .64}),
    ("deepseek-r1-14b", "deepseek-r1:14b", "DeepSeek R1 14B", "deepseek", "qwen2.5", "dense", 14, 12.0, 25, A, ["seat"], {"math": .72, "logic": .74}),
    ("falcon3-10b", "falcon3:10b-instruct-q8_0", "Falcon3 10B", "tii", "falcon3", "dense", 10, 13.5, 20, N, ["seat"], {"knowledge": .62}),
    ("gemma4-12b", "gemma4:12b-it-q8_0", "Gemma 4 12B", "google", "gemma4", "dense", 12, 14.7, 16.8, T, ["seat"], {"writing": .7, "reading": .7, "knowledge": .66}),
]
# Tuned rows that are not one of the eight (kept from the old hand table).
ALSO_TUNED = [
    ("gemma4-12b-q4", "gemma4:12b-it-q4_K_M", "Gemma 4 12B (4-bit)", "google", "gemma4", "dense", 12, 11.0, 30, T, ["seat"], {"writing": .7, "reading": .7, "knowledge": .66}),
]
# (row, reason): the Ollama files of these do not run under plain llama.cpp. Listed, not seated.
KNOWN_BAD = [
    (("ministral3-14b", "ministral-3:14b", "Ministral 3 14B", "mistral", "ministral3", "dense", 14, 12.0, 25, N, ["seat"], {"writing": .68, "planning": .66, "knowledge": .64}),
     "cannot run under llama.cpp (vision model packed into one Ollama file)"),
    (("phi4-reasoning", "phi4-reasoning:plus", "Phi-4 Reasoning Plus", "microsoft", "phi4", "dense", 14, 14.0, 22, {"kind": "always", "off": {}, "council": {}, "max": {}}, ["seat"], {"math": .75, "logic": .75, "science": .7}),
     "cannot run under llama.cpp (its thinking runs into the answer)"),
    (("mistral-small32", "mistral-small3.2:24b", "Mistral Small 3.2 24B", "mistral", "mistral-small3", "dense", 24, 18.5, 14, N, ["seat"], {"writing": .72, "planning": .7, "knowledge": .7}),
     "cannot run under llama.cpp (vision model packed into one Ollama file)"),
]
RECOMMENDED_TAGS = tuple(r[1] for r in RECOMMENDED)
KNOWN_BAD_REASON = {row[1]: why for row, why in KNOWN_BAD}
ALL_ROWS = RECOMMENDED + ALSO_TUNED + [row for row, _ in KNOWN_BAD]
ROW_BY_TAG = {r[1]: r for r in ALL_ROWS}

# Family name prefix -> lab. First match wins.
LABS = [("codellama", "meta"), ("llama", "meta"), ("qwen", "alibaba"), ("qwq", "alibaba"), ("gemma", "google"),
        ("phi", "microsoft"), ("mistral", "mistral"), ("mixtral", "mistral"), ("ministral", "mistral"),
        ("codestral", "mistral"), ("devstral", "mistral"), ("granite", "ibm"), ("deepseek", "deepseek"),
        ("falcon", "tii"), ("gpt-oss", "openai"), ("command", "cohere"), ("aya", "cohere"),
        ("nemotron", "nvidia"), ("glm", "zhipu")]
EMBED_WORDS = ("embed", "bge", "nomic", "minilm", "e5")
_UNITS = {"KB": 1e3 / 1e9, "MB": 1e6 / 1e9, "GB": 1.0, "TB": 1e3, "B": 1 / 1e9}


# --------------------------------------------------------------------------------------
# What is installed
# --------------------------------------------------------------------------------------


def default_models_dir() -> Path:
    env = os.environ.get("OLLAMA_MODELS")
    if env:
        return Path(env)
    if SYSTEM_STORE.is_dir():
        return SYSTEM_STORE
    return Path.home() / ".ollama" / "models"


def _tag_name(registry: str, namespace: str, name: str, tag: str) -> str:
    if namespace == "library" and registry == "registry.ollama.ai":
        return f"{name}:{tag}"
    if registry == "registry.ollama.ai":
        return f"{namespace}/{name}:{tag}"
    return f"{registry}/{namespace}/{name}:{tag}"


def _from_store(models_dir: Path) -> list[dict]:
    out: list[dict] = []
    root = models_dir / "manifests"
    try:
        files = sorted(p for p in root.glob("*/*/*/*") if p.is_file())
    except OSError:
        return out
    for path in files:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            layers = manifest.get("layers") or []
        except (OSError, ValueError, AttributeError):
            continue
        size = None
        blob = None
        projector = False
        for layer in layers:
            if not isinstance(layer, dict):
                continue
            media = str(layer.get("mediaType") or "")
            if media.endswith("image.model"):
                try:
                    size = round(float(layer.get("size")) / 1e9, 2)
                except (TypeError, ValueError):
                    size = None
                digest = str(layer.get("digest") or "")
                if digest:
                    blob = str(models_dir / "blobs" / digest.replace(":", "-"))
            elif "projector" in media:
                projector = True
        if blob is None and size is None:
            continue  # not a model manifest
        reg, ns, name, tag = path.parts[-4:]
        out.append({"tag": _tag_name(reg, ns, name, tag), "size_gb": size, "blob": blob,
                    "has_projector": projector, "source": "store"})
    return out


def parse_ollama_list(text: str) -> list[dict]:
    """Rows of "ollama list" (NAME ID SIZE MODIFIED)."""
    out: list[dict] = []
    for line in str(text or "").splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0].upper() == "NAME":
            continue
        size = None
        for i in range(1, len(parts) - 1):
            unit = parts[i + 1].upper()
            if unit in _UNITS:
                try:
                    size = round(float(parts[i]) * _UNITS[unit], 2)
                    break
                except ValueError:
                    continue
        out.append({"tag": parts[0], "size_gb": size, "blob": None, "has_projector": False,
                    "source": "ollama list"})
    return out


def _run_ollama_list() -> str:
    exe = shutil.which("ollama")
    if not exe:
        return ""
    try:
        done = subprocess.run([exe, "list"], capture_output=True, text=True, timeout=OLLAMA_LIST_TIMEOUT_S)
        return done.stdout if done.returncode == 0 else ""
    except Exception:
        return ""


def installed_tags(models_dir: Path | None = None, ollama_list_text: str | None = None) -> list[dict]:
    """Every model Ollama has: [{tag, size_gb, blob, has_projector, source}]. Never raises.

    The store folder is read first. "ollama list" text is added when given; the command itself is
    run only when the folder gave nothing and no text was given.
    """
    found = _from_store(Path(models_dir) if models_dir is not None else default_models_dir())
    if ollama_list_text is None and not found:
        ollama_list_text = _run_ollama_list()
    have = {t["tag"] for t in found}
    for row in parse_ollama_list(ollama_list_text or ""):
        if row["tag"] not in have:
            have.add(row["tag"])
            found.append(row)
    return found


# --------------------------------------------------------------------------------------
# Registry entries
# --------------------------------------------------------------------------------------


def row_entry(row: tuple, checks: dict | None = None, llamacpp: dict | None = None,
              notes: list | None = None) -> dict:
    """One registry entry from a table row. Measured values from `checks` win over estimates.

    `llamacpp` is the result of tools/box/llamacpp_check.py keyed by tag, or None when the box does
    not serve with llama.cpp.
    """
    id, tag, disp, lab, lin, arch, pb, ram, tps, r, roles, pri = row
    notes = notes if notes is not None else []
    c = (checks or {}).get(tag)
    quarantined = False
    svr = None
    if c:
        if c.get("ok") is False:
            quarantined = True
            notes.append(f"{id}: quarantined (check failed: {str(c.get('error'))[:60]})")
        if c.get("ram_gib"):
            ram = c["ram_gib"]
            notes.append(f"{id}: ram_gb {ram} measured")
        if c.get("tps"):
            tps = c["tps"]
            notes.append(f"{id}: tps {tps} measured")
        if c.get("think_ok") is False and r["kind"] != "none":
            r = N
            notes.append(f"{id}: reasoning none (think not accepted)")
        if c.get("json_ok") is not None:
            svr = 1.0 if c["json_ok"] else 0.0
            notes.append(f"{id}: json {'ok' if c['json_ok'] else 'FAILED'} measured")
    lc = (llamacpp or {}).get(tag)
    if lc is not None:
        # llama.cpp cannot load some Ollama files, and one model never stops thinking under it.
        off = lc.get("think_off") or {}
        if lc.get("load_error"):
            quarantined = True
            notes.append(f"{id}: quarantined under llama.cpp (cannot load)")
        elif off.get("finish") == "length" and not off.get("reasoning_len"):
            quarantined = True
            notes.append(f"{id}: quarantined under llama.cpp (thinking runs into the answer)")
    return {
        "id": id, "ollama_tag": tag, "display": disp, "lab": lab, "lineage": lin, "arch": arch, "params_b": pb,
        "active_params_b": 3.6 if arch == "moe" else pb, "quant": "Q8" if "q8" in tag else "Q4",
        "source": {"repo": "ollama:" + tag, "file": "", "sha256": None, "license": None}, "roles": list(roles),
        "modalities": ["text"],
        "serve": {"live": {"ctx": 16384, "parallel": 1}, "batch": {"ctx": 8192, "parallel": 8}, "extra_args": []},
        "reasoning": r, "structured": ("prompt_only" if (llamacpp is not None and "gpt-oss" in tag) else "grammar"),
        "sampling": {}, "priors": {**P, **pri},
        "measured": {"ram_gb_live": ram, "ram_gb_batch": ram, "load_s": 8, "tps_1": tps, "tps_8": None,
                     "tps_32": None, "structured_valid_rate": svr, "probe_date": None},
        # Models that will not load on the box yet are kept in the list but not seated.
        "status": "quarantined" if quarantined else "active",
    }


def model_name(tag: str) -> str:
    """"hf.co/org/Llama3.3:70b" -> "llama3.3"."""
    return str(tag).split(":")[0].split("/")[-1].lower()


def family_of(tag: str) -> str:
    """Letters before the first digit: "llama3.3:70b" -> "llama", "deepseek-r1:14b" -> "deepseek-r"."""
    name = model_name(tag)
    return re.split(r"\d", name)[0].strip("-._") or name


def slug(tag: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(tag).lower()).strip("-") or "model"


def lab_of(tag: str) -> tuple[str, str]:
    """(lab, lineage). Unknown families get the lab "unknown:<family>" so each counts as its own lab."""
    name = model_name(tag)
    for prefix, lab in LABS:
        if name.startswith(prefix):
            return lab, name
    if "llama" in name:
        return "meta", name
    family = family_of(tag)
    return f"unknown:{family}", family


def quant_of(tag: str) -> str:
    low = str(tag).lower()
    m = re.search(r"(?:^|[-_:])(q\d|fp?16|f32)", low)
    if not m:
        return "Q4"  # what Ollama downloads by default
    return m.group(1).upper().replace("FP16", "F16")


def params_of(tag: str, size_gb: float | None = None) -> float | None:
    """Billions of parameters: from the tag ("14b", "e2b", "270m"), else from the file size."""
    low = str(tag).lower()
    m = re.search(r"(?:^|[:\-_])e?(\d+(?:\.\d+)?)([bm])(?=$|[\-_:])", low)
    if m:
        value = float(m.group(1))
        return value if m.group(2) == "b" else round(value / 1000.0, 3)
    if size_gb:
        return round(float(size_gb) / (1.1 if quant_of(tag) == "Q8" else 0.7), 1)
    return None


def display_of(tag: str) -> str:
    """"llama3.3:70b" -> "Llama 3.3 70B"."""
    name = re.sub(r"(?<=[a-z]{3})(?=\d)", " ", model_name(tag))
    words = ["-".join(p[:1].upper() + p[1:] for p in w.split("-")) for w in name.split()]
    m = re.search(r"(?:^|[:\-_])(e?\d+(?:\.\d+)?[bm])(?=$|[\-_:])", str(tag).lower().split(":", 1)[-1] if ":" in tag else "")
    if m:
        words.append(m.group(1).upper())
    return " ".join(words)


def reasoning_of(tag: str) -> dict:
    name = model_name(tag)
    if name.startswith("deepseek-r1"):
        return A
    if name.startswith("gpt-oss"):
        return E
    if name.startswith(("qwen3", "qwq", "gemma4")):
        return T
    return N


def is_embedding(tag: str) -> bool:
    name = model_name(tag)
    return any(w in name for w in EMBED_WORDS)


def _generic_row(info: dict) -> tuple:
    tag = info["tag"]
    size = info.get("size_gb")
    params = params_of(tag, size)
    if size:
        ram = round(float(size) * 1.25 + 1.5, 1)
    elif params:
        ram = round(params * 0.7 + 2.0, 1)
    else:
        ram = None
    lab, lineage = lab_of(tag)
    return (slug(tag), tag, display_of(tag), lab, lineage, "dense", params, ram, None, reasoning_of(tag),
            ["seat"], dict(GENERIC_PRIORS))


def _entry(info: dict, checks: dict | None, llamacpp: dict | None) -> tuple[dict, list[str]]:
    tag = info["tag"]
    notes: list[str] = []
    row = ROW_BY_TAG.get(tag)
    reasons: list[str] = []
    if row is not None:
        e = row_entry(row, checks, llamacpp, notes)
        if tag in KNOWN_BAD_REASON and llamacpp is not None:
            reasons.append(KNOWN_BAD_REASON[tag])
    else:
        e = row_entry(_generic_row(info), checks, llamacpp, notes)
        e["quant"] = quant_of(tag)
        if info.get("has_projector"):
            reasons.append("vision model packed the Ollama way: plain llama.cpp cannot load it")
        if is_embedding(tag):
            reasons.append("embedding model, not a chat model")
        if re.search(r"[:\-]cloud$", tag.lower()):
            reasons.append("Ollama cloud model: there is no local file to run")
        if e["measured"]["ram_gb_live"] is None:
            reasons.append("size unknown")
    if reasons:
        e["status"] = "quarantined"
    reasons += [n.split(": ", 1)[1] for n in notes if "quarantined" in n]
    e["recommended"] = tag in RECOMMENDED_TAGS
    e["note"] = "; ".join(dict.fromkeys(reasons))
    return e, notes


def entry_for(tag_info: dict, checks: dict | None = None, llamacpp: dict | None = None) -> dict:
    """The registry entry for one installed model (a dict from installed_tags, or just {"tag": ...}).

    Two keys beyond the old shape: "recommended" (one of the eight) and "note" (why it is not seated).
    """
    return _entry(dict(tag_info), checks, llamacpp)[0]


def build_registry(tags: list, checks: dict | None = None, llamacpp: dict | None = None,
                   budget_gib: float | None = None) -> tuple[list[dict], list[str]]:
    """(entries, notes in plain words). Recommended models first, then the other tuned rows, then the rest."""
    infos: dict[str, dict] = {}
    for t in tags or []:
        info = {"tag": t} if isinstance(t, str) else dict(t)
        if info.get("tag"):
            infos.setdefault(info["tag"], info)
    order = {r[1]: i for i, r in enumerate(ALL_ROWS)}
    ordered = sorted(infos.values(), key=lambda i: (order.get(i["tag"], len(order)), i["tag"]))
    entries: list[dict] = []
    detail: list[str] = []
    ids: set[str] = set()
    for info in ordered:
        e, notes = _entry(info, checks, llamacpp)
        base, n = e["id"], 2
        while e["id"] in ids:
            e["id"] = f"{base}-{n}"
            n += 1
        ids.add(e["id"])
        ram = e["measured"]["ram_gb_live"]
        if budget_gib is not None and ram is not None and e["status"] == "active" and ram > budget_gib:
            e["status"] = "quarantined"
            e["note"] = f"needs about {ram:g} GiB, more than the memory budget of {budget_gib:g} GiB"
        if e["status"] != "active" and e["note"]:
            detail.append(f"{e['ollama_tag']}: not seated: {e['note']}")
        detail.extend(n for n in notes if "quarantined" not in n)
        entries.append(e)
    usable = [e for e in entries if e["status"] == "active"]
    have_rec = [e["ollama_tag"] for e in entries if e["recommended"]]
    missing = [t for t in RECOMMENDED_TAGS if t not in have_rec]
    notes_out = [f"{len(entries)} models installed, {len(have_rec)} of the {len(RECOMMENDED_TAGS)} recommended present"]
    if missing:
        notes_out.append("recommended models not installed: " + ", ".join(missing))
    labs: dict[str, int] = {}
    for e in usable:
        labs[e["lab"]] = labs.get(e["lab"], 0) + 1
    together = min(MAX_SEATS, sum(min(MAX_PER_LAB, n) for n in labs.values()))
    line = f"The council seats {MIN_SEATS} to {MAX_SEATS} models: {len(usable)} usable"
    if together < min(MAX_SEATS, len(usable)):
        line += f", {together} can sit together (at most {MAX_PER_LAB} models of one lab)"
    notes_out.append(line)
    if len(usable) < MIN_SEATS:
        notes_out.append(f"at least {MIN_SEATS} usable models are needed; run tools/box/pull_models.sh")
    return entries, notes_out + detail


def table_text(entries: list[dict], sizes: dict | None = None) -> str:
    """Plain table for the CLI: tag, size, recommended, status, reason."""
    sizes = sizes or {}
    rows = [("TAG", "SIZE", "RECOMMENDED", "STATUS", "REASON")]
    for e in entries:
        size = sizes.get(e["ollama_tag"])
        usable = e["status"] == "active"
        rows.append((e["ollama_tag"], f"{size:g} GB" if size else "-", "yes" if e.get("recommended") else "no",
                     "usable" if usable else "not seated", "" if usable else (e.get("note") or e["status"])))
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    return "\n".join("  ".join(c.ljust(widths[i]) if i < 4 else c for i, c in enumerate(r)).rstrip() for r in rows)


__all__ = ["RECOMMENDED", "ALSO_TUNED", "KNOWN_BAD", "RECOMMENDED_TAGS", "ALL_ROWS", "GENERIC_PRIORS",
           "installed_tags", "parse_ollama_list", "default_models_dir", "entry_for", "row_entry",
           "build_registry", "table_text"]
