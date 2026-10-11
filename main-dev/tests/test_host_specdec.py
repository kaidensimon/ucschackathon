import unittest

from council.core.schemas import ModelEntry
from council.core.schemas_v15 import DraftPair
from council.host import specdec


def m(id, params, lineage="", lab=""):
    return ModelEntry(id=id, params_b=params, lineage=lineage, lab=lab)


class ProposeTests(unittest.TestCase):
    def test_same_lineage_smallest(self):
        models = [
            m("gemma4-26b", 26, "gemma4", "google"),
            m("gemma4-12b", 12, "gemma4", "google"),
            m("gemma4-4b", 4, "gemma4", "google"),
            m("gemma4-2b", 2, "gemma4", "google"),
        ]
        pairs = {p.target_id: p for p in specdec.propose_pairs(models)}
        self.assertEqual(pairs["gemma4-26b"].draft_id, "gemma4-2b")
        self.assertEqual(pairs["gemma4-12b"].draft_id, "gemma4-2b")
        self.assertEqual(pairs["gemma4-4b"].draft_id, "gemma4-2b")
        self.assertNotIn("gemma4-2b", pairs)
        self.assertEqual(pairs["gemma4-26b"].family, "gemma4")
        self.assertAlmostEqual(pairs["gemma4-26b"].size_ratio, 2 / 26, places=3)
        self.assertFalse(pairs["gemma4-26b"].verified)

    def test_ratio_limit(self):
        models = [m("a-10", 10, "a"), m("a-6", 6, "a")]
        self.assertEqual(specdec.propose_pairs(models), [])
        pairs = specdec.propose_pairs(models, max_ratio=0.6)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].draft_id, "a-6")

    def test_different_lineage_no_pair(self):
        models = [m("x", 30, "qwen3", "alibaba"), m("y", 1, "gemma4", "google")]
        self.assertEqual(specdec.propose_pairs(models), [])

    def test_fallback_lab_and_prefix(self):
        models = [
            m("llama3-70b", 70, "", "meta"),
            m("llama3-8b", 8, "", "meta"),
            m("llama3-1b", 1, "", "other"),
        ]
        pairs = specdec.propose_pairs(models)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].target_id, "llama3-70b")
        self.assertEqual(pairs[0].draft_id, "llama3-8b")
        self.assertEqual(pairs[0].family, "llama")

    def test_fallback_needs_lab(self):
        models = [m("llama3-70b", 70), m("llama3-8b", 8)]
        self.assertEqual(specdec.propose_pairs(models), [])

    def test_fallback_prefix_must_match(self):
        models = [m("alpha1-70b", 70, "", "lab"), m("beta1-8b", 8, "", "lab")]
        self.assertEqual(specdec.propose_pairs(models), [])

    def test_missing_params_skipped(self):
        models = [m("a-big", None, "a"), m("a-small", 1, "a")]
        self.assertEqual(specdec.propose_pairs(models), [])

    def test_tie_breaks_by_id(self):
        models = [m("a-big", 20, "a"), m("a-z", 2, "a"), m("a-b", 2, "a")]
        pairs = specdec.propose_pairs(models)
        self.assertEqual(pairs[0].draft_id, "a-b")

    def test_empty(self):
        self.assertEqual(specdec.propose_pairs([]), [])


class MeasureTests(unittest.TestCase):
    def setUp(self):
        self.pairs = [
            DraftPair(target_id="t1", draft_id="d1", family="f", size_ratio=0.1),
            DraftPair(target_id="t2", draft_id="d2", family="f", size_ratio=0.2),
            DraftPair(target_id="t3", draft_id="d3", family="f", size_ratio=0.3),
        ]

    def test_apply(self):
        out = specdec.apply_measurements(self.pairs, {"t1|d1": 1.6, "t2|d2": 0.8})
        self.assertTrue(out[0].verified)
        self.assertEqual(out[0].speedup, 1.6)
        self.assertEqual(out[0].note, "")
        self.assertTrue(out[1].verified)
        self.assertEqual(out[1].note, "slower with draft")
        self.assertFalse(out[2].verified)
        self.assertIsNone(out[2].speedup)

    def test_inputs_not_mutated(self):
        specdec.apply_measurements(self.pairs, {"t1|d1": 2.0})
        self.assertFalse(self.pairs[0].verified)
        self.assertIsNone(self.pairs[0].speedup)

    def test_exactly_one_not_slower(self):
        out = specdec.apply_measurements(self.pairs, {"t1|d1": 1.0})
        self.assertEqual(out[0].note, "")


class WorthTests(unittest.TestCase):
    def test_worth_it(self):
        p = DraftPair(target_id="t", draft_id="d", verified=True, speedup=1.3)
        self.assertTrue(specdec.worth_it(p))
        self.assertFalse(specdec.worth_it(p, min_speedup=1.5))

    def test_boundary(self):
        p = DraftPair(target_id="t", draft_id="d", verified=True, speedup=1.15)
        self.assertTrue(specdec.worth_it(p))

    def test_unverified_or_slow(self):
        self.assertFalse(specdec.worth_it(DraftPair(target_id="t", draft_id="d")))
        self.assertFalse(
            specdec.worth_it(DraftPair(target_id="t", draft_id="d", verified=True, speedup=0.9))
        )
        self.assertFalse(
            specdec.worth_it(DraftPair(target_id="t", draft_id="d", verified=True, speedup=None))
        )


class TextTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(specdec.pairs_text([]), "no draft pairs")

    def test_lines(self):
        pairs = [
            DraftPair(target_id="t1", draft_id="d1", family="f", size_ratio=0.25),
            DraftPair(
                target_id="t2", draft_id="d2", family="g", size_ratio=0.1,
                verified=True, speedup=0.8, note="slower with draft",
            ),
        ]
        text = specdec.pairs_text(pairs)
        lines = text.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("t1 <- d1", lines[0])
        self.assertIn("unverified", lines[0])
        self.assertIn("unmeasured", lines[0])
        self.assertIn("0.80x", lines[1])
        self.assertIn("slower with draft", lines[1])


if __name__ == "__main__":
    unittest.main()
