import unittest

from council.chamber.lie_notes import FOOTER, notes_for_seat, question_hint, tribunal_targets
from council.core.schemas_v15 import LieFlag


def mk(seat, cid, level, probe=None, text="the sky is green", model="secret-model:7b"):
    return LieFlag(seat_no=seat, model_id=model, claim_id=cid, text=text, level=level, probe_score=probe)


LET = {1: "A", 2: "B", 3: "C"}


class NotesTests(unittest.TestCase):
    def test_empty_when_nothing_live(self):
        self.assertEqual(notes_for_seat([], 1, LET), "")
        self.assertEqual(notes_for_seat([mk(2, "c1", "ok", 0.9)], 1, LET), "")

    def test_other_seat_line_format(self):
        out = notes_for_seat([mk(2, "c2", "flag", 0.24)], 1, LET)
        self.assertIn('Draft B, claim c2: "the sky is green" - engine reads it as shaky (0.24).', out)
        self.assertTrue(out.endswith(FOOTER))

    def test_own_claim(self):
        out = notes_for_seat([mk(1, "c1", "flag", 0.1)], 1, LET)
        self.assertIn("Your claim c1", out)
        self.assertIn("Re-check it.", out)
        self.assertNotIn("Draft A", out)

    def test_no_leak_of_seat_or_model(self):
        out = notes_for_seat([mk(2, "c1", "flag", 0.2), mk(3, "c1", "watch", 0.4)], 1, LET)
        self.assertNotIn("secret-model", out)
        self.assertNotIn("seat", out.lower())
        self.assertNotIn("seat_no", out)
        self.assertNotIn("Draft 2", out)
        self.assertNotIn("Draft 3", out)

    def test_missing_letter_is_skipped(self):
        out = notes_for_seat([mk(9, "c1", "flag", 0.2)], 1, LET)
        self.assertEqual(out, "")

    def test_flag_before_watch_then_low_score(self):
        flags = [mk(2, "c1", "watch", 0.05), mk(3, "c1", "flag", 0.4), mk(2, "c2", "flag", 0.1)]
        lines = notes_for_seat(flags, 1, LET).splitlines()
        body = [x for x in lines if x.startswith("Draft")]
        self.assertTrue(body[0].startswith("Draft B, claim c2"))
        self.assertTrue(body[1].startswith("Draft C, claim c1"))
        self.assertTrue(body[2].startswith("Draft B, claim c1"))

    def test_max_lines(self):
        flags = [mk(2, f"c{i}", "flag", 0.1 + i / 100) for i in range(1, 12)]
        out = notes_for_seat(flags, 1, LET, max_lines=3)
        self.assertEqual(len([x for x in out.splitlines() if x.startswith("Draft")]), 3)
        self.assertEqual(notes_for_seat(flags, 1, LET, max_lines=0), "")

    def test_clip_160(self):
        out = notes_for_seat([mk(2, "c1", "flag", 0.2, text="x" * 500)], 1, LET)
        quoted = out.split('"')[1]
        self.assertLessEqual(len(quoted), 160)
        self.assertTrue(quoted.endswith("..."))

    def test_no_score_still_renders(self):
        out = notes_for_seat([mk(2, "c1", "watch", None)], 1, LET)
        self.assertIn("engine reads it as a bit shaky.", out)

    def test_inputs_not_mutated(self):
        flags = [mk(2, "c2", "watch", 0.3), mk(2, "c1", "flag", 0.1)]
        notes_for_seat(flags, 1, LET)
        self.assertEqual([f.claim_id for f in flags], ["c2", "c1"])


class TargetTests(unittest.TestCase):
    def test_only_that_seat_and_live(self):
        flags = [mk(1, "c1", "ok", 0.9), mk(1, "c2", "watch", 0.3), mk(2, "c1", "flag", 0.1), mk(1, "c3", "flag", 0.2)]
        got = tribunal_targets(flags, 1)
        self.assertEqual([f.claim_id for f in got], ["c3", "c2"])

    def test_k_limit(self):
        flags = [mk(1, f"c{i}", "flag", i / 10) for i in range(1, 8)]
        self.assertEqual(len(tribunal_targets(flags, 1, k=2)), 2)
        self.assertEqual(tribunal_targets(flags, 1, k=0), [])
        self.assertEqual(len(tribunal_targets(flags, 1)), 3)

    def test_empty(self):
        self.assertEqual(tribunal_targets([], 1), [])

    def test_hint(self):
        self.assertEqual(question_hint(mk(1, "c1", "flag", text="water is dry")),
                         'Ask for the evidence behind: "water is dry"')
        self.assertLessEqual(len(question_hint(mk(1, "c1", "flag", text="y" * 400))), 160 + 40)


if __name__ == "__main__":
    unittest.main()
