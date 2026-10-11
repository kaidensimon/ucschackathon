"""Tests for council.chamber.open_debate. Scripted CallResults, no I/O."""

import json
import random
import unittest

from council.chamber.consensus import ConsensusConfig
from council.chamber.open_debate import (
    CARD_TOKENS,
    POSITION_TOKENS,
    REPLY_TOKENS,
    OpenDebate,
)
from council.core import event_types as E
from council.core.schemas import (
    MODE_DEFAULTS,
    CallResult,
    LineupRecord,
    ModeConfig,
    SeatAssignment,
    TaskProfile,
)

NAMES = ["Qwen", "Gemma", "Phi", "Llama", "Mistral", "Granite"]
TASK = "A snail climbs 3 m by day and slips 2 m by night in a 10 m well. On which day is it out?"


def lineup(k):
    seats = [SeatAssignment(seat_no=i, model_id=f"m{i}", q=0.9 - i * 0.1) for i in range(k)]
    return LineupRecord(seats=seats, k=k)


def make(k=6, mode="standard", **kw):
    if isinstance(mode, str):
        mode = MODE_DEFAULTS[mode]
    kw.setdefault("seat_names", {i: NAMES[i] for i in range(k)})
    kw.setdefault("write_final", False)  # the writer call has its own tests (FinalWriter)
    return OpenDebate("run1", TASK, TaskProfile(), lineup(k), mode, **kw)


def rounds(n):
    return ModeConfig(name="standard", rounds=["r0"] + ["r1"] * n, deadline_s=600.0, reasoning="off")


def card(stance, backs="new", conf=0.9, to="all", note=None, changed=False, because=""):
    return {
        "note": note or stance, "to": to, "stance": stance, "backs": backs, "confidence": conf,
        "changed": changed, "changed_because": because,
    }


def user_of(spec):
    return spec.messages[-1]["content"]


class Driver:
    """Feeds results in and keeps every event, checking known ones against the event contract."""

    def __init__(self, test, d):
        self.test, self.d = test, d
        self.events = []
        self.take(d.take_events())

    def take(self, events):
        for type_, payload in events:
            if type_ in E.PAYLOADS:
                E.validate_payload(type_, payload)
            json.dumps(payload)
            self.events.append((type_, payload))
        return events

    def of(self, type_):
        return [p for t, p in self.events if t == type_]

    def calls(self, purpose=None, n=None):
        specs = self.d.pending_calls()
        if purpose is not None:
            self.test.assertEqual({s.purpose for s in specs}, {purpose})
        if n is not None:
            self.test.assertEqual(len(specs), n)
        return specs

    def text(self, spec, text):
        return self.take(self.d.on_result(
            CallResult(call_id=spec.call_id, ok=True, model_id=spec.model_id, content=text)))

    def obj(self, spec, parsed):
        return self.take(self.d.on_result(
            CallResult(call_id=spec.call_id, ok=True, model_id=spec.model_id, parsed=parsed)))

    def fail(self, spec, error="timeout"):
        return self.take(self.d.on_result(
            CallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id, error=error)))

    def messages(self, specs, texts=None):
        """Answer the message calls. Returns {seat_no: card spec}."""
        for i, spec in enumerate(specs):
            seat = spec.meta["seat"]
            self.text(spec, texts[seat] if texts else f"Message of seat {seat}, call {i}.")
        cards = self.calls("seat.card", len(specs))
        return {s.meta["seat"]: s for s in cards}

    def round(self, cards, purpose=None, texts=None):
        """One whole round. `cards` = {seat_no: card dict}."""
        specs = self.calls(purpose, len(cards))
        for seat, spec in self.messages(specs, texts).items():
            self.obj(spec, cards[seat])
        return specs

    def merge(self, groups):
        spec = self.calls("clerk.merge", 1)[0]
        if groups is None:
            self.fail(spec, "invalid_output")
        else:
            self.obj(spec, {"groups": groups})
        return spec

    def groups(self):
        """{answer_id: [seat ids]} of the last tally."""
        return {g["answer_id"]: list(g["seat_ids"]) for g in self.of("table.tally")[-1]["groups"]}


BOX_R0 = {0: "Day 8", 1: "Day 8", 2: "Day 7", 3: "Day 4", 4: "Day 3", 5: "day  8"}


class EarlyConsensus(unittest.TestCase):
    def test_three_seats_agree_in_round_zero(self):
        dr = Driver(self, make(3))
        specs = dr.calls("seat.r0", 3)
        for spec in specs:
            self.assertTrue(spec.stream)
            self.assertIsNone(spec.json_schema)
            self.assertEqual(spec.max_output_tokens, POSITION_TOKENS)
            self.assertIn(TASK, spec.messages[0]["content"])
            self.assertIn("Round 0, opening positions", user_of(spec))
        texts = {0: "It is day 8. Short.", 1: "Day 8, I am sure.", 2: "Day 8 as well."}
        cards = dr.messages(specs, texts)
        for spec in cards.values():
            self.assertEqual(spec.max_output_tokens, CARD_TOKENS)
            self.assertEqual(spec.reasoning, "off")
            self.assertEqual(spec.json_schema["properties"]["backs"]["enum"], ["new"])
            self.assertIn("YOUR MESSAGE", user_of(spec))
        dr.obj(cards[0], card("Day 8", conf=0.7))
        dr.obj(cards[1], card("Day 8", conf=0.95))
        self.assertFalse(dr.d.is_done())
        dr.obj(cards[2], card("day 8", conf=0.8))
        self.assertTrue(dr.d.is_done())
        self.assertEqual(dr.d.pending_calls(), [])  # same stance: no merge call, no round 1
        decision = dr.d.decision()
        self.assertEqual(decision.outcome, "consensus")
        self.assertEqual(decision.option_id, "A1")
        self.assertEqual(decision.final_text, texts[1])  # the most confident backer's message
        self.assertEqual(decision.agreement, 1.0)
        self.assertEqual(decision.tally, {"A1": 3})
        self.assertEqual(decision.rounds_run, 1)
        self.assertEqual(decision.minority_report, [])
        self.assertTrue(dr.of("consensus.reached")[0]["early"])
        tally = dr.of("table.tally")[0]
        self.assertEqual((tally["agree"], tally["seats"], tally["needed"], tally["reached"]), (3, 3, 3, True))
        self.assertEqual(tally["basis"], "round-vote")
        types = [t for t, _ in dr.events]
        self.assertEqual(types[0], "round.started")
        self.assertEqual(types[-1], "decision.final")
        self.assertEqual(types.count("msg.started"), 3)
        self.assertEqual(types.count("msg.ended"), 3)
        self.assertEqual(types.count("msg.card"), 3)
        started = dr.of("msg.started")[0]
        self.assertEqual(
            {k: started[k] for k in ("seat_no", "model_id", "round", "kind", "to")},
            {"seat_no": 0, "model_id": "m0", "round": 0, "kind": "position", "to": "all"},
        )
        self.assertEqual(started["turn_id"], specs[0].call_id)
        for seat in dr.d.table_view().values():
            self.assertFalse(seat["thinking"])
            self.assertLessEqual(len(seat["note"]), 55)

    def test_unsure_agreement_goes_to_round_one(self):
        dr = Driver(self, make(3))
        dr.round({i: card("Day 8", conf=0.4) for i in range(3)}, "seat.r0")
        self.assertEqual(dr.d.phase, "r1")
        self.assertEqual(dr.of("consensus.failed")[0]["next_step"], "round")
        dr.round({i: card("Day 8", "A1", conf=0.5) for i in range(3)}, "seat.r1")
        self.assertEqual(dr.d.decision().outcome, "consensus")

    def test_thinking_until_the_card_is_in(self):
        dr = Driver(self, make(3))
        specs = dr.calls("seat.r0", 3)
        self.assertTrue(all(v["thinking"] and v["note"] is None for v in dr.d.table_view().values()))
        dr.text(specs[0], "Day 8.")
        self.assertTrue(dr.d.table_view()["s0"]["thinking"])  # text is in, the card is not
        dr.obj(dr.calls("seat.card", 1)[0], card("Day 8", note="Day 8: slip is at night"))
        view = dr.d.table_view()["s0"]
        self.assertEqual((view["thinking"], view["note"]), (False, "Day 8: slip is at night"))
        self.assertEqual(len(dr.d.chat_view()), 3)


