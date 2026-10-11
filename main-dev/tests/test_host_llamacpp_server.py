import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from council.host import llamacpp_server

from council.core.schemas import ModelEntry
from council.host.drivers import HostDriver
from council.host.llamacpp_server import LlamaServerDriver

BIN = Path("bin") / "llama-server"
BLOBS = {"big:20b": Path("blobs") / "sha256-big", "tiny": Path("blobs") / "sha256-tiny",
         "other:7b": Path("blobs") / "sha256-other"}


def run(coro):
    return asyncio.run(coro)


def make_registry():
    return [
        ModelEntry(id="big", ollama_tag="big:20b"),
        ModelEntry(id="tiny"),
        ModelEntry(id="other", ollama_tag="other:7b"),
    ]


class FakeProc:
    next_pid = 4000

    def __init__(self, stubborn=False, dead=False):
        self.returncode = 1 if dead else None
        self.stubborn = stubborn
        self.terminated = 0
        self.killed = 0
        self._gone = None
        FakeProc.next_pid += 1
        self.pid = FakeProc.next_pid

    def _event(self):
        if self._gone is None:
            self._gone = asyncio.Event()
            if self.returncode is not None:
                self._gone.set()
        return self._gone

    def terminate(self):
        self.terminated += 1
        if not self.stubborn:
            self.returncode = -15
            self._event().set()

    def kill(self):
        self.killed += 1
        self.returncode = -9
        self._event().set()

    async def wait(self):
        await self._event().wait()
        return self.returncode


class Rig:
    def __init__(self, healthy=True, hang=False, **proc_kw):
        self.healthy = healthy
        self.hang = hang
        self.proc_kw = proc_kw
        self.argvs = []
        self.procs = []
        self.probed = []

    async def spawn(self, argv):
        self.argvs.append(list(argv))
        proc = FakeProc(**self.proc_kw)
        self.procs.append(proc)
        return proc

    async def probe(self, url):
        self.probed.append(url)
        if self.hang:
            await asyncio.sleep(3600)
        return self.healthy

    def driver(self, registry=None, **kw):
        kw.setdefault("drafts", {"big": "tiny"})
        return LlamaServerDriver(
            registry if registry is not None else make_registry(),
            lambda tag: BLOBS[tag],
            server_bin=BIN,
            spawn=self.spawn,
            probe_health=self.probe,
            **kw,
        )


class ArgvTests(unittest.TestCase):
    def test_argv_plain(self):
        d = Rig().driver()
        self.assertEqual(
            d.argv_for("other"),
            [str(BIN), "-m", str(BLOBS["other:7b"]), "--port", "18102", "-c", "8192",
             "-ngl", "99", "--jinja"],
        )

    def test_argv_with_draft(self):
        d = Rig().driver(ctx=4096, base_port=19000)
        self.assertEqual(
            d.argv_for("big"),
            [str(BIN), "-m", str(BLOBS["big:20b"]), "--port", "19000", "-c", "4096",
             "-ngl", "99", "--jinja",
             "-md", str(BLOBS["tiny"]), "-ngld", "99", "--draft-max", "16", "--draft-min", "1"],
        )

    def test_argv_is_pure(self):
        rig = Rig()
        d = rig.driver()
        self.assertEqual(d.argv_for("big"), d.argv_for("big"))
        self.assertEqual(rig.argvs, [])
        self.assertEqual(run(d.status()), {})

    def test_dict_registry_and_ports(self):
        d = Rig().driver(registry={m.id: m for m in make_registry()})
        ports = [d.port_for(m) for m in ("big", "tiny", "other")]
        self.assertEqual(ports, [18100, 18101, 18102])

    def test_unknown_model(self):
        d = Rig().driver()
        with self.assertRaises(ValueError):
            d.argv_for("nope")

    def test_missing_blob(self):
        d = LlamaServerDriver(make_registry(), lambda tag: None, server_bin=BIN)
        with self.assertRaises(ValueError):
            d.argv_for("big")


