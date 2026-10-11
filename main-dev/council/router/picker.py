"""Router picker (spec 9.2, 9.4, 9.5, 9.6). Tier A and Tier B. Pure: no I/O, deterministic for a seed.

pick() builds the council before anyone speaks:
  1. eligible models (9.2) and their q (9.3 Tier A)
  2. every feasible lineup of size K-1 is scored (9.5)
  3. one of the top N is softmax-sampled with tau (9.6 step 2)
  4. the wildcard seat is filled with the looser floor (9.6 step 3)
  5. two alternates, lenses, chair

When nothing is feasible the constraints are loosened in this order, and each step is noted:
  a. max_per_lab 1 -> 2                                  (spec 9.2)
  b. the quality floor is widened in steps of 0.05       (keeps K; the spec is silent here)
  c. K shrinks by one

Tier B is used when a CalibrationIndex is given, it is ready(), and the task has an embedding.
Then q is q_b per model, the score uses the Tier B weights plus the nearest calibration tasks
(vote, cover), and pair distance mixes lineage with error distance. Otherwise Tier A, unchanged.

random_lineup() gives a feasible lineup drawn at random (bench mode random_council).

Notes
- chosen_score and rejected[].score are scores of the K-1 merit lineups, so they compare
  like with like. The wildcard is not part of either.
- A need maps to a modality through NEED_MODALITY. Needs with no entry (code_execution,
  long_context, multilingual) are served by the engine and constrain no model.
"""

from __future__ import annotations

import itertools
import random
from collections import Counter
from typing import Any, Optional

from council.chamber.lenses import assign_lenses
from council.core.config import RouterConfig
from council.core.schemas import (
    LineupRecord,
    LineupScore,
    ModelEntry,
    RejectedLineup,
    SeatAssignment,
    TaskProfile,
)
from council.router.competence import SkillTable, exploration_bonus, passes_floor, q_tier_a
from council.router.distance import pair_distance
from council.router.scoring import ScoringContext, score_lineup, softmax_sample
from council.router.tier_b import CalibrationIndex

TIER = "A"
TIER_B = "B"
RANDOM_TRIES = 200
NEED_MODALITY: dict[str, str] = {"vision": "image"}
FLOOR_STEP = 0.05
N_ALTERNATES = 2
N_REJECTED = 5
_EPS = 1e-9


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------


def _cfg(router_cfg: Any) -> RouterConfig:
    if router_cfg is None:
        return RouterConfig()
    if isinstance(router_cfg, RouterConfig):
        return router_cfg
    if isinstance(router_cfg, dict):
        return RouterConfig(**router_cfg)
    return router_cfg  # duck-typed: anything with the same attributes


def _weights(cfg: Any, tier: str = TIER) -> dict[str, float]:
    w = cfg.weights_tier_a
    if tier == TIER_B:
        w = getattr(cfg, "weights_tier_b", None) or w
    if isinstance(w, dict):
        return dict(w)
    return {k: float(getattr(w, k, 0.0)) for k in ("merit", "vote", "cover", "div", "load", "repeat")}


def covers_needs(m: ModelEntry, needs: list[str]) -> bool:
    return all(NEED_MODALITY[n] in m.modalities for n in needs if n in NEED_MODALITY)


def footprint(m: ModelEntry) -> float:
    """Measured live footprint in GiB. Only called on eligible models."""
    return float(m.measured.ram_gb_live or 0.0)


def eligible_models(profile: TaskProfile, registry: list[ModelEntry]) -> list[ModelEntry]:
    """9.2: active, has the seat role, modalities cover the needs, footprint measured. Sorted by id."""
    out: dict[str, ModelEntry] = {}
    for m in registry:
        if m.status != "active" or "seat" not in m.roles:
            continue
        if m.measured.ram_gb_live is None:
            continue
        if not covers_needs(m, list(profile.needs)):
            continue
        out.setdefault(m.id, m)
    return [out[i] for i in sorted(out)]


def _lab_ok(models: list[ModelEntry], max_per_lab: int) -> bool:
    counts = Counter(m.lab or m.id for m in models)
    return max(counts.values(), default=0) <= max_per_lab


def _fits(models: list[ModelEntry], budget: float) -> bool:
    return sum(footprint(m) for m in models) <= budget + _EPS


def _feasible(models: list[ModelEntry], budget: float, max_per_lab: int) -> bool:
    return _fits(models, budget) and _lab_ok(models, max_per_lab)


