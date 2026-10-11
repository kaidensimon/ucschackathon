import asyncio
import unittest

from council.chronicle import recall
from council.chronicle.reflect import Reflector, pick_judges, source_kind, verdict_schema
from council.core.schemas import (
    CallResult,
    ChronicleEntry,
    EvidenceRef,
    LineupRecord,
    MeasuredStats,
    MemoryCandidate,
    ModelEntry,
    SeatAssignment,
)

JUDGES = ["m-a", "m-b", "m-c"]
CFG = {"recall_k": 8, "review_after_runs": 10, "decay": 0.9, "retract_below": 0.3}


def run(coro):
    return asyncio.run(coro)


class FakeStore:
    def __init__(self, entries=()):
        self.rows = {e.id: e for e in entries}

    def chronicle_list(self):
        return list(self.rows.values())

    def chronicle_put(self, entry):
        self.rows[entry.id] = entry


class FakeGateway:
    """Answers each judge from `by_model` (dict, or callable taking the spec)."""

    def __init__(self, by_model):
        self.by_model = by_model
        self.specs = []

    async def call(self, spec):
        self.specs.append(spec)
        answer = self.by_model[spec.model_id]
        if callable(answer):
            answer = answer(spec)
        if answer is None:
            return CallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id, error="invalid_output")
        return CallResult(call_id=spec.call_id, ok=True, model_id=spec.model_id, parsed=answer)


async def embed(texts):
    return [recall.keyword_embedding(t) for t in texts]


def V(action, scope="global", kind="preference", rewrite="Use tabs in this repo.", reason="user said so"):
    return {
        "durable": action != "reject", "kind": kind, "scope": scope,
        "statement_rewrite": rewrite, "action": action, "reason": reason,
    }


def panel(*actions, **kw):
    return {m: (V(a, **kw) if a is not None else None) for m, a in zip(JUDGES, actions)}


def C(text="Always use tabs", source="user_statement", run_id="r1", **kw):
    evidence = kw.pop("evidence", None)
    if evidence is None:
        evidence = [EvidenceRef(run_id=run_id, event_seq=4, quote=text)]
    return MemoryCandidate(
        text=text, id=kw.pop("id", "c1"), run_id=run_id, source=source, evidence=evidence, **kw,
    )


def Ent(id, status="active", scope="project:p1", conf=0.8, statement="Use spaces in this repo.", run_id="r0", **kw):
    return ChronicleEntry(
        id=id, status=status, scope=scope, confidence=conf, statement=statement,
        evidence=[EvidenceRef(run_id=run_id, quote="old")], support_count=1,
        embedding=recall.keyword_embedding(statement), created_at=1.0, last_confirmed_at=1.0, **kw,
    )


def make(by_model, entries=(), cfg=CFG, clock=100.0):
    events = []
    store = FakeStore(entries)
    gw = FakeGateway(by_model)
    r = Reflector(gw, store, lambda t, p: events.append((t, p)), embed, cfg, lambda: clock)
    return r, store, gw, events


def types(events):
    return [t for t, _ in events]


def U(text="From now on, always use tabs for indentation in this project.", run_id="r1", **kw):
    return C(text=text, source="user", run_id=run_id, kind_hint="preference", **kw)


