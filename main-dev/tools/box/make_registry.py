"""Write ~/council/box/config/models.json from whatever models Ollama has downloaded.

Thin: council/host/discover.py finds the models and builds the entries. The eight recommended models
get their measured rows; any other chat model gets a generic entry. model_checks.json and
llamacpp_checks.json adjust entries as before. COUNCIL_ONLY_RECOMMENDED=1 keeps only the eight.
"""
import importlib.util, json, os, pathlib, sys

d = pathlib.Path.home() / "council/box/config"
CHECKS = pathlib.Path.home() / "council/box/model_checks.json"
_DISCOVER = pathlib.Path(__file__).resolve().parents[2] / "council" / "host" / "discover.py"
_spec = importlib.util.spec_from_file_location("council_host_discover_tool", _DISCOVER)
discover = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = discover
_spec.loader.exec_module(discover)


def _llamacpp_checks():
    """Results of tools/box/llamacpp_check.py, keyed by tag. None unless the box serves with llama.cpp."""
    if os.environ.get("COUNCIL_DRIVER", "llamacpp") != "llamacpp": return None
    f = pathlib.Path.home() / "council/box/llamacpp_checks.json"
    try: return {r["tag"]: r for r in json.loads(f.read_text())}
    except Exception: return None


LLAMACPP = _llamacpp_checks()
P, T, N, E = discover.P, discover.T, discover.N, discover.E
L = list(discover.ALL_ROWS)  # every tuned row: the eight, gemma 4-bit, and the three llama.cpp cannot run


def load_checks(path=CHECKS):
    try:
        with open(path) as f: c = json.load(f)
        return c if isinstance(c, dict) else None
    except Exception:
        return None


def build_entry(row, checks=None, notes=None):
    """One registry entry from a table row; measured values from `checks` (or None) win over estimates."""
    return discover.row_entry(row, checks, LLAMACPP, notes)


def build_registry(installed, checks=None, llamacpp=LLAMACPP, budget_gib=None, only_recommended=False):
    """(entries, notes). `installed`: tags, or the dicts of discover.installed_tags()."""
    tags = sorted(installed) if isinstance(installed, (set, frozenset)) else list(installed)
    out, notes = discover.build_registry(tags, checks, llamacpp, budget_gib)
    if only_recommended:
        out = [m for m in out if m["recommended"]]
        notes.append("COUNCIL_ONLY_RECOMMENDED: kept only the recommended models")
    return out, notes


def memory_budget_gib():
    """COUNCIL_BUDGET_GIB, else this machine's memory minus 12 GiB, else None (no limit applied)."""
    try: return float(os.environ["COUNCIL_BUDGET_GIB"])
    except (KeyError, ValueError): pass
    try:
        for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"): return round(int(line.split()[1]) / 1048576 - 12, 1)
    except Exception: pass
    return None


if __name__ == "__main__":
    driver_is_llamacpp = os.environ.get("COUNCIL_DRIVER", "llamacpp") == "llamacpp"
    # Under llama.cpp with no check file yet, {} still marks the models known not to run under it.
    llamacpp = LLAMACPP if LLAMACPP is not None else ({} if driver_is_llamacpp else None)
    checks = load_checks()
    found = discover.installed_tags()
    out, notes = build_registry(found, checks, llamacpp, memory_budget_gib(),
                                os.environ.get("COUNCIL_ONLY_RECOMMENDED") == "1")
    d.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(d / "models.json", "w"), indent=1)
    print(len(out), "registered:", [m["id"] for m in out]); print("labs:", sorted({m["lab"] for m in out}))
    print("from measurements:" if checks is not None else "no model_checks.json: using estimates")
    for n in notes: print(" ", n)
