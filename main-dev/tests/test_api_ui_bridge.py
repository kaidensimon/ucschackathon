"""UiBridge: engine events in, the partner UI's DebateEvent stream out."""

from __future__ import annotations

import re
import unittest

from council.api.ui_bridge import UiBridge, clip, epoch, needed, seat_id, short_name, table_snapshot

BASE_KEYS = {"v", "seq", "debateId", "at", "clock", "type"}
MODELS = [("qwen", "Qwen 2.5 Coder"), ("llama", "Llama 3.2"), ("phi", "Phi-4 Mini Reasoning")]
LONG_NOTE = "Use the queue because it keeps the workers apart and is far simpler to test"


class Script:
    """Builds engine events with rising seq and ts (0.1 s apart)."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def add(self, type_: str, **payload) -> None:
        n = len(self.events)
        self.events.append({"seq": n + 1, "ts": 1000.0 + n * 0.1, "type": type_, "payload": payload})


def run(bridge: UiBridge, events: list[dict]) -> list[dict]:
    out: list[dict] = []
    for event in events:
        out.extend(bridge.feed(event))
    return out


def setup_events(s: Script) -> None:
    s.add("run.created", task="Queue or lock?", state="INTAKE")
    s.add("router.lineup_selected",
          lineup={"seats": [{"seat_no": i + 1, "model_id": m, "lens": "skeptic" if i == 0 else None}
                            for i, (m, _) in enumerate(MODELS)]},
          models=[{"model_id": m, "display": d} for m, d in MODELS])
    for i, (m, d) in enumerate(MODELS):
        s.add("seat.assigned", seat_no=i + 1, model_id=m, display=d, lens="skeptic" if i == 0 else None)


def open_script() -> list[dict]:
    s = Script()
    setup_events(s)
    s.add("model.loaded", model_id="qwen")
    s.add("run.state_changed", from_state="CONVENING", to_state="DELIBERATING")
    for no in (1, 2, 3):  # round 0: all three write at the same time
        s.add("msg.started", turn_id=f"r0s{no}", seat_no=no, model_id=MODELS[no - 1][0], round=0,
              kind="position", to="all")
    s.add("msg.thinking", turn_id="r0s1", seat_no=1)
    for no in (1, 2, 3):
        s.add("msg.delta", turn_id=f"r0s{no}", text="I say ")
        s.add("msg.delta", turn_id=f"r0s{no}", text="queue.")
    for no in (1, 2, 3):
        s.add("msg.ended", turn_id=f"r0s{no}", seat_no=no, text="I say queue.")
        s.add("msg.lie", turn_id=f"r0s{no}", seat_no=no, score=0.9 if no < 3 else 0.2,
              level="ok" if no < 3 else "flag", reasons=[] if no < 3 else ["no source"])
        s.add("msg.card", turn_id=f"r0s{no}", seat_no=no,
              card={"note": LONG_NOTE if no == 1 else "Queue.", "to": "all", "stance": "queue",
                    "backs": "new", "confidence": 0.7, "changed": False})
    s.add("table.tally", round=0,
          groups=[{"answer_id": "A1", "statement": "queue", "seat_ids": [1, 2]},
                  {"answer_id": "A2", "statement": "lock", "seat_ids": [3]}],
          leading="A1", agree=2, seats=3, needed=3, reached=False, basis="round-vote")
    # round 1: seat 3 replies; it was announced to all, its card says it spoke to seat 1
    s.add("msg.started", turn_id="r1s3", seat_no=3, model_id="phi", round=1, kind="reply", to="all")
    s.add("msg.delta", turn_id="r1s3", text="Fine, queue.")
    s.add("msg.ended", turn_id="r1s3", seat_no=3, text="Fine, queue.")
    s.add("msg.card", turn_id="r1s3", seat_no=3,
          card={"note": "Moved to queue.", "to": [1], "stance": "queue", "backs": "A1",
                "confidence": 0.8, "changed": True})
    s.add("table.tally", round=1,
          groups=[{"answer_id": "A1", "statement": "queue", "seat_ids": ["s1", "s2", "s3"]}],
          leading="A1", agree=3, seats=3, needed=3, reached=True, basis="round-vote")
    s.add("round.completed", round=1, options=[{"id": "o1", "summary": "queue", "holders": [1, 2, 3]}],
          converged=True)
    s.add("decision.final", decision={"outcome": "consensus", "final_text": "Use a queue.", "rounds_run": 2})
    s.add("run.completed", outcome="consensus", final_text="Use a queue.")
    return s.events


OPEN_EXPECTED = (
    # seat 1's model reports loaded; the other two are ready when the debate begins
    ["debate.created", "phase.changed", "seat.status", "seat.status", "seat.status", "phase.changed",
     "round.started"]
    + ["turn.started", "seat.thinking"] * 3
    + ["turn.delta"] * 6
    + ["turn.ended", "lie.posted", "summary.posted", "seat.thinking"] * 3
    + ["tally.posted", "round.started", "turn.started", "seat.thinking", "turn.delta", "turn.ended",
       "summary.posted", "turn.addressed", "seat.thinking", "tally.posted",
       "turn.started", "turn.ended", "answer.released", "phase.changed"]
)


class OpenProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.out = run(UiBridge("d1", limit_ms=60000), open_script())

    def by_type(self, type_: str) -> list[dict]:
        return [e for e in self.out if e["type"] == type_]

    def test_types_in_order(self) -> None:
        self.assertEqual([e["type"] for e in self.out], OPEN_EXPECTED)

    def test_envelope(self) -> None:
        self.assertEqual([e["seq"] for e in self.out], list(range(1, len(self.out) + 1)))
        for a, b in zip(self.out, self.out[1:]):
            self.assertLessEqual(a["at"], b["at"])
            self.assertLessEqual(a["clock"], b["clock"])
        for e in self.out:
            self.assertTrue(BASE_KEYS <= set(e))
            self.assertEqual((e["v"], e["debateId"]), (1, "d1"))

    def test_keys_are_camel_case(self) -> None:
        def walk(value) -> None:
            if isinstance(value, dict):
                for key, inner in value.items():
                    self.assertRegex(key, r"^[a-z][A-Za-z0-9]*$")
                    walk(inner)
            elif isinstance(value, list):
                for inner in value:
                    walk(inner)

        walk(self.out)

    def test_body_fields_match_events_ts(self) -> None:
        want = {
            "debate.created": {"question", "files", "seats", "limitMs"},
            "turn.started": {"turnId", "seatId", "round", "kind", "to"},
            "turn.delta": {"turnId", "text"},
            "turn.ended": {"turnId", "text", "citations"},
            "summary.posted": {"summaryId", "seatId", "turnId", "text", "source"},
            "tally.posted": {"round", "basis", "groups", "leading", "agree", "seats", "needed", "reached"},
            "answer.released": {"outcome", "turnId", "tallyRound", "rounds", "elapsedMs", "dissentTurnIds"},
            "lie.posted": {"turnId", "seatId", "score", "level", "reasons"},
            "seat.thinking": {"seatId", "turnId", "on"},
            "turn.addressed": {"turnId", "to"},
        }
        for e in self.out:
            if e["type"] in want:
                self.assertEqual(set(e) - BASE_KEYS, want[e["type"]], e["type"])

    def test_created_and_seats(self) -> None:
        created = self.out[0]
        self.assertEqual(created["question"], "Queue or lock?")
        self.assertEqual(created["limitMs"], 60000)
        self.assertEqual([s["id"] for s in created["seats"]], ["s1", "s2", "s3"])
        self.assertEqual([s["index"] for s in created["seats"]], [0, 1, 2])
        self.assertEqual([s["shortName"] for s in created["seats"]], ["Qwen", "Llama", "Phi"])
        self.assertEqual(created["seats"][0]["role"], "skeptic")
        self.assertNotIn("role", created["seats"][1])
        status = self.by_type("seat.status")[0]
        self.assertEqual((status["seatId"], status["status"]), ("s1", "ready"))
        self.assertEqual([e["phase"] for e in self.by_type("phase.changed")], ["spooling", "debate", "released"])

    def test_note_is_at_most_55(self) -> None:
        notes = self.by_type("summary.posted")
        self.assertEqual(len(notes), 4)
        for e in notes:
            self.assertLessEqual(len(e["text"]), 55)
            self.assertEqual(e["source"], "self")
        self.assertTrue(notes[0]["text"].startswith("Use the queue"))
        self.assertEqual((notes[0]["seatId"], notes[0]["turnId"]), ("s1", "r0s1"))

    def test_addressing(self) -> None:
        reply = [e for e in self.by_type("turn.started") if e["turnId"] == "r1s3"][0]
        self.assertEqual((reply["to"], reply["kind"], reply["round"]), ("all", "reply", 1))
        addressed = self.by_type("turn.addressed")
        self.assertEqual(len(addressed), 1)  # round 0 cards said "all", as announced
        self.assertEqual((addressed[0]["turnId"], addressed[0]["to"]), ("r1s3", ["s1"]))

    def test_lie_and_tally(self) -> None:
        lie = self.by_type("lie.posted")[2]
        self.assertEqual((lie["seatId"], lie["score"], lie["level"], lie["reasons"]), ("s3", 0.2, "flag", ["no source"]))
        first, last = self.by_type("tally.posted")  # round.completed for round 1 added no third
        self.assertEqual(first["groups"][0], {"answerId": "A1", "statement": "queue", "seatIds": ["s1", "s2"]})
        self.assertFalse(first["reached"])
        self.assertTrue(last["reached"])
        self.assertEqual(last["groups"][0]["seatIds"], ["s1", "s2", "s3"])

    def test_answer(self) -> None:
        released = self.by_type("answer.released")[0]
        self.assertEqual((released["outcome"], released["turnId"], released["tallyRound"], released["rounds"]),
                         ("agreed", "answer", 1, 2))
        started = [e for e in self.by_type("turn.started") if e["turnId"] == "answer"][0]
        self.assertEqual(started["kind"], "answer")
        ended = [e for e in self.by_type("turn.ended") if e["turnId"] == "answer"][0]
        self.assertEqual(ended["text"], "Use a queue.")
        self.assertEqual(released["elapsedMs"], released["clock"])
        self.assertGreater(released["clock"], 0)

    def test_table_snapshot(self) -> None:
        cut = next(i for i, e in enumerate(self.out) if e["type"] == "turn.delta")
        early = table_snapshot(self.out[:cut])  # all three writing, no card yet
        self.assertEqual(set(early), {"s1", "s2", "s3"})
        for seat in early.values():
            self.assertEqual(seat, {"note": None, "thinking": True, "lie": None, "mark": None})
        cut = next(i for i, e in enumerate(self.out) if e["type"] == "tally.posted")
        mid = table_snapshot(self.out[: cut + 1])
        self.assertEqual(mid["s3"], {"note": "Queue.", "thinking": False,
                                     "lie": {"score": 0.2, "level": "flag"}, "mark": "differs"})
        self.assertEqual(mid["s1"]["mark"], "agrees")
        end = table_snapshot(self.out)
        self.assertEqual(end["s3"]["note"], "Moved to queue.")
        self.assertEqual([end[s]["mark"] for s in ("s1", "s2", "s3")], ["agrees"] * 3)
        self.assertFalse(any(seat["thinking"] for seat in end.values()))


class OpenProtocolEdgesTest(unittest.TestCase):
    def test_failed_message_stops_thinking_and_tally_clears_stragglers(self) -> None:
        s = Script()
        s.add("msg.started", turn_id="a", seat_no=1, model_id="qwen", round=0, kind="position", to="all")
        s.add("msg.ended", turn_id="a", seat_no=1, text="", error="timeout")
        s.add("msg.started", turn_id="b", seat_no=1, model_id="qwen", round=1, kind="reply", to=[2])
        s.add("msg.ended", turn_id="b", seat_no=1, text="ok")  # its card never arrives
        s.add("table.tally", round=1, groups=[{"answer_id": "A1", "statement": "x", "seat_ids": [1]}])
        out = run(UiBridge("d"), s.events)
        self.assertEqual(out[0]["type"], "debate.created")  # made from the first message
        self.assertEqual(out[0]["seats"][0]["id"], "s1")
        self.assertEqual(out[1], {**out[1], "type": "seat.status", "seatId": "s1", "status": "ready"})
        self.assertEqual(out[2], {**out[2], "type": "phase.changed", "phase": "debate"})
        ended = [e for e in out if e["type"] == "turn.ended"]
        self.assertEqual(ended[0]["error"], "timeout")
        self.assertNotIn("error", ended[1])
        self.assertEqual([e["on"] for e in out if e["type"] == "seat.thinking"], [True, False, True, False])
        tally = out[-1]
        self.assertEqual((tally["type"], tally["leading"], tally["agree"], tally["basis"]),
                         ("tally.posted", "A1", 1, "round-vote"))
        started = [e for e in out if e["type"] == "turn.started"]
        self.assertEqual(started[1]["to"], ["s2"])

    def test_unknown_event_and_late_delta_give_nothing(self) -> None:
        bridge = UiBridge("d")
        self.assertEqual(bridge.feed({"seq": 1, "ts": 1.0, "type": "telemetry.tick", "payload": {}}), [])
        self.assertEqual(bridge.feed({"seq": 2, "ts": 1.1, "type": "msg.delta",
                                      "payload": {"turn_id": "nope", "text": "x"}}), [])


class FallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        s = Script()
        s.add("run.created", task="Pick a cache.", state="INTAKE")
        s.add("run.state_changed", from_state="INTAKE", to_state="PROFILING")
        s.add("model.loading", model_id="qwen")
        s.add("model.loading", model_id="clerk-model")  # holds no seat: dropped
        s.add("router.lineup_selected",
              lineup={"seats": [{"seat_no": i + 1, "model_id": m} for i, (m, _) in enumerate(MODELS)]},
              models=[{"model_id": m, "display": d} for m, d in MODELS])
        s.add("model.loaded", model_id="qwen")
        s.add("model.failed", model_id="phi", error="out of memory")
        s.add("run.state_changed", from_state="CONVENING", to_state="DELIBERATING")
        s.add("round.started", round=0)
        s.add("turn.started", call_id="c1", seat_no=1, round=0, purpose="draft")
        s.add("turn.started", call_id="clerk", seat_no=None, round=0, purpose="cluster")
        s.add("turn.delta", call_id="c1", seat_no=1, text='{"answer"')
        s.add("turn.delta", call_id="clerk", text="x")
        s.add("turn.completed", call_id="c1", seat_no=1, round=0, content='{"answer": "LRU"}',
              parsed={"answer": "LRU", "summary": "LRU is enough here, " + "really " * 10})
        s.add("turn.started", call_id="c2", seat_no=2, round=0)
        s.add("turn.timeout", call_id="c2", seat_no=2, will_retry=True)
        s.add("turn.started", call_id="c2", seat_no=2, round=0, attempt=2)
        s.add("turn.completed", call_id="c2", seat_no=2, round=0, content="LFU")
        s.add("round.completed", round=0, leading_option_id="o1", converged=False,
              options=[{"id": "o1", "summary": "LRU", "holders": [1]}, {"id": "o2", "summary": "LFU", "holders": [2]}])
        s.add("round.started", round=1)
        s.add("turn.started", call_id="c3", seat_no=2, round=1)
        s.add("turn.completed", call_id="c3", seat_no=2, round=1, content="still LFU")
        s.add("run.state_changed", from_state="DELIBERATING", to_state="DECIDED")
        s.add("decision.final", decision={"outcome": "chair", "final_text": "LRU.", "rounds_run": 2})
        s.add("run.state_changed", from_state="DECIDED", to_state="DONE")
        s.add("run.completed", outcome="chair", final_text="LRU.")
        self.out = run(UiBridge("d2"), s.events)

    def test_types_in_order(self) -> None:
        self.assertEqual([e["type"] for e in self.out], [
            "debate.created", "phase.changed", "seat.status", "seat.status", "seat.status", "seat.status",
            "phase.changed", "round.started",
            "turn.started", "turn.delta", "turn.ended", "summary.posted",
            "turn.started", "turn.ended", "turn.started", "turn.ended",
            "tally.posted", "round.started", "turn.started", "turn.ended", "phase.changed",
            "turn.started", "turn.ended", "answer.released", "phase.changed",
        ])
        self.assertEqual([e["seq"] for e in self.out], list(range(1, len(self.out) + 1)))

    def test_seats_status_phases(self) -> None:
        self.assertEqual(len(self.out[0]["seats"]), 3)
        status = [(e["seatId"], e["status"], e.get("reason")) for e in self.out if e["type"] == "seat.status"]
        self.assertEqual(status, [("s1", "loading", None), ("s1", "ready", None), ("s3", "failed", "out of memory"),
                                  ("s2", "ready", None)])  # no model event for seat 2: ready as the debate begins
        self.assertEqual([e["phase"] for e in self.out if e["type"] == "phase.changed"],
                         ["spooling", "debate", "vote", "released"])

    def test_turns(self) -> None:
        started = [e for e in self.out if e["type"] == "turn.started"]
        self.assertEqual([e["turnId"] for e in started], ["c1", "c2", "c2#2", "c3", "answer"])
        self.assertEqual([e["kind"] for e in started], ["position", "position", "position", "reply", "answer"])
        self.assertTrue(all(e["to"] == "all" for e in started))
        ended = {e["turnId"]: e for e in self.out if e["type"] == "turn.ended"}
        self.assertEqual(ended["c1"]["text"], "LRU")
        self.assertEqual(ended["c2"]["error"], "timed out")
        self.assertEqual(ended["c2#2"]["text"], "LFU")
        note = [e for e in self.out if e["type"] == "summary.posted"][0]
        self.assertEqual(note["source"], "engine")
        self.assertLessEqual(len(note["text"]), 55)

    def test_tally_and_release(self) -> None:
        tally = [e for e in self.out if e["type"] == "tally.posted"][0]
        self.assertEqual(tally["groups"], [{"answerId": "o1", "statement": "LRU", "seatIds": ["s1"]},
                                           {"answerId": "o2", "statement": "LFU", "seatIds": ["s2"]}])
        self.assertEqual((tally["leading"], tally["agree"], tally["seats"], tally["needed"], tally["reached"]),
                         ("o1", 1, 2, 2, False))  # seat 3 failed: two seats are in the debate
        released = [e for e in self.out if e["type"] == "answer.released"][0]
        self.assertEqual((released["outcome"], released["tallyRound"], released["rounds"]), ("no-consensus", 0, 2))
        self.assertEqual(released["dissentTurnIds"], ["c3"])  # seat 2's newest turn

    def test_cancel_is_stopped(self) -> None:
        s = Script()
        setup_events(s)
        s.add("turn.started", call_id="c1", seat_no=1, round=0)
        s.add("run.cancelled", reason="user pressed stop")
        out = run(UiBridge("d3"), s.events)
        self.assertEqual([e["type"] for e in out][-6:], [
            "turn.started", "turn.ended", "turn.started", "turn.ended", "answer.released", "phase.changed"])
        self.assertEqual(out[-2]["outcome"], "stopped")
        self.assertEqual(out[-3]["error"], "user pressed stop")

    def test_pause(self) -> None:
        s = Script()
        setup_events(s)
        s.add("run.state_changed", to_state="DELIBERATING")
        s.add("run.state_changed", to_state="AWAITING_USER")
        s.add("run.state_changed", to_state="DELIBERATING")
        out = run(UiBridge("d4"), s.events)
        self.assertEqual([e["type"] for e in out][-3:], ["phase.changed", "clock.paused", "clock.resumed"])
        self.assertEqual(out[-1]["clock"], out[-2]["clock"])  # frozen while paused


NAMES = {"gemma": "Gemma 4 12B", "qwen": "Qwen3 14B", "falcon": "Falcon3 10B", "phi": "Phi-4 14B",
         "granite": "Granite 4 8B"}


def lineup_event(s: Script, models: list, residents: tuple = ()) -> None:
    s.add("router.lineup_selected",
          lineup={"seats": [{"seat_no": no, "model_id": m, "lens": "skeptic"} for no, m in models]},
          models=[{"model_id": m, "display": NAMES[m], "resident": m in residents} for _, m in models])


def statuses(out: list[dict]) -> list[tuple]:
    return [(e["seatId"], e["status"]) for e in out if e["type"] == "seat.status"]


def last_status(out: list[dict]) -> dict[str, dict]:
    return {e["seatId"]: e for e in out if e["type"] == "seat.status"}


def names_now(out: list[dict]) -> dict[str, str]:
    created = [e for e in out if e["type"] == "debate.created"][-1]
    return {s["id"]: s["modelName"] for s in created["seats"]}


class SeatLoadingTest(unittest.TestCase):
    """seat.status follows the real model events; debate.created comes with the lineup."""

    def start(self, residents: tuple = ()) -> Script:
        s = Script()
        s.add("run.created", task="Queue or lock?")
        s.add("router.candidates_scored", candidates=[{"model_id": m, "display": d} for m, d in NAMES.items()])
        lineup_event(s, [(0, "gemma"), (1, "qwen"), (2, "falcon")], residents)
        return s

    def test_created_at_once_then_one_by_one(self) -> None:
        s = self.start()
        bridge = UiBridge("d")
        first = run(bridge, s.events)
        self.assertEqual([e["type"] for e in first], ["debate.created", "phase.changed"])
        self.assertEqual([x["id"] for x in first[0]["seats"]], ["s0", "s1", "s2"])

        def feed(type_: str, **p) -> list[dict]:
            return bridge.feed({"seq": 0, "ts": 0, "type": type_, "payload": p})

        self.assertEqual(statuses(feed("model.loading", model_id="gemma")), [("s0", "loading")])
        self.assertEqual(statuses(feed("model.loaded", model_id="gemma")), [("s0", "ready")])
        self.assertEqual(feed("model.loaded", model_id="gemma"), [])  # said once
        self.assertEqual(feed("model.loading", model_id="clerk-model"), [])  # holds no seat
        self.assertEqual(feed("model.loaded", model_id="clerk-model"), [])
        self.assertEqual(feed("model.failed", model_id="clerk-model", error="x", replaced_by=None), [])
        self.assertEqual(statuses(feed("model.loading", model_id="qwen")), [("s1", "loading")])
        self.assertEqual(feed("seat.assigned", seat_no=0, model_id="gemma", display="Gemma 4 12B", lens="skeptic"), [])
        out = feed("run.state_changed", to_state="DELIBERATING")  # all seats resident, says the engine
        self.assertEqual(statuses(out), [("s1", "ready"), ("s2", "ready")])
        self.assertEqual(out[-1]["phase"], "debate")

    def test_resident_models_are_ready_at_once(self) -> None:
        out = run(UiBridge("d"), self.start(residents=("gemma", "falcon")).events)
        self.assertEqual(statuses(out), [("s0", "ready"), ("s2", "ready")])

    def test_time_limit_arrives_later(self) -> None:
        s = self.start()
        s.add("effort.planned", deadline_s=90.5)
        s.add("effort.planned", deadline_s=10)
        created = [e for e in run(UiBridge("d"), s.events) if e["type"] == "debate.created"]
        self.assertEqual([e["limitMs"] for e in created], [0, 90500])
        self.assertEqual(created[0]["seats"], created[1]["seats"])

    def test_failed_model_is_replaced(self) -> None:
        s = self.start()
        s.add("model.loading", model_id="gemma")
        s.add("model.loaded", model_id="gemma")
        s.add("model.loading", model_id="qwen")
        s.add("model.failed", model_id="qwen", display="Qwen3 14B", error="llama-server exited (code 1)",
              stage="load", replaced_by="phi")
        s.add("model.loading", model_id="phi")
        s.add("model.loaded", model_id="phi")
        s.add("model.loading", model_id="falcon")
        s.add("model.loaded", model_id="falcon")
        lineup_event(s, [(0, "gemma"), (1, "phi"), (2, "falcon")])  # the final lineup, same numbers
        for no, m in enumerate(("gemma", "phi", "falcon")):
            s.add("seat.assigned", seat_no=no, model_id=m, display=NAMES[m], lens="skeptic",
                  replaces_model_id="qwen" if m == "phi" else None)
        s.add("run.state_changed", to_state="DELIBERATING")
        s.add("msg.started", turn_id="t1", seat_no=1, model_id="phi", round=0, kind="position", to="all")
        out = run(UiBridge("d"), s.events)
        self.assertEqual(statuses(out), [("s0", "loading"), ("s0", "ready"), ("s1", "loading"), ("s1", "loading"),
                                         ("s1", "ready"), ("s2", "loading"), ("s2", "ready")])
        swap = [e for e in out if e["type"] == "seat.status" and e.get("reason")]
        self.assertEqual(len(swap), 1)
        self.assertEqual(swap[0]["reason"], "Qwen3 14B did not load. Phi-4 14B takes the seat.")
        self.assertEqual(names_now(out), {"s0": "Gemma 4 12B", "s1": "Phi-4 14B", "s2": "Falcon3 10B"})
        self.assertEqual(last_status(out)["s1"]["status"], "ready")
        created = [e for e in out if e["type"] == "debate.created"]
        self.assertEqual(len(created), 2)  # the lineup, and the new name; the rest said nothing new
        self.assertLess(created[1]["seq"], swap[0]["seq"])
        first_turn = next(e["seq"] for e in out if e["type"] == "turn.started")
        self.assertTrue(all(e["seq"] < first_turn for e in out if e["type"] == "seat.status"))

    def test_failed_model_with_no_replacement_drops_the_seat(self) -> None:
        s = self.start()
        s.add("model.loading", model_id="gemma")
        s.add("model.loaded", model_id="gemma")
        s.add("model.loading", model_id="qwen")
        s.add("model.failed", model_id="qwen", error="out of\n  memory " + "x" * 400, stage="load", replaced_by=None)
        s.add("model.loading", model_id="falcon")
        s.add("model.loaded", model_id="falcon")
        lineup_event(s, [(0, "gemma"), (1, "falcon")])  # the engine renumbers: falcon is seat 1 now
        s.add("seat.assigned", seat_no=0, model_id="gemma", display="Gemma 4 12B")
        s.add("seat.assigned", seat_no=1, model_id="falcon", display="Falcon3 10B")
        s.add("run.state_changed", to_state="DELIBERATING")
        s.add("round.started", round=0, seats=[0, 1])
        s.add("msg.started", turn_id="t0", seat_no=0, model_id="gemma", round=0, kind="position", to="all")
        s.add("msg.started", turn_id="t1", seat_no=1, model_id="falcon", round=0, kind="position", to=["s0"])
        s.add("msg.ended", turn_id="t1", seat_no=1, text="Lock.")
        s.add("msg.card", turn_id="t1", seat_no=1, card={"note": "Lock.", "to": [0]})
        s.add("msg.lie", turn_id="zz", seat_no=1, score=0.5)
        s.add("chair.started", call_id="chair", seat_no=1)
        s.add("table.tally", round=0, leading="A1", agree=1, seats=2, needed=2, reached=False,
              groups=[{"answer_id": "A1", "statement": "queue", "seat_ids": ["s0"]},
                      {"answer_id": "A2", "statement": "lock", "seat_ids": ["s1", "s1", "s0"]}])
        out = run(UiBridge("d"), s.events)
        self.assertEqual(names_now(out), {"s0": "Gemma 4 12B", "s1": "Qwen3 14B", "s2": "Falcon3 10B"})
        end = last_status(out)
        self.assertEqual({k: v["status"] for k, v in end.items()}, {"s0": "ready", "s1": "failed", "s2": "ready"})
        self.assertTrue(end["s1"]["reason"].startswith("out of memory x"))  # one line, cut
        self.assertLessEqual(len(end["s1"]["reason"]), 140)
        turns = {e["turnId"]: e for e in out if e["type"] == "turn.started"}
        self.assertEqual((turns["t0"]["seatId"], turns["t1"]["seatId"]), ("s0", "s2"))  # engine seat 1 = Falcon3
        self.assertEqual(turns["t1"]["to"], ["s0"])
        self.assertEqual([e["seatId"] for e in out if e["type"] == "summary.posted"], ["s2"])
        self.assertEqual([e["seatId"] for e in out if e["type"] == "lie.posted"], ["s2"])
        self.assertEqual({e["seatId"] for e in out if e["type"] == "seat.thinking"}, {"s0", "s2"})
        tally = [e for e in out if e["type"] == "tally.posted"][0]
        self.assertEqual([g["seatIds"] for g in tally["groups"]], [["s0"], ["s2"]])  # one group per seat
        self.assertEqual((tally["seats"], tally["needed"], tally["agree"]), (2, 2, 1))
        marks = table_snapshot(out)
        self.assertEqual((marks["s0"]["mark"], marks["s1"]["mark"], marks["s2"]["mark"]), ("agrees", None, "differs"))

    def test_seat_without_a_model_event_is_dropped_by_the_new_lineup(self) -> None:
        s = self.start()
        lineup_event(s, [(0, "gemma"), (1, "falcon")])
        out = run(UiBridge("d"), s.events)
        dropped = last_status(out)["s1"]
        self.assertEqual((dropped["status"], dropped["reason"]), ("dropped", "Qwen3 14B was left out of this debate."))
        self.assertEqual(len([e for e in out if e["type"] == "debate.created"]), 1)

    def test_round_zero_swap_and_a_seat_that_stops_answering(self) -> None:
        s = self.start(residents=("gemma", "qwen", "falcon"))
        s.add("run.state_changed", to_state="DELIBERATING")
        s.add("round.started", round=0, seats=[0, 1, 2])
        s.add("msg.started", turn_id="t1", seat_no=1, model_id="qwen", round=0, kind="position", to="all")
        s.add("seat.assigned", seat_no=1, model_id="granite", lens="skeptic", replaces_model_id="qwen")
        s.add("msg.ended", turn_id="t1", seat_no=1, text="", error="invalid_output")
        mid = len(s.events)
        s.add("msg.started", turn_id="t1b", seat_no=1, model_id="granite", round=0, kind="position", to="all")
        s.add("round.started", round=1, seats=[0, 1])
        bridge = UiBridge("d")
        out = run(bridge, s.events[:mid])
        self.assertEqual(names_now(out)["s1"], "Granite 4 8B")
        self.assertEqual((out[-3]["type"], out[-3]["status"], out[-3]["reason"]),
                         ("seat.status", "loading", "Qwen3 14B did not answer. Granite 4 8B takes the seat."))
        self.assertEqual((out[-2]["type"], out[-2]["error"]), ("turn.ended", "invalid_output"))
        out += run(bridge, s.events[mid:])
        end = last_status(out)
        self.assertEqual(end["s1"]["status"], "ready")  # it speaks again
        self.assertEqual((end["s2"]["status"], end["s2"]["reason"]),
                         ("dropped", "Falcon3 10B stopped answering and was left out of the debate."))
        self.assertEqual([e["seq"] for e in out], list(range(1, len(out) + 1)))

    def test_gateway_events_do_not_end_an_open_message(self) -> None:
        s = self.start(residents=("gemma", "qwen", "falcon"))
        s.add("msg.started", turn_id="t0", call_id="t0", seat_no=0, model_id="gemma", round=0, kind="position", to="all")
        s.add("turn.started", call_id="t0", seat_no=None, round=0, attempt=1)
        s.add("turn.delta", call_id="t0", text="Que")
        s.add("turn.timeout", call_id="t0", will_retry=True)
        s.add("turn.started", call_id="t0", seat_no=None, round=0, attempt=2)
        s.add("turn.completed", call_id="t0", seat_no=None, content="<raw> Queue.", parsed={"summary": "raw"})
        s.add("msg.ended", turn_id="t0", seat_no=0, text="Queue.")
        out = run(UiBridge("d"), s.events)
        self.assertEqual([e["type"] for e in out if e["type"].startswith("turn.")],
                         ["turn.started", "turn.delta", "turn.ended"])
        self.assertEqual(out[-1]["text"], "Queue.")
        self.assertNotIn("error", out[-1])
        self.assertEqual([e for e in out if e["type"] == "summary.posted"], [])

    def test_iso_timestamps(self) -> None:
        bridge = UiBridge("d")

        def at(ts: str, type_: str, **p) -> list[dict]:
            return bridge.feed({"seq": 0, "ts": ts, "type": type_, "payload": p})

        at("2026-10-11T18:15:54.273000+00:00", "run.created", task="x")
        out = at("2026-10-11T18:15:56.273000Z", "msg.started", turn_id="t", seat_no=0, round=0, kind="position")
        self.assertEqual({e["at"] for e in out}, {2000})
        out = at("2026-10-11T18:16:00.773000+00:00", "msg.ended", turn_id="t", seat_no=0, text="ok")
        self.assertEqual((out[0]["at"], out[0]["clock"]), (6500, 4500))
        self.assertEqual(epoch(1000.5), 1000.5)
        self.assertEqual(epoch("1000.5"), 1000.5)
        self.assertEqual(epoch("nonsense"), 0.0)
        self.assertEqual(epoch(None), 0.0)
        self.assertEqual(epoch("2026-10-11T18:16:00") - epoch("2026-10-11T18:15:00+00:00"), 60.0)


class HelpersTest(unittest.TestCase):
    def test_helpers(self) -> None:
        self.assertEqual(seat_id(3), "s3")
        self.assertEqual(seat_id("s3"), "s3")
        self.assertEqual(short_name("Qwen 2.5 Coder"), "Qwen")
        self.assertEqual(short_name("deepseek-r1:8b"), "deepsee")
        self.assertLessEqual(len(short_name("SuperLongModelName")), 7)
        self.assertEqual(short_name(""), "seat")
        self.assertEqual(clip("  two\n words "), "two words")
        self.assertEqual(len(clip("x" * 200)), 55)
        self.assertEqual([needed(n) for n in (3, 4, 5, 6, 7)], [3, 4, 4, 5, 6])
        self.assertTrue(re.fullmatch(r"s\d+", seat_id("7")))


class EngineContractTest(unittest.TestCase):
    """UiBridge against the events council.chamber.open_debate really emits."""

    def setUp(self) -> None:
        from council.chamber.open_debate import OpenDebate
        from council.core.schemas import CallResult, LineupRecord, ModeConfig, SeatAssignment, TaskProfile

        self.CallResult = CallResult
        seats = [SeatAssignment(seat_no=i, model_id=m) for i, (m, _) in enumerate(MODELS)]
        mode = ModeConfig(name="standard", rounds=["r0", "r1"], deadline_s=600.0, reasoning="off")
        self.d = OpenDebate("run9", "Queue or lock?", TaskProfile(), LineupRecord(seats=seats, k=3), mode,
                            seat_names={0: "Qwen", 1: "Llama", 2: "Phi"}, seed=1)
        self.bridge = UiBridge("run9", limit_ms=600000)
        self.engine: list[tuple[str, dict]] = []
        self.out: list[dict] = []
        self.n = 0
        self.take(self.d.take_events())

    def take(self, events) -> list[dict]:
        got: list[dict] = []
        for type_, payload in events:
            self.n += 1
            self.engine.append((type_, payload))
            got.extend(self.bridge.feed({"seq": self.n, "ts": 1000.0 + self.n, "type": type_, "payload": payload}))
        self.out.extend(got)
        return got

    def result(self, spec, text=None, parsed=None, ok=True):
        return self.take(self.d.on_result(self.CallResult(
            call_id=spec.call_id, ok=ok, model_id=spec.model_id, content=text or "", parsed=parsed,
            error=None if ok else "timeout")))

    def card(self, stance, backs="new", to="all", conf=0.9):
        return {"note": stance, "to": to, "stance": stance, "backs": backs, "confidence": conf,
                "changed": False, "changed_because": ""}

    def play(self) -> None:
        r0 = self.d.pending_calls()
        # the gateway streams the message call under the turn id, with no seat
        self.out.extend(self.bridge.feed({"seq": 0, "ts": 1001.5, "type": "turn.started", "payload": {
            "call_id": r0[0].call_id, "seat_no": None, "round": 0, "purpose": "seat.r0"}}))
        delta = self.bridge.feed({"seq": 0, "ts": 1001.6, "type": "turn.delta", "payload": {
            "call_id": r0[0].call_id, "seat_no": None, "text": "Use a "}})
        self.assertEqual([(e["type"], e["turnId"], e["text"]) for e in delta],
                         [("turn.delta", r0[0].call_id, "Use a ")])
        self.out.extend(delta)
        for spec, text in zip(r0, ["Use a queue.", "Queue.", "A lock."]):
            self.result(spec, text)
        c0 = self.d.pending_calls()
        # a card call is not a turn: its completion gives nothing
        self.assertEqual(self.bridge.feed({"seq": 0, "ts": 1001.7, "type": "turn.completed", "payload": {
            "call_id": c0[0].call_id, "seat_no": None, "content": "{}"}}), [])
        self.result(c0[0], parsed=self.card("queue"))
        self.result(c0[1], ok=False)  # card call fails: the engine makes the card
        self.result(c0[2], parsed=self.card("lock", to=["s0"]))
        self.result(self.d.pending_calls()[0], parsed={"groups": [["s0"], ["s1"], ["s2"]]})
        self.d.set_lie_metrics({r0[2].call_id: {"score": 0.2, "level": "flag", "reasons": ["no source"]},
                                r0[1].call_id: {"score": None, "level": "ok"}})
        self.take(self.d.take_events())
        r1 = self.d.pending_calls()
        for spec in r1:
            self.result(spec, "Still mine.")
        c1 = self.d.pending_calls()
        self.result(c1[0], parsed=self.card("queue", "A1"))
        self.result(c1[1], parsed=self.card("queue", "A2"))
        self.result(c1[2], parsed=self.card("lock", "A3"))
        self.assertEqual(self.d.phase, "chair")
        self.decider = self.d.pending_calls()[0]
        self.thinking_decider = table_snapshot(self.out)
        self.result(self.decider, parsed={"backs": "A1", "final_answer": "Use a queue.", "objection": ""})
        self.take([("run.completed", {"outcome": "chair", "final_text": "Use a queue."})])

    def test_every_engine_event_has_a_handler_and_its_keys_are_read(self) -> None:
        self.play()
        seen = {t for t, _ in self.engine}
        self.assertEqual(seen, {"round.started", "msg.started", "msg.ended", "msg.card", "msg.lie", "table.tally",
                                "round.completed", "consensus.failed", "chair.started", "decision.final",
                                "run.completed"})
        silent = {"consensus.failed"}  # the tally already says it
        for type_ in seen - silent:
            self.assertTrue(hasattr(self.bridge, "_on_" + type_.replace(".", "_")), type_)
        read = {"msg.started": {"turn_id", "seat_no", "model_id", "round", "kind", "to"},
                "msg.ended": {"turn_id", "text", "error"},
                "msg.card": {"turn_id", "seat_no", "card", "fallback"},
                "msg.lie": {"turn_id", "seat_no", "score", "level", "reasons"},
                "table.tally": {"round", "groups", "leading", "agree", "seats", "needed", "reached", "basis"},
                "chair.started": {"call_id", "seat_no"}}
        for type_, payload in self.engine:
            self.assertTrue(read.get(type_, set()) <= set(payload), (type_, sorted(payload)))
        for group in [g for t, p in self.engine if t == "table.tally" for g in p["groups"]]:
            self.assertEqual(set(group), {"answer_id", "statement", "seat_ids"})

    def test_what_the_ui_gets(self) -> None:
        self.play()
        by = lambda t: [e for e in self.out if e["type"] == t]
        self.assertEqual(self.out[0]["type"], "debate.created")
        self.assertEqual([s["id"] for s in self.out[0]["seats"]], ["s0", "s1", "s2"])  # from round.started
        notes = by("summary.posted")
        self.assertEqual([n["source"] for n in notes[:3]], ["self", "engine", "self"])
        self.assertTrue(all(len(n["text"]) <= 55 for n in notes))
        self.assertEqual([(e["turnId"].rsplit(":", 2)[1:], e["to"]) for e in by("turn.addressed")],
                         [(["0", "s2"], ["s0"])])
        lies = by("lie.posted")  # the reading with no score is not shown as a number
        self.assertEqual([(e["seatId"], e["score"], e["level"]) for e in lies], [("s2", 0.2, "flag")])
        tallies = by("tally.posted")
        self.assertEqual([(t["round"], t["agree"], t["needed"], t["reached"]) for t in tallies],
                         [(0, 1, 3, False), (1, 1, 3, False)])
        self.assertEqual(tallies[0]["groups"][0], {"answerId": "A1", "statement": "queue", "seatIds": ["s0"]})
        seat = f"s{self.decider.meta['seat']}"
        self.assertTrue(self.thinking_decider[seat]["thinking"])  # the deciding vote shows as thinking
        answer = [e for e in by("turn.started") if e["kind"] == "answer"][0]
        self.assertEqual(answer["seatId"], seat)  # written by the seat that cast the deciding vote
        released = by("answer.released")[0]
        self.assertEqual((released["outcome"], released["tallyRound"], released["rounds"]), ("no-consensus", 1, 2))
        end = table_snapshot(self.out)
        self.assertFalse(any(s["thinking"] for s in end.values()))
        self.assertEqual({k: v["note"] for k, v in end.items()}, {"s0": "queue", "s1": "queue", "s2": "lock"})
        ended = {e["turnId"]: e["text"] for e in by("turn.ended")}
        self.assertEqual(ended[self.engine[1][1]["turn_id"]], "Use a queue.")


if __name__ == "__main__":
    unittest.main()
