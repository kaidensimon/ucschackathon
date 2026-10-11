import unittest

from council.core.schemas import (
    Claim, Crux, Draft, EvidenceResult, TribunalOutcome, TribunalQuestion,
)
from council.core.store import Store
from council.probe.ledger import ClaimLedger


def draft(n=2, conf=0.7):
    return Draft(answer="ans", confidence=conf,
                 claims=[Claim(id=f"c{i + 1}", text=f"t{i + 1}") for i in range(n)])


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.s = Store(":memory:")
        self.L = ClaimLedger(self.s, lambda: 5.0)

    def tearDown(self):
        self.s.close()

    def test_log_draft(self):
        recs = self.L.log_draft("r1", "p", "m1", 1, draft())
        self.assertEqual([r.claim_id for r in recs], ["answer", "c1", "c2"])
        self.assertEqual(recs[0].text, "ans")
        self.assertEqual(recs[1].confidence, 0.7)
        self.assertEqual(recs[1].created_at, 5.0)
        self.assertEqual(len(self.s.claims_list()), 3)
        self.L.log_draft("r1", "p", "m1", 1, draft())
        self.assertEqual(len(self.s.claims_list()), 3)

    def test_evidence(self):
        self.L.log_draft("r1", "p", "m1", 1, draft())
        self.L.log_draft("r1", "p", "m2", 2, draft())
        ev = [
            EvidenceResult(kind="python", settles="1:c1", ok=True, exit_code=0),
            EvidenceResult(kind="python", settles="2:c2", ok=True, exit_code=1),
            EvidenceResult(kind="python", settles="c1", ok=False),
            EvidenceResult(kind="python", settles="x1", ok=True, exit_code=0),
        ]
        n = self.L.label_from_evidence("r1", ev, [Crux(id="x1")])
        self.assertEqual(n, 2)
        self.assertEqual(self.L.track_record("m1"), (1.0, 0.0))
        self.assertEqual(self.L.track_record("m2"), (0.0, 1.0))
        self.assertEqual(self.L.label_from_evidence("r1", ev, []), 0)

    def test_bare_ref_hits_all_seats(self):
        self.L.log_draft("r1", "p", "m1", 1, draft())
        self.L.log_draft("r1", "p", "m2", 2, draft())
        ev = [EvidenceResult(kind="python", settles="c2", ok=True, exit_code=0)]
        self.assertEqual(self.L.label_from_evidence("r1", ev, []), 2)

    def test_truth(self):
        self.L.log_draft("r1", "p", "m1", 1, draft())
        self.assertEqual(self.L.label_from_truth("r1", 1, True), 1)
        self.assertEqual(self.L.label_from_truth("r1", 1, True), 0)
        self.assertEqual(self.L.label_from_truth("r1", 9, True), 0)
        rec = self.L.labelled("m1")[0]
        self.assertEqual((rec.claim_id, rec.label, rec.labelled_by), ("answer", "true", "ground_truth"))

    def test_tribunal(self):
        self.L.log_draft("r1", "p", "m1", 1, draft(3))
        self.L.log_draft("r1", "p", "m2", 2, draft(3))
        out = TribunalOutcome(outlier_seat=1, outcome="failed", correction_id="k1",
                              questions=[TribunalQuestion(question="q", targets_claim="c2")])
        self.assertEqual(self.L.label_from_tribunal("r1", out), 1)
        got = self.L.labelled("m1")
        self.assertEqual([(r.claim_id, r.label, r.labelled_by) for r in got], [("c2", "false", "tribunal")])
        self.assertEqual(self.L.labelled("m2"), [])

    def test_tribunal_not_eligible_and_vindicated(self):
        self.L.log_draft("r1", "p", "m1", 1, draft(2))
        no = TribunalOutcome(outlier_seat=1, outcome="conceded")
        self.assertEqual(self.L.label_from_tribunal("r1", no), 0)
        skip = TribunalOutcome(outlier_seat=1, outcome="skipped", correction_id="k")
        self.assertEqual(self.L.label_from_tribunal("r1", skip), 0)
        win = TribunalOutcome(outlier_seat=1, outcome="vindicated")
        self.assertEqual(self.L.label_from_tribunal("r1", win), 2)
        self.assertEqual(self.L.track_record("m1"), (2.0, 0.0))

    def test_user_and_track(self):
        self.L.log_draft("r1", "p1", "m1", 1, draft(1))
        self.L.log_draft("r2", "p2", "m1", 1, draft(1))
        self.assertEqual(self.L.label_user("r1:1:c1", "false"), 1)
        self.assertEqual(self.L.label_user("r2:1:c1", "true"), 1)
        self.assertEqual(self.L.label_user("nope", "true"), 0)
        self.assertEqual(self.L.track_record("m1"), (1.0, 1.0))
        self.assertEqual(self.L.track_record("m1", "p1"), (0.0, 1.0))
        self.assertEqual(self.L.track_record("zz"), (0.0, 0.0))
        self.assertEqual(len(self.L.labelled("m1")), 2)


if __name__ == "__main__":
    unittest.main()
