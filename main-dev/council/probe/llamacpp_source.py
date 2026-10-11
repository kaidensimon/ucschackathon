"""Real hidden states through the actdump tool (tap/actdump.cpp), for the deception probe.

What this source measures
- actdump loads a GGUF file with llama.cpp (an Ollama blob works as it is), runs one text
  through the model and returns the residual stream after each block ("l_out-<n>"), pooled
  over the tokens ("last" = the last token, "mean" = the average). These are true per-layer
  activations, unlike OllamaEmbedSource.
- The text is NOT the model's chat template. One user message (the probe layout of
  probe/layout.py, used for training and for live scoring) is sent as it is, with no role
  prefix: the text ends exactly with "The statement above is", and with pool="last" the vector
  sits on that last token. Several messages become plain "<role>: <content>" lines joined by
  newlines, ending with the content of the last message. A probe trained here must be scored
  on text rendered here.
- System messages are left out by default, the same rule OllamaEmbedSource follows: the
  bootstrap instruction ("you must deceive ...") would otherwise be what the probe learns,
  and live answers never carry it. Pass include_system=True to keep them.

Cost: each live actdump process holds its own full copy of the model, next to the copy Ollama
holds. At most `max_models` processes live at once; the least recently used is closed first.
Call close() when a batch of captures is done.
"""
from __future__ import annotations

import asyncio
import json
import math
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

POOLS = ("last", "mean")
STREAM_LIMIT = 1 << 28  # one reply line carries every layer: far above asyncio's 64 KiB default
STDERR_TAIL = 20
INFO_TIMEOUT_S = 600.0

Runner = Callable[[list[str]], Awaitable[Any]]


class ActivationError(RuntimeError):
    """The activation tool could not give the vectors that were asked for."""


