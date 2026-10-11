# Research: engine

Read-only research on 2026-10-10. Nothing was run on the GX10. The re-check section overrides the findings where they differ.

## Summary
LangGraph has no blocker for this debate, so the owner's pick stands, but it covers only part of the engine. Pause, Stop, the wall-clock limit and the event log must be built in plain asyncio either way. Nothing was installed or run: the graph sketch is unexecuted, versions come from PyPI today, and the plan PDF was read as extracted text (wireframes not seen).

- **Versions (PyPI, 2026-10-10):** langgraph 1.2.14 (MIT, Python >=3.10), langgraph-checkpoint-sqlite 3.1.1, langchain-core 1.6.9, FastAPI 0.143.0, Starlette 1.7.0, uvicorn 0.54.0. Every compiled dependency I checked has cp312 Linux aarch64 and macOS arm64 wheels.
- **Offline:** LangSmith tracing is off unless an env var equals "true", and a scan of the LangGraph and langchain-core wheels found no telemetry. The one outbound call found is `draw_mermaid_png()`, which requests mermaid.ink by default.
- **Graph shape:** `Send` fan-out to seats, a conditional edge for the 80% loop, and a subgraph for the review all exist under current names. `max_concurrency` switches the same graph between all-at-once and one-speaker-at-a-time.
- **Model calls:** use plain httpx inside nodes with the custom stream writer. `ChatOpenAI` drops non-standard fields such as `reasoning_content`, and `messages` mode only works with LangChain chat models.
- **Pause, Stop, time limit:** `interrupt()` restarts its node on resume and cannot be triggered from outside; `RunControl.request_drain()` only stops between super-steps. Node timeouts discard the attempt's writes. One per-debate control object (pausable clock plus "cut the streams") should serve all three.
- **Checkpoints:** `AsyncSqliteSaver` resumes from the last completed super-step, so a restart loses in-flight turns but not finished rounds.
- **Event log:** storing every token delta is cheap, measured at 64-66 bytes per row (45,000 deltas = 2.9 MB). Token volumes per debate are assumptions until measured on the GX10.
- **council.md:** git CLI, dulwich 1.2.17 and pygit2 1.20.1 all work on aarch64. Make SQLite the source of truth and the file a rendered, committed artefact, because `git revert` of an old entry can conflict.

The largest unresolved design point is the plan's phrase "the engine checks which answers match": free-text one-sentence answers will rarely be identical, so the 80% rule needs an explicit ballot.

## Claims

### E1a [confirmed] (load-bearing)
LangGraph for Python is stable, permissively licensed and installable on both the arm64 GX10 and the dev Mac.

Evidence: PyPI today: langgraph 1.2.14 (uploaded 2026-10-06), MIT, requires-python >=3.10, pure-Python wheel, classifier Production/Stable. Compiled transitive dependencies checked (xxhash, ormsgpack, orjson, pydantic-core, uuid-utils 0.17.1, zstandard, jiter, PyYAML, sqlite-vec, websockets 16.1.1) all publish cp312 manylinux aarch64 and macOS arm64 wheels. Not installed or run on either machine.

For the build: Pin langgraph==1.2.14 and langgraph-checkpoint-sqlite==3.1.1 in a uv lock file with requires-python >=3.12, and smoke-test `uv sync` on the GX10 in the first engine spike. Releases are frequent (1.2.12 on 2026-09-21, 1.2.13 on 10-05, 1.2.14 on 10-06), so upgrade deliberately, never by floating ranges.

Sources: https://pypi.org/pypi/langgraph/json, https://raw.githubusercontent.com/langchain-ai/langgraph/main/libs/langgraph/pyproject.toml, https://pypi.org/pypi/uuid-utils/json, https://pypi.org/pypi/ormsgpack/json

### E1b [partly]
LangGraph can be used without pulling in LangChain.

Evidence: langgraph 1.2.14 hard-requires langchain-core>=1.4.7,<2, langgraph-checkpoint>=4.1.0,<5, langgraph-prebuilt>=1.1.0,<1.2, langgraph-sdk>=0.4.6,<0.5, pydantic>=2.7.4 and xxhash>=3.5.0. langchain-core 1.6.9 in turn requires langsmith>=0.3.45 (current 0.14.7), which requires requests, httpx2, zstandard, orjson and websockets>=15. No chat-model package (langchain, langchain-openai) is required.

For the build: Accept langchain-core and langsmith as installed-but-unused dependencies (roughly two dozen extra packages; an estimate from declared dependency lists, not a resolved count). Do not add `langchain` or `langchain-openai`.

Sources: https://pypi.org/pypi/langgraph/json, https://pypi.org/pypi/langchain-core/json, https://pypi.org/pypi/langsmith/json

### E1c [partly] (load-bearing)
Nothing in the LangGraph stack phones home by default, so the app stays offline.

Evidence: langsmith's `tracing_is_enabled()` returns true only when LANGSMITH_/LANGCHAIN_ `TRACING_V2` or `TRACING` equals "true" (default empty). A regex scan of the published wheels for langgraph 1.2.14, langgraph-checkpoint 4.2.0, langgraph-prebuilt 1.1.0, langgraph-checkpoint-sqlite 3.1.1, langgraph-sdk 0.4.6 and langchain-core 1.6.9 found no telemetry or analytics code. The exception is `draw_mermaid_png()`, whose default `MermaidDrawMethod.API` sends the graph to mermaid.ink; langsmith's optional OpenTelemetry export paths were not audited.

For the build: In the gateway's service environment set LANGSMITH_TRACING=false and LANGCHAIN_TRACING_V2=false and never set LANGSMITH_API_KEY. Never call `draw_mermaid_png()`; use `get_graph().draw_mermaid()` (text) if a picture of the flow is wanted. Add one automated test that runs a stub debate with non-local sockets blocked. Note FastAPI 0.143.0 now lists opentelemetry-api>=1.44.0 as a dependency (API only by design; its no-op behaviour was not checked today).

Sources: https://raw.githubusercontent.com/langchain-ai/langsmith-sdk/main/python/langsmith/utils.py, https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/core/langchain_core/tracers/context.py, https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/core/langchain_core/runnables/graph_mermaid.py, https://pypi.org/pypi/fastapi/json

### E2 [confirmed] (load-bearing)
The debate (fan-out to seats, a loop over rounds with an 80% check, a learning-review subgraph) maps directly onto today's LangGraph API.

Evidence: The docs' map-reduce example uses `add_conditional_edges(node, fn, [target])` returning `[Send(target, arg), ...]` followed by `add_edge(target, reducer_node)`, with `Annotated[list, operator.add]` to merge parallel results; loops are a conditional edge back to an earlier node. `max_concurrency` is a top-level config key backed by an asyncio semaphore in `pregel/_executor.py`, and the default recursion limit is 1000 super-steps since 1.0.6. Subgraphs are either added as a node (shared state keys) or invoked inside a wrapper node (different schemas), and by default inherit the parent's checkpointer.

