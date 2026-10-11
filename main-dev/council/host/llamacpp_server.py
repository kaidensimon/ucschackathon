"""Host driver: one llama.cpp `llama-server` process per model, optionally with a draft model.

Ollama cannot do speculative decoding, so a model that has a draft is served here instead. The
GGUF files are the blobs Ollama already pulled (see `ollama_blobs`), nothing is downloaded.
Each server speaks the OpenAI-compatible HTTP API on its own local port.
"""
from __future__ import annotations

import asyncio
import re
import socket
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx

from council.core.schemas import ModelEntry

HOST = "127.0.0.1"
HEALTH_TIMEOUT_S = 180.0
STOP_GRACE_S = 5.0
DEFAULT_BIN = Path.home() / "llama.cpp" / "build" / "bin" / "llama-server"


async def _spawn(argv: list[str], log: Path | None = None) -> Any:
    """Start the child. With `log`, its stderr is appended to that file."""
    if log is None:
        return await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as fh:  # the child keeps its own copy of the handle
        return await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.DEVNULL, stderr=fh
        )


async def _probe_health(url: str) -> bool:
    """Poll GET <url>/health until it answers 200. The caller owns the timeout."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            try:
                if (await client.get(f"{url}/health")).status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)


def _port_busy(port: int) -> bool:
    """True when something already listens on the local port."""
    try:
        with socket.create_connection((HOST, int(port)), timeout=0.3):
            return True
    except OSError:
        return False


async def _post_json(url: str, body: dict) -> Any:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, json=body)
        r.raise_for_status()
        return r.json()


def _slug(model_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model_id).strip("-") or "model"


class LlamaServerDriver:
    """Implements HostDriver. `drafts` maps a target model id to its draft model id."""

    health_timeout_s: float = HEALTH_TIMEOUT_S
    stop_grace_s: float = STOP_GRACE_S

    def __init__(
        self,
        registry: dict[str, ModelEntry] | list[ModelEntry],
        blob_for: Callable[[str], Path],
        server_bin: Path = DEFAULT_BIN,
        base_port: int = 18100,
        drafts: dict[str, str] | None = None,
        ctx: int = 8192,
        spawn: Callable[[list[str]], Awaitable[Any]] | None = None,
        probe_health: Callable[[str], Awaitable[bool]] | None = None,
        ctx_for: Callable[[str], int] | None = None,
        parallel: int | None = None,
        extra_args: list[str] | None = None,
        log_dir: Path | None = None,
        post_json: Callable[[str, dict], Awaitable[Any]] | None = None,
        health_timeout_s: float | None = None,
        port_busy: Callable[[int], bool] | None = None,
    ) -> None:
        entries = list(registry.values()) if isinstance(registry, dict) else list(registry)
        self.registry: dict[str, ModelEntry] = {m.id: m for m in entries}
        self.blob_for = blob_for
        self.server_bin = Path(server_bin)
        self.base_port = int(base_port)
        self.drafts: dict[str, str] = dict(drafts or {})
        self.ctx = int(ctx)
        self.ctx_for = ctx_for
        self.parallel = None if parallel is None else int(parallel)
        self.extra_args: list[str] = [str(a) for a in (extra_args or [])]
        self.log_dir = None if log_dir is None else Path(log_dir)
        if health_timeout_s is not None:
            self.health_timeout_s = float(health_timeout_s)
        self._spawn = spawn  # None = the real spawner, which also writes the log file
        self._probe = probe_health or _probe_health
        self._post = post_json or _post_json
        # Checked before a spawn. With an injected spawner there is no real server to collide with.
        self._port_busy = port_busy if port_busy is not None else (_port_busy if spawn is None else None)
        self._steer: dict[str, tuple[Path, float]] = {}  # wanted
        self._steer_live: dict[str, tuple[Path, float] | None] = {}  # what the child runs with
        # One fixed port per model, by registry order: the same model always gets the same port.
        self._ports: dict[str, int] = {m: self.base_port + i for i, m in enumerate(self.registry)}
        self._procs: dict[str, Any] = {}
        self._state: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.started = False

    # ---- pure helpers ----

    def _entry(self, model_id: str) -> ModelEntry:
        entry = self.registry.get(model_id)
        if entry is None:
            raise ValueError(f"unknown model: {model_id}")
        return entry

    def port_for(self, model_id: str) -> int:
        self._entry(model_id)
        return self._ports[model_id]

    def url_for(self, model_id: str) -> str:
        return f"http://{HOST}:{self.port_for(model_id)}"

    def _blob(self, model_id: str) -> Path:
        entry = self._entry(model_id)
        tag = entry.ollama_tag or entry.id
        blob = self.blob_for(tag)
        if blob is None:
            raise ValueError(f"no GGUF blob for model {model_id} (tag {tag})")
        return Path(blob)

    def ctx_of(self, model_id: str) -> int:
        """Context size for this model: `ctx_for` when it gives a positive number, else `ctx`."""
        if self.ctx_for is not None:
            n = self.ctx_for(model_id)
            if n and int(n) > 0:
                return int(n)
        return self.ctx

    def log_path_for(self, model_id: str) -> Path | None:
        self._entry(model_id)
        if self.log_dir is None:
            return None
        return self.log_dir / f"llama-server-{_slug(model_id)}.log"

    def set_steering(self, model_id: str, path: Path | None, scale: float = 1.0) -> None:
        """Record the control vector for this model. It takes effect at the next load()."""
        self._entry(model_id)
        if path is None:
            self._steer.pop(model_id, None)
        else:
            self._steer[model_id] = (Path(path), float(scale))

    def steering_of(self, model_id: str) -> tuple[Path, float] | None:
        return self._steer.get(model_id)

    def _template_file(self, model_id: str) -> Path | None:
        """A chat template llama.cpp ships for a model whose Ollama file carries none it can use.

        gpt-oss: the Ollama blob falls back to a generic template and the model's thinking then
        lands in the answer text (seen on the box). llama.cpp's own gpt-oss template fixes it.
        """
        if "gpt-oss" not in model_id.lower():
            return None
        try:
            path = Path(self.server_bin).expanduser().resolve().parents[2] / "models" / "templates" / "openai-gpt-oss-120b.jinja"
        except (IndexError, OSError):
            return None
        return path if path.is_file() else None

    def argv_for(self, model_id: str) -> list[str]:
        """The full command line for this model. No process is started."""
        argv = [
            str(self.server_bin),
            "-m", str(self._blob(model_id)),
            "--port", str(self.port_for(model_id)),
            "-c", str(self.ctx_of(model_id)),
            "-ngl", "99",
            "--jinja",
        ]
        if self.parallel is not None:
            argv += ["--parallel", str(self.parallel)]
        template = self._template_file(model_id)
        if template is not None:
            argv += ["--chat-template-file", str(template)]
        draft = self.drafts.get(model_id)
        if draft:
            argv += ["-md", str(self._blob(draft)), "-ngld", "99", "--draft-max", "16", "--draft-min", "1"]
        steer = self._steer.get(model_id)
        if steer is not None:
            argv += ["--control-vector-scaled", f"{steer[0]}:{steer[1]}"]
        argv += self.extra_args
        return argv

    @classmethod
    def from_config(
        cls,
        config: Any,
        registry: dict[str, ModelEntry] | list[ModelEntry],
        blob_for: Callable[[str], Path],
        **kw: Any,
    ) -> "LlamaServerDriver":
        """Build the driver from the [llamacpp] config section. Missing fields use the defaults."""
        lc = getattr(config, "llamacpp", None)
        server_bin = getattr(lc, "server_bin", None)
        kw.setdefault("server_bin", Path(server_bin).expanduser() if server_bin else DEFAULT_BIN)
        kw.setdefault("base_port", getattr(lc, "base_port", 18100))
        kw.setdefault("ctx", getattr(lc, "ctx", 8192))
        kw.setdefault("parallel", getattr(lc, "parallel", 1))
        kw.setdefault("health_timeout_s", getattr(lc, "health_timeout_s", HEALTH_TIMEOUT_S))
        kw.setdefault("extra_args", list(getattr(lc, "extra_args", None) or []))
        return cls(registry, blob_for, **kw)

    # ---- lifecycle ----

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        for model_id in list(self._procs):
            await self.unload(model_id)
        self.started = False

    async def _terminate(self, proc: Any) -> None:
        if getattr(proc, "returncode", None) is not None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), self.stop_grace_s)
        except asyncio.TimeoutError:
            await self._kill(proc)

    async def _kill(self, proc: Any) -> None:
        if getattr(proc, "returncode", None) is not None:
            return
        try:
            proc.kill()
        except ProcessLookupError:
            return
        await proc.wait()

    async def _healthy(self, proc: Any, url: str) -> bool:
        """True when the server answers in time. False on timeout or when the child dies first."""
        probe = asyncio.ensure_future(self._probe(url))
        died = asyncio.ensure_future(proc.wait())
        try:
            done, _ = await asyncio.wait(
                {probe, died}, timeout=self.health_timeout_s, return_when=asyncio.FIRST_COMPLETED
            )
            if probe in done:
                return probe.exception() is None and bool(probe.result())
            return False
        finally:
            for task in (probe, died):
                if not task.done():
                    task.cancel()
            await asyncio.gather(probe, died, return_exceptions=True)

    async def load(self, model_id: str, profile: str) -> str:
        url = self.url_for(model_id)
        lock = self._locks.setdefault(model_id, asyncio.Lock())
        async with lock:
            steer = self._steer.get(model_id)
            proc = self._procs.get(model_id)
            if proc is not None and getattr(proc, "returncode", None) is None:
                if self._steer_live.get(model_id) == steer:
                    return url
                await self._terminate(proc)  # steering changed: restart with the new vector
            self._procs.pop(model_id, None)
            self._steer_live.pop(model_id, None)
            argv = self.argv_for(model_id)
            if self._port_busy is not None and await asyncio.to_thread(
                    self._port_busy, self.port_for(model_id)):
                # A server of an earlier process still owns the port. Its /health would answer for
                # our child, which then dies on bind: calls would go to the old model and vector.
                self._state[model_id] = "failed"
                raise RuntimeError(
                    f"port {self.port_for(model_id)} is already in use, cannot start llama-server "
                    f"for {model_id}: stop the old llama-server process on that port")
            self._state[model_id] = "loading"
            try:
                if self._spawn is not None:
                    proc = await self._spawn(argv)
                else:
                    proc = await _spawn(argv, self.log_path_for(model_id))
            except Exception as exc:
                self._state[model_id] = "failed"
                raise RuntimeError(f"llama-server did not start: {exc}; argv: {' '.join(argv)}") from exc
            try:
                ok = await self._healthy(proc, url)
            except BaseException:
                await self._kill(proc)
                self._state[model_id] = "failed"
                raise
            if not ok:
                await self._kill(proc)
                self._state[model_id] = "failed"
                raise RuntimeError(f"llama-server not healthy for {model_id}; argv: {' '.join(argv)}")
            self._procs[model_id] = proc
            self._steer_live[model_id] = steer
            self._state[model_id] = "loaded"
            return url

    async def unload(self, model_id: str) -> None:
        proc = self._procs.pop(model_id, None)
        self._steer_live.pop(model_id, None)
        if proc is not None:
            await self._terminate(proc)
        if model_id in self._state or proc is not None:
            self._state[model_id] = "unloaded"

    def _reap(self) -> None:
        """Drop children that exited by themselves: state "failed", port free for the next load."""
        for model_id, proc in list(self._procs.items()):
            if getattr(proc, "returncode", None) is not None:
                del self._procs[model_id]
                self._steer_live.pop(model_id, None)
                self._state[model_id] = "failed"

    async def status(self) -> dict[str, str]:
        self._reap()
        return dict(self._state)

    def dead_models(self) -> list[str]:
        """Models whose server is not running any more (it exited by itself, or never came up)."""
        self._reap()
        return [m for m, s in self._state.items() if s == "failed" and m not in self._procs]

    def pids(self) -> dict[str, int]:
        """Process id of each running server."""
        self._reap()
        return {
            m: int(p.pid) for m, p in self._procs.items() if getattr(p, "pid", None) is not None
        }

    async def footprints(self) -> dict[str, float]:
        """GiB each loaded model occupies. llama-server reports none, so this is the registry's
        measured size (plus the draft's, which lives in the same process). Unmeasured: left out."""
        self._reap()
        out: dict[str, float] = {}
        for model_id in self._procs:
            size = self._measured(model_id)
            if size is None:
                continue
            draft = self.drafts.get(model_id)
            out[model_id] = size + ((self._measured(draft) or 0.0) if draft else 0.0)
        return out

    def _measured(self, model_id: str) -> float | None:
        entry = self.registry.get(model_id)
        measured = getattr(entry, "measured", None)
        for name in ("ram_gb_live", "ram_gb_batch"):
            value = getattr(measured, name, None)
            if value is not None:
                return float(value)
        return None

    async def render(self, model_id: str, messages: list[dict]) -> str:
        """The prompt text the model's chat template makes of `messages` (POST /apply-template)."""
        self._reap()
        if model_id not in self._procs:
            raise RuntimeError(f"model not loaded: {model_id}")
        out = await self._post(f"{self.url_for(model_id)}/apply-template", {"messages": messages})
        prompt = out.get("prompt") if isinstance(out, dict) else None
        if not isinstance(prompt, str):
            raise RuntimeError(f"apply-template gave no prompt for {model_id}")
        return prompt


__all__ = ["LlamaServerDriver"]
