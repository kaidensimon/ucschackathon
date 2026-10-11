"""OpenAI-compatible chat client (spec 6.1, 7.1, 7.4). Never raises: failures become CallResult.error."""

from __future__ import annotations

import copy
import json
from typing import Any, Callable, Optional

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


class OpenAIClient:
    def __init__(self, base_url: str, client: Optional[httpx.AsyncClient] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client

    # ------------------------------------------------------------------ helpers

    def _body(self, spec: CallSpec, extra_fields: Optional[dict], mode: str) -> dict[str, Any]:
        messages = copy.deepcopy(spec.messages)
        body: dict[str, Any] = {
            "model": spec.model_id,
            "messages": messages,
            "max_tokens": spec.max_output_tokens,
            "stream": bool(spec.stream),
        }
        if spec.temperature is not None:
            body["temperature"] = spec.temperature
        if spec.top_p is not None:
            body["top_p"] = spec.top_p
        if spec.seed is not None:
            body["seed"] = spec.seed
        if spec.json_schema:
            if mode == "grammar":
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "out", "schema": spec.json_schema, "strict": True},
                }
            elif mode == "prompt":
                messages.append({"role": "system", "content": _PROMPT_JSON_LINE})
        if extra_fields:
            body.update(extra_fields)
        return body

    def _fail(self, spec: CallSpec, error: str) -> CallResult:
        return CallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id, error=error)  # type: ignore[arg-type]

    def _finish(
        self,
        spec: CallSpec,
        content: str,
        reasoning: str,
        finish_reason: Optional[str],
        usage: dict,
        timings: dict,
    ) -> CallResult:
        tokens_out = _int(usage.get("completion_tokens"))
        details = usage.get("completion_tokens_details") or {}
        tokens_reasoning = _int(details.get("reasoning_tokens")) if isinstance(details, dict) else 0
        prompt_ms = _num(timings.get("prompt_ms"))
        gen_ms = _num(timings.get("predicted_ms"))
        tps = _num(timings.get("predicted_per_second"))
        if not tps and gen_ms > 0 and tokens_out:
            tps = tokens_out / (gen_ms / 1000.0)
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
            finish_reason=finish_reason,
            tokens_in=_int(usage.get("prompt_tokens")),
            tokens_out=tokens_out,
            tokens_reasoning=tokens_reasoning,
            prompt_ms=prompt_ms,
            gen_ms=gen_ms,
            tps=tps,
        )

    # ------------------------------------------------------------------ public

    async def chat(
        self,
        spec: CallSpec,
        extra_fields: Optional[dict] = None,
        mode: str = "grammar",
        on_delta: Optional[Callable[[str, str], None]] = None,
    ) -> CallResult:
        owns = self._client is None
        client = self._client or httpx.AsyncClient()
        try:
            body = self._body(spec, extra_fields, mode)
            url = f"{self.base_url}/v1/chat/completions"
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
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
        except (ValueError, AttributeError, IndexError, TypeError):
            return self._fail(spec, "server_error")
        return self._finish(
            spec,
            message.get("content") or "",
            message.get("reasoning_content") or "",
            choice.get("finish_reason"),
            data.get("usage") or {},
            data.get("timings") or {},
        )

    async def _stream(self, client, url, body, timeout, spec, on_delta) -> CallResult:
        content: list[str] = []
        reasoning: list[str] = []
        finish: Optional[str] = None
        usage: dict = {}
        timings: dict = {}
        async with client.stream("POST", url, json=body, timeout=timeout) as resp:
            if resp.status_code >= 400:
                await resp.aread()
                return self._fail(spec, "server_error")
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                if not payload:
                    continue
                try:
                    chunk = json.loads(payload)
                except ValueError:
                    continue
                if not isinstance(chunk, dict):
                    continue
                if isinstance(chunk.get("usage"), dict):
                    usage = chunk["usage"]
                if isinstance(chunk.get("timings"), dict):
                    timings = chunk["timings"]
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    r = delta.get("reasoning_content")
                    if r:
                        reasoning.append(r)
                        if on_delta:
                            on_delta("reasoning", r)
                    c = delta.get("content")
                    if c:
                        content.append(c)
                        if on_delta:
                            on_delta("content", c)
                    if choice.get("finish_reason"):
                        finish = choice["finish_reason"]
        return self._finish(spec, "".join(content), "".join(reasoning), finish, usage, timings)
