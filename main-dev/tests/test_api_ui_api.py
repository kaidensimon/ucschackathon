import asyncio
import json
import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from council.api.controller import RunController
from council.api.server import create_app
from council.api.ui_api import DEFAULT_SEATS, RunTranslator, debate_frames, seat_count, seat_models
from council.api.ui_bridge import UiBridge
from council.core import event_types as ET
from council.core.schemas import RunRequest

MESSAGE_KEYS = {"id", "chatId", "role", "text", "status", "createdAt", "model",
                "tokensPerSecond", "answerTokens", "error", "runId"}


def parse_sse(text):
    out = []
    for frame in text.split("\n\n"):
        data = [ln[6:] for ln in frame.split("\n") if ln.startswith("data: ")]
        if data:
            out.append(json.loads(data[0]))
    return out


def stream(c, path):
    with c.stream("GET", path) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    assert "event:" not in body
    return parse_sse(body)


class UiApiTest(unittest.TestCase):
    def test_flow(self):
        ctrl = RunController.build_mock(speed=500.0)
        with TestClient(create_app(ctrl)) as c:
            h = c.get("/ui/health").json()
            self.assertTrue(h["ok"])
            self.assertEqual(h["model"]["state"], "ready")
            active = [m for m in ctrl.registry if m.status == "active"]
            self.assertEqual(h["model"]["name"], f"Council ({len(active)} models)")
            self.assertEqual(set(h["model"]), {"state", "address", "name", "contextTokens", "detail", "checkedAt"})
            self.assertEqual(len(h["models"]), len(ctrl.registry))
            self.assertEqual(set(h["models"][0]), {"id", "name", "status", "seat"})
            usable = len(seat_models(ctrl.registry))
            self.assertEqual(h["seats"], {"default": min(3, usable), "min": 2, "max": min(6, usable), "usable": usable})

            s = c.get("/ui/settings").json()
            self.assertIn("systemPrompt", s)
            s = c.patch("/ui/settings", json={"maxAnswerTokens": 512}).json()
            self.assertEqual(s["maxAnswerTokens"], 512)

            # 404 shape
            for r in (c.get("/ui/chats/nope"), c.post("/ui/chats/nope/messages", json={"text": "x"}),
                      c.get("/ui/runs/nope/events"), c.get("/ui/runs/nope/debate"),
                      c.post("/ui/runs/nope/stop"), c.delete("/ui/chats/nope")):
                self.assertEqual(r.status_code, 404)
                self.assertEqual(r.json()["code"], "not_found")
                self.assertTrue(r.json()["message"])

            chat = c.post("/ui/chats", json={}).json()
            cid = chat["id"]
            self.assertEqual(chat["messages"], [])
            self.assertEqual(c.post(f"/ui/chats/{cid}/messages", json={"text": " "}).status_code, 422)
            bad = c.post(f"/ui/chats/{cid}/messages", json={"text": "x", "seats": 9})
            self.assertEqual((bad.status_code, bad.json()["code"]), (422, "bad_request"))
            self.assertEqual(c.post(f"/ui/chats/{cid}/regenerate").status_code, 409)

            # send -> RunStarted
            r = c.post(f"/ui/chats/{cid}/messages", json={"text": "Which database for a zebra shop?", "seats": 3})
            self.assertEqual(r.status_code, 200, r.text)
            rs = r.json()
            self.assertEqual(set(rs), {"runId", "userMessage", "assistantMessage", "chat"})
            rid = rs["runId"]
            self.assertEqual(set(rs["userMessage"]), MESSAGE_KEYS)
            self.assertEqual(set(rs["assistantMessage"]), MESSAGE_KEYS)
            self.assertEqual(rs["userMessage"]["role"], "user")
            self.assertEqual(rs["assistantMessage"]["status"], "writing")
            self.assertEqual(rs["assistantMessage"]["runId"], rid)
            self.assertEqual(rs["chat"]["id"], cid)
            self.assertIn("preview", rs["chat"])
            self.assertIsNotNone(ctrl.store.get_run(rid))
            self.assertEqual(ctrl.store.kv_get("ui_runs", rid)["chatId"], cid)

            evs = stream(c, f"/ui/runs/{rid}/events")
            self.assertEqual(evs[0]["type"], "run.started")
            self.assertEqual(evs[0]["messageId"], rs["assistantMessage"]["id"])
            self.assertEqual(evs[1]["type"], "run.status")
            self.assertEqual(evs[1]["status"], "waiting")
            self.assertEqual([e["seq"] for e in evs], list(range(1, len(evs) + 1)))
            self.assertEqual(evs[-1]["type"], "run.done", evs[-1])
            self.assertTrue(all(e["runId"] == rid for e in evs))
            self.assertTrue(any(e["type"] == "run.status" and e["status"] == "reading" for e in evs))
            for e in evs:
                if e["type"] == "run.status" and e["progress"] is not None:
                    self.assertTrue(0 <= e["progress"] <= 1)
            text = "".join(e["text"] for e in evs if e["type"] == "delta")
            done = evs[-1]["message"]
            self.assertTrue(text)
            self.assertEqual(done["text"], text)
            self.assertEqual(done["status"], "complete")
            self.assertTrue(done["model"].startswith("Council"))

            got = c.get(f"/ui/chats/{cid}").json()
            self.assertEqual(len(got["messages"]), 2)
            self.assertEqual(got["messages"][1]["status"], "complete")
            self.assertEqual(got["messages"][1]["text"], text)

            # replay of a finished run: the same sequence
            again = stream(c, f"/ui/runs/{rid}/events")
            self.assertEqual([e["type"] for e in again], [e["type"] for e in evs])

            # debate stream of a finished run: whole, ends with the answer
            self.assertEqual(ctrl.store.kv_get("ui_runs", rid)["seats"], 3)
            deb = stream(c, f"/ui/runs/{rid}/debate")
            self.assertTrue(all("type" in e and "seq" in e for e in deb))
            self.assertEqual([e["seq"] for e in deb], list(range(1, len(deb) + 1)))
            self.assertEqual(deb[0]["type"], "debate.created")
            self.assertEqual(len(deb[0]["seats"]), 3)
            self.assertEqual([e["type"] for e in deb[-2:]], ["answer.released", "phase.changed"])
            self.assertEqual(len([e for e in deb if e["type"] == "answer.released"]), 1)
            seat_ids = {seat["id"] for seat in deb[0]["seats"]}
            first_turn = next(i for i, e in enumerate(deb) if e["type"] == "turn.started")
            status = {e["seatId"]: e["status"] for e in deb[:first_turn] if e["type"] == "seat.status"}
            self.assertEqual(set(status), seat_ids)
            self.assertTrue(all(v in ("ready", "failed", "dropped") for v in status.values()), status)
            self.assertEqual([e["type"] for e in stream(c, f"/ui/runs/{rid}/debate")], [e["type"] for e in deb])

            # stop
            r2 = c.post(f"/ui/chats/{cid}/messages", json={"text": "And the cache?"}).json()
            # no "seats" in the request: the UI's default, not the engine's six
            self.assertEqual(ctrl.store.kv_get("ui_runs", r2["runId"])["seats"], DEFAULT_SEATS)
            self.assertEqual(c.post(f"/ui/runs/{r2['runId']}/stop").status_code, 204)
            deb2 = stream(c, f"/ui/runs/{r2['runId']}/debate")  # a stopped run is closed too
            released = [e for e in deb2 if e["type"] == "answer.released"]
            self.assertEqual([e["outcome"] for e in released], ["stopped"])
            created = [e for e in deb2 if e["type"] == "debate.created"]
            self.assertTrue(all(len(e["seats"]) == DEFAULT_SEATS for e in created))
            evs2 = stream(c, f"/ui/runs/{r2['runId']}/events")
            self.assertEqual(evs2[-1]["type"], "run.error")
            self.assertEqual(evs2[-1]["message"]["status"], "stopped")
            got = c.get(f"/ui/chats/{cid}").json()
            self.assertEqual(got["messages"][-1]["status"], "stopped")
            self.assertEqual(len(got["messages"]), 4)

            # regenerate
            r3 = c.post(f"/ui/chats/{cid}/regenerate")
            self.assertEqual(r3.status_code, 200, r3.text)
            r3 = r3.json()
            self.assertIsNone(r3["userMessage"])
            self.assertEqual(r3["assistantMessage"]["status"], "writing")
            self.assertIn("And the cache?", ctrl.store.get_run(r3["runId"])["task"])
            self.assertIn("Conversation so far", ctrl.store.get_run(r3["runId"])["task"])
            evs3 = stream(c, f"/ui/runs/{r3['runId']}/events")
            self.assertEqual(evs3[-1]["type"], "run.done")
            self.assertEqual(evs3[-1]["message"]["model"], f"Council of {DEFAULT_SEATS}")

            # "ask again" keeps the seats of the run it replaces
            two = c.post("/ui/chats", json={}).json()["id"]
            a = c.post(f"/ui/chats/{two}/messages", json={"text": "Tabs or spaces?", "seats": 2}).json()
            self.assertEqual(stream(c, f"/ui/runs/{a['runId']}/events")[-1]["type"], "run.done")
            b = c.post(f"/ui/chats/{two}/regenerate").json()
            self.assertEqual(ctrl.store.kv_get("ui_runs", b["runId"])["seats"], 2)
            deb = stream(c, f"/ui/runs/{b['runId']}/debate")
            self.assertEqual(len(deb[0]["seats"]), 2)
            self.assertEqual(deb[-2]["type"], "answer.released")
            self.assertEqual(c.delete(f"/ui/chats/{two}").status_code, 204)
            got = c.get(f"/ui/chats/{cid}").json()
            self.assertEqual(len(got["messages"]), 4)
            self.assertEqual(got["messages"][-1]["status"], "complete")

            # export
            ex = c.get(f"/ui/chats/{cid}/export", params={"format": "markdown"}).json()
            self.assertEqual(set(ex), {"filename", "mime", "text"})
            self.assertIn("zebra", ex["text"])
            ej = c.get(f"/ui/chats/{cid}/export", params={"format": "json"}).json()
            self.assertEqual(json.loads(ej["text"])["id"], cid)
            self.assertEqual(c.get(f"/ui/chats/{cid}/export", params={"format": "pdf"}).status_code, 422)

            # search, update, delete
            other = c.post("/ui/chats", json={"title": "Other"}).json()
            self.assertEqual(len(c.get("/ui/chats").json()), 2)
            hits = c.get("/ui/chats", params={"query": "zebra"}).json()
            self.assertEqual([x["id"] for x in hits], [cid])
            self.assertIn("zebra", hits[0]["match"])
            up = c.patch(f"/ui/chats/{cid}", json={"title": "Shop", "pinned": True}).json()
            self.assertEqual((up["title"], up["pinned"]), ("Shop", True))
            self.assertEqual(c.delete(f"/ui/chats/{other['id']}").status_code, 204)
            self.assertEqual(len(c.get("/ui/chats").json()), 1)

            # CORS
            pre = c.options("/ui/health", headers={"Origin": "null", "Access-Control-Request-Method": "GET"})
            self.assertEqual(pre.headers.get("access-control-allow-origin"), "*")


