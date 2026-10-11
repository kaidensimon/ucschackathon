import unittest

from council.core import event_types as ET
from council.core.schemas import (
    CallResult,
    CallSpec,
    Decision,
    Event,
    LineupRecord,
    ModelEntry,
    SeatAssignment,
    TaskProfile,
)
from council.core.store import Store
from council.router.competence import SkillTable
from council.router.stats import (
    load_table,
    quarantine_candidates,
    update_from_run,
    update_from_truth,
)


def ev(t, **p):
    return Event(type=t, payload=p)


def lineup():
    return LineupRecord(seats=[
        SeatAssignment(seat_no=1, model_id="a"),
        SeatAssignment(seat_no=2, model_id="b"),
        SeatAssignment(seat_no=3, model_id="c"),
    ])


def events():
    return [
        ev(ET.OPTIONS_CLUSTERED, round=0, options=[
            {"id": "o1", "holders": [1]}, {"id": "o2", "holders": [2, 3]}]),
        ev(ET.TURN_COMPLETED, purpose="seat.r1", seat_no=1, parsed={
            "reviews": [{"target": "A", "flaws": [{"id": "f1"}]}], "changed_because": []}),
        ev(ET.TURN_TIMEOUT, model_id="c", seat_no=3),
        ev(ET.TURN_INVALID, model_id="c", seat_no=3),
        # seat 2 moves o2 -> o1 citing f1 (seat 1's flaw); seat 3 stays
        ev(ET.BALLOT_CAST, seat_no=1, round=2, ballot={"choice": "o1"}),
        ev(ET.BALLOT_CAST, seat_no=2, round=2, ballot={"choice": "o1", "changed_because": ["f1"]}),
        ev(ET.BALLOT_CAST, seat_no=3, round=2, ballot={"choice": "o2"}),
    ]


PROFILE = TaskProfile(categories={"math": 0.6, "code": 0.4})


class UpdateFromRunTest(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.table = SkillTable({})

    def run_it(self, accepted=True, option="o1"):
        return update_from_run(events(), lineup(), PROFILE, Decision(outcome="majority", option_id=option),
                               accepted, self.table, self.store)

    def test_skill_rewards_half_weight(self):
        self.run_it()
        # a: round-0 == final -> reward 1, weight 0.5*0.6
        self.assertAlmostEqual(self.table.trials("a", "math"), 0.3)
        self.assertGreater(self.table.mean("a", "math"), 0.5)
        self.assertLess(self.table.mean("b", "math"), 0.5)
        self.assertIn(("a", "math"), self.store.get_model_stats())

    def test_rejected_gives_zero(self):
        self.run_it(accepted=False)
        self.assertLess(self.table.mean("a", "math"), 0.5)

    def test_behaviour(self):
        s = self.run_it()
        self.assertEqual(s["flip_to_right"], 1)
        b = self.store.behaviour_get("b")
        self.assertEqual((b.flip_to_right, b.runs, b.agree_with_decision), (1, 1, 1))
        self.assertEqual(self.store.behaviour_get("a").persuaded, 1)
        c = self.store.behaviour_get("c")
        self.assertEqual((c.invalid, c.timeouts, c.agree_with_decision), (1, 1, 0))

    def test_flip_to_wrong(self):
        self.run_it(option="o2")
        # seat 2 left o2, which turned out right
        self.assertEqual(self.store.behaviour_get("b").flip_to_wrong, 1)
        self.assertEqual(self.store.behaviour_get("b").flip_to_right, 0)

    def test_no_decision_option(self):
        s = self.run_it(option=None)
        self.assertEqual(s["skill_updates"], 0)
        self.assertEqual(self.store.behaviour_get("a").runs, 1)


class TruthAndTableTest(unittest.TestCase):
    def test_truth_full_weight_persists(self):
        store, table = Store(), SkillTable({"a": {"math": 0.5}})
        r = update_from_truth("a", "math", True, table, store)
        self.assertAlmostEqual(table.trials("a", "math"), 1.0)
        self.assertEqual(store.get_model_stats()[("a", "math")], (r["alpha"], r["beta"]))

    def test_load_table(self):
        store = Store()
        store.upsert_model_stat("a", "math", 5.0, 1.0)
        reg = [ModelEntry(id="a", priors={"math": 0.2, "code": 0.9})]
        t = load_table(reg, store)
        self.assertAlmostEqual(t.mean("a", "math"), 5 / 6)
        self.assertAlmostEqual(t.mean("a", "code"), 0.9)


class QuarantineTest(unittest.TestCase):
    def test_candidates(self):
        store = Store()
        i = 0
        for model, oks in (("a", [True] * 10 + [False] * 3), ("b", [False, False] + [True] * 8)):
            for ok in oks:
                i += 1
                spec = CallSpec(model_id=model, call_id=f"c{i}", run_id="r")
                res = CallResult(call_id=f"c{i}", model_id=model, ok=ok, error=None if ok else "timeout")
                store.record_turn(spec, res)
        reg = [ModelEntry(id="a"), ModelEntry(id="b"), ModelEntry(id="c", status="quarantined")]
        self.assertEqual(quarantine_candidates(store, reg), ["a"])
        self.assertEqual(quarantine_candidates(store, reg, window=3, strikes=3), ["a"])
        self.assertEqual(quarantine_candidates(store, reg, strikes=2), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
