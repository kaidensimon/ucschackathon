"""Gateway (spec 7): every model call is a CallSpec in and a CallResult out.

Order of one call: cache lookup -> governor slot -> turn.started -> structured ladder
(mock responder, llama-server client, Ollama client or OpenAI client, by config.host.driver)
under the timeout -> turn.completed / turn.invalid / turn.timeout -> turns table -> counters ->
cache store.

Driver "llamacpp": one llama-server per model. endpoint_for(model_id) gives its base URL for
every call (the host may restart a model on another port). Driver "ollama" is the fallback.
Every real call first passes the context guard: messages that overflow the model's context are
cut in the middle, so the system prompt and the question survive.

call() returns a CallResult for every failure. The one exception is task cancellation:
the turn is recorded as "cancelled" and CancelledError is re-raised so asyncio keeps working.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from typing import Any, Callable, Optional

from council.core import event_types as ev
from council.core.schemas import CallResult, CallSpec, ModelEntry
from council.gateway import ctx_guard
from council.gateway import reasoning as reasoning_mod
from council.gateway.cache import CallCache
from council.gateway.governor import Governor
from council.gateway.structured import run_ladder

_TPS_SAMPLES = 20
_TPS_WINDOW_S = 30.0
_TRANSPORT_ERRORS = ("server_error", "timeout")

_REPAIR_SYSTEM = (
    "You fix malformed output. Restate the same content as one JSON object that matches the "
    "schema. Do not add, remove or change any content. Reply with the JSON object only."
)


class Gateway:
    def __init__(
        self,
        config: Any,
        registry: list[ModelEntry],
        store: Any,
        bus: Any,
        responder: Any = None,
        endpoint_for: Callable[[str], Optional[str]] | None = None,
        clients: dict | None = None,
        embedder: Any = None,
        ctx_for: Callable[[str], Optional[int]] | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.bus = bus
        self.responder = responder
        self.endpoint_for = endpoint_for
        self.ctx_for = ctx_for  # model_id -> loaded context size; None: read it from the config
        self.clients: dict = clients if clients is not None else {}
        self.registry: dict[str, ModelEntry] = {e.id: e for e in registry or []}

        self.driver = str(getattr(getattr(config, "host", None), "driver", "") or "")
        self._model_tags: dict[str, str] = {}  # model_id -> Ollama tag override
        self._ollama: Any = None
        self._llamacpp: dict[str, tuple[str, Any]] = {}  # model_id -> (base URL, client)
        self.ctx_trims = 0  # real calls whose messages were cut to fit the context
        self._embedder: Any = embedder

        gw = getattr(config, "gateway", None)
        self.mock = bool(getattr(gw, "mock", False))
        if self.mock and responder is None:
            raise ValueError("config.gateway.mock is set: a MockResponder is required")
        self.default_timeout_s = float(getattr(gw, "default_timeout_s", 120.0) or 0.0)
        max_models = max(1, int(getattr(gw, "max_concurrent_models", 2) or 1))
        slots = {e.id: max(1, int(e.serve.live.parallel)) for e in self.registry.values()}
        if self.driver == "llamacpp" and not self.mock:
            # llama-server has [llamacpp].parallel slots, whatever the registry says: a call
            # beyond them would wait inside the server with its timeout already running.
            cap = max(1, int(getattr(getattr(config, "llamacpp", None), "parallel", 1) or 1))
            slots = {mid: min(n, cap) for mid, n in slots.items()}
        # The host calls governor.set_slots(model_id, n) when it loads a model in another profile.
        self.governor = Governor(slots, max_models)
        use_cache = bool(getattr(gw, "cache", True)) and store is not None
        self.cache: Optional[CallCache] = CallCache(store) if use_cache else None

        self._clock = time.monotonic
        self._tps: dict[str, deque] = {}
        self._tokens_in = 0
        self._tokens_out = 0
        self._tokens_reasoning = 0
        self._calls = 0
        self._calls_failed = 0
        self._cache_hits = 0

    # ------------------------------------------------------------------ helpers

    def _entry(self, model_id: str) -> ModelEntry:
        return self.registry.get(model_id) or ModelEntry(id=model_id)

    def _emit(self, type: str, run_id: Optional[str], **fields: Any) -> None:
        if self.bus is None:
            return
        try:
            self.bus.emit(type, run_id, fields)
        except Exception:
            pass

    # ------------------------------------------------------------------ ollama

    @property
    def uses_ollama(self) -> bool:
        return self.driver == "ollama"

    def set_model_tag(self, model_id: str, tag: Optional[str]) -> None:
        """Override the Ollama tag for a model. None or "" clears it."""
        if tag:
            self._model_tags[model_id] = tag
        else:
            self._model_tags.pop(model_id, None)

    def model_tag(self, model_id: str) -> str:
        """Tag Ollama loads for this model: override, then ModelEntry.ollama_tag, then the id."""
        tag = self._model_tags.get(model_id)
        if tag:
            return tag
        entry = self.registry.get(model_id)
        return (entry.ollama_tag if entry is not None and entry.ollama_tag else None) or model_id

    def _ollama_client(self) -> Any:
        if self._ollama is None:
            from council.gateway.ollama_client import OllamaClient  # needs httpx; unused in mock mode

            cfg = getattr(self.config, "ollama", None)
            keep_alive: Any = getattr(cfg, "keep_alive", -1)
            try:
                keep_alive = int(keep_alive)  # "-1" -> -1: Ollama wants a number or a duration string
            except (TypeError, ValueError):
                pass
            num_ctx = getattr(cfg, "num_ctx_live", None)
            self._ollama = OllamaClient(
                base_url=str(getattr(cfg, "base_url", "") or "http://127.0.0.1:11434"),
                keep_alive=keep_alive,
                num_ctx=int(num_ctx) if num_ctx else None,
            )
        return self._ollama

    def _ollama_options(self, entry: ModelEntry, spec: Optional[CallSpec] = None) -> dict[str, Any]:
        """Merge order: config draft default (speculative entries only), entry options, then
        the per-call spec.meta["ollama_options"] (probes)."""
        opts: dict[str, Any] = {}
        default = getattr(getattr(self.config, "ollama", None), "default_draft_num_predict", 0)
        if getattr(entry, "speculative", "none") != "none" and default:
            opts["draft_num_predict"] = int(default)
        opts.update(getattr(entry, "ollama_options", None) or {})
        call_opts = (getattr(spec, "meta", None) or {}).get("ollama_options")
        if isinstance(call_opts, dict):
            opts.update(call_opts)
        return opts

    def _ollama_call(self, spec: CallSpec, entry: ModelEntry) -> tuple[CallSpec, dict[str, Any]]:
        """Ollama takes sampling inside `options`, which the client builds from the spec.
        Card sampling goes onto the spec; only reasoning fields travel as extra fields."""
        update: dict[str, Any] = {}
        for key in ("temperature", "top_p"):
            if getattr(spec, key, None) is None and key in (entry.sampling or {}):
                update[key] = entry.sampling[key]
        try:
            extra = reasoning_mod.request_fields(entry, spec.reasoning)
        except ValueError:
            extra = {}
        return (spec.model_copy(update=update) if update else spec), extra

    # ------------------------------------------------------------------ llama.cpp

    @property
    def uses_llamacpp(self) -> bool:
        return self.driver == "llamacpp"

    def _llamacpp_client(self, model_id: str) -> Any:
        """Client for this model's llama-server. Rebuilt when the host reports a new base URL."""
        base = self.endpoint_for(model_id) if self.endpoint_for else None
        if not base:
            return None
        base = str(base).rstrip("/")
        held = self._llamacpp.get(model_id)
        if held is not None and held[0] == base:
            return held[1]
        from council.gateway.llamacpp_client import LlamaCppClient  # needs httpx; unused in mock mode

        client = LlamaCppClient(base)
        self._llamacpp[model_id] = (base, client)
        return client

    def _llamacpp_call(self, spec: CallSpec, entry: ModelEntry) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """(extra fields, sampling options, best-effort thinking fields) for one llama-server call.
        A thinking switch the model card already sets is not sent twice."""
        from council.gateway.llamacpp_client import thinking_fields

        extra = self._extra_fields(spec, entry)
        optional = {k: v for k, v in thinking_fields(spec.reasoning).items() if k not in extra}
        call_opts = (spec.meta or {}).get("llamacpp_options")
        return extra, (dict(call_opts) if isinstance(call_opts, dict) else {}), optional

    # ------------------------------------------------------------------ context guard

    def _num_ctx(self, model_id: str) -> int:
        """Context size the model is loaded with. 0 = not known, the guard is skipped."""
        if self.ctx_for is not None:
            try:
                n = self.ctx_for(model_id)
            except Exception:
                n = None
            if n:
                return int(n)
        if self.uses_llamacpp:
            n = getattr(getattr(self.config, "llamacpp", None), "ctx", 0)
        elif self.uses_ollama:
            n = getattr(getattr(self.config, "ollama", None), "num_ctx_live", 0)
        else:
            n = self._entry(model_id).serve.live.ctx
        try:
            return int(n or 0)
        except (TypeError, ValueError):
            return 0

    def _fit(self, spec: CallSpec) -> tuple[CallSpec, Optional[dict]]:
        """Spec with messages cut to the context window, and the guard's info (None = not run)."""
        try:
            num_ctx = self._num_ctx(spec.model_id)
            if num_ctx <= 0 or not spec.messages:
                return spec, None
            max_output = int(spec.max_output_tokens or 0)
            if spec.reasoning != "off" and spec.max_reasoning_tokens:
                max_output += int(spec.max_reasoning_tokens)
            messages, info = ctx_guard.fit_messages(spec.messages, num_ctx, max_output)
        except Exception:
            return spec, None
        if not info.get("trimmed"):
            return spec, info
        self.ctx_trims += 1
        return spec.model_copy(update={"messages": messages}), info

    @staticmethod
    def _note_trim(res: Any, info: Optional[dict]) -> Any:
        """Put the guard's result on results that have an `extra` dict (llama.cpp results)."""
        if info is None or not isinstance(res, CallResult) or not isinstance(getattr(res, "extra", None), dict):
            return res
        extra = dict(res.extra)
        extra["trimmed"] = bool(info.get("trimmed"))
        if info.get("trimmed"):
            extra["ctx_fit"] = {k: info.get(k) for k in ("before", "after", "budget", "fits")}
        return res.model_copy(update={"extra": extra})

    def _client(self, model_id: str) -> Any:
        client = self.clients.get(model_id)
        if client is not None:
            return client
        if self.uses_llamacpp:
            return self._llamacpp_client(model_id)
        if self.uses_ollama:
            return self._ollama_client()
        base = self.endpoint_for(model_id) if self.endpoint_for else None
        if not base:
            return None
        from council.gateway.http_client import OpenAIClient  # needs httpx; unused in mock mode

        client = OpenAIClient(base)
        self.clients[model_id] = client
        return client

    def _extra_fields(self, spec: CallSpec, entry: ModelEntry) -> dict[str, Any]:
        """Model card sampling, reasoning level fields and token caps for one request."""
        extra: dict[str, Any] = {}
        for key, value in (entry.sampling or {}).items():
            if getattr(spec, key, None) is None:
                extra[key] = value
        try:
            extra.update(reasoning_mod.request_fields(entry, spec.reasoning))
        except ValueError:
            pass
        if spec.reasoning != "off" and spec.max_reasoning_tokens:
            # No server-side reasoning budget is assumed: one cap covers both (7.4).
            extra.update(reasoning_mod.apply_caps(
                spec.max_output_tokens + spec.max_reasoning_tokens, spec.max_reasoning_tokens, False
            ))
        return extra

    @staticmethod
    def _clean(res: CallResult) -> CallResult:
        """Move any inline thinking block out of content into reasoning_text."""
        if not isinstance(res, CallResult) or not res.content:
            return res
        content, stripped = reasoning_mod.strip_reasoning(res.content)
        if not stripped and content == res.content:
            return res
        parts = [p for p in (res.reasoning_text, stripped) if p]
        return res.model_copy(update={"content": content, "reasoning_text": "\n\n".join(parts) or None})

    async def _attempt(self, spec: CallSpec, mode: str, on_delta: Any, seen: list) -> CallResult:
        if self.mock:
            res = await self.responder.respond(spec, on_delta)
        else:
            client = self._client(spec.model_id)
            fit_info: Optional[dict] = None
            if client is not None:
                spec, fit_info = self._fit(spec)
            if client is None:
                res = CallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id,
                                 error="server_error")
            elif self.uses_llamacpp:
                extra, options, optional = self._llamacpp_call(spec, self._entry(spec.model_id))
                res = await client.chat(spec, extra, mode, on_delta, options=options,
                                        optional_fields=optional)
            elif self.uses_ollama:
                call_spec, extra = self._ollama_call(spec, self._entry(spec.model_id))
                res = await client.chat(call_spec, extra, mode, on_delta,
                                        model_tag=self.model_tag(spec.model_id),
                                        options=self._ollama_options(self._entry(spec.model_id), spec))
            else:
                res = await client.chat(
                    spec, self._extra_fields(spec, self._entry(spec.model_id)), mode, on_delta
                )
            res = self._note_trim(res, fit_info)
        res = self._clean(res)
        seen.append(res.error if isinstance(res, CallResult) else "server_error")
        return res

    def _repair_model(self, fallback: str) -> str:
        for entry in self.registry.values():
            if "clerk" in entry.roles and entry.status == "active":
                return entry.id
        return fallback

    def _make_repair(self, spec: CallSpec, seen: list) -> Any:
        if self.mock:
            # The mock builds output from the schema, not from the bad text. A repair would
            # hide the configured failure rate, so mock mode has no repair step.
            return None

        async def repair(text: str, schema: dict) -> CallResult:
            fix = CallSpec(
                model_id=self._repair_model(spec.model_id),
                call_id=f"{spec.call_id}:repair",
                run_id=spec.run_id,
                purpose="clerk.repair",
                messages=[
                    {"role": "system", "content": _REPAIR_SYSTEM},
                    {"role": "user", "content": "Schema:\n" + json.dumps(schema, ensure_ascii=False)
                     + "\n\nText to restate:\n" + (text or "")},
                ],
                json_schema=schema,
                reasoning="off",
                max_output_tokens=spec.max_output_tokens,
                temperature=0.0,
                seed=spec.seed,
                timeout_s=spec.timeout_s,
                priority=spec.priority,
                stream=False,
            )
            # Runs inside the caller's governor slot: taking a second slot here could deadlock
            # when max_concurrent_models is 1.
            res = await self._attempt(fix, "grammar", None, seen)
            return res.model_copy(update={"call_id": spec.call_id})

        return repair

    def _count(self, model_id: str, result: CallResult) -> None:
        self._calls += 1
        if not result.ok:
            self._calls_failed += 1
        self._tokens_in += result.tokens_in
        self._tokens_out += result.tokens_out
        self._tokens_reasoning += result.tokens_reasoning
        if result.ok and result.tps > 0:
            self._tps.setdefault(model_id, deque(maxlen=_TPS_SAMPLES)).append((self._clock(), result.tps))

    def _record(self, spec: CallSpec, result: CallResult) -> None:
        if self.store is None:
            return
        try:
            self.store.record_turn(spec, result)
        except Exception:
            pass

    def _emit_end(self, spec: CallSpec, result: CallResult, seat_no: Optional[int], rnd: int,
                  ms: float, timeout_s: Optional[float]) -> None:
        common = dict(call_id=spec.call_id, seat_no=seat_no, round=rnd, purpose=spec.purpose,
                      model_id=spec.model_id)
        if result.ok:
            self._emit(
                ev.TURN_COMPLETED, spec.run_id, **common,
                tokens=result.tokens_out, tokens_in=result.tokens_in, tokens_out=result.tokens_out,
                tokens_reasoning=result.tokens_reasoning, tps=result.tps, ms=ms,
                parsed=result.parsed if isinstance(result.parsed, dict) else None,
                content=result.content, finish_reason=result.finish_reason,
                attempts=result.attempts, cached=result.cached,
            )
        elif result.error == "timeout":
            self._emit(ev.TURN_TIMEOUT, spec.run_id, **common, timeout_s=timeout_s or 0.0, ms=ms,
                       will_retry=False)
        else:
            self._emit(ev.TURN_INVALID, spec.run_id, **common, error=result.error or "invalid_output",
                       attempts=result.attempts, will_retry=False,
                       content_tail=(result.content or "")[-400:])

    # ------------------------------------------------------------------ public

    async def call(self, spec: CallSpec, seat_no: int | None = None, round: int | None = None) -> CallResult:
        try:
            return await self._call(spec, seat_no, round)
        except asyncio.CancelledError:
            raise
        except Exception:
            call_id = getattr(spec, "call_id", "") or ""
            return CallResult(call_id=call_id, ok=False, model_id=getattr(spec, "model_id", None),
                              error="server_error")

    async def _call(self, spec: CallSpec, seat_no: Optional[int], round_: Optional[int]) -> CallResult:
        meta = dict(spec.meta or {})
        if seat_no is None:
            seat_no = meta.get("seat_no") if isinstance(meta.get("seat_no"), int) else None
        if round_ is None:
            round_ = meta.get("round") if isinstance(meta.get("round"), int) else None
        if seat_no is not None:
            meta["seat_no"] = seat_no
        if round_ is not None:
            meta["round"] = round_
        spec = spec.model_copy(update={"meta": meta})
        rnd = int(round_ or 0)
        entry = self._entry(spec.model_id)
        started = dict(call_id=spec.call_id, purpose=spec.purpose, model_id=spec.model_id,
                       seat_no=seat_no, round=rnd, reasoning=spec.reasoning,
                       max_output_tokens=spec.max_output_tokens, attempt=1)

        # 1. cache
        if self.cache is not None:
            try:
                hit = self.cache.get(spec, entry.quant)
            except Exception:
                hit = None
            if hit is not None:
                hit = hit.model_copy(update={"call_id": spec.call_id, "cached": True,
                                             "model_id": spec.model_id})
                self._cache_hits += 1
                self._calls += 1
                self._emit(ev.TURN_STARTED, spec.run_id, **started)
                self._emit_end(spec, hit, seat_no, rnd, 0.0, None)
                self._record(spec, hit)
                return hit

        timeout_s: Optional[float] = spec.timeout_s if spec.timeout_s and spec.timeout_s > 0 else None
        if "timeout_s" not in spec.model_fields_set:
            # The caller did not choose a timeout: the 120 s in the schema is only a placeholder,
            # far too short for a slow real model. The configured default applies instead.
            timeout_s = None
        if timeout_s is None and self.default_timeout_s > 0:
            timeout_s = self.default_timeout_s

        def on_delta(kind: str, text: str) -> None:
            if not text:
                return
            type_ = ev.TURN_REASONING_DELTA if kind == "reasoning" else ev.TURN_DELTA
            self._emit(type_, spec.run_id, call_id=spec.call_id, seat_no=seat_no, text=text)

        delta_cb = on_delta if spec.stream else None
        seen: list = []

        async def attempt(s: CallSpec, mode: str) -> CallResult:
            return await self._attempt(s, mode, delta_cb, seen)

        t0 = self._clock()
        emitted_start = False
        try:
            # 2. governor, 3. ladder under the timeout
            async with self.governor.acquire(spec.model_id, spec.priority):
                t0 = self._clock()
                self._emit(ev.TURN_STARTED, spec.run_id, **started)
                emitted_start = True
                try:
                    result = await asyncio.wait_for(
                        run_ladder(spec, attempt, self._make_repair(spec, seen), entry.structured),
                        timeout_s,
                    )
                except asyncio.TimeoutError:
                    result = CallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id,
                                        attempts=max(len(seen), 1), error="timeout")
                except asyncio.CancelledError:
                    raise
                except Exception:
                    result = CallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id,
                                        attempts=max(len(seen), 1), error="server_error")
        except asyncio.CancelledError:
            ms = (self._clock() - t0) * 1000.0
            result = CallResult(call_id=spec.call_id, ok=False, model_id=spec.model_id,
                                attempts=max(len(seen), 1), error="cancelled")
            if emitted_start:
                self._emit_end(spec, result, seat_no, rnd, ms, timeout_s)
            self._record(spec, result)
            self._count(spec.model_id, result)
            raise

        ms = (self._clock() - t0) * 1000.0
        update: dict[str, Any] = {"call_id": spec.call_id, "model_id": result.model_id or spec.model_id}
        if not result.ok:
            # The ladder labels every exhausted call invalid_output. If no attempt ever
            # produced text, report what really happened.
            if result.error in (None, "invalid_output") and seen and all(e in _TRANSPORT_ERRORS for e in seen):
                update["error"] = "timeout" if "timeout" in seen else "server_error"
            elif result.error is None:
                update["error"] = "invalid_output"
        elif not result.tps and result.gen_ms > 0 and result.tokens_out:
            update["tps"] = result.tokens_out / (result.gen_ms / 1000.0)
        result = result.model_copy(update=update)

        # 4. events, turns table, counters, cache
        self._emit_end(spec, result, seat_no, rnd, ms, timeout_s)
        self._record(spec, result)
        self._count(spec.model_id, result)
        if self.cache is not None and result.ok:
            try:
                self.cache.put(spec, entry.quant, result)
            except Exception:
                pass
        return result

    async def call_many(self, specs: list[CallSpec]) -> list[CallResult]:
        return list(await asyncio.gather(*(self.call(s) for s in specs)))

    def _embed_model(self) -> Optional[ModelEntry]:
        for entry in self.registry.values():
            if "embed" in entry.roles and entry.status == "active":
                return entry
        return None

    def _make_embedder(self) -> Any:
        from council.gateway import embedder as emb  # imports httpx

        if self.mock:
            return emb.MockEmbedder()
        entry = self._embed_model()
        if entry is None:
            return emb.MockEmbedder()  # no embed model in the registry: keyword vectors
        if self.uses_ollama:
            return emb.OllamaEmbedder(self._client(entry.id), self.model_tag(entry.id))
        base = self.endpoint_for(entry.id) if self.endpoint_for else None
        if not base:
            return emb.MockEmbedder()
        return emb.OpenAIEmbedder(base, entry.id)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """One vector per text, in order. Never raises; a failed batch gives zero vectors."""
        if not texts:
            return []
        try:
            if self._embedder is None:
                self._embedder = self._make_embedder()
            return await self._embedder.embed(list(texts))
        except asyncio.CancelledError:
            raise
        except Exception:
            return [[] for _ in texts]

    def stats(self) -> dict:
        gov = self.governor.stats()
        now = self._clock()
        tps_by_model: dict[str, float] = {}
        for model_id, samples in self._tps.items():
            recent = [tps for ts, tps in samples if now - ts <= _TPS_WINDOW_S]
            if recent:
                tps_by_model[model_id] = sum(recent) / len(recent)
        return {
            "in_flight": gov["in_flight"],
            "queue_depth": gov["queue_depth"],
            "tps_by_model": tps_by_model,
            "tps_total": sum(tps_by_model.values()),
            "tokens_in": self._tokens_in,
            "tokens_out": self._tokens_out,
            "tokens_reasoning": self._tokens_reasoning,
            "calls": self._calls,
            "calls_failed": self._calls_failed,
            "cache_hits": self._cache_hits,
        }


__all__ = ["Gateway"]