class BoxCase(unittest.TestCase):
    def play_r0(self, dr, merge):
        dr.round({s: card(v) for s, v in BOX_R0.items()}, "seat.r0")
        self.assertEqual(dr.d.phase, "merge")
        spec = dr.merge(merge)
        for sid in ("s0", "s5"):
            self.assertIn(f"{sid}:", user_of(spec))
        return spec

    def assert_named(self, dr, cards):
        groups = dr.groups()
        for seat, c in cards.items():
            if c["backs"] != "new":
                self.assertIn(f"s{seat}", groups[c["backs"]], f"seat {seat} named {c['backs']}")
        seats = [s for g in groups.values() for s in g]
        self.assertEqual(len(seats), len(set(seats)))  # nobody is counted twice

    def test_four_answers_converge_through_backs(self):
        dr = Driver(self, make(6))
        spec = self.play_r0(dr, [["s0"], ["s1"], ["s2"], ["s3"], ["s4"], ["s5"]])
        self.assertEqual(spec.model_id, "m0")  # the first seat's model
        self.assertEqual(dr.groups(), {"A1": ["s0", "s1", "s5"], "A2": ["s2"], "A3": ["s3"], "A4": ["s4"]})
        self.assertEqual(dr.d.r0_options(), {0: "A1", 1: "A1", 2: "A2", 3: "A3", 4: "A4", 5: "A1"})
        tally = dr.of("table.tally")[-1]
        self.assertEqual((tally["agree"], tally["needed"], tally["reached"]), (3, 5, False))

        r1 = {
            0: card("Day 8", "A1"), 1: card("Day 8", "A1"), 5: card("Day 8", "A1"),
            2: card("Day 8", "A1", changed=True, because="the slip is at night"),
            3: card("Day 4", "A3"), 4: card("Day 3", "A4"),
        }
        specs = dr.round(r1, "seat.r1")
        for spec in specs:
            self.assertEqual(spec.max_output_tokens, REPLY_TOKENS)
            self.assertEqual(spec.temperature, 0.4)
            body = user_of(spec)
            self.assertIn("A1: Day 8 - backed by", body)
            self.assertIn("(3 of 6)", body)
            self.assertIn("[round 0] YOU -> all", body)
            self.assertIn("backs A1", body)  # round 0 cards carry the id they were given
        self.assert_named(dr, r1)
        self.assertEqual(dr.groups()["A1"], ["s0", "s1", "s2", "s5"])
        self.assertFalse(dr.d.is_done())

        r2 = dict(r1)
        r2[2] = card("Day 8", "A1")
        r2[3] = card("Day 8", "A1", changed=True, because="worked it through")
        dr.round(r2, "seat.r2")
        self.assert_named(dr, r2)
        tally = dr.of("table.tally")[-1]
        self.assertEqual((tally["round"], tally["agree"], tally["reached"]), (2, 5, True))
        decision = dr.d.decision()
        self.assertEqual((decision.outcome, decision.option_id, decision.rounds_run), ("consensus", "A1", 3))
        self.assertAlmostEqual(decision.agreement, 5 / 6)
        self.assertEqual(decision.tally, {"A1": 5, "A4": 1})
        self.assertEqual([(m.seats, m.option_id, m.position) for m in decision.minority_report],
                         [([4], "A4", "Day 3")])
        self.assertFalse(dr.of("consensus.reached")[0]["early"])
        self.assertEqual([p["round"] for p in dr.of("round.completed")], [0, 1, 2])

    def test_clerk_joins_whole_answers_and_never_splits_one(self):
        dr = Driver(self, make(6))
        # s0 and s1 gave the same stance: the clerk cannot pull them apart. s2 is named twice.
        self.play_r0(dr, [["s0", "s2"], ["s1", "s3"], ["s2", "s4"], ["zz"], "junk"])
        self.assertEqual(dr.groups(), {"A1": ["s0", "s1", "s2", "s3", "s5"], "A4": ["s4"]})
        # Agreement by the clerk's word alone, low confidence: every seat still confirms itself.
        self.assertTrue(dr.d.is_done() or dr.d.phase == "r1")

    def test_a_seat_leaves_the_clerks_group_in_round_one(self):
        dr = Driver(self, make(6), )
        dr.round({s: card(v, conf=0.5) for s, v in BOX_R0.items()}, "seat.r0")
        dr.merge([["s0", "s1", "s2", "s5"], ["s3", "s4"]])
        self.assertEqual(dr.groups(), {"A1": ["s0", "s1", "s2", "s5"], "A3": ["s3", "s4"]})
        r1 = {
            0: card("Day 8", "A1"), 1: card("Day 8", "A1"), 5: card("Day 8", "A1"),
            2: card("Day 7", "new"), 3: card("Day 4", "A3"), 4: card("Day 3", "new"),
        }
        dr.round(r1, "seat.r1")
        groups = dr.groups()
        self.assertEqual(groups["A1"], ["s0", "s1", "s5"])
        self.assertEqual(groups["A3"], ["s3"])
        self.assertEqual(sorted(len(g) for g in groups.values()), [1, 1, 1, 3])
        self.assertNotIn("A2", groups)  # an id is never handed to a second answer

    def test_merge_failure_keeps_every_distinct_stance(self):
        dr = Driver(self, make(6))
        self.play_r0(dr, None)
        self.assertEqual(dr.groups(), {"A1": ["s0", "s1", "s5"], "A2": ["s2"], "A3": ["s3"], "A4": ["s4"]})
        self.assertEqual(dr.d.phase, "r1")

    def test_seats_swap_answers_in_one_round(self):
        dr = Driver(self, make(2, mode=rounds(2)))
        dr.round({0: card("Day 8"), 1: card("Day 4")}, "seat.r0")
        dr.merge([["s0"], ["s1"]])
        r1 = {0: card("Day 4", "A2", changed=True, because="x"), 1: card("Day 8", "A1", changed=True, because="y")}
        dr.round(r1, "seat.r1")
        self.assertEqual(dr.groups(), {"A1": ["s1"], "A2": ["s0"]})


class Decider(unittest.TestCase):
    def play(self, seed):
        dr = Driver(self, make(4, mode=rounds(1), seed=seed))
        dr.round({0: card("Day 8"), 1: card("Day 8"), 2: card("Day 4"), 3: card("Day 4")}, "seat.r0")
        dr.merge([["s0", "s1"], ["s2", "s3"]])
        dr.round({0: card("Day 8", "A1"), 1: card("Day 8", "A1"), 2: card("Day 4", "A2"),
                  3: card("Day 4", "A2")}, "seat.r1")
        self.assertEqual(dr.d.phase, "chair")
        return dr, dr.calls("chair", 1)[0]

    def test_split_to_the_end_goes_to_a_seeded_decider(self):
        dr, spec = self.play(7)
        expected = random.Random("7:decider").choice([0, 1, 2, 3])
        self.assertEqual(spec.model_id, f"m{expected}")
        self.assertEqual(dr.d.decider_seat(), expected)
        self.assertEqual(dr.of("chair.started")[0]["seat_no"], expected)
        self.assertEqual(dr.of("consensus.failed")[-1]["next_step"], "chair")
        self.assertEqual(spec.json_schema["properties"]["backs"]["enum"], ["A1", "A2"])
        body = user_of(spec)
        self.assertIn("picked at random", body)
        self.assertIn("[round 1]", body)
        self.assertIn("A2: Day 4 - backed by", body)
        dr.obj(spec, {"backs": "A2", "final_answer": "The snail is out on day 4.", "objection": "none left"})
        decision = dr.d.decision()
        self.assertEqual((decision.outcome, decision.option_id), ("chair", "A2"))
        self.assertEqual(decision.final_text, "The snail is out on day 4.")
        self.assertEqual(decision.agreement, 0.5)
        self.assertEqual(decision.tally, {"A1": 2, "A2": 2})
        self.assertEqual(decision.rounds_run, 2)
        self.assertEqual([(m.seats, m.option_id) for m in decision.minority_report], [([0, 1], "A1")])
        self.assertTrue(any("deciding vote" in n for n in decision.notes))

        again, spec2 = self.play(7)
        self.assertEqual(spec2.model_id, spec.model_id)
        self.assertEqual(user_of(spec2), body)
        picks = {self.play(seed)[1].model_id for seed in range(12)}
        self.assertTrue(picks <= {"m0", "m1", "m2", "m3"})
        self.assertGreater(len(picks), 1)

    def test_failed_decider_passes_on_then_deadlock(self):
        dr, spec = self.play(3)
        tried = [spec.model_id]
        dr.fail(spec)
        for _ in range(2):
            spec = dr.calls("chair", 1)[0]
            tried.append(spec.model_id)
            dr.fail(spec, "invalid_output")
        self.assertEqual(len(set(tried)), 3)
        decision = dr.d.decision()
        self.assertEqual(decision.outcome, "deadlock")
        self.assertEqual(decision.option_id, "A1")
        self.assertTrue(decision.final_text)

    def test_no_round_left_after_round_zero(self):
        dr = Driver(self, make(3, mode="quick"))
        dr.round({0: card("Day 8"), 1: card("Day 8"), 2: card("Day 4")}, "seat.r0")
        dr.merge([["s0", "s1"], ["s2"]])
        spec = dr.calls("chair", 1)[0]
        dr.text(spec, json.dumps({"backs": "A9", "final_answer": "Day 8.", "objection": ""}))
        decision = dr.d.decision()
        self.assertEqual((decision.outcome, decision.option_id), ("chair", "A1"))
        # "Day 8." is too short to be the answer the user reads: statement + best backer's message
        self.assertEqual(decision.final_text, "Day 8\n\nMessage of seat 0, call 0.")


