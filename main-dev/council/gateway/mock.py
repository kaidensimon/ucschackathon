"""Mock responder: schema-valid canned output for mock mode (spec 7.6)."""
from __future__ import annotations

import asyncio
import json
import random
import re
import zlib
from typing import Any, Callable, Optional

from council.core.schemas import CallResult, CallSpec
from council.gateway import mock_scenario, mock_text
from council.gateway.schema_fake import fake_instance

_LIST_FIELDS = ("assumptions", "risks", "user_questions")
_TEXT_NAMES = set(mock_text._TEXT_FIELDS) | {"blocking_objection"}
_DEFAULT_SEATS = 5
_DEFAULT_ACCURACY = 0.7
_MAX_LOGPROBS = 256


def _unit(*parts: Any) -> float:
    """Deterministic number in [0, 1) from the parts."""
    return zlib.crc32("|".join(str(p) for p in parts).encode("utf-8")) / 4294967296.0


def _trailing_int(text: str, pattern: str, default: int = 0) -> int:
    m = re.search(pattern, text or "")
    return int(m.group(1)) if m else default


def _small_file(path: str) -> str:
    low = path.lower()
    if low.endswith(".py"):
        return '"""Mock file."""\n\nVALUE = 1\n'
    if low.endswith(".md"):
        return "# Mock\n\nA small mock file.\n"
    if low.endswith(".json"):
        return "{}\n"
    return "mock\n"


def _resolve(node: Any, root: dict) -> Any:
    seen = 0
    while isinstance(node, dict) and "$ref" in node and seen < 32:
        target: Any = root
        for part in [p for p in node["$ref"].lstrip("#").split("/") if p]:
            target = target.get(part.replace("~1", "/").replace("~0", "~"), {})
        node = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
        seen += 1
    return node


def _non_null(node: Any, root: dict) -> Any:
    node = _resolve(node, root)
    if isinstance(node, dict):
        for key in ("anyOf", "oneOf"):
            if key in node:
                opts = [_resolve(b, root) for b in node[key]]
                opts = [b for b in opts if not (isinstance(b, dict) and b.get("type") == "null")]
                if opts:
                    return opts[0]
    return node


def _allows_null(node: Any, root: dict) -> bool:
    node = _resolve(node, root)
    if not isinstance(node, dict):
        return False
    t = node.get("type")
    if t == "null" or (isinstance(t, list) and "null" in t):
        return True
    return any(
        isinstance(_resolve(b, root), dict) and _resolve(b, root).get("type") == "null"
        for b in node.get("anyOf", []) + node.get("oneOf", [])
    )


def _est_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