class ReflectExplicitUserRuleTests(unittest.TestCase):
    def test_user_rule_committed_active_without_panel(self):
        r, store, gw, events = make({})  # no judge answers at all
        out = run(r.reflect("r1", [U()], JUDGES, "p1", ["coding"]))
        self.assertEqual(len(out), 1)
        e = out[0]
        self.assertEqual((e.status, e.confidence, e.kind), ("active", 0.9, "preference"))
        self.assertEqual(e.scope, "project:p1")
        self.assertEqual(e.statement, "From now on, always use tabs for indentation in this project.")
        self.assertEqual(gw.specs, [])
        self.assertEqual(types(events), ["memory.candidate", "memory.committed"])
        self.assertEqual(list(store.rows.values()), [e])
        self.assertEqual(e.embedding, recall.keyword_embedding(e.statement))

    def test_user_rule_global_hint(self):
        r, store, _, _ = make({})
        out = run(r.reflect("r1", [U("Always answer in English.", scope_hint="global")], JUDGES, "p1", []))
        self.assertEqual(out[0].scope, "global")

    def test_task_text_to_one_committed_entry(self):
        from council.chronicle.collect import collect_candidates

        task = "Add a login form. From now on, always use tabs for indentation in this project."
        cands = collect_candidates([], task)
        r, store, gw, events = make({})
        out = run(r.reflect("r1", cands, JUDGES, "p1", ["coding"]))
        self.assertEqual(len(out), 1)
        self.assertEqual(len(store.rows), 1)
        self.assertEqual(types(events).count("memory.committed"), 1)
        only = next(iter(store.rows.values()))
        self.assertEqual(only.status, "active")
        self.assertIn("tabs", only.statement)

    def test_user_rule_same_run_duplicate_skipped(self):
        r, store, _, _ = make({})
        run(r.reflect("r1", [U()], JUDGES, "p1", []))
        again = run(r.reflect("r1", [U(id="c2")], JUDGES, "p1", []))
        self.assertEqual(again, [])
        self.assertEqual(len(store.rows), 1)

    def test_user_rule_from_new_run_merges_and_promotes(self):
        old = Ent("e1", status="provisional", conf=0.5, statement=U().text, run_id="r0")
        r, store, _, events = make({}, entries=[old])
        out = run(r.reflect("r2", [U(run_id="r2")], JUDGES, "p1", []))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].id, "e1")
        self.assertEqual(out[0].status, "active")
        self.assertEqual(out[0].support_count, 2)
        self.assertEqual(len(store.rows), 1)

    def test_empty_user_rule_ignored(self):
        r, store, _, _ = make({})
        self.assertEqual(run(r.reflect("r1", [U(text="   ")], JUDGES, "p1", [])), [])
        self.assertEqual(store.rows, {})


