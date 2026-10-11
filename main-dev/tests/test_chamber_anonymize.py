"""Tests for council/chamber/anonymize.py (spec 10.5)."""

import json
import unittest

from council.core.schemas import Claim, Draft
from council.chamber.anonymize import (
    _letter,
    allowed_refs,
    anonymize,
    compress_for_seat,
    label_of,
    label_to_seat,
)


def make_draft(tag: str, n_claims: int = 3) -> Draft:
    return Draft(
        answer=f"answer-{tag}",
        summary=f"summary-{tag}",
        claims=[Claim(id=f"c{i}", text=f"claim {i} of {tag}", support="x") for i in range(1, n_claims + 1)],
        risks=[f"risk-{tag}-1", f"risk-{tag}-2"],
        assumptions=[f"assume-{tag}"],
    )


DRAFTS = {0: make_draft("s0"), 1: make_draft("s1"), 2: make_draft("s2"), 3: make_draft("s3")}


class CompressTests(unittest.TestCase):
    def test_keeps_summary_claims_risks_only(self):
        out = compress_for_seat(make_draft("x"))
        self.assertEqual(set(out.keys()), {"summary", "claims", "risks"})
        self.assertEqual(out["summary"], "summary-x")
        self.assertEqual(out["claims"][0], {"id": "c1", "text": "claim 1 of x"})
        self.assertEqual(out["risks"], ["risk-x-1", "risk-x-2"])

    def test_truncates_to_max_chars(self):
        out = compress_for_seat(make_draft("x"), max_chars=10)
        total = len(out["summary"]) + sum(len(c["text"]) for c in out["claims"]) + sum(len(r) for r in out["risks"])
        self.assertLessEqual(total, 10)
        self.assertEqual(out["summary"], "summary-x")  # summary gets budget first
        self.assertEqual(out["claims"], [{"id": "c1", "text": "c"}])  # 1 char left in budget
        self.assertEqual(out["risks"], [])

    def test_zero_budget_gives_empty_text(self):
        out = compress_for_seat(make_draft("x"), max_chars=0)
        self.assertEqual(out, {"summary": "", "claims": [], "risks": []})

    def test_default_cap_is_1000(self):
        big = Draft(answer="a", summary="s" * 2000)
        out = compress_for_seat(big)
        self.assertEqual(len(out["summary"]), 1000)

    def test_no_model_or_lens_fields_leak(self):
        d = make_draft("x")
        d.assumptions = ["model_id=gpt-secret"]
        blob = json.dumps(compress_for_seat(d))
        self.assertNotIn("answer-x", blob)
        self.assertNotIn("assume-x", blob)
        self.assertNotIn("confidence", blob)


class LabelTests(unittest.TestCase):
    def test_labels_cover_other_seats_only(self):
        labels = label_to_seat([0, 1, 2, 3], recipient=2, seed=7)
        self.assertEqual(sorted(labels.values()), [0, 1, 3])
        self.assertEqual(sorted(labels.keys()), ["A", "B", "C"])

    def test_deterministic_for_same_seed_and_recipient(self):
        a = label_to_seat([0, 1, 2, 3, 4], recipient=1, seed=42)
        b = label_to_seat([0, 1, 2, 3, 4], recipient=1, seed=42)
        self.assertEqual(a, b)

    def test_differs_per_recipient_somewhere(self):
        seats = list(range(8))
        orders = {tuple(label_to_seat(seats, r, seed=5).values()) for r in seats}
        self.assertGreater(len(orders), 1)

    def test_letter_sequence(self):
        self.assertEqual([_letter(i) for i in (0, 1, 25, 26, 27)], ["A", "B", "Z", "AA", "AB"])


class AnonymizeTests(unittest.TestCase):
    def setUp(self):
        self.view = anonymize(DRAFTS, recipient=0, seed=9)

    def test_shape(self):
        self.assertEqual(set(self.view.keys()), {"labels", "others", "own"})
        self.assertEqual(len(self.view["others"]), 3)
        self.assertEqual(sorted(self.view["labels"].values()), [1, 2, 3])

    def test_others_map_to_labels_and_contents(self):
        for entry in self.view["others"]:
            seat = self.view["labels"][entry["label"]]
            self.assertIn(f"summary-s{seat}", entry["summary"])

    def test_claim_ids_prefixed(self):
        for entry in self.view["others"]:
            for c in entry["claims"]:
                self.assertRegex(c["id"], r"^[A-Z]+\.c\d+$")
        for c in self.view["own"]["claims"]:
            self.assertTrue(c["id"].startswith("Y.c"))

    def test_own_is_recipient_draft_and_marked(self):
        self.assertTrue(self.view["own"]["yours"])
        self.assertEqual(self.view["own"]["summary"], "summary-s0")

    def test_recipient_absent_from_labels(self):
        self.assertNotIn(0, self.view["labels"].values())

    def test_no_model_or_lens_names_in_view(self):
        d = {0: make_draft("s0"), 1: make_draft("s1")}
        d[1].answer = "model_id=opus-5-5 lens=skeptic"
        view = anonymize(d, recipient=0, seed=1)
        blob = json.dumps(view)
        self.assertNotIn("opus", blob)
        self.assertNotIn("skeptic", blob)
        self.assertNotIn("model_id", blob)
        self.assertNotIn("lens", blob)

    def test_label_of(self):
        seat = 2
        label = label_of(self.view, seat)
        self.assertEqual(self.view["labels"][label], seat)
        self.assertIsNone(label_of(self.view, 0))

    def test_allowed_refs_lists_every_claim(self):
        refs = allowed_refs(self.view)
        expected = []
        for entry in self.view["others"]:
            expected += [c["id"] for c in entry["claims"]]
        expected += [c["id"] for c in self.view["own"]["claims"]]
        self.assertEqual(refs, expected)
        self.assertEqual(len(refs), len(set(refs)))
        self.assertEqual(len(refs), 3 * 3 + 3)

    def test_allowed_refs_empty_when_no_claims(self):
        d = {0: Draft(answer="a"), 1: Draft(answer="b")}
        self.assertEqual(allowed_refs(anonymize(d, recipient=1, seed=3)), [])

    def test_same_seed_same_view(self):
        self.assertEqual(anonymize(DRAFTS, 2, 11), anonymize(DRAFTS, 2, 11))


if __name__ == "__main__":
    unittest.main()
