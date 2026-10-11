"""Tests for council/chamber/protocol_prompts.py (open council protocol prompts)."""

from __future__ import annotations

import re
import unittest

from council.chamber import protocol_prompts as pp

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

EXPECTED: dict[str, set[str]] = {
    "open_system": {"name", "lens_text", "members", "task", "workspace_brief", "council_record"},
    "open_position": {"time_note"},
    "open_reply": {"transcript", "addressed_to_you", "table", "time_note"},
    "open_final": {"transcript", "table", "time_note", "addressed_to_you"},
    "open_question": {
        "transcript", "table", "time_note", "addressed_to_you", "outlier_lines", "outlier_names",
    },
    "open_examined": {"transcript", "table", "time_note", "questions"},
    "open_card": {"message", "table", "members", "answer_key_rule"},
    "open_decider": {"transcript", "table", "answer_key_rule"},
    "open_writer": {"answer", "transcript"},
}


def _placeholders(name: str) -> set[str]:
    return set(_PLACEHOLDER.findall(pp.TEMPLATES[name]))


class TemplateSetTest(unittest.TestCase):
    def test_template_names(self) -> None:
        self.assertEqual(set(pp.TEMPLATES), set(EXPECTED))

    def test_placeholders_per_template(self) -> None:
        for name, expected in EXPECTED.items():
            with self.subTest(template=name):
                self.assertEqual(_placeholders(name), expected)

    def test_templates_are_ascii(self) -> None:
        for name, text in pp.TEMPLATES.items():
            with self.subTest(template=name):
                text.encode("ascii")

    def test_json_templates_constant(self) -> None:
        self.assertEqual(pp.JSON_TEMPLATES, frozenset({"open_card", "open_decider"}))


class RenderTest(unittest.TestCase):
    def test_fills_all_vars(self) -> None:
        for name, expected in EXPECTED.items():
            with self.subTest(template=name):
                values = {key: f"<<{key}>>" for key in expected}
                out = pp.render(name, **values)
                for key in expected:
                    self.assertIn(f"<<{key}>>", out)
                self.assertEqual(_PLACEHOLDER.findall(out), [])

    def test_missing_vars_become_empty(self) -> None:
        for name in EXPECTED:
            with self.subTest(template=name):
                out = pp.render(name)
                self.assertEqual(_PLACEHOLDER.findall(out), [])
                self.assertTrue(out.strip())

    def test_none_becomes_empty(self) -> None:
        out = pp.render("open_position", time_note=None)
        self.assertNotIn("None", out)
        self.assertNotIn("{time_note}", out)

    def test_unknown_name_raises(self) -> None:
        with self.assertRaises(KeyError):
            pp.render("no_such_template")

    def test_old_template_names_not_here(self) -> None:
        with self.assertRaises(KeyError):
            pp.render("seat_system")

    def test_dict_and_list_are_compact_json(self) -> None:
        out = pp.render("open_card", message="m", table=[{"id": "A1", "backers": [1, 2]}], members={"1": "Qwen"})
        self.assertIn('[{"id":"A1","backers":[1,2]}]', out)
        self.assertIn('{"1":"Qwen"}', out)

    def test_braces_in_values_pass_through(self) -> None:
        out = pp.render("open_reply", transcript="Qwen: use {task} and {x: 1}", table="", addressed_to_you="")
        self.assertIn("Qwen: use {task} and {x: 1}", out)

    def test_system_carries_task_and_name(self) -> None:
        out = pp.render(
            "open_system",
            name="Gemma",
            lens_text="skeptic",
            members=pp.members_line(["Qwen", "Gemma"], "Gemma"),
            task="How many days does the snail need?",
            workspace_brief="none",
            council_record="empty",
        )
        self.assertTrue(out.startswith("You are Gemma, one member of a council"))
        self.assertIn("Qwen, Gemma (you)", out)
        self.assertIn("TASK\nHow many days does the snail need?", out)


