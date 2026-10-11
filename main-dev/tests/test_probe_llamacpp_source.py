import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from council.probe.llamacpp_source import (
    ActivationError,
    LlamaCppActivationSource,
    pick_layers,
    render_text,
)

N_LAYER = 6
N_EMBD = 3


class _Pipe:
    """Stands in for a StreamReader."""

    def __init__(self):
        self.q = asyncio.Queue()

    def feed(self, data: bytes):
        self.q.put_nowait(data)

    async def readline(self) -> bytes:
        data = await self.q.get()
        if data == b"":
            self.q.put_nowait(b"")  # EOF stays EOF
        return data


class _Stdin:
    def __init__(self, proc):
        self.proc = proc
        self.closed = False

    def write(self, data: bytes):
        if self.proc.returncode is not None:
            raise BrokenPipeError("process is gone")
        for line in data.decode("utf-8").splitlines():
            self.proc.handle(json.loads(line))

    async def drain(self):
        await asyncio.sleep(0)

    def close(self):
        self.closed = True


class FakeProc:
    """Speaks the actdump JSON-lines protocol. `mode` picks a failure to act out."""

    def __init__(self, argv, mode="ok"):
        self.argv = argv
        self.mode = mode
        self.returncode = None
        self.stdin = _Stdin(self)
        self.stdout = _Pipe()
        self.stderr = _Pipe()
        self.requests = []
        self.terminated = False

    def handle(self, req):
        self.requests.append(req)
        text = req["text"]
        if self.mode == "die":
            self.stderr.feed(b"actdump: cannot load model x\n")
            self.exit(1)
            return
        if self.mode == "silent":
            return
        if self.mode == "garbage":
            self.stdout.feed(b"not json\n")
            return
        if self.mode == "wrong_id":
            self.stdout.feed((json.dumps({"id": "other", "layers": {}}) + "\n").encode())
            return
        if "TOO LONG" in text:
            reply = {"id": req["id"], "error": "prompt longer than context"}
        else:
            layers = {str(n): [float(n), float(len(text)), 0.5] for n in range(N_LAYER)}
            if self.mode == "null":
                layers["2"] = [None, 1.0, 2.0]
            reply = {"id": req["id"], "n_tokens": len(text.split()), "n_embd": N_EMBD,
                     "layers": layers}
        self.stdout.feed((json.dumps(reply) + "\n").encode())

    def exit(self, code):
        if self.returncode is None:
            self.returncode = code
            self.stdout.feed(b"")
            self.stderr.feed(b"")

    def terminate(self):
        self.terminated = True
        self.exit(-15)

    def kill(self):
        self.exit(-9)

    async def wait(self):
        return self.returncode

    async def communicate(self):
        if self.mode == "info_fail":
            self.returncode = 1
            return b"", b"actdump: cannot load model x\n"
        self.returncode = 0
        info = {"n_layer": N_LAYER, "n_embd": N_EMBD, "architecture": "fake"}
        return (json.dumps(info) + "\n").encode(), b""


class Runner:
    def __init__(self, mode="ok"):
        self.mode = mode
        self.procs = []

    async def __call__(self, argv):
        proc = FakeProc(argv, self.mode)
        self.procs.append(proc)
        return proc

    @property
    def workers(self):
        return [p for p in self.procs if "--info" not in p.argv]


MSGS = [{"role": "system", "content": "be careful"},
        {"role": "user", "content": "what is 2+2"},
        {"role": "assistant", "content": "4"}]


class SourceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.binary = self.dir / "actdump"
        self.binary.write_bytes(b"x")
        for name in ("m1", "m2", "m3"):
            (self.dir / f"{name}.gguf").write_bytes(b"GGUF")

    def blob_for(self, model_id):
        return None if model_id == "unknown" else self.dir / f"{model_id}.gguf"

    def source(self, mode="ok", **kw):
        self.runner = Runner(mode)
        return LlamaCppActivationSource(self.binary, self.blob_for, runner=self.runner, **kw)

    async def test_capture_returns_only_the_asked_layers(self):
        src = self.source()
        out = await src.capture("m1", MSGS, [1, 4])
        self.assertEqual(sorted(out), [1, 4])
        self.assertTrue(all(isinstance(k, int) for k in out))
        text = "user: what is 2+2\nassistant: 4"
        self.assertEqual(out[4], [4.0, float(len(text)), 0.5])
        self.assertEqual(self.runner.procs[0].requests[0]["text"], text)
        await src.close()

    async def test_argv(self):
        src = self.source(pool="mean", n_gpu_layers=7, ctx=512)
        await src.capture("m1", MSGS, [0])
        self.assertEqual(self.runner.procs[0].argv, [
            str(self.binary), "-m", str(self.dir / "m1.gguf"), "--layers", "all",
            "--pool", "mean", "-ngl", "7", "-c", "512"])
        await src.close()

    async def test_one_process_is_reused(self):
        src = self.source()
        a = await src.capture("m1", MSGS, [0])
        b = await src.capture("m1", MSGS, [5])  # a layer not asked the first time
        self.assertEqual((sorted(a), sorted(b)), ([0], [5]))
        self.assertEqual(len(self.runner.procs), 1)
        ids = [r["id"] for r in self.runner.procs[0].requests]
        self.assertEqual(len(set(ids)), 2)
        await src.close()

    async def test_requests_in_parallel_do_not_mix(self):
        src = self.source()
        texts = [[{"role": "user", "content": "x" * n}] for n in range(1, 9)]
        outs = await asyncio.gather(*(src.capture("m1", m, [3]) for m in texts))
        self.assertEqual([o[3][1] for o in outs], [float(n) for n in range(1, 9)])
        self.assertEqual(len(self.runner.procs), 1)
        await src.close()

    async def test_lru_keeps_max_models_alive(self):
        src = self.source()
        await src.capture("m1", MSGS, [0])
        await src.capture("m2", MSGS, [0])
        self.assertEqual(src.alive(), ["m2"])
        self.assertTrue(self.runner.procs[0].terminated)
        self.assertTrue(self.runner.procs[0].stdin.closed)
        self.assertFalse(self.runner.procs[1].terminated)
        await src.capture("m1", MSGS, [0])  # started again
        self.assertEqual(len(self.runner.procs), 3)
        await src.close()

    async def test_lru_order_with_two_slots(self):
        src = self.source(max_models=2)
        await src.capture("m1", MSGS, [0])
        await src.capture("m2", MSGS, [0])
        await src.capture("m1", MSGS, [0])  # m1 is now the most recent
        await src.capture("m3", MSGS, [0])  # so m2 goes
        self.assertEqual(src.alive(), ["m1", "m3"])
        self.assertTrue(self.runner.procs[1].terminated)
        self.assertFalse(self.runner.procs[0].terminated)
        await src.close()

    async def test_switching_models_in_parallel(self):
        src = self.source()
        jobs = [src.capture(m, MSGS, [1]) for m in ("m1", "m2", "m1", "m2", "m3")]
        outs = await asyncio.gather(*jobs)
        self.assertTrue(all(sorted(o) == [1] for o in outs))
        self.assertLessEqual(len(src.alive()), 1)
        await src.close()

    async def test_close(self):
        src = self.source(max_models=2)
        await src.capture("m1", MSGS, [0])
        await src.capture("m2", MSGS, [0])
        await src.close("m1")
        self.assertEqual(src.alive(), ["m2"])
        await src.close("never-started")
        await src.close()
        self.assertEqual(src.alive(), [])
        self.assertTrue(all(p.terminated for p in self.runner.procs))
        await src.close()  # closing twice is fine

    async def test_info_is_cached(self):
        src = self.source()
        info = await src.info("m1")
        self.assertEqual(info, {"n_layer": N_LAYER, "n_embd": N_EMBD, "architecture": "fake"})
        info["n_layer"] = 999  # the cache is not the caller's dict
        self.assertEqual((await src.info("m1"))["n_layer"], N_LAYER)
        self.assertEqual(len(self.runner.procs), 1)
        argv = self.runner.procs[0].argv
        self.assertIn("--info", argv)
        self.assertEqual(argv[:3], [str(self.binary), "-m", str(self.dir / "m1.gguf")])
        self.assertEqual(src.alive(), [])  # --info is not a long-lived process

    async def test_info_failure(self):
        src = self.source("info_fail")
        with self.assertRaisesRegex(ActivationError, "cannot load model"):
            await src.info("m1")

    async def test_binary_missing(self):
        self.runner = Runner()
        src = LlamaCppActivationSource(self.dir / "absent", self.blob_for, runner=self.runner)
        with self.assertRaisesRegex(ActivationError, "binary is missing"):
            await src.capture("m1", MSGS, [0])
        with self.assertRaisesRegex(ActivationError, "binary is missing"):
            await src.info("m1")
        self.assertEqual(self.runner.procs, [])

    async def test_model_missing(self):
        src = self.source()
        with self.assertRaisesRegex(ActivationError, "no GGUF file for model unknown"):
            await src.capture("unknown", MSGS, [0])
        (self.dir / "m3.gguf").unlink()
        with self.assertRaisesRegex(ActivationError, "is missing"):
            await src.capture("m3", MSGS, [0])
        self.assertEqual(self.runner.procs, [])

    async def test_runner_that_cannot_start(self):
        async def boom(argv):
            raise OSError("exec format error")
        src = LlamaCppActivationSource(self.binary, self.blob_for, runner=boom)
        with self.assertRaisesRegex(ActivationError, "cannot start actdump for m1"):
            await src.capture("m1", MSGS, [0])

    async def test_process_died(self):
        src = self.source("die")
        with self.assertRaisesRegex(ActivationError, r"died.*exit code 1.*cannot load model"):
            await src.capture("m1", MSGS, [0])
        self.assertEqual(src.alive(), [])
        self.runner.mode = "ok"  # the next call starts a fresh process
        self.assertEqual(sorted(await src.capture("m1", MSGS, [0])), [0])
        self.assertEqual(len(self.runner.procs), 2)
        await src.close()

    async def test_error_reply_keeps_the_process(self):
        src = self.source()
        with self.assertRaisesRegex(ActivationError, "prompt longer than context"):
            await src.capture("m1", [{"role": "user", "content": "TOO LONG"}], [0])
        self.assertEqual(src.alive(), ["m1"])
        await src.capture("m1", MSGS, [0])
        self.assertEqual(len(self.runner.procs), 1)
        await src.close()

    async def test_layer_out_of_range(self):
        src = self.source()
        with self.assertRaisesRegex(ActivationError, r"layer 40 not in the reply \(layers 0\.\.5\)"):
            await src.capture("m1", MSGS, [2, 40])
        await src.close()

    async def test_bad_replies(self):
        for mode, pattern in (("garbage", "not JSON"), ("wrong_id", "another request"),
                              ("null", "not a number")):
            src = self.source(mode)
            with self.assertRaisesRegex(ActivationError, pattern):
                await src.capture("m1", MSGS, [2])
            await src.close()

    async def test_timeout_kills_the_process(self):
        src = self.source("silent", timeout_s=0.05)
        with self.assertRaisesRegex(ActivationError, "no reply in"):
            await src.capture("m1", MSGS, [0])
        self.assertEqual(src.alive(), [])
        self.assertTrue(self.runner.procs[0].terminated)

    async def test_no_text(self):
        src = self.source()
        with self.assertRaisesRegex(ActivationError, "no message text"):
            await src.capture("m1", [{"role": "system", "content": "only this"}], [0])
        self.assertEqual(self.runner.procs, [])

    async def test_bad_pool(self):
        with self.assertRaises(ValueError):
            LlamaCppActivationSource(self.binary, self.blob_for, pool="max")