class Addressing(unittest.TestCase):
    def test_message_to_a_seat_is_in_its_next_prompt(self):
        # 2 against 1 names an outlier and changes the prompts: that has its own tests (Outliers)
        dr = Driver(self, make(3, mode=rounds(2), question_outliers=False))
        texts = {0: "Gemma, your day-4 answer forgets the slip back.", 1: "Day 4 it is.", 2: "Day 8."}
        cards = {0: card("Day 8", to=["s1"]), 1: card("Day 4"), 2: card("Day 8")}
        dr.round(cards, "seat.r0", texts)
        dr.merge([["s0", "s2"], ["s1"]])
        self.assertEqual(dr.of("msg.card")[0]["card"]["to"], ["s1"])
        specs = {s.meta["seat"]: s for s in dr.calls("seat.r1", 3)}

        def addressed(spec):
            body = user_of(spec)
            return body.split("Messages addressed to you.")[1].split("Now write your reply")[0]

        self.assertIn("Qwen (round 0): Gemma, your day-4 answer forgets the slip back.", addressed(specs[1]))
        self.assertIn("(none)", addressed(specs[0]))
        self.assertIn("(none)", addressed(specs[2]))
        self.assertIn("[round 0] Qwen -> YOU", user_of(specs[1]))
        self.assertIn("[round 0] Qwen -> Gemma", user_of(specs[2]))
        self.assertIn("Qwen, Gemma (you), Phi", specs[1].messages[0]["content"])
        # round 1 has not been written yet: nobody sees a round 1 line
        self.assertNotIn("[round 1]", user_of(specs[2]))

    def test_lie_metrics_show_in_the_next_round(self):
        dr = Driver(self, make(3, mode=rounds(2)))
        first = dr.round({0: card("Day 8"), 1: card("Day 4"), 2: card("Day 8")}, "seat.r0")
        dr.merge(None)
        turn = first[1].call_id
        dr.d.set_lie_metrics({turn: {"score": 0.2, "level": "flag", "reasons": ["hedged claim"]},
                              "nope": {"score": 0.9}})
        dr.take(dr.d.take_events())
        self.assertEqual(dr.of("msg.lie"), [{"turn_id": turn, "seat_no": 1, "score": 0.2, "level": "flag",
                                             "reasons": ["hedged claim"]}])
        for spec in dr.calls("seat.r1", 3):
            self.assertIn("(lie detector: 0.20 FLAG: hedged claim)", user_of(spec))
        self.assertEqual(dr.d.chat_view()[1]["lie"]["level"], "flag")


class Failures(unittest.TestCase):
    def test_card_failure_gives_a_fallback_card(self):
        dr = Driver(self, make(3, mode=rounds(2)))
        specs = dr.calls("seat.r0", 3)
        long = "It is day 8 because the slip happens at night after the climb of the day. More words follow here."
        cards = dr.messages(specs, {0: long, 1: "Day 4.", 2: "Day 4."})
        dr.fail(cards[0], "invalid_output")
        dr.obj(cards[1], card("Day 4"))
        dr.obj(cards[2], card("Day 4"))
        posted = dr.of("msg.card")[0]
        self.assertTrue(posted["fallback"])
        self.assertLessEqual(len(posted["card"]["note"]), 55)
        self.assertTrue(long.startswith(posted["card"]["note"][:20]))
        dr.merge([["s0"], ["s1", "s2"]])
        self.assertEqual(dr.groups(), {"A2": ["s1", "s2"], "A1": ["s0"]})

        # round 1: seat 1's card call breaks. It stays on the answer it backed.
        cards = dr.messages(dr.calls("seat.r1", 3))
        dr.obj(cards[0], card("Day 8", "A1"))
        dr.text(cards[1], "this is not json")
        dr.obj(cards[2], card("Day 4", "A2"))
        self.assertEqual(dr.groups(), {"A2": ["s1", "s2"], "A1": ["s0"]})
        last = [p for p in dr.of("msg.card") if p["seat_no"] == 1][-1]
        self.assertEqual((last["fallback"], last["card"]["backs"], last["card"]["stance"]), (True, "A2", "Day 4"))

    def test_failed_turn_keeps_the_card_and_two_in_a_row_drop_the_seat(self):
        dr = Driver(self, make(4, mode=rounds(3)))
        dr.round({0: card("Day 8"), 1: card("Day 8"), 2: card("Day 8"), 3: card("Day 4")}, "seat.r0")
        dr.merge(None)
        for rnd in (1, 2):
            specs = {s.meta["seat"]: s for s in dr.calls(f"seat.r{rnd}", 4)}
            dr.fail(specs.pop(2))
            for seat, spec in dr.messages(list(specs.values())).items():
                dr.obj(spec, card("Day 8", "A1") if seat != 3 else card("Day 4", "A2"))
            tally = dr.of("table.tally")[-1]
            if rnd == 1:  # seat 2 failed once: still counted on its last card
                self.assertEqual((tally["agree"], tally["seats"], tally["needed"]), (3, 4, 4))
                self.assertEqual(dr.of("round.completed")[-1]["failed_seats"], [2])
                self.assertEqual(dr.of("msg.ended")[-4]["error"], "timeout")
        # dropped after the second failure: 2 of 3 agree, 3 needed
        self.assertEqual((tally["agree"], tally["seats"], tally["needed"], tally["reached"]), (2, 3, 3, False))
        self.assertEqual(len(dr.calls("seat.r3", 3)), 3)

    def test_no_message_at_all_is_a_deadlock(self):
        dr = Driver(self, make(3))
        for spec in dr.calls("seat.r0", 3):
            dr.fail(spec, "server_error")
        decision = dr.d.decision()
        self.assertEqual((decision.outcome, decision.rounds_run), ("deadlock", 1))

    def test_below_quorum_goes_to_the_decider(self):
        dr = Driver(self, make(5))
        specs = dr.calls("seat.r0", 5)
        for spec in specs[2:]:
            dr.fail(spec)
        for spec in dr.messages(specs[:2]).values():
            dr.obj(spec, card("Day 8"))
        self.assertEqual(dr.d.phase, "chair")
        self.assertIn("quorum", dr.of("consensus.failed")[0]["reason"])


class Deadline(unittest.TestCase):
    def test_deadline_mid_round(self):
        dr = Driver(self, make(4, mode=rounds(3)))
        dr.round({0: card("Day 8"), 1: card("Day 8"), 2: card("Day 4"), 3: card("Day 4")}, "seat.r0")
        dr.merge(None)
        specs = dr.calls("seat.r1", 4)
        dr.text(specs[2], "Fine, day 8: the slip is at night.")
        dr.text(specs[3], "Still day 4.")
        cards = {s.meta["seat"]: s for s in dr.calls("seat.card", 2)}
        dr.obj(cards[2], card("Day 8", "A1", changed=True, because="slip at night"))
        dr.take(dr.d.on_deadline(40.0))
        self.assertEqual(dr.d.phase, "chair")
        self.assertEqual(dr.d.chair_reserve_s(), 0.0)
        self.assertEqual(dr.groups(), {"A1": ["s0", "s1", "s2"], "A2": ["s3"]})
        self.assertEqual([p["seat_no"] for p in dr.of("msg.ended") if p["error"] == "cancelled"], [0, 1])
        self.assertFalse(any(v["thinking"] for v in dr.d.table_view().values()))
        # results of the calls that were dropped are ignored
        dr.text(specs[0], "late")
        dr.obj(cards[3], card("Day 8", "A1"))
        self.assertEqual(dr.groups(), {"A1": ["s0", "s1", "s2"], "A2": ["s3"]})
        spec = dr.calls("chair", 1)[0]
        self.assertGreaterEqual(spec.timeout_s, 40.0)
        self.assertEqual(spec.call_id in dr.d._waiting, True)  # LiveExecutor keeps it alive
        dr.obj(spec, {"backs": "A1", "final_answer": "Day 8.", "objection": ""})
        decision = dr.d.decision()
        self.assertEqual((decision.outcome, decision.option_id, decision.rounds_run), ("chair", "A1", 2))
        self.assertEqual(dr.d.on_deadline(), [])

    def test_deadline_can_still_find_consensus(self):
        dr = Driver(self, make(3, mode=rounds(2)))
        specs = dr.calls("seat.r0", 3)
        for spec in dr.messages(specs).values():
            dr.obj(spec, card("Day 8", conf=0.3))  # unsure: round 1 starts
        self.assertEqual(dr.d.phase, "r1")
        dr.take(dr.d.on_deadline(0.0))
        self.assertEqual(dr.d.decision().outcome, "consensus")

    def test_deadline_in_round_zero_and_in_merge(self):
        dr = Driver(self, make(3))
        specs = dr.calls("seat.r0", 3)
        dr.text(specs[0], "Day 8.")
        dr.take(dr.d.on_deadline())
        self.assertEqual(dr.d.phase, "chair")  # one card of three: below quorum
        spec = dr.calls("chair", 1)[0]
        self.assertTrue(any("deadline" in n for n in dr.d._notes))
        dr.obj(spec, {"backs": "A1", "final_answer": "Day 8.", "objection": ""})
        self.assertEqual(dr.d.decision().outcome, "chair")

        dr = Driver(self, make(3))
        dr.round({0: card("Day 8"), 1: card("Day 8"), 2: card("Day 4")}, "seat.r0")
        self.assertEqual(dr.d.phase, "merge")
        dr.take(dr.d.on_deadline(30.0))
        self.assertEqual(dr.d.phase, "chair")
        self.assertEqual(dr.groups(), {"A1": ["s0", "s1"], "A2": ["s2"]})

    def test_no_round_starts_when_the_time_does_not_fit(self):
        dr = Driver(self, make(3, mode=rounds(3), seat_tps={0: 10.0, 1: 10.0, 2: 10.0}))
        specs = dr.calls("seat.r0", 3)
        cards = dr.messages(specs)
        dr.d.set_remaining(dr.d.chair_reserve_s() + 20.0)  # 20 s of debate left: no round fits
        dr.obj(cards[0], card("Day 8"))
        dr.obj(cards[1], card("Day 8"))
        dr.obj(cards[2], card("Day 8", conf=0.2))
        self.assertTrue(dr.d.is_done())  # agreement and no time to test it: consensus
        dr = Driver(self, make(3, mode=rounds(3), seat_tps={0: 10.0, 1: 10.0, 2: 10.0}))
        cards = dr.messages(dr.calls("seat.r0", 3))
        dr.obj(cards[0], card("Day 8"))
        dr.obj(cards[1], card("Day 8"))
        dr.obj(cards[2], card("Day 4"))
        dr.d.set_remaining(dr.d.chair_reserve_s() + 20.0)
        dr.merge(None)
        self.assertEqual(dr.d.phase, "chair")