For the build: Sketch (names checked against the 1.2.14 wheel and docs; NOT executed):

import operator
from dataclasses import dataclass
from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

@dataclass
class Ctx:            # runtime-only services, not checkpointed
    svc: Any          # llama clients, clock/control, inbox, search, tally

class Debate(TypedDict, total=False):
    question: str
    seats: list[dict]
    council_md: str
    round: int
    owner_notes: Annotated[list[dict], operator.add]
    turns: Annotated[list[dict], operator.add]
    tally: dict
    end_reason: str | None   # consensus | time | stop
    final: dict | None

async def prepare(state, runtime: Runtime[Ctx]):
    return {"council_md": await runtime.context.svc.read_council_md(), "round": 0}

async def open_round(state, runtime: Runtime[Ctx]):
    n = state["round"] + 1
    notes = await runtime.context.svc.drain_inbox(n)   # idempotent
    get_stream_writer()({"type": "round_start", "round": n})
    return {"round": n, "owner_notes": notes}

def fan_out(state):
    return [Send("seat_turn", {**state, "seat": s}) for s in state["seats"]]

async def seat_turn(arg, runtime: Runtime[Ctx]):
    turn = await runtime.context.svc.speak(arg, emit=get_stream_writer())
    return {"turns": [turn]}

async def tally(state, runtime: Runtime[Ctx]):
    t = await runtime.context.svc.tally(state)          # need = -(-4*n//5)
    reason = "consensus" if t["agreed"] else runtime.context.svc.end_reason()
    get_stream_writer()({"type": "vote", "round": state["round"], **t})
    return {"tally": t, "end_reason": reason}

def route(state):
    return "finalise" if state.get("end_reason") else "open_round"

async def finalise(state, runtime: Runtime[Ctx]):
    return {"final": await runtime.context.svc.write_final(state, emit=get_stream_writer())}

b = StateGraph(Debate, context_schema=Ctx)
for name, fn in [("prepare", prepare), ("open_round", open_round), ("seat_turn", seat_turn), ("tally", tally), ("finalise", finalise)]:
    b.add_node(name, fn)
b.add_edge(START, "prepare")
b.add_edge("prepare", "open_round")
b.add_conditional_edges("open_round", fan_out, ["seat_turn"])
b.add_edge("seat_turn", "tally")
b.add_conditional_edges("tally", route, ["open_round", "finalise"])
b.add_edge("finalise", END)

async with AsyncSqliteSaver.from_conn_string("data/checkpoints.sqlite") as saver:
    graph = b.compile(checkpointer=saver)
    cfg = {"configurable": {"thread_id": f"debate-{debate_id}"}, "max_concurrency": 7}
    async for part in graph.astream(inputs, cfg, context=Ctx(svc), stream_mode=["custom", "updates"], version="v2", durability="sync"):
        if part["type"] == "custom":
            await event_log.append(debate_id, part["data"])

Research is a first fan-out of the same shape before round 1. Keep routers pure functions of state (compute time-up and stop inside `tally`). Trim the Send payload to what a seat needs, since Send arguments are checkpointed. Add a hard max-rounds cap. `-(-4*n//5)` gives 3,4,4,5,6 for 3-7 seats, matching the plan's table.

Sources: https://docs.langchain.com/oss/python/langgraph/use-graph-api.md, https://docs.langchain.com/oss/python/langgraph/graph-api.md, https://docs.langchain.com/oss/python/langgraph/use-subgraphs.md, https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.14/libs/langgraph/langgraph/types.py

### E3a [confirmed] (load-bearing)
LangGraph can stream live output from several models to one consumer that forwards it over a single WebSocket.

Evidence: Stream modes are `values`, `updates`, `messages`, `custom`, `checkpoints`, `tasks`, `debug`; `version="v2"` (LangGraph 1.1+) makes every chunk a dict with `type`, `ns`, `data`. `get_stream_writer()` from `langgraph.config` emits arbitrary payloads received under `stream_mode="custom"`; in async code it needs Python 3.11+. LangGraph 1.2 also added `stream_events(version="v3")` with typed projections, which the docs recommend for new apps.

For the build: Each node emits small dicts through the stream writer with `seat`, `round` and `msg_id` in the payload. One pump task per debate consumes `astream(stream_mode=["custom","updates"], version="v2")` and hands every event to the event log, which assigns the sequence number and broadcasts. Skip `stream_events` v3 for now: it is five months old and adds nothing when events are already custom dicts.

Sources: https://docs.langchain.com/oss/python/langgraph/streaming.md, https://docs.langchain.com/oss/python/langgraph/event-streaming.md, https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.14/libs/langgraph/langgraph/pregel/main.py

### E3b [refuted] (load-bearing)
LangGraph's `messages` stream mode is the natural way to get token deltas from the seats.

Evidence: The streaming docs say `messages` mode works with LangChain chat models and recommend `stream_mode="custom"` with a raw client loop for any LLM without a LangChain integration. Chunks are identified by `langgraph_node` or model `tags`; with every seat running through one `seat_turn` node, telling seats apart would need per-model tags (an inference from the docs, not tested).

For the build: Do not use `messages` mode. Stream from llama-server with a raw HTTP client inside the node and emit through the custom writer, which also carries llama-server's `timings`, `prompt_progress` and reasoning text.

Sources: https://docs.langchain.com/oss/python/langgraph/streaming.md

### E4a [partly] (load-bearing)
LangGraph interrupts and resume provide the Pause button.

Evidence: `interrupt()` must be called from inside a node, needs a checkpointer and `thread_id`, and on `Command(resume=...)` the node restarts from its beginning; nothing lets an outside caller pause a node that is mid-generation. `RunControl.request_drain()` (langgraph>=1.2) stops a run only after the current super-step, raises `GraphDrained` with a resumable checkpoint, and the docs state it "does not cancel running asyncio tasks". Static `interrupt_before`/`interrupt_after` are described as debugging tools.

For the build: Build Pause in the gateway: freeze the clock, then either cut the in-flight streams and keep the partial text, or let the current turns finish. Hold seat nodes on an asyncio gate until Resume; LangGraph does not need to know. Use `request_drain()` only for gateway shutdown so a running debate checkpoints at a round boundary. Do not put `interrupt()` in seat nodes: parallel interrupts need a resume map by interrupt id and re-run the whole turn.

Sources: https://docs.langchain.com/oss/python/langgraph/interrupts.md, https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md, https://docs.langchain.com/oss/python/langgraph/graph-api.md

### E4b [confirmed] (load-bearing)
Cancelling an in-flight model call from the gateway makes llama-server actually stop generating.