class AcrossLoops(unittest.TestCase):
    def test_a_new_event_loop_gets_a_new_process(self):
        with tempfile.TemporaryDirectory() as d:
            binary, model = Path(d) / "actdump", Path(d) / "m.gguf"
            binary.write_bytes(b"x")
            model.write_bytes(b"GGUF")
            runner = Runner()
            src = LlamaCppActivationSource(binary, lambda m: model, runner=runner)
            a = asyncio.run(src.capture("m1", MSGS, [1]))
            b = asyncio.run(src.capture("m1", MSGS, [1]))
            self.assertEqual(a, b)
            self.assertEqual(len(runner.procs), 2)
            self.assertTrue(runner.procs[0].terminated)
            asyncio.run(src.close())
            self.assertTrue(runner.procs[1].terminated)


FAKE_TOOL = """
import json, sys
if "--info" in sys.argv:
    print(json.dumps({"n_layer": 4, "n_embd": 30000, "architecture": "fake"}), flush=True)
    sys.exit(0)
print("actdump: a warning on stderr", file=sys.stderr, flush=True)
for line in sys.stdin:
    req = json.loads(line)
    # about 1 MB per reply: far past the 64 KiB default line limit of asyncio streams
    vec = [0.123456789 + len(req["text"])] * 30000
    print(json.dumps({"id": req["id"], "n_tokens": 1, "n_embd": 30000,
                      "layers": {str(n): vec for n in range(4)}}), flush=True)
"""