class TwoSeats(unittest.TestCase):
    def test_both_must_agree(self):
        dr = Driver(self, make(2, mode=rounds(1)))
        dr.round({0: card("Day 8"), 1: card("Day 8")}, "seat.r0")
        tally = dr.of("table.tally")[0]
        self.assertEqual((tally["needed"], tally["reached"]), (2, True))
        self.assertEqual(dr.d.decision().outcome, "consensus")

    def test_one_one_split_is_decided_by_the_decider(self):
        dr = Driver(self, make(2, mode=rounds(1)))
        dr.round({0: card("Day 8"), 1: card("Day 4")}, "seat.r0")
        dr.merge([["s0"], ["s1"]])
        self.assertEqual(dr.of("table.tally")[0]["reached"], False)
        specs = dr.round({0: card("Day 8", "A1"), 1: card("Day 4", "A2")}, "seat.r1")
        self.assertEqual(specs[0].json_schema, None)
        spec = dr.calls("chair", 1)[0]
        self.assertIn(spec.model_id, ("m0", "m1"))
        dr.obj(spec, {"backs": "A1", "final_answer": "Day 8.", "objection": "Phi disagrees"})
        decision = dr.d.decision()
        self.assertEqual((decision.outcome, decision.agreement), ("chair", 0.5))

    def test_one_moves_and_they_agree(self):
        dr = Driver(self, make(2, mode=rounds(2)))
        dr.round({0: card("Day 8"), 1: card("Day 4")}, "seat.r0")
        dr.merge(None)
        cards = {s: spec for s, spec in dr.messages(dr.calls("seat.r1", 2)).items()}
        self.assertEqual(cards[1].json_schema["properties"]["backs"]["enum"], ["A1", "A2", "new"])
        self.assertEqual(cards[1].json_schema["properties"]["to"]["anyOf"][1]["items"]["enum"], ["s0"])
        dr.obj(cards[0], card("Day 8", "A1"))
        dr.obj(cards[1], card("Day 8", "A1", changed=True, because="slip at night"))
        self.assertEqual(dr.d.decision().outcome, "consensus")
        ballots = dr.d.final_ballots()
        self.assertEqual((ballots[1].choice, ballots[1].changed_because), ("A1", ["slip at night"]))


class Interface(unittest.TestCase):
    def test_unused_parts_of_the_shared_interface(self):
        d = make(3)
        self.assertEqual(d.pending_checks(), [])
        self.assertEqual((d.cruxes(), d.evidence(), d.drafts()), ([], [], {}))
        self.assertIsNone(d.set_claim_scores([]))
        self.assertIsNone(d.set_lie_flags([]))
        self.assertGreater(d.chair_reserve_s(), 0.0)
        with self.assertRaises(RuntimeError):
            d.decision()
        d.take_events()
        self.assertEqual(d.on_evidence("k1", None), [])
        self.assertEqual(d.on_result(CallResult(call_id="unknown", ok=True)), [])

    def test_names_fall_back_to_the_model_id_and_stay_unique(self):
        seats = [SeatAssignment(seat_no=1, model_id="qwen2.5-coder:7b"),
                 SeatAssignment(seat_no=2, model_id="qwen2.5-coder:14b"),
                 SeatAssignment(seat_no=3, model_id="gemma3:4b")]
        d = OpenDebate("r", TASK, TaskProfile(), LineupRecord(seats=seats, k=3), MODE_DEFAULTS["quick"])
        names = [m.name for m in d.messages()]
        self.assertEqual(names, ["Qwen2.5-s1", "Qwen2.5-s2", "Gemma3"])

    def test_call_ids_do_not_parse_as_seat_turns(self):
        from council.chamber.executors import _parse_call_id

        dr = Driver(self, make(2, mode=rounds(1)))
        specs = dr.calls("seat.r0", 2)
        cards = dr.messages(specs)
        for spec in specs + list(cards.values()):
            self.assertEqual(_parse_call_id(spec.call_id), (None, None))
            self.assertNotIn("seat_no", spec.meta)


class SnapshotRestore(unittest.TestCase):
    def finish(self, d, out):
        """Play the rest with one script. Returns (decision, events)."""
        dr = Driver(self, d)
        dr.events = []
        for spec in sorted(out, key=lambda x: x.call_id):
            seat = spec.meta.get("seat")
            if spec.purpose == "seat.card":
                dr.obj(spec, card("Day 8", "A1") if seat != 3 else card("Day 4", "A2"))
            else:
                dr.text(spec, f"Reply of seat {seat}.")
        for spec in dr.d.pending_calls():
            seat = spec.meta["seat"]
            dr.obj(spec, card("Day 8", "A1") if seat != 3 else card("Day 4", "A2"))
        specs = dr.calls("seat.r2", 4)
        prompts = [user_of(s) for s in specs]
        for seat, spec in dr.messages(specs).items():
            dr.obj(spec, card("Day 8", "A1", changed=seat == 3, because="ok" if seat == 3 else ""))
        return d.decision().model_dump(mode="json"), dr.events, prompts

    def test_mid_round_snapshot_gives_the_same_continuation(self):
        dr = Driver(self, make(4, mode=rounds(3), seed=5))
        dr.round({0: card("Day 8"), 1: card("Day 8"), 2: card("Day 8"), 3: card("Day 4")}, "seat.r0")
        dr.merge(None)
        specs = dr.calls("seat.r1", 4)
        dr.text(specs[0], "Reply of seat 0.")
        dr.text(specs[1], "Reply of seat 1.")
        card_specs = dr.calls("seat.card", 2)
        dr.obj(card_specs[0], card("Day 8", "A1"))
        out = [card_specs[1], specs[2], specs[3]]  # still in flight

        snap = dr.d.snapshot()
        json.dumps(snap)
        twin = OpenDebate.restore(json.loads(json.dumps(snap)))
        self.assertEqual(twin.phase, "r1")
        self.assertEqual(twin.snapshot(), snap)
        again = twin.pending_calls()  # calls that were out are handed out again
        by_id = lambda specs: sorted((s.model_dump() for s in specs), key=lambda x: x["call_id"])
        self.assertEqual(by_id(again), by_id(out))
        self.assertEqual(dr.d.pending_calls(), [])

        a = self.finish(dr.d, out)
        b = self.finish(twin, again)
        self.assertEqual(a, b)
        self.assertEqual(a[0]["outcome"], "consensus")
        self.assertEqual(a[0]["rounds_run"], 3)

    def test_snapshot_when_done(self):
        dr = Driver(self, make(3))
        dr.round({i: card("Day 8") for i in range(3)}, "seat.r0")
        twin = OpenDebate.restore(dr.d.snapshot())
        self.assertTrue(twin.is_done())
        self.assertEqual(twin.decision(), dr.d.decision())
        self.assertEqual(twin.table_view(), dr.d.table_view())


