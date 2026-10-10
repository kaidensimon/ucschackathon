# 07 - Contract: app facade, HTTP, events, memory math, UI

Owners: A3 for `ecc/placement/`, `ecc/api/` and `ecc/ui/`; A1 for `ecc/app.py`, the real implementation of the facade. The facade is the single seam between A3's server and the rest: A3 builds everything against a mock facade, A1 later supplies the real one, and nothing in the server or the page changes.

## 1. Memory math: `ecc/placement/budget.py`

Pure functions on integers. Imports only `ecc.common`. This is what makes the UI refuse a placement.

| Quantity | Formula |
|---|---|
| bytes of one expert on a node | `expert_params * itemsize(node.compute_dtype)` |
| backbone bytes on the master | `backbone_params * itemsize(master.compute_dtype)` |
| key-value cache bytes on the master | `2 * num_layers * num_kv_heads * head_dim * context_len * itemsize(master.compute_dtype)` |
| master fixed bytes | `MASTER_OVERHEAD_BYTES + backbone bytes + draft_bytes` (`draft_bytes` is 0 unless speculative decoding is on) |
| satellite fixed bytes | `SATELLITE_OVERHEAD_BYTES` |
| node total | fixed + key-value cache (master only) + expert bytes times experts placed there |
| over by | `max(0, total - budget_bytes)` |
| expert capacity of a node | `max(0, (budget_bytes - fixed - kv) // bytes of one expert)`; 0 for an offline node |

| Name | Signature |
|---|---|
| `expert_bytes_on` | `expert_bytes_on(expert_params: int, compute_dtype: str) -> int` |
| `kv_cache_bytes` | `kv_cache_bytes(num_layers: int, num_kv_heads: int, head_dim: int, context_len: int, compute_dtype: str) -> int` |
| `fixed_bytes` | `fixed_bytes(role: str, backbone_params: int, compute_dtype: str, draft_bytes: int) -> int` |
| `expert_capacity` | `expert_capacity(budget_bytes: int, fixed: int, kv: int, bytes_per_expert: int) -> int` |

## 2. Checker and auto-placer: `ecc/placement/planner.py`

**`NodeMemory`**: frozen dataclass, one per node: `node_id`, `fixed_bytes`, `kv_bytes`, `expert_count`, `expert_bytes`, `total_bytes`, `budget_bytes`, `over_by_bytes`, `capacity_count` (experts that would fit).

