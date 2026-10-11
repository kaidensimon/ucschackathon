"""Host drivers (spec 6.1): one interface over the model runtime."""

from __future__ import annotations

import asyncio
import inspect
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx

from council.core.schemas import ModelEntry


@runtime_checkable
class HostDriver(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def load(self, model_id: str, profile: str) -> str:
        """Block until the model is served. Return the endpoint URL."""
        ...

    async def unload(self, model_id: str) -> None: ...

    async def status(self) -> dict[str, str]: ...


class MockDriver:
    """In-memory driver for tests and dry runs."""

    def __init__(self, load_delay_s: float = 0.0, fail: set[str] | None = None) -> None:
        self.load_delay_s = load_delay_s
        self.fail: set[str] = set(fail or ())
        self.started = False
        self._state: dict[str, str] = {}
        self.profiles: dict[str, str] = {}

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False
        self._state.clear()
        self.profiles.clear()

    async def load(self, model_id: str, profile: str) -> str:
        if model_id in self.fail:
            self._state[model_id] = "failed"
            raise RuntimeError(f"mock load failed: {model_id}")
        self._state[model_id] = "loading"
        if self.load_delay_s > 0:
            await asyncio.sleep(self.load_delay_s)
        self._state[model_id] = "loaded"
        self.profiles[model_id] = profile
        return f"mock://{model_id}"

    async def unload(self, model_id: str) -> None:
        self._state[model_id] = "unloaded"
        self.profiles.pop(model_id, None)

    async def status(self) -> dict[str, str]:
        return dict(self._state)


_KNOWN = {"unloaded", "loading", "loaded", "failed"}


def _norm_status(raw: Any) -> str:
    if isinstance(raw, dict):
        raw = raw.get("value") or raw.get("status") or raw.get("state")
    s = str(raw or "unloaded").lower()
    return s if s in _KNOWN else "unloaded"


class LlamaRouterDriver:
    """Drives one llama-server in router mode over HTTP."""

    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        poll_s: float = 0.5,
        load_timeout_s: float = 300,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client
        self._own_client = client is None
        self.poll_s = poll_s
        self.load_timeout_s = load_timeout_s

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
            self._own_client = True

    async def stop(self) -> None:
        if self._client is not None and self._own_client:
            await self._client.aclose()
            self._client = None

    def _c(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
            self._own_client = True
        return self._client

    async def load(self, model_id: str, profile: str) -> str:
        c = self._c()
        r = await c.post(f"{self.base_url}/models/load", json={"model": model_id})
        r.raise_for_status()
        deadline = time.monotonic() + self.load_timeout_s
        while True:
            st = (await self.status()).get(model_id, "unloaded")
            if st == "loaded":
                return self.base_url
            if st == "failed":
                raise RuntimeError(f"model failed to load: {model_id}")
            if time.monotonic() >= deadline:
                raise TimeoutError(f"load timeout for {model_id} after {self.load_timeout_s}s")
            await asyncio.sleep(self.poll_s)

    async def unload(self, model_id: str) -> None:
        r = await self._c().post(f"{self.base_url}/models/unload", json={"model": model_id})
        r.raise_for_status()

    async def status(self) -> dict[str, str]:
        r = await self._c().get(f"{self.base_url}/models")
        r.raise_for_status()
        body = r.json()
        items = body.get("data", body.get("models", [])) if isinstance(body, dict) else body
        out: dict[str, str] = {}
        for it in items or []:
            if not isinstance(it, dict):
                continue
            mid = it.get("id") or it.get("name") or it.get("model")
            if mid:
                out[str(mid)] = _norm_status(it.get("status"))
        return out


def write_preset_ini(
    registry: list[ModelEntry], models_dir: Path, profile: str, out: Path
) -> None:
    """Write a llama-server preset INI, one section per model."""
    lines: list[str] = ["version = 1", ""]
    for m in registry:
        sp = getattr(m.serve, profile, None)
        if sp is None:
            raise ValueError(f"unknown profile: {profile}")
        path = Path(models_dir) / m.source.file
        lines.append(f"[{m.id}]")
        lines.append(f"model = {path.as_posix()}")
        lines.append(f"ctx-size = {sp.ctx}")
        lines.append(f"parallel = {sp.parallel}")
        lines.append("")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def _accepted(fn: Any, offered: dict[str, Any]) -> dict[str, Any]:
    """The offered keyword arguments fn takes (all of them when it takes **kwargs)."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {}
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return dict(offered)
    return {k: v for k, v in offered.items() if k in params}


def _llamacpp_driver(config: Any, registry: list[ModelEntry]) -> Any:
    """One llama-server per model, each on the GGUF blob Ollama pulled for its tag."""
    from council.host import ollama_blobs
    from council.host.llamacpp_server import LlamaServerDriver

    lc = getattr(config, "llamacpp", None)
    models_dir = ollama_blobs.models_dir_from(getattr(lc, "ollama_models_dir", ""))
    blob_for = ollama_blobs.resolver(models_dir)
    from_config = getattr(LlamaServerDriver, "from_config", None)
    if from_config is not None:
        offered = {
            "config": config, "cfg": config, "registry": registry, "blob_for": blob_for,
            "models_dir": models_dir, "ollama_models_dir": models_dir,
        }
        kwargs = _accepted(from_config, offered)
        try:
            return from_config(**kwargs) if "registry" in kwargs else from_config(config, registry)
        except TypeError:
            pass  # another signature than expected: build it by hand below
    offered = {
        "server_bin": Path(str(getattr(lc, "server_bin", "") or "llama-server")).expanduser(),
        "base_port": int(getattr(lc, "base_port", 18100)),
        "ctx": int(getattr(lc, "ctx", 8192)),
        "parallel": int(getattr(lc, "parallel", 1)),
        "extra_args": list(getattr(lc, "extra_args", []) or []),
        "health_timeout_s": float(getattr(lc, "health_timeout_s", 240)),
    }
    driver = LlamaServerDriver(registry, blob_for, **_accepted(LlamaServerDriver.__init__, offered))
    driver.health_timeout_s = offered["health_timeout_s"]
    return driver


def build_driver(config: Any, registry: list[ModelEntry]) -> Any:
    """Pick the host driver from config. Mock whenever gateway.mock is set."""
    if config.gateway.mock or config.host.driver == "mock":
        return MockDriver()
    if config.host.driver == "llamacpp":
        return _llamacpp_driver(config, registry)
    if config.host.driver == "ollama":
        from council.host.ollama_driver import OllamaDriver

        oc = config.ollama
        ka: Any = oc.keep_alive
        try:
            ka = int(ka)
        except (TypeError, ValueError):
            pass
        return OllamaDriver(
            oc.base_url,
            registry,
            keep_alive=ka,
            num_ctx={"live": oc.num_ctx_live, "batch": oc.num_ctx_batch},
        )
    return LlamaRouterDriver("http://127.0.0.1:8080")
