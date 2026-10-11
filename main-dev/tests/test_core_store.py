import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

from council.core import event_types as et
from council.core.schemas import (
    BehaviourStats,
    CalibrationCell,
    CallResult,
    ClaimRecord,
    Correction,
    CallSpec,
    ChronicleEntry,
    Decision,
    Event,
    EvidenceRef,
    LineupRecord,
    MemoryVerdict,
    Plan,
    RunState,
    SeatAssignment,
)
from council.core.store import JSON_TABLES, TABLES, Store

SPEC_TABLES = {
    "runs", "events", "lineups", "seats", "turns", "options", "cruxes", "ballots", "decisions",
    "plans", "tasks", "attempts", "checks", "chronicle", "chronicle_votes", "model_stats",
    "pair_stats", "calibration", "call_cache",
}


class FakeClock:
    def __init__(self, start: float = 1_800_000_000.0):
        self.t = start

    def __call__(self) -> float:
        self.t += 1.0
        return self.t


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.store = Store(clock=self.clock)
        self.addCleanup(self.store.close)


class TestInit(StoreCase):
    def test_every_table_of_16_2(self):
        rows = self.store._all("SELECT name FROM sqlite_master WHERE type = 'table'")
        names = {r["name"] for r in rows}
        self.assertTrue(SPEC_TABLES <= names, SPEC_TABLES - names)
        self.assertEqual(set(TABLES), SPEC_TABLES)

    def test_init_twice_keeps_data(self):
        self.store.create_run("r1", "t", None, "quick", "INTAKE")
        self.store.init()
        self.assertIsNotNone(self.store.get_run("r1"))

    def test_close_twice_and_use_after_close(self):
        s = Store()
        s.close()
        s.close()
        with self.assertRaises(RuntimeError):
            s.list_runs()

    def test_context_manager(self):
        with Store() as s:
            s.create_run("r", "t", None, "quick", "INTAKE")
        with self.assertRaises(RuntimeError):
            s.get_run("r")


class TestRuns(StoreCase):
    def test_create_get(self):
        self.store.create_run("r1", "do thing", "/ws", "standard", RunState.INTAKE)
        run = self.store.get_run("r1")
        self.assertEqual(run["id"], "r1")
        self.assertEqual(run["task"], "do thing")
        self.assertEqual(run["workspace"], "/ws")
        self.assertEqual(run["mode"], "standard")
        self.assertEqual(run["state"], "INTAKE")
        self.assertEqual(run["counters"], {})
        self.assertIsNone(run["finished"])
        self.assertIsNone(run["outcome"])
        self.assertIsInstance(run["created"], float)

    def test_get_missing(self):
        self.assertIsNone(self.store.get_run("nope"))

    def test_duplicate_id_raises(self):
        self.store.create_run("r1", "t", None, "quick", "INTAKE")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.create_run("r1", "t", None, "quick", "INTAKE")

    def test_update(self):
        self.store.create_run("r1", "t", None, "quick", "INTAKE")
        before = self.store.get_run("r1")["updated"]
        self.store.update_run(
            "r1", state=RunState.DONE, outcome="consensus", finished=5.0,
            counters={"calls": 3, "phase_ms": {"INTAKE": 1.5}}, snapshot={"run_id": "r1"},
        )
        run = self.store.get_run("r1")
        self.assertEqual(run["state"], "DONE")
        self.assertEqual(run["outcome"], "consensus")
        self.assertEqual(run["finished"], 5.0)
        self.assertEqual(run["counters"], {"calls": 3, "phase_ms": {"INTAKE": 1.5}})
        self.assertEqual(run["snapshot"], {"run_id": "r1"})
        self.assertGreater(run["updated"], before)

    def test_update_unknown_column(self):
        self.store.create_run("r1", "t", None, "quick", "INTAKE")
        with self.assertRaises(ValueError):
            self.store.update_run("r1", id="x")
        with self.assertRaises(ValueError):
            self.store.update_run("r1", **{"state = 'x' --": 1})

    def test_list_newest_first(self):
        for rid in ("a", "b", "c"):
            self.store.create_run(rid, "t", None, "quick", "INTAKE")
        self.assertEqual([r["id"] for r in self.store.list_runs()], ["c", "b", "a"])

    def test_list_empty(self):
        self.assertEqual(self.store.list_runs(), [])