**`MemoryReport`**: frozen dataclass: `ok: bool`, `context_len: int`, `nodes: list[NodeMemory]` (same order as the placement's `node_ids`), `disk_count: int`, `violations: list[str]`. Method `to_json()`.

| Name | Signature | Behaviour |
|---|---|---|
| `check_placement` | `check_placement(model_map: ModelMap, nodes: list[NodeInfo], placement: Placement, draft_bytes: int = 0) -> MemoryReport` | validates the grid's shape, then computes every node's memory. A violation is one sentence per problem: a node over budget (`<name> is over its budget by <amount>: <placed> experts placed, room for <capacity>`, the amount in GiB with two decimals from 1 GiB up and in MiB with one decimal below), a node whose fixed bytes alone exceed its budget (`<name> cannot hold the backbone: it needs <x.xx> GiB before any expert and its budget is <y.yy> GiB`), experts placed on an offline node, a node id in the placement that is not in `nodes`, node index 0 not being the master. `ok` is true when there are no violations. It never raises for a bad placement; it reports |
| `auto_place` | `auto_place(model_map: ModelMap, nodes: list[NodeInfo], context_len: int, draft_bytes: int = 0) -> Placement` | see the steps below. Same inputs, same result |

**Auto-place steps.** Node order: the master, then online satellites by ascending round-trip time rounded up to a multiple of 5 ms (unmeasured last), ties by position in `nodes`. The rounding keeps the result the same from one launch to the next although measurements jitter. The numbers written into `owner` are positions in the `nodes` argument, never positions in this fill order. Offline nodes get nothing. The master's usable capacity is half of its expert capacity: the other half stays free so that hot experts can migrate in. A satellite's usable capacity is its full expert capacity.

1. `share` = the total number of experts divided by the number of online nodes including the master, rounded up.
2. First pass, in node order: each node is given the smaller of `share` and its usable capacity.
3. Second pass, satellites in order and then the master: each takes more of what is left, up to its usable capacity.
4. Whatever is still left is disk (`-1`).
5. The counts are turned into a grid by walking the experts layer by layer, expert by expert, and filling the nodes in node order, so layers stay together where they can.

The even share in step 2 means a model that would fit on the master alone is still spread over the cluster, which is what a demonstration with a small model needs.

## 3. The facade: `ecc/api/facade.py`

A `typing.Protocol` named `Facade`. Every method returns plain JSON-ready values (dicts, lists, strings, numbers, booleans, `None`). Methods return quickly; long work runs on the app's own threads and reports through events. Methods are called from the HTTP server's worker threads, several at once.

| Method | Signature | Behaviour |
|---|---|---|
| `get_state` | `get_state() -> dict` | the State object of section 4 |
| `load_model` | `load_model(path: str) -> dict` | indexes the folder and builds the model map (no weights loaded). Returns the new state. Phase becomes `model_loaded` |
| `add_node` | `add_node(host: str, port: int) -> dict` | connects to a satellite. Returns its `NodeInfo` JSON |
| `remove_node` | `remove_node(node_id: str) -> None` | its experts become disk in the current placement |
| `set_budget` | `set_budget(node_id: str, budget_bytes: int) -> dict` | returns the node's `NodeInfo` JSON |
| `check_placement` | `check_placement(owner: list[list[int]], context_len: int) -> dict` | a `MemoryReport` as JSON for a placement the user is considering. Changes nothing |
| `set_placement` | `set_placement(owner: list[list[int]], context_len: int) -> dict` | stores the placement if its report is ok and returns the new state; otherwise raises `PlacementError` carrying the violations |
| `auto_place` | `auto_place(context_len: int) -> dict` | computes, stores and returns the new state |
| `launch` | `launch() -> None` | starts the launch in the background: weights go out to the satellites, the master loads its backbone and its own experts. Progress arrives as `launch` events; at the end the phase is `ready` or `error` |
| `generate` | `generate(messages: list[dict], options: dict) -> None` | starts a generation. Tokens arrive as `token` events |
| `stop` | `stop() -> None` | |
| `update_settings` | `update_settings(patch: dict) -> dict` | changes the given settings keys and returns all settings |
| `events` | `events() -> EventHub` | the hub the server subscribes to |

`owner` has the same meaning as in `Placement`, with indexes referring to `state["nodes"]` in order. Index 0 is the master.

Rules both facades follow:

- `generate`: `options` may hold `max_new_tokens`, `temperature`, `top_p` and `speculative`. An absent key takes the value in settings (`top_p`: 0.9). Any other key raises `ValueError`. The page sends an empty object.
- `update_settings`: an unknown key or a wrongly typed value raises `ValueError`. `migration`, `speculative`, `max_new_tokens` and `temperature` take effect at once. `wire_dtype`, `context_len` and `draft_model_dir` are read at launch: a change takes effect at the next launch.
- `load_model` also stores the all-disk placement (every cell `-1`) and its memory report, so `placement` and `memory` are `null` only in phase `empty`.
- `add_node`, `remove_node`, `set_budget`, and a node going online or offline, recompute `memory` for the stored placement and publish `state`. `launch` checks the placement again and raises `PlacementError` if its report is not ok.
- `remove_node`: the id leaves the node list; in `owner`, cells equal to its index become `-1` and cells above it decrease by 1.
- `locations` is non-null only in phases `ready` and `generating`. `set_placement`, `auto_place` and `load_model` called in `ready` or `error` drop the loaded model and set `locations` to `null`.
- `error` is set only by a failed launch and is `null` again after the next successful `load_model`, `set_placement`, `auto_place` or `launch`.
- The thread started by `launch` or `generate` has one outermost handler for every exception (the one place a broad `except Exception` is allowed; it logs the traceback). A failed launch sets phase `error` with the text; a failed generation emits `gen_done` with reason `error` and returns to `ready`. Both publish `state`.
- Every number in a State or an event is finite (never NaN or infinity).
- At launch the master's expert cache gets the budget `master budget_bytes - master fixed bytes - key-value cache bytes` from the memory report (never below 0). The experts the placement gives the master are loaded into it as pinned; what is left over is the room for migration.
- The app calls `stats.reset()` at the start of every generation, so "total" in the stats keys means since that generation started.

### The real facade: `ecc/app.py` (A1)

**`EccApp(registry: NodeRegistry)`**: implements `Facade`. The master is `registry.nodes()[0]`. Besides the facade methods:

| Member | Meaning |
|---|---|
| `close() -> None` | stops the migrator, the stats thread and any generation; safe to call twice |
| `generate_ids(input_ids: list[int], options: dict) -> None` | like `generate` but from token ids, so checks need no tokenizer; same events (`token` text is empty when there is no tokenizer) |
| read-only attributes `model`, `dispatcher`, `generation`, `migrator`, `registry` | for checks; `None` before launch where that applies |

`main(argv)` is mode `master`: flags `--model`, `--peer` (repeatable), `--host` (default `127.0.0.1`), `--port`, `--device`, `--dtype`, `--budget-gb`, `--context-len`, `--auto-place`, `--launch`, `--full-load`, `--draft`, `--no-mdns`, `--no-browser`.

**Which call is allowed in which phase.** Anything else raises `EngineError` with a message that names the phase.

| Phase | Meaning | Allowed calls (besides `get_state`, `events`, `update_settings`) |
|---|---|---|
| `empty` | no model | `load_model`, `add_node`, `remove_node`, `set_budget` |
| `model_loaded` | model indexed, nothing in RAM | all of the above, `check_placement`, `set_placement`, `auto_place`, and `launch` once a placement is stored |
| `launching` | weights are moving | none |
| `ready` | can generate | `generate`, `add_node`, `remove_node`, `set_budget`, `check_placement`; `set_placement`, `auto_place` and `load_model` are allowed and put the phase back to `model_loaded` |
| `generating` | a reply is being produced | `stop` |
| `error` | launch failed; `state["error"]` says why | the same as `model_loaded` |

### Event hub: `ecc/api/events.py`

**`EventHub()`**: thread-safe publish and subscribe.

| Method | Signature | Behaviour |
|---|---|---|
| `publish` | `publish(event_type: str, data: dict) -> None` | puts `(event_type, data)` on every subscriber's queue; never blocks; if a subscriber's queue (capacity 2000) is full, that one event is dropped for that subscriber |
| `subscribe` | `subscribe() -> Subscription` | |
| `Subscription.get` | `get(timeout_s: float) -> tuple[str, dict] or None` | `None` on timeout |
| `Subscription.close` | `close() -> None` | removes it from the hub |

### Conformance: `ecc/api/conformance.py`

The page is built against the mock facade and must work unchanged on the real app. One module holds the definition of "a correct State" and "a correct event" as code, and the checks of both facades use it. Never imports torch.

| Name | Signature | Behaviour |
|---|---|---|
| `validate_state` | `validate_state(state: dict) -> list[str]` | returns one sentence per problem, an empty list when the State matches section 4: exactly the listed top-level keys; `phase` one of the six names; every node has exactly the `NodeInfo` fields with allowed values; the master is first; when `placement` is present its grid has the model's dimensions and its indexes are valid for `nodes`; `locations` has the same dimensions; `memory` has the `MemoryReport` keys; `settings` has exactly the listed keys with the right types |
| `validate_event` | `validate_event(event_type: str, data: dict) -> list[str]` | the same for one event against the events table: a known type and exactly the listed fields with the right types; a `state` event is checked with `validate_state` |

## 4. State and events

**State** (the result of `get_state`, and the data of the `state` event):

| Key | Value |
|---|---|
| `phase` | one of the phase names above |
| `error` | `null` or a message |
| `model` | `null` or the `ModelMap` JSON |
| `nodes` | list of `NodeInfo` JSON, the master first, then satellites in the order they were added. A node keeps its position for as long as it is in the list; when a node is removed, the ones after it move up by one and the app rewrites the stored placement to match |
| `placement` | `null` or `{"node_ids": [...], "owner": [[...]], "context_len": n}`, where `node_ids` lists the ids of `nodes` in the same order |
| `memory` | `null` or the `MemoryReport` JSON of the stored placement |
| `locations` | `null` before launch; afterwards a grid like `owner` showing where each expert is right now (it differs from `owner` once experts migrate): a node index, or `-1` for disk |
| `launch` | `null`, or an object with one entry per node id: `{"done_count", "total_count", "bytes_sent", "status", "message"}`; status is `pending`, `pushing`, `done` or `failed` |
| `settings` | `{"migration": bool, "speculative": bool, "wire_dtype": "float16" or "float32", "max_new_tokens": int, "temperature": number, "context_len": int, "draft_model_dir": string or null}`. Start values: `true`, `false`, `DEFAULT_WIRE_DTYPE`, 256, 0.7, `DEFAULT_CONTEXT_LEN`, `null` |
| `stats` | the latest `stats` event data, or `null` |

**Events.** Each has a type and a JSON object.

| Type | When | Data |
|---|---|---|
| `state` | when a client connects, and whenever phase, model, nodes list membership, placement or settings change | the whole State |
| `nodes` | every `NODE_POLL_INTERVAL_S`, and when a node goes online or offline | `{"nodes": [...]}` |
| `launch` | after every expert pushed or loaded during a launch | `{"node_id", "done_count", "total_count", "bytes_sent", "status", "message"}` |
| `token` | for every piece of generated text | `{"text", "index"}`; `index` is the number of tokens generated so far, so the first event has 1 or more |
| `gen_done` | when a generation ends | `{"reason", "tokens", "seconds", "message", "token_ids"}` (`message` is an empty string unless the reason is `error`; `token_ids` is the list of generated ids) |
| `stats` | every `STATS_INTERVAL_S` while generating, and once more immediately before `gen_done` | the fifteen keys defined below |
| `heat` | every `STATS_INTERVAL_S` while generating and once more immediately before `gen_done`, each time only if an expert was used since the previous one | `{"cells": [[layer, expert, calls], ...]}` for experts used since the previous `heat` event |
| `migration` | when experts change location | `{"moved": [[layer, expert, from_index, to_index], ...]}` with node indexes as in `locations` (`-1` = disk) |

**The `stats` keys.** "Total" means since this generation started. "Window" means since the previous `stats` event. Every ratio is `0.0` when its denominator is 0.

| Key | Definition | Filled by |
|---|---|---|
| `tokens`, `forward_passes`, `local_calls`, `remote_calls`, `disk_calls` | totals | `EngineStats.take_window` |
| `tokens_per_s`, `bytes_sent_per_s`, `bytes_received_per_s` | window amount divided by window seconds | `take_window` |
| `round_trips_per_token`, `remote_ms_per_token` | window amount divided by window tokens | `take_window` |
| `local_fraction` | window local calls divided by all window calls | `take_window` |
| `tokens_per_forward` | total tokens divided by total forward passes | `take_window` |
| `experts_in_master_ram`, `master_cache_bytes_used`, `master_cache_bytes_budget` | from the dispatcher and the cache | the app, added to what `take_window` returned |

## 5. HTTP: `ecc/api/server.py`

FastAPI. Every route calls exactly one facade method and returns its result as JSON. Route functions are ordinary (non-async) functions, so each request runs on a worker thread.

| Method and path | Request body | Calls | Success reply |
|---|---|---|---|
| `GET /` and `GET /<file>` | | static files from `ecc/ui/`: one static mount at `/` (with `html=True`, so `/` gives `index.html`), added after every `/api/` route. `create_app` first registers the types `text/javascript` for `.js` and `text/css` for `.css`, because Windows often reports the wrong type and browsers then refuse modules | the file |
| `GET /api/state` | | `get_state` | State |
| `POST /api/model` | `{"path"}` | `load_model` | State |
| `POST /api/nodes` | `{"host", "port"}` | `add_node` | NodeInfo |
| `DELETE /api/nodes/{node_id}` | | `remove_node` | `{"ok": true}` |
| `POST /api/nodes/{node_id}/budget` | `{"budget_bytes"}` | `set_budget` | NodeInfo |
| `POST /api/placement/check` | `{"owner", "context_len"}` | `check_placement` | MemoryReport (status 200 even when not ok) |
| `POST /api/placement` | `{"owner", "context_len"}` | `set_placement` | State |
| `POST /api/placement/auto` | `{"context_len"}` | `auto_place` | State |
| `POST /api/launch` | | `launch` | `{"ok": true}` |
| `POST /api/generate` | `{"messages": [{"role", "content"}], "options": {...}}` | `generate` | `{"ok": true}` |
| `POST /api/stop` | | `stop` | `{"ok": true}` |
| `POST /api/settings` | a settings patch | `update_settings` | settings |
| `GET /api/events` | | subscribes to the hub | a Server-Sent Events stream |

**Errors.** Every failure is JSON of the form `{"error": {"code": "...", "message": "...", "violations": [...]}}` (`violations` only for placement errors).

| Exception | Status | Code |
|---|---|---|
| `PlacementError` | 409 | `placement` |
| `EngineError` | 409 | `engine` |
| `ModelFileError` | 400 | `model_file` |
| `NodeUnavailable` | 502 | `node_unavailable` |
| `ValueError`, a missing or wrongly typed body field | 400 | `bad_request` |
| anything else | 500 | `internal` (logged with traceback) |

**Event stream.** `GET /api/events` answers with media type `text/event-stream`. The first event sent is `state` with the current State. Each event is written as a line `event: <type>`, a line `data: <one-line JSON>`, and a blank line. When no event arrives for 10 seconds the server writes a comment line (`: keepalive`) and a blank line. The subscription is closed when the client disconnects. In the browser the page uses `EventSource`, which reconnects by itself.

| Name | Signature | Behaviour |
|---|---|---|
| `create_app` | `create_app(facade: Facade, keepalive_s: float = 10.0) -> FastAPI` | builds the routes |
| `serve` | `serve(facade: Facade, host: str, port: int) -> None` | runs the server until interrupted |
| `start_server` | `start_server(facade: Facade, host: str = "127.0.0.1", port: int = 0) -> RunningServer` | runs the server on a background thread and returns once it is listening (at most 10 seconds, else `EngineError`). `RunningServer` has `port: int` and `stop() -> None`. Used by checks and by the `master` mode |
| `main_mock` | `main_mock(argv: list[str]) -> int` | mode `mock-ui`: serves the page on a `MockFacade`; flags `--port`, `--layers`, `--experts`, `--nodes` |

All route functions are ordinary functions except `GET /api/events`, which is `async`: it subscribes first, reads the State second, and reaches `get_state` and `Subscription.get` only through the thread pool. `EventHub` has a read-only property `subscriber_count`.

**`MockFacade(num_layers: int = 24, num_experts: int = 60, node_count: int = 3, speed: float = 1.0)`** in `ecc/api/mock.py` implements `Facade` with no model and no network: an invented model map (24 layers of 60 experts by default), three invented nodes, real `check_placement` and `auto_place` from the planner, a launch that takes about 5 seconds of timed progress events, a generation that emits words from a fixed text at about 15 tokens per second with believable `stats`, `heat` and `migration` events. The page is built and demonstrated against it.

## 6. The page: `ecc/ui/`

Served at `/`. Files: `index.html`, `style.css`, and modules in `js/`.

| Module | Owns |
|---|---|
| `js/main.js` | start-up, the one store object (latest State plus UI-only state such as the current selection), the `EventSource`, and telling the other modules to redraw |
| `js/api.js` | one function per HTTP route; turns an error reply into a thrown error carrying `code`, `message`, `violations` |
| `js/nodes.js` | the node cards |
| `js/grid.js` | the expert grid: one `div` per expert in a CSS grid, each with `data-layer` and `data-expert`. Cells are built once per model; afterwards only cells whose owner changed are recoloured |
| `js/select.js` | selecting experts and assigning them to a node |
| `js/chat.js` | the chat box and token stream |
| `js/stats.js` | the live numbers |
| `js/dialogs.js` | load model, add node, settings |

**Layout.** A header bar (model name, phase, buttons Load model, Auto-place, Launch). Below it two columns: on the left the expert grid, one row per layer and one column per expert, with the layer number at the start of each row; on the right the node cards, the master first, then each satellite, then one card for "Disk". Under both, a chat panel on the left and a stats panel on the right.

**Colour.** Each node has a colour from a fixed palette by its position in `state.nodes`; the master's is always the first. Disk is dark grey. A grid cell is drawn in the colour of the node that currently holds that expert (from `locations` after launch, from the edited placement before). A cell that was just used flashes brighter and fades over about a second. So during a session the viewer sees cells light up as experts are called and turn master-coloured as they migrate.

**Node card.** Name, link type, round-trip time, online or offline, a memory bar (fixed, key-value cache, experts, free, against the budget, with numbers in GiB), expert count, and a button "Assign selection here".

**Placing.** Click a cell to select it; click a layer number to select the whole layer; drag across cells to select a rectangle; a "Select all" button. Then press the target card's "Assign selection here" button (dragging onto a card is not built). Before a move is applied the page asks `POST /api/placement/check`; if the report is not ok the move is refused: the card shakes and shows the violation text, and nothing changes. An accepted move is stored with `POST /api/placement`.

**Names shared by all page tasks.** Several tasks build this page in separate sessions; these names are fixed so the pieces fit.

| Thing | Fixed as |
|---|---|
| Region element ids in `index.html` | `header`, `message-bar`, `grid-panel`, `nodes-panel`, `chat-panel`, `stats-panel` |
| Every module in `js/` except `main.js`, `api.js`, `selftest.js` | exports `init(store, api)` (called once at start: build elements, attach listeners) and `render(state)` (called after every change). `R06-A3a` creates all of them as stubs and `main.js` already calls them; later tasks fill in their own module and do not edit `main.js` |
| The store (made in `main.js`) | `store.state` (latest State from the server), `store.selection` (a `Set` of strings `"<layer>:<expert>"`), `store.messages` (the chat as a list of `{role, content}`), `store.notice` (text for the message bar or `null`), `store.update(changes)` (merge and re-render everything), `store.setState(state)` |
| `js/api.js` exports | `getState`, `loadModel(path)`, `addNode(host, port)`, `removeNode(nodeId)`, `setBudget(nodeId, budgetBytes)`, `checkPlacement(owner, contextLen)`, `setPlacement(owner, contextLen)`, `autoPlace(contextLen)`, `launch()`, `generate(messages, options)`, `stop()`, `updateSettings(patch)`; each returns a promise and throws an `Error` with `code`, `message`, `violations` on an error reply |
| Events | exactly one `EventSource` on `/api/events`, created in `main.js`, with one `addEventListener` per event type. Never create another in `onerror`: the browser reconnects by itself. For every event `main.js` first folds it into `store.state` where it belongs (`state` replaces it; `nodes`, `launch`, `stats`, `migration` patch their part), then calls the optional export `onEvent(type, data)` of every module that has one, then re-renders. That is how a module receives `token`, `gen_done`, `heat` without anyone editing `main.js` |
| `render(state)` | receives `store.state`, which is `null` until the first `state` event |
| Colours | CSS custom properties defined once in `style.css`: `--node-color-0` to `--node-color-7` (position in `state.nodes`, wrapping after 8) and `--disk-color` |
| Header controls | buttons and selectors go into the element with id `header-actions` inside `header` |
| Self-test page | `selftest.html` loads `js/selftest.js`, which exports `test(name, fn)` and `assertEqual(actual, expected)`; each module's pure functions get cases there. When all cases have run the page shows one line per case (`PASS <name>` or `FAIL <name>: <why>`) and a last line `SELFTEST OK <n>` or `SELFTEST FAILED <n>` |
| Seeing the page without a person | `ecc/api/uitest.py` has `run_headless(url: str, wait_ms: int = 3000) -> str or None`: it looks for Edge or Chrome already installed on the machine, runs it headless with a temporary profile and the dump-DOM option, and returns the page's HTML, or `None` when no such browser is found. UI checks use it on `selftest.html` and require `SELFTEST OK`; with no browser they print `PASS selftest (skipped: no browser found)` |
