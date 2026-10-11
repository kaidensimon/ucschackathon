import unittest

from council.core.schemas import ModelEntry
from council.router.roles import assign_roles, extra_models


def entry(id, params=10.0, roles=None, structured="grammar", code=0.5, status="active"):
    return ModelEntry(
        id=id, params_b=params, roles=roles or ["seat"], structured=structured,
        priors={"code": code}, status=status,
    )


class TestRoles(unittest.TestCase):
    def setUp(self):
        self.reg = {
            "big": entry("big", 70, code=0.6),
            "mid": entry("mid", 30, code=0.9),
            "small": entry("small", 4, code=0.2),
            "tiny": entry("tiny", 1, code=0.1),
            "off": entry("off", 8, status="disabled"),
        }
        self.seats = ["big", "mid", "small", "tiny"]

    def test_pick_from_seats(self):
        r = assign_roles(self.seats, self.reg, {}, False)
        self.assertEqual(r["planner"], "big")
        self.assertEqual(r["senior_worker"], "mid")
        self.assertEqual(r["worker"], "tiny")  # smallest, not planner
        self.assertEqual(r["clerk"], "tiny")

    def test_tps_wins(self):
        tps = {"big": 5, "mid": 20, "small": 90, "tiny": 50}
        r = assign_roles(self.seats, self.reg, {}, False, tps)
        self.assertEqual(r["worker"], "small")
        self.assertEqual(r["clerk"], "small")

    def test_planner_tag_wins(self):
        reg = dict(self.reg)
        reg["mid"] = entry("mid", 30, roles=["seat", "planner"], code=0.9)
        r = assign_roles(self.seats, reg, {}, False)
        self.assertEqual(r["planner"], "mid")

    def test_planner_needs_structured(self):
        reg = dict(self.reg)
        # schemas.StructuredMode has no "none" value today; bypass validation to test the guard.
        reg["big"] = ModelEntry.model_construct(**{**reg["big"].__dict__, "structured": "none"})
        r = assign_roles(self.seats, reg, {}, False)
        self.assertEqual(r["planner"], "mid")

    def test_worker_not_planner(self):
        tps = {"big": 500, "mid": 1, "small": 1, "tiny": 1}
        r = assign_roles(self.seats, self.reg, {}, False, tps)
        self.assertEqual(r["planner"], "big")
        self.assertNotEqual(r["worker"], "big")
        self.assertEqual(r["clerk"], "big")

    def test_single_seat_does_all(self):
        r = assign_roles(["mid"], self.reg, {}, False)
        self.assertEqual(set(r.values()), {"mid"})
        self.assertEqual(set(r), {"planner", "senior_worker", "worker", "clerk"})

    def test_preferred_used_when_extra_allowed(self):
        r = assign_roles(self.seats, self.reg, {"planner": "off", "worker": "mid"}, True)
        self.assertEqual(r["planner"], "big")  # off is disabled
        self.assertEqual(r["worker"], "mid")

    def test_preferred_ignored_when_extra_not_allowed(self):
        reg = dict(self.reg)
        reg["ext"] = entry("ext", 3)
        r = assign_roles(self.seats, reg, {"clerk": "ext"}, False)
        self.assertNotEqual(r["clerk"], "ext")
        r2 = assign_roles(self.seats, reg, {"clerk": "ext"}, True)
        self.assertEqual(r2["clerk"], "ext")

    def test_none_preferred_and_unknown(self):
        r = assign_roles(self.seats, self.reg, {"planner": None, "clerk": "ghost"}, True)
        self.assertIn(r["planner"], self.seats)
        self.assertIn(r["clerk"], self.seats)

    def test_tie_break_by_id(self):
        reg = {"b": entry("b", 5, code=0.5), "a": entry("a", 5, code=0.5)}
        r = assign_roles(["b", "a"], reg, {}, False)
        self.assertEqual(r["planner"], "a")
        self.assertEqual(r["senior_worker"], "a")
        self.assertEqual(r["clerk"], "a")
        self.assertEqual(r["worker"], "b")

    def test_deterministic_order(self):
        a = assign_roles(self.seats, self.reg, {}, False)
        b = assign_roles(list(reversed(self.seats)), self.reg, {}, False)
        self.assertEqual(a, b)

    def test_empty_seats(self):
        self.assertEqual(assign_roles([], self.reg, {}, False), {})

    def test_extra_models(self):
        roles = {"planner": "big", "worker": "ext", "clerk": "ext2", "senior_worker": "ext"}
        self.assertEqual(extra_models(roles, ["big", "mid"]), ["ext", "ext2"])
        self.assertEqual(extra_models({"planner": "big"}, ["big"]), [])


if __name__ == "__main__":
    unittest.main()