class ProtocolRules(unittest.TestCase):
    """The rules the user set, checked from the outside."""

    def test_unconfirmed_round_zero_agreement_is_not_posted_as_reached(self):
        dr = Driver(self, make(3))
        dr.round({i: card("Day 8", conf=0.4) for i in range(3)}, "seat.r0")
        self.assertEqual(dr.d.phase, "r1")  # the debate goes on ...
        tally = dr.of("table.tally")[0]
        self.assertEqual((tally["agree"], tally["needed"]), (3, 3))
        self.assertFalse(tally["reached"])  # ... so the UI must not stop its clock
        self.assertTrue(tally["unconfirmed"])
        self.assertFalse(dr.d.tally()["reached"])
        self.assertFalse(dr.of("round.completed")[0]["converged"])
        dr.round({i: card("Day 8", "A1", conf=0.5) for i in range(3)}, "seat.r1")
        tally = dr.of("table.tally")[1]
        self.assertEqual((tally["reached"], tally["unconfirmed"]), (True, False))

    def test_reached_in_the_tally_always_means_the_debate_ended(self):
        dr = Driver(self, make(4, mode=rounds(2)))
        dr.round({0: card("Day 8"), 1: card("Day 8"), 2: card("Day 8"), 3: card("Day 4")}, "seat.r0")
        dr.merge(None)
        dr.round({s: card("Day 8", "A1") for s in range(4)}, "seat.r1")
        self.assertEqual([t["reached"] for t in dr.of("table.tally")], [False, True])
        self.assertTrue(dr.d.is_done())

    def test_the_message_carries_whom_its_card_says_it_addressed(self):
        dr = Driver(self, make(3, mode=rounds(2)))
        dr.round({0: card("Day 8", to=["s1"]), 1: card("Day 4"), 2: card("Day 8")}, "seat.r0")
        chat = dr.d.chat_view()
        self.assertEqual([m["to"] for m in chat], [["s1"], "all", "all"])
        self.assertEqual(dr.d.messages()[0].to, ["s1"])
        twin = OpenDebate.restore(dr.d.snapshot())
        self.assertEqual(twin.chat_view(), chat)

    def test_late_lie_readings_reach_a_waiting_decider(self):
        dr = Driver(self, make(2, mode=rounds(1)))
        dr.round({0: card("Day 8"), 1: card("Day 4")}, "seat.r0")
        dr.merge(None)
        r1 = dr.round({0: card("Day 8", "A1"), 1: card("Day 4", "A2")}, "seat.r1")
        self.assertEqual(dr.d.phase, "chair")  # the decider call is waiting, not handed out
        dr.d.set_lie_metrics({r1[1].call_id: {"score": 0.1, "level": "flag", "reasons": ["made up"]}})
        spec = dr.calls("chair", 1)[0]
        self.assertIn("(lie detector: 0.10 FLAG: made up)", user_of(spec))
        self.assertIs(dr.d._waiting[spec.call_id]["spec"], spec)
        self.assertGreater(spec.timeout_s, 0)

    def test_every_reader_sees_all_text_by_name_with_address_and_reading(self):
        dr = Driver(self, make(3, mode=rounds(2)))
        texts = {0: "Gemma, day 4 forgets the slip. SECRET-ZERO", 1: "Day 4. SECRET-ONE", 2: "Day 8. SECRET-TWO"}
        first = dr.round({0: card("Day 8", to=["s1"]), 1: card("Day 4"), 2: card("Day 8")}, "seat.r0", texts)
        for spec in first:  # blind opening: nobody reads anybody
            self.assertNotIn("SECRET", user_of(spec))
        dr.merge(None)
        dr.d.set_lie_metrics({s.call_id: {"score": 0.25 * (i + 1), "level": "watch"} for i, s in enumerate(first)})
        for spec in dr.calls("seat.r1", 3):
            body, me = user_of(spec), spec.meta["seat"]
            for word in ("SECRET-ZERO", "SECRET-ONE", "SECRET-TWO"):
                self.assertIn(word, body)  # nothing is hidden from any member
            for seat, name in enumerate(NAMES[:3]):
                who = "YOU" if seat == me else name
                to = ("YOU" if me == 1 else "Gemma") if seat == 0 else "all"
                self.assertIn(f"[round 0] {who} -> {to}   (lie detector: {0.25 * (seat + 1):.2f} watch)", body)

    def test_no_seat_is_counted_on_an_answer_it_did_not_name_after_round_zero(self):
        ids = ["A1", "A2", "A3", "A4", "new"]
        for seed in range(40):
            rng = random.Random(seed)
            dr = Driver(self, make(6, mode=rounds(3)))
            dr.round({s: card(v) for s, v in BOX_R0.items()}, "seat.r0")
            dr.merge([["s0", "s1", "s5"], ["s2", "s3"], ["s4"]])
            named = {}
            while not dr.d.is_done() and dr.d.phase != "chair":
                before = dr.groups()
                specs = dr.calls(None)
                cards = dr.messages(specs)
                for seat, spec in cards.items():
                    allowed = spec.json_schema["properties"]["backs"]["enum"]
                    pick = rng.choice([i for i in ids if i in allowed])
                    named[seat] = pick
                    # a stance no answer on the table has: "new" can only mean a new answer
                    dr.obj(spec, card(f"stance {seed} {dr.d.phase} {seat}", pick, conf=0.6))
                after = dr.groups()
                for seat, pick in named.items():
                    sid = f"s{seat}"
                    where = [a for a, seats in after.items() if sid in seats]
                    self.assertEqual(len(where), 1)
                    if pick == "new":
                        self.assertNotIn(where[0], before)  # an answer that was not there before
                        self.assertEqual(after[where[0]], [sid])
                    else:
                        self.assertEqual(where[0], pick)

    def test_the_decider_is_drawn_from_the_seed_alone(self):
        for seed in range(8):
            a = make(5, seed=seed).decider_seat()
            self.assertEqual(a, make(5, seed=seed).decider_seat())
            self.assertEqual(a, random.Random(f"{seed}:decider").choice([0, 1, 2, 3, 4]))
        self.assertGreater(len({make(5, seed=s).decider_seat() for s in range(30)}), 2)

    def test_it_never_waits_on_nothing(self):
        """Random scripts with failures and deadlines: while not done, a call is always out."""
        for seed in range(150):
            rng = random.Random(seed)
            k = rng.choice([2, 3, 4, 6])
            dr = Driver(self, make(k, mode=rounds(rng.choice([0, 1, 2, 3])), seed=seed,
                                   write_final=rng.random() < 0.7))
            out, steps = [], 0
            while not dr.d.is_done():
                steps += 1
                self.assertLess(steps, 500, f"seed {seed}: does not end")
                out.extend(dr.d.pending_calls())
                self.assertEqual({s.call_id for s in out}, set(dr.d._waiting), f"seed {seed}")
                self.assertTrue(out, f"seed {seed}: phase {dr.d.phase}, nothing pending, not done")
                if rng.random() < 0.04:
                    dr.take(dr.d.on_deadline(rng.choice([0.0, 30.0])))
                    out = [s for s in out if s.call_id in dr.d._waiting]
                    continue
                spec = out.pop(rng.randrange(len(out)))
                kind, roll = spec.meta["kind"], rng.random()
                if roll < 0.2:
                    dr.fail(spec, rng.choice(["timeout", "invalid_output"]))
                elif kind in ("msg", "answer"):
                    dr.text(spec, f"text {steps}")
                elif kind == "card":
                    allowed = spec.json_schema["properties"]["backs"]["enum"]
                    dr.obj(spec, card(rng.choice(["Day 8", "Day 4", "Day 7"]), rng.choice(allowed), conf=rng.random()))
                elif kind == "merge":
                    seats = spec.json_schema["properties"]["groups"]["items"]["items"]["enum"]
                    dr.obj(spec, {"groups": [seats[:2], seats[2:]]})
                else:
                    dr.obj(spec, {"backs": "A1", "final_answer": "Day 8.", "objection": ""})
                out = [s for s in out if s.call_id in dr.d._waiting]
            self.assertIn(dr.d.decision().outcome, ("consensus", "chair", "deadlock"))
            self.assertFalse(any(v["thinking"] for v in dr.d.table_view().values()))

    def test_module_is_pure(self):
        import ast
        import pathlib

        import council.chamber.messages as messages
        import council.chamber.open_debate as open_debate
        import council.chamber.protocol_prompts as protocol_prompts

        allowed = {"__future__", "dataclasses", "json", "math", "random", "re", "typing", "pydantic", "council"}
        for mod in (open_debate, messages, protocol_prompts):
            tree = ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom):
                    roots = {(node.module or "").split(".")[0]}
                else:
                    roots = set()
                self.assertTrue(roots <= allowed, f"{mod.__name__} imports {roots - allowed}")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, ("open", "print", "input", "exec", "eval"))
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "random":
                    self.assertEqual(node.attr, "Random")  # only a seeded generator
        tree = ast.parse(pathlib.Path(open_debate.__file__).read_text(encoding="utf-8"))
        seeded = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "Random"]
        self.assertEqual(len(seeded), 1)
        self.assertEqual(len(seeded[0].args), 1)  # never Random() without a seed


WRITTEN = "The snail is out of the well on day 8, because it tops out by day before it can slip."