class TestEvents(StoreCase):
    def test_append_returns_event(self):
        ev = self.store.append_event("r1", et.RUN_CREATED, {"task": "x"})
        self.assertIsInstance(ev, Event)
        self.assertEqual(ev.seq, 1)
        self.assertEqual(ev.run_id, "r1")
        self.assertEqual(ev.type, "run.created")
        self.assertEqual(ev.payload, {"task": "x"})
        self.assertEqual(ev.ts, self.clock.t)

    def test_seq_strictly_increasing_across_runs(self):
        seqs = [self.store.append_event(f"r{i % 3}", et.ROUND_STARTED, {"round": i}).seq for i in range(20)]
        self.assertEqual(seqs, sorted(set(seqs)))
        self.assertEqual(len(seqs), 20)

    def test_seq_not_reused_after_delete(self):
        last = [self.store.append_event("r", et.ROUND_STARTED, {}).seq for _ in range(3)][-1]
        self.store._exec("DELETE FROM events")
        self.assertGreater(self.store.append_event("r", et.ROUND_STARTED, {}).seq, last)

    def test_ts_stored_as_iso_utc(self):
        ev = self.store.append_event("r1", et.RUN_CREATED, {})
        iso = self.store.event_ts_iso(ev.seq)
        self.assertIsInstance(iso, str)
        parsed = datetime.fromisoformat(iso)
        self.assertEqual(parsed.utcoffset().total_seconds(), 0)
        self.assertEqual(parsed, datetime.fromtimestamp(ev.ts, tz=timezone.utc))
        self.assertIsNone(self.store.event_ts_iso(999))

    def test_events_since(self):
        for i in range(5):
            self.store.append_event("a", et.ROUND_STARTED, {"round": i})
            self.store.append_event("b", et.ROUND_STARTED, {"round": i})
        a = self.store.events_since("a", 0)
        self.assertEqual([e.payload["round"] for e in a], [0, 1, 2, 3, 4])
        self.assertTrue(all(e.run_id == "a" for e in a))
        self.assertEqual([e.seq for e in self.store.events_since("a", a[2].seq)], [a[3].seq, a[4].seq])
        self.assertEqual(self.store.events_since("a", a[-1].seq), [])
        self.assertEqual(self.store.events_since("zzz", 0), [])

    def test_events_since_all_runs_and_limit(self):
        for i in range(6):
            self.store.append_event("a" if i % 2 else "b", et.ROUND_STARTED, {"round": i})
        every = self.store.events_since(None, 0)
        self.assertEqual([e.seq for e in every], [1, 2, 3, 4, 5, 6])
        self.assertEqual([e.seq for e in self.store.events_since(None, 2, limit=3)], [3, 4, 5])

    def test_round_trip_matches_appended(self):
        payload = et.make_payload(et.TURN_COMPLETED, call_id="c1", seat_no=2, parsed={"answer": "é"})
        ev = self.store.append_event("r1", et.TURN_COMPLETED, payload)
        self.assertEqual(self.store.events_since("r1", 0), [ev])

    def test_no_run_and_empty_payload(self):
        ev = self.store.append_event(None, et.TELEMETRY_TICK, None)
        self.assertEqual(ev.payload, {})
        got = self.store.events_since(None, 0)
        self.assertEqual(len(got), 1)
        self.assertIsNone(got[0].run_id)

    def test_threads(self):
        seqs, errors = [], []

        def work(n):
            try:
                for i in range(50):
                    seqs.append(self.store.append_event(f"r{n}", et.ROUND_STARTED, {"round": i}).seq)
                    self.store.events_since(f"r{n}", 0, limit=5)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(sorted(seqs), list(range(1, 401)))
        for n in range(8):
            mine = self.store.events_since(f"r{n}", 0)
            self.assertEqual([e.payload["round"] for e in mine], list(range(50)))


