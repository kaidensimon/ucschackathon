"""Scripted full run for phase 1: one coherent plan-mode run, no models needed.

demo_events(task, run_id, models=None, seed=0) -> list[(delay_s, event_type, payload)]

- `delay_s` is the pause before emitting that event.
- Every payload is built with event_types.make_payload, so it is valid and JSON-ready.
- One tuple has type WAIT_DELEGATE ("__wait_delegate__") and an empty payload. The player
  stops there until the user delegates, then plays the rest.
- Every type in EVENT_TYPES appears at least once, except run.failed and run.cancelled.
- The dissenting seat is cross-examined (27) after the decision and its correction is
  recorded; a small bench plays during reflection. probe.* (28) is shown
  as advisory scores after round 0 and one probe trained at the end.
- telemetry.tick is derived from the other events (resident models, calls in flight, tokens),
  one per second, so the numbers follow the story.

The story is fixed: designing an API rate limiter. Same arguments -> same output.
"""

from __future__ import annotations

import random
from typing import Any, Optional

from council.core import event_types as ET
from council.core.schemas import (
    BenchResult,
    BenchRunRequest,
    BenchSummaryRow,
    ClaimScore,
    Correction,
    DefenseVerdict,
    Probe,
    TrainingExample,
    TribunalAnswer,
    TribunalOutcome,
    TribunalQuestion,
    AttemptRecord,
    Ballot,
    Check,
    CheckResult,
    ChronicleEntry,
    Claim,
    Critique,
    Crux,
    CruxVote,
    Decision,
    Deliverable,
    Departure,
    DiffStats,
    Draft,
    EvidenceRef,
    EvidenceResult,
    Flaw,
    InterfaceDef,
    LineupRecord,
    LineupScore,
    MemoryCandidate,
    MemoryVerdict,
    MicroTask,
    MinorityPosition,
    ModelEntry,
    Option,
    Plan,
    RejectedLineup,
    ResidentModel,
    Review,
    ReviewBallot,
    ReviewFix,
    RunCounters,
    RunState,
    SeatAssignment,
    TaskBudget,
    TaskContext,
    TaskProfile,
    TaskStatus,
    WorkerOp,
    WorkerOutput,
    WorkReport,
    WorkReportTask,
    WorkSummary,
    CheckRequest,
)

from council.core.schemas_v15 import LieFlag, LieReport, MemoryPlan, SeatHonesty

WAIT_DELEGATE = "__wait_delegate__"

_EPOCH = 1791590400.0  # 2026-10-10 00:00:00 UTC; fixed so the script is deterministic
_MEM_TOTAL_GIB = 121.7
_MEM_SYSTEM_GIB = 6.4
_K = 5

BUILTIN_MODELS: tuple[ModelEntry, ...] = (
    ModelEntry(id="gpt-oss-20b", display="gpt-oss 20B", lab="OpenAI", lineage="gpt-oss", arch="moe",
               params_b=21.0, active_params_b=3.6, quant="Q4_K_M", roles=["seat", "chair"],
               priors={"code": 0.78, "planning": 0.80, "logic": 0.79}),
    ModelEntry(id="qwen3.8-27b", display="Qwen3.8 27B", lab="Alibaba", lineage="qwen3", arch="dense",
               params_b=27.0, quant="Q4_K_M", roles=["seat", "chair", "senior_worker"],
               priors={"code": 0.84, "planning": 0.77, "logic": 0.76}),
    ModelEntry(id="gemma-4-26b-a4b", display="Gemma 4 26B-A4B", lab="Google", lineage="gemma4", arch="moe",
               params_b=26.0, active_params_b=4.0, quant="Q4_K_M", roles=["seat"],
               priors={"code": 0.72, "planning": 0.76, "logic": 0.74}),
    ModelEntry(id="nemotron-3-nano-30b", display="Nemotron 3 Nano 30B-A3B", lab="NVIDIA", lineage="nemotron3",
               arch="moe", params_b=30.0, active_params_b=3.0, quant="Q4_K_M", roles=["seat"],
               priors={"code": 0.74, "planning": 0.71, "logic": 0.75}),
    ModelEntry(id="phi-4-14b", display="Phi-4 14B", lab="Microsoft", lineage="phi4", arch="dense",
               params_b=14.0, quant="Q4_K_M", roles=["seat"],
               priors={"code": 0.66, "planning": 0.64, "logic": 0.70}),
    ModelEntry(id="ministral-3-3b", display="Ministral 3 3B", lab="Mistral", lineage="ministral3", arch="dense",
               params_b=3.0, quant="Q4_K_M", roles=["worker", "clerk"],
               priors={"code": 0.48, "planning": 0.40, "logic": 0.45}),
)

_PROFILE_WEIGHTS = {"code": 0.5, "planning": 0.3, "logic": 0.2}
_LENSES = ("specialist", "builder", "skeptic", "first_principles", "risk")

# ------------------------------------------------------------------------------------------
# Story text
# ------------------------------------------------------------------------------------------

_O1, _O2 = "o1", "o2"

_DRAFTS: tuple[dict[str, Any], ...] = (
    dict(
        option=_O1, confidence=0.82,
        reasoning="Need: per-key cap, bursts bounded, many app nodes. State must be shared, so Redis. "
                  "Update must be atomic or two nodes double-spend a token.",
        answer="Use a token bucket per API key, stored in Redis and updated by one atomic Lua script. "
               "Capacity bounds the burst and the refill rate sets the steady limit. Keep an in-process "
               "bucket as a fallback so a Redis outage degrades the limiter instead of the API. Return "
               "X-RateLimit headers and Retry-After on every 429.",
        summary="Token bucket per API key in Redis, atomic Lua refill-and-take, in-process fallback, standard headers.",
        claims=[("c1", "A token bucket bounds bursts by capacity.", "definition of the algorithm"),
                ("c2", "Refill and take must be one atomic step.", "two nodes can read the same count")],
        risks=["Lua script bugs are hard to see in production."],
        change="Evidence that Redis is not available to this service.",
    ),
    dict(
        option=_O1, confidence=0.78,
        reasoning="Smallest thing that ships: one script, one config file, one middleware. "
                  "Check whether Redis is already in the stack before leaning on it.",
        answer="Ship the smallest thing that works: a token bucket, with one Lua script doing refill and "
               "take in a single round trip. Limits live in a TOML file keyed by route and plan. The "
               "middleware calls take(key) before the handler runs. Redis is already in this service, "
               "so there is no new infrastructure to run.",
        summary="Token bucket, single Lua round trip, limits in limits.toml, thin middleware. No new infrastructure.",
        claims=[("c1", "Redis is already a dependency of this service.", "seen in the workspace brief"),
                ("c2", "One round trip per request keeps overhead under a millisecond.", "single EVALSHA")],
        risks=["Config drift between limits.toml and what product promised."],
        change="A measured p99 above 2 ms for the script.",
    ),
    dict(
        option=_O1, confidence=0.74,
        reasoning="Assume the obvious fixed window is wrong. Where does it leak? At the boundary: "
                  "limit at 0:59 plus limit at 1:00. Clock skew between nodes is the second leak.",
        answer="The obvious fixed window is wrong: a client can spend the full limit at the end of one "
               "window and again at the start of the next. A token bucket that reads time from Redis "
               "TIME avoids clock skew between app nodes. Make it atomic in Lua, give each key a TTL "
               "so idle keys expire, and write down what happens when Redis is down.",
        summary="Fixed windows leak 2x at the boundary. Token bucket with Redis TIME, atomic Lua, TTL on idle keys.",
        claims=[("c1", "A fixed window admits up to twice the limit across a boundary.", "two adjacent full windows"),
                ("c2", "Using Redis TIME removes clock skew between nodes.", "one clock for all callers")],
        risks=["Outage behaviour is undefined unless we choose it."],
        change="A proof that the weighted sliding window has no boundary burst.",
    ),
    dict(
        option=_O2, confidence=0.70,
        reasoning="Requirement, not convention: a fair cap per client over time. What is the least state "
                  "that gives it? Two integers per key.",
        answer="The requirement is a fair cap per client over time. A sliding-window counter needs two "
               "integers per key and plain INCR with EXPIRE, with no scripting at all. Weight the "
               "previous window by its overlap to smooth the boundary. It is simpler to reason about "
               "and to operate than a Lua script.",
        summary="Sliding-window counter: two integers per key, INCR and EXPIRE, previous window weighted by overlap.",
        claims=[("c1", "A weighted sliding window needs no server-side script.", "INCR and EXPIRE only"),
                ("c2", "The weighted estimate is close enough to exact.", "assumes even traffic in the last window")],
        risks=["The estimate is wrong when traffic in the previous window was bursty."],
        change="A concrete burst the weighted window lets through.",
    ),
    dict(
        option=_O2, confidence=0.66,
        reasoning="What breaks, what is irreversible? A slow script blocks Redis for every caller. "
                  "And an open limiter during an outage is an abuse window.",
        answer="Lua scripts in Redis are an operational risk: a slow script blocks the server for every "
               "caller and is hard to debug. Prefer a sliding-window counter with INCR and EXPIRE at "
               "the gateway. If the counter store is unreachable, fail closed so abuse cannot slip "
               "through while we are blind.",
        summary="Avoid Lua. Sliding-window counter with INCR and EXPIRE. Fail closed when the store is down.",
        claims=[("c1", "A long Lua script blocks Redis for all clients.", "Redis runs scripts on one thread"),
                ("c2", "Failing closed is safer than failing open.", "abuse is worse than refusals")],
        risks=["Failing closed turns a Redis outage into an API outage."],
        change="A script short enough that blocking is not a concern, with tests.",
    ),
)

_OPTION_SUMMARY = {
    _O1: "Token bucket per API key in Redis, refill-and-take in one atomic Lua script, in-process fallback.",
    _O2: "Sliding-window counter with INCR and EXPIRE, previous window weighted by overlap, no Lua.",
}

_CRITIQUE_TEXT = (
    "Strongest point of the counter proposal: no script to operate. Flaw: the weighted window still "
    "lets a burst through when the last window was uneven. I keep my position.",
    "The counter draft is honest about simplicity. But Redis is already here, so the script costs us "
    "nothing new. Requesting a grep to confirm. I keep my position.",
    "Both counter drafts assume even traffic in the previous window. That is the case a limiter exists "
    "for. Burst at the boundary stays near twice the limit. I keep my position.",
    "The bucket drafts bound the burst exactly, and mine only estimates it. Flaw f1 is correct: my "
    "claim c2 fails for bursty clients. I adopt the token bucket.",
    "The bucket is exact, I grant that. My objection stands: a script on the Redis thread is a shared "
    "risk, and nobody has shown its length. I keep my position.",
)

_BALLOT_TEXT = (
    "Token bucket in Redis with one atomic Lua script, Redis TIME as the clock, in-process fallback.",
    "Token bucket. The grep shows redis is already pinned in requirements, so nothing new to run.",
    "Token bucket. It is the only option on the table that bounds the boundary burst exactly.",
    "Token bucket. I changed because of flaw f1 and the evidence that Redis is already a dependency.",
    "Sliding-window counter. I still rank operational simplicity above exact burst control.",
)

_CHAIR_TEXT = (
    "Decision: a token bucket per API key, held in Redis and updated by one atomic Lua script that "
    "refills and takes in a single round trip, using Redis TIME as the only clock. Limits live in "
    "limits.toml, keyed by route and plan. The middleware calls take(key, cost) before the handler and "
    "sets X-RateLimit-Limit, X-RateLimit-Remaining and Retry-After. If Redis is unreachable the limiter "
    "falls back to an in-process bucket and fails open with an alert, as the user chose. Dissent kept: "
    "a sliding-window counter avoids Lua entirely. We bound that risk by keeping the script under 20 "
    "lines and covering it with tests. This departs from the fixed-window precedent because a fixed "
    "window admits a double burst at the boundary."
)

