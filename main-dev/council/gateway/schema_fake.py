"""Make a fake JSON value that is valid for a pydantic-style JSON Schema."""
from __future__ import annotations

import random
from typing import Any

MAX_DEPTH = 8
_MISSING = object()


def fake_instance(schema: dict, seed: int = 0, hints: dict | None = None) -> Any:
    rng = random.Random(seed)
    ctx = {"root": schema, "rng": rng, "hints": hints or {}}
    return _gen(schema, ctx, 0, None)


def _resolve(node: dict, root: dict) -> dict:
    seen = 0
    while isinstance(node, dict) and "$ref" in node and seen < 32:
        ref = node["$ref"]
        target: Any = root
        if ref.startswith("#"):
            for part in [p for p in ref[1:].split("/") if p]:
                part = part.replace("~1", "/").replace("~0", "~")
                target = target[part]
        extra = {k: v for k, v in node.items() if k != "$ref"}
        node = {**target, **extra} if isinstance(target, dict) else {}
        seen += 1
    return node


def _pick(ctx: dict, options: list) -> Any:
    idx = ctx["hints"].get("enum_index")
    if idx is not None:
        return options[idx % len(options)]
    return ctx["rng"].choice(options)


def _allows_null(node: dict, root: dict) -> bool:
    node = _resolve(node, root)
    if node.get("type") == "null":
        return True
    if isinstance(node.get("type"), list) and "null" in node["type"]:
        return True
    return any(
        _resolve(b, root).get("type") == "null"
        for b in node.get("anyOf", []) + node.get("oneOf", [])
    )


def _gen(node: Any, ctx: dict, depth: int, field: str | None) -> Any:
    root = ctx["root"]
    if node is True or node is None or node == {}:
        return _gen({"type": "string"}, ctx, depth, field)
    node = _resolve(node, root)
    hints = ctx["hints"]

    if "const" in node:
        return node["const"]
    if "enum" in node and node["enum"]:
        return _pick(ctx, list(node["enum"]))

    # field overrides win over default
    if field is not None:
        if field in hints.get("strings", {}) and _is_type(node, "string"):
            return hints["strings"][field]
        if field in hints.get("numbers", {}) and (
            _is_type(node, "number") or _is_type(node, "integer")
        ):
            return hints["numbers"][field]

    if "allOf" in node:
        merged: dict = {k: v for k, v in node.items() if k != "allOf"}
        for part in node["allOf"]:
            part = _resolve(part, root)
            for k, v in part.items():
                if k == "properties":
                    merged.setdefault("properties", {}).update(v)
                elif k == "required":
                    merged["required"] = list(merged.get("required", [])) + list(v)
                else:
                    merged.setdefault(k, v)
        return _gen(merged, ctx, depth, field)

    for key in ("anyOf", "oneOf"):
        if key in node:
            branches = node[key]
            non_null = [b for b in branches if _resolve(b, root).get("type") != "null"]
            if depth >= MAX_DEPTH:
                if _allows_null(node, root):
                    return None
            if non_null:
                return _gen(non_null[0], ctx, depth, field)
            return None

    if "default" in node:
        return node["default"]

    t = node.get("type")
    if isinstance(t, list):
        non_null = [x for x in t if x != "null"]
        t = non_null[0] if non_null else "null"
    if t is None:
        if "properties" in node:
            t = "object"
        elif "items" in node:
            t = "array"
        else:
            t = "string"

    rng: random.Random = ctx["rng"]

    if t == "null":
        return None
    if t == "boolean":
        return rng.choice([True, False])
    if t == "integer":
        lo, hi = _bounds(node, 0, 100, integer=True)
        return rng.randint(lo, hi)
    if t == "number":
        lo, hi = _bounds(node, 0, 100, integer=False)
        v = rng.uniform(lo, hi)
        v = min(max(v, lo), hi)
        if node.get("exclusiveMinimum") is not None and v <= node["exclusiveMinimum"]:
            v = (lo + hi) / 2
        if node.get("exclusiveMaximum") is not None and v >= node["exclusiveMaximum"]:
            v = (lo + hi) / 2
        return v
    if t == "string":
        return _gen_string(node, rng, field)
    if t == "array":
        return _gen_array(node, ctx, depth, field)
    if t == "object":
        return _gen_object(node, ctx, depth)
    return None


