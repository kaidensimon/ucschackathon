"""Ollama host driver (spec 6.1): load and unload through the Ollama API."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

import httpx

from council.core.schemas import ModelEntry


def _norm_tag(tag: str) -> str:
    tag = str(tag).strip()
    return tag if ":" in tag.rsplit("/", 1)[-1] else f"{tag}:latest"


async def _default_runner(args: list[str]) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    out, _ = await proc.communicate()
    return proc.returncode or 0, out.decode("utf-8", "replace")



def _keep_alive(value):
    """Ollama wants a number of seconds or a duration with a unit; "-1" as text is rejected."""
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return value
    return value

class OllamaDriver:
    """Drives a local Ollama server. Satisfies the HostDriver protocol."""

    def __init__(
        self,
        base_url: str,
        registry: list[ModelEntry],
        client: httpx.AsyncClient | None = None,
        keep_alive: str | int = -1,
        num_ctx: dict[str, int] | None = None,
        runner: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.registry = list(registry)
        self._client = client
        self._own_client = client is None
        self.keep_alive = _keep_alive(keep_alive)
        self.num_ctx = dict(num_ctx or {})
        self._runner = runner or _default_runner
        self._installed: set[str] = set()
        self._by_id = {m.id: m for m in self.registry}

    # ---- plumbing ----

    def _c(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=600.0)
            self._own_client = True
        return self._client

    async def start(self) -> None:
        r = await self._c().get(f"{self.base_url}/api/tags")
        r.raise_for_status()
        body = r.json()
        self._installed = {
            _norm_tag(m.get("name") or m.get("model"))
            for m in (body.get("models") or [])
            if isinstance(m, dict) and (m.get("name") or m.get("model"))
        }

    async def stop(self) -> None:
        if self._client is not None and self._own_client:
            await self._client.aclose()
            self._client = None

    # ---- tags ----

    def _entry(self, model_id: str) -> ModelEntry:
        try:
            return self._by_id[model_id]
        except KeyError:
            raise KeyError(f"unknown model id: {model_id}") from None

    def _base_tag(self, model_id: str) -> str:
        tag = self._entry(model_id).ollama_tag
        if not tag:
            raise ValueError(f"model {model_id} has no ollama_tag")
        return tag

    def tag_for(self, model_id: str) -> str:
        return self._base_tag(model_id)

    def missing_tags(self) -> list[str]:
        out: list[str] = []
        for m in self.registry:
            if m.ollama_tag and _norm_tag(m.ollama_tag) not in self._installed:
                if m.ollama_tag not in out:
                    out.append(m.ollama_tag)
        return out

    # ---- load / unload / status ----

    async def _running(self) -> set[str]:
        r = await self._c().get(f"{self.base_url}/api/ps")
        r.raise_for_status()
        body = r.json()
        return {
            _norm_tag(m.get("name") or m.get("model"))
            for m in (body.get("models") or [])
            if isinstance(m, dict) and (m.get("name") or m.get("model"))
        }

    async def footprints(self) -> dict[str, float]:
        """GiB each loaded model occupies, as Ollama reports it (weights plus context)."""
        r = await self._c().get(f"{self.base_url}/api/ps")
        r.raise_for_status()
        by_tag = {
            _norm_tag(m.get("name") or m.get("model")): float(m.get("size") or 0) / 2**30
            for m in (r.json().get("models") or [])
            if isinstance(m, dict) and (m.get("name") or m.get("model"))
        }
        return {
            m.id: by_tag[_norm_tag(self.tag_for(m.id))]
            for m in self.registry
            if m.ollama_tag and _norm_tag(self.tag_for(m.id)) in by_tag
        }

    async def load(self, model_id: str, profile: str) -> str:
        tag = self.tag_for(model_id)
        if _norm_tag(tag) not in self._installed:
            # Not started yet, or pulled since the last look: ask Ollama again before refusing.
            await self.start()
        if _norm_tag(tag) not in self._installed:
            raise RuntimeError(
                f"ollama tag not installed: {tag} (model {model_id}); run: ollama pull {tag}"
            )
        entry = self._entry(model_id)
        ctx = self.num_ctx.get(profile)
        if ctx is None:
            sp = getattr(entry.serve, profile, None)
            if sp is None:
                raise ValueError(f"unknown profile: {profile}")
            ctx = sp.ctx
        payload = {
            "model": tag,
            "keep_alive": self.keep_alive,
            "options": {"num_ctx": int(ctx)},
        }
        r = await self._c().post(f"{self.base_url}/api/generate", json=payload)
        r.raise_for_status()
        if _norm_tag(tag) not in await self._running():
            raise RuntimeError(f"ollama did not report {tag} loaded (model {model_id})")
        return self.base_url

    async def unload(self, model_id: str) -> None:
        r = await self._c().post(
            f"{self.base_url}/api/generate",
            json={"model": self.tag_for(model_id), "keep_alive": 0},
        )
        r.raise_for_status()

    async def status(self) -> dict[str, str]:
        running = await self._running()
        out: dict[str, str] = {}
        for m in self.registry:
            if not m.ollama_tag:
                continue
            out[m.id] = "loaded" if _norm_tag(self.tag_for(m.id)) in running else "unloaded"
        return out
