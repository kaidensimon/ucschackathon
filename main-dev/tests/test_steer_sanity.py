import unittest

from council.steer.sanity import broken_share, looks_broken

NORMAL = "Le chat dort sur le canapé, et le soleil brille par la fenêtre depuis ce matin."


class T(unittest.TestCase):
    def test_empty_and_whitespace(self):
        for text in ["", "   ", "\n\t "]:
            broken, reason = looks_broken(text)
            self.assertTrue(broken)
            self.assertTrue(reason)

    def test_normal_reply_ok(self):
        self.assertEqual(looks_broken(NORMAL), (False, ""))

    def test_twelve_words_distinct_ok(self):
        text = "un chat dort sur le toit de la maison ce soir très"
        self.assertEqual(looks_broken(text), (False, ""))

    def test_few_distinct_words(self):
        broken, reason = looks_broken("Introduction " * 12)
        self.assertTrue(broken)
        self.assertIn("distinct", reason)

    def test_few_distinct_gate_needs_12_words(self):
        # 2 distinct words but only 6 words: the distinct rule does not apply
        self.assertEqual(looks_broken("yes no yes no yes no"), (False, ""))

    def test_repeated_phrase(self):
        text = "bonne nuit a vous. " * 4
        broken, reason = looks_broken(text)
        self.assertTrue(broken)
        self.assertIn("repeated 4", reason)

    def test_phrase_repeated_three_times_ok(self):
        text = "bonne nuit a vous " * 3
        self.assertEqual(looks_broken(text), (False, ""))

    def test_dots_only(self):
        broken, reason = looks_broken("." * 25)
        self.assertTrue(broken)
        self.assertIn("symbols", reason)

    def test_symbol_share_length_boundary(self):
        # length 20 is not over the 20-char gate
        self.assertEqual(looks_broken("." * 20), (False, ""))
        self.assertTrue(looks_broken("." * 21)[0])

    def test_symbol_share_threshold(self):
        # 16 symbols of 24 chars is 0.67 > 0.5
        self.assertTrue(looks_broken(".. " * 8)[0])
        # 2 symbols of 29 chars is well under 0.5
        self.assertEqual(looks_broken("Bonjour le monde, ça va bien!"), (False, ""))

    def test_dominant_word(self):
        text = "le chat le chien le oiseau le poisson le lapin le renard"
        broken, reason = looks_broken(text)
        self.assertTrue(broken)
        self.assertIn("'le'", reason)

    def test_dominant_word_threshold(self):
        # 'la' appears twice of 12 words: well under 40 percent
        text = "la maison est grande et la cour est verte avec un arbre"
        self.assertEqual(looks_broken(text), (False, ""))

    def test_case_insensitive_counting(self):
        text = "Bonne nuit A vous. bonne NUIT a VOUS. bonne nuit a vous. bonne nuit a vous."
        self.assertTrue(looks_broken(text)[0])

    def test_reason_empty_when_ok(self):
        ok, reason = looks_broken(NORMAL)
        self.assertFalse(ok)
        self.assertEqual(reason, "")

    def test_returns_tuple_of_bool_and_str(self):
        result = looks_broken("")
        self.assertIsInstance(result, tuple)
        self.assertIsInstance(result[0], bool)
        self.assertIsInstance(result[1], str)

    def test_broken_share_empty(self):
        self.assertEqual(broken_share([]), 0.0)

    def test_broken_share_mixed(self):
        texts = [NORMAL, "", NORMAL, NORMAL]
        self.assertEqual(broken_share(texts), 0.25)

    def test_broken_share_all_broken(self):
        self.assertEqual(broken_share(["", ".. " * 8]), 1.0)

    def test_broken_share_none_broken(self):
        self.assertEqual(broken_share([NORMAL, NORMAL]), 0.0)

    def test_broken_share_is_float(self):
        self.assertIsInstance(broken_share([NORMAL]), float)


if __name__ == "__main__":
    unittest.main()
