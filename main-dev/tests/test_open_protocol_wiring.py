"""The open council protocol wired into the pipeline, the bench, the CLI, the box config and
the UI stream. Mock mode only. The repo default stays "structured"."""

import asyncio
import importlib.util
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from council import cli
from council.api import run_pipeline as rp
from council.api.controller import RunController
from council.api.server import create_app
from council.api.ui_bridge import UiBridge, seat_names
from council.chamber.messages import Card, CouncilMessage
from council.core import config as config_mod
from council.core.config import Config
from council.core.schemas import BenchRunRequest, LineupRecord, Probe, SeatAssignment
from tests.test_bench_runner import SAMPLE, build

ROOT = Path(__file__).resolve().parents[1]
TASK = "Which rate limiter should a small public API use?"


def parse_sse(text):
    out = []
    for frame in text.split("\n\n"):
        data = [ln[6:] for ln in frame.split("\n") if ln.startswith("data: ")]
        if data:
            out.append(json.loads(data[0]))
    return out


def run_once(client, options):
    rid = client.post("/runs", json={"task": TASK, "mode": "standard", "options": options}).json()["run_id"]
    with client.stream("GET", f"/runs/{rid}/events") as resp:
        events = parse_sse("".join(resp.iter_text()))
    return rid, events


class OpenRunTests(unittest.TestCase):
    def test_open_run_at_k_2_3_6(self):
        for k in (2, 3, 6):
            with self.subTest(k=k):
                ctrl = RunController.build_mock(speed=500.0)
                with TestClient(create_app(ctrl)) as c:
                    rid, events = run_once(c, {"protocol": "open", "k": k})
                    self.assertEqual(c.get(f"/runs/{rid}").json()["state"], "DONE")
                    kinds = Counter(e["type"] for e in events)
                    for name in ("msg.started", "msg.card", "table.tally", "decision.final"):
                        self.assertGreater(kinds[name], 0, name)
                    self.assertGreaterEqual(kinds["msg.started"], k)
                    self.assertEqual(kinds["tribunal.started"], 0)  # skipped for the open protocol
                    decision = [e for e in events if e["type"] == "decision.final"][-1]["payload"]["decision"]
                    self.assertTrue(decision["final_text"])
                    started = [e["payload"] for e in events if e["type"] == "msg.started"]
                    self.assertTrue(all(p.get("call_id") for p in started))
                    names = [p["name"] for p in started if p["round"] == 0]
                    self.assertEqual(len(names), len(set(names)))
                    # One lie-detector reading per message. No probe is trained in the mock box.
                    lies = [e["payload"] for e in events if e["type"] == "msg.lie"]
                    self.assertEqual(len(lies), kinds["msg.card"])
                    self.assertTrue(all(p["score"] is None and p["level"] == "ok"
                                        and p["reasons"] == ["no probe"] for p in lies))

                    ui = parse_sse(c.get(f"/runs/{rid}/ui-events").text)
                    ui_kinds = Counter(e["type"] for e in ui)
                    for name in ("debate.created", "turn.started", "summary.posted", "tally.posted",
                                 "answer.released"):
                        self.assertGreater(ui_kinds[name], 0, name)
                    self.assertEqual(ui[0]["type"], "debate.created")
                    self.assertEqual(len(ui[0]["seats"]), k)
                    self.assertEqual([e["seq"] for e in ui], list(range(1, len(ui) + 1)))
                    # One UI turn per message, plus the answer turn. After a consensus the answer
                    # is itself a message (kind "answer", written by one backer): no extra turn.
                    written = any(p["kind"] == "answer" for p in started)
                    self.assertEqual(ui_kinds["turn.started"], kinds["msg.started"] + (0 if written else 1))
                    self.assertEqual(sum(e["type"] == "turn.started" and e["kind"] == "answer" for e in ui), 1)
                    if decision["outcome"] == "consensus":
                        self.assertTrue(written)
                        self.assertEqual(kinds["msg.ended"], kinds["msg.started"])

    def test_ui_events_unknown_run(self):
        ctrl = RunController.build_mock(speed=500.0)
        with TestClient(create_app(ctrl)) as c:
            self.assertEqual(c.get("/runs/nope/ui-events").status_code, 404)

    def test_default_is_structured(self):
        self.assertEqual(Config().chamber.protocol, "structured")
        self.assertEqual(config_mod.load_config().chamber.protocol, "structured")
        ctrl = RunController.build_mock(speed=500.0)
        with TestClient(create_app(ctrl)) as c:
            rid, events = run_once(c, {"k": 3})
            self.assertEqual(c.get(f"/runs/{rid}").json()["state"], "DONE")
            kinds = Counter(e["type"] for e in events)
            self.assertEqual(kinds["msg.started"], 0)
            self.assertEqual(kinds["table.tally"], 0)
            self.assertGreater(kinds["turn.started"], 0)

    def test_config_selects_the_protocol_and_an_option_overrides_it(self):
        ctrl = RunController.build_mock(speed=500.0)
        ctrl.config.chamber.protocol = "open"
        with TestClient(create_app(ctrl)) as c:
            _, events = run_once(c, {"k": 2})
            self.assertGreater(Counter(e["type"] for e in events)["msg.started"], 0)
            _, events = run_once(c, {"k": 2, "protocol": "structured"})
            self.assertEqual(Counter(e["type"] for e in events)["msg.started"], 0)


