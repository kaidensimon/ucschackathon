"""Memory readings from /proc/meminfo (spec 4.2, 6.2, 19).

All parsed values are kB, as the kernel reports them. The *_gib helpers convert to GiB.
On a machine without /proc/meminfo (the Windows dev box) read_meminfo returns a synthetic
128 GiB machine with about 115 GiB available, so the rest of the Host can run unchanged.
"""

from __future__ import annotations

import os

KB_PER_GIB = 1024 * 1024

# Synthetic reading for machines without /proc/meminfo: 128 GiB total, about 115 GiB available,
# 8 GiB swap, all of it free.
_SYNTHETIC: dict[str, int] = {
    "MemTotal": 128 * KB_PER_GIB,
    "MemAvailable": 115 * KB_PER_GIB,
    "SwapTotal": 8 * KB_PER_GIB,
    "SwapFree": 8 * KB_PER_GIB,
}


def parse_meminfo(text: str) -> dict[str, int]:
    """Parse /proc/meminfo text into {key: kB}. Lines that do not hold an integer value are skipped."""
    out: dict[str, int] = {}
    for line in text.splitlines():
        key, sep, rest = line.partition(":")
        if not sep:
            continue
        parts = rest.split()
        if not parts:
            continue
        try:
            out[key.strip()] = int(parts[0])
        except ValueError:
            continue
    return out


def read_meminfo(path: str = "/proc/meminfo") -> dict[str, int]:
    """Read and parse the meminfo file. A missing file yields the synthetic 128 GiB reading."""
    if not os.path.isfile(path):
        return dict(_SYNTHETIC)
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return parse_meminfo(fh.read())


def available_gib(info: dict[str, int]) -> float:
    """MemAvailable in GiB. Missing key reads as 0."""
    return info.get("MemAvailable", 0) / KB_PER_GIB


def used_gib(info: dict[str, int]) -> float:
    """MemTotal minus MemAvailable, in GiB. Never negative."""
    used = info.get("MemTotal", 0) - info.get("MemAvailable", 0)
    return max(used, 0) / KB_PER_GIB


def swap_used_gib(info: dict[str, int]) -> float:
    """SwapTotal minus SwapFree, in GiB. Never negative."""
    used = info.get("SwapTotal", 0) - info.get("SwapFree", 0)
    return max(used, 0) / KB_PER_GIB
