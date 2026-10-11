import unittest
from collections import Counter
from pathlib import Path

from council.core.config import RouterConfig, load_config, load_registry
from council.core.schemas import (
    LENSES, CalibrationCell, LineupRecord, MeasuredStats, ModelEntry, TaskProfile,
)
from council.router.competence import SkillTable
from council.router.picker import eligible_models, pick, pick_with_notes, random_lineup
from council.router.tier_b import CalibrationIndex

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = load_registry(ROOT / "config" / "models.json")
CFG = load_config(ROOT / "config" / "council.toml").router
BY_ID = {m.id: m for m in REGISTRY}
BUDGET = 100.0


def table_for(registry):
    return SkillTable({m.id: dict(m.priors) for m in registry})


def prof(**cats):
    return TaskProfile(categories=cats)


def ids(rec):
    return [s.model_id for s in rec.seats]


def mk(mid, lab, ram=10.0, q=0.6, roles=("seat",), status="active", modalities=("text",), lineage=""):
    return ModelEntry(
        id=mid, lab=lab, lineage=lineage or mid, roles=list(roles), status=status,
        modalities=list(modalities), priors={"math": q},
        measured=MeasuredStats(ram_gb_live=ram, load_s=1.0),
    )


class RealRegistryTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(REGISTRY, "config/models.json missing")
        self.table = table_for(REGISTRY)

    def run_pick(self, profile, **kw):
        kw.setdefault("seed", 1)
        return pick(profile, 5, REGISTRY, self.table, BUDGET, CFG, **kw)

    def test_shape(self):
        rec = self.run_pick(prof(math=1.0))
        self.assertIsInstance(rec, LineupRecord)
        self.assertEqual(rec.k, 5)
        self.assertEqual(len(rec.seats), 5)
        self.assertEqual([s.seat_no for s in rec.seats], [0, 1, 2, 3, 4])
        self.assertEqual(len(set(ids(rec))), 5)
        self.assertEqual(rec.tier, "A")
        self.assertEqual(rec.seed, 1)
        self.assertEqual(sum(s.is_wildcard for s in rec.seats), 1)
        self.assertTrue(rec.seats[-1].is_wildcard)
        self.assertEqual(sum(s.is_chair for s in rec.seats), 1)

    def test_hard_constraints(self):
        for cats in ({"math": 1.0}, {"writing": 1.0}, {"code": 0.6, "planning": 0.4}):
            rec = self.run_pick(TaskProfile(categories=cats))
            for mid in ids(rec):
                m = BY_ID[mid]
                self.assertEqual(m.status, "active")
                self.assertIn("seat", m.roles)
                self.assertIsNotNone(m.measured.ram_gb_live)
            self.assertLessEqual(sum(BY_ID[i].measured.ram_gb_live for i in ids(rec)), BUDGET)
            self.assertEqual(max(Counter(BY_ID[i].lab for i in ids(rec)).values()), 1)

    def test_chair_is_highest_q(self):
        rec = self.run_pick(prof(logic=1.0))
        top = max(rec.seats, key=lambda s: s.q)
        self.assertEqual(rec.chair_model_id, top.model_id)
        self.assertTrue(next(s for s in rec.seats if s.model_id == top.model_id).is_chair)

    def test_lenses(self):
        rec = self.run_pick(prof(science=1.0))
        lenses = [s.lens for s in rec.seats]
        self.assertTrue(all(l in LENSES for l in lenses))
        for required in ("builder", "skeptic", "first_principles"):
            self.assertIn(required, lenses)
        chair = next(s for s in rec.seats if s.is_chair)
        self.assertEqual(chair.lens, "specialist")

    def test_alternates(self):
        rec = self.run_pick(prof(math=1.0))
        self.assertLessEqual(len(rec.alternates), 2)
        self.assertTrue(rec.alternates)
        self.assertFalse(set(rec.alternates) & set(ids(rec)))
        for a in rec.alternates:
            self.assertIn("seat", BY_ID[a].roles)

    def test_deterministic_for_seed(self):
        p = prof(knowledge=0.5, reading=0.5)
        a = self.run_pick(p, seed=7)
        b = self.run_pick(p, seed=7)
        self.assertEqual(a.model_dump(), b.model_dump())
        shuffled = list(reversed(REGISTRY))
        c = pick(p, 5, shuffled, self.table, BUDGET, CFG, seed=7)
        self.assertEqual(a.model_dump(), c.model_dump())

    def test_profiles_yield_different_lineups(self):
        seen = set()
        for cat in ("math", "writing", "code", "planning", "reading"):
            rec = self.run_pick(TaskProfile(categories={cat: 1.0}))
            seen.add(frozenset(ids(rec)))
        self.assertGreaterEqual(len(seen), 3)
        math = set(ids(self.run_pick(prof(math=1.0))))
        writing = set(ids(self.run_pick(prof(writing=1.0))))
        self.assertNotEqual(math, writing)
        self.assertIn("phi-next-14b", math)
        self.assertIn("gemma4-26b-a4b", writing)

    def test_scores_recorded(self):
        rec = self.run_pick(prof(planning=0.5, code=0.5))
        self.assertGreater(rec.chosen_score.total, 0)
        self.assertGreater(rec.chosen_score.merit, 0)
        self.assertLessEqual(len(rec.rejected), 5)
        totals = [r.score.total for r in rec.rejected]
        self.assertEqual(totals, sorted(totals, reverse=True))
        merit = set(ids(rec)[:-1])
        for r in rec.rejected:
            self.assertEqual(len(r.models), 4)
            self.assertNotEqual(set(r.models), merit)

    def test_budget_respected_when_tight(self):
        rec = self.run_pick(prof(math=1.0), )
        tight = pick(prof(math=1.0), 5, REGISTRY, self.table, 60.0, CFG, seed=1)
        self.assertLessEqual(sum(BY_ID[i].measured.ram_gb_live for i in ids(tight)), 60.0)
        self.assertEqual(tight.k, 5)
        self.assertNotEqual(set(ids(rec)), set(ids(tight)))

    def test_vision_need_filters(self):
        p = TaskProfile(categories={"reading": 1.0}, needs=["vision"])
        el = eligible_models(p, REGISTRY)
        self.assertTrue(el)
        self.assertTrue(all("image" in m.modalities for m in el))
        rec, notes = pick_with_notes(p, 5, REGISTRY, self.table, BUDGET, CFG)
        self.assertEqual(rec.k, len(el))
        self.assertTrue(any("k shrunk" in n for n in notes))

    def test_override(self):
        forced = ["glm-small", "gpt-oss-120b", "phi-next-14b"]
        rec, notes = pick_with_notes(prof(math=1.0), 5, REGISTRY, self.table, BUDGET, CFG, override=forced)
        self.assertEqual(ids(rec), forced)
        self.assertEqual(rec.k, 3)
        self.assertFalse(any(s.is_wildcard for s in rec.seats))
        self.assertEqual(rec.chair_model_id, "gpt-oss-120b")
        self.assertTrue(any("override" in n for n in notes))
        with self.assertRaises(ValueError):
            pick(prof(math=1.0), 5, REGISTRY, self.table, BUDGET, CFG, override=["nope"])

    def test_repeat_penalty_and_resident_change_scores(self):
        p = prof(planning=1.0)
        base = self.run_pick(p)
        again = self.run_pick(p, recent=[ids(base)] * 5)
        self.assertGreater(again.chosen_score.repeat + sum(r.score.repeat for r in again.rejected), 0)
        self.assertGreater(base.chosen_score.load, 0)
        warm = self.run_pick(p, resident={m.id for m in REGISTRY})
        self.assertEqual(warm.chosen_score.load, 0)