MODELS = ["m-a", "m-b", "m-c", "m-d", "m-e", "m-f"]


class SlowSource:
    """One model at a time, like the box: captures queue, each takes `delay` seconds."""

    max_models = 1

    def __init__(self, delay=0.0, fail=(), slow=()):
        self.delay, self.fail, self.slow = delay, set(fail), set(slow)
        self.calls, self.texts, self.running, self.most = [], [], 0, 0
        self._lock = None

    async def capture(self, model_id, messages, layers):
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            self.calls.append(model_id)
            self.texts.append(messages[-1]["content"])
            self.running += 1
            self.most = max(self.most, self.running)
            try:
                if model_id in self.fail:
                    raise RuntimeError("boom")
                await asyncio.sleep(5.0 if model_id in self.slow else self.delay)
                return {3: [0.0, 0.0]}
            finally:
                self.running -= 1


class FakeReliability:
    """Every model has an active probe, except `untrusted` (trained, not active) and `none`."""

    def __init__(self, source=None, untrusted=(), none=()):
        self.source = source if source is not None else SlowSource()
        self.untrusted, self.none = set(untrusted), set(none)
        self.released = 0

    def active_probes(self, model_id):
        if model_id in self.untrusted or model_id in self.none:
            return []
        return [Probe(model_id=model_id, layer=3, weights=[1.0, 1.0], bias=-1.5, auroc=0.9,
                      n_train=40, trained_at=0.0, status="validated")]

    def probe_state(self, model_id):
        if model_id in self.untrusted:
            return "untrusted"
        return "none" if model_id in self.none else "active"

    def platt_for(self, model_id):
        return None

    async def _release(self):
        self.released += 1


NO = {"score": None, "level": "ok"}


class LieReadingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pipe = rp.RunPipeline.__new__(rp.RunPipeline)
        self.cfg = Config()
        self.pipe.d = SimpleNamespace(config=self.cfg)
        self.lineup = LineupRecord(seats=[SeatAssignment(seat_no=n, model_id=m)
                                          for n, m in enumerate(MODELS)], k=6)
        self.msgs = [self.msg(n) for n in range(6)]

    @staticmethod
    def msg(n, stance="token bucket", note="use a token bucket", text="I say token bucket."):
        card = Card(note=note, stance=stance, backs="new")
        return CouncilMessage(turn_id=f"t{n}", seat_id=f"s{n}", seat_no=n, name=f"N{n}", round=0,
                              kind="position", text=text, card=card, done=True)

    async def read(self, rel, msgs=None):
        return await self.pipe._message_readings(rel, "task", self.lineup, msgs or self.msgs)

    async def test_all_six_get_a_reading_when_each_takes_its_time(self):
        # Scaled from the box: 5 s a reading and a 20 s limit are 0.1 s and 0.4 s here. Six
        # readings in a row take 0.6 s, more than the limit of one.
        self.cfg.lie.timeout_s = 0.4
        rel = FakeReliability(SlowSource(delay=0.1))
        out = await self.read(rel, list(reversed(self.msgs)))
        self.assertEqual(sorted(out), [f"t{n}" for n in range(6)])
        for reading in out.values():
            self.assertIsNotNone(reading["score"])
            self.assertEqual(reading["level"], "ok")
            self.assertRegex(reading["reasons"][0], r"^truth probe reads the stance at 0\.\d\d$")
        self.assertEqual(rel.source.calls, MODELS)  # seat order, whatever order they came in
        self.assertEqual(rel.source.most, 1)  # never two captures at once
        self.assertEqual(rel.released, 1)

    async def test_the_three_reasons(self):
        self.cfg.lie.timeout_s = 0.1
        rel = FakeReliability(SlowSource(delay=0.01, fail={"m-c"}, slow={"m-d"}),
                              untrusted={"m-b"}, none={"m-f"})
        out = await self.read(rel)
        self.assertIsNotNone(out["t0"]["score"])
        self.assertEqual(out["t1"], dict(NO, reasons=["probe not trusted for this model"]))
        self.assertEqual(out["t2"], dict(NO, reasons=["reading failed"]))
        self.assertEqual(out["t3"], dict(NO, reasons=["reading timed out"]))
        self.assertIsNotNone(out["t4"]["score"])  # the slow one before it cost it nothing
        self.assertEqual(out["t5"], dict(NO, reasons=["no probe"]))
        self.assertEqual(rel.source.calls, ["m-a", "m-c", "m-d", "m-e"])  # no capture without a probe

    async def test_the_batch_budget_is_respected(self):
        import time
        self.cfg.lie.timeout_s = 0.1
        rel = FakeReliability(SlowSource(slow=set(MODELS)))  # every member hangs
        t0 = time.monotonic()
        out = await self.read(rel)
        took = time.monotonic() - t0
        self.assertTrue(all(v == dict(NO, reasons=["reading timed out"]) for v in out.values()))
        self.assertGreaterEqual(took, 0.5)  # each member had its own 0.1 s
        self.assertLess(took, 0.6 + 0.6)  # and the debate waited no longer than 6 * 0.1 s
        self.assertEqual(rel.released, 1)

    async def test_a_source_that_ignores_its_timeout_cannot_hold_the_debate(self):
        class Deaf(rp.LiveScorer):
            async def read_many(self, task, items, budget_s=None, clock=None):
                await asyncio.sleep(30)

        self.cfg.lie.timeout_s = 0.02
        old, rp.LiveScorer, slack = rp.LiveScorer, Deaf, rp._LIE_SLACK_S
        rp._LIE_SLACK_S = 0.05
        try:
            rel = FakeReliability()
            out = await asyncio.wait_for(self.read(rel), 5)
        finally:
            rp.LiveScorer, rp._LIE_SLACK_S = old, slack
        self.assertTrue(all(v["reasons"] == ["reading timed out"] for v in out.values()))
        self.assertEqual(rel.released, 1)

    async def test_what_is_read_stance_then_note_then_first_sentence(self):
        rel = FakeReliability()
        msgs = [self.msg(0), self.msg(1, stance="  "),
                self.msg(2, stance="", note="", text="Use a leaky bucket. It is simple.\nMore."),
                self.msg(3, stance="", note="", text="no full stop here\nsecond line")]
        await self.read(rel, msgs)
        said = [t.split("Statement: ")[1].split("\n")[0] for t in rel.source.texts]
        self.assertEqual(said, ["token bucket", "use a token bucket", "Use a leaky bucket.",
                                "no full stop here"])
        self.assertEqual(rp._reading_text(SimpleNamespace(card=None, text="")), "")
        self.assertEqual(len(rp._reading_text(SimpleNamespace(card=None, text="x" * 900))), 400)

    async def test_never_raises(self):
        out = await self.read(None)
        self.assertTrue(all(v == dict(NO, reasons=["no probe"]) for v in out.values()))
        rel = FakeReliability()
        rel.source = None
        self.assertEqual((await self.read(rel))["t0"]["reasons"], ["no probe"])

        class Broken(FakeReliability):
            def active_probes(self, model_id):
                raise RuntimeError("boom")

        out = await self.read(Broken())
        self.assertTrue(all(v == dict(NO, reasons=["no probe"]) for v in out.values()))


