# ROUND 01 - instructions for all three agents

One file, three parts. Your human told you which agent you are. Find the heading **AGENT 1**, **AGENT 2** or **AGENT 3** that is yours and do only that part. Do not read or do the other two parts.

Every agent, before its part:

1. Read `AGENTS.md` and do its section 3 (pull, read `AGENT_CHAT.md`, answer what is addressed to you).
2. Read `store/01-OVERVIEW.md` and `store/02-CODE-RULES.md`.
3. If your part has two tasks, do them in the order written, and save after each.
4. When a task is finished and its check passes, save as `AGENTS.md` section 5 says. Start the PUSHED entry with `DONE <task id>:`.
5. When your whole part is done, tell your human: `Agent <n>: round 01 done.` Then stop. Do not start another round.
6. If something your part needs from another agent is not pushed yet, do what the task's "Before you start" section says, then tell your human what you are waiting for.

| Agent | Tasks in this round |
|---|---|
| Agent 1 (A1) | `R01-A1a-skeleton`, then `R01-A1b-common-types` |
| Agent 2 (A2) | `R01-A2-wire-frames` |
| Agent 3 (A3) | `R01-A3-tensor-index` |

---

# AGENT 1 (A1) - round 01

You are A1. This part has 2 tasks. Stop reading at the next line that starts with `# AGENT` or `# HUMANS`.

## Task 1 of 2: R01-A1a-skeleton

| | |
|---|---|
| Agent | A1 |
| Round | 01, first of two files (`R01-A1b-common-types` follows) |
| You create | `requirements.txt`, `ecc/__init__.py`, `ecc/common/__init__.py`, `ecc/common/settings.py`, `ecc/common/errors.py`, `ecc/common/log.py`, `ecc/__main__.py`, `checks/run_all.py`, `checks/check_common_skeleton.py` |
| You change | nothing |
| Needs | nothing |
| Size | 9 files, about 330 lines of code, about 260 lines of check |


### 1. Outcome
The repo gets its skeleton: the pinned dependency list, the `ecc` package with settings, errors and logging, the mode dispatcher, and the runner that is the project's Check. A2 and A3 can run nothing until this is pushed. So you save twice: at the Save point in section 4, and again when the check passes.

Done means: `python -B -m checks.check_common_skeleton` prints `OK check_common_skeleton.py (20 checks)` as its last line.

### 2. Read first
- `store/01-OVERVIEW.md` and `store/02-CODE-RULES.md`.
- `store/03-CONTRACT-COMMON.md` sections 1, 2, 3, 6 and 7. The tables below are copied from them. If a table here differs, 03 wins (code rule 4).
- Do not open other files in `store/`.

### 3. Before you start
1. Run `python -c "import sys; print(sys.prefix)"`. It must print the project environment (the path contains `.ecc`). If not, stop and tell your human. Never install anything.
2. Needs: nothing. This task imports only the standard library. One input file, `store/PINS-requirements.txt`, must exist. If it is missing: build every other file, do not make `requirements.txt` any other way, ask your human for the file, put that on your `waiting on` line and say it in your PUSHED entry.

### 4. Build
Write the files in this order. Every Python file follows code rules 6 to 15.

#### 4.1 `requirements.txt`, `ecc/__init__.py`, `ecc/common/__init__.py`
1. `requirements.txt`: copy it, never retype it. PowerShell: `Copy-Item store/PINS-requirements.txt requirements.txt`. Other shells: `cp store/PINS-requirements.txt requirements.txt`. The copy equals the source byte for byte. Do not open it in an editor. You do not install it: installing is your human's step.
2. `ecc/__init__.py`: docstring, future import, one constant `__version__` with the value `"0.1.0"`. No other import.
3. `ecc/common/__init__.py`: docstring and future import only. It imports no submodule.

#### 4.2 `ecc/common/settings.py`
Twenty constants, written in the order of 03 section 1 (down the left pair of columns, then down the right pair). A value with a decimal point is a `float`, `WIRE_MAGIC` is `bytes`, the two quoted values are `str`, every other value is an `int`.

| Name | Value | Name | Value |
|---|---|---|---|
| `PROTO_VERSION` | 1 | `LOAD_CACHED_BATCH` | 8 |
| `WIRE_MAGIC` | the 4 bytes `ECC1` | `MASTER_OVERHEAD_BYTES` | 1610612736 |
| `MAX_PAYLOAD_BYTES` | 268435456 | `SATELLITE_OVERHEAD_BYTES` | 805306368 |
| `DEFAULT_SATELLITE_PORT` | 7700 | `DEFAULT_CONTEXT_LEN` | 4096 |
| `DEFAULT_UI_PORT` | 7860 | `DEFAULT_WIRE_DTYPE` | `"float16"` |
| `CONNECT_TIMEOUT_S` | 3.0 | `MIGRATE_INTERVAL_S` | 0.25 |
| `CALL_TIMEOUT_S` | 15.0 | `MIGRATE_MIN_HEAT` | 4.0 |
| `NODE_POLL_INTERVAL_S` | 2.0 | `HEAT_DECAY` | 0.98 |
| `PING_SAMPLES` | 5 | `STATS_INTERVAL_S` | 0.5 |
| `DEFAULT_BUDGET_FRACTION` | 0.8 | `SERVICE_TYPE` | `"_ecc._tcp.local."` |

| Function | Returns | Behaviour |
|---|---|---|
| `data_dir()` | `Path` | the folder named by the environment variable `ECC_HOME` if it is set, otherwise `~/.ecc`. Creates it if missing |
| `local_node_id()` | `str` | reads `data_dir()/node_id`; if the file is missing, writes a new id made of the lower-cased host name, a dash and 6 random hex characters, and returns it. The same machine always returns the same id |

1. Each constant has a short comment taken from the Meaning column of 03 section 1.
2. `data_dir()` reads `ECC_HOME` on every call, never at import. An empty value counts as not set.
3. `~` is `Path.home()`, read on every call. The folder and its missing parents are created. An existing folder is not an error.
4. `local_node_id()` reads the file as UTF-8 text and strips white space. A missing or empty file means: build the id, write it without a newline, return it. Host name: `socket.gethostname()` lower-cased. Random part: `secrets.token_hex(3)`.
5. Nothing is kept in a module variable. Both functions go to the environment and the disk on every call.

#### 4.3 `ecc/common/errors.py`
| Class | Parent | Constructor | Raised when |
|---|---|---|---|
| `EccError` | `Exception` | `EccError(message)` | base of all project errors |
| `WireError` | `EccError` | `WireError(message)` | a frame is malformed: bad magic, payload too large, connection closed in the middle of a frame |
| `ConnectionClosed` | `WireError` | `ConnectionClosed(message)` | the other side closed the connection cleanly between frames |
| `RemoteError` | `EccError` | `RemoteError(message, code, experts=None)`; `code: str`; `experts: list[ExpertKey]`, `None` becomes an empty list | a satellite answered with an ERROR frame |
| `NodeUnavailable` | `EccError` | `NodeUnavailable(message, node_id)`; `node_id: str` | a node cannot be reached, timed out or dropped the connection |
| `ModelFileError` | `EccError` | `ModelFileError(message)` | a model folder is missing something or a tensor has the wrong shape or dtype |
| `PlacementError` | `EccError` | `PlacementError(message, violations)`; `violations: list[str]` | a placement does not fit or has the wrong shape |
| `EngineError` | `EccError` | `EngineError(message)` | the engine is used in the wrong state (no model, already generating) |

1. Every constructor passes only `message` to its parent, so `str(error)` is the message.
2. The extra arguments are kept as attributes of the same name: `code`, `experts`, `node_id`, `violations`.
3. `experts=None` becomes a new empty list in each instance.
4. `ExpertKey` is needed for the type hint only. Import it from `ecc.common.types` under `if typing.TYPE_CHECKING:` (code rule 14a). That file arrives with R01-A1b. `errors.py` imports nothing else from `ecc`.

#### 4.4 `ecc/common/log.py`
`get_logger(name: str) -> logging.Logger`. The first call configures the root logger once: output to stderr, format `HH:MM:SS.mmm LEVEL name: message`, level taken from the environment variable `ECC_LOG` (default `INFO`). Later calls only return `logging.getLogger(name)`.

1. Configuring means: add one `logging.StreamHandler` on `sys.stderr` to the root logger and set the root logger's level. Do not call `logging.basicConfig`.
2. The handler gets the name `ecc` (`set_name`). "Already configured" means the root logger has a handler with that name. No module-level flag (code rule 13). The handler name is private to this task.
3. Formatter: format text `%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s`, date format `%H:%M:%S`. A line looks like `14:03:07.215 INFO ecc.net.wire: listening on port 7700`.
4. `ECC_LOG` is read at the first call and upper-cased. Allowed: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Missing, empty or any other value gives `INFO`.

#### 4.5 `ecc/__main__.py`
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

`python -B -m ecc <mode> [arguments]`. Every mode function has the signature `main(argv: list[str]) -> int`. Private to this task: the constant `MODES: dict[str, tuple[str, str]]` (mode to module path and function name, in table order) and this file's own function `main(argv: list[str]) -> int`. The file ends with a `__name__ == "__main__"` guard that gives `main(sys.argv[1:])` to `sys.exit`. Importing `ecc.__main__` as a module runs nothing. Rules for this file's `main`:

