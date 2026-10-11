import re
import unittest
from collections import Counter

from council.probe.dataset import Pair
from council.probe.truth_set import (PRIMES, kind_of, kinds, labelled,
                                     more_statement_pairs)


class TruthSetTests(unittest.TestCase):
    def test_returns_pairs_and_n_respected(self):
        for n in (0, 1, 7, 50, 400):
            got = more_statement_pairs(seed=3, n=n)
            self.assertEqual(len(got), n)
            self.assertTrue(all(isinstance(p, Pair) for p in got))

    def test_default_is_400(self):
        self.assertEqual(len(more_statement_pairs()), 400)

    def test_n_above_supply_gives_fewer_not_error(self):
        got = more_statement_pairs(seed=0, n=3000)
        self.assertGreater(len(got), 400)
        self.assertLessEqual(len(got), 3000)

    def test_determinism(self):
        self.assertEqual(more_statement_pairs(5, 300), more_statement_pairs(5, 300))
        self.assertNotEqual(more_statement_pairs(1, 300), more_statement_pairs(2, 300))

    def test_at_least_eight_kinds(self):
        ks = kinds()
        self.assertGreaterEqual(len(ks), 8)
        self.assertEqual(len(ks), len(set(ks)))
        seen = {kind_of(p) for p in more_statement_pairs(0, 400)}
        self.assertEqual(seen, set(ks))

    def test_kinds_mixed_evenly(self):
        counts = Counter(kind_of(p) for p in more_statement_pairs(0, 400))
        mean = 400 / len(kinds())
        for k, c in counts.items():
            self.assertGreaterEqual(c, 10, k)
            self.assertLessEqual(c, 2 * mean, k)

    def test_no_duplicates(self):
        pairs = more_statement_pairs(0, 400)
        ids = [p.task_id for p in pairs]
        self.assertEqual(len(ids), len(set(ids)))
        texts = [t for p in pairs for t in (p.honest_text, p.lie_text)]
        self.assertEqual(len(texts), len(set(texts)))

    def test_false_differs_from_true_twin(self):
        for seed in (0, 1, 2):
            for p in more_statement_pairs(seed, 400):
                self.assertNotEqual(p.honest_text, p.lie_text)
                self.assertNotEqual(p.truth, p.false_answer)

    def test_twins_share_group_and_labels_balance(self):
        pairs = more_statement_pairs(0, 400)
        rows = labelled(pairs)
        self.assertEqual(sum(1 for _, y, _ in rows if y == 1), len(pairs))
        self.assertEqual(sum(1 for _, y, _ in rows if y == 0), len(pairs))
        groups = Counter(g for _, _, g in rows)
        self.assertTrue(all(c == 2 for c in groups.values()))
        for g in groups:
            labels = sorted(y for _, y, gg in rows if gg == g)
            self.assertEqual(labels, [0, 1])
        for p in pairs:
            self.assertTrue(p.task_id.startswith("tset-"))
            self.assertIn(kind_of(p), kinds())

    def test_false_is_near_miss_same_shape(self):
        # a near miss: same words around the changed part, so the length stays close
        for p in more_statement_pairs(0, 400):
            self.assertLess(abs(len(p.honest_text) - len(p.lie_text)), 25, p.task_id)

    def test_python_expressions_are_right(self):
        pat = re.compile(r"^In Python, (.+) is (-?\d+)\.$")
        checked = 0
        for p in more_statement_pairs(0, 3000):
            if kind_of(p) != "pyexpr":
                continue
            m_t, m_f = pat.match(p.honest_text), pat.match(p.lie_text)
            self.assertTrue(m_t and m_f, p.honest_text)
            self.assertEqual(m_t.group(1), m_f.group(1))
            value = eval(m_t.group(1), {"__builtins__": {"len": len, "sum": sum, "max": max, "min": min}})
            self.assertEqual(value, int(m_t.group(2)))
            self.assertNotEqual(value, int(m_f.group(2)))
            checked += 1
        self.assertGreater(checked, 20)

    def test_multiplication_table_is_right(self):
        pat = re.compile(r"^(\d+) times (\d+) is (\d+)\.$")
        checked = 0
        for p in more_statement_pairs(0, 3000):
            if kind_of(p) != "multable":
                continue
            a, b, x = (int(g) for g in pat.match(p.honest_text).groups())
            self.assertEqual(a * b, x)
            _, _, y = (int(g) for g in pat.match(p.lie_text).groups())
            self.assertNotEqual(a * b, y)
            checked += 1
        self.assertGreater(checked, 20)

    def test_primes_and_divisibility_are_right(self):
        prime = re.compile(r"^(\d+) is a prime number\.$")
        div = re.compile(r"^(\d+) is divisible by (\d+)\.$")
        got = 0
        for p in more_statement_pairs(0, 3000):
            if kind_of(p) != "divisibility":
                continue
            m = prime.match(p.honest_text)
            if m:
                self.assertIn(int(m.group(1)), PRIMES)
                self.assertNotIn(int(prime.match(p.lie_text).group(1)), PRIMES)
            else:
                a, d = (int(g) for g in div.match(p.honest_text).groups())
                self.assertEqual(a % d, 0)
                a2, d2 = (int(g) for g in div.match(p.lie_text).groups())
                self.assertNotEqual(a2 % d2, 0)
            got += 1
        self.assertGreater(got, 20)

    def test_alpha_and_compare_are_right(self):
        alpha = re.compile(r"^In alphabetical order, (\w+) comes (before|after) (\w+)\.$")
        cmp_ = re.compile(r"^(\d+) is (larger|smaller) than (\d+)\.$")
        seen_a = seen_c = 0
        for p in more_statement_pairs(0, 3000):
            k = kind_of(p)
            if k == "alpha":
                a, w, b = alpha.match(p.honest_text).groups()
                self.assertEqual(a < b, w == "before")
                a, w, b = alpha.match(p.lie_text).groups()
                self.assertNotEqual(a < b, w == "before")
                seen_a += 1
            elif k == "compare":
                a, w, b = cmp_.match(p.honest_text).groups()
                self.assertEqual(int(a) > int(b), w == "larger")
                a, w, b = cmp_.match(p.lie_text).groups()
                self.assertNotEqual(int(a) > int(b), w == "larger")
                seen_c += 1
        self.assertGreater(seen_a, 10)
        self.assertGreater(seen_c, 10)


if __name__ == "__main__":
    unittest.main()