class TestJson(StoreCase):
    def test_whitelist(self):
        self.assertEqual(set(JSON_TABLES), {"lineups", "decisions", "plans"})
        for bad in ("runs", "events", "lineups; DROP TABLE runs", ""):
            with self.assertRaises(ValueError):
                self.store.put_json(bad, "k", {})
            with self.assertRaises(ValueError):
                self.store.get_json(bad, "k")

    def test_missing(self):
        for table in JSON_TABLES:
            self.assertIsNone(self.store.get_json(table, "nope"))

    def test_lineup_model_round_trip(self):
        lineup = LineupRecord(seats=[SeatAssignment(seat_no=0, model_id="m1", lens="skeptic")], k=1)
        self.store.put_json("lineups", "r1", lineup)
        self.assertEqual(LineupRecord.model_validate(self.store.get_json("lineups", "r1")), lineup)

    def test_decision_replaced(self):
        self.store.put_json("decisions", "r1", Decision(outcome="majority", final_text="a"))
        self.store.put_json("decisions", "r1", {"outcome": "consensus", "final_text": "b"})
        got = self.store.get_json("decisions", "r1")
        self.assertEqual(got["outcome"], "consensus")
        self.assertEqual(got["final_text"], "b")
        self.assertEqual(self.store._one("SELECT COUNT(*) AS n FROM decisions")["n"], 1)

    def test_plans_versioned(self):
        self.assertEqual(self.store.plan_version("r1"), 0)
        self.store.put_json("plans", "r1", Plan(goal="one"))
        self.store.put_json("plans", "r1", Plan(goal="two"))
        self.store.put_json("plans", "r2", Plan(goal="other"))
        self.assertEqual(self.store.get_json("plans", "r1")["goal"], "two")
        self.assertEqual(self.store.plan_version("r1"), 2)
        self.assertEqual(self.store.plan_version("r2"), 1)
        self.assertEqual(self.store.get_json("plans", "r2")["goal"], "other")

    def test_plain_values(self):
        self.store.put_json("lineups", "k", [1, "two", None, {"x": 1.5}])
        self.assertEqual(self.store.get_json("lineups", "k"), [1, "two", None, {"x": 1.5}])


class TestTurns(StoreCase):
    def test_record_turn(self):
        spec = CallSpec(model_id="m1", run_id="r1", purpose="seat.r0", meta={"round": 0, "seat_no": 3})
        res = CallResult(
            call_id=spec.call_id, ok=True, model_id="m1", content="hi", reasoning_text="think",
            tokens_in=10, tokens_out=20, tokens_reasoning=5, prompt_ms=100.0, gen_ms=400.0, tps=50.0,
        )
        self.store.record_turn(spec, res)
        rows = self.store.list_turns("r1")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["call_id"], spec.call_id)
        self.assertEqual(row["purpose"], "seat.r0")
        self.assertEqual(row["model_id"], "m1")
        self.assertEqual(row["round"], 0)
        self.assertEqual(row["seat_no"], 3)
        self.assertEqual((row["tokens_in"], row["tokens_out"], row["tokens_reasoning"]), (10, 20, 5))
        self.assertEqual(row["ms"], 500.0)
        self.assertEqual(row["tps"], 50.0)
        self.assertIs(row["ok"], True)
        self.assertIsNone(row["error"])
        self.assertEqual(row["content"], "hi")
        self.assertEqual(row["reasoning_text"], "think")

    def test_turn_keeps_prompt(self):
        msgs = [{"role": "system", "content": "be brief"}, {"role": "user", "content": "2 + 2?"}]
        spec = CallSpec(model_id="m1", run_id="r1", purpose="seat.r0", messages=msgs)
        self.store.record_turn(spec, CallResult(call_id=spec.call_id, ok=True, content="4"))
        self.assertEqual(self.store.list_turns("r1")[0]["prompt"], msgs)
        bare = CallSpec(model_id="m1", run_id="r2")
        self.store.record_turn(bare, CallResult(call_id=bare.call_id, ok=True))
        self.assertEqual(self.store.list_turns("r2")[0]["prompt"], [])

    def test_old_database_gains_prompt_column(self):
        self.store._exec("ALTER TABLE turns DROP COLUMN prompt")
        self.store.init()
        spec = CallSpec(model_id="m1", run_id="r1", messages=[{"role": "user", "content": "hi"}])
        self.store.record_turn(spec, CallResult(call_id=spec.call_id, ok=True))
        self.assertEqual(self.store.list_turns("r1")[0]["prompt"][0]["content"], "hi")

    def test_failed_turn_and_no_meta(self):
        spec = CallSpec(model_id="m2", run_id="r1", purpose="worker")
        self.store.record_turn(spec, CallResult(call_id=spec.call_id, ok=False, error="timeout"))
        row = self.store.list_turns("r1")[0]
        self.assertIs(row["ok"], False)
        self.assertEqual(row["error"], "timeout")
        self.assertEqual(row["model_id"], "m2")
        self.assertIsNone(row["round"])
        self.assertIsNone(row["seat_no"])

    def test_same_call_id_replaces(self):
        spec = CallSpec(model_id="m1", run_id="r1")
        self.store.record_turn(spec, CallResult(call_id=spec.call_id, ok=False, error="timeout"))
        self.store.record_turn(spec, CallResult(call_id=spec.call_id, ok=True, content="ok"))
        rows = self.store.list_turns("r1")
        self.assertEqual(len(rows), 1)
        self.assertIs(rows[0]["ok"], True)


