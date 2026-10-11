"""Train the truth probe of one model from instruction-free pairs (ARCHITECTURE 28.4).

    python -m council.probe.train_cli --model ID [--tasks PATH] [--layers 8,16,24 | auto]
        [--limit N] [--source mock|llamacpp] [--out PATH] [--seed N] [--min-auroc X]

No controller, no gateway, no model server: config and registry come from COUNCIL_HOME, the
activation source is built the way probe/service.py builds it, and the Probe goes into the
store kv namespace "probes" under the model id AND into <COUNCIL_HOME>/probes as a file
(probe/probe_files.py), with its card, its Platt pair and the text layout it was trained on.
The reliability service reads both.

- --tasks: a benchmark JSONL. Without it the built-in true/false statements are used: the
  four kinds of probe/dataset.py plus the twelve kinds of probe/truth_set.py (600 by default).
- --layers auto: picked from the model depth when the source knows it (llamacpp), else the
  configured layers.
- --source: default is [probe] source of the config when it is mock or llamacpp, else mock.
- --out: the report JSON. Default <COUNCIL_HOME>/bench/results/probe_<model>.json.

The probe is trained on the one probe layout, probe/layout.py probe_messages(task, statement):
"Question: ...\\nStatement: ...\\nThe statement above is" in one user message, the same text a
live claim is scored on. It is a true-statement-versus-false-statement probe on that framing.
Whether it is switched on is decided by probe/gate.py from the held-out AUROC, the
shuffled-label control and the surface-feature baseline.

Exit code 0 when training ran (validated or not), 1 on any error.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, TextIO

from council.bench.graders import load_tasks
from council.core import config as config_mod
from council.core.schemas import Probe
from council.core.store import Store
from council.probe import service, trainer
from council.probe.dataset import Pair, make_pairs
from council.probe.llamacpp_source import pick_layers
from council.probe.probe_files import ProbeFiles

SOURCES = ("mock", "llamacpp")
DEFAULT_STATEMENTS = trainer.BUILTIN_PAIRS


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m council.probe.train_cli",
                                description="Train the truth probe of one model.")
    p.add_argument("--model", required=True, help="model id of the registry (or an Ollama tag)")
    p.add_argument("--tasks", default=None, help="benchmark JSONL (default: built-in statements)")
    p.add_argument("--layers", default="auto", help='comma list such as "8,16,24", or "auto"')
    p.add_argument("--limit", type=int, default=None, help="use at most N questions")
    p.add_argument("--source", default=None, choices=SOURCES, help="activation source")
    p.add_argument("--out", default=None, help="where the report JSON is written")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--min-auroc", type=float, default=None, help="default: [probe] min_auroc")
    return p


def parse_layers(text: str) -> Optional[list[int]]:
    """None for "auto", else the layers in the order given, no repeats."""
    s = (text or "").strip().lower()
    if s in ("", "auto"):
        return None
    try:
        layers = [int(part) for part in s.split(",") if part.strip()]
    except ValueError:
        raise ValueError(f'--layers must be "auto" or a comma list of numbers, not {text!r}') from None
    if not layers:
        raise ValueError("--layers names no layer")
    return list(dict.fromkeys(layers))


def build_pairs(tasks_path: Optional[str], limit: Optional[int], seed: int) -> tuple[list[Pair], str]:
    """(pairs, where they came from)."""
    if limit is not None and limit <= 0:
        raise ValueError("--limit must be positive")
    if tasks_path:
        path = Path(tasks_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"tasks file not found: {path}")
        pairs = make_pairs(load_tasks(path), seed)
        if limit is not None:
            pairs = pairs[:limit]
        return pairs, str(path)
    return trainer.builtin_pairs(seed, limit or DEFAULT_STATEMENTS), "built-in statements"


def build_source(cfg: Any, registry: list, kind: str) -> Any:
    """The activation source, built by probe/service.py from the probe config and the registry."""
    pcfg = cfg.probe.model_copy(update={"source": kind, "enabled": True})
    source = service.build_source(pcfg, SimpleNamespace(registry=list(registry)))
    if source is None:
        raise RuntimeError(f"cannot build the activation source {kind!r}")
    return source


async def resolve_layers(source: Any, model_id: str, wanted: Optional[list[int]],
                         configured: list[int]) -> list[int]:
    """Explicit layers the model has, or (auto) layers from its depth, or the configured ones."""
    pseudo = getattr(source, "PSEUDO_LAYER", None)
    if pseudo is not None:
        return [pseudo]
    info = getattr(source, "info", None)
    n_layer = int((await info(model_id)).get("n_layer", 0)) if callable(info) else 0
    if wanted is None:
        if n_layer > 0:
            return pick_layers(n_layer)
        return [int(l) for l in configured] or list(service.DEFAULT_LAYERS)
    if n_layer > 0:
        kept = [l for l in wanted if 0 <= l < n_layer]
        if not kept:
            raise ValueError(f"model {model_id} has layers 0..{n_layer - 1}; none of {wanted} exist")
        return kept
    return wanted


def _num(value: Any) -> str:
    return "  -  " if value is None else f"{float(value):.3f}"


def format_report(report: dict, source_kind: str = "", pairs_from: str = "") -> str:
    """The table and the verdict, as plain text."""
    lines = [
        f"probe training: model {report.get('model_id')}  source {source_kind or '?'}  "
        f"pairs from {pairs_from or '?'}",
        f"questions: {report.get('n_used')} used of {report.get('n_pairs')} "
        f"(train {report.get('n_train_pairs')}, select {report.get('n_select_pairs')}, "
        f"test {report.get('n_test_pairs')}); capture errors {report.get('n_capture_errors', 0)}",
        "",
        f"{'layer':>5}  {'n_train':>7}  {'n_test':>6}  {'AUROC':>6}  {'shuffled':>8}  "
        f"{'cheap':>6}  pick",
    ]
    for row in report.get("layers", []):
        lines.append(
            f"{row['layer']:>5}  {row['n_train']:>7}  {row['n_test']:>6}  {_num(row['auroc']):>6}  "
            f"{_num(row['shuffled_auroc']):>8}  {_num(row['cheap_auroc']):>6}  "
            f"{'*' if row.get('picked') else ''}")
    if not report.get("layers"):
        lines.append("(no layer was trained)")
    lines.append("")
    lines.append("n_train and n_test are rows, two per question. shuffled: labels shuffled, "
                 "should be near 0.5. cheap: answer length and token counts only.")
    if report.get("accuracy") is not None:
        platt = report.get("platt")
        lines.append(
            f"accuracy {_num(report.get('accuracy'))}  calibration error {_num(report.get('ece'))}  "
            + (f"platt a={platt[0]:.2f} b={platt[1]:.2f} (fitted on the {report.get('platt_on')} rows)"
               if platt else "no platt fit"))
    status = str(report.get("status", "rejected")).upper()
    if report.get("best_layer") is None:
        lines.append(f"verdict: {status}")
    else:
        lines.append(
            f"verdict: {status}  layer {report['best_layer']}  held-out AUROC "
            f"{_num(report.get('auroc'))}  (needs >= {report.get('min_auroc'):.2f} and >= cheap "
            f"{_num(report.get('cheap_auroc'))} + {report.get('margin'):.2f})")
    if "active" in report:
        lines.append(f"live scoring: {'ON' if report['active'] else 'off'}  "
                     f"({report.get('gate_reason', '')})")
    for reason in report.get("reasons", []):
        lines.append(f"  why: {reason}")
    for warning in report.get("warnings", []):
        lines.append(f"  warning: {warning}")
    return "\n".join(lines)


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or "model"


async def _train(args: argparse.Namespace, cfg: Any, registry: list, kind: str,
                 pairs: list[Pair], source: Any, err: TextIO) -> dict:
    own = source is None
    if own:
        source = build_source(cfg, registry, kind)

    def progress(done: int, total: int) -> None:
        if done == total or done % 25 == 0:
            print(f"captured {done}/{total} questions", file=err, flush=True)

    try:
        layers = await resolve_layers(source, args.model, parse_layers(args.layers),
                                      list(cfg.probe.layers))
        min_auroc = float(cfg.probe.min_auroc if args.min_auroc is None else args.min_auroc)
        return await trainer.train_from_pairs(
            source, args.model, pairs, layers, min_auroc, time.time(), args.seed,
            progress=progress)
    finally:
        close = getattr(source, "close", None)
        if callable(close):
            try:
                await close()
            except Exception:
                pass


def main(argv: Optional[list[str]] = None, out: Optional[TextIO] = None,
         err: Optional[TextIO] = None, store: Any = None, source: Any = None) -> int:
    """`store` and `source` are for tests; by default both are built from COUNCIL_HOME."""
    out = out or sys.stdout
    err = err or sys.stderr
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return 0 if e.code in (0, None) else 1
    own_store = None
    try:
        parse_layers(args.layers)  # a bad value fails before any model is loaded
        home = config_mod.home()
        cfg = config_mod.load_config(home / "config" / "council.toml")
        registry = config_mod.load_registry(home / "config" / "models.json")
        kind = args.source or (cfg.probe.source if cfg.probe.source in SOURCES else "mock")
        pairs, pairs_from = build_pairs(args.tasks, args.limit, args.seed)
        if not pairs:
            raise ValueError(f"no usable question in {pairs_from}")
        report = asyncio.run(_train(args, cfg, registry, kind, pairs, source, err))
        report["source"] = service.source_kind(source) if source is not None else kind
        report["pairs_from"] = pairs_from

        probe = Probe.model_validate(report["probe"])
        if store is None:
            own_store = store = Store(home / "db" / "council.db")
        card = service.persist_report(store, ProbeFiles(home), args.model, report,
                                      report["source"])
        report["card"] = card.model_dump()

        out_path = Path(args.out).expanduser() if args.out else (
            home / "bench" / "results" / f"probe_{_slug(args.model)}.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        print(format_report(report, report["source"], pairs_from), file=out)
        print(f"probe stored: kv {service.NS}/{args.model} (status {probe.status}) and "
              f"{home / 'probes'} (version {card.version})", file=out)
        print(f"report: {out_path}", file=out)
        return 0
    except Exception as e:
        print(f"error: {e}", file=err)
        return 1
    finally:
        if own_store is not None:
            own_store.close()


if __name__ == "__main__":
    sys.exit(main())
