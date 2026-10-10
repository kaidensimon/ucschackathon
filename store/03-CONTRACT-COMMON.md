# 03 - Contract: common pieces

Owner of everything in this file: A1 (`ecc/common/`, `ecc/__main__.py`, `checks/run_all.py`). Every other agent imports these and never edits them. If you need a change here, post an ASK to A1.

## 1. Settings: `ecc/common/settings.py`

Module-level constants and two small functions. Never imports torch.

| Name | Value | Meaning |
|---|---|---|
| `PROTO_VERSION` | 1 | wire protocol version |
| `WIRE_MAGIC` | the 4 bytes `ECC1` | first bytes of every frame |
| `MAX_PAYLOAD_BYTES` | 268435456 (256 MiB) | largest frame payload accepted |
| `DEFAULT_SATELLITE_PORT` | 7700 | TCP port a satellite listens on |
| `DEFAULT_UI_PORT` | 7860 | HTTP port of the master's UI |
| `CONNECT_TIMEOUT_S` | 3.0 | opening a TCP connection |
| `CALL_TIMEOUT_S` | 15.0 | waiting for any reply |
| `NODE_POLL_INTERVAL_S` | 2.0 | how often the master refreshes a node's stats and round-trip time |
| `PING_SAMPLES` | 5 | pings per round-trip measurement; the median is reported |
| `DEFAULT_BUDGET_FRACTION` | 0.8 | the budget a process gives itself at start when no `--budget-gb` is passed: this times the RAM available at that moment. Each node computes its own budget and reports it; nobody computes it for another node |
| `LOAD_CACHED_BATCH` | 8 | most keys in one `LOAD_CACHED` request, so that no reply takes longer than the call timeout |
| `MASTER_OVERHEAD_BYTES` | 1610612736 (1.5 GiB) | RAM the master process needs besides tensors |
| `SATELLITE_OVERHEAD_BYTES` | 805306368 (0.75 GiB) | the same for a satellite |
| `DEFAULT_CONTEXT_LEN` | 4096 | context length used for key-value cache sizing |
| `DEFAULT_WIRE_DTYPE` | `"float16"` | activation precision on the wire; checks use `"float32"` |
| `MIGRATE_INTERVAL_S` | 0.25 | how often the migrator looks for a hot expert |
| `MIGRATE_MIN_HEAT` | 4.0 | heat an expert needs before it is loaded into the master's RAM |
| `HEAT_DECAY` | 0.98 | every expert's heat is multiplied by this once per generated token |
| `STATS_INTERVAL_S` | 0.5 | how often stats and heat events are sent while generating |
| `SERVICE_TYPE` | `"_ecc._tcp.local."` | mDNS service type |

Functions:

| Name | Returns | Behaviour |
|---|---|---|
| `data_dir()` | `Path` | the folder named by the environment variable `ECC_HOME` if it is set, otherwise `~/.ecc`. Creates it if missing |
| `local_node_id()` | `str` | reads `data_dir()/node_id`; if the file is missing, writes a new id made of the lower-cased host name, a dash and 6 random hex characters, and returns it. The same machine always returns the same id |

## 2. Errors: `ecc/common/errors.py`

One base class and seven subclasses. Each takes a message string first; three take extra arguments after it and keep them as attributes of the same name.

| Class | Parent | Constructor | Raised when |
|---|---|---|---|
| `EccError` | `Exception` | `EccError(message)` | base of all project errors |
| `WireError` | `EccError` | `WireError(message)` | a frame is malformed: bad magic, payload too large, connection closed in the middle of a frame |
| `ConnectionClosed` | `WireError` | `ConnectionClosed(message)` | the other side closed the connection cleanly between frames |
| `RemoteError` | `EccError` | `RemoteError(message, code, experts=None)`; `code: str`; `experts: list[ExpertKey]`, `None` becomes an empty list | a satellite answered with an ERROR frame |
| `NodeUnavailable` | `EccError` | `NodeUnavailable(message, node_id)`; `node_id: str` is the satellite's id, or the text `host:port` when HELLO has not answered yet | a node cannot be reached, timed out or dropped the connection |
| `ModelFileError` | `EccError` | `ModelFileError(message)` | a model folder is missing something or a tensor has the wrong shape or dtype |
| `PlacementError` | `EccError` | `PlacementError(message, violations)`; `violations: list[str]` | a placement does not fit or has the wrong shape |
| `EngineError` | `EccError` | `EngineError(message)` | the engine is used in the wrong state (no model, already generating) |

## 3. Logging: `ecc/common/log.py`

