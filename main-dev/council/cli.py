"""Command line for the council (spec 17, 16.3).

    python -m council.cli demo [--speed N]
    python -m council.cli run "task text" [--mode standard] [--deliverable answer] [--effort auto]

Builds a RunController in mock mode, starts one run, subscribes to its bus and prints one
line per event. Streamed token events (.delta) are skipped unless --stream.
Exit 0 after run.completed, 1 after run.failed or run.cancelled.

More commands: build, bench, probe, train-probe, models pull-list, chronicle export.
1.5 commands: summary, lies, cards, memory, compare, steer.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TextIO

from council.api.controller import RunController
from council.bench import report as bench_report
from council.bench import runner as bench_runner
from council.core.schemas import BenchRunRequest, BenchSummaryRow
from council.host.probes import ProbeSuite
from council.core import event_types as ET
from council.core.schemas import RunRequest

DEMO_TASK = "Demo: plan a small Python CLI tool."
PREVIEW_CHARS = 90
BENCH_POLL_S = 0.2
DEFAULT_BENCH_MODES = ("solo:*", "council_vote_only", "council")  # when --modes is not given
FAST_LIMIT = 12
FAST_CALIBRATION_LIMIT = 6
EFFORT_CHOICES = ("auto", "light", "normal", "heavy", "fixed")
EFFORT_HELP = ("deliberation effort in standard mode: auto fits rounds, deadline and reasoning "
               "to the task; light, normal, heavy force a level; fixed uses the mode as written")
SUPPLY_CHAIN_LINE = ("# Supply-chain check: look up each model source (publisher, tag, recent "
                     "advisories) before you pull. Do not pull blind.")


PROTOCOL_CHOICES = ("structured", "open")
PROTOCOL_HELP = "council protocol (default: chamber.protocol of the config)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m council.cli", description="Council command line.")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="replay the scripted demo run")
    demo.add_argument("--speed", type=float, default=1.0, help="time divisor for the demo script")
    demo.add_argument("--stream", action="store_true", help="also print streamed .delta events")

    run = sub.add_parser("run", help="run the council on a task in mock mode")
    run.add_argument("task", help="the task text")
    run.add_argument("--mode", default="standard", choices=["quick", "standard", "deep"])
    run.add_argument("--deliverable", default=None, choices=["answer", "plan", "build"])
    run.add_argument("--effort", default="auto", choices=list(EFFORT_CHOICES), help=EFFORT_HELP)
    run.add_argument("--k", type=int, default=None, choices=[2, 3, 4, 5, 6], help="council size (seats)")
    run.add_argument("--protocol", default=None, choices=list(PROTOCOL_CHOICES), help=PROTOCOL_HELP)
    run.add_argument("--speed", type=float, default=1.0, help="time divisor for mock delays")
    run.add_argument("--stream", action="store_true", help="also print streamed .delta events")

    build = sub.add_parser("build", help="build a deliverable in a workspace (real pipeline)")
    build.add_argument("task", help="the task text")
    build.add_argument("--workspace", required=True, help="folder the build writes into")
    build.add_argument("--mode", default="standard", choices=["quick", "standard", "deep"])
    build.add_argument("--auto-delegate", action="store_true", help="skip the plan pause")
    build.add_argument("--effort", default="auto", choices=list(EFFORT_CHOICES), help=EFFORT_HELP)
    build.add_argument("--k", type=int, default=None, choices=[2, 3, 4, 5, 6], help="council size (seats)")
    build.add_argument("--protocol", default=None, choices=list(PROTOCOL_CHOICES), help=PROTOCOL_HELP)
    build.add_argument("--speed", type=float, default=1.0, help="time divisor for mock delays")
    build.add_argument("--stream", action="store_true", help="also print streamed .delta events")

    bench = sub.add_parser("bench", help="run the benchmark and print the markdown report")
    bench.add_argument("--tasks", default="", help="tasks file (default: sample tasks)")
    bench.add_argument("--modes", default="", help="comma list of bench modes")
    bench.add_argument("--split", default="test", choices=["calibration", "test"])
    bench.add_argument("--limit", type=int, default=None, help="at most N reported tasks")
    bench.add_argument("--protocol", default=None, choices=list(PROTOCOL_CHOICES), help=PROTOCOL_HELP)
    bench.add_argument("--speed", type=float, default=1.0)
    bench.add_argument("--calibration-limit", type=int, default=None, metavar="N",
                       help="at most N calibration tasks, spread over the categories")
    bench.add_argument("--no-calibration", action="store_true",
                       help="skip the calibration pass; the Router uses Tier A")
    bench.add_argument("--calibration-models", default="lineup", choices=["lineup", "all"],
                       help="who answers the calibration split (default: models that could be seated)")
    bench.add_argument("--reasoning", default=None, choices=["off", "council", "max"],
                       help="reasoning of the solo calls (default max, spec 18.2)")
    bench.add_argument("--max-output-tokens", type=int, default=None)
    bench.add_argument("--max-reasoning-tokens", type=int, default=None)
    bench.add_argument("--fast", action="store_true",
                       help=f"--reasoning off, --calibration-limit {FAST_CALIBRATION_LIMIT}, "
                            f"--limit {FAST_LIMIT} (each only where not given)")
    bench.add_argument("--no-resume", action="store_true",
                       help="reuse nothing: no cached call, no result of an earlier run")

    probe =sub.add_parser("probe", help="onboarding probes: P1-P6 for a model, P7 for the box")
    probe.add_argument("--model", default=None, help="model id (probes P1 to P6)")
    probe.add_argument("--box", action="store_true", help="cross-model probe (P7)")
    probe.add_argument("--speed", type=float, default=1.0)

    tp = sub.add_parser("train-probe", help="train the truth probe of one model")
    tp.add_argument("--model", required=True, help="model id")
    tp.add_argument("--speed", type=float, default=1.0)

    models = sub.add_parser("models", help="list the models Ollama has here (no subcommand), or helpers")
    msub = models.add_subparsers(dest="models_command", required=False)
    pl = msub.add_parser("pull-list", help="print one ollama pull line per model")
    pl.add_argument("--speed", type=float, default=1.0)

    chron = sub.add_parser("chronicle", help="chronicle helpers")
    csub = chron.add_subparsers(dest="chronicle_command", required=True)
    ce = csub.add_parser("export", help="print the chronicle as markdown")
    ce.add_argument("--workspace", default=None, help="project (workspace) to export")
    ce.add_argument("--speed", type=float, default=1.0)

    summary = sub.add_parser("summary", help="plain-text summary of one stored run")
    summary.add_argument("--run", default=None, help="run id (default: the last run)")
    lies = sub.add_parser("lies", help="the lie report of one stored run")
    lies.add_argument("--run", default=None, help="run id (default: the last run)")
    sub.add_parser("cards", help="one model card per registry model")
    sub.add_parser("memory", help="memory plan for the 6 largest active models plus role models")

    compare = sub.add_parser("compare", help="compare the council with solo models")
    compare.add_argument("--solo", required=True, help="solo report file")
    compare.add_argument("--council", required=True, help="council results (bench out dir or file)")
    compare.add_argument("--md", default=None, help="write the markdown table here")

    steer = sub.add_parser("steer", help="train one steering vector for a project and model")
    steer.add_argument("--project", required=True, help="project folder")
    steer.add_argument("--model", required=True, help="model id")
    steer.add_argument("--rule", required=True, help="the rule the vector should push towards")
    steer.add_argument("--opposite", default=None, help="what the rule is the opposite of")
    return parser


def _footprint_key(m: Any) -> float:
    live = m.measured.ram_gb_live
    if live is not None:
        return float(live)
    return float(m.params_b) * 0.6 + 1.0 if m.params_b else 1e9


def pull_lines(registry: list) -> list[str]:
    """One `ollama pull <tag>` per model with a tag, smallest footprint first, then the reminder."""
    tagged = [m for m in registry if getattr(m, "ollama_tag", None)]
    tagged.sort(key=lambda m: (_footprint_key(m), m.id))
    return [f"ollama pull {m.ollama_tag}" for m in tagged] + [SUPPLY_CHAIN_LINE]


def bench_request(args: Any) -> BenchRunRequest:
    """The bench request for parsed arguments. --fast fills only what was not given."""
    modes = [x.strip() for x in str(args.modes or "").split(",") if x.strip()]
    fast = bool(getattr(args, "fast", False))
    limit = args.limit
    if limit is None and fast:
        limit = FAST_LIMIT
    cal_limit = getattr(args, "calibration_limit", None)
    if getattr(args, "no_calibration", False):
        cal_limit = 0
    elif cal_limit is None and fast:
        cal_limit = FAST_CALIBRATION_LIMIT
    reasoning = getattr(args, "reasoning", None) or ("off" if fast else "max")
    req = BenchRunRequest(
        tasks_path=args.tasks or "", modes=modes or list(DEFAULT_BENCH_MODES), split=args.split,
        limit=limit, calibration_limit=cal_limit,
        calibration_models=getattr(args, "calibration_models", None) or "lineup",
        reasoning=reasoning, max_output_tokens=getattr(args, "max_output_tokens", None),
        max_reasoning_tokens=getattr(args, "max_reasoning_tokens", None),
        resume=not getattr(args, "no_resume", False),
        progress=True,  # the runner prints its progress lines to stderr
    )
    protocol = getattr(args, "protocol", None)
    if protocol:
        # BenchRunRequest has no "protocol" field (and drops unknown ones): the runner reads
        # the option with getattr, like "k".
        object.__setattr__(req, "protocol", str(protocol))
    return req


def _bench_extra(st: dict) -> dict:
    """extra of report.json: the settings used, what did not run, which models did not load."""
    try:
        path = Path(str(st.get("out_dir") or "")) / "report.json"
        return dict(json.loads(path.read_text(encoding="utf-8")).get("extra") or {})
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


async def _bench(ctrl: RunController, args: Any, out: TextIO) -> int:
    """Exit 0: every mode has a number. 1: the run failed. 2: a model did not load or a mode
    did not run; those modes are named and get no number."""
    bench_id = await ctrl.start_bench(bench_request(args))
    while True:
        st = ctrl.bench_status(bench_id)
        if st["state"] not in ("queued", "running"):
            break
        await asyncio.sleep(BENCH_POLL_S)
    if st["state"] != "done":
        print(f"bench {st['state']}: {st.get('error') or ''}".rstrip(), file=out, flush=True)
        return 1
    rows = [BenchSummaryRow.model_validate(r) for r in st["summary"]]
    extra = _bench_extra(st)
    not_run = dict(extra.get("not_run") or {})
    load_failed = dict(extra.get("load_failed") or {})
    for model_id, why in load_failed.items():
        print(f"bench: model {model_id} failed to load: {why}", file=sys.stderr, flush=True)
    for mode, why in not_run.items():
        print(f"bench: {mode} NOT RUN: {why}", file=sys.stderr, flush=True)
    head = bench_runner.header_markdown(extra)
    if head:
        print(head, file=out, flush=True)
    if rows:
        print(bench_report.to_markdown(rows), file=out, end="", flush=True)
    elif not_run or load_failed:
        # Never a table of zeros: nothing was measured.
        print("No results: no mode ran. This is not a score.", file=out, flush=True)
    else:
        print(bench_report.to_markdown(rows), file=out, end="", flush=True)
    if st.get("out_dir"):
        print(f"\nreport: {Path(str(st['out_dir'])) / 'report.md'}", file=out, flush=True)
    return 2 if (not_run or load_failed) else 0


async def _probe(ctrl: RunController, args: Any, out: TextIO) -> int:
    if not args.model and not args.box:
        print("probe needs --model ID or --box", file=out, flush=True)
        return 2
    suite = ProbeSuite(ctrl.gateway, ctrl.host, ctrl.host.ram.read_available_gib, ctrl.registry)
    try:
        if args.box:
            ids = [m.id for m in ctrl.registry if "embed" not in m.id][:5]
            res: Any = await suite.p7_cross_model(ids)
        else:
            res = await suite.run_model(args.model)
    except KeyError as exc:
        print(f"error: {exc.args[0] if exc.args else exc}", file=out, flush=True)
        return 1
    data = res.model_dump(mode="json") if hasattr(res, "model_dump") else res
    print(json.dumps(data, indent=2, default=str), file=out, flush=True)
    return 0


async def _other(ctrl: RunController, args: Any, out: TextIO) -> int:
    cmd = args.command
    if cmd == "bench":
        return await _bench(ctrl, args, out)
    if cmd == "probe":
        return await _probe(ctrl, args, out)
    if cmd == "train-probe":
        try:
            probe = await ctrl.train_probe(args.model)
        except (KeyError, ValueError) as exc:
            print(f"error: {exc.args[0] if exc.args else exc}", file=out, flush=True)
            return 1
        print(probe.model_dump_json(indent=2), file=out, flush=True)
        return 0
    if cmd == "models":
        for line in pull_lines(ctrl.registry):
            print(line, file=out, flush=True)
        return 0
    if cmd == "chronicle":
        print(ctrl.export_chronicle(args.workspace), file=out, flush=True)
        return 0
    return 2


def _cmd_models_found(out: TextIO) -> int:
    """`models`: what Ollama has downloaded on this machine and which of it the council can seat.
    Needs no database and no controller."""
    from council.host import discover
    found = discover.installed_tags()
    if not found:
        print(f"No Ollama models found (looked in {discover.default_models_dir()} and asked "
              "'ollama list').", file=out)
        print("Download some with: bash tools/box/pull_models.sh", file=out)
    entries, notes = discover.build_registry(found, None, {})  # {}: served by plain llama.cpp
    if entries:
        print(discover.table_text(entries, {t["tag"]: t.get("size_gb") for t in found}), file=out)
        print("", file=out)
    for note in notes:
        print(note, file=out)
    out.flush()
    return 0


NEW_COMMANDS = ("summary", "lies", "cards", "memory", "steer")
MEMORY_SEATS = 6
MOCK_TOTAL_GIB = 121.7


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat()


def _event_dicts(events: list) -> list[dict]:
    """Stored events as the dicts run_summary wants: ts as an ISO string."""
    return [{"seq": e.seq, "type": e.type, "run_id": e.run_id, "ts": _iso(e.ts),
             "payload": e.payload} for e in events]


def _pick_run(ctrl: RunController, run_id: Optional[str], out: TextIO) -> Optional[str]:
    """The asked run, else the newest one. Prints why and returns None when there is none."""
    if run_id:
        if ctrl.store.get_run(run_id) is None:
            print(f"error: no such run: {run_id}", file=out, flush=True)
            return None
        return run_id
    runs = ctrl.store.list_runs()
    if not runs:
        print("error: no runs stored yet", file=out, flush=True)
        return None
    return str(runs[0].get("run_id") or runs[0].get("id"))


def _cmd_summary(ctrl: RunController, args: Any, out: TextIO) -> int:
    from council.api import run_summary
    run_id = _pick_run(ctrl, args.run, out)
    if run_id is None:
        return 1
    summary = run_summary.summarize(_event_dicts(ctrl.store.events_for_run(run_id)))
    print(run_summary.summary_text(summary), file=out, flush=True)
    return 0


def _stored_lie_report(ctrl: RunController, run_id: str) -> Any:
    """The LieReport of a run: the store key "lie_reports", else the lie.report event."""
    from council.core.schemas_v15 import LieReport
    raw = None
    try:
        raw = ctrl.store.kv_get("lie_reports", run_id)
    except Exception:
        raw = None
    if raw is None:
        for ev in reversed(ctrl.store.events_for_run(run_id)):
            if ev.type == ET.LIE_REPORT and isinstance(ev.payload.get("report"), dict):
                raw = ev.payload["report"]
                break
    if not raw:
        return None
    try:
        return LieReport.model_validate(raw)
    except Exception:
        return None


def _cmd_lies(ctrl: RunController, args: Any, out: TextIO) -> int:
    from council.probe import lie_report
    run_id = _pick_run(ctrl, args.run, out)
    if run_id is None:
        return 1
    report = _stored_lie_report(ctrl, run_id)
    if report is None:
        print(f"no lie report stored for run {run_id}", file=out, flush=True)
        return 0
    print(lie_report.report_text(report), file=out, flush=True)
    return 0


def _checks_by_id(ctrl: RunController) -> dict:
    """Measured rows from the on-box check file (when present), keyed by registry id."""
    from council.core import config as config_mod
    from council.host import model_checks
    named = str(ctrl.config.memory.measured_file or "")
    paths = [Path(named)] if named else [model_checks.default_path(Path(ctrl.data_home)),
                                         model_checks.default_path(config_mod.home())]
    for path in paths:
        checks = model_checks.load_checks(path)
        if checks:
            return model_checks.by_model_id(checks, ctrl.registry)
    return {}


def _cmd_cards(ctrl: RunController, args: Any, out: TextIO) -> int:
    from council.telemetry import model_cards
    cards = model_cards.build_cards(ctrl.registry, measured=_checks_by_id(ctrl))
    print(model_cards.cards_text(cards), file=out, flush=True)
    return 0


def _total_gib() -> float:
    from council.host import meminfo
    try:
        total = float(meminfo.read_meminfo().get("MemTotal", 0)) / (1024.0 * 1024.0)
    except Exception:
        total = 0.0
    return total if total > 0 else MOCK_TOTAL_GIB


def _cmd_memory(ctrl: RunController, args: Any, out: TextIO) -> int:
    from council.host import memplan
    from council.router import roles as roles_mod
    active = [m for m in ctrl.registry if m.status == "active"]
    active.sort(key=lambda m: (-(m.params_b or 0.0), m.id))
    seats = [m.id for m in active[:MEMORY_SEATS]]
    by_id = {m.id: m for m in ctrl.registry}
    role_map = roles_mod.assign_roles(seats, by_id, {}, False)
    measured = _checks_by_id(ctrl)
    gib: dict[str, float] = {}
    for m in active:
        row = measured.get(m.id)
        value = (row.ram_gib if row is not None and row.ram_gib else None) or m.measured.ram_gb_live
        if value:
            gib[m.id] = float(value)
    mem = ctrl.config.memory
    plan = memplan.plan_memory(seats, dict(role_map), gib, _total_gib(),
                               reserve_gib=float(mem.reserve_gib), overhead=float(mem.overhead))
    print(f"seats: {', '.join(seats) or '-'}", file=out)
    print("roles: " + (", ".join(f"{k}={v}" for k, v in plan.roles.items()) or "-"), file=out)
    print(f"fits: {'yes' if plan.fits else 'NO'}  budget {plan.budget_gib:g} of {plan.total_gib:g} GiB",
          file=out)
    for mid, used in plan.per_model.items():
        print(f"  {mid}: {used:g} GiB, ctx {plan.num_ctx.get(mid, '-')}", file=out)
    if plan.dropped:
        print(f"dropped: {', '.join(plan.dropped)}", file=out)
    for note in plan.notes:
        print(f"note: {note}", file=out)
    out.flush()
    return 0


async def _cmd_steer(ctrl: RunController, args: Any, out: TextIO) -> int:
    """Train one vector. 0 = trained, 1 = error, 2 = nothing trained (mock mode, service missing)."""
    if ctrl.config.gateway.mock:
        print("steer: mock mode, no model server: nothing trained", file=out, flush=True)
        return 2
    try:
        importlib.import_module("council.steer.service")
        contrast = importlib.import_module("council.steer.contrast")
    except ImportError as exc:
        print(f"steer: council.steer.service is not available: {exc}", file=out, flush=True)
        return 2
    # The controller does not build a SteerService yet (it needs a llama.cpp activation
    # source). Use ctrl.steer when something put one there.
    service = getattr(ctrl, "steer", None)
    if service is None or not hasattr(service, "train"):
        print("steer: the controller has no steer service (no llama.cpp source wired): "
              "nothing trained", file=out, flush=True)
        return 2
    pairs = [contrast.rule_pair(args.rule, args.opposite)]
    card = await service.train(str(Path(args.project)), args.model, pairs)  # never raises
    print(card.model_dump_json(indent=2), file=out, flush=True)
    return 0 if card.active else 1


async def _new_command(ctrl: RunController, args: Any, out: TextIO) -> int:
    cmd = args.command
    if cmd == "summary":
        return _cmd_summary(ctrl, args, out)
    if cmd == "lies":
        return _cmd_lies(ctrl, args, out)
    if cmd == "cards":
        return _cmd_cards(ctrl, args, out)
    if cmd == "memory":
        return _cmd_memory(ctrl, args, out)
    return await _cmd_steer(ctrl, args, out)


def _effort_options(args: Any) -> dict:
    """options["effort"] for the run. auto = not set: the pipeline plans the effort itself."""
    effort = getattr(args, "effort", None)
    out: dict = {"effort": effort} if effort and effort != "auto" else {}
    if getattr(args, "k", None):
        out["k"] = int(args.k)
    if getattr(args, "protocol", None):
        out["protocol"] = str(args.protocol)
    return out


def _preview(payload: Any) -> str:
    if not payload:
        return ""
    try:
        text = json.dumps(payload, ensure_ascii=True, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(payload)
    return text if len(text) <= PREVIEW_CHARS else text[: PREVIEW_CHARS - 3] + "..."


def _line(ev: Any) -> str:
    return f"{ev.seq:>5}  {ev.type:<26} {_preview(ev.payload)}".rstrip()


async def _consume(ctrl: RunController, run_id: str, out: TextIO, stream: bool) -> int:
    """Print events until the run is terminal. Returns the process exit code."""
    code: Optional[int] = None
    async for ev in ctrl.bus.subscribe(run_id):
        if ev.type in ET.EPHEMERAL_EVENTS and not stream:
            continue
        print(_line(ev), file=out, flush=True)
        if ev.type == ET.RUN_COMPLETED:
            code = 0
        elif ev.type in (ET.RUN_FAILED, ET.RUN_CANCELLED):
            code = 1
    return 1 if code is None else code


async def main(argv: Optional[list[str]] = None, out: Optional[TextIO] = None,
               controller: Optional[RunController] = None) -> int:
    """Parse argv, run once, print events. Returns the exit code. `controller` is for tests."""
    args = build_parser().parse_args(argv)
    out = out if out is not None else sys.stdout
    if args.command == "compare":  # needs no controller
        from council.bench import compare_cli
        cargs = ["--solo", args.solo, "--council", args.council]
        if args.md:
            cargs += ["--md", args.md]
        return compare_cli.main(cargs, out=out)
    if args.command == "models" and not getattr(args, "models_command", None):  # needs no controller
        return _cmd_models_found(out)
    speed = float(getattr(args, "speed", 1.0))
    ctrl = controller if controller is not None else RunController.build_from_config(speed=speed)
    if args.command in NEW_COMMANDS:
        try:
            return await _new_command(ctrl, args, out)
        finally:
            await ctrl.shutdown()
    if args.command in ("bench", "probe", "train-probe", "models", "chronicle"):
        try:
            return await _other(ctrl, args, out)
        finally:
            await ctrl.shutdown()
    if args.command == "demo":
        req = RunRequest(task=DEMO_TASK, mode="standard",
                         options={"demo": True, "auto_delegate": True})
    elif args.command == "build":
        req = RunRequest(task=args.task, mode=args.mode, deliverable="build",
                         workspace=args.workspace,
                         options={"auto_delegate": bool(args.auto_delegate), **_effort_options(args)})
    else:
        req = RunRequest(task=args.task, mode=args.mode, deliverable=args.deliverable or "answer",
                         options=_effort_options(args))

    try:
        run_id = await ctrl.start(req)
        print(f"run {run_id} ({args.command})", file=out, flush=True)
        return await _consume(ctrl, run_id, out, bool(args.stream))
    finally:
        await ctrl.shutdown()


def cli_main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    return asyncio.run(main(sys.argv[1:]))


if __name__ == "__main__":
    sys.exit(cli_main())