def _model_runs(model_id: str, profile: TaskProfile, table: SkillTable) -> float:
    """Runs this model has had in the task's categories, weighted by category weight."""
    weights = {c: w for c, w in profile.categories.items() if w > 0}
    total = sum(weights.values())
    if total <= 0:
        return 0.0
    return sum(w * table.trials(model_id, c) for c, w in weights.items()) / total


def _wild_candidates(
    chosen: list[ModelEntry],
    pool: list[ModelEntry],
    q: dict[str, float],
    best_q: float,
    wild_delta: float,
    budget: float,
    max_per_lab: int,
) -> list[ModelEntry]:
    taken = {m.id for m in chosen}
    out = []
    for m in pool:
        if m.id in taken:
            continue
        if not passes_floor(q[m.id], best_q, True, wildcard_floor_delta=wild_delta):
            continue
        if _feasible(chosen + [m], budget, max_per_lab):
            out.append(m)
    return out


def _levels(cfg: Any) -> list[tuple[int, float, list[str]]]:
    """Constraint ladder: (max_per_lab, extra floor width, notes)."""
    base_lab = max(1, int(cfg.max_per_lab))
    labs = [base_lab] if base_lab >= 2 else [base_lab, 2]
    out: list[tuple[int, float, list[str]]] = []
    steps = int(round(1.0 / FLOOR_STEP))
    for i in range(steps + 1):
        extra = round(i * FLOOR_STEP, 4)
        for lab in labs:
            notes = []
            if lab != base_lab:
                notes.append(f"max_per_lab relaxed {base_lab}->{lab}: no feasible lineup")
            if extra > 0:
                notes.append(f"quality floor widened by {extra:.2f}: no feasible lineup")
            out.append((lab, extra, notes))
    return out


# --------------------------------------------------------------------------------------
# pick
# --------------------------------------------------------------------------------------


