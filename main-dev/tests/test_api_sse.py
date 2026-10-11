"""Tests for council/api/sse.py (spec 17)."""

import asyncio
import json
import unittest

from council.api.sse import format_sse, keepalive, parse_since, stream_frames
from council.core.events import EventBus
from council.core.schemas import Event


class FormatSseTests(unittest.TestCase):
    def test_frame_shape(self):
        ev = Event(type="run.created", seq=7, ts=1.5, run_id="r1", payload={"task": "hi"})
        frame = format_sse(ev)
        self.assertTrue(frame.endswith("\n\n"))
        lines = frame.rstrip("\n").split("\n")
        self.assertEqual(lines[0], "id: 7")
        self.assertEqual(lines[1], "event: run.created")
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[2].startswith("data: "))

    def test_data_is_full_envelope(self):
        ev = Event(type="turn.delta", seq=3, ts=2.0, run_id="r9", payload={"call_id": "c", "text": "a\nb"})
        frame = format_sse(ev)
        data_line = [l for l in frame.split("\n") if l.startswith("data: ")][0]
        body = json.loads(data_line[len("data: "):])
        self.assertEqual(body["type"], "turn.delta")
        self.assertEqual(body["seq"], 3)
        self.assertEqual(body["ts"], 2.0)
        self.assertEqual(body["run_id"], "r9")
        self.assertEqual(body["payload"], {"call_id": "c", "text": "a\nb"})

    def test_newlines_in_payload_stay_on_one_data_line(self):
        ev = Event(type="x", seq=1, payload={"t": "line1\nline2"})
        frame = format_sse(ev)
        self.assertEqual(sum(1 for l in frame.split("\n") if l.startswith("data: ")), 1)


class KeepaliveTests(unittest.TestCase):
    def test_keepalive(self):
        self.assertEqual(keepalive(), ": ping\n\n")


class ParseSinceTests(unittest.TestCase):
    def test_none_none(self):
        self.assertEqual(parse_since(None, None), 0)

    def test_query_only(self):
        self.assertEqual(parse_since("12", None), 12)

    def test_header_only(self):
        self.assertEqual(parse_since(None, "40"), 40)

    def test_larger_wins(self):
        self.assertEqual(parse_since("5", "9"), 9)
        self.assertEqual(parse_since("9", "5"), 9)

    def test_garbage_is_zero(self):
        self.assertEqual(parse_since("abc", None), 0)
        self.assertEqual(parse_since("", "x1"), 0)
        self.assertEqual(parse_since("1.5", "-3"), 0)

    def test_garbage_ignored_when_other_valid(self):
        self.assertEqual(parse_since("junk", "8"), 8)
        self.assertEqual(parse_since("4", "junk"), 4)

    def test_whitespace_tolerated(self):
        self.assertEqual(parse_since(" 7 ", None), 7)


class _Store:
    """The two calls EventBus makes."""

    def __init__(self):
        self.rows = []

    def append_event(self, run_id, type_, payload):
        ev = Event(type=type_, seq=len(self.rows) + 1, ts=0.0, run_id=run_id, payload=payload)
        self.rows.append(ev)
        return ev

    def events_since(self, run_id, since, limit=1000):
        return [e for e in self.rows if e.run_id == run_id and e.seq > since][:limit]


def _types(frames):
    return [f.split("\n")[1][len("event: "):] if f.startswith("id: ") else f for f in frames]


class StreamFramesTests(unittest.IsolatedAsyncioTestCase):
    TERMINAL = ("run.completed",)

    async def _take(self, gen):
        return [f async for f in gen]

    async def test_replay_then_live_with_deltas(self):
        store = _Store()
        bus = EventBus(store)
        bus.emit("run.created", "r1", {"task": "t"})
        bus.emit("round.started", "r1", {"round": 1})
        gen = stream_frames(bus.subscribe("r1", 1), terminal=self.TERMINAL, poll_s=0.01)
        task = asyncio.ensure_future(self._take(gen))
        await asyncio.sleep(0.05)
        bus.emit("turn.delta", "r1", {"call_id": "c", "text": "hi"})
        bus.emit("run.completed", "r1", {})
        bus.emit("turn.delta", "r1", {"call_id": "c", "text": "late"})
        frames = await asyncio.wait_for(task, 5)
        self.assertEqual(_types(frames), ["round.started", "turn.delta", "run.completed"])
        self.assertTrue(frames[1].startswith("id: 2\n"))  # a delta carries the last stored seq
        self.assertEqual(len(store.rows), 3)  # the delta was never stored
        self.assertEqual(bus._subs, {})  # unsubscribed

    async def test_finished_run_replays_and_closes(self):
        store = _Store()
        bus = EventBus(store)
        bus.emit("run.created", "r1", {"task": "t"})
        bus.emit("run.completed", "r1", {})
        frames = await asyncio.wait_for(
            self._take(stream_frames(bus.subscribe("r1", 0), terminal=self.TERMINAL)), 5)
        self.assertEqual(_types(frames), ["run.created", "run.completed"])
        frames = await asyncio.wait_for(
            self._take(stream_frames(bus.subscribe("r1", 2), terminal=self.TERMINAL,
                                     poll_s=0.01, should_stop=lambda: True)), 5)
        self.assertEqual(frames, [])
        self.assertEqual(bus._subs, {})

    async def test_keepalive_loses_no_event(self):
        store = _Store()
        bus = EventBus(store)
        gen = stream_frames(bus.subscribe("r1", 0), keepalive_s=0.03, poll_s=0.01,
                            terminal=self.TERMINAL)
        task = asyncio.ensure_future(self._take(gen))
        await asyncio.sleep(0.15)
        bus.emit("run.created", "r1", {"task": "t"})
        await asyncio.sleep(0.01)
        bus.emit("run.completed", "r1", {})
        frames = await asyncio.wait_for(task, 5)
        self.assertGreaterEqual(frames.count(keepalive()), 2)
        self.assertEqual([t for t in _types(frames) if t != keepalive()],
                         ["run.created", "run.completed"])

    async def test_async_should_stop_and_early_close(self):
        bus = EventBus(_Store())
        calls = []

        async def stop():
            calls.append(1)
            return len(calls) >= 3

        frames = await asyncio.wait_for(
            self._take(stream_frames(bus.subscribe("r1", 0), poll_s=0.01, should_stop=stop)), 5)
        self.assertEqual(frames, [])
        self.assertEqual(len(calls), 3)
        self.assertEqual(bus._subs, {})

        gen = stream_frames(bus.subscribe("r1", 0), poll_s=0.01)
        bus.emit("run.created", "r1", {"task": "t"})
        self.assertTrue((await gen.__anext__()).startswith("id: 1\n"))
        await gen.aclose()  # the client went away
        self.assertEqual(bus._subs, {})


if __name__ == "__main__":
    unittest.main()
