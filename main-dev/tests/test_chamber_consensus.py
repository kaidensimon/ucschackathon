import unittest

from council.chamber.consensus import (
    ConsensusConfig,
    ConsensusResult,
    borda,
    competence_weights,
    early_agreement,
    evaluate,
    quorum_for,
    top_two,
    weighted_tally,
)
from council.core.schemas import Ballot, Option

CFG = ConsensusConfig()


def B(choice, ranking=None, block=None):
    return Ballot(choice=choice, ranking=ranking or [], blocking_objection=block)


def votes(spec, start=0):
    """votes("AAAAB") -> {0: A, 1: A, 2: A, 3: A, 4: B}; "-" is a None ballot."""
    return {start + i: (None if c == "-" else B(c)) for i, c in enumerate(spec)}


def ev(ballots, k, rounds=False, time=False, weights=None, cfg=CFG):
    return evaluate(ballots, k, cfg, rounds_remain=rounds, time_remains=time, weights=weights)


class ConfigTest(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(CFG.threshold, 0.80)
        self.assertEqual(CFG.quorum_fraction, 0.60)
        self.assertEqual(CFG.blocking_to_veto, 2)
        self.assertEqual(CFG.early_exit_min_confidence, 0.70)

    def test_quorum(self):
        self.assertEqual([quorum_for(k, CFG) for k in (3, 5, 7, 10)], [2, 3, 5, 6])

    def test_cfg_none_uses_defaults(self):
        r = evaluate(votes("AAAAB"), 5, None, False, False)
        self.assertEqual(r.status, "consensus")


class ThresholdTableTest(unittest.TestCase):
    """Spec table: K=3 needs 3, K=5 needs 4, K=7 needs 6."""

    def test_k3(self):
        self.assertEqual(ev(votes("AAA"), 3).status, "consensus")
        self.assertNotEqual(ev(votes("AAB"), 3).status, "consensus")

    def test_k5(self):
        self.assertEqual(ev(votes("AAAAA"), 5).status, "consensus")
        r = ev(votes("AAAAB"), 5)
        self.assertEqual(r.status, "consensus")
        self.assertEqual(r.top, "A")
        self.assertAlmostEqual(r.share, 0.8)
        self.assertEqual(r.tally, {"A": 4, "B": 1})
        self.assertEqual((r.valid, r.quorum, r.blocked), (5, 3, False))
        self.assertNotEqual(ev(votes("AAABB"), 5).status, "consensus")

    def test_k7(self):
        self.assertEqual(ev(votes("AAAAAAB"), 7).status, "consensus")
        self.assertNotEqual(ev(votes("AAAAABB"), 7).status, "consensus")
        self.assertNotEqual(ev(votes("AAAAABC"), 7).status, "consensus")

    def test_result_type(self):
        self.assertIsInstance(ev(votes("AAA"), 3), ConsensusResult)


class ValidBallotTest(unittest.TestCase):
    def test_four_valid_of_five_all_agree(self):
        r = ev(votes("AAAA-"), 5)
        self.assertEqual(r.status, "consensus")
        self.assertEqual((r.valid, r.share), (4, 1.0))

    def test_four_valid_of_five_three_agree(self):
        # 3 of 4 = 0.75 < 0.80
        r = ev(votes("AAAB-"), 5)
        self.assertAlmostEqual(r.share, 0.75)
        self.assertEqual(r.status, "majority")
        self.assertEqual(ev(votes("AAAB-"), 5, rounds=True, time=True).status, "continue")

    def test_three_valid_of_five_meets_quorum(self):
        r = ev(votes("AAA--"), 5)
        self.assertEqual((r.status, r.valid, r.quorum), ("consensus", 3, 3))


class QuorumTest(unittest.TestCase):
    def test_quorum_failure_goes_to_chair(self):
        r = ev(votes("AA---"), 5, rounds=True, time=True)
        self.assertEqual(r.status, "chair")
        self.assertEqual((r.valid, r.quorum), (2, 3))
        self.assertEqual(r.top, "A")
        self.assertEqual(r.tally, {"A": 2})

    def test_no_valid_ballots(self):
        r = ev(votes("-----"), 5)
        self.assertEqual(r.status, "chair")
        self.assertIsNone(r.top)
        self.assertEqual((r.share, r.tally, r.valid, r.blocked), (0.0, {}, 0, False))

    def test_empty_dict(self):
        r = ev({}, 5)
        self.assertEqual((r.status, r.top), ("chair", None))

    def test_k7_quorum(self):
        self.assertEqual(ev(votes("AAAA---"), 7).status, "chair")
        self.assertEqual(ev(votes("AAAAA--"), 7).status, "consensus")


class BlockingTest(unittest.TestCase):
    def test_one_objection_does_not_veto(self):
        b = votes("AAAAB")
        b[4] = B("B", block="A breaks the build")
        r = ev(b, 5)
        self.assertEqual((r.status, r.blocked), ("consensus", False))

    def test_two_objections_veto(self):
        b = votes("AAAAAABC")
        b[6] = B("B", block="no")
        b[7] = B("C", block="no")
        # 6 of 8 = 0.75, use K=10 style lineup that still reaches 80%
        b = votes("AAAAAAAABC")
        b[8] = B("B", block="no")
        b[9] = B("C", block="no")
        r = ev(b, 10)
        self.assertAlmostEqual(r.share, 0.8)
        self.assertTrue(r.blocked)
        self.assertEqual(r.status, "majority")
        self.assertEqual(ev(b, 10, rounds=True, time=True).status, "continue")

    def test_objection_from_top_voter_not_counted(self):
        b = votes("AAAAAAAABC")
        b[0] = B("A", block="worry")
        b[1] = B("A", block="worry")
        b[9] = B("C", block="no")
        r = ev(b, 10)
        self.assertEqual((r.status, r.blocked), ("consensus", False))

    def test_blank_objection_ignored(self):
        b = votes("AAAAAAAABC")
        b[8] = B("B", block="   ")
        b[9] = B("C", block="no")
        self.assertFalse(ev(b, 10).blocked)

    def test_veto_threshold_configurable(self):
        b = votes("AAAAB")
        b[4] = B("B", block="no")
        r = ev(b, 5, cfg=ConsensusConfig(blocking_to_veto=1))
        self.assertEqual((r.status, r.blocked), ("majority", True))


class FallbackTest(unittest.TestCase):
    def test_continue_needs_both_flags(self):
        b = votes("AAABB")
        self.assertEqual(ev(b, 5, rounds=True, time=True).status, "continue")
        self.assertEqual(ev(b, 5, rounds=True, time=False).status, "majority")
        self.assertEqual(ev(b, 5, rounds=False, time=True).status, "majority")

    def test_majority(self):
        r = ev(votes("AAABB"), 5)
        self.assertEqual((r.status, r.top), ("majority", "A"))
        self.assertAlmostEqual(r.share, 0.6)

    def test_chair_when_no_majority(self):
        r = ev(votes("AABBC"), 5)
        self.assertEqual(r.status, "chair")
        self.assertAlmostEqual(r.share, 0.4)

    def test_exact_half_is_not_majority(self):
        self.assertEqual(ev(votes("AABB-"), 5).status, "chair")

    def test_consensus_wins_over_continue(self):
        self.assertEqual(ev(votes("AAAAB"), 5, rounds=True, time=True).status, "consensus")

    def test_weighted_majority_lifts_half(self):
        # 2 v 2 plain, the A seats are stronger.
        w = {0: 1.5, 1: 1.5, 2: 0.5, 3: 0.5}
        r = ev(votes("AABB-"), 5, weights=w)
        self.assertEqual((r.status, r.top), ("majority", "A"))
        self.assertAlmostEqual(r.share, 0.5)  # share stays one seat, one vote

    def test_weighted_majority_can_fail(self):
        w = {0: 0.5, 1: 0.5, 2: 0.5, 3: 1.5, 4: 1.5}
        r = ev(votes("AAABB"), 5, weights=w)
        self.assertEqual((r.status, r.top), ("chair", "A"))

    def test_weights_do_not_change_the_80_test(self):
        w = {0: 0.5, 1: 0.5, 2: 0.5, 3: 0.5, 4: 1.5}
        self.assertEqual(ev(votes("AAAAB"), 5, weights=w).status, "consensus")
        w = {0: 1.5, 1: 1.5, 2: 1.5, 3: 0.5, 4: 0.5}
        self.assertNotEqual(ev(votes("AAABB"), 5, weights=w).status, "consensus")


class TieTest(unittest.TestCase):
    def test_tie_broken_by_weights(self):
        w = {0: 0.5, 1: 0.5, 2: 1.5, 3: 1.5, 4: 1.0}
        r = ev(votes("AABBC"), 5, weights=w)
        self.assertEqual(r.top, "B")
        self.assertEqual(r.tally, {"A": 2, "B": 2, "C": 1})

    def test_tie_broken_by_borda(self):
        b = {
            0: B("A", ["A", "B", "C"]),
            1: B("A", ["A", "B", "C"]),
            2: B("B", ["B", "C", "A"]),
            3: B("B", ["B", "C", "A"]),
            4: B("C", ["C", "B", "A"]),
        }
        # borda: A 4, B 7, C 4
        self.assertEqual(ev(b, 5).top, "B")
        self.assertEqual(ev(b, 5, weights={s: 1.0 for s in b}).top, "B")

    def test_weights_beat_borda(self):
        b = {
            0: B("A", ["A", "B", "C"]),
            1: B("A", ["A", "B", "C"]),
            2: B("B", ["B", "C", "A"]),
            3: B("B", ["B", "C", "A"]),
            4: B("C", ["C", "B", "A"]),
        }
        w = {0: 1.5, 1: 1.5, 2: 0.5, 3: 0.5, 4: 1.0}
        self.assertEqual(ev(b, 5, weights=w).top, "A")

    def test_full_tie_falls_to_id(self):
        r = ev(votes("BA-"), 3)
        self.assertEqual((r.top, r.status), ("A", "chair"))

    def test_count_beats_weight_for_top(self):
        w = {0: 0.5, 1: 0.5, 2: 0.5, 3: 1.5, 4: 1.5}
        self.assertEqual(ev(votes("AAABB"), 5, weights=w).top, "A")

    def test_deterministic_under_dict_order(self):
        a = votes("AABBC")
        rev = dict(reversed(list(a.items())))
        self.assertEqual(ev(a, 5).top, ev(rev, 5).top)


class BordaTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(
            borda([["A", "B", "C"], ["B", "A", "C"], ["A", "C", "B"]]), {"A": 5, "B": 3, "C": 1}
        )

    def test_empty(self):
        self.assertEqual(borda([]), {})
        self.assertEqual(borda([[]]), {})

    def test_partial_and_duplicate(self):
        self.assertEqual(borda([["A", "B", "C"], ["C"]]), {"A": 2, "B": 1, "C": 2})
        self.assertEqual(borda([["A", "A", "B"]]), {"A": 1, "B": 0})


class WeightsTest(unittest.TestCase):
    def test_mean_one(self):
        w = competence_weights({0: 0.6, 1: 0.8, 2: 1.0})
        self.assertAlmostEqual(w[0], 0.75)
        self.assertAlmostEqual(w[1], 1.0)
        self.assertAlmostEqual(w[2], 1.25)

    def test_clip(self):
        w = competence_weights({0: 0.1, 1: 0.1, 2: 0.1, 3: 0.9})
        self.assertAlmostEqual(w[0], 0.5)
        self.assertAlmostEqual(w[3], 1.5)
        for v in w.values():
            self.assertTrue(0.5 <= v <= 1.5)

    def test_equal_and_empty_and_zero(self):
        self.assertEqual(competence_weights({0: 0.4, 1: 0.4}), {0: 1.0, 1: 1.0})
        self.assertEqual(competence_weights({}), {})
        self.assertEqual(competence_weights({0: 0.0, 1: 0.0}), {0: 1.0, 1: 1.0})

    def test_weighted_tally(self):
        b = votes("AAB-")
        self.assertEqual(weighted_tally(b, None), {"A": 2.0, "B": 1.0})
        t = weighted_tally(b, {0: 0.5, 2: 1.5})  # seat 1 missing -> 1.0
        self.assertAlmostEqual(t["A"], 1.5)
        self.assertAlmostEqual(t["B"], 1.5)
        self.assertEqual(weighted_tally({}, None), {})


class TopTwoTest(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(top_two(votes("AAABBC"), None), ["A", "B"])

    def test_weights_reorder(self):
        w = {0: 0.5, 1: 0.5, 2: 1.5, 3: 1.0}
        self.assertEqual(top_two(votes("AABC"), w), ["B", "A"])

    def test_single_and_none(self):
        self.assertEqual(top_two(votes("AAA"), None), ["A"])
        self.assertEqual(top_two(votes("---"), None), [])

    def test_borda_breaks_second_place(self):
        b = {
            0: B("A", ["A", "C", "B"]),
            1: B("A", ["A", "C", "B"]),
            2: B("B", ["B", "C", "A"]),
            3: B("C", ["C", "B", "A"]),
        }
        self.assertEqual(top_two(b, None), ["A", "C"])


class EarlyAgreementTest(unittest.TestCase):
    def opts(self, *groups):
        return [Option(id=f"o{i}", holders=list(g)) for i, g in enumerate(groups)]

    def test_agree_and_confident(self):
        o = self.opts([0, 1, 2, 3], [4])
        conf = {0: 0.9, 1: 0.8, 2: 0.7, 3: 0.7, 4: 0.1}
        got = early_agreement(o, conf, 5, CFG)
        self.assertIs(got, o[0])

    def test_low_confidence(self):
        o = self.opts([0, 1, 2, 3], [4])
        conf = {0: 0.6, 1: 0.6, 2: 0.7, 3: 0.7, 4: 1.0}
        self.assertIsNone(early_agreement(o, conf, 5, CFG))

    def test_confidence_exactly_at_floor(self):
        o = self.opts([0, 1, 2])
        self.assertIs(early_agreement(o, {0: 0.7, 1: 0.7, 2: 0.7}, 3, CFG), o[0])

    def test_share_too_low(self):
        o = self.opts([0, 1, 2], [3, 4])
        self.assertIsNone(early_agreement(o, {s: 1.0 for s in range(5)}, 5, CFG))

    def test_k3_and_k7(self):
        self.assertIsNone(early_agreement(self.opts([0, 1], [2]), {0: 1, 1: 1, 2: 1}, 3, CFG))
        o = self.opts([0, 1, 2, 3, 4, 5], [6])
        self.assertIs(early_agreement(o, {s: 0.9 for s in range(7)}, 7, CFG), o[0])

    def test_four_valid_of_five(self):
        o = self.opts([0, 1, 2, 3])
        self.assertIs(early_agreement(o, {s: 0.8 for s in range(4)}, 5, CFG), o[0])

    def test_quorum_failure(self):
        o = self.opts([0, 1])
        self.assertIsNone(early_agreement(o, {0: 1.0, 1: 1.0}, 5, CFG))

    def test_empty_and_no_confidence(self):
        self.assertIsNone(early_agreement([], {}, 5, CFG))
        self.assertIsNone(early_agreement(self.opts([0, 1, 2]), {}, 3, CFG))

    def test_cfg_none(self):
        o = self.opts([0, 1, 2])
        self.assertIs(early_agreement(o, {0: 0.9, 1: 0.9, 2: 0.9}, 3), o[0])


if __name__ == "__main__":
    unittest.main()