def pick_with_notes(
    profile: TaskProfile,
    k: int,
    registry: list[ModelEntry],
    table: SkillTable,
    seat_budget_gib: float,
    router_cfg: Any = None,
    resident: Optional[set[str]] = None,
    recent: Optional[list[list[str]]] = None,
    deadline_s: float = 300,
    seed: int = 0,
    total_runs: int = 0,
    override: Optional[list[str]] = None,
    calibration: Optional[CalibrationIndex] = None,
    embedding: Optional[list[float]] = None,
) -> tuple[LineupRecord, list[str]]:
    """Like pick(), plus the list of notes (k shrunk, lab cap relaxed, floor widened, ...)."""
    cfg = _cfg(router_cfg)
    resident = set(resident or ())
    recent = [list(r) for r in (recent or [])][-max(1, int(cfg.repeat_window)):]
    notes: list[str] = []
    rng = random.Random(seed)
    by_id: dict[str, ModelEntry] = {}
    for m in registry:
        by_id.setdefault(m.id, m)

    q_all = {mid: q_tier_a(mid, profile, table) for mid in by_id}

    tier = TIER
    neighbours: Optional[list[dict]] = None
    err: Optional[dict[tuple[str, str], float]] = None
    if calibration is not None and embedding and calibration.ready():
        tier = TIER_B
        emb = list(embedding)
        n_near = max(1, int(getattr(cfg, "neighbours", 30)))
        q_all = {mid: calibration.q_b(mid, emb, qa, n_near) for mid, qa in q_all.items()}
        neighbours = calibration.neighbours(emb, n_near)
        err = calibration.error_distances(sorted(by_id))

    def dist(a: str, b: str) -> float:
        return pair_distance(by_id[a], by_id[b], tier, err)

    ctx = ScoringContext(
        q=q_all,
        distance=dist,
        weights=_weights(cfg, tier),
        tier=tier,
        neighbours=neighbours,
        resident=resident,
        load_s={mid: float(m.measured.load_s or 0.0) for mid, m in by_id.items()},
        deadline_s=deadline_s,
        recent=recent,
    )

    eligible = eligible_models(profile, registry)

    # ---- override: the given models, in the given order --------------------------------
    if override:
        ids: list[str] = []
        for mid in override:
            if mid in by_id and mid not in ids:
                ids.append(mid)
            elif mid not in by_id:
                notes.append(f"override: unknown model {mid!r} dropped")
        if not ids:
            raise ValueError("override names no model in the registry")
        notes.append("lineup forced by override")
        seated = [by_id[i] for i in ids]
        alternates = _alternates(seated, eligible, q_all, seat_budget_gib, max(2, int(cfg.max_per_lab)))
        record = _record(ids, None, q_all, score_lineup(ids, ctx), [], alternates, seed, tier)
        return record, notes

    if not eligible:
        raise ValueError("no eligible seat models for this task")

    q = {m.id: q_all[m.id] for m in eligible}
    best_q = max(q.values())
    floor_delta = float(cfg.floor_delta)
    wild_gap = max(0.0, float(cfg.wildcard_floor_delta) - floor_delta)

    k_eff = max(1, int(k))
    if len(eligible) < k_eff:
        notes.append(f"k shrunk {k_eff}->{len(eligible)}: only {len(eligible)} eligible models")
        k_eff = len(eligible)

    found = None
    while k_eff >= 1 and found is None:
        n_merit = k_eff - 1 if k_eff > 1 else 1
        for max_lab, extra, level_notes in _levels(cfg):
            delta = floor_delta + extra
            wild_delta = delta + wild_gap
            pool = [m for m in eligible if passes_floor(q[m.id], best_q, False, floor_delta=delta)]
            if len(pool) < n_merit:
                continue
            lineups: list[list[ModelEntry]] = []
            for combo in itertools.combinations(pool, n_merit):
                members = list(combo)
                if not _feasible(members, seat_budget_gib, max_lab):
                    continue
                if k_eff > 1 and not _wild_candidates(
                    members, eligible, q, best_q, wild_delta, seat_budget_gib, max_lab
                ):
                    continue  # the full lineup of K must exist too
                lineups.append(members)
            if lineups:
                found = (lineups, max_lab, wild_delta)
                notes.extend(level_notes)
                break
        if found is None:
            if k_eff == 1:
                break
            notes.append(f"k shrunk {k_eff}->{k_eff - 1}: no feasible lineup")
            k_eff -= 1
    if found is None:
        raise ValueError("no feasible lineup: no eligible model fits the seat budget")

    lineups, max_lab, wild_delta = found
    scored = [([m.id for m in members], score_lineup([m.id for m in members], ctx)) for members in lineups]
    chosen_ids = softmax_sample(
        [(ids, s.total) for ids, s in scored], float(cfg.tau), int(cfg.top_n_sample), rng
    )
    chosen_key = tuple(chosen_ids)
    chosen_score = next(s for ids, s in scored if tuple(ids) == chosen_key)
    rejected = [
        RejectedLineup(models=ids, score=s)
        for ids, s in sorted(
            (t for t in scored if tuple(t[0]) != chosen_key), key=lambda t: t[1].total, reverse=True
        )[:N_REJECTED]
    ]

    merit_ids = sorted(chosen_ids, key=lambda i: (-q[i], i))
    chosen = [by_id[i] for i in merit_ids]

    wildcard_id: Optional[str] = None
    if k_eff > 1:
        cands = _wild_candidates(chosen, eligible, q, best_q, wild_delta, seat_budget_gib, max_lab)

        def wild_value(m: ModelEntry) -> float:
            mean_d = sum(dist(m.id, c) for c in merit_ids) / len(merit_ids)
            return mean_d + exploration_bonus(total_runs, _model_runs(m.id, profile, table))

        wildcard_id = sorted(cands, key=lambda m: (-wild_value(m), -q[m.id], m.id))[0].id

    seat_ids = merit_ids + ([wildcard_id] if wildcard_id else [])
    alternates = _alternates([by_id[i] for i in seat_ids], eligible, q, seat_budget_gib, max_lab)
    return _record(seat_ids, wildcard_id, q, chosen_score, rejected, alternates, seed, tier), notes


def _alternates(
    seated: list[ModelEntry],
    eligible: list[ModelEntry],
    q: dict[str, float],
    budget: float,
    max_per_lab: int,
) -> list[str]:
    """Next best unseated models that could replace a seat and keep the lineup feasible.

    A model that can replace any seat ranks ahead of one that can replace only some.
    """
    taken = {m.id for m in seated}
    ranked = []
    for a in eligible:
        if a.id in taken:
            continue
        ok = [
            _feasible([s for s in seated if s.id != out.id] + [a], budget, max_per_lab) for out in seated
        ]
        if any(ok):
            ranked.append((0 if all(ok) else 1, -q.get(a.id, 0.0), a.id))
    return [mid for _, _, mid in sorted(ranked)[:N_ALTERNATES]]


