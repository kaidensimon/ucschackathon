"""llama.cpp llama-server chat client (OpenAI-compatible API). Same surface as OllamaClient.

POST <base>/v1/chat/completions. Never raises from chat: failures become CallResult.error.
Speed comes from the "timings" object llama-server returns. When speculative decoding is on,
draft_n / draft_n_accepted land in result.extra (CallResult has no meta dict, so the result is a
CallResult subclass that adds one; isinstance(result, CallResult) holds).

optional_fields are best-effort request fields (thinking switches). If the server answers 4xx
with them in the body, the call is sent once more without them.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Callable, Optional

import httpx

from council.core.schemas import CallResult, CallSpec

_PROMPT_JSON_LINE = "Reply with one JSON object only. No prose, no code fences."


class _HttpStatus(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(str(code))
        self.code = code


def thinking_fields(level: str) -> dict[str, Any]:
    """Best-effort llama-server fields for a council reasoning level.

    off: the chat template is asked not to think (needs --jinja; other templates ignore it).
    council / max: thinking stays on and comes back as "reasoning_content".
    """
    if level == "off":
        return {"chat_template_kwargs": {"enable_thinking": False}}
    return {"chat_template_kwargs": {"enable_thinking": True}, "reasoning_format": "deepseek"}


class LlamaCppCallResult(CallResult):
    """CallResult plus an `extra` dict: predicted_n, prompt_n, draft_n, draft_n_accepted, accept_rate."""

    extra: dict[str, Any] = {}


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


def _extra_from_timings(timings: dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("predicted_n", "prompt_n", "draft_n", "draft_n_accepted"):
        if key in timings and timings[key] is not None:
            out[key] = _int(timings[key])
    drafted = out.get("draft_n", 0)
    if drafted > 0:
        out["accept_rate"] = out.get("draft_n_accepted", 0) / drafted
    return out


class LlamaCppClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8080", client: Optional[httpx.AsyncClient] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client

    # ------------------------------------------------------------------ helpers

    def _body(
        self, spec: CallSpec, extra_fields: Optional[dict], mode: str, model_tag: Optional[str],
        options: Optional[dict] = None, optional_fields: Optional[dict] = None,
    ) -> dict[str, Any]:
        messages = copy.deepcopy(spec.messages)
        cap = spec.max_output_tokens
        if spec.max_reasoning_tokens:
            cap += spec.max_reasoning_tokens
        body: dict[str, Any] = {
            "model": model_tag or spec.model_id,
            "messages": messages,
            "max_tokens": cap,
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
        if optional_fields:
            body.update(copy.deepcopy(optional_fields))
        if extra_fields:
            body.update(extra_fields)  # the model card wins over the best-effort fields
        if options:
            body.update(options)  # llama-server sampling knobs (top_k, min_p, ...) sit at the top level
        return body

    def _fail(self, spec: CallSpec, error: str) -> LlamaCppCallResult:
        return LlamaCppCallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id, error=error)  # type: ignore[arg-type]

    def _finish(
        self,
        spec: CallSpec,
        content: str,
        reasoning: str,
        finish_reason: Optional[str],
        usage: dict,
        timings: dict,
    ) -> LlamaCppCallResult:
        if not (content or "").strip() and reasoning and "{" in reasoning and "}" in reasoning:
            # A model that keeps its whole reply in its thinking channel (gpt-oss asked for JSON):
            # the JSON object is in there. Use it as the reply so the call is not lost.
            content = reasoning[reasoning.index("{"): reasoning.rindex("}") + 1]
        tokens_in = _int(usage.get("prompt_tokens")) or _int(timings.get("prompt_n"))
        tokens_out = _int(usage.get("completion_tokens")) or _int(timings.get("predicted_n"))
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
        return LlamaCppCallResult(
            call_id=spec.call_id,
            ok=True,
            model_id=spec.model_id,
            content=content,
            parsed=parsed,
            reasoning_text=reasoning or None,
            finish_reason=finish_reason,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_reasoning=tokens_reasoning,
            prompt_ms=prompt_ms,
            gen_ms=gen_ms,
            tps=tps,
            extra=_extra_from_timings(timings),
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
        optional_fields: Optional[dict] = None,
    ) -> CallResult:
        owns = self._client is None
        client = self._client or httpx.AsyncClient()
        try:
            url = f"{self.base_url}/v1/chat/completions"
            timeout = httpx.Timeout(spec.timeout_s)
            tries = [optional_fields, None] if optional_fields else [None]
            for i, optional in enumerate(tries):
                body = self._body(spec, extra_fields, mode, model_tag, options, optional)
                try:
                    if spec.stream:
                        return await self._stream(client, url, body, timeout, spec, on_delta)
                    return await self._once(client, url, body, timeout, spec)
                except _HttpStatus as status:
                    # 4xx before any token: the server may not know the optional fields.
                    if not (400 <= status.code < 500) or i == len(tries) - 1:
                        break
            return self._fail(spec, "server_error")
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
            raise _HttpStatus(resp.status_code)
        try:
            data = resp.json()
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            usage = data.get("usage") or {}
            timings = data.get("timings") or {}
            if not isinstance(usage, dict) or not isinstance(timings, dict):
                return self._fail(spec, "server_error")
        except (ValueError, AttributeError, IndexError, TypeError):
            return self._fail(spec, "server_error")
        return self._finish(
            spec,
            message.get("content") or "",
            message.get("reasoning_content") or "",
            choice.get("finish_reason"),
            usage,
            timings,
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
                raise _HttpStatus(resp.status_code)
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