1. `argv[0]` is the mode. `argv[1:]` goes to the mode function unchanged. No `argparse` in this file. All output is `print` to stdout.
2. No mode: print the mode list, return 2. The mode list is the line `usage: python -B -m ecc <mode> [arguments]`, then one line per mode in table order: two spaces and the mode name.
3. Unknown mode: print `unknown mode '<name>'`, then the mode list, return 2.
4. Known mode: import its module with a call written as `importlib.import_module(module_path)`, at this point and nowhere earlier. The file has no `ecc` import at the top.
5. If that call raises `ModuleNotFoundError` whose `name` is the module path or a dotted parent of it (for `ecc.net.doctor`: `ecc.net.doctor`, `ecc.net` or `ecc`): print `mode '<name>' is not built yet`, return 2.
6. Any other error from the import is not caught: a `ModuleNotFoundError` with another `name` (such as `torch` or `ecc.ne`), any other `ImportError`. Its traceback must show.
7. The module has no attribute with the function's name: same line and return value as rule 5.
8. Otherwise call the function with `argv[1:]` and return what it returns.

#### 4.6 `checks/run_all.py`
`python -B -m checks.run_all [prefix ...] [--jobs N]`. Same shape as 4.5: a `main(argv: list[str]) -> int` and a `__name__` guard. No `__init__.py` in `checks/`.
1. Arguments by `argparse`: zero or more prefixes; `--jobs`, an integer, default 4.
2. Files: every `check_*.py` in the folder that holds `run_all.py`, sorted by name. With prefixes: only files whose name starts with `check_<prefix>` for at least one prefix (`python -B -m checks.run_all net migrate`).
3. If at least one file is selected: call `importlib.import_module("ecc.engine.tiny_model")` and then its `ensure_tiny_model() -> Path` once, before any check starts. A `ModuleNotFoundError` whose `name` is `ecc.engine` or `ecc.engine.tiny_model` means skip this step silently. Catch nothing else.
4. Each file runs as `<sys.executable> -B -m checks.<file name without .py>` in its own process. Working folder: the parent of `checks/`. Limit: 120 seconds. Stdout and stderr are captured together as text with `encoding="utf-8"` and `errors="replace"`.
5. `--jobs` files run at the same time: a `ThreadPoolExecutor` in a `with` block, with `thread_name_prefix` set.
6. Result word: `PASS` for exit code 0, `TIMEOUT` when the limit is hit (the child is killed), `FAIL` for anything else.
7. One line per file, in sorted order: result word, file name, seconds taken with one decimal and the letter `s`. Example: `PASS check_net_wire.py 1.3s`.
8. Under a `FAIL` or `TIMEOUT` line: that file's last 15 output lines, each after four spaces. On `TIMEOUT` the captured output can be `None` or bytes: `None` is empty, bytes are decoded as in rule 4.
9. Last line: `DONE <p> passed, <f> failed, <t> timed out in <seconds>s`. The seconds are the total time, one decimal. The exact text of the lines in rules 7 to 9 is private to this task.
10. Exit code 1 if any file is `FAIL` or `TIMEOUT`, otherwise 0. No file selected: only the `DONE` line with three zeros, exit code 0.

Save point: these three must work. `python -B -c "import ecc.common.settings, ecc.common.errors, ecc.common.log"` prints nothing. `python -B -m ecc` prints the mode list. `python -B -m checks.run_all` ends with a `DONE` line. Then save as AGENTS.md section 5 says, with a PUSHED entry to all that says the check script is not written yet. Then write the check.

### 5. Traps
- `README.md`, `ecc/common/dtypes.py`, `ecc/common/types.py` and `checks/check_common_basics.py` are R01-A1b. `pick_device` is R02-A1. Do not create them and do not import them. Do not edit `AGENTS.md` or anything in `store/`. Do not run `pip`.
- `errors.py`: a plain import of `ExpertKey` fails today and becomes a circular import later. Only under `typing.TYPE_CHECKING`.
- `RemoteError`: never write the default as an empty list in the signature. All instances would share it.
- `__main__.py`: never catch `ImportError` as a whole. A missing `torch` inside a module that exists would then print "not built yet" and hide the real fault. No `argparse` either: `python -B -m ecc chat --help` must reach the chat mode's own parser.
- `log.py`: the default `asctime` prints a date and a comma. Use the two format texts of 4.4 rule 3. Stderr, never stdout.
- `run_all.py`: `sys.executable`, never the word `python`. Without `encoding="utf-8"` Windows fails on some output bytes.

### 6. Check: `checks/check_common_skeleton.py`
The file name is private to this task. Setup: save a copy of `os.environ`; make one temporary folder `T`; set `ECC_HOME` to `T/home1` (not created); delete any leftover `checks/check_zzzprobe*.py`. Children run as `sys.executable -B ...` with the repo root as working folder, stdout and stderr captured apart as text. Compare paths after `Path.resolve()`. "The patch" is `unittest.mock.patch.object(importlib, "import_module", ...)`; `main` is `ecc.__main__.main`; capture its prints with `contextlib.redirect_stdout`. At the end restore the environment and delete `T`.

| # | PASS name | What must be true |
|---|---|---|
| 1 | `requirements copy` | `requirements.txt` and `store/PINS-requirements.txt` hold the same bytes; exactly 65 lines contain `==` |
| 2 | `version` | `ecc.__version__` is `"0.1.0"` |
| 3 | `light imports` | after importing `ecc.common`, `ecc.common.settings`, `ecc.common.errors`, `ecc.common.log`, `ecc.__main__`: none of `torch`, `numpy`, `ecc.common.types` is in `sys.modules` |
| 4 | `settings values` | all 20 constants have the value and the exact type of 4.2 (floats within 1e-9); `MAX_PAYLOAD_BYTES` is `256 * 1024**2`; `MASTER_OVERHEAD_BYTES` is `3 * 1024**3 // 2` and twice `SATELLITE_OVERHEAD_BYTES` |
| 5 | `data_dir env` | `data_dir()` is `T/home1` and that folder now exists; after `ECC_HOME` is changed to `T/home2/deep`, `data_dir()` is that folder and it exists |
| 6 | `data_dir default` | with `HOME` and `USERPROFILE` both set to `T/user`: once with `ECC_HOME` empty and once with it removed, `data_dir()` is `T/user/.ecc` and it exists |
| 7 | `node id` | in a fresh `ECC_HOME`, `local_node_id()` is `socket.gethostname().lower()`, a dash and 6 characters from `0-9a-f`; the file `node_id` there holds exactly that text; a second call returns the same text. In another fresh folder whose `node_id` holds `abc-123456` and a newline, the call returns `abc-123456`. An empty `node_id` file gets a new id written into it |
| 8 | `error tree` | `__bases__` of each of the eight classes is exactly its one parent from 4.3; each class built with the message `m` (plus its extra arguments) gives `str(error)` equal to `m` |
| 9 | `error fields` | `RemoteError("m", "EXPERT_NOT_LOADED")` has that `code` and `experts` equal to `[]`; two such errors hold two different list objects; with a third argument `[(0, 1)]`, `experts` is that list; `NodeUnavailable("m", "127.0.0.1:7700").node_id` and `PlacementError("m", ["a", "b"]).violations` hold what was passed |
| 10 | `log format` | a child with no `ECC_LOG` calls `get_logger("ecc.demo")` three times, logs `hello` at INFO and `quiet` at DEBUG, and prints how many root handlers are named `ecc`. Stdout is `1`. Stderr is one line matching `^\d\d:\d\d:\d\d\.\d\d\d INFO ecc\.demo: hello$` |
| 11 | `log level` | the same child with `ECC_LOG=debug`: stderr has two lines and the second ends with `DEBUG ecc.demo: quiet`. With `ECC_LOG=nonsense`: one line, as in 10 |
| 12 | `modes table` | `list(ecc.__main__.MODES.items())` equals the eight rows of 4.5 in order |
| 13 | `no mode` | child `-m ecc`: exit code 2; stdout has the usage line and all eight mode names |
| 14 | `unknown mode` | child `-m ecc nope`: exit code 2; stdout has `unknown mode 'nope'` and all eight mode names |
| 15 | `lazy import` | with the patch in place, `main([])` and `main(["nope"])` return 2 and the patched function was never called |
| 16 | `dispatch` | the patch returns an object whose `main` records its argument and returns 7: `main(["doctor", "--x", "1"])` returns 7, the record is `["--x", "1"]`, the patch was called once with `"ecc.net.doctor"`. With an object whose `main` returns 1 and `main_mock` returns 5, `main(["mock-ui"])` returns 5 |
| 17 | `not built` | the patch raises `ModuleNotFoundError` with `name="ecc.net.doctor"`, then with `name="ecc.net"`, then returns an object without `main`: each time `main(["doctor"])` returns 2 and prints `mode 'doctor' is not built yet` |
| 18 | `other import errors` | the patch raises `ModuleNotFoundError` with `name="torch"`, then with `name="ecc.ne"`, then `ImportError("boom")`: each time that same error comes out of `main(["doctor"])` |
| 19 | `run_all no match` | child `-m checks.run_all zzznomatch` with the saved environment: exit code 0; stdout is one line starting `DONE 0 passed, 0 failed, 0 timed out in ` |
| 20 | `run_all pass and fail` | write two probe files into `checks/`: `check_zzzprobe_bad.py` prints the 20 lines `line 1` to `line 20` and exits with code 1; `check_zzzprobe_good.py` prints `ok` and exits with code 0. Child `-m checks.run_all zzzprobe --jobs 2` with the saved environment: exit code 1; a stdout line starts `FAIL check_zzzprobe_bad.py `; a later line starts `PASS check_zzzprobe_good.py `; the indented lines `line 6` and `line 20` are there and `line 5` is not; the last line starts `DONE 1 passed, 1 failed, 0 timed out in `. Delete both probe files in a `finally` block |

