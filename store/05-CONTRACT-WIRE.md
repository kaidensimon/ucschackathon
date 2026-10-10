# 05 - Contract: the network

Owner: A2 (`ecc/net/`). Used by A1 (dispatcher, app). The master is always the client; a satellite is always the server. Everything here is blocking sockets and threads from the standard library.

## 1. Connection rules

1. One TCP connection per (master, satellite) pair, opened by the master and kept open.
2. On one connection the master sends a request and reads the reply before sending the next request. Never two requests in flight on one connection. The client object enforces this with a lock.
3. Both ends set `TCP_NODELAY` on the socket immediately after connect or accept. Without it small request-reply messages are delayed by tens of milliseconds and the model crawls.
4. Only the master sets timeouts: `CONNECT_TIMEOUT_S` for connecting, `CALL_TIMEOUT_S` for every read and write after that. A satellite sets no timeout on an accepted socket: a master that sends nothing for minutes is normal, and `stop()` closes the sockets to wake the waiting threads.
5. All integers are little-endian. All arrays are row-major and contiguous.
6. The first request on a connection must be HELLO. Any other first request gets an ERROR with code `NO_HELLO` and the satellite closes the connection.

## 2. Frame

Every message is a 16-byte header followed by the payload.

| Offset | Size | Field | Value |
|---|---|---|---|
| 0 | 4 | magic | the bytes `ECC1` |
| 4 | 1 | msg_type | unsigned 8-bit, see section 3 |
| 5 | 1 | flags | 0 |
| 6 | 2 | reserved | 0 |
| 8 | 4 | request_id | unsigned 32-bit, chosen by the master, copied into the reply |
| 12 | 4 | payload_len | unsigned 32-bit, at most `MAX_PAYLOAD_BYTES` |

Reading a frame: read exactly 16 bytes, check the magic and the length limit, then read exactly `payload_len` bytes. A read from a socket may return fewer bytes than asked for; keep reading until you have them all. Zero bytes returned before the first header byte means the peer closed cleanly (`ConnectionClosed`); zero bytes anywhere later is a `WireError`.

### `ecc/net/wire.py`

Imports only the standard library and `ecc.common`.

| Name | Signature | Behaviour |
|---|---|---|
| `HEADER_SIZE` | 16 | |
| `Frame` | frozen dataclass: `msg_type: int`, `request_id: int`, `payload: bytes` | |
| `pack_header` | `pack_header(msg_type: int, request_id: int, payload_len: int) -> bytes` | raises `WireError` if `payload_len` exceeds the limit |
| `unpack_header` | `unpack_header(header: bytes) -> tuple[int, int, int]` | returns `(msg_type, request_id, payload_len)`; raises `WireError` on wrong size, wrong magic or oversize length |
| `recv_exact` | `recv_exact(sock: socket.socket, byte_count: int) -> bytes` | loops until done; raises `ConnectionClosed` if the very first read of the call returns nothing, `WireError` if a later one does |
| `send_frame` | `send_frame(sock: socket.socket, msg_type: int, request_id: int, *parts: bytes) -> int` | sends the header and then each part with `sendall`, without joining the parts into one buffer. The payload length is the sum of the part lengths. Returns the total bytes sent |
| `recv_frame` | `recv_frame(sock: socket.socket) -> Frame` | |
| `configure_socket` | `configure_socket(sock: socket.socket, timeout_s: float or None) -> None` | sets `TCP_NODELAY`, `SO_KEEPALIVE` and the timeout; `None` means no timeout |

A `socket.timeout` or `OSError` is not caught in this module; the caller turns it into `NodeUnavailable`.

## 3. Message types

Named integer constants in `ecc/net/messages.py`.

