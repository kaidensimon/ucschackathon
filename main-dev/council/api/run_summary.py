"""Run summary (pure). Fold a run's stored events into one flat dict, and print it compact.

summarize(events) -> dict        every key always present; bad events are skipped, never raise
summary_text(summary) -> str     about 25 lines for a terminal

Events: [{"seq", "ts" (ISO string), "type", "payload" (dict)}] in order. `run_id` may sit on the
envelope. No I/O, no clock, no randomness.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

_FAIL_TYPES = ("model.failed", "run.failed", "turn.invalid", "turn.timeout", "task.failed")
_TASK_END = {
    "task.passed": "passed",
    "task.failed": "failed",
    "task.blocked": "blocked",
    "task.skipped": "skipped",
}
_SHORT = 120
_FINAL_TEXT = 600


def _d(x: Any) -> dict:
    return x if isinstance(x, dict) else {}


def _l(x: Any) -> list:
    return x if isinstance(x, list) else []


def _num(x: Any, default: float = 0.0) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return default
    return float(x)


def _int(x: Any) -> int:
    return int(_num(x))


def _s(x: Any) -> str:
    if x is None:
        return ""
    v = getattr(x, "value", x)
    return str(v)


def _parse_ts(ts: Any) -> Optional[datetime]:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _seconds_between(a: Any, b: Any) -> Optional[float]:
    da, db = _parse_ts(a), _parse_ts(b)
    if da is None or db is None:
        return None
    try:
        return (db - da).total_seconds()
    except TypeError:  # naive vs aware
        return None


def _short(text: Any) -> str:
    t = " ".join(_s(text).split())
    return t if len(t) <= _SHORT else t[: _SHORT - 3] + "..."


def _failure_short(typ: str, p: dict) -> str:
    if typ == "turn.timeout":
        return _short(f"{p.get('model_id', '')} timeout {p.get('timeout_s', 0)}s round {p.get('round', 0)}")
    if typ == "task.failed":
        return _short(f"{p.get('task_id', '')} {p.get('failing_check') or p.get('reason') or p.get('error_tail') or ''}")
    if typ == "model.failed":
        return _short(f"{p.get('model_id', '')} {p.get('stage', '')} {p.get('error', '')}")
    if typ == "turn.invalid":
        return _short(f"{p.get('model_id', '')} {p.get('error', '')}")
    return _short(p.get("error") or p.get("detail") or typ)


def _empty() -> dict:
    return {
        "run_id": "",
        "started": None,
        "ended": None,
        "wall_s": 0.0,
        "state": None,
        "lineup": [],
        "effort": None,
        "rounds": [],
        "agreement_trend": [],
        "decision": {
            "outcome": None, "option_id": None, "agreement": 0.0,
            "rounds_run": 0, "confidence": 0.0, "final_text": "",
        },
        "extended": 0,
        "tribunal": None,
        "plan": {"tasks": 0, "titles": []},
        "tasks": {"passed": 0, "failed": 0, "blocked": 0, "skipped": 0},
        "reviews": [],
        "final_say": None,
        "integration": {"ok": None, "files_written": 0},
        "memory": {"candidates": 0, "committed": 0},
        "failures": [],
        "tokens": {"in": 0, "out": 0},
        "calls": 0,
    }


def _apply(out: dict, st: dict, e: dict) -> None:
    typ = e.get("type")
    if not isinstance(typ, str):
        return
    p = _d(e.get("payload"))

    if typ == "run.state_changed":
        out["state"] = _s(p.get("to_state")) or out["state"]
    elif typ == "router.lineup_selected":
        seats = _l(_d(p.get("lineup")).get("seats"))
        out["lineup"] = [
            {"seat_no": s.get("seat_no"), "model_id": s.get("model_id", ""), "lens": s.get("lens")}
            for s in seats if isinstance(s, dict)
        ]
    elif typ == "effort.planned":
        out["effort"] = p
    elif typ == "round.started":
        rnd = _int(p.get("round"))
        if p.get("is_review"):
            st["review_rounds"].add(rnd)
        else:
            st["round_ts"][rnd] = e.get("ts")
    elif typ == "round.completed":
        rnd = _int(p.get("round"))
        if rnd in st["review_rounds"]:
            return
        ms = p.get("ms")
        secs = _num(ms) / 1000.0 if _num(ms) > 0 else _seconds_between(st["round_ts"].get(rnd), e.get("ts"))
        out["rounds"].append({
            "round": rnd,
            "agreement": _num(p.get("agreement")),
            "tally": _d(p.get("tally")),
            "converged": bool(p.get("converged")),
            "seconds": round(secs, 2) if secs is not None else None,
        })
    elif typ == "decision.final":
        dec = _d(p.get("decision"))
        out["decision"] = {
            "outcome": _s(dec.get("outcome")) or None,
            "option_id": dec.get("option_id"),
            "agreement": _num(dec.get("agreement")),
            "rounds_run": _int(dec.get("rounds_run")),
            "confidence": _num(dec.get("confidence")),
            "final_text": _s(dec.get("final_text"))[:_FINAL_TEXT],
        }
    elif typ == "round.extended":
        out["extended"] += 1
    elif typ == "tribunal.outcome":
        out["tribunal"] = p
    elif typ in ("plan.ready", "plan.drafted"):
        tasks = [t for t in _l(_d(p.get("plan")).get("tasks")) if isinstance(t, dict)]
        if tasks or typ == "plan.ready" or not out["plan"]["tasks"]:
            out["plan"] = {
                "tasks": len(tasks),
                "titles": [_s(t.get("title") or t.get("id")) for t in tasks],
            }
    elif typ in _TASK_END:
        tid = p.get("task_id")
        if isinstance(tid, str):
            st["task_final"][tid] = _TASK_END[typ]
    elif typ == "review.verdict":
        out["reviews"].append({
            "cycle": _int(p.get("cycle")),
            "verdict": _s(p.get("verdict")) or None,
            "tally": _d(p.get("tally")),
        })
    elif typ == "review.final_say":
        out["final_say"] = p
    elif typ == "integration.result":
        out["integration"] = {"ok": bool(p.get("ok")), "files_written": len(_l(p.get("files_written")))}
    elif typ == "memory.candidate":
        out["memory"]["candidates"] += 1
    elif typ == "memory.committed":
        out["memory"]["committed"] += 1
    elif typ == "turn.completed":
        out["calls"] += 1
        tin = _int(p.get("tokens_in"))
        tout = _int(p.get("tokens_out")) or _int(p.get("tokens"))
        out["tokens"]["in"] += tin
        out["tokens"]["out"] += tout
    elif typ == "run.created" and not out["run_id"]:
        out["run_id"] = _s(p.get("run_id"))

    if typ in _FAIL_TYPES:
        out["failures"].append({"seq": e.get("seq"), "type": typ, "short": _failure_short(typ, p)})


def summarize(events: list[dict]) -> dict:
    """Fold events into the summary dict. Unknown or malformed events are skipped."""
    out = _empty()
    st: dict = {"round_ts": {}, "review_rounds": set(), "task_final": {}}
    first_ts = last_ts = None
    try:
        evs = list(events) if events is not None else []
    except TypeError:
        evs = []
    for e in evs:
        if not isinstance(e, dict):
            continue
        try:
            if not out["run_id"] and isinstance(e.get("run_id"), str):
                out["run_id"] = e["run_id"]
            ts = e.get("ts")
            if _parse_ts(ts) is not None:
                if first_ts is None:
                    first_ts = ts
                last_ts = ts
            _apply(out, st, e)
        except Exception:  # one bad event must not sink the report
            continue
    out["started"], out["ended"] = first_ts, last_ts
    wall = _seconds_between(first_ts, last_ts)
    out["wall_s"] = round(wall, 2) if wall is not None else 0.0
    out["agreement_trend"] = [r["agreement"] for r in out["rounds"]]
    for status in st["task_final"].values():
        out["tasks"][status] += 1
    return out


def _tally(t: Any) -> str:
    t = _d(t)
    return " ".join(f"{k}:{v}" for k, v in t.items()) or "-"


def summary_text(summary: dict) -> str:
    """Compact terminal report, about 25 lines. Tolerates a partial dict."""
    base = _empty()
    s = {**base, **(summary if isinstance(summary, dict) else {})}
    dec = {**base["decision"], **_d(s["decision"])}
    tasks = {**base["tasks"], **_d(s["tasks"])}
    plan = {**base["plan"], **_d(s["plan"])}
    integ = {**base["integration"], **_d(s["integration"])}
    mem = {**base["memory"], **_d(s["memory"])}
    tok = {**base["tokens"], **_d(s["tokens"])}
    lines = [
        f"RUN {s['run_id'] or '?'}  state={s['state'] or '?'}  wall={_num(s['wall_s']):.1f}s",
        f"  {s['started'] or '?'} -> {s['ended'] or '?'}",
        f"calls={s['calls']}  tokens in={tok['in']} out={tok['out']}",
    ]
    lineup = [x for x in _l(s["lineup"]) if isinstance(x, dict)]
    if lineup:
        lines.append("LINEUP")
        lines += [f"  seat {x.get('seat_no')}: {x.get('model_id', '')} [{x.get('lens') or '-'}]" for x in lineup]
    eff = s["effort"]
    if isinstance(eff, dict):
        lines.append(f"EFFORT {eff.get('level', '?')} deadline={eff.get('deadline_s', 0)}s "
                     f"extra<={eff.get('max_extra_rounds', 0)}  extended={s['extended']}")
    else:
        lines.append(f"EFFORT none  extended={s['extended']}")
    rounds = [r for r in _l(s["rounds"]) if isinstance(r, dict)]
    lines.append("ROUNDS " + (" -> ".join(f"{_num(r.get('agreement')):.0%}" for r in rounds) or "none"))
    for r in rounds:
        sec = r.get("seconds")
        lines.append(f"  r{r.get('round')}: {_num(r.get('agreement')):.0%} {_tally(r.get('tally'))}"
                     f"{' CONVERGED' if r.get('converged') else ''}"
                     f"{f' {sec:.1f}s' if isinstance(sec, (int, float)) else ''}")
    lines.append(f"DECISION {dec['outcome'] or 'none'} option={dec['option_id']} agree={_num(dec['agreement']):.0%} "
                 f"rounds={dec['rounds_run']} conf={_num(dec['confidence']):.2f}")
    if dec["final_text"]:
        lines.append("  " + _short(dec["final_text"]))
    trib = s["tribunal"]
    if isinstance(trib, dict):
        lines.append(f"TRIBUNAL {_s(trib.get('outcome')) or '?'} seat={trib.get('seat_no')} "
                     f"{_short(trib.get('reason'))}")
    lines.append(f"PLAN tasks={plan['tasks']}  passed={tasks['passed']} failed={tasks['failed']} "
                 f"blocked={tasks['blocked']} skipped={tasks['skipped']}")
    for rv in _l(s["reviews"]):
        if isinstance(rv, dict):
            lines.append(f"REVIEW cycle {rv.get('cycle')}: {rv.get('verdict')} ({_tally(rv.get('tally'))})")
    fs = s["final_say"]
    if isinstance(fs, dict):
        lines.append(f"FINAL SAY seat={fs.get('seat_no')} {_s(fs.get('verdict'))} {_short(fs.get('reason'))}")
    lines.append(f"INTEGRATION ok={integ['ok']} files={integ['files_written']}  "
                 f"MEMORY candidates={mem['candidates']} committed={mem['committed']}")
    fails = [f for f in _l(s["failures"]) if isinstance(f, dict)]
    lines.append(f"FAILURES {len(fails)}")
    for f in fails[:5]:
        lines.append(f"  #{f.get('seq')} {f.get('type')}: {f.get('short')}")
    if len(fails) > 5:
        lines.append(f"  ... {len(fails) - 5} more")
    return "\n".join(lines)