`TIMEOUT` is not asserted: it would take 120 seconds. Last line printed: `OK check_common_skeleton.py (20 checks)`.

### 7. Verify
1. `python -B -m checks.check_common_skeleton`: 20 `PASS` lines, then `OK check_common_skeleton.py (20 checks)`.
2. `python -B -m ecc`: the usage line and eight mode names. `python -B -m ecc chat`: `mode 'chat' is not built yet`.
3. `python -B -m checks.run_all` with a command time limit of 600 seconds: every file line starts with `PASS`; the last line starts with `DONE` and names 0 failed and 0 timed out. A `FAIL` on a file that is not yours: AGENTS.md section 7. Afterwards `checks/` holds no `check_zzzprobe*.py` file and no `__init__.py`.

### 8. Hand off
- Status lines: `- A1 provides: ecc.common.settings, ecc.common.errors, ecc.common.log per store/03-CONTRACT-COMMON.md sections 1 to 3; env vars ECC_HOME, ECC_LOG` and `- A1 provides: python -B -m ecc <mode> and python -B -m checks.run_all [prefix ...] [--jobs N] per store/03-CONTRACT-COMMON.md sections 6 and 7`.
- PUSHED to all, at the Save point and again at the end. It says: the skeleton files are in; which commands of section 7 you ran and their last lines, or `untested`; what the others do now: pull, then run their own check, because `ecc.common.settings` and `ecc.common.errors` now import; no agent installs anything; `dtypes.py` and `types.py` come with R01-A1b. No `STUB`.
- Next task builds on: R01-A1b adds `dtypes.py` and `types.py` beside these files; R01-A2 and R01-A3 import `settings` and `errors`; every later task runs `checks/run_all.py` and calls `get_logger`.

## Task 2 of 2: R01-A1b-common-types

| | |
|---|---|
| Agent | A1 |
| Round | 01 |
| You create | `ecc/common/dtypes.py`, `ecc/common/types.py`, `README.md`, `checks/check_common_basics.py` |
| You change | nothing |
| Needs | R01-A1a: `ecc/common/settings.py`, `ecc/common/errors.py`, `ecc/common/log.py`, `ecc/__main__.py`, `checks/run_all.py`, `requirements.txt` |
| Size | 4 files: about 250 lines of code, a README of 27 lines, about 280 lines of check |


### 1. Outcome
`ecc/common/dtypes.py` and `ecc/common/types.py` exist as `store/03-CONTRACT-COMMON.md` sections 4 and 5 define them; A2 and A3 import them from round 02 on. `README.md` tells a human how to install, run and check. One check proves all of `ecc.common` and the mode dispatcher, including the files R01-A1a wrote.

Done means: `python -B -m checks.check_common_basics` ends with the line `OK check_common_basics.py (23 checks)`.

### 2. Read first
1. `store/01-OVERVIEW.md` and `store/02-CODE-RULES.md`.
2. `store/03-CONTRACT-COMMON.md` sections 1, 2, 3 and 6: R01-A1a built them, your check calls them.
3. `ecc/common/settings.py`, `ecc/common/errors.py`, `ecc/common/log.py`, `ecc/__main__.py`: the code your check calls.

Do not open other files in `store/`.

### 3. Before you start
1. Run `python -c "import sys; print(sys.prefix)"`. It must print the project environment (the path contains `.ecc`). If not, stop and tell your human. Never install anything.
2. R01-A1a: `python -B -c "import ecc.common.settings, ecc.common.errors, ecc.common.log"` prints nothing, and `ecc/__main__.py`, `checks/run_all.py` and `requirements.txt` exist. If one is missing, do not write it here: tell your human that task `R01-A1a-skeleton` (in the `ROUND` file of its round) must be finished first, and stop. `store/PINS-requirements.txt` must exist too (check row 20 reads it): if it is missing, ask your human for it and build everything else meanwhile.

### 4. Build

#### 4.1 `ecc/common/dtypes.py`

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

Rules:
1. No `import torch` at module level. `import numpy` at module level is allowed.
2. One private module-level constant holds the three rows. All six functions read it. No value is written twice.
3. Every one of the six functions raises `ValueError` for a value that is not in its column. The message contains the bad value and the allowed values.
4. Matching is exact: `"f32"`, `"Float32"`, `"F64"` and code `0` are bad values.
5. `numpy_dtype` returns the dtype object: `numpy.dtype(numpy.float16)` or `numpy.dtype(numpy.float32)`. For `bfloat16` it raises; never map it to `float16`.

#### 4.2 `ecc/common/types.py`
No `import torch` line and no `import numpy` line. It imports `dtype_itemsize` from `ecc.common.dtypes` and `PlacementError` from `ecc.common.errors`.

**`ExpertKey`**: a named tuple `(layer: int, expert: int)`, both from 0.

**`ExpertBlob`**: a frozen dataclass. One expert's three weight matrices exactly as stored in the model file, as raw bytes. Fields in this order: `layer: int`, `expert: int`, `dtype: str` (our dtype name of the bytes: `float16`, `float32` or `bfloat16`), `hidden_size: int` (`H`), `intermediate_size: int` (`I`), `gate_proj: bytes` (shape `(I, H)`, row-major, little-endian), `up_proj: bytes` (shape `(I, H)`), `down_proj: bytes` (shape `(H, I)`). Property `nbytes`: the three lengths added. Method `validate()`: raises `ValueError` unless each byte string has exactly `I * H * itemsize` bytes.

**`NodeInfo`**: a dataclass (not frozen; the registry updates it). Fields in this order, none with a default:

| Field | Type | Meaning and allowed values |
|---|---|---|
| `node_id` | `str` | master: `local_node_id()`. Satellite: `local_node_id()`, a dash, and the port it listens on (for example `lab-pc-3fa9c1-7701`) |
| `name` | `str` | display name, by default the host name |
| `role` | `str` | `"master"`, `"satellite"` |
| `host` | `str` | IP address the master uses to reach it; `"127.0.0.1"` for the master itself |
| `port` | `int` | satellite TCP port; 0 for the master |
| `device` | `str` | `"cpu"`, `"cuda"`, `"mps"` |
| `compute_dtype` | `str` | `"float32"`, `"float16"`, `"bfloat16"` |
| `ram_total_bytes` | `int` | |
| `ram_available_bytes` | `int` | last reported |
| `budget_bytes` | `int` | most RAM this node may use for this app |
| `link_type` | `str` | `"loopback"`, `"thunderbolt"`, `"ethernet"`, `"wifi"`, `"unknown"` |
| `rtt_ms` | `float` or `None` | median round-trip time; `None` until measured; `0.0` for the master |
| `status` | `str` | `"online"`, `"offline"` |
| `experts_loaded` | `int` | experts in its RAM now |
| `expert_bytes_loaded` | `int` | bytes those experts take |

Methods: `to_json() -> dict` (every field, same names) and the class method `from_json(data: dict) -> NodeInfo` (raises `ValueError` naming a missing field or a value outside the allowed strings).

