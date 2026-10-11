import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from council.bench import graders
from council.bench.runner import BenchRunner, parse_mode, read_options, stratified
from council.core.config import Config
from council.core.events import EventBus
from council.core.schemas import BenchRunRequest, MeasuredStats, ModelEntry
from council.core.store import Store
from council.gateway.gateway import Gateway
from council.gateway.mock import MockResponder
from council.host.drivers import MockDriver
from council.host.host import Host
from council.host.ram import RamBudget

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "bench" / "tasks" / "sample.jsonl"
MODES = ["solo:*", "council_vote_only", "council", "random_council", "self_consistency:best@3"]
SEATS = ["m-a", "m-b", "m-c", "m-d", "m-e", "m-f"]
ACCURACY = {"m-a": 0.9, "m-b": 0.8, "m-c": 0.7, "m-d": 0.6, "m-e": 0.5, "m-f": 0.4}


def model(mid, roles, lab, ram=8.0, params=8.0):
    return ModelEntry(
        id=mid, lab=lab, lineage=lab, roles=roles, quant="Q4", params_b=params,
        sampling={"temperature": 0.6, "top_p": 0.95},
        priors={"math": 0.6, "logic": 0.6},
        measured=MeasuredStats(ram_gb_live=ram, ram_gb_batch=ram, load_s=1.0),
    )


def registry():
    out = [model(mid, ["seat"], f"lab-{mid}") for mid in SEATS]
    out.append(model("clerk-1", ["clerk", "worker"], "lab-clerk", ram=4.0))
    out.append(model("big-1", ["baseline"], "lab-big", ram=60.0, params=120.0))
    return out


class SpyStore(Store):
    def __init__(self):
        super().__init__(":memory:")
        self.cells = []

    def calibration_put(self, cell):
        self.cells.append(cell)
        super().calibration_put(cell)


class SpyGateway(Gateway):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.specs = []

    async def call(self, spec, seat_no=None, round=None):
        self.specs.append(spec)
        return await super().call(spec, seat_no, round)


class SpyHost(Host):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.loads = []
        self.unloads = []

    async def load(self, model_id, profile, run_id="manual"):
        self.loads.append((model_id, profile))
        return await super().load(model_id, profile, run_id)

    async def unload(self, model_id, run_id="manual"):
        self.unloads.append(model_id)
        await super().unload(model_id, run_id)


def build(tribunal_in_bench=False):
    config = Config()
    config.gateway.mock = True
    config.host.core_models = []
    config.tribunal.in_bench = tribunal_in_bench
    reg = registry()
    store = SpyStore()
    bus = EventBus(store)
    footprints = {}
    for m in reg:
        footprints[(m.id, "live")] = m.measured.ram_gb_live
        footprints[(m.id, "batch")] = m.measured.ram_gb_batch
    ram = RamBudget(lambda: 128.0, 12.0, set(), footprints)
    host = SpyHost(MockDriver(), ram, reg, bus)
    gateway = SpyGateway(config, reg, store, bus, responder=MockResponder(seed=0, accuracy=ACCURACY),
                         endpoint_for=host.endpoint)
    events = []
    runner = BenchRunner(gateway, host, reg, store, config, lambda t, p: events.append((t, p)))
    return runner, gateway, host, store, events


class ParseModeTests(unittest.TestCase):
    def test_modes(self):
        self.assertEqual(parse_mode("solo:m1").kind, "solo")
        self.assertEqual(parse_mode("solo:m1").model, "m1")
        self.assertEqual(parse_mode("solo:*").model, "*")
        for name in ("big_single", "council_vote_only", "council", "random_council"):
            self.assertEqual(parse_mode(name).kind, name)
        m = parse_mode("self_consistency:best@3")
        self.assertEqual((m.kind, m.model, m.k), ("self_consistency", "best", 3))
        m = parse_mode("self_consistency:m1", default_k=7)
        self.assertEqual((m.model, m.k), ("m1", 7))

    def test_bad(self):
        for bad in ("", "solo", "solo:", "nope", "self_consistency:@3", "self_consistency:m@0"):
            with self.assertRaises(ValueError):
                parse_mode(bad)


class FullRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "run"
        cls.runner, cls.gateway, cls.host, cls.store, cls.events = build()
        req = BenchRunRequest(tasks_path=str(SAMPLE), modes=MODES, split="test")
        cls.rows = asyncio.run(cls.runner.run(req, cls.out))
        cls.tasks = graders.load_tasks(SAMPLE)
        cls.test_ids = {t.id for t in cls.tasks if t.split == "test"}
        cls.cal_ids = {t.id for t in cls.tasks if t.split == "calibration"}

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.tmp.cleanup()

    def test_rows(self):
        names = [r.mode for r in self.rows]
        want = [f"solo:{m}" for m in SEATS] + [
            "council_vote_only", "council", "random_council", "self_consistency:best@3"]
        self.assertEqual(sorted(names), sorted(want))
        for row in self.rows:
            self.assertEqual(row.n, len(self.test_ids))
            self.assertGreaterEqual(row.accuracy, 0.0)
            self.assertLessEqual(row.accuracy, 1.0)
            self.assertGreater(row.mean_tokens, 0)

    def test_files(self):
        self.assertTrue((self.out / "report.md").is_file())
        payload = json.loads((self.out / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(len(payload["rows"]), len(self.rows))
        self.assertEqual(payload["extra"]["tasks"], len(self.test_ids))
        self.assertTrue((self.out / "results.jsonl").is_file())
        for rel in payload["extra"]["results_files"].values():
            path = self.out / rel
            self.assertTrue(path.is_file(), rel)
            lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
            self.assertEqual({x["id"] for x in lines}, self.test_ids)
            self.assertEqual(len({x["mode"] for x in lines}), 1)

    def test_events(self):
        types = [t for t, _ in self.events]
        self.assertEqual(types[0], "bench.started")
        self.assertEqual(types[-1], "bench.completed")
        self.assertEqual(types.count("bench.completed"), 1)
        self.assertIn("bench.progress", types)
        started, completed = self.events[0][1], self.events[-1][1]
        total = len(self.rows) * len(self.test_ids)
        self.assertEqual(started["total"], total)
        self.assertIsNone(completed["error"])
        self.assertEqual(len(completed["summary"]), len(self.rows))
        with_result = [p for t, p in self.events if t == "bench.progress" and p["result"]]
        self.assertEqual(len(with_result), total)
        self.assertEqual(with_result[-1]["done"], total)

    def test_no_test_task_in_calibration(self):
        self.assertTrue(self.store.cells)
        put_ids = {c.task_id for c in self.store.cells}
        self.assertFalse(put_ids & self.test_ids)
        self.assertLessEqual(put_ids, self.cal_ids)
        self.assertEqual(len(self.store.cells), len(self.cal_ids) * len(SEATS))
        self.assertFalse(set(self.store.calibration_matrix()) & self.test_ids)
        embedded = self.store.kv_list("calibration_embeddings")
        self.assertEqual(set(embedded), self.cal_ids)
        self.assertFalse(set(embedded) & self.test_ids)
        by_id = {t.id: t for t in self.tasks}
        for tid, row in embedded.items():
            self.assertTrue(row["embedding"])
            self.assertEqual(row["truth"], graders.normalize(by_id[tid].answer, by_id[tid].answer_type))
            self.assertEqual(row["category"], by_id[tid].category)
            self.assertEqual(row["difficulty"], by_id[tid].difficulty)
        index = self.runner.calibration_index
        self.assertIsNotNone(index)
        for held in (index.matrix, index.task_embeddings, index.truths):
            self.assertTrue(held)
            self.assertFalse(set(held) & self.test_ids)
            self.assertLessEqual(set(held), self.cal_ids)

    def test_skill_updated_from_calibration_only(self):
        stats = self.store.get_model_stats()
        self.assertTrue(stats)
        self.assertLessEqual({m for m, _ in stats}, set(SEATS))
        prior = 4.0
        extra = sum(a + b - prior for a, b in stats.values())
        self.assertAlmostEqual(extra, len(self.cal_ids) * len(SEATS), places=6)

    def test_round0_is_the_solo_call(self):
        purposes = [s.purpose for s in self.gateway.specs]
        self.assertNotIn("seat.r0", purposes)
        self.assertIn("bench.solo", purposes)
        solo_ids = [s.call_id for s in self.gateway.specs if s.purpose == "bench.solo"]
        self.assertEqual(len(solo_ids), len(set(solo_ids)))  # each solo call is paid for once
        # Solo calls are free text now; the mock gives every model the same reply, so the
        # council agrees at round 0 and no later round is needed.

    def test_council_results(self):
        lines = [json.loads(x) for x in
                 (self.out / "council" / "results.jsonl").read_text(encoding="utf-8").splitlines()]
        for line in lines:
            self.assertTrue(line["lineup"])
            self.assertLessEqual(set(line["lineup"]), set(SEATS))
            self.assertIn(line["outcome"], ("consensus", "majority", "chair", "deadlock"))
            self.assertGreaterEqual(line["rounds_run"], 1)
            self.assertIsNotNone(line["agreement"])
        vote = [json.loads(x) for x in (self.out / "council_vote_only" / "results.jsonl")
                .read_text(encoding="utf-8").splitlines()]
        self.assertTrue(all(v["rounds_run"] == 1 for v in vote))
        self.assertTrue(all(v["outcome"] in ("consensus", "majority", "deadlock") for v in vote))
        by_id = {x["id"]: x for x in lines}
        self.assertTrue(all(by_id[v["id"]]["lineup"] == v["lineup"] for v in vote))

    def test_model_major(self):
        self.assertTrue(self.host.loads)
        self.assertTrue(all(profile == "batch" for _, profile in self.host.loads))
        self.assertEqual(sorted(self.host.loads), sorted((m, "batch") for m in self.host.unloads))
        # the calibration pass loads each seat model once, one after the other
        self.assertEqual(sorted(m for m, _ in self.host.loads[: len(SEATS)]), sorted(SEATS))

    def test_best_and_self_consistency(self):
        best = self.runner.resolved["self_consistency:best"]
        self.assertIn(best, SEATS)
        lines = [json.loads(x) for x in (self.out / "self_consistency_best@3" / "results.jsonl")
                 .read_text(encoding="utf-8").splitlines()]
        self.assertTrue(all(x["lineup"] == [best] for x in lines))
        solo = {r.mode: r for r in self.rows}[f"solo:{best}"]
        sc = {r.mode: r for r in self.rows}["self_consistency:best@3"]
        self.assertGreater(sc.mean_tokens, solo.mean_tokens)


class LiveTierBTests(unittest.TestCase):
    def test_live_pick_uses_tier_b_after_a_bench_run(self):
        from types import SimpleNamespace

        from council.api.run_pipeline import RunPipeline
        from council.core.schemas import TaskProfile
        from council.router import picker, stats as router_stats

        runner, gateway, host, store, events = build()
        self.addCleanup(store.close)
        with tempfile.TemporaryDirectory() as tmp:
            req = BenchRunRequest(tasks_path=str(SAMPLE), modes=["council_vote_only"], split="test",
                                  limit=3)
            asyncio.run(runner.run(req, Path(tmp) / "run"))
        index = RunPipeline._calibration(SimpleNamespace(d=SimpleNamespace(store=store)))
        self.assertIsNotNone(index)
        task = next(t for t in graders.load_tasks(SAMPLE) if t.split == "test")
        vec = asyncio.run(gateway.embed([task.prompt]))[0]
        self.assertTrue(vec)
        profile = TaskProfile(categories={task.category: 1.0}, difficulty=task.difficulty,
                              deliverable="answer", embedding=vec, rationale="live")
        reg = registry()
        table = router_stats.load_table(reg, store)
        lineup = picker.pick(profile, 3, reg, table, runner._seat_budget(), runner.config.router,
                             calibration=index, embedding=vec, seed=1)
        self.assertEqual(lineup.tier, "B")


class SmallRunTests(unittest.TestCase):
    def run_modes(self, modes, **kw):
        runner, gateway, host, store, events = build(**kw)
        self.addCleanup(store.close)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        req = BenchRunRequest(tasks_path=str(SAMPLE), modes=modes, split="test", limit=4)
        rows = asyncio.run(runner.run(req, Path(tmp.name) / "run"))
        return rows, runner, gateway, store, events

    def test_big_single_and_solo(self):
        rows, runner, gateway, store, _ = self.run_modes(["big_single", "solo:m-a", "solo:m-a"])
        self.assertEqual([r.mode for r in rows], ["big_single", "solo:m-a"])
        self.assertEqual(runner.resolved["big_single"], "big-1")
        self.assertTrue(all(r.n == 4 for r in rows))
        self.assertEqual(store.cells, [])  # no router, no "best": the calibration split is not run
        self.assertEqual({s.model_id for s in gateway.specs}, {"big-1", "m-a"})

    def test_models_filter(self):
        runner, gateway, host, store, events = build()
        self.addCleanup(store.close)
        with tempfile.TemporaryDirectory() as tmp:
            req = BenchRunRequest(tasks_path=str(SAMPLE), modes=["solo:*", "council"], split="test",
                                  limit=3, models=["m-a", "m-b", "m-c"])
            rows = asyncio.run(runner.run(req, Path(tmp) / "run"))
        self.assertEqual(sorted(r.mode for r in rows), ["council", "solo:m-a", "solo:m-b", "solo:m-c"])
        self.assertLessEqual({s.model_id for s in gateway.specs}, {"m-a", "m-b", "m-c", "clerk-1"})

    def test_second_run_hits_cache_and_keeps_skill(self):
        runner, gateway, host, store, events = build()
        self.addCleanup(store.close)
        req = BenchRunRequest(tasks_path=str(SAMPLE), modes=["council_vote_only"], split="test", limit=3)
        with tempfile.TemporaryDirectory() as tmp:
            # two parents: the second run must not find the first one's result files
            first = asyncio.run(runner.run(req, Path(tmp) / "a" / "run"))
            stats = store.get_model_stats()
            hits = gateway.stats()["cache_hits"]
            second = asyncio.run(runner.run(req, Path(tmp) / "b" / "run"))
        self.assertEqual([r.model_dump() for r in first], [r.model_dump() for r in second])
        self.assertEqual(stats, store.get_model_stats())  # no double counting
        self.assertGreater(gateway.stats()["cache_hits"], hits)

    def test_tribunal_in_bench(self):
        rows, runner, gateway, _, events = self.run_modes(["council"], tribunal_in_bench=True)
        self.assertEqual([r.mode for r in rows], ["council"])
        self.assertEqual(events[-1][0], "bench.completed")
        purposes = {s.purpose for s in gateway.specs}
        if runner.tribunal_outcomes:
            self.assertTrue(any(p.startswith("tribunal.") for p in purposes))

    def test_tribunal_off_by_default(self):
        _, runner, gateway, _, _ = self.run_modes(["council"])
        self.assertEqual(runner.tribunal_outcomes, {})
        self.assertFalse(any(s.purpose.startswith("tribunal.") for s in gateway.specs))

    def test_bad_mode_fails_and_reports(self):
        runner, _, _, store, events = build()
        self.addCleanup(store.close)
        with tempfile.TemporaryDirectory() as tmp:
            req = BenchRunRequest(tasks_path=str(SAMPLE), modes=["solo:nobody"], split="test")
            with self.assertRaises(ValueError):
                asyncio.run(runner.run(req, Path(tmp) / "run"))
        self.assertEqual(events[-1][0], "bench.completed")
        self.assertTrue(events[-1][1]["error"])


class SplitGuardTests(unittest.TestCase):
    """The reported split is kept apart from the calibration split (18.5)."""

    def run_on(self, modes, split, tasks_path=SAMPLE, limit=4):
        runner, gateway, host, store, events = build()
        self.addCleanup(store.close)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        req = BenchRunRequest(tasks_path=str(tasks_path), modes=modes, split=split, limit=limit)
        return runner, gateway, store, events, req, Path(tmp.name) / "run"

    def test_tuned_modes_are_refused_on_the_calibration_split(self):
        for modes in (["council"], ["council_vote_only"], ["random_council"],
                      ["self_consistency:best@3"], ["solo:m-a", "council"]):
            runner, gateway, store, events, req, out = self.run_on(modes, "calibration")
            with self.assertRaises(ValueError) as ctx:
                asyncio.run(runner.run(req, out))
            self.assertIn("calibration split", str(ctx.exception))
            self.assertEqual(gateway.specs, [], modes)  # refused before any model call
            self.assertEqual(store.cells, [], modes)    # and before anything was calibrated
            self.assertEqual(events[-1][0], "bench.completed")
            self.assertTrue(events[-1][1]["error"])

    def test_plain_solo_may_run_on_the_calibration_split_and_the_report_says_so(self):
        import json
        runner, gateway, store, events, req, out = self.run_on(["solo:m-a"], "calibration")
        rows = asyncio.run(runner.run(req, out))
        self.assertEqual([(r.mode, r.n) for r in rows], [("solo:m-a", 4)])
        extra = json.loads((out / "report.json").read_text(encoding="utf-8"))["extra"]
        self.assertTrue(extra["reported_on_calibration_split"])
        runner, gateway, store, events, req, out = self.run_on(["solo:m-a"], "test")
        asyncio.run(runner.run(req, out))
        extra = json.loads((out / "report.json").read_text(encoding="utf-8"))["extra"]
        self.assertFalse(extra["reported_on_calibration_split"])

    def test_a_task_id_that_is_also_a_calibration_task_is_never_reported(self):
        import json
        rows = [json.loads(ln) for ln in SAMPLE.read_text(encoding="utf-8").splitlines() if ln.strip()]
        cal = next(r for r in rows if r["split"] == "calibration")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "tasks.jsonl"
        leaked = dict(cal, split="test")
        path.write_text("\n".join(json.dumps(r) for r in [leaked] + rows), encoding="utf-8")
        runner, gateway, store, events, req, out = self.run_on(["solo:m-a"], "test", path, limit=None)
        asyncio.run(runner.run(req, out))
        got = [json.loads(ln)["id"] for ln in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(got)
        self.assertNotIn(cal["id"], got)


# ---------------------------------------------------------------------------------------
# Run-size options, progress, resume, failed loads
# ---------------------------------------------------------------------------------------

MANY = [f"s-{i:02d}" for i in range(12)]


def many_seats():
    """Twelve seat models with different priors, so a Tier A lineup is a proper subset."""
    out = []
    for i, mid in enumerate(MANY):
        m = model(mid, ["seat"], f"lab-{mid}")
        out.append(m.model_copy(update={"priors": {"math": 0.3 + 0.05 * i, "logic": 0.9 - 0.05 * i}}))
    out.append(model("clerk-1", ["clerk", "worker"], "lab-clerk", ram=4.0))
    return out


class BrokenHost(SpyHost):
    """A host on which some models (or all of them) will not load."""

    broken = set()
    all_broken = False

    async def load(self, model_id, profile, run_id="manual"):
        if self.all_broken or model_id in self.broken:
            self.loads.append((model_id, profile))
            raise RuntimeError(f"cannot load {model_id}: out of memory")
        return await super().load(model_id, profile, run_id)


def build_with(reg=None, host_cls=SpyHost):
    config = Config()
    config.gateway.mock = True
    config.host.core_models = []
    reg = reg if reg is not None else registry()
    store = SpyStore()
    bus = EventBus(store)
    footprints = {}
    for m in reg:
        footprints[(m.id, "live")] = m.measured.ram_gb_live
        footprints[(m.id, "batch")] = m.measured.ram_gb_batch
    host = host_cls(MockDriver(), RamBudget(lambda: 128.0, 12.0, set(), footprints), reg, bus)
    gateway = SpyGateway(config, reg, store, bus, responder=MockResponder(seed=0, accuracy=ACCURACY),
                         endpoint_for=host.endpoint)
    events = []
    runner = BenchRunner(gateway, host, reg, store, config, lambda t, p: events.append((t, p)))
    return runner, gateway, host, store, events


def read_extra(out):
    return json.loads((Path(out) / "report.json").read_text(encoding="utf-8"))["extra"]


class _Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tasks = graders.load_tasks(SAMPLE)
        self.cal_ids = {t.id for t in self.tasks if t.split == "calibration"}
        self.test_ids = {t.id for t in self.tasks if t.split == "test"}

    def make(self, **kw):
        built = build_with(**kw)
        self.addCleanup(built[3].close)
        return built

    def req(self, modes, **kw):
        kw.setdefault("limit", 4)
        return BenchRunRequest(tasks_path=str(SAMPLE), modes=modes, split="test", **kw)

    def go(self, runner, req, name="run"):
        out = self.root / name
        return asyncio.run(runner.run(req, out)), out


class OptionTests(unittest.TestCase):
    def test_defaults_are_the_spec_settings(self):
        opts = read_options(BenchRunRequest(), Config().bench)
        self.assertEqual((opts.reasoning, opts.calibration_limit, opts.calibration_models),
                         ("max", None, "lineup"))
        self.assertEqual(opts.max_output_tokens, Config().bench.solo_max_output_tokens)
        self.assertEqual(opts.max_reasoning_tokens, Config().bench.solo_max_reasoning_tokens)
        self.assertTrue(opts.resume)
        self.assertFalse(opts.progress)
        self.assertTrue(opts.plain)

    def test_a_request_without_the_new_fields_still_works(self):
        from types import SimpleNamespace
        opts = read_options(SimpleNamespace(), Config().bench)
        self.assertEqual((opts.reasoning, opts.resume, opts.plain), ("max", True, True))

    def test_off_has_no_reasoning_cap_unless_one_is_given(self):
        cfg = Config().bench
        self.assertIsNone(read_options(BenchRunRequest(reasoning="off"), cfg).max_reasoning_tokens)
        opts = read_options(BenchRunRequest(reasoning="council", max_output_tokens=200,
                                            max_reasoning_tokens=300), cfg)
        self.assertEqual((opts.max_output_tokens, opts.max_reasoning_tokens), (200, 300))
        self.assertFalse(opts.plain)

    def test_bad_values_are_refused(self):
        from types import SimpleNamespace
        cfg = Config().bench
        for bad in (dict(reasoning="loud"), dict(calibration_models="some"),
                    dict(calibration_limit=-1), dict(max_output_tokens=0)):
            with self.assertRaises(ValueError):
                read_options(SimpleNamespace(**bad), cfg)

    def test_stratified_takes_every_category_first(self):
        cal = [t for t in graders.load_tasks(SAMPLE) if t.split == "calibration"]
        cats = {t.category for t in cal}
        self.assertEqual(stratified(cal, None), cal)
        self.assertEqual(stratified(cal, 0), [])
        self.assertEqual(stratified(cal, 10 ** 6), cal)
        for n in (1, 3, len(cats), len(cats) + 2):
            got = stratified(cal, n)
            self.assertEqual(len(got), n)
            self.assertEqual(len({t.id for t in got}), n)
            self.assertEqual(len({t.category for t in got}), min(n, len(cats)))
            self.assertEqual(got, stratified(cal, n))  # no randomness
            self.assertEqual(got, [t for t in cal if t in got])  # file order kept


class CalibrationBoundTests(_Case):
    def test_calibration_limit_bounds_the_calibration_pass(self):
        runner, gateway, host, store, _ = self.make()
        _, out = self.go(runner, self.req(["council_vote_only"], calibration_limit=5))
        used = {c.task_id for c in store.cells}
        self.assertEqual(len(used), 5)
        self.assertLessEqual(used, self.cal_ids)  # still the calibration split, never the test split
        asked = {s.meta["task_id"] for s in gateway.specs if s.purpose == "bench.solo"}
        self.assertEqual(len(asked & self.cal_ids), 5)
        self.assertLessEqual(set(store.kv_list("calibration_embeddings")), used)
        st = read_extra(out)["settings"]
        self.assertEqual((st["calibration_limit"], st["calibration_tasks"]), (5, 5))

    def test_zero_skips_calibration_and_routes_with_tier_a(self):
        runner, gateway, host, store, _ = self.make()
        rows, out = self.go(runner, self.req(["council_vote_only", "council"], calibration_limit=0))
        self.assertEqual([r.n for r in rows], [4, 4])
        self.assertEqual(store.cells, [])
        asked = {s.meta["task_id"] for s in gateway.specs if s.purpose == "bench.solo"}
        self.assertFalse(asked & self.cal_ids)
        self.assertIsNone(runner.calibration_index)
        extra = read_extra(out)
        self.assertEqual(extra["router_tiers"], {"A": 4})
        self.assertEqual(extra["settings"]["calibrated_models"], [])
        self.assertIn("skipped", (out / "report.md").read_text(encoding="utf-8"))

    def test_lineup_calibrates_only_models_that_could_be_seated(self):
        runner, gateway, host, store, _ = self.make(reg=many_seats())
        _, out = self.go(runner, self.req(["council_vote_only"], limit=2))
        lineup_models = {c.model_id for c in store.cells}
        self.assertTrue(lineup_models)
        self.assertLess(len(lineup_models), len(MANY))  # not every registered model
        self.assertEqual(sorted(lineup_models), sorted(read_extra(out)["settings"]["calibrated_models"]))
        self.assertLessEqual({c.task_id for c in store.cells}, self.cal_ids)

        runner, gateway, host, store, _ = self.make(reg=many_seats())
        _, out = self.go(runner, self.req(["council_vote_only"], limit=2, calibration_models="all"), "all")
        self.assertEqual({c.model_id for c in store.cells}, set(MANY))
        self.assertEqual(read_extra(out)["settings"]["calibration_models"], "all")

    def test_best_needs_every_seat_model(self):
        runner, gateway, host, store, _ = self.make(reg=many_seats())
        self.go(runner, self.req(["self_consistency:best@2"], limit=2, calibration_limit=3))
        self.assertEqual({c.model_id for c in store.cells}, set(MANY))
        self.assertEqual(len({c.task_id for c in store.cells}), 3)


class ReasoningTests(_Case):
    def solo_specs(self, gateway):
        return [s for s in gateway.specs if s.purpose == "bench.solo"]

    def test_default_is_max_with_the_configured_caps(self):
        runner, gateway, _, _, _ = self.make()
        _, out = self.go(runner, self.req(["solo:m-a", "council_vote_only"]))
        cfg = runner.config.bench
        got = {(s.reasoning, s.max_output_tokens, s.max_reasoning_tokens, s.cacheable)
               for s in self.solo_specs(gateway)}
        self.assertEqual(got, {("max", cfg.solo_max_output_tokens, cfg.solo_max_reasoning_tokens, True)})
        self.assertEqual(read_extra(out)["settings"]["reasoning"], "max")

    def test_off_and_caps_apply_to_every_solo_call_in_every_mode(self):
        runner, gateway, _, _, _ = self.make()
        req = self.req(["solo:m-a", "big_single", "council", "self_consistency:m-b@2"],
                       reasoning="off", max_output_tokens=300)
        rows, out = self.go(runner, req)
        self.assertEqual(len(rows), 4)
        specs = self.solo_specs(gateway)
        self.assertTrue(specs)
        self.assertEqual({(s.reasoning, s.max_output_tokens, s.max_reasoning_tokens) for s in specs},
                         {("off", 300, None)})
        self.assertEqual(len({json.dumps(s.messages) for s in specs if s.meta["task_id"] == specs[0].meta["task_id"]}), 1)
        self.assertNotIn("seat.r0", [s.purpose for s in gateway.specs])  # round 0 is still the solo call
        st = read_extra(out)["settings"]
        self.assertEqual((st["reasoning"], st["max_output_tokens"], st["max_reasoning_tokens"]),
                         ("off", 300, None))
        text = (out / "report.md").read_text(encoding="utf-8")
        self.assertIn("Settings used", text)
        self.assertIn("reasoning off, max_output_tokens 300", text)
        self.assertIn("| mode |", text)


class ResumeTests(_Case):
    def test_results_of_an_earlier_run_are_reused(self):
        runner, gateway, host, store, _ = self.make()
        req = self.req(["solo:m-a", "council"])
        first, _ = self.go(runner, req, "one")
        calls, loads = len(gateway.specs), len(host.loads)
        second, out = self.go(runner, req, "two")
        self.assertEqual([r.model_dump() for r in first], [r.model_dump() for r in second])
        self.assertEqual(len(gateway.specs), calls)  # nothing was asked again
        self.assertEqual(len(host.loads), loads)     # and no model was loaded
        self.assertEqual(read_extra(out)["settings"]["reused"], {"solo:m-a": 4, "council": 4})
        self.assertTrue((out / "council" / "results.jsonl").is_file())

    def test_other_settings_are_not_reused(self):
        runner, gateway, host, store, _ = self.make()
        self.go(runner, self.req(["solo:m-a"]), "one")
        calls = len(gateway.specs)
        _, out = self.go(runner, self.req(["solo:m-a"], reasoning="off"), "two")
        self.assertEqual(len(gateway.specs), calls + 4)
        self.assertEqual(read_extra(out)["settings"]["reused"], {})

    def test_a_longer_run_reuses_the_solo_tasks_already_done(self):
        runner, gateway, host, store, _ = self.make()
        self.go(runner, self.req(["solo:m-a"], limit=2), "one")
        rows, out = self.go(runner, self.req(["solo:m-a"], limit=5), "two")
        self.assertEqual(rows[0].n, 5)
        self.assertEqual(read_extra(out)["settings"]["reused"], {"solo:m-a": 2})
        self.assertEqual(len([s for s in gateway.specs if s.purpose == "bench.solo"]), 5)

    def test_cached_calls_do_not_load_the_model(self):
        runner, gateway, host, store, _ = self.make()
        req = self.req(["solo:m-a"])
        self.go(runner, req, "p1/run")
        loads = len(host.loads)
        hits = gateway.stats()["cache_hits"]
        rows, _ = self.go(runner, req, "p2/run")  # another parent: no result file to reuse
        self.assertEqual(rows[0].n, 4)
        self.assertEqual(len(host.loads), loads)
        self.assertEqual(gateway.stats()["cache_hits"], hits + 4)

    def test_no_resume_asks_again(self):
        runner, gateway, host, store, _ = self.make()
        req = self.req(["solo:m-a"], resume=False)
        first, _ = self.go(runner, req, "one")
        calls, loads = len(gateway.specs), len(host.loads)
        second, out = self.go(runner, req, "two")
        self.assertEqual([r.model_dump() for r in first], [r.model_dump() for r in second])
        self.assertEqual(len(gateway.specs), calls * 2)
        self.assertEqual(len(host.loads), loads * 2)
        self.assertEqual(gateway.stats()["cache_hits"], 0)
        self.assertFalse(read_extra(out)["settings"]["resume"])


class FailedLoadTests(_Case):
    def test_a_model_that_will_not_load_is_not_run_and_not_zero(self):
        class Host(BrokenHost):
            broken = {"m-a"}
        runner, gateway, host, store, events = self.make(host_cls=Host)
        with contextlib.redirect_stderr(io.StringIO()):
            rows, out = self.go(runner, self.req(["solo:m-a", "solo:m-b"]))
        self.assertEqual([r.mode for r in rows], ["solo:m-b"])
        self.assertEqual(rows[0].n, 4)
        extra = read_extra(out)
        self.assertEqual(list(extra["not_run"]), ["solo:m-a"])
        self.assertIn("failed to load", extra["not_run"]["solo:m-a"])
        self.assertEqual(list(extra["load_failed"]), ["m-a"])
        self.assertEqual(runner.not_run, extra["not_run"])
        self.assertTrue(runner.load_errors)
        self.assertNotIn("solo:m-a", extra["results_files"])
        self.assertFalse((out / "solo_m-a").exists())
        lines = (out / "results.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual({json.loads(x)["mode"] for x in lines}, {"solo:m-b"})
        text = (out / "report.md").read_text(encoding="utf-8")
        self.assertIn("NOT RUN", text)
        self.assertNotIn("| solo:m-a |", text)
        self.assertEqual(events[-1][0], "bench.completed")

    def test_no_model_loads_gives_no_table_of_zeros(self):
        class Host(BrokenHost):
            all_broken = True
        runner, gateway, host, store, events = self.make(host_cls=Host)
        with contextlib.redirect_stderr(io.StringIO()):
            rows, out = self.go(runner, self.req(["solo:*", "council_vote_only", "council"]))
        self.assertEqual(rows, [])
        extra = read_extra(out)
        self.assertEqual(set(extra["not_run"]), {f"solo:{m}" for m in SEATS} | {"council_vote_only", "council"})
        self.assertEqual((out / "results.jsonl").read_text(encoding="utf-8"), "")
        # A model that never loaded did not answer: nothing is written to the calibration table
        # and the Router's skill table is left alone.
        self.assertEqual(store.cells, [])
        self.assertEqual(store.get_model_stats(), {})
        self.assertNotIn("0.0%", (out / "report.md").read_text(encoding="utf-8"))

    def test_a_failed_run_is_never_reused(self):
        class Host(BrokenHost):
            pass
        Host.all_broken = True
        runner, gateway, host, store, _ = self.make(host_cls=Host)
        req = self.req(["solo:m-a"])
        with contextlib.redirect_stderr(io.StringIO()):
            rows, _ = self.go(runner, req, "one")
        self.assertEqual(rows, [])
        Host.all_broken = False
        rows, out = self.go(runner, req, "two")
        self.assertEqual([(r.mode, r.n) for r in rows], [("solo:m-a", 4)])
        self.assertEqual(read_extra(out)["not_run"], {})
        self.assertEqual(read_extra(out)["settings"]["reused"], {})

    def test_council_runs_with_a_substitute_and_says_so(self):
        class Host(BrokenHost):
            broken = {"m-a"}
        runner, gateway, host, store, _ = self.make(host_cls=Host)
        with contextlib.redirect_stderr(io.StringIO()):
            rows, out = self.go(runner, self.req(["council_vote_only"], calibration_limit=0))
        self.assertEqual([(r.mode, r.n) for r in rows], [("council_vote_only", 4)])
        extra = read_extra(out)
        self.assertEqual(extra["not_run"], {})
        self.assertEqual(list(extra["load_failed"]), ["m-a"])
        if extra["degraded"]:
            self.assertEqual(extra["degraded"], {"council_vote_only": ["m-a"]})


class ProgressTests(_Case):
    def run_capture(self, req, **kw):
        runner, gateway, host, store, _ = self.make(**kw)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rows, out = self.go(runner, req)
        return rows, [ln for ln in err.getvalue().splitlines() if ln.startswith("bench: ")]

    def test_quiet_by_default(self):
        _, lines = self.run_capture(self.req(["solo:m-a", "council"]))
        self.assertEqual(lines, [])

    def test_one_line_per_finished_model(self):
        req = self.req(["solo:m-a", "solo:m-b", "council"], progress=True, calibration_limit=3)
        _, lines = self.run_capture(req)
        self.assertIn("start:", lines[0])
        self.assertIn("reasoning max", lines[0])
        cal = [ln for ln in lines if ln.startswith("bench: calibration: model ")]
        solo = [ln for ln in lines if ln.startswith("bench: solo: model ")]
        self.assertEqual(len(cal), len(SEATS))
        self.assertTrue(solo)
        for i, line in enumerate(cal, 1):
            self.assertIn(f"model {i}/{len(SEATS)} done", line)
            self.assertIn(f"calls {3 * i}/{3 * len(SEATS)}", line)
            for part in ("accuracy so far", "elapsed", "left in this pass ~"):
                self.assertIn(part, line)
        self.assertRegex(cal[-1], r"accuracy so far \d+\.\d%")
        self.assertRegex(cal[-1], r"elapsed \d+:\d\d:\d\d")
        self.assertTrue(any(ln.startswith("bench: finished council:") for ln in lines))

    def test_one_line_per_ten_council_tasks(self):
        req = BenchRunRequest(tasks_path=str(SAMPLE), modes=["council"], split="test", progress=True,
                              calibration_limit=0)
        rows, lines = self.run_capture(req)
        n = rows[0].n
        self.assertGreater(n, 10)
        council = [ln for ln in lines if ln.startswith("bench: council: ") and "tasks done" in ln]
        self.assertTrue(council)
        self.assertLessEqual(len(council), n // 10 + 1)
        self.assertIn(f"{n}/{n} tasks done", council[-1])
        for line in council:
            for part in ("accuracy so far", "elapsed", "left in the debate ~"):
                self.assertIn(part, line)

    def test_a_failed_load_is_said(self):
        class Host(BrokenHost):
            broken = {"m-a"}
        _, lines = self.run_capture(self.req(["solo:m-a"], progress=True), host_cls=Host)
        self.assertTrue(any("LOAD FAILED" in ln for ln in lines))
        self.assertTrue(any(ln.startswith("bench: NOT RUN solo:m-a") for ln in lines))


class CompareFilesTests(_Case):
    def test_three_files_are_written_and_read_back(self):
        from council.bench import compare_cli, solo_import
        runner, *_ = self.make()
        rows, out = self.go(runner, self.req(["solo:m-a", "solo:m-b", "council"]), name="bench-1")
        folder = self.root / "results"
        council = json.loads((folder / "bench-1_council.json").read_text(encoding="utf-8"))
        cats = json.loads((folder / "bench-1_categories.json").read_text(encoding="utf-8"))
        self.assertEqual(set(council), set(cats))
        self.assertEqual(len(council), 4)
        self.assertTrue(all(isinstance(v, bool) for v in council.values()))
        got, got_cats = compare_cli.load_council(folder / "bench-1_council.json")
        self.assertEqual(got, council)
        self.assertEqual(compare_cli.load_tags(folder / "bench-1_categories.json"), cats)
        solo = solo_import.load_solo(folder / "bench-1_solo.json")
        self.assertEqual({s.model_id for s in solo}, {"m-a", "m-b"})
        self.assertEqual(len(solo), 8)
        # the council file matches the council rows of results.jsonl
        lines = [json.loads(x) for x in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
        want = {r["id"]: r["correct"] is True for r in lines if r["mode"] == "council"}
        self.assertEqual(council, want)

    def test_no_solo_condition_no_solo_file(self):
        runner, *_ = self.make()
        self.go(runner, self.req(["council"]), name="bench-2")
        folder = self.root / "results"
        self.assertTrue((folder / "bench-2_council.json").is_file())
        self.assertFalse((folder / "bench-2_solo.json").exists())

    def test_no_council_condition_no_council_file(self):
        runner, *_ = self.make()
        self.go(runner, self.req(["solo:m-a"]), name="bench-3")
        folder = self.root / "results"
        self.assertFalse((folder / "bench-3_council.json").exists())
        self.assertTrue((folder / "bench-3_solo.json").is_file())


class CouncilSizeTests(_Case):
    def test_k_sets_the_number_of_seats(self):
        for k in (2, 4, 6):
            runner, *_ = self.make()
            req = self.req(["council"], limit=3)
            rows, out = asyncio.run(runner.run(req, self.root / f"k{k}", k=k)), self.root / f"k{k}"
            lines = [json.loads(x) for x in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(lines)
            for r in lines:
                self.assertEqual(len(r["lineup"]), k)
            report = json.loads((out / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["extra"]["settings"]["k"], k)

    def test_k_on_the_request_is_read(self):
        class Req:
            k = 3
        opts = read_options(Req(), Config().bench)
        self.assertEqual(opts.k, 3)
        self.assertIsNone(read_options(BenchRunRequest(), Config().bench).k)

    def test_bad_k_is_refused(self):
        for k in (1, 7, 0):
            with self.assertRaises(ValueError):
                read_options(BenchRunRequest(), Config().bench, k=k)

    def test_another_k_is_not_resumed(self):
        runner, *_ = self.make()
        req = self.req(["council"], limit=3)
        asyncio.run(runner.run(req, self.root / "a", k=2))
        out = self.root / "a"
        asyncio.run(runner.run(req, out, k=5))
        lines = [json.loads(x) for x in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(all(len(r["lineup"]) == 5 for r in lines))


class TolerantTasksTests(_Case):
    def run_file(self, name, text, modes=("solo:m-a",)):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        runner, *_ = self.make()
        req = BenchRunRequest(tasks_path=str(path), modes=list(modes), split="test", calibration_limit=0)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rows = asyncio.run(runner.run(req, self.root / "out"))
        return rows, err.getvalue()

    def test_csv_with_other_column_names(self):
        csv_text = "question,answer,subject\nWhat is 2+2?,4,math\nCapital of France?,Paris,geography\nNo answer here,,logic\n"
        rows, err = self.run_file("mine.csv", csv_text)
        self.assertEqual(rows[0].n, 3)
        self.assertIn("bench: tasks: t3: no answer", err)

    def test_json_list(self):
        data = json.dumps([{"id": "a", "prompt": "1+1?", "answer": "2"}, {"id": "b", "prompt": "2+2?", "answer": "4"}])
        rows, err = self.run_file("mine.json", data)
        self.assertEqual(rows[0].n, 2)
        self.assertEqual(err, "")

    def test_full_bench_lines_load_as_they_are(self):
        self.assertEqual(BenchRunner._load_tasks(SAMPLE), graders.load_tasks(SAMPLE))

    def test_empty_file_is_refused(self):
        with self.assertRaises(ValueError):
            self.run_file("empty.jsonl", "")


if __name__ == "__main__":
    unittest.main()
