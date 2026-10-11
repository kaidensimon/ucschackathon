import asyncio
import unittest

from council.core import event_types as et
from council.core.events import EventBus
from council.core.schemas import Event


class FakeStore:
    def __init__(self):
        self.events = []
        self.seq = 0

    def append_event(self, run_id, type, payload):
        self.seq += 1
        ev = Event(type=type, seq=self.seq, ts=1.0, run_id=run_id, payload=payload)
        self.events.append(ev)
        return ev

    def events_since(self, run_id, since, limit=5000):
        return [e for e in self.events if e.run_id == run_id and e.seq > since][:limit]


async def collect(agen, out):
    async for ev in agen:
        out.append(ev)


class EventBusTests(unittest.IsolatedAsyncioTestCase):
    async def test_emit_persists_and_validates(self):
        store = FakeStore()
        bus = EventBus(store)
        ev = bus.emit(et.RUN_CREATED, "r1", {"task": "hi"})
        self.assertEqual(ev.seq, 1)
        self.assertEqual(store.events[0].payload["task"], "hi")
        with self.assertRaises(ValueError):
            bus.emit("nope.nope", "r1")
        with self.assertRaises(ValueError):
            bus.emit(et.TURN_STARTED, "r1", {})  # call_id required
        self.assertEqual(len(store.events), 1)

    async def test_ephemeral_not_stored_uses_last_seq(self):
        store = FakeStore()
        bus = EventBus(store)
        bus.emit(et.RUN_CREATED, "r1")
        d = bus.emit(et.TURN_DELTA, "r1", {"call_id": "c", "text": "x"})
        self.assertEqual(d.seq, 1)
        self.assertEqual(len(store.events), 1)
        self.assertEqual(d.type, et.TURN_DELTA)

    async def test_listener(self):
        bus = EventBus(FakeStore())
        seen = []
        remove = bus.add_listener(seen.append)
        bus.add_listener(lambda e: 1 / 0)  # bad tap must not break emit
        bus.emit(et.RUN_CREATED, "r1")
        remove()
        bus.emit(et.RUN_STATE_CHANGED, "r1")
        self.assertEqual([e.type for e in seen], [et.RUN_CREATED])

    async def test_replay_then_live_ends_on_terminal(self):
        store = FakeStore()
        bus = EventBus(store)
        bus.emit(et.RUN_CREATED, "r1")
        bus.emit(et.RUN_STATE_CHANGED, "r1")
        bus.emit(et.RUN_CREATED, "other")
        out = []
        task = asyncio.ensure_future(collect(bus.subscribe("r1"), out))
        await asyncio.sleep(0.01)
        bus.emit(et.TURN_DELTA, "r1", {"call_id": "c", "text": "a"})
        bus.emit(et.BRIEF_READY, "r1")
        bus.emit(et.RUN_COMPLETED, "r1")
        await asyncio.wait_for(task, 1)
        self.assertEqual(
            [e.type for e in out],
            [et.RUN_CREATED, et.RUN_STATE_CHANGED, et.TURN_DELTA, et.BRIEF_READY, et.RUN_COMPLETED],
        )
        self.assertEqual(bus._subs, {})

    async def test_since_skips_old(self):
        store = FakeStore()
        bus = EventBus(store)
        for _ in range(3):
            bus.emit(et.RUN_STATE_CHANGED, "r1")
        bus.emit(et.RUN_FAILED, "r1")
        out = []
        await asyncio.wait_for(collect(bus.subscribe("r1", since=2), out), 1)
        self.assertEqual([e.seq for e in out], [3, 4])

    async def test_no_gap_no_dup_when_emit_races_replay(self):
        store = FakeStore()
        bus = EventBus(store)
        bus.emit(et.RUN_CREATED, "r1")
        orig = store.events_since

        def racing(run_id, since, limit=5000):
            res = orig(run_id, since, limit)
            # event lands after the snapshot was read but while subscribed
            if not getattr(racing, "done", False):
                racing.done = True
                bus.emit(et.RUN_STATE_CHANGED, "r1")
            return res

        store.events_since = racing
        out = []
        task = asyncio.ensure_future(collect(bus.subscribe("r1"), out))
        await asyncio.sleep(0.01)
        bus.emit(et.RUN_COMPLETED, "r1")
        await asyncio.wait_for(task, 1)
        self.assertEqual([e.seq for e in out], [1, 2, 3])

    async def test_replay_stops_at_stored_terminal(self):
        store = FakeStore()
        bus = EventBus(store)
        bus.emit(et.RUN_CANCELLED, "r1")
        out = []
        await asyncio.wait_for(collect(bus.subscribe("r1"), out), 1)
        self.assertEqual(len(out), 1)

    async def test_two_subscribers(self):
        bus = EventBus(FakeStore())
        a, b = [], []
        ta = asyncio.ensure_future(collect(bus.subscribe("r1"), a))
        tb = asyncio.ensure_future(collect(bus.subscribe("r1"), b))
        await asyncio.sleep(0.01)
        bus.emit(et.RUN_CREATED, "r1")
        bus.emit(et.RUN_COMPLETED, "r1")
        await asyncio.wait_for(asyncio.gather(ta, tb), 1)
        self.assertEqual(len(a), 2)
        self.assertEqual(len(b), 2)


if __name__ == "__main__":
    unittest.main()
