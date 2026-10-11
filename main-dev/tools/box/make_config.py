"""Write the box's council.toml from the repo default, with the settings the GX10 needs.

Run on the box:  python3 tools/box/make_config.py
Reads  config/council.toml  (repo default, mock mode)
Writes ~/council/box/config/council.toml

Environment:  COUNCIL_PROTOCOL = open (default) | structured   -> [chamber] protocol
              COUNCIL_DRIVER = llamacpp (default) | ollama
  llamacpp: one llama-server per model on the GGUF blob Ollama downloaded. Ollama is only the downloader.
  ollama:   Ollama serves the models too (fallback).
"""
import os
import pathlib
import re
import shutil
import sys

DRIVERS = ("llamacpp", "ollama")
PROTOCOLS = ("structured", "open")
OLLAMA_MODELS_DIR = "/usr/share/ollama/.ollama/models"
SHOW = r"^(mock|driver|protocol|core_models|default_timeout_s|base_url|deadline_s|min_deadline_s|max_deadline_s|k|server_bin|ctx|ollama_models_dir) "


def chosen_driver(env=None) -> str:
    value = (os.environ if env is None else env).get("COUNCIL_DRIVER", "").strip().lower() or "llamacpp"
    if value not in DRIVERS:
        raise SystemExit(f"COUNCIL_DRIVER must be one of {DRIVERS}, got {value!r}")
    return value


def chosen_protocol(env=None) -> str:
    """COUNCIL_PROTOCOL: the council protocol of the box. Default "open"."""
    value = (os.environ if env is None else env).get("COUNCIL_PROTOCOL", "").strip().lower() or "open"
    if value not in PROTOCOLS:
        raise SystemExit(f"COUNCIL_PROTOCOL must be one of {PROTOCOLS}, got {value!r}")
    return value


def set_in_section(text: str, section: str, key: str, value: str) -> str:
    """Set `key = value` inside [section]; append the key, or the whole section, when missing."""
    line = f"{key} = {value}"
    head = re.search(rf"^\[{re.escape(section)}\][ \t]*(?:#[^\n]*)?$", text, flags=re.M)
    if head is None:
        return text.rstrip("\n") + f"\n\n[{section}]\n{line}\n"
    end = re.search(r"^\[", text[head.end():], flags=re.M)
    stop = head.end() + end.start() if end else len(text)
    body = text[head.end():stop]
    new_body, n = re.subn(
        rf"^{re.escape(key)}[ \t]*=[^\n#]*(#[^\n]*)?",
        lambda m: line + (" " + m.group(1) if m.group(1) else ""),
        body, count=1, flags=re.M,
    )
    if n == 0:
        new_body = body.rstrip("\n") + f"\n{line}\n" + ("\n" if end else "")
    return text[:head.end()] + new_body + text[stop:]


def transform(text: str, driver: str, home: pathlib.Path,
              protocol: str | None = None) -> tuple[str, list[str]]:
    """The box config text from the repo default. Returns (text, warnings)."""
    warnings: list[str] = []

    def setting(pattern: str, replacement: str) -> None:
        nonlocal text
        text, n = re.subn(pattern, replacement, text, flags=re.M)
        if n == 0:
            warnings.append("no match for " + pattern)

    setting(r"^mock\s*=\s*true", "mock = false")
    setting(r'^driver\s*=\s*"[^"]*"', f'driver = "{driver}"')
    setting(r"^core_models\s*=.*$", 'core_models = ["qwen35-9b"]')
    setting(r"^default_timeout_s\s*=.*$", "default_timeout_s = 420")
    # The council's own Ollama instance (eight models loaded at once), not the shared one on 11434.
    setting(r'^base_url\s*=\s*"http://127\.0\.0\.1:11434"', 'base_url = "http://127.0.0.1:11435"')

    # Six real seats share the machine's speed: measured runs need far longer than the mock defaults.
    for mode, seconds in {"quick": 180, "standard": 900, "deep": 2400}.items():
        setting(
            rf"(\[chamber\.modes\.{mode}\]\n(?:(?!\[chamber)[^\n]*\n)*?deadline_s\s*=\s*)\d+",
            rf"\g<1>{seconds}",
        )

    # Adaptive effort scales the standard deadline from measured seat speed, inside these bounds.
    setting(r"^min_deadline_s\s*=.*$", "min_deadline_s = 120")
    setting(r"^max_deadline_s\s*=.*$", "max_deadline_s = 2400")

    if protocol:
        text = set_in_section(text, "chamber", "protocol", f'"{protocol}"')

    if driver == "llamacpp":
        server_bin = (home / "llama.cpp" / "build" / "bin" / "llama-server").as_posix()
        text = set_in_section(text, "llamacpp", "server_bin", f'"{server_bin}"')
        text = set_in_section(text, "llamacpp", "ctx", "8192")
        text = set_in_section(text, "llamacpp", "ollama_models_dir", f'"{OLLAMA_MODELS_DIR}"')
        # Lie detector: read real activations (the probes on the box were trained on them).
        # layers = [] lets each model use the layer its own probe was trained on.
        # No steering vector is made or applied on the box (the library stays in council/steer/).
        text = set_in_section(text, "steer", "enabled", "false")
        text = set_in_section(text, "probe", "source", '"llamacpp"')
        text = set_in_section(text, "probe", "layers", "[]")
        text = set_in_section(text, "probe", "ollama_models_dir", f'"{OLLAMA_MODELS_DIR}"')
        # A reading loads a second copy of the member's model (3 to 8 s) before it can capture.
        text = set_in_section(text, "lie", "timeout_s", "30")
    return text, warnings


def main() -> None:
    driver = chosen_driver()
    repo = pathlib.Path(__file__).resolve().parents[2]
    dst = pathlib.Path.home() / "council" / "box" / "config"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy(repo / "config" / "lenses.json", dst / "lenses.json")

    protocol = chosen_protocol()
    text, warnings = transform((repo / "config" / "council.toml").read_text(), driver, pathlib.Path.home(),
                               protocol)
    for w in warnings:
        print("warning:", w)
    (dst / "council.toml").write_text(text)
    print("driver:", driver)
    print("protocol:", protocol)
    print("wrote", dst / "council.toml")
    for line in text.splitlines():
        if re.match(SHOW, line):
            print("  ", line)


if __name__ == "__main__":
    main()