**`Placement`**: a dataclass. Fields in this order: `node_ids: list[str]` (index 0 is always the master's node id), `owner: list[list[int]]` (`owner[layer][expert]` is an index into `node_ids`, or `-1` meaning disk), `context_len: int` (context length the memory report was computed for).

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

Rules:
1. `ExpertKey` is a `typing.NamedTuple`. It equals the plain tuple with the same numbers and works as a dict key.
2. `ExpertBlob.validate()` takes the item size from `dtype_itemsize(self.dtype)`, so an unknown dtype raises `ValueError`. The message names the matrix, the expected byte count and the found byte count.
3. No class validates in its constructor. No `__post_init__`. Callers call `validate()` and `validate_shape()` themselves.
4. `NodeInfo.to_json()` returns exactly the 15 keys in field order. `rtt_ms` stays `None` when it is `None`.
5. `NodeInfo.from_json` checks `role`, `status`, `link_type`, `device` and `compute_dtype` against the allowed values; the message contains the field name and the bad value. For a missing key the message contains the key. Extra keys are ignored. `rtt_ms` stays `None` when null, otherwise becomes a `float`. Nothing else is checked: `host` may be `""`.
6. The allowed values live in one private module-level constant (private to this task).
7. `counts()` does not count `-1`. `experts_of` for an index that owns nothing returns `[]`. With `owner` equal to `[]`: `num_layers` is 0, `num_experts` is 0, `counts()` is all zeros.
8. `validate_shape` collects one sentence per problem, each with the expected and the found value, then raises one `PlacementError(message, violations)`: `violations` is that list, `message` is the sentences joined by `"; "`. Problems: `len(owner)` is not `num_layers`; a row whose length is not `num_experts`; a cell outside `-1 .. len(node_ids) - 1`. With no problem it returns `None`. It never raises `IndexError`.
9. `Placement.to_json` and `from_json` build new lists: changing the dict afterwards does not change the `Placement`. `from_json` with a missing key raises `ValueError` whose message contains the key.
10. `all_on` builds every row as its own list. `node_index` `-1` gives an all-disk placement.

Save point: when `python -B -c "import ecc.common.types"` prints nothing, save as AGENTS.md section 5 says, with `untested` in the PUSHED entry.

#### 4.3 `README.md`
1. At most 30 lines. Line 1 is `# Expert Cache Cluster`.
2. One paragraph with these three sentences: `Expert Cache Cluster (package ecc) runs one Mixture-of-Experts language model that is too big for the RAM of any single laptop. One machine, the master, runs the backbone; the other machines, satellites, hold expert weights in RAM and answer expert calls over TCP. The master moves the experts it uses most into its own RAM while it runs.`
3. `## Install`: the line `Python 3.11, 3.12 or 3.13. A human runs these commands, one per line. The virtual environment is outside the repo.` Then a table with columns System and Commands and these two rows:
   - Windows PowerShell: `python -m venv $HOME\.ecc\venv`, `& $HOME\.ecc\venv\Scripts\Activate.ps1`, `python -m pip install --only-binary=:all: -r requirements.txt`, `python -m pip check`
   - macOS, Linux: `python3 -m venv ~/.ecc/venv`, `source ~/.ecc/venv/bin/activate`, `python -m pip install --only-binary=:all: -r requirements.txt`, `python -m pip check`
4. `## Run`: a table with columns Command and What it does. Copy the first six rows of the Modes table in `store/01-OVERVIEW.md` (`make-tiny` to `mock-ui`). Then `## Check`: the line `python -B -m checks.run_all`. Nothing else in the file.

### 5. Traps
- `[[node_index] * num_experts] * num_layers` makes every row the same list object. Build each row separately. Row 19 tests it.
- `import torch` at the top of `dtypes.py`, `types.py` or the check fails row 1. The check imports torch only inside the function for row 23.
- `ExpertBlob` is frozen. `NodeInfo` and `Placement` are not. `ExpertKey` is a named tuple, not a dataclass. Do not add fields, defaults, public constants or extra public methods. Other agents build these classes by keyword with every field.
- `from_json` must accept `host` `""` and `rtt_ms` null: a satellite's `HELLO_OK` reply sends exactly that.
- The check sets `ECC_HOME` before the first `data_dir()` call. Otherwise it writes into the real `~/.ecc`.
- If row 5, 6, 7, 8, 20 or 22 fails, the fault is in an R01-A1a file. Those files are yours: make the smallest change that matches contract 03 and name it in the PUSHED entry. Never change the row.
- `pick_device` and `ecc/common/expert_math.py` belong to R02-A1. Leave every `__init__.py` as it is. Never run pip.

### 6. Check: `checks/check_common_basics.py`
Setup: make a folder with `tempfile.mkdtemp()` and set `ECC_HOME` to `<temp>/home` (do not create it) before the first `ecc` call. The repo root is the parent of the `checks` folder. No network, no model, no sleep. At the end, also after a failure, delete the temporary folder and ignore a deletion error.
Sample node (rows 12 to 14): `node_id` `"lab-pc-3fa9c1-7701"`, `name` `"lab-pc"`, `role` `"satellite"`, `host` `"127.0.0.1"`, `port` 7701, `device` `"cpu"`, `compute_dtype` `"float32"`, `ram_total_bytes` 17179869184, `ram_available_bytes` 12884901888, `budget_bytes` 8589934592 (8 GiB), `link_type` `"loopback"`, `rtt_ms` 1.5, `status` `"online"`, `experts_loaded` 0, `expert_bytes_loaded` 0. Sample placement (rows 15 to 18): `node_ids` `["m", "s1", "s2"]`, `owner` `[[0, 1, 1, -1], [2, 0, -1, -1]]`, `context_len` 4096.

| # | PASS name | What must be true |
|---|---|---|
| 1 | `no_torch_import` | first row run: after importing `ecc.common.dtypes`, `types`, `settings`, `errors` and `log`, `"torch"` is not in `sys.modules` |
| 2 | `dtype_round_trip` | for (1, `float16`, `F16`, 2), (2, `float32`, `F32`, 4), (3, `bfloat16`, `BF16`, 2): `dtype_code(name)` is the code, `dtype_name(code)` is the name, `dtype_itemsize(name)` is the size, `dtype_from_safetensors` of the third value is the name |
| 3 | `dtype_bad_values` | each raises `ValueError` and the message contains the bad value: `dtype_code("float64")`, `dtype_name(0)`, `dtype_name(4)`, `dtype_itemsize("int8")`, `dtype_from_safetensors("F64")`, `dtype_from_safetensors("f32")` |
| 4 | `numpy_dtype` | `numpy_dtype("float16")` equals `numpy.dtype("float16")` and its `itemsize` is 2; `float32` likewise with 4; `numpy_dtype("bfloat16")` and `numpy_dtype("int8")` raise `ValueError` |
| 5 | `data_dir_env` | `data_dir()` returns a `Path` equal to `<temp>/home`, and that folder now exists |
| 6 | `node_id_stable` | `local_node_id()` returns the same string twice; the file `<temp>/home/node_id` exists and its stripped text is that string; the string is lower case and ends with a dash and 6 hex characters |
| 7 | `error_classes` | `EccError` subclasses `Exception`; `WireError`, `RemoteError`, `NodeUnavailable`, `ModelFileError`, `PlacementError`, `EngineError` subclass `EccError`; `ConnectionClosed` subclasses `WireError`. `RemoteError("m", "OVER_BUDGET")` has `code` `"OVER_BUDGET"` and `experts` `[]`; given a third argument `[ExpertKey(1, 2)]` it keeps that list. `NodeUnavailable("m", "n1").node_id` is `"n1"`. `PlacementError("m", ["a"]).violations` is `["a"]`. `str()` of each contains `m` |
| 8 | `logger_once` | `get_logger("ecc.check")` returns a `logging.Logger` with that name; the root logger has at least one handler; a second call leaves the number of root handlers unchanged |
| 9 | `expert_key` | `ExpertKey(2, 5)` equals `(2, 5)`; `layer` is 2, `expert` is 5; a dict keyed by it is found again with the plain tuple `(2, 5)` |
| 10 | `blob_validate` | `H` 4, `I` 6, `float32`, three byte strings of 96 bytes: `validate()` returns `None`, `nbytes` is 288. The same with `bfloat16` and 48 bytes each: `validate()` returns `None`, `nbytes` is 144 |
| 11 | `blob_rejects` | `down_proj` of 95 bytes: `validate()` raises `ValueError`. 48-byte strings with dtype `float32`: raises `ValueError`. Dtype `"float64"`: raises `ValueError`. Assigning to `blob.layer` raises `dataclasses.FrozenInstanceError` |
| 12 | `node_json_round_trip` | `list(node.to_json())` is the 15 field names in field order; `json.dumps` of it works; `NodeInfo.from_json(node.to_json())` equals the node; setting `node.status` to `"offline"` works |
| 13 | `node_json_hello_form` | the sample JSON with `host` `""`, `link_type` `"unknown"`, `rtt_ms` `None` and one extra key `"extra"` is accepted; the result's `rtt_ms` is `None` and `host` is `""`. With `rtt_ms` 3 the result's `rtt_ms` is a `float` |
| 14 | `node_json_rejects` | each raises `ValueError` whose message contains the bad value: `link_type` `"bluetooth"`, `role` `"client"`, `status` `"busy"`, `device` `"gpu"`, `compute_dtype` `"float64"`. The sample JSON without `budget_bytes` raises `ValueError` whose message contains `budget_bytes` |
| 15 | `placement_counts` | sample placement: `num_layers` 2, `num_experts` 4, `counts()` `[2, 2, 1]`, `disk_count()` 3, `validate_shape(2, 4)` returns `None`. With `owner` `[]`: `num_layers` 0, `num_experts` 0, `counts()` `[0, 0, 0]` |
| 16 | `placement_experts_of` | `experts_of(0)` is `[(0, 0), (1, 1)]`; `experts_of(1)` is `[(0, 1), (0, 2)]`; `experts_of(2)` is `[(1, 0)]`; `experts_of(-1)` is `[(0, 3), (1, 2), (1, 3)]`; every item is an `ExpertKey` |
| 17 | `placement_shape_bad` | each raises `PlacementError` whose `violations` is a non-empty list of strings: sample with `validate_shape(3, 4)`; sample with `validate_shape(2, 5)`; `owner` `[[0, 1, 1, -1], [2, 0, -1]]` with `(2, 4)`; a cell `3`; a cell `-2`; `owner` `[]` with `(1, 1)`. `owner` `[[0, 5, 1, -1], [2, 0, -1]]` with `(2, 4)` gives at least 2 violations |
| 18 | `placement_json` | `to_json()` has exactly the keys `node_ids`, `owner`, `context_len`; `Placement.from_json(p.to_json())` equals `p`; changing a cell in the dict afterwards leaves `p.owner` unchanged; `from_json` of a dict without `owner` raises `ValueError` containing `owner` |
| 19 | `placement_all_on` | `Placement.all_on(["m", "s1"], 3, 5, 1, 2048)`: `counts()` `[0, 15]`, `disk_count()` 0, `context_len` 2048, `validate_shape(3, 5)` returns `None`; after setting `owner[0][0]` to `-1`, `owner[1][0]` is still 1. With `node_index` `-1`: `disk_count()` 15 |
| 20 | `requirements_pinned` | the bytes of `requirements.txt` equal the bytes of `store/PINS-requirements.txt` |
| 21 | `readme` | `README.md` (read as UTF-8) has at most 30 lines and contains `# Expert Cache Cluster`, `python -m pip install --only-binary=:all: -r requirements.txt`, `python -m pip check`, `python -B -m checks.run_all`, and `python -B -m ecc ` followed by each of `make-tiny`, `inspect`, `satellite`, `chat`, `master`, `mock-ui` |
| 22 | `dispatcher_modes` | `sys.executable -B -m ecc` and `sys.executable -B -m ecc nope`, run as subprocesses from the repo root with a 60 second limit: each exits with code 2 and its output (stdout plus stderr) contains all of `make-tiny`, `inspect`, `satellite`, `chat`, `master`, `mock-ui`, `bench-net`, `doctor` |
| 23 | `torch_dtype` | last row: `torch_dtype` gives `torch.float16`, `torch.float32`, `torch.bfloat16` for the three names; `torch_dtype("int8")` raises `ValueError` |

Last line it prints: `OK check_common_basics.py (23 checks)`.

### 7. Verify
1. `python -B -m checks.check_common_basics`: 23 `PASS` lines, then `OK check_common_basics.py (23 checks)`.
2. `python -B -m checks.run_all common`: a `PASS` line naming `check_common_basics`, exit code 0.
3. `python -B -m checks.run_all` with a command time limit of 600 seconds: every line says `PASS`, exit code 0. A failing check of another agent: AGENTS.md section 7.
4. Read your diff: only your four files and this task file. Save as AGENTS.md section 5 says.

### 8. Hand off
- Status line: `- A1 provides: ecc.common.dtypes and ecc.common.types per store/03-CONTRACT-COMMON.md sections 4 and 5`.
- PUSHED entry, to all: `ecc.common` is complete per contract 03 sections 1 to 5 and `README.md` is in; the commands of section 7 you ran and the last line each printed; no stubs; any R01-A1a file you fixed and the change.
- Next task builds on: `ExpertKey`, `ExpertBlob` and the dtype functions (R02-A1, R02-A2, R02-A3, R03-A2b); `NodeInfo` and `Placement` (R03-A3 and every later task).

---

# AGENT 2 (A2) - round 01

You are A2. This part has 1 task. Stop reading at the next line that starts with `# AGENT` or `# HUMANS`.

## Task 1 of 1: R01-A2-wire-frames

| | |
|---|---|
| Agent | A2 |
| Round | 1 |
| You create | `ecc/net/__init__.py`, `ecc/net/wire.py`, `checks/check_net_wire.py` |
| You change | nothing |
| Needs | R01-A1a, written in this same round: `ecc/common/settings.py`, `ecc/common/errors.py` |
| Size | 3 files; about 110 lines of code; about 280 lines of check |


### 1. Outcome

`ecc/net/wire.py` turns a TCP byte stream into frames: a 16-byte header, then a payload. Every message between the master and a satellite goes through it. R02-A2 (messages), R04-A2 (satellite server) and R05-A2 (client) call it next.

Done means: `python -B -m checks.check_net_wire` ends with the line `OK check_net_wire.py (29 checks)`.

### 2. Read first

1. `store/01-OVERVIEW.md`
2. `store/02-CODE-RULES.md`
3. `store/03-CONTRACT-COMMON.md` sections 1 and 2: the settings and the error classes this task imports.
4. `store/05-CONTRACT-WIRE.md` sections 1 and 2: the source of section 4 below. If the two differ, the contract wins (code rule 4).

Do not open other files in `store/`.

### 3. Before you start

1. Run `python -c "import sys; print(sys.prefix)"`. It must print the project environment (the path contains `.ecc`). If not, stop and tell your human. Never install anything.
2. Need R01-A1a. Proof: `python -B -c "from ecc.common.settings import WIRE_MAGIC, MAX_PAYLOAD_BYTES; from ecc.common.errors import EccError, WireError, ConnectionClosed; print('ok')"` prints `ok`.
3. If step 2 fails because `ecc/common/` is not pushed yet: write all three files against the table below, run nothing, and save as AGENTS.md section 5 says with `untested` in the PUSHED entry (AGENTS.md Kickoff rule 2). That save pulls. When a pull brings the two files, do section 7 and post the result. If the session ends first, write `run checks.check_net_wire after the skeleton lands` on your `next` line.
4. If step 2 fails although both files exist: post a BUG to A1 with the one error line, then continue as in step 3.

| Name you import | Module | What it is |
|---|---|---|
| `WIRE_MAGIC` | `ecc.common.settings` | the 4 bytes `ECC1` |
| `MAX_PAYLOAD_BYTES` | `ecc.common.settings` | 268435456 |
| `WireError(message)` | `ecc.common.errors` | subclass of `EccError` |
| `ConnectionClosed(message)` | `ecc.common.errors` | subclass of `WireError` |

### 4. Build

#### 4.1 `ecc/net/__init__.py`

1. A module docstring (code rule 6) and the line `from __future__ import annotations`. No imports, no re-exports, nothing else.

#### 4.2 `ecc/net/wire.py`

Header layout. All integers are little-endian. The `struct` format of the whole header is `<4sBBHII`.

| Offset | Size | Field | Value |
|---|---|---|---|
| 0 | 4 | magic | the bytes `ECC1` |
| 4 | 1 | msg_type | unsigned 8-bit |
| 5 | 1 | flags | 0 |
| 6 | 2 | reserved | 0 |
| 8 | 4 | request_id | unsigned 32-bit, chosen by the master, copied into the reply |
| 12 | 4 | payload_len | unsigned 32-bit, at most `MAX_PAYLOAD_BYTES` |

Public surface (contract 05 section 2):

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

Rules:

1. Imports: `dataclasses`, `socket`, `struct`; `WIRE_MAGIC` and `MAX_PAYLOAD_BYTES` from `ecc.common.settings`; `WireError` and `ConnectionClosed` from `ecc.common.errors`. Nothing else. No logger, no threads, no locks, no module state. The docstring says: never imports torch or numpy, never catches socket errors.
2. One constant `_HEADER_STRUCT` (private to this task) holds `struct.Struct("<4sBBHII")`. `HEADER_SIZE` is 16.
3. `pack_header` writes `WIRE_MAGIC`, flags 0 and reserved 0. A `payload_len` equal to `MAX_PAYLOAD_BYTES` is accepted; one more raises `WireError`. It does not check `msg_type` or `request_id`: callers pass 0 to 255 and 0 to 4294967295.
4. `unpack_header` checks in this order: the length is exactly 16; the magic equals `WIRE_MAGIC`; `payload_len` is at most `MAX_PAYLOAD_BYTES`. Each failure raises plain `WireError`. It ignores flags and reserved. It never raises `ConnectionClosed` or `struct.error`.
5. `recv_exact` with `byte_count` 0 returns `b""` and does not touch the socket.
6. `recv_exact` otherwise: make one `bytearray(byte_count)`, wrap it in a `memoryview`, and call `sock.recv_into` with the unfilled slice as its only argument until the buffer is full. Never call `sock.recv`. No call offers more room than the bytes still missing, so nothing of the next frame is consumed.
7. In `recv_exact` a `recv_into` result of 0 before any byte of this call arrived raises `ConnectionClosed`. A result of 0 after at least one byte raises plain `WireError`. On success return `bytes` (convert the full bytearray once).
8. `send_frame` steps: (a) add up the part sizes with `memoryview(part).nbytes`; (b) build the header with `pack_header`, so an oversize sum raises `WireError` before anything is sent; (c) `sock.sendall(header)`; (d) one `sock.sendall(part)` per part, in order; (e) return `HEADER_SIZE` plus the sum. With no parts the payload length is 0 and it returns 16.
9. `recv_frame` steps: (a) `recv_exact(sock, HEADER_SIZE)`, errors pass through unchanged; (b) `unpack_header`; (c) `recv_exact(sock, payload_len)`, and a `ConnectionClosed` from this step is re-raised as plain `WireError` with `from error`, because the peer closed in the middle of a frame; (d) return `Frame(msg_type, request_id, payload)`.
10. `configure_socket` makes three calls: `sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)`, `sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)`, `sock.settimeout(timeout_s)`. Write the hint of `timeout_s` as `float | None`.
11. No `try` around a socket call. `socket.timeout` and every other `OSError` leave this module unchanged; the caller turns them into `NodeUnavailable` (R04-A2, R05-A2). This module never closes a socket.
12. Every error message names the expected and the found value (code rule 19), for example `expected magic b'ECC1', found b'HTTP'`.

| Situation | Required behaviour of `recv_frame` |
|---|---|
| peer closes before any header byte | `ConnectionClosed` |
| peer closes after 1 to 15 header bytes | plain `WireError` |
| peer closes after the full header, `payload_len` above 0, no payload byte yet | plain `WireError` |
| peer closes inside the payload | plain `WireError` |
| `payload_len` is 0 | `Frame` with payload `b""` |
| two frames arrive in one read | two calls return them in order |

Save point: when `wire.py` is written and section 3 step 2 still fails, save now as `untested`.

### 5. Traps

- `recv_into` returns fewer bytes than asked for. One call is never enough: loop.
- Never grow a `bytes` value with `+=` in the read loop. One `bytearray`, filled through a `memoryview`.
- Never `b"".join(parts)` and never `header + part` in `send_frame`: a part can be hundreds of megabytes.
- `len()` of a `memoryview` counts items, not bytes. Use `.nbytes`.
- `ConnectionClosed` is a `WireError`. "Plain `WireError`" in this file means `type(error) is WireError`; test it that way in the check.
- `socket.socketpair()` is not TCP on macOS and Linux: `configure_socket` raises `OSError` on it. In the check call `configure_socket` only on a real loopback TCP connection.
- `sendall` of 5 MB blocks until the other end reads. Send from a helper thread and read on the main thread.
- Not this task: message codes, JSON, payload layouts (R02-A2); HELLO, locks, closing sockets, `NodeUnavailable` (R04-A2, R05-A2). Do not create or edit `ecc/__init__.py`, anything in `ecc/common/`, `checks/run_all.py`, `requirements.txt` or `checks/__init__.py`.

### 6. Check: `checks/check_net_wire.py`

Setup: imports only the standard library, `ecc.common.settings`, `ecc.common.errors`, `ecc.net.wire`. Private to the check: `pair()` returns `socket.socketpair()` with `settimeout(10.0)` on both ends; `tcp_pair()` makes a listener with `socket.create_server(("127.0.0.1", 0))`, connects with `socket.create_connection`, accepts, closes the listener and returns `(client, accepted)`; `SlowReader` has one method `recv_into(buffer)` that copies at most 3 bytes per call from a fixed byte string, counts calls, and remembers whether a buffer was ever larger than the bytes it had left; `SendRecorder` has one method `sendall(data)` that appends `bytes(data)` to a list.
Each row uses fresh sockets and closes them. Helper threads are named daemon threads, joined with `join(10.0)`. An `AssertionError`, `EccError` or `OSError` in a row prints `FAIL <name>: <expected and found>` and exits with code 1. `a` sends, `b` receives.

| # | PASS name | What must be true |
|---|---|---|
| 1 | `no_torch` | first row: after `import ecc.net.wire`, `"torch"` is not in `sys.modules` |
| 2 | `header_size` | `HEADER_SIZE == 16` and `len(pack_header(1, 1, 0)) == 16` |
| 3 | `header_bytes` | `pack_header(0x20, 0x01020304, 5) == bytes.fromhex("45434331200000000403020105000000")` |
| 4 | `header_round_trip` | `unpack_header(pack_header(*t)) == t` for `(0, 0, 0)`, `(0x7F, 4294967295, MAX_PAYLOAD_BYTES)`, `(0x21, 7, 1)` |
| 5 | `pack_oversize` | `pack_header(1, 1, MAX_PAYLOAD_BYTES + 1)` raises `WireError` |
| 6 | `unpack_bad_magic` | a packed header with byte 0 replaced by `X` raises plain `WireError` |
| 7 | `unpack_wrong_size` | inputs of 0, 15 and 17 bytes each raise plain `WireError` |
| 8 | `unpack_oversize` | `struct.pack("<4sBBHII", b"ECC1", 1, 0, 0, 1, MAX_PAYLOAD_BYTES + 1)` raises plain `WireError` |
| 9 | `unpack_ignores_flags` | `struct.pack("<4sBBHII", b"ECC1", 3, 9, 513, 7, 2)` unpacks to `(3, 7, 2)` |
| 10 | `frame_frozen` | `Frame(1, 2, b"x")` has the three fields; assigning `payload` raises `dataclasses.FrozenInstanceError` |
| 11 | `recv_exact_loops` | with `data = random.Random(1).randbytes(1000)`: `recv_exact(SlowReader(data), 1000)` equals `data`, its type is `bytes`, the reader got at least 334 calls and never a buffer larger than what it had left |
| 12 | `recv_exact_zero` | `recv_exact(SlowReader(data), 0) == b""` and the reader got 0 calls |
| 13 | `recv_exact_closed_first` | `a` closed, nothing sent: `recv_exact(b, 4)` raises `ConnectionClosed` |
| 14 | `recv_exact_closed_later` | `a` sends 2 bytes and closes: `recv_exact(b, 4)` raises plain `WireError` |
| 15 | `send_parts_separate` | `send_frame(SendRecorder(), 0x10, 9, b"abc", b"defgh", b"ijklmno")` returns 31; recorded lengths are `[16, 3, 5, 7]`; the first chunk equals `pack_header(0x10, 9, 15)` |
| 16 | `frame_round_trip` | `send_frame(a, 0x03, 77, b"abcdefgh")` returns 24; `recv_frame(b) == Frame(0x03, 77, b"abcdefgh")`; the payload's type is `bytes` |
| 17 | `empty_payload` | `send_frame(a, 0x05, 1)` returns 16; `recv_frame(b) == Frame(0x05, 1, b"")` |
| 18 | `one_byte_pieces` | a helper thread sends `pack_header(0x20, 5, 100) + bytes(range(100))` with one `sendall` per byte; `recv_frame(b) == Frame(0x20, 5, bytes(range(100)))` |
| 19 | `big_three_parts` | `big = random.Random(1234).randbytes(5242880)`, cut at 1000000 and 3000000; a helper thread calls `send_frame(a, 0x10, 99, part1, part2, part3)`; `recv_frame(b)` has payload equal to `big`, `request_id` 99, `msg_type` 0x10; `send_frame` returned 5242896 |
| 20 | `two_frames_one_send` | one `a.sendall` of `pack_header(1, 10, 3) + b"abc" + pack_header(2, 11, 2) + b"de"`; two `recv_frame(b)` calls return `Frame(1, 10, b"abc")` then `Frame(2, 11, b"de")` |
| 21 | `oversize_sends_nothing` | `send_frame(a, 1, 1, *([bytes(1048576)] * 257))` raises `WireError`; then `send_frame(a, 1, 42, b"ok")`; the first `recv_frame(b)` has `request_id` 42 |
| 22 | `close_before_frame` | `a` closes at once: `recv_frame(b)` raises `ConnectionClosed` |
| 23 | `close_in_header` | `a` sends the first 7 bytes of `pack_header(1, 1, 10)` and closes: plain `WireError` |
| 24 | `close_after_header` | `a` sends `pack_header(1, 1, 10)` and closes: plain `WireError` |
| 25 | `close_in_payload` | `a` sends `pack_header(1, 1, 10) + b"abcd"` and closes: plain `WireError` |
| 26 | `bad_magic_on_socket` | `a` sends `b"HTTP" + bytes(12)`: `recv_frame(b)` raises plain `WireError` |
| 27 | `timeout_not_caught` | `b.settimeout(0.05)`, `a` sends nothing: `recv_frame(b)` raises `socket.timeout`, and the error is not an `EccError` |
| 28 | `configure_tcp` | on `tcp_pair()`, after `configure_socket(client, 2.5)` and `configure_socket(accepted, None)`: `getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)` and `getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE)` are not 0 on both sockets; `client.gettimeout()` is within 1e-6 of 2.5; `accepted.gettimeout()` is `None` |
| 29 | `tcp_round_trip` | on that configured pair: `send_frame(client, 0x03, 8, b"12345678")`, then `recv_frame(accepted) == Frame(0x03, 8, b"12345678")` |

Last line it prints: `OK check_net_wire.py (29 checks)`.

### 7. Verify

1. `python -B -m checks.check_net_wire`: 29 `PASS` lines, then `OK check_net_wire.py (29 checks)`, exit code 0, in a few seconds.
2. `python -B -m checks.run_all net`: a line starting `PASS check_net_wire.py`.
3. `python -B -m checks.run_all` with a command time limit of 600 seconds: every line starts with `PASS`, exit code 0. If `checks/run_all.py` is not pushed yet, say so in the PUSHED entry. If another agent's check fails, follow AGENTS.md section 7.
4. Read your diff: only the three files of this task and `this part of store/ROUND-01.md`.
5. Save as AGENTS.md section 5 says.

### 8. Hand off

- Status line: `- A2 provides: ecc.net.wire per store/05-CONTRACT-WIRE.md section 2: HEADER_SIZE, Frame, pack_header, unpack_header, recv_exact, send_frame, recv_frame, configure_socket. No port, no env var.`
- The PUSHED entry says: the three files; the last line `checks.check_net_wire` printed, or `untested` and why; the `run_all` result or `run_all not pushed yet`; no STUB; the others need to do nothing.
- Next task builds on: R02-A2 hands its `list[bytes]` parts to `send_frame` and decodes `Frame.payload`; R04-A2 and R05-A2 call `recv_frame`, `send_frame` and `configure_socket`.

---

# AGENT 3 (A3) - round 01

You are A3. This part has 1 task. Stop reading at the next line that starts with `# AGENT` or `# HUMANS`.

## Task 1 of 1: R01-A3-tensor-index

| | |
|---|---|
| Agent | A3 |
| Round | 01 |
| You create | `ecc/modelfile/__init__.py`, `ecc/modelfile/tensor_index.py`, `checks/check_modelfile_index.py` |
| You change | nothing |
| Needs | `R01-A1a-skeleton` (same round, may not be pushed yet): proved by `ecc/common/errors.py` |
| Size | 3 files, about 160 lines of code, about 240 lines of check |


### 1. Outcome

A module that lists every weight tensor of a model folder by reading only the headers of its safetensors files, and returns one tensor's raw bytes on request. It also tells from a tensor name whether the tensor belongs to a routed expert. Standard library only.

Done means: `python -B -m checks.check_modelfile_index` prints `OK check_modelfile_index.py (22 checks)` as its last line and exits with code 0.

### 2. Read first

1. `store/01-OVERVIEW.md`
2. `store/02-CODE-RULES.md`
3. `store/03-CONTRACT-COMMON.md` section 2, row `ModelFileError`: the only project name this task imports.

Section 4 below restates `store/04-CONTRACT-MODELFILE.md` sections 1 to 3 in full. Do not open other files in `store/`.

### 3. Before you start

1. Run `python -c "import sys; print(sys.prefix)"`. It must print the project environment (the path contains `.ecc`). If not, stop and tell your human. Never install anything.
2. Need `R01-A1a-skeleton`: `ecc/common/errors.py` exists and `python -B -c "from ecc.common.errors import ModelFileError; print('ok')"` prints `ok`.
3. If it is missing, A1 is writing it now. Do not wait and do not replace it:
   1. Write the three files as specified, with `from ecc.common.errors import ModelFileError`. Create nothing else: no `ecc/__init__.py`, nothing under `ecc/common/`, no stand-in error class.
   2. Syntax check: `python -B -c "import ast, pathlib; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8')) for p in ('ecc/modelfile/tensor_index.py', 'checks/check_modelfile_index.py')]; print('syntax ok')"` must print `syntax ok`.
   3. Save as AGENTS.md section 5 says, PUSHED text `untested` (AGENTS.md Kickoff, rule 2). After each save's pull, look again for `ecc/common/errors.py`.
   4. When it is there: do section 7, fix what fails, save again. If the session ends first, your `next` line reads: `run checks.check_modelfile_index once R01-A1a is pushed`.

### 4. Build

#### 4.1 `ecc/modelfile/__init__.py`

1. A module docstring (reads model folders; imported by A1 and A2 code; never imports torch, numpy, `safetensors` or `transformers`) and `from __future__ import annotations`. No imports, no re-exports.

#### 4.2 `ecc/modelfile/tensor_index.py`

A model folder holds one or more `*.safetensors` files. The header of a file is one JSON object. Its key `__metadata__`, if present, is not a tensor. Every other key is a tensor name whose value has `dtype` (a string such as `F32`, `F16`, `BF16`, `I64`), `shape` (a list of integers) and `data_offsets` (`[begin, end]`, measured from the start of the data area). Layout of one file:

| Bytes | Content |
|---|---|
| 0 to 7 | `N`: unsigned 64-bit little-endian integer, the length of the header in bytes |
| 8 to 8+N-1 | the header: UTF-8 JSON, possibly padded with spaces at the end |
| 8+N to end | the data area |

| Name | Kind | Signature or fields | Behaviour |
|---|---|---|---|
| `EXPERT_PARTS` | constant | the tuple `("gate_proj", "up_proj", "down_proj")` | the order used everywhere, including on the wire |
| `parse_expert_name` | function | `parse_expert_name(name: str) -> tuple[int, int, str] or None` | `(layer, expert, part)` for an expert tensor, `None` for anything else |
| `expert_tensor_name` | function | `expert_tensor_name(layer: int, expert: int, part: str) -> str` | the inverse |
| `TensorEntry` | frozen dataclass | `name: str`, `file: Path`, `dtype: str`, `shape: tuple[int, ...]`, `data_start: int`, `nbytes: int` | `data_start` is the absolute byte offset in the file, `8 + N + begin`; `nbytes` is `end - begin` |
| `TensorEntry.element_count` | property | `int` | the product of `shape` (1 for an empty shape) |
| `TensorIndex` | class | holds `model_dir: Path` and `entries: dict[str, TensorEntry]` | |
| `TensorIndex.load` | class method | `load(model_dir: Path) -> TensorIndex` | reads the header of every `*.safetensors` file directly inside the folder, in file-name order |
| `TensorIndex.names` | method | `names() -> list[str]` | all tensor names, sorted |
| `TensorIndex.get` | method | `get(name: str) -> TensorEntry` | raises `ModelFileError` naming the tensor if absent |
| `TensorIndex.read_bytes` | method | `read_bytes(name: str) -> bytes` | opens the file, seeks to `data_start`, reads exactly `nbytes`; safe from several threads at once |

Stage 1, expert names. Rules:

1. An expert tensor name is, as a whole string, `model.layers.L.mlp.experts.E.P.weight`. `P` is one of `EXPERT_PARTS`. `L` and `E` use the digits `0` to `9` only: no sign, no leading zero (`0` alone is fine).
2. `parse_expert_name` returns `(L as int, E as int, P)` for such a name and `None` for every other string. It never raises.
3. `expert_tensor_name` returns the string of rule 1 for its arguments. It does not validate them. Parsing a name and passing the result to it gives the same name back.
4. Use one regular expression compiled at module level (private to this task): every dot escaped, each number as `(0|[1-9][0-9]*)`, applied with `fullmatch`.

Save point: save both files now as AGENTS.md section 5 says (`untested` if the skeleton is not there).

Stage 2, entry and index. Rules:

5. `TensorEntry` fields are in the table's order. `shape` is a tuple. `element_count` is 1 for `()` and 0 when any dimension is 0.
6. `TensorIndex` is a dataclass with the fields `model_dir`, `entries` in that order (the constructor is private to this task: other code calls only `load`). Nothing changes the object after `load`. Its docstring says: called from any thread.
7. `load(model_dir)` does this, in 7 steps:
   1. Collect the regular files directly inside `model_dir` whose name ends in `.safetensors`, sorted by file name. Subfolders are not searched. If `model_dir` is missing, is not a folder, or has no such file: `ModelFileError` whose message contains the folder path.
   2. For each file: take the file size and read 8 bytes. Fewer than 8 bytes: error. `N` is those bytes as an unsigned 64-bit little-endian integer.
   3. If `8 + N` is larger than the file size: error. Decide this before reading anything more.
   4. Read `N` bytes, decode as UTF-8, parse as JSON. A decode error, a JSON error, or a top-level value that is not an object: error. Trailing spaces need no handling: the JSON parser accepts them.
   5. For each key other than `__metadata__`: the value must be an object with `dtype` a string, `shape` a list of integers and `data_offsets` a list of two integers, and `0 <= begin <= end <= file size - 8 - N` must hold (`end` equal to the data area size is fine). Otherwise error.
   6. A name already taken from an earlier file: error whose message contains the tensor name and both file names.
   7. Store a `TensorEntry`: the name, the file's path, `dtype` as written, `shape` as a tuple, `data_start = 8 + N + begin`, `nbytes = end - begin`.
8. Every error of rule 7 is a `ModelFileError`. In steps 2 to 5 its message contains the file name; in step 5 also the tensor name. No `json.JSONDecodeError`, `UnicodeDecodeError`, `OSError`, `KeyError` or `TypeError` leaves `load`: catch the narrow type and raise `ModelFileError` from it.
9. `names()` returns a new list on each call, in plain string order, across all files. `get(name)` for an absent name raises `ModelFileError` whose message contains the name.
10. `read_bytes(name)`: `get`, then open the entry's file in binary mode in a `with` block, seek, read, return `bytes`. Fewer than `nbytes` read, or a file that cannot be opened: `ModelFileError` whose message contains the tensor name, the expected count and the found count. No handle kept open, no cache, no lock.
11. Imports: `dataclasses`, `json`, `math`, `pathlib`, `re`, `struct`, and `ecc.common.errors`. Nothing else. No logging, no `print`.

| Situation | Required behaviour |
|---|---|
| `shape` is `[]` | `shape == ()`, `element_count == 1` |
| `begin == end` | `nbytes == 0`, `read_bytes` returns `b""` |
| a dtype string such as `I64` | kept as written; `nbytes` is never compared with shape or dtype |
| `N` is 2 to the power 63 | `ModelFileError` from step 3, no read attempted |
| `config.json`, `model.safetensors.index.json` in the folder | ignored |

### 5. Traps

- Not yours: `ecc/__init__.py`, `ecc/common/`, `checks/run_all.py`. Do not create `checks/__init__.py`. Do not define your own `ModelFileError`.
- Do not use the `safetensors` package, numpy or torch, in the module or in the check. The check writes its files with `json` and `struct`.
- `data_offsets` count from the start of the data area, not of the file, and header key order says nothing about data order. Use `N` as read from the file, padding included.
- Real shard files are about 4 GB. `load` reads `8 + N` bytes per file, never the whole file and never tensor data.
- `re.match` with `$` accepts a trailing newline; an unescaped `.` matches any character; `\d` matches non-ASCII digits. Hence rule 4. `shared_expert.*`, `mlp.gate.weight` and `shared_expert_gate.weight` are backbone: `parse_expert_name` gives `None`.
- Belongs to `R02-A3-model-map-and-reader`, do not build it: reading `config.json`, checking expert shapes or dtypes, the model hash, `model_map.py`, `expert_reader.py`, `inspect.py`.
- Code rules 10 and 12: split `load` into private helpers (for example `_list_files`, `_read_header`, `_make_entry`); `8` and `"__metadata__"` are named module constants.

### 6. Check: `checks/check_modelfile_index.py`

Setup: one `tempfile.mkdtemp()` folder, removed in a `finally` with `shutil.rmtree(..., ignore_errors=True)`. Every fixture is its own subfolder of it. Helpers, private to this check:

- `write_safetensors(path, tensors, metadata, pad_count) -> int`: `tensors` is a list of `(name, dtype, shape, data)` in data order; offsets run from 0 in that order. Header keys: `__metadata__` first when `metadata` is not `None`, then the tensors in reverse list order. Header bytes: the JSON text in UTF-8 plus `pad_count` spaces. It writes the 8 length bytes, the header, the data, and returns `N`.
- `write_raw(path, n_value, header_bytes, data_bytes)`: writes `n_value` as 8 bytes, then the two byte strings unchanged. For broken files.
- `expect_error(action, must_contain) -> bool`: true only when `action()` raises an exception whose type is exactly `ModelFileError` and whose message contains every string in `must_contain`.

Fixture `good/`. Byte `i` of tensor number `t` is `(31 * t + i) mod 256`. File A is `model-00001-of-00002.safetensors`, metadata `{"format": "pt"}`, `pad_count` 5. File B is `model-00002-of-00002.safetensors`, no metadata, `pad_count` 0. `good/` also holds `config.json` and `model.safetensors.index.json` (each `{}`) and a subfolder `sub/` with a copy of file A named `extra.safetensors`. In rows 16 to 19 of the check table the broken file is always named `a.safetensors`.

| t | File | Name | dtype | shape | nbytes | begin |
|---|---|---|---|---|---|---|
| 1 | A | `model.embed_tokens.weight` | `F32` | `[2, 3]` | 24 | 0 |
| 2 | A | `model.layers.0.mlp.experts.0.gate_proj.weight` | `F32` | `[6, 4]` | 96 | 24 |
| 3 | A | `model.layers.0.mlp.experts.0.up_proj.weight` | `F32` | `[6, 4]` | 96 | 120 |
| 4 | A | `model.layers.0.mlp.gate.weight` | `F32` | `[3, 4]` | 48 | 216 |
| 5 | B | `lm_head.weight` | `BF16` | `[2, 3]` | 12 | 0 |
| 6 | B | `model.layers.0.mlp.experts.0.down_proj.weight` | `F32` | `[4, 6]` | 96 | 12 |
| 7 | B | `model.layers.0.mlp.shared_expert.gate_proj.weight` | `F16` | `[5, 4]` | 40 | 108 |
| 8 | B | `model.step` | `I64` | `[]` | 8 | 148 |
| 9 | B | `model.empty` | `F32` | `[0, 4]` | 0 | 156 |

| # | PASS name | What must be true |
|---|---|---|
| 1 | `no heavy imports` | after importing `ecc.modelfile.tensor_index`: `torch`, `numpy`, `safetensors`, `transformers` are not in `sys.modules` |
| 2 | `expert parts` | `EXPERT_PARTS` is a tuple equal to `("gate_proj", "up_proj", "down_proj")` |
| 3 | `parse match` | for (L, E) in (0, 0), (3, 17), (47, 127) and each part: `parse_expert_name` of the rule 1 name equals `(L, E, part)`, types `int`, `int`, `str` |
| 4 | `parse near-miss` | `None` for each of: `model.layers.0.mlp.experts.1.gate_proj.bias`; `model.layers.0.mlp.shared_expert.gate_proj.weight`; `model.layers.0.mlp.gate.weight`; `model.layers.0.mlp.shared_expert_gate.weight`; `model.layers.0.mlp.experts.1.mid_proj.weight`; `model.layers.0.mlp.experts.gate_proj.weight`; `model.layers.a.mlp.experts.1.up_proj.weight`; `model.layers.-1.mlp.experts.1.up_proj.weight`; `model.layers.01.mlp.experts.1.up_proj.weight`; `xmodel.layers.0.mlp.experts.1.up_proj.weight`; `model.layers.0.mlp.experts.1.up_proj.weight.x`; `modelXlayers.0.mlp.experts.1.up_proj.weight`; a valid name followed by a newline character; the empty string |
| 5 | `name inverse` | `expert_tensor_name(3, 17, "up_proj")` is `model.layers.3.mlp.experts.17.up_proj.weight`; for the nine names of row 3, name to tuple to name gives the same name |
| 6 | `load` | `TensorIndex.load(good)`: `model_dir` equals the folder as a `Path`; `entries` has exactly 9 keys; each key equals its entry's `name`; `__metadata__` is not a key |
| 7 | `names sorted` | `names()` equals `sorted` of the nine names; the first is `lm_head.weight`; clearing the returned list does not change the next call |
| 8 | `entry fields` | for all nine: `get(name)` is a `TensorEntry`; `file` is the path of file A or B as in the table; `dtype`, `shape` (a `tuple`) and `nbytes` match the table |
| 9 | `data_start` | for all nine: `data_start == 8 + N + begin`, with `N` as returned by `write_safetensors` for that file |
| 10 | `element_count` | 6, 24, 24, 12, 6, 24, 20, 1, 0 for t = 1 to 9 |
| 11 | `frozen` | assigning to `nbytes` of an entry raises `dataclasses.FrozenInstanceError` |
| 12 | `read_bytes` | for all nine: the result is `bytes` and equals the bytes written; `model.empty` gives `b""` |
| 13 | `read_bytes threads` | 8 threads each read all nine tensors 50 times; all threads end (join limit 30 s each); no exception; every result equals the bytes written |
| 14 | `get missing` | `get("nope.weight")` and `read_bytes("nope.weight")`: `expect_error` with `nope.weight` |
| 15 | `err no file` | `load` of `empty/` (no files), `only_config/` (only `config.json`), `missing/` (never created): `expect_error` with the folder name |
| 16 | `err bad json` | header is the 6 bytes `{"x": `; header is `[1, 2]`; header is the 4 bytes `FF FE 7B 7D`: `expect_error` with `a.safetensors` |
| 17 | `err N too large` | `N` = 100 followed by 10 bytes; `N` = 2 to the power 63 followed by 10 bytes; a file of 5 bytes: `expect_error` with `a.safetensors` |
| 18 | `err offsets` | one tensor `bad.weight` (`F32`, `[1]`, 4 data bytes) with `data_offsets` `[0, 8]`; `[4, 0]`; `[-4, 0]`: `expect_error` with `a.safetensors` and `bad.weight` |
| 19 | `err entry fields` | `bad.weight` without `data_offsets`; `bad.weight` with `shape` given as the string `"4"`: `expect_error` with `a.safetensors` and `bad.weight` |
| 20 | `err duplicate` | `a.safetensors` and `b.safetensors` both hold `model.norm.weight`: `expect_error` with `model.norm.weight`, `a.safetensors`, `b.safetensors` |
| 21 | `err short read` | one file with `head.weight` then `tail.weight`, 8 bytes each; after `load` the check cuts the last 4 bytes off the file; `read_bytes("tail.weight")`: `expect_error` with `tail.weight`; `read_bytes("head.weight")` still returns its 8 bytes |
| 22 | `no heavy imports at end` | row 1 again, after every other row ran |

Each row prints one `PASS` line. Last line: `OK check_modelfile_index.py (22 checks)`.

### 7. Verify

1. `python -B -m checks.check_modelfile_index`: 22 `PASS` lines, then `OK check_modelfile_index.py (22 checks)`, exit code 0.
2. `python -B -m checks.run_all modelfile`: a `PASS` line for `check_modelfile_index`.
3. `python -B -m checks.run_all`, with a command time limit of 600 seconds: no `FAIL`, no `TIMEOUT`. A failing file that is not yours: AGENTS.md section 7.

### 8. Hand off

- Status line: `- A3 provides: ecc/modelfile/tensor_index.py: EXPERT_PARTS; parse_expert_name(name) -> (layer, expert, part) or None; expert_tensor_name(layer, expert, part) -> str; TensorEntry(name, file, dtype, shape, data_start, nbytes) with element_count; TensorIndex.load(model_dir), .model_dir, .entries, .names(), .get(name), .read_bytes(name) -> bytes; errors are ModelFileError; standard library only. Spec: store/04-CONTRACT-MODELFILE.md section 3.`
- PUSHED entry: the three files; the last line the check printed, or `untested` with the reason; no stubs; no new dependency.
- Next task builds on: `R02-A3-model-map-and-reader` uses `TensorIndex`, `parse_expert_name`, `expert_tensor_name` and `EXPERT_PARTS`; `R07-A1-backbone-only-loading` reads backbone tensors by name through `TensorIndex`.

---

# HUMANS - after round 01

1. Wait until all three agents have said "round 01 done" and each has a `DONE` entry in `AGENT_CHAT.md` for every task in the table at the top.
2. On one laptop, pull and run `python -B -m checks.run_all`. Every line must say PASS.
3. Then put `ROUND-02.md` into `store/`, push it, and give each agent the same line with the new file name.