def _record(
    seat_ids: list[str],
    wildcard_id: Optional[str],
    q: dict[str, float],
    chosen_score: LineupScore,
    rejected: list[RejectedLineup],
    alternates: list[str],
    seed: int,
    tier: str = TIER,
) -> LineupRecord:
    lenses = assign_lenses(seat_ids, q, seed)
    chair_idx = 0
    for i, mid in enumerate(seat_ids):
        if q.get(mid, 0.0) > q.get(seat_ids[chair_idx], 0.0):  # strict: earlier seat wins ties
            chair_idx = i
    seats = [
        SeatAssignment(
            seat_no=i,
            model_id=mid,
            lens=lenses.get(mid),
            is_wildcard=(mid == wildcard_id),
            is_chair=(i == chair_idx),
            q=q.get(mid, 0.0),
        )
        for i, mid in enumerate(seat_ids)
    ]
    return LineupRecord(
        seats=seats,
        alternates=alternates,
        chair_model_id=seat_ids[chair_idx],
        tier=tier,
        chosen_score=chosen_score,
        rejected=rejected,
        seed=seed,
        k=len(seats),
    )


def pick(
    profile: TaskProfile,
    k: int,
    registry: list[ModelEntry],
    table: SkillTable,
    seat_budget_gib: float,
    router_cfg: Any = None,
    resident: Optional[set[str]] = None,
    recent: Optional[list[list[str]]] = None,
    deadline_s: float = 300,
    seed: int = 0,
    total_runs: int = 0,
    override: Optional[list[str]] = None,
    calibration: Optional[CalibrationIndex] = None,
    embedding: Optional[list[float]] = None,
) -> LineupRecord:
    """Choose the lineup for one task. See the module docstring. LineupRecord.k is the K actually seated."""
    record, _ = pick_with_notes(
        profile, k, registry, table, seat_budget_gib, router_cfg,
        resident=resident, recent=recent, deadline_s=deadline_s, seed=seed,
        total_runs=total_runs, override=override,
        calibration=calibration, embedding=embedding,
    )
    return record


def random_lineup(
    profile: TaskProfile,
    k: int,
    registry: list[ModelEntry],
    seat_budget_gib: float,
    seed: int = 0,
) -> LineupRecord:
    """A feasible lineup drawn at random (bench mode random_council). Deterministic for a seed.

    Same hard constraints as pick(): eligible models, seat budget, one model per lab. No quality
    floor, no wildcard, no scoring of rivals. If K seats cannot be filled the lab cap goes to 2,
    then K shrinks. q is Tier A from the registry priors; it only sets lenses and the chair.
    """
    eligible = eligible_models(profile, registry)
    if not eligible:
        raise ValueError("no eligible seat models for this task")
    rng = random.Random(seed)
    by_id = {m.id: m for m in eligible}
    table = SkillTable({m.id: dict(m.priors) for m in eligible})
    q = {m.id: q_tier_a(m.id, profile, table) for m in eligible}

    chosen: Optional[list[ModelEntry]] = None
    k_eff = min(max(1, int(k)), len(eligible))
    while k_eff >= 1 and chosen is None:
        for max_lab in (1, 2):
            for _ in range(RANDOM_TRIES):
                order = list(eligible)
                rng.shuffle(order)
                members: list[ModelEntry] = []
                for m in order:
                    if len(members) == k_eff:
                        break
                    if _feasible(members + [m], seat_budget_gib, max_lab):
                        members.append(m)
                if len(members) == k_eff:
                    chosen = members
                    break
            if chosen is not None:
                break
        else:
            k_eff -= 1
    if chosen is None:
        raise ValueError("no feasible lineup: no eligible model fits the seat budget")

    seat_ids = [m.id for m in chosen]
    ctx = ScoringContext(
        q=q,
        distance=lambda a, b: pair_distance(by_id[a], by_id[b], TIER, None),
        weights=_weights(RouterConfig()),
        tier=TIER,
        load_s={mid: float(m.measured.load_s or 0.0) for mid, m in by_id.items()},
    )
    alternates = _alternates(chosen, eligible, q, seat_budget_gib, 2)
    return _record(seat_ids, None, q, score_lineup(seat_ids, ctx), [], alternates, seed)


__all__ = ["pick", "pick_with_notes", "random_lineup", "eligible_models", "covers_needs", "footprint", "NEED_MODALITY"]
