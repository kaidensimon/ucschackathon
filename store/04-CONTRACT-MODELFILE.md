# 04 - Contract: the model file

Owner: A3 (`ecc/modelfile/`). Used by A1 (engine, app) and A2 (weight push). Nothing in `ecc/modelfile/` imports torch, numpy, `safetensors` or `transformers`: it reads files with the standard library only, so it is fast to import and easy to check.

## 1. What a model folder is

A folder in Hugging Face layout, downloaded once to the master:

| File | Used for |
|---|---|
| `config.json` | the numbers in the model map |
| one or more `*.safetensors` files | every weight tensor |
| `model.safetensors.index.json` (optional) | not needed; we read each file's own header |
| tokenizer files | read by `transformers`, not by this package |

## 2. The safetensors file format

| Bytes | Content |
|---|---|
| 0 to 7 | `N`: unsigned 64-bit little-endian integer, the length of the header in bytes |
| 8 to 8+N-1 | the header: UTF-8 JSON, possibly padded with spaces at the end |
| 8+N to end | the data area |

The header is one JSON object. The key `__metadata__`, if present, is not a tensor and is skipped. Every other key is a tensor name whose value has three fields: `dtype` (a string such as `F32`, `F16`, `BF16`, `I64`), `shape` (a list of integers) and `data_offsets` (a pair `[begin, end]` measured from the start of the data area). So the tensor's bytes are the file's bytes from `8 + N + begin` up to but not including `8 + N + end`, row-major, little-endian.

## 3. Tensor index: `ecc/modelfile/tensor_index.py`

**`TensorEntry`**: frozen dataclass.

| Field | Type | Meaning |
|---|---|---|
| `name` | `str` | tensor name exactly as in the header |
| `file` | `Path` | the safetensors file that holds it |
| `dtype` | `str` | the safetensors dtype string |
| `shape` | `tuple[int, ...]` | |
| `data_start` | `int` | absolute byte offset in the file: `8 + N + begin` |
| `nbytes` | `int` | `end - begin` |

Property `element_count`: the product of `shape` (1 for an empty shape).

**`TensorIndex`**: holds `model_dir: Path` and `entries: dict[str, TensorEntry]`.

| Member | Signature | Behaviour |
|---|---|---|
| class method `load` | `load(model_dir: Path) -> TensorIndex` | reads the header of every `*.safetensors` file directly inside the folder, in file-name order. Raises `ModelFileError` if the folder has no such file, a header is not valid JSON, `N` is larger than the file, an entry's offsets fall outside the file, or the same tensor name appears in two files |
| `names` | `names() -> list[str]` | all tensor names, sorted |
| `get` | `get(name: str) -> TensorEntry` | raises `ModelFileError` naming the tensor if absent |
| `read_bytes` | `read_bytes(name: str) -> bytes` | opens the file, seeks to `data_start`, reads exactly `nbytes`. Raises `ModelFileError` on a short read. Safe to call from several threads at once because each call opens its own file handle |

**Expert tensor names.** A tensor belongs to a routed expert when its name matches exactly this pattern, where `L` and `E` are decimal integers and the part is one of three words:

`model.layers.L.mlp.experts.E.gate_proj.weight`
`model.layers.L.mlp.experts.E.up_proj.weight`
`model.layers.L.mlp.experts.E.down_proj.weight`

Every other tensor is backbone. That includes the router (`model.layers.L.mlp.gate.weight`), the shared expert (`model.layers.L.mlp.shared_expert.*`) and its gate (`model.layers.L.mlp.shared_expert_gate.weight`).

| Name | Signature | Behaviour |
|---|---|---|
| `EXPERT_PARTS` | the tuple `("gate_proj", "up_proj", "down_proj")` | the order used everywhere, including on the wire |
| `parse_expert_name` | `parse_expert_name(name: str) -> tuple[int, int, str] or None` | returns `(layer, expert, part)` for an expert tensor, `None` for anything else |
| `expert_tensor_name` | `expert_tensor_name(layer: int, expert: int, part: str) -> str` | the inverse |

## 4. Model map: `ecc/modelfile/model_map.py`

**`ModelMap`**: frozen dataclass. Everything the UI, the planner and the engine need to know about a model without loading a weight.

