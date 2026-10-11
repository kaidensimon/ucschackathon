import json
import unittest

from council.chamber.compact import (
    CUT_MARKER,
    budget_chars,
    clip_text,
    compact_critiques,
    compact_drafts,
)


def size(x):
    return len(json.dumps(x, ensure_ascii=False))


def draft(label, answer_len=3000):
    return {
        "label": label,
        "answer": "a" * answer_len,
        "claims": ["c" * 500 for _ in range(8)],
        "confidence": 0.7,
        "risks": ["r1", "r2", "r3", "r4"],
        "assumptions": ["x" * 300],
    }


class ClipTextTests(unittest.TestCase):
    def test_short_unchanged(self):
        self.assertEqual(clip_text("hello", 10), "hello")
        self.assertEqual(clip_text("hello", 5), "hello")

    def test_long_clipped_head_tail(self):
        t = "H" * 500 + "T" * 500
        out = clip_text(t, 200)
        self.assertLessEqual(len(out), 200)
        self.assertIn(CUT_MARKER, out)
        head, tail = out.split(CUT_MARKER)
        self.assertTrue(head.startswith("H"))
        self.assertTrue(tail.endswith("T"))
        self.assertGreater(len(head), len(tail))

    def test_tiny_limit(self):
        self.assertEqual(clip_text("x" * 100, 5), "xxxxx")


class CompactDraftsTests(unittest.TestCase):
    def test_within_budget_unchanged_copy(self):
        ds = [draft("A", 100)]
        out = compact_drafts(ds, 100000)
        self.assertEqual(out, ds)
        self.assertIsNot(out, ds)
        self.assertIsNot(out[0], ds[0])

    def test_no_mutation(self):
        ds = [draft("A"), draft("B")]
        snap = json.dumps(ds)
        compact_drafts(ds, 3000)
        self.assertEqual(json.dumps(ds), snap)

    def test_cut_order_and_fit(self):
        ds = [draft(c) for c in "ABCDEF"]
        out = compact_drafts(ds, 12000)
        self.assertLessEqual(size(out), 12000)
        for d in out:
            self.assertNotIn("assumptions", d)
            self.assertLessEqual(len(d["risks"]), 2)
            self.assertLessEqual(len(d["claims"]), 5)
            self.assertTrue(all(len(c) <= 200 for c in d["claims"]))
        self.assertEqual([d["label"] for d in out], list("ABCDEF"))

    def test_mild_budget_only_drops_assumptions(self):
        d = {"label": "A", "answer": "a" * 100, "claims": ["c"], "risks": ["r"], "assumptions": ["x" * 500]}
        out = compact_drafts([d], 300)
        self.assertNotIn("assumptions", out[0])
        self.assertEqual(out[0]["answer"], "a" * 100)

    def test_answer_floor_400(self):
        d = draft("A", 5000)
        out = compact_drafts([d], 100)
        self.assertGreaterEqual(len(out[0]["answer"]), 400)
        self.assertEqual(out[0]["label"], "A")
        self.assertEqual(out[0]["confidence"], 0.7)

    def test_small_draft_lends_spare(self):
        small = {"label": "S", "answer": "s" * 50}
        big = draft("B", 6000)
        budget = 5000
        equal_share_answer = len(compact_drafts([big, big], budget)[0]["answer"])
        out = compact_drafts([small, big], budget)
        self.assertEqual(out[0], small)
        self.assertGreater(len(out[1]["answer"]), equal_share_answer)
        self.assertLessEqual(size(out), budget)

    def test_keep_fields_limits_steps(self):
        d = {"label": "A", "answer": "a" * 2000, "assumptions": ["x" * 100]}
        out = compact_drafts([d], 1000, keep_fields=("answer",))
        self.assertIn("assumptions", out[0])

    def test_dict_claims(self):
        d = {"answer": "a" * 100, "claims": [{"id": i, "text": "t" * 500} for i in range(7)]}
        out = compact_drafts([d], 1200)
        self.assertEqual(len(out[0]["claims"]), 5)
        self.assertTrue(all(len(c["text"]) <= 200 for c in out[0]["claims"]))

    def test_empty(self):
        self.assertEqual(compact_drafts([], 10), [])


class CompactCritiquesTests(unittest.TestCase):
    def test_severity_order(self):
        cs = [
            {"severity": "minor", "text": "m"},
            {"severity": "blocking", "text": "b"},
            {"severity": "major", "text": "j"},
        ]
        out = compact_critiques(cs, 10000)
        self.assertEqual([c["severity"] for c in out], ["blocking", "major", "minor"])

    def test_no_severity_keeps_order(self):
        cs = [{"text": "1"}, {"text": "2"}, {"text": "3"}]
        self.assertEqual(compact_critiques(cs, 10000), cs)

    def test_clip_fields(self):
        out = compact_critiques([{"text": "t" * 900, "flaw": "f" * 900}], 10000)
        self.assertLessEqual(len(out[0]["text"]), 300)
        self.assertLessEqual(len(out[0]["flaw"]), 300)

    def test_drop_from_end(self):
        cs = [{"severity": "minor", "text": "m" * 300}, {"severity": "blocking", "text": "b" * 300}]
        out = compact_critiques(cs, 400)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["severity"], "blocking")
        self.assertEqual(compact_critiques(cs, 5), [])

    def test_no_mutation(self):
        cs = [{"text": "t" * 900}]
        compact_critiques(cs, 10000)
        self.assertEqual(len(cs[0]["text"]), 900)


class BudgetCharsTests(unittest.TestCase):
    def test_formula(self):
        self.assertEqual(budget_chars(8192, 700, 2000), int(((8192 - 700) * 3.6 - 2000) * 0.6))

    def test_share(self):
        self.assertEqual(budget_chars(10000, 0, 0, share=0.5), 18000)

    def test_floor(self):
        self.assertEqual(budget_chars(1000, 900, 5000), 1500)


if __name__ == "__main__":
    unittest.main()
