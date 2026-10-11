"""Canned prose for mock mode. Demo topic: "Design a rate limiter for a public API".

Pure functions, deterministic per seed. No imports from the rest of the package.
"""

from __future__ import annotations

from typing import Optional

TOPIC = "Design a rate limiter for a public API"

_ANSWER = [
    "Use a token bucket keyed by API key, with a small burst allowance and a steady refill rate. It is cheap, easy to explain to customers, and tolerates real traffic spikes.",
    "Token bucket in Redis, one bucket per key, updated atomically with a Lua script. Return 429 with a Retry-After header when the bucket is empty.",
    "A sliding window counter gives the fairest limits. Keep two adjacent fixed windows and weight them by elapsed time; memory stays tiny and bursts at window edges disappear.",
    "Enforce limits at the gateway, not in each service. Per-key token buckets at the edge, plus a coarse per-IP limit for unauthenticated routes.",
    "Start with token bucket at 100 requests per minute and a burst of 20. Expose the remaining quota in response headers so clients can back off themselves.",
    "Layer it: a cheap in-process limiter absorbs obvious abuse, and a shared Redis token bucket makes the real decision. Fail open if Redis is unreachable.",
    "Token bucket per customer plan tier. Free gets 60 per minute, paid gets 600. Cost-weighted endpoints consume more than one token.",
    "Use token bucket for steady traffic and add a concurrency cap for expensive endpoints, since request counts alone do not protect slow queries.",
]
_SUMMARY = [
    "Per-key token bucket in Redis, enforced at the gateway, 429 plus Retry-After on rejection.",
    "Sliding window counters give smoother fairness but cost more state; token bucket wins on simplicity.",
    "The council leans toward token bucket with burst, plan-based tiers and fail-open behavior.",
    "Agreement on edge enforcement and shared state; disagreement on window algorithm and failure mode.",
    "Limiter design: identify caller, check bucket atomically, answer fast, tell the client how long to wait.",
    "Most views converge on a token bucket. The open question is what happens when the shared store is down.",
    "Keep the limiter off the hot path where possible and make every decision observable.",
    "Two viable designs, one clear favorite, and a short list of risks to test before launch.",
]
_TEXT = [
    "A rate limiter protects shared capacity. The choice of algorithm matters less than where it runs and how clearly it tells clients what to do next.",
    "Think of each API key as owning a bucket of tokens. Every request spends one, and time slowly refills the bucket.",
    "The hard part is not counting requests. It is counting them correctly across many servers without adding a slow network hop to every call.",
    "Clients behave better when limits are predictable. Publish the numbers, send headers on every response, and keep error bodies machine readable.",
    "Fixed windows are simple but let a client send double the limit across a boundary. That flaw is usually the reason teams move off them.",
    "Redis with a Lua script gives atomic read-modify-write in one round trip, which is enough for most public APIs.",
    "Abuse and accidents look the same at first. A good limiter slows both down and leaves room for the humans to notice.",
    "Observability is part of the design: log rejections by key and route, and alert on sudden changes in the rejection rate.",
]
_SUPPORT = [
    "Token bucket allows short bursts, which matches how real clients batch requests after an idle period.",
    "State per key is two numbers, tokens and last refill time, so memory stays small even with millions of keys.",
    "Large public APIs commonly use a variant of token bucket, so client developers already understand it.",
    "A single atomic script removes race conditions between concurrent requests for the same key.",
    "Sliding window counters avoid the boundary spike of fixed windows while staying far cheaper than a full request log.",
    "Edge enforcement rejects bad traffic before it consumes application resources.",
    "Retry-After and remaining-quota headers turn rejections into guidance instead of dead ends.",
    "Plan tiers map cleanly to bucket size and refill rate, so pricing and limits share one config.",
]
_STRONGEST_POINT = [
    "Bursts are normal. A limiter that punishes them will generate support tickets, not safety.",
    "Atomicity: the limit is only real if concurrent requests cannot both read the same count.",
    "The limiter must never become the outage. Its failure mode matters more than its algorithm.",
    "Clients need to be told how long to wait; a bare 429 invites retry storms.",
    "Per-key limits stop one tenant from starving the rest, which is the whole point of shared infrastructure.",
    "Memory per key is constant with token bucket, so cost does not grow with traffic.",
    "Enforcing at the edge keeps rejected traffic away from the services that are expensive to run.",
    "Sliding windows remove the boundary exploit that fixed windows leave open.",
]
_WOULD_CHANGE_MIND = [
    "Evidence that clients routinely hit boundary spikes would push me toward sliding window.",
    "If Redis latency exceeded a few milliseconds at the 99th percentile, I would move to local limits with periodic sync.",
    "A requirement for exact, auditable counts would make me prefer a request log over approximations.",
    "If most abuse comes from many IPs per key, per-key limits alone would not convince me.",
    "Data showing that burst allowance is being exploited would change my view on bucket size.",
    "A hard compliance need to fail closed would override the fail-open default.",
    "If the API is mostly long-running calls, I would switch the primary control to concurrency limits.",
    "Seeing the cost of the Lua script under load could change my mind about where state lives.",
]
_FINAL_ANSWER = [
    "Adopt a per-key token bucket in Redis, enforced at the gateway. Default 100 requests per minute with a burst of 20, tiered by plan. Reject with 429 and Retry-After, send quota headers on every response, and fail open with an alert if Redis is unreachable.",
    "Ship a token bucket limiter at the edge. Keys map to buckets in Redis updated by an atomic Lua script. Expensive endpoints cost more tokens. Add a per-IP floor for anonymous routes and dashboards for rejections by key and route.",
    "Use token bucket as the primary limiter, with a concurrency cap on slow endpoints. Publish limits in the docs, return structured 429 errors, and review the numbers after two weeks of real traffic.",
    "Go with token bucket per API key, tiered by plan, enforced at the gateway with shared Redis state. Keep a tiny local fallback so a store outage degrades gracefully instead of opening the floodgates.",
    "Recommend a token bucket per key with burst, atomic updates in Redis, standard rate-limit headers, and a fail-open policy guarded by alerts. Revisit sliding window only if boundary abuse shows up in the data.",
    "Build the limiter as a gateway plugin: identify the caller, run one atomic token bucket check, and answer with remaining quota. Start conservative, measure, then loosen.",
    "Token bucket wins on simplicity and client familiarity. Implement it per key and per plan, test failure modes explicitly, and keep the algorithm behind an interface so it can change later.",
    "Deploy per-key token buckets with burst, a modest per-IP cap, and clear client signals. Treat Redis outages as a first-class scenario with a tested fallback.",
]
_BLOCKING_OBJECTION = [
    "Failing open on a store outage could let a single client take the service down, and no one has quantified that risk.",
    "The plan has no answer for clock skew between gateway nodes, which breaks refill calculations.",
    "Without per-route costs, one cheap limit will not protect the expensive endpoints.",
]
_LESSON = [
    "Decide the failure mode of the limiter before choosing its algorithm.",
    "Publish limits early; clients tune to what they can see.",
    "Atomic updates beat clever algorithms every time.",
    "Burst allowance is a product decision, not just an engineering one.",
    "Measure rejection rate by key before changing any limit.",
    "Retry storms are a design problem, so send Retry-After and mean it.",
    "Keep the algorithm behind an interface; the first choice is rarely the last.",
    "Test the limiter under Redis latency, not just under Redis failure.",
]
_REASON = [
    "The argument rests on a claim about burst traffic that nobody measured.",
    "This option adds a network hop to every request, which the others avoid.",
    "The fail-open default is reasonable but the risk was waved away rather than analysed.",
    "Two proposals describe the same algorithm under different names, so they should be merged.",
    "The cost estimate ignores memory for idle keys, which can dominate at scale.",
    "It answers the question asked and names its own limits, which makes it easy to trust.",
    "The reasoning skips what happens when clocks drift between nodes.",
    "It is correct but generic; it would fit any API, not this one.",
]
_STATEMENT = [
    "Token bucket is the right default for a public API.",
    "Rate limits should be enforced at the gateway, not inside each service.",
    "Failing open is acceptable if the outage is loud and short.",
    "Sliding window counters are worth their extra cost for fairness.",
    "Clients should always be told how long to wait.",
    "A single shared Redis is a sufficient store for the first year.",
    "Per-IP limits alone are not enough to protect authenticated routes.",
    "Burst allowance should be configurable per plan tier.",
]
_STATEMENT_REWRITE = [
    "Token bucket is the right default for a public API, unless boundary abuse is observed.",
    "Enforce rate limits at the gateway so rejected traffic never reaches application services.",
    "Fail open when the store is unreachable, but page someone within a minute.",
    "Sliding window counters give fairer limits at modest extra cost, and are worth it for paid tiers.",
    "Every rejection should include a Retry-After value the client can trust.",
    "One shared Redis cluster is enough initially, provided the limiter degrades gracefully.",
    "Combine per-IP and per-key limits; neither alone covers both anonymous and authenticated traffic.",
    "Let plan tier set both bucket size and refill rate.",
]
_RATIONALE = [
    "Chosen because it balances simplicity, fairness and cost, and matches what client developers already expect.",
    "Ranked first since it handles bursts, uses constant memory per key, and has a well understood failure story.",
    "Ranked lower because the extra state buys little over the simpler option for this traffic profile.",
    "Kept as a fallback: it is easy to implement locally and needs no shared store.",
    "Preferred because the decision happens in one atomic step, which removes a whole class of race bugs.",
    "Rejected for now; the added complexity is not justified before there is real abuse data.",
    "Selected for clarity: the numbers can be explained to customers in one sentence.",
    "Scored well on cost and latency, less well on strict accuracy under heavy concurrency.",
]
_GOAL = [
    "Protect shared capacity from any single caller without hurting legitimate bursts.",
    "Give every API key a fair, predictable share of the service.",
    "Reject abusive traffic cheaply, before it reaches expensive services.",
    "Make limits visible to clients so they can adapt without support.",
    "Keep the limiter fast enough that its overhead is invisible at the 99th percentile.",
    "Survive a limiter store outage without taking the API down.",
    "Let pricing tiers translate directly into limits.",
    "Produce a design a small team can build and operate in two weeks.",
]
_TITLE = [
    "Token bucket per API key",
    "Sliding window counter at the edge",
    "Layered local and shared limiter",
    "Gateway-enforced tiered limits",
    "Cost-weighted token bucket",
    "Concurrency cap for slow endpoints",
    "Fail-open policy with alerting",
    "Rate limiter design review",
]
_NOTES = [
    "Check the Lua script under concurrent load before trusting the numbers.",
    "Remember to document the headers; clients cannot guess them.",
    "Redis latency budget is about two milliseconds per decision.",
    "Idle keys should expire so memory does not grow without bound.",
    "Open question: do webhooks count against the same bucket?",
    "Run a shadow mode first that logs would-be rejections without enforcing them.",
    "Burst of 20 came from sampling a week of production traffic.",
    "Keep the algorithm behind an interface for easy replacement.",
]
_FINAL_TEXT = [
    "Final recommendation: a per-key token bucket in Redis, enforced at the gateway. Limits scale with plan tier, expensive routes cost more tokens, and every response carries remaining-quota headers. Rejections return 429 with Retry-After. If Redis is unreachable the limiter fails open and raises an alert, and a small local bucket caps the worst case. Roll out in shadow mode for a week, then enforce.",
    "The council settled on token bucket. It is simple to explain, cheap to run, and tolerant of bursts. The main risk is the store outage case, handled by a local fallback and alerting. A sliding window variant remains an option if boundary abuse appears in the data.",
    "Build a gateway limiter with atomic Redis updates. Identify the caller by key, fall back to IP for anonymous traffic, and tier limits by plan. Publish the numbers, test failure modes, and review rejection metrics after two weeks.",
    "Design: token bucket per key, 100 per minute, burst 20; per-IP floor of 30 per minute for anonymous routes; concurrency cap of 10 on report endpoints. Observability from day one, with rejection dashboards and an alert on sudden jumps.",
    "Adopt the token bucket. Keep state minimal, update it atomically, and be generous with information to clients. The cleverness belongs in the monitoring, not the algorithm.",
    "Use a layered limiter: local first, shared second. This keeps latency low and degrades gracefully. Document the headers and the retry policy so client authors can build against them.",
    "The chosen design is conservative on purpose. It favors a well known algorithm, one clear failure mode, and numbers that can be tuned without a deploy.",
    "Ship the per-key token bucket, instrument it heavily, and plan one review after real traffic. Every other option stays on the table behind a small interface.",
]
_QUESTION = [
    "What happens to requests when the limiter store is unreachable?",
    "Should webhook deliveries count against the same quota as normal calls?",
    "Do you need exact counts, or are approximate limits acceptable?",
    "How should anonymous traffic be identified and limited?",
    "Are some endpoints much more expensive than others?",
    "Is there a contractual limit promised to paying customers?",
    "Should limits reset on a schedule or refill continuously?",
    "How many requests per second do you expect at peak?",
]
_STRONGEST_ARGUMENT = [
    "A limiter that fails closed turns a cache outage into a full API outage, so the failure mode must be open and loud.",
    "Token bucket is the algorithm clients already understand, which lowers support cost.",
    "Atomic single-round-trip updates make the limit actually hold under concurrency.",
    "Sliding window removes the doubling exploit at window boundaries at almost no extra cost.",
    "Edge enforcement saves more compute than any algorithm choice could.",
    "Cost-weighted tokens protect expensive routes without a second mechanism.",
    "Visibility through headers reduces both abuse and retries.",
    "Constant memory per key means the design scales with keys, not traffic.",
]
_APPROACH = [
    "Prototype the limiter as a gateway plugin, load test it, then tune the numbers from real traffic.",
    "Start with shadow mode: compute decisions, log them, enforce nothing, and compare with expectations.",
    "Implement the token bucket behind an interface, with a Redis backend and an in-memory test double.",
    "Write the Lua script first and test it with concurrent clients before building anything around it.",
    "Define the headers and error format first, then build the limiter to satisfy them.",
    "Roll out per tier: internal, then free, then paid, watching rejection rates at each step.",
    "Model expected traffic from logs and simulate both algorithms against it.",
    "Build the simplest working version, then add layers only where measurements demand them.",
]
_DESCRIPTION = [
    "A per-key token bucket held in Redis, checked atomically at the gateway on every request.",
    "A two-window sliding counter that weights the previous window by elapsed time.",
    "A small in-process bucket that absorbs obvious abuse before the shared check.",
    "Standard rate-limit headers and a structured 429 body with a Retry-After value.",
    "A concurrency cap that protects slow endpoints regardless of request count.",
    "A dashboard of rejections by key, route and plan, with an alert on sudden change.",
    "A tier table mapping plan names to bucket size and refill rate.",
    "A shadow mode that records decisions without enforcing them.",
]
_PROBLEM = [
    "Fixed windows let a client double its quota across a boundary.",
    "A store outage could either block everyone or let everyone through.",
    "A single limit treats a cheap read and an expensive report the same.",
    "Clients retry immediately after a rejection and make overload worse.",
    "Clock differences between nodes distort refill calculations.",
    "Anonymous traffic has no key, so the caller identity is weak.",
    "Idle keys accumulate state and quietly consume memory.",
    "Limits that no one can see produce confusing support tickets.",
]
_PROPOSED_CHANGE = [
    "Add a Retry-After header to every 429 response.",
    "Weight expensive endpoints so they consume several tokens per call.",
    "Run the limiter in shadow mode for one week before enforcing.",
    "Replace the fixed window with a sliding window counter for paid tiers.",
    "Add a small local fallback bucket for when Redis is unreachable.",
    "Expire idle bucket keys after an hour.",
    "Expose remaining quota in headers on every successful response too.",
    "Split the per-IP floor from the per-key limit in the config.",
]

