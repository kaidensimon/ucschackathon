import asyncio
import unittest

from council.chamber.executors import BatchExecutor, LiveExecutor, _parse_call_id
from council.chamber.deliberation import CHAIR_FLOOR_S, LATE_CHAIR_NOTE, Deliberation
from council.core.schemas import (
    CallResult,
    CallSpec,
    CheckRequest,
    Decision,
    EvidenceResult,
    LineupRecord,
    ModeConfig,
    SeatAssignment,
    TaskProfile,
)


class FakeDelib:
    """Asks for n calls, optionally one check, then is done when all came back."""

    def __init__(self, run_id, models, check=False):
        self.run_id = run_id
        self.models = models
        self.waiting = {}
        self.outbox = []
        self.checks_out = []
        self.events = [("round.started", {"round": 0})]
        self.done = False
        self.remaining = None
        self.deadline_calls = 0
        self.results = []
        self.evidence = []
        self.want_check = check
        for i, m in enumerate(models):
            spec = CallSpec(model_id=m, call_id=f"{run_id}:0:{i}")
            self.waiting[spec.call_id] = spec
            self.outbox.append(spec)

    def is_done(self):
        return self.done

    def set_remaining(self, s):
        self.remaining = s

    def pending_calls(self):
        out, self.outbox = self.outbox, []
        return out

    def pending_checks(self):
        out, self.checks_out = self.checks_out, []
        return out

    def take_events(self):
        out, self.events = self.events, []
        return out

    def on_result(self, r):
        if self.waiting.pop(r.call_id, None) is None:
            return []
        self.results.append(r)
        if not self.waiting:
            if self.want_check and not self.evidence:
                self.want_check = False
                c = CheckRequest(kind="python", spec="print(1)")
                c = c.model_copy()
                c.__dict__["check_id"] = "k1"  # not a field; getattr still sees it
                self.checks_out.append(c)
                return [("evidence.requested", {"check_id": "k1"})]
            self.done = True
        return [("ballot.cast", {"call_id": r.call_id})]

    def on_evidence(self, check_id, res):
        self.evidence.append((check_id, res))
        self.done = True
        return [("evidence.result", {"check_id": check_id})]

    def on_deadline(self):
        self.deadline_calls += 1
        self.waiting = {}
        self.done = True
        return [("round.completed", {})]

    def decision(self):
        return Decision(outcome="consensus", final_text="ok")


class FakeBus:
    def __init__(self):
        self.out = []

    async def emit(self, type_, run_id, payload):
        self.out.append((type_, run_id, payload))


class FakeGateway:
    def __init__(self, delay=0.0, slow_models=()):
        self.calls = []
        self.many = []
        self.delay = delay
        self.slow = set(slow_models)

    async def call(self, spec, seat_no=None, round=None):
        self.calls.append((spec.call_id, seat_no, round))
        if spec.model_id in self.slow:
            await asyncio.sleep(30)
        await asyncio.sleep(self.delay)
        return CallResult(call_id=spec.call_id, ok=True, model_id=spec.model_id, content="hi")

    async def call_many(self, specs):
        self.many.append([s.model_id for s in specs])
        return [CallResult(call_id=s.call_id, ok=True, model_id=s.model_id) for s in specs]


class FakeHost:
    def __init__(self):
        self.log = []

    async def load(self, model, profile):
        self.log.append(("load", model, profile))

    def unload(self, model):
        self.log.append(("unload", model))