| Code | Name | Direction | Payload | Reply |
|---|---|---|---|---|
| 0x01 | `HELLO` | master to satellite | JSON | `HELLO_OK` |
| 0x02 | `HELLO_OK` | satellite to master | JSON | |
| 0x03 | `PING` | master to satellite | 0 to 64 arbitrary bytes | `PONG` |
| 0x04 | `PONG` | satellite to master | the same bytes | |
| 0x05 | `STATS` | master to satellite | empty | `STATS_OK` |
| 0x06 | `STATS_OK` | satellite to master | JSON | |
| 0x10 | `LOAD_EXPERT` | master to satellite | binary, section 5 | `LOAD_OK` |
| 0x11 | `LOAD_OK` | satellite to master | JSON | |
| 0x12 | `HAVE` | master to satellite | JSON | `HAVE_OK` |
| 0x13 | `HAVE_OK` | satellite to master | JSON | |
| 0x14 | `LOAD_CACHED` | master to satellite | JSON | `LOAD_OK` |
| 0x15 | `UNLOAD` | master to satellite | JSON | `UNLOAD_OK` |
| 0x16 | `UNLOAD_OK` | satellite to master | JSON | |
| 0x20 | `EXPERT_CALL` | master to satellite | binary, section 6 | `EXPERT_RESULT` |
| 0x21 | `EXPERT_RESULT` | satellite to master | binary, section 6 | |
| 0x7F | `ERROR` | satellite to master | JSON | may replace any reply |

JSON payloads are UTF-8 with no extra whitespace. Expert keys in JSON are two-element lists `[layer, expert]`.

## 4. JSON messages

| Message | Fields |
|---|---|
| `HELLO` | `proto` (int, must equal `PROTO_VERSION`), `node_id` (the master's), `name` (the master's) |
| `HELLO_OK` | `proto`; `node`: the satellite's `NodeInfo` as JSON with `role` `"satellite"`, `host` `""`, `link_type` `"unknown"`, `rtt_ms` null, `status` `"online"` (the master fills in host, link type and round-trip time itself) |
| `STATS_OK` | `ram_total_bytes`, `ram_available_bytes`, `budget_bytes`, `experts_loaded`, `expert_bytes_loaded`, `calls_served`, `rows_served`, `uptime_s` |
| `LOAD_OK` | `experts_loaded`, `expert_bytes_loaded`, `ram_available_bytes` |
| `HAVE` | `model_hash` |
| `HAVE_OK` | `in_ram`: list of keys in RAM for that model; `on_disk`: list of keys in the disk cache for that model |
| `LOAD_CACHED` | `model_hash`, `experts`: list of keys to load from the disk cache into RAM |
| `UNLOAD` | `model_hash`, `experts`: a list of keys, or the string `"all"` |
| `UNLOAD_OK` | `experts_loaded`, `expert_bytes_loaded` |
| `ERROR` | `code` (string from the table below), `message` (human text), `experts` (list of keys, may be empty) |

| Error code | Meaning | What the master does |
|---|---|---|
| `PROTO` | protocol versions differ | marks the node offline and shows the message |
| `NO_HELLO` | first request was not HELLO | bug: fix the client |
| `BAD_PAYLOAD` | payload could not be decoded or sizes do not add up | bug: fix the sender |
| `UNKNOWN_TYPE` | unknown msg_type | bug |
| `OVER_BUDGET` | loading this expert would exceed the satellite's budget | stops the push to that node and reports it |
| `EXPERT_NOT_LOADED` | an EXPERT_CALL named experts that are not in RAM; `experts` lists them. Nothing was computed | computes those experts itself from disk |
| `NOT_CACHED` | LOAD_CACHED named experts that are not in the disk cache; `experts` lists them. Nothing was loaded | pushes those experts normally |
| `INTERNAL` | any other failure on the satellite | treats the node as unavailable for this call |

## 5. LOAD_EXPERT payload

| Offset | Size | Field |
|---|---|---|
| 0 | 16 | model_hash: 16 ASCII characters |
| 16 | 2 | layer, unsigned 16-bit |
| 18 | 2 | expert, unsigned 16-bit |
| 20 | 1 | weight dtype code (1, 2 or 3; see `03-CONTRACT-COMMON.md` section 4) |
| 21 | 1 | persist: 1 = also save to the disk cache, 0 = RAM only |
| 22 | 2 | reserved, 0 |
| 24 | 4 | `H`, hidden size, unsigned 32-bit |
| 28 | 4 | `I`, intermediate size, unsigned 32-bit |
| 32 | `I*H*s` | gate_proj, shape `(I, H)` |
| then | `I*H*s` | up_proj, shape `(I, H)` |
| then | `H*I*s` | down_proj, shape `(H, I)` |

