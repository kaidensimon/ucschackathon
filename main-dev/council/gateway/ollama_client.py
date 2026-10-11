"""Native Ollama chat client (spec 6.1, 27). Same surface as OpenAIClient. Never raises from chat."""

from __future__ import annotations

import copy
import json
from typing import Any, Callable, Optional, Union

import httpx

from council.core.schemas import CallResult, CallSpec

_PROMPT_JSON_LINE = "Reply with one JSON object only. No prose, no code fences."


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _logprobs(raw: Any) -> Optional[list[float]]:
    if not isinstance(raw, list) or not raw:
        return None
    out: list[float] = []
    for item in raw:
        if isinstance(item, dict):
            item = item.get("logprob")
        try:
            out.append(float(item))
        except (TypeError, ValueError):
            continue
    return out or None



def _keep_alive(value):
    """Ollama wants a number of seconds or a duration with a unit; "-1" as text is rejected."""
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return value
    return value

class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        client: Optional[httpx.AsyncClient] = None,
        keep_alive: Union[str, int] = -1,
        num_ctx: Optional[int] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client
        self.keep_alive = _keep_alive(keep_alive)
        self.num_ctx = num_ctx

    # ------------------------------------------------------------------ helpers

    def _body(
        self, spec: CallSpec, extra_fields: Optional[dict], mode: str, model_tag: Optional[str],
        extra_options: Optional[dict] = None,
    ) -> dict[str, Any]:
        messages = copy.deepcopy(spec.messages)
        cap = spec.max_output_tokens
        if spec.max_reasoning_tokens:
            cap += spec.max_reasoning_tokens
        options: dict[str, Any] = {"num_predict": cap}
        if spec.temperature is not None:
            options["temperature"] = spec.temperature
        if spec.top_p is not None:
            options["top_p"] = spec.top_p
        if spec.seed is not None:
            options["seed"] = spec.seed
        if self.num_ctx:
            options["num_ctx"] = self.num_ctx
        body: dict[str, Any] = {
            "model": model_tag or spec.model_id,
            "messages": messages,
            "stream": bool(spec.stream),
            "options": options,
            "keep_alive": self.keep_alive,
            "logprobs": True,
        }
        if spec.json_schema:
            if mode == "grammar":
                body["format"] = spec.json_schema
            elif mode == "prompt":
                messages.append({"role": "system", "content": _PROMPT_JSON_LINE})
        if extra_fields:
            extra = dict(extra_fields)
            if "think" in extra:
                body["think"] = extra.pop("think")
            body.update(extra)
        if extra_options:
            body["options"] = {**(body.get("options") or {}), **extra_options}  # merged last
        return body

    def _fail(self, spec: CallSpec, error: str) -> CallResult:
        return CallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id, error=error)  # type: ignore[arg-type]

    def _finish(
        self,
        spec: CallSpec,
        content: str,
        reasoning: str,
        final: dict,
        logprobs: Optional[list[float]],
    ) -> CallResult:
        tokens_out = _int(final.get("eval_count"))
        prompt_ms = _num(final.get("prompt_eval_duration")) / 1e6
        gen_ms = _num(final.get("eval_duration")) / 1e6
        tps = tokens_out / (gen_ms / 1000.0) if gen_ms > 0 and tokens_out else 0.0
        parsed = None
        if spec.json_schema and content:
            try:
                parsed = json.loads(content)
            except ValueError:
                parsed = None
        return CallResult(
            call_id=spec.call_id,
            ok=True,
            model_id=spec.model_id,
            content=content,
            parsed=parsed,
            reasoning_text=reasoning or None,
            finish_reason=final.get("done_reason"),
            tokens_in=_int(final.get("prompt_eval_count")),
            tokens_out=tokens_out,
            tokens_reasoning=0,
            prompt_ms=prompt_ms,
            gen_ms=gen_ms,
            tps=tps,
            logprobs=logprobs,
        )

    # ------------------------------------------------------------------ public

    async def chat(
        self,
        spec: CallSpec,
        extra_fields: Optional[dict] = None,
        mode: str = "grammar",
        on_delta: Optional[Callable[[str, str], None]] = None,
        model_tag: Optional[str] = None,
        options: Optional[dict] = None,
    ) -> CallResult:
        owns = self._client is None
        client = self._client or httpx.AsyncClient()
        try:
            body = self._body(spec, extra_fields, mode, model_tag, options)
            url = f"{self.base_url}/api/chat"
            timeout = httpx.Timeout(spec.timeout_s)
            if spec.stream:
                return await self._stream(client, url, body, timeout, spec, on_delta)
            return await self._once(client, url, body, timeout, spec)
        except httpx.TimeoutException:
            return self._fail(spec, "timeout")
        except (httpx.HTTPError, OSError):
            return self._fail(spec, "server_error")
        except Exception:
            return self._fail(spec, "server_error")
        finally:
            if owns:
                try:
                    await client.aclose()
                except Exception:
                    pass

    async def _once(self, client, url, body, timeout, spec) -> CallResult:
        resp = await client.post(url, json=body, timeout=timeout)
        if resp.status_code >= 400:
            return self._fail(spec, "server_error")
        try:
            data = resp.json()
            message = data.get("message") or {}
            content = message.get("content") or ""
            thinking = message.get("thinking") or ""
        except (ValueError, AttributeError, TypeError):
            return self._fail(spec, "server_error")
        lp = _logprobs(data.get("logprobs") or message.get("logprobs"))
        return self._finish(spec, content, thinking, data, lp)

    async def _stream(self, client, url, body, timeout, spec, on_delta) -> CallResult:
        content: list[str] = []
        reasoning: list[str] = []
        lps: list[float] = []
        final: dict = {}
        async with client.stream("POST", url, json=body, timeout=timeout) as resp:
            if resp.status_code >= 400:
                await resp.aread()
                return self._fail(spec, "server_error")
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(chunk, dict):
                    continue
                message = chunk.get("message") or {}
                if not isinstance(message, dict):
                    message = {}
                r = message.get("thinking")
                if r:
                    reasoning.append(r)
                    if on_delta:
                        on_delta("reasoning", r)
                c = message.get("content")
                if c:
                    content.append(c)
                    if on_delta:
                        on_delta("content", c)
                got = _logprobs(chunk.get("logprobs") or message.get("logprobs"))
                if got:
                    lps.extend(got)
                if chunk.get("done"):
                    final = chunk
                    break
        return self._finish(spec, "".join(content), "".join(reasoning), final, lps or None)

    async def embed(self, model_tag: str, inputs: list[str]) -> list[list[float]]:
        owns = self._client is None
        client = self._client or httpx.AsyncClient()
        try:
            resp = await client.post(
                f"{self.base_url}/api/embed",
                json={"model": model_tag, "input": list(inputs), "keep_alive": self.keep_alive},
                timeout=httpx.Timeout(60.0),
            )
            resp.raise_for_status()
            vectors = resp.json().get("embeddings") or []
            return [[float(x) for x in v] for v in vectors]
        finally:
            if owns:
                try:
                    await client.aclose()
                except Exception:
                    pass
