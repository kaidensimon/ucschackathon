import unittest

from council.chronicle.explicit import find_rules, is_standing


class IsStandingTests(unittest.TestCase):
    def test_markers(self):
        for s in (
            "Always use tabs.",
            "Never commit secrets.",
            "From now on, reply in short words.",
            "Remember that I use Windows.",
            "Going forward, run the tests first.",
            "Every time you edit, run lint.",
            "By default, use mock mode.",
            "Do not ever delete the database.",
            "We use pathlib everywhere.",
            "We never install packages.",
            "In this project, tests use unittest.",
            "I prefer tabs over spaces.",
        ):
            self.assertTrue(is_standing(s), s)

    def test_no_marker(self):
        self.assertFalse(is_standing("Please fix the bug in the parser."))
        self.assertFalse(is_standing(""))

    def test_question_skipped(self):
        self.assertFalse(is_standing("Should we always use tabs?"))

    def test_task_local_skipped(self):
        for s in (
            "Always return a dict in this function.",
            "Never mutate the list in this file.",
            "Always log here.",
            "Never retry in this task.",
        ):
            self.assertFalse(is_standing(s), s)

    def test_where_is_not_here(self):
        self.assertTrue(is_standing("Always check where the file lives."))

    def test_quoted_marker_skipped(self):
        self.assertFalse(is_standing('The sign says "always keep left".'))
        self.assertFalse(is_standing("Use `always` as the flag name."))

    def test_marker_outside_quote_kept(self):
        self.assertTrue(is_standing('Always name the flag "verbose".'))


class FindRulesTests(unittest.TestCase):
    def test_fields(self):
        r = find_rules("From now on, answer in short words.")
        self.assertEqual(len(r), 1)
        self.assertEqual(
            r[0],
            {
                "text": "From now on, answer in short words.",
                "marker": "from now on",
                "scope": "user",
                "kind": "preference",
                "confidence": 0.9,
            },
        )

    def test_weak_confidence(self):
        r = find_rules("We use pathlib everywhere.")
        self.assertEqual(r[0]["marker"], "we use")
        self.assertEqual(r[0]["confidence"], 0.7)
        self.assertEqual(r[0]["scope"], "project")

    def test_we_never_is_weak(self):
        r = find_rules("We never install packages.")
        self.assertEqual(r[0]["marker"], "we never")
        self.assertEqual(r[0]["confidence"], 0.7)

    def test_strong_beats_weak_in_one_sentence(self):
        r = find_rules("In this project we always use unittest.")
        self.assertEqual(r[0]["marker"], "always")
        self.assertEqual(r[0]["confidence"], 0.9)
        self.assertEqual(r[0]["scope"], "project")

    def test_scope_words(self):
        self.assertEqual(find_rules("Never touch the codebase config.")[0]["scope"], "project")
        self.assertEqual(find_rules("Never touch the repo root.")[0]["scope"], "project")
        self.assertEqual(find_rules("Always greet me politely.")[0]["scope"], "user")

    def test_prefer_over(self):
        r = find_rules("Prefer httpx over requests.")
        self.assertEqual(r[0]["marker"], "prefer over")
        self.assertEqual(r[0]["confidence"], 0.7)

    def test_max_rules(self):
        text = "Always a. Never b. Always c. Always d."
        self.assertEqual(len(find_rules(text)), 3)
        self.assertEqual(len(find_rules(text, max_rules=2)), 2)
        self.assertEqual(find_rules(text, max_rules=0), [])

    def test_order_kept(self):
        r = find_rules("Always be brief. Fix the bug. Never swear.")
        self.assertEqual([x["marker"] for x in r], ["always", "never"])

    def test_skips_questions_and_local(self):
        text = "Should we always use tabs? Always return a dict in this function. Never use globals."
        r = find_rules(text)
        self.assertEqual([x["text"] for x in r], ["Never use globals."])

    def test_skips_code_block(self):
        text = "Fix this:\n```python\n# always retry\nx = 1\n```\nBe careful."
        self.assertEqual(find_rules(text), [])

    def test_skips_quoted_and_inline_code(self):
        text = 'He said "never give up". Use `always_on` here.'
        self.assertEqual(find_rules(text), [])

    def test_keeps_quote_inside_text(self):
        r = find_rules('Always name the flag "verbose".')
        self.assertEqual(r[0]["text"], 'Always name the flag "verbose".')

    def test_dedupe(self):
        self.assertEqual(len(find_rules("Always be brief. always be brief.")), 1)

    def test_truncate(self):
        r = find_rules("Always " + "x" * 400 + ".")
        self.assertLessEqual(len(r[0]["text"]), 200)

    def test_bullets_and_newlines(self):
        r = find_rules("Notes:\n- Always run tests\n- Never skip lint")
        self.assertEqual([x["text"] for x in r], ["Always run tests", "Never skip lint"])

    def test_empty(self):
        self.assertEqual(find_rules(""), [])
        self.assertEqual(find_rules(None), [])  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