class SmallRegistryTest(unittest.TestCase):
    def test_shrinks_k_when_few_eligible(self):
        reg = [
            mk("a", "A"), mk("b", "B"),
            mk("off", "C", status="disabled"), mk("w", "D", roles=("worker",)),
            mk("nofp", "E", ram=None),
        ]
        rec, notes = pick_with_notes(prof(math=1.0), 5, reg, table_for(reg), 100.0, RouterConfig())
        self.assertEqual(rec.k, 2)
        self.assertEqual(set(ids(rec)), {"a", "b"})
        self.assertTrue(any("k shrunk" in n for n in notes))

    def test_lab_relaxed_only_when_needed(self):
        reg = [mk("a1", "A"), mk("a2", "A", lineage="x"), mk("b1", "B")]
        rec, notes = pick_with_notes(prof(math=1.0), 3, reg, table_for(reg), 100.0, RouterConfig())
        self.assertEqual(rec.k, 3)
        self.assertTrue(any("max_per_lab relaxed" in n for n in notes))

        reg2 = reg + [mk("c1", "C")]
        rec2, notes2 = pick_with_notes(prof(math=1.0), 3, reg2, table_for(reg2), 100.0, RouterConfig())
        labs = {m.id: m.lab for m in reg2}
        self.assertEqual(len({labs[i] for i in ids(rec2)}), 3)
        self.assertFalse(any("max_per_lab" in n for n in notes2))

    def test_floor(self):
        reg = [
            mk("top", "A", q=0.90), mk("m1", "B", q=0.85), mk("m2", "C", q=0.82),
            mk("wild", "D", q=0.72), mk("low", "E", q=0.40),
        ]
        rec, notes = pick_with_notes(prof(math=1.0), 4, reg, table_for(reg), 100.0, RouterConfig())
        self.assertEqual(ids(rec), ["top", "m1", "m2", "wild"])
        self.assertEqual(notes, [])
        self.assertTrue(rec.seats[3].is_wildcard)
        self.assertEqual(rec.alternates, ["low"])
        self.assertEqual(rec.rejected, [])

    def test_floor_widened_when_no_lineup(self):
        reg = [mk("top", "A", q=0.90), mk("m1", "B", q=0.60), mk("m2", "C", q=0.55)]
        rec, notes = pick_with_notes(prof(math=1.0), 3, reg, table_for(reg), 100.0, RouterConfig())
        self.assertEqual(rec.k, 3)
        self.assertTrue(any("floor widened" in n for n in notes))

    def test_budget_shrinks_k(self):
        reg = [mk("a", "A", ram=10), mk("b", "B", ram=10), mk("c", "C", ram=10)]
        rec, notes = pick_with_notes(prof(math=1.0), 3, reg, table_for(reg), 20.0, RouterConfig())
        self.assertEqual(rec.k, 2)
        self.assertTrue(any("k shrunk" in n for n in notes))
        with self.assertRaises(ValueError):
            pick(prof(math=1.0), 3, reg, table_for(reg), 5.0, RouterConfig())

    def test_no_eligible_raises(self):
        with self.assertRaises(ValueError):
            pick(prof(math=1.0), 3, [mk("w", "A", roles=("worker",))], SkillTable({}), 100.0, RouterConfig())

    def test_wildcard_prefers_less_used_model(self):
        reg = [
            mk("top", "A", q=0.9), mk("m1", "B", q=0.9),
            mk("used", "C", q=0.75), mk("fresh", "D", q=0.75),
        ]
        table = table_for(reg)
        table.stats[("used", "math")] = (30.0, 10.0)  # mean 0.75, 36 trials
        rec = pick(prof(math=1.0), 3, reg, table, 100.0, RouterConfig(), total_runs=50)
        self.assertEqual(rec.seats[-1].model_id, "fresh")

    def test_seed_rotates_near_equal_lineups(self):
        reg = [mk(f"m{i}", f"L{i}", q=0.7) for i in range(6)]
        table = table_for(reg)
        seen = {
            frozenset(ids(pick(prof(math=1.0), 4, reg, table, 100.0, RouterConfig(), seed=s)))
            for s in range(20)
        }
        self.assertGreater(len(seen), 1)

    def test_config_as_dict_or_none(self):
        reg = [mk("a", "A"), mk("b", "B"), mk("c", "C")]
        self.assertEqual(pick(prof(math=1.0), 3, reg, table_for(reg), 100.0, None).k, 3)
        self.assertEqual(pick(prof(math=1.0), 3, reg, table_for(reg), 100.0, {"tau": 0.0}).k, 3)


