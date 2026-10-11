"""Canned BUILD scenario for mock mode: a small Python package "ratelimiter".

Every reply here is coherent with the others, so the whole works pipeline (decompose, lint,
workers, checks, review, memory, tribunal) can run for real with no model server.

Pure functions, deterministic. No imports from the rest of the package; every function
returns a fresh plain dict shaped for the matching schema in council.core.schemas.

Exactly one task (BUGGY_TASK_ID) returns code with a deliberate bug on attempt 1. Its command
check fails. Attempt 2 and later return the correct code.
"""

from __future__ import annotations

import copy
from typing import Any

TOPIC = "Build a small Python package 'ratelimiter'"
PACKAGE = "ratelimiter"
BUGGY_TASK_ID = "t02_token_bucket"
GLOBAL_ACCEPTANCE_CMD = "python -m unittest discover -s tests"

# --------------------------------------------------------------------------------------
# File contents (real, working)
# --------------------------------------------------------------------------------------

_INIT_PY = '''"""ratelimiter: small in-process rate limiters.

Import the parts from their modules:
    from ratelimiter.token_bucket import TokenBucket
    from ratelimiter.sliding_window import SlidingWindow
    from ratelimiter.factory import make_limiter
"""

__version__ = "0.1.0"
'''

_CLOCK_PY = '''"""Clocks. A clock is any callable with no arguments that returns seconds as a float."""

import time


def monotonic_clock():
    """The default clock."""
    return time.monotonic()


class ManualClock:
    """A clock that only moves when told to. For tests."""

    def __init__(self, start=0.0):
        self.now = float(start)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        if seconds < 0:
            raise ValueError("seconds must be >= 0")
        self.now += float(seconds)
        return self.now
'''

_TOKEN_BUCKET_HEAD = '''"""Token bucket rate limiter."""

from ratelimiter.clock import monotonic_clock


class TokenBucket:
    """Holds up to `capacity` tokens and refills `refill_rate` tokens per second.

    Starts full. Each allowed request spends `cost` tokens.
    """

    def __init__(self, capacity, refill_rate, clock=None):
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        if refill_rate < 0:
            raise ValueError("refill_rate must be >= 0")
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self._clock = clock if clock is not None else monotonic_clock
        self._tokens = self.capacity
        self._last = self._clock()

    def _refill(self):
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._last = now
'''

_TOKEN_BUCKET_TAIL = '''
    @property
    def available(self):
        """Tokens in the bucket right now."""
        self._refill()
        return self._tokens

    def allow(self, cost=1):
        """Spend `cost` tokens if the bucket has them. Return True if the request may go."""
        if cost <= 0:
            raise ValueError("cost must be > 0")
        self._refill()
        if self._tokens >= cost:
            self._tokens -= cost
            return True
        return False
'''

_TOKEN_BUCKET_PY = (
    _TOKEN_BUCKET_HEAD
    + "        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)\n"
    + _TOKEN_BUCKET_TAIL
)

# The deliberate bug: the refill is not capped at capacity, so an idle bucket overfills.
_TOKEN_BUCKET_BUGGY_PY = (
    _TOKEN_BUCKET_HEAD
    + "        self._tokens = self._tokens + elapsed * self.refill_rate\n"
    + _TOKEN_BUCKET_TAIL
)

_SLIDING_WINDOW_PY = '''"""Sliding window rate limiter."""

from collections import deque

from ratelimiter.clock import monotonic_clock


class SlidingWindow:
    """Allows at most `limit` requests in any span of `window_s` seconds."""

    def __init__(self, limit, window_s, clock=None):
        if limit <= 0:
            raise ValueError("limit must be > 0")
        if window_s <= 0:
            raise ValueError("window_s must be > 0")
        self.limit = int(limit)
        self.window_s = float(window_s)
        self._clock = clock if clock is not None else monotonic_clock
        self._stamps = deque()

    def _evict(self, now):
        cutoff = now - self.window_s
        while self._stamps and self._stamps[0] <= cutoff:
            self._stamps.popleft()

    @property
    def count(self):
        """Requests counted in the current window."""
        self._evict(self._clock())
        return len(self._stamps)

    def allow(self):
        """Record the request if the window has room. Return True if it may go."""
        now = self._clock()
        self._evict(now)
        if len(self._stamps) < self.limit:
            self._stamps.append(now)
            return True
        return False
'''