class UiBridgeDeltaTests(unittest.TestCase):
    def test_gateway_delta_goes_to_the_message_turn_by_call_id(self):
        b = UiBridge("d1")
        out = b.feed({"type": "msg.started", "ts": 1.0, "payload": {
            "turn_id": "turn-A", "call_id": "call-A", "seat_no": 0, "model_id": "m-a", "name": "A",
            "round": 0, "kind": "position", "to": "all"}})
        self.assertIn("turn.started", [e["type"] for e in out])
        out = b.feed({"type": "turn.delta", "ts": 1.1, "payload": {"call_id": "call-A", "text": "Hel"}})
        self.assertEqual([(e["type"], e["turnId"], e["text"]) for e in out], [("turn.delta", "turn-A", "Hel")])
        self.assertEqual(b.feed({"type": "turn.delta", "ts": 1.2,
                                 "payload": {"call_id": "other", "text": "x"}}), [])

    def _written(self, text, error=None):
        b = UiBridge("d1")
        b.feed({"type": "msg.started", "ts": 1.0, "payload": {
            "turn_id": "run:final:s1", "call_id": "run:final:s1", "seat_no": 1, "model_id": "m-b",
            "name": "B", "round": 1, "kind": "answer", "to": "all"}})
        out = b.feed({"type": "turn.delta", "ts": 1.1, "payload": {"call_id": "run:final:s1", "text": "Use"}})
        self.assertEqual([e["type"] for e in out], ["turn.delta"])
        out = b.feed({"type": "msg.ended", "ts": 1.2, "payload": {
            "turn_id": "run:final:s1", "seat_no": 1, "text": text, "error": error}})
        self.assertEqual([e["on"] for e in out if e["type"] == "seat.thinking"], [False])  # no card follows
        final = "Use a token bucket." if text else "Token bucket\n\nB, I agree with you."
        out += b.feed({"type": "decision.final", "ts": 1.3, "payload": {
            "decision": {"outcome": "consensus", "final_text": final, "rounds_run": 2}}})
        out += b.feed({"type": "run.completed", "ts": 1.4, "payload": {"outcome": "consensus"}})
        return out

    def test_the_written_answer_is_the_answer_turn(self):
        out = self._written("Use a token bucket.")
        self.assertEqual([e for e in out if e["type"] == "turn.started"], [])  # no second answer turn
        ended = [e for e in out if e["type"] == "turn.ended"]
        self.assertEqual([(e["turnId"], e["text"]) for e in ended], [("run:final:s1", "Use a token bucket.")])
        released = [e for e in out if e["type"] == "answer.released"][0]
        self.assertEqual((released["outcome"], released["turnId"]), ("agreed", "run:final:s1"))

    def test_a_failed_writer_still_gets_an_answer_turn(self):
        out = self._written("", "timeout")
        started = [e for e in out if e["type"] == "turn.started"]
        self.assertEqual([(e["turnId"], e["kind"]) for e in started], [("answer", "answer")])
        ended = {e["turnId"]: e for e in out if e["type"] == "turn.ended"}
        self.assertEqual(ended["run:final:s1"]["error"], "timeout")
        self.assertEqual(ended["answer"]["text"], "Token bucket\n\nB, I agree with you.")
        self.assertEqual([e for e in out if e["type"] == "answer.released"][0]["turnId"], "answer")

    def test_seat_names_are_first_words_and_unique(self):
        self.assertEqual(seat_names({0: "Qwen 2.5 Coder", 1: "Qwen 3", 2: "Gemma-3", 3: ""}),
                         {0: "Qwen", 1: "Qwen2", 2: "Gemma", 3: "Seat3"})