class FinalWriter(unittest.TestCase):
    def agree(self, k=3, confs=(0.7, 0.95, 0.8), mode="standard", **kw):
        dr = Driver(self, make(k, mode=mode, write_final=True, **kw))
        texts = {i: f"Day 8, says seat {i}." for i in range(k)}
        dr.round({i: card("Day 8", conf=confs[i]) for i in range(k)}, "seat.r0", texts)
        return dr, texts

    def test_consensus_queues_one_writer_call_and_its_text_is_the_answer(self):
        dr, texts = self.agree()
        self.assertFalse(dr.d.is_done())
        self.assertEqual(dr.d.phase, "write")
        self.assertEqual(dr.d.chair_reserve_s(), 0.0)
        self.assertTrue(dr.of("consensus.reached")[0]["early"])  # the vote is posted before the writer
        self.assertEqual(dr.of("decision.final"), [])
        spec = dr.calls("seat.final", 1)[0]
        self.assertEqual((spec.model_id, spec.meta["seat"], spec.meta["kind"]), ("m1", 1, "answer"))
        self.assertEqual((spec.stream, spec.reasoning, spec.json_schema), (True, "off", None))
        self.assertEqual((spec.max_output_tokens, spec.max_reasoning_tokens), (500, 1200))
        self.assertIn(TASK, spec.messages[0]["content"])
        self.assertIn("You are Gemma", spec.messages[0]["content"])
        body = user_of(spec)
        self.assertIn("The agreed answer is:\nDay 8", body)
        self.assertIn("Day 8, says seat 0.", body)  # the transcript
        self.assertIn("Do not mention the council", body)
        started = dr.of("msg.started")[-1]
        self.assertEqual((started["kind"], started["seat_no"], started["turn_id"], started["call_id"]),
                         ("answer", 1, spec.call_id, spec.call_id))
        from council.chamber.executors import _parse_call_id
        self.assertEqual(_parse_call_id(spec.call_id), (None, None))
        dr.text(spec, WRITTEN + "\n")
        self.assertTrue(dr.d.is_done())
        decision = dr.d.decision()
        self.assertEqual((decision.outcome, decision.option_id, decision.final_text), ("consensus", "A1", WRITTEN))
        self.assertEqual(dr.of("msg.ended")[-1], {"turn_id": spec.call_id, "seat_no": 1, "text": WRITTEN,
                                                  "error": None})
        types = [t for t, _ in dr.events]
        self.assertEqual(types[-1], "decision.final")
        self.assertLess(types.index("consensus.reached"), len(types) - 3)
        self.assertEqual(types.count("msg.card"), 3)  # no card for the answer
        self.assertEqual(len(dr.d.chat_view()), 3)  # the answer is not a debate message
        self.assertEqual(dr.d.final_ballots()[1].final_answer, texts[1])
        self.assertEqual(dr.d.pending_calls(), [])

    def test_confidence_tie_goes_to_the_lowest_seat(self):
        dr, _ = self.agree(confs=(0.9, 0.9, 0.9))
        self.assertEqual(dr.calls("seat.final", 1)[0].meta["seat"], 0)

    def test_writer_failure_falls_back_and_keeps_the_decision(self):
        for how in ("timeout", "empty", "deadline"):
            dr, texts = self.agree()
            spec = dr.calls("seat.final", 1)[0]
            if how == "timeout":
                dr.fail(spec, "timeout")
            elif how == "empty":
                dr.text(spec, "   ")
            else:
                dr.take(dr.d.on_deadline(0.0))
                dr.text(spec, "late")  # ignored
            decision = dr.d.decision()
            self.assertEqual((decision.outcome, decision.option_id), ("consensus", "A1"), how)
            self.assertEqual(decision.final_text, "Day 8\n\n" + texts[1], how)
            error = {"timeout": "timeout", "empty": "invalid_output", "deadline": "cancelled"}[how]
            self.assertEqual(dr.of("msg.ended")[-1]["error"], error)
            self.assertEqual([t for t, _ in dr.events][-1], "decision.final")

    def test_deadline_already_passed_skips_the_writer(self):
        dr = Driver(self, make(3, mode=rounds(2), write_final=True))
        for spec in dr.messages(dr.calls("seat.r0", 3)).values():
            dr.obj(spec, card("Day 8", conf=0.3))  # unsure: round 1 starts
        dr.take(dr.d.on_deadline(0.0))
        decision = dr.d.decision()
        self.assertEqual(decision.outcome, "consensus")
        self.assertTrue(decision.final_text.startswith("Day 8\n\nMessage of seat"))
        self.assertNotIn("answer", [p["kind"] for p in dr.of("msg.started")])

    def test_consensus_in_a_later_round_also_goes_to_the_writer(self):
        dr = Driver(self, make(3, mode=rounds(2), write_final=True))
        dr.round({0: card("Day 8", conf=0.6), 1: card("Day 8", conf=0.6), 2: card("Day 4")}, "seat.r0")
        dr.merge(None)
        dr.round({0: card("Day 8", "A1", conf=0.6), 1: card("Day 8", "A1", conf=0.6),
                  2: card("Day 8", "A1", conf=0.99, changed=True, because="slip at night")}, "seat.r1")
        self.assertEqual(dr.d.phase, "write")
        self.assertFalse(dr.of("consensus.reached")[0]["early"])
        spec = dr.calls("seat.final", 1)[0]
        self.assertEqual((spec.meta["seat"], spec.meta["round_no"]), (2, 1))
        self.assertIn("[round 1]", user_of(spec))
        dr.text(spec, WRITTEN)
        self.assertEqual((dr.d.decision().final_text, dr.d.decision().rounds_run), (WRITTEN, 2))

    def test_write_final_false_keeps_the_old_behaviour(self):
        dr = Driver(self, make(3, write_final=False))
        texts = {i: f"Day 8, says seat {i}." for i in range(3)}
        dr.round({0: card("Day 8", conf=0.7), 1: card("Day 8", conf=0.95), 2: card("Day 8")}, "seat.r0", texts)
        self.assertTrue(dr.d.is_done())
        self.assertEqual(dr.d.pending_calls(), [])
        self.assertEqual(dr.d.decision().final_text, texts[1])
        self.assertFalse(OpenDebate.restore(dr.d.snapshot()).write_final)

    def test_keyed_task_keeps_its_key_and_still_gets_a_written_answer(self):
        dr = Driver(self, keyed(3, write_final=True))
        dr.round({i: kcard("B") for i in range(3)}, "seat.r0")
        spec = dr.calls("seat.final", 1)[0]
        self.assertIn("The agreed answer is:\nB", user_of(spec))
        dr.text(spec, WRITTEN)
        decision = dr.d.decision()
        self.assertEqual((decision.answer_key, decision.final_text), ("B", WRITTEN))

    def test_snapshot_in_the_write_phase(self):
        dr, _ = self.agree()
        spec = dr.calls("seat.final", 1)[0]
        snap = dr.d.snapshot()
        twin = OpenDebate.restore(json.loads(json.dumps(snap)))
        self.assertEqual(twin.phase, "write")
        self.assertEqual(twin.snapshot(), snap)
        again = twin.pending_calls()  # the call that was out is handed out again
        self.assertEqual([s.model_dump() for s in again], [spec.model_dump()])
        a, b = Driver(self, dr.d), Driver(self, twin)
        a.events, b.events = [], []
        a.text(spec, WRITTEN)
        b.text(again[0], WRITTEN)
        self.assertEqual(a.events, b.events)
        self.assertEqual(twin.decision(), dr.d.decision())
        self.assertEqual(twin.decision().final_text, WRITTEN)
        # and the deadline on a restored engine still ends with the fallback
        late = OpenDebate.restore(snap)
        late.on_deadline(0.0)
        self.assertTrue(late.decision().final_text.startswith("Day 8\n\n"))


class DeciderGuard(unittest.TestCase):
    def play(self, final_answer, objection=""):
        dr = Driver(self, make(2, mode=rounds(0), seed=1, write_final=True))
        texts = {0: "It is day 8: the slip is at night.", 1: "Day 4, by plain division."}
        dr.round({0: card("Day 8", conf=0.9), 1: card("Day 4", conf=0.5)}, "seat.r0", texts)
        dr.merge(None)
        spec = dr.calls("chair", 1)[0]
        self.assertEqual(spec.max_reasoning_tokens, 600)
        self.assertIn("never a\n  remark about objections", user_of(spec))
        dr.obj(spec, {"backs": "A1", "final_answer": final_answer, "objection": objection})
        self.assertEqual(dr.d.pending_calls(), [])  # the decider's answer is not rewritten
        return dr.d.decision(), texts

    def test_a_remark_instead_of_an_answer_is_replaced(self):
        decision, texts = self.play("No objection raised.")
        self.assertEqual((decision.outcome, decision.option_id), ("chair", "A1"))
        self.assertEqual(decision.final_text, "Day 8\n\n" + texts[0])

    def test_the_objection_copied_into_the_answer_is_replaced(self):
        said = "Gemma still holds that plain division gives day 4."
        decision, texts = self.play(said, " " + said.upper())
        self.assertEqual(decision.final_text, "Day 8\n\n" + texts[0])
        self.assertTrue(any("remaining objection" in n for n in decision.notes))

    def test_a_real_answer_is_kept(self):
        decision, _ = self.play("The snail is out on day 8, at the end of the climb.", "none")
        self.assertEqual(decision.final_text, "The snail is out on day 8, at the end of the climb.")

    def test_cards_get_thinking_room(self):
        dr = Driver(self, make(2))
        for spec in dr.messages(dr.calls("seat.r0", 2)).values():
            self.assertEqual((spec.max_output_tokens, spec.max_reasoning_tokens), (CARD_TOKENS, 600))


def keyed(k, n_rounds=1, answer_type="mcq", **kw):
    from council.bench.graders import normalize

    return make(k, rounds(n_rounds), answer_type=answer_type, normalize=normalize, **kw)


def kcard(key, **kw):
    out = card(kw.pop("stance", f"Option {key}"), **kw)
    if key is not None:
        out["answer_key"] = key
    return out