Evidence: Earlier research (E9b, confirmed by its verifier) found llama-server wires connection-closed into `should_stop` and has no REST stop endpoint. httpcore's `_response_closed` closes the connection whenever the response is closed before both sides reach DONE, so leaving an httpx `client.stream(...)` block early drops the socket. The httpx2 client used by the openai SDK was not checked.

For the build: Run each seat's stream as an inner asyncio task registered with the debate's control object. Stop, Pause and time-up all call one `cut(reason)` that cancels those inner tasks; the inner task catches the cancellation, closes the stream and returns the partial text with a `cut` flag, so the node still returns normally and the checkpoint stays consistent. Earlier research notes cancellation is acted on between decode batches, so a cut during long prompt processing may lag.

Sources: https://raw.githubusercontent.com/encode/httpcore/master/httpcore/_async/http11.py, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md

### E4c [refuted] (load-bearing)
LangGraph provides the debate's wall-clock time limit, including a timer that freezes on Pause.

Evidence: LangGraph 1.2 has per-node-attempt timeouts only (`add_node(..., timeout=)`, `TimeoutPolicy(run_timeout, idle_timeout)`, `Send(..., timeout=)`), for async nodes. On expiry it raises `NodeTimeoutError` and "clears any writes from the failed attempt", which would discard the partial turn. There is no run-level pausable clock.

For the build: Write a small `DebateClock` in the gateway: budget in ms, active ms used, and a monotonic `running_since` that is cleared on Pause. Persist used time at each pause and round end and put it in graph state. One watchdog task calls `cut("time")` at expiry and the `tally` node sets `end_reason="time"`. Send the browser `remaining_ms` plus a running flag on changes and every few seconds; the browser counts down locally. Do not use LangGraph node timeouts for the debate limit.

Sources: https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md, https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.14/libs/langgraph/langgraph/types.py

### E4d [partly] (load-bearing)
A SQLite checkpointer lets a debate survive a gateway restart.

Evidence: `langgraph-checkpoint-sqlite` 3.1.1 (2026-07-30; requires aiosqlite>=0.20, langgraph-checkpoint>=4.1.0,<5, sqlite-vec>=0.1.6) provides `AsyncSqliteSaver` in `langgraph.checkpoint.sqlite.aio` with `from_conn_string`, WAL mode and `adelete_thread`. Checkpoints are written per super-step with per-node pending writes, durability is `"exit"`, `"async"` (default) or `"sync"`, and a run resumes with `None` input on the same `thread_id` without re-running nodes that finished. Resume is at super-step granularity, so turns that were mid-generation are regenerated, and the class docstring says it is not recommended for production workloads because of SQLite write performance.

For the build: Use `AsyncSqliteSaver` on its own file (for example `data/checkpoints.sqlite`), `durability="sync"`, thread id `debate-<id>`, and call `adelete_thread` once the debate is finished and its event log is complete. On gateway start, mark any debate left running as "interrupted" and let the owner choose Resume (re-spool models, restore the clock from persisted used time, `astream(None, cfg)`) or release the best answer so far. Keep state to plain dicts, lists, strings and numbers.

Sources: https://pypi.org/pypi/langgraph-checkpoint-sqlite/json, https://raw.githubusercontent.com/langchain-ai/langgraph/main/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/aio.py, https://docs.langchain.com/oss/python/langgraph/checkpointers.md, https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.14/libs/langgraph/langgraph/pregel/main.py

### E4e [partly] (load-bearing)
A message the owner types mid-debate can be injected into the running graph for the next round.

Evidence: LangGraph offers no input channel into a running graph: the graph API docs say `Command(resume=...)` is the only `Command` pattern intended as input, and it requires a prior `interrupt()`. Delivery at the next round therefore has to be done by a node reading from outside the graph (a design inference, not a documented feature).

For the build: Store owner messages in a `debate_inbox` table and log an `owner_message` event at once so the UI can show it as queued. The `open_round` node drains the inbox into state and stamps each row with the round it was delivered in, so a re-run of the node after a crash delivers the same rows again rather than losing or doubling them.

Sources: https://docs.langchain.com/oss/python/langgraph/graph-api.md, https://docs.langchain.com/oss/python/langgraph/interrupts.md

### E5a [refuted] (load-bearing)
langchain-openai's ChatOpenAI with a base_url is a good way to call llama-server from the graph.

Evidence: The langchain-openai source states ChatOpenAI "targets official OpenAI API specifications only. Non-standard response fields added by third-party providers (e.g., `reasoning_content`, `reasoning_details`) are **not** extracted or preserved". llama-server returns reasoning in `reasoning_content` and adds `timings` and `prompt_progress`, which this app wants. langchain-openai 1.7.0 would also add openai>=2.45.0 (current 3.28.0, built on httpx2) and tiktoken.

For the build: Call each seat's `/v1/chat/completions` with httpx (`AsyncClient.stream`) from one small `llama_client.py` shared by plain chat (phase 2) and the debate nodes. Send `stream: true`, `timings_per_token: true`, `return_progress: true` (earlier research A7a) and tolerate SSE comment pings.

Sources: https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/partners/openai/langchain_openai/chat_models/base.py, https://pypi.org/pypi/langchain-openai/json, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md

### E5b [confirmed] (load-bearing)
llama-server supports structured output and tool calls through its OpenAI-compatible endpoint.

Evidence: `server-common.cpp` on master reads `response_format` of type `json_object` (optional `schema`) and `json_schema` (schema at `response_format.json_schema.schema`) and turns it into a grammar; the README also documents `json_schema` and `grammar` request fields. Tool calls need the Jinja engine (`--jinja, --no-jinja`, listed as default enabled on master), use native handlers for recognised templates and a "Generic" fallback otherwise, and `parallel_tool_calls` is off by default. The version installed on the GX10 is unknown, so none of this is confirmed for that build.

For the build: Use schema-constrained JSON (`response_format` with `json_schema`) for the one-sentence answer, the ballot, search queries and the review vote, because grammar constraints work with any model. Treat model-driven tool calling as optional and per-model. Test constrained output together with reasoning-enabled models on the GX10's build before relying on it.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/server-common.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/docs/function-calling.md

### E5c [refuted]
LangChain's model layer is needed to run the debate on LangGraph.

Evidence: The LangGraph streaming docs show nodes looping over a raw client's stream and emitting via the stream writer, with no LangChain chat model. Only langchain-core is required, as a transitive dependency of langgraph.

For the build: Keep prompts as plain lists of role/content dicts and state as plain dicts; do not use `add_messages`, `MessagesState` or prebuilt agents.

Sources: https://docs.langchain.com/oss/python/langgraph/streaming.md, https://pypi.org/pypi/langgraph/json

### E6 [partly] (load-bearing)
LangGraph is a better fit than a few hundred lines of plain asyncio for this bounded debate loop.

