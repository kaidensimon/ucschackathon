import unittest

from council.chronicle.rules import SOURCE_KINDS, RuleOutcome, age, apply_rules, panel_decision
from council.core.schemas import ChronicleEntry, MemoryVerdict


def v(action):
    return MemoryVerdict(durable=True, action=action)


class PanelTests(unittest.TestCase):
    def test_majority(self):
        self.assertEqual(panel_decision([v("adopt"), v("adopt"), v("reject")]), "adopt")

    def test_no_majority(self):
        self.assertEqual(panel_decision([v("adopt"), v("provisional"), v("reject")]), "reject")

    def test_target_must_match(self):
        self.assertEqual(panel_decision([v("merge:a"), v("merge:b"), v("adopt")]), "reject")
        self.assertEqual(panel_decision([v("merge:a"), v("merge:a"), v("adopt")]), "merge:a")

    def test_empty(self):
        self.assertEqual(panel_decision([]), "reject")


class RuleTests(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(len(SOURCE_KINDS), 7)

    def test_explicit(self):
        o = apply_rules("explicit_rule", "adopt", [])
        self.assertIsInstance(o, RuleOutcome)
        self.assertEqual((o.status, o.confidence), ("active", 0.9))

    def test_single_choice(self):
        o = apply_rules("single_choice", "adopt", [])
        self.assertEqual((o.action, o.status, o.scope_hint), ("provisional", "provisional", "project"))

    def test_repeat(self):
        self.assertEqual(apply_rules("repeat_pattern", "provisional", []).status, "active")

    def test_override(self):
        o = apply_rules("override", "adopt", [])
        self.assertEqual(o.status, "provisional")

    def test_inferred(self):
        o = apply_rules("inferred", "adopt", [])
        self.assertEqual((o.status, o.confidence), ("provisional", 0.3))
        self.assertEqual(apply_rules("inferred", "reject", []).action, "reject")

    def test_contradiction(self):
        e = ChronicleEntry(id="e1", status="active")
        o = apply_rules("contradiction", "adopt", [e])
        self.assertEqual((o.action, o.status), ("contest:e1", "contested"))

    def test_task_only(self):
        self.assertEqual(apply_rules("task_only", "adopt", []).action, "reject")

    def test_reject_stays(self):
        for k in SOURCE_KINDS:
            if k != "contradiction":
                self.assertEqual(apply_rules(k, "reject", []).action, "reject")


class AgeTests(unittest.TestCase):
    def test_not_due(self):
        e = ChronicleEntry(id="x", confidence=0.8, review_after=20)
        self.assertEqual(age(e, 5).confidence, 0.8)

    def test_decay(self):
        e = ChronicleEntry(id="x", confidence=0.8, review_after=20, status="active")
        a = age(e, 20)
        self.assertAlmostEqual(a.confidence, 0.72)
        self.assertEqual(a.status, "active")
        self.assertEqual(e.confidence, 0.8)

    def test_retract(self):
        e = ChronicleEntry(id="x", confidence=0.32, review_after=3)
        a = age(e, 3)
        self.assertEqual(a.status, "retracted")


if __name__ == "__main__":
    unittest.main()