_FACTORY_PY = '''"""Build a limiter by name."""

from ratelimiter.sliding_window import SlidingWindow
from ratelimiter.token_bucket import TokenBucket

KINDS = ("token_bucket", "sliding_window")


def make_limiter(kind, **kwargs):
    """Return a limiter. `kind` is "token_bucket" or "sliding_window".

    token_bucket   : capacity, refill_rate, clock (optional)
    sliding_window : limit, window_s, clock (optional)
    """
    if kind == "token_bucket":
        return TokenBucket(**kwargs)
    if kind == "sliding_window":
        return SlidingWindow(**kwargs)
    raise ValueError("unknown limiter kind: %r (use one of %s)" % (kind, ", ".join(KINDS)))
'''

_TEST_TOKEN_BUCKET_PY = '''import unittest

from ratelimiter.clock import ManualClock
from ratelimiter.token_bucket import TokenBucket


class TestTokenBucket(unittest.TestCase):
    def setUp(self):
        self.clock = ManualClock()

    def test_starts_full_then_refuses(self):
        b = TokenBucket(3, 1.0, clock=self.clock)
        self.assertTrue(b.allow())
        self.assertTrue(b.allow())
        self.assertTrue(b.allow())
        self.assertFalse(b.allow())

    def test_refills_over_time(self):
        b = TokenBucket(2, 2.0, clock=self.clock)
        self.assertTrue(b.allow(2))
        self.assertFalse(b.allow())
        self.clock.advance(0.5)
        self.assertTrue(b.allow())
        self.assertFalse(b.allow())

    def test_refill_is_capped_at_capacity(self):
        b = TokenBucket(2, 1.0, clock=self.clock)
        self.clock.advance(100)
        self.assertEqual(b.available, 2.0)
        self.assertTrue(b.allow())
        self.assertTrue(b.allow())
        self.assertFalse(b.allow())

    def test_cost_larger_than_tokens_is_refused_and_spends_nothing(self):
        b = TokenBucket(2, 0.0, clock=self.clock)
        self.assertFalse(b.allow(3))
        self.assertEqual(b.available, 2.0)

    def test_bad_arguments(self):
        with self.assertRaises(ValueError):
            TokenBucket(0, 1.0)
        with self.assertRaises(ValueError):
            TokenBucket(1, -1.0)
        with self.assertRaises(ValueError):
            TokenBucket(1, 1.0, clock=self.clock).allow(0)


if __name__ == "__main__":
    unittest.main()
'''

_TEST_SLIDING_WINDOW_PY = '''import unittest

from ratelimiter.clock import ManualClock
from ratelimiter.sliding_window import SlidingWindow


class TestSlidingWindow(unittest.TestCase):
    def setUp(self):
        self.clock = ManualClock()

    def test_allows_up_to_limit(self):
        w = SlidingWindow(2, 10.0, clock=self.clock)
        self.assertTrue(w.allow())
        self.assertTrue(w.allow())
        self.assertFalse(w.allow())
        self.assertEqual(w.count, 2)

    def test_old_requests_leave_the_window(self):
        w = SlidingWindow(2, 10.0, clock=self.clock)
        self.assertTrue(w.allow())
        self.clock.advance(6)
        self.assertTrue(w.allow())
        self.assertFalse(w.allow())
        self.clock.advance(4)
        self.assertTrue(w.allow())
        self.assertFalse(w.allow())
        self.assertEqual(w.count, 2)

    def test_refused_requests_are_not_counted(self):
        w = SlidingWindow(1, 5.0, clock=self.clock)
        self.assertTrue(w.allow())
        for _ in range(5):
            self.assertFalse(w.allow())
        self.clock.advance(5)
        self.assertTrue(w.allow())

    def test_bad_arguments(self):
        with self.assertRaises(ValueError):
            SlidingWindow(0, 1.0)
        with self.assertRaises(ValueError):
            SlidingWindow(1, 0)


if __name__ == "__main__":
    unittest.main()
'''