Evidence: No blocker was found. LangGraph supplies per-round checkpoints with resume, a named node-and-edge structure that can be drawn, a fan-out switchable by `max_concurrency`, and a reusable subgraph. It does not supply Pause mid-generation, Stop, the pausable clock, the event log or the llama-server client (claims E3b, E4a, E4c, E5a). The size comparison is a judgment, not a measurement.

For the build: Keep LangGraph, used thinly: one graph file of wiring (about 150 lines, an estimate) whose nodes call plain Python modules for prompts, tally, clock, control and the llama client. That keeps the option of replacing the wiring with an asyncio loop without touching the rest. Costs to manage: about two dozen extra packages, fast release cadence, node re-execution on resume (side effects must be idempotent), and coding agents writing pre-1.1 idioms. Put a short "LangGraph idioms we use" note in the repo listing the exact imports and call shapes from claim E2.

Sources: https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md, https://docs.langchain.com/oss/python/langgraph/interrupts.md, https://docs.langchain.com/oss/python/langgraph/streaming.md, https://pypi.org/pypi/langgraph/json

### E7a [confirmed] (load-bearing)
An append-only, sequence-numbered event log per debate is an established pattern that can serve live views, reconnect and replay from one table.

Evidence: The HTML standard's server-sent events define reconnect by sending the last seen event id in a `Last-Event-ID` header, the same "everything after N" idea. LangGraph's own protocol events carry `seq`, documented as "strictly increasing within a run; use for ordering", with a separate wall-clock timestamp that "can drift".

For the build: Make the event log the only path to the browser: a single writer per debate assigns `seq`, commits, then broadcasts. On connect the client sends its last `seq`; the server subscribes it first, sends rows with a higher `seq` from SQLite, then live events, dropping any already sent. Replay reads the same rows and schedules them by active-time offset.

Sources: https://html.spec.whatwg.org/multipage/server-sent-events.html, https://docs.langchain.com/oss/python/langgraph/event-streaming.md

### E7b [refuted]
Storing every token delta would make a debate's log too large, so only completed messages should be kept.

Evidence: Measured in an in-memory SQLite 3.53.1 rowid table with `UNIQUE(debate_id, seq)` and synthetic 4-character deltas: 45,000 rows took 2.90 MB and 90,000 rows 5.97 MB (64-66 bytes per row); deltas batched to about 40 characters cost about 100 bytes per row. A `WITHOUT ROWID` version stored 60 messages of 1.5 KB in 287 KB against 135 KB, consistent with SQLite's advice to keep such rows under about 1/20 of a page. How many tokens a debate produces is unknown; 45,000 assumes a combined 150 tokens/s for 5 minutes.

For the build: Store deltas, coalesced per seat into one row per flush of about 100 ms, plus a `message_complete` row holding the full text. Flush each batch in one transaction. Use an ordinary rowid table. Size is not the constraint; write frequency and duplicate rows from re-run nodes are.

Sources: https://www.sqlite.org/withoutrowid.html

### E8a [confirmed]
Python can commit council.md to a git repository on the arm64 GX10 using the git command, dulwich or pygit2.

Evidence: dulwich 1.2.17 (Apache-2.0 OR GPL-2.0-or-later, Python >=3.10) ships cp312 manylinux_2_28_aarch64, macOS arm64 and pure-Python wheels and has `porcelain.init`, `add`, `commit`, `log` and `revert`. pygit2 1.20.1 (GPLv2 with linking exception, Python >=3.11, cffi>=2.0) ships cp312 manylinux aarch64 and macOS arm64 wheels. GitPython 3.2.0 only wraps the git command. Whether git is installed on the GX10 was not checked.

For the build: Wrap the git command in one small class (`init`, `commit_file`, `log`, `show`), run it through `asyncio.to_thread`, and pass the identity explicitly (`-c user.name=... -c user.email=...`) so commits work on a fresh machine. Fall back to dulwich if the owner prefers no system package. Write order: take a lock, render, check the budget, write a temp file in the same folder, fsync, `os.replace`, `git add`, `git commit`, then record the commit id in SQLite. On startup, if the working copy is dirty, restore HEAD and re-render.

Sources: https://pypi.org/pypi/dulwich/json, https://raw.githubusercontent.com/jelmer/dulwich/main/dulwich/porcelain/__init__.py, https://pypi.org/pypi/pygit2/json, https://pypi.org/pypi/GitPython/json

### E8b [partly] (load-bearing)
Because every change is a commit, any single entry can be rolled back with git revert.

Evidence: Both git and dulwich (`porcelain.revert`) can revert a commit, but a revert undoes a whole commit and can conflict when later commits changed neighbouring lines, which is the normal case for adjacent list entries (general git behaviour; not tested here). The plan also keeps per-entry data the file does not need to carry (waiting and rejected lists, pins, use counts).

For the build: Make SQLite the source of truth (`council_entries` plus `council_entry_versions`) and council.md a rendered file. Rollback, edit, pin and retire are new changes that re-render and add a forward commit with the reason; never rewrite history. Keep the "used N times" counter out of the committed file, or every debate produces a commit. Read the file once at debate start and keep the text and commit id in debate state; `os.replace` means a reader sees the old or the new file, never half of one.

Sources: https://raw.githubusercontent.com/jelmer/dulwich/main/dulwich/porcelain/__init__.py

### E8c [partly]
The roughly 2,000-token budget for council.md can be checked with a single token count.

Evidence: Seats run different models with different tokenisers, so one count does not hold for all. Earlier research (E5a and its verifier) found llama-server's `/tokenize` is answered directly from the vocabulary in the HTTP handler rather than the task queue, so it can be called per model while generation is running.

For the build: Count the rendered file with each loaded seat's `/tokenize` and enforce the budget on the largest count; cache counts by model and commit id. Leave a margin (for example enforce 1,800 against 2,000; the margin is a guess) for models seated later. Place council.md at the very start of every seat's system prompt so the prefix is reused from the prompt cache across rounds.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md

### E9a [confirmed]
FastAPI, Starlette and uvicorn are current and compatible with the LangGraph dependency set.

Evidence: PyPI today: fastapi 0.143.0 (2026-10-08, requires starlette>=0.46.0 and now opentelemetry-api>=1.44.0), starlette 1.7.0 (2026-09-23), uvicorn 0.54.0 (2026-09-25), all Python >=3.10. websockets is at 17.2 but langgraph-sdk 0.4.6 requires `websockets<17,>=14`, so a resolver will pick 16.1.1, which has a cp312 aarch64 wheel; uvicorn[standard] asks for websockets>=13.0. The combination was not resolved or installed here.

For the build: Declare fastapi, uvicorn and websockets without pinning websockets to 17; let uv resolve and commit the lock file. Run one uvicorn process with one worker (earlier research E9c) so the debate registry and the broadcast hub are shared.