_PROJECT = "9f2c1a"
_OUTLIER = 4  # the seat still on the minority option after the ballots
_STEERED = 3  # the seat that loads with a steering vector from an earlier run
_EXAMINERS = (0, 2)
_TRIBUNAL_QA: tuple[dict[str, Any], ...] = (
    dict(claim="c1",
         q="You say a Lua script can stall Redis. The proposed script is under 20 lines and does a fixed "
           "number of commands. What run time do you claim it exceeds?",
         a="I have no measurement. A fixed number of commands cannot stall the server; my risk was about "
           "scripts in general, not this one.",
         concedes=False),
    dict(claim="c2",
         q="Flaw f1 shows a weighted window lets a bursty client take close to twice the limit. Does your "
           "option meet the requirement of a bounded burst?",
         a="No. It estimates the burst and the estimate is wrong for bursty clients. I gave that less weight "
           "than operational taste. I concede the token bucket meets the requirement and mine does not.",
         concedes=True),
)
_TRIBUNAL_LESSON = ("When a flaw shows your option misses a stated requirement, answer that flaw before "
                    "arguing from operational preference.")
_VERDICT_POINTS = (
    "The member could not name a run time the script exceeds.",
    "The member agreed the weighted window does not bound the burst.",
    "Flaw f1 was on the table in round 1 and was not answered until now.",
    "The defence rested on a general risk, not on this script.",
)

_REVIEW_TEXT = (
    ("accept", "Core limiter, both stores and the middleware pass. The failed benchmark is a sandbox timing issue."),
    ("accept", "Six of eight passed and the unit tests are green on the staged copy. Ship it."),
    ("accept", "Integration checks pass. The bench threshold was unrealistic for the sandbox, not a code fault."),
    ("accept", "Interfaces match the plan. Missing docs are worth a follow-up, not a block."),
    ("fix", "T7 failed and T8 was skipped, so the latency claim is unproven and undocumented."),
)

# id, title, kind, tier, deps, write_set, goal, checks, streamed worker text
_TASKS: tuple[dict[str, Any], ...] = (
    dict(id="T1", title="Token bucket core", kind="create_file", tier="micro", deps=[],
         write=["limiter/bucket.py"], ifaces=["Decision"],
         goal="Write the pure token bucket maths: refill by elapsed time, then take `cost` tokens.",
         checks=[dict(type="parses", path="limiter/bucket.py", language="python"),
                 dict(type="contains", path="limiter/bucket.py", pattern="def refill")],
         text='{"ops":[{"op":"write_file","path":"limiter/bucket.py","content":"def refill(tokens, capacity, '
              'refill_per_s, elapsed):\\n    return min(capacity, tokens + elapsed * refill_per_s)\\n\\ndef take('
              'tokens, cost):\\n    return (tokens >= cost, max(tokens - cost, 0))\\n"}],"notes":"pure functions"}'),
    dict(id="T2", title="Limits config loader", kind="create_file", tier="micro", deps=[],
         write=["limiter/config.py", "limits.toml"], ifaces=["limits.toml"],
         goal="Load limits.toml into a dict of route and plan to (capacity, refill_per_s).",
         checks=[dict(type="parses", path="limiter/config.py", language="python"),
                 dict(type="exists", path="limits.toml")],
         text='{"ops":[{"op":"write_file","path":"limits.toml","content":"[default.free]\\ncapacity = 60\\n'
              'refill_per_s = 1.0\\n"},{"op":"write_file","path":"limiter/config.py","content":"import tomllib\\n\\n'
              'def load_limits(path):\\n    with open(path, \'rb\') as f:\\n        return tomllib.load(f)\\n"}]}'),
    dict(id="T3", title="Redis store with Lua script", kind="create_file", tier="micro", deps=["T1"],
         write=["limiter/store_redis.py", "limiter/take.lua"], ifaces=["Store"],
         goal="Implement Store on Redis. One Lua script refills and takes atomically, using Redis TIME.",
         checks=[dict(type="parses", path="limiter/store_redis.py", language="python"),
                 dict(type="contains", path="limiter/take.lua", pattern="redis.call\\('TIME'\\)")],
         text='{"ops":[{"op":"write_file","path":"limiter/take.lua","content":"local t = redis.call(\'TIME\')\\n'
              'local now = t[1] + t[2] / 1e6\\nlocal b = redis.call(\'HMGET\', KEYS[1], \'tokens\', \'ts\')\\n'
              '-- refill, take, HSET, PEXPIRE\\n"},{"op":"write_file","path":"limiter/store_redis.py",'
              '"content":"class RedisStore:\\n    def take(self, key, capacity, refill_per_s, cost, now): ...\\n"}]}'),
    dict(id="T4", title="In-memory fallback store", kind="create_file", tier="micro", deps=["T1"],
         write=["limiter/store_memory.py"], ifaces=["Store"],
         goal="Implement Store in process memory with a lock, for use when Redis is unreachable.",
         checks=[dict(type="parses", path="limiter/store_memory.py", language="python"),
                 dict(type="contains", path="limiter/store_memory.py", pattern="class MemoryStore")],
         text='{"ops":[{"op":"write_file","path":"limiter/store_memory.py","content":"import threading\\n\\n'
              'class MemoryStore:\\n    def __init__(self):\\n        self._lock = threading.Lock()\\n'
              '        self._buckets = {}\\n    def take(self, key, capacity, refill_per_s, cost, now): ...\\n"}]}'),
    dict(id="T5", title="Rate limit middleware", kind="create_file", tier="micro", deps=["T2", "T3", "T4"],
         write=["limiter/middleware.py"], ifaces=["RateLimiter.take", "Store", "Decision"],
         goal="Call take(key, cost) before the handler. On Redis errors use MemoryStore and fail open with an alert.",
         checks=[dict(type="parses", path="limiter/middleware.py", language="python"),
                 dict(type="command", cmd="python -m unittest tests.contract_middleware", timeout_s=30.0)],
         text='{"ops":[{"op":"write_file","path":"limiter/middleware.py","content":"class RateLimiter:\\n'
              '    def take(self, key, cost=1):\\n        try:\\n            ok, left, wait = self.redis.take(...)\\n'
              '        except ConnectionError:\\n            self.alert(\'limiter fail-open\')\\n'
              '            ok, left, wait = self.memory.take(...)\\n        return Decision(ok, left, wait)\\n"}]}'),
    dict(id="T6", title="Limiter unit tests", kind="write_test", tier="micro", deps=["T4", "T5"],
         write=["tests/test_limiter.py"], ifaces=["RateLimiter.take", "Decision"],
         goal="Test burst up to capacity, refusal after it, refill over time and the fail-open path.",
         checks=[dict(type="parses", path="tests/test_limiter.py", language="python"),
                 dict(type="command", cmd="python -m unittest tests.test_limiter", timeout_s=60.0)],
         text='{"ops":[{"op":"write_file","path":"tests/test_limiter.py","content":"import unittest\\n\\n'
              'class FakeClock:\\n    now = 0.0\\n\\nclass BurstTest(unittest.TestCase):\\n'
              '    def test_burst_then_refuse(self):\\n        ...\\n    def test_fail_open(self):\\n        ...\\n"}]}'),
    dict(id="T7", title="Burst benchmark script", kind="create_file", tier="senior", deps=["T5"],
         write=["bench/burst.py"], ifaces=["RateLimiter.take"],
         goal="Fire 10k take() calls and assert the p99 overhead stays under one millisecond.",
         checks=[dict(type="parses", path="bench/burst.py", language="python"),
                 dict(type="command", cmd="python bench/burst.py --assert-p99-ms 1.0", timeout_s=60.0)],
         text='{"ops":[{"op":"write_file","path":"bench/burst.py","content":"import time\\n\\ndef run(n=10000):\\n'
              '    samples = []\\n    for _ in range(n):\\n        t = time.perf_counter()\\n'
              '        limiter.take(\'bench\')\\n        samples.append(time.perf_counter() - t)\\n'
              '    return sorted(samples)[int(n * 0.99)]\\n"}]}'),
    dict(id="T8", title="Rate limiting docs", kind="write_doc", tier="micro", deps=["T7"],
         write=["docs/rate_limiting.md"], ifaces=["limits.toml"],
         goal="Document the limits file, the headers, the outage behaviour and the measured overhead.",
         checks=[dict(type="exists", path="docs/rate_limiting.md"),
                 dict(type="contains", path="docs/rate_limiting.md", pattern="Retry-After")],
         text=""),
)

_INTERFACES = (
    InterfaceDef(name="Decision", kind="type",
                 definition="Decision(allowed: bool, remaining: int, retry_after_s: float)"),
    InterfaceDef(name="Store", kind="type",
                 definition="class Store(Protocol):\n    def take(self, key: str, capacity: int, refill_per_s: float, "
                            "cost: int, now: float) -> tuple[bool, int, float]"),
    InterfaceDef(name="RateLimiter.take", kind="function",
                 definition="def take(self, key: str, cost: int = 1) -> Decision"),
    InterfaceDef(name="limits.toml", kind="file_format",
                 definition="[<route>.<plan>]\ncapacity = <int>\nrefill_per_s = <float>"),
)


def _chunks(text: str, n_words: int) -> list[str]:
    words = text.split(" ")
    out = []
    for i in range(0, len(words), n_words):
        piece = " ".join(words[i:i + n_words])
        out.append(piece if i + n_words >= len(words) else piece + " ")
    return [c for c in out if c]


def _tokens(text: str) -> int:
    return max(1, int(len(text) / 3.8))


def _footprint(m: ModelEntry) -> float:
    if m.measured.ram_gb_live:
        return round(float(m.measured.ram_gb_live), 1)
    if m.params_b:
        return round(min(72.0, m.params_b * 0.6 + 2.2), 1)
    return 12.0


