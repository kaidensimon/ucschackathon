"""Embedders (spec 27): text in, vectors out. Every model runs locally through Ollama.

Contract for all embedders:
- embed([]) returns [].
- embed(texts) returns one vector per text, in order.
- Never raises. A failed batch returns zero vectors of the right count.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

import httpx

from council.chronicle.recall import keyword_embedding

_DEFAULT_DIM = 64
_OPENAI_TIMEOUT_S = 60.0


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def _zeros(count: int, dim: int) -> list[list[float]]:
    return [[0.0] * dim for _ in range(count)]


def _valid_batch(vectors: Any, count: int) -> Optional[list[list[float]]]:
    """Return the vectors as lists of floats when shape matches, else None."""
    if not isinstance(vectors, list) or len(vectors) != count:
        return None
    out: list[list[float]] = []
    dim: Optional[int] = None
    for vec in vectors:
        if not isinstance(vec, list) or not vec:
            return None
        if dim is None:
            dim = len(vec)
        elif len(vec) != dim:
            return None
        try:
            out.append([float(x) for x in vec])
        except (TypeError, ValueError):
            return None
    return out


class MockEmbedder:
    """Deterministic hashed bag-of-words vectors. No model server needed."""

    def __init__(self, dim: int = _DEFAULT_DIM) -> None:
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            return [keyword_embedding(str(t), self.dim) for t in texts]
        except Exception:
            return _zeros(len(texts), max(self.dim, 0))


class OllamaEmbedder:
    """Calls an Ollama client exposing `async embed(model_tag, inputs)`.

    Accepts either a plain list of vectors or a dict with an "embeddings" key
    (the shape Ollama's /api/embed returns).
    """

    def __init__(self, client: Any, model_tag: str, dim: int = _DEFAULT_DIM) -> None:
        self.client = client
        self.model_tag = model_tag
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        inputs = [str(t) for t in texts]
        try:
            raw = await self.client.embed(self.model_tag, inputs)
            if isinstance(raw, dict):
                raw = raw.get("embeddings")
            vectors = _valid_batch(raw, len(inputs))
            if vectors is None:
                return _zeros(len(inputs), self.dim)
            self.dim = len(vectors[0])
            return vectors
        except Exception:
            return _zeros(len(inputs), self.dim)


class OpenAIEmbedder:
    """POST {base_url}/v1/embeddings (OpenAI-compatible, e.g. Ollama's OpenAI endpoint).

    If `client` is None, a short-lived httpx.AsyncClient is made per call.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        client: Optional[httpx.AsyncClient] = None,
        dim: int = _DEFAULT_DIM,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = client
        self.dim = dim

    @property
    def url(self) -> str:
        return f"{self.base_url}/v1/embeddings"

    async def _post(self, payload: dict[str, Any]) -> Any:
        if self.client is not None:
            resp = await self.client.post(self.url, json=payload, timeout=_OPENAI_TIMEOUT_S)
        else:
            async with httpx.AsyncClient(timeout=_OPENAI_TIMEOUT_S) as client:
                resp = await client.post(self.url, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        inputs = [str(t) for t in texts]
        try:
            body = await self._post({"model": self.model, "input": inputs})
            data = body.get("data") if isinstance(body, dict) else None
            if not isinstance(data, list):
                return _zeros(len(inputs), self.dim)
            ordered = sorted(
                (d for d in data if isinstance(d, dict)),
                key=lambda d: d.get("index", 0) if isinstance(d.get("index"), int) else 0,
            )
            vectors = _valid_batch([d.get("embedding") for d in ordered], len(inputs))
            if vectors is None:
                return _zeros(len(inputs), self.dim)
            self.dim = len(vectors[0])
            return vectors
        except Exception:
            return _zeros(len(inputs), self.dim)