class RealPipes(unittest.IsolatedAsyncioTestCase):
    """The same protocol over real OS pipes, with a Python script standing in for actdump."""

    async def test_big_lines_over_real_pipes(self):
        import sys
        from council.probe import llamacpp_source as L

        with tempfile.TemporaryDirectory() as d:
            tool, model = Path(d) / "actdump", Path(d) / "m.gguf"
            tool.write_text(FAKE_TOOL, encoding="utf-8")
            model.write_bytes(b"GGUF")

            async def runner(argv):  # the default runner, with python in front of the script
                return await L._default_runner([sys.executable] + argv)

            src = LlamaCppActivationSource(tool, lambda m: model, runner=runner, timeout_s=60)
            try:
                self.assertEqual((await src.info("m1"))["n_layer"], 4)
                out = await src.capture("m1", MSGS, [1, 3])
                self.assertEqual(sorted(out), [1, 3])
                self.assertEqual(len(out[3]), 30000)
                again = await src.capture("m1", MSGS, [0])
                self.assertEqual(again[0], out[1])
            finally:
                await src.close()
            self.assertEqual(src.alive(), [])


class TextTests(unittest.TestCase):
    def test_render(self):
        self.assertEqual(render_text(MSGS), "user: what is 2+2\nassistant: 4")
        self.assertEqual(render_text(MSGS, include_system=True),
                         "system: be careful\nuser: what is 2+2\nassistant: 4")
        self.assertEqual(render_text([]), "")

    def test_meta_is_never_text(self):
        text = render_text([{"role": "assistant", "content": "B", "meta": {"lie": True}}])
        self.assertEqual(text, "assistant: B")

    def test_single_user_message_is_sent_without_a_role_prefix(self):
        from council.probe.layout import TAIL, probe_messages
        from council.probe.trainer import pair_messages
        text = render_text(probe_messages("What is 2+2?", "It is 4."))
        self.assertEqual(text, "Question: What is 2+2?\nStatement: It is 4.\n" + TAIL)
        self.assertTrue(text.endswith("The statement above is"))
        self.assertTrue(render_text(pair_messages("2 + 2 = 5.", True)).endswith(TAIL))
        self.assertNotIn("user:", render_text(pair_messages("2 + 2 = 5.", True)))
        # a system message in front does not bring the prefix back, unless it is kept
        sys_user = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]
        self.assertEqual(render_text(sys_user), "q")
        self.assertEqual(render_text(sys_user, include_system=True), "system: s\nuser: q")

    def test_pick_layers(self):
        self.assertEqual(pick_layers(32), [8, 13, 19, 24])
        self.assertEqual(pick_layers(24), [6, 10, 14, 18])
        self.assertEqual(pick_layers(12, 2), [3, 9])
        self.assertEqual(pick_layers(32, 1), [16])
        self.assertEqual(pick_layers(0), [])
        self.assertEqual(pick_layers(8, 0), [])
        for n in range(1, 80):
            got = pick_layers(n)
            self.assertTrue(got)
            self.assertEqual(got, sorted(set(got)))
            self.assertTrue(all(n // 4 <= x <= max(n // 4, min(n - 1, 3 * n // 4)) for x in got))
            self.assertTrue(all(0 <= x < n for x in got))


if __name__ == "__main__":
    unittest.main()
