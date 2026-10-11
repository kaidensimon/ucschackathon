import asyncio
import unittest

from council.gateway.governor import Governor


async def settle():
    for _ in range(5):
        await asyncio.sleep(0)


class Holder:
    """Acquires, records, then holds until released by event."""

    def __init__(self, gov, model, priority="interactive", log=None, name=None):
        self.gov, self.model, self.priority = gov, model, priority
        self.log, self.name = log, name or model
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.task = asyncio.ensure_future(self._run())

    async def _run(self):
        async with self.gov.acquire(self.model, self.priority):
            if self.log is not None:
                self.log.append(self.name)
            self.entered.set()
            await self.release.wait()

    async def finish(self):
        self.release.set()
        await self.task


class GovernorTests(unittest.IsolatedAsyncioTestCase):
    async def test_per_model_slots(self):
        g = Governor({"a": 2}, max_concurrent_models=5)
        h = [Holder(g, "a") for _ in range(3)]
        await settle()
        self.assertEqual([x.entered.is_set() for x in h], [True, True, False])
        self.assertEqual(g.stats()["in_flight"], {"a": 2})
        self.assertEqual(g.stats()["queue_depth"], 1)
        await h[0].finish()
        await settle()
        self.assertTrue(h[2].entered.is_set())
        await h[1].finish()
        await h[2].finish()
        self.assertEqual(g.stats(), {"in_flight": {}, "queue_depth": 0, "active_models": []})

    async def test_default_slots(self):
        g = Governor({}, max_concurrent_models=5, default_slots=1)
        h1, h2 = Holder(g, "x"), Holder(g, "x")
        await settle()
        self.assertTrue(h1.entered.is_set())
        self.assertFalse(h2.entered.is_set())
        await h1.finish()
        await settle()
        self.assertTrue(h2.entered.is_set())
        await h2.finish()

    async def test_distinct_model_cap(self):
        g = Governor({"a": 3, "b": 1, "c": 1}, max_concurrent_models=2)
        a1, b1, c1 = Holder(g, "a"), Holder(g, "b"), Holder(g, "c")
        await settle()
        self.assertTrue(a1.entered.is_set() and b1.entered.is_set())
        self.assertFalse(c1.entered.is_set())
        # Already-active model does not count again.
        a2 = Holder(g, "a")
        await settle()
        self.assertTrue(a2.entered.is_set())
        self.assertEqual(sorted(g.stats()["active_models"]), ["a", "b"])
        await b1.finish()
        await settle()
        self.assertTrue(c1.entered.is_set())  # b left, room for c
        self.assertEqual(sorted(g.stats()["active_models"]), ["a", "c"])
        await a1.finish()
        await a2.finish()
        await c1.finish()

    async def test_interactive_before_batch_fifo(self):
        g = Governor({"a": 1}, max_concurrent_models=1)
        log = []
        first = Holder(g, "a", log=log, name="first")
        await settle()
        b1 = Holder(g, "a", "batch", log, "b1")
        await settle()
        b2 = Holder(g, "a", "batch", log, "b2")
        await settle()
        i1 = Holder(g, "a", "interactive", log, "i1")
        await settle()
        i2 = Holder(g, "a", "interactive", log, "i2")
        await settle()
        for h in (first, i1, i2, b1, b2):
            await h.finish()
            await settle()
        self.assertEqual(log, ["first", "i1", "i2", "b1", "b2"])

    async def test_blocked_new_model_does_not_starve_active(self):
        g = Governor({"a": 2, "b": 1}, max_concurrent_models=1)
        a1 = Holder(g, "a")
        await settle()
        b1 = Holder(g, "b")  # waits: cap is 1
        await settle()
        a2 = Holder(g, "a")  # queued after b1 but a is active with a free slot
        await settle()
        self.assertFalse(b1.entered.is_set())
        self.assertTrue(a2.entered.is_set())
        await a1.finish()
        await a2.finish()
        await settle()
        self.assertTrue(b1.entered.is_set())
        await b1.finish()

    async def test_cancel_waiting_and_release_on_error(self):
        g = Governor({"a": 1}, max_concurrent_models=1)
        h1 = Holder(g, "a")
        h2 = Holder(g, "a")
        await settle()
        h2.task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await h2.task
        self.assertEqual(g.stats()["queue_depth"], 0)
        await h1.finish()
        self.assertEqual(g.stats()["in_flight"], {})

        g2 = Governor({"a": 1}, max_concurrent_models=1)
        with self.assertRaises(ValueError):
            async with g2.acquire("a"):
                raise ValueError("boom")
        self.assertEqual(g2.stats()["in_flight"], {})

    async def test_set_slots_wakes_waiters(self):
        g = Governor({"a": 1}, max_concurrent_models=1)
        h1, h2 = Holder(g, "a"), Holder(g, "a")
        await settle()
        self.assertFalse(h2.entered.is_set())
        g.set_slots("a", 2)
        await settle()
        self.assertTrue(h2.entered.is_set())
        await h1.finish()
        await h2.finish()


if __name__ == "__main__":
    unittest.main()