class SeatCountTest(unittest.TestCase):
    def test_seat_count(self):
        self.assertEqual(seat_count(None, 8), 3)  # nothing asked: the UI default
        self.assertEqual(seat_count(6, 8), 6)
        self.assertEqual(seat_count(9, 8), 6)
        self.assertEqual(seat_count(1, 8), 2)
        self.assertEqual(seat_count(6, 4), 4)  # never more than the models that can sit
        self.assertEqual(seat_count(None, 2), 2)
        self.assertEqual(seat_count(5, 1), 2)  # the engine reports what is missing
        self.assertEqual(seat_count(5, 0), 5)  # registry unknown: as asked
        self.assertEqual(seat_count(True, 8), 3)
        self.assertEqual(seat_count("4", 8), 3)

    def test_seat_models(self):
        m = lambda status, roles: SimpleNamespace(status=status, roles=roles)
        reg = [m("active", ["seat"]), m("active", ["clerk"]), m("failed", ["seat"]), m("quarantined", ["seat"]),
               m("active", ["seat", "worker"])]
        self.assertEqual(len(seat_models(reg)), 2)
        self.assertEqual(len(seat_models([m("active", []), m("active", []), m("failed", [])])), 2)  # no roles used
        self.assertEqual(seat_models(None), [])


class _Reader:
    """A request that never goes away."""

    async def is_disconnected(self) -> bool:
        return False


