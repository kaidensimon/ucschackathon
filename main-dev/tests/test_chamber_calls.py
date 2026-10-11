import unittest

from council.chamber.calls import (
    ballot_schema,
    build_chair_call,
    build_ratify_call,
    build_seat_call,
    critique_schema,
    draft_schema,
    parse_position,
)
from council.core.schemas import MODE_DEFAULTS, SeatAssignment


def _resolve(schema, node):
    if "$ref" in node:
        return schema["$defs"][node["$ref"].rsplit("/", 1)[-1]]
    return node


class CallsTest(unittest.TestCase):
    def test_draft_schema(self):
        self.assertIn("answer", draft_schema()["properties"])

    def test_critique_schema(self):
        s = critique_schema(["A", "B"], ["f1", "c1"])
        review = _resolve(s, s["properties"]["reviews"]["items"])
        self.assertEqual(review["properties"]["target"]["enum"], ["A", "B"])
        self.assertEqual(s["properties"]["position"]["enum"], ["keep", "revise", "adopt:A", "adopt:B"])
        self.assertEqual(s["properties"]["changed_because"]["items"]["enum"], ["f1", "c1"])

    def test_critique_free_refs(self):
        s = critique_schema(["A"], [])
        self.assertNotIn("enum", s["properties"]["changed_because"]["items"])

    def test_ballot_schema(self):
        s = ballot_schema(["o1", "o2"], ["x1"], ["f1"])
        self.assertEqual(s["properties"]["choice"]["enum"], ["o1", "o2"])
        self.assertEqual(s["properties"]["ranking"]["items"]["enum"], ["o1", "o2"])
        vote = _resolve(s, s["properties"]["crux_votes"]["items"])
        self.assertEqual(vote["properties"]["crux_id"]["enum"], ["x1"])

    def test_seat_call(self):
        seat = SeatAssignment(seat_no=2, model_id="m1")
        caps = {"max_output": 500, "max_reasoning": 800, "temperature": 0.4}
        c = build_seat_call(
            "r1", "run9", seat, "TASKTEXT", "BRIEF", "REC", "LENS",
            {"own_draft": "mine", "anonymized_drafts": [1], "cruxes": ""},
            critique_schema(["A"], []), MODE_DEFAULTS["standard"], caps, 7,
        )
        self.assertEqual(c.call_id, "run9:r1:2")
        self.assertEqual(c.purpose, "seat.r1")
        self.assertEqual(c.reasoning, "council")
        self.assertTrue(c.stream)
        self.assertEqual(c.priority, "interactive")
        self.assertEqual(c.max_output_tokens, 500)
        self.assertEqual(c.max_reasoning_tokens, 800)
        self.assertEqual(c.temperature, 0.4)
        self.assertEqual(c.seed, 7)
        self.assertEqual(c.messages[0]["role"], "system")
        self.assertIn("TASKTEXT", c.messages[0]["content"])
        self.assertIn("LENS", c.messages[0]["content"])
        self.assertIn("mine", c.messages[1]["content"])

    def test_seat_call_notes(self):
        seat = SeatAssignment(seat_no=1, model_id="m1")
        args = ("r0", "run9", seat, "TASKTEXT", "BRIEF", "REC", "LENS", {}, draft_schema(),
                MODE_DEFAULTS["standard"], {"max_output": 500}, 7)
        plain = build_seat_call(*args)
        self.assertEqual(build_seat_call(*args, notes="").messages, plain.messages)
        noted = build_seat_call(*args, notes="Corrections from earlier sessions in this project:\n- NOTE1")
        system = noted.messages[0]["content"]
        self.assertTrue(system.startswith(plain.messages[0]["content"]))
        self.assertTrue(system.endswith("- NOTE1"))
        self.assertLess(system.index("REC"), system.index("NOTE1"))
        self.assertEqual(noted.messages[1], plain.messages[1])
        self.assertEqual(noted.call_id, plain.call_id)

    def test_chair_ratify(self):
        seat = SeatAssignment(seat_no=0, model_id="m1")
        mode = MODE_DEFAULTS["standard"]
        ch = build_chair_call("r", seat, "t", "", "", "", {"transcript": "T"}, None, mode,
                              {"max_output": 900, "max_reasoning": 1500, "temperature": 0.2}, 1)
        self.assertEqual(ch.purpose, "chair")
        self.assertEqual(ch.call_id, "r:chair:0")
        ra = build_ratify_call("r", seat, "t", "", "", "", {"task": "t", "final_text": "F"}, None, mode,
                               {"max_output": 60, "max_reasoning": 0, "temperature": 0.0}, 1)
        self.assertEqual(ra.purpose, "ratify")
        self.assertEqual(ra.reasoning, "off")
        self.assertEqual(ra.call_id, "r:ratify:0")
        self.assertIn("F", ra.messages[1]["content"])

    def test_user_message_is_self_sufficient(self):
        seat = SeatAssignment(seat_no=1, model_id="m1")
        mode = MODE_DEFAULTS["standard"]
        c = build_seat_call("r0", "r", seat, "WHAT IS 2+2", "B", "R", "L", {}, draft_schema(), mode, {}, 1)
        user = c.messages[1]["content"]
        self.assertTrue(user.startswith("TASK\nWHAT IS 2+2\n\nWHAT TO DO NOW\n"))
        self.assertLess(user.index("WHAT TO DO NOW"), user.index("OUTPUT"))
        self.assertIn("Answer the TASK itself", user)
        self.assertIn("actual answer to the TASK itself", user)
        self.assertTrue(user.endswith("Now answer the TASK."))

    def test_every_round_restates_task(self):
        seat = SeatAssignment(seat_no=1, model_id="m1")
        mode = MODE_DEFAULTS["standard"]
        for rnd in ("r0", "r1", "r2", "r3"):
            c = build_seat_call(rnd, "r", seat, "TASKX", "", "", "", {}, None, mode, {}, 1)
            user = c.messages[1]["content"]
            with self.subTest(rnd=rnd):
                self.assertTrue(user.startswith("TASK\nTASKX"))
                self.assertIn("TASK", user.splitlines()[-1])
        ch = build_chair_call("r", seat, "TASKX", "", "", "", {"transcript": "T"}, None, mode, {}, 1)
        ra = build_ratify_call("r", seat, "TASKX", "", "", "", {"final_text": "F"}, None, mode, {}, 1)
        for c in (ch, ra):
            self.assertTrue(c.messages[1]["content"].startswith("TASK\nTASKX"))

    def test_ratify_task_falls_back_to_body(self):
        seat = SeatAssignment(seat_no=1, model_id="m1")
        ra = build_ratify_call("r", seat, "", "", "", "", {"task": "FROMBODY", "final_text": "F"}, None,
                               MODE_DEFAULTS["standard"], {}, 1)
        self.assertTrue(ra.messages[1]["content"].startswith("TASK\nFROMBODY"))

    def test_parse_position(self):
        self.assertEqual(parse_position("keep"), ("keep", None))
        self.assertEqual(parse_position("revise"), ("revise", None))
        self.assertEqual(parse_position("adopt:B"), ("adopt", "B"))


if __name__ == "__main__":
    unittest.main()