class _Script:
    def __init__(self, task: str, run_id: str, models: Optional[list[ModelEntry]], seed: int) -> None:
        self.task = task
        self.run_id = run_id
        self.rng = random.Random(seed)
        self.seed = seed
        self.out: list[tuple[float, str, dict]] = []
        self.seg: list[tuple[float, int, str, dict]] = []
        self.n = 0
        self.state: Optional[RunState] = None
        self.state_t = 0.0
        self.phase_ms: dict[str, float] = {}
        self.round = 0
        # telemetry state, carried across both segments
        self.clock = 0.0
        self.resident: dict[str, float] = {}
        self.in_flight: dict[str, str] = {}
        self.started_at: dict[str, float] = {}
        self.tok_in = 0
        self.tok_out = 0
        self.tok_reason = 0
        self.tok_out_seen = 0
        self.calls = 0
        self.calls_failed = 0
        self._cast(models)

    # -- cast -----------------------------------------------------------------------------

    def _cast(self, models: Optional[list[ModelEntry]]) -> None:
        pool: list[ModelEntry] = []
        seen: set[str] = set()
        for m in list(models or []):
            if not isinstance(m, ModelEntry):
                m = ModelEntry.model_validate(m)
            if m.id not in seen and m.status != "disabled":
                pool.append(m)
                seen.add(m.id)

        def lab(m: ModelEntry) -> str:
            return m.lab or m.id

        def seat_ok(m: ModelEntry) -> bool:
            return not m.roles or "seat" in m.roles or "chair" in m.roles

        def add_builtins(want) -> None:
            for b in BUILTIN_MODELS:
                if want():
                    return
                if b.id not in seen:
                    pool.append(b)
                    seen.add(b.id)

        add_builtins(lambda: len({lab(m) for m in pool if seat_ok(m)}) >= _K)
        if len({lab(m) for m in pool if seat_ok(m)}) < _K:  # labs collide with the built-ins: relax roles
            seat_ok = lambda m: True  # noqa: E731

        self.q: dict[str, float] = {}

        def score_new() -> None:
            for m in pool:
                if m.id in self.q:
                    continue
                if m.priors:
                    q = sum(w * float(m.priors.get(c, 0.6)) for c, w in _PROFILE_WEIGHTS.items())
                else:
                    q = self.rng.uniform(0.58, 0.84)
                self.q[m.id] = round(min(0.97, max(0.05, q)), 3)

        score_new()

        best: dict[str, ModelEntry] = {}
        for m in pool:
            if seat_ok(m) and (lab(m) not in best or self.q[m.id] > self.q[best[lab(m)].id]):
                best[lab(m)] = m
        ranked = sorted(best.values(), key=lambda m: (-self.q[m.id], m.id))
        core, rest = ranked[:_K - 1], ranked[_K - 1:]
        wild = self.rng.choice(rest)
        lineup = core + [wild]

        used = {m.id for m in lineup}
        add_builtins(lambda: any(m.id not in used for m in pool))
        score_new()
        spare = [m for m in pool if m.id not in used]
        workers = [m for m in spare if "worker" in m.roles] or spare
        self.worker = min(workers, key=lambda m: (m.params_b or 1e9, m.id))
        self.pool = pool
        self.alternates = [m for m in ranked if m.id not in used]
        self.seats: list[dict[str, Any]] = []
        for i, m in enumerate(lineup):
            self.seats.append(dict(
                seat_no=i, m=m, q=self.q[m.id], lens=_LENSES[i], wild=(i == _K - 1), chair=(i == 0),
                label="ABCDE"[i], tps=round(m.measured.tps_1 or self.rng.uniform(31.0, 58.0), 1),
            ))
        self.chair = self.seats[0]
        self.senior = self.chair["m"]
        self.tps = {s["m"].id: s["tps"] for s in self.seats}
        self.tps[self.worker.id] = round(self.worker.measured.tps_1 or self.rng.uniform(70.0, 95.0), 1)
        self.fp = {m.id: _footprint(m) for m in pool}
        self.resident[self.worker.id] = self.fp[self.worker.id]  # idle, left over from the last run

    def info(self, m: ModelEntry, resident: bool = False) -> dict:
        return dict(model_id=m.id, display=m.display or m.id, lab=m.lab, lineage=m.lineage,
                    params_b=m.params_b, quant=m.quant, footprint_gib=self.fp[m.id], resident=resident)

    def mev(self, m: ModelEntry, profile: str = "live") -> dict:
        return dict(model_id=m.id, display=m.display or m.id, lab=m.lab, footprint_gib=self.fp[m.id],
                    serve_profile=profile)

    # -- timeline -------------------------------------------------------------------------

    def e(self, t: float, type: str, **fields: Any) -> None:
        self.seg.append((round(t, 3), self.n, type, ET.make_payload(type, **fields)))
        self.n += 1

    def to(self, t: float, state: RunState, reason: str, review_cycle: int = 0) -> None:
        phase = None
        if self.state is not None:
            phase = round((t - self.state_t) * 1000.0, 1)
            self.phase_ms[self.state.value] = round(self.phase_ms.get(self.state.value, 0.0) + phase, 1)
        self.e(t, ET.RUN_STATE_CHANGED, from_state=self.state, to_state=state, reason=reason,
               round=self.round, review_cycle=review_cycle, phase_ms=phase)
        self.state, self.state_t = state, t

    def stream(self, t0: float, dur: float, type: str, text: str, n_words: int = 5, **ids: Any) -> None:
        parts = _chunks(text, n_words)
        for i, part in enumerate(parts):
            self.e(t0 + dur * (i + 1) / (len(parts) + 1), type, text=part, **ids)

    def turn(self, t0: float, dur: float, call_id: str, purpose: str, model_id: str, seat_no: Optional[int],
             text: str, parsed: Optional[dict] = None, reasoning_text: str = "", tokens_in: int = 900,
             attempt: int = 1, attempts: int = 1, start: bool = True, max_out: int = 500,
             delta: str = ET.TURN_DELTA) -> float:
        """One model call: started, optional reasoning stream, text stream, completed. Returns end time."""
        if start:
            self.e(t0, ET.TURN_STARTED, call_id=call_id, purpose=purpose, model_id=model_id, seat_no=seat_no,
                   round=self.round, reasoning="council" if reasoning_text else "off",
                   max_output_tokens=max_out, attempt=attempt)
        t_text = t0
        if reasoning_text:
            t_text = t0 + dur * 0.25
            self.stream(t0, dur * 0.25, ET.TURN_REASONING_DELTA, reasoning_text, 6,
                        call_id=call_id, seat_no=seat_no)
        if text:
            self.stream(t_text, t0 + dur - t_text, delta, text, 5, call_id=call_id, seat_no=seat_no)
        out = _tokens(text) + (_tokens(str(parsed)) // 3 if parsed else 0)
        self.e(t0 + dur, ET.TURN_COMPLETED, call_id=call_id, seat_no=seat_no, round=self.round, purpose=purpose,
               model_id=model_id, tokens=out, tokens_in=tokens_in, tokens_out=out,
               tokens_reasoning=_tokens(reasoning_text) if reasoning_text else 0,
               tps=round(out / max(dur, 0.1), 1), ms=round(dur * 1000.0, 1), parsed=parsed, content=text,
               finish_reason="stop", attempts=attempts)
        return t0 + dur

    # -- telemetry ------------------------------------------------------------------------

    def _observe(self, t: float, type: str, p: dict) -> None:
        if type == ET.MODEL_LOADED:
            self.resident[p["model_id"]] = p["footprint_gib"]
        elif type in (ET.MODEL_UNLOADED, ET.MODEL_EVICTED, ET.MODEL_FAILED):
            self.resident.pop(p["model_id"], None)
        elif type == ET.TURN_STARTED:
            self.in_flight[p["call_id"]] = p["model_id"]
            self.started_at[p["call_id"]] = t
            self.calls += 1
        elif type == ET.TASK_STARTED:
            key = f'{p["task_id"]}#{p["attempt"]}'
            self.in_flight[key] = p["model_id"] or ""
            self.started_at[key] = t
            self.calls += 1
        elif type == ET.TURN_COMPLETED:
            self.in_flight.pop(p["call_id"], None)
            self.tok_in += p["tokens_in"]
            self.tok_out += p["tokens_out"]
            self.tok_reason += p["tokens_reasoning"]
        elif type == ET.TURN_TIMEOUT:
            self.in_flight.pop(p["call_id"], None)
            self.calls_failed += 1
        elif type == ET.TURN_INVALID:
            self.calls_failed += 1
        elif type == ET.TASK_ATTEMPT_COMPLETED:
            self.in_flight.pop(f'{p["task_id"]}#{p["attempt"]}', None)
            self.tok_in += p["tokens_in"]
            self.tok_out += p["tokens_out"]
            if not p["ok"]:
                self.calls_failed += 1

    def _tick(self, t: float) -> dict:
        counts: dict[str, int] = {}
        live_out = 0.0
        for key, model_id in self.in_flight.items():
            counts[model_id] = counts.get(model_id, 0) + 1
            live_out += self.tps.get(model_id, 40.0) * 0.6 * max(0.0, t - self.started_at.get(key, t))
        tps_by = {m: round(self.tps.get(m, 40.0) * (n ** 0.85) * self.rng.uniform(0.9, 1.06), 1)
                  for m, n in sorted(counts.items())}
        self.tok_out_seen = max(self.tok_out_seen, self.tok_out + int(live_out))
        used = _MEM_SYSTEM_GIB + sum(self.resident.values()) + self.rng.uniform(-0.05, 0.05)
        busy = bool(counts)
        util = self.rng.uniform(0.86, 0.98) if busy else self.rng.uniform(0.02, 0.07)
        return ET.make_payload(
            ET.TELEMETRY_TICK,
            ts=round(_EPOCH + self.clock + t, 3),
            mem_total_gib=_MEM_TOTAL_GIB,
            mem_used_gib=round(used, 2),
            mem_available_gib=round(_MEM_TOTAL_GIB - used, 2),
            swap_used_gib=0.0,
            resident=[ResidentModel(model_id=m, footprint_gib=f) for m, f in sorted(self.resident.items())],
            tps_by_model=tps_by,
            tps_total=round(sum(tps_by.values()), 1),
            in_flight=dict(sorted(counts.items())),
            queue_depth=max(0, len(self.in_flight) - 4),
            tokens_in=self.tok_in,
            tokens_out=self.tok_out_seen,
            tokens_reasoning=self.tok_reason,
            gpu_util=round(util, 3),
            gpu_temp_c=round(self.rng.uniform(66.0, 74.0) if busy else self.rng.uniform(47.0, 52.0), 1),
            gpu_power_w=round(self.rng.uniform(118.0, 139.0) if busy else self.rng.uniform(24.0, 31.0), 1),
            cpu_util=round(self.rng.uniform(0.12, 0.31) if busy else self.rng.uniform(0.02, 0.06), 3),
            cloud_equiv_usd=round((self.tok_in * 3.0 + self.tok_out_seen * 15.0) / 1e6, 5),
        )

    def flush(self) -> None:
        """Sort the segment, weave in one telemetry.tick per second, convert to delays."""
        self.seg.sort(key=lambda x: (x[0], x[1]))
        prev = 0.0
        next_tick = 1.0
        for t, _, type, payload in self.seg:
            while next_tick <= t:
                self.out.append((round(next_tick - prev, 3), ET.TELEMETRY_TICK, self._tick(next_tick)))
                prev = next_tick
                next_tick += 1.0
            self._observe(t, type, payload)
            self.out.append((round(t - prev, 3), type, payload))
            prev = t
        self.clock += prev + 5.0
        self.seg = []

    # -- story: before delegation ---------------------------------------------------------

    def memory_plan(self) -> MemoryPlan:
        """What fits in memory: every seat at its context size, and which model plays each side role."""
        used = [s["m"] for s in self.seats]
        per_model = {m.id: self.fp[m.id] for m in used}
        per_model[self.worker.id] = self.fp[self.worker.id]
        total = round(sum(per_model.values()), 1)
        chair = self.chair["m"].id
        return MemoryPlan(
            fits=True, budget_gib=round(_MEM_TOTAL_GIB - _MEM_SYSTEM_GIB, 1), total_gib=total, per_model=per_model,
            num_ctx={mid: (16384 if mid == self.worker.id else 32768) for mid in per_model},
            roles={"planner": chair, "worker": self.worker.id, "senior_worker": chair, "clerk": self.worker.id},
            shared_roles=["planner", "senior_worker"], dropped=[],
            notes=["Planner and senior worker share the chair's model: no extra weights to load.",
                   "The worker model is loaded after the seats, when the work phase starts."])

    def lie_report(self) -> LieReport:
        """Behaviour-only honesty scores for the round 0 claims (no probe is active yet)."""
        flags: list[LieFlag] = []
        seat_rows: list[SeatHonesty] = []
        for s, d in zip(self.seats, _DRAFTS):
            n = s["seat_no"]
            levels = []
            for i, c in enumerate(d["claims"]):
                beh = round(min(0.95, d["confidence"] - 0.06 - 0.09 * i), 2)
                gap = round(d["confidence"] - beh, 2)
                level = "flag" if (n == _OUTLIER and i == 1) else ("watch" if gap > 0.12 else "ok")
                levels.append(level)
                flags.append(LieFlag(
                    run_id=self.run_id, seat_no=n, model_id=s["m"].id, claim_id=c[0], text=c[1], probe_score=None,
                    behaviour_score=beh, stated_confidence=d["confidence"], bluff_gap=gap, level=level,
                    reasons=(["states the claim as settled, but its support is an assumption"]
                             if level != "ok" else [])))
            row_level = "flag" if "flag" in levels else ("watch" if "watch" in levels else "ok")
            seat_rows.append(SeatHonesty(
                seat_no=n, model_id=s["m"].id, claims=len(levels), flagged=levels.count("flag"),
                watched=levels.count("watch"), mean_probe=None,
                mean_gap=round(sum(f.bluff_gap for f in flags if f.seat_no == n) / len(levels), 3),
                level=row_level))
        rank = {"flag": 0, "watch": 1, "ok": 2}
        flags.sort(key=lambda f: (rank[f.level], -(f.bluff_gap or 0.0), f.seat_no, f.claim_id))
        return LieReport(run_id=self.run_id, seats=seat_rows, flags=flags, probe_models=[],
                         note="no active probe: behaviour signals only")

    def counters(self, t_total_ms: float, **extra: Any) -> RunCounters:
        return RunCounters(calls=self.calls, calls_failed=self.calls_failed, tokens_in=self.tok_in,
                           tokens_out=self.tok_out, tokens_reasoning=self.tok_reason, wall_ms=t_total_ms,
                           phase_ms=dict(self.phase_ms),
                           cloud_equiv_usd=round((self.tok_in * 3.0 + self.tok_out * 15.0) / 1e6, 5), **extra)

    def act_one(self) -> None:
        rid, seats = self.run_id, self.seats
        seat_nos = [s["seat_no"] for s in seats]

        # 1-4 intake, brief, recall, profile
        self.e(0.0, ET.RUN_CREATED, task=self.task, workspace="./service", mode="standard", deliverable="plan",
               state=RunState.INTAKE, created_at=_EPOCH, options={"demo": True, "seed": self.seed})
        self.to(0.05, RunState.INTAKE, "run created")
        self.e(0.45, ET.BRIEF_READY, workspace="./service",
               summary="Python web service with 14 routes. Redis is used for caching. No rate limiting yet.",
               file_count=47, languages=["python", "toml"],
               key_files=["app/main.py", "app/cache.py", "requirements.txt", "tests/test_routes.py"],
               tree="service/\n  app/\n    main.py\n    cache.py\n    routes/\n  tests/\n  requirements.txt",
               cached=False, ms=380.0)
        self.record = [
            ChronicleEntry(id="ce-0007", kind="precedent", scope="project:9f2c1a", status="active", confidence=0.72,
                           statement="Rate limits in this project use fixed-window counters keyed by API key.",
                           rationale="Chosen in an earlier run for its simplicity.", support_count=2,
                           created_at=_EPOCH - 21 * 86400.0, last_confirmed_at=_EPOCH - 9 * 86400.0),
            ChronicleEntry(id="ce-0011", kind="preference", scope="global", status="active", confidence=0.9,
                           statement="The user wants no new dependency unless one is already present.",
                           rationale="Stated by the user as a standing rule.", support_count=3,
                           created_at=_EPOCH - 40 * 86400.0, last_confirmed_at=_EPOCH - 2 * 86400.0),
            ChronicleEntry(id="ce-0003", kind="project_fact", scope="project:9f2c1a", status="provisional",
                           confidence=0.31, statement="Redis is not available in the dev environment.",
                           rationale="Inferred once from a failed connection.", support_count=1, contradict_count=1,
                           created_at=_EPOCH - 55 * 86400.0, review_after=20),
        ]
        self.e(0.75, ET.RECALL_READY, entries=self.record, count=len(self.record), ms=41.0,
               record_block="\n".join(f"[{c.status} {c.confidence:.2f}] {c.statement}" for c in self.record))
        self.to(0.85, RunState.PROFILING, "brief and recall ready")
        self.turn(0.9, 0.6, f"{rid}:profile", "profile", self.worker.id, None, "", tokens_in=310,
                  parsed={"difficulty": "medium", "deliverable": "plan"}, max_out=200)
        self.profile = TaskProfile(categories=dict(_PROFILE_WEIGHTS), difficulty="medium", needs=[],
                                   deliverable="plan",
                                   rationale="Design and build task: mostly code, with planning and some logic.")
        self.e(1.55, ET.PROFILE_READY, profile=self.profile, model_id=self.worker.id, ms=600.0)
        self.e(1.6, ET.EFFORT_PLANNED, level="normal", rounds=["r0", "r1", "r2", "r3"], deadline_s=300.0,
               reasoning="council", max_extra_rounds=1, difficulty="medium",
               rationale="Medium difficulty: the mode's four rounds, plus one extra voting round if the vote is close.")

        # 5 convene
        self.to(1.65, RunState.CONVENING, "profile ready")
        self.e(1.7, ET.MEMORY_PLANNED, plan=self.memory_plan().model_dump(mode="json"))
        lineup_ids = {s["m"].id for s in seats}
        cands = []
        for m in sorted(self.pool, key=lambda m: (-self.q[m.id], m.id)):
            eligible = m.id in lineup_ids or m in self.alternates
            cands.append(ET.ScoredCandidate(model_id=m.id, display=m.display or m.id, lab=m.lab, q=self.q[m.id],
                                            eligible=eligible,
                                            reason="" if eligible else "not a seat model, or below the quality floor"))
        qs = [s["q"] for s in seats]
        merit = round(sum(qs) / len(qs), 3)
        score = LineupScore(merit=merit, vote=round(min(0.99, merit + 0.11), 3), cover=0.91, div=1.0, load=0.18,
                            repeat=0.0, total=round(merit + 0.62, 3))
        rejected = []
        for i, alt in enumerate(self.alternates[:3]):  # same core, another model in the wildcard seat
            ids = [s["m"].id for s in seats[:-1]] + [alt.id]
            rejected.append(RejectedLineup(models=ids, score=LineupScore(
                merit=round(merit - 0.012 * (i + 1), 3), vote=score.vote, cover=0.88, div=round(1.0 - 0.05 * i, 2),
                load=0.2, repeat=0.0, total=round(score.total - 0.03 * (i + 1), 3))))
        self.e(1.95, ET.ROUTER_CANDIDATES_SCORED, candidates=cands, lineups_considered=126, top=rejected,
               tier="A", k=_K)
        self.lineup = LineupRecord(
            seats=[SeatAssignment(seat_no=s["seat_no"], model_id=s["m"].id, lens=s["lens"], is_wildcard=s["wild"],
                                  is_chair=s["chair"], q=s["q"]) for s in seats],
            alternates=[m.id for m in self.alternates], chair_model_id=self.chair["m"].id, tier="A",
            chosen_score=score, rejected=rejected, seed=self.seed, k=_K)
        self.e(2.25, ET.ROUTER_LINEUP_SELECTED, lineup=self.lineup, models=[self.info(s["m"]) for s in seats],
               chair_model_id=self.chair["m"].id, wildcard_seat_no=seats[-1]["seat_no"], score=score,
               mode="standard", k=_K, labs=len({s["m"].lab or s["m"].id for s in seats}))
        for s in seats:
            self.e(2.35 + 0.06 * s["seat_no"], ET.SEAT_ASSIGNED, seat_no=s["seat_no"], model_id=s["m"].id,
                   display=s["m"].display or s["m"].id, lab=s["m"].lab, lens=s["lens"], is_wildcard=s["wild"],
                   is_chair=s["chair"], q=s["q"], label=s["label"])
        w = self.worker
        self.e(2.75, ET.MODEL_EVICTED, **self.mev(w), freed_gib=self.fp[w.id], for_model_id=seats[0]["m"].id,
               reason="idle since the last run; headroom reserved for seat loads")
        t = 2.9
        avail = _MEM_TOTAL_GIB - _MEM_SYSTEM_GIB
        for s in seats:
            m = s["m"]
            load_s = round(0.75 + self.fp[m.id] / 90.0, 2)
            self.e(t, ET.MODEL_LOADING, **self.mev(m), mem_available_gib=round(avail, 1),
                   reason=f"seat {s['seat_no']}", expected_load_s=load_s)
            if s["seat_no"] == 2:  # one health-check failure, reloaded once (10.11)
                t += load_s
                self.e(t, ET.MODEL_FAILED, **self.mev(m), mem_available_gib=round(avail, 1),
                       error="health check got no reply within 5 s", stage="health", replaced_by=None)
                t += 0.15
                self.e(t, ET.MODEL_LOADING, **self.mev(m), mem_available_gib=round(avail, 1),
                       reason=f"seat {s['seat_no']}, reload after failed health check", expected_load_s=load_s)
            t += load_s
            avail -= self.fp[m.id]
            self.e(t, ET.MODEL_LOADED, **self.mev(m), mem_available_gib=round(avail, 1),
                   load_ms=round(load_s * 1000.0, 1), ctx=m.serve.live.ctx, parallel=m.serve.live.parallel,
                   endpoint=f"http://127.0.0.1:{8101 + s['seat_no']}/v1")
            if s["seat_no"] == _STEERED:  # a vector from an earlier run of this project goes in with the seat
                self.e(t + 0.05, ET.STEER_APPLIED, project=_PROJECT, model_id=m.id, scale=0.35,
                       layers=[14, 16, 18, 20, 22, 24, 26],
                       source=f"steer/{_PROJECT}/{m.id}/v1/vector.gguf")
            t += 0.1

        # 6 round 0: blind drafts
        t += 0.1
        self.to(t, RunState.DELIBERATING, "all seats resident")
        t += 0.1
        self.round = 0
        self.e(t, ET.ROUND_STARTED, round=0, purpose="seat.r0", seats=seat_nos, deadline_s=300.0)
        r0 = t
        ends = []
        for s, d in zip(seats, _DRAFTS):
            draft = Draft(answer=d["answer"], summary=d["summary"],
                          claims=[Claim(id=c[0], text=c[1], support=c[2]) for c in d["claims"]],
                          assumptions=["Limits are per API key."], risks=d["risks"], confidence=d["confidence"],
                          would_change_mind=d["change"])
            ends.append(self.turn(t + 0.05 + 0.07 * s["seat_no"], 4.6 + 0.35 * ((s["seat_no"] * 3) % 5),
                                  f"{rid}:r0:s{s['seat_no']}", "seat.r0", s["m"].id, s["seat_no"], d["answer"],
                                  parsed=draft.model_dump(mode="json"), reasoning_text=d["reasoning"],
                                  tokens_in=1840, max_out=700))
        t = max(ends) + 0.4
        for s, d in zip(seats, _DRAFTS):  # 28.5: advisory claim scores, behaviour only (no probe yet)
            scores = [ClaimScore(claim_ref=c[0], seat_no=s["seat_no"],
                                 reliability=round(min(0.95, d["confidence"] - 0.06 - 0.09 * i), 2))
                      for i, c in enumerate(d["claims"])]
            self.e(t - 0.25 + 0.03 * s["seat_no"], ET.PROBE_SCORES, seat_no=s["seat_no"], model_id=s["m"].id,
                   round=0, scores=scores, probe_status=None, shown_to_council=False)

        # 7 agreement check
        holders = {o: [s["seat_no"] for s, d in zip(seats, _DRAFTS) if d["option"] == o] for o in (_O1, _O2)}
        options0 = [Option(id=o, summary=_OPTION_SUMMARY[o], holders=holders[o]) for o in (_O1, _O2)]
        tally0 = {o: len(h) for o, h in holders.items()}
        lie = self.lie_report()
        self.e(t + 0.05, ET.LIE_REPORT, report=lie.model_dump(mode="json"),
               flagged=sum(1 for f in lie.flags if f.level == "flag"),
               watched=sum(1 for f in lie.flags if f.level == "watch"))
        self.e(t, ET.OPTIONS_CLUSTERED, round=0, options=options0, tally=tally0, agreement=0.6,
               leading_option_id=_O1)
        self.e(t + 0.1, ET.ROUND_COMPLETED, round=0, options=options0, tally=tally0, agreement=0.6,
               leading_option_id=_O1, valid_turns=_K, failed_seats=[], converged=False,
               ms=round((t + 0.1 - r0) * 1000.0, 1))
        cruxes = [
            Crux(id="cx1", kind="checkable", between=[_O1, _O2],
                 statement="Redis is already a dependency of this service, so a Lua script adds no new infrastructure."),
            Crux(id="cx2", kind="factual", between=[_O1, _O2],
                 statement="A weighted sliding window still admits close to twice the limit at a window boundary."),
            Crux(id="cx3", kind="value", between=[_O1, _O2],
                 statement="When the limiter store is unreachable, the API should fail open rather than fail closed."),
        ]
        self.e(t + 0.2, ET.CONSENSUS_FAILED, round=0, agreement=0.6, threshold=0.8, tally=tally0,
               leading_option_id=_O1, open_cruxes=cruxes, reason="3 of 5 seats agree; 4 of 5 are needed",
               next_step="round")
        t += 0.6
        self.e(t, ET.CRUXES_EXTRACTED, round=0, cruxes=cruxes)

        # a value crux belongs to the user (10.1)
        t += 0.2
        self.to(t, RunState.AWAITING_USER, "crux cx3 is a value judgment")
        choices = ["Fail open: serve traffic, log and alert", "Fail closed: reject until the store is back"]
        self.e(t + 0.05, ET.USER_INPUT_REQUESTED, request_id=f"{rid}:q1", crux_id="cx3", options=choices,
               question="If the rate limiter cannot reach its store, should requests be let through or refused?",
               context="Two seats would refuse traffic to block abuse. Three would rather keep the API up.",
               from_state=RunState.DELIBERATING, source="decision")
        t += 2.2
        self.e(t, ET.USER_INPUT_RECEIVED, request_id=f"{rid}:q1", choice=choices[0], text=None,
               resume_state=RunState.DELIBERATING)
        self.to(t + 0.1, RunState.DELIBERATING, "user answered cx3")
        cruxes[2] = cruxes[2].model_copy(update={"resolved": True, "resolved_by": "user"})

        # 8 round 1: examine
        t += 0.3
        self.round = 1
        self.e(t, ET.ROUND_STARTED, round=1, purpose="seat.r1", seats=seat_nos, deadline_s=240.0,
               focus_crux_ids=["cx1", "cx2"])
        r1 = t
        ends = []
        for s in seats:
            n = s["seat_no"]
            mine = _DRAFTS[n]["option"]
            other = "D" if mine == _O1 else "B"
            flaw = (Flaw(id="f1", claim_ref="c2", severity="major", kind="factual",
                         text="The weighted estimate assumes even traffic; a bursty client gets near twice the limit.")
                    if mine == _O1 else
                    Flaw(id="f2", claim_ref="c2", severity="minor", kind="risk",
                         text="No bound is given on the script's run time on the Redis thread."))
            crit = Critique(
                reviews=[Review(target=other, flaws=[flaw],
                                strongest_point="No script to operate." if mine == _O1 else "The burst is bounded exactly.",
                                verdict="worse_than_mine" if n != 3 else "better_than_mine")],
                checks_requested=[CheckRequest(kind="grep", spec="redis -- requirements.txt app/", settles="cx1")]
                if n == 1 else [],
                position="adopt:B" if n == 3 else "keep", changed_because=["f1"] if n == 3 else [])
            parsed = crit.model_dump(mode="json")
            t0 = t + 0.05 + 0.06 * n
            dur = 3.0 + 0.3 * ((n * 2) % 5)
            cid = f"{rid}:r1:s{n}"
            if n == 2:  # first call times out, second one lands
                self.e(t0, ET.TURN_STARTED, call_id=cid, purpose="seat.r1", model_id=s["m"].id, seat_no=n,
                       round=1, reasoning="council", max_output_tokens=500, attempt=1)
                self.stream(t0, 1.0, ET.TURN_DELTA, "Both counter drafts assume", 2, call_id=cid, seat_no=n)
                self.e(t0 + 1.6, ET.TURN_TIMEOUT, call_id=cid, seat_no=n, round=1, purpose="seat.r1",
                       model_id=s["m"].id, timeout_s=1.6, ms=1600.0, will_retry=True)
                ends.append(self.turn(t0 + 1.7, dur - 0.4, cid + ":b", "seat.r1", s["m"].id, n, _CRITIQUE_TEXT[n],
                                      parsed=parsed, tokens_in=2210, attempt=2))
            elif n == 3:  # first output breaks the schema, the ladder retries inside the same call
                self.e(t0, ET.TURN_STARTED, call_id=cid, purpose="seat.r1", model_id=s["m"].id, seat_no=n,
                       round=1, reasoning="council", max_output_tokens=500, attempt=1)
                self.e(t0 + 1.3, ET.TURN_INVALID, call_id=cid, seat_no=n, round=1, purpose="seat.r1",
                       model_id=s["m"].id, attempts=1, will_retry=True,
                       error="changed_because is required when position is not keep",
                       content_tail='"position": "adopt:B", "changed_because": []}')
                ends.append(self.turn(t0 + 1.4, dur - 0.3, cid, "seat.r1", s["m"].id, n, _CRITIQUE_TEXT[n],
                                      parsed=parsed, tokens_in=2210, attempts=2, start=False))
            else:
                ends.append(self.turn(t0, dur, cid, "seat.r1", s["m"].id, n, _CRITIQUE_TEXT[n], parsed=parsed,
                                      tokens_in=2210))
            if n == 1:
                self.e(ends[-1] + 0.05, ET.EVIDENCE_REQUESTED, round=1, check_id="ev1", kind="grep",
                       spec="redis -- requirements.txt app/", settles="cx1", crux_id="cx1", requested_by=[1])
        t = max(ends) + 0.2
        self.e(t, ET.ROUND_COMPLETED, round=1, options=options0, tally=tally0, agreement=0.6,
               leading_option_id=_O1, valid_turns=_K, failed_seats=[], converged=False,
               ms=round((t - r1) * 1000.0, 1))
        t += 0.5
        self.e(t, ET.EVIDENCE_RESULT, round=1, check_id="ev1", crux_id="cx1", crux_resolved=True,
               result=EvidenceResult(kind="grep", id="ev1", spec="redis -- requirements.txt app/", settles="cx1",
                                     crux_id="cx1", requested_by=[1], ok=True, exit_code=0, duration_ms=38.0,
                                     output="requirements.txt:7:redis==5.0.8\napp/cache.py:3:import redis\n"
                                            "app/cache.py:11:    return redis.Redis.from_url(settings.REDIS_URL)"))
        cruxes[0] = cruxes[0].model_copy(update={"resolved": True, "resolved_by": "ev1"})

        # round 2: ballots, 4 vs 1
        t += 0.3
        self.round = 2
        self.e(t, ET.ROUND_STARTED, round=2, purpose="seat.r2", seats=seat_nos, deadline_s=200.0,
               focus_crux_ids=["cx2"])
        r2 = t
        ends = []
        ballots: dict[int, Ballot] = {}
        for s in seats:
            n = s["seat_no"]
            choice = _O2 if n == 4 else _O1
            ballots[n] = Ballot(
                choice=choice, ranking=[choice, _O2 if choice == _O1 else _O1], final_answer=_BALLOT_TEXT[n],
                confidence=(0.86, 0.84, 0.81, 0.72, 0.61)[n],
                crux_votes=[CruxVote(crux_id="cx1", stance="agree"),
                            CruxVote(crux_id="cx2", stance="abstain" if n == 4 else "agree")],
                changed_because=["f1"] if n == 3 else [],
                lesson="Check what is already in the stack before arguing about new infrastructure." if n == 1
                else None)
            cid = f"{rid}:r2:s{n}"
            end = self.turn(t + 0.05 + 0.06 * n, 2.2 + 0.25 * ((n * 3) % 5), cid, "seat.r2", s["m"].id, n,
                            _BALLOT_TEXT[n], parsed=ballots[n].model_dump(mode="json"), tokens_in=1480, max_out=400)
            self.e(end + 0.03, ET.BALLOT_CAST, seat_no=n, round=2, ballot=ballots[n], model_id=s["m"].id,
                   call_id=cid, changed=(n == 3))
            ends.append(end)
        t = max(ends) + 0.3
        holders2 = {_O1: [n for n, b in ballots.items() if b.choice == _O1],
                    _O2: [n for n, b in ballots.items() if b.choice == _O2]}
        self.options = [Option(id=o, summary=_OPTION_SUMMARY[o], holders=holders2[o]) for o in (_O1, _O2)]
        tally2 = {o: len(h) for o, h in holders2.items()}
        cruxes[1] = cruxes[1].model_copy(update={"resolved": True, "resolved_by": "vote"})
        self.e(t, ET.ROUND_COMPLETED, round=2, options=self.options, tally=tally2, agreement=0.8,
               leading_option_id=_O1, valid_turns=_K, failed_seats=[], converged=False,
               ms=round((t - r2) * 1000.0, 1))

        # round 3: the vote sits exactly on the line, so the effort plan adds one round for the last objection
        t += 0.2
        self.e(t, ET.ROUND_EXTENDED, round=3, agreement=0.8, extra_used=1, extra_max=1,
               reason="the vote is exactly at the 80% line and seat 4 still has an open objection")
        t += 0.1
        self.round = 3
        self.e(t, ET.ROUND_STARTED, round=3, purpose="seat.r3", seats=[_OUTLIER], deadline_s=120.0,
               focus_crux_ids=["cx2"])
        r3 = t
        n = _OUTLIER
        b3 = Ballot(choice=_O2, ranking=[_O2, _O1], confidence=0.58,
                    final_answer="Sliding-window counter. I accept that the bucket bounds the burst, but I "
                                 "still rank not running a script on the Redis thread higher.",
                    crux_votes=[CruxVote(crux_id="cx1", stance="agree"), CruxVote(crux_id="cx2", stance="abstain")])
        cid = f"{rid}:r3:s{n}"
        end = self.turn(t + 0.05, 2.0, cid, "seat.r3", seats[n]["m"].id, n, b3.final_answer,
                        parsed=b3.model_dump(mode="json"), tokens_in=1320, max_out=300)
        self.e(end + 0.03, ET.BALLOT_CAST, seat_no=n, round=3, ballot=b3, model_id=seats[n]["m"].id,
               call_id=cid, changed=False)
        t = end + 0.3
        self.e(t, ET.ROUND_COMPLETED, round=3, options=self.options, tally=tally2, agreement=0.8,
               leading_option_id=_O1, valid_turns=1, failed_seats=[], converged=True,
               ms=round((t - r3) * 1000.0, 1))
        self.e(t + 0.15, ET.CONSENSUS_REACHED, round=3, option_id=_O1, agreement=0.8, threshold=0.8,
               tally=tally2, outcome="consensus", early=False)

        # 9 decision: chair merge, ratify
        t += 0.35
        chair_call = f"{rid}:chair"
        self.e(t, ET.CHAIR_STARTED, call_id=chair_call, model_id=self.chair["m"].id,
               seat_no=self.chair["seat_no"], reason="plan mode: merge the agreeing group into one final text")
        t = self.turn(t + 0.02, 4.0, chair_call, "chair", self.chair["m"].id, self.chair["seat_no"], _CHAIR_TEXT,
                      tokens_in=3120, max_out=900, delta=ET.CHAIR_DELTA)
        votes = {str(n): n != 4 for n in seat_nos}
        t += 0.5
        self.e(t, ET.RATIFY_RESULT, ratified=True, votes_for=4, votes_against=1, votes=votes, option_id=_O1,
               objections=["The script's run time on the Redis thread is still unmeasured."])
        self.decision = Decision(
            outcome="consensus", option_id=_O1, final_text=_CHAIR_TEXT, agreement=0.8, tally=tally2, rounds_run=4,
            confidence=0.81,
            minority_report=[MinorityPosition(
                seats=[4], option_id=_O2, position=_OPTION_SUMMARY[_O2],
                strongest_argument="A script runs on the single Redis thread, so a slow one stalls every caller. "
                                   "INCR and EXPIRE cannot do that.")],
            open_cruxes=[],
            departures=[Departure(chronicle_entry_id="ce-0007",
                                  why="A fixed window admits twice the limit across a boundary; the council "
                                      "chose a token bucket for this limiter.")])
        self.e(t + 0.2, ET.DECISION_FINAL, decision=self.decision, options=self.options,
               ms=round((t + 0.2 - r0) * 1000.0, 1))
        t += 0.3
        self.to(t, RunState.DECIDED, "consensus, ratified 4 to 1")

        # 9b tribunal: the dissenting seat defends its position (27)
        t = self.tribunal(t + 0.2)

        # 10 plan
        t += 0.2
        self.to(t, RunState.PLANNING, "deliverable is a plan")
        plan_v1 = self.plan(lint_gap=True)
        t = self.turn(t + 0.1, 1.9, f"{rid}:foreman:1", "foreman.decompose", self.chair["m"].id, None, "",
                      parsed={"tasks": [x["id"] for x in _TASKS]}, tokens_in=2650, max_out=1500)
        self.e(t + 0.05, ET.PLAN_DRAFTED, plan=plan_v1, version=1, task_count=len(plan_v1.tasks),
               model_id=self.chair["m"].id, call_id=f"{rid}:foreman:1")
        self.e(t + 0.3, ET.PLAN_LINTED, ok=False, version=1, task_count=len(plan_v1.tasks), will_retry=True,
               errors=["T8 has no machine-checkable acceptance and no review rubric"],
               warnings=["T2 writes 2 files, the most a micro-task may write"])
        self.the_plan = self.plan(lint_gap=False)
        t = self.turn(t + 0.4, 0.8, f"{rid}:foreman:2", "foreman.decompose", self.chair["m"].id, None, "",
                      parsed={"patched": ["T8"]}, tokens_in=2890, max_out=600)
        n_tasks = len(self.the_plan.tasks)
        self.e(t + 0.05, ET.PLAN_DRAFTED, plan=self.the_plan, version=2, task_count=n_tasks,
               model_id=self.chair["m"].id, call_id=f"{rid}:foreman:2")
        self.e(t + 0.25, ET.PLAN_LINTED, ok=True, version=2, task_count=n_tasks, will_retry=False, errors=[],
               warnings=["T2 writes 2 files, the most a micro-task may write"])
        reviewer = seats[1]
        t = self.turn(t + 0.35, 1.1, f"{rid}:foreman:review", "foreman.review", reviewer["m"].id,
                      reviewer["seat_no"], "", parsed={"patches": []}, tokens_in=2400, max_out=400)
        self.e(t + 0.05, ET.PLAN_REVIEWED, ok=True, version=2, reviewer_seat_no=reviewer["seat_no"],
               reviewer_model_id=reviewer["m"].id, issues=[],
               changes=["T7 marked senior: a benchmark harness is too much for one micro generation"])
        self.e(t + 0.3, ET.PLAN_READY, plan=self.the_plan, version=2, task_count=n_tasks,
               micro_count=sum(1 for x in self.the_plan.tasks if x.tier == "micro"),
               senior_count=sum(1 for x in self.the_plan.tasks if x.tier == "senior"), edited_by_user=False)
        self.to(t + 0.5, RunState.AWAITING_DELEGATION, "plan ready, waiting for the user to delegate")

    def tribunal(self, t: float) -> float:
        """Cross-examination of the outlier seat. It concedes, so a correction is recorded. Returns end time."""
        rid, seats = self.run_id, self.seats
        out = seats[_OUTLIER]
        judges = [s["seat_no"] for s in seats if s["seat_no"] != _OUTLIER]
        t_start = t
        self.to(t, RunState.EXAMINING, f"seat {_OUTLIER} is cross-examined")
        self.e(t + 0.05, ET.TRIBUNAL_STARTED, outlier_seat=_OUTLIER, outlier_model_id=out["m"].id, distance=0.65,
               option_id=_O1, outlier_option_id=_O2, examiners=list(_EXAMINERS), judges=judges,
               questions=len(_TRIBUNAL_QA))
        t += 0.15
        questions, ends = [], []
        for i, (n, qa) in enumerate(zip(_EXAMINERS, _TRIBUNAL_QA)):
            q = TribunalQuestion(question=qa["q"], targets_claim=qa["claim"], seat_no=n)
            questions.append(q)
            cid = f"{rid}:tribunal:q{i}"
            end = self.turn(t + 0.05 * i, 0.9 + 0.15 * i, cid, "tribunal.question", seats[n]["m"].id, n, qa["q"],
                            parsed=q.model_dump(mode="json"), tokens_in=1320, max_out=200)
            self.e(end + 0.03, ET.TRIBUNAL_QUESTION, seat_no=n, model_id=seats[n]["m"].id, index=i, question=q,
                   outlier_seat=_OUTLIER, call_id=cid)
            ends.append(end)
        t = max(ends) + 0.2
        answers = [TribunalAnswer(answer=qa["a"], concedes=qa["concedes"], seat_no=_OUTLIER)
                   for qa in _TRIBUNAL_QA]
        cid = f"{rid}:tribunal:answer"
        t = self.turn(t, 1.6, cid, "tribunal.answer", out["m"].id, _OUTLIER,
                      " ".join(a.answer for a in answers),
                      parsed={"answers": [a.model_dump(mode="json") for a in answers]}, tokens_in=1510, max_out=500)
        for i, a in enumerate(answers):
            self.e(t + 0.03 + 0.03 * i, ET.TRIBUNAL_ANSWER, seat_no=_OUTLIER, model_id=out["m"].id, index=i,
                   answer=a, call_id=cid)
        t += 0.2
        verdicts, ends = [], []
        for j, n in enumerate(judges):
            v = DefenseVerdict(held=False, score=(0.2, 0.25, 0.15, 0.3)[j % 4],
                               decisive_point=_VERDICT_POINTS[j % len(_VERDICT_POINTS)],
                               error_kind="logic" if j == 3 else "ignored_evidence", lesson=_TRIBUNAL_LESSON,
                               seat_no=n)
            verdicts.append(v)
            cid = f"{rid}:tribunal:v{n}"
            end = self.turn(t + 0.04 * j, 0.8 + 0.1 * j, cid, "tribunal.verdict", seats[n]["m"].id, n,
                            v.decisive_point, parsed=v.model_dump(mode="json"), tokens_in=1740, max_out=250)
            self.e(end + 0.03, ET.TRIBUNAL_VERDICT, seat_no=n, model_id=seats[n]["m"].id, verdict=v, call_id=cid)
            ends.append(end)
        t = max(ends) + 0.2
        self.correction = Correction(
            id="cor-0001", project=_PROJECT, model_id=out["m"].id, lineage=out["m"].lineage, run_id=rid,
            created_at=round(_EPOCH + t, 3), task=self.task[:400], wrong_position=_OPTION_SUMMARY[_O2],
            council_position=_OPTION_SUMMARY[_O1], error_kind="ignored_evidence", lesson=_TRIBUNAL_LESSON,
            verified_by="conceded",
            examples=[TrainingExample(
                messages=[{"role": "user", "content": self.task + "\n\nA reviewer says: " + _TRIBUNAL_QA[1]["q"]}],
                target="The weighted window does not bound the burst, so it misses the requirement. "
                       "Use the token bucket.")])
        outcome = TribunalOutcome(outlier_seat=_OUTLIER, outlier_model_id=out["m"].id, outcome="conceded",
                                  held_share=0.0, error_kind="ignored_evidence", lesson=_TRIBUNAL_LESSON,
                                  questions=questions, answers=answers, verdicts=verdicts,
                                  correction_id=self.correction.id)
        self.e(t, ET.TRIBUNAL_OUTCOME, outcome=outcome, seat_no=_OUTLIER, model_id=out["m"].id,
               contested_after_review=False, correction_eligible=True,
               reason="the member conceded and no judge said the defence held",
               ms=round((t - t_start) * 1000.0, 1))
        self.dataset_size = 8
        self.e(t + 0.15, ET.CORRECTION_RECORDED, correction=self.correction, seat_no=_OUTLIER,
               model_id=out["m"].id, project=_PROJECT, dataset_size=self.dataset_size)
        return t + 0.3

    def bench_and_probe(self, t: float) -> float:
        """During reflection: a small solo bench of the outlier, then one probe is validated (28.4)."""
        rid = self.run_id
        m = self.seats[_OUTLIER]["m"]
        bench_id, mode = f"{rid}:gate", f"solo:{m.id}"
        graded = (True, True, False, True)
        self.e(t + 0.2, ET.BENCH_STARTED, bench_id=bench_id, modes=[mode], models=[m.id], tasks=len(graded),
               total=len(graded),
               request=BenchRunRequest(tasks_path="bench/tasks/sample.jsonl", modes=[mode], split="calibration",
                                       limit=len(graded), models=[m.id]))
        correct = 0
        for i, ok in enumerate(graded):
            correct += ok
            res = BenchResult(id=f"gate-{i + 1}", mode=mode, answer="B" if ok else "C", answer_key="B", correct=ok,
                              tokens_in=410 + 20 * i, tokens_out=36, wall_ms=310.0 + 15 * i, lineup=[m.id])
            self.e(t + 0.5 + 0.3 * i, ET.BENCH_PROGRESS, bench_id=bench_id, mode=mode, model_id=m.id, done=i + 1,
                   total=len(graded), correct=correct, result=res)
        t += 0.5 + 0.3 * len(graded)
        acc = correct / len(graded)
        self.e(t, ET.BENCH_COMPLETED, bench_id=bench_id, results_path="",
               summary=[BenchSummaryRow(mode=mode, n=len(graded), accuracy=acc, mean_tokens=476.0,
                                        mean_wall_ms=332.5)],
               ms=round((0.3 + 0.3 * len(graded)) * 1000.0, 1))
        chair = self.chair["m"]
        self.e(t + 0.7, ET.PROBE_TRAINED, model_id=chair.id, validated=True, layers_tried=[8, 12, 16],
               auroc_by_layer={"8": 0.61, "12": 0.7, "16": 0.74}, top_dims=[412, 87, 1930, 655], ms=840.0,
               probe=Probe(model_id=chair.id, layer=16, weights=[0.42, -0.31, 0.27, -0.22], bias=-0.08,
                           auroc=0.74, n_train=212, trained_at=round(_EPOCH + self.clock + t + 0.7, 3),
                           status="validated"))
        self.e(t + 0.9, ET.STEER_TRAINED, project=_PROJECT, model_id=m.id, examples=self.dataset_size, scale=0.35,
               active=True,
               reason="strength 0.35 passed the sanity check; larger strengths broke the model's answers")
        return t + 1.1

    def plan(self, lint_gap: bool) -> Plan:
        by_name = {i.name: i for i in _INTERFACES}
        tasks = []
        for x in _TASKS:
            checks = [Check(id=f"{x['id']}.c{i + 1}", **c) for i, c in enumerate(x["checks"])]
            if lint_gap and x["id"] == "T8":
                checks = []
            tasks.append(MicroTask(
                id=x["id"], title=x["title"], kind=x["kind"], goal=x["goal"],
                context=TaskContext(interfaces=[by_name[n] for n in x["ifaces"]],
                                    notes="Standard library only. Redis client is already installed."),
                read_set=["limiter/"] if x["deps"] else [], write_set=list(x["write"]),
                output_contract="Exactly these files exist and pass the checks: " + ", ".join(x["write"]),
                acceptance=checks, deps=list(x["deps"]), tier=x["tier"],
                budget=TaskBudget(max_output_tokens=1500, max_attempts=2 if x["tier"] == "senior" else 3)))
        return Plan(
            goal=self.task, approach=_CHAIR_TEXT, interfaces=list(_INTERFACES),
            deliverables=[
                Deliverable(id="d1", description="Rate limiter package",
                            paths=["limiter/bucket.py", "limiter/config.py", "limiter/store_redis.py",
                                   "limiter/take.lua", "limiter/store_memory.py", "limiter/middleware.py",
                                   "limits.toml"]),
                Deliverable(id="d2", description="Tests and benchmark",
                            paths=["tests/test_limiter.py", "bench/burst.py"]),
                Deliverable(id="d3", description="Docs", paths=["docs/rate_limiting.md"]),
            ],
            global_acceptance=[
                Check(id="g1", type="command", cmd="python -m unittest discover -s tests", timeout_s=120.0),
                Check(id="g2", type="exists", path="limiter/middleware.py"),
            ],
            out_of_scope=["Per-IP limits", "A dashboard for limit usage", "Changing the Redis deployment"],
            risks=["The Lua script runs on the single Redis thread; keep it under 20 lines."],
            tasks=tasks)

    # -- story: after delegation ----------------------------------------------------------

    def attempt(self, t0: float, dur: float, task: MicroTask, n: int, model_id: str, tier: str, text: str,
                fail: Optional[tuple[int, str, int]] = None, blocked: Optional[str] = None,
                will_retry: bool = False) -> tuple[float, AttemptRecord]:
        """One worker generation plus its checks. Returns (end time, record)."""
        call_id = f"{self.run_id}:{task.id}:a{n}"
        temp = 0.6 if (n == 2 and tier == "micro") else 0.2
        common = dict(task_id=task.id, title=task.title, attempt=n, model_id=model_id, tier=tier)
        self.e(t0, ET.TASK_STARTED, call_id=call_id, max_attempts=task.budget.max_attempts, temperature=temp,
               **common)
        body = text if blocked is None else '{"ops":[],"notes":"","blocked":"' + blocked + '"}'
        self.stream(t0, dur, ET.TASK_DELTA, body, 4, task_id=task.id, attempt=n, call_id=call_id)
        t = t0 + dur
        results: list[CheckResult] = []
        failing = None
        tail = ""
        if blocked is None:
            for i, chk in enumerate(task.acceptance):
                bad = fail is not None and fail[0] == i
                self.e(t, ET.CHECK_STARTED, task_id=task.id, attempt=n, check_id=chk.id, check=chk, level="L1")
                took = 0.34 if chk.type == "command" else 0.12
                t += took
                res = CheckResult(ok=not bad, type=chk.type, check=chk, check_id=chk.id, task_id=task.id,
                                  attempt=n, level="L1", duration_ms=round(took * 1000.0, 1),
                                  exit_code=(fail[2] if bad else 0) if chk.type == "command" else None,
                                  output_tail=fail[1] if bad else ("OK" if chk.type == "command" else ""))
                results.append(res)
                self.e(t, ET.CHECK_RESULT, result=res, task_id=task.id, attempt=n, check_id=chk.id, level="L1",
                       ok=res.ok)
                t += 0.03
                if bad:
                    failing, tail = chk.id, fail[1]
                    break
        ok = blocked is None and failing is None
        files = list(task.write_set) if ok else []
        tok_in, tok_out = 1150 + 240 * (n - 1), _tokens(body)
        rec = AttemptRecord(
            task_id=task.id, attempt=n, model_id=model_id, temperature=temp, ok=ok, blocked=blocked,
            output=WorkerOutput(ops=[] if blocked else [WorkerOp(op="write_file", path=p, content="...")
                                                        for p in task.write_set], blocked=blocked),
            checks=results, failing_check=failing, error_tail=tail, files_changed=files, tokens_in=tok_in,
            tokens_out=tok_out, wall_ms=round((t - t0) * 1000.0, 1))
        self.e(t, ET.TASK_ATTEMPT_COMPLETED, status=TaskStatus.running, ok=ok, record=rec, blocked=blocked,
               failing_check=failing, error_tail=tail, files_changed=files, tokens_in=tok_in, tokens_out=tok_out,
               tps=round(tok_out / max(dur, 0.1), 1), ms=round((t - t0) * 1000.0, 1), will_retry=will_retry,
               **common)
        return t, rec

    def ended(self, t: float, type: str, task: MicroTask, model_id: Optional[str], tier: str,
              recs: list[AttemptRecord], t0: float, reason: str = "", **extra: Any) -> None:
        last = recs[-1] if recs else None
        self.e(t, type, task_id=task.id, title=task.title, attempt=last.attempt if last else 0, model_id=model_id,
               tier=tier, attempts=len(recs), checks=last.checks if last else [],
               failing_check=last.failing_check if last else None, error_tail=last.error_tail if last else "",
               reason=reason, files_changed=last.files_changed if last else [], ms=round((t - t0) * 1000.0, 1),
               **extra)
        self.final[task.id] = (type, recs, model_id)

    def act_two(self) -> None:
        rid, seats = self.run_id, self.seats
        plan = self.the_plan
        T = {x.id: x for x in plan.tasks}
        text = {x["id"]: x["text"] for x in _TASKS}
        w, senior = self.worker, self.senior
        self.final: dict[str, tuple[str, list[AttemptRecord], Optional[str]]] = {}

        # 11 delegate
        self.to(0.1, RunState.EXECUTING, "user delegated")
        avail = _MEM_TOTAL_GIB - _MEM_SYSTEM_GIB - sum(self.resident.values())
        self.e(0.2, ET.MODEL_LOADING, **self.mev(w, "batch"), mem_available_gib=round(avail, 1),
               reason="worker fleet, batch profile", expected_load_s=0.7)
        self.e(0.9, ET.MODEL_LOADED, **self.mev(w, "batch"), mem_available_gib=round(avail - self.fp[w.id], 1),
               load_ms=700.0, ctx=w.serve.batch.ctx, parallel=w.serve.batch.parallel,
               endpoint="http://127.0.0.1:8110/v1")
        self.e(1.0, ET.DELEGATION_STARTED, task_count=len(plan.tasks), task_ids=[x.id for x in plan.tasks],
               workers=[self.info(w, True), self.info(senior, True)], max_parallel=w.serve.batch.parallel,
               cycle=0, plan_version=2)
        for i, x in enumerate(plan.tasks):
            self.e(1.05 + 0.02 * i, ET.TASK_QUEUED, task_id=x.id, title=x.title, attempt=0, tier=x.tier,
                   kind=x.kind, deps=x.deps, write_set=x.write_set, cycle=0,
                   model_id=senior.id if x.tier == "senior" else w.id)

        # wave 1: T1, T2 pass first time
        a, r = self.attempt(1.3, 1.6, T["T1"], 1, w.id, "micro", text["T1"])
        self.ended(a + 0.05, ET.TASK_PASSED, T["T1"], w.id, "micro", [r], 1.3)
        b, r = self.attempt(1.36, 1.35, T["T2"], 1, w.id, "micro", text["T2"])
        self.ended(b + 0.05, ET.TASK_PASSED, T["T2"], w.id, "micro", [r], 1.36)

        # wave 2: T4 passes; T3 fails its first attempt and passes on the retry (12.2)
        t0 = max(a, b) + 0.25
        c, r = self.attempt(t0 + 0.05, 1.5, T["T4"], 1, w.id, "micro", text["T4"])
        self.ended(c + 0.05, ET.TASK_PASSED, T["T4"], w.id, "micro", [r], t0 + 0.05)
        d, r1 = self.attempt(t0, 1.45, T["T3"], 1, w.id, "micro", text["T3"].replace("redis.call('TIME')", "os.time()"),
                             fail=(1, "pattern not found in limiter/take.lua: redis.call\\('TIME'\\)", 1),
                             will_retry=True)
        d, r2 = self.attempt(d + 0.15, 1.45, T["T3"], 2, w.id, "micro", text["T3"])
        self.ended(d + 0.05, ET.TASK_PASSED, T["T3"], w.id, "micro", [r1, r2], t0)

        # wave 3: T5 fails twice on the worker, escalates to the senior worker, passes
        t0 = max(c, d) + 0.25
        err = ("FAIL: test_fail_open (tests.contract_middleware.ContractTest)\n"
               "AssertionError: ConnectionError escaped take(); expected Decision(allowed=True)")
        f, r1 = self.attempt(t0, 1.35, T["T5"], 1, w.id, "micro",
                             text["T5"].replace("except ConnectionError", "except TimeoutError"),
                             fail=(1, err, 1), will_retry=True)
        f, r2 = self.attempt(f + 0.15, 1.35, T["T5"], 2, w.id, "micro",
                             text["T5"].replace("except ConnectionError", "except OSError as exc"),
                             fail=(1, err.replace("ConnectionError escaped take()", "alert() was never called"), 1),
                             will_retry=True)
        self.e(f + 0.1, ET.TASK_ESCALATED, task_id="T5", title=T["T5"].title, attempt=2, model_id=w.id,
               tier="micro", status=TaskStatus.queued, to="senior", from_tier="micro", to_tier="senior",
               from_model_id=w.id, to_model_id=senior.id, failing_check="T5.c2",
               reason="two worker attempts failed the same contract test")
        f, r3 = self.attempt(f + 0.3, 1.9, T["T5"], 3, senior.id, "senior", text["T5"])
        self.ended(f + 0.05, ET.TASK_PASSED, T["T5"], senior.id, "senior", [r1, r2, r3], t0)

        # wave 4a: T6 is blocked, the Foreman re-specifies it once, then it passes (12.1, 13.2)
        t0 = f + 0.3
        why = "read_set names tests/conftest.py for the fake clock fixture, but that file does not exist"
        g, r1 = self.attempt(t0, 0.8, T["T6"], 1, w.id, "micro", "", blocked=why)
        self.ended(g + 0.05, ET.TASK_BLOCKED, T["T6"], w.id, "micro", [r1], t0, reason=why)
        self.e(g + 0.6, ET.TASK_QUEUED, task_id="T6", title=T["T6"].title + " (re-specified)", attempt=1,
               model_id=w.id, tier="micro", kind=T["T6"].kind, deps=T["T6"].deps, write_set=T["T6"].write_set,
               cycle=0)
        g, r2 = self.attempt(g + 0.75, 1.5, T["T6"], 2, w.id, "micro", text["T6"])
        self.ended(g + 0.05, ET.TASK_PASSED, T["T6"], w.id, "micro", [r1, r2], t0)

        # wave 4b: T7 (senior) fails both attempts; T8 depends on it and is skipped
        bench = "p99 overhead 3.84 ms > 1.00 ms\nAssertionError: latency budget exceeded"
        h, s1 = self.attempt(t0 + 0.06, 1.6, T["T7"], 1, senior.id, "senior", text["T7"], fail=(1, bench, 1),
                             will_retry=True)
        h, s2 = self.attempt(h + 0.15, 1.6, T["T7"], 2, senior.id, "senior", text["T7"],
                             fail=(1, bench.replace("3.84", "3.61"), 1))
        self.ended(h + 0.08, ET.TASK_FAILED, T["T7"], senior.id, "senior", [s1, s2], t0 + 0.06,
                   reason="senior attempts exhausted; marked for the council's review")
        self.ended(h + 0.2, ET.TASK_SKIPPED, T["T8"], None, "micro", [], h + 0.2,
                   reason="depends on T7, which failed", blocked_by=["T7"])

        # L3 integration checks on the staged copy
        t = max(g, h) + 0.5
        integ: list[CheckResult] = []
        for chk, took, tail in zip(plan.global_acceptance, (0.7, 0.1), ("Ran 9 tests in 0.412s\n\nOK", "")):
            self.e(t, ET.CHECK_STARTED, task_id=None, attempt=None, check_id=chk.id, check=chk, level="L3")
            t += took
            res = CheckResult(ok=True, type=chk.type, check=chk, check_id=chk.id, level="L3", output_tail=tail,
                              exit_code=0 if chk.type == "command" else None, duration_ms=took * 1000.0)
            integ.append(res)
            self.e(t, ET.CHECK_RESULT, result=res, task_id=None, attempt=None, check_id=chk.id, level="L3", ok=True)
            t += 0.05
        written = [p for x in plan.tasks if self.final[x.id][0] == ET.TASK_PASSED for p in x.write_set]
        diff = DiffStats(files_added=len(written), files_changed=0, lines_added=312, lines_removed=0)
        self.e(t, ET.INTEGRATION_RESULT, ok=True, stage="checks", checks=integ, files_written=[], diff_stats=diff)

        # 13 review
        t += 0.2
        self.to(t, RunState.REVIEWING, "all tasks finished")
        status = {ET.TASK_PASSED: TaskStatus.passed, ET.TASK_FAILED: TaskStatus.failed,
                  ET.TASK_SKIPPED: TaskStatus.skipped}
        rows = []
        for x in plan.tasks:
            kind, recs, model_id = self.final[x.id]
            last = recs[-1] if recs else None
            rows.append(WorkReportTask(
                id=x.id, title=x.title, status=status[kind], attempts=len(recs), model=model_id,
                failing_check=last.failing_check if last else None, error_tail=last.error_tail if last else "",
                files_changed=last.files_changed if last else []))
        counts = WorkSummary(passed=sum(1 for r in rows if r.status == TaskStatus.passed),
                             failed=sum(1 for r in rows if r.status == TaskStatus.failed),
                             skipped=sum(1 for r in rows if r.status == TaskStatus.skipped))
        report = WorkReport(summary=counts, tasks=rows, integration=integ, diff_stats=diff,
                            deviations=["bench/burst.py and docs/rate_limiting.md were not delivered (d2, d3)"])
        t = self.turn(t + 0.05, 0.5, f"{rid}:clerk:report", "clerk.work_report", w.id, None, "",
                      parsed={"passed": counts.passed, "failed": counts.failed, "skipped": counts.skipped},
                      tokens_in=1900, max_out=400)
        t += 0.1
        self.e(t, ET.REVIEW_STARTED, cycle=0, report=report, seats=[s["seat_no"] for s in seats], max_cycles=2)
        fix = ReviewFix(task_id="T7", problem="The benchmark asserts a wall-clock p99 the sandbox cannot meet.",
                        proposed_change="Assert on call count and correctness; report latency without a threshold.")
        ends = []
        for s in seats:
            n = s["seat_no"]
            verdict, reason = _REVIEW_TEXT[n]
            rb = ReviewBallot(verdict=verdict, reason=reason, fixes=[fix] if verdict == "fix" else [])
            cid = f"{rid}:review0:s{n}"
            end = self.turn(t + 0.05 + 0.06 * n, 1.5 + 0.2 * ((n * 2) % 5), cid, "review", s["m"].id, n, reason,
                            parsed=rb.model_dump(mode="json"), tokens_in=1650, max_out=300)
            self.e(end + 0.03, ET.REVIEW_BALLOT, seat_no=n, model_id=s["m"].id, cycle=0, ballot=rb, call_id=cid)
            ends.append(end)
        t = max(ends) + 0.3
        tally_r = {"accept": 4, "fix": 1}
        self.e(t, ET.REVIEW_DEBATE, cycle=0, tally_before=tally_r, tally_after=dict(tally_r))  # nobody moved
        say = (0, 1, 2, 3)[self.seed % 4]  # a seat from the accepting side, picked from the seed
        t += 0.35
        self.e(t, ET.REVIEW_FINAL_SAY, cycle=0, seat_no=say, model_id=seats[say]["m"].id,
               verdict=_REVIEW_TEXT[say][0], reason=_REVIEW_TEXT[say][1])
        t += 0.3
        self.e(t, ET.REVIEW_VERDICT, verdict="accept", tally=tally_r, fixes=[], cycle=0,
               reason="4 of 5 accept; the failed benchmark and skipped docs are recorded as follow-ups",
               next_state=RunState.INTEGRATING)

        # 14 integrate
        t += 0.2
        self.to(t, RunState.INTEGRATING, "work accepted")
        t += 0.5
        self.e(t, ET.INTEGRATION_RESULT, ok=True, stage="copy", checks=integ, files_written=written,
               diff_stats=diff)
        self.e(t + 0.15, ET.MODEL_UNLOADED, **self.mev(w, "batch"), freed_gib=self.fp[w.id],
               reason="work phase over; worker fleet released")

        # 15 reflect
        t += 0.3
        self.to(t, RunState.REFLECTING, "integration done")
        panel = seats[1:4]
        proj = "project:9f2c1a"

        def ref(quote: str) -> list[EvidenceRef]:
            return [EvidenceRef(run_id=rid, quote=quote)]

        cands = [
            (MemoryCandidate(id="mc1", run_id=rid, source="review_failure", kind_hint="lesson",
                             scope_hint="category:code", evidence=ref("p99 overhead 3.84 ms > 1.00 ms"),
                             text="A wall-clock latency threshold in an acceptance check failed twice in the sandbox."),
             "adopt", "lesson", "category:code",
             "Acceptance checks that assert wall-clock latency fail in the sandbox; assert on behaviour instead."),
            (MemoryCandidate(id="mc2", run_id=rid, source="user_choice", kind_hint="preference", scope_hint=proj,
                             evidence=ref("Fail open: serve traffic, log and alert"),
                             text="Asked about a limiter store outage, the user chose to fail open."),
             "provisional", "preference", proj,
             "When a protective dependency is down, the user prefers failing open with an alert."),
            (MemoryCandidate(id="mc3", run_id=rid, source="departure", kind_hint="precedent", scope_hint=proj,
                             related_entry_ids=["ce-0007"], evidence=ref("departs from the fixed-window precedent"),
                             text="The council chose a token bucket against the fixed-window precedent ce-0007."),
             "contest:ce-0007", "precedent", proj,
             "Rate limits in this project use a token bucket, not fixed-window counters."),
            (MemoryCandidate(id="mc4", run_id=rid, source="user_statement", kind_hint="preference",
                             scope_hint="global", evidence=ref(self.task[:80]),
                             text="The user asked for a rate limiter design in this run."),
             "reject", "preference", "global", "The user wants a rate limiter."),
        ]
        for i, (cand, *_rest) in enumerate(cands):
            self.e(t + 0.2 + 0.08 * i, ET.MEMORY_CANDIDATE, candidate=cand, index=i, total=len(cands))
        t += 0.7
        verdicts: dict[str, list[MemoryVerdict]] = {}
        for i, (cand, action, kind, scope, rewrite) in enumerate(cands):
            for j, s in enumerate(panel):
                dissent = (i == 1 and j == 2)  # one seat would reject the single user choice
                v = MemoryVerdict(
                    durable=action != "reject" and not dissent, kind=kind, scope=scope, statement_rewrite=rewrite,
                    action="reject" if dissent else action,
                    reason={"adopt": "Seen twice in this run with the same cause; it will recur.",
                            "provisional": "One explicit choice: a hint, not yet a rule.",
                            "contest:ce-0007": "It contradicts an active entry, so both must be contested.",
                            "reject": "Applies to this task only."}["reject" if dissent else action])
                verdicts.setdefault(cand.id, []).append(v)
                self.e(t + 0.42 * i + 0.13 * j, ET.MEMORY_VERDICT, candidate_id=cand.id, seat_no=s["seat_no"],
                       model_id=s["m"].id, verdict=v)
        t += 0.42 * len(cands) + 0.2
        now = _EPOCH + self.clock + t
        self.e(t, ET.MEMORY_COMMITTED, candidate_id="mc1", action="adopt", entry=ChronicleEntry(
            id="ce-0019", kind="lesson", scope="category:code", statement=cands[0][4], status="provisional",
            rationale="Panel 3 of 3. A review failure is capped at provisional by the rules of evidence.",
            evidence=cands[0][0].evidence, confidence=0.6, support_count=1, created_at=now,
            last_confirmed_at=now, votes=verdicts["mc1"]))
        self.e(t + 0.25, ET.MEMORY_COMMITTED, candidate_id="mc2", action="provisional", entry=ChronicleEntry(
            id="ce-0020", kind="preference", scope=proj, statement=cands[1][4], status="provisional",
            rationale="Panel 2 of 3. A single user choice is provisional and project-scoped.",
            evidence=cands[1][0].evidence, confidence=0.55, support_count=1, created_at=now,
            last_confirmed_at=now, votes=verdicts["mc2"]))
        old = self.record[0].model_copy(update={"status": "contested", "contradict_count": 1,
                                                 "votes": verdicts["mc3"]})
        self.e(t + 0.5, ET.MEMORY_CONTESTED, entry_id="ce-0007", entry=old, candidate_id="mc3",
               reason="This run's decision departs from it. A question for the user is queued.")
        gone = self.record[2].model_copy(update={"status": "retracted", "confidence": 0.28,
                                                  "contradict_count": 2})
        self.e(t + 0.75, ET.MEMORY_RETRACTED, entry_id="ce-0003", entry=gone, by="aging",
               reason="Not confirmed in 20 in-scope runs; confidence fell to 0.28. Evidence check ev1 also "
                      "found redis pinned in requirements.txt.")
        t = self.bench_and_probe(t + 1.0)
        t += 0.2
        self.to(t, RunState.DONE, "reflection done")
        self._pending_done = (t + 0.1, written, counts)

    def finish(self) -> None:
        """Emit run.completed last, after the telemetry state has seen every other event."""
        t, written, counts = self._pending_done
        self.flush()  # counters must include everything above
        total_ms = round(sum(self.phase_ms.values()), 1)
        payload = ET.make_payload(
            ET.RUN_COMPLETED, state=RunState.DONE, outcome="consensus", final_text=_CHAIR_TEXT,
            decision=self.decision, files_written=written, finished_at=round(_EPOCH + self.clock, 3),
            counters=self.counters(total_ms, rounds_run=4, review_cycles=1, tasks_total=len(self.the_plan.tasks),
                                   tasks_passed=counts.passed, tasks_failed=counts.failed,
                                   tasks_blocked=counts.blocked, tasks_skipped=counts.skipped))
        self.out.append((0.1, ET.RUN_COMPLETED, payload))


def demo_events(
    task: str,
    run_id: str,
    models: Optional[list[ModelEntry]] = None,
    seed: int = 0,
) -> list[tuple[float, str, dict]]:
    """The scripted run as (delay in seconds before emitting, event type, payload dict)."""
    s = _Script(task, run_id, models, seed)
    s.act_one()
    s.flush()
    s.out.append((0.2, WAIT_DELEGATE, {}))
    s.act_two()
    s.finish()
    return s.out


__all__ = ["demo_events", "WAIT_DELEGATE", "BUILTIN_MODELS"]