class ReflectNewEntryTests(unittest.TestCase):
    def test_reject_writes_nothing(self):
        r, store, gw, events = make(panel("reject", "reject", "adopt"))
        out = run(r.reflect("r1", [C()], JUDGES, "p1", ["coding"]))
        self.assertEqual(out, [])
        self.assertEqual(store.rows, {})
        self.assertEqual(types(events), ["memory.candidate"] + ["memory.verdict"] * 3)

    def test_no_majority_rejects(self):
        r, store, _, events = make(panel("adopt", "reject", "reject"))
        self.assertEqual(run(r.reflect("r1", [C()], JUDGES, "p1", [])), [])
        self.assertNotIn("memory.committed", types(events))

    def test_failed_judges_do_not_make_a_majority(self):
        r, store, _, events = make(panel("adopt", None, None))
        self.assertEqual(run(r.reflect("r1", [C()], JUDGES, "p1", [])), [])
        self.assertEqual(store.rows, {})

    def test_split_accept_majority_is_provisional(self):
        # adopt + provisional + reject: no single action has 2 votes, but 2 of 3 accept.
        r, store, _, events = make(panel("adopt", "provisional", "reject"))
        out = run(r.reflect("r1", [C()], JUDGES, "p1", []))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].status, "provisional")
        self.assertLessEqual(out[0].confidence, 0.5)
        self.assertIn("memory.committed", types(events))
        self.assertEqual(len(store.rows), 1)

    def test_split_majority_never_active_even_for_explicit_rule(self):
        r, store, _, _ = make(panel("provisional", "adopt", "reject"))
        out = run(r.reflect("r1", [C(source="explicit_rule")], JUDGES, "p1", []))
        self.assertEqual(out[0].status, "provisional")

    def test_explicit_rule_adopt_active_global(self):
        r, store, gw, events = make(panel("adopt", "adopt", "reject"))
        out = run(r.reflect("r1", [C()], JUDGES, "p1", ["coding"]))
        self.assertEqual(len(out), 1)
        e = out[0]
        self.assertEqual((e.status, e.confidence, e.scope), ("active", 0.9, "global"))
        self.assertEqual(e.statement, "Use tabs in this repo.")
        self.assertEqual(e.kind, "preference")
        self.assertEqual(e.evidence[0].quote, "Always use tabs")
        self.assertEqual(e.evidence[0].event_seq, 4)
        self.assertEqual(e.embedding, recall.keyword_embedding(e.statement))
        self.assertEqual((e.created_at, e.last_confirmed_at, e.review_after), (100.0, 100.0, 10))
        self.assertEqual(len(e.votes), 3)
        self.assertEqual(store.rows[e.id], e)
        self.assertEqual(types(events)[-1], "memory.committed")
        payload = events[-1][1]
        self.assertEqual(payload["action"], "adopt")
        self.assertEqual(payload["candidate_id"], "c1")
        self.assertEqual(payload["entry"]["id"], e.id)

    def test_explicit_rule_stays_project_when_panel_does_not_say_global(self):
        r, _, _, _ = make(panel("adopt", "adopt", "adopt", scope="project:p1"))
        out = run(r.reflect("r1", [C()], JUDGES, "p1", []))
        self.assertEqual(out[0].scope, "project:p1")

    def test_single_choice_is_provisional_project_even_if_panel_says_global(self):
        r, _, _, events = make(panel("adopt", "adopt", "adopt"))
        out = run(r.reflect("r1", [C("picked tabs", source="user_choice")], JUDGES, "p1", []))
        self.assertEqual((out[0].status, out[0].confidence, out[0].scope), ("provisional", 0.5, "project:p1"))
        self.assertEqual(events[-1][1]["action"], "provisional")

    def test_inferred_low_confidence(self):
        r, _, _, _ = make(panel("adopt", "adopt", "adopt"))
        out = run(r.reflect("r1", [C("seems to like tabs", source="lesson")], JUDGES, "p1", []))
        self.assertEqual((out[0].status, out[0].confidence), ("provisional", 0.3))

    def test_task_only_rejected(self):
        r, store, _, _ = make(panel("adopt", "adopt", "adopt"))
        self.assertEqual(run(r.reflect("r1", [C(source="task_only")], JUDGES, "p1", [])), [])
        self.assertEqual(store.rows, {})

    def test_failed_and_broken_judges_are_skipped(self):
        answers = {"m-a": V("adopt"), "m-b": None, "m-c": {"nonsense": 1}}
        r, _, _, events = make(answers)
        self.assertEqual(run(r.reflect("r1", [C()], JUDGES, "p1", [])), [])
        self.assertEqual(types(events).count("memory.verdict"), 1)

    def test_evidence_falls_back_to_candidate_text(self):
        r, _, _, _ = make(panel("adopt", "adopt", "adopt"))
        out = run(r.reflect("r9", [C(evidence=[], run_id=None)], JUDGES, "p1", []))
        self.assertEqual((out[0].evidence[0].run_id, out[0].evidence[0].quote), ("r9", "Always use tabs"))

    def test_candidate_without_id_gets_one(self):
        r, _, _, events = make(panel("reject", "reject", "reject"))
        run(r.reflect("r1", [C(id="")], JUDGES, "p1", []))
        cid = events[0][1]["candidate"]["id"]
        self.assertTrue(cid)
        self.assertEqual(events[1][1]["candidate_id"], cid)


