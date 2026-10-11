"""Telemetry sampler (spec 19). Builds TelemetrySnapshot from injected readers."""

from __future__ import annotations

import math
import random
import subprocess
import time
from typing import Callable, Optional

from council.core.schemas import ResidentModel, TelemetrySnapshot

_KIB_PER_GIB = 1024.0 * 1024.0


def _kb(meminfo: dict, key: str) -> int:
    for k in (key, key + ":"):
        if k in meminfo:
            try:
                return int(meminfo[k])
            except (TypeError, ValueError):
                return 0
    return 0


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def default_gpu_reader() -> Optional[dict]:
    """Run nvidia-smi. Return {gpu_util, gpu_temp_c, gpu_power_w} or None on any failure."""
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if proc.returncode != 0:
            return None
        line = proc.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            return None
        return {
            "gpu_util": float(parts[0]),
            "gpu_temp_c": float(parts[1]),
            "gpu_power_w": float(parts[2]),
        }
    except Exception:
        return None


class Sampler:
    def __init__(
        self,
        read_meminfo: Callable[[], dict[str, int]],
        gateway_stats: Callable[[], dict] | None = None,
        host_status: Callable[[], list[dict]] | None = None,
        gpu_reader: Callable[[], dict | None] | None = None,
        reference_price_per_mtok: float = 0.0,
    ) -> None:
        self._read_meminfo = read_meminfo
        self._gateway_stats = gateway_stats
        self._host_status = host_status
        self._gpu_reader = gpu_reader
        self._price = float(reference_price_per_mtok)

    def sample(self) -> TelemetrySnapshot:
        snap = TelemetrySnapshot(ts=time.time())

        try:
            mi = self._read_meminfo() or {}
        except Exception:
            mi = {}
        total = _kb(mi, "MemTotal")
        avail = _kb(mi, "MemAvailable")
        snap.mem_total_gib = total / _KIB_PER_GIB
        snap.mem_available_gib = avail / _KIB_PER_GIB
        snap.mem_used_gib = max(total - avail, 0) / _KIB_PER_GIB
        swap_used = max(_kb(mi, "SwapTotal") - _kb(mi, "SwapFree"), 0)
        snap.swap_used_gib = swap_used / _KIB_PER_GIB

        if self._host_status is not None:
            try:
                for row in self._host_status() or []:
                    mid = row.get("model_id") or row.get("id")
                    if not mid:
                        continue
                    snap.resident.append(
                        ResidentModel(model_id=str(mid), footprint_gib=_num(row.get("footprint_gib")))
                    )
            except Exception:
                pass

        if self._gateway_stats is not None:
            try:
                gs = self._gateway_stats() or {}
            except Exception:
                gs = {}
            tps = {str(k): _num(v) for k, v in (gs.get("tps_by_model") or {}).items()}
            snap.tps_by_model = tps
            snap.tps_total = _num(gs["tps_total"]) if "tps_total" in gs else sum(tps.values())
            snap.in_flight = {str(k): int(v) for k, v in (gs.get("in_flight") or {}).items()}
            snap.queue_depth = int(_num(gs.get("queue_depth")))
            snap.tokens_in = int(_num(gs.get("tokens_in")))
            snap.tokens_out = int(_num(gs.get("tokens_out")))
            snap.tokens_reasoning = int(_num(gs.get("tokens_reasoning")))

        if self._gpu_reader is not None:
            try:
                g = self._gpu_reader()
            except Exception:
                g = None
            if g:
                for src, dst in (
                    ("gpu_util", "gpu_util"),
                    ("gpu_temp_c", "gpu_temp_c"),
                    ("gpu_power_w", "gpu_power_w"),
                ):
                    if g.get(src) is not None:
                        setattr(snap, dst, _num(g[src]))

        n_tokens = snap.tokens_in + snap.tokens_out + snap.tokens_reasoning
        snap.cloud_equiv_usd = n_tokens / 1_000_000.0 * self._price
        return snap


class FakeSampler:
    """Plausible, smoothly moving numbers for mock mode."""

    _MODELS = [
        ("qwen3-32b", 20.0),
        ("llama-3.3-70b", 40.0),
        ("gemma-3-27b", 17.0),
        ("mistral-small-24b", 15.0),
        ("phi-4", 9.0),
        ("deepseek-r1-distill-32b", 20.0),
    ]

    def __init__(self, seed: int = 0) -> None:
        self._rng = random.Random(seed)
        self._phase = self._rng.random() * 6.28
        self._activity = 0.5
        self._t0 = time.time()
        self._tok_in = 0
        self._tok_out = 0
        self._tok_reason = 0
        self._last = self._t0
        self._price = 3.0

    def set_activity(self, level: float) -> None:
        self._activity = min(1.0, max(0.0, float(level)))

    def sample(self) -> TelemetrySnapshot:
        now = time.time()
        dt = max(now - self._last, 0.0)
        self._last = now
        t = now - self._t0
        a = self._activity
        wave = math.sin(t / 7.0 + self._phase)
        wave2 = math.sin(t / 3.1 + self._phase * 2)

        total = 128.0
        used = min(max(90.0 + 2.0 * wave + 1.0 * wave2, 0.0), total)
        tps_total = 150.0 + (420.0 - 150.0) * (0.15 + 0.7 * a + 0.15 * (wave * 0.5 + 0.5))
        tps_total = min(max(tps_total, 150.0), 420.0)

        weights = [1.0 + 0.3 * math.sin(t / 5.0 + i * 1.3 + self._phase) for i in range(len(self._MODELS))]
        wsum = sum(weights)
        tps_by_model = {m: tps_total * w / wsum for (m, _), w in zip(self._MODELS, weights)}
        in_flight = {m: max(0, int(round(a * 4 + wave2 + i % 2))) for i, (m, _) in enumerate(self._MODELS)}

        out_rate = tps_total * dt
        self._tok_out += int(out_rate)
        self._tok_in += int(out_rate * 2.5)
        self._tok_reason += int(out_rate * 0.8)
        n = self._tok_in + self._tok_out + self._tok_reason

        return TelemetrySnapshot(
            ts=now,
            mem_total_gib=total,
            mem_available_gib=total - used,
            mem_used_gib=used,
            swap_used_gib=0.0,
            resident=[ResidentModel(model_id=m, footprint_gib=f) for m, f in self._MODELS],
            tps_by_model=tps_by_model,
            tps_total=tps_total,
            in_flight=in_flight,
            queue_depth=int(round(a * 6 + max(wave, 0) * 2)),
            tokens_in=self._tok_in,
            tokens_out=self._tok_out,
            tokens_reasoning=self._tok_reason,
            gpu_util=min(100.0, max(0.0, 25 + 65 * a + 5 * wave)),
            gpu_temp_c=45 + 30 * a + 2 * wave2,
            gpu_power_w=60 + 180 * a + 8 * wave,
            cpu_util=min(100.0, max(0.0, 10 + 40 * a + 5 * wave2)),
            cloud_equiv_usd=n / 1_000_000.0 * self._price,
        )