class TestParse(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(_parse_call_id("run1:2:3"), (3, 2))
        self.assertEqual(_parse_call_id("run:x:1:2:3"), (3, 2))
        self.assertEqual(_parse_call_id("r:1:2#2"), (2, 1))
        self.assertEqual(_parse_call_id("r:clerk.cluster_options"), (None, None))
        self.assertEqual(_parse_call_id("abc"), (None, None))


class TestLive(unittest.IsolatedAsyncioTestCase):
    async def test_basic_run_and_seat_round(self):
        d = FakeDelib("r1", ["a", "b", "c"])
        gw, bus = FakeGateway(), FakeBus()
        dec = await LiveExecutor(gw, bus).run(d, "r1", 60)
        self.assertEqual(dec.outcome, "consensus")
        self.assertEqual(sorted(gw.calls), [("r1:0:0", 0, 0), ("r1:0:1", 1, 0), ("r1:0:2", 2, 0)])
        types = [t for t, _, _ in bus.out]
        self.assertEqual(types[0], "round.started")
        self.assertEqual(types.count("ballot.cast"), 3)
        self.assertTrue(all(r == "r1" for _, r, _ in bus.out))
        self.assertIsNotNone(d.remaining)

    async def test_no_runner_answers_not_run(self):
        d = FakeDelib("r2", ["a"], check=True)
        bus = FakeBus()
        await LiveExecutor(FakeGateway(), bus).run(d, "r2", 60)
        self.assertEqual(len(d.evidence), 1)
        cid, res = d.evidence[0]
        self.assertEqual(cid, "k1")
        self.assertFalse(res.ok)
        self.assertIn("not run", res.error)
        self.assertIn("evidence.result", [t for t, _, _ in bus.out])

    async def test_runner_used(self):
        async def runner(check):
            return EvidenceResult(kind=check.kind, ok=True, output="1")

        d = FakeDelib("r3", ["a"], check=True)
        await LiveExecutor(FakeGateway(), FakeBus(), evidence_runner=runner).run(d, "r3", 60)
        self.assertTrue(d.evidence[0][1].ok)

    async def test_deadline_once_and_cancel(self):
        t = [0.0]
        d = FakeDelib("r4", ["slow", "slow"])
        gw = FakeGateway(slow_models=["slow"])

        def clock():
            return t[0]

        ex = LiveExecutor(gw, FakeBus(), clock=clock)
        task = asyncio.ensure_future(ex.run(d, "r4", 0.05))
        await asyncio.sleep(0.01)
        t[0] = 1.0  # past the deadline; the wait times out on the real 0.05s
        dec = await asyncio.wait_for(task, 5)
        self.assertEqual(d.deadline_calls, 1)
        self.assertEqual(dec.outcome, "consensus")

    async def test_gateway_exception_becomes_failed_result(self):
        class Boom(FakeGateway):
            async def call(self, spec, seat_no=None, round=None):
                raise ValueError("x")

        d = FakeDelib("r5", ["a"])
        await LiveExecutor(Boom(), FakeBus()).run(d, "r5", 60)
        self.assertEqual(d.results[0].error, "server_error")
        self.assertFalse(d.results[0].ok)


class TestBatch(unittest.IsolatedAsyncioTestCase):
    async def test_model_major_largest_first(self):
        d1 = FakeDelib("a", ["m1", "m2", "m2"])
        d2 = FakeDelib("b", ["m2", "m3", "m1", "m2"])
        gw, host = FakeGateway(), FakeHost()
        decs = await BatchExecutor(gw, host).run_many([d1, d2])
        self.assertEqual(len(decs), 2)
        self.assertTrue(d1.done and d2.done)
        # m2 has 4 calls, m1 has 2, m3 has 1
        self.assertEqual([sorted(set(g)) for g in gw.many], [["m2"], ["m1"], ["m3"]])
        self.assertEqual([len(g) for g in gw.many], [4, 2, 1])
        loads = [e for e in host.log if e[0] == "load"]
        self.assertEqual([e[1] for e in loads], ["m2", "m1", "m3"])
        self.assertTrue(all(e[2] == "batch" for e in loads))
        self.assertEqual(len([e for e in host.log if e[0] == "unload"]), 3)

    async def test_no_host_and_checks(self):
        d = FakeDelib("c", ["m1"], check=True)
        decs = await BatchExecutor(FakeGateway()).run_many([d])
        self.assertEqual(decs[0].outcome, "consensus")
        self.assertFalse(d.evidence[0][1].ok)


class ReserveDelib(FakeDelib):
    """A FakeDelib that keeps a Chair reserve and is told the time left at the deadline."""

    def __init__(self, *a, reserve=40.0, **kw):
        super().__init__(*a, **kw)
        self.reserve = reserve
        self.told = []

    def chair_reserve_s(self):
        return self.reserve

    def on_deadline(self, remaining_s=None):
        self.told.append(remaining_s)
        return super().on_deadline()


class ScriptGateway:
    """Seats 0 and 1 answer round 0 at once. Seat 2 moves the clock, then hangs. The Chair answers."""

    def __init__(self, clock_box, jump_to, chair_ok=True):
        self.t = clock_box
        self.jump_to = jump_to
        self.chair_ok = chair_ok
        self.specs = []

    async def call(self, spec, seat_no=None, round=None):
        self.specs.append(spec)
        if spec.purpose == "chair":
            if not self.chair_ok:
                return CallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id, error="timeout")
            return CallResult(
                call_id=spec.call_id, ok=True, model_id=spec.model_id,
                parsed={"option_id": "o1", "final_text": "The Chair decides.", "confidence": 0.8},
            )
        seat = spec.meta["seat_no"]
        if seat == 2:
            self.t[0] = self.jump_to
            await asyncio.sleep(30)
        key = "AB"[seat]
        return CallResult(
            call_id=spec.call_id, ok=True, model_id=spec.model_id,
            parsed={"answer": f"It is {key}.", "answer_key": key, "summary": key, "confidence": 0.9},
        )