def pick_layers(n_layer: int, k: int = 4) -> list[int]:
    """k layers evenly spaced through the middle half of the network (quarter to three quarters)."""
    n = int(n_layer)
    if n <= 0 or k <= 0:
        return []
    lo = n // 4
    hi = max(lo, min(n - 1, (3 * n) // 4))
    if k == 1:
        return [(lo + hi) // 2]
    return sorted({lo + round(i * (hi - lo) / (k - 1)) for i in range(k)})


def render_text(messages: list[dict], include_system: bool = False) -> str:
    """One user message: its content, unchanged. Otherwise plain "<role>: <content>" lines.
    Either way the text ends with the last message content."""
    rows = [m for m in messages if include_system or m.get("role") != "system"]
    if len(rows) == 1 and rows[0].get("role") == "user":
        return str(rows[0].get("content", ""))
    return "\n".join(f"{m.get('role', '')}: {m.get('content', '')}" for m in rows)


async def _default_runner(argv: list[str]) -> Any:
    return await asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, limit=STREAM_LIMIT)


class _Proc:
    """One live actdump process."""

    def __init__(self, model_id: str, proc: Any, loop: Any) -> None:
        self.model_id = model_id
        self.proc = proc
        self.loop = loop
        self.lock = asyncio.Lock()
        self.closed = False
        self.seq = 0
        self.stderr: deque[str] = deque(maxlen=STDERR_TAIL)
        self.drain_task: Optional[asyncio.Task] = None

    def stderr_tail(self) -> str:
        return " | ".join(self.stderr)


class LlamaCppActivationSource:
    """ActivationSource over one long-lived actdump process per model.

    No chat template is applied: see the module text for how messages become text.
    """

    def __init__(
        self,
        binary: Path,
        blob_for: Callable[[str], Optional[Path]],
        pool: str = "last",
        n_gpu_layers: int = 99,
        ctx: int = 4096,
        runner: Optional[Runner] = None,
        max_models: int = 1,
        timeout_s: float = 600.0,
        include_system: bool = False,
    ) -> None:
        if pool not in POOLS:
            raise ValueError(f"pool must be one of {POOLS}, not {pool!r}")
        self.binary = Path(binary).expanduser()
        self.blob_for = blob_for
        self.pool = pool
        self.n_gpu_layers = int(n_gpu_layers)
        self.ctx = int(ctx)
        self.max_models = max(1, int(max_models))
        self.timeout_s = float(timeout_s)
        self.include_system = bool(include_system)
        self._runner: Runner = runner or _default_runner
        self._procs: "OrderedDict[str, _Proc]" = OrderedDict()
        self._info: dict[str, dict] = {}
        self._manage: Optional[asyncio.Lock] = None
        self._manage_loop: Any = None

    # ------------------------------------------------------------------ paths and spawning

    def _model_path(self, model_id: str) -> Path:
        try:
            path = self.blob_for(model_id)
        except Exception as e:
            raise ActivationError(f"cannot find the model file for {model_id}: {e}") from e
        if path is None:
            raise ActivationError(f"no GGUF file for model {model_id} (is it pulled in Ollama?)")
        path = Path(path)
        if not path.is_file():
            raise ActivationError(f"model file for {model_id} is missing: {path}")
        return path

    def _argv(self, model_id: str) -> list[str]:
        model = self._model_path(model_id)
        if not self.binary.is_file():
            raise ActivationError(f"actdump binary is missing: {self.binary}")
        return [str(self.binary), "-m", str(model)]

    async def _spawn(self, model_id: str, argv: list[str]) -> Any:
        try:
            return await self._runner(argv)
        except ActivationError:
            raise
        except Exception as e:
            raise ActivationError(f"cannot start actdump for {model_id}: {e}") from e

    def _manage_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._manage is None or self._manage_loop is not loop:
            self._manage, self._manage_loop = asyncio.Lock(), loop
        return self._manage

    # ------------------------------------------------------------------ process life

    async def _drain_stderr(self, entry: _Proc) -> None:
        stream = getattr(entry.proc, "stderr", None)
        if stream is None:
            return
        try:
            while True:
                line = await stream.readline()
                if not line:
                    return
                text = line.decode("utf-8", "replace").strip()
                if text:
                    entry.stderr.append(text)
        except Exception:
            return

    async def _stop(self, entry: _Proc) -> None:
        """Terminate one process. The caller holds entry.lock or knows nobody else uses it."""
        if entry.closed:
            return
        entry.closed = True
        proc = entry.proc
        same_loop = entry.loop is asyncio.get_running_loop()
        try:
            stdin = getattr(proc, "stdin", None)
            if stdin is not None and same_loop:
                stdin.close()
        except Exception:
            pass
        try:
            if getattr(proc, "returncode", None) is None:
                proc.terminate()
        except Exception:
            pass
        if same_loop:
            try:
                await asyncio.wait_for(proc.wait(), 5.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            if entry.drain_task is not None:
                entry.drain_task.cancel()

    def _kill_now(self, entry: _Proc) -> None:
        """Kill without waiting. For a caller that is being cancelled and cannot await."""
        entry.closed = True
        try:
            if getattr(entry.proc, "returncode", None) is None:
                entry.proc.kill()
        except Exception:
            pass
        if entry.drain_task is not None:
            entry.drain_task.cancel()

    async def _evict(self, entry: _Proc) -> None:
        # The entry stays in the table until its process is stopped: a waiter cancelled here
        # (the scorer's timeout) must not leave a running model copy that close() cannot see.
        try:
            if entry.loop is asyncio.get_running_loop():
                async with entry.lock:  # wait for a request in flight
                    await self._stop(entry)
            else:  # left over from a loop that is gone: its pipes are dead
                await self._stop(entry)
        except asyncio.CancelledError:
            self._kill_now(entry)
            raise
        finally:
            if self._procs.get(entry.model_id) is entry:
                del self._procs[entry.model_id]

    async def _acquire(self, model_id: str) -> _Proc:
        """The live process for this model, started if needed, marked most recently used."""
        loop = asyncio.get_running_loop()
        async with self._manage_lock():
            entry = self._procs.get(model_id)
            if entry is not None and (entry.closed or entry.loop is not loop
                                      or getattr(entry.proc, "returncode", None) is not None):
                await self._evict(entry)
                entry = None
            if entry is None:
                argv = self._argv(model_id) + [
                    "--layers", "all", "--pool", self.pool,
                    "-ngl", str(self.n_gpu_layers), "-c", str(self.ctx)]
                while len(self._procs) >= self.max_models:
                    await self._evict(next(iter(self._procs.values())))
                proc = await self._spawn(model_id, argv)
                entry = _Proc(model_id, proc, loop)
                entry.drain_task = loop.create_task(self._drain_stderr(entry))
                self._procs[model_id] = entry
            self._procs.move_to_end(model_id)
            return entry

    async def _fail(self, entry: _Proc, message: str) -> ActivationError:
        """Drop a process that can no longer be trusted and build the error to raise."""
        await asyncio.sleep(0)  # let the stderr reader catch up
        code = getattr(entry.proc, "returncode", None)
        tail = entry.stderr_tail()
        if self._procs.get(entry.model_id) is entry:
            del self._procs[entry.model_id]
        await self._stop(entry)
        extra = (f" (exit code {code})" if code is not None else "") + (f": {tail}" if tail else "")
        return ActivationError(f"actdump for {entry.model_id} {message}{extra}")

    # ------------------------------------------------------------------ the protocol

    async def _ask(self, entry: _Proc, text: str) -> dict:
        entry.seq += 1
        rid = f"{entry.model_id}#{entry.seq}"
        line = json.dumps({"id": rid, "text": text}, ensure_ascii=False) + "\n"
        try:
            entry.proc.stdin.write(line.encode("utf-8"))
            await entry.proc.stdin.drain()
        except Exception as e:
            raise await self._fail(entry, f"died before the request was sent ({e})") from e
        try:
            raw = await asyncio.wait_for(entry.proc.stdout.readline(), self.timeout_s)
        except asyncio.TimeoutError:
            raise await self._fail(entry, f"gave no reply in {self.timeout_s:g} s") from None
        except Exception as e:
            raise await self._fail(entry, f"reply could not be read ({e})") from e
        if not raw:
            raise await self._fail(entry, "died (no reply)")
        try:
            reply = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            raise await self._fail(entry, "sent a reply that is not JSON") from None
        if not isinstance(reply, dict) or reply.get("id") != rid:
            raise await self._fail(entry, "sent a reply for another request")
        return reply

    async def capture(
        self, model_id: str, messages: list[dict], layers: list[int]
    ) -> dict[int, list[float]]:
        text = render_text(messages, self.include_system)
        if not text:
            raise ActivationError(f"nothing to run for {model_id}: no message text")
        while True:
            entry = await self._acquire(model_id)
            async with entry.lock:
                if entry.closed:  # evicted while this request waited: start again
                    continue
                try:
                    reply = await self._ask(entry, text)
                except asyncio.CancelledError:
                    # Cancelled mid-request (the caller's timeout): the reply still to come would
                    # answer the NEXT request. This process cannot be used again.
                    if self._procs.get(entry.model_id) is entry:
                        del self._procs[entry.model_id]
                    self._kill_now(entry)
                    raise
            break
        if reply.get("error"):
            raise ActivationError(f"actdump for {model_id}: {reply['error']}")
        got = reply.get("layers")
        if not isinstance(got, dict):
            raise ActivationError(f"actdump for {model_id}: reply has no layers")
        out: dict[int, list[float]] = {}
        for layer in layers:
            vec = got.get(str(int(layer)))
            if vec is None:
                have = sorted(int(k) for k in got)
                span = f"{have[0]}..{have[-1]}" if have else "none"
                raise ActivationError(
                    f"actdump for {model_id}: layer {layer} not in the reply (layers {span})")
            try:
                vals = [float(x) for x in vec]
            except (TypeError, ValueError):
                raise ActivationError(
                    f"actdump for {model_id}: layer {layer} holds a value that is not a number"
                ) from None
            if not vals or not all(math.isfinite(v) for v in vals):
                raise ActivationError(
                    f"actdump for {model_id}: layer {layer} is empty or not finite")
            out[int(layer)] = vals
        return out

    async def info(self, model_id: str) -> dict:
        """{"n_layer", "n_embd", "architecture"} from `actdump --info`. Cached per model."""
        if model_id in self._info:
            return dict(self._info[model_id])
        # -ngl 0: only the header is wanted, so nothing is put on the GPU.
        argv = self._argv(model_id) + ["--info", "-ngl", "0"]
        proc = await self._spawn(model_id, argv)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), INFO_TIMEOUT_S)
        except Exception as e:
            try:
                proc.kill()
            except Exception:
                pass
            raise ActivationError(f"actdump --info for {model_id} failed: {e!r}") from e
        text = (out or b"").decode("utf-8", "replace")
        data = None
        for line in reversed(text.splitlines()):
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if isinstance(data, dict) and "n_layer" in data:
                break
            data = None
        if data is None:
            tail = (err or b"").decode("utf-8", "replace").strip().splitlines()[-3:]
            code = getattr(proc, "returncode", None)
            raise ActivationError(
                f"actdump --info for {model_id} gave no answer (exit code {code})"
                + (": " + " | ".join(tail) if tail else ""))
        try:
            info = {"n_layer": int(data["n_layer"]), "n_embd": int(data.get("n_embd", 0)),
                    "architecture": str(data.get("architecture", ""))}
        except (TypeError, ValueError):
            raise ActivationError(f"actdump --info for {model_id}: bad answer {data!r}") from None
        self._info[model_id] = info
        return dict(info)

    async def close(self, model_id: Optional[str] = None) -> None:
        """Terminate the process of one model, or of every model."""
        async with self._manage_lock():
            if model_id is None:
                entries = list(self._procs.values())
            else:
                entries = [self._procs[model_id]] if model_id in self._procs else []
            for entry in entries:
                await self._evict(entry)

    def alive(self) -> list[str]:
        """Model ids with a live process, least recently used first."""
        return list(self._procs)


__all__ = ["ActivationError", "LlamaCppActivationSource", "pick_layers", "render_text"]
