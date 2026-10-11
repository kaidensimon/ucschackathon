"""Onboarding probes P1 to P7 (spec 5.5). The entrance exam for one model.

All calls go through the Gateway, so the probes run in mock mode too. Speeds come from the
server's own timings (CallResult.gen_ms / tps), never from our wall clock, so mock runs are
deterministic.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable

from council.core.schemas import CallSpec, CallResult, Draft, MeasuredStats, ModelEntry

PROBE_RUN = "probe"
SPEED_PROMPT = (
    "Write a long, detailed explanation of how a token bucket rate limiter works. "
    "Cover refill, burst size, and failure cases. Keep writing until you are told to stop."
)
SPEED_TOKENS = 300
STRUCT_PASS = 0.95
STRAY_TOKENS = ("<|", "|>", "</s>", "<eos>", "<end_of_turn>")
CANNED = (
    ("Reply with only the word PONG in capital letters. No other text.", "ping", "PONG"),
    ("Answer with only a number. No words, no punctuation.", "What is 7 plus 5?", "12"),
    ("Always reply in lowercase letters only. No other text.", "Repeat after me: HELLO WORLD", "hello world"),
)
REASON_PROMPT = (
    "A train leaves at 3:15 and travels 140 km at 70 km/h, then stops 25 minutes, then "
    "travels 90 km at 60 km/h. When does it arrive? Think it through, then answer."
)
GAIN = 1.1  # concurrent must beat sequential by this factor to count as a help


def _tps(res: CallResult) -> float:
    if res.gen_ms and res.gen_ms > 0:
        return (res.tokens_out + res.tokens_reasoning) / (res.gen_ms / 1000.0)
    return float(res.tps or 0.0)


class ProbeSuite:
    def __init__(
        self,
        gateway: Any,
        host: Any,
        read_available_gib: Callable[[], float],
        registry: list[ModelEntry],
    ) -> None:
        self.gateway = gateway
        self.host = host
        self.read_available_gib = read_available_gib
        self.registry = {m.id: m for m in registry}
        # extra findings that MeasuredStats has no field for, per model
        self.reports: dict[str, dict] = {}

    # ------------------------------------------------------------ helpers

    def _entry(self, model_id: str) -> ModelEntry:
        try:
            return self.registry[model_id]
        except KeyError:
            raise KeyError(f"unknown model: {model_id}") from None

    def _spec(self, model_id: str, content: str, system: str | None = None, **kw: Any) -> CallSpec:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": content})
        base: dict[str, Any] = dict(
            model_id=model_id, run_id=PROBE_RUN, purpose="profile", messages=msgs,
            cacheable=False, priority="batch",
        )
        base.update(kw)
        return CallSpec(**base)

    def _set_slots(self, model_id: str, n: int) -> None:
        gov = getattr(self.gateway, "governor", None)
        if gov is not None:
            gov.set_slots(model_id, max(1, int(n)))

    def _slots_of(self, model_id: str) -> int:
        gov = getattr(self.gateway, "governor", None)
        slots = getattr(gov, "_slots", None) or {}
        return int(slots.get(model_id, 1))

    def _ensure_footprint(self, model_id: str, profile: str) -> None:
        """A brand-new model has no measured footprint yet: give the RamBudget a rough guess."""
        fps = getattr(getattr(self.host, "ram", None), "footprints", None)
        if fps is None or (model_id, profile) in fps:
            return
        params = self._entry(model_id).params_b
        fps[(model_id, profile)] = round(params * 0.6 + 1.0, 2) if params else 1.0

    async def _load(self, model_id: str, profile: str) -> None:
        self._ensure_footprint(model_id, profile)
        await self.host.ensure_resident([model_id], profile, PROBE_RUN)
        self.host.release(PROBE_RUN)
        prof = getattr(self._entry(model_id).serve, profile)
        self._set_slots(model_id, prof.parallel)

    async def _ensure_live(self, model_id: str) -> None:
        await self._load(model_id, "live")

    # ------------------------------------------------------------ P1

    async def p1_footprint(self, model_id: str, profile: str) -> dict:
        """RAM before and after a cold load in `profile`, and the load time."""
        self._entry(model_id)
        if any(s["model_id"] == model_id for s in self.host.status()):
            await self.host._unload(model_id, PROBE_RUN, evicted=False)
        self._ensure_footprint(model_id, profile)
        before = float(self.read_available_gib())
        t0 = time.perf_counter()
        await self.host.ensure_resident([model_id], profile, PROBE_RUN)
        load_s = time.perf_counter() - t0
        after = float(self.read_available_gib())
        reported = None
        sizes = getattr(getattr(self.host, "driver", None), "footprints", None)
        if sizes is not None:
            try:
                reported = (await sizes()).get(model_id)
            except Exception:  # noqa: BLE001
                reported = None
        self.host.release(PROBE_RUN)
        prof = getattr(self._entry(model_id).serve, profile)
        self._set_slots(model_id, prof.parallel)
        return {
            "model_id": model_id,
            "profile": profile,
            "available_before_gib": before,
            "available_after_gib": after,
            # The server's own figure when it has one: on unified memory the weights often
            # sit in the page cache already, so the drop in available memory understates them.
            "footprint_gib": reported if reported else max(0.0, before - after),
            "load_s": load_s,
        }

    # ------------------------------------------------------------ P2

    async def p2_speed(self, model_id: str, streams: tuple[int, ...] = (1, 8, 32)) -> dict:
        """Aggregate tokens/s at each stream count. Keys are the stream counts."""
        self._entry(model_id)
        old_slots = self._slots_of(model_id)
        out: dict[int, float] = {}
        try:
            self._set_slots(model_id, max(streams))
            for n in streams:
                specs = [
                    self._spec(model_id, SPEED_PROMPT, max_output_tokens=SPEED_TOKENS, seed=i)
                    for i in range(n)
                ]
                t0 = time.perf_counter()
                results = await self.gateway.call_many(specs)
                wall = max(time.perf_counter() - t0, 1e-6)
                good = [r for r in results if r.ok]
                # Aggregate = tokens produced per second of wall clock. Summing each request's
                # own rate overstates it whenever the server queues requests instead of batching.
                out[n] = sum(int(r.tokens_out or 0) for r in good) / wall if good else 0.0
        finally:
            self._set_slots(model_id, old_slots)
        return out

    # ------------------------------------------------------------ P3

    async def p3_structured(self, model_id: str, n: int = 20) -> float:
        """Fraction of n calls that return an object valid against the Draft schema."""
        self._entry(model_id)
        schema = Draft.model_json_schema()
        specs = [
            self._spec(
                model_id,
                f"Question {i}: which rate limiter fits a bursty API, and why? Answer as the schema says.",
                json_schema=schema, max_output_tokens=1024, seed=i,
            )
            for i in range(n)
        ]
        results = await self.gateway.call_many(specs)
        valid = 0
        for r in results:
            if not r.ok or not isinstance(r.parsed, dict):
                continue
            try:
                Draft.model_validate(r.parsed)
            except Exception:  # noqa: BLE001
                continue
            valid += 1
        return valid / n if n else 0.0

    # ------------------------------------------------------------ P4

    async def p4_reasoning(self, model_id: str) -> dict:
        """Reasoning tokens at off, council, max. `differs` is True when they are not all equal
        and rise from off to max."""
        self._entry(model_id)
        counts: dict[str, int] = {}
        for level in ("off", "council", "max"):
            res = await self.gateway.call(
                self._spec(model_id, REASON_PROMPT, reasoning=level, max_output_tokens=2048, seed=1)
            )
            counts[level] = int(res.tokens_reasoning) if res.ok else 0
        counts["differs"] = counts["off"] <= counts["council"] <= counts["max"] and counts["off"] < counts["max"]
        return counts

    # ------------------------------------------------------------ P5

    async def p5_context(self, model_id: str) -> bool:
        """One call filled to 90% of serve.live.ctx. Pass when it succeeds without cutoff and the
        server saw most of the prompt."""
        ctx = self._entry(model_id).serve.live.ctx
        target = int(ctx * 0.9)
        room = max(0, target - 64)  # leave space for the question and the answer
        filler = ("The quick brown fox jumps over the lazy dog. " * (room // 10 + 1))[: room * 4]
        res = await self.gateway.call(
            self._spec(
                model_id, filler + "\n\nIn one short sentence, what animal jumps in the text above?",
                max_output_tokens=32, timeout_s=600.0,
            )
        )
        if not res.ok or res.finish_reason in ("length", "error"):
            return False
        return res.tokens_in >= int(target * 0.8)

    # ------------------------------------------------------------ P6

    async def p6_template(self, model_id: str) -> bool:
        """Three canned prompts with exact expected output; no stray special tokens."""
        self._entry(model_id)
        for system, user, expected in CANNED:
            res = await self.gateway.call(
                self._spec(model_id, user, system=system, max_output_tokens=32, temperature=0.0)
            )
            if not res.ok:
                return False
            text = res.content.strip().strip(".").strip()
            if text != expected:
                return False
            if any(tok in res.content for tok in STRAY_TOKENS):
                return False
        return True

    # ------------------------------------------------------------ P7

    async def p7_cross_model(self, model_ids: list[str]) -> dict:
        """Different models generating together vs one after another.

        Totals are tokens per second from server timings: together = all tokens over the slowest
        call, sequential = all tokens over the summed time of calls run one at a time. Tested at 2 and at 5 models
        (or all of them, if fewer). Recommends the largest count where together wins by 10%."""
        ids = list(dict.fromkeys(model_ids))
        for m in ids:
            self._entry(m)
            await self._ensure_live(m)
        gov = getattr(self.gateway, "governor", None)
        old_max = getattr(gov, "_max_models", None)
        points: dict[int, dict] = {}
        recommended = 1
        try:
            if gov is not None and old_max is not None:
                gov._max_models = max(len(ids), 1)
            for k in sorted({min(2, len(ids)), min(5, len(ids))}):
                if k < 1:
                    continue
                group = ids[:k]
                specs = [
                    self._spec(m, SPEED_PROMPT, max_output_tokens=SPEED_TOKENS, seed=j)
                    for j, m in enumerate(group)
                ]
                together = [r for r in await self.gateway.call_many(specs) if r.ok]
                one_by_one = []
                for sp in specs:
                    r = await self.gateway.call(sp.model_copy(update={"call_id": sp.call_id + "-seq"}))
                    if r.ok:
                        one_by_one.append(r)
                t_times = [r.gen_ms / 1000.0 for r in together if r.gen_ms > 0]
                s_times = [r.gen_ms / 1000.0 for r in one_by_one if r.gen_ms > 0]
                if not t_times or not s_times:
                    points[k] = {"simultaneous_tps": 0.0, "sequential_tps": 0.0}
                    continue
                simul = sum(r.tokens_out + r.tokens_reasoning for r in together) / max(t_times)
                seq = sum(r.tokens_out + r.tokens_reasoning for r in one_by_one) / sum(s_times)
                points[k] = {"simultaneous_tps": simul, "sequential_tps": seq}
                if k > 1 and simul >= GAIN * seq:
                    recommended = k
        finally:
            if gov is not None and old_max is not None:
                gov._max_models = old_max
        top = points[max(points)] if points else {"simultaneous_tps": 0.0, "sequential_tps": 0.0}
        return {
            "simultaneous_tps": top["simultaneous_tps"],
            "sequential_tps": top["sequential_tps"],
            "points": points,
            "recommended_max_concurrent_models": recommended,
        }

    # ------------------------------------------------------------ P8 and context cost

    async def p8_speculative(self, model_id: str, draft_values: tuple[int, ...] = (0, 4, 8)) -> dict:
        """Tokens/s for the same 300-token prompt at each draft_num_predict value. Never raises.

        The gateway reads draft_num_predict from the model entry's ollama_options (CallSpec.meta is not
        read), so that is set on the gateway's entry per value and restored. `honoured` says whether
        the hook exists; if not, `note` says so."""
        out: dict[str, Any] = {"model_id": model_id, "tps": {}, "best": None, "honoured": False, "note": ""}
        gw_entry = None
        old_opts: dict = {}
        try:
            self._entry(model_id)
            gw_entry = (getattr(self.gateway, "registry", None) or {}).get(model_id)
            out["honoured"] = gw_entry is not None and hasattr(self.gateway, "_ollama_options")
            old_opts = dict(getattr(gw_entry, "ollama_options", None) or {})
            if not out["honoured"]:
                out["note"] = "gateway has no per-model ollama_options hook; numbers show noise only"
            await self._ensure_live(model_id)
            for v in draft_values:
                if out["honoured"]:  # the gateway reads the entry's ollama_options per call
                    gw_entry.ollama_options = {**old_opts, "draft_num_predict": int(v)}
                spec = self._spec(
                    model_id, SPEED_PROMPT, max_output_tokens=SPEED_TOKENS, seed=1,
                    meta={"ollama_options": {"draft_num_predict": int(v)}},
                )
                res = await self.gateway.call(spec)
                out["tps"][v] = _tps(res) if res.ok else 0.0
            if out["tps"] and max(out["tps"].values()) > 0:
                out["best"] = max(out["tps"], key=lambda k: out["tps"][k])
        except Exception as e:  # noqa: BLE001
            out["error"] = f"{type(e).__name__}: {e}"
        finally:
            if gw_entry is not None and out["honoured"]:
                try:
                    gw_entry.ollama_options = old_opts
                except Exception:  # noqa: BLE001
                    pass
        return out

    async def context_cost(self, model_id: str, ctx_values: tuple[int, ...] = (8192, 16384, 32768)) -> dict:
        """Available memory after loading the model at each context size, and GiB per 1k tokens
        of context (slope between the smallest and largest size). Never raises."""
        out: dict[str, Any] = {"model_id": model_id, "points": {}, "gib_per_1k_ctx": None}
        prof = None
        old_ctx = None
        try:
            prof = self._entry(model_id).serve.live
            old_ctx = prof.ctx
            for c in ctx_values:
                prof.ctx = int(c)
                if any(x["model_id"] == model_id for x in self.host.status()):
                    await self.host._unload(model_id, PROBE_RUN, evicted=False)
                before = float(self.read_available_gib())
                self._ensure_footprint(model_id, "live")
                await self.host.ensure_resident([model_id], "live", PROBE_RUN)
                after = float(self.read_available_gib())
                self.host.release(PROBE_RUN)
                out["points"][c] = {"available_after_gib": after, "footprint_gib": max(0.0, before - after)}
            keys = sorted(out["points"])
            if len(keys) >= 2:
                lo, hi = keys[0], keys[-1]
                d = out["points"][hi]["footprint_gib"] - out["points"][lo]["footprint_gib"]
                out["gib_per_1k_ctx"] = round(d / ((hi - lo) / 1000.0), 6)
        except Exception as e:  # noqa: BLE001
            out["error"] = f"{type(e).__name__}: {e}"
        finally:
            if prof is not None and old_ctx is not None:
                try:
                    prof.ctx = old_ctx
                except Exception:  # noqa: BLE001
                    pass
        return out

    # ------------------------------------------------------------ whole exam

    async def run_model(self, model_id: str) -> MeasuredStats:
        """P1 to P6 for one model. Extra findings go to self.reports[model_id]."""
        self._entry(model_id)
        live = await self.p1_footprint(model_id, "live")
        batch = await self.p1_footprint(model_id, "batch")
        await self._ensure_live(model_id)
        speed = await self.p2_speed(model_id)
        rate = await self.p3_structured(model_id)
        reasoning = await self.p4_reasoning(model_id)
        ctx_ok = await self.p5_context(model_id)
        tmpl_ok = await self.p6_template(model_id)

        def gib(d: dict) -> float | None:
            return round(d["footprint_gib"], 3) if d["footprint_gib"] > 0 else None

        self.reports[model_id] = {
            "reasoning": reasoning,
            "context_ok": ctx_ok,
            "template_ok": tmpl_ok,
            "structured_recommended": "grammar" if rate >= STRUCT_PASS else "prompt_only",
        }
        return MeasuredStats(
            ram_gb_live=gib(live),
            ram_gb_batch=gib(batch),
            load_s=round(live["load_s"], 3),
            tps_1=round(speed.get(1, 0.0), 2),
            tps_8=round(speed.get(8, 0.0), 2),
            tps_32=round(speed.get(32, 0.0), 2),
            structured_valid_rate=round(rate, 4),
            probe_date=date.today().isoformat(),
        )


def write_measured(path: Path, model_id: str, measured: MeasuredStats) -> None:
    """Update one model's `measured` block in models.json in place. Null values keep the old number."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["models"] if isinstance(data, dict) and "models" in data else data
    for row in rows:
        if row.get("id") == model_id:
            block = row.setdefault("measured", {})
            for k, v in measured.model_dump().items():
                if v is not None:
                    block[k] = v
                else:
                    block.setdefault(k, None)
            break
    else:
        raise KeyError(f"model not in {path.name}: {model_id}")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


__all__ = ["ProbeSuite", "write_measured"]
