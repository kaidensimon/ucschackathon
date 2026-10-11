"""Print one council run from the box database.

Run from ~/council/main-dev on the box:
    python tools/box/summarize_run.py            latest run (last run.created)
    python tools/box/summarize_run.py <run_id>   a given run

Prints the compact summary (council/api/run_summary.py), then the full final text of
decision.final and every review.verdict / review.final_say event.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from council.api.run_summary import summarize, summary_text  # noqa: E402

DB = Path.home() / "council" / "box" / "db" / "council.db"


def _payload(raw) -> dict:
    try:
        d = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _latest_run(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT run_id FROM events WHERE type = 'run.created' ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    return row[0] if row and row[0] else None


def _load(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT seq, ts, type, payload, run_id FROM events WHERE run_id = ? ORDER BY seq",
        (run_id,),
    ).fetchall()
    return [
        {"seq": seq, "ts": ts, "type": typ, "payload": _payload(raw), "run_id": rid}
        for seq, ts, typ, raw, rid in rows
    ]


def _full_lines(events: list[dict]) -> list[str]:
    out: list[str] = []
    for e in events:
        typ = e["type"]
        if typ == "decision.final":
            dec = e["payload"].get("decision")
            dec = dec if isinstance(dec, dict) else {}
            text = dec.get("final_text")
            out.append(f"FINAL TEXT (seq {e['seq']}):")
            out.append("" if text is None else str(text))
        elif typ in ("review.verdict", "review.final_say"):
            body = json.dumps(e["payload"], ensure_ascii=False, sort_keys=True)
            out.append(f"{typ} seq={e['seq']} {body}")
    return out


def main(argv: list[str]) -> int:
    if not DB.is_file():
        print(f"no database at {DB}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(str(DB))
    try:
        run_id = argv[1] if len(argv) > 1 else _latest_run(conn)
        if not run_id:
            print("no run found", file=sys.stderr)
            return 1
        events = _load(conn, run_id)
    finally:
        conn.close()
    if not events:
        print(f"no events for run {run_id}", file=sys.stderr)
        return 1
    print(summary_text(summarize(events)))
    lines = _full_lines(events)
    if lines:
        print()
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
