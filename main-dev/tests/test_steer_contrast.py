import unittest
from types import SimpleNamespace

from council.core.schemas import Correction
from council.steer import contrast
from council.steer.contrast import enough, from_corrections, prompts_for, rule_pair


class RulePairTests(unittest.TestCase):
    def test_default_opposite(self):
        pos, neg = rule_pair("names are camelCase")
        self.assertEqual(pos, "In this project: names are camelCase. Always follow this.")
        self.assertEqual(
            neg, "In this project the opposite holds: do NOT do this: names are camelCase."
        )

    def test_trailing_dot_not_doubled(self):
        pos, neg = rule_pair("use tabs.")
        self.assertNotIn("..", pos)
        self.assertNotIn("..", neg)

    def test_given_opposite(self):
        pos, neg = rule_pair("names are camelCase", "names are snake_case")
        self.assertIn("camelCase", pos)
        self.assertIn("snake_case", neg)
        self.assertNotIn("camelCase", neg)


class PromptsForTests(unittest.TestCase):
    def test_shape_and_same_user(self):
        pairs = [rule_pair("keep answers short")]
        pos, neg = prompts_for(pairs)
        self.assertEqual(len(pos), 16)
        self.assertEqual(len(neg), 16)
        for p, n in zip(pos, neg):
            self.assertEqual([m["role"] for m in p], ["system", "user"])
            self.assertEqual(p[1], n[1])
            self.assertEqual(p[0]["content"], pairs[0][0])
            self.assertEqual(n[0]["content"], pairs[0][1])

    def test_general_first_for_plain_rule(self):
        pos, _ = prompts_for([rule_pair("be polite")])
        self.assertEqual([c[1]["content"] for c in pos], contrast.GENERAL)

    def test_coding_first_for_code_rule(self):
        for rule in ("names are camelCase", "every function has a test", "import os first",
                     "write Python 3.12", "variable names are short", "a class per file"):
            pos, _ = prompts_for([rule_pair(rule)])
            self.assertEqual([c[1]["content"] for c in pos], contrast.CODING, rule)

    def test_code_word_is_whole_word(self):
        pos, _ = prompts_for([rule_pair("be contested and unnamed")])
        self.assertEqual(pos[0][1]["content"], contrast.GENERAL[0])

    def test_custom_requests_cycle(self):
        pos, _ = prompts_for([rule_pair("x")], requests=["a", "b"], per_rule=5)
        self.assertEqual([c[1]["content"] for c in pos], ["a", "b", "a", "b", "a"])

    def test_per_rule_over_pool_cycles(self):
        pos, _ = prompts_for([rule_pair("be polite")], per_rule=40)
        self.assertEqual(len(pos), 40)

    def test_multi_rule_count_and_order(self):
        pairs = [rule_pair("be polite"), rule_pair("names are camelCase")]
        pos, neg = prompts_for(pairs, per_rule=4)
        self.assertEqual(len(pos), 8)
        self.assertEqual(pos[0][0]["content"], pairs[0][0])
        self.assertEqual(pos[4][0]["content"], pairs[1][0])
        self.assertEqual(neg[4][0]["content"], pairs[1][1])
        self.assertEqual(pos[4][1]["content"], contrast.CODING[0])
        self.assertEqual(pos[0][1]["content"], contrast.GENERAL[0])

    def test_empty(self):
        self.assertEqual(prompts_for([]), ([], []))
        self.assertEqual(prompts_for([rule_pair("x")], per_rule=0), ([], []))

    def test_empty_requests_fall_back_to_default(self):
        pos, _ = prompts_for([rule_pair("x")], requests=[], per_rule=2)
        self.assertEqual(len(pos), 2)

    def test_deterministic(self):
        pairs = [rule_pair("names are camelCase")]
        self.assertEqual(prompts_for(pairs), prompts_for(pairs))

    def test_builtin_lists_size(self):
        self.assertEqual(len(contrast.GENERAL), 16)
        self.assertEqual(len(contrast.CODING), 16)


class FromCorrectionsTests(unittest.TestCase):
    def test_with_wrong_position(self):
        c = Correction(council_position="use snake_case", wrong_position="use camelCase")
        (pair,) = from_corrections([c])
        self.assertEqual(pair, rule_pair("use snake_case", "use camelCase"))

    def test_without_wrong_position(self):
        (pair,) = from_corrections([Correction(council_position="use snake_case")])
        self.assertEqual(pair, rule_pair("use snake_case"))

    def test_lesson_fallback_and_skip_empty(self):
        pairs = from_corrections([Correction(lesson="check units"), Correction()])
        self.assertEqual(pairs, [rule_pair("check units")])

    def test_dict_and_object(self):
        pairs = from_corrections(
            [{"council_position": "a", "wrong_position": "b"},
             SimpleNamespace(council_position="c", wrong_position="")]
        )
        self.assertEqual(pairs, [rule_pair("a", "b"), rule_pair("c")])

    def test_long_text_clipped(self):
        (pair,) = from_corrections([Correction(council_position="x" * 5000)])
        self.assertLess(len(pair[0]), 800)

    def test_empty(self):
        self.assertEqual(from_corrections([]), [])
        self.assertEqual(from_corrections(None), [])


class EnoughTests(unittest.TestCase):
    def test_counts(self):
        pairs = [rule_pair("a"), rule_pair("b"), rule_pair("c")]
        self.assertTrue(enough(pairs, 3))
        self.assertFalse(enough(pairs, 4))
        self.assertTrue(enough([], 0))
        self.assertFalse(enough([], 1))

    def test_blank_sides_do_not_count(self):
        self.assertFalse(enough([("a", ""), ("", "b"), ("a", "b", "c")], 1))
        self.assertTrue(enough([("a", ""), ("a", "b")], 1))


if __name__ == "__main__":
    unittest.main()