def calib(right, n_tasks=24, models=("a", "b", "c", "d", "e")):
    """Calibration matrix: models in `right` always answer right, the rest always wrong."""
    matrix, emb, truths = {}, {}, {}
    for i in range(n_tasks):
        t = f"t{i:02d}"
        matrix[t] = {
            m: CalibrationCell(task_id=t, model_id=m, correct=(m in right),
                               answer_key="yes" if m in right else f"no-{m}")
            for m in models
        }
        emb[t] = [1.0, 0.0]
        truths[t] = "yes"
    return CalibrationIndex(matrix, emb, truths)


class TierBTest(unittest.TestCase):
    def setUp(self):
        # Tier A priors favour a, b, c. The calibration matrix says only some models are right.
        self.reg = [
            mk("a", "A", q=0.80), mk("b", "B", q=0.79), mk("c", "C", q=0.78),
            mk("d", "D", q=0.72), mk("e", "E", q=0.71),
        ]
        self.table = table_for(self.reg)
        self.cfg = RouterConfig(tau=0.0)
        self.p = prof(math=1.0)
        self.emb = [1.0, 0.0]

    def run_pick(self, **kw):
        return pick(self.p, 4, self.reg, self.table, 100.0, self.cfg, seed=3, **kw)

    def test_tier_b_changes_choice(self):
        base = self.run_pick()
        self.assertEqual(base.tier, "A")
        self.assertEqual(set(ids(base)[:-1]), {"a", "b", "c"})

        rec = self.run_pick(calibration=calib({"c", "d", "e"}), embedding=self.emb)
        self.assertEqual(rec.tier, "B")
        self.assertEqual(set(ids(rec)[:-1]), {"c", "d", "e"})
        self.assertGreater(rec.chosen_score.vote, 0.9)
        self.assertGreater(rec.chosen_score.cover, 0.9)
        self.assertIn(rec.chair_model_id, {"c", "d", "e"})
        q = {s.model_id: s.q for s in rec.seats}
        self.assertGreater(q["c"], 0.9)  # q_b, not the prior

    def test_tier_b_other_matrix_other_lineup(self):
        rec = self.run_pick(calibration=calib({"a", "b", "e"}), embedding=self.emb)
        self.assertEqual(rec.tier, "B")
        self.assertEqual(set(ids(rec)[:-1]), {"a", "b", "e"})

    def test_tier_a_path_unchanged(self):
        base = self.run_pick().model_dump()
        ready = calib({"c", "d", "e"})
        small = calib({"c", "d", "e"}, n_tasks=5)
        self.assertFalse(small.ready())
        for kw in (
            {"calibration": None, "embedding": self.emb},   # no calibration
            {"calibration": ready, "embedding": None},      # no embedding
            {"calibration": ready, "embedding": []},        # empty embedding
            {"calibration": small, "embedding": self.emb},  # not ready
        ):
            self.assertEqual(self.run_pick(**kw).model_dump(), base)

    def test_tier_b_override_records_tier(self):
        rec, notes = pick_with_notes(
            self.p, 4, self.reg, self.table, 100.0, self.cfg,
            calibration=calib({"c", "d", "e"}), embedding=self.emb, override=["a", "b"],
        )
        self.assertEqual(ids(rec), ["a", "b"])
        self.assertEqual(rec.tier, "B")
        self.assertTrue(any("override" in n for n in notes))

    def test_tier_b_deterministic(self):
        c = calib({"c", "d", "e"})
        a = self.run_pick(calibration=c, embedding=self.emb)
        b = self.run_pick(calibration=c, embedding=self.emb)
        self.assertEqual(a.model_dump(), b.model_dump())