def _ui(frames: list) -> list:
    return [json.loads(f.split("\ndata: ", 1)[1]) for f in frames if f.startswith("id:")]


class DebateStreamTest(unittest.IsolatedAsyncioTestCase):
    SPEED = 500.0

    async def asyncSetUp(self):
        self.ctrl = RunController.build_mock(speed=self.SPEED)

    async def asyncTearDown(self):
        await self.ctrl.shutdown()

    def replayed(self, run_id: str) -> list:
        bridge = UiBridge(run_id)
        out = []
        for event in self.ctrl.store.events_since(run_id, 0):
            out.extend(bridge.feed(event.model_dump(mode="json")))
        return out

    async def test_reader_that_comes_mid_run_gets_the_backlog_then_the_rest(self):
        await self.ctrl.shutdown()
        ctrl = self.ctrl = RunController.build_mock(speed=80.0)  # slow enough to come in mid-run
        run_id = await ctrl.start(RunRequest(task="Queue or lock?", deliverable="answer",
                                             options={"auto_delegate": True, "auto_input": True, "k": 3}))
        for _ in range(400):  # until the debate is under way
            if any(e.type == "round.started" for e in ctrl.store.events_since(run_id, 0)):
                break
            await asyncio.sleep(0.01)
        self.assertTrue(ctrl.is_active(run_id), "the run ended before the reader came; lower the speed")
        backlog = len(ctrl.store.events_since(run_id, 0))
        self.assertGreater(backlog, 5)
        frames = []

        async def read():
            async for frame in debate_frames(ctrl, run_id, _Reader()):
                frames.append(frame)

        await asyncio.wait_for(read(), timeout=60)
        self.assertFalse(ctrl.is_active(run_id))  # the stream stayed open until the run ended
        self.assertGreater(len(ctrl.store.events_since(run_id, 0)), backlog)  # and events came live
        got = _ui(frames)
        self.assertEqual([e["seq"] for e in got], list(range(1, len(got) + 1)))  # no duplicate, no gap
        self.assertEqual(got[0]["type"], "debate.created")
        self.assertEqual([e["type"] for e in got[-2:]], ["answer.released", "phase.changed"])
        # exactly what a reader of the finished run gets, plus the text pieces that are only sent
        # live (turn.delta is not stored); every engine event went through the bridge once
        def steady(events):
            return [{k: v for k, v in e.items() if k != "seq"} for e in events if e["type"] != "turn.delta"]

        self.assertEqual(steady(got), steady(self.replayed(run_id)))
        self.assertEqual(len([e for e in got if e["type"] == "answer.released"]), 1)
        started = [e["turnId"] for e in got if e["type"] == "turn.started"]
        self.assertEqual(len(started), len(set(started)))

    async def test_run_that_died_without_an_end_is_closed_as_stopped(self):
        ctrl = self.ctrl
        run_id = await ctrl.start(RunRequest(task="Queue or lock?", deliverable="answer",
                                             options={"auto_delegate": True, "auto_input": True, "k": 3}))
        await ctrl.wait(run_id, timeout=60)
        whole = self.replayed(run_id)

        class Cut:  # the store of a server that was killed mid-run: the last events are missing
            def events_since(_, rid, since, limit=5000):
                events = ctrl.store.events_since(rid, since, limit=limit)
                return [e for e in events if e.type not in ET.TERMINAL_EVENTS and e.type != "decision.final"]

        async def subscribe(rid, since=0):
            for event in Cut().events_since(rid, since):
                yield event
            await asyncio.sleep(3600)

        dead = SimpleNamespace(store=Cut(), bus=SimpleNamespace(subscribe=subscribe), is_active=lambda rid: False)
        frames = [f async for f in debate_frames(dead, run_id, _Reader())]
        got = _ui(frames)
        self.assertLess(len(got), len(whole) + 2)
        self.assertEqual([e["seq"] for e in got], list(range(1, len(got) + 1)))
        self.assertEqual([e["type"] for e in got[-2:]], ["answer.released", "phase.changed"])
        self.assertEqual(got[-2]["outcome"], "stopped")

    async def test_end_events_the_bus_did_not_hand_out_are_read_from_the_store(self):
        ctrl = self.ctrl
        run_id = await ctrl.start(RunRequest(task="Queue or lock?", deliverable="answer",
                                             options={"auto_delegate": True, "auto_input": True, "k": 3}))
        await ctrl.wait(run_id, timeout=60)
        events = ctrl.store.events_since(run_id, 0)

        async def subscribe(rid, since=0):  # stops handing out half way, as if the run ended between reads
            for event in events[: len(events) // 2]:
                yield event
            await asyncio.sleep(3600)

        late = SimpleNamespace(store=ctrl.store, bus=SimpleNamespace(subscribe=subscribe), is_active=lambda rid: False)
        got = _ui([f async for f in debate_frames(late, run_id, _Reader())])
        self.assertEqual(got, self.replayed(run_id))
        self.assertEqual(got[-2]["type"], "answer.released")
        self.assertNotEqual(got[-2]["outcome"], "stopped")


class TranslatorTest(unittest.TestCase):
    def test_translate(self):
        t = RunTranslator("r1", "m1")
        out = t.start()
        self.assertEqual([e["type"] for e in out], ["run.started", "run.status"])
        self.assertIsNone(out[1]["progress"])
        t.feed({"type": ET.ROUTER_LINEUP_SELECTED, "payload": {"lineup": {"seats": [{}, {}]}}})
        t.feed({"type": ET.MODEL_LOADING, "payload": {"model_id": "a"}})
        got = t.feed({"type": ET.MODEL_LOADED, "payload": {"model_id": "a"}})
        self.assertEqual((got[0]["status"], got[0]["progress"]), ("waiting", 0.5))
        t.feed({"type": ET.EFFORT_PLANNED, "payload": {"rounds": ["a", "b", "c"]}})
        got = t.feed({"type": ET.ROUND_STARTED, "payload": {"round": 1}})
        self.assertEqual((got[0]["status"], got[0]["progress"]), ("reading", 0.5))
        got = t.feed({"type": ET.ROUND_STARTED, "payload": {"round": 9}})
        self.assertLess(got[0]["progress"], 1)
        deltas = t.feed({"type": ET.RUN_COMPLETED, "payload": {"final_text": "x" * 200}})
        self.assertEqual([len(d["text"]) for d in deltas], [80, 80, 40])
        self.assertEqual(t.end, "done")
        self.assertEqual(t.fields()["model"], "Council of 2")
        self.assertEqual(t.finish({"id": "m1"})["type"], "run.done")

        f = RunTranslator("r2", "m2")
        f.start()
        f.feed({"type": ET.RUN_FAILED, "payload": {"error": "boom"}})
        self.assertEqual(f.fields()["status"], "failed")
        self.assertIn("boom", f.fields()["error"])
        self.assertEqual(f.finish({})["type"], "run.error")

    def test_models_already_in_memory_count_as_loaded(self):
        t = RunTranslator("r3", "m3")
        t.start()
        got = t.feed({"type": ET.ROUTER_LINEUP_SELECTED, "payload": {
            "lineup": {"seats": [{}, {}, {}, {}]},
            "models": [{"model_id": "a", "resident": True}, {"model_id": "b", "resident": True},
                       {"model_id": "c", "resident": False}, {"model_id": "d"}]}})
        self.assertEqual((got[0]["status"], got[0]["progress"]), ("waiting", 0.5))
        t.feed({"type": ET.MODEL_LOADING, "payload": {"model_id": "c"}})
        got = t.feed({"type": ET.MODEL_LOADED, "payload": {"model_id": "c"}})
        self.assertEqual(got[0]["progress"], 0.75)


if __name__ == "__main__":
    unittest.main()