class MockResponder:
    def __init__(
        self,
        seed: int = 0,
        delay: tuple[float, float] = (0.0, 0.0),
        tps: float = 60.0,
        fail_rate: float = 0.0,
        split: bool = True,
        tribunal_concede: bool = False,
        accuracy: Optional[dict[str, float]] = None,
    ) -> None:
        self.seed = int(seed)
        self.delay = (float(delay[0]), float(delay[1]))
        self.tps = float(tps) if tps and tps > 0 else 60.0
        self.fail_rate = float(fail_rate)
        self.split = bool(split)
        self.tribunal_concede = bool(tribunal_concede)
        self.accuracy: dict[str, float] = dict(accuracy) if accuracy else {}

    # ------------------------------------------------------------------
    def _call_seed(self, spec: CallSpec) -> int:
        return (self.seed * 1_000_003 + zlib.crc32(str(spec.call_id).encode("utf-8"))) & 0x7FFFFFFF

    def _seat_info(self, spec: CallSpec) -> tuple[Optional[int], int]:
        meta = spec.meta or {}
        seat = meta.get("seat_no")
        k = meta.get("k") or meta.get("seats") or _DEFAULT_SEATS
        try:
            seat = int(seat) if seat is not None else None
        except (TypeError, ValueError):
            seat = None
        try:
            k = int(k)
        except (TypeError, ValueError):
            k = _DEFAULT_SEATS
        return seat, max(k, 1)

    def _is_minority(self, seat: Optional[int], k: int) -> bool:
        return self.split and seat is not None and seat >= k - 2 and k > 2

    def _is_last(self, seat: Optional[int], k: int) -> bool:
        return seat is not None and seat == k - 1

    # ------------------------------------------------------------------
    def _solo_right(self, spec: CallSpec) -> bool:
        meta = spec.meta or {}
        try:
            p = float(self.accuracy.get(spec.model_id, _DEFAULT_ACCURACY))
        except (TypeError, ValueError):
            p = _DEFAULT_ACCURACY
        return _unit(spec.model_id, meta.get("task_id"), self.seed) < p

    @staticmethod
    def _crux_options(schema: dict) -> list[str]:
        try:
            enum = schema["properties"]["cruxes"]["items"]["properties"]["between"]["items"]["enum"]
        except (KeyError, TypeError):
            return []
        return [str(e) for e in enum] if isinstance(enum, list) else []

    def _route(self, spec: CallSpec, s: int, purpose: str) -> Optional[tuple[Any, bool]]:
        """Scenario reply for the purposes that have one: (object, answer_is_right) or None."""
        meta = spec.meta or {}
        cid = str(spec.call_id)
        seat = meta.get("seat_no")
        try:
            seat = int(seat) if seat is not None else 0
        except (TypeError, ValueError):
            seat = 0
        if purpose == "foreman.decompose":
            if "tasks:" in cid:
                idx = _trailing_int(cid, r"tasks:(\d+)", 1)
            else:
                idx = 0
            return mock_scenario.decompose_reply(idx), True
        if purpose == "foreman.review":
            return mock_scenario.second_key_patches(), True
        if purpose == "worker":
            task_id = str(meta.get("task_id", ""))
            attempt = meta.get("attempt", 1)
            try:
                attempt = int(attempt)
            except (TypeError, ValueError):
                attempt = 1
            out = mock_scenario.worker_output_for(task_id, attempt)
            if out.get("blocked") and task_id not in mock_scenario.TASK_IDS:
                paths = meta.get("write_set")
                if isinstance(paths, (list, tuple)) and paths:
                    ops = [{"op": "write_file", "path": str(p), "content": _small_file(str(p))}
                           for p in paths]
                    return {"ops": ops, "notes": "Wrote " + ", ".join(str(p) for p in paths) + ".",
                            "blocked": None}, True
                return None
            return out, True
        if purpose == "review":
            cycle = _trailing_int(cid, r"rv(\d+)", 1)
            return mock_scenario.review_ballot_for(seat, cycle), True
        if purpose == "memory.judge":
            cand = str(meta.get("candidate_id", ""))
            cidx = _trailing_int(cand, r"(\d+)$", zlib.crc32(cand.encode("utf-8")) % 1000)
            return mock_scenario.memory_verdict_for(cidx, seat), True
        if purpose in ("tribunal.question", "tribunal.answer"):
            idx = meta.get("index", 0)
            idx = idx if isinstance(idx, int) else 0
            return mock_scenario.tribunal_reply(purpose, idx, self.tribunal_concede), True
        if purpose == "tribunal.verdict":
            if self.tribunal_concede:
                return mock_scenario.tribunal_reply(purpose, 0, True), True
            if seat % 5 == 1:
                return mock_scenario.tribunal_reply(purpose, 2, False), True
            fail = mock_scenario.tribunal_reply(purpose, 0, False)
            fail["error_kind"] = "logic"
            fail["score"] = 0.2
            fail["held"] = False
            return fail, True
        if purpose == "bench.solo":
            right = self._solo_right(spec)
            task_id = meta.get("task_id")
            if "mock_truth" in meta:
                truth = str(meta["mock_truth"])
            else:
                truth = None
            if right and truth is not None:
                key = truth
            else:
                key = "wrong-%08x" % zlib.crc32(f"{spec.model_id}|{task_id}".encode("utf-8"))
                right = False
            obj = fake_instance(spec.json_schema or {}, seed=s, hints={"numbers": {"confidence": 0.7}})
            if not isinstance(obj, dict):
                obj = {}
            obj["answer_key"] = key
            return obj, right
        if purpose == "clerk.extract_cruxes":
            opts = self._crux_options(spec.json_schema or {})
            if len(opts) < 2:
                return None
            a, b = opts[0], opts[1]
            return {"cruxes": [
                {"statement": f"Does {a} actually hold up when tested, or does {b}?",
                 "between": [a, b], "kind": "checkable"},
                {"statement": f"How much should {a} be weighed against {b}?",
                 "between": [a, b], "kind": "value"},
            ]}, True
        return None

    @staticmethod
    def _logprobs(s: int, n: int, right: bool) -> list[float]:
        rng = random.Random(s ^ 0x10CB)
        n = max(1, min(int(n), _MAX_LOGPROBS))
        lo, hi = (-0.4, -0.01) if right else (-2.2, -0.6)
        return [round(rng.uniform(lo, hi), 4) for _ in range(n)]

    # ------------------------------------------------------------------
    def _overlay(self, value: Any, node: Any, root: dict, field: Optional[str], ctx: dict) -> Any:
        node = _non_null(node, root)
        if not isinstance(node, dict):
            return value
        if isinstance(value, dict):
            props = node.get("properties", {}) or {}
            for name in list(value):
                if name in props:
                    value[name] = self._overlay(value[name], props[name], root, name, ctx)
            return value
        if isinstance(value, list):
            items = node.get("items", {})
            if field in _LIST_FIELDS and all(isinstance(v, str) for v in value):
                ctx["n"] += 1
                new = mock_text.list_for(field, ctx["s"] + ctx["n"], len(value))
                return new if len(new) == len(value) else value
            return [self._overlay(v, items, root, field, ctx) for v in value]
        if isinstance(value, str) or value is None:
            if field is None or field not in _TEXT_NAMES or "enum" in node or "const" in node:
                return value
            if value is None and not _allows_null(node, root):
                return value
            if node.get("type") not in (None, "string") and not isinstance(node.get("type"), list):
                return value
            ctx["n"] += 1
            text = mock_text.text_for(field, ctx["s"] + ctx["n"])
            if text is None:
                return None if _allows_null(node, root) else value
            mx = node.get("maxLength")
            if mx is not None and len(text) > mx:
                text = text[:mx]
            mn = node.get("minLength", 0)
            if len(text) < mn:
                text = text + " " * (mn - len(text))
            return text
        return value

    def _build_object(self, spec: CallSpec, s: int, purpose: str) -> Any:
        schema = spec.json_schema or {}
        seat, k = self._seat_info(spec)
        rng = random.Random(s ^ 0x5EED)
        hints: dict[str, Any] = {"numbers": {"confidence": round(rng.uniform(0.6, 0.95), 3)}}
        if purpose in ("seat.r2", "seat.r3"):
            hints["enum_index"] = 1 if self._is_last(seat, k) else 0
        obj = fake_instance(schema, seed=s, hints=hints)
        ctx = {"s": s, "n": 0}
        obj = self._overlay(obj, schema, schema, None, ctx)
        if isinstance(obj, dict):
            props = (_non_null(schema, schema) or {}).get("properties", {}) or {}
            if "answer_key" in props:
                key = None
                if purpose == "seat.r0":
                    if self.split and seat is not None:
                        key = "sliding-window" if self._is_minority(seat, k) else "token-bucket"
                    else:
                        key = mock_text.answer_key_for(s, self.split)
                elif purpose in ("seat.r2", "seat.r3"):
                    key = "sliding-window" if self._is_last(seat, k) else "token-bucket"
                if key is not None:
                    obj["answer_key"] = key
            if "confidence" in props and isinstance(obj.get("confidence"), (int, float)):
                c = obj["confidence"]
                obj["confidence"] = min(max(float(c), 0.6), 0.95)
        return obj

    # ------------------------------------------------------------------
    async def respond(
        self,
        spec: CallSpec,
        on_delta: Optional[Callable[[str, str], None]] = None,
    ) -> CallResult:
        s = self._call_seed(spec)
        rng = random.Random(s)
        lo, hi = self.delay
        sleeping = hi > 0
        if sleeping:
            await asyncio.sleep(rng.uniform(lo, hi))

        if self.fail_rate > 0 and rng.random() < self.fail_rate:
            return CallResult(
                call_id=spec.call_id, ok=False, model_id=spec.model_id,
                error="invalid_output", finish_reason="error",
            )

        purpose = spec.purpose or ""
        parsed: Any = None
        right = True
        if spec.json_schema is not None:
            routed = self._route(spec, s, purpose)
            if routed is not None:
                parsed, right = routed
            else:
                parsed = self._build_object(spec, s, purpose)
            content = json.dumps(parsed, ensure_ascii=False)
        else:
            parts = [mock_text.text_for("answer", s) or "", mock_text.text_for("summary", s + 1) or ""]
            content = " ".join(p for p in parts if p).strip() or mock_text.TOPIC

        prompt_text = " ".join(str(m.get("content", "")) for m in (spec.messages or []))
        tokens_in = _est_tokens(prompt_text) if prompt_text else 1
        tokens_out = _est_tokens(content)
        tokens_reasoning = 0
        reasoning_text = None
        if spec.reasoning != "off":
            tokens_reasoning = tokens_out * (3 if spec.reasoning == "max" else 1)
            reasoning_text = "Weigh the options, check the constraints, then settle on the best fit."
        if spec.max_output_tokens and tokens_out > spec.max_output_tokens and spec.json_schema is None:
            content = content[: spec.max_output_tokens * 4]
            tokens_out = _est_tokens(content)

        if spec.stream and on_delta is not None:
            scale = (lo + hi) / 2 if sleeping else 0.0
            chunks = re.findall(r"\S+\s*", content) or [content]
            for chunk in chunks:
                on_delta("content", chunk)
                if scale > 0:
                    await asyncio.sleep(scale * _est_tokens(chunk) / self.tps)

        gen_ms = (tokens_out + tokens_reasoning) / self.tps * 1000.0
        prompt_ms = tokens_in / (self.tps * 10.0) * 1000.0
        return CallResult(
            call_id=spec.call_id,
            ok=True,
            model_id=spec.model_id,
            content=content,
            parsed=parsed,
            reasoning_text=reasoning_text,
            finish_reason="stop",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_reasoning=tokens_reasoning,
            prompt_ms=round(prompt_ms, 3),
            gen_ms=round(gen_ms, 3),
            tps=self.tps,
            logprobs=self._logprobs(s, tokens_out, right),
        )