class LifecycleTests(unittest.TestCase):
    def test_protocol(self):
        self.assertIsInstance(Rig().driver(), HostDriver)

    def test_load_returns_url_and_status(self):
        rig = Rig()
        d = rig.driver()

        async def go():
            await d.start()
            url = await d.load("big", "live")
            return url, await d.status()

        url, status = run(go())
        self.assertEqual(url, "http://127.0.0.1:18100")
        self.assertEqual(status, {"big": "loaded"})
        self.assertEqual(rig.argvs, [d.argv_for("big")])
        self.assertEqual(rig.probed, [url])

    def test_second_load_reuses_process(self):
        rig = Rig()
        d = rig.driver()

        async def go():
            return await asyncio.gather(d.load("big", "live"), d.load("big", "batch"))

        a, b = run(go())
        self.assertEqual(a, b)
        self.assertEqual(len(rig.procs), 1)

    def test_port_reused_after_unload(self):
        rig = Rig()
        d = rig.driver()

        async def go():
            first = await d.load("other", "live")
            await d.unload("other")
            mid = await d.status()
            second = await d.load("other", "live")
            return first, mid, second, await d.status()

        first, mid, second, end = run(go())
        self.assertEqual(first, second)
        self.assertEqual(mid, {"other": "unloaded"})
        self.assertEqual(end, {"other": "loaded"})
        self.assertEqual(len(rig.procs), 2)
        self.assertEqual(rig.procs[0].terminated, 1)
        self.assertEqual(rig.procs[0].killed, 0)

    def test_failed_health_kills_and_raises_with_argv(self):
        rig = Rig(healthy=False)
        d = rig.driver()

        async def go():
            with self.assertRaises(RuntimeError) as cm:
                await d.load("big", "live")
            return str(cm.exception), await d.status()

        msg, status = run(go())
        self.assertIn(str(BLOBS["big:20b"]), msg)
        self.assertIn("--draft-max", msg)
        self.assertEqual(rig.procs[0].killed, 1)
        self.assertEqual(status, {"big": "failed"})

    def test_health_timeout_kills(self):
        rig = Rig(hang=True)
        d = rig.driver()
        d.health_timeout_s = 0.05

        async def go():
            with self.assertRaises(RuntimeError):
                await d.load("tiny", "live")

        run(go())
        self.assertEqual(rig.procs[0].killed, 1)

    def test_child_dies_before_health(self):
        rig = Rig(hang=True, dead=True)
        d = rig.driver()

        async def go():
            with self.assertRaises(RuntimeError):
                await d.load("tiny", "live")
            return await d.status()

        self.assertEqual(run(go()), {"tiny": "failed"})

    def test_spawn_error_is_runtime_error(self):
        async def boom(argv):
            raise FileNotFoundError("no bin")

        d = LlamaServerDriver(make_registry(), lambda tag: BLOBS[tag], server_bin=BIN, spawn=boom)

        async def go():
            with self.assertRaises(RuntimeError):
                await d.load("tiny", "live")
            return await d.status()

        self.assertEqual(run(go()), {"tiny": "failed"})

    def test_stop_terminates_every_child(self):
        rig = Rig()
        d = rig.driver()

        async def go():
            await d.start()
            await d.load("big", "live")
            await d.load("other", "live")
            await d.stop()
            return await d.status()

        status = run(go())
        self.assertEqual(status, {"big": "unloaded", "other": "unloaded"})
        self.assertTrue(all(p.terminated == 1 and p.killed == 0 for p in rig.procs))
        self.assertFalse(d.started)

    def test_stop_kills_stubborn_child(self):
        rig = Rig(stubborn=True)
        d = rig.driver()
        d.stop_grace_s = 0.05

        async def go():
            await d.load("tiny", "live")
            await d.stop()

        run(go())
        self.assertEqual((rig.procs[0].terminated, rig.procs[0].killed), (1, 1))

    def test_dead_server_shows_failed_and_reloads(self):
        rig = Rig()
        d = rig.driver()

        async def go():
            await d.load("tiny", "live")
            rig.procs[0].kill()
            status = await d.status()
            await d.load("tiny", "live")
            return status

        self.assertEqual(run(go()), {"tiny": "failed"})
        self.assertEqual(len(rig.procs), 2)

    def test_unload_unknown_is_quiet(self):
        d = Rig().driver()

        async def go():
            await d.unload("big")
            return await d.status()

        self.assertEqual(run(go()), {})


