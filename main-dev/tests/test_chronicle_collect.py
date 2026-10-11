import unittest

from council.chronicle.collect import collect_candidates
from council.chronicle.rules import SOURCE_KINDS
from council.core.schemas import Event


def ev(t, seq, **payload):
    return Event(type=t, seq=seq, run_id="r1", payload=payload)


def by(cands, kind):
    return [c for c in cands if c.source == kind]


class CollectTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(collect_candidates([], ""), [])

    def test_choice_and_rule(self):
        evs = [
            ev("user.input_requested", 1, request_id="q1", question="Tabs or spaces?"),
            ev("user.input_received", 2, request_id="q1", choice="spaces"),
            ev("user.input_received", 3, text="From now on use type hints."),
        ]
        c = collect_candidates(evs, "t")
        self.assertIn("Tabs or spaces?", by(c, "single_choice")[0].text)
        self.assertEqual(by(c, "single_choice")[0].evidence[0].event_seq, 2)
        self.assertEqual(by(c, "explicit_rule")[0].evidence[0].run_id, "r1")

    def test_plan_edit(self):
        evs = [
            ev("plan.drafted", 1, plan={"goal": "G"}),
            ev("plan.drafted", 2, plan={"goal": "G"}, edited_by_user=True),
        ]
        c = collect_candidates(evs, "")
        self.assertEqual(len(by(c, "single_choice")), 1)
        self.assertEqual(c[0].evidence[0].event_seq, 2)

    def test_cancel_and_override(self):
        evs = [
            ev("run.cancelled", 1, reason="slow"),
            ev("review.verdict", 2, verdict="accept", overridden_by_user=True),
            ev("review.verdict", 3, verdict="fix"),
        ]
        self.assertEqual(len(by(collect_candidates(evs, "x"), "override")), 2)

    def test_ballot_lesson(self):
        evs = [
            ev("ballot.cast", 1, ballot={"choice": "a", "lesson": "Check edge cases first"}),
            ev("ballot.cast", 2, ballot={"choice": "a"}),
        ]
        c = collect_candidates(evs, "")
        self.assertEqual([x.text for x in by(c, "inferred")], ["Check edge cases first"])

    def test_repeated_failure(self):
        evs = [
            ev("task.failed", 1, task_id="t1", attempts=1, title="T", failing_check="lint"),
            ev("task.failed", 2, task_id="t2", attempts=1),
            ev("task.failed", 3, task_id="t1", attempts=2, title="T", failing_check="lint"),
        ]
        c = by(collect_candidates(evs, ""), "inferred")
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0].evidence[0].event_seq, 3)

    def test_departure(self):
        evs = [
            ev("decision.final", 1, decision={
                "outcome": "chair",
                "departures": [{"chronicle_entry_id": "e1", "why": "new facts"}],
            })
        ]
        c = collect_candidates(evs, "")
        self.assertEqual(c[0].source, "contradiction")
        self.assertIn("e1", c[0].text)

    def test_task_text_rule(self):
        c = collect_candidates([], "Build a tool. Never use global state. Keep it small.")
        self.assertEqual([x.text for x in c], ["Never use global state."])
        self.assertEqual(c[0].source, "user")

    def test_task_rule_scope(self):
        c = collect_candidates([], "From now on, always use tabs for indentation in this project.")
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0].source, "user")
        self.assertEqual(c[0].kind_hint, "preference")
        self.assertIsNone(c[0].scope_hint)
        g = collect_candidates([], "Always answer in English.")
        self.assertEqual(g[0].scope_hint, "global")

    def test_task_question_or_local_is_no_rule(self):
        self.assertEqual(collect_candidates([], "Should we always use tabs?"), [])
        self.assertEqual(collect_candidates([], "Never mind, in this file just fix it."), [])

    def test_dedupe_and_stable_id(self):
        evs = [ev("user.input_received", 5, text="Never use global state.")]
        a = collect_candidates(evs, "Never use global state.")
        b = collect_candidates(evs, "Never use global state.")
        self.assertEqual(len(a), 1)
        self.assertEqual(len(a[0].evidence), 2)
        self.assertEqual(a[0].id, b[0].id)
        self.assertTrue(a[0].id)

    def test_sources_valid(self):
        evs = [ev("run.cancelled", 1), ev("ballot.cast", 2, ballot={"choice": "a", "lesson": "x y"})]
        for c in collect_candidates(evs, "Always test."):
            self.assertIn(c.source, SOURCE_KINDS + ("user",))


if __name__ == "__main__":
    unittest.main()