`s` is the item size of the dtype. The payload length must be exactly `32 + 3*I*H*s`, otherwise the satellite answers `BAD_PAYLOAD`. Loading an expert that is already in RAM replaces it and is not an error.

## 6. EXPERT_CALL and EXPERT_RESULT payload

Both use the same layout. The reply repeats the header and the call table and carries output rows instead of input rows.

| Offset | Size | Field |
|---|---|---|
| 0 | 16 | model_hash |
| 16 | 1 | activation dtype code (1 or 2) |
| 17 | 1 | reserved, 0 |
| 18 | 2 | `n`, number of calls, unsigned 16-bit, at least 1 |
| 20 | 4 | `H`, hidden size |
| 24 | `8*n` | call table: for each call `layer` (u16), `expert` (u16), `rows` (u32) |
| `24 + 8*n` | sum of `rows*H*s` | the rows of call 1, then call 2, and so on; each block has shape `(rows, H)` |

For each call the satellite converts the rows to its compute dtype on its device, runs the expert (formula in `06-CONTRACT-ENGINE.md` section 1), converts the result to the same activation dtype the request used, and writes it at the same position. If any named expert is not in RAM it computes nothing and answers `EXPERT_NOT_LOADED` listing all the missing keys.

### `ecc/net/messages.py`

Imports numpy but not torch. Arrays in this module are numpy arrays of dtype `float16` or `float32`, shape `(rows, H)`.

| Name | Signature | Behaviour |
|---|---|---|
| `ExpertCallItem` | frozen dataclass: `layer: int`, `expert: int`, `rows: numpy.ndarray` | one call or one result |
| `encode_json` / `decode_json` | `encode_json(data: dict) -> bytes`, `decode_json(payload: bytes) -> dict` | `decode_json` raises `WireError` on bad JSON |
| `encode_expert_call` | `encode_expert_call(model_hash: str, items: list[ExpertCallItem]) -> list[bytes]` | returns the payload as parts (the fixed part, then one buffer per item) ready to hand to `send_frame`. All items must share one dtype and one hidden size, else `ValueError` |
| `decode_expert_call` | `decode_expert_call(payload: bytes) -> tuple[str, list[ExpertCallItem]]` | returns `(model_hash, items)`. Raises `WireError` when the sizes do not add up. The arrays may be read-only views of the payload |
| `encode_load_expert` | `encode_load_expert(model_hash: str, blob: ExpertBlob, persist: bool) -> list[bytes]` | parts: the 32-byte fixed part, then the three byte strings |
| `decode_load_expert` | `decode_load_expert(payload: bytes) -> tuple[str, ExpertBlob, bool]` | returns `(model_hash, blob, persist)`; raises `WireError` on a size mismatch |
| `encode_error` / `raise_if_error` | `encode_error(code: str, message: str, experts: list[ExpertKey]) -> bytes`, `raise_if_error(frame: Frame) -> None` | `raise_if_error` raises `RemoteError` when the frame is an ERROR and does nothing otherwise |

`EXPERT_RESULT` is encoded and decoded by the same two expert-call functions.

## 7. The satellite

### `ecc/net/satellite_store.py`

**`SatelliteStore(budget_bytes: int, device: str, compute_dtype: str, cache_dir: Path or None)`**. Holds experts in RAM as `ExpertWeights` (from `ecc/common/expert_math.py`) keyed by `(model_hash, layer, expert)`. Called by many connection threads at once. Two locks: a table lock guards the dictionary and the byte counter and is never held during computation; a separate compute lock lets only one `forward` compute at a time, because several threads computing with torch at once each start their own team of worker threads and slow each other down.

