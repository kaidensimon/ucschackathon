import json
import unittest

from council.api.demo_script import BUILTIN_MODELS, WAIT_DELEGATE, demo_events
from council.core import event_types as ET
from council.core.schemas import ModelEntry, RunState
from council.core.schemas_v15 import LieReport, MemoryPlan

S = RunState
LEGAL = {
    (None, S.INTAKE),
    (S.INTAKE, S.PROFILING), (S.PROFILING, S.CONVENING), (S.CONVENING, S.DELIBERATING),
    (S.DELIBERATING, S.DECIDED), (S.DECIDED, S.DONE), (S.DECIDED, S.PLANNING),
    (S.DECIDED, S.EXAMINING), (S.EXAMINING, S.DONE), (S.EXAMINING, S.PLANNING),
    (S.PLANNING, S.AWAITING_DELEGATION), (S.AWAITING_DELEGATION, S.EXECUTING),
    (S.EXECUTING, S.REVIEWING), (S.REVIEWING, S.EXECUTING), (S.REVIEWING, S.DELIBERATING),
    (S.REVIEWING, S.INTEGRATING), (S.INTEGRATING, S.REFLECTING), (S.REFLECTING, S.DONE),
}
SEAT_INT_KEYS = {"seat_no", "reviewer_seat_no", "wildcard_seat_no"}
SEAT_LIST_KEYS = {"seats", "holders", "requested_by", "failed_seats"}
OPTION_KEYS = {"option_id", "leading_option_id"}


