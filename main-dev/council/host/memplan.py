"""Memory planner: decide which models, roles and context sizes fit in the box. Pure, no I/O.

Measured on the GX10: 121.6 GiB total, about 16.5 GiB real memory per ~12 GiB model at a
16384-token context. Six seats take 103-107 GiB, so a separate seventh model (the planner)
does not fit. plan_memory() finds what fits and says what it changed.
"""

from __future__ import annotations

from council.core.schemas_v15 import MemoryPlan

ROLE_ORDER = ("planner", "senior_worker", "worker", "clerk")
BIG_ROLES = ("planner", "senior_worker")  # these go to the largest seated model
MISSING_GIB = 14.0
FLOOR_SHARE = 0.60


def _cost(real: float, ctx: int, ctx_default: int, per_8k: float) -> float:
    """GiB a model takes at a given context. Never below 60% of its full size."""
    raw = real - per_8k * (ctx_default - ctx) / 8192.0
    return max(raw, FLOOR_SHARE * real)


def plan_memory(
    seats: list[str],
    roles: dict[str, str | None],
    gib: dict[str, float],
    total_gib: float,
    reserve_gib: float = 10.0,
    overhead: float = 1.35,
    ctx_default: int = 16384,
    ctx_steps: tuple[int, ...] = (16384, 8192, 4096),
    ctx_gib_per_8k: float = 1.2,
    reported: bool = False,
) -> MemoryPlan:
    """Pick what is loaded and at what context.

    gib is real resident GiB per model at ctx_default. If reported=True the numbers are
    Ollama-reported, so overhead is multiplied in first. Seats are never dropped.
    """
    budget = total_gib - reserve_gib
    seat_list = list(dict.fromkeys(seats))
    seat_set = set(seat_list)
    notes: list[str] = []
    shared: list[str] = []
    dropped: list[str] = []

    # role -> model id (None entries kept out)
    cur_roles: dict[str, str] = {}
    for name in ROLE_ORDER + tuple(k for k in roles if k not in ROLE_ORDER):
        mid = roles.get(name)
        if mid:
            cur_roles[name] = mid

    loaded: list[str] = list(seat_list)
    for mid in cur_roles.values():
        if mid not in loaded:
            loaded.append(mid)

    real: dict[str, float] = {}
    for mid in loaded:
        base = float(gib.get(mid, MISSING_GIB))
        real[mid] = base * overhead if reported else base
        if mid not in gib:
            notes.append(f"No size known for {mid}, so it is counted as {MISSING_GIB:g} GiB.")
    if reported and loaded:
        notes.append(f"Sizes were reported by Ollama, so each is multiplied by {overhead:g} to get real memory.")

    ladder = [ctx_default] + sorted({s for s in ctx_steps if s < ctx_default}, reverse=True)
    level: dict[str, int] = {mid: 0 for mid in loaded}  # index into ladder

    def cost_of(mid: str) -> float:
        return _cost(real[mid], ladder[level[mid]], ctx_default, ctx_gib_per_8k)

    def used() -> float:
        return sum(cost_of(m) for m in loaded)

    def over() -> bool:
        return used() > budget + 1e-9

    # Step 1: hand roles of non-seated models to seated models.
    if over() and seat_list:
        for name in [r for r in cur_roles]:
            if not over():
                break
            holder = cur_roles[name]
            if holder in seat_set:
                continue
            if name in BIG_ROLES:
                target = max(seat_list, key=lambda m: (real[m], -seat_list.index(m)))
            else:
                target = min(seat_list, key=lambda m: (real[m], seat_list.index(m)))
            cur_roles[name] = target
            shared.append(name)
            if holder not in cur_roles.values():
                loaded.remove(holder)
                del level[holder]
                notes.append(
                    f"The {name} role moved from {holder} to seated model {target}, so {holder} is not loaded."
                )
            else:
                notes.append(f"The {name} role moved from {holder} to seated model {target}.")

    # Step 2: step contexts down, largest model first, one step at a time.
    while over():
        steppable = [m for m in loaded if level[m] < len(ladder) - 1]
        if not steppable:
            break
        pick = max(steppable, key=lambda m: (cost_of(m), -loaded.index(m)))
        level[pick] += 1
        notes.append(f"Context for {pick} lowered to {ladder[level[pick]]} tokens.")

    # Step 3: drop non-seat models, largest first. Seats are never dropped.
    while over():
        extras = [m for m in loaded if m not in seat_set]
        if not extras:
            break
        pick = max(extras, key=lambda m: (cost_of(m), -loaded.index(m)))
        loaded.remove(pick)
        del level[pick]
        dropped.append(pick)
        lost = [r for r, m in cur_roles.items() if m == pick]
        for r in lost:
            del cur_roles[r]
        suffix = f" Role(s) without a model now: {', '.join(lost)}." if lost else ""
        notes.append(f"Dropped {pick} because it did not fit.{suffix}")

    total_used = used()
    fits = total_used <= budget + 1e-9
    if not fits:
        notes.append(
            f"Does not fit: {total_used - budget:.1f} GiB short even with only the seats at the smallest context."
        )

    return MemoryPlan(
        fits=fits,
        budget_gib=round(budget, 2),
        total_gib=round(total_gib, 2),
        per_model={m: round(cost_of(m), 2) for m in loaded},
        num_ctx={m: ladder[level[m]] for m in loaded},
        roles=dict(cur_roles),
        shared_roles=shared,
        dropped=dropped,
        notes=notes,
    )