`get_logger(name: str) -> logging.Logger`. The first call configures the root logger once: output to stderr, format `HH:MM:SS.mmm LEVEL name: message`, level taken from the environment variable `ECC_LOG` (default `INFO`). Later calls only return `logging.getLogger(name)`.

## 4. Dtype table: `ecc/common/dtypes.py`

The only place that knows how the four spellings of a dtype relate. It must not import torch at module level (the network and placement code import this module without torch); the one function that returns a torch dtype imports torch inside itself.

| Code (u8 on the wire) | Name (our string) | safetensors string | Bytes per element | numpy | torch |
|---|---|---|---|---|---|
| 1 | `float16` | `F16` | 2 | `numpy.float16` | `torch.float16` |
| 2 | `float32` | `F32` | 4 | `numpy.float32` | `torch.float32` |
| 3 | `bfloat16` | `BF16` | 2 | none (numpy has no such type) | `torch.bfloat16` |

| Function | Returns | Notes |
|---|---|---|
| `dtype_code(name: str)` | `int` | raises `ValueError` naming the bad value for anything not in the table |
| `dtype_name(code: int)` | `str` | same |
| `dtype_itemsize(name: str)` | `int` | 2 or 4 |
| `dtype_from_safetensors(st_name: str)` | `str` | `"BF16"` gives `"bfloat16"`; any other string not in the table raises `ValueError` |
| `numpy_dtype(name: str)` | a numpy dtype | raises `ValueError` for `bfloat16` |
| `torch_dtype(name: str)` | a torch dtype | imports torch inside the function |

Activations on the wire use only codes 1 and 2. Expert weights use codes 1, 2 and 3.

## 5. Types: `ecc/common/types.py`

Never imports torch or numpy.

**`ExpertKey`**: a named tuple `(layer: int, expert: int)`, both from 0.

**`ExpertBlob`**: a frozen dataclass. One expert's three weight matrices exactly as stored in the model file, as raw bytes. It is what the expert reader returns, what travels in a `LOAD_EXPERT` message and what a satellite saves to disk.

| Field | Type | Meaning |
|---|---|---|
| `layer` | `int` | |
| `expert` | `int` | |
| `dtype` | `str` | our dtype name of the bytes: `float16`, `float32` or `bfloat16` |
| `hidden_size` | `int` | `H` |
| `intermediate_size` | `int` | `I` |
| `gate_proj` | `bytes` | shape `(I, H)`, row-major, little-endian |
| `up_proj` | `bytes` | shape `(I, H)` |
| `down_proj` | `bytes` | shape `(H, I)` |

Property `nbytes`: the three lengths added. Method `validate()`: raises `ValueError` unless each byte string has exactly `I * H * itemsize` bytes.

**Allowed strings**

| Field | Allowed values |
|---|---|
| role | `"master"`, `"satellite"` |
| status | `"online"`, `"offline"` |
| link_type | `"loopback"`, `"thunderbolt"`, `"ethernet"`, `"wifi"`, `"unknown"` |
| device | `"cpu"`, `"cuda"`, `"mps"` |
| compute_dtype | `"float32"`, `"float16"`, `"bfloat16"` |

**`NodeInfo`**: a dataclass (not frozen; the registry updates it). Fields in this order:

| Field | Type | Meaning |
|---|---|---|
| `node_id` | `str` | for the master: `local_node_id()`. For a satellite: `local_node_id()`, a dash, and the port it listens on (for example `lab-pc-3fa9c1-7701`), so that several satellites on one machine have different ids |
| `name` | `str` | display name, by default the host name |
| `role` | `str` | see table above |
| `host` | `str` | IP address the master uses to reach it; `"127.0.0.1"` for the master itself |
| `port` | `int` | satellite TCP port; 0 for the master |
| `device` | `str` | where it computes |
| `compute_dtype` | `str` | precision it computes and stores experts in |
| `ram_total_bytes` | `int` | |
| `ram_available_bytes` | `int` | last reported |
| `budget_bytes` | `int` | most RAM this node may use for this app |
| `link_type` | `str` | how the master reaches it |
| `rtt_ms` | `float` or `None` | median round-trip time; `None` until measured; `0.0` for the master |
| `status` | `str` | |
| `experts_loaded` | `int` | experts in its RAM now |
| `expert_bytes_loaded` | `int` | bytes those experts take |

Methods: `to_json() -> dict` (every field, same names) and the class method `from_json(data: dict) -> NodeInfo` (raises `ValueError` naming a missing field or a value outside the allowed strings).

**`Placement`**: a dataclass.

| Field | Type | Meaning |
|---|---|---|
| `node_ids` | `list[str]` | index 0 is always the master's node id |
| `owner` | `list[list[int]]` | `owner[layer][expert]` is an index into `node_ids`, or `-1` meaning disk |
| `context_len` | `int` | context length the memory report was computed for |