class RandomLineupTest(unittest.TestCase):
    def test_feasible_on_real_registry(self):
        for seed in range(10):
            rec = random_lineup(prof(math=1.0), 5, REGISTRY, 60.0, seed)
            self.assertIsInstance(rec, LineupRecord)
            self.assertEqual(rec.k, len(rec.seats))
            self.assertEqual(len(set(ids(rec))), rec.k)
            self.assertEqual(rec.seed, seed)
            self.assertEqual(rec.tier, "A")
            self.assertEqual(sum(s.is_chair for s in rec.seats), 1)
            self.assertFalse(any(s.is_wildcard for s in rec.seats))
            self.assertLessEqual(sum(BY_ID[i].measured.ram_gb_live for i in ids(rec)), 60.0)
            for mid in ids(rec):
                self.assertEqual(BY_ID[mid].status, "active")
                self.assertIn("seat", BY_ID[mid].roles)
            self.assertFalse(set(rec.alternates) & set(ids(rec)))

    def test_deterministic_and_varies(self):
        a = random_lineup(prof(math=1.0), 5, REGISTRY, BUDGET, 4)
        b = random_lineup(prof(math=1.0), 5, REGISTRY, BUDGET, 4)
        self.assertEqual(a.model_dump(), b.model_dump())
        seen = {frozenset(ids(random_lineup(prof(math=1.0), 5, REGISTRY, BUDGET, s))) for s in range(20)}
        self.assertGreater(len(seen), 1)

    def test_ignores_quality(self):
        reg = [mk("top", "A", q=0.9), mk("low", "B", q=0.1), mk("mid", "C", q=0.5)]
        seen = set()
        for s in range(30):
            seen |= set(ids(random_lineup(prof(math=1.0), 2, reg, 100.0, s)))
        self.assertEqual(seen, {"top", "low", "mid"})

    def test_shrinks_and_raises(self):
        reg = [mk("a", "A", ram=10), mk("b", "B", ram=10), mk("c", "C", ram=10)]
        self.assertEqual(random_lineup(prof(math=1.0), 3, reg, 20.0, 0).k, 2)
        same_lab = [mk("a1", "A"), mk("a2", "A")]
        self.assertEqual(random_lineup(prof(math=1.0), 2, same_lab, 100.0, 0).k, 2)
        with self.assertRaises(ValueError):
            random_lineup(prof(math=1.0), 3, reg, 5.0, 0)
        with self.assertRaises(ValueError):
            random_lineup(prof(math=1.0), 3, [mk("w", "A", roles=("worker",))], 100.0, 0)


if __name__ == "__main__":
    unittest.main()
