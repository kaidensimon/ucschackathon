"""A bigger built-in truth set for the activation probe, before any council history exists.

Twelve kinds of (true statement, near-miss false statement) pairs. They sit beside the four
kinds of dataset.statement_pairs (capitals, units, arithmetic, ordering) and reuse its Pair.

Group id: a Pair carries both twins, and Pair.task_id is the group (as in dataset.py). It reads
"tset-<kind>-<slug>", so the true and false twin always share it.

Pure: no I/O, no clock; randomness only from the seed (one Random per kind, seeded by
"<seed>:<kind>").
"""
from __future__ import annotations

import random
import re
from typing import Callable, Iterator, Optional

from council.probe.dataset import MONTHS, Pair

PREFIX = "tset"

# ---------------------------------------------------------------------- tables

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# (name, symbol, atomic number)
ELEMENTS: list[tuple[str, str, int]] = [
    ("Hydrogen", "H", 1), ("Helium", "He", 2), ("Lithium", "Li", 3), ("Beryllium", "Be", 4),
    ("Boron", "B", 5), ("Carbon", "C", 6), ("Nitrogen", "N", 7), ("Oxygen", "O", 8),
    ("Fluorine", "F", 9), ("Neon", "Ne", 10), ("Sodium", "Na", 11), ("Magnesium", "Mg", 12),
    ("Aluminium", "Al", 13), ("Silicon", "Si", 14), ("Phosphorus", "P", 15), ("Sulfur", "S", 16),
    ("Chlorine", "Cl", 17), ("Argon", "Ar", 18), ("Potassium", "K", 19), ("Calcium", "Ca", 20),
    ("Titanium", "Ti", 22), ("Chromium", "Cr", 24), ("Manganese", "Mn", 25), ("Iron", "Fe", 26),
    ("Cobalt", "Co", 27), ("Nickel", "Ni", 28), ("Copper", "Cu", 29), ("Zinc", "Zn", 30),
    ("Bromine", "Br", 35), ("Krypton", "Kr", 36), ("Silver", "Ag", 47), ("Tin", "Sn", 50),
    ("Iodine", "I", 53), ("Xenon", "Xe", 54), ("Tungsten", "W", 74), ("Platinum", "Pt", 78),
    ("Gold", "Au", 79), ("Mercury", "Hg", 80), ("Lead", "Pb", 82), ("Uranium", "U", 92),
]

WORDS = [
    "apple", "banana", "cherry", "dog", "elephant", "fox", "grape", "horse", "igloo", "jungle",
    "kite", "lemon", "mango", "night", "orange", "piano", "queen", "river", "sun", "tiger",
    "umbrella", "violin", "window", "yellow", "zebra", "anchor", "bridge", "castle", "desert",
    "engine", "forest", "garden", "harbor", "island", "jacket", "kettle", "ladder", "mirror",
    "needle", "ocean",
]