_TEST_FACTORY_PY = '''import unittest

from ratelimiter.clock import ManualClock
from ratelimiter.factory import KINDS, make_limiter
from ratelimiter.sliding_window import SlidingWindow
from ratelimiter.token_bucket import TokenBucket


class TestFactory(unittest.TestCase):
    def test_token_bucket(self):
        b = make_limiter("token_bucket", capacity=1, refill_rate=0.0, clock=ManualClock())
        self.assertIsInstance(b, TokenBucket)
        self.assertTrue(b.allow())
        self.assertFalse(b.allow())

    def test_sliding_window(self):
        w = make_limiter("sliding_window", limit=1, window_s=1.0, clock=ManualClock())
        self.assertIsInstance(w, SlidingWindow)
        self.assertTrue(w.allow())
        self.assertFalse(w.allow())

    def test_unknown_kind(self):
        with self.assertRaises(ValueError):
            make_limiter("leaky_bucket")

    def test_kinds_all_build(self):
        self.assertEqual(KINDS, ("token_bucket", "sliding_window"))


if __name__ == "__main__":
    unittest.main()
'''

_README_MD = '''# ratelimiter

Small in-process rate limiters. Standard library only.

## Token bucket

Holds up to `capacity` tokens and refills `refill_rate` tokens per second. Allows short bursts.

```python
from ratelimiter.token_bucket import TokenBucket

bucket = TokenBucket(capacity=20, refill_rate=5.0)
if bucket.allow():
    handle_request()
```

## Sliding window

Allows at most `limit` requests in any span of `window_s` seconds. No burst at window edges.

```python
from ratelimiter.sliding_window import SlidingWindow

window = SlidingWindow(limit=100, window_s=60.0)
if window.allow():
    handle_request()
```

## Factory

```python
from ratelimiter.factory import make_limiter

limiter = make_limiter("token_bucket", capacity=20, refill_rate=5.0)
limiter = make_limiter("sliding_window", limit=100, window_s=60.0)
```

## Tests

```
python -m unittest discover -s tests
```

Every limiter takes an optional `clock`. Pass `ratelimiter.clock.ManualClock()` to test without sleeping.
'''

# --------------------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------------------

_INTERFACES: list[dict[str, Any]] = [
    {
        "name": "Clock",
        "kind": "type",
        "definition": (
            "A clock is any callable with no arguments that returns seconds as a float. "
            "ratelimiter/clock.py defines monotonic_clock() and class ManualClock(start=0.0) "
            "with __call__() -> float and advance(seconds) -> float."
        ),
    },
    {
        "name": "TokenBucket",
        "kind": "type",
        "definition": (
            "class TokenBucket(capacity, refill_rate, clock=None) in ratelimiter/token_bucket.py. "
            "Starts full. allow(cost=1) -> bool spends tokens when it returns True. "
            "Property available -> float. Tokens never exceed capacity. "
            "ValueError when capacity <= 0, refill_rate < 0 or cost <= 0."
        ),
    },
    {
        "name": "SlidingWindow",
        "kind": "type",
        "definition": (
            "class SlidingWindow(limit, window_s, clock=None) in ratelimiter/sliding_window.py. "
            "allow() -> bool; at most `limit` True results in any span of window_s seconds. "
            "Property count -> int. ValueError when limit <= 0 or window_s <= 0."
        ),
    },
    {
        "name": "make_limiter",
        "kind": "function",
        "definition": (
            "make_limiter(kind, **kwargs) in ratelimiter/factory.py. kind is 'token_bucket' or "
            "'sliding_window'; kwargs go to the class. ValueError on any other kind. "
            "KINDS = ('token_bucket', 'sliding_window')."
        ),
    },
]

_DELIVERABLES: list[dict[str, Any]] = [
    {
        "id": "d1_package",
        "description": "The ratelimiter package: clock, token bucket, sliding window, factory.",
        "paths": [
            "ratelimiter/__init__.py",
            "ratelimiter/clock.py",
            "ratelimiter/token_bucket.py",
            "ratelimiter/sliding_window.py",
            "ratelimiter/factory.py",
        ],
    },
    {
        "id": "d2_tests",
        "description": "unittest tests for every module.",
        "paths": [
            "tests/test_token_bucket.py",
            "tests/test_sliding_window.py",
            "tests/test_factory.py",
        ],
    },
    {"id": "d3_readme", "description": "A README with usage examples.", "paths": ["README.md"]},
]