| Field | Type | Where it comes from |
|---|---|---|
| `model_dir` | `str` | the folder path as given |
| `model_name` | `str` | the folder's last path component |
| `model_hash` | `str` | 16 hex characters, see below |
| `arch` | `str` | `model_type` in `config.json` (`qwen2_moe` or `qwen3_moe`) |
| `num_layers` | `int` | `num_hidden_layers` |
| `num_experts` | `int` | `num_experts`; if that key is absent, `num_local_experts` (newer library versions write the Qwen3 config with that name) |
| `top_k` | `int` | `num_experts_per_tok` |
| `hidden_size` | `int` | `hidden_size` |
| `moe_intermediate_size` | `int` | `moe_intermediate_size` |
| `has_shared_expert` | `bool` | true when the index contains `model.layers.0.mlp.shared_expert.gate_proj.weight` |
| `stored_dtype` | `str` | our dtype name for the expert tensors' dtype (`dtype_from_safetensors`) |
| `expert_params` | `int` | `3 * hidden_size * moe_intermediate_size` |
| `expert_stored_bytes` | `int` | `expert_params` times the stored item size |
| `total_experts` | `int` | `num_layers * num_experts` |
| `backbone_params` | `int` | sum of `element_count` over every non-expert tensor |
| `backbone_stored_bytes` | `int` | sum of `nbytes` over every non-expert tensor |
| `total_stored_bytes` | `int` | sum of `nbytes` over all tensors |
| `num_kv_heads` | `int` | `num_key_value_heads`, or `num_attention_heads` if that key is absent |
| `head_dim` | `int` | `head_dim` if the config has it, otherwise `hidden_size // num_attention_heads` |
| `max_context` | `int` | `max_position_embeddings` |
| `vocab_size` | `int` | `vocab_size` |

Method `to_json() -> dict` returns every field under its own name.

**`build_model_map(model_dir: Path, index: TensorIndex) -> ModelMap`** reads `config.json`, fills the fields and verifies the file set. It raises `ModelFileError` with a message that names what is wrong when:

- `config.json` is missing or lacks one of the keys above;
- `model_type` is not `qwen2_moe` or `qwen3_moe`;
- for some layer and expert in range, one of the three expert tensors is missing (the message lists up to five missing names and the total count);
- an expert tensor has the wrong shape: `gate_proj` and `up_proj` must be `(moe_intermediate_size, hidden_size)`, `down_proj` must be `(hidden_size, moe_intermediate_size)`;
- expert tensors do not all share one dtype, or that dtype is not `F16`, `F32` or `BF16`;
- the index holds an expert tensor whose layer or expert number is outside the config's range.

**Model hash.** Take every tensor in name order and write one line per tensor: name, a vertical bar, dtype, a vertical bar, and the shape's numbers joined by commas. Join the lines with newline characters, encode as UTF-8, append the raw bytes of `config.json`, take SHA-256 and keep the first 16 hex characters in lower case. The hash depends on names, dtypes, shapes and the config, not on weight values, so it is instant even for a 60 GB model.

## 5. Expert reader: `ecc/modelfile/expert_reader.py`

The reader returns an **`ExpertBlob`**: one expert's three weight matrices exactly as stored, as raw bytes. `ExpertBlob` is defined in `ecc/common/types.py` (fields in `03-CONTRACT-COMMON.md` section 5); its `dtype` is the model map's `stored_dtype`.

**`ExpertReader`**: constructed as `ExpertReader(index: TensorIndex, model_map: ModelMap)`.

| Method | Signature | Behaviour |
|---|---|---|
| `read` | `read(layer: int, expert: int) -> ExpertBlob` | three `read_bytes` calls in `EXPERT_PARTS` order. Raises `ModelFileError` for a key outside the model. Thread-safe |
| `model_hash` (property) | `str` | from the model map |
| `model_map` (property) | `ModelMap` | the model map it was built with |

The reader returns bytes, not tensors. Turning an `ExpertBlob` into tensors is the job of `weights_from_blob` in `ecc/common/expert_math.py` (see `06-CONTRACT-ENGINE.md`), which both the master and the satellites use.

## 6. Inspect mode: `ecc/modelfile/inspect.py`

`python -B -m ecc inspect <model folder> [--json]`. Prints the model map: without `--json` as aligned `name: value` lines with byte counts also shown in GiB to two decimals; with `--json` as one JSON object (the output of `to_json()`). Exit code 0 on success; on a `ModelFileError` it prints the message and returns 1.