def walk(node, key=None):
    """Yield (key, value) for every dict entry at any depth."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield k, v
            yield from walk(v, k)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v, key)

# Every event type except run.failed and run.cancelled is in the demo script.
NOT_IN_DEMO_YET: set = {  # the open council protocol is not in the demo script yet
    ET.MSG_STARTED, ET.MSG_DELTA, ET.MSG_THINKING, ET.MSG_ENDED, ET.MSG_CARD, ET.MSG_LIE,
    ET.TABLE_TALLY,
}


class DemoScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = demo_events("Design a rate limiter for our public API.", "run-demo")
        cls.real = [e for e in cls.events if e[1] != WAIT_DELEGATE]
        cls.types = [e[1] for e in cls.events]

    def of(self, type):
        return [p for _, t, p in self.events if t == type]

    def test_shape_and_payloads_validate(self):
        for delay, type, payload in self.events:
            self.assertIsInstance(delay, float)
            self.assertGreaterEqual(delay, 0.0)
            self.assertIsInstance(payload, dict)
            if type == WAIT_DELEGATE:
                self.assertEqual(payload, {})
                continue
            ET.validate_payload(type, payload)
            json.dumps(payload)

    def test_coverage_of_event_types(self):
        want = set(ET.EVENT_TYPES) - {ET.RUN_FAILED, ET.RUN_CANCELLED} - NOT_IN_DEMO_YET
        self.assertEqual(want - set(self.types), set())
        self.assertNotIn(ET.RUN_FAILED, self.types)
        self.assertNotIn(ET.RUN_CANCELLED, self.types)
        self.assertEqual(set(self.types) - set(ET.EVENT_TYPES), {WAIT_DELEGATE})

    def test_first_and_last(self):
        self.assertEqual(self.types[0], ET.RUN_CREATED)
        self.assertEqual(self.types[-1], ET.RUN_COMPLETED)
        self.assertEqual(self.types.count(ET.RUN_COMPLETED), 1)
        done = self.events[-1][2]
        self.assertEqual(done["state"], "DONE")
        self.assertEqual(done["counters"]["tasks_total"], 8)
        self.assertGreater(done["counters"]["tokens_out"], 0)

    def test_state_transitions_are_legal(self):
        state, before_pause = None, None
        for _, type, p in self.events:
            if type != ET.RUN_STATE_CHANGED:
                continue
            frm = RunState(p["from_state"]) if p["from_state"] else None
            to = RunState(p["to_state"])
            self.assertEqual(frm, state)
            if to == S.AWAITING_USER:
                before_pause = frm
            elif frm == S.AWAITING_USER:
                self.assertEqual(to, before_pause)
            else:
                self.assertIn((frm, to), LEGAL)
            state = to
        self.assertEqual(state, S.DONE)
        visited = {p["to_state"] for p in self.of(ET.RUN_STATE_CHANGED)}
        self.assertEqual(visited, {s.value for s in RunState} - {"CANCELLED", "FAILED"})

    def test_wait_marker_sits_at_awaiting_delegation(self):
        self.assertEqual(self.types.count(WAIT_DELEGATE), 1)
        i = self.types.index(WAIT_DELEGATE)
        last_state = [p for _, t, p in self.events[:i] if t == ET.RUN_STATE_CHANGED][-1]
        self.assertEqual(last_state["to_state"], "AWAITING_DELEGATION")
        self.assertIn(ET.PLAN_READY, self.types[:i])
        nxt = [(t, p) for _, t, p in self.events[i + 1:] if t != ET.TELEMETRY_TICK][0]
        self.assertEqual(nxt[0], ET.RUN_STATE_CHANGED)
        self.assertEqual(nxt[1]["to_state"], "EXECUTING")
        for t in self.types[:i]:
            if t != ET.MEMORY_PLANNED:  # the memory plan is made at convening, before the work
                self.assertFalse(t.startswith(("task.", "delegation.", "review.", "memory.")), t)
        self.assertIn(ET.DELEGATION_STARTED, self.types[i:])

    def test_seats_and_models(self):
        seats = self.of(ET.SEAT_ASSIGNED)
        self.assertEqual(sorted(s["seat_no"] for s in seats), [0, 1, 2, 3, 4])
        self.assertEqual(len({s["lab"] for s in seats}), 5)
        self.assertEqual(sum(1 for s in seats if s["is_wildcard"]), 1)
        self.assertEqual(sum(1 for s in seats if s["is_chair"]), 1)
        self.assertTrue({"builder", "skeptic", "first_principles"} <= {s["lens"] for s in seats})
        known = {m.id for m in BUILTIN_MODELS}
        self.assertTrue({s["model_id"] for s in seats} <= known)
        sel = self.of(ET.ROUTER_LINEUP_SELECTED)[0]
        self.assertEqual(sel["labs"], 5)
        self.assertEqual([s["model_id"] for s in sel["lineup"]["seats"]], [s["model_id"] for s in seats])
        loaded = [p["model_id"] for p in self.of(ET.MODEL_LOADED)]
        for s in seats:
            self.assertIn(s["model_id"], loaded)
        # every seat model is loaded before the first seat turn
        first_r0 = self.types.index(ET.ROUND_STARTED)
        early = [p["model_id"] for _, t, p in self.events[:first_r0] if t == ET.MODEL_LOADED]
        self.assertEqual(set(early), {s["model_id"] for s in seats})
        for _, type, p in self.real:
            for k, v in walk(p):
                if k == "model_id" and v:
                    self.assertIn(v, known, type)

    def test_seat_numbers_referenced_exist(self):
        seat_nos = {s["seat_no"] for s in self.of(ET.SEAT_ASSIGNED)}
        for _, type, p in self.real:
            for k, v in walk(p):
                if k in SEAT_INT_KEYS and v is not None:
                    self.assertIn(v, seat_nos, type)
                elif k in SEAT_LIST_KEYS and isinstance(v, list):
                    for x in v:
                        if isinstance(x, int):
                            self.assertIn(x, seat_nos, type)
        ratify = self.of(ET.RATIFY_RESULT)[0]
        self.assertEqual({int(k) for k in ratify["votes"]}, seat_nos)

    def test_option_and_crux_ids_referenced_exist(self):
        option_ids = {o["id"] for p in self.of(ET.OPTIONS_CLUSTERED) for o in p["options"]}
        crux_ids = {c["id"] for p in self.of(ET.CRUXES_EXTRACTED) for c in p["cruxes"]}
        self.assertEqual(len(option_ids), 2)
        for _, type, p in self.real:
            if type in (ET.REVIEW_VERDICT, ET.USER_INPUT_RECEIVED, ET.USER_INPUT_REQUESTED):
                continue
            for k, v in walk(p):
                if k in OPTION_KEYS and v is not None:
                    self.assertIn(v, option_ids, type)
                elif k == "tally" and isinstance(v, dict):
                    self.assertTrue(set(v) <= option_ids, type)
                elif k == "between":
                    self.assertTrue(set(v) <= option_ids, type)
                elif k in ("crux_id", ) and v is not None:
                    self.assertIn(v, crux_ids, type)
                elif k == "focus_crux_ids":
                    self.assertTrue(set(v) <= crux_ids, type)
        for p in self.of(ET.BALLOT_CAST):
            self.assertIn(p["ballot"]["choice"], option_ids)
            self.assertEqual(set(p["ballot"]["ranking"]), option_ids)
        for p in self.of(ET.OPTIONS_CLUSTERED) + self.of(ET.ROUND_COMPLETED) + self.of(ET.DECISION_FINAL):
            for o in p["options"]:
                self.assertIn(o["id"], option_ids)

    def test_deliberation_story(self):
        clustered = self.of(ET.OPTIONS_CLUSTERED)[0]
        self.assertEqual(sorted(clustered["tally"].values()), [2, 3])
        self.assertEqual(sorted(len(o["holders"]) for o in clustered["options"]), [2, 3])
        self.assertEqual([p["round"] for p in self.of(ET.ROUND_STARTED)], [0, 1, 2, 3])
        self.assertEqual([p["round"] for p in self.of(ET.ROUND_COMPLETED)], [0, 1, 2, 3])
        # every seat streams text in round 0
        r0 = {p["call_id"]: p["seat_no"] for p in self.of(ET.TURN_STARTED) if p["purpose"] == "seat.r0"}
        self.assertEqual(sorted(r0.values()), [0, 1, 2, 3, 4])
        text = {c: "" for c in r0}
        for p in self.of(ET.TURN_DELTA):
            if p["call_id"] in text:
                text[p["call_id"]] += p["text"]
        done = {p["call_id"]: p for p in self.of(ET.TURN_COMPLETED)}
        for call_id in r0:
            self.assertGreater(len(text[call_id]), 100)
            self.assertEqual(text[call_id], done[call_id]["content"])
        all_ballots = self.of(ET.BALLOT_CAST)
        self.assertEqual([b["round"] for b in all_ballots], [2] * 5 + [3])  # round 3: the dissenter only
        ballots = all_ballots[:5]
        self.assertEqual(self.of(ET.ROUND_EXTENDED)[0]["round"], 3)
        choices = [b["ballot"]["choice"] for b in ballots]
        self.assertEqual(sorted(choices.count(c) for c in set(choices)), [1, 4])
        reached = self.of(ET.CONSENSUS_REACHED)[0]
        self.assertEqual(choices.count(reached["option_id"]), 4)
        self.assertEqual(len(self.of(ET.EVIDENCE_REQUESTED)), 1)
        self.assertEqual(self.of(ET.EVIDENCE_REQUESTED)[0]["check_id"], self.of(ET.EVIDENCE_RESULT)[0]["check_id"])
        final = self.of(ET.DECISION_FINAL)[0]["decision"]
        self.assertEqual(final["option_id"], reached["option_id"])
        self.assertEqual(len(final["minority_report"]), 1)
        self.assertNotEqual(final["minority_report"][0]["option_id"], final["option_id"])
        chair = "".join(p["text"] for p in self.of(ET.CHAIR_DELTA))
        self.assertEqual(chair, final["final_text"])
        order = [ET.BRIEF_READY, ET.RECALL_READY, ET.PROFILE_READY, ET.ROUTER_CANDIDATES_SCORED,
                 ET.ROUTER_LINEUP_SELECTED, ET.OPTIONS_CLUSTERED, ET.CRUXES_EXTRACTED, ET.EVIDENCE_RESULT,
                 ET.CONSENSUS_REACHED, ET.CHAIR_STARTED, ET.RATIFY_RESULT, ET.DECISION_FINAL, ET.PLAN_DRAFTED,
                 ET.PLAN_READY, ET.DELEGATION_STARTED, ET.REVIEW_STARTED, ET.REVIEW_VERDICT,
                 ET.MEMORY_CANDIDATE, ET.RUN_COMPLETED]
        at = [self.types.index(t) for t in order]
        self.assertEqual(at, sorted(at))
        asked = self.of(ET.USER_INPUT_REQUESTED)[0]
        self.assertEqual(self.of(ET.USER_INPUT_RECEIVED)[0]["request_id"], asked["request_id"])

    def test_plan_and_task_story(self):
        plan = self.of(ET.PLAN_READY)[0]["plan"]
        ids = [t["id"] for t in plan["tasks"]]
        self.assertEqual(len(ids), 8)
        self.assertEqual(len(set(ids)), 8)
        seen = set()
        for t in plan["tasks"]:  # listed in dependency order, so no cycles
            self.assertTrue(set(t["deps"]) <= seen, t["id"])
            self.assertTrue(t["acceptance"], t["id"])
            seen.add(t["id"])
        self.assertTrue(any(t["deps"] for t in plan["tasks"]))
        self.assertEqual(self.of(ET.DELEGATION_STARTED)[0]["task_ids"], ids)
        for _, type, p in self.real:
            if type.startswith("task."):
                self.assertIn(p["task_id"], ids, type)
            if type in (ET.CHECK_STARTED, ET.CHECK_RESULT) and p["task_id"] is not None:
                self.assertIn(p["task_id"], ids)
        # a task starts only after its dependencies passed
        passed_at = {}
        for i, (_, type, p) in enumerate(self.events):
            if type == ET.TASK_PASSED:
                passed_at[p["task_id"]] = i
        deps = {t["id"]: t["deps"] for t in plan["tasks"]}
        for i, (_, type, p) in enumerate(self.events):
            if type == ET.TASK_STARTED:
                for d in deps[p["task_id"]]:
                    self.assertLess(passed_at[d], i, p["task_id"])
        passed = set(passed_at)
        attempts = self.of(ET.TASK_ATTEMPT_COMPLETED)
        retry_ok = [a["task_id"] for a in attempts if a["attempt"] == 1 and not a["ok"] and a["task_id"] in passed]
        self.assertTrue(retry_ok)
        escalated = self.of(ET.TASK_ESCALATED)
        self.assertEqual(len(escalated), 1)
        self.assertIn(escalated[0]["task_id"], passed)
        failed = {p["task_id"] for p in self.of(ET.TASK_FAILED)}
        skipped = self.of(ET.TASK_SKIPPED)
        self.assertTrue(set(skipped[0]["blocked_by"]) <= failed)
        self.assertEqual(passed | failed | {s["task_id"] for s in skipped}, set(ids))
        deltas = {p["task_id"] for p in self.of(ET.TASK_DELTA)}
        self.assertTrue(passed <= deltas)
        counters = self.events[-1][2]["counters"]
        self.assertEqual(counters["tasks_passed"], len(passed))
        self.assertEqual(counters["tasks_failed"], len(failed))
        stages = [p["stage"] for p in self.of(ET.INTEGRATION_RESULT)]
        self.assertEqual(stages, ["checks", "copy"])

    def test_new_event_story(self):
        first = lambda t: self.types.index(t)  # noqa: E731
        # effort after profile, memory plan at convening, lie report after round 0
        self.assertLess(first(ET.PROFILE_READY), first(ET.EFFORT_PLANNED))
        self.assertLess(first(ET.EFFORT_PLANNED), first(ET.MEMORY_PLANNED))
        convening = next(i for i, (_, t, p) in enumerate(self.events)
                         if t == ET.RUN_STATE_CHANGED and p["to_state"] == "CONVENING")
        self.assertLess(convening, first(ET.MEMORY_PLANNED))
        self.assertLess(first(ET.MEMORY_PLANNED), first(ET.ROUTER_LINEUP_SELECTED))
        self.assertGreater(first(ET.LIE_REPORT), first(ET.PROBE_SCORES))
        self.assertLess(first(ET.LIE_REPORT), first(ET.CRUXES_EXTRACTED))
        effort = self.of(ET.EFFORT_PLANNED)[0]
        self.assertGreaterEqual(effort["max_extra_rounds"], self.of(ET.ROUND_EXTENDED)[0]["extra_used"])
        plan = MemoryPlan.model_validate(self.of(ET.MEMORY_PLANNED)[0]["plan"])
        self.assertTrue(plan.fits)
        self.assertLessEqual(plan.total_gib, plan.budget_gib)
        report = LieReport.model_validate(self.of(ET.LIE_REPORT)[0]["report"])
        lie = self.of(ET.LIE_REPORT)[0]
        self.assertEqual(lie["flagged"], sum(1 for f in report.flags if f.level == "flag"))
        self.assertEqual(lie["watched"], sum(1 for f in report.flags if f.level == "watch"))
        self.assertEqual(sorted(r.seat_no for r in report.seats), [0, 1, 2, 3, 4])
        # round 3 is announced just before it starts
        r3 = [i for i, (_, t, p) in enumerate(self.events) if t == ET.ROUND_STARTED and p["round"] == 3][0]
        self.assertLess(first(ET.ROUND_EXTENDED), r3)
        # the steered seat gets its vector right after loading; the outlier's vector is trained last
        applied = self.of(ET.STEER_APPLIED)[0]
        seat_model = {s["seat_no"]: s["model_id"] for s in self.of(ET.SEAT_ASSIGNED)}
        self.assertIn(applied["model_id"], seat_model.values())
        self.assertLess(first(ET.STEER_APPLIED), first(ET.ROUND_STARTED))
        trained = self.of(ET.STEER_TRAINED)[0]
        self.assertEqual(trained["model_id"], seat_model[4])
        self.assertEqual(trained["project"], applied["project"])
        self.assertGreater(first(ET.STEER_TRAINED), first(ET.REVIEW_VERDICT))
        # review debate and final say sit between the ballots and the verdict
        self.assertLess(first(ET.REVIEW_BALLOT), first(ET.REVIEW_DEBATE))
        self.assertLess(first(ET.REVIEW_DEBATE), first(ET.REVIEW_FINAL_SAY))
        self.assertLess(first(ET.REVIEW_FINAL_SAY), first(ET.REVIEW_VERDICT))
        say = self.of(ET.REVIEW_FINAL_SAY)[0]
        self.assertEqual(say["model_id"], seat_model[say["seat_no"]])
        debate = self.of(ET.REVIEW_DEBATE)[0]
        self.assertEqual(debate["tally_after"], self.of(ET.REVIEW_VERDICT)[0]["tally"])

    def test_review_and_memory_story(self):
        ballots = self.of(ET.REVIEW_BALLOT)
        self.assertEqual(len(ballots), 5)
        verdict = self.of(ET.REVIEW_VERDICT)[0]
        self.assertEqual(verdict["verdict"], "accept")
        accept = sum(1 for b in ballots if b["ballot"]["verdict"] == "accept")
        self.assertGreaterEqual(accept / 5, 0.8)
        self.assertEqual(verdict["tally"]["accept"], accept)
        cands = {p["candidate"]["id"] for p in self.of(ET.MEMORY_CANDIDATE)}
        self.assertGreaterEqual(len(cands), 3)
        for p in self.of(ET.MEMORY_VERDICT):
            self.assertIn(p["candidate_id"], cands)
        commits = self.of(ET.MEMORY_COMMITTED)
        self.assertEqual(len(commits), 2)
        for p in commits + self.of(ET.MEMORY_CONTESTED):
            self.assertIn(p["candidate_id"], cands)
        self.assertEqual(len(self.of(ET.MEMORY_CONTESTED)), 1)
        recalled = {e["id"] for e in self.of(ET.RECALL_READY)[0]["entries"]}
        self.assertIn(self.of(ET.MEMORY_CONTESTED)[0]["entry_id"], recalled)
        self.assertIn(self.of(ET.MEMORY_RETRACTED)[0]["entry_id"], recalled)

    def test_duration_and_telemetry(self):
        total = sum(d for d, _, _ in self.events)
        self.assertGreaterEqual(total, 60.0)
        self.assertLessEqual(total, 90.0)
        gap, ticks = 0.0, 0
        for delay, type, _ in self.events:
            gap += delay
            if type in (ET.TELEMETRY_TICK, WAIT_DELEGATE):
                self.assertLessEqual(gap, 1.5)
                gap = 0.0
                ticks += type == ET.TELEMETRY_TICK
        self.assertGreaterEqual(ticks, 50)
        out = [p["tokens_out"] for p in self.of(ET.TELEMETRY_TICK)]
        self.assertEqual(out, sorted(out))
        self.assertTrue(any(p["in_flight"] for p in self.of(ET.TELEMETRY_TICK)))
        self.assertTrue(all(p["mem_available_gib"] > 0 for p in self.of(ET.TELEMETRY_TICK)))

    def test_deterministic(self):
        again = demo_events("Design a rate limiter for our public API.", "run-demo")
        self.assertEqual(again, self.events)

    def test_uses_given_models(self):
        labs = ["LabA", "LabB", "LabC", "LabD", "LabE", "LabF", "LabA"]
        models = [ModelEntry(id=f"m{i}", display=f"Model {i}", lab=lab, params_b=8.0 + i,
                             roles=["worker"] if i == 5 else ["seat"]) for i, lab in enumerate(labs)]
        events = demo_events("Rate limit the API.", "run-x", models=models, seed=7)
        given = {m.id for m in models}
        seats = [p for _, t, p in events if t == ET.SEAT_ASSIGNED]
        self.assertEqual(len(seats), 5)
        self.assertEqual(len({s["lab"] for s in seats}), 5)
        self.assertTrue({s["model_id"] for s in seats} <= given)
        for _, type, p in events:
            if type == WAIT_DELEGATE:
                continue
            ET.validate_payload(type, p)
            for k, v in walk(p):
                if k == "model_id" and v:
                    self.assertIn(v, given, type)
        self.assertEqual(set(ET.EVENT_TYPES) - {t for _, t, _ in events} - NOT_IN_DEMO_YET,
                         {ET.RUN_FAILED, ET.RUN_CANCELLED})

    def test_few_models_fall_back_to_builtins(self):
        events = demo_events("Rate limit the API.", "run-y", models=[ModelEntry(id="solo", lab="LabA")], seed=3)
        seats = [p for _, t, p in events if t == ET.SEAT_ASSIGNED]
        self.assertEqual(len({s["lab"] for s in seats}), 5)
        self.assertEqual(events[-1][1], ET.RUN_COMPLETED)


if __name__ == "__main__":
    unittest.main()