class RealUseTests(unittest.TestCase):
    def test_ctx_for_and_fallback(self):
        d = Rig().driver(ctx_for=lambda m: {"big": 32768}.get(m, 0))
        self.assertEqual(d.ctx_of("big"), 32768)
        self.assertEqual(d.ctx_of("tiny"), 8192)
        argv = d.argv_for("big")
        self.assertEqual(argv[argv.index("-c") + 1], "32768")

    def test_parallel_and_extra_args(self):
        d = Rig().driver(parallel=4, extra_args=["--no-webui", "-fa", "on"], drafts={})
        self.assertEqual(
            d.argv_for("other"),
            [str(BIN), "-m", str(BLOBS["other:7b"]), "--port", "18102", "-c", "8192",
             "-ngl", "99", "--jinja", "--parallel", "4", "--no-webui", "-fa", "on"],
        )

    def test_steering_argv(self):
        d = Rig().driver()
        vec = Path("steer") / "big.gguf"
        self.assertIsNone(d.steering_of("big"))
        d.set_steering("big", vec, 0.25)
        self.assertEqual(d.steering_of("big"), (vec, 0.25))
        argv = d.argv_for("big")
        self.assertEqual(argv[-2:], ["--control-vector-scaled", f"{vec}:0.25"])
        self.assertNotIn("--control-vector-scaled", d.argv_for("tiny"))
        d.set_steering("big", None)
        self.assertIsNone(d.steering_of("big"))
        self.assertNotIn("--control-vector-scaled", d.argv_for("big"))
        with self.assertRaises(ValueError):
            d.set_steering("nope", vec)

    def test_steering_change_restarts(self):
        rig = Rig()
        d = rig.driver()
        vec = Path("steer") / "tiny.gguf"

        async def go():
            await d.load("tiny", "live")
            await d.load("tiny", "live")            # same steering: reuse
            d.set_steering("tiny", vec, 0.5)
            await d.load("tiny", "live")            # changed: restart
            await d.load("tiny", "live")            # same again: reuse
            d.set_steering("tiny", vec, 0.7)
            await d.load("tiny", "live")            # scale changed: restart
            d.set_steering("tiny", None)
            await d.load("tiny", "live")            # cleared: restart
            return await d.status()

        self.assertEqual(run(go()), {"tiny": "loaded"})
        self.assertEqual(len(rig.procs), 4)
        self.assertEqual([p.terminated for p in rig.procs], [1, 1, 1, 0])
        self.assertNotIn("--control-vector-scaled", rig.argvs[0])
        self.assertEqual(rig.argvs[1][-1], f"{vec}:0.5")
        self.assertEqual(rig.argvs[2][-1], f"{vec}:0.7")
        self.assertNotIn("--control-vector-scaled", rig.argvs[3])

    def test_render(self):
        rig = Rig()
        calls = []

        async def post(url, body):
            calls.append((url, body))
            return {"prompt": "<|user|>hi<|assistant|>"}

        d = rig.driver(post_json=post)
        msgs = [{"role": "user", "content": "hi"}]

        async def go():
            with self.assertRaises(RuntimeError):
                await d.render("tiny", msgs)        # not loaded
            await d.load("tiny", "live")
            return await d.render("tiny", msgs)

        self.assertEqual(run(go()), "<|user|>hi<|assistant|>")
        self.assertEqual(calls, [("http://127.0.0.1:18101/apply-template", {"messages": msgs})])

    def test_render_bad_answer(self):
        async def post(url, body):
            return {"error": "x"}

        d = Rig().driver(post_json=post)

        async def go():
            await d.load("tiny", "live")
            with self.assertRaises(RuntimeError):
                await d.render("tiny", [])

        run(go())

    def test_footprints_and_pids(self):
        reg = make_registry()
        reg[0].measured.ram_gb_live = 14.5      # big
        reg[1].measured.ram_gb_batch = 1.5      # tiny, the draft of big
        rig = Rig()
        d = rig.driver(registry=reg)

        async def go():
            empty = await d.footprints(), d.pids()
            await d.load("big", "live")
            await d.load("tiny", "live")
            await d.load("other", "live")       # not measured: no footprint
            full = await d.footprints(), d.pids()
            rig.procs[0].kill()                 # big dies by itself
            return empty, full, (await d.footprints(), d.pids())

        empty, full, after = run(go())
        self.assertEqual(empty, ({}, {}))
        self.assertEqual(full[0], {"big": 16.0, "tiny": 1.5})
        self.assertEqual(full[1], {"big": rig.procs[0].pid, "tiny": rig.procs[1].pid,
                                   "other": rig.procs[2].pid})
        self.assertEqual(after[0], {"tiny": 1.5})
        self.assertNotIn("big", after[1])

    def test_self_exit_is_failed_and_port_free(self):
        rig = Rig()
        d = rig.driver()
        d.set_steering("tiny", Path("v.gguf"), 0.1)

        async def go():
            url = await d.load("tiny", "live")
            rig.procs[0].kill()
            status = await d.status()
            again = await d.load("tiny", "live")
            return url, status, again

        url, status, again = run(go())
        self.assertEqual(status, {"tiny": "failed"})
        self.assertEqual(url, again)
        self.assertEqual(len(rig.procs), 2)

    def test_log_path(self):
        d = Rig().driver()
        self.assertIsNone(d.log_path_for("big"))
        reg = make_registry() + [ModelEntry(id="org/odd name:7b")]
        d = Rig().driver(registry=reg, log_dir=Path("logs"))
        self.assertEqual(d.log_path_for("big"), Path("logs") / "llama-server-big.log")
        self.assertEqual(d.log_path_for("org/odd name:7b"),
                         Path("logs") / "llama-server-org-odd-name-7b.log")

    def test_default_spawn_writes_stderr_to_log(self):
        seen = {}

        async def fake_exec(*argv, stdout=None, stderr=None):
            seen["argv"] = list(argv)
            seen["stderr"] = stderr
            if hasattr(stderr, "write"):
                stderr.write(b"boot line\n")
            return FakeProc()

        async def probe(url):
            return True

        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp) / "logs"
            d = LlamaServerDriver(make_registry(), lambda tag: BLOBS[tag], server_bin=BIN,
                                  probe_health=probe, log_dir=log_dir)
            with mock.patch.object(llamacpp_server.asyncio, "create_subprocess_exec", fake_exec):
                run(d.load("tiny", "live"))
                text = (log_dir / "llama-server-tiny.log").read_bytes()
                plain = LlamaServerDriver(make_registry(), lambda tag: BLOBS[tag], server_bin=BIN,
                                          probe_health=probe)
                run(plain.load("tiny", "live"))
        self.assertEqual(text, b"boot line\n")
        self.assertEqual(seen["argv"], plain.argv_for("tiny"))
        self.assertEqual(seen["stderr"], asyncio.subprocess.DEVNULL)

    def test_from_config(self):
        cfg = SimpleNamespace(llamacpp=SimpleNamespace(
            server_bin="srv/llama-server", base_port=20000, ctx=4096, parallel=2,
            health_timeout_s=33, extra_args=["--no-webui"]))
        rig = Rig()
        d = LlamaServerDriver.from_config(cfg, make_registry(), lambda tag: BLOBS[tag],
                                          spawn=rig.spawn, probe_health=rig.probe)
        self.assertIsInstance(d, HostDriver)
        self.assertEqual(d.health_timeout_s, 33.0)
        self.assertEqual(
            d.argv_for("tiny"),
            [str(Path("srv/llama-server")), "-m", str(BLOBS["tiny"]), "--port", "20001",
             "-c", "4096", "-ngl", "99", "--jinja", "--parallel", "2", "--no-webui"],
        )

    def test_from_config_without_section(self):
        d = LlamaServerDriver.from_config(SimpleNamespace(), make_registry(),
                                          lambda tag: BLOBS[tag])
        self.assertEqual(d.server_bin, llamacpp_server.DEFAULT_BIN)
        self.assertEqual((d.base_port, d.ctx, d.parallel), (18100, 8192, 1))
        self.assertEqual(d.health_timeout_s, llamacpp_server.HEALTH_TIMEOUT_S)

    def test_from_real_config(self):
        from council.core.config import Config

        d = LlamaServerDriver.from_config(Config(), make_registry(), lambda tag: BLOBS[tag])
        self.assertEqual(d.base_port, Config().llamacpp.base_port)
        self.assertEqual(d.health_timeout_s, float(Config().llamacpp.health_timeout_s))


if __name__ == "__main__":
    unittest.main()
