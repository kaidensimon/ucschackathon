import unittest

from council.host.memplan import plan_memory


class MemPlanTests(unittest.TestCase):
    def test_everything_fits_untouched(self):
        seats = [f"m{i}" for i in range(4)]
        gib = {s: 16.5 for s in seats}
        gib["plan"] = 16.5
        p = plan_memory(seats, {"planner": "plan", "worker": None}, gib, 121.6)
        self.assertTrue(p.fits)
        self.assertEqual(p.shared_roles, [])
        self.assertEqual(p.dropped, [])
        self.assertEqual(p.roles, {"planner": "plan"})
        self.assertEqual(set(p.num_ctx.values()), {16384})
        self.assertAlmostEqual(p.budget_gib, 111.6)
        self.assertIn("plan", p.per_model)

    def test_real_case_planner_shared(self):
        seats = [f"m{i}" for i in range(6)]
        gib = {s: 17.5 for s in seats}
        gib["m3"] = 18.0  # largest seat
        gib["plan"] = 16.5
        p = plan_memory(seats, {"planner": "plan", "clerk": None}, gib, 121.6)
        self.assertTrue(p.fits)
        self.assertEqual(p.shared_roles, ["planner"])
        self.assertEqual(p.roles["planner"], "m3")
        self.assertNotIn("plan", p.per_model)
        self.assertEqual(set(p.num_ctx.values()), {16384})
        self.assertTrue(any("planner" in n for n in p.notes))

    def test_worker_goes_to_smallest_seat(self):
        seats = ["a", "b", "c", "d", "e", "f"]
        gib = {"a": 18, "b": 17, "c": 16, "d": 17, "e": 18, "f": 17, "w": 17}
        p = plan_memory(seats, {"worker": "w"}, gib, 121.6)
        self.assertEqual(p.roles["worker"], "c")

    def test_tight_case_steps_context(self):
        seats = [f"m{i}" for i in range(6)]
        gib = {s: 19.5 for s in seats}  # 117 GiB > 111.6
        p = plan_memory(seats, {}, gib, 121.6)
        self.assertTrue(p.fits)
        self.assertLessEqual(sum(p.per_model.values()), p.budget_gib + 1e-6)
        self.assertIn(8192, p.num_ctx.values())
        self.assertNotIn(4096, p.num_ctx.values())

    def test_impossible_case(self):
        seats = ["a", "b", "c"]
        gib = {s: 50.0 for s in seats}
        p = plan_memory(seats, {}, gib, 121.6)
        self.assertFalse(p.fits)
        self.assertEqual(set(p.per_model), set(seats))
        self.assertEqual(set(p.num_ctx.values()), {4096})
        self.assertTrue(any("short" in n for n in p.notes))
        self.assertEqual(p.dropped, [])

    def test_drops_non_seat_when_nothing_else_helps(self):
        # Seats fit only at a low context; the extra worker model gets dropped, not a seat.
        seats = ["a", "b", "c"]
        gib = {"a": 36.0, "b": 36.0, "c": 36.0, "x": 20.0}
        p = plan_memory(seats, {"worker": "x"}, gib, 121.6, reserve_gib=10.0)
        # worker role is shared first, so x is simply not loaded
        self.assertNotIn("x", p.per_model)
        self.assertEqual(p.shared_roles, ["worker"])
        self.assertTrue(p.fits)

    def test_missing_gib_and_reported_overhead(self):
        p = plan_memory(["a"], {}, {}, 121.6)
        self.assertEqual(p.per_model["a"], 14.0)
        r = plan_memory(["a"], {}, {"a": 10.0}, 121.6, reported=True)
        self.assertAlmostEqual(r.per_model["a"], 13.5)
        r2 = plan_memory(["a"], {}, {"a": 10.0}, 121.6)
        self.assertAlmostEqual(r2.per_model["a"], 10.0)

    def test_floor_is_sixty_percent(self):
        p = plan_memory(["a"], {}, {"a": 100.0}, 50.0)
        self.assertFalse(p.fits)
        self.assertAlmostEqual(p.per_model["a"], 100.0 - 1.2 * 1.5)  # 4096 is 12288 below default
        p2 = plan_memory(["a"], {}, {"a": 2.0}, 1.0, reserve_gib=0.0)
        self.assertAlmostEqual(p2.per_model["a"], 1.2)  # floor 60% of 2.0

    def test_seat_never_dropped(self):
        p = plan_memory(["a", "b"], {"planner": "a"}, {"a": 80.0, "b": 80.0}, 121.6)
        self.assertFalse(p.fits)
        self.assertEqual(p.dropped, [])
        self.assertEqual(set(p.per_model), {"a", "b"})


if __name__ == "__main__":
    unittest.main()
