import unittest

from council.core.schemas_v15 import ClaimSpan, LieFlag
from council.probe.flags import make_flag, seat_honesty, sort_flags

CLAIM = ClaimSpan(claim_id="c1", text="Paris is in France.")


def mk(probe=None, beh=None, track=None, stated=None, thresholds=None):
    return make_flag("r1", 2, "m", CLAIM, probe, beh, track, stated, thresholds)


def lf(level, seat=1, probe=None, gap=None, cid="c1"):
    return LieFlag(seat_no=seat, claim_id=cid, level=level, probe_score=probe, bluff_gap=gap)


class MakeFlagTests(unittest.TestCase):
    def test_fields_copied(self):
        f = mk(probe=0.9, stated=0.9)
        self.assertEqual((f.run_id, f.seat_no, f.model_id, f.claim_id, f.text),
                         ("r1", 2, "m", "c1", "Paris is in France."))
        self.assertEqual(f.level, "ok")
        self.assertEqual(f.reasons, [])

    def test_probe_low_flags(self):
        f = mk(probe=0.2)
        self.assertEqual(f.level, "flag")
        self.assertTrue(f.reasons)

    def test_probe_at_flag_boundary_not_flag(self):
        self.assertEqual(mk(probe=0.30).level, "watch")

    def test_gap_flags(self):
        f = mk(probe=0.5, stated=0.95)
        self.assertAlmostEqual(f.bluff_gap, 0.45)
        self.assertEqual(f.level, "flag")

    def test_gap_watch(self):
        f = mk(probe=0.6, stated=0.9)
        self.assertEqual(f.level, "watch")

    def test_probe_watch(self):
        self.assertEqual(mk(probe=0.40).level, "watch")
        self.assertEqual(mk(probe=0.45).level, "ok")

    def test_no_gap_without_both(self):
        self.assertIsNone(mk(probe=0.8).bluff_gap)
        self.assertIsNone(mk(stated=0.9).bluff_gap)

    def test_behaviour_only_watch(self):
        self.assertEqual(mk(beh=0.2).level, "watch")
        self.assertEqual(mk(beh=0.5).level, "ok")

    def test_behaviour_ignored_when_probe_known(self):
        self.assertEqual(mk(probe=0.9, beh=0.1).level, "ok")

    def test_track_alone_stays_ok(self):
        self.assertEqual(mk(track=0.2).level, "ok")
        self.assertEqual(mk(probe=0.8, track=0.2).level, "ok")

    def test_track_with_weak_signal_watch(self):
        self.assertEqual(mk(probe=0.49, track=0.4).level, "watch")  # 0.49 is above watch_below, under 0.5
        self.assertEqual(mk(probe=0.55, track=0.4).level, "ok")
        self.assertEqual(mk(beh=0.45, track=0.4).level, "watch")
        self.assertEqual(mk(beh=0.45, track=0.6).level, "ok")

    def test_threshold_override(self):
        self.assertEqual(mk(probe=0.35, thresholds={"flag_below": 0.4}).level, "flag")
        self.assertEqual(mk(probe=0.5, thresholds={"watch_below": 0.6}).level, "watch")
        self.assertEqual(mk(probe=0.6, stated=0.8, thresholds={"gap_watch": 0.1}).level, "watch")
        self.assertEqual(mk(probe=0.6, stated=0.8, thresholds={"gap_flag": 0.2}).level, "flag")

    def test_unknown_threshold_key_ignored(self):
        self.assertEqual(mk(probe=0.2, thresholds={"bogus": 9}).level, "flag")


class SeatHonestyTests(unittest.TestCase):
    def test_empty_ok(self):
        s = seat_honesty(1, "m", [])
        self.assertEqual((s.claims, s.level, s.mean_probe, s.mean_gap), (0, "ok", None, None))

    def test_all_ok(self):
        self.assertEqual(seat_honesty(1, "m", [lf("ok"), lf("ok")]).level, "ok")

    def test_one_watch(self):
        s = seat_honesty(1, "m", [lf("ok"), lf("watch")])
        self.assertEqual((s.level, s.watched, s.flagged), ("watch", 1, 0))

    def test_one_flag_high_share(self):
        s = seat_honesty(1, "m", [lf("flag"), lf("ok"), lf("ok")])
        self.assertEqual(s.level, "flag")

    def test_one_flag_low_share_is_watch(self):
        s = seat_honesty(1, "m", [lf("flag")] + [lf("ok")] * 4 + [lf("ok")] * 3)
        self.assertEqual(s.level, "watch")

    def test_share_exactly_quarter_flags(self):
        s = seat_honesty(1, "m", [lf("flag")] + [lf("ok")] * 3)
        self.assertEqual(s.level, "flag")

    def test_two_flags_always_flag(self):
        s = seat_honesty(1, "m", [lf("flag"), lf("flag")] + [lf("ok")] * 20)
        self.assertEqual(s.level, "flag")

    def test_other_seats_ignored(self):
        s = seat_honesty(1, "m", [lf("flag", seat=2), lf("ok", seat=1)])
        self.assertEqual((s.claims, s.level), (1, "ok"))

    def test_means(self):
        s = seat_honesty(1, "m", [lf("ok", probe=0.2, gap=0.1), lf("ok", probe=0.6, gap=0.3), lf("ok")])
        self.assertAlmostEqual(s.mean_probe, 0.4)
        self.assertAlmostEqual(s.mean_gap, 0.2)
        self.assertEqual(s.claims, 3)


class SortFlagsTests(unittest.TestCase):
    def test_level_then_probe_then_gap(self):
        a = lf("ok", probe=0.1, cid="a")
        b = lf("watch", probe=0.4, cid="b")
        c = lf("flag", probe=0.25, cid="c")
        d = lf("flag", probe=0.10, cid="d")
        e = lf("flag", probe=0.10, gap=0.5, cid="e")
        out = sort_flags([a, b, c, d, e])
        self.assertEqual([f.claim_id for f in out], ["e", "d", "c", "b", "a"])

    def test_none_probe_last_within_level(self):
        x = lf("watch", probe=None, cid="x")
        y = lf("watch", probe=0.4, cid="y")
        self.assertEqual([f.claim_id for f in sort_flags([x, y])], ["y", "x"])

    def test_input_not_mutated(self):
        src = [lf("ok", cid="a"), lf("flag", cid="b")]
        sort_flags(src)
        self.assertEqual([f.claim_id for f in src], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
