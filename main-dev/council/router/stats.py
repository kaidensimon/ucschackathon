"""Router learning from outcomes (spec 9.7).

update_from_run folds one finished run into the skill table and the per-model behaviour
counters. Everything is persisted through the store.
"""

from __future__ import annotations

from typing import Any

from council.core import event_types as ET
from council.core.schemas import Decision, Event, LineupRecord, TaskProfile
from council.router.competence import SkillTable

LIVE_WEIGHT = 0.5  # 9.7: the live signal is noisy, so half weight
TRUTH_WEIGHT = 1.0


def _persist_skill(table: SkillTable, store: Any, model_id: str, category: str) -> None:
    a, b = table.stats[(model_id, category)]
    store.upsert_model_stat(model_id, category, a, b)


def _round0_positions(events: list[Event]) -> dict[int, str]:
    pos: dict[int, str] = {}
    for e in events:
        if e.type != ET.OPTIONS_CLUSTERED or e.payload.get("round", 0) != 0:
            continue
        for o in e.payload.get("options") or []:
            if isinstance(o, dict):
                for seat in o.get("holders") or []:
                    pos[int(seat)] = str(o.get("id"))
        break
    return pos


def _final_ballots(events: list[Event]) -> dict[int, dict]:
    """Last ballot per seat: {choice, changed_because}."""
    out: dict[int, dict] = {}
    for e in events:
        if e.type != ET.BALLOT_CAST:
            continue
        seat = e.payload.get("seat_no")
        ballot = e.payload.get("ballot")
        if seat is None or not isinstance(ballot, dict):
            continue
        out[int(seat)] = {
            "choice": ballot.get("choice"),
            "changed_because": list(ballot.get("changed_because") or []),
        }
    return out


def _critiques(events: list[Event]) -> dict[int, dict]:
    """Round-1 parsed critiques per seat: {flaw_ids, changed_because}."""
    out: dict[int, dict] = {}
    for e in events:
        if e.type != ET.TURN_COMPLETED or e.payload.get("purpose") != "seat.r1":
            continue
        parsed = e.payload.get("parsed")
        seat = e.payload.get("seat_no")
        if seat is None or not isinstance(parsed, dict):
            continue
        flaws: set[str] = set()
        for rv in parsed.get("reviews") or []:
            if isinstance(rv, dict):
                for f in rv.get("flaws") or []:
                    if isinstance(f, dict) and f.get("id"):
                        flaws.add(str(f["id"]))
        out[int(seat)] = {
            "flaw_ids": flaws,
            "changed_because": [str(x) for x in (parsed.get("changed_because") or [])],
        }
    return out


def update_from_run(
    events: list[Event],
    lineup: LineupRecord,
    profile: TaskProfile,
    decision: Decision,
    accepted: bool | None,
    table: SkillTable,
    store: Any,
) -> dict:
    seat_model = {s.seat_no: s.model_id for s in lineup.seats}
    final_opt = decision.option_id
    r0 = _round0_positions(events)
    ballots = _final_ballots(events)
    crits = _critiques(events)

    final_pos: dict[int, str] = {}
    for seat in seat_model:
        choice = ballots.get(seat, {}).get("choice") or r0.get(seat)
        if choice is not None:
            final_pos[seat] = str(choice)

    beh: dict[str, Any] = {}

    def get(m: str) -> Any:
        if m not in beh:
            beh[m] = store.behaviour_get(m)
        return beh[m]

    for m in dict.fromkeys(seat_model.values()):
        get(m).runs += 1

    # invalid / timeouts from gateway events
    for e in events:
        if e.type not in (ET.TURN_INVALID, ET.TURN_TIMEOUT):
            continue
        m = e.payload.get("model_id")
        if m is None and e.payload.get("seat_no") is not None:
            m = seat_model.get(int(e.payload["seat_no"]))
        if m is None or m not in seat_model.values():
            continue
        if e.type == ET.TURN_INVALID:
            get(m).invalid += 1
        else:
            get(m).timeouts += 1

    flips = {"to_right": 0, "to_wrong": 0}
    movers_right: dict[int, list[str]] = {}
    skill_updates = 0
    persuaders = 0

    if final_opt is not None:
        for seat, m in seat_model.items():
            fp, p0 = final_pos.get(seat), r0.get(seat)
            if fp == final_opt:
                get(m).agree_with_decision += 1
            if fp is None or p0 is None or fp == p0:
                continue
            if fp == final_opt:
                get(m).flip_to_right += 1
                flips["to_right"] += 1
                cited = list(ballots.get(seat, {}).get("changed_because") or [])
                cited += crits.get(seat, {}).get("changed_because") or []
                movers_right[seat] = cited
            elif p0 == final_opt:
                get(m).flip_to_wrong += 1
                flips["to_wrong"] += 1

        # persuaded: another seat's round-1 flaw was cited by a seat that moved to the right answer
        credited: set[int] = set()
        for mover, cited in movers_right.items():
            ids = set(cited)
            if not ids:
                continue
            for seat, c in crits.items():
                if seat != mover and seat in seat_model and ids & c["flaw_ids"]:
                    credited.add(seat)
        for seat in credited:
            get(seat_model[seat]).persuaded += 1
        persuaders = len(credited)

        # live skill update
        cats = {c: w for c, w in profile.categories.items() if w > 0}
        for seat, m in seat_model.items():
            p0 = r0.get(seat)
            if p0 is None:
                continue
            reward = 1.0 if (p0 == final_opt and accepted is not False) else 0.0
            for cat, w in cats.items():
                table.update(m, cat, reward, weight=LIVE_WEIGHT * w)
                _persist_skill(table, store, m, cat)
                skill_updates += 1

    for stats in beh.values():
        store.behaviour_put(stats)

    return {
        "models": sorted(beh),
        "skill_updates": skill_updates,
        "flip_to_right": flips["to_right"],
        "flip_to_wrong": flips["to_wrong"],
        "persuaders": persuaders,
        "accepted": accepted,
        "final_option": final_opt,
    }


def update_from_truth(
    model_id: str, category: str, correct: bool, table: SkillTable, store: Any
) -> dict:
    table.update(model_id, category, 1.0 if correct else 0.0, weight=TRUTH_WEIGHT)
    _persist_skill(table, store, model_id, category)
    a, b = table.stats[(model_id, category)]
    return {"model_id": model_id, "category": category, "correct": bool(correct),
            "alpha": a, "beta": b, "mean": table.mean(model_id, category)}


def _entries(registry: Any) -> list:
    if isinstance(registry, dict):
        return list(registry.values())
    return list(registry or [])


def quarantine_candidates(store: Any, registry: Any, window: int = 20, strikes: int = 3) -> list[str]:
    """Active models with `strikes` or more failed calls among their last `window` calls."""
    query = getattr(store, "_all", None)
    if query is None:
        return []
    out: list[str] = []
    for m in _entries(registry):
        if getattr(m, "status", "active") != "active":
            continue
        rows = query(
            "SELECT ok FROM turns WHERE model_id = ? ORDER BY ts DESC, rowid DESC LIMIT ?",
            (m.id, int(window)),
        )
        fails = sum(1 for r in rows if not r["ok"])
        if fails >= strikes:
            out.append(m.id)
    return out


def load_table(registry: Any, store: Any, prior_strength: float = 4.0) -> SkillTable:
    priors = {m.id: dict(m.priors) for m in _entries(registry)}
    return SkillTable(priors, prior_strength=prior_strength, stats=store.get_model_stats())
