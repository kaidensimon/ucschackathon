"""Read and write llama.cpp control-vector files (GGUF v3, F32, one tensor per layer).

Byte layout is the one tools/box/steer_test.py wrote and llama-server loaded on the box:
keys general.architecture="controlvector", controlvector.model_hint (string),
controlvector.layer_count (int32); tensors "direction.<layer>" F32 1-D; 32-byte alignment.

Standard library only. read_cvec parses the same subset and raises ValueError on anything else.
"""
from __future__ import annotations

import os
import struct
from pathlib import Path

__all__ = ["write_cvec", "read_cvec", "scaled_arg"]

_MAGIC = b"GGUF"
_VERSION = 3
_ALIGN = 32
_T_INT32 = 5
_T_STRING = 8
_TYPE_F32 = 0
# scalar GGUF value types we can skip over: id -> byte size
_SCALAR_SIZE = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
_PREFIX = "direction."


def _string(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack("<Q", len(b)) + b


def write_cvec(path: Path, directions: dict[int, list[float]], hint: str = "") -> Path:
    """Write {layer: vector} as a control-vector GGUF. Atomic: temp file then replace."""
    path = Path(path)
    kvs = [("general.architecture", _T_STRING, _string("controlvector")),
           ("controlvector.model_hint", _T_STRING, _string(hint)),
           ("controlvector.layer_count", _T_INT32, struct.pack("<i", len(directions)))]
    head = _MAGIC + struct.pack("<IQQ", _VERSION, len(directions), len(kvs))
    for key, typ, val in kvs:
        head += _string(key) + struct.pack("<I", typ) + val
    data, offset = b"", 0
    for layer in sorted(directions):
        vec = directions[layer]
        head += _string(f"{_PREFIX}{layer}") + struct.pack("<IQIQ", 1, len(vec), _TYPE_F32, offset)
        blob = struct.pack(f"<{len(vec)}f", *vec)
        blob += b"\0" * ((-len(blob)) % _ALIGN)
        data += blob
        offset += len(blob)
    head += b"\0" * ((-len(head)) % _ALIGN)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(head + data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


class _Reader:
    def __init__(self, buf: bytes):
        self.buf = buf
        self.pos = 0

    def take(self, fmt: str):
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.buf):
            raise ValueError("cvec file truncated")
        vals = struct.unpack_from(fmt, self.buf, self.pos)
        self.pos += size
        return vals

    def string(self) -> str:
        (n,) = self.take("<Q")
        if self.pos + n > len(self.buf):
            raise ValueError("cvec file truncated")
        raw = self.buf[self.pos:self.pos + n]
        self.pos += n
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ValueError("cvec string is not utf-8") from e


def read_cvec(path: Path) -> dict[int, list[float]]:
    """Parse a control-vector GGUF written by write_cvec. Raises ValueError if bad."""
    try:
        buf = Path(path).read_bytes()
    except OSError as e:
        raise ValueError(f"cannot read cvec file: {e}") from e
    if buf[:4] != _MAGIC:
        raise ValueError("bad magic, not a GGUF file")
    r = _Reader(buf)
    r.pos = 4
    version, n_tensors, n_kv = r.take("<IQQ")
    if version != _VERSION:
        raise ValueError(f"unsupported GGUF version {version}")
    if n_tensors > 100_000 or n_kv > 100_000:
        raise ValueError("implausible tensor or key count")
    kv: dict[str, object] = {}
    for _ in range(n_kv):
        key = r.string()
        (typ,) = r.take("<I")
        if typ == _T_STRING:
            kv[key] = r.string()
        elif typ == _T_INT32:
            (kv[key],) = r.take("<i")
        elif typ in _SCALAR_SIZE:
            r.take(f"<{_SCALAR_SIZE[typ]}s")
        else:
            raise ValueError(f"unsupported value type {typ} for key {key!r}")
    if kv.get("general.architecture") != "controlvector":
        raise ValueError("not a controlvector file")
    infos: list[tuple[int, int, int]] = []  # layer, length, offset
    for _ in range(n_tensors):
        name = r.string()
        (n_dims,) = r.take("<I")
        if n_dims != 1:
            raise ValueError(f"tensor {name!r} is not 1-D")
        (length,) = r.take("<Q")
        ttype, offset = r.take("<IQ")
        if ttype != _TYPE_F32:
            raise ValueError(f"tensor {name!r} is not F32")
        if not name.startswith(_PREFIX):
            raise ValueError(f"unexpected tensor name {name!r}")
        try:
            layer = int(name[len(_PREFIX):])
        except ValueError as e:
            raise ValueError(f"bad layer in tensor name {name!r}") from e
        infos.append((layer, length, offset))
    base = r.pos + ((-r.pos) % _ALIGN)
    out: dict[int, list[float]] = {}
    for layer, length, offset in infos:
        start = base + offset
        end = start + 4 * length
        if end > len(buf):
            raise ValueError("cvec tensor data truncated")
        if layer in out:
            raise ValueError(f"duplicate layer {layer}")
        out[layer] = list(struct.unpack_from(f"<{length}f", buf, start))
    declared = kv.get("controlvector.layer_count")
    if declared is not None and declared != len(out):
        raise ValueError("layer_count does not match tensor count")
    return dict(sorted(out.items()))


def scaled_arg(path: Path, scale: float) -> str:
    """Value for llama-server --control-vector-scaled: '<path>:<scale>'."""
    return f"{Path(path)}:{scale:g}"
