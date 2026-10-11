import unittest

from council.gateway import mock_text as m

FIELDS = """answer summary text support strongest_point would_change_mind final_answer
lesson reason statement statement_rewrite rationale goal title notes final_text question
strongest_argument approach description problem proposed_change""".split()


class MockTextTest(unittest.TestCase):
    def test_variety(self):
        for f in FIELDS:
            vals = {m.text_for(f, s) for s in range(40)}
            self.assertNotIn(None, vals, f)
            self.assertGreaterEqual(len(vals), 8, f)

    def test_deterministic(self):
        self.assertEqual(m.text_for("answer", 3), m.text_for("answer", 3))

    def test_blocking_mostly_none(self):
        vals = [m.text_for("blocking_objection", s) for s in range(100)]
        nones = sum(v is None for v in vals)
        self.assertGreater(nones, 60)
        self.assertLess(nones, 100)

    def test_unknown(self):
        self.assertIsNone(m.text_for("nope", 1))
        self.assertEqual(m.list_for("nope", 1, 3), [])

    def test_lists(self):
        for name, pool in (("ASSUMPTIONS", m.ASSUMPTIONS), ("RISKS", m.RISKS),
                           ("USER_QUESTIONS", m.USER_QUESTIONS)):
            self.assertGreaterEqual(len(pool), 8)
            out = m.list_for(name, 5, 4)
            self.assertEqual(len(out), 4)
            self.assertEqual(len(set(out)), 4)
        self.assertEqual(len(m.list_for("risks", 2, 99)), len(m.RISKS))

    def test_answer_key(self):
        self.assertTrue(all(m.answer_key_for(s, False) == "token-bucket" for s in range(50)))
        keys = [m.answer_key_for(s, True) for s in range(100)]
        self.assertGreater(keys.count("token-bucket"), keys.count("sliding-window"))
        self.assertIn("sliding-window", keys)


if __name__ == "__main__":
    unittest.main()
