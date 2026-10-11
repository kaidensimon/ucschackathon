"""Train the lie-detector probe of many models, one after another.

    python -m council.probe.train_all [--models a,b,c] [--state FILE]

Each model's activation process holds a full copy of the model, so never two at once: the loop is
strictly sequential and calls `release(model_id)` after every model, failed or not.

How the default `train_one` works: probe/train_cli.py exposes only `main(argv)` (its helpers are
private and build their own source), so this module calls `train_cli.main(["--model", id, ...])`
in a worker thread (it runs its own event loop). That call trains, stores the Probe in the kv
namespace "probes" and writes the report JSON to the default path
<COUNCIL_HOME>/bench/results/probe_<model>.json. Exit code 1 -> the model counts as failed.
Exit code 0 -> the report file is read back and turned into a ProbeCard by `card_from_report`.

State file: a JSON list of ProbeCard dicts, rewritten after every model. On start, models with a
card whose reason does not start with "training failed" are skipped (resume).
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from council.core.schemas_v15 import ProbeCard

FAIL_PREFIX = "training failed"
ERROR_CLIP = 200

TrainOne = Callable[[str], Awaitable[ProbeCard]]
Release = Callable[[str], Awaitable[None]]
Progress = Callable[[str, str], None]


def _load_state(state_path: Optional[Path]) -> dict[str, ProbeCard]:
    if state_path is None or not Path(state_path).is_file():
        return {}
    try:
        raw = json.loads(Path(state_path).read_text(encoding="utf-8"))
        cards = [ProbeCard.model_validate(item) for item in raw]
    except Exception:
        return {}  # a broken state file means start over, not crash
    return {c.model_id: c for c in cards}


def _save_state(state_path: Optional[Path], cards: list[ProbeCard]) -> None:
    if state_path is None:
        return
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps([c.model_dump() for c in cards], indent=2), encoding="utf-8")
    tmp.replace(path)


def _failed_card(model_id: str, error: BaseException) -> ProbeCard:
    text = f"{type(error).__name__}: {error}" if str(error) else type(error).__name__
    return ProbeCard(model_id=model_id, active=False,
                     reason=f"{FAIL_PREFIX}: {text[:ERROR_CLIP]}")


async def train_models(model_ids: list[str], train_one: TrainOne,
                       release: Optional[Release] = None,
                       progress: Optional[Progress] = None,
                       state_path: Optional[Path] = None) -> list[ProbeCard]:
    """Train each model in order, never two at once. A failure becomes an inactive card."""
    say = progress or (lambda _m, _s: None)
    done = _load_state(state_path)
    results: dict[str, ProbeCard] = {}  # insertion order = run order; drives what the state holds

    def write() -> None:
        # State keeps cards of models not in this run too, so a narrower run loses nothing.
        merged = {**done, **results}
        _save_state(state_path, list(merged.values()))

    ordered: list[str] = list(dict.fromkeys(model_ids))
    for model_id in ordered:
        prior = done.get(model_id)
        if prior is not None and not prior.reason.startswith(FAIL_PREFIX):
            say(model_id, "skipped, already trained")
            results[model_id] = prior
            continue
        say(model_id, "training")
        try:
            card = await train_one(model_id)
            say(model_id, "done")
        except Exception as e:  # CancelledError is not an Exception: it still stops the loop
            card = _failed_card(model_id, e)
            say(model_id, card.reason)
        results[model_id] = card
        if release is not None:
            try:
                await release(model_id)
            except Exception as e:
                say(model_id, f"release failed: {str(e)[:ERROR_CLIP]}")
        write()
    return [results[m] for m in ordered]


def _fmt(value: Optional[float]) -> str:
    return "-" if value is None else f"{value:.3f}"


def summary_text(cards: list[ProbeCard]) -> str:
    """Plain table: model, auroc, control, baseline, n_test, active, reason."""
    header = ["model", "auroc", "control", "baseline", "n_test", "active", "reason"]
    rows = [[c.model_id, _fmt(c.auroc), _fmt(c.control_auroc), _fmt(c.baseline_auroc),
             str(c.n_test), "yes" if c.active else "no", c.reason.replace("\n", " ")] for c in cards]
    widths = [max(len(header[i]), *(len(r[i]) for r in rows)) if rows else len(header[i])
              for i in range(len(header))]

    def line(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)).rstrip()

    out = [line(header), line(["-" * w for w in widths])] + [line(r) for r in rows]
    n_active = sum(1 for c in cards if c.active)
    out.append(f"{n_active} of {len(cards)} probes active")
    return "\n".join(out)


def card_from_report(model_id: str, report: dict, now: float = 0.0) -> ProbeCard:
    """Pure: train_cli report dict -> ProbeCard. Active means the trainer validated the probe."""
    best = report.get("best_layer")
    row = next((r for r in report.get("layers", []) if r.get("layer") == best), {}) if best is not None else {}
    probe = report.get("probe") or {}
    reasons = [str(r) for r in report.get("reasons", [])]
    active = report.get("status") == "validated"
    source = str(report.get("source", "mock"))
    return ProbeCard(
        model_id=model_id, source=source if source in ("mock", "ollama_embed", "llamacpp") else "mock",
        layers=[int(r["layer"]) for r in report.get("layers", []) if "layer" in r],
        auroc=report.get("auroc"), control_auroc=report.get("shuffled_auroc"),
        baseline_auroc=report.get("cheap_auroc"),
        n_train=int(row.get("n_train", probe.get("n_train", 0)) or 0),
        n_test=int(row.get("n_test", 0) or 0), trained_at=now, active=active,
        reason="validated" if active and not reasons else "; ".join(reasons) or str(report.get("status", "rejected")))


def cli_train_one(extra_args: Optional[list[str]] = None) -> TrainOne:
    """train_one that runs train_cli.main in a worker thread and reads back its report file."""
    async def run(model_id: str) -> ProbeCard:
        from council.core import config as config_mod
        from council.probe import train_cli

        out_path = (config_mod.home() / "bench" / "results" / f"probe_{train_cli._slug(model_id)}.json")
        out_path.unlink(missing_ok=True)  # never read an old report as if it were new
        out, err = io.StringIO(), io.StringIO()
        argv = ["--model", model_id, *(extra_args or [])]
        code = await asyncio.to_thread(train_cli.main, argv, out, err)
        if code != 0:
            raise RuntimeError(err.getvalue().strip().splitlines()[-1] if err.getvalue().strip()
                               else f"train_cli exit code {code}")
        report = json.loads(out_path.read_text(encoding="utf-8"))
        return card_from_report(model_id, report, time.time())
    return run


def default_models() -> list[str]:
    """Ids of the active seat models of the registry."""
    from council.core import config as config_mod
    registry = config_mod.load_registry(config_mod.home() / "config" / "models.json")
    return [m.id for m in registry if m.status == "active" and "seat" in m.roles]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m council.probe.train_all",
                                description="Train the lie-detector probe of many models, one by one.")
    p.add_argument("--models", default=None, help="comma list of model ids (default: active seats)")
    p.add_argument("--state", default=None, help="state file: resume from it, write after each model")
    return p


def main(argv: Optional[list[str]] = None, train_one: Optional[TrainOne] = None,
         release: Optional[Release] = None, out: Any = None) -> int:
    """Exit 0 when every model was tried (even if some failed), 1 on setup error or no model."""
    out = out or sys.stdout
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return 0 if e.code in (0, None) else 1
    try:
        ids = ([m.strip() for m in args.models.split(",") if m.strip()] if args.models
               else default_models())
        if not ids:
            print("error: no models to train", file=sys.stderr)
            return 1
        state = Path(args.state).expanduser() if args.state else None
        cards = asyncio.run(train_models(
            ids, train_one or cli_train_one(), release,
            lambda m, s: print(f"[{m}] {s}", file=sys.stderr, flush=True), state))
        print(summary_text(cards), file=out)
        return 0
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
