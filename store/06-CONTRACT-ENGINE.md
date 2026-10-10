# 06 - Contract: the engine

Owner: A1 (`ecc/common/expert_math.py`, `ecc/engine/`). The engine is the master-side code between `transformers` and the network. A2's satellite uses section 1; A3's server reaches the engine only through the facade in `07-CONTRACT-APP-API.md`.

## 1. Expert math: `ecc/common/expert_math.py`

Imports torch and numpy. Used by the master and by every satellite, so that there is exactly one implementation of the formula.

**One expert.** An expert has three weight matrices and no biases. With hidden size `H` and intermediate size `I`: `gate_proj` has shape `(I, H)`, `up_proj` has shape `(I, H)`, `down_proj` has shape `(H, I)`. For input rows `x` of shape `(n, H)`:

1. `g = x times gate_proj transposed`, shape `(n, I)`
2. `u = x times up_proj transposed`, shape `(n, I)`
3. `a = silu(g) times u`, element by element, where `silu(z) = z times sigmoid(z)`
4. `output = a times down_proj transposed`, shape `(n, H)`

In PyTorch terms each "times a matrix transposed" is one `torch.nn.functional.linear` call without bias.

| Name | Signature | Behaviour |
|---|---|---|
| `ExpertWeights` | frozen dataclass: `gate_proj`, `up_proj`, `down_proj` (torch tensors) | property `nbytes`: total bytes of the three tensors as stored on their device |
| `pick_device` | `pick_device(preferred_device: str, preferred_dtype: str = "auto") -> tuple[str, str]` | returns `(device, compute_dtype)` by the rules in `03-CONTRACT-COMMON.md` section 8. Raises `ValueError` if a named device is not available on this machine or a name is not one of the allowed values |
| `weights_from_blob` | `weights_from_blob(blob: ExpertBlob, device: str, compute_dtype: str) -> ExpertWeights` | reads the three byte strings in the blob's dtype, reshapes them, and returns new tensors on the device in the compute dtype. The result owns its memory: it must not share storage with the blob's bytes |
| `expert_forward` | `expert_forward(weights: ExpertWeights, rows: torch.Tensor) -> torch.Tensor` | the four steps above. `rows` is `(n, H)` on the weights' device and dtype; so is the result. The function applies `torch.no_grad()` itself, because it is called from many threads and the setting is per thread. Zero rows in gives zero rows out |
| `rows_to_numpy` | `rows_to_numpy(rows: torch.Tensor, wire_dtype: str) -> numpy.ndarray` | moves to CPU, converts to the wire dtype (`float16` or `float32`), returns a contiguous array `(n, H)` |
| `rows_from_numpy` | `rows_from_numpy(array: numpy.ndarray, device: str, dtype: str) -> torch.Tensor` | the inverse; copies, because the array may be a read-only view of a network buffer |

`ExpertBlob` is defined in `ecc/common/types.py` (fields in `04-CONTRACT-MODELFILE.md` section 5).

## 2. The tiny model and the reference: `ecc/engine/tiny_model.py`, `ecc/engine/reference.py`

**Tiny model.** A random-weight model of the same class as the real one, small enough to load in a second. Its text output is nonsense; that does not matter, because what we check is that our code path gives the same numbers as plain `transformers`.

| Config key | Value |
|---|---|
| model class | `Qwen2MoeForCausalLM` with `Qwen2MoeConfig` (it has a shared expert, the harder case) |
| `vocab_size` | 151936 |
| `hidden_size` | 64 |
| `num_hidden_layers` | 4 |
| `num_attention_heads`, `num_key_value_heads` | 4, 4 |
| `intermediate_size` | 128 |
| `moe_intermediate_size` | 96 |
| `shared_expert_intermediate_size` | 128 |
| `num_experts` | 16 |
| `num_experts_per_tok` | 4 |
| `norm_topk_prob` | false |
| `max_position_embeddings` | 2048 |

Rules for building it:

