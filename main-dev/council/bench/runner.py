"""Bench runner (spec 18). Runs the modes of 18.2 over one benchmark file and writes the report.

Order of one run
    1. Calibration pass (18.5): every seat model answers the calibration split, model by model.
       Each answer goes to store.calibration_put and into the router skill table.
    2. The Router picks a lineup for every task of the reported split (18.3: before round 0).
       Tier B reads the calibration split only.
    3. Solo pass (18.3): every solo call any mode needs, grouped by model. One model is loaded
       in its batch profile, answers all its tasks, and is unloaded.
    4. Council modes (18.4): a seat's round-0 draft IS its solo answer for that task. The drafts
       are fed into the Deliberation, and BatchExecutor.run_many drives the debate rounds only.
    5. Grade, write results.jsonl per mode, write the report.

Choices the spec leaves open, as made here
- "solo:*" is one mode per seat-eligible model (active, has the seat role).
- "big_single" is the first active model with the baseline role; with none, the largest seat model.
- "self_consistency:best@K": best = highest solo accuracy on the calibration split, ties to the
  registry order. Sample 0 is the plain solo call, so it is reused.
- "council" uses the chamber mode named by BENCH_COUNCIL_MODE ("standard"). "council_vote_only"
  uses the same routed lineup with round 0 only and a plain plurality vote: no Chair call.
  Ties go to the option whose seats have more summed competence, then to the lower option id.
- A solo answer that cannot be used as a draft is fed as a failed round-0 turn, so the
  Deliberation substitutes an alternate exactly as it does live. The alternate's solo call is run.
- wall_ms is model time (prompt_ms + gen_ms). A council task costs its slowest round-0 seat plus,
  for each later step (r1, r2, chair, ...), the slowest call of that step.
- Router skill is updated once per (task, model): a cell already in the calibration table is
  written again but does not count twice.
- If the Router finds no feasible lineup (for example footprints not measured yet), it is asked
  again with no seat budget and unmeasured footprints read as zero. The bench loads one model at
  a time, so the budget is not what limits it.
- The tribunal runs only when config.tribunal.in_bench is set. It never changes the graded
  answer; outcomes are counted in the report. No correction is written from a bench run.
- Results are written to <out_dir>/<mode>/results.jsonl and all together to <out_dir>/results.jsonl.
- The reported split is kept apart from the calibration split. A run with split = the
  calibration split is refused (ValueError) for every council mode and for
  self_consistency:best, which are tuned on that split; plain solo modes may run on it and the
  report says so ("reported_on_calibration_split"). A task of the reported split whose id is
  also a calibration task is dropped.

Run-size options (BenchRunRequest, all optional)
- calibration_limit: at most N calibration tasks, taken category by category in file order.
  0 skips the calibration pass: the Router then uses Tier A only.
- calibration_models: "lineup" (default) calibrates only the models that could be seated: the
  seats the Router names (Tier A, from task labels and the skill table, no answers) for the
  tasks of this run. The final lineups are picked after that from the whole pool; a model with
  no calibration row is judged on its priors, as in a live run. "all" calibrates every seat
  model, as does any run with self_consistency:best (it needs every model's score).
- reasoning / max_output_tokens / max_reasoning_tokens: settings of every solo call, the same
  for every model and mode. "max" is spec 18.2. With "off" there is no reasoning cap to add.
- resume: a model whose solo calls are all in the call cache is not loaded; results written
  by an earlier run in a sibling folder of out_dir for the same tasks file, mode and settings
  are reused (<mode>/settings.json holds the fingerprint). False: nothing is reused or cached.
- progress: one line per finished model and per ten finished council tasks, on stderr.

Failures
- A mode whose model did not load, or whose every call failed, is "not run": it has no row and
  no results file, and the report names it. It is never reported as 0%.
- The report header (report.md) and report.json extra["settings"] state the settings used.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
import sys
import time
import uuid
import zlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from council.bench import graders, report, task_import
from council.bench import solo as solo_mod
from council.chamber.consensus import ConsensusConfig
from council.chamber.deliberation import Deliberation
from council.chamber.executors import BatchExecutor
from council.chamber.messages import last_answer_line
from council.chamber.open_debate import OpenDebate
from council.api.ui_bridge import seat_names
from council.core import config as config_mod
from council.core import event_types as E
from council.gateway import cache as call_cache
from council.core.schemas import (
    MODE_DEFAULTS,
    BenchResult,
    BenchRunRequest,
    BenchSummaryRow,
    BenchTask,
    CalibrationCell,
    CallResult,
    CallSpec,
    Decision,
    LineupRecord,
    ModeConfig,
    ModelEntry,
    TaskProfile,
)
from council.core.schemas_v15 import SoloScore
from council.router import picker
from council.router import stats as router_stats
from council.router.tier_b import CalibrationIndex

BENCH_SEED = 0
BENCH_COUNCIL_MODE = "standard"
FALLBACK_BUDGET_GIB = 64.0
SOLO_KINDS = ("solo", "big_single", "self_consistency")
COUNCIL_KINDS = ("council_vote_only", "council", "random_council")
ROUTED_KINDS = ("council_vote_only", "council")
BEST = "best"
CALIBRATION_NS = "calibration_embeddings"  # kv namespace read by the live run pipeline (Tier B)
REASONING_LEVELS = ("off", "council", "max")
CALIBRATION_MODELS = ("lineup", "all")
NOT_AN_ANSWER = ("server_error", "cancelled")  # call errors that are not the model being wrong
MODE_META = "settings.json"  # per mode folder: fingerprint + the task ids that may be reused
SIBLING_SCAN_MAX = 2000
COUNCIL_PROGRESS_EVERY = 10
K_MIN, K_MAX = 2, 6  # council sizes the UI offers
WARNING_LINES_MAX = 20  # task-file warnings printed to stderr
RESULTS_DIR = "results"  # <bench dir>/results/<bench_id>_*.json, read by compare_cli and solo_import


@dataclass
class _Opts:
    """Run-size options of one request, read with getattr so an older request still works."""

    calibration_limit: Optional[int] = None
    calibration_models: str = "lineup"
    reasoning: str = "max"
    max_output_tokens: int = 1200
    max_reasoning_tokens: Optional[int] = 4000
    resume: bool = True
    progress: bool = False
    plain: bool = True  # True: the solo call is exactly the one solo.build_solo_call makes
    k: Optional[int] = None  # council size (seats) of the council modes; None = the mode's own k


def _opt_int(value: Any) -> Optional[int]:
    return None if value is None else int(value)


def read_options(req: Any, bench_cfg: Any, k: Optional[int] = None) -> _Opts:
    limit = _opt_int(getattr(req, "calibration_limit", None))
    if limit is not None and limit < 0:
        raise ValueError("calibration_limit must be 0 or more")
    who = str(getattr(req, "calibration_models", None) or "lineup")
    if who not in CALIBRATION_MODELS:
        raise ValueError(f"calibration_models must be one of {CALIBRATION_MODELS}: {who!r}")
    reasoning = str(getattr(req, "reasoning", None) or "max")
    if reasoning not in REASONING_LEVELS:
        raise ValueError(f"reasoning must be one of {REASONING_LEVELS}: {reasoning!r}")
    out_o = _opt_int(getattr(req, "max_output_tokens", None))
    rea_o = _opt_int(getattr(req, "max_reasoning_tokens", None))
    if (out_o is not None and out_o < 1) or (rea_o is not None and rea_o < 0):
        raise ValueError("token caps must be positive")
    resume = getattr(req, "resume", True)
    resume = True if resume is None else bool(resume)
    out_cap = out_o if out_o is not None else int(bench_cfg.solo_max_output_tokens)
    if rea_o is not None:
        rea_cap: Optional[int] = rea_o
    elif reasoning == "off":
        rea_cap = None  # no reasoning: nothing to cap, and the cap must not pad the output cap
    else:
        rea_cap = bench_cfg.solo_max_reasoning_tokens
    plain = reasoning == "max" and out_o is None and rea_o is None and resume
    size = _opt_int(k if k is not None else getattr(req, "k", None))
    if size is not None and not K_MIN <= size <= K_MAX:
        raise ValueError(f"k must be {K_MIN} to {K_MAX}: {size}")
    return _Opts(limit, who, reasoning, out_cap, rea_cap, resume,
                 bool(getattr(req, "progress", False)), plain, size)


def stratified(tasks: list[BenchTask], limit: Optional[int]) -> list[BenchTask]:
    """At most `limit` tasks, taken one category at a time in file order. None = all of them."""
    if limit is None or limit >= len(tasks):
        return list(tasks)
    if limit <= 0:
        return []
    groups: dict[str, list[int]] = {}
    for i, task in enumerate(tasks):
        groups.setdefault(task.category, []).append(i)
    picked: set[int] = set()
    depth = 0
    while len(picked) < limit:
        for cat in sorted(groups):
            if depth < len(groups[cat]) and len(picked) < limit:
                picked.add(groups[cat][depth])
        depth += 1
    return [t for i, t in enumerate(tasks) if i in picked]


def _clock(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _eta(elapsed: float, done: int, total: int) -> str:
    if total <= done:
        return _clock(0)
    if done <= 0:
        return "?"
    return _clock(elapsed / done * (total - done))


def _rate(right: int, graded: int) -> str:
    return "-" if graded <= 0 else f"{right / graded * 100:.1f}%"


def header_markdown(extra: dict) -> str:
    """The settings of a run, and what did not run, as markdown lines (report header, CLI)."""
    st = dict((extra or {}).get("settings") or {})
    lines: list[str] = []
    if st:
        cal = st.get("calibration_tasks", 0)
        models = list(st.get("calibrated_models") or [])
        if st.get("calibration_limit") == 0:
            cal_text = "skipped (calibration_limit 0): the Router uses Tier A only"
        elif not models:
            cal_text = "not run (no mode of this run needed it, or its results were reused)"
        else:
            cal_text = (f"{cal} tasks (limit {st.get('calibration_limit')}) x {len(models)} models "
                        f"({st.get('calibration_models')}): {', '.join(models)}")
        lines += [
            "Settings used:",
            "",
            f"- tasks file: {st.get('tasks_path')} (split {st.get('split')}, {st.get('tasks')} tasks, "
            f"limit {st.get('limit')})",
            f"- modes: {', '.join(st.get('modes') or [])}",
            f"- models: {', '.join(st.get('models') or [])}",
            f"- solo calls: reasoning {st.get('reasoning')}, max_output_tokens "
            f"{st.get('max_output_tokens')}, max_reasoning_tokens {st.get('max_reasoning_tokens')}",
            f"- calibration: {cal_text}",
            f"- router tiers: {st.get('router_tiers') or {}}; council mode {st.get('council_mode')}",
            f"- resume: {'on' if st.get('resume') else 'off'}; reused results: {st.get('reused') or {}}",
            f"- seed {st.get('seed')}; mock {st.get('mock')}",
            "",
        ]
        if st.get("reported_on_calibration_split"):
            lines += ["Reported on the calibration split: solo numbers only, not a test score.", ""]
    not_run = dict((extra or {}).get("not_run") or {})
    if not_run:
        lines += ["NOT RUN (no number for these modes; this is not 0%):", ""]
        lines += [f"- {mode}: {why}" for mode, why in not_run.items()]
        lines.append("")
    failed = dict((extra or {}).get("load_failed") or {})
    if failed:
        lines += ["Models that failed to load:", ""]
        lines += [f"- {mid}: {why}" for mid, why in failed.items()]
        lines.append("")
    degraded = dict((extra or {}).get("degraded") or {})
    if degraded:
        lines += ["Ran with substitutes (a seated model did not load):", ""]
        lines += [f"- {mode}: {', '.join(mids)}" for mode, mids in degraded.items()]
        lines.append("")
    return "\n".join(lines)


async def _maybe(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._@-]+", "_", name).strip("_") or "mode"


def _failed(spec: CallSpec, error: str = "server_error") -> CallResult:
    return CallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id, error=error)  # type: ignore[arg-type]


def _ms(result: CallResult) -> float:
    return float(result.prompt_ms or 0.0) + float(result.gen_ms or 0.0)


async def _call_many(gateway: Any, specs: list[CallSpec]) -> list[CallResult]:
    """One result per spec, in order. Never raises (cancellation aside)."""
    if not specs:
        return []
    try:
        if hasattr(gateway, "call_many"):
            results = list(await _maybe(gateway.call_many(specs)))
        else:
            results = list(await asyncio.gather(*[gateway.call(s) for s in specs]))
    except Exception:
        return [_failed(s) for s in specs]
    by_id = {r.call_id: r for r in results if isinstance(r, CallResult)}
    out: list[CallResult] = []
    for i, spec in enumerate(specs):
        res = by_id.get(spec.call_id)
        if res is None and len(results) == len(specs) and isinstance(results[i], CallResult):
            res = results[i]
        out.append(res or _failed(spec))
    return out


class _Meter:
    """Gateway wrapper that keeps every result by run id, so debate tokens can be counted."""

    def __init__(self, gateway: Any, after: Optional[Callable[[], None]] = None) -> None:
        self.gateway = gateway
        self.after = after
        self.by_run: dict[str, list[tuple[str, CallResult]]] = {}

    def _tick(self) -> None:
        if self.after is not None:
            try:
                self.after()
            except Exception:
                pass

    def _note(self, spec: CallSpec, result: CallResult) -> None:
        self.by_run.setdefault(spec.run_id or "", []).append((spec.purpose or "", result))

    async def call(self, spec: CallSpec, **kwargs: Any) -> CallResult:
        try:
            result = await self.gateway.call(spec, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception:
            result = _failed(spec)
        self._note(spec, result)
        self._tick()
        return result

    async def call_many(self, specs: list[CallSpec]) -> list[CallResult]:
        results = await _call_many(self.gateway, specs)
        for spec, result in zip(specs, results):
            self._note(spec, result)
        self._tick()
        return results


@dataclass
class _Mode:
    name: str  # the row name in the report
    kind: str
    model: Optional[str] = None
    k: int = 1


@dataclass
class _Seat:
    """One council task in one mode."""

    mode: _Mode
    task: BenchTask
    run_id: str
    lineup: LineupRecord
    delib: Any = None
    seat_models: dict[int, str] = field(default_factory=dict)
    r0: list[CallResult] = field(default_factory=list)
    decision: Optional[Decision] = None


def parse_mode(text: str, default_k: int = 5) -> _Mode:
    """One mode string of 18.2. "solo:*" stays as it is; the runner expands it."""
    raw = (text or "").strip()
    if raw in ("big_single", "council_vote_only", "council", "random_council"):
        return _Mode(name=raw, kind=raw)
    head, sep, rest = raw.partition(":")
    rest = rest.strip()
    if head == "solo" and sep and rest:
        return _Mode(name=f"solo:{rest}", kind="solo", model=rest)
    if head == "self_consistency" and sep and rest:
        model, at, k_text = rest.rpartition("@")
        if not at or not k_text.strip().isdigit():
            model, k = rest, int(default_k)
        else:
            k = int(k_text)
        model = model.strip()
        if not model or k < 1:
            raise ValueError(f"bad bench mode: {text!r}")
        return _Mode(name=f"self_consistency:{model}@{k}", kind="self_consistency", model=model, k=k)
    raise ValueError(f"unknown bench mode: {text!r}")


class BenchRunner:
    def __init__(
        self,
        gateway: Any,
        host: Any,
        registry: Any,
        store: Any,
        config: Any,
        emit: Callable[[str, dict], None],
    ) -> None:
        self.load_errors: list[str] = []
        self.gateway = gateway
        self.host = host
        entries = list(registry.values()) if isinstance(registry, dict) else list(registry or [])
        self.registry: list[ModelEntry] = entries
        self.store = store
        self.config = config
        self.emit = emit
        self.mock = bool(getattr(getattr(config, "gateway", None), "mock", False))
        self.seed = BENCH_SEED
        try:
            self.lens_texts = config_mod.load_lenses()
        except Exception:
            self.lens_texts = {}
        # Kept after a run, for callers and tests.
        self.calibration_index: Optional[CalibrationIndex] = None
        self.resolved: dict[str, str] = {}
        self.tribunal_outcomes: dict[str, Any] = {}
        self._reset()

    def _reset(self) -> None:
        self._by_id: dict[str, ModelEntry] = {}
        for m in self.registry:
            self._by_id.setdefault(m.id, m)
        self._memo: dict[tuple[str, str, int], CallResult] = {}
        self._tasks: dict[str, BenchTask] = {}
        self._cal_done: set[tuple[str, str]] = set()
        self._cal_known: set[tuple[str, str]] = set()
        self._cal_embedded: set[str] = set()
        self._table: Any = None
        self._bench_id = ""
        self._done = 0
        self._correct = 0
        self._total = 0
        self._opts = _Opts()
        self._t0 = time.monotonic()
        self.load_failed: dict[str, str] = {}  # model id -> why its load failed, this run
        self.not_run: dict[str, str] = {}  # mode name -> why it has no number, this run
        self.calibration_index = None
        self.resolved = {}
        self.tribunal_outcomes = {}
        self._k_arg: Optional[int] = None
        self._protocol = "structured"  # council protocol of this run: "structured" | "open"

    # ------------------------------------------------------------------ small helpers

    def _send(self, type_: str, **fields: Any) -> None:
        if self.emit is None:
            return
        try:
            self.emit(type_, E.make_payload(type_, bench_id=self._bench_id, **fields))
        except Exception:
            pass

    @property
    def _bcfg(self) -> Any:
        return getattr(self.config, "bench", None) or config_mod.BenchConfig()

    @property
    def _cal_split(self) -> str:
        return str(getattr(self._bcfg, "calibration_split", "calibration") or "calibration")

    def _task_seed(self, task: BenchTask, salt: str = "") -> int:
        return zlib.crc32(f"{self.seed}|{salt}|{task.id}".encode("utf-8")) & 0x7FFFFFFF

    def _pool(self, req: BenchRunRequest) -> list[ModelEntry]:
        wanted = set(req.models or [])
        return [m for m in self._by_id.values() if not wanted or m.id in wanted]

    @staticmethod
    def _seat_models(pool: list[ModelEntry]) -> list[ModelEntry]:
        return [m for m in pool if m.status == "active" and "seat" in m.roles]

    def _baseline(self, pool: list[ModelEntry]) -> Optional[ModelEntry]:
        for group in (pool, list(self._by_id.values())):
            for m in group:
                if m.status == "active" and "baseline" in m.roles:
                    return m
        seats = self._seat_models(pool)
        if not seats:
            return None
        return max(seats, key=lambda m: float(m.params_b or 0.0))

    def _clerk_id(self) -> Optional[str]:
        for m in self._by_id.values():
            if m.status == "active" and "clerk" in m.roles:
                return m.id
        return None

    def _seat_budget(self) -> float:
        try:
            ram = self.host.ram
            resident = sum(float(r.get("footprint_gib") or 0.0) for r in self.host.status())
            return float(ram.seat_budget(float(ram.read_available_gib()) + resident))
        except Exception:
            return FALLBACK_BUDGET_GIB

    def _mode_config(self, kind: str) -> ModeConfig:
        name = BENCH_COUNCIL_MODE
        try:
            mode = self.config.mode(name)
        except Exception:
            mode = MODE_DEFAULTS[name]
        mode = mode.model_copy(deep=True)
        if kind == "council_vote_only":
            mode = mode.model_copy(update={"rounds": ["r0"]})
        if self._opts.k is not None:
            mode = mode.model_copy(update={"k": int(self._opts.k)})
        return mode

    def _consensus_cfg(self) -> ConsensusConfig:
        chamber = getattr(self.config, "chamber", None)
        if chamber is None:
            return ConsensusConfig()
        return ConsensusConfig(
            threshold=float(chamber.consensus_threshold),
            quorum_fraction=float(chamber.quorum_fraction),
            blocking_to_veto=int(chamber.blocking_objections_to_veto),
            early_exit_min_confidence=float(chamber.early_exit_min_confidence),
        )

    async def _host_call(self, name: str, *args: Any) -> bool:
        fn = getattr(self.host, name, None) if self.host is not None else None
        if fn is None:
            return True
        try:
            await _maybe(fn(*args))
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # A model that will not load must be visible: silent zeros look like a real score.
            self.load_errors.append(f"{name} {' '.join(str(a) for a in args)}: {exc}")
            if name == "load" and args:
                self.load_failed.setdefault(str(args[0]), f"{type(exc).__name__}: {exc}"[:300])
            print(f"bench: host.{name}{args} failed: {exc}", file=sys.stderr, flush=True)
            return False

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        fn = getattr(self.gateway, "embed", None)
        if fn is None or not texts:
            return [[] for _ in texts]
        try:
            vecs = list(await _maybe(fn(list(texts))))
        except asyncio.CancelledError:
            raise
        except Exception:
            return [[] for _ in texts]
        if len(vecs) != len(texts):
            return [[] for _ in texts]
        return [list(v or []) for v in vecs]

    @staticmethod
    def _prompt(task: BenchTask) -> str:
        return solo_mod.solo_prompt(task)[0]["content"]

    @staticmethod
    def _grade(task: BenchTask, key: Optional[str]) -> Optional[bool]:
        """No answer is wrong (18.2). A grader this build cannot run gives None."""
        if not key:
            return False
        try:
            return bool(graders.grade(task, key))
        except (NotImplementedError, ValueError):
            return None

    # ------------------------------------------------------------------ modes

    def _parse_modes(self, req: BenchRunRequest, pool: list[ModelEntry]) -> list[_Mode]:
        default_k = int(getattr(self._bcfg, "self_consistency_k", 5) or 5)
        seats = self._seat_models(pool)
        out: dict[str, _Mode] = {}
        for text in req.modes or []:
            mode = parse_mode(text, default_k)
            if mode.kind == "solo" and mode.model == "*":
                if not seats:
                    raise ValueError("solo:* needs at least one seat-eligible model")
                for m in seats:
                    out.setdefault(f"solo:{m.id}", _Mode(name=f"solo:{m.id}", kind="solo", model=m.id))
                continue
            if mode.kind == "solo" and mode.model not in self._by_id:
                raise ValueError(f"unknown model in bench mode: {text!r}")
            if mode.kind == "self_consistency" and mode.model != BEST and mode.model not in self._by_id:
                raise ValueError(f"unknown model in bench mode: {text!r}")
            if mode.kind == "self_consistency" and mode.model == BEST and not seats:
                raise ValueError("self_consistency:best needs at least one seat-eligible model")
            if mode.kind in COUNCIL_KINDS and not seats:
                raise ValueError(f"{mode.kind} needs at least one seat-eligible model")
            if mode.kind == "big_single":
                base = self._baseline(pool)
                if base is None:
                    raise ValueError("big_single needs a baseline model")
                mode.model = base.id
                self.resolved["big_single"] = base.id
            out.setdefault(mode.name, mode)
        if not out:
            raise ValueError("no bench modes given")
        return list(out.values())

    # ------------------------------------------------------------------ solo pass (18.3)

    def _solo_spec(self, task: BenchTask, model_id: str, sample: int) -> CallSpec:
        spec = solo_mod.build_solo_call(
            task, self._by_id[model_id], self._bcfg, seed=self.seed, sample=sample,
            mock_truth=self.mock,
        )
        opts = self._opts
        if opts.plain:
            return spec
        # The same settings for every model and every mode (18.2), whatever they are.
        return spec.model_copy(update={
            "reasoning": opts.reasoning,
            "max_output_tokens": opts.max_output_tokens,
            "max_reasoning_tokens": opts.max_reasoning_tokens,
            "cacheable": bool(opts.resume),
        })

    def _say(self, text: str) -> None:
        if self._opts.progress:
            print(f"bench: {text}", file=sys.stderr, flush=True)

    def _in_cache(self, spec: CallSpec) -> bool:
        """True when the gateway will answer this call from its cache, so no model is needed."""
        cache = getattr(self.gateway, "cache", None)
        if cache is None or not self._opts.resume:
            return False
        try:
            if not (spec.cacheable and spec.seed is not None):
                return False
            key = call_cache.cache_key(spec, self._by_id[spec.model_id].quant)
            return cache.store.cache_get(key) is not None  # a peek: no hit or miss is counted
        except Exception:
            return False

    async def _solo_pass(self, wanted: list[tuple[BenchTask, str, int]], label: str) -> None:
        """Run the solo calls not answered yet: one model at a time, largest group first."""
        groups: dict[str, list[tuple[tuple[str, str, int], CallSpec]]] = {}
        seen: set[tuple[str, str, int]] = set()
        for task, model_id, sample in wanted:
            key = (task.id, model_id, int(sample))
            if key in self._memo or key in seen or model_id not in self._by_id:
                continue
            seen.add(key)
            self._tasks.setdefault(task.id, task)
            groups.setdefault(model_id, []).append((key, self._solo_spec(task, model_id, sample)))
        total_calls = sum(len(v) for v in groups.values())
        done_calls = right = graded = 0
        started = time.monotonic()
        if groups:
            self._say(f"{label}: {total_calls} calls on {len(groups)} models")
        ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))
        for n, (model_id, items) in enumerate(ordered, 1):
            specs = [spec for _, spec in items]
            note = ""
            if all(self._in_cache(s) for s in specs):
                # Resume: every answer is already paid for. Do not load a model to read a cache.
                results = await _call_many(self.gateway, specs)
                note = ", from cache"
            elif model_id in self.load_failed:
                results = [_failed(s) for s in specs]
                note = ", LOAD FAILED"
            elif await self._host_call("load", model_id, "batch"):
                results = await _call_many(self.gateway, specs)
                await self._host_call("unload", model_id)
            else:
                results = [_failed(s) for s in specs]
                note = ", LOAD FAILED"
                await self._host_call("unload", model_id)
            for (key, _), result in zip(items, results):
                self._memo[key] = result
            done_calls += len(items)
            if self._opts.progress:
                for (key, _), result in zip(items, results):
                    task = self._tasks.get(key[0])
                    mark = None if task is None else self._grade(
                        task, solo_mod.extract_answer(result, task.answer_type))
                    if mark is not None:
                        graded += 1
                        right += int(mark)
                bad = sum(1 for r in results if not r.ok)
                if bad and not note:
                    note = f", {bad} calls failed"
                self._say(
                    f"{label}: model {n}/{len(ordered)} done ({model_id}{note}) | "
                    f"calls {done_calls}/{total_calls} | accuracy so far {_rate(right, graded)} | "
                    f"elapsed {_clock(time.monotonic() - self._t0)} | "
                    f"left in this pass ~{_eta(time.monotonic() - started, done_calls, total_calls)}"
                )
            self._send(
                E.BENCH_PROGRESS, mode=label, model_id=model_id, done=self._done,
                total=self._total, correct=self._correct,
            )
        self._record_calibration()
        await self._store_calibration_embeddings()

    def _solo_key(self, task: BenchTask, model_id: str, sample: int = 0) -> Optional[str]:
        result = self._memo.get((task.id, model_id, sample))
        return None if result is None else solo_mod.extract_answer(result, task.answer_type)

    # ------------------------------------------------------------------ calibration (18.5)

    def _record_calibration(self) -> None:
        """Calibration-split solo answers go to the calibration table and the skill table.

        Only tasks whose split is the calibration split ever get here: a test task is never
        written, never used to tune anything.
        """
        cal = self._cal_split
        for (task_id, model_id, sample), result in list(self._memo.items()):
            if sample != 0 or (task_id, model_id) in self._cal_done:
                continue
            task = self._tasks.get(task_id)
            if task is None or task.split != cal:
                continue
            if not result.ok and result.error in NOT_AN_ANSWER:
                # The model never answered (it did not load, the server failed). That says
                # nothing about its skill: it must not be written down as a wrong answer.
                continue
            self._cal_done.add((task_id, model_id))
            key = solo_mod.extract_answer(result, task.answer_type)
            correct = self._grade(task, key)
            if correct is None:
                continue  # no grader for this task: it cannot calibrate anything
            self.store.calibration_put(
                CalibrationCell(task_id=task_id, model_id=model_id, correct=correct, answer_key=key)
            )
            if (task_id, model_id) not in self._cal_known:
                self._cal_known.add((task_id, model_id))
                router_stats.update_from_truth(model_id, task.category, correct, self._table, self.store)

    async def _store_calibration_embeddings(self) -> None:
        """Embed each calibration prompt once and keep it for live Tier B routing.

        Only tasks of the calibration split that have a calibration row are written; a test
        task never is. Nothing is stored when the gateway gives no vector.
        """
        cal = self._cal_split
        todo: list[BenchTask] = []
        for task_id in sorted({t for t, _ in self._cal_done}):
            task = self._tasks.get(task_id)
            if task is None or task.split != cal or task_id in self._cal_embedded:
                continue
            todo.append(task)
        if not todo:
            return
        vecs = await self._embed([self._prompt(t) for t in todo])
        for task, vec in zip(todo, vecs):
            if not vec:
                continue
            self._cal_embedded.add(task.id)
            self.store.kv_put(CALIBRATION_NS, task.id, {
                "embedding": [float(x) for x in vec],
                "truth": graders.normalize(task.answer, task.answer_type),
                "category": task.category,
                "difficulty": task.difficulty,
            })

    def _calibration_accuracy(self, cal_tasks: list[BenchTask], models: list[ModelEntry]) -> dict[str, float]:
        out: dict[str, float] = {}
        for m in models:
            marks = [
                self._grade(t, self._solo_key(t, m.id)) is True
                for t in cal_tasks if (t.id, m.id, 0) in self._memo
            ]
            if marks:
                out[m.id] = sum(marks) / len(marks)
        return out

    async def _build_index(self, cal_tasks: list[BenchTask]) -> CalibrationIndex:
        """Tier B data. Built from the calibration split of this file and nothing else."""
        ids = {t.id for t in cal_tasks}
        matrix = {tid: row for tid, row in self.store.calibration_matrix().items() if tid in ids}
        tasks = [t for t in cal_tasks if t.id in matrix]
        vecs = await self._embed([self._prompt(t) for t in tasks])
        embeddings = {t.id: v for t, v in zip(tasks, vecs) if v}
        truths: dict[str, str] = {}
        for t in tasks:
            right = [c.answer_key for _, c in sorted(matrix[t.id].items()) if c.correct and c.answer_key]
            truths[t.id] = right[0] if right else graders.normalize(t.answer, t.answer_type)
        return CalibrationIndex(matrix, embeddings, truths)

    # ------------------------------------------------------------------ router

    def _profile(self, task: BenchTask, embedding: list[float]) -> TaskProfile:
        return TaskProfile(
            categories={task.category: 1.0}, difficulty=task.difficulty, deliverable="answer",
            embedding=list(embedding or []), rationale="bench task labels",
        )

    @staticmethod
    def _loose(pool: list[ModelEntry]) -> list[ModelEntry]:
        out = []
        for m in pool:
            if m.measured.ram_gb_live is None:
                measured = m.measured.model_copy(update={"ram_gb_live": 0.0})
                m = m.model_copy(update={"measured": measured})
            out.append(m)
        return out

    def _lineup(
        self, kind: str, task: BenchTask, embedding: list[float], pool: list[ModelEntry],
        budget: float, mode: ModeConfig,
    ) -> LineupRecord:
        profile = self._profile(task, embedding)
        k = int(mode.k)

        def build(models: list[ModelEntry], gib: float) -> LineupRecord:
            if kind == "random_council":
                return picker.random_lineup(profile, k, models, gib, seed=self._task_seed(task, "random"))
            return picker.pick(
                profile, k, models, self._table, gib, getattr(self.config, "router", None),
                deadline_s=float(mode.deadline_s), seed=self._task_seed(task, "route"),
                calibration=self.calibration_index, embedding=list(embedding) or None,
            )

        try:
            return build(pool, budget)
        except ValueError:
            return build(self._loose(pool), float("inf"))

    # ------------------------------------------------------------------ round 0 (18.4)

    def _protocol_of(self, req: Any) -> str:
        """The council protocol: the request's "protocol" option, else chamber.protocol."""
        said = str(getattr(req, "protocol", None) or "").strip().lower()
        if said not in ("structured", "open"):
            said = str(getattr(getattr(self.config, "chamber", None), "protocol", "") or "structured")
        return said if said in ("structured", "open") else "structured"

    def _new_deliberation(self, item: _Seat, mode: ModeConfig, clerk: Optional[str]) -> None:
        task = item.task
        item.seat_models = {s.seat_no: s.model_id for s in item.lineup.seats}
        if self._protocol == "open" and item.mode.kind != "council_vote_only":
            # Open protocol: free text by name plus a card per message. "council_vote_only"
            # stays a plain vote over the solo answer keys (the Deliberation below).
            names = seat_names({
                s.seat_no: (self._by_id[s.model_id].display if s.model_id in self._by_id else "")
                or s.model_id for s in item.lineup.seats})
            item.delib = OpenDebate(
                item.run_id, self._prompt(task), self._profile(task, []), item.lineup, mode,
                lens_texts=self.lens_texts, clerk_model_id=clerk,
                answer_type=task.answer_type, normalize=graders.normalize,
                cfg=self._consensus_cfg(), seed=self._task_seed(task, "chamber"),
                seat_names=names, max_extra_rounds=0, write_final=False,
            )
            return
        item.delib = Deliberation(
            item.run_id, self._prompt(task), self._profile(task, []), item.lineup, mode,
            lens_texts=self.lens_texts,
            clerk_model_id=clerk if item.mode.kind != "council_vote_only" else None,
            answer_type=task.answer_type, normalize=graders.normalize,
            cfg=self._consensus_cfg(), seed=self._task_seed(task, "chamber"),
        )
        item.seat_models = {s.seat_no: s.model_id for s in item.lineup.seats}

    async def _feed_round0(self, items: list[_Seat]) -> None:
        """Give every seat its solo answer as its round-0 draft. Runs solo calls that are missing."""
        self._seed_open(items)
        while True:
            pending: list[tuple[_Seat, CallSpec]] = []
            for item in items:
                if item.delib.phase != "r0" or isinstance(item.delib, OpenDebate):
                    continue
                pending.extend((item, spec) for spec in item.delib.pending_calls())
            if not pending:
                return
            await self._solo_pass([(item.task, spec.model_id, 0) for item, spec in pending], "round0")
            for item, spec in pending:
                seat_no = (spec.meta or {}).get("seat_no")
                if isinstance(seat_no, int):
                    item.seat_models[seat_no] = spec.model_id
                solo = self._memo.get((item.task.id, spec.model_id, 0))
                draft = solo_mod.to_draft(solo) if solo is not None else None
                if solo is not None:
                    item.r0.append(solo)
                if draft is None:
                    error = (solo.error if solo is not None else None) or "invalid_output"
                    fed = _failed(spec, error)
                else:
                    if draft.answer_key:
                        key = graders.normalize(draft.answer_key, item.task.answer_type)
                        draft = draft.model_copy(update={"answer_key": key or draft.answer_key})
                    fed = CallResult(
                        call_id=spec.call_id, ok=True, model_id=spec.model_id,
                        content=solo.content, parsed=draft.model_dump(mode="json"), cached=True,
                    )
                item.delib.on_result(fed)

    def _seed_open(self, items: list[_Seat]) -> None:
        """Open protocol: each seat's solo answer text is its round-0 message (no model call).
        A seat with no usable solo answer is left to the debate: its position call is run."""
        for item in items:
            if not isinstance(item.delib, OpenDebate):
                continue
            for seat in item.lineup.seats:
                solo = self._memo.get((item.task.id, seat.model_id, 0))
                if solo is None:
                    continue
                item.r0.append(solo)
                if not solo.ok:
                    continue
                text = str(solo.content or "").strip()
                draft = solo_mod.to_draft(solo)
                if draft is not None and not last_answer_line(text):
                    # A solo answer that came as JSON: say it as text with its ANSWER line.
                    text = str(draft.answer or text).strip()
                    if draft.answer_key and not last_answer_line(text):
                        text = f"{text}\nANSWER: {draft.answer_key}".strip()
                item.delib.seed_position(seat.seat_no, text)

    @staticmethod
    def _text_key(item: _Seat, decision: Optional[Decision]) -> Optional[str]:
        """The answer key of a decision: its answer_key, else the last ANSWER line of its text."""
        if decision is None:
            return None
        if decision.answer_key:
            return decision.answer_key
        if not isinstance(item.delib, OpenDebate):
            return None
        raw = last_answer_line(decision.final_text or "")
        return (graders.normalize(raw, item.task.answer_type) or None) if raw else None

    def _plain_vote(self, item: _Seat) -> Decision:
        """Round 0, plain plurality (council_vote_only). No Chair."""
        delib = item.delib
        options = delib.options()
        drafts = delib.drafts()
        q = {s.seat_no: float(s.q) for s in item.lineup.seats}
        voted = [o for o in options if o.holders]
        if not voted:
            return Decision(outcome="deadlock", rounds_run=1)
        top = sorted(voted, key=lambda o: (-len(o.holders), -sum(q.get(s, 0.0) for s in o.holders), o.id))[0]
        valid = sum(len(o.holders) for o in voted)
        share = len(top.holders) / valid
        holders = sorted(top.holders, key=lambda s: (-q.get(s, 0.0), s))
        text = next((drafts[s].answer for s in holders if s in drafts and drafts[s].answer), top.summary)
        conf = [drafts[s].confidence for s in holders if s in drafts]
        outcome = "consensus" if share >= self._consensus_cfg().threshold - 1e-9 else "majority"
        return Decision(
            outcome=outcome, option_id=top.id, final_text=text, answer_key=top.answer_key,
            agreement=share, tally={o.id: len(o.holders) for o in voted}, rounds_run=1,
            confidence=sum(conf) / len(conf) if conf else 0.0,
        )

    # ------------------------------------------------------------------ tribunal (27, optional)

    async def _run_tribunals(self, items: list[_Seat], meter: _Meter) -> None:
        cfg = getattr(self.config, "tribunal", None)
        if cfg is None or not getattr(cfg, "in_bench", False) or not getattr(cfg, "enabled", True):
            return
        try:
            from council.chamber import outlier as outlier_mod
            from council.chamber.tribunal import Tribunal
        except Exception:
            return
        courts: list[tuple[_Seat, Any]] = []
        for item in items:
            decision = item.decision
            if item.mode.kind == "council_vote_only" or decision is None or decision.option_id is None:
                continue
            if isinstance(item.delib, OpenDebate):
                continue  # the tribunal reads drafts: skipped for the open protocol for now
            try:
                delib = item.delib
                ballots, r0, options = delib.final_ballots(), delib.r0_options(), delib.options()
                seat = outlier_mod.find_outlier(ballots, r0, decision.option_id, len(options))
                if seat is None:
                    continue
                lineup = item.lineup.model_copy(update={"seats": [
                    s.model_copy(update={"model_id": item.seat_models.get(s.seat_no, s.model_id)})
                    for s in item.lineup.seats
                ]})
                examiners = outlier_mod.examiners(
                    lineup.seats, seat, ballots, decision.option_id, int(getattr(cfg, "questions", 3))
                )
                ballot = ballots.get(seat)
                held = ballot.choice if ballot is not None else r0.get(seat)
                option = next((o for o in options if o.id == held), None)
                position = (ballot.final_answer if ballot is not None else "") or (
                    option.summary if option is not None else ""
                )
                truth = None
                if option is not None and option.answer_key:
                    truth = self._grade(item.task, option.answer_key)
                court = Tribunal(
                    item.run_id, self._prompt(item.task), decision, lineup, seat, position, examiners,
                    delib.cruxes(), delib.evidence(), cfg=cfg, ground_truth_supports=truth,
                    seed=self._task_seed(item.task, "tribunal"),
                )
            except Exception:
                continue
            courts.append((item, court))

        stalled = False
        while any(not c.is_done() for _, c in courts):
            owner: dict[str, Any] = {}
            groups: dict[str, list[CallSpec]] = {}
            for _, court in courts:
                if court.is_done():
                    continue
                for spec in court.pending_calls():
                    owner[spec.call_id] = court
                    groups.setdefault(spec.model_id, []).append(spec)
            if not groups:
                if stalled:
                    break
                stalled = True
                for _, court in courts:
                    if not court.is_done():
                        court.on_deadline()
                continue
            stalled = False
            for model_id, specs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
                await self._host_call("load", model_id, "batch")
                for result in await meter.call_many(specs):
                    owner[result.call_id].on_result(result)
                await self._host_call("unload", model_id)
        for item, court in courts:
            if court.is_done():
                self.tribunal_outcomes[item.run_id] = court.outcome()

    # ------------------------------------------------------------------ results

    def _finish(self, result: BenchResult) -> BenchResult:
        self._done += 1
        if result.correct is True:
            self._correct += 1
        self._send(
            E.BENCH_PROGRESS, mode=result.mode, model_id=None, done=self._done, total=self._total,
            correct=self._correct, result=result,
        )
        return result

    def _solo_result(self, mode: _Mode, task: BenchTask) -> BenchResult:
        model_id = mode.model or ""
        n = mode.k if mode.kind == "self_consistency" else 1
        calls = [self._memo.get((task.id, model_id, i)) for i in range(n)]
        calls = [c for c in calls if c is not None]
        keys = [solo_mod.extract_answer(c, task.answer_type) for c in calls]
        agreement: Optional[float] = None
        if mode.kind == "self_consistency":
            key = solo_mod.majority_answer(keys)
            agreement = (keys.count(key) / n) if key else 0.0
        else:
            key = keys[0] if keys else None
        return BenchResult(
            id=task.id, mode=mode.name, answer=key or "", answer_key=key,
            correct=self._grade(task, key),
            tokens_in=sum(c.tokens_in for c in calls),
            tokens_out=sum(c.tokens_out for c in calls),
            tokens_reasoning=sum(c.tokens_reasoning for c in calls),
            wall_ms=sum(_ms(c) for c in calls),
            lineup=[model_id], rounds_run=0, agreement=agreement,
        )

    def _council_result(self, item: _Seat, meter: _Meter) -> BenchResult:
        decision = item.decision or Decision(outcome="deadlock")
        later = meter.by_run.get(item.run_id, [])
        calls = list(item.r0) + [r for _, r in later]
        steps: dict[str, float] = {}
        for purpose, result in later:
            steps[purpose] = max(steps.get(purpose, 0.0), _ms(result))
        wall = max((_ms(r) for r in item.r0), default=0.0) + sum(steps.values())
        key = self._text_key(item, decision)
        if key:
            key = graders.normalize(key, item.task.answer_type) or key
        return BenchResult(
            id=item.task.id, mode=item.mode.name, answer=decision.final_text or key or "",
            answer_key=key, correct=self._grade(item.task, key),
            tokens_in=sum(c.tokens_in for c in calls),
            tokens_out=sum(c.tokens_out for c in calls),
            tokens_reasoning=sum(c.tokens_reasoning for c in calls),
            wall_ms=wall,
            lineup=[item.seat_models[s] for s in sorted(item.seat_models)],
            rounds_run=int(decision.rounds_run), outcome=decision.outcome,
            agreement=float(decision.agreement),
        )

    # ------------------------------------------------------------------ run

    async def run(self, req: BenchRunRequest, out_dir: Path, k: Optional[int] = None) -> list[BenchSummaryRow]:
        """k: council size (2 to 6) of the council modes. Default: req.k when the request has one."""
        self._reset()
        self._bench_id = uuid.uuid4().hex[:12]
        self._k_arg = k
        self._protocol = self._protocol_of(req)
        out_dir = Path(out_dir)
        t0 = time.monotonic()
        try:
            return await self._run(req, out_dir, t0)
        except Exception as exc:
            self._send(
                E.BENCH_COMPLETED, summary=[], results_path=str(out_dir / "results.jsonl"),
                ms=(time.monotonic() - t0) * 1000.0, error=f"{type(exc).__name__}: {exc}"[:400],
            )
            raise

    # ------------------------------------------------------------------ resume: results on disk

    def _fingerprint(self, req: BenchRunRequest, mode: _Mode, base: dict, pool: list[ModelEntry]) -> str:
        """What a result of this mode depends on. Same fingerprint = the result may be reused."""
        material = dict(base)
        material.update({"mode": mode.name, "kind": mode.kind, "model": mode.model, "k": mode.k})
        if mode.kind in COUNCIL_KINDS:
            # A lineup depends on who was calibrated, and that depends on the tasks of the run.
            opts = self._opts
            material.update({
                "limit": req.limit,
                "pool": sorted(m.id for m in pool),
                "council": self._mode_config(mode.kind).model_dump(mode="json"),
                "clerk": self._clerk_id(),
                "calibration_limit": opts.calibration_limit,
                "calibration_models": opts.calibration_models,
                "calibration_split": self._cal_split,
            })
            if self._protocol == "open" and mode.kind != "council_vote_only":
                material["protocol"] = "open"
        text = json.dumps(material, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _reusable(self, out_dir: Path, mode: _Mode, fingerprint: str, wanted: set[str]) -> dict[str, BenchResult]:
        """Results an earlier run wrote for this mode with the same fingerprint, by task id."""
        if not self._opts.resume or not wanted:
            return {}
        slug = _slug(mode.name)
        found: list[tuple[float, Path]] = []
        try:
            folders = [out_dir] + [d for d in list(out_dir.parent.iterdir())[:SIBLING_SCAN_MAX] if d != out_dir]
        except OSError:
            folders = [out_dir]
        for folder in folders:
            meta = folder / slug / MODE_META
            try:
                if meta.is_file():
                    found.append((meta.stat().st_mtime, folder / slug))
            except OSError:
                continue
        out: dict[str, BenchResult] = {}
        for _, folder in sorted(found, key=lambda x: (-x[0], str(x[1]))):  # newest first
            try:
                meta = json.loads((folder / MODE_META).read_text(encoding="utf-8"))
                if meta.get("fingerprint") != fingerprint:
                    continue
                ok_ids = set(meta.get("reusable_ids") or [])
                for line in (folder / "results.jsonl").read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    result = BenchResult.model_validate(json.loads(line))
                    if result.mode == mode.name and result.id in ok_ids and result.id in wanted:
                        out.setdefault(result.id, result)
            except Exception:
                continue  # a broken or half-written folder is not a result
        return out

    def _write_mode(self, out_dir: Path, mode: _Mode, results: list[BenchResult], fingerprint: str,
                    reusable_ids: set[str]) -> None:
        folder = out_dir / _slug(mode.name)
        graders.write_results(folder / "results.jsonl", results)
        meta = {"mode": mode.name, "fingerprint": fingerprint, "reusable_ids": sorted(reusable_ids)}
        (folder / MODE_META).write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------ not run

    def _solo_not_run(self, mode: _Mode, new_tasks: list[BenchTask]) -> Optional[str]:
        """Why a solo mode has no number, or None when it ran."""
        model_id = mode.model or ""
        if not new_tasks:
            return None
        if model_id in self.load_failed:
            return f"model {model_id} failed to load: {self.load_failed[model_id]}"
        n = mode.k if mode.kind == "self_consistency" else 1
        calls = [self._memo.get((t.id, model_id, i)) for t in new_tasks for i in range(n)]
        if any(c is not None and c.ok for c in calls):
            return None
        errors = Counter(str(c.error) for c in calls if c is not None and c.error)
        top = errors.most_common(1)[0][0] if errors else "no result"
        return f"every call to {model_id} failed ({top})"

    def _solo_ok(self, mode: _Mode, task: BenchTask) -> bool:
        n = mode.k if mode.kind == "self_consistency" else 1
        calls = [self._memo.get((task.id, mode.model or "", i)) for i in range(n)]
        return all(c is not None and c.ok for c in calls)

    # ------------------------------------------------------------------ calibration set

    def _candidates(self, tasks: list[BenchTask], pool: list[ModelEntry], budget: float) -> set[str]:
        """Models that could be seated on these tasks: the seats of the Tier A lineups.

        Read from the task labels and the skill table only. No answer of any split is used.
        """
        cfg = self._mode_config("council")
        out: set[str] = set()
        for task in tasks:
            try:
                lineup = self._lineup("council", task, [], pool, budget, cfg)
            except ValueError:
                continue
            out.update(s.model_id for s in lineup.seats)
        return out

    # ------------------------------------------------------------------ task file, compare files

    @staticmethod
    def _load_tasks(path: Any) -> list[BenchTask]:
        """Tasks from a bench file. A file of full BenchTask lines loads as it is (exact fields,
        splits). Anything else (JSON, JSONL, CSV with other column names) goes through the
        tolerant loader, and its warnings are printed to stderr."""
        try:
            strict = graders.load_tasks(path)
            if strict:
                return strict
        except Exception:
            pass
        try:
            tasks, info = task_import.load_tasks(Path(path))
        except OSError:
            raise
        except Exception as exc:
            raise ValueError(f"cannot read tasks file {path}: {type(exc).__name__}: {exc}") from None
        warnings = list(info.get("warnings") or [])
        for line in warnings[:WARNING_LINES_MAX]:
            print(f"bench: tasks: {line}", file=sys.stderr, flush=True)
        if len(warnings) > WARNING_LINES_MAX:
            print(f"bench: tasks: ... {len(warnings) - WARNING_LINES_MAX} more warnings",
                  file=sys.stderr, flush=True)
        if info.get("skipped"):
            print(f"bench: tasks: {info['skipped']} rows skipped", file=sys.stderr, flush=True)
        if not tasks:
            raise ValueError(f"no usable tasks in {path}")
        return tasks

    def _write_compare_files(
        self, out_dir: Path, ran: list[_Mode], results: dict[str, list[BenchResult]],
        tasks: list[BenchTask],
    ) -> dict[str, str]:
        """<bench dir>/results/<bench_id>_{council,categories,solo}.json, in the shapes
        compare_cli.load_council / load_tags and solo_import.load_solo read. The id is the name of
        out_dir (the controller's bench id). Returns kind -> path; a failed write is only reported."""
        folder = Path(out_dir).parent / RESULTS_DIR
        bench_id = Path(out_dir).name or self._bench_id
        names = {m.name for m in ran}
        written: dict[str, str] = {}

        def put(kind: str, data: Any) -> None:
            path = folder / f"{bench_id}_{kind}.json"
            try:
                folder.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                written[kind] = str(path)
            except OSError as exc:
                print(f"bench: cannot write {path}: {exc}", file=sys.stderr, flush=True)

        council = next((n for n in ("council", "council_vote_only") if n in names), None)
        if council is not None:
            put("council", {r.id: r.correct is True for r in results[council]})  # ungraded = wrong
        if tasks:
            put("categories", {t.id: t.category for t in tasks})
        by_id = {t.id: t for t in tasks}
        scores: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for mode in ran:
            if mode.kind not in ("solo", "big_single"):
                continue
            for r in results[mode.name]:
                key = (mode.model or "", r.id)
                task = by_id.get(r.id)
                if key in seen or task is None:
                    continue
                seen.add(key)
                scores.append(SoloScore(
                    model_id=mode.model or "", task_id=r.id, correct=r.correct,
                    answer=r.answer_key or r.answer or "", category=task.category,
                    latency_s=r.wall_ms / 1000.0, tokens_out=r.tokens_out,
                ).model_dump(mode="json"))
        if scores:
            put("solo", scores)
        return written

    # ------------------------------------------------------------------ run

    async def _run(self, req: BenchRunRequest, out_dir: Path, t0: float) -> list[BenchSummaryRow]:
        opts = self._opts = read_options(req, self._bcfg, self._k_arg)
        self._t0 = t0
        all_tasks = self._load_tasks(req.tasks_path)
        cal_tasks = [t for t in all_tasks if t.split == self._cal_split]
        cal_ids = {t.id for t in cal_tasks}
        on_calibration = req.split == self._cal_split
        tasks = [t for t in all_tasks if t.split == req.split]
        if not on_calibration:  # an id that is also a calibration task is never reported
            tasks = [t for t in tasks if t.id not in cal_ids]
        if req.limit is not None:
            tasks = tasks[: max(0, int(req.limit))]
        self._tasks = {t.id: t for t in all_tasks}
        # The calibration tasks this run may use. Always tasks of the calibration split.
        cal_use = stratified(cal_tasks, opts.calibration_limit)

        pool = self._pool(req)
        seats = self._seat_models(pool)
        modes = self._parse_modes(req, pool)
        kinds = {m.kind for m in modes}
        needs_best = any(m.kind == "self_consistency" and m.model == BEST for m in modes)
        if on_calibration:
            # 18.5: the calibration split tunes the Router and picks "best". A mode that uses
            # either cannot be reported on those same tasks: it would be graded on what it
            # was tuned on. Plain solo modes use neither, so they may run.
            tuned = sorted(
                m.name for m in modes
                if m.kind in COUNCIL_KINDS or (m.kind == "self_consistency" and m.model == BEST)
            )
            if tuned:
                raise ValueError(
                    f"split '{req.split}' is the calibration split: {', '.join(tuned)} "
                    "is tuned on it and cannot be reported on it. Use the test split."
                )

        self._total = len(modes) * len(tasks)
        self._send(
            E.BENCH_STARTED, request=req, modes=[m.name for m in modes],
            models=[m.id for m in pool], tasks=len(tasks), total=self._total,
        )
        self._say(
            f"start: {len(tasks)} tasks x {len(modes)} modes | reasoning {opts.reasoning}, "
            f"max_output_tokens {opts.max_output_tokens}, max_reasoning_tokens "
            f"{opts.max_reasoning_tokens} | calibration {len(cal_use)} of {len(cal_tasks)} tasks "
            f"({opts.calibration_models}) | resume {'on' if opts.resume else 'off'}"
        )

        self._table = router_stats.load_table(self.registry, self.store)
        self._cal_known = {
            (tid, mid) for tid, row in self.store.calibration_matrix().items() for mid in row
        }

        # 0. resume: results an earlier run wrote for the same tasks file, mode and settings
        try:
            tasks_sha = hashlib.sha256(Path(req.tasks_path).read_bytes()).hexdigest()
        except OSError:
            tasks_sha = ""
        base = {
            "tasks_path": str(req.tasks_path), "tasks_sha256": tasks_sha, "split": req.split,
            "seed": self.seed, "mock": self.mock, "reasoning": opts.reasoning,
            "max_output_tokens": opts.max_output_tokens,
            "max_reasoning_tokens": opts.max_reasoning_tokens,
        }
        wanted_ids = {t.id for t in tasks}
        prints: dict[str, str] = {}
        reused: dict[str, dict[str, BenchResult]] = {m.name: {} for m in modes}

        def look_up(mode: _Mode) -> None:
            prints[mode.name] = self._fingerprint(req, mode, base, pool)
            reused[mode.name] = self._reusable(out_dir, mode, prints[mode.name], wanted_ids)

        def todo(mode: _Mode) -> list[BenchTask]:
            return [t for t in tasks if t.id not in reused[mode.name]]

        for mode in modes:
            if not (mode.kind == "self_consistency" and mode.model == BEST):
                look_up(mode)  # "best" is looked up once it is known which model it is

        # 1. calibration pass: on the calibration split only, and only who is needed
        routed_ids: set[str] = set()
        for mode in modes:
            if mode.kind in ROUTED_KINDS:
                routed_ids.update(t.id for t in todo(mode))
        routed_tasks = [t for t in tasks if t.id in routed_ids]
        needs_router = bool(routed_tasks)
        budget = self._seat_budget()
        cal_models: list[ModelEntry] = []
        if cal_use and seats and (needs_router or needs_best):
            if needs_best or opts.calibration_models == "all":
                cal_models = list(seats)
            else:
                could_sit = self._candidates(routed_tasks, pool, budget)
                cal_models = [m for m in seats if m.id in could_sit]
            await self._solo_pass([(t, m.id, 0) for m in cal_models for t in cal_use], "calibration")
        if needs_best:
            acc = self._calibration_accuracy(cal_use, seats)
            best = max(seats, key=lambda m: acc.get(m.id, -1.0))  # max keeps the first of a tie
            self.resolved["self_consistency:best"] = best.id
            for m in modes:
                if m.kind == "self_consistency" and m.model == BEST:
                    m.model = best.id
                    look_up(m)

        # 2. lineups for every council task, before round 0
        items: list[_Seat] = []
        tiers: dict[str, int] = {}
        if any(todo(m) for m in modes if m.kind in COUNCIL_KINDS):
            embeddings: dict[str, list[float]] = {}
            if needs_router and cal_use:
                self.calibration_index = await self._build_index(cal_use)
                if self.calibration_index.ready():
                    vecs = await self._embed([self._prompt(t) for t in routed_tasks])
                    embeddings = {t.id: v for t, v in zip(routed_tasks, vecs) if v}
            clerk = self._clerk_id()
            routed: dict[tuple[str, str], LineupRecord] = {}
            for mode in modes:
                if mode.kind not in COUNCIL_KINDS:
                    continue
                cfg = self._mode_config(mode.kind)
                group = "routed" if mode.kind in ROUTED_KINDS else "random"
                for task in todo(mode):
                    lineup = routed.get((group, task.id))
                    if lineup is None:
                        lineup = self._lineup(
                            mode.kind, task, embeddings.get(task.id, []), pool, budget, cfg
                        )
                        routed[(group, task.id)] = lineup
                        if group == "routed":
                            tiers[lineup.tier] = tiers.get(lineup.tier, 0) + 1
                    item = _Seat(
                        mode=mode, task=task, lineup=lineup.model_copy(deep=True),
                        run_id=f"bench.{self._bench_id}.{_slug(mode.name)}.{task.id}",
                    )
                    self._new_deliberation(item, cfg, clerk)
                    items.append(item)

        # 3. solo pass: every solo call a mode needs, model-major
        wanted: list[tuple[BenchTask, str, int]] = []
        for mode in modes:
            if mode.kind in ("solo", "big_single"):
                wanted += [(t, mode.model or "", 0) for t in todo(mode)]
            elif mode.kind == "self_consistency":
                wanted += [(t, mode.model or "", i) for t in todo(mode) for i in range(mode.k)]
        for item in items:
            wanted += [(item.task, s.model_id, 0) for s in item.lineup.seats]
        await self._solo_pass(wanted, "solo")

        results: dict[str, list[BenchResult]] = {m.name: [] for m in modes}
        fresh_ok: dict[str, set[str]] = {m.name: set(reused[m.name]) for m in modes}
        for mode in modes:
            if mode.kind not in SOLO_KINDS:
                continue
            why = self._solo_not_run(mode, todo(mode))
            if why:
                self.not_run[mode.name] = why
                self._say(f"NOT RUN {mode.name}: {why}")
                continue
            for task in tasks:
                old = reused[mode.name].get(task.id)
                if old is None and self._solo_ok(mode, task):
                    fresh_ok[mode.name].add(task.id)
                results[mode.name].append(self._finish(old or self._solo_result(mode, task)))
            # Written now, so a run that dies in the debate keeps its solo modes.
            self._write_mode(out_dir, mode, results[mode.name], prints[mode.name], fresh_ok[mode.name])

        # 4. council modes: round 0 from the solo answers, then only the debate rounds
        full = [i for i in items if i.mode.kind != "council_vote_only"]
        debate = {"started": time.monotonic(), "said": 0}

        def council_progress() -> None:
            """One line per ten finished council tasks, and one when the last is done."""
            if not self._opts.progress:
                return
            done = [i for i in full if i.delib.is_done()]
            said = int(debate["said"])
            last = len(done) == len(full) and said != len(full)
            if len(done) // COUNCIL_PROGRESS_EVERY <= said // COUNCIL_PROGRESS_EVERY and not last:
                return
            marks = [self._grade(i.task, self._decision_key(i, i.delib.decision())) for i in done]
            graded = [m for m in marks if m is not None]
            self._say(
                f"council: {len(done)}/{len(full)} tasks done | accuracy so far "
                f"{_rate(sum(1 for m in graded if m), len(graded))} | "
                f"elapsed {_clock(time.monotonic() - self._t0)} | left in the debate "
                f"~{_eta(time.monotonic() - debate['started'], len(done), len(full))}"
            )
            debate["said"] = len(done)

        meter = _Meter(self.gateway, council_progress)
        if items:
            await self._feed_round0(items)
            debate["started"] = time.monotonic()
            if full:
                self._say(f"council: debate on {len(full)} tasks")
            decisions = await BatchExecutor(meter, self.host).run_many([i.delib for i in full])
            for item, decision in zip(full, decisions):
                item.decision = decision
            if full:
                council_progress()
            for item in items:
                if item.mode.kind == "council_vote_only":
                    delib = item.delib
                    item.decision = delib.decision() if delib.is_done() else self._plain_vote(item)
            await self._run_tribunals(items, meter)
        degraded: dict[str, list[str]] = {}
        for mode in modes:
            if mode.kind not in COUNCIL_KINDS:
                continue
            mine = {i.task.id: i for i in items if i.mode is mode}
            if mine and not any(r.ok for i in mine.values() for r in i.r0):
                why = "every seat call failed"
                down = sorted({s.model_id for i in mine.values() for s in i.lineup.seats} & set(self.load_failed))
                if down:
                    why += f": models failed to load ({', '.join(down)})"
                self.not_run[mode.name] = why
                self._say(f"NOT RUN {mode.name}: {why}")
                continue
            down = sorted({s.model_id for i in mine.values() for s in i.lineup.seats} & set(self.load_failed))
            if down:
                degraded[mode.name] = down
            for task in tasks:
                old = reused[mode.name].get(task.id)
                item = mine.get(task.id)
                if old is None and item is None:
                    continue
                if old is None and any(r.ok for r in item.r0):
                    fresh_ok[mode.name].add(task.id)
                results[mode.name].append(self._finish(old or self._council_result(item, meter)))

        # 5. files and report
        flat: list[BenchResult] = []
        ran = [m for m in modes if m.name not in self.not_run]
        for mode in ran:
            self._write_mode(out_dir, mode, results[mode.name], prints[mode.name], fresh_ok[mode.name])
            flat += results[mode.name]
            marks = [r.correct for r in results[mode.name]]
            self._say(
                f"finished {mode.name}: {len(marks)}/{len(tasks)} tasks "
                f"({len(reused[mode.name])} reused) | accuracy "
                f"{_rate(sum(1 for m in marks if m is True), len(marks))} | "
                f"elapsed {_clock(time.monotonic() - self._t0)}"
            )
        results_path = out_dir / "results.jsonl"
        graders.write_results(results_path, flat)
        rows = report.summarize(flat, tasks)
        index = self.calibration_index
        tribunal: dict[str, int] = {}
        for outcome in self.tribunal_outcomes.values():
            name = str(getattr(outcome, "outcome", "skipped"))
            tribunal[name] = tribunal.get(name, 0) + 1
        settings = {
            "tasks_path": str(req.tasks_path),
            "split": req.split,
            "reported_on_calibration_split": on_calibration,
            "limit": req.limit,
            "tasks": len(tasks),
            "modes": [m.name for m in modes],
            "models": [m.id for m in pool],
            "reasoning": opts.reasoning,
            "max_output_tokens": opts.max_output_tokens,
            "max_reasoning_tokens": opts.max_reasoning_tokens,
            "calibration_limit": opts.calibration_limit,
            "calibration_models": opts.calibration_models,
            "calibration_tasks": len(cal_use) if cal_models else 0,
            "calibrated_models": [m.id for m in cal_models],
            "router_tiers": tiers,
            "council_mode": BENCH_COUNCIL_MODE,
            "k": opts.k,
            "resume": opts.resume,
            "reused": {name: len(old) for name, old in reused.items() if old},
            "seed": self.seed,
            "mock": self.mock,
        }
        extra = {
            "bench_id": self._bench_id,
            "tasks_path": str(req.tasks_path),
            "split": req.split,
            "reported_on_calibration_split": on_calibration,  # solo numbers only; not a test score
            "tasks": len(tasks),
            "modes": [m.name for m in modes],
            "resolved": dict(self.resolved),
            "seed": self.seed,
            "mock": self.mock,
            "settings": settings,
            "not_run": dict(self.not_run),  # these modes have no row: not 0%, no number at all
            "load_failed": dict(self.load_failed),
            "degraded": degraded,
            "agreement_curve": report.agreement_curve(flat),
            "calibration": {
                "split": self._cal_split,
                "tasks": len({t for t, _ in self._cal_done}),
                "cells": len(self._cal_done),
                "tier_b_ready": bool(index is not None and index.ready()),
            },
            "router_tiers": tiers,
            "tribunal": tribunal,
            "results_files": {m.name: f"{_slug(m.name)}/results.jsonl" for m in ran},
        }
        report.write_report(out_dir, rows, extra)
        self._write_header(out_dir, extra)
        self._write_compare_files(out_dir, ran, results, tasks)
        self._send(
            E.BENCH_COMPLETED, summary=rows, results_path=str(results_path),
            ms=(time.monotonic() - t0) * 1000.0, error=None,
        )
        return rows

    @staticmethod
    def _decision_key(item: _Seat, decision: Optional[Decision]) -> Optional[str]:
        key = BenchRunner._text_key(item, decision)
        return (graders.normalize(key, item.task.answer_type) or key) if key else None

    @staticmethod
    def _write_header(out_dir: Path, extra: dict) -> None:
        """Put the settings (and what did not run) under the title of report.md."""
        path = Path(out_dir) / "report.md"
        head = header_markdown(extra)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return
        title, sep, rest = text.partition("\n")
        path.write_text(f"{title}{sep}\n{head}\n{rest.lstrip(chr(10))}", encoding="utf-8")


__all__ = [
    "BenchRunner", "parse_mode", "read_options", "stratified", "header_markdown",
    "BENCH_SEED", "BENCH_COUNCIL_MODE",
]