_MILESTONES: list[dict[str, Any]] = [
    {
        "id": "m1_core",
        "title": "Core package",
        "description": "Clock, token bucket, sliding window and the factory.",
        "deliverables": ["d1_package"],
    },
    {
        "id": "m2_tests_docs",
        "title": "Tests and README",
        "description": "unittest tests for each module, and the README.",
        "deliverables": ["d2_tests", "d3_readme"],
    },
]

_GLOBAL_ACCEPTANCE: list[dict[str, Any]] = [
    {"type": "command", "id": "g1_unittest", "cmd": GLOBAL_ACCEPTANCE_CMD, "expect_exit": 0,
     "timeout_s": 120.0},
    {"type": "exists", "id": "g2_readme", "path": "README.md"},
]

_IFACE = {i["name"]: i for i in _INTERFACES}


def _file_checks(task_id: str, paths: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n, p in enumerate(paths, start=1):
        lang = "python" if p.endswith(".py") else "markdown"
        out.append({"type": "exists", "id": f"{task_id}.exists{n}", "path": p})
        out.append({"type": "parses", "id": f"{task_id}.parses{n}", "path": p, "language": lang})
    return out


def _cmd(task_id: str, cmd: str) -> dict[str, Any]:
    return {"type": "command", "id": f"{task_id}.cmd", "cmd": cmd, "expect_exit": 0, "timeout_s": 60.0}


def _task(task_id: str, milestone: str, title: str, kind: str, goal: str, write_set: list[str],
          deps: list[str], interfaces: list[str], extra_checks: list[dict[str, Any]],
          read_set: list[str] | None = None, contract: str = "") -> dict[str, Any]:
    return {
        "id": task_id,
        "milestone": milestone,  # not a MicroTask field; schemas ignore extras
        "title": title,
        "kind": kind,
        "goal": goal,
        "context": {
            "files": [],
            "interfaces": [copy.deepcopy(_IFACE[n]) for n in interfaces],
            "notes": "Python standard library only. No third-party imports.",
        },
        "read_set": list(read_set or []),
        "write_set": list(write_set),
        "output_contract": contract or ("Write the whole file with one write_file op per path: "
                                        + ", ".join(write_set)),
        "acceptance": _file_checks(task_id, write_set) + extra_checks,
        "deps": list(deps),
        "tier": "micro",
        "budget": {"max_output_tokens": 1500, "max_attempts": 3},
    }


_TASKS: list[dict[str, Any]] = [
    _task(
        "t01_package_clock", "m1_core", "Package init and clock", "create_file",
        "Create the ratelimiter package marker with __version__ and the clock module "
        "(monotonic_clock and ManualClock).",
        ["ratelimiter/__init__.py", "ratelimiter/clock.py"], [], ["Clock"],
        [_cmd("t01_package_clock",
              'python -c "from ratelimiter.clock import ManualClock, monotonic_clock; '
              'c = ManualClock(); c.advance(2.5); assert c() == 2.5; '
              'assert monotonic_clock() >= 0"')],
    ),
    _task(
        "t02_token_bucket", "m1_core", "Token bucket class", "create_file",
        "Write class TokenBucket. It starts full, refills over time, never holds more than "
        "capacity, and allow(cost) spends tokens only when it returns True.",
        ["ratelimiter/token_bucket.py"], ["t01_package_clock"], ["Clock", "TokenBucket"],
        [_cmd("t02_token_bucket",
              'python -c "from ratelimiter.clock import ManualClock; '
              'from ratelimiter.token_bucket import TokenBucket; '
              'c = ManualClock(); b = TokenBucket(2, 1.0, clock=c); '
              'assert b.allow() and b.allow() and not b.allow(); '
              'c.advance(10); '
              'assert b.allow() and b.allow() and not b.allow()"')],
        read_set=["ratelimiter/clock.py"],
    ),
    _task(
        "t03_sliding_window", "m1_core", "Sliding window class", "create_file",
        "Write class SlidingWindow. It keeps the timestamps of allowed requests and allows at "
        "most `limit` of them in any span of window_s seconds.",
        ["ratelimiter/sliding_window.py"], ["t01_package_clock"], ["Clock", "SlidingWindow"],
        [_cmd("t03_sliding_window",
              'python -c "from ratelimiter.clock import ManualClock; '
              'from ratelimiter.sliding_window import SlidingWindow; '
              'c = ManualClock(); w = SlidingWindow(2, 10.0, clock=c); '
              'assert w.allow() and w.allow() and not w.allow(); '
              'c.advance(10); '
              'assert w.allow() and w.count == 1"')],
        read_set=["ratelimiter/clock.py"],
    ),
    _task(
        "t04_factory", "m1_core", "Limiter factory", "create_file",
        "Write make_limiter(kind, **kwargs) and the KINDS tuple. Unknown kinds raise ValueError.",
        ["ratelimiter/factory.py"], ["t02_token_bucket", "t03_sliding_window"],
        ["TokenBucket", "SlidingWindow", "make_limiter"],
        [_cmd("t04_factory",
              'python -c "from ratelimiter.factory import make_limiter, KINDS; '
              'assert len(KINDS) == 2; '
              'assert make_limiter(KINDS[0], capacity=1, refill_rate=0.0).allow(); '
              'assert make_limiter(KINDS[1], limit=1, window_s=1.0).allow()"')],
        read_set=["ratelimiter/token_bucket.py", "ratelimiter/sliding_window.py"],
    ),
    _task(
        "t05_test_token_bucket", "m2_tests_docs", "Tests for the token bucket", "write_test",
        "Write unittest tests for TokenBucket using ManualClock: starts full, refills, capped at "
        "capacity, refused cost spends nothing, bad arguments raise ValueError.",
        ["tests/test_token_bucket.py"], ["t02_token_bucket"], ["Clock", "TokenBucket"],
        [_cmd("t05_test_token_bucket", "python -m unittest discover -s tests -p test_token_bucket.py")],
        read_set=["ratelimiter/token_bucket.py"],
    ),
    _task(
        "t06_test_sliding_window", "m2_tests_docs", "Tests for the sliding window", "write_test",
        "Write unittest tests for SlidingWindow using ManualClock: allows up to the limit, old "
        "requests leave the window, refused requests are not counted, bad arguments raise.",
        ["tests/test_sliding_window.py"], ["t03_sliding_window"], ["Clock", "SlidingWindow"],
        [_cmd("t06_test_sliding_window", "python -m unittest discover -s tests -p test_sliding_window.py")],
        read_set=["ratelimiter/sliding_window.py"],
    ),
    _task(
        "t07_test_factory", "m2_tests_docs", "Tests for the factory", "write_test",
        "Write unittest tests for make_limiter: both kinds build the right class and work, and "
        "an unknown kind raises ValueError.",
        ["tests/test_factory.py"], ["t04_factory"], ["Clock", "make_limiter"],
        [_cmd("t07_test_factory", "python -m unittest discover -s tests -p test_factory.py")],
        read_set=["ratelimiter/factory.py"],
    ),
    _task(
        "t08_readme", "m2_tests_docs", "README", "write_doc",
        "Write README.md: what the package is, one usage example each for TokenBucket, "
        "SlidingWindow and make_limiter, and how to run the tests.",
        ["README.md"], ["t04_factory"], ["TokenBucket", "SlidingWindow", "make_limiter"],
        [
            {"type": "contains", "id": "t08_readme.contains1", "path": "README.md", "pattern": "TokenBucket"},
            {"type": "contains", "id": "t08_readme.contains2", "path": "README.md", "pattern": "SlidingWindow"},
            {"type": "contains", "id": "t08_readme.contains3", "path": "README.md", "pattern": "make_limiter"},
        ],
    ),
]

TASK_IDS: tuple[str, ...] = tuple(t["id"] for t in _TASKS)

_FILES: dict[str, dict[str, str]] = {
    "t01_package_clock": {"ratelimiter/__init__.py": _INIT_PY, "ratelimiter/clock.py": _CLOCK_PY},
    "t02_token_bucket": {"ratelimiter/token_bucket.py": _TOKEN_BUCKET_PY},
    "t03_sliding_window": {"ratelimiter/sliding_window.py": _SLIDING_WINDOW_PY},
    "t04_factory": {"ratelimiter/factory.py": _FACTORY_PY},
    "t05_test_token_bucket": {"tests/test_token_bucket.py": _TEST_TOKEN_BUCKET_PY},
    "t06_test_sliding_window": {"tests/test_sliding_window.py": _TEST_SLIDING_WINDOW_PY},
    "t07_test_factory": {"tests/test_factory.py": _TEST_FACTORY_PY},
    "t08_readme": {"README.md": _README_MD},
}

_APPROACH = (
    "Build a standard-library Python package 'ratelimiter' with a token bucket, a sliding window "
    "and a factory. Every limiter takes an injectable clock so tests never sleep. "
    "Cover each module with unittest tests and document usage in a README."
)


def plan_for(task: str) -> dict:
    """A valid Plan for the scenario. `task` becomes the goal (the scenario topic if empty)."""
    return {
        "goal": (task or "").strip() or TOPIC,
        "approach": _APPROACH,
        "interfaces": copy.deepcopy(_INTERFACES),
        "deliverables": copy.deepcopy(_DELIVERABLES),
        "global_acceptance": copy.deepcopy(_GLOBAL_ACCEPTANCE),
        "out_of_scope": [
            "Distributed or Redis-backed limiting",
            "Thread safety",
            "Packaging metadata (pyproject, setup.py)",
        ],
        "risks": [
            "A bucket that is not capped at capacity lets an idle client burst without bound.",
            "Tests that sleep are slow and flaky; use the injected clock.",
        ],
        "tasks": copy.deepcopy(_TASKS),
    }


def decompose_reply(call_index: int) -> dict:
    """Foreman decompose replies. call_index is 0-based.

    0      : {goal, approach, interfaces, deliverables, milestones, global_acceptance,
              out_of_scope, risks}
    1..n   : {milestone, tasks} for milestone number call_index (1 = first milestone)
    beyond : {milestone: None, tasks: []}
    """
    if call_index <= 0:
        p = plan_for("")
        return {
            "goal": p["goal"],
            "approach": p["approach"],
            "interfaces": p["interfaces"],
            "deliverables": p["deliverables"],
            "milestones": copy.deepcopy(_MILESTONES),
            "global_acceptance": p["global_acceptance"],
            "out_of_scope": p["out_of_scope"],
            "risks": p["risks"],
        }
    if call_index > len(_MILESTONES):
        return {"milestone": None, "tasks": []}
    mid = _MILESTONES[call_index - 1]["id"]
    return {"milestone": mid, "tasks": [copy.deepcopy(t) for t in _TASKS if t["milestone"] == mid]}


def worker_output_for(task_id: str, attempt: int) -> dict:
    """WorkerOutput for one task. attempt is 1-based. Unknown task ids come back blocked."""
    files = _FILES.get(task_id)
    if files is None:
        return {"ops": [], "notes": "", "blocked": f"unknown task id: {task_id}"}
    buggy = task_id == BUGGY_TASK_ID and attempt <= 1
    ops = []
    for path, content in files.items():
        if buggy:
            content = _TOKEN_BUCKET_BUGGY_PY
        ops.append({"op": "write_file", "path": path, "content": content})
    if buggy:
        notes = "Wrote TokenBucket with time-based refill."
    elif task_id == BUGGY_TASK_ID:
        notes = "Fixed: the refill is now capped at capacity, so an idle bucket cannot overfill."
    else:
        notes = "Wrote " + ", ".join(files) + "."
    return {"ops": ops, "notes": notes, "blocked": None}


def second_key_patches() -> dict:
    """The second key finds nothing to change: an empty patch list."""
    return {"patches": [], "notes": "Tasks are small, write sets are disjoint, every task has a machine check."}


def review_ballot_for(seat_no: int, cycle: int) -> dict:
    """ReviewBallot. Seat 3 asks for a small fix in cycle 1; every other ballot accepts (4 of 5)."""
    if seat_no == 3 and cycle <= 1:
        return {
            "verdict": "fix",
            "fixes": [{
                "problem": "The README does not say the limiters are not thread safe.",
                "task_id": "t08_readme",
                "proposed_change": "Add one line: wrap allow() in a lock when sharing a limiter across threads.",
            }],
            "reason": "The work is correct; the README misses one caveat.",
        }
    reasons = [
        "All eight tasks passed and the full unittest run is green.",
        "The token bucket bug was caught by its check and fixed on the second attempt.",
        "Interfaces match the plan and the tests use the injected clock, so nothing sleeps.",
        "Deliverables are all present: package, tests and README.",
        "The integration check passes and there are no deviations from the plan.",
    ]
    return {"verdict": "accept", "fixes": [], "reason": reasons[seat_no % len(reasons)]}


_MEMORY: list[dict[str, Any]] = [
    {
        "durable": True, "kind": "lesson", "scope": "category:code", "action": "provisional",
        "statement_rewrite": "When a value refills over time, cap it at its maximum and test the idle case.",
        "reason": "The uncapped refill bug cost a retry and the idle-case check caught it.",
    },
    {
        "durable": True, "kind": "precedent", "scope": "global", "action": "provisional",
        "statement_rewrite": "Inject a clock into time-based code so tests never sleep.",
        "reason": "Every test in this run was fast and deterministic because of it.",
    },
    {
        "durable": False, "kind": "project_fact", "scope": "global", "action": "reject",
        "statement_rewrite": "",
        "reason": "This only describes one run; it is not worth keeping.",
    },
]


def memory_verdict_for(candidate_index: int, judge_index: int) -> dict:
    """MemoryVerdict. Candidates cycle through keep, keep, reject. One judge in five dissents."""
    v = dict(_MEMORY[candidate_index % len(_MEMORY)])
    if judge_index % 5 == 4 and v["durable"]:
        v.update(durable=False, action="reject", statement_rewrite="",
                 reason="One run is thin evidence for a general rule.")
    return v


_QUESTIONS = [
    ("A token bucket lets a client spend a full bucket at once. Why is that burst acceptable here?", "c1"),
    ("The sliding window stores one timestamp per request. What bounds its memory?", "c2"),
    ("What test would show your position is wrong?", None),
]
_ANSWERS = [
    ("The burst is bounded by capacity, which the operator sets. The tests pin that bound.",
     "tests/test_token_bucket.py: test_refill_is_capped_at_capacity"),
    ("Only allowed requests are stored, so the deque never holds more than `limit` entries.",
     "ratelimiter/sliding_window.py: allow() appends only when under the limit"),
    ("A run where an idle bucket allows more than capacity. The first attempt did exactly that.", ""),
]
_CONCESSIONS = [
    "I concede. The cap at capacity is what bounds the burst; I argued as if it were missing.",
    "I concede. Memory is bounded by `limit`; my objection assumed refused requests were stored.",
    "I concede. The council's position is the one the tests support.",
]
_VERDICTS = [
    (False, 0.25, "The outlier assumed the bucket could overfill; the capped refill shows it cannot.",
     "factual", "Check the refill cap before arguing about burst size."),
    (False, 0.3, "The claim about unbounded memory ignored that refused requests are never stored.",
     "ignored_evidence", "Read the allow() path before claiming a data structure grows without bound."),
    (True, 0.7, "Preferring a sliding window for fairness is a fair design preference.",
     "preference", "State a preference as a preference, not as a defect in the other design."),
]


def tribunal_reply(purpose: str, index: int, concede: bool = False) -> dict:
    """Reply for tribunal.question (TribunalQuestion), tribunal.answer (TribunalAnswer) or
    tribunal.verdict (DefenseVerdict). `concede` makes the answer concede and the verdict not hold."""
    kind = (purpose or "").rsplit(".", 1)[-1]
    if kind == "question":
        q, claim = _QUESTIONS[index % len(_QUESTIONS)]
        return {"question": q, "targets_claim": claim}
    if kind == "answer":
        if concede:
            return {"answer": _CONCESSIONS[index % len(_CONCESSIONS)], "concedes": True, "new_evidence": ""}
        a, ev = _ANSWERS[index % len(_ANSWERS)]
        return {"answer": a, "concedes": False, "new_evidence": ev}
    if kind == "verdict":
        held, score, point, err, lesson = _VERDICTS[index % len(_VERDICTS)]
        if concede and held:
            held, score, point, err, lesson = _VERDICTS[0]
        return {"held": held, "score": score, "decisive_point": point, "error_kind": err, "lesson": lesson}
    raise ValueError(f"unknown tribunal purpose: {purpose!r}")