class TestCache(StoreCase):
    def test_miss(self):
        self.assertIsNone(self.store.cache_get("k"))

    def test_put_get_replace(self):
        res = CallResult(call_id="c1", ok=True, content="x", parsed={"a": [1, 2]}, tokens_out=7)
        self.store.cache_put("k", res)
        got = self.store.cache_get("k")
        self.assertIsInstance(got, CallResult)
        self.assertEqual(got, res)
        self.store.cache_put("k", CallResult(call_id="c2", ok=True, content="y"))
        self.assertEqual(self.store.cache_get("k").content, "y")
        self.assertIsNone(self.store.cache_get("other"))


class TestModelStats(StoreCase):
    def test_empty(self):
        self.assertEqual(self.store.get_model_stats(), {})

    def test_upsert(self):
        self.store.upsert_model_stat("m1", "math", 2.0, 3.0)
        self.store.upsert_model_stat("m1", "code", 1, 1)
        self.store.upsert_model_stat("m2", "math", 4.5, 0.5)
        self.store.upsert_model_stat("m1", "math", 3.0, 3.0)
        self.assertEqual(
            self.store.get_model_stats(),
            {("m1", "math"): (3.0, 3.0), ("m1", "code"): (1.0, 1.0), ("m2", "math"): (4.5, 0.5)},
        )

    def test_upsert_keeps_counters(self):
        self.store.upsert_model_stat("m1", "math", 1.0, 1.0)
        self.store._exec("UPDATE model_stats SET counters = ? WHERE model_id = 'm1'", ('{"flips":2}',))
        self.store.upsert_model_stat("m1", "math", 2.0, 1.0)
        self.assertEqual(self.store._one("SELECT counters FROM model_stats")["counters"], '{"flips":2}')


class TestChronicle(StoreCase):
    def entry(self, id="e1", **kw):
        base = dict(
            id=id, kind="preference", scope="project:abc", statement="use tabs", rationale="user said",
            evidence=[EvidenceRef(run_id="r1", event_seq=4, quote="tabs please")],
            status="active", confidence=0.9, support_count=2, created_at=10.0,
            votes=[MemoryVerdict(durable=True, action="adopt")], embedding=[0.1, 0.2],
        )
        base.update(kw)
        return ChronicleEntry(**base)

    def test_empty(self):
        self.assertEqual(self.store.chronicle_list(), [])

    def test_round_trip(self):
        e = self.entry()
        self.store.chronicle_put(e)
        self.assertEqual(self.store.chronicle_list(), [e])

    def test_defaults_round_trip(self):
        e = ChronicleEntry(id="bare")
        self.store.chronicle_put(e)
        self.assertEqual(self.store.chronicle_list(), [e])

    def test_put_replaces(self):
        self.store.chronicle_put(self.entry())
        self.store.chronicle_put(self.entry(status="retracted", supersedes="e0"))
        got = self.store.chronicle_list()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].status, "retracted")
        self.assertEqual(got[0].supersedes, "e0")

    def test_order_and_delete(self):
        self.store.chronicle_put(self.entry("b", created_at=2.0))
        self.store.chronicle_put(self.entry("a", created_at=1.0))
        self.store.chronicle_put(self.entry("c", created_at=3.0))
        self.assertEqual([e.id for e in self.store.chronicle_list()], ["a", "b", "c"])
        self.store.chronicle_delete("b")
        self.store.chronicle_delete("missing")
        self.assertEqual([e.id for e in self.store.chronicle_list()], ["a", "c"])


