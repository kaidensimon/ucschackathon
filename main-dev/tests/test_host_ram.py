import unittest

from council.host.ram import AdmitPlan, RamBudget, Resident


def make(avail=100.0):
    fp = {
        ("core", "live"): 10.0,
        ("emb", "live"): 2.0,
        ("a", "live"): 20.0,
        ("b", "live"): 30.0,
        ("big", "live"): 60.0,
        ("a", "batch"): 5.0,
    }
    return RamBudget(lambda: avail, 12.0, {"core", "emb"}, fp)


class RamTest(unittest.TestCase):
    def test_footprint(self):
        r = make()
        self.assertEqual(r.footprint("a", "batch"), 5.0)
        with self.assertRaises(KeyError):
            r.footprint("zzz", "live")

    def test_seat_budget(self):
        self.assertEqual(make().seat_budget(115.0), 115 - 12 - 12)

    def test_admit_no_evict(self):
        p = make(100).plan_admit("a", "live", [])
        self.assertTrue(p.ok)
        self.assertEqual(p.evict, [])

    def test_admit_evict_lru(self):
        res = [
            Resident("core", "live", 10, True, 1.0),
            Resident("b", "live", 30, True, 5.0),
            Resident("a", "live", 20, True, 2.0),
        ]
        p = make(40).plan_admit("big", "live", res)  # free 28, need 60
        self.assertTrue(p.ok)
        self.assertEqual(p.evict, ["a", "b"])

    def test_admit_skips_busy_and_core(self):
        res = [
            Resident("core", "live", 10, True, 1.0),
            Resident("b", "live", 30, False, 2.0),
        ]
        p = make(40).plan_admit("big", "live", res)
        self.assertFalse(p.ok)
        self.assertEqual(p.evict, [])
        self.assertTrue(p.reason)

    def test_admit_stops_when_fits(self):
        res = [
            Resident("a", "live", 20, True, 1.0),
            Resident("b", "live", 30, True, 2.0),
        ]
        p = make(25).plan_admit("b", "live", res)  # free 13, need 30; evict a -> 33
        self.assertEqual(p.evict, ["a"])

    def test_fits(self):
        r = make()
        self.assertTrue(r.fits(["a", "b"], 50.0))
        self.assertFalse(r.fits(["a", "b"], 49.9))
        self.assertTrue(r.fits([], 0.0))


if __name__ == "__main__":
    unittest.main()