PLANETS = ["Mercury", "Venus", "Earth", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"]

# (phrase with article, sides)
POLYGONS: list[tuple[str, int]] = [
    ("A triangle", 3), ("A square", 4), ("A rectangle", 4), ("A pentagon", 5), ("A hexagon", 6),
    ("A heptagon", 7), ("An octagon", 8), ("A nonagon", 9), ("A decagon", 10),
    ("A quadrilateral", 4), ("A rhombus", 4), ("A parallelogram", 4),
]
# (shape without article, interior angle sum)
ANGLE_SUMS: list[tuple[str, int]] = [
    ("triangle", 180), ("quadrilateral", 360), ("pentagon", 540), ("hexagon", 720),
    ("heptagon", 900), ("octagon", 1080),
]
# (frame with {x}, count)
SOLIDS: list[tuple[str, int]] = [
    ("A cube has {x} faces.", 6), ("A cube has {x} edges.", 12), ("A cube has {x} vertices.", 8),
    ("A tetrahedron has {x} faces.", 4), ("An octahedron has {x} faces.", 8),
]

# (frame with {x}, value)
CONSTANTS: list[tuple[str, int]] = [
    ("Water boils at {x} degrees Celsius at sea level.", 100),
    ("Water boils at {x} degrees Fahrenheit at sea level.", 212),
    ("Water freezes at {x} degrees Celsius.", 0),
    ("Water freezes at {x} degrees Fahrenheit.", 32),
    ("Water freezes at about {x} kelvin.", 273),
    ("Water boils at about {x} kelvin at sea level.", 373),
    ("Ethanol boils at about {x} degrees Celsius.", 78),
    ("Liquid nitrogen boils at about {x} degrees Celsius.", -196),
    ("Mercury freezes at about {x} degrees Celsius.", -39),
    ("Iron melts at about {x} degrees Celsius.", 1538),
    ("Absolute zero is about {x} degrees Celsius.", -273),
    ("Normal human body temperature is about {x} degrees Celsius.", 37),
    ("Oxygen boils at about {x} degrees Celsius.", -183),
    ("Lead melts at about {x} degrees Celsius.", 327),
    ("Gold melts at about {x} degrees Celsius.", 1064),
]

ISO_CODES: list[tuple[str, str]] = [
    ("France", "FR"), ("Germany", "DE"), ("Italy", "IT"), ("Spain", "ES"), ("Japan", "JP"),
    ("China", "CN"), ("India", "IN"), ("Brazil", "BR"), ("Canada", "CA"), ("Australia", "AU"),
    ("Mexico", "MX"), ("Russia", "RU"), ("the United Kingdom", "GB"), ("the United States", "US"),
    ("Egypt", "EG"), ("Kenya", "KE"), ("Nigeria", "NG"), ("South Africa", "ZA"),
    ("Argentina", "AR"), ("Chile", "CL"), ("Peru", "PE"), ("Sweden", "SE"), ("Norway", "NO"),
    ("Finland", "FI"), ("Denmark", "DK"), ("Poland", "PL"), ("Greece", "GR"), ("Turkey", "TR"),
    ("South Korea", "KR"), ("Switzerland", "CH"),
]


# ---------------------------------------------------------------------- helpers


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def _ordinal(k: int) -> str:
    if 10 <= k % 100 <= 20:
        return f"{k}th"
    return f"{k}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th') }"


def _mk(kind: str, slug: str, category: str, frame: str, truth: object, lie: object) -> Pair:
    """Pair from a frame with one {x} slot. truth and lie are the two fillers."""
    t, f = str(truth), str(lie)
    return Pair(f"{PREFIX}-{kind}-{_slug(slug)}", category,
                frame.format(x=t), frame.format(x=f), t, f)


def _mk_full(kind: str, slug: str, category: str, honest: str, lie: str) -> Pair:
    return Pair(f"{PREFIX}-{kind}-{_slug(slug)}", category, honest, lie, honest, lie)


def _off(v: int, rng: random.Random, steps: tuple[int, ...] = (-2, -1, 1, 2)) -> int:
    """A near wrong integer; stays non-negative when v is."""
    cands = [v + s for s in steps if v + s != v and (v < 0 or v + s >= 0)]
    return rng.choice(cands) if cands else v + 1


def _like(value: str, pool: list[str], rng: random.Random) -> str:
    """Another entry of pool that looks like value: same first letter, else same length, else any."""
    others = [p for p in pool if p != value]
    for test in (lambda p: p[0] == value[0] and len(p) == len(value),
                 lambda p: p[0] == value[0], lambda p: len(p) == len(value)):
        near = [p for p in others if test(p)]
        if near:
            return rng.choice(near)
    return rng.choice(others)


def _shuffled(rows: list, rng: random.Random) -> list:
    rows = list(rows)
    rng.shuffle(rows)
    return rows


def _primes_below(limit: int) -> list[int]:
    sieve = [True] * limit
    sieve[0:2] = [False, False]
    for i in range(2, int(limit ** 0.5) + 1):
        if sieve[i]:
            for j in range(i * i, limit, i):
                sieve[j] = False
    return [i for i, ok in enumerate(sieve) if ok]


PRIMES = _primes_below(200)
_PRIME_SET = set(PRIMES)


# ---------------------------------------------------------------------- generators
# Each takes its own Random and yields distinct-looking pairs, finite or endless.


def _compare(rng: random.Random) -> Iterator[Pair]:
    while True:
        a = rng.randint(10, 99999)
        b = a + rng.choice((-1, 1)) * rng.randint(1, max(2, a // 20))
        if b < 1 or a == b:
            continue
        word = rng.choice(("larger", "smaller"))
        big, small = max(a, b), min(a, b)
        first, second = (big, small) if word == "larger" else (small, big)
        frame = "{a} is " + word + " than {b}."
        yield _mk_full("compare", f"{first}-{word}-{second}", "math",
                       frame.format(a=first, b=second), frame.format(a=second, b=first))


def _calendar(rng: random.Random) -> Iterator[Pair]:
    rows: list[Pair] = []
    for i, m in enumerate(MONTHS):
        d = MONTH_DAYS[i]
        lie_d = {31: 30, 30: 31, 28: 29}[d]
        rows.append(_mk("calendar", f"days-{m}", "knowledge",
                        f"{m} has {{x}} days in a common year.", d, lie_d))
        k = i + 1
        lie_k = rng.choice([c for c in (k - 1, k + 1) if 1 <= c <= 12])
        rows.append(_mk("calendar", f"pos-{m}", "knowledge",
                        f"{m} is the {{x}} month of the year.", _ordinal(k), _ordinal(lie_k)))
    for i, day in enumerate(WEEKDAYS):
        nxt = WEEKDAYS[(i + 1) % 7]
        wrong = WEEKDAYS[(i + rng.choice((2, 6))) % 7]  # two after, or the day before
        rows.append(_mk("calendar", f"after-{day}", "knowledge",
                        f"The day after {day} is {{x}}.", nxt, wrong))
    yield from _shuffled(rows, rng)


def _element(rng: random.Random) -> Iterator[Pair]:
    symbols = [s for _, s, _ in ELEMENTS]
    rows: list[Pair] = []
    for name, sym, z in ELEMENTS:
        rows.append(_mk("element", f"symbol-{name}", "science",
                        f"The chemical symbol for {name} is {{x}}.", sym, _like(sym, symbols, rng)))
        rows.append(_mk("element", f"number-{name}", "science",
                        f"The atomic number of {name} is {{x}}.", z, _off(z, rng, (-3, -2, -1, 1, 2, 3))))
    yield from _shuffled(rows, rng)


def _wordlen(rng: random.Random) -> Iterator[Pair]:
    for w in _shuffled(WORDS, rng):
        n = len(w)
        yield _mk("wordlen", w, "language", f'The word "{w}" has {{x}} letters.', n,
                  _off(n, rng, (-2, -1, 1, 2)) if n > 2 else n + 1)


def _pyexpr(rng: random.Random) -> Iterator[Pair]:
    while True:
        lst = [rng.randint(1, 9) for _ in range(rng.randint(2, 5))]
        w = rng.choice(WORDS)
        a, b = rng.randint(10, 99), rng.randint(2, 9)
        pick = rng.randrange(10)
        if pick == 0:
            expr, val = f"len({lst})", len(lst)
        elif pick == 1:
            expr, val = f"sum({lst})", sum(lst)
        elif pick == 2:
            expr, val = f"max({lst})", max(lst)
        elif pick == 3:
            expr, val = f"min({lst})", min(lst)
        elif pick == 4:
            expr, val = f'len("{w}")', len(w)
        elif pick == 5:
            expr, val = f"{b} ** {a % 3 + 2}", b ** (a % 3 + 2)
        elif pick == 6:
            expr, val = f"{a} // {b}", a // b
        elif pick == 7:
            expr, val = f"{a} % {b}", a % b
        elif pick == 8:
            ch = rng.choice(w)
            expr, val = f'"{w}".count("{ch}")', w.count(ch)
        else:
            i = rng.randrange(len(lst))
            expr, val = f"{lst}[{i}]", lst[i]
        yield _mk("pyexpr", expr, "code", "In Python, " + expr + " is {x}.", val, _off(val, rng))


def _divisibility(rng: random.Random) -> Iterator[Pair]:
    prime_rows: list[Pair] = []
    for p in PRIMES:
        near = [c for c in range(max(4, p - 6), p + 7) if c < 200 and c not in _PRIME_SET and c != p]
        comp = rng.choice(sorted(near, key=lambda c: abs(c - p))[:3])
        prime_rows.append(_mk_full("divisibility", f"prime-{p}", "math",
                                   f"{p} is a prime number.", f"{comp} is a prime number."))
    div_rows: list[Pair] = []
    for d in (3, 4, 6, 7, 9, 11):
        for k in range(2, 199 // d + 1):
            a = d * k
            if a >= 200:
                continue
            miss = a + rng.choice((-1, 1))
            div_rows.append(_mk_full("divisibility", f"div-{a}-by-{d}", "math",
                                     f"{a} is divisible by {d}.", f"{miss} is divisible by {d}."))
    prime_rows, div_rows = _shuffled(prime_rows, rng), _shuffled(div_rows, rng)
    # Primes and divisibility take turns; the longer list runs on alone at the end.
    for i in range(max(len(prime_rows), len(div_rows))):
        for rows in (prime_rows, div_rows):
            if i < len(rows):
                yield rows[i]


def _multable(rng: random.Random) -> Iterator[Pair]:
    rows: list[Pair] = []
    for a in range(2, 13):
        for b in range(a, 13):
            x = a * b
            lie = x + rng.choice((-1, 1)) * rng.choice((a, b))  # off by one whole step
            if lie != x and lie > 0:
                rows.append(_mk("multable", f"{a}x{b}", "math", f"{a} times {b} is {{x}}.", x, lie))
    yield from _shuffled(rows, rng)


def _planet(rng: random.Random) -> Iterator[Pair]:
    rows: list[Pair] = []
    for i, p in enumerate(PLANETS):
        k = i + 1
        lie_k = rng.choice([c for c in (k - 1, k + 1) if 1 <= c <= 8])
        rows.append(_mk("planet", f"pos-{p}", "science",
                        f"{p} is planet number {{x}} from the Sun.", k, lie_k))
        for q in PLANETS[i + 1:]:
            rows.append(_mk_full("planet", f"closer-{p}-{q}", "science",
                                 f"{p} is closer to the Sun than {q}.",
                                 f"{q} is closer to the Sun than {p}."))
    yield from _shuffled(rows, rng)


def _shape(rng: random.Random) -> Iterator[Pair]:
    rows: list[Pair] = []
    for phrase, n in POLYGONS:
        rows.append(_mk("shape", f"sides-{phrase}", "math", phrase + " has {x} sides.", n, _off(n, rng, (-1, 1))))
    for name, total in ANGLE_SUMS:
        rows.append(_mk("shape", f"angles-{name}", "math",
                        f"The interior angles of a {name} add up to {{x}} degrees.",
                        total, total + rng.choice((-180, 180)) if total > 180 else 360))
    for frame, n in SOLIDS:
        rows.append(_mk("shape", frame.replace("{x}", "n"), "math", frame, n, _off(n, rng, (-2, -1, 1, 2))))
    yield from _shuffled(rows, rng)


def _alpha(rng: random.Random) -> Iterator[Pair]:
    seen: set[tuple[str, str]] = set()
    while len(seen) < len(WORDS) * (len(WORDS) - 1) // 2:
        a, b = sorted(rng.sample(WORDS, 2))
        if (a, b) in seen:
            continue
        seen.add((a, b))
        word = rng.choice(("before", "after"))
        first, second = (a, b) if word == "before" else (b, a)
        frame = "In alphabetical order, {a} comes " + word + " {b}."
        yield _mk_full("alpha", f"{a}-{b}", "logic",
                       frame.format(a=first, b=second), frame.format(a=second, b=first))


def _constant(rng: random.Random) -> Iterator[Pair]:
    for frame, v in _shuffled(CONSTANTS, rng):
        step = max(3, int(round(abs(v) * rng.choice((0.05, 0.1, 0.2)))))
        lie = v + rng.choice((-1, 1)) * step
        yield _mk("constant", frame.replace("{x}", "n"), "science", frame, v, lie)


def _iso(rng: random.Random) -> Iterator[Pair]:
    codes = [c for _, c in ISO_CODES]
    for country, code in _shuffled(ISO_CODES, rng):
        yield _mk("iso", country, "knowledge",
                  f"The ISO 3166 alpha-2 code for {country} is {{x}}.", code, _like(code, codes, rng))


_GENERATORS: dict[str, Callable[[random.Random], Iterator[Pair]]] = {
    "compare": _compare, "calendar": _calendar, "element": _element, "wordlen": _wordlen,
    "pyexpr": _pyexpr, "divisibility": _divisibility, "multable": _multable, "planet": _planet,
    "shape": _shape, "alpha": _alpha, "constant": _constant, "iso": _iso,
}


def kinds() -> list[str]:
    """The kinds of statement pairs made here, in the order they take turns."""
    return list(_GENERATORS)


def kind_of(pair: Pair) -> Optional[str]:
    """The kind of a pair made here, or None for a pair from elsewhere."""
    parts = pair.task_id.split("-", 2)
    return parts[1] if len(parts) > 2 and parts[0] == PREFIX else None


def more_statement_pairs(seed: int = 0, n: int = 400) -> list[Pair]:
    """Up to n (true, near-miss false) statement pairs, kinds taking turns.

    Small tables run dry before n; the rest fill from the kinds that still have more. A task_id
    (the group, shared by both twins) and every statement text appears only once.
    """
    want = max(0, int(n))
    streams = {k: _GENERATORS[k](random.Random(f"{seed}:{k}")) for k in _GENERATORS}
    misses = {k: 0 for k in streams}
    out: list[Pair] = []
    ids: set[str] = set()
    texts: set[str] = set()
    while len(out) < want and streams:
        for kind in list(streams):
            if len(out) >= want:
                break
            try:
                pair = next(streams[kind])
            except StopIteration:
                del streams[kind]
                continue
            if (pair.task_id in ids or pair.honest_text == pair.lie_text
                    or pair.honest_text in texts or pair.lie_text in texts):
                misses[kind] += 1
                if misses[kind] > 500:
                    del streams[kind]
                continue
            misses[kind] = 0
            ids.add(pair.task_id)
            texts.update((pair.honest_text, pair.lie_text))
            out.append(pair)
    return out


def labelled(pairs: list[Pair]) -> list[tuple[str, int, str]]:
    """(text, label, group) rows, label 1 true and 0 false. Twins share the group."""
    rows: list[tuple[str, int, str]] = []
    for p in pairs:
        rows.append((p.honest_text, 1, p.task_id))
        rows.append((p.lie_text, 0, p.task_id))
    return rows


__all__ = ["kind_of", "kinds", "labelled", "more_statement_pairs"]