Sources: https://pypi.org/pypi/fastapi/json, https://pypi.org/pypi/starlette/json, https://pypi.org/pypi/uvicorn/json, https://pypi.org/pypi/langgraph-sdk/json, https://pypi.org/pypi/websockets/json

### E9b [partly]
WebSocket connections are kept alive and dead ones are detected without extra work.

Evidence: uvicorn's config defaults are `ws_ping_interval=20.0`, `ws_ping_timeout=20.0`, `ws_max_size` 16 MiB and `ws_max_queue=32`; with `websockets` installed, `ws="auto"` selects the sans-IO implementation, which reads those ping settings (read on uvicorn main, not the 0.54.0 tag). That covers the server side; page JavaScript cannot see protocol pings, so the browser needs its own staleness check.

For the build: Keep uvicorn's ping defaults. Send an application-level timer event every few seconds during a debate; the client reconnects with backoff and its last `seq` when nothing arrives for about 15 s. Give each socket its own bounded queue and sender task, and close a socket whose queue overflows so a sleeping tab cannot stall the others.

Sources: https://raw.githubusercontent.com/Kludex/uvicorn/main/uvicorn/config.py, https://raw.githubusercontent.com/Kludex/uvicorn/main/uvicorn/protocols/websockets/auto.py, https://raw.githubusercontent.com/Kludex/uvicorn/main/uvicorn/protocols/websockets/websockets_sansio_impl.py

### E9c [partly] (load-bearing)
A debate keeps running when every browser tab disconnects, and several tabs can watch the same debate.

Evidence: This holds only by design: FastAPI's docs (earlier research E9c) show the in-memory connection manager works only within a single process, and a coroutine started inside a WebSocket handler ends with that connection. Nothing in FastAPI or LangGraph keeps a run alive on its own.

For the build: Start each debate as its own asyncio task held in a registry (strong reference), never inside a WebSocket handler. Sockets are only subscribers to the event log. With no viewers the debate runs to its limit and the answer lands in history; whether it should pause instead is the owner's call.

Sources: https://fastapi.tiangolo.com/advanced/websockets/

## Recommendations
- **Debate engine library and how much of it to use**: langgraph==1.2.14 with only: `StateGraph`, `START`/`END`, `Send`, `add_conditional_edges`, `context_schema` + `Runtime`, `get_stream_writer`, `AsyncSqliteSaver`, and `RunControl` for shutdown. One graph file of wiring; all real logic in plain Python modules the nodes call. _Why:_ No blocker was found and the owner chose it. It adds per-round checkpoints, a drawable structure and a one-key switch between parallel and one-at-a-time seats. Keeping it thin limits exposure to its fast release cadence and leaves an exit to plain asyncio.
- **How nodes call llama-server**: httpx 0.28.1 `AsyncClient.stream("POST", f"{base}/v1/chat/completions", json=...)` in one shared `llama_client.py`; schema-constrained JSON via `response_format: {"type":"json_schema","json_schema":{"name":...,"schema":...}}`. _Why:_ ChatOpenAI states it does not preserve non-standard fields such as `reasoning_content`, and this app also wants `timings` and `prompt_progress`. httpx is already installed as a langchain-core dependency, and its early-close behaviour was checked in httpcore source.
- **Live streaming path from graph to browser**: `graph.astream(..., stream_mode=["custom","updates"], version="v2", durability="sync")` consumed by one pump task per debate, which appends to the event log; the log broadcasts one envelope `{seq, t_ms, type, seat, round, msg_id, payload}` on the single WebSocket. _Why:_ Custom mode works with any HTTP client and lets the payload name the seat. A single consumer gives a single writer for sequence numbers.
- **Pause, Stop and the time limit**: One `DebateControl` per debate in the gateway: a pausable `DebateClock` (active ms used, persisted) and `cut(reason)` that cancels the registered inner stream tasks so seat nodes return partial text. Stop and time-up set `end_reason` for the `tally` node to route to `finalise`. Pause freezes the clock and holds nodes on an asyncio gate. `RunControl.request_drain()` is used only on gateway shutdown. _Why:_ LangGraph cannot pause a running node from outside, its drain only acts between super-steps, and its node timeouts discard the partial turn. One cut mechanism serves all three features and keeps the graph's state and checkpoints consistent.
- **Durable checkpoints**: langgraph-checkpoint-sqlite==3.1.1, `AsyncSqliteSaver.from_conn_string("data/checkpoints.sqlite")` opened in the FastAPI lifespan, `durability="sync"`, thread id `debate-<id>`, `adelete_thread` when the debate is finished. After a restart, show the debate as interrupted with Resume or Release best answer. _Why:_ It gives resume from the last finished round for little code. A separate file avoids lock contention with the app database and can be deleted safely. Sync durability costs little at about three super-steps per round.
- **How "the engine checks which answers match"**: An explicit ballot each round: collect every seat's one-sentence answer, have the small model merge them into K distinct numbered candidates, then ask every seat for `{"vote": k}` under a JSON schema with an enum of 1..K. Count votes with `need = -(-4*n//5)`. _Why:_ Free-text answers from different models will rarely be identical, so matching needs a rule. A constrained ballot makes each seat explicitly back one answer, as the plan words it, and counting becomes arithmetic. The extra call is short and reuses each seat's cached context.
- **How agents research files**: Engine-driven retrieval for the first version: each seat returns `{"queries": [...]}` under a JSON schema, the engine runs the SQLite search and injects passages with file and page ids; the seat cites by id. _Why:_ Grammar-constrained JSON works with any GGUF model, while tool-call quality depends on each model's chat template (native handler or generic fallback).
- **Parallel or one-at-a-time seats**: Keep the single `Send` fan-out graph and set `max_concurrency` in the run config: N for all seats at once, 1 for one speaker at a time. Decide after a GX10 benchmark. _Why:_ The plan's Table View implies a visible speaker, and several llama-server processes share one GPU with unknown combined throughput. A config key avoids committing the graph shape before measuring.
- **Event log storage**: Table `debate_events(id INTEGER PRIMARY KEY, debate_id INTEGER NOT NULL, seq INTEGER NOT NULL, t_ms INTEGER NOT NULL, wall_ms INTEGER NOT NULL, type TEXT NOT NULL, seat INTEGER, round INTEGER, msg_id TEXT, payload TEXT NOT NULL, UNIQUE(debate_id, seq))` in WAL mode. Types: seat_ready, delta, message_complete, bubble, vote, round_start, round_end, owner_message, paused, resumed, timer, final, error. Deltas coalesced per seat per ~100 ms flush; `message_complete` carries the full text; a separate `debate_messages` table feeds history and search. `msg_id` includes the attempt number. _Why:_ Measured cost is 64-100 bytes per row, so even per-token storage is a few MB per debate. One row per broadcast frame makes reconnect and replay the same query. Bubble rows let replay show the original summaries without re-running the small model.
- **WebSocket fan-out and keep-alive**: One uvicorn process, one worker, default ping 20 s / timeout 20 s. One socket per tab; client opens with `{debate_id, after_seq}`. Per-socket bounded `asyncio.Queue` and sender task; overflow closes that socket. A timer event every few seconds doubles as the heartbeat. _Why:_ The in-memory hub and debate registry need a single process. Per-socket queues stop a sleeping Mac or background tab from stalling the pump.
- **council.md storage and commits**: SQLite entries as the source of truth; render council.md; atomic temp-file write and `os.replace`; commit with the git command (explicit identity, via `asyncio.to_thread`); rollback and retire as forward commits; snapshot text and commit id at debate start; count tokens with each seat's `/tokenize` and enforce on the largest. _Why:_ The plan's Council file screen needs data the file should not carry, and reverting old commits can conflict. The git command adds no Python dependency and is the form coding agents know best.
- **Learning review placement**: Compile the review as its own graph and run it as its own thread (`review-<id>`) after the answer is released and whenever later feedback creates a candidate; share the ballot fan-out with the debate graph as a subgraph. _Why:_ The plan's candidates include corrections made after the owner reads the answer, so the review cannot only be a tail node of the debate. A separate run also lets the debate finish cleanly and lets a new question cancel a review.
- **Guaranteeing offline operation**: Service environment: `LANGSMITH_TRACING=false`, `LANGCHAIN_TRACING_V2=false`, no `LANGSMITH_API_KEY`. Never call `draw_mermaid_png()`. One test that runs a stub debate with non-local sockets blocked. _Why:_ Tracing is off by default but an inherited shell variable could turn it on, and the mermaid PNG helper posts the graph to mermaid.ink by default.

