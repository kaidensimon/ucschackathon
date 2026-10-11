import json
import unittest

from council.core.schemas_v15 import LieFlag
from council.probe.lie_report import NO_PROBE_NOTE, build_report, report_dict, report_text


def mk(seat, cid, level="ok", probe=None, gap=None, reasons=None, text="x"):
    return LieFlag(
        run_id="r1", seat_no=seat, model_id=f"m{seat}", claim_id=cid, text=text,
        probe_score=probe, bluff_gap=gap, level=level, reasons=reasons or [],
    )


SEATS = [(1, "m1"), (2, "m2"), (3, "qwen35-9b")]


class BuildReportTests(unittest.TestCase):
    def test_seat_without_claims_still_listed(self):
        r = build_report("r1", [], SEATS, ["m1"])
        self.assertEqual([s.seat_no for s in r.seats], [1, 2, 3])
        for s in r.seats:
            self.assertEqual(s.claims, 0)
            self.assertEqual(s.level, "ok")
            self.assertIsNone(s.mean_probe)
            self.assertIsNone(s.mean_gap)

    def test_note_when_no_probe(self):
        self.assertEqual(build_report("r", [], SEATS, []).note, NO_PROBE_NOTE)
        self.assertEqual(build_report("r", [], SEATS, ["m1"]).note, "")

    def test_counts_and_means(self):
        flags = [
            mk(3, "c1", "flag", 0.2, 0.6),
            mk(3, "c2", "watch", 0.5, 0.2),
            mk(3, "c3", "ok", None, None),
            mk(3, "c4", "ok", 0.9, 0.0),
        ]
        s = build_report("r", flags, SEATS, ["qwen35-9b"]).seats[2]
        self.assertEqual((s.claims, s.flagged, s.watched), (4, 1, 1))
        self.assertAlmostEqual(s.mean_probe, (0.2 + 0.5 + 0.9) / 3)
        self.assertAlmostEqual(s.mean_gap, (0.6 + 0.2 + 0.0) / 3)

    def test_level_two_flags_is_flag(self):
        flags = [mk(1, f"c{i}", "flag" if i < 2 else "ok") for i in range(20)]
        self.assertEqual(build_report("r", flags, SEATS, []).seats[0].level, "flag")

    def test_level_quarter_ratio_with_one_flag(self):
        flags = [mk(1, "c1", "flag")] + [mk(1, f"c{i}") for i in range(2, 5)]  # 1/4
        self.assertEqual(build_report("r", flags, SEATS, []).seats[0].level, "flag")

    def test_level_low_ratio_one_flag_is_watch(self):
        flags = [mk(1, "c1", "flag")] + [mk(1, f"c{i}") for i in range(2, 6)]  # 1/5
        self.assertEqual(build_report("r", flags, SEATS, []).seats[0].level, "watch")

    def test_level_watch_only_and_ok(self):
        r = build_report("r", [mk(1, "c1", "watch"), mk(2, "c1", "ok")], SEATS, [])
        self.assertEqual(r.seats[0].level, "watch")
        self.assertEqual(r.seats[1].level, "ok")

    def test_flags_sorted_worst_first(self):
        flags = [
            mk(1, "a", "ok", 0.1),
            mk(1, "b", "watch", 0.4),
            mk(2, "c", "flag", None),
            mk(2, "d", "flag", 0.7),
            mk(3, "e", "flag", 0.1),
            mk(3, "f", "watch", None),
        ]
        order = [f.claim_id for f in build_report("r", flags, SEATS, []).flags]
        self.assertEqual(order, ["e", "d", "c", "b", "f", "a"])

    def test_unknown_seat_flag_kept_in_flags(self):
        r = build_report("r", [mk(9, "c1", "flag")], SEATS, [])
        self.assertEqual(len(r.flags), 1)
        self.assertEqual(len(r.seats), 3)

    def test_input_not_mutated(self):
        flags = [mk(1, "a", "ok"), mk(1, "b", "flag")]
        build_report("r", flags, SEATS, [])
        self.assertEqual([f.claim_id for f in flags], ["a", "b"])


class ReportTextTests(unittest.TestCase):
    def setUp(self):
        self.flags = [
            mk(3, "c1", "flag", 0.12, reasons=["probe low", "says sure"], text="Paris is in Spain"),
            mk(3, "c2", "watch", 0.5, text="maybe"),
            mk(3, "c3", "ok", 0.9),
            mk(3, "c4", "ok", 0.8),
            mk(3, "c5", "ok", 0.7),
            mk(3, "c6", "ok", 0.6),
        ]
        self.report = build_report("r1", self.flags, SEATS, ["qwen35-9b"])

    def test_seat_line_format(self):
        text = report_text(self.report)
        self.assertIn("seat 3 qwen35-9b: 6 claims, 1 flagged, 1 watch, mean probe 0.60", text)

    def test_seat_with_no_probe_prints_na(self):
        text = report_text(build_report("r", [], SEATS, []))
        self.assertIn("seat 1 m1: 0 claims, 0 flagged, 0 watch, mean probe n/a", text)
        self.assertIn(NO_PROBE_NOTE, text)

    def test_worst_claims_with_reasons(self):
        text = report_text(self.report)
        self.assertIn("Paris is in Spain", text)
        self.assertIn("probe low", text)
        self.assertIn("says sure", text)
        self.assertNotIn("c3", text)

    def test_max_flags_limits(self):
        text = report_text(self.report, max_flags=1)
        self.assertIn("Paris is in Spain", text)
        self.assertNotIn("maybe", text)

    def test_no_bad_claims(self):
        text = report_text(build_report("r", [mk(1, "c1", "ok", 0.9)], SEATS, []))
        self.assertIn("no flagged claims", text)

    def test_plain_ascii(self):
        f = mk(1, "c1", "flag", 0.1, reasons=["café — bad"], text="naïve “claim”")
        text = report_text(build_report("r", [f], [(1, "mé")], []))
        text.encode("ascii")

    def test_long_text_truncated(self):
        f = mk(1, "c1", "flag", 0.1, text="word " * 200)
        text = report_text(build_report("r", [f], SEATS, []))
        self.assertLess(max(len(line) for line in text.splitlines()), 200)


class ReportDictTests(unittest.TestCase):
    def test_json_safe_and_roundtrip(self):
        r = build_report("r1", [mk(1, "c1", "flag", 0.1, 0.5, ["why"])], SEATS, ["m1"])
        d = report_dict(r)
        self.assertEqual(json.loads(json.dumps(d)), d)
        self.assertEqual(d["run_id"], "r1")
        self.assertEqual(len(d["seats"]), 3)
        self.assertEqual(d["flags"][0]["claim_id"], "c1")


if __name__ == "__main__":
    unittest.main()
