"""UiBridge against a real event log from the box (docs/ui_ref/real_run_events.jsonl):
one finished 3-seat run and one 6-seat run that was still going when the log was cut.

The log cuts every line at 3000 characters, so two lines of the 6-seat run (the router's) are
not whole JSON. load_runs() rebuilds what the bridge reads of them from the part that is there.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from council.api.ui_bridge import UiBridge, epoch, needed, table_snapshot

LOG = Path(__file__).resolve().parent.parent / "docs" / "ui_ref" / "real_run_events.jsonl"
RUN_3 = "run_e96b8af78000"  # 3 seats, finished, agreed in round 0
RUN_6 = "run_0f4e1e52625e"  # 6 seats, three models already in memory, cut in round 1
DONE = ("ready", "failed", "dropped")

_HEAD = re.compile(r'^\{"run_id": "([^"]+)", "seq": (\d+), "ts": "([^"]+)", "type": "([^"]+)", "payload": ')
_MODEL = re.compile(r'\{"model_id": "[^"{}]+", "display": "[^"{}]*"[^{}]*\}')


def _mend(line: str) -> dict | None:
    """A line the log cut short: the envelope, and the whole objects of its payload."""
    head = _HEAD.match(line)
    if head is None:
        return None
    run_id, seq, ts, type_ = head.groups()
    payload: dict = {}
    if type_ == "router.lineup_selected":
        seats = re.search(r'"seats": (\[.*?\])', line)
        payload["lineup"] = {"seats": json.loads(seats.group(1)) if seats else []}
        tail = line.split('"models": ', 1)
        payload["models"] = [json.loads(m) for m in _MODEL.findall(tail[1])] if len(tail) > 1 else []
    elif type_ == "router.candidates_scored":
        payload["candidates"] = [json.loads(m) for m in _MODEL.findall(line)]
    return {"run_id": run_id, "seq": int(seq), "ts": ts, "type": type_, "payload": payload}


def load_runs() -> dict[str, list[dict]]:
    runs: dict[str, list[dict]] = {}
    for line in LOG.read_text(encoding="utf-8").split("\n"):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            event = _mend(line)
        if event:
            runs.setdefault(event["run_id"], []).append(event)
    return runs


def replay(events: list[dict], run_id: str = "d") -> list[dict]:
    bridge = UiBridge(run_id)
    out: list[dict] = []
    for event in events:
        out.extend(bridge.feed(event))
    return out


def statuses_until(out: list[dict], stop: int) -> dict[str, str]:
    seen: dict[str, str] = {}
    for e in out[:stop]:
        if e["type"] == "seat.status":
            seen[e["seatId"]] = e["status"]
    return seen


class RealRunBase(unittest.TestCase):
    RUN = ""
    engine: list[dict]
    out: list[dict]

    @classmethod
    def setUpClass(cls) -> None:
        if cls is RealRunBase:
            raise unittest.SkipTest("base class")
        cls.engine = load_runs()[cls.RUN]
        cls.out = replay(cls.engine, cls.RUN)

    def by(self, type_: str) -> list[dict]:
        return [e for e in self.out if e["type"] == type_]

    def created(self) -> dict:
        return self.by("debate.created")[-1]

    def seat_ids(self) -> list[str]:
        return [s["id"] for s in self.created()["seats"]]

    # ---- envelope

    def test_envelope_and_time(self) -> None:
        self.assertEqual([e["seq"] for e in self.out], list(range(1, len(self.out) + 1)))
        for a, b in zip(self.out, self.out[1:]):
            self.assertLessEqual(a["at"], b["at"])
            self.assertLessEqual(a["clock"], b["clock"])
        # the log's ts is an ISO string: `at` must still move (it once stayed 0 for a real run)
        span_ms = (epoch(self.engine[-1]["ts"]) - epoch(self.engine[0]["ts"])) * 1000
        self.assertGreater(span_ms, 60000)
        self.assertAlmostEqual(self.out[-1]["at"], span_ms, delta=5)
        self.assertGreater(self.out[-1]["clock"], 30000)
        self.assertLess(self.out[-1]["clock"], self.out[-1]["at"])  # loading is not debate time

    # ---- a. seats are announced at once and load one by one

    def test_created_comes_with_the_lineup(self) -> None:
        lineup_ts = next(e["ts"] for e in self.engine if e["type"] == "router.lineup_selected")
        first = self.out[0]
        self.assertEqual(first["type"], "debate.created")
        self.assertAlmostEqual(first["at"], (epoch(lineup_ts) - epoch(self.engine[0]["ts"])) * 1000, delta=2)
        self.assertLess(first["at"], 100)
        for created in self.by("debate.created"):  # sent again only with more to say; seats stay
            self.assertEqual([s["id"] for s in created["seats"]], [s["id"] for s in first["seats"]])
            self.assertEqual(created["question"], self.engine[0]["payload"]["task"])
        self.assertGreater(self.created()["limitMs"], 0)  # effort.planned came after the lineup

    def test_names(self) -> None:
        for seat in self.created()["seats"]:
            self.assertTrue(seat["shortName"] and len(seat["shortName"]) <= 7)
            self.assertNotEqual(seat["modelName"], "")
            self.assertTrue(seat.get("role"))
        self.assertEqual([s["index"] for s in self.created()["seats"]], list(range(len(self.seat_ids()))))

    def test_status_follows_the_model_events_in_real_time(self) -> None:
        t0 = epoch(self.engine[0]["ts"])
        seat_of = {s["model_id"]: f"s{s['seat_no']}"
                   for e in self.engine if e["type"] == "router.lineup_selected"
                   for s in e["payload"]["lineup"]["seats"]}
        want = []
        for e in self.engine:
            status = {"model.loading": "loading", "model.loaded": "ready"}.get(e["type"])
            sid = seat_of.get(e["payload"].get("model_id")) if status else None
            if sid:  # a model that holds no seat (the clerk) gives no seat.status
                want.append((sid, status, int(round((epoch(e["ts"]) - t0) * 1000))))
        got = [(e["seatId"], e["status"], e["at"]) for e in self.by("seat.status")]
        self.assertTrue(want)
        self.assertEqual(got[:len(want)], want)
        loading_at = [at for _, status, at in got if status == "loading"]
        self.assertEqual(len(set(loading_at)), len(loading_at))  # one by one, not all at one instant
        for e in self.by("seat.status"):
            self.assertIn(e["seatId"], self.seat_ids())

    # ---- b. every seat is settled before anyone speaks

    def test_every_seat_is_ready_before_the_first_turn(self) -> None:
        first_turn = next(i for i, e in enumerate(self.out) if e["type"] == "turn.started")
        seen = statuses_until(self.out, first_turn)
        self.assertEqual(sorted(seen), sorted(self.seat_ids()))
        for sid in self.seat_ids():
            self.assertEqual(seen[sid], "ready", sid)
        end = statuses_until(self.out, len(self.out))
        self.assertTrue(all(status in DONE for status in end.values()))

    # ---- c. tallies

    def test_tallies_match_the_engine(self) -> None:
        engine = [e["payload"] for e in self.engine if e["type"] == "table.tally"]
        tallies = self.by("tally.posted")
        self.assertEqual(len(tallies), len(engine))  # round.completed adds no second one
        for ui, eng in zip(tallies, engine):
            self.assertEqual((ui["round"], ui["seats"], ui["needed"], ui["agree"], ui["reached"], ui["leading"]),
                             (eng["round"], eng["seats"], eng["needed"], eng["agree"], eng["reached"], eng["leading"]))
            self.assertEqual(ui["seats"], len(self.seat_ids()))  # nobody was dropped in these runs
            self.assertEqual(ui["needed"], needed(ui["seats"]))
            voted = [sid for g in ui["groups"] for sid in g["seatIds"]]
            self.assertEqual(len(voted), len(set(voted)))  # a seat is in one group or none
            self.assertTrue(set(voted) <= set(self.seat_ids()))
            self.assertEqual(ui["agree"], len(next(g for g in ui["groups"] if g["answerId"] == ui["leading"])["seatIds"]))

    # ---- turns

    def test_turns(self) -> None:
        started = {e["turnId"]: e for e in self.by("turn.started")}
        self.assertEqual(len(started), len(self.by("turn.started")))  # no turn opened twice
        messages = [e["payload"] for e in self.engine if e["type"] == "msg.started"]
        self.assertEqual(list(started)[:len(messages)], [m["turn_id"] for m in messages])
        for m in messages:  # gateway calls (cards, clerk, seat_no null) are not turns
            self.assertEqual(started[m["turn_id"]]["seatId"], f"s{m['seat_no']}")
        ended = {e["turnId"]: e for e in self.by("turn.ended")}
        self.assertEqual(len(ended), len(self.by("turn.ended")))
        for e in self.engine:
            if e["type"] == "msg.ended":  # the member's own text, not the gateway's raw completion
                self.assertEqual(ended[e["payload"]["turn_id"]]["text"], e["payload"]["text"])
        cards = [e["payload"] for e in self.engine if e["type"] == "msg.card"]
        notes = self.by("summary.posted")
        self.assertEqual([n["turnId"] for n in notes], [c["turn_id"] for c in cards])
        self.assertTrue(all(len(n["text"]) <= 55 for n in notes))
        lies = self.by("lie.posted")  # a reading with no score is never shown
        self.assertEqual(len(lies), sum(1 for e in self.engine
                                        if e["type"] == "msg.lie" and e["payload"]["score"] is not None))


class ThreeSeatRunTest(RealRunBase):
    RUN = RUN_3

    def test_seats(self) -> None:
        self.assertEqual(self.seat_ids(), ["s0", "s1", "s2"])
        self.assertEqual([s["modelName"] for s in self.created()["seats"]],
                         ["Gemma 4 12B", "Qwen3 14B", "Falcon3 10B"])
        self.assertEqual([s["shortName"] for s in self.created()["seats"]], ["Gemma", "Qwen3", "Falcon3"])
        # four models were loaded (the fourth is the clerk): three seats, six status events
        self.assertEqual([(e["seatId"], e["status"]) for e in self.by("seat.status")],
                         [("s0", "loading"), ("s0", "ready"), ("s1", "loading"), ("s1", "ready"),
                          ("s2", "loading"), ("s2", "ready")])

    def test_stream_ends_with_the_answer(self) -> None:  # d.
        self.assertEqual([e["type"] for e in self.out[-2:]], ["answer.released", "phase.changed"])
        released = self.out[-2]
        self.assertEqual((released["outcome"], released["tallyRound"], released["rounds"]), ("agreed", 0, 1))
        self.assertEqual(released["dissentTurnIds"], [])
        self.assertEqual(len(self.by("answer.released")), 1)
        answer = [e for e in self.by("turn.started") if e["kind"] == "answer"]
        self.assertEqual(len(answer), 1)  # the writer's streamed turn is the answer: no second one
        self.assertEqual(released["turnId"], answer[0]["turnId"])
        text = next(e["text"] for e in self.by("turn.ended") if e["turnId"] == released["turnId"])
        self.assertEqual(text, self.engine[-1]["payload"]["final_text"])
        self.assertEqual([e["phase"] for e in self.by("phase.changed")],
                         ["spooling", "debate", "vote", "writing", "released"])
        self.assertGreater(released["elapsedMs"], 40000)

    def test_table_at_the_end(self) -> None:
        table = table_snapshot(self.out)
        self.assertEqual(sorted(table), ["s0", "s1", "s2"])
        for seat in table.values():
            self.assertFalse(seat["thinking"])
            self.assertEqual(seat["mark"], "agrees")
            self.assertTrue(seat["note"])


class SixSeatRunTest(RealRunBase):
    RUN = RUN_6

    def test_seats(self) -> None:
        self.assertEqual(self.seat_ids(), ["s0", "s1", "s2", "s3", "s4", "s5"])
        self.assertEqual([s["modelName"] for s in self.created()["seats"]],
                         ["gpt-oss 20B", "DeepSeek R1 14B", "Phi-4 14B", "Gemma 4 12B", "Qwen3 14B", "Falcon3 10B"])

    def test_models_already_in_memory_become_ready(self) -> None:
        # only three models were loaded for this run; the other three seats got no model.* event
        loaded = {e["payload"]["model_id"] for e in self.engine if e["type"] == "model.loaded"}
        self.assertEqual(len(loaded), 3)
        ready = {e["seatId"] for e in self.by("seat.status") if e["status"] == "ready"}
        self.assertEqual(ready, set(self.seat_ids()))
        self.assertEqual([e["seatId"] for e in self.by("seat.status") if e["status"] == "loading"],
                         ["s0", "s1", "s2"])

    def test_a_run_that_is_still_going_is_not_released(self) -> None:  # d.
        self.assertEqual(self.by("answer.released"), [])
        self.assertEqual(self.out[-1]["type"], "seat.thinking")
        self.assertEqual([e["round"] for e in self.by("round.started")], [0, 1])
        tally = self.by("tally.posted")[0]
        self.assertEqual((tally["agree"], tally["seats"], tally["needed"], tally["reached"]), (1, 6, 5, False))
        self.assertEqual(len(tally["groups"]), 6)
        open_turns = {e["turnId"] for e in self.by("turn.started")} - {e["turnId"] for e in self.by("turn.ended")}
        self.assertEqual(open_turns, set())  # all twelve messages were written
        waiting = [sid for sid, seat in table_snapshot(self.out).items() if seat["thinking"]]
        self.assertEqual(sorted(waiting), ["s0", "s1", "s3", "s4", "s5"])  # round-1 cards still to come

    def test_stopping_it_closes_everything(self) -> None:
        bridge = UiBridge(self.RUN)
        for event in self.engine:
            bridge.feed(event)
        self.assertFalse(bridge.released)
        out = bridge.feed({"seq": 0, "ts": self.engine[-1]["ts"], "type": "run.cancelled",
                           "payload": {"reason": "stopped"}})
        self.assertTrue(bridge.released)
        self.assertEqual([e["type"] for e in out[-2:]], ["answer.released", "phase.changed"])
        self.assertEqual(out[-2]["outcome"], "stopped")
        self.assertEqual(bridge.feed({"seq": 0, "ts": self.engine[-1]["ts"], "type": "run.cancelled",
                                      "payload": {}}), [])


if __name__ == "__main__":
    unittest.main()
