"""SQLite store (spec 16.2). One connection, one lock, every statement under the lock.

Conventions
- `Store(path)` opens the database and creates every table of 16.2. `init()` is idempotent.
- File databases use write-ahead logging. ":memory:" is for tests.
- The connection is in autocommit mode: each statement is its own transaction.
- JSON columns hold `json.dumps` text. Pydantic models are dumped with `mode="json"`.
- `events.ts` is an ISO-8601 UTC string (for people and SQL). `events.ts_epoch` holds the same
  instant as float seconds, which is what `schemas.Event.ts` carries.
- No table here knows about HTTP, models or the clock except through the injected `clock`.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import BaseModel

from council.core.schemas import (
    BehaviourStats,
    CalibrationCell,
    CallResult,
    CallSpec,
    ChronicleEntry,
    ClaimRecord,
    Correction,
    Event,
)

# Tables reachable through put_json / get_json.
JSON_TABLES: tuple[str, ...] = ("lineups", "decisions", "plans")

# Columns update_run may set.
RUN_COLUMNS: tuple[str, ...] = (
    "task", "workspace", "mode", "state", "created", "updated", "finished", "outcome",
    "counters", "error", "snapshot",
)
_RUN_JSON_COLUMNS = ("counters", "snapshot")

_CHRONICLE_JSON_COLUMNS = ("evidence", "votes", "embedding")
_CHRONICLE_COLUMNS: tuple[str, ...] = (
    "id", "kind", "scope", "statement", "rationale", "evidence", "status", "confidence",
    "support_count", "contradict_count", "created_at", "last_confirmed_at", "review_after",
    "supersedes", "votes", "embedding",
)

SCHEMA: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        task TEXT NOT NULL DEFAULT '',
        workspace TEXT,
        mode TEXT NOT NULL DEFAULT 'standard',
        state TEXT NOT NULL DEFAULT 'INTAKE',
        created REAL,
        updated REAL,
        finished REAL,
        outcome TEXT,
        counters TEXT NOT NULL DEFAULT '{}',
        error TEXT,
        snapshot TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        ts TEXT NOT NULL,
        ts_epoch REAL NOT NULL,
        type TEXT NOT NULL,
        payload TEXT NOT NULL DEFAULT '{}'
    )""",
    "CREATE INDEX IF NOT EXISTS events_run_seq ON events (run_id, seq)",
    """CREATE TABLE IF NOT EXISTS lineups (
        run_id TEXT PRIMARY KEY,
        json TEXT NOT NULL,
        updated REAL
    )""",
    """CREATE TABLE IF NOT EXISTS seats (
        run_id TEXT NOT NULL,
        seat_no INTEGER NOT NULL,
        model_id TEXT NOT NULL,
        lens TEXT,
        is_wildcard INTEGER NOT NULL DEFAULT 0,
        is_chair INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (run_id, seat_no)
    )""",
    """CREATE TABLE IF NOT EXISTS turns (
        call_id TEXT PRIMARY KEY,
        run_id TEXT,
        purpose TEXT NOT NULL DEFAULT '',
        model_id TEXT,
        round INTEGER,
        seat_no INTEGER,
        tokens_in INTEGER NOT NULL DEFAULT 0,
        tokens_out INTEGER NOT NULL DEFAULT 0,
        tokens_reasoning INTEGER NOT NULL DEFAULT 0,
        ms REAL NOT NULL DEFAULT 0,
        tps REAL NOT NULL DEFAULT 0,
        ok INTEGER NOT NULL DEFAULT 0,
        error TEXT,
        content TEXT NOT NULL DEFAULT '',
        reasoning_text TEXT,
        attempts INTEGER NOT NULL DEFAULT 1,
        cached INTEGER NOT NULL DEFAULT 0,
        ts REAL,
        prompt TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS turns_run ON turns (run_id)",
    """CREATE TABLE IF NOT EXISTS options (
        run_id TEXT NOT NULL,
        round INTEGER NOT NULL,
        option_id TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        holders TEXT NOT NULL DEFAULT '[]',
        answer_key TEXT,
        PRIMARY KEY (run_id, round, option_id)
    )""",
    """CREATE TABLE IF NOT EXISTS cruxes (
        run_id TEXT NOT NULL,
        crux_id TEXT NOT NULL,
        statement TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL DEFAULT 'factual',
        between_options TEXT NOT NULL DEFAULT '[]',
        resolved INTEGER NOT NULL DEFAULT 0,
        resolved_by TEXT,
        PRIMARY KEY (run_id, crux_id)
    )""",
    """CREATE TABLE IF NOT EXISTS ballots (
        run_id TEXT NOT NULL,
        round INTEGER NOT NULL,
        seat_no INTEGER NOT NULL,
        choice TEXT NOT NULL,
        ranking TEXT NOT NULL DEFAULT '[]',
        confidence REAL NOT NULL DEFAULT 0.5,
        blocking TEXT,
        changed_because TEXT NOT NULL DEFAULT '[]',
        PRIMARY KEY (run_id, round, seat_no)
    )""",
    """CREATE TABLE IF NOT EXISTS decisions (
        run_id TEXT PRIMARY KEY,
        json TEXT NOT NULL,
        updated REAL
    )""",
    """CREATE TABLE IF NOT EXISTS plans (
        run_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        json TEXT NOT NULL,
        updated REAL,
        PRIMARY KEY (run_id, version)
    )""",
    """CREATE TABLE IF NOT EXISTS tasks (
        run_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        tier TEXT NOT NULL DEFAULT 'micro',
        deps TEXT NOT NULL DEFAULT '[]',
        write_set TEXT NOT NULL DEFAULT '[]',
        PRIMARY KEY (run_id, task_id)
    )""",
    """CREATE TABLE IF NOT EXISTS attempts (
        run_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        n INTEGER NOT NULL,
        model_id TEXT,
        ops TEXT NOT NULL DEFAULT '[]',
        result TEXT,
        failing_check TEXT,
        PRIMARY KEY (run_id, task_id, n)
    )""",
    """CREATE TABLE IF NOT EXISTS checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        task_id TEXT,
        attempt INTEGER,
        check_json TEXT NOT NULL DEFAULT '{}',
        exit_code INTEGER,
        output_path TEXT,
        ok INTEGER NOT NULL DEFAULT 0,
        ms REAL NOT NULL DEFAULT 0
    )""",
    "CREATE INDEX IF NOT EXISTS checks_run_task ON checks (run_id, task_id, attempt)",
    """CREATE TABLE IF NOT EXISTS chronicle (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL DEFAULT 'lesson',
        scope TEXT NOT NULL DEFAULT 'global',
        statement TEXT NOT NULL DEFAULT '',
        rationale TEXT NOT NULL DEFAULT '',
        evidence TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'provisional',
        confidence REAL NOT NULL DEFAULT 0.5,
        support_count INTEGER NOT NULL DEFAULT 0,
        contradict_count INTEGER NOT NULL DEFAULT 0,
        created_at REAL,
        last_confirmed_at REAL,
        review_after INTEGER NOT NULL DEFAULT 20,
        supersedes TEXT,
        votes TEXT NOT NULL DEFAULT '[]',
        embedding TEXT NOT NULL DEFAULT '[]'
    )""",
    """CREATE TABLE IF NOT EXISTS chronicle_votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_id TEXT NOT NULL,
        run_id TEXT,
        seat_model TEXT,
        verdict TEXT NOT NULL DEFAULT '{}'
    )""",
    "CREATE INDEX IF NOT EXISTS chronicle_votes_entry ON chronicle_votes (entry_id)",
    """CREATE TABLE IF NOT EXISTS model_stats (
        model_id TEXT NOT NULL,
        category TEXT NOT NULL,
        alpha REAL NOT NULL DEFAULT 1.0,
        beta REAL NOT NULL DEFAULT 1.0,
        counters TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (model_id, category)
    )""",
    """CREATE TABLE IF NOT EXISTS pair_stats (
        model_a TEXT NOT NULL,
        model_b TEXT NOT NULL,
        runs INTEGER NOT NULL DEFAULT 0,
        successes INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (model_a, model_b)
    )""",
    """CREATE TABLE IF NOT EXISTS calibration (
        task_id TEXT NOT NULL,
        model_id TEXT NOT NULL,
        correct INTEGER,
        answer_key TEXT,
        PRIMARY KEY (task_id, model_id)
    )""",
    """CREATE TABLE IF NOT EXISTS call_cache (
        key TEXT PRIMARY KEY,
        json TEXT NOT NULL,
        created REAL
    )""",
    # Phase 2 tables (27, 28). Not part of the 16.2 TABLES tuple.
    """CREATE TABLE IF NOT EXISTS kv (
        namespace TEXT NOT NULL,
        key TEXT NOT NULL,
        json TEXT NOT NULL,
        updated REAL,
        PRIMARY KEY (namespace, key)
    )""",
    """CREATE TABLE IF NOT EXISTS claims (
        id TEXT PRIMARY KEY,
        run_id TEXT,
        project TEXT NOT NULL DEFAULT '',
        model_id TEXT NOT NULL DEFAULT '',
        label TEXT NOT NULL DEFAULT 'unknown',
        labelled_by TEXT NOT NULL DEFAULT 'none',
        json TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS claims_model ON claims (model_id)",
    """CREATE TABLE IF NOT EXISTS corrections (
        id TEXT PRIMARY KEY,
        project TEXT NOT NULL DEFAULT '',
        model_id TEXT NOT NULL DEFAULT '',
        json TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS behaviour (
        model_id TEXT PRIMARY KEY,
        json TEXT NOT NULL
    )""",
)