| Method | Signature | Behaviour |
|---|---|---|
| `load` | `load(model_hash: str, blob: ExpertBlob, persist: bool) -> None` | converts the blob to weights on the store's device and dtype. Raises `RemoteError` with code `OVER_BUDGET` if `SATELLITE_OVERHEAD_BYTES` plus bytes already loaded plus this expert would exceed the budget. With `persist` true and a cache folder set, also saves the blob to disk (section 9) |
| `has` | `has(model_hash: str, key: ExpertKey) -> bool` | |
| `keys_in_ram` | `keys_in_ram(model_hash: str) -> list[ExpertKey]` | sorted |
| `unload` | `unload(model_hash: str, keys: list[ExpertKey] or None) -> None` | `None` unloads every expert of that model |
| `forward` | `forward(model_hash: str, items: list[ExpertCallItem]) -> list[ExpertCallItem]` | raises `RemoteError` with code `EXPERT_NOT_LOADED` and all missing keys before computing anything. Otherwise returns one item per input item with the output rows in the same numpy dtype as the input |
| `stats` | `stats() -> dict` | the fields of `STATS_OK` except the RAM numbers, which the server adds |

### `ecc/net/satellite_server.py`

**`SatelliteServer(store: SatelliteStore, node_info: NodeInfo, host: str, port: int)`**.

| Method | Behaviour |
|---|---|
| `start() -> int` | binds, listens, starts the accept thread, returns the real port (useful when `port` was 0) |
| `stop() -> None` | closes the listening socket and every open connection, joins the threads |
| `serve_forever() -> None` | `start`, then blocks until interrupted, then `stop` |
| `connection_count` (property) `-> int` | connections open right now |

One thread per accepted connection. Each thread loops: read a frame, handle it, send exactly one reply with the same `request_id`.

- An error while reading a frame (`ConnectionClosed`, any other `WireError`, `OSError`) ends the connection: close the socket, end the thread, send nothing. `ConnectionClosed` is quiet; the others log one line.
- An error while handling a complete frame gets exactly one `ERROR` reply and the connection stays open: a `RemoteError` from the store keeps its code; a `WireError` or `ValueError` from decoding the payload becomes `BAD_PAYLOAD`; anything else becomes `INTERNAL` and is logged with its traceback.

The satellite's node id is `local_node_id()`, a dash, and the port it actually listens on. Its `budget_bytes` is what `--budget-gb` says, or `DEFAULT_BUDGET_FRACTION` of the RAM available when it starts; it reports that number in `HELLO_OK` and enforces it in its store.

**`main(argv)`**: mode `satellite`. Flags: `--host` (default `0.0.0.0`), `--port` (default `DEFAULT_SATELLITE_PORT`), `--name` (default the host name), `--budget-gb` (float; default `DEFAULT_BUDGET_FRACTION` of available RAM), `--device` and `--dtype` (both default `auto`; `03-CONTRACT-COMMON.md` section 8), `--no-cache` (do not keep a disk cache). It prints one line when ready: `satellite <name> <node_id> listening on <host>:<port> device=<device> dtype=<compute dtype> budget=<x.xx> GiB`.

The listening socket is made with `socket.create_server`, which handles address reuse correctly on Windows and on Unix.

### `ecc/net/local.py`

One helper that every check needing a satellite uses, so that nobody rebuilds the same setup.

| Name | Signature | Behaviour |
|---|---|---|
| `start_local_satellite` | `start_local_satellite(name: str, budget_bytes: int = 4 * 1024**3, cache_dir: Path or None = None, port: int = 0) -> tuple[SatelliteServer, int]` | builds a `SatelliteStore` (device `cpu`, dtype `float32`) and a `SatelliteServer` on `127.0.0.1`, starts it and returns the server and its real port. The node id is `local_node_id()`, a dash, and that port. The caller calls `server.stop()` |

## 8. The master's side

### `ecc/net/client.py`

**`SatelliteClient(host: str, port: int, master_id: str, master_name: str, connect_timeout_s: float = CONNECT_TIMEOUT_S, call_timeout_s: float = CALL_TIMEOUT_S)`**. One connection to one satellite. Any thread may call it; a lock makes requests take turns.