class ReflectCallTests(unittest.TestCase):
    def test_three_blind_batch_calls(self):
        old = Ent("e1")
        r, _, gw, events = make(panel("reject", "reject", "reject"), [old])
        run(r.reflect("r1", [C()], JUDGES, "p1", ["coding"]))
        self.assertEqual([s.model_id for s in gw.specs], JUDGES)
        for s in gw.specs:
            self.assertEqual((s.purpose, s.priority, s.run_id), ("memory.judge", "batch", "r1"))
            self.assertIn("Always use tabs", s.messages[-1]["content"])
            self.assertIn("e1", s.messages[-1]["content"])
            self.assertIn("merge:e1", s.json_schema["properties"]["action"]["enum"])
        self.assertEqual(len({s.call_id for s in gw.specs}), 3)
        self.assertEqual(gw.specs[0].messages, gw.specs[1].messages)  # blind: same prompt, no peer verdicts
        v = [p for t, p in events if t == "memory.verdict"]
        self.assertEqual([(p["seat_no"], p["model_id"]) for p in v], list(enumerate(JUDGES)))
        self.assertEqual(events[0][1]["total"], 1)

    def test_recall_skips_other_project_and_dead_entries(self):
        entries = [Ent("mine"), Ent("other", scope="project:p2"), Ent("gone", status="retracted")]
        r, _, gw, _ = make(panel("reject", "reject", "reject"), entries)
        run(r.reflect("r1", [C()], JUDGES, "p1", []))
        enum = gw.specs[0].json_schema["properties"]["action"]["enum"]
        self.assertIn("merge:mine", enum)
        self.assertNotIn("merge:other", enum)
        self.assertNotIn("merge:gone", enum)

    def test_later_candidate_sees_earlier_commit(self):
        seen = []

        def answer(spec):
            seen.append(len(spec.json_schema["properties"]["action"]["enum"]))
            text = spec.messages[-1]["content"]
            return V("adopt", rewrite="Avoid semicolons." if "semicolons" in text else "Use tabs in this repo.")

        r, store, _, _ = make({m: answer for m in JUDGES})
        out = run(r.reflect("r1", [C(id="c1"), C("Never use semicolons", id="c2")], JUDGES, "p1", []))
        self.assertEqual(len(out), 2)
        self.assertEqual(seen[0], 3)
        self.assertEqual(seen[-1], 6)

    def test_embed_failure_falls_back(self):
        async def bad(texts):
            raise RuntimeError("no embedder")

        store, events = FakeStore(), []
        r = Reflector(FakeGateway(panel("adopt", "adopt", "adopt")), store,
                      lambda t, p: events.append((t, p)), bad, CFG, lambda: 1.0)
        out = run(r.reflect("r1", [C()], JUDGES, "p1", []))
        self.assertEqual(out[0].embedding, recall.keyword_embedding(out[0].statement))

    def test_cfg_object_and_none(self):
        class Cfg:
            recall_k, review_after_runs, decay, retract_below = 2, 7, 0.9, 0.3

        r, _, _, _ = make(panel("adopt", "adopt", "adopt"), cfg=Cfg())
        self.assertEqual(run(r.reflect("r1", [C()], JUDGES, "p1", []))[0].review_after, 7)
        r, _, _, _ = make(panel("adopt", "adopt", "adopt"), cfg=None)
        self.assertEqual(run(r.reflect("r1", [C()], JUDGES, "p1", []))[0].review_after, 10)