# Phase 2 tables created by init() in addition to TABLES.
EXTRA_TABLES: tuple[str, ...] = ("kv", "claims", "corrections", "behaviour")

TABLES: tuple[str, ...] = (
    "runs", "events", "lineups", "seats", "turns", "options", "cruxes", "ballots", "decisions",
    "plans", "tasks", "attempts", "checks", "chronicle", "chronicle_votes", "model_stats",
    "pair_stats", "calibration", "call_cache",
)


def _plain(obj: Any) -> Any:
    """Pydantic models and enums to JSON-ready values."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"not JSON serializable: {obj.__class__.__name__}")


def _dumps(obj: Any) -> str:
    return json.dumps(obj, default=_plain, ensure_ascii=False, separators=(",", ":"))


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="microseconds")


def _prompt_json(messages: Any) -> str:
    """The messages of a call as JSON text: what the model was actually sent."""
    try:
        return json.dumps(list(messages or []), ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return "[]"


class Store:
    def __init__(self, path: str | Path = ":memory:", clock: Callable[[], float] = time.time):
        self.path = str(path)
        self._clock = clock
        self._lock = threading.RLock()
        self._closed = False
        self.is_memory = self.path == ":memory:"
        if not self.is_memory:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            self.path, check_same_thread=False, isolation_level=None, timeout=30.0
        )
        self._conn.row_factory = sqlite3.Row
        if not self.is_memory:
            self._exec("PRAGMA journal_mode=WAL")
            self._exec("PRAGMA synchronous=NORMAL")
        self.init()

    # ---------------------------------------------------------------- low level

    def _exec(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self._lock:
            if self._closed:
                raise RuntimeError("store is closed")
            return self._conn.execute(sql, params)

    def _all(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._exec(sql, params).fetchall()

    def _one(self, sql: str, params: tuple | list = ()) -> Optional[sqlite3.Row]:
        with self._lock:
            return self._exec(sql, params).fetchone()

    def init(self) -> None:
        """Create every table of 16.2. Safe to call again."""
        with self._lock:
            for stmt in SCHEMA:
                self._exec(stmt)
            # databases made before turns.prompt existed
            cols = {r["name"] for r in self._exec("PRAGMA table_info(turns)").fetchall()}
            if "prompt" not in cols:
                self._exec("ALTER TABLE turns ADD COLUMN prompt TEXT")

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---------------------------------------------------------------- runs

    def create_run(self, run_id: str, task: str, workspace: Optional[str], mode: str, state: Any) -> None:
        now = self._clock()
        self._exec(
            "INSERT INTO runs (id, task, workspace, mode, state, created, updated, counters)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, '{}')",
            (run_id, task, workspace, _scalar(mode), _scalar(state), now, now),
        )

    def update_run(self, run_id: str, **fields: Any) -> None:
        """Set columns of one run. Unknown column names raise ValueError."""
        unknown = [k for k in fields if k not in RUN_COLUMNS]
        if unknown:
            raise ValueError(f"unknown run columns: {sorted(unknown)}")
        if "updated" not in fields:
            fields["updated"] = self._clock()
        cols, vals = [], []
        for name, value in fields.items():
            cols.append(f"{name} = ?")
            if name in _RUN_JSON_COLUMNS:
                vals.append(None if value is None else _dumps(value))
            else:
                vals.append(_scalar(value))
        vals.append(run_id)
        self._exec(f"UPDATE runs SET {', '.join(cols)} WHERE id = ?", vals)

    def get_run(self, run_id: str) -> Optional[dict]:
        row = self._one("SELECT * FROM runs WHERE id = ?", (run_id,))
        return _run_dict(row) if row is not None else None

    def list_runs(self) -> list[dict]:
        """Newest first."""
        rows = self._all("SELECT * FROM runs ORDER BY created DESC, rowid DESC")
        return [_run_dict(r) for r in rows]

    # ---------------------------------------------------------------- events

    def append_event(self, run_id: Optional[str], type: str, payload: Optional[dict] = None) -> Event:
        epoch = float(self._clock())
        if isinstance(payload, BaseModel):
            payload = payload.model_dump(mode="json")
        text = _dumps(payload or {})
        with self._lock:
            cur = self._exec(
                "INSERT INTO events (run_id, ts, ts_epoch, type, payload) VALUES (?, ?, ?, ?, ?)",
                (run_id, _iso(epoch), epoch, type, text),
            )
            seq = int(cur.lastrowid)
        return Event(type=type, seq=seq, ts=epoch, run_id=run_id, payload=json.loads(text))

    def events_since(self, run_id: Optional[str], since: int, limit: int = 5000) -> list[Event]:
        """Events with seq > since, oldest first. run_id None means every run."""
        if run_id is None:
            rows = self._all(
                "SELECT seq, run_id, ts_epoch, type, payload FROM events"
                " WHERE seq > ? ORDER BY seq LIMIT ?",
                (int(since), int(limit)),
            )
        else:
            rows = self._all(
                "SELECT seq, run_id, ts_epoch, type, payload FROM events"
                " WHERE run_id = ? AND seq > ? ORDER BY seq LIMIT ?",
                (run_id, int(since), int(limit)),
            )
        return [
            Event(
                type=r["type"], seq=r["seq"], ts=r["ts_epoch"], run_id=r["run_id"],
                payload=json.loads(r["payload"]),
            )
            for r in rows
        ]

    def event_ts_iso(self, seq: int) -> Optional[str]:
        """The stored ISO-8601 UTC timestamp of one event."""
        row = self._one("SELECT ts FROM events WHERE seq = ?", (int(seq),))
        return row["ts"] if row is not None else None

    # ---------------------------------------------------------------- JSON blobs

    def put_json(self, table: str, key: str, obj: Any) -> None:
        """lineups, decisions: one row per key, replaced. plans: every put is a new version."""
        _check_json_table(table)
        text = _dumps(obj)
        now = self._clock()
        with self._lock:
            if table == "plans":
                row = self._one("SELECT COALESCE(MAX(version), 0) AS v FROM plans WHERE run_id = ?", (key,))
                self._exec(
                    "INSERT INTO plans (run_id, version, json, updated) VALUES (?, ?, ?, ?)",
                    (key, int(row["v"]) + 1, text, now),
                )
            else:
                self._exec(
                    f"INSERT INTO {table} (run_id, json, updated) VALUES (?, ?, ?)"
                    " ON CONFLICT(run_id) DO UPDATE SET json = excluded.json, updated = excluded.updated",
                    (key, text, now),
                )

    def get_json(self, table: str, key: str) -> Any:
        """The stored object, or None. For plans: the latest version."""
        _check_json_table(table)
        if table == "plans":
            row = self._one(
                "SELECT json FROM plans WHERE run_id = ? ORDER BY version DESC LIMIT 1", (key,)
            )
        else:
            row = self._one(f"SELECT json FROM {table} WHERE run_id = ?", (key,))
        return json.loads(row["json"]) if row is not None else None

    def plan_version(self, run_id: str) -> int:
        """Latest plan version of a run, 0 when there is none."""
        row = self._one("SELECT COALESCE(MAX(version), 0) AS v FROM plans WHERE run_id = ?", (run_id,))
        return int(row["v"])

    # ---------------------------------------------------------------- turns

    def record_turn(self, spec: CallSpec, result: CallResult) -> None:
        meta = spec.meta or {}
        self._exec(
            "INSERT OR REPLACE INTO turns (call_id, run_id, purpose, model_id, round, seat_no,"
            " tokens_in, tokens_out, tokens_reasoning, ms, tps, ok, error, content,"
            " reasoning_text, attempts, cached, ts, prompt)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                spec.call_id, spec.run_id, spec.purpose, result.model_id or spec.model_id,
                _int_or_none(meta.get("round")), _int_or_none(meta.get("seat_no")),
                result.tokens_in, result.tokens_out, result.tokens_reasoning,
                result.prompt_ms + result.gen_ms, result.tps, int(result.ok), result.error,
                result.content, result.reasoning_text, result.attempts, int(result.cached),
                self._clock(), _prompt_json(spec.messages),
            ),
        )

    def list_turns(self, run_id: str) -> list[dict]:
        """Turns of one run, oldest first. `prompt` is the list of messages that was sent."""
        rows = self._all("SELECT * FROM turns WHERE run_id = ? ORDER BY ts, rowid", (run_id,))
        out = []
        for r in rows:
            d = dict(r)
            d["ok"] = bool(d["ok"])
            d["cached"] = bool(d["cached"])
            try:
                d["prompt"] = json.loads(d["prompt"]) if d.get("prompt") else []
            except (TypeError, ValueError):
                d["prompt"] = []
            out.append(d)
        return out

    # ---------------------------------------------------------------- call cache

    def cache_get(self, key: str) -> Optional[CallResult]:
        row = self._one("SELECT json FROM call_cache WHERE key = ?", (key,))
        return CallResult.model_validate_json(row["json"]) if row is not None else None

    def cache_put(self, key: str, result: CallResult) -> None:
        self._exec(
            "INSERT INTO call_cache (key, json, created) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET json = excluded.json, created = excluded.created",
            (key, _dumps(result), self._clock()),
        )

    # ---------------------------------------------------------------- model stats

    def get_model_stats(self) -> dict[tuple[str, str], tuple[float, float]]:
        rows = self._all("SELECT model_id, category, alpha, beta FROM model_stats")
        return {(r["model_id"], r["category"]): (r["alpha"], r["beta"]) for r in rows}

    def upsert_model_stat(self, model_id: str, category: str, alpha: float, beta: float) -> None:
        self._exec(
            "INSERT INTO model_stats (model_id, category, alpha, beta) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(model_id, category) DO UPDATE SET alpha = excluded.alpha, beta = excluded.beta",
            (model_id, category, float(alpha), float(beta)),
        )

    # ---------------------------------------------------------------- chronicle

    def chronicle_put(self, entry: ChronicleEntry) -> None:
        data = entry.model_dump(mode="json")
        vals = [
            _dumps(data[c]) if c in _CHRONICLE_JSON_COLUMNS else data[c] for c in _CHRONICLE_COLUMNS
        ]
        marks = ", ".join("?" for _ in _CHRONICLE_COLUMNS)
        self._exec(
            f"INSERT OR REPLACE INTO chronicle ({', '.join(_CHRONICLE_COLUMNS)}) VALUES ({marks})",
            vals,
        )

    def chronicle_list(self) -> list[ChronicleEntry]:
        """Oldest first."""
        rows = self._all("SELECT * FROM chronicle ORDER BY created_at, rowid")
        out = []
        for r in rows:
            d = dict(r)
            for c in _CHRONICLE_JSON_COLUMNS:
                d[c] = json.loads(d[c]) if d[c] else []
            out.append(ChronicleEntry.model_validate(d))
        return out

    def chronicle_delete(self, id: str) -> None:
        self._exec("DELETE FROM chronicle WHERE id = ?", (id,))

    # ---------------------------------------------------------------- kv

    def kv_put(self, namespace: str, key: str, obj: Any) -> None:
        self._exec(
            "INSERT INTO kv (namespace, key, json, updated) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(namespace, key) DO UPDATE SET json = excluded.json, updated = excluded.updated",
            (namespace, key, _dumps(obj), self._clock()),
        )

    def kv_get(self, namespace: str, key: str) -> Optional[dict]:
        row = self._one("SELECT json FROM kv WHERE namespace = ? AND key = ?", (namespace, key))
        return json.loads(row["json"]) if row is not None else None

    def kv_list(self, namespace: str) -> dict[str, dict]:
        rows = self._all("SELECT key, json FROM kv WHERE namespace = ? ORDER BY key", (namespace,))
        return {r["key"]: json.loads(r["json"]) for r in rows}

    def kv_delete(self, namespace: str, key: str) -> None:
        self._exec("DELETE FROM kv WHERE namespace = ? AND key = ?", (namespace, key))

    # ---------------------------------------------------------------- calibration

    def calibration_put(self, cell: CalibrationCell) -> None:
        self._exec(
            "INSERT INTO calibration (task_id, model_id, correct, answer_key) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(task_id, model_id) DO UPDATE SET correct = excluded.correct,"
            " answer_key = excluded.answer_key",
            (cell.task_id, cell.model_id, int(bool(cell.correct)), cell.answer_key),
        )

    def calibration_matrix(self) -> dict[str, dict[str, CalibrationCell]]:
        out: dict[str, dict[str, CalibrationCell]] = {}
        for r in self._all("SELECT * FROM calibration ORDER BY task_id, model_id"):
            out.setdefault(r["task_id"], {})[r["model_id"]] = CalibrationCell(
                task_id=r["task_id"], model_id=r["model_id"],
                correct=bool(r["correct"]), answer_key=r["answer_key"],
            )
        return out

    def calibration_clear(self) -> None:
        self._exec("DELETE FROM calibration")

    # ---------------------------------------------------------------- claims

    def claims_put(self, record: ClaimRecord) -> None:
        self._exec(
            "INSERT INTO claims (id, run_id, project, model_id, label, labelled_by, json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET run_id = excluded.run_id, project = excluded.project,"
            " model_id = excluded.model_id, label = excluded.label,"
            " labelled_by = excluded.labelled_by, json = excluded.json",
            (record.id, record.run_id, record.project, record.model_id,
             record.label, record.labelled_by, _dumps(record)),
        )

    def claims_list(
        self, model_id: Optional[str] = None, project: Optional[str] = None,
        labelled_only: bool = False,
    ) -> list[ClaimRecord]:
        """Insertion order. labelled_only keeps labels "true" and "false"."""
        where: list[str] = []
        params: list[Any] = []
        if model_id is not None:
            where.append("model_id = ?")
            params.append(model_id)
        if project is not None:
            where.append("project = ?")
            params.append(project)
        if labelled_only:
            where.append("label IN ('true', 'false')")
        sql = "SELECT json FROM claims" + (" WHERE " + " AND ".join(where) if where else "")
        rows = self._all(sql + " ORDER BY rowid", params)
        return [ClaimRecord.model_validate_json(r["json"]) for r in rows]

    def claim_label(self, id: str, label: str, labelled_by: str) -> None:
        """Set the label of one claim. Unknown id does nothing."""
        with self._lock:
            row = self._one("SELECT json FROM claims WHERE id = ?", (id,))
            if row is None:
                return
            rec = ClaimRecord.model_validate_json(row["json"])
            self.claims_put(rec.model_copy(update={"label": label, "labelled_by": labelled_by}))

    # ---------------------------------------------------------------- corrections

    def corrections_put(self, c: Correction) -> None:
        self._exec(
            "INSERT INTO corrections (id, project, model_id, json) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET project = excluded.project,"
            " model_id = excluded.model_id, json = excluded.json",
            (c.id, c.project, c.model_id, _dumps(c)),
        )

    def corrections_list(
        self, project: Optional[str] = None, model_id: Optional[str] = None
    ) -> list[Correction]:
        where: list[str] = []
        params: list[Any] = []
        if project is not None:
            where.append("project = ?")
            params.append(project)
        if model_id is not None:
            where.append("model_id = ?")
            params.append(model_id)
        sql = "SELECT json FROM corrections" + (" WHERE " + " AND ".join(where) if where else "")
        rows = self._all(sql + " ORDER BY rowid", params)
        return [Correction.model_validate_json(r["json"]) for r in rows]

    # ---------------------------------------------------------------- behaviour

    def behaviour_get(self, model_id: str) -> BehaviourStats:
        row = self._one("SELECT json FROM behaviour WHERE model_id = ?", (model_id,))
        if row is None:
            return BehaviourStats(model_id=model_id)
        return BehaviourStats.model_validate_json(row["json"])

    def behaviour_put(self, stats: BehaviourStats) -> None:
        self._exec(
            "INSERT INTO behaviour (model_id, json) VALUES (?, ?)"
            " ON CONFLICT(model_id) DO UPDATE SET json = excluded.json",
            (stats.model_id, _dumps(stats)),
        )

    # ---------------------------------------------------------------- run queries

    def events_for_run(self, run_id: str) -> list[Event]:
        """Every event of one run, oldest first."""
        return self.events_since(run_id, 0, limit=-1)

    def recent_lineups(self, n: int = 5) -> list[list[str]]:
        """Model ids (seat order) of the n newest stored lineups, newest first."""
        rows = self._all("SELECT json FROM lineups ORDER BY updated DESC, rowid DESC")
        out: list[list[str]] = []
        for r in rows:
            if len(out) >= n:
                break
            try:
                seats = json.loads(r["json"]).get("seats", [])
                ids = [x["model_id"] for x in sorted(seats, key=lambda x: x.get("seat_no", 0))]
            except (AttributeError, TypeError, KeyError, ValueError):
                continue
            out.append(ids)
        return out


# -------------------------------------------------------------------- helpers


def _check_json_table(table: str) -> None:
    if table not in JSON_TABLES:
        raise ValueError(f"table not allowed: {table!r} (allowed: {', '.join(JSON_TABLES)})")


def _scalar(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _run_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["counters"] = json.loads(d["counters"]) if d.get("counters") else {}
    d["snapshot"] = json.loads(d["snapshot"]) if d.get("snapshot") else None
    return d


__all__ = ["Store", "JSON_TABLES", "RUN_COLUMNS", "TABLES", "EXTRA_TABLES", "SCHEMA"]