def _is_type(node: dict, name: str) -> bool:
    t = node.get("type")
    if isinstance(t, list):
        return name in t
    if t is None:
        for key in ("anyOf", "oneOf"):
            for b in node.get(key, []):
                if _is_type(_resolve(b, {}) if "$ref" not in b else b, name):
                    return True
        return name == "string" and "properties" not in node and "items" not in node
    return t == name


def _bounds(node: dict, lo: float, hi: float, integer: bool) -> tuple:
    mn = node.get("minimum")
    mx = node.get("maximum")
    emn = node.get("exclusiveMinimum")
    emx = node.get("exclusiveMaximum")
    step = 1 if integer else 0.5
    if mn is None and emn is not None:
        mn = emn + step
    if mx is None and emx is not None:
        mx = emx - step
    if mn is None and mx is None:
        mn, mx = lo, hi
    elif mn is None:
        mn = min(lo, mx)
    elif mx is None:
        mx = max(hi, mn)
    if integer:
        import math
        mn, mx = math.ceil(mn), math.floor(mx)
        if mn > mx:
            mx = mn
    return mn, mx


def _gen_string(node: dict, rng: random.Random, field: str | None) -> str:
    fmt = node.get("format")
    if fmt == "date-time":
        return "2026-01-01T00:00:00Z"
    if fmt == "date":
        return "2026-01-01"
    if fmt == "uuid":
        return "00000000-0000-4000-8000-%012d" % rng.randint(0, 10**11)
    if fmt in ("uri", "url"):
        return "http://example.com/x"
    if fmt == "email":
        return "a@example.com"
    base = (field or "text") + "_" + "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(4))
    mn = node.get("minLength", 0)
    mx = node.get("maxLength")
    while len(base) < mn:
        base += "x"
    if mx is not None and len(base) > mx:
        base = base[:mx]
    return base


def _gen_array(node: dict, ctx: dict, depth: int, field: str | None) -> list:
    rng: random.Random = ctx["rng"]
    mn = node.get("minItems", 1 if "minItems" not in node else node["minItems"])
    mx = node.get("maxItems")
    if depth >= MAX_DEPTH:
        n = mn
    else:
        hi = 2 if mx is None else mx
        lo = min(1, hi) if "minItems" not in node else mn
        hi = max(hi, lo)
        if mx is None and "minItems" in node:
            hi = max(2, mn)
        n = rng.randint(lo, hi)
    if mx is not None:
        n = min(n, mx)
    n = max(n, mn if mn else 0)
    items = node.get("items")
    prefix = node.get("prefixItems")
    out = []
    for i in range(n):
        if prefix and i < len(prefix):
            out.append(_gen(prefix[i], ctx, depth + 1, field))
        else:
            out.append(_gen(items if items is not None else {"type": "string"}, ctx, depth + 1, field))
    if node.get("uniqueItems"):
        uniq = []
        for v in out:
            if v not in uniq:
                uniq.append(v)
        out = uniq
    return out


def _gen_object(node: dict, ctx: dict, depth: int) -> dict:
    props = node.get("properties", {}) or {}
    out = {}
    if depth >= MAX_DEPTH:
        required = set(node.get("required", []))
        for name, sub in props.items():
            if name in required and not _allows_null(sub, ctx["root"]):
                out[name] = _gen(sub, ctx, depth + 1, name)
            elif name in required:
                out[name] = None
        return out
    for name, sub in props.items():
        out[name] = _gen(sub, ctx, depth + 1, name)
    ap = node.get("additionalProperties")
    if not props and isinstance(ap, dict) and ap:
        for i in range(1, 3):
            out["key%d" % i] = _gen(ap, ctx, depth + 1, None)
    return out
