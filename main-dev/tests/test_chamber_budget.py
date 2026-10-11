import unittest

from council.chamber.budget import (
    TURN_CAPS,
    can_start_round,
    chair_reserve_s,
    estimate_round_s,
    turn_timeout,
    turn_timeout_s,
)


class BudgetTests(unittest.TestCase):
    def test_caps_table(self):
        self.assertEqual(TURN_CAPS["r0"], {"max_output": 700, "max_reasoning": 1500, "temperature": None})
        self.assertEqual(TURN_CAPS["r1"]["temperature"], 0.4)
        self.assertEqual(TURN_CAPS["r3"]["max_output"], 350)
        self.assertEqual(TURN_CAPS["chair"]["max_reasoning"], 1500)
        self.assertEqual(TURN_CAPS["ratify"], {"max_output": 60, "max_reasoning": 0, "temperature": 0.0})
        self.assertEqual(TURN_CAPS["clerk"], {"max_output": 400, "max_reasoning": 0, "temperature": 0.0})

    def test_estimate_off_no_reasoning(self):
        # r1 off: 500 tokens per seat, tps 100 -> 5s each, 2 seats -> 10s
        self.assertAlmostEqual(estimate_round_s("r1", [100.0, 100.0], "off"), 10.0)

    def test_estimate_with_reasoning(self):
        # r1 council: (500+800)=1300 tokens at 100 tps -> 13s per seat
        self.assertAlmostEqual(estimate_round_s("r1", [100.0], "council"), 13.0)

    def test_reasoning_ignored_when_cap_zero(self):
        self.assertAlmostEqual(estimate_round_s("ratify", [60.0], "max"), 1.0)

    def test_concurrency_divides_capped_at_two(self):
        base = estimate_round_s("r2", [40.0, 40.0], "off")
        self.assertAlmostEqual(estimate_round_s("r2", [40.0, 40.0], "off", concurrent=2), base / 2)
        self.assertAlmostEqual(estimate_round_s("r2", [40.0, 40.0], "off", concurrent=8), base / 2)

    def test_tps_floor_of_one(self):
        # tps 0 treated as 1: 400 tokens -> 400s
        self.assertAlmostEqual(estimate_round_s("clerk", [0.0], "off"), 400.0)
        self.assertAlmostEqual(estimate_round_s("clerk", [-5.0], "off"), 400.0)

    def test_can_start_round(self):
        cost = estimate_round_s("r2", [50.0], "council")
        self.assertTrue(can_start_round("r2", [50.0], "council", cost))
        self.assertTrue(can_start_round("r2", [50.0], "council", cost + 100))
        self.assertFalse(can_start_round("r2", [50.0], "council", cost - 0.01))

    def test_turn_timeout(self):
        self.assertEqual(turn_timeout(30.0, 10.0), 10.0)
        self.assertEqual(turn_timeout(5.0, 100.0), 5.0)
        self.assertEqual(turn_timeout(5.0, 0.2), 1.0)
        self.assertEqual(turn_timeout(0.0, 0.0), 1.0)


class TurnTimeoutTests(unittest.TestCase):
    """turn_timeout_s: slack * tokens / (tps / max(1, concurrent * 0.5)), floor, cap by time left."""

    def test_formula_with_reasoning_and_six_models_on_one_gpu(self):
        # r0 council: 700 + 1500 tokens; 30 tps alone, 6 together -> 10 tps; 2.5 * 2200 / 10
        self.assertAlmostEqual(turn_timeout_s("r0", 30.0, "council", 6, None), 550.0)

    def test_reasoning_off_leaves_the_reasoning_tokens_out(self):
        self.assertAlmostEqual(turn_timeout_s("r0", 30.0, "off", 6, None), 175.0)
        # ratify has no reasoning budget at all
        self.assertAlmostEqual(turn_timeout_s("ratify", 1.0, "max", 1, None), 150.0)

    def test_floor(self):
        self.assertEqual(turn_timeout_s("ratify", 75.0, "off", 1, None), 60.0)
        self.assertEqual(turn_timeout_s("ratify", 75.0, "off", 1, None, floor_s=20), 20.0)
        self.assertEqual(turn_timeout_s("r3", 500.0, "council", 6, None), 60.0)

    def test_unknown_speed_is_15_tokens_per_second(self):
        want = 2.5 * 500 / 15.0
        for tps in (None, 0, 0.0, -3.0):
            self.assertAlmostEqual(turn_timeout_s("r1", tps, "off", 1, None), want)

    def test_one_or_two_models_do_not_slow_each_other(self):
        alone = turn_timeout_s("chair", 20.0, "council", 1, None)
        self.assertAlmostEqual(alone, 2.5 * 2400 / 20.0)
        self.assertAlmostEqual(turn_timeout_s("chair", 20.0, "council", 2, None), alone)
        self.assertAlmostEqual(turn_timeout_s("chair", 20.0, "council", 0, None), alone)
        self.assertAlmostEqual(turn_timeout_s("chair", 20.0, "council", 4, None), alone * 2)

    def test_slack(self):
        self.assertAlmostEqual(turn_timeout_s("r0", 10.0, "off", 1, None, slack=1.0), 70.0)

    def test_capped_by_time_left_but_never_under_45(self):
        self.assertEqual(turn_timeout_s("r0", 30.0, "council", 6, 100.0), 100.0)
        self.assertEqual(turn_timeout_s("r0", 30.0, "council", 6, 10.0), 45.0)
        self.assertEqual(turn_timeout_s("r0", 30.0, "council", 6, 0.0), 45.0)
        self.assertEqual(turn_timeout_s("r0", 30.0, "council", 6, -50.0), 45.0)
        self.assertAlmostEqual(turn_timeout_s("r0", 30.0, "council", 6, 5000.0), 550.0)
        # the floor is capped too: 60 s wanted, 50 s left
        self.assertEqual(turn_timeout_s("ratify", 75.0, "off", 1, 50.0), 50.0)

    def test_the_box_case_is_far_over_the_old_flat_120(self):
        # slowest model of the box: 15 tps alone, six seats generating together
        self.assertGreater(turn_timeout_s("r0", 15.0, "council", 6, None), 120.0)
        self.assertGreater(turn_timeout_s("r1", 15.0, "council", 6, None), 120.0)
        self.assertGreater(turn_timeout_s("chair", 15.0, "council", 1, None), 30.0)

    def test_tokens_override(self):
        self.assertAlmostEqual(turn_timeout_s("clerk", None, "off", 1, None, tokens=600), 100.0)
        self.assertAlmostEqual(turn_timeout_s("no such round", 10.0, "off", 1, None, tokens=400), 100.0)

    def test_chair_reserve(self):
        # the Chair alone at unknown speed wants 2.5 * 2400 / 15 = 400 s; at most 40% of the deadline
        self.assertAlmostEqual(chair_reserve_s(None, "council", 300.0), 120.0)
        self.assertAlmostEqual(chair_reserve_s(None, "council", 5000.0), 400.0)
        self.assertAlmostEqual(chair_reserve_s(75.0, "off", 1000.0), 60.0)  # floor
        self.assertEqual(chair_reserve_s(None, "council", 0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