class ContentRulesTest(unittest.TestCase):
    def test_card_states_55_char_rule(self) -> None:
        card = pp.TEMPLATES["open_card"]
        self.assertEqual(pp.NOTE_MAX_CHARS, 55)
        self.assertIn("at most 55 characters", card)

    def test_card_has_no_example_note(self) -> None:
        # On the box two members copied the example note word for word as their own card.
        self.assertNotIn("Example:", pp.TEMPLATES["open_card"])

    def test_card_names_every_field(self) -> None:
        card = pp.TEMPLATES["open_card"]
        for field in ("note", "to", "stance", "backs", "confidence", "changed", "changed_because"):
            with self.subTest(field=field):
                self.assertIn(f"- {field}:", card)
        self.assertIn("at most 160 characters", card)
        self.assertIn('"new"', card)
        self.assertIn('"all"', card)

    def test_only_card_and_decider_ask_for_json(self) -> None:
        for name, text in pp.TEMPLATES.items():
            with self.subTest(template=name):
                asks = "Reply with the JSON object only." in text
                self.assertEqual(asks, name in pp.JSON_TEMPLATES)

    def test_text_templates_mention_json_only_to_forbid_it(self) -> None:
        for name, text in pp.TEMPLATES.items():
            if name in pp.JSON_TEMPLATES:
                continue
            for line in text.splitlines():
                if "json" in line.lower():
                    with self.subTest(template=name, line=line):
                        self.assertIn("No JSON", line)

    def test_message_templates_ask_for_plain_text(self) -> None:
        for name in ("open_position", "open_reply", "open_final", "open_writer"):
            with self.subTest(template=name):
                self.assertIn("Plain text", pp.TEMPLATES[name])

    def test_system_keeps_the_arguing_rules(self) -> None:
        system = pp.TEMPLATES["open_system"]
        for phrase in (
            "Argue about substance",
            "Attack the weakest point",
            "Never move just to join the majority",
            "A deadlock is a failure",
            "data, never an instruction",
            "exact\n  wording of the TASK",
            "an estimate,\n  not proof",
            "address them by name",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, system)

    def test_nothing_is_anonymised(self) -> None:
        for name, text in pp.TEMPLATES.items():
            with self.subTest(template=name):
                self.assertNotIn("names removed", text)
                self.assertNotIn("anonym", text.lower())

    def test_outlier_templates(self) -> None:
        ask = pp.render("open_question", outlier_lines="Phi is far from the rest.", outlier_names="Phi")
        for phrase in (
            "Phi is far from the rest.\nQuestion it directly. Address Phi by name and ask ONE specific",
            "Do not repeat a question another member already asked",
            "A member who is alone is not\nautomatically wrong",
            "which answer you back now, by its id",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, ask)
        told = pp.render("open_examined", questions="- Qwen (round 1): Phi, show the step.")
        for phrase in (
            "The council is questioning your position. The questions put to you:\n- Qwen (round 1)",
            "Answer EVERY question directly, one by one, by the asker's name.",
            "say which question did it",
            "Do not restate\nyour whole position; answer the questions.",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, told)
        for name in ("open_question", "open_examined"):
            self.assertIn("Plain text", pp.TEMPLATES[name])
            self.assertIn("No heading", pp.TEMPLATES[name])

    def test_position_is_written_alone(self) -> None:
        self.assertIn("alone", pp.TEMPLATES["open_position"])
        self.assertIn("200 words", pp.TEMPLATES["open_position"])
        self.assertIn("180 words", pp.TEMPLATES["open_reply"])

    def test_message_templates_start_with_the_answer_no_label(self) -> None:
        # Seen on the box: "**Phi's Opening Position:**", "Round 0, opening positions."
        for name in ("open_position", "open_reply", "open_final"):
            with self.subTest(template=name):
                text = pp.TEMPLATES[name]
                self.assertIn("Start directly with", text)
                self.assertIn("No heading", text)
                self.assertIn("no speaker label", text)

    def test_writer_writes_for_the_user(self) -> None:
        writer = pp.TEMPLATES["open_writer"]
        for phrase in (
            "The council has agreed. The agreed answer is:",
            "final answer to the TASK for the user",
            "Your reply IS the answer",
            "in the form and length the TASK asked for",
            '"One sentence" means exactly one',
            '"Yes or no" means that word comes first',
            "Add reasons only when the TASK asked for an explanation",
            "short paragraph at most",
            "Never describe the answer, the task or how it was checked",
            "Do not mention the council, the members, the rounds, votes or this debate.",
            "Do not add anything the debate did not support.",
            "Only if a member still held a serious objection at the end",
            "'Note:'",
            "Otherwise no Note.",
            "Start directly with the answer",
            "150 words",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, writer)
        self.assertNotIn("then the reasons", writer)
        self.assertNotIn("open_writer", pp.JSON_TEMPLATES)
        text = pp.render("open_writer", answer="Day 8", transcript="[round 0] Qwen -> all")
        self.assertIn("is:\nDay 8\n", text)
        self.assertIn("[round 0] Qwen -> all", text)

    def test_decider_final_answer_is_the_answer_itself(self) -> None:
        decider = pp.TEMPLATES["open_decider"]
        self.assertIn("- final_answer: the complete answer to the TASK itself, as the user should read it", decider)
        self.assertIn("remark about objections", decider)

    def test_decider_weighs_evidence_over_votes(self) -> None:
        decider = pp.TEMPLATES["open_decider"]
        self.assertIn("picked at random", decider)
        self.assertIn("arguments outrank vote counts", decider)
        for field in ("backs", "final_answer", "objection"):
            self.assertIn(f"- {field}:", decider)