class ReflectTargetedTests(unittest.TestCase):
    def test_merge_bumps_and_promotes_repeat_pattern(self):
        old = Ent("e1", status="provisional", conf=0.5)
        r, store, _, events = make(panel("merge:e1", "merge:e1", "reject"), [old])
        out = run(r.reflect("r1", [C("picked tabs again", source="user_choice")], JUDGES, "p1", []))
        self.assertEqual(len(store.rows), 1)
        m = store.rows["e1"]
        self.assertEqual(out, [m])
        self.assertEqual((m.support_count, m.last_confirmed_at, m.status, m.confidence), (2, 100.0, "active", 0.8))
        self.assertEqual(len(m.evidence), 2)
        self.assertEqual(m.created_at, 1.0)
        p = events[-1][1]
        self.assertEqual((events[-1][0], p["action"], p["merged_into_id"]), ("memory.committed", "merge:e1", "e1"))

    def test_merge_same_run_is_not_a_repeat(self):
        old = Ent("e1", status="provisional", conf=0.5, run_id="r1")
        r, store, _, _ = make(panel("merge:e1", "merge:e1", "merge:e1"), [old])
        run(r.reflect("r1", [C("picked tabs", source="user_choice")], JUDGES, "p1", []))
        m = store.rows["e1"]
        self.assertEqual((m.status, m.support_count), ("provisional", 2))
        self.assertAlmostEqual(m.confidence, 0.55)

    def test_merge_confidence_capped_at_one(self):
        r, store, _, _ = make(panel("merge:e1", "merge:e1", "merge:e1"), [Ent("e1", conf=0.99)])
        run(r.reflect("r1", [C()], JUDGES, "p1", []))
        self.assertEqual(store.rows["e1"].confidence, 1.0)

    def test_supersede(self):
        r, store, _, events = make(panel("supersede:e1", "supersede:e1", "adopt"), [Ent("e1")])
        out = run(r.reflect("r1", [C()], JUDGES, "p1", []))
        self.assertEqual(store.rows["e1"].status, "superseded")
        new = out[0]
        self.assertEqual((new.supersedes, new.status, new.confidence), ("e1", "active", 0.9))
        self.assertIn(new.id, store.rows)
        self.assertEqual(events[-1][1]["superseded_id"], "e1")
        self.assertEqual(types(events).count("memory.committed"), 1)

    def test_contest_marks_both(self):
        r, store, _, events = make(panel("contest:e1", "contest:e1", "reject"), [Ent("e1")])
        out = run(r.reflect("r1", [C()], JUDGES, "p1", []))
        old = store.rows["e1"]
        self.assertEqual((old.status, old.contradict_count), ("contested", 1))
        self.assertEqual((out[0].status, out[0].confidence), ("contested", 0.5))
        self.assertEqual(store.rows[out[0].id].status, "contested")
        contested = [p for t, p in events if t == "memory.contested"]
        self.assertEqual(len(contested), 1)
        self.assertEqual((contested[0]["entry_id"], contested[0]["candidate_id"]), ("e1", "c1"))
        self.assertTrue(contested[0]["reason"])
        self.assertEqual(types(events)[-1], "memory.committed")

    def test_contradiction_source_forces_contest_of_active_entry(self):
        r, store, _, events = make(panel("adopt", "adopt", "adopt"), [Ent("e1")])
        out = run(r.reflect("r1", [C(source="contradiction")], JUDGES, "p1", []))
        self.assertEqual(store.rows["e1"].status, "contested")
        self.assertEqual(out[0].status, "contested")
        self.assertIn("memory.contested", types(events))

    def test_unknown_target(self):
        r, store, _, _ = make(panel("contest:nope", "contest:nope", "reject"))
        self.assertEqual(run(r.reflect("r1", [C()], JUDGES, "p1", [])), [])
        r, store, _, _ = make(panel("merge:nope", "merge:nope", "reject"))
        out = run(r.reflect("r1", [C()], JUDGES, "p1", []))
        self.assertEqual(len(out), 1)
        self.assertIsNone(out[0].supersedes)
        self.assertEqual(list(store.rows), [out[0].id])

    def test_override_counts_against_related_entries(self):
        led = Ent("e1", scope="project:p2")  # out of recall scope, named by the Clerk
        r, store, gw, _ = make(panel("provisional", "provisional", "adopt"), [led])
        cand = C("user overrode the plan", source="override", related_entry_ids=["e1"])
        out = run(r.reflect("r1", [cand], JUDGES, "p1", []))
        self.assertEqual(store.rows["e1"].contradict_count, 1)
        self.assertEqual((out[0].status, out[0].confidence), ("provisional", 0.5))
        self.assertIn("supersede:e1", gw.specs[0].json_schema["properties"]["action"]["enum"])


class AgePassTests(unittest.TestCase):
    def test_decay_retract_and_skip(self):
        entries = [
            Ent("fresh", conf=0.8, review_after=10),
            Ent("stale", conf=0.8, review_after=10),
            Ent("weak", conf=0.31, review_after=10, scope="global"),
            Ent("other", conf=0.8, review_after=10, scope="project:p2"),
            Ent("dead", conf=0.8, review_after=10, status="superseded"),
            Ent("unlisted", conf=0.8, review_after=10),
        ]
        r, store, _, events = make({}, entries)
        since = {"fresh": 3, "stale": 10, "weak": 12, "other": 50, "dead": 50}
        changed = run(r.age_pass("p1", since))
        self.assertEqual([e.id for e in changed], ["stale", "weak"])
        self.assertAlmostEqual(store.rows["stale"].confidence, 0.72)
        self.assertEqual(store.rows["stale"].status, "active")
        self.assertEqual(store.rows["weak"].status, "retracted")
        for same in ("fresh", "other", "dead", "unlisted"):
            self.assertEqual(store.rows[same].confidence, 0.8)
        self.assertEqual(types(events), ["memory.retracted"])
        p = events[0][1]
        self.assertEqual((p["entry_id"], p["by"], p["entry"]["status"]), ("weak", "aging", "retracted"))

    def test_cfg_values_used(self):
        r, store, _, _ = make({}, [Ent("a", conf=0.8, review_after=1)], cfg={"decay": 0.5, "retract_below": 0.5})
        run(r.age_pass("p1", {"a": 1}))
        self.assertEqual((store.rows["a"].confidence, store.rows["a"].status), (0.4, "retracted"))