## Risks
- The consensus rule is underspecified: the plan says the engine "checks which answers match", but one-sentence answers from different models will rarely be identical. Without an explicit ballot, debates will end in false "No consensus" or false agreement.
- The time limit may not fit the hardware: combined tokens per second with 3-7 llama-server processes on one GPU is unknown, so a 2-minute debate may allow only one or two rounds. Writing the final answer and dissent notes also takes model time after the limit unless a reserve is held back.
- LangGraph re-runs nodes on resume and retry. Any node that writes to the event log, drains the owner inbox or commits council.md will do it twice unless writes are idempotent (attempt numbers in `msg_id`, delivered-round stamps, side effects in their own nodes).
- Pause mid-generation is hand-built. Continuing a cut turn relies on llama-server's assistant prefill (`--prefill-assistant`, default on per the README) and the prompt cache, and behaviour with reasoning models and each chat template is untested. The fallback is letting current turns finish while the clock is frozen.
- Coding agents will write stale LangGraph code. Version 1.1 (2026-03-10) added the v2 stream format and 1.2 (2026-05-12) added node timeouts, error handlers, `RunControl` and `stream_events` v3; `config_schema` and `checkpoint_during` are deprecated. The docs and main branch also run ahead of PyPI (main requires langgraph-checkpoint>=4.3.0 while PyPI has 4.2.0), so read source at the pinned tag.
- All pins are days old and untested on either machine: langgraph 1.2.14 (10-06), langchain-core 1.6.9 (10-08), langsmith 0.14.7 (10-09), fastapi 0.143.0 (10-08). Lock the set that passes a smoke test rather than the newest.
- If someone later swaps the httpx client for ChatOpenAI to "simplify", reasoning text, timings and prompt progress disappear silently.
- Offline leaks: `draw_mermaid_png()` calls mermaid.ink by default, and a `LANGSMITH_TRACING=true` inherited from a shell profile would start sending traces. langsmith's OpenTelemetry export paths were not audited, and FastAPI now installs opentelemetry-api.
- Asyncio pitfalls: a debate started inside a WebSocket handler dies when the tab closes; tasks without a strong reference can be garbage-collected; blocking calls (`subprocess.run` for git, synchronous SQLite) inside the event loop freeze every seat's stream.
- A slow or sleeping tab can stall the whole broadcast if sends are awaited inline; each socket needs its own bounded queue.
- Checkpoint growth: LangGraph writes the full state at every super-step, and Send arguments are checkpointed too. Passing the whole transcript in each Send and never deleting threads will bloat the checkpoint file.
- council.md pitfalls: `git revert` conflicts on adjacent entries; a "used N times" counter in the file makes every debate a commit; `git commit` fails on a machine with no git identity; edits made outside the app diverge from the database.
- Two seats sharing one model share one llama-server. They need two slots (`-np 2`) or their turns run one after the other, and the memory meter must count the second slot's context.
- The durability default and several source facts were read on the main branch (labelled 1.2.14) rather than only the release tag; uvicorn settings were read on main rather than the 0.54.0 tag.

## Open questions
- GX10 test: combined tokens per second with N llama-server processes generating at once versus one at a time, for the owner's likely councils. This decides `max_concurrency`, per-turn token caps and how many rounds fit in 2, 5 and 10 minutes.
- GX10 test: which llama.cpp build is installed, and does it accept `response_format` with `json_schema`, enable Jinja by default, continue a prefilled assistant message, and combine constrained JSON with reasoning-enabled models?
- GX10 test: is git installed (`git --version`), and does `uv sync` of the locked set succeed on DGX OS?
- Owner: does the timer start when the models are ready or when the question is sent, and does it include writing the final answer?
- Owner: when Pause is pressed, should text being generated stop at once and continue later, or may the current turns finish while the clock is frozen?
- Owner: after Stop, is a wait of roughly 10-30 seconds (an estimate) for a written final answer acceptable, or should the leading group's latest statement be released instantly?
- Owner: is an explicit vote on numbered candidate answers an acceptable reading of "the engine checks which answers match", and may the small summary model merge the candidates?
- Owner: should seats speak one at a time (later speakers can answer earlier ones in the same round, one clear speaker in Table View) or all at once (faster rounds, replies only to the previous round)?
- Owner: should a debate keep running when no browser is watching (assumed yes), and after a gateway restart should an interrupted debate wait for a Resume click (assumed) or resume by itself?
- Owner: should models' reasoning text be shown, stored and summarised in bubbles, or only their final messages? It roughly doubles log volume for reasoning models (an estimate).
- Owner: may the learning review keep the council busy after an answer, and should a new question cancel or queue a running review?
- Owner: should "used N times" appear inside council.md, as the plan's example shows, or only on the Council file screen?
- Not checked: whether the httpx2 client closes the connection when a stream is abandoned early, and whether langsmith's OpenTelemetry paths stay silent with tracing disabled.

## Independent re-check (overrides the above)

