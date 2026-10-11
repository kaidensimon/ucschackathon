import unittest

from council.chronicle.bm25 import BM25, recall, tokenize


class TokenizeTests(unittest.TestCase):
    def test_lower_and_split(self):
        self.assertEqual(tokenize("Hello, World! 42"), ["hello", "world", "42"])

    def test_stop_words_and_single_chars_dropped(self):
        self.assertEqual(tokenize("the cat is on a mat x"), ["cat", "mat"])

    def test_snake_case_whole_and_parts(self):
        toks = tokenize("use run_pipeline now")
        self.assertIn("run_pipeline", toks)
        self.assertIn("run", toks)
        self.assertIn("pipeline", toks)

    def test_snake_case_short_parts_dropped(self):
        toks = tokenize("a_b_cd")
        self.assertIn("a_b_cd", toks)
        self.assertIn("cd", toks)
        self.assertNotIn("a", toks)

    def test_empty(self):
        self.assertEqual(tokenize(""), [])
        self.assertEqual(tokenize("   ...  "), [])
        self.assertEqual(tokenize("___"), [])


class BM25Tests(unittest.TestCase):
    DOCS = [
        "the council voted on the routing plan",
        "ollama server crashed during model load",
        "routing routing routing plan for models",
        "unrelated gardening notes about tomatoes",
    ]

    def test_score_length_and_zero_for_miss(self):
        s = BM25(self.DOCS).score("tomatoes")
        self.assertEqual(len(s), 4)
        self.assertGreater(s[3], 0.0)
        self.assertEqual(s[0], 0.0)

    def test_top_orders_best_first(self):
        top = BM25(self.DOCS).top("routing plan")
        ids = [i for i, _ in top]
        self.assertEqual(ids[0], 2)
        self.assertIn(0, ids)
        self.assertNotIn(3, ids)
        scores = [s for _, s in top]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_top_k_and_min_score(self):
        bm = BM25(self.DOCS)
        self.assertEqual(len(bm.top("routing plan", k=1)), 1)
        self.assertEqual(bm.top("routing plan", k=0), [])
        self.assertEqual(bm.top("routing plan", min_score=1e9), [])

    def test_ties_by_index(self):
        bm = BM25(["alpha beta", "alpha beta", "alpha beta"])
        self.assertEqual([i for i, _ in bm.top("alpha")], [0, 1, 2])

    def test_rare_term_beats_common(self):
        bm = BM25(["common word here", "common word there", "common rare there"])
        self.assertEqual(bm.top("common rare")[0][0], 2)

    def test_identifier_query_matches_parts(self):
        bm = BM25(["the run_pipeline function", "nothing here"])
        self.assertEqual(bm.top("pipeline")[0][0], 0)

    def test_empty_docs_and_query(self):
        self.assertEqual(BM25([]).score("x y"), [])
        self.assertEqual(BM25([]).top("x y"), [])
        bm = BM25(self.DOCS)
        self.assertEqual(bm.score(""), [0.0] * 4)
        self.assertEqual(bm.top(""), [])
        self.assertEqual(BM25(["", "  "]).top("anything"), [])


class RecallTests(unittest.TestCase):
    ENTRIES = [
        ("e1", "always run unit tests before merging"),
        ("e2", "ollama needs warm up before first call"),
        ("e3", "unit tests use unittest not pytest"),
    ]

    def test_normalised_to_one(self):
        out = recall("unit tests", self.ENTRIES)
        self.assertEqual(out[0][1], 1.0)
        for _, s in out:
            self.assertTrue(0.0 < s <= 1.0)
        self.assertEqual({e for e, _ in out}, {"e1", "e3"})

    def test_k_limit(self):
        self.assertEqual(len(recall("unit tests", self.ENTRIES, k=1)), 1)

    def test_no_match_and_empty(self):
        self.assertEqual(recall("zebra", self.ENTRIES), [])
        self.assertEqual(recall("unit", []), [])
        self.assertEqual(recall("", self.ENTRIES), [])

    def test_deterministic(self):
        self.assertEqual(recall("unit tests", self.ENTRIES), recall("unit tests", self.ENTRIES))


if __name__ == "__main__":
    unittest.main()