1. Seed torch with 0 before creating the model, so every machine builds identical weights.
2. After creation, re-draw every parameter that has two or three dimensions from a normal distribution with standard deviation `1 / sqrt(size of its last dimension)` (the last dimension is the number of input features, both for an ordinary weight matrix and for the library's stacked expert tensors). The library's default initialisation is so small that the experts would barely change the output, and then a wrong expert could not be detected. With this scaling a wrong expert changes the logits visibly.
3. Save it with `save_pretrained` in 32-bit floats as safetensors, split into several shard files of at most about 30 MB each, so that the multi-file case is exercised. In memory the library keeps each layer's experts stacked in two large tensors, but `save_pretrained` writes them to disk one expert at a time under the names of `04-CONTRACT-MODELFILE.md` section 3, exactly like the real model's files. The builder verifies this after saving: the first shard that mentions layer 0 must contain the name `model.layers.0.mlp.experts.0.gate_proj.weight`.
4. Building never touches the network and writes no tokenizer: every check works on token ids. Only the mode `make-tiny`, run by a human, adds one: with `--tokenizer-from <folder>` it copies the tokenizer files from a model folder the human has downloaded (the draft model's folder is the usual choice). Chatting in text with the tiny model needs that; nothing else does.

| Name | Signature | Behaviour |
|---|---|---|
| `tiny_model_dir` | `tiny_model_dir() -> Path` | `data_dir()/models/tiny` |
| `build_tiny_model` | `build_tiny_model(target_dir: Path, seed: int = 0) -> Path` | builds a tiny model into the folder by rules 1 to 3 with the given seed. Checks that need a second, different model call it with seed 1 and a temporary folder |
| `ensure_tiny_model` | `ensure_tiny_model() -> Path` | builds the tiny model (seed 0) if its `config.json` is missing; returns the folder. Every check that needs a model calls this |
| `main` | `main(argv)` | mode `make-tiny`; flags `--force` (rebuild) and `--tokenizer-from <folder>`; prints the folder and its size |

**Reference.** Plain `transformers`, no cluster code.

| Name | Signature | Behaviour |
|---|---|---|
| `FIXED_INPUT_IDS` | a tuple of 16 integers, each between 1000 and 150000, written out literally | the input every logit check uses |
| `load_reference` | `load_reference(model_dir: Path) -> model` | `AutoModelForCausalLM.from_pretrained` in 32-bit floats on the CPU, in eval mode, with the keyword `experts_implementation="eager"` so that the library uses its plain expert loop |
| `reference_logits` | `reference_logits(model_dir: Path) -> torch.Tensor` | logits of shape `(1, 16, vocab_size)` for `FIXED_INPUT_IDS`, no gradients |
| `reference_greedy` | `reference_greedy(model_dir: Path, new_token_count: int) -> list[int]` | the next tokens from greedy decoding after `FIXED_INPUT_IDS` |
| `LOGIT_TOLERANCE` | `1e-4` | largest allowed absolute difference when every float is 32-bit |
| `LOGIT_TOLERANCE_FLOAT16` | `0.05` | the same when activations travel as 16-bit floats and everything else is 32-bit |

## 3. The MoE block: `ecc/engine/moe_block.py`

**`ClusterMoeBlock`** is a `torch.nn.Module` that takes the place of a decoder layer's `mlp` attribute. It keeps the layer's router and shared expert (backbone, in the master's RAM) and asks the dispatcher for every routed expert's output.

Constructor arguments, in order: `layer_index: int`, `hidden_size: int`, `num_experts: int`, `top_k: int`, `norm_topk_prob: bool`, `shared_intermediate_size: int or None`, `dispatcher: ExpertDispatcher`.

The block creates its own sub-modules, and their attribute names are fixed, because the weights are later loaded by name and these names are the ones in the model files:

| Attribute | What it is | Parameter names it gives the model | Shape |
|---|---|---|---|
| `gate` | a `RouterGate`: a small module defined in this file that holds one parameter called `weight` and nothing else | `...mlp.gate.weight` | `(E, H)` |
| `shared_expert` | a `SharedExpert`: a module defined in this file with three bias-free linear layers called `gate_proj`, `up_proj`, `down_proj`, whose forward is the expert formula of section 1. Present only when `shared_intermediate_size` is given | `...mlp.shared_expert.gate_proj.weight`, `.up_proj.weight`, `.down_proj.weight` | `(S, H)`, `(S, H)`, `(H, S)` |
| `shared_expert_gate` | a bias-free `torch.nn.Linear` from `H` to 1. Present only with the shared expert | `...mlp.shared_expert_gate.weight` | `(1, H)` |

The block never has an attribute called `experts`.

`forward(hidden_states)` receives one tensor of shape `(batch, tokens, H)` and computes, in this order (this is the library's own arithmetic; do not reorder the steps):

1. Flatten to `x` of shape `(N, H)` with `N = batch * tokens` (use `reshape`).
2. `router_logits = x times gate.weight transposed` (one bias-free linear), shape `(N, E)`.
3. `probabilities = softmax(router_logits)` over the expert dimension, computed in 32-bit floats.
4. Take the `top_k` largest probabilities per row: `weights` and `selected`, both `(N, top_k)`.
5. If `norm_topk_prob` is true, divide each row of `weights` by its sum.
6. Convert `weights` to the dtype of `x`.
7. For every expert number that occurs in `selected`, in ascending order: find the rows that selected it and which of the `top_k` positions it took; gather those rows of `x`.
8. Call `dispatcher.run_layer(layer_index, expert_numbers, inputs)` once with all of them. It returns one output tensor per expert, same order, each `(rows, H)`.
9. Start from zeros `(N, H)`. For each expert, multiply its output rows by the matching weights and add them into the rows they came from (`index_add_`), again in ascending expert order.
10. If there is a shared expert: add `sigmoid(shared_expert_gate(x)) * shared_expert(x)`. The shared expert is added last, after every routed expert.
11. Reshape to `(batch, tokens, H)` and return that one tensor, in the dtype and on the device of the input. Never return a tuple: the decoder layer adds the result straight onto its residual.

The block holds no weights of routed experts and no statistics. Everything it knows about where experts live comes from the dispatcher.

## 4. The dispatcher: `ecc/engine/dispatcher.py`

**`ExpertDispatcher`** decides, for every expert call, where it is computed. Called from the generation thread (`run_layer`) and from the migrator and app threads (everything else). One lock guards the location table; no computation, file read or network call happens while it is held.

Constructor: `ExpertDispatcher(model_map: ModelMap, reader: ExpertReader, cache: ExpertCache, stats: EngineStats, device: str, compute_dtype: str, wire_dtype: str)`.

**Locations.** Every expert key has a current location and a home (where the placement put it). A location is a string: the constant `LOCAL` (`"@local"`, in the master's RAM), the constant `DISK` (`"@disk"`), or a satellite's node id.

| Method | Signature | Behaviour |
|---|---|---|
| `attach_cluster` | `attach_cluster(cluster: ClusterClient or None) -> None` | with `None`, every non-local expert is treated as `DISK` |
| `set_failure_listener` | `set_failure_listener(callback: Callable[[str], None] or None) -> None` | the callback is called with the node id, on the generation thread and outside the lock, each time `run_layer` marks a node down. The app uses it to tell the registry and the page |
| `apply_placement` | `apply_placement(placement: Placement) -> None` | sets home and location of every key: node index 0 becomes `LOCAL`, `-1` becomes `DISK`, any other index becomes that node's id. Validates the shape against the model map first |
| `load_local` | `load_local(keys: list[ExpertKey], on_progress: Callable[[int, int], None]) -> None` | reads each key from the model file and puts it in the cache as pinned. Raises `EngineError` if the cache has no room |
| `location_of` | `location_of(key: ExpertKey) -> str` | |
| `set_location` | `set_location(key: ExpertKey, location: str) -> None` | used by the migrator |
| `restore_home` | `restore_home(key: ExpertKey) -> None` | location goes back to home, or to `DISK` if home is a node that is down |
| `mark_node_down` | `mark_node_down(node_id: str) -> int` | every key whose location is that node becomes `DISK`; returns how many |
| `mark_node_up` | `mark_node_up(node_id: str, keys_in_ram: list[ExpertKey]) -> int` | keys whose home is that node, whose location is `DISK` and which the node reports in RAM go back to the node |
| `local_count` | `local_count() -> int` | keys currently `LOCAL` |
| `run_layer` | `run_layer(layer: int, expert_numbers: list[int], inputs: list[torch.Tensor]) -> list[torch.Tensor]` | see below |

**`run_layer`**, step by step:

1. Under the lock, read the location of each requested expert. For every key that says `LOCAL` or `DISK`, call `cache.get(key)` once, now, and keep the returned weights for step 3: a key with weights is computed locally whatever its location says, a key without weights is a disk expert. Never ask the cache a second time for the same key in this call (the migrator may remove it in between; the tensors you hold stay valid).
2. Remote experts: convert each input to a numpy array in the wire dtype, group by node, and call `cluster.call_many` once for the whole layer.
3. Local experts: run `expert_forward` with the weights kept in step 1.
4. Disk experts: read the blob, convert it, run `expert_forward`, then `cache.put(key, weights, pinned=False)`. If `put` returned true, set the key's location to `LOCAL` under the lock, provided it is still `DISK`. (Otherwise the same 17 MB would be read from disk again on every token.)
5. A node whose result is `NodeUnavailable`: call `mark_node_down` for it, log one warning `node <id> unavailable, <n> experts now read from disk`, call the failure listener, then compute its experts as in step 4. A node whose result is `RemoteError` with code `EXPERT_NOT_LOADED`: set the listed keys to `DISK` and compute that node's experts as in step 4. Any other `RemoteError`: log it, set that node's keys of this call to `DISK`, and compute them as in step 4. Generation never stops because a satellite failed.
6. Convert remote results back to tensors on the master's device and dtype.
7. Record in the stats: how many experts were local, remote and disk; round trips (one per node called); bytes sent and received; milliseconds spent waiting; and the heat of each expert (add the number of rows). When `layer` is 0, also call `stats.forward_pass()`: layer 0 runs exactly once each time the big model runs, which is how we count runs for speculative decoding.
8. Return the outputs in the order of `expert_numbers`.

Counting rules for step 7: an expert served by the fallback of step 5 counts as disk; a failed node call still counts as one round trip; bytes are the bytes of the arrays sent and received plus, per request and per reply, 16 for the frame header and `24 + 8n` for the payload header (`n` = calls in the request).

The dispatcher has read-only attributes `stats` (the `EngineStats` it was given) and `model_hash`, and the method `down_nodes() -> list[str]` (nodes marked down and not yet marked up). `dispatcher.py` never imports `ecc.net.cluster` at run time (rule 14a): any object with a `call_many` method works, which is what lets checks use a stand-in.

### `ecc/engine/session.py`

One helper that assembles the engine, used by `chat`, by the app and by every check that needs a working model. Nobody else repeats these steps.

| Name | Signature | Behaviour |
|---|---|---|
| `EngineParts` | dataclass: `index`, `model_map`, `reader`, `cache`, `stats`, `dispatcher`, `model`, `tokenizer` | |
| `build_engine` | `build_engine(model_dir: Path, cache_budget_bytes: int, device: str = "cpu", compute_dtype: str = "float32", wire_dtype: str = "float32", backbone_only: bool = False) -> EngineParts` | builds the tensor index, model map, reader, cache, stats and dispatcher, then loads the model with `load_full_model`, or with `load_backbone_model` when `backbone_only` is true. Every expert starts as `DISK`; the caller applies a placement and attaches a cluster |

## 5. Expert cache and migration: `ecc/engine/expert_cache.py` (A1), `ecc/migrate/migrator.py` (A2)

**`ExpertCache(budget_bytes: int)`**: the experts in the master's RAM. Thread-safe. It never evicts by itself.

| Method | Signature | Behaviour |
|---|---|---|
| `get` | `get(key: ExpertKey) -> ExpertWeights or None` | |
| `put` | `put(key: ExpertKey, weights: ExpertWeights, pinned: bool) -> bool` | false, and nothing stored, when it does not fit. Putting a key that is present replaces it |
| `remove` | `remove(key: ExpertKey) -> bool` | false for a pinned or absent key |
| `contains`, `is_pinned` | `(key) -> bool` | |
| `unpinned_keys` | `unpinned_keys() -> list[ExpertKey]` | |
| `bytes_used`, `budget_bytes`, `free_bytes` (properties) | `int` | |
| `set_budget` | `set_budget(budget_bytes: int) -> None` | may leave the cache over budget; the migrator then evicts |

Pinned experts are the ones the placement gave to the master; they are never evicted. Unpinned experts arrived by migration or by a disk load.

**`Migrator(dispatcher, cache, reader, stats, device, compute_dtype, on_migrated, interval_s=MIGRATE_INTERVAL_S)`** lives in `ecc/migrate/migrator.py` and is owned by A2. It is a background thread that moves hot experts into the master's RAM. `on_migrated` is called with a list of `(key, from_location, to_location)` tuples. Methods: `start()`, `stop()`, `tick() -> list[tuple[ExpertKey, str, str]]` (one cycle, callable directly so that checks need no timing), and the property `enabled` (settable).

Every `MIGRATE_INTERVAL_S` the thread calls `tick()`. A tick does nothing when not enabled; otherwise it does at most 4 moves:

To evict a key, always in this order: `dispatcher.restore_home(key)` first, then `cache.remove(key)`. To bring a key in, always in this order: read the blob, convert, `cache.put(key, weights, pinned=False)`, and only if `put` returned true, `dispatcher.set_location(key, LOCAL)`; if it returned false, drop the weights and end the tick. With these two orders a `run_layer` running at the same moment always finds what the table promises, or falls back to disk by step 1 of `run_layer`.

1. Not counted in the 4 moves: while the cache is over budget and has an unpinned key, evict its coldest unpinned key.
2. Pick the candidate: walk `stats.hottest(dispatcher.local_count() + 4)` from the top and take the first key whose location is not `LOCAL` and whose heat is at least `MIGRATE_MIN_HEAT`. If there is none, end the tick.
3. If the cache has room for one more expert, bring the candidate in. That is one move.
4. If there is no room: find the coldest unpinned key in the cache. Only if the candidate's heat is more than twice that key's heat, evict the cold one and bring the candidate in (one move). Otherwise end the tick. The factor of two prevents two experts from swapping places forever.

The thread catches and logs any error of a tick and carries on with the next one.

## 6. Stats: `ecc/engine/stats.py`

**`EngineStats(num_layers: int, num_experts: int, clock: Callable[[], float] = time.monotonic)`**: thread-safe counters. Written by the generation thread, read by the app's event thread and the migrator. The clock argument lets a check pass a fake clock, so that rates can be tested without waiting. `take_window` returns the twelve keys of the `stats` event that the engine can know (definitions in `07-CONTRACT-APP-API.md` section 4); the app adds the three master-cache keys.

| Method | Signature | Behaviour |
|---|---|---|
| `forward_pass` | `forward_pass() -> None` | counts one run of the big model |
| `token_done` | `token_done(count: int = 1) -> None` | counts generated tokens and multiplies every heat value by `HEAT_DECAY` once per token |
| `record_layer` | `record_layer(local_count: int, remote_count: int, disk_count: int, round_trips: int, bytes_sent: int, bytes_received: int, remote_ms: float) -> None` | |
| `add_heat` | `add_heat(key: ExpertKey, rows: int) -> None` | |
| `heat_of` | `heat_of(key: ExpertKey) -> float` | |
| `hottest` | `hottest(count: int) -> list[tuple[ExpertKey, float]]` | highest heat first |
| `take_heat_delta` | `take_heat_delta() -> list[tuple[int, int, int]]` | `(layer, expert, calls)` for every expert used since the previous call, then forgets them |
| `take_window` | `take_window() -> dict` | the `stats` event of `07-CONTRACT-APP-API.md` section 4: rates since the previous call plus running totals |
| `reset` | `reset() -> None` | |

## 7. Generation: `ecc/engine/generate.py`, `ecc/engine/draft.py`

**`GenerationOptions`**: dataclass with defaults: `max_new_tokens = 256`, `temperature = 0.7`, `top_p = 0.9`, `speculative = False`. A temperature of 0 means greedy decoding.

**`GenerationService(model, tokenizer, stats: EngineStats)`**: runs one generation at a time on its own thread.

| Method | Signature | Behaviour |
|---|---|---|
| `set_draft_model` | `set_draft_model(draft_model or None) -> None` | the small model used when `speculative` is true |
| `start` | `start(messages: list[dict], options: GenerationOptions, on_event: Callable[[dict], None]) -> None` | raises `EngineError` if a generation is running. Builds the prompt with the tokenizer's chat template, starts the worker thread and returns at once |
| `start_ids` | `start_ids(input_ids: list[int], options: GenerationOptions, on_event: Callable[[dict], None]) -> None` | the same as `start` but from token ids, with no tokenizer needed (the `text` of token events is empty when the model has no tokenizer) |
| `run_ids` | `run_ids(input_ids: list[int], options: GenerationOptions) -> list[int]` | blocking, no events, no tokenizer needed: returns the newly generated token ids. Checks use it to compare with `reference_greedy`. Raises `EngineError` if a generation is running |
| `stop` | `stop() -> None` | asks the running generation to end after the current token |
| `is_busy` (property) | `bool` | |

Events passed to `on_event`, from the worker thread:

| Event | Fields |
|---|---|
| token text | `type` = `"token"`, `text` (a piece of decoded text, never half a character), `index` (count of tokens so far) |
| end | `type` = `"gen_done"`, `reason` (`"eos"`, `"length"`, `"stopped"` or `"error"`), `tokens`, `seconds`, `message` (empty unless the reason is `"error"`), `token_ids` (the generated ids) |

The service calls `stats.token_done()` for every generated token. Speculative decoding uses the library's assisted generation: the draft model proposes a few tokens and the big model checks them all in one run, so several tokens can cost a single trip through the layers.

**`load_draft_model(draft_dir: Path, device: str, compute_dtype: str)`** in `ecc/engine/draft.py` loads a small ordinary model with plain `transformers`.

**`main(argv)`** in `ecc/engine/chat.py` (owned by A2, who knows the network side it drives): mode `chat`, a terminal chat for testing without the UI. After each reply it prints one line: `tokens=<n> seconds=<s> tokens_per_s=<x> local=<a> remote=<b> disk=<c> round_trips=<d>`. With `--check` it prints `max logit difference: <value>` and `calls local=<a> remote=<b> disk=<c>`, and returns 0 only if the difference is within `LOGIT_TOLERANCE` (wire `float32`) or `LOGIT_TOLERANCE_FLOAT16` (wire `float16`), and, for `--place remote` or `split`, `disk` is 0, and for `--place remote`, `local` is 0. (Without the second condition a broken network path would hide behind the disk fallback and still give correct numbers.) Flags: `--model` (folder; default the tiny model), `--peer host:port` (repeatable), `--place` (`local`, `remote`, `split` or `disk`: how experts are spread over the master and the peers), `--prompt` (one prompt, then exit; otherwise it reads lines until end of input), `--max-new-tokens`, `--temperature` (default 0, greedy), `--device`, `--dtype`, `--wire-dtype`, `--draft` (folder of a draft model; turns speculative decoding on), `--check` (instead of chatting, compare logits with the reference and print `max logit difference: <value>`; this flag forces device `cpu` and dtype `float32` on the master, and is only meaningful for a model small enough to load whole as the reference).

## 8. Loading the model on the master: `ecc/engine/backbone.py`

| Name | Signature | Behaviour |
|---|---|---|
| `install_cluster_blocks` | `install_cluster_blocks(model, dispatcher: ExpertDispatcher) -> int` | for every decoder layer (`model.model.layers`), builds a `ClusterMoeBlock` from the config, copies the router weight, the shared expert's three weights and the shared-expert gate weight out of the layer's original block, moves the new block to the model's device and dtype, and assigns it to `layer.mlp`. Returns the number of layers changed. Raises `EngineError` if a layer's `mlp` has no attribute `experts` (a dense layer: not supported) |
| `load_full_model` | `load_full_model(model_dir: Path, device: str, compute_dtype: str, dispatcher: ExpertDispatcher) -> tuple[model, tokenizer or None]` | loads the whole model with `from_pretrained`, then installs the blocks. The original expert tensors are released. Fine for the tiny model; it holds the whole model in RAM for a moment, so it is not for the real one |
| `load_backbone_model` | `load_backbone_model(model_dir: Path, index: TensorIndex, device: str, compute_dtype: str, dispatcher: ExpertDispatcher) -> tuple[model, tokenizer or None]` | builds the model's structure without allocating any routed expert, puts a `ClusterMoeBlock` in every layer, then loads only the backbone tensors from the files by name. This is what makes "too big for one machine" true |

Both loaders return the model in eval mode, with its generation settings read from the model folder, and the tokenizer if the folder has one (`None` otherwise).

**Facts about `transformers` 5.17.0**, the pinned version, verified against its source. Code written from memory of older versions gets these wrong.

| Fact | Detail |
|---|---|
| Where the layers are | `model.model.layers` is the list of decoder layers; each has the attribute `mlp` |
| How a layer calls its block | `hidden_states = self.mlp(hidden_states)` with one tensor `(batch, tokens, H)`, then adds the result to the residual. The block must return one tensor, not a tuple |
| The library's own block | `layer.mlp` has the attributes `gate` (a router module with one bare parameter `weight` of shape `(E, H)`; it is not a `Linear`), `experts` (one module holding all of the layer's experts stacked in two three-dimensional parameters, `gate_up_proj` and `down_proj`; it is not a list and cannot be indexed per expert), and for `qwen2_moe` only: `shared_expert` (three bias-free linears `gate_proj`, `up_proj`, `down_proj`) and `shared_expert_gate` (a bias-free linear to 1 output) |
| Files against memory | the model files store every expert separately under `model.layers.L.mlp.experts.E.<part>.weight`. `from_pretrained` stacks them when loading and `save_pretrained` un-stacks them when saving. Our code reads experts from the files and never from the library's stacked tensors |
| Which layers are MoE | a layer whose `mlp` has the attribute `experts`. In both real models and in the tiny model every layer is |
| Config fields | read them from the config object: `num_experts`, `num_experts_per_tok`, `norm_topk_prob`, `hidden_size`, `moe_intermediate_size`, `num_hidden_layers`, and for `qwen2_moe` `shared_expert_intermediate_size`. `norm_topk_prob` is false for the Qwen1.5 MoE model and true for the Qwen3 one: never assume it |
| Shared expert | exists in `qwen2_moe` models, does not exist in `qwen3_moe` models. Test with `hasattr(original_block, "shared_expert")` |
| No biases | nothing inside the MoE block has a bias |
| Router logits output | never pass `output_router_logits=True`; with a replaced block it fails |
| Rotary buffer | the rotary position module keeps a buffer `inv_freq` that is not stored in the model files. Any way of building the model that leaves buffers empty breaks it silently |
| Generation settings | the real models' `generation_config.json` turns sampling on. A comparison between two runs is only meaningful with sampling off, passed explicitly |

**How `load_backbone_model` builds the model** (the mechanism judged most reliable; `R07-A1` carries the full steps and a fallback):

1. Read the config. Make a copy in which every layer is declared dense (`mlp_only_layers` lists every layer index) and `intermediate_size` is tiny. A model built from this copy has a small placeholder in every layer instead of the experts.
2. Build the model from the copy inside `accelerate.init_empty_weights()` with its default setting, which leaves parameters without memory but keeps buffers real (so the rotary buffer is correct).
3. Inside a second `accelerate.init_empty_weights()` block, create a `ClusterMoeBlock` for every layer from the original config and assign it to `layer.mlp`. Its parameters take no memory yet; step 4 gives every one of them a real tensor and step 5 proves it. There is no original block to look at here: a shared expert exists when the index holds the tensor `model.layers.0.mlp.shared_expert.gate_proj.weight`.
4. Read every non-expert tensor from the files, convert it to the compute dtype, and load them all with the model's `load_state_dict(..., strict=False, assign=True)`.
5. Verify: no missing keys, no unexpected keys, and no parameter or buffer left without memory. Then move to the device, eval mode, load the generation settings and the tokenizer.