class BenchmarkKeys(unittest.TestCase):
    def test_seats_are_grouped_by_key_without_a_merge_call(self):
        dr = Driver(self, keyed(3))
        specs = dr.calls("seat.r0", 3)
        texts = {0: "It is B.", 1: "I say b.", 2: "Worked through.\nANSWER: B"}
        cards = dr.messages(specs, texts)
        for spec in cards.values():
            self.assertIn("answer_key", spec.json_schema["required"])
            self.assertIn("- answer_key:", user_of(spec))
        dr.obj(cards[0], kcard("B", stance="B, the queue"))
        dr.obj(cards[1], kcard("(b)", stance="the second option"))
        dr.obj(cards[2], kcard(None, stance="something else in words"))  # no key: ANSWER line
        self.assertTrue(dr.d.is_done())
        self.assertEqual(dr.calls(), [])  # no clerk.merge
        self.assertEqual(dr.groups(), {"A1": ["s0", "s1", "s2"]})
        decision = dr.d.decision()
        self.assertEqual((decision.outcome, decision.answer_key, decision.option_id), ("consensus", "B", "A1"))
        self.assertEqual([o.summary for o in dr.d.options()], ["B"])
        self.assertEqual({m.card.backs for m in dr.d.messages()}, {"A1"})

    def test_split_keys_go_to_round_one_and_a_seat_moves_by_key(self):
        dr = Driver(self, keyed(3, 1))
        dr.round({0: kcard("B"), 1: kcard("B"), 2: kcard("C")}, "seat.r0")
        self.assertEqual(dr.groups(), {"A1": ["s0", "s1"], "A2": ["s2"]})
        self.assertEqual(dr.d.phase, "r1")  # straight to round 1, no merge phase
        # Seat 2 says "backs A2" but its key is B: the key counts.
        dr.round({0: kcard("B", backs="A1"), 1: kcard("B", backs="A1"), 2: kcard("B", backs="A2")}, "seat.r1")
        self.assertEqual(dr.groups(), {"A1": ["s0", "s1", "s2"]})
        self.assertEqual(dr.d.decision().answer_key, "B")

    def test_no_key_at_all_follows_backs_then_stays(self):
        dr = Driver(self, keyed(3, 2))
        dr.round({0: kcard("B"), 1: kcard("C"), 2: kcard(None)}, "seat.r0")
        self.assertEqual(dr.groups(), {"A1": ["s0"], "A2": ["s1"]})  # seat 2 is not on the table
        dr.round({0: kcard("B", backs="A1"), 1: kcard("C", backs="A2"), 2: kcard(None, backs="A2")}, "seat.r1")
        self.assertEqual(dr.groups(), {"A2": ["s1", "s2"], "A1": ["s0"]})
        self.assertEqual(dr.d.final_ballots()[2].choice, "A2")

    def test_the_deciders_key_is_the_answer_key(self):
        dr = Driver(self, keyed(2, 0, answer_type="numeric"))
        dr.round({0: kcard("8"), 1: kcard("7.0")}, "seat.r0")
        self.assertEqual(dr.groups(), {"A1": ["s0"], "A2": ["s1"]})
        spec = dr.calls("chair", 1)[0]
        self.assertIn("answer_key", spec.json_schema["required"])
        self.assertIn("- answer_key:", user_of(spec))
        dr.obj(spec, {"backs": "A1", "final_answer": "It is 7.", "objection": "", "answer_key": "7"})
        decision = dr.d.decision()
        self.assertEqual((decision.outcome, decision.answer_key, decision.option_id), ("chair", "7", "A2"))

    def test_free_form_tasks_are_unchanged(self):
        dr = Driver(self, make(3, rounds(1), answer_type="free"))
        specs = dr.calls("seat.r0", 3)
        cards = dr.messages(specs)
        for spec in cards.values():
            self.assertNotIn("answer_key", spec.json_schema["properties"])
            self.assertNotIn("answer_key", user_of(spec))
        for seat, spec in cards.items():
            dr.obj(spec, card(f"Stance {seat}"))
        self.assertEqual(dr.d.phase, "merge")
        dr.merge([["s0", "s1", "s2"]])
        self.assertIsNone(dr.d.decision().answer_key)


class SeedAndSwap(unittest.TestCase):
    def test_seed_position_skips_the_message_call(self):
        dr = Driver(self, keyed(3))
        self.assertTrue(dr.d.seed_position(0, "Solo working.\nANSWER: B"))
        self.assertTrue(dr.d.seed_position(1, "Solo working.\nANSWER: B"))
        self.assertFalse(dr.d.seed_position(1, "again"))
        self.assertFalse(dr.d.seed_position(2, "  "))
        dr.take(dr.d.take_events())
        specs = dr.calls()
        self.assertEqual(sorted((s.purpose, s.meta["seat"]) for s in specs),
                         [("seat.card", 0), ("seat.card", 1), ("seat.r0", 2)])
        self.assertEqual([p["text"] for p in dr.of("msg.ended")], ["Solo working.\nANSWER: B"] * 2)
        for spec in specs:
            if spec.purpose == "seat.card":
                self.assertIn("ANSWER: B", user_of(spec))
                dr.fail(spec, "invalid_output")  # the fallback card still finds the key
            else:
                dr.text(spec, "ANSWER: B")
        dr.obj(dr.calls("seat.card", 1)[0], kcard("B"))
        self.assertEqual(dr.groups(), {"A1": ["s0", "s1", "s2"]})

    def test_failed_opening_call_gets_an_alternate_once(self):
        lu = lineup(3)
        lu.alternates = ["alt1", "alt2"]
        dr = Driver(self, OpenDebate("run1", TASK, TaskProfile(), lu, rounds(1)))
        specs = {s.meta["seat"]: s for s in dr.calls("seat.r0", 3)}
        dr.fail(specs[1], "server_error")
        swap = dr.of(E.SEAT_ASSIGNED)[-1]
        self.assertEqual((swap["seat_no"], swap["model_id"], swap["replaces_model_id"]), (1, "alt1", "m1"))
        self.assertEqual(dr.of("msg.ended")[-1]["error"], "server_error")
        again = dr.calls("seat.r0", 1)[0]
        self.assertEqual((again.model_id, again.meta["seat"]), ("alt1", 1))
        started = dr.of("msg.started")[-1]
        self.assertEqual((started["call_id"], started["turn_id"], started["model_id"]),
                         (again.call_id, again.call_id, "alt1"))
        self.assertEqual(len([m for m in dr.d.messages() if m.seat_no == 1]), 1)
        again_d = OpenDebate.restore(dr.d.snapshot())
        self.assertEqual({c.meta["seat"]: c.model_id for c in again_d.pending_calls()}[1], "alt1")
        dr.fail(again, "server_error")  # no second swap
        self.assertEqual(len(dr.of(E.SEAT_ASSIGNED)), 1)
        self.assertEqual(dr.calls(), [])
        dr.fail(specs[0], "timeout")  # a timeout is not a model fault: no swap
        self.assertEqual(len(dr.of(E.SEAT_ASSIGNED)), 1)

    def test_open_events_are_in_the_contract_and_started_carries_the_call_id(self):
        dr = Driver(self, make(3))
        specs = dr.calls("seat.r0", 3)
        self.assertEqual([p["call_id"] for p in dr.of(E.MSG_STARTED)], [s.call_id for s in specs])
        for seat, spec in dr.messages(specs).items():
            dr.obj(spec, card("Day 8"))
        dr.d.set_lie_metrics({specs[0].call_id: {"score": 0.2, "level": "flag", "reasons": ["x"]}})
        dr.take(dr.d.take_events())
        for type_ in (E.MSG_STARTED, E.MSG_ENDED, E.MSG_CARD, E.MSG_LIE, E.TABLE_TALLY):
            self.assertIn(type_, E.PAYLOADS)
            self.assertTrue(dr.of(type_), type_)
        self.assertEqual(
            set(dr.of(E.TABLE_TALLY)[-1]),
            {"round", "groups", "leading", "agree", "seats", "needed", "reached", "valid", "quorum",
             "unconfirmed", "basis"},
        )