def real_delib(deadline_s=1000.0):
    seats = [SeatAssignment(seat_no=i, model_id=f"m{i}", q=0.5) for i in range(3)]
    mode = ModeConfig(name="standard", k=3, rounds=["r0"], deadline_s=deadline_s, reasoning="off")
    return Deliberation(
        "run1", "A or B?", TaskProfile(), LineupRecord(seats=seats, k=3), mode, answer_type="mcq"
    )


def jump_clock(later):
    """0 on the first reading (the start of the run), `later` on every reading after it."""
    seen = []

    def clock():
        seen.append(1)
        return 0.0 if len(seen) == 1 else later

    return clock


class TestChairReserve(unittest.IsolatedAsyncioTestCase):
    async def test_debate_stops_when_only_the_reserve_is_left(self):
        t = [0.0]
        d = ReserveDelib("r6", ["slow", "slow"], reserve=40.0)
        ex = LiveExecutor(FakeGateway(slow_models=["slow"]), FakeBus(), clock=lambda: t[0])
        task = asyncio.ensure_future(ex.run(d, "r6", 100.0))
        await asyncio.sleep(0.01)
        self.assertEqual(d.told, [])
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        # 39 s left of 100, the reserve is 40: the debate is over although the deadline is not
        d = ReserveDelib("r7", ["slow", "slow"], reserve=40.0)
        ex = LiveExecutor(FakeGateway(slow_models=["slow"]), FakeBus(), clock=jump_clock(61.0))
        await asyncio.wait_for(ex.run(d, "r7", 100.0), 5)
        self.assertEqual(d.told, [39.0])
        self.assertEqual(d.deadline_calls, 1)

    async def test_engine_without_a_reserve_keeps_the_whole_deadline(self):
        d = FakeDelib("r8", ["a"])
        await asyncio.wait_for(LiveExecutor(FakeGateway(), FakeBus(), clock=jump_clock(61.0)).run(d, "r8", 100.0), 5)
        self.assertEqual(d.deadline_calls, 0)
        self.assertEqual(d.remaining, 39.0)

    async def test_chair_gets_the_time_that_was_kept_for_it(self):
        t = [0.0]
        d = real_delib()  # Chair alone, reasoning off, speed unknown: 150 s reserve
        self.assertAlmostEqual(d.chair_reserve_s(), 150.0)
        gw = ScriptGateway(t, jump_to=900.0)  # 100 s left: inside the reserve
        dec = await asyncio.wait_for(LiveExecutor(gw, FakeBus(), clock=lambda: t[0]).run(d, "run1", 1000.0), 5)
        self.assertEqual(dec.outcome, "chair")
        self.assertEqual(dec.final_text, "The Chair decides.")
        self.assertEqual(dec.notes, [])
        chair = [s for s in gw.specs if s.purpose == "chair"]
        self.assertEqual([s.timeout_s for s in chair], [100.0])
        self.assertTrue(all(s.timeout_s > 120.0 for s in gw.specs if s.purpose == "seat.r0"))

    async def test_chair_after_the_deadline_still_decides_with_a_note(self):
        t = [0.0]
        d = real_delib()
        gw = ScriptGateway(t, jump_to=5000.0)  # far past the deadline
        dec = await asyncio.wait_for(LiveExecutor(gw, FakeBus(), clock=lambda: t[0]).run(d, "run1", 1000.0), 5)
        self.assertEqual(dec.outcome, "chair")
        self.assertEqual(dec.notes, [LATE_CHAIR_NOTE])
        chair = [s for s in gw.specs if s.purpose == "chair"]
        self.assertEqual([s.timeout_s for s in chair], [CHAIR_FLOOR_S])

    async def test_deadlock_only_when_the_chair_call_fails(self):
        t = [0.0]
        d = real_delib()
        gw = ScriptGateway(t, jump_to=5000.0, chair_ok=False)
        dec = await asyncio.wait_for(LiveExecutor(gw, FakeBus(), clock=lambda: t[0]).run(d, "run1", 1000.0), 5)
        self.assertEqual(dec.outcome, "deadlock")
        self.assertEqual(len([s for s in gw.specs if s.purpose == "chair"]), 1)


if __name__ == "__main__":
    unittest.main()