_TEXT_FIELDS = {
    "answer": _ANSWER, "summary": _SUMMARY, "text": _TEXT, "support": _SUPPORT,
    "strongest_point": _STRONGEST_POINT, "would_change_mind": _WOULD_CHANGE_MIND,
    "final_answer": _FINAL_ANSWER, "lesson": _LESSON, "reason": _REASON,
    "statement": _STATEMENT, "statement_rewrite": _STATEMENT_REWRITE,
    "rationale": _RATIONALE, "goal": _GOAL, "title": _TITLE, "notes": _NOTES,
    "final_text": _FINAL_TEXT, "question": _QUESTION,
    "strongest_argument": _STRONGEST_ARGUMENT, "approach": _APPROACH,
    "description": _DESCRIPTION, "problem": _PROBLEM,
    "proposed_change": _PROPOSED_CHANGE,
}

ASSUMPTIONS = [
    "Traffic is dominated by authenticated clients with stable API keys.",
    "Redis is already part of the stack and is operated by the same team.",
    "Clients can tolerate a 429 response and honor Retry-After.",
    "Peak load is within one order of magnitude of current traffic.",
    "A few milliseconds of limiter latency per request is acceptable.",
    "Plan tiers already exist in the billing system.",
    "Gateway nodes have clocks synchronized within a few hundred milliseconds.",
    "Most abuse is accidental, such as loops in client code.",
]
RISKS = [
    "Redis outage causes the limiter to fail open or block everything.",
    "Hot keys concentrate load on a single Redis shard.",
    "Clock drift between gateway nodes skews refill timing.",
    "Retry storms after a wave of 429 responses amplify the overload.",
    "Burst allowance is too generous and is exploited.",
    "Limits are set too tight and break legitimate integrations.",
    "Memory grows without bound if idle keys never expire.",
    "Lua script becomes a bottleneck under heavy concurrency.",
]
USER_QUESTIONS = [
    "What is the expected peak request rate for a single customer?",
    "Should anonymous traffic be limited by IP address?",
    "Is failing open acceptable if the limiter store goes down?",
    "Do paid plans need different burst sizes as well as rates?",
    "Are there endpoints that should cost more than one token?",
    "Do webhooks share the same quota as regular calls?",
    "Do you need exact counts for billing, or only protection?",
    "Is there an existing gateway or proxy we must build on?",
]

_LISTS = {"assumptions": ASSUMPTIONS, "risks": RISKS, "user_questions": USER_QUESTIONS}


def text_for(field_name: str, seed: int) -> Optional[str]:
    """Return varied canned prose for a property name, or None if unknown.

    blocking_objection is mostly None: only about one seed in five yields text.
    """
    s = int(seed)
    if field_name == "blocking_objection":
        if s % 5 != 0:
            return None
        return _BLOCKING_OBJECTION[(s // 5) % len(_BLOCKING_OBJECTION)]
    pool = _TEXT_FIELDS.get(field_name)
    if pool is None:
        return None
    return pool[s % len(pool)]


def list_for(field_name: str, seed: int, n: int) -> list[str]:
    """Return n distinct strings (fewer if the pool is smaller) rotated by seed."""
    pool = _LISTS.get(field_name.lower())
    if pool is None or n <= 0:
        return []
    n = min(n, len(pool))
    start = int(seed) % len(pool)
    return [pool[(start + i) % len(pool)] for i in range(n)]


def answer_key_for(seed: int, split: bool) -> str:
    """'token-bucket' mostly; 'sliding-window' for about one seed in four when split."""
    if split and int(seed) % 4 == 3:
        return "sliding-window"
    return "token-bucket"