Methods:

| Method | Returns | Behaviour |
|---|---|---|
| `num_layers` (property) | `int` | `len(owner)` |
| `num_experts` (property) | `int` | `len(owner[0])` |
| `experts_of(node_index: int)` | `list[ExpertKey]` | every key owned by that index, in layer then expert order; `-1` gives the disk experts |
| `counts()` | `list[int]` | experts per node index, same length as `node_ids` |
| `disk_count()` | `int` | number of `-1` entries |
| `validate_shape(num_layers: int, num_experts: int)` | `None` | raises `PlacementError` if the grid has the wrong size, rows of unequal length, or an index outside `-1 .. len(node_ids) - 1` |
| `to_json()` / `from_json(data)` | `dict` / `Placement` | keys `node_ids`, `owner`, `context_len` |
| class method `all_on(node_ids, num_layers, num_experts, node_index, context_len)` | `Placement` | every expert on one index; used by checks |

## 6. Mode dispatcher: `ecc/__main__.py`

`python -B -m ecc <mode> [arguments]`. The dispatcher holds one table from mode name to a module path and function name. It imports that module only when the mode is chosen, calls the function with the remaining arguments as a list of strings, and exits with the integer it returns.

| Mode | Module | Function |
|---|---|---|
| `make-tiny` | `ecc.engine.tiny_model` | `main` |
| `inspect` | `ecc.modelfile.inspect` | `main` |
| `satellite` | `ecc.net.satellite_server` | `main` |
| `chat` | `ecc.engine.chat` | `main` |
| `master` | `ecc.app` | `main` |
| `mock-ui` | `ecc.api.server` | `main_mock` |
| `bench-net` | `ecc.net.bench` | `main` |
| `doctor` | `ecc.net.doctor` | `main` |

Every such function has the signature `main(argv: list[str]) -> int`, parses `argv` with `argparse`, and returns 0 on success. If the module for a mode does not exist yet, the dispatcher prints `mode '<name>' is not built yet` and exits with code 2. With no mode or an unknown mode it prints the list of modes and exits with code 2. Because of this table nobody but A1 ever needs to edit `ecc/__main__.py`.

## 7. Checks: `checks/run_all.py`

`python -B -m checks.run_all [prefix ...]` finds every file `checks/check_*.py`, sorted by name, and runs each as `python -B -m checks.<name>` in its own process (the same interpreter, `sys.executable`) with a 120 second limit, four at a time (flag `--jobs`, default 4). With prefixes it runs only the files whose name starts with `check_<prefix>` (for example `python -B -m checks.run_all net migrate`). Before starting it builds the tiny model once if `ecc.engine.tiny_model` can be imported, so that parallel checks do not build it at the same moment. It prints one line per file (`PASS`, `FAIL` or `TIMEOUT`, the file name, the seconds taken), then a summary line with the total time, and exits with code 1 if any file did not pass. Late in the project a full run takes a few minutes: start it with a command time limit of at least 600 seconds. On a failure it prints that file's last 15 output lines. There is no `__init__.py` in `checks/`. The rules a check script follows are in `02-CODE-RULES.md`, rules 27 to 30.

## 8. Which device and precision a node computes in

A node picks its device and its compute dtype once, when it starts, and never changes them. Two command-line flags, the same on `satellite`, `master` and `chat`:

| Flag | Values | Default |
|---|---|---|
| `--device` | `auto`, `cpu`, `cuda`, `mps` | `auto`: `cuda` if available, otherwise `mps` if available, otherwise `cpu` |
| `--dtype` | `auto`, `float32`, `float16`, `bfloat16` | `auto`: taken from the device by the table below |

| Device | compute dtype when `--dtype` is `auto` | Why |
|---|---|---|
| `cpu` | `float32` | fastest on a CPU and exact; costs twice the memory of the 16-bit types |
| `mps` | `float16` | Apple GPUs handle 16-bit floats; bfloat16 needs a recent macOS |
| `cuda` | `float16` | |

A human with a small laptop and no usable GPU passes `--dtype bfloat16`: 16-bit computation works on a CPU, a few times slower, and halves the memory. Every check and every exactness test uses device `cpu` and dtype `float32` explicitly.

Weights arrive in the model file's stored dtype (the real models store `bfloat16`) and are converted to the node's compute dtype when loaded. Memory math therefore uses the node's compute dtype, not the stored dtype: an expert costs twice as much RAM on a `float32` node as on a 16-bit node. The function `pick_device(preferred_device: str, preferred_dtype: str = "auto") -> tuple[str, str]` in `ecc/common/expert_math.py` returns `(device, compute_dtype)` by these rules.
