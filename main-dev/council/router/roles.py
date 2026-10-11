"""Role assignment from seated models. Pure.

When memory is tight, planner and workers should be models that are already seated
instead of loading a seventh model.
"""

from __future__ import annotations

from typing import Optional

from council.core.schemas import ModelEntry

ROLE_NAMES = ("planner", "senior_worker", "worker", "clerk")


def _params(m: ModelEntry) -> float:
    return float(m.params_b) if m.params_b is not None else 0.0


def _fastest(ids: list[str], registry: dict[str, ModelEntry], tps: Optional[dict[str, float]]) -> Optional[str]:
    """Fastest by tps; when no candidate has a tps number, smallest params_b. Tie-break by id."""
    if not ids:
        return None
    speeds = {i: tps[i] for i in ids if tps and tps.get(i) is not None}
    if speeds:
        return min(ids, key=lambda i: (-speeds.get(i, float("-inf")), i))
    return min(ids, key=lambda i: (_params(registry[i]), i))


def _pick_planner(ids: list[str], registry: dict[str, ModelEntry]) -> Optional[str]:
    if not ids:
        return None
    tagged = [i for i in ids if "planner" in registry[i].roles]
    pool = tagged
    if not pool:
        pool = [i for i in ids if registry[i].structured != "none"] or ids
    return min(pool, key=lambda i: (-_params(registry[i]), i))


def _pick_senior(ids: list[str], registry: dict[str, ModelEntry]) -> Optional[str]:
    if not ids:
        return None
    return min(ids, key=lambda i: (-registry[i].priors.get("code", 0.0), i))


def _preferred_ok(model_id: Optional[str], registry: dict[str, ModelEntry]) -> bool:
    if not model_id:
        return False
    entry = registry.get(model_id)
    return entry is not None and entry.status == "active"


def assign_roles(
    seat_ids: list[str],
    registry: dict[str, ModelEntry],
    preferred: dict[str, Optional[str]],
    allow_extra: bool,
    tps: Optional[dict[str, float]] = None,
) -> dict[str, str]:
    """Map planner/senior_worker/worker/clerk to model ids.

    Preferred (configured) model wins when allow_extra and it is active. Otherwise
    pick among the seated models. A role stays out of the result if nothing can fill it.
    """
    seats = sorted({i for i in seat_ids if i in registry})
    out: dict[str, str] = {}

    planner = _pick_planner(seats, registry)
    senior = _pick_senior(seats, registry)
    worker_pool = [i for i in seats if i != planner] if len(seats) >= 2 else seats
    worker = _fastest(worker_pool, registry, tps)
    clerk = _fastest(seats, registry, tps)
    chosen = {"planner": planner, "senior_worker": senior, "worker": worker, "clerk": clerk}

    for role in ROLE_NAMES:
        pref = preferred.get(role)
        if allow_extra and _preferred_ok(pref, registry):
            out[role] = pref  # type: ignore[assignment]
        elif chosen[role] is not None:
            out[role] = chosen[role]  # type: ignore[assignment]
    return out


def extra_models(roles: dict[str, str], seat_ids: list[str]) -> list[str]:
    """Role models that are not seated (need loading). Sorted, no repeats."""
    seated = set(seat_ids)
    return sorted({m for m in roles.values() if m not in seated})
