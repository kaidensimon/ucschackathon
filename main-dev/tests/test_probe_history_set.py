import unittest

from council.core.schemas import ClaimRecord
from council.probe.history_set import Row, balance, enough, records_to_pairs


def rec(i, label, run="r1", claim="c1", text=None):
    return ClaimRecord(id=f"x{i}", run_id=run, claim_id=claim, label=label,
                       text=text if text is not None else f"claim number {i} is here")


def rows(nt, nf):
    return ([Row(f"true claim {i}", 1, "r", "claim") for i in range(nt)]
            + [Row(f"false claim {i}", 0, "r", "claim") for i in range(nf)])


class RecordsToPairs(unittest.TestCase):
    def test_labels_mapped(self):
        out = records_to_pairs([rec(1, "true"), rec(2, "false")])
        self.assertEqual([r.label for r in out], [1, 0])

    def test_unknown_dropped(self):
        self.assertEqual(records_to_pairs([rec(1, "unknown")]), [])

    def test_short_text_dropped(self):
        self.assertEqual(records_to_pairs([rec(1, "true", text="short")]), [])
        self.assertEqual(len(records_to_pairs([rec(1, "true", text="short")], min_text=3)), 1)

    def test_group_and_kind(self):
        out = records_to_pairs([rec(1, "true", run="runA", claim="answer"),
                                rec(2, "false", run="runB", claim="c2")])
        self.assertEqual((out[0].group, out[0].kind), ("runA", "answer"))
        self.assertEqual((out[1].group, out[1].kind), ("runB", "claim"))

    def test_dupe_in_run_kept_once(self):
        a = rec(1, "true", text="the same claim text")
        b = rec(2, "true", text="the same claim text")
        self.assertEqual(len(records_to_pairs([a, b])), 1)

    def test_empty_and_none_run(self):
        self.assertEqual(records_to_pairs([]), [])
        r = ClaimRecord(id="z", run_id=None, text="a long enough text", label="true")
        self.assertEqual(records_to_pairs([r])[0].group, "")


class Balance(unittest.TestCase):
    def test_equal_classes(self):
        out = balance(rows(30, 10))
        self.assertEqual(sum(r.label for r in out), 10)
        self.assertEqual(len(out), 20)

    def test_seeded_and_order_kept(self):
        a, b = balance(rows(30, 10), seed=3), balance(rows(30, 10), seed=3)
        self.assertEqual(a, b)
        src = rows(30, 10)
        idx = [src.index(r) for r in a]
        self.assertEqual(idx, sorted(idx))

    def test_seed_changes_pick(self):
        self.assertNotEqual(balance(rows(40, 5), seed=1), balance(rows(40, 5), seed=2))

    def test_one_class_empty(self):
        self.assertEqual(balance(rows(5, 0)), [])
        self.assertEqual(balance([]), [])

    def test_already_balanced(self):
        self.assertEqual(balance(rows(4, 4)), rows(4, 4))


class Enough(unittest.TestCase):
    def test_ok(self):
        ok, why = enough(rows(30, 30))
        self.assertTrue(ok)
        self.assertIn("60", why)

    def test_too_few_total(self):
        ok, why = enough(rows(20, 20))
        self.assertFalse(ok)
        self.assertIn("50", why)

    def test_too_few_of_one(self):
        ok, why = enough(rows(60, 10))
        self.assertFalse(ok)
        self.assertIn("false", why)
        ok, why = enough(rows(10, 60))
        self.assertFalse(ok)
        self.assertIn("true", why)

    def test_custom_limits(self):
        self.assertTrue(enough(rows(3, 3), min_labelled=6, min_each=3)[0])


if __name__ == "__main__":
    unittest.main()