class Outliers(unittest.TestCase):
    """The council questions a seat that is far from the rest, inside the normal rounds."""

    STRICT = ConsensusConfig(threshold=1.0)
    R0 = {0: "Day 8", 1: "Day 8", 2: "Day 8", 3: "Day 8", 4: "Day 8", 5: "Day 4"}
    DECIDE = {"backs": "A1", "final_answer": "The snail is out of the well on day 8.", "objection": ""}

    def start(self, n_rounds=3, r0=None, **kw):
        kw.setdefault("cfg", self.STRICT)
        dr = Driver(self, make(6, mode=rounds(n_rounds), **kw))
        dr.round({s: card(v) for s, v in (r0 or self.R0).items()}, "seat.r0")
        dr.merge(None)
        return dr

    def finish(self, dr, specs, backs, texts=None, to=None):
        """Answer a reply round. `backs` = {seat: answer id}, `to` = {seat: [seat ids]}."""
        stance = {"A1": "Day 8", "A2": "Day 4", "A3": "Day 3"}
        for seat, spec in dr.messages(specs, texts).items():
            dr.obj(spec, card(stance[backs[seat]], backs=backs[seat], to=(to or {}).get(seat, "all")))

    def log(self, dr, type_):
        return [p for t, p in dr.d.outlier_events() if t == type_]

    def test_one_outlier_is_named_questioned_and_moves(self):
        dr = self.start()
        self.assertEqual(dr.d.outliers(), [5])
        self.assertEqual(self.log(dr, "outlier.named"), [
            {"round": 0, "seats": [5], "leading": "A1", "their_answers": {"5": "A2"}}])
        if "outlier.named" not in E.PAYLOADS:  # the bus refuses unknown types: not in take_events()
            self.assertEqual(dr.of("outlier.named"), [])
        specs = {s.meta["seat"]: s for s in dr.calls("seat.r1", 6)}
        for seat in range(5):
            body = user_of(specs[seat])
            self.assertIn(
                "Granite is far from the rest of the council: it backs A2 (Day 4) while most back "
                "A1 (Day 8).", body)
            self.assertIn("Question it directly. Address Granite by name and ask ONE specific question", body)
            self.assertIn("Granite (being questioned)", body)
            self.assertNotIn("Now write your reply", body)
        mine = user_of(specs[5])
        self.assertIn("The council is questioning your position. The questions put to you:", mine)
        self.assertIn("no member has put a question to you by name yet", mine)
        self.assertIn("Granite (you) (being questioned)", mine)
        self.assertNotIn("is far from the rest", mine)

        texts = {s: f"Granite, question {s}: where does the snail slip back on day 4?" for s in range(5)}
        texts[5] = "Day 4 stands, the snail is at 4 m."
        stay = {0: "A1", 1: "A1", 2: "A1", 3: "A1", 4: "A1", 5: "A2"}
        self.finish(dr, list(specs.values()), stay, texts, to={s: ["s5"] for s in range(5)})
        self.assertEqual(dr.d.outliers(), [5])
        specs = {s.meta["seat"]: s for s in dr.calls("seat.r2", 6)}
        mine = user_of(specs[5])
        for seat in range(5):
            self.assertIn(f"- {NAMES[seat]} (round 1): Granite, question {seat}: where does", mine)
        self.assertIn("Answer EVERY question directly, one by one, by the asker's name.", mine)
        self.assertIn("Address Granite by name", user_of(specs[0]))

        self.finish(dr, list(specs.values()), {s: "A1" for s in range(6)})
        self.assertEqual(self.log(dr, "outlier.resolved"), [{"seat": 5, "outcome": "moved", "round": 2}])
        self.assertEqual(dr.d.outliers(), [])
        decision = dr.d.decision()
        self.assertEqual((decision.outcome, decision.option_id, decision.minority_report),
                         ("consensus", "A1", []))
        self.assertIn("Granite (seat 5) was questioned as an outlier: moved in round 2", decision.notes)

    def test_council_moves_to_the_outlier_vindicated(self):
        dr = self.start(1)
        self.finish(dr, dr.calls("seat.r1", 6), {0: "A2", 1: "A2", 2: "A1", 3: "A1", 4: "A1", 5: "A2"})
        self.assertEqual(self.log(dr, "outlier.resolved"), [{"seat": 5, "outcome": "vindicated", "round": 1}])
        self.assertEqual(dr.d.outliers(), [])
        self.assertEqual(dr.d.phase, "chair")  # 3-3: no outlier, so no extra round
        dr.obj(dr.calls("chair", 1)[0], self.DECIDE)
        self.assertEqual(len(self.log(dr, "outlier.resolved")), 1)

    def test_nobody_moves_no_extension_held(self):
        dr = self.start(1)
        self.finish(dr, dr.calls("seat.r1", 6), {s: "A1" if s < 5 else "A2" for s in range(6)})
        self.assertEqual(dr.d.phase, "chair")
        self.assertEqual(self.log(dr, "outlier.resolved"), [])
        dr.obj(dr.calls("chair", 1)[0], self.DECIDE)
        decision = dr.d.decision()
        self.assertEqual((decision.outcome, decision.rounds_run), ("chair", 2))
        self.assertEqual(self.log(dr, "outlier.resolved"), [{"seat": 5, "outcome": "held", "round": 1}])
        self.assertEqual([(m.seats, m.position, m.option_id) for m in decision.minority_report],
                         [([5], "Day 4", "A2")])
        self.assertIn("Granite (seat 5) was questioned as an outlier: held in round 1", decision.notes)

    def test_five_to_one_unconfirmed_then_consensus_holds_the_outlier(self):
        dr = Driver(self, make(6, mode=rounds(2)))  # default threshold: 5 of 6 is a consensus
        dr.round({s: card(v, conf=0.4) for s, v in self.R0.items()}, "seat.r0")
        dr.merge(None)
        self.assertTrue(dr.of("table.tally")[-1]["unconfirmed"])
        self.assertEqual(dr.d.outliers(), [5])
        specs = dr.calls("seat.r1", 6)
        self.assertIn("Address Granite by name", user_of(specs[0]))
        self.finish(dr, specs, {s: "A1" if s < 5 else "A2" for s in range(6)})
        decision = dr.d.decision()
        self.assertEqual(decision.outcome, "consensus")
        self.assertEqual(self.log(dr, "outlier.resolved"), [{"seat": 5, "outcome": "held", "round": 1}])
        self.assertEqual([m.seats for m in decision.minority_report], [[5]])

    def test_extra_rounds_while_someone_moves_at_most_two(self):
        dr = self.start(1)
        self.finish(dr, dr.calls("seat.r1", 6), {0: "A1", 1: "A1", 2: "A1", 3: "A1", 4: "A2", 5: "A2"})
        self.assertEqual(dr.d.phase, "r2")  # the planned rounds are used up: first extra round
        self.assertEqual(dr.d.outliers(), [4, 5])
        self.assertEqual(self.log(dr, "outlier.named")[-1], {
            "round": 1, "seats": [4, 5], "leading": "A1", "their_answers": {"4": "A2", "5": "A2"}})
        specs = {s.meta["seat"]: s for s in dr.calls("seat.r2", 6)}
        body = user_of(specs[0])
        self.assertIn("Mistral is far from the rest of the council", body)
        self.assertIn("Granite is far from the rest of the council", body)
        self.assertIn("Address Mistral and Granite (one question each) by name", body)
        self.assertIn("The council is questioning your position", user_of(specs[4]))
        self.assertIn("The council is questioning your position", user_of(specs[5]))
        self.finish(dr, list(specs.values()), {s: "A1" if s < 5 else "A2" for s in range(6)})
        self.assertEqual(self.log(dr, "outlier.resolved"), [{"seat": 4, "outcome": "moved", "round": 2}])
        self.assertEqual(dr.d.phase, "r3")  # seat 4 moved: second extra round
        self.finish(dr, dr.calls("seat.r3", 6), {0: "A1", 1: "A1", 2: "A1", 3: "A1", 4: "A2", 5: "A2"})
        self.assertEqual(dr.d.phase, "chair")  # it moved again, but two extra rounds is the limit
        dr.obj(dr.calls("chair", 1)[0], self.DECIDE)
        self.assertEqual(dr.d.decision().rounds_run, 4)
        self.assertEqual([p["outcome"] for p in self.log(dr, "outlier.resolved")], ["moved", "held", "held"])

    def test_extension_stops_when_nothing_moved(self):
        dr = self.start(1)
        self.finish(dr, dr.calls("seat.r1", 6), {0: "A1", 1: "A1", 2: "A1", 3: "A1", 4: "A2", 5: "A2"})
        same = {0: "A1", 1: "A1", 2: "A1", 3: "A1", 4: "A2", 5: "A2"}
        self.finish(dr, dr.calls("seat.r2", 6), same)
        self.assertEqual(dr.d.phase, "chair")

    def test_two_outliers_on_two_answers(self):
        dr = self.start(r0={0: "Day 8", 1: "Day 8", 2: "Day 8", 3: "Day 8", 4: "Day 4", 5: "Day 3"})
        self.assertEqual(dr.d.outliers(), [4, 5])
        self.assertEqual(self.log(dr, "outlier.named")[0]["their_answers"], {"4": "A2", "5": "A3"})
        body = user_of(dr.calls("seat.r1", 6)[0])
        self.assertIn("Mistral is far from the rest of the council: it backs A2 (Day 4)", body)
        self.assertIn("Granite is far from the rest of the council: it backs A3 (Day 3)", body)

    def test_no_outlier_on_an_even_split(self):
        dr = self.start(r0={0: "Day 8", 1: "Day 8", 2: "Day 8", 3: "Day 4", 4: "Day 4", 5: "Day 4"})
        self.assertEqual((dr.d.outliers(), dr.d.outlier_events()), ([], []))
        body = user_of(dr.calls("seat.r1", 6)[0])
        self.assertIn("Now write your reply", body)
        self.assertNotIn("being questioned", body)

    def test_switched_off(self):
        dr = self.start(1, question_outliers=False)
        self.assertEqual((dr.d.outliers(), dr.d.outlier_events()), ([], []))
        specs = dr.calls("seat.r1", 6)
        for spec in specs:
            self.assertIn("Now write your reply", user_of(spec))
            self.assertNotIn("being questioned", user_of(spec))
        self.finish(dr, specs, {0: "A1", 1: "A1", 2: "A1", 3: "A1", 4: "A2", 5: "A2"})
        self.assertEqual(dr.d.phase, "chair")  # no extra round
        dr.obj(dr.calls("chair", 1)[0], self.DECIDE)
        self.assertEqual(dr.d.outlier_events(), [])
        self.assertFalse(OpenDebate.restore(dr.d.snapshot()).question_outliers)

    def test_snapshot_restore_mid_questioning(self):
        dr = self.start(1)
        snap = json.loads(json.dumps(dr.d.snapshot()))  # round 1 is queued, the outlier is named
        specs = dr.calls("seat.r1", 6)
        twin = Driver(self, OpenDebate.restore(snap))
        self.assertEqual(twin.d.outliers(), [5])
        self.assertEqual(twin.d.outlier_events(), dr.d.outlier_events())
        again = twin.calls("seat.r1", 6)
        self.assertEqual([user_of(s) for s in again], [user_of(s) for s in specs])
        self.finish(twin, again, {0: "A1", 1: "A1", 2: "A1", 3: "A1", 4: "A2", 5: "A2"})
        self.assertEqual(twin.d.phase, "r2")
        # the extra round and the open cases survive a second snapshot
        late = Driver(self, OpenDebate.restore(json.loads(json.dumps(twin.d.snapshot()))))
        self.assertEqual((late.d.phase, late.d.outliers()), ("r2", [4, 5]))
        self.finish(late, late.calls("seat.r2", 6), {s: "A1" for s in range(6)})
        self.assertEqual(late.d.decision().outcome, "consensus")
        self.assertEqual(self.log(late, "outlier.resolved"), [
            {"seat": 4, "outcome": "moved", "round": 2}, {"seat": 5, "outcome": "moved", "round": 2}])


if __name__ == "__main__":
    unittest.main()
