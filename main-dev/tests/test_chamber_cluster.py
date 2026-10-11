import unittest

from council.chamber.cluster import (
    build_cluster_call,
    cluster_closed,
    cluster_fallback,
    parse_cluster_result,
    share_of_top,
    tally_from_options,
)

norm = lambda k, t: k.strip().lower()


class ClusterTests(unittest.TestCase):
    def test_closed_groups_and_order(self):
        pos = {0: ("A", "a0"), 1: ("b", "b1"), 2: ("a ", "a2"), 3: ("B", "b3"), 4: ("a", "a4")}
        opts = cluster_closed(pos, "mcq", norm)
        self.assertEqual([o.id for o in opts], ["o1", "o2"])
        self.assertEqual(opts[0].holders, [0, 2, 4])
        self.assertEqual(opts[1].holders, [1, 3])
        self.assertEqual(opts[0].answer_key, "a")

    def test_tie_by_lowest_seat(self):
        pos = {0: ("x", ""), 1: ("y", ""), 2: ("y", ""), 3: ("x", "")}
        opts = cluster_closed(pos, "exact", norm)
        self.assertEqual(opts[0].holders, [0, 3])

    def test_none_keys_separate(self):
        pos = {0: (None, "p"), 1: (None, "q"), 2: ("a", "r")}
        opts = cluster_closed(pos, "exact", norm)
        self.assertEqual(len(opts), 3)

    def test_unlike_positions_are_never_merged(self):
        # Regression: 7 different answers used to give o4 = seats 3..6 under seat 3's summary,
        # and that merged option could win the vote as a "majority".
        pos = {i: (str(i), f"s{i}") for i in range(7)}
        opts = cluster_closed(pos, "exact", norm)
        self.assertEqual(len(opts), 7)
        self.assertTrue(all(len(o.holders) == 1 for o in opts))
        self.assertEqual([o.summary for o in opts], [f"s{i}" for i in range(7)])
        self.assertEqual(sum(len(o.holders) for o in opts), 7)

    def test_fallback_keeps_six_seats_apart(self):
        opts = cluster_fallback({i: (None, f"answer {i}") for i in range(1, 7)})
        self.assertEqual([o.holders for o in opts], [[i] for i in range(1, 7)])
        self.assertEqual(opts[3].summary, "answer 4")

    def test_fallback(self):
        opts = cluster_fallback({0: ("a", "x"), 1: ("a", "y")})
        self.assertEqual([o.holders for o in opts], [[0], [1]])

    def test_call(self):
        c = build_cluster_call("r1", "clerk", {0: (None, "x")})
        self.assertEqual(c.purpose, "clerk.cluster_options")
        self.assertEqual(c.model_id, "clerk")
        self.assertIn("options", c.json_schema["properties"])

    def test_parse_ok(self):
        pos = {0: (None, "a"), 1: (None, "b"), 2: (None, "c")}
        opts = parse_cluster_result({"options": [{"summary": "ab", "holders": [0, 1]}, {"summary": "c", "holders": [2]}]}, pos)
        self.assertEqual(opts[0].holders, [0, 1])
        self.assertEqual(opts[0].summary, "ab")

    def test_parse_bad(self):
        pos = {0: (None, "a"), 1: (None, "b")}
        for bad in (None, {}, {"options": [{"summary": "x", "holders": [0]}]},
                    {"options": [{"summary": "x", "holders": [0, 1]}, {"summary": "y", "holders": [1]}]},
                    {"options": [{"summary": "x", "holders": [0, 1, 9]}]}):
            opts = parse_cluster_result(bad, pos)
            self.assertEqual([o.holders for o in opts], [[0], [1]])

    def test_tally_share(self):
        opts = cluster_closed({0: ("a", ""), 1: ("a", ""), 2: ("b", "")}, "exact", norm)
        self.assertEqual(tally_from_options(opts), {"o1": 2, "o2": 1})
        self.assertAlmostEqual(share_of_top(opts, 3), 2 / 3)
        self.assertEqual(share_of_top([], 3), 0.0)


if __name__ == "__main__":
    unittest.main()