def M(id, lab, ram=None, params=None, **kw):
    return ModelEntry(id=id, lab=lab, params_b=params, measured=MeasuredStats(ram_gb_batch=ram), **kw)


class PickJudgesTests(unittest.TestCase):
    REG = [
        M("big-a", "A", ram=20), M("small-a", "A", ram=3), M("b", "B", ram=8),
        M("c", "C", ram=5), M("d", "D", ram=1),
    ]

    def test_three_labs_cheapest_first(self):
        self.assertEqual(pick_judges(self.REG, None), ["d", "small-a", "c"])
        self.assertEqual(pick_judges(self.REG, [], n=4), ["d", "small-a", "c", "b"])

    def test_lineup_models_first(self):
        lineup = LineupRecord(seats=[SeatAssignment(seat_no=0, model_id="big-a"),
                                     SeatAssignment(seat_no=1, model_id="b")])
        self.assertEqual(pick_judges(self.REG, lineup), ["b", "big-a", "d"])
        self.assertEqual(pick_judges(self.REG, ["b", "big-a"]), ["b", "big-a", "d"])

    def test_skips_inactive_and_embed_only(self):
        reg = self.REG + [M("q", "Q", ram=0.1, status="quarantined"), M("emb", "E", ram=0.1, roles=["embed"])]
        self.assertEqual(pick_judges(reg, None), ["d", "small-a", "c"])

    def test_labs_repeat_when_too_few(self):
        reg = [M("a1", "A", ram=2), M("a2", "A", ram=1), M("b1", "B", ram=9)]
        self.assertEqual(pick_judges(reg, None), ["a2", "b1", "a1"])
        self.assertEqual(pick_judges(reg[:2], None), ["a2", "a1"])
        self.assertEqual(pick_judges([], None), [])

    def test_dict_registry_and_params_fallback(self):
        reg = {m.id: m for m in [M("x", "X", params=7), M("y", "Y", params=2), M("z", "Z")]}
        self.assertEqual(pick_judges(reg, None), ["y", "x", "z"])


class HelperTests(unittest.TestCase):
    def test_source_kind(self):
        self.assertEqual(source_kind(C("From now on use tabs"), "adopt", []), "explicit_rule")
        self.assertEqual(source_kind(C("use tabs here"), "adopt", []), "inferred")
        self.assertEqual(source_kind(C(source="plan_edit"), "adopt", []), "single_choice")
        self.assertEqual(source_kind(C(source="override"), "merge:e1", [Ent("e1")]), "override")
        self.assertEqual(source_kind(C(source="repeat_pattern"), "adopt", []), "repeat_pattern")
        self.assertEqual(source_kind(C(source="who knows"), "adopt", []), "inferred")

    def test_verdict_schema(self):
        s = verdict_schema(["e1"], "p1", ["coding"])
        self.assertEqual(
            s["properties"]["action"]["enum"],
            ["reject", "provisional", "adopt", "merge:e1", "supersede:e1", "contest:e1"],
        )
        self.assertEqual(s["properties"]["scope"]["enum"], ["project:p1", "global", "category:coding"])
        self.assertIn("durable", s["required"])


