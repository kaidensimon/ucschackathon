"""Tiny JSON Schema validator covering what pydantic model_json_schema() emits.

validate(instance, schema) -> list[str] of errors with a JSON path; empty when valid.
"""

from __future__ import annotations

from typing import Any

_MAX_DEPTH = 64


def _type_ok(value: Any, t: str) -> bool:
    if t == "null":
        return value is None
    if t == "boolean":
        return isinstance(value, bool)
    if t == "string":
        return isinstance(value, str)
    if t == "integer":
        if isinstance(value, bool):
            return False
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "array":
        return isinstance(value, list)
    if t == "object":
        return isinstance(value, dict)
    return False


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _equal(a: Any, b: Any) -> bool:
    # JSON equality: True != 1, but 1 == 1.0.
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def _resolve(ref: str, root: dict) -> Any:
    if not ref.startswith("#"):
        raise ValueError(f"unsupported $ref: {ref}")
    node: Any = root
    for part in ref[1:].split("/"):
        if part == "":
            continue
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise ValueError(f"unresolvable $ref: {ref}")
    return node


def _fmt(path: str) -> str:
    return path


def _check(inst: Any, schema: Any, root: dict, path: str, depth: int) -> list[str]:
    if depth > _MAX_DEPTH:
        return [f"{_fmt(path)}: schema nesting too deep"]
    if schema is True or schema is None:
        return []
    if schema is False:
        return [f"{_fmt(path)}: no value allowed here"]
    if not isinstance(schema, dict):
        return []

    errs: list[str] = []
    p = _fmt(path)

    if "$ref" in schema:
        try:
            target = _resolve(schema["$ref"], root)
        except ValueError as exc:
            return [f"{p}: {exc}"]
        errs += _check(inst, target, root, path, depth + 1)

    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(inst, t) for t in types):
            errs.append(f"{p}: expected {' or '.join(types)}, got {_type_name(inst)}")
            return errs  # further checks would be noise

    if "const" in schema and not _equal(inst, schema["const"]):
        errs.append(f"{p}: must equal {schema['const']!r}")
    if "enum" in schema and not any(_equal(inst, e) for e in schema["enum"]):
        errs.append(f"{p}: must be one of {schema['enum']!r}, got {inst!r}")

    if "allOf" in schema:
        for sub in schema["allOf"]:
            errs += _check(inst, sub, root, path, depth + 1)
    if "anyOf" in schema:
        subs = [_check(inst, s, root, path, depth + 1) for s in schema["anyOf"]]
        if not any(len(s) == 0 for s in subs):
            errs.append(f"{p}: does not match any allowed shape ({_summ(subs)})")
    if "oneOf" in schema:
        subs = [_check(inst, s, root, path, depth + 1) for s in schema["oneOf"]]
        n = sum(1 for s in subs if not s)
        if n == 0:
            errs.append(f"{p}: does not match any allowed shape ({_summ(subs)})")
        elif n > 1:
            errs.append(f"{p}: matches {n} shapes, must match exactly one")

    is_num = isinstance(inst, (int, float)) and not isinstance(inst, bool)
    if is_num:
        if "minimum" in schema and inst < schema["minimum"]:
            errs.append(f"{p}: {inst} is less than minimum {schema['minimum']}")
        if "maximum" in schema and inst > schema["maximum"]:
            errs.append(f"{p}: {inst} is greater than maximum {schema['maximum']}")
        if "exclusiveMinimum" in schema and inst <= schema["exclusiveMinimum"]:
            errs.append(f"{p}: {inst} must be greater than {schema['exclusiveMinimum']}")
        if "exclusiveMaximum" in schema and inst >= schema["exclusiveMaximum"]:
            errs.append(f"{p}: {inst} must be less than {schema['exclusiveMaximum']}")

    if isinstance(inst, str):
        if "minLength" in schema and len(inst) < schema["minLength"]:
            errs.append(f"{p}: string shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(inst) > schema["maxLength"]:
            errs.append(f"{p}: string longer than maxLength {schema['maxLength']}")

    if isinstance(inst, list):
        if "minItems" in schema and len(inst) < schema["minItems"]:
            errs.append(f"{p}: fewer than minItems {schema['minItems']}")
        if "maxItems" in schema and len(inst) > schema["maxItems"]:
            errs.append(f"{p}: more than maxItems {schema['maxItems']}")
        prefix = schema.get("prefixItems")
        n_prefix = 0
        if isinstance(prefix, list):
            n_prefix = len(prefix)
            for i, sub in enumerate(prefix):
                if i < len(inst):
                    errs += _check(inst[i], sub, root, f"{path}[{i}]", depth + 1)
        if "items" in schema:
            items = schema["items"]
            if isinstance(items, dict) or isinstance(items, bool):
                for i in range(n_prefix, len(inst)):
                    errs += _check(inst[i], items, root, f"{path}[{i}]", depth + 1)

    if isinstance(inst, dict):
        props = schema.get("properties", {}) or {}
        for name in schema.get("required", []) or []:
            if name not in inst:
                errs.append(f"{p}: missing required property '{name}'")
        for name, sub in props.items():
            if name in inst:
                errs += _check(inst[name], sub, root, f"{path}.{name}", depth + 1)
        ap = schema.get("additionalProperties", True)
        extra = [k for k in inst if k not in props]
        if ap is False:
            for k in extra:
                errs.append(f"{p}: unexpected property '{k}'")
        elif isinstance(ap, dict):
            for k in extra:
                errs += _check(inst[k], ap, root, f"{path}.{k}", depth + 1)

    return errs


def _summ(subs: list[list[str]]) -> str:
    firsts = [s[0] for s in subs if s]
    return "; ".join(firsts[:3])


def validate(instance: Any, schema: dict) -> list[str]:
    """Return human-readable errors (with JSON path); empty list when valid."""
    return _check(instance, schema, schema, "$", 0)


def is_valid(instance: Any, schema: dict) -> bool:
    return not validate(instance, schema)