class TestPhase2(StoreCase):
    def test_kv(self):
        s = self.store
        self.assertIsNone(s.kv_get("ns", "a"))
        s.kv_put("ns", "a", {"x": 1})
        s.kv_put("ns", "b", BehaviourStats(model_id="m"))
        s.kv_put("other", "a", {"y": 2})
        self.assertEqual(s.kv_get("ns", "a"), {"x": 1})
        self.assertEqual(s.kv_get("ns", "b")["model_id"], "m")
        self.assertEqual(set(s.kv_list("ns")), {"a", "b"})
        s.kv_put("ns", "a", {"x": 9})
        self.assertEqual(s.kv_get("ns", "a"), {"x": 9})
        s.kv_delete("ns", "a")
        self.assertIsNone(s.kv_get("ns", "a"))
        self.assertEqual(s.kv_get("other", "a"), {"y": 2})

    def test_calibration(self):
        s = self.store
        s.calibration_put(CalibrationCell(task_id="t1", model_id="m1", correct=True, answer_key="A"))
        s.calibration_put(CalibrationCell(task_id="t1", model_id="m2"))
        s.calibration_put(CalibrationCell(task_id="t1", model_id="m2", correct=True))
        m = s.calibration_matrix()
        self.assertEqual(set(m["t1"]), {"m1", "m2"})
        self.assertTrue(m["t1"]["m2"].correct)
        self.assertEqual(m["t1"]["m1"].answer_key, "A")
        s.calibration_clear()
        self.assertEqual(s.calibration_matrix(), {})

    def test_claims(self):
        s = self.store
        s.claims_put(ClaimRecord(id="a", model_id="m1", project="p1", text="x"))
        s.claims_put(ClaimRecord(id="b", model_id="m2", project="p1", label="true", labelled_by="evidence"))
        s.claims_put(ClaimRecord(id="c", model_id="m1", project="p2"))
        self.assertEqual([c.id for c in s.claims_list()], ["a", "b", "c"])
        self.assertEqual([c.id for c in s.claims_list(model_id="m1")], ["a", "c"])
        self.assertEqual([c.id for c in s.claims_list(project="p1", model_id="m1")], ["a"])
        self.assertEqual([c.id for c in s.claims_list(labelled_only=True)], ["b"])
        s.claim_label("a", "false", "evidence")
        self.assertEqual([c.id for c in s.claims_list(labelled_only=True)], ["a", "b"])
        got = s.claims_list(model_id="m1")[0]
        self.assertEqual((got.label, got.labelled_by, got.text), ("false", "evidence", "x"))
        s.claim_label("nope", "true", "evidence")

    def test_corrections(self):
        s = self.store
        s.corrections_put(Correction(id="x", project="p1", model_id="m1", lesson="l"))
        s.corrections_put(Correction(id="y", project="p2", model_id="m1"))
        s.corrections_put(Correction(id="z", project="p1", model_id="m2"))
        self.assertEqual(len(s.corrections_list()), 3)
        self.assertEqual([c.id for c in s.corrections_list(project="p1")], ["x", "z"])
        self.assertEqual([c.id for c in s.corrections_list(project="p1", model_id="m1")], ["x"])
        self.assertEqual(s.corrections_list(model_id="m1")[0].lesson, "l")

    def test_behaviour(self):
        s = self.store
        self.assertEqual(s.behaviour_get("m"), BehaviourStats(model_id="m"))
        s.behaviour_put(BehaviourStats(model_id="m", runs=3, persuaded=1))
        got = s.behaviour_get("m")
        self.assertEqual((got.runs, got.persuaded), (3, 1))

    def test_events_for_run(self):
        s = self.store
        s.append_event("r1", "a")
        s.append_event("r2", "b")
        s.append_event("r1", "c")
        self.assertEqual([e.type for e in s.events_for_run("r1")], ["a", "c"])
        self.assertEqual(s.events_for_run("none"), [])

    def test_recent_lineups(self):
        s = self.store
        for i in range(3):
            rec = LineupRecord(seats=[
                SeatAssignment(seat_no=2, model_id=f"b{i}"),
                SeatAssignment(seat_no=1, model_id=f"a{i}"),
            ])
            s.put_json("lineups", f"r{i}", rec)
        s.put_json("lineups", "junk", [1, 2])
        self.assertEqual(s.recent_lineups(2), [["a2", "b2"], ["a1", "b1"]])
        self.assertEqual(len(s.recent_lineups()), 3)

    def test_old_database_opens(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "old.db"
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, task TEXT NOT NULL DEFAULT '')")
            conn.commit()
            conn.close()
            s = Store(path)
            try:
                s.kv_put("n", "k", {"a": 1})
                self.assertEqual(s.kv_get("n", "k"), {"a": 1})
            finally:
                s.close()


class TestFile(unittest.TestCase):
    def test_wal_persist_and_seq_continues(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "db" / "council.db"
            s = Store(path)
            try:
                self.assertEqual(s._one("PRAGMA journal_mode")[0].lower(), "wal")
                s.create_run("r1", "t", str(tmp), "deep", "INTAKE")
                first = s.append_event("r1", et.RUN_CREATED, {"task": "t"})
                s.cache_put("k", CallResult(call_id="c", ok=True))
            finally:
                s.close()
            self.assertTrue(path.exists())

            s2 = Store(str(path))
            try:
                self.assertEqual(s2.get_run("r1")["mode"], "deep")
                self.assertEqual(s2.events_since("r1", 0), [first])
                self.assertGreater(s2.append_event("r1", et.RUN_COMPLETED, {}).seq, first.seq)
                self.assertTrue(s2.cache_get("k").ok)
            finally:
                s2.close()

    def test_memory_is_not_wal(self):
        s = Store()
        try:
            self.assertTrue(s.is_memory)
            self.assertEqual(s._one("PRAGMA journal_mode")[0].lower(), "memory")
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