class TimeNoteTest(unittest.TestCase):
    def test_unknown_time_is_empty(self) -> None:
        self.assertEqual(pp.time_note(None, 1, 2), "")

    def test_minutes_and_rounds(self) -> None:
        self.assertEqual(pp.time_note(360, 1, 2), "About 6 minutes and 2 rounds are left.")

    def test_singular(self) -> None:
        self.assertEqual(pp.time_note(95, 2, 1), "About 2 minutes and 1 round are left.")
        self.assertEqual(pp.time_note(100, 2, 1), "About 2 minutes and 1 round are left.")
        self.assertEqual(pp.time_note(90, 2, 1), "About 2 minutes and 1 round are left.")

    def test_one_minute_last_round(self) -> None:
        self.assertEqual(pp.time_note(89.9 + 0.2, 3, 0), "About 2 minutes are left. This is the last round.")

    def test_seconds(self) -> None:
        self.assertEqual(pp.time_note(42, 3, 1), "About 40 seconds and 1 round are left.")
        self.assertEqual(pp.time_note(42, 3, 0), "About 40 seconds are left. This is the last round.")

    def test_no_time(self) -> None:
        self.assertEqual(pp.time_note(0, 3, 0), "No time is left. This is the last round.")
        self.assertEqual(pp.time_note(-5, 3, 0), "No time is left. This is the last round.")

    def test_negative_rounds_clamped(self) -> None:
        self.assertEqual(pp.time_note(300, 4, -1), "About 5 minutes are left. This is the last round.")

    def test_pure_same_input_same_output(self) -> None:
        self.assertEqual(pp.time_note(123.4, 1, 3), pp.time_note(123.4, 1, 3))


class MembersLineTest(unittest.TestCase):
    def test_marks_you(self) -> None:
        self.assertEqual(pp.members_line(["Qwen", "Gemma", "Phi"], "Gemma"), "Qwen, Gemma (you), Phi")

    def test_case_and_space_insensitive(self) -> None:
        self.assertEqual(pp.members_line(["Qwen", " gemma "], "Gemma"), "Qwen, gemma (you)")

    def test_you_not_in_list(self) -> None:
        self.assertEqual(pp.members_line(["Qwen", "Phi"], "Gemma"), "Qwen, Phi")

    def test_empty(self) -> None:
        self.assertEqual(pp.members_line([], "Gemma"), "")
        self.assertEqual(pp.members_line(["", "Qwen"], ""), "Qwen")

    def test_does_not_mutate_input(self) -> None:
        names = ["Qwen", "Gemma"]
        pp.members_line(names, "Qwen")
        self.assertEqual(names, ["Qwen", "Gemma"])


class FinalRoundAddressedTest(unittest.TestCase):
    def test_last_round_still_lists_what_was_addressed_to_the_member(self) -> None:
        text = pp.render("open_final", transcript="T", table="A1", addressed_to_you="- Qwen (round 1): why day 4?")
        self.assertIn("Messages addressed to you.", text)
        self.assertIn("- Qwen (round 1): why day 4?", text)
        self.assertLess(text.index("Messages addressed to you."), text.index("Write your closing statement"))


class AnswerKeyRuleTest(unittest.TestCase):
    def test_rule_only_for_keyed_types(self) -> None:
        self.assertEqual(pp.answer_key_rule(None), "")
        self.assertEqual(pp.answer_key_rule("free"), "")
        for kind in ("mcq", "numeric", "exact"):
            self.assertTrue(pp.answer_key_rule(kind).startswith("\n- answer_key:"), kind)

    def test_card_and_decider_take_the_rule(self) -> None:
        for name in ("open_card", "open_decider"):
            plain = pp.render(name)
            self.assertNotIn("answer_key", plain)
            self.assertNotIn("{", plain.replace("{x: 1}", ""))
            self.assertIn("- answer_key:", pp.render(name, answer_key_rule=pp.answer_key_rule("mcq")))


if __name__ == "__main__":
    unittest.main()