| Method | Signature | Behaviour |
|---|---|---|
| `connect` | `connect() -> NodeInfo` | opens the socket, sends HELLO, returns the satellite's `NodeInfo` with `host` and `port` filled in from the constructor |
| `close` | `close() -> None` | idempotent |
| `is_connected` (property) | `bool` | |
| `ping` | `ping() -> float` | one PING with 8 bytes; returns the round trip in milliseconds |
| `stats` | `stats() -> dict` | |
| `load_expert` | `load_expert(model_hash: str, blob: ExpertBlob, persist: bool) -> dict` | returns the `LOAD_OK` fields |
| `have` | `have(model_hash: str) -> tuple[list[ExpertKey], list[ExpertKey]]` | `(in_ram, on_disk)` |
| `load_cached` | `load_cached(model_hash: str, keys: list[ExpertKey]) -> dict` | |
| `unload` | `unload(model_hash: str, keys: list[ExpertKey] or None) -> dict` | |
| `call` | `call(model_hash: str, items: list[ExpertCallItem]) -> list[ExpertCallItem]` | one EXPERT_CALL; returns the results in the same order |
| `bytes_sent`, `bytes_received` (properties) | `int` | running totals including headers |

`load_cached` sends at most `LOAD_CACHED_BATCH` keys per request and makes as many requests as needed. Keys that arrive in JSON as two-element lists are returned as `ExpertKey` tuples.

Failure rules for every method: a timeout, a socket error, a `WireError` or a reply whose `request_id` or type is not the expected one closes the socket and raises `NodeUnavailable(message, node_id)`. An `ERROR` frame raises `RemoteError` and leaves the connection open. If the client is not connected when a method is called, it tries `connect()` once first.

### `ecc/net/cluster.py`

**`ClusterClient()`**. The set of satellites the dispatcher can call.

