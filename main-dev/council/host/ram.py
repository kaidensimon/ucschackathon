"""RamBudget (spec 6.2, 4.2): the only authority on what may be loaded."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

LIVE_PROFILE = "live"


@dataclass
class Resident:
    model_id: str
    profile: str
    footprint_gib: float
    idle: bool
    last_used: float


@dataclass
class AdmitPlan:
    ok: bool
    evict: list[str] = field(default_factory=list)
    reason: str = ""


class RamBudget:
    def __init__(
        self,
        read_available_gib: Callable[[], float],
        headroom_gib: float,
        core: set[str],
        footprints: dict[tuple[str, str], float],
    ) -> None:
        self.read_available_gib = read_available_gib
        self.headroom_gib = headroom_gib
        self.core = set(core)
        self.footprints = dict(footprints)

    def footprint(self, model_id: str, profile: str) -> float:
        try:
            return self.footprints[(model_id, profile)]
        except KeyError:
            raise KeyError(f"footprint not measured: {model_id}/{profile}") from None

    def seat_budget(self, idle_available_gib: float) -> float:
        core_total = sum(self.footprint(m, LIVE_PROFILE) for m in self.core)
        return idle_available_gib - self.headroom_gib - core_total

    def plan_admit(self, model_id: str, profile: str, resident: list[Resident]) -> AdmitPlan:
        need = self.footprint(model_id, profile)
        free = self.read_available_gib() - self.headroom_gib
        if need <= free:
            return AdmitPlan(ok=True, evict=[], reason="")
        candidates = sorted(
            (r for r in resident if r.idle and r.model_id not in self.core and r.model_id != model_id),
            key=lambda r: r.last_used,
        )
        evict: list[str] = []
        for r in candidates:
            evict.append(r.model_id)
            free += r.footprint_gib
            if need <= free:
                return AdmitPlan(ok=True, evict=evict, reason="")
        return AdmitPlan(
            ok=False,
            evict=[],
            reason=f"need {need:.1f} GiB, only {free:.1f} GiB free after evicting all idle non-core",
        )

    def fits(self, lineup: list[str], budget_gib: float) -> bool:
        total = sum(self.footprint(m, LIVE_PROFILE) for m in lineup)
        return total <= budget_gib