class DedupeTests(unittest.TestCase):
    LESSON = "Run the linter before committing generated files."

    def _lesson_run(self, r, run_id, **kw):
        return run(r.reflect(run_id, [C("lint first", source="lesson", run_id=run_id, id=f"c-{run_id}", **kw)],
                             JUDGES, "p1", []))

    def test_three_runs_same_lesson_leave_one_active_entry(self):
        r, store, _, _ = make(panel("adopt", "adopt", "adopt", scope="project:p1", kind="lesson", rewrite=self.LESSON))
        for rid in ("r1", "r2", "r3"):
            self._lesson_run(r, rid)
        rows = store.chronicle_list()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].support_count, rows[0].status), (3, "active"))
        self.assertEqual({ev.run_id for ev in rows[0].evidence}, {"r1", "r2", "r3"})

    def test_second_independent_run_promotes_provisional(self):
        r, store, _, events = make(panel("adopt", "adopt", "adopt", scope="project:p1", kind="lesson", rewrite=self.LESSON))
        self._lesson_run(r, "r1")
        self.assertEqual(store.chronicle_list()[0].status, "provisional")
        self._lesson_run(r, "r2")
        e = store.chronicle_list()[0]
        self.assertEqual((e.support_count, e.status), (2, "active"))
        self.assertEqual(events[-1][1]["merged_into_id"], e.id)

    def test_near_duplicate_wording_merges(self):
        r, store, _, _ = make(lambda: None) if False else make(
            {m: (lambda spec, n=[0]: None) for m in JUDGES})
        store.chronicle_put(Ent("e1", status="provisional", statement=self.LESSON, scope="project:p1"))
        r.gateway.by_model = panel("adopt", "adopt", "adopt", scope="project:p1", kind="lesson",
                                   rewrite="Run the linter before committing generated files!")
        self._lesson_run(r, "r2")
        self.assertEqual(len(store.chronicle_list()), 1)
        self.assertEqual(store.chronicle_list()[0].support_count, 2)

    def test_same_run_duplicates_collapse_without_bump(self):
        r, store, _, _ = make(panel("adopt", "adopt", "adopt", scope="project:p1", kind="lesson", rewrite=self.LESSON))
        out = run(r.reflect("r1", [
            C("lint first", source="lesson", run_id="r1", id="a"),
            C("lint first please", source="lesson", run_id="r1", id="b"),
        ], JUDGES, "p1", []))
        self.assertEqual(len(out), 1)
        rows = store.chronicle_list()
        self.assertEqual((len(rows), rows[0].support_count, rows[0].status), (1, 1, "provisional"))

    def test_distinct_statement_still_creates_entry(self):
        r, store, _, _ = make(panel("adopt", "adopt", "adopt", scope="project:p1", kind="lesson",
                                    rewrite="Pin dependencies to exact versions."),
                              [Ent("e1", statement=self.LESSON, scope="project:p1")])
        self._lesson_run(r, "r2")
        self.assertEqual(len(store.chronicle_list()), 2)

    def test_other_project_scope_not_merged(self):
        r, store, _, _ = make(panel("adopt", "adopt", "adopt", scope="project:p1", kind="lesson", rewrite=self.LESSON),
                              [Ent("e1", statement=self.LESSON, scope="project:other")])
        self._lesson_run(r, "r2")
        self.assertEqual(len(store.chronicle_list()), 2)


class MockModeTests(unittest.TestCase):
    def test_runs_against_mock_gateway(self):
        from council.core.config import load_config
        from council.core.events import EventBus
        from council.core.store import Store
        from council.gateway.gateway import Gateway
        from council.gateway.mock import MockResponder

        reg = [M("m-a", "A", ram=1), M("m-b", "B", ram=2), M("m-c", "C", ram=3)]
        store = Store(":memory:")
        try:
            bus = EventBus(store)
        except TypeError:
            bus = EventBus()
        gw = Gateway(load_config(), reg, store, bus, responder=MockResponder(seed=1))
        events = []
        r = Reflector(gw, store, lambda t, p: events.append((t, p)), embed, CFG, lambda: 5.0)
        judges = pick_judges(reg, None)
        out = run(r.reflect("r1", [C(), C("picked tabs", source="user_choice", id="c2")], judges, "p1", ["coding"]))
        self.assertEqual(types(events).count("memory.candidate"), 2)
        self.assertEqual(types(events).count("memory.verdict"), 6)
        self.assertEqual(types(events).count("memory.committed"), len(out))
        ids = {e.id for e in store.chronicle_list()}
        self.assertTrue(all(e.id in ids for e in out))


if __name__ == "__main__":
    unittest.main()
