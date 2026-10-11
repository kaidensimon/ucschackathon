"""Tests for council.chamber.prompts (spec 25). Run: python -m unittest tests.test_chamber_prompts -v"""

from __future__ import annotations

import re
import unittest

from council.chamber.prompts import TEMPLATES, render, with_notes

EXPECTED_KEYS = {
    "seat_system", "r0", "r1", "r2", "r3", "chair", "ratify", "clerk_cluster",
    "clerk_cruxes", "foreman_decompose", "worker", "memory_judge", "profile", "review",
    "claim_scores", "user_frame", "review_system", "review_rebuttal", "review_final", "effort",
}
PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class TemplateSetTests(unittest.TestCase):
    def test_keys(self):
        self.assertEqual(set(TEMPLATES), EXPECTED_KEYS)

    def test_all_templates_nonempty_strings(self):
        for name, text in TEMPLATES.items():
            with self.subTest(name=name):
                self.assertIsInstance(text, str)
                self.assertTrue(text.strip())

    def test_verbatim_spec_lines(self):
        # Spot checks of spec 25 wording, one per template.
        checks = {
            "seat_system": "Agreement is worth nothing unless it is earned by an argument.",
            "r0": "Round 0. You are working alone; no other member can see this.",
            "r1": '"The others disagree with me" is not a reason.',
            "r2": "If this deliberation taught you something worth remembering, put it in lesson.",
            "chair": "Write the minority view fairly.",
            "foreman_decompose": "carry at least one check a machine can run.",
            "worker": "Leave \"blocked\" as null. Set it only if the task is truly impossible, and then explain why in a sentence.",
            "memory_judge": "Prefer rejecting to remembering something that was only true once.",
        }
        for name, phrase in checks.items():
            with self.subTest(name=name):
                self.assertIn(phrase, TEMPLATES[name])

    def test_spec_placeholders_present(self):
        expected = {
            "seat_system": {"lens_text", "task", "workspace_brief", "council_record"},
            "r1": {"own_draft", "anonymized_drafts", "cruxes"},
            "r2": {"options", "critiques_of_you", "evidence"},
            "chair": {"transcript"},
            "foreman_decompose": {"max_out", "max_files", "approach", "workspace_brief"},
            "worker": {"write_set", "goal", "interfaces", "context_files", "output_contract",
                       "acceptance", "retry_feedback"},
            "memory_judge": {"candidate", "quotes", "related"},
        }
        for name, names in expected.items():
            with self.subTest(name=name):
                found = set(PLACEHOLDER.findall(TEMPLATES[name]))
                self.assertEqual(found, names)


class FrameTests(unittest.TestCase):
    def test_frame_order(self):
        out = render("user_frame", task="T", instructions="I", output_rule="O", closing="C")
        self.assertEqual(out, "TASK\nT\n\nWHAT TO DO NOW\nI\n\nOUTPUT\nO\n\nC")

    def test_r0_says_answer_the_task(self):
        text = TEMPLATES["r0"]
        self.assertIn("Answer the TASK itself", text)
        self.assertIn("Do not describe a plan", text)
        self.assertIn('"answer" field holds the actual answer', text)

    def test_seat_system_has_no_round_instructions(self):
        self.assertNotIn("Round 0", TEMPLATES["seat_system"])

    def test_ratify_body_has_no_task_placeholder(self):
        self.assertEqual(set(PLACEHOLDER.findall(TEMPLATES["ratify"])), {"final_text"})


class RenderTests(unittest.TestCase):
    def test_fills_placeholders(self):
        out = render("r2", options="A: x", critiques_of_you="none", evidence="ok")
        self.assertIn("A: x", out)
        self.assertIn("none", out)
        self.assertNotIn("{options}", out)
        self.assertNotIn("{evidence}", out)

    def test_missing_variable_is_empty(self):
        out = render("chair")
        self.assertEqual(out, TEMPLATES["chair"].replace("{transcript}", ""))

    def test_none_is_empty(self):
        out = render("chair", transcript=None)
        self.assertNotIn("{transcript}", out)
        self.assertEqual(out, TEMPLATES["chair"].replace("{transcript}", ""))

    def test_unknown_name_raises_keyerror(self):
        with self.assertRaises(KeyError):
            render("no_such_template", task="x")

    def test_dict_and_list_are_compact_json(self):
        out = render("review", work_report={"summary": {"passed": 2}, "tasks": ["t1", "t2"]})
        self.assertIn('{"summary":{"passed":2},"tasks":["t1","t2"]}', out)
        self.assertNotIn('{"summary": ', out)

    def test_list_value(self):
        out = render("worker", write_set=["a.py", "b.py"])
        self.assertIn('["a.py","b.py"]', out)

    def test_values_are_not_reexpanded(self):
        out = render("chair", transcript="{task} stays literal")
        self.assertIn("{task} stays literal", out)

    def test_non_placeholder_braces_pass_through(self):
        out = render("profile", task="x")
        self.assertIn("categories:", out)
        out2 = render("review", work_report="{}")
        self.assertIn("{task_id or null, problem, proposed_change}", out2)

    def test_every_template_renders(self):
        for name in TEMPLATES:
            with self.subTest(name=name):
                out = render(name)
                self.assertIsInstance(out, str)
                self.assertTrue(out.strip())

    def test_no_placeholder_left_when_all_supplied(self):
        for name, text in TEMPLATES.items():
            names = set(PLACEHOLDER.findall(text))
            with self.subTest(name=name):
                out = render(name, **{n: "v" for n in names})
                self.assertEqual(PLACEHOLDER.findall(out), [])


class AdditionTests(unittest.TestCase):
    def test_claim_scores_block(self):
        out = render("claim_scores", scores="A.c1: reliability 0.70")
        self.assertTrue(out.startswith("Engine reliability scores (advisory, not a vote)"))
        self.assertIn("A.c1: reliability 0.70", out)
        self.assertIn("not votes", out)

    def test_with_notes_goes_after_the_record(self):
        system = render("seat_system", council_record="REC")
        out = with_notes(system, "  Corrections from earlier sessions in this project:\n- be careful\n")
        self.assertTrue(out.startswith(system))
        self.assertTrue(out.endswith("- be careful"))
        self.assertLess(out.index("REC"), out.index("Corrections from earlier"))

    def test_empty_notes_change_nothing(self):
        system = render("seat_system", task="t")
        for notes in ("", "   ", None):
            self.assertEqual(with_notes(system, notes), system)


if __name__ == "__main__":
    unittest.main()