| Method | Signature | Behaviour |
|---|---|---|
| `add` | `add(node_id: str, client: SatelliteClient) -> None` | |
| `remove` | `remove(node_id: str) -> None` | closes that client |
| `node_ids` | `node_ids() -> list[str]` | |
| `get` | `get(node_id: str) -> SatelliteClient` | raises `NodeUnavailable` for an unknown id |
| `call_many` | `call_many(model_hash: str, calls: dict[str, list[ExpertCallItem]]) -> dict[str, list[ExpertCallItem] or EccError]` | sends each node its items at the same time (one worker thread per node; with a single node, calls it directly on the caller's thread). Never raises for a node failure: that node's value in the result is the `NodeUnavailable` or `RemoteError` instance |
| `close` | `close() -> None` | closes every client and the thread pool |

### `ecc/net/push.py`

| Name | Signature | Behaviour |
|---|---|---|
| `PushProgress` | frozen dataclass: `node_id`, `done_count`, `total_count`, `bytes_sent`, `status` (`"pushing"`, `"done"`, `"failed"`), `message` | handed to the progress callback |
| `push_experts` | `push_experts(client: SatelliteClient, node_id: str, reader: ExpertReader, keys: list[ExpertKey], on_progress: Callable[[PushProgress], None], persist: bool = True) -> PushProgress` | makes the satellite hold exactly `keys` for this model. First asks `have`. Keys the satellite has in RAM that are not wanted any more are unloaded (otherwise a second launch with a different placement would run into the budget). Wanted keys already in RAM are skipped; wanted keys on the satellite's disk are loaded with `load_cached`; the rest are read from the model file and sent one `LOAD_EXPERT` at a time. Calls `on_progress` after every expert. Returns the final progress; a failure returns status `"failed"` with the error text instead of raising |
| `push_placement` | `push_placement(cluster: ClusterClient, placement: Placement, reader: ExpertReader, on_progress: Callable[[PushProgress], None]) -> dict[str, PushProgress]` | runs `push_experts` for every satellite in the placement at the same time, one thread per node. The master's own experts and the disk experts are not its business |

### `ecc/net/registry.py`

**`NodeRegistry(master_info: NodeInfo, poll_interval_s: float = NODE_POLL_INTERVAL_S)`**. The master's list of nodes and the one place that knows who is online. The method `poll_once() -> None` does one poll cycle; the poll thread calls it in a loop, and checks call it directly.

| Method | Signature | Behaviour |
|---|---|---|
| `add_peer` | `add_peer(host: str, port: int) -> NodeInfo` | opens two connections to the satellite: a data connection, whose client goes into `cluster` and carries expert calls and weight pushes, and a control connection that the registry keeps for itself for pings and stats. (With one shared connection, a stats request from the poll thread would make an expert call wait.) Says HELLO on both, measures the round-trip time on the control connection (median of `PING_SAMPLES` pings), detects the link type, keeps the `budget_bytes` the satellite reported in `HELLO_OK`, and stores the node. Adding the same host and port again replaces the old connections and keeps the node's position. Raises `NodeUnavailable` if it cannot connect |
| `remove` | `remove(node_id: str) -> None` | closes both connections |
| `nodes` | `nodes() -> list[NodeInfo]` | copies; the master first, then satellites in the order they were first added. The order never changes while a node stays in the registry, because placements refer to nodes by position |
| `get` | `get(node_id: str) -> NodeInfo` | |
| `set_budget` | `set_budget(node_id: str, budget_bytes: int) -> None` | changes the number the planner uses. For a satellite it may only be lowered: a value above the budget the satellite reported raises `ValueError`, because the satellite enforces its own limit. The poll copies `ram_available_bytes`, `experts_loaded` and `expert_bytes_loaded` from `STATS_OK` and never touches `budget_bytes` |
| `cluster` (property) | `ClusterClient` | |
| `subscribe` | `subscribe(callback: Callable[[list[NodeInfo]], None]) -> None` | called from the poll thread whenever any node's fields changed |
| `start` / `stop` | | start or stop the poll thread: every `NODE_POLL_INTERVAL_S` it refreshes each satellite's stats and round-trip time over the control connection, marks a node `"offline"` when that raises `NodeUnavailable`, and tries to reconnect offline nodes (both connections) |
| `report_failure` | `report_failure(node_id: str) -> None` | called by the app when an expert call to that node failed: marks it `"offline"` at once instead of waiting for the next poll, and notifies subscribers |

### `ecc/net/discovery.py` and `ecc/net/netinfo.py`

| Name | Signature | Behaviour |
|---|---|---|
| `Advertiser` | `Advertiser(node_info: NodeInfo, port: int)`, `start()`, `stop()` | announces the satellite by mDNS under `SERVICE_TYPE`; the instance name is the satellite's node id; text records `id`, `name`, `proto`. `start()` raises `EccError` when mDNS cannot start on this machine. The `satellite` mode advertises unless `--no-mdns` is passed |
| `Browser` | `Browser(on_found: Callable[[str, int, dict], None], on_lost: Callable[[str], None])`, `start()`, `stop()` | calls `on_found(host, port, text_records)` for every satellite seen, `on_lost(node_id)` when one disappears |
| `attach_browser` | `attach_browser(registry: NodeRegistry) -> Browser` | starts a browser that adds every satellite it finds to the registry with `add_peer`, skipping ones already known. Never raises: if mDNS cannot start it logs one line and returns a stopped browser |
| `detect_link_type` | `detect_link_type(peer_host: str) -> str` | finds the local network interface whose subnet contains the peer address and classifies it as one of the link types in `03-CONTRACT-COMMON.md`; `"loopback"` for `127.*`; `"unknown"` when unsure |
| `local_addresses` | `local_addresses() -> list[tuple[str, str, str]]` | `(interface name, IPv4 address, link type)` for every interface that is up, best link first (thunderbolt, ethernet, wifi) |

## 9. The satellite's disk cache: `ecc/net/disk_cache.py`

A satellite saves each expert it is sent so that the next launch needs no transfer.

- Folder: `data_dir()/cache/<model_hash>/`.
- One file per expert named `L<layer>_E<expert>.ecx` with the numbers zero-padded to 4 digits, for example `L0003_E0017.ecx`.
- File content: exactly the `LOAD_EXPERT` payload of section 5 with the persist byte set to 0. Reading a file back therefore uses `decode_load_expert`.
- A file is written under a temporary name in the same folder and then renamed, so a crash never leaves a half-written file under the final name.

| Name | Signature | Behaviour |
|---|---|---|
| `DiskCache` | `DiskCache(root: Path)` | |
| `save` | `save(model_hash: str, blob: ExpertBlob) -> None` | |
| `load` | `load(model_hash: str, key: ExpertKey) -> ExpertBlob` | raises `RemoteError` with code `NOT_CACHED` if absent or the file size is wrong |
| `keys` | `keys(model_hash: str) -> list[ExpertKey]` | parsed from file names, sorted |
| `bytes_used` | `bytes_used() -> int` | |
