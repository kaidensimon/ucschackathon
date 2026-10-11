import unittest

from council.chamber import budget
from council.chamber.effort import apply_effort, plan_effort
from council.core.config import ChamberConfig
from council.core.schemas import MODE_DEFAULTS, EffortPlan, TaskProfile

STD = MODE_DEFAULTS["standard"]
TPS = [20.0] * 6


def prof(difficulty="medium", contested=None, deliverable="answer"):
    return TaskProfile(difficulty=difficulty, contested=contested, deliverable=deliverable)


def plan(p, tps=TPS, chamber=None, name="standard", mode=STD):
    return plan_effort(p, mode, name, tps, chamber or ChamberConfig())


class FixedModeTest(unittest.TestCase):
    def test_other_modes_untouched(self):
        for name in ("quick", "deep"):
            m = MODE_DEFAULTS[name]
            p = plan(prof("hard", True), name=name, mode=m)
            self.assertEqual(p.level, "normal")
            self.assertEqual(p.rounds, m.rounds)
            self.assertEqual(p.deadline_s, m.deadline_s)
            self.assertEqual(p.reasoning, m.reasoning)
            self.assertEqual(p.max_extra_rounds, 0)
            self.assertEqual(p.rationale, "fixed mode")

    def test_adaptive_off_untouched(self):
        p = plan(prof("hard"), chamber=ChamberConfig(adaptive=False))
        self.assertEqual(p.rationale, "fixed mode")
        self.assertEqual(p.deadline_s, STD.deadline_s)
        self.assertEqual(p.max_extra_rounds, 0)


class LevelTest(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(plan(prof("easy")).level, "light")
        self.assertEqual(plan(prof("medium")).level, "normal")
        self.assertEqual(plan(prof("hard")).level, "heavy")
        self.assertEqual(plan(prof("medium", True)).level, "heavy")
        self.assertEqual(plan(prof("easy", True)).level, "heavy")
        self.assertEqual(plan(prof("easy", False)).level, "light")

    def test_build_and_plan_never_light(self):
        for d in ("build", "plan"):
            self.assertEqual(plan(prof("easy", deliverable=d)).level, "normal")
            self.assertEqual(plan(prof("hard", deliverable=d)).level, "heavy")

    def test_light_shape(self):
        p = plan(prof("easy"))
        self.assertEqual(p.rounds, ["r0", "r1", "r2"])
        self.assertEqual(p.reasoning, "off")
        self.assertEqual(p.max_extra_rounds, 1)

    def test_light_short_mode_kept(self):
        short = STD.model_copy(update={"rounds": ["r0", "r1"]})
        self.assertEqual(plan(prof("easy"), mode=short).rounds, ["r0", "r1"])

    def test_normal_shape(self):
        p = plan(prof("medium"))
        self.assertEqual(p.rounds, STD.rounds)
        self.assertEqual(p.reasoning, STD.reasoning)
        self.assertEqual(p.max_extra_rounds, 1)

    def test_extra_rounds_follow_config(self):
        c = ChamberConfig(max_extra_rounds=0)
        self.assertEqual(plan(prof("easy"), chamber=c).max_extra_rounds, 0)
        self.assertEqual(plan(prof("medium"), chamber=c).max_extra_rounds, 0)
        c = ChamberConfig(max_extra_rounds=3)
        self.assertEqual(plan(prof("hard"), chamber=c).max_extra_rounds, 3)
        self.assertEqual(plan(prof("medium"), chamber=c).max_extra_rounds, 1)

    def test_heavy_shape(self):
        p = plan(prof("hard"))
        self.assertEqual(p.reasoning, "max")
        self.assertEqual(p.max_extra_rounds, ChamberConfig().max_extra_rounds)
        self.assertEqual(p.rounds[-1], "r3")

    def test_heavy_appends_r3(self):
        short = STD.model_copy(update={"rounds": ["r0", "r1", "r2"]})
        self.assertEqual(plan(prof("hard"), mode=short).rounds, ["r0", "r1", "r2", "r3"])

    def test_does_not_mutate_mode(self):
        before = list(STD.rounds)
        plan(prof("easy"))
        plan(prof("hard"))
        self.assertEqual(STD.rounds, before)


class DeadlineTest(unittest.TestCase):
    def test_easy_lt_medium_lt_hard(self):
        c = ChamberConfig(min_deadline_s=1, max_deadline_s=10**7)
        e = plan(prof("easy"), chamber=c).deadline_s
        m = plan(prof("medium"), chamber=c).deadline_s
        h = plan(prof("hard"), chamber=c).deadline_s
        self.assertLess(e, m)
        self.assertLess(m, h)

    def test_slower_seats_longer(self):
        c = ChamberConfig(min_deadline_s=1, max_deadline_s=10**7)
        fast = plan(prof("medium"), tps=[40.0] * 6, chamber=c).deadline_s
        slow = plan(prof("medium"), tps=[10.0] * 6, chamber=c).deadline_s
        self.assertGreater(slow, fast)

    def test_one_slow_seat_counts(self):
        c = ChamberConfig(min_deadline_s=1, max_deadline_s=10**7)
        even = plan(prof("medium"), tps=[30.0] * 6, chamber=c).deadline_s
        mixed = plan(prof("medium"), tps=[30.0] * 5 + [5.0], chamber=c).deadline_s
        self.assertGreater(mixed, even)

    def test_clamps(self):
        lo = plan(prof("easy"), tps=[1000.0] * 6, chamber=ChamberConfig(min_deadline_s=90))
        self.assertEqual(lo.deadline_s, 90)
        hi = plan(prof("hard"), tps=[1.0] * 6, chamber=ChamberConfig(max_deadline_s=500))
        self.assertEqual(hi.deadline_s, 500)

    def test_empty_tps_uses_default(self):
        c = ChamberConfig(min_deadline_s=1, max_deadline_s=10**7)
        a = plan(prof("medium"), tps=[], chamber=c).deadline_s
        b = plan(prof("medium"), tps=[budget.DEFAULT_TPS] * 6, chamber=c).deadline_s
        self.assertAlmostEqual(a, b)

    def test_slack_scales(self):
        base = dict(min_deadline_s=1, max_deadline_s=10**7)
        a = plan(prof("medium"), chamber=ChamberConfig(deadline_slack=1.0, **base)).deadline_s
        b = plan(prof("medium"), chamber=ChamberConfig(deadline_slack=2.0, **base)).deadline_s
        self.assertGreater(b, a)

    def test_rationale(self):
        p = plan(prof("hard", True))
        self.assertIn("hard", p.rationale)
        self.assertIn("contested", p.rationale)
        self.assertIn("reasoning max", p.rationale)


class ApplyTest(unittest.TestCase):
    def test_apply(self):
        p = plan(prof("easy"))
        m = apply_effort(STD, p)
        self.assertEqual(m.rounds, p.rounds)
        self.assertEqual(m.deadline_s, p.deadline_s)
        self.assertEqual(m.reasoning, "off")
        self.assertEqual(m.k, STD.k)
        self.assertEqual(STD.rounds, ["r0", "r1", "r2", "r3"])

    def test_apply_effort_plan_type(self):
        self.assertIsInstance(plan(prof()), EffortPlan)


if __name__ == "__main__":
    unittest.main()