- **E1a** [confirmed] 
- **E1b** [partly] The dependency list is right but incomplete and the count is low. langchain-core 1.6.9 also directly requires httpx<1, langchain-protocol>=0.0.17, jsonpatch, tenacity, PyYAML, packaging and uuid-utils<1.0 (so uuid-utils 1.0.0 is excluded and 0.17.1 resolves). My walk of PyPI metadata for linux aarch64 / Python 3.12 gives 41 packages for langgraph + langgraph-checkpoint-sqlite, about 29 of them beyond what fastapi + uvicorn + httpx + aiosqlite already need (approximate marker evaluation, not a uv resolve). Two HTTP client stacks end up installed: httpx 0.28.1/httpcore 1.0.9 and httpx2 2.13.1/httpcore2.
- **E1c** [partly] The recommended pair of variables leaves a hole. In the langsmith 0.14.7 wheel, get_env_var returns the first non-empty of LANGSMITH_TRACING_V2, LANGCHAIN_TRACING_V2, then LANGSMITH_TRACING, LANGCHAIN_TRACING, and tracing is on only when that value == "true". An inherited LANGSMITH_TRACING_V2=true would beat LANGSMITH_TRACING=false and LANGCHAIN_TRACING_V2=false; set LANGSMITH_TRACING_V2=false (or all four). My own scan of the langgraph 1.2.14, langgraph-checkpoint 4.2.0, langgraph-prebuilt 1.1.0, langgraph-checkpoint-sqlite 3.1.1, langgraph-sdk 0.4.6, langchain-core 1.6.9 and langchain-protocol 0.0.19 wheels also found no telemetry code; draw_mermaid_png defaults to MermaidDrawMethod.API (mermaid.ink).
- **E2** [confirmed] One number is wrong at source level: the docs say the default recursion limit is 1000 since 1.0.6, but langgraph/_internal/_config.py has DEFAULT_RECURSION_LIMIT = int(getenv("LANGGRAPH_DEFAULT_RECURSION_LIMIT", "10007")) at tag 1.2.14 ("10000" at 1.0.6 and 1.1.0, "25" at 1.0.5). Either way it will not bound the loop, so the hard max-rounds cap is required. Every import and call shape in the sketch exists in the 1.2.14 source (StateGraph(context_schema=), Runtime, Send, get_stream_writer, astream(context=, version="v2", durability=), max_concurrency semaphore); not executed by me either. Caveats from the docs that the sketch does not show: a super-step is transactional (one seat raising discards the round's updates and siblings are cancelled), parallel updates are not ordered consistently, and seats in one fan-out cannot see each other's same-round output.
- **E3a** [confirmed] 
- **E3b** [refuted] Refuted as a choice, not as a capability: messages mode would work if seats were called through a LangChain chat model such as ChatOpenAI with per-seat tags, but that path is rejected in E5a, and the docs point non-LangChain clients to custom mode.
- **E4a** [partly] 
- **E4b** [confirmed] 
- **E4c** [refuted] 
- **E4d** [partly] Facts hold against the published 3.1.1 wheel (docstring warning, from_conn_string, PRAGMA journal_mode=WAL, adelete_thread). Sourcing note: the main-branch pyproject still says version 3.1.1 but already requires langgraph-checkpoint>=4.3.0, while PyPI 3.1.1 requires >=4.1.0 and the newest langgraph-checkpoint on PyPI is 4.2.0, so main has unreleased changes; read the wheel, not main. sqlite-vec is a declared dependency but aio.py never imports it (only the store modules do), and the 0.1.9 aarch64 wheel's vec0.so is a 64-bit AArch64 ELF.
- **E4e** [partly] 
- **E5a** [refuted] 
- **E5b** [confirmed] Two details. (1) parallel_tool_calls is not unconditionally off: server-common.cpp on master reads json_value(body, "parallel_tool_calls", caps["supports_parallel_tool_calls"]), so the default follows the chat template's capability, although docs/function-calling.md says disabled by default. (2) The README's example for type json_schema puts the schema at response_format.schema, but the source reads only response_format.json_schema.schema; the README form yields an empty schema that is then widened to {"type":"object"}, i.e. silently unconstrained. Use the OpenAI form the original recommends. All of this is master; the GX10 build is unknown.
- **E5c** [refuted] 
- **E6** [partly] No blocker found by me either. Two costs are understated: the extra packages are about 29, not two dozen (my metadata walk, approximate), and the planned event log already stores every completed message durably, so the LangGraph checkpoint file is a second durable record that must be reconciled with it on resume (resume is per super-step, the log is per message).
- **E7a** [confirmed] 
- **E7b** [refuted] Reproduced on the dev Mac (Python 3.12.14, SQLite 3.53.1, in-memory) with the recommended full debate_events schema: 45,000 four-character delta rows = 3.12 MB (69 bytes/row), 90,000 = 6.38 MB (71 bytes/row), 40-character batches = 105 bytes/row; the original's 2.90/5.97 MB and 64-66 bytes are about 7% lower, a payload-shape difference. WITHOUT ROWID matched exactly: 286.7 KB against 135.2 KB for 60 rows of 1.5 KB. These are in-memory sizes that exclude the WAL file, measured on the Mac not the GX10, and the 45,000-row figure rests on an assumed 150 tokens/s, not a measurement.
- **E8b** [partly] No change. dulwich main does define porcelain.revert; the adjacent-line conflict behaviour of reverting an older commit remains untested in both passes (it needs a scratch repository, which this read-only pass could not create).
- **E8c** [partly] 
- **E9b** [partly] The defaults (ws_ping_interval 20.0, ws_ping_timeout 20.0, ws_max_size 16 MiB, ws_max_queue 32) and the sans-IO selection are identical at tag 0.54.0, not only on main. Missing caveat: uvicorn 0.54.0 does not depend on websockets (only the uvicorn[standard] extra does, websockets>=13.0). In this stack it arrives only transitively via langsmith (>=15) and langgraph-sdk (>=14,<17, so 16.1.1 while 17.2 is current). Without it uvicorn has no WebSocket protocol, so declare websockets explicitly.
- **E9c** [partly] The conclusion is right; the mechanism is slightly different. A handler is not cancelled when the browser leaves: code awaited inside it keeps running until its next send or receive, where Starlette 1.7.0 raises WebSocketDisconnect(1006) or WebSocketDisconnected, which would kill a debate run inline. Separately, asyncio keeps only weak references to tasks ("Save a reference to the result of this function"), which is why the registry must hold the task.

### Objections to recommendations
- Parallel or one-at-a-time seats: max_concurrency=1 only serialises execution. All Send tasks of a round are one super-step, so no seat sees another seat's same-round text and the docs say parallel updates 'may not be ordered consistently'. If the owner wants a visible speaker whose words the next seat answers by name in the same round, the graph needs a seat-index loop (one super-step per seat), which is a different shape, not a config key. That shape also gives a checkpoint and a drain point after every seat instead of every round.
- Debate engine: seat_turn must never raise. The docs state a super-step is transactional (any branch raising means none of the round's updates are applied) and the runner cancels sibling tasks. One llama-server dying under memory pressure on the GX10's unified memory would otherwise throw away every other seat's turn in that round. Catch everything in the node and return an error turn.
- Pause/Stop cut mechanism: langgraph/errors.py converts an asyncio.CancelledError raised from a node body into NodeCancelledError, a node failure. If the cancelled inner stream task's CancelledError leaks through `await inner`, the round fails instead of returning partial text. The inner task has to swallow the cancellation and return normally, and this needs a test.
- Gateway shutdown: request_drain() lets a node that is mid-execution run to completion, which here is a whole round and can be minutes. systemd's default stop timeout is 90 s, after which the service is killed and the round is lost anyway. Call cut("shutdown") first, then request_drain(), and set TimeoutStopSec deliberately.
- Pause, Stop and the time limit: finalise is not free. After time-up or Stop the engine still needs a ballot (if the round had none), one seat writing the final answer and a one-line note from each dissenter, all on one shared GPU. Give this phase its own token caps and a visible 'Writing the answer' state, or the debate will overrun its limit by an unmeasured amount. Stop before the first vote has no 'best answer so far' and needs a defined fallback.
- Ballot design: each round adds one small-model merge call plus one constrained call per seat, on a GPU the bubble summaries also use. The cost is unmeasured and should be part of the GX10 benchmark. An enum of 1..K forces every seat to pick a candidate, so a bad merge can manufacture agreement; add a 'none of these' option and log the candidate texts as an event so the owner can see what was voted on.
- How nodes call llama-server: httpx's default timeout is 5 s for every phase including read (DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)), while llama-server stays silent during prompt processing and only pings every 30 s by default (--sse-ping-interval). Long file-reading prompts will raise ReadTimeout unless the client sets an explicit timeout such as connect 5 s with read None, or a read timeout above the ping interval.
- Pause: 'let the current turns finish' keeps the GPU generating while the timer is frozen, and 'cut and keep the partial text' needs a way to continue. llama.cpp master has a continue_final_message request field and --prefill-assistant (default enabled) that continue a trailing assistant message. Neither is tested with reasoning models, and the GX10's installed build is unknown. Decide the Pause behaviour after testing this, or define Pause as taking effect at the next seat boundary.
- Durable checkpoints: resume re-runs every seat that had not finished in the interrupted round, while the event log already holds their partial deltas. That is two durable records to reconcile, and resume also needs every model re-loaded. For a non-programmer owner the safer default after a restart is 'release the best answer so far', with Resume as the secondary choice. Use an absolute path for the checkpoint file, since a systemd unit's working directory is not the project folder unless set.
- Offline guarantee: set LANGSMITH_TRACING_V2=false as well (it is read first). Note the gateway itself must reach Hugging Face for model downloads, so the 'non-local sockets blocked' test covers the debate path only, not the whole service.
- Pins: langgraph 1.2.14 (2026-10-06), langchain-core 1.6.9 (10-08), langsmith 0.14.7 (10-09) and fastapi 0.143.0 (10-08) are days old and untested on either machine. Lock the set that passes a smoke test on the GX10 and the Mac. uv on the dev Mac supports --exclude-newer to keep a later re-lock from drifting.
- council.md commits: confirm git exists on the GX10 (`git --version`; not checked). A service usually runs without the owner's git config, so pass identity with -c user.name/-c user.email, and expect git's 'dubious ownership' refusal if the repository belongs to a different user than the service (from memory, not checked today). The plan's own example entry shows 'used 3 times' inside the file, so keeping that counter out of the file is a change the owner should approve.
- Learning review placement: the review needs the council's models still loaded, and the owner may ask a new question at once with a different council. Candidates must be queued durably (the plan's 'candidate log'), the review must give way to a new question via the same cut mechanism, and the owner needs to decide which council votes on a deferred candidate.

### Missed by the first pass
- Seats are not servers. Plan page 8: 'The same model can fill two seats with different roles when memory is tight.' Two seats on one llama-server share its slots: with -np 1 the second request queues and the two prompts evict each other's cache. The engine needs a seat-to-server map and a per-server limit; max_concurrency cannot express this.
- The learning review is not one binary 80% vote. Plan page 9 has three outcomes (accepted, waits for more evidence, rejected and not re-proposed), four questions per candidate, and explicit owner preferences that the council 'cannot veto' (wording and conflict check only; page 16 confirms the assumption). The review graph needs a separate path for owner preferences and a three-way ballot schema.
- Plan page 16 assumes an accepted lesson goes 'straight in with an undo notice'. Undo of the newest entry is therefore the common rollback and must be one click. Entry ids such as L7 and P3 are cited as chips in answers (page 9), so ids must be stable and never reused.
- llama-server stop latency on master: should_stop is polled every HTTP_POLLING_SECONDS = 1 second (server-context.cpp), so a cut can lag about a second plus the current decode batch. Verified in master source only; the GX10's installed version is unknown and should be read from `llama-server --version` in the first spike.
- llama-server master sends `timings`, `prompt_progress` and SSE comment pings, and exposes POST /tokenize with add_special default false and cache_prompt default true. Each of these is a README or source fact for master, not for the GX10's build.
- Order turns explicitly. Because parallel updates are not ordered consistently, store seat index and round in each turn and sort before building prompts, tallies or the Chat View.
- Checkpoint size: by default every super-step writes the full value of every state channel, and Send arguments are persisted through the tasks channel. With `{**state, 'seat': s}` each round stores N copies of all turns. Keep full text in the event log and pass only what a seat needs.
- Event log durability setting: set PRAGMA synchronous=NORMAL with WAL on the event database. SQLite documents WAL as corruption-safe at NORMAL, with only the last transactions at risk on power loss. Otherwise a flush every 100 ms per debate may sync the disk on every commit (default not checked on the GX10).
- Building on the Mac: there is no llama.cpp on the dev machine, so phases 4 and 5 need a scripted fake llama-server (SSE deltas, pings, slow prompt phase, mid-stream death) from day one. It is also what the offline test, the cut test and the Table View can run against without the GX10.
- Hygiene in the sketch: a node and a state key are both named `tally`. The 1.2.14 add_node source has no check against this, but older LangGraph versions rejected it (from memory, not verified today); rename the node to avoid the question.
- Scope of this re-check: the plan PDF's wireframes could not be rendered on the dev Mac (pdftoppm is not installed); only its text was read. GitHub release notes for 1.2.13 and 1.2.14 were not read (API rate limit), so why two releases shipped a day apart is unknown.
- Nothing in this area was executed against LangGraph, llama-server or the GX10 by either pass. The first engine spike should run the E2 sketch with a stub seat, kill the gateway mid-round and resume, and time a cut.