class BenchOpenTests(unittest.TestCase):
    def _run(self, protocol=None, config_protocol=None):
        runner, gateway, host, store, events = build()
        if config_protocol:
            runner.config.chamber.protocol = config_protocol
        req = BenchRunRequest(tasks_path=str(SAMPLE), modes=["council", "council_vote_only"],
                              split="test", limit=4)
        if protocol:
            object.__setattr__(req, "protocol", protocol)
        with tempfile.TemporaryDirectory() as tmp:
            rows = asyncio.run(runner.run(req, Path(tmp) / "run"))
            lines = [json.loads(x) for x in (Path(tmp) / "run" / "council" / "results.jsonl")
                     .read_text(encoding="utf-8").splitlines()]
        store.close()
        return rows, lines, [s.purpose for s in gateway.specs], runner

    def test_open_bench_reports_a_council_accuracy(self):
        rows, lines, purposes, runner = self._run(protocol="open")
        by = {r.mode: r for r in rows}
        self.assertEqual(set(by), {"council", "council_vote_only"})
        self.assertEqual(by["council"].n, 4)
        self.assertTrue(0.0 <= by["council"].accuracy <= 1.0)
        self.assertEqual(runner.not_run, {})
        self.assertIn("seat.card", purposes)  # the open protocol ran
        self.assertNotIn("seat.r0", purposes)  # round 0 is the solo answer, never a new call
        for line in lines:
            self.assertIn(line["outcome"], ("consensus", "chair", "deadlock"))
            self.assertTrue(line["answer_key"])  # graded from Decision.answer_key

    def test_config_names_the_protocol(self):
        _, _, purposes, _ = self._run(config_protocol="open")
        self.assertIn("seat.card", purposes)

    def test_structured_is_unchanged(self):
        _, _, purposes, _ = self._run()
        self.assertNotIn("seat.card", purposes)


class CliAndBoxTests(unittest.TestCase):
    def test_cli_flag(self):
        p = cli.build_parser()
        self.assertEqual(cli._effort_options(p.parse_args(["run", "x", "--protocol", "open"])),
                         {"protocol": "open"})
        self.assertEqual(cli._effort_options(p.parse_args(["run", "x"])), {})
        args = p.parse_args(["build", "x", "--workspace", "w", "--protocol", "structured"])
        self.assertEqual(cli._effort_options(args)["protocol"], "structured")
        req = cli.bench_request(p.parse_args(["bench", "--protocol", "open"]))
        self.assertEqual(getattr(req, "protocol", None), "open")
        self.assertIsNone(getattr(cli.bench_request(p.parse_args(["bench"])), "protocol", None))

    def test_bench_cli_runs_the_open_protocol(self):
        ctrl = RunController.build_mock(speed=1000.0)
        import io
        out = io.StringIO()
        code = asyncio.run(cli.main(["bench", "--protocol", "open", "--modes", "council", "--limit", "1",
                                     "--no-calibration", "--speed", "1000"], out=out, controller=ctrl))
        self.assertEqual(code, 0)
        self.assertIn("| council | 1 |", out.getvalue())

    def test_box_config_writes_the_protocol(self):
        spec = importlib.util.spec_from_file_location("make_config_t", ROOT / "tools" / "box" / "make_config.py")
        mc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mc)
        self.assertEqual(mc.chosen_protocol({}), "open")
        self.assertEqual(mc.chosen_protocol({"COUNCIL_PROTOCOL": "Structured"}), "structured")
        with self.assertRaises(SystemExit):
            mc.chosen_protocol({"COUNCIL_PROTOCOL": "nope"})
        base = (ROOT / "config" / "council.toml").read_text(encoding="utf-8")
        text, _ = mc.transform(base, "llamacpp", Path("/home/x"), "open")
        self.assertRegex(text, r'(?m)^protocol = "open"')
        self.assertNotRegex(text, r'(?m)^protocol = "structured"')
        same, _ = mc.transform(base, "llamacpp", Path("/home/x"))
        self.assertRegex(same, r'(?m)^protocol = "structured"')


if __name__ == "__main__":
    unittest.main()
