# Phase 2 research: llama

Read-only research on 2026-10-10. The re-check section overrides the findings where they differ. Written in the agents' short style.

## Summary
Read-only. Nothing saved, nothing run from llama.cpp. Checked today 2026-10-10 against GitHub API, source at tag b11429, Hugging Face API, live Range test from Node 24.19.

Big finds:
- Pin stay b11429 (= release v0.6.0, 2026-10-05). Mac file: llama-b11429-bin-macos-arm64.tar.gz, 11971406 bytes, sha256 740288ec6887be94280a5dfa25b5e23a78285cab104519e6c7e218904ee82459. Inside: llama-server + dylibs, rpath @loader_path, min macOS 13.3. Runs from plain folder (read from file headers, not run).
- Binaries ad-hoc signed only. Not notarized. Gatekeeper pass when Node downloads = expected, NOT tested.
- Chat model pick: unsloth/Qwen3.5-4B-GGUF, Qwen3.5-4B-Q4_K_M.gguf, 2.74 GB, Apache-2.0, no gate, thinking off by default in its template. Fallback: mistralai/Ministral-3-8B-Instruct-2512-GGUF Q4_K_M, 5.20 GB (no thinking mode at all).
- Gemma 4 E4B NOT default: open bug #30256 on build 11429, json_schema + thinking off still thinks, long prompt ends empty.
- Embedding: Qwen3-Embedding-0.6B Q8_0 stays. EmbeddingGemma 2 can NOT load at b11429 (arch gemma-embedding2 missing; present at b11552).
- Download with plain fetch works, no account: 302 to CDN, Range gives 206, sha256 in X-Linked-Etag and tree API. @huggingface/hub 2.17.6 does not resume.
- No measured speed for Qwen3.5-4B or any M5. Nearest measured: Mac mini M4, Qwen3 4B Q4_K_M, 36.2 tok/s write, 300-417 tok/s read. Long passages = slow first read. Keep passage budget small.
- All memory numbers here = my estimate.

## Claims

### R1a [confirmed] (load-bearing)
Newest llama.cpp release has ready macOS arm64 archive; pin it by tag and sha256.

Evidence: GitHub API: releases/latest = v0.6.0 (2026-10-05T16:56:22Z), holds only nightly-tag.txt, content 'b11429'. Tag b11429 asset llama-b11429-bin-macos-arm64.tar.gz, size 11971406, digest sha256:740288ec6887be94280a5dfa25b5e23a78285cab104519e6c7e218904ee82459. Newest nightly today: b11552 (2026-10-10T19:52:01Z), llama-b11552-bin-macos-arm64.tar.gz, 12086252 bytes, sha256:f4b33fe40d098033fb1a19a8a4a84383c4ca84c37b6a60d9f9a253f349b48c07; nightlies are prerelease, several per day.

For the build: Hard-code URL + size + sha256 in one manifest file in repo. Do not call GitHub API at run time (unauth limit hit during this research). Check sha256 before unpack.

Sources: https://api.github.com/repos/ggml-org/llama.cpp/releases/latest, https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b11429, https://github.com/ggml-org/llama.cpp/releases/download/b11429/llama-b11429-bin-macos-arm64.tar.gz, https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=8

### R1b [partly] (load-bearing)
Archive runs from plain folder, no install; binary still named llama-server.

Evidence: Listed archive from stream: folder llama-b11429/ with llama-server (49984 bytes, thin stub), libllama-server-impl.dylib (9192120), libllama-common, libllama, libmtmd, libggml, libggml-base, libggml-cpu, libggml-metal, libggml-blas, libggml-rpc dylibs plus version symlinks; also llama (unified, README says 'llama serve'), llama-fit-params, llama-bench, llama-tokenize. Mach-O headers: LC_RPATH @loader_path, all llama libs @rpath, LC_BUILD_VERSION minos 13.3.0 sdk 26.5.0; workflow sets -DCMAKE_OSX_DEPLOYMENT_TARGET=13.3 and -DCMAKE_INSTALL_RPATH='@loader_path'. Unpacked about 32 MB (my sum of listed sizes). NOT run here, so 'runs' is read from headers only.

For the build: Unpack with system /usr/bin/tar -xzf (keeps symlinks; same tool on Ubuntu). Keep whole folder together. Spawn <folder>/llama-b11429/llama-server by full path. First build step: run `llama-server --version` and fail loud.

Sources: https://github.com/ggml-org/llama.cpp/releases/download/b11429/llama-b11429-bin-macos-arm64.tar.gz, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/.github/workflows/release.yml, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/README.md

### R1c [refuted] (load-bearing)
Mac binaries are Developer-ID signed and notarized.

Evidence: Code signature in llama-server, libllama-server-impl.dylib, libggml-metal: one CodeDirectory, flags 0x20002 = adhoc + linker-signed. No Developer ID, so no notarization possible. macOS on this Mac reports 'assessments enabled' (spctl --status).

For the build: File with quarantine mark would be blocked. Never let owner fetch archive by browser. Engine fetches it itself.

Sources: https://github.com/ggml-org/llama.cpp/releases/download/b11429/llama-b11429-bin-macos-arm64.tar.gz

### R1d [unverified] (load-bearing)
Archive fetched by Node process and unpacked by tar gets no quarantine mark, so Gatekeeper stays quiet.

Evidence: Apple doc: LSFileQuarantineEnabled = 'whether the files this app creates are quarantined by default'. Packaged app Info.plist (release/GX10 Council-darwin-arm64) has no such key; plain Node has no bundle. So no mark expected. This is inference; no source opened settles it for macOS 26.6.2 and nothing was downloaded to test.

For the build: Make it first test of Phase 2: after unpack run `xattr -p com.apple.quarantine <llama-server>` (want: no such xattr) then `llama-server --version`. Test from dev Node AND from packaged Electron app. If blocked: stop and report, do not strip marks silently.

Sources: https://developer.apple.com/documentation/bundleresources/information-property-list/lsfilequarantineenabled

### R2a [confirmed] (load-bearing)
Planned flag spellings all exist at b11429.

Evidence: In common/arg.cpp at b11429: --host, --port, -c/--ctx-size, -ngl/--gpu-layers (number, 'auto', 'all'), -np/--parallel, --jinja/--no-jinja, -rea/--reasoning [on|off|auto], --reasoning-format, --reasoning-budget, -cram/--cache-ram, --cache-prompt/--no-cache-prompt, -ctxcp/--ctx-checkpoints, --no-ui/--no-webui, --offline, --api-key (env LLAMA_API_KEY), --api-key-file, --log-file, --log-timestamps, --log-prefix, --log-colors, -fit/--fit [on|off], -lm/--load-mode, --slots/--no-slots, --sleep-idle-seconds, -a/--alias, --embedding/--embeddings, --pooling, -b, -ub. --jinja default is on (common.h use_jinja = true).

For the build: Use flag set in recommendations. Pass API key by env LLAMA_API_KEY, not argv (argv shows in ps). Keep flags in one typed list; a start-up self-test parses `llama-server --help` is not needed if tag is pinned.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/arg.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/common.h

### R2b [refuted] (load-bearing)
llama-server defaults are fine for a 24 GB laptop.

Evidence: common.h at b11429: n_ctx = 0 (= model trained size; Qwen3.5-4B GGUF says 262144), fit_params = true with fit_params_min_ctx 4096 (silently shrinks context), cache_ram_mib = 8192, n_ctx_checkpoints = 32, ui = true, port 8080 (earlier research: 9931 on master), endpoint_slots = true. server.cpp: -np unset becomes 4 slots with kv_unified = true.

For the build: Always pass -c, -np 1, --fit off, --cache-ram 0, --ctx-checkpoints 4, --no-webui, --port. Then read /props default_generation_settings.n_ctx and check it equals what was asked.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/common.h, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server.cpp, https://huggingface.co/api/models/unsloth/Qwen3.5-4B-GGUF

### R3a [confirmed] (load-bearing)
Three ungated 2-5 GB chat GGUFs exist that load at b11429.

Evidence: HF API, all gated:false, licence apache-2.0. (1) unsloth/Qwen3.5-4B-GGUF @ e87f176479d0855a907a41277aca2f8ee7a09523, Qwen3.5-4B-Q4_K_M.gguf, 2740937888 bytes, sha256 00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4, arch qwen35, ctx 262144. (2) mistralai/Ministral-3-8B-Instruct-2512-GGUF @ 0102285ad796bd99af90f58de616092e5630e970, Ministral-3-8B-Instruct-2512-Q4_K_M.gguf, 5198911904 bytes, sha256 33e7a72cf5e6e2cfc2f2847075acc013d68bba023e35310cef86b5cf8fdca761, arch mistral3, ctx 262144. (3) google/gemma-4-E4B-it-qat-q4_0-gguf @ 4b4a2c1d584be7264f87aac328a1bc739ce81b6c, gemma-4-E4B_q4_0-it.gguf, 5154941280 bytes, sha256 676c35070db6dbe52f93e9c864ee0fba4eddea94b9c875d9cb10daff453fbaee, arch gemma4, ctx 131072. Also ibm-granite/granite-4.2-3b-GGUF Q4_K_M 2244011552 bytes and granite-4.2-8b-GGUF Q4_K_M 5347917952 bytes (arch granite, ctx 131072). All four arch names are in src/llama-arch.cpp at b11429. Live test: Qwen file fetched 16 bytes with no token, magic 'GGUF'.

For the build: Model manifest in repo: repo, commit, file, bytes, sha256, licence, context, thinking switch, sampler. Download by commit, never by 'main'.

Sources: https://huggingface.co/api/models/unsloth/Qwen3.5-4B-GGUF?blobs=true, https://huggingface.co/api/models/mistralai/Ministral-3-8B-Instruct-2512-GGUF?blobs=true, https://huggingface.co/api/models/google/gemma-4-E4B-it-qat-q4_0-gguf?blobs=true, https://huggingface.co/api/models/ibm-granite/granite-4.2-8b-GGUF?blobs=true, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/src/llama-arch.cpp

### R3b [partly] (load-bearing)
Small models think by default, so engine must switch thinking off.

Evidence: Differs per model, read from GGUF chat templates. Qwen3.5-4B GGUF: thinks only when enable_thinking is defined and true, so OFF by default (Qwen card says family default is thinking; Unsloth doc says small models have reasoning disabled by default). Gemma 4 E4B: `enable_thinking | default(false)`, OFF. Granite 4.2: `enable_thinking ... else True`, ON. Ministral-3 Instruct: no enable_thinking in template. All four templates contain tools.

For the build: Still send it explicit: server `--reasoning off` plus per request `chat_template_kwargs: {"enable_thinking": false}`. Self-test at model install: one prompt, assert reasoning_content empty.

Sources: https://huggingface.co/api/models/unsloth/Qwen3.5-4B-GGUF, https://huggingface.co/api/models/google/gemma-4-E4B-it-qat-q4_0-gguf, https://huggingface.co/api/models/ibm-granite/granite-4.2-8b-GGUF, https://huggingface.co/Qwen/Qwen3.5-4B/raw/main/README.md, https://unsloth.ai/docs/models/qwen3.5

### R3c [refuted] (load-bearing)
Gemma 4 E4B is a safe default for JSON-schema citations.

Evidence: Issue #30256 (open, filed 2026-10-09 on build 11429, Gemma 4 E2B): response_format json_schema + enable_thinking false still gives reasoning_content 3 of 3; with long prompt and big schema ends finish_reason 'length' with empty content 15 of 15. Workaround in issue: send GBNF in `grammar` field. `--reasoning off` and `--reasoning-budget 0` did not help (on build 11146). Reported on E2B and Linux CUDA; E4B on Metal not tested by anyone I found.

For the build: Do not ship Gemma 4 as default at b11429. Always set max_tokens. Treat empty content + finish_reason 'length' as failure and retry once.

Sources: https://github.com/ggml-org/llama.cpp/issues/30256

### R3d [refuted] (load-bearing)
Measured speed exists for the picked model on this Mac class.

Evidence: No measurement found for Qwen3.5-4B on any Mac, none for any M5. Nearest measured (author's own run, 2026-09-12): Mac mini M4 32 GB, official macOS arm64 b10929, llama-bench, Qwen3 4B Q4_K_M: read 416.6 tok/s (512 tokens) and 299.9 tok/s (8192 tokens), write 36.2 tok/s empty and 24.6 tok/s at 8K depth; Qwen3 8B Q4_K_M: read 223.8 / 174.5, write 19.7 / 16.1. willitrunai.com figures (35 tok/s Qwen3.5-4B on M4 Air; 13.3 tok/s Gemma 4 E4B) are site estimates, not runs.

For the build: Plan on roughly 300-400 tok/s read, 25-40 tok/s write until measured (my estimate from the M4 run; different model). 8,000 passage tokens = about 20-27 s cold read. Cap passages near 4,000 tokens, show progress via return_progress. Measure on this Mac with bundled llama-bench in week one. MacBook Air has no fan: long runs may slow (my inference).

Sources: https://vettedconsumer.com/mac-mini-m4-32gb-first-party-benchmark-qwen3-llama-cpp/, https://willitrunai.com/can-run/qwen-3.5-4b-on-m4-air-24gb, https://willitrunai.com/can-run/gemma-4-e4b-on-m4-air-24gb

### R4a [confirmed] (load-bearing)
Qwen3-Embedding-0.6B GGUF is still the embedding pick.

Evidence: Qwen/Qwen3-Embedding-0.6B-GGUF @ 370f27d7550e0def9b39c1f16d3fbaa13aa67728, Qwen3-Embedding-0.6B-Q8_0.gguf, 639150592 bytes, sha256 06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439, apache-2.0, gated false, arch qwen3, context 32768, dimension up to 1024 (card: user-defined 32 to 1024). Card command: `llama-server -m model.gguf --embedding --pooling last -ub 8192`. Query form on base card: `Instruct: {task_description}\nQuery:{query}`; documents get no instruction. Newer rival EmbeddingGemma 2 (ggml-org/embeddinggemma-2-GGUF, Q8_0 309855456 bytes, 768d, 8,192 ctx, mean pooling, apache-2.0, uploaded 2026-10-06) has arch 'gemma-embedding2', which is NOT in src/llama-arch.cpp at b11429 but is at b11552.

For the build: Use Qwen3-Embedding-0.6B Q8_0, store 1024-d float32. Store model id + dimension + instruction text with the index, so a later model swap forces a clean re-index. Smaller option that loads at b11429: ggml-org/embeddinggemma-300M-GGUF embeddinggemma-300M-Q8_0.gguf (333590944 bytes, ctx 2048, arch gemma-embedding; repo shows no licence field) - not advised.

Sources: https://huggingface.co/api/models/Qwen/Qwen3-Embedding-0.6B-GGUF?blobs=true, https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/raw/main/README.md, https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/raw/main/README.md, https://huggingface.co/api/models/ggml-org/embeddinggemma-2-GGUF?blobs=true, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/src/llama-arch.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11552/src/llama-arch.cpp

### R4b [confirmed] (load-bearing)
/v1/embeddings takes a batch of strings and returns one vector each, already normalised.

Evidence: README at b11429: `{"input": ["hello", "world"], "model":"GPT-4", "encoding_format": "float"}`; 'normalized using the Eucledian norm'; needs pooling other than none. Source: reply `{model, object:"list", usage:{prompt_tokens,total_tokens}, data:[{embedding, index, object:"embedding"}]}`; encoding_format 'base64' returns raw float32 bytes; each input becomes its own task; server without --embeddings answers not_supported_error 'Start it with `--embeddings`'. With pooling LAST an input may span several ubatches; an input larger than slot context errors with exceed_context_size_error. No `dimensions` field handling found in source.

For the build: Batch 16-32 chunks per request, read data[i].index to map back. Keep chunks well under per-slot context (plan 2048 with -c 8192 -np 4; source reading, not run). If shorter vectors wanted, cut and re-normalise in code.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/README.md, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-context.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-common.cpp

### R5a [confirmed] (load-bearing)
Chat stream is OpenAI-style chunks plus timings and optional read progress.

Evidence: Source at b11429: first chunk delta `{"role":"assistant","content":null}`; later chunks `choices[0].delta`, object 'chat.completion.chunk', fields created, id, model, system_fingerprint; last chunk `finish_reason` 'stop' | 'length' | 'tool_calls' with empty delta and `timings` on the final object; with `stream_options.include_usage` one more chunk with empty `choices` and `usage`; then `data: [DONE]`. timings: cache_n, prompt_n, prompt_ms, prompt_per_second, predicted_n, predicted_ms, predicted_per_second. `timings_per_token: true` adds timings per chunk. `return_progress: true` adds `prompt_progress` {total, cache, processed, time_ms}. `cache_prompt` default true. Silent stream gets SSE comment ping `:\n\n` every 30 s (source comment names undici time-outs). Mid-stream error arrives as `data: {"error":{...}}`; an error before first token is a plain HTTP error reply. README names `reasoning_content` for thoughts.

For the build: Write own small SSE reader on fetch body: skip lines starting ':', stop on [DONE], handle {error}. Send stream:true, return_progress:true, stream_options.include_usage:true. Save timings with each message.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-task.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-context.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/README.md

### R5b [partly] (load-bearing)
Closing the HTTP connection stops generation fast.

Evidence: README-dev: 'By default a streaming generation is bound to its HTTP socket: when the socket drops ... the generation aborts'. Source: handler checks should_stop before each chunk and while waiting, wait wakes every HTTP_POLLING_SECONDS = 1; reader then posts cancel tasks. So stop is near instant while tokens flow and within about 1 s plus the running batch while reading the prompt - source reading, not timed. Trap: header X-Conversation-Id turns on resumable streams; then socket close does NOT stop, only `DELETE /v1/stream?conv_id=<id>` does.

For the build: Stop = AbortController.abort() on the fetch. Never send X-Conversation-Id. Test: abort mid-answer, then next request must start within 2 s; log result.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/README-dev.md, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-context.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-queue.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-stream.cpp

### R5c [confirmed] (load-bearing)
/health, /props and a token count endpoint give what the engine needs.

Evidence: /health is public (no key): 503 `{"error":{"message":"Loading model","type":"unavailable_error","code":503}}` while loading, 200 `{"status":"ok"}` when ready; no load progress. All other routes also 503 until ready. GET /props: default_generation_settings.n_ctx, total_slots, model_alias, model_path, modalities, chat_template, chat_template_caps, build_info, is_sleeping, endpoint_slots. Token count: POST /v1/chat/completions/input_tokens with a chat body returns `{"object":"response.input_tokens","input_tokens":11}`; POST /tokenize also exists.

For the build: Ready poll: GET /health every 250 ms; connection refused or 503 = wait; 200 = ready; child exit = fail. Then GET /props and compare build_info and n_ctx. Count tokens with /v1/chat/completions/input_tokens before sending, to trim history and passages.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/README.md, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-http.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-context.cpp

### R5d [confirmed] (load-bearing)
response_format json_schema nesting and context-overflow error have fixed shapes.

Evidence: server-common.cpp: type 'json_schema' reads `response_format.json_schema.schema`; type 'json_object' reads `response_format.schema`; top-level `json_schema` also accepted; json_schema together with `grammar` throws 'Cannot use both json_schema and grammar'; empty schema means any object. Overflow: HTTP 400 `{"error":{"code":400,"message":"request (N tokens) exceeds the available context size (M tokens), try increasing it","type":"exceed_context_size_error","n_prompt_tokens":N,"n_ctx":M}}`. Context shift is off by default (ctx_shift = false). Other error types: invalid_request_error 400, authentication_error 401, not_found_error 404, server_error 500, not_supported_error 501, unavailable_error 503.

For the build: Send `response_format: {"type":"json_schema","json_schema":{"schema":{...}}}`. Validate reply in code anyway. Map exceed_context_size_error to a plain message and a trim-and-retry path. Always set max_tokens.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-common.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-context.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-task.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/common.h

### R6a [confirmed] (load-bearing)
Model files download in Node with resume and no account.

Evidence: Live test, Node 24.19 fetch, no token: HEAD on https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf gives 302 with x-linked-size 2740937888, x-linked-etag "00fe7986..." (= sha256), x-repo-commit, accept-ranges bytes. GET with `Range: bytes=2740937872-` follows redirect to us.aws.cdn.hf.co and returns 206, content-range bytes 2740937872-2740937887/2740937888. CDN `etag` is the xet hash, NOT sha256. AbortController abort raised AbortError mid-body. Tree API /api/models/<repo>/tree/<commit> returns 200 with lfs.oid = sha256 and size, no token.

For the build: Plain fetch. Write to <file>.part plus <file>.part.json {url, commit, bytes, sha256}. Resume: stat .part, send Range from that size to the huggingface.co URL again (CDN link is signed and short-lived; never store it); want 206 and matching Content-Range start, else restart from 0. After last byte: stream whole file through node:crypto sha256, compare with manifest, then rename. Progress = bytes written / bytes. Pause and cancel = abort(); cancel also deletes .part.

Sources: https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf, https://huggingface.co/api/models/unsloth/Qwen3.5-4B-GGUF/tree/e87f176479d0855a907a41277aca2f8ee7a09523

### R6b [refuted]
@huggingface/hub gives resume for free.

Evidence: npm: @huggingface/hub 2.17.6, MIT, node >=18, unpackedSize 3156257, deps @huggingface/tasks and @huggingface/xetchunk-wasm. Source on main (not checked at the 2.17.6 tag): downloadFileToCacheDir pipes the body into createWriteStream(`${blobPath}.incomplete`) then renames; no Range, no hash check, uses console.debug, and stores in the HF cache layout (blobs/snapshots symlinks).

For the build: Skip the package. One small own module (about 150 lines) covers both model files and the llama.cpp archive.

Sources: https://registry.npmjs.org/@huggingface/hub, https://raw.githubusercontent.com/huggingface/huggingface.js/main/packages/hub/src/lib/download-file-to-cache-dir.ts, https://raw.githubusercontent.com/huggingface/huggingface.js/main/packages/hub/README.md

### R7 [partly] (load-bearing)
Node can supervise llama-server cleanly: spawn, ready poll, logs, stop, orphan sweep; two servers fit in 24 GB.

Evidence: Source: server.cpp installs one handler for SIGINT and SIGTERM that runs shutdown; a second signal prints 'Received second interrupt, terminating immediately.' and exit(1). /health gives ready state. --log-file exists. Undocumented: a server started with env LLAMA_SERVER_ROUTER_PORT set acts as router child and shuts down on stdin EOF (server-models.cpp) - internal, may change. Memory is my estimate, not measured: chat about 4-5 GB (2.74 GB weights + 16k KV + buffers), embedder about 1 GB, Electron about 1 GB; total about 7 GB of 24 GB.

For the build: child_process.spawn (no shell), stdio pipes to own log file plus --log-file. Stop: SIGTERM, wait 5 s, SIGKILL. Write servers.json {pid, port, startedAt, binaryPath} on spawn; at engine start sweep: for each pid alive, confirm command path is our llama-server (ps -p <pid> -o command=), then SIGTERM. Never kill by name. Ports: ask OS (net listen on 0, read port, close) then pass --port; retry once on bind fail. Record RSS of both servers after first real chat.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-models.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/arg.cpp

### R8 [unverified] (load-bearing)
A 4B-class model can cite [n] with a verbatim quote well enough when the prompt is laid out right.

Evidence: No source found on 4B local models with quote citations. Related evidence: a 2026 clinical QA study found smaller models drop on verbatim compliance (one small model about 69% of citations verbatim) and that even verified quotes fully support only about 37% of claims for the top model; a practitioner guide warns quotes stitched from two sources pass a check if sources are joined. So code check proves 'quote is on that page', not 'claim is true'. Layout advice below is my inference.

For the build: Build a 30-question test set from own files before trusting any layout. Measure: share of citations whose quote matches the cited page. Keep the checker strict per passage, never across joined passages.

Sources: https://arxiv.org/pdf/2609.15964, https://arxiv.org/html/2510.20303v1, https://docs.gloo.com/best-practices/trustworthy-grounded-applications

### R9 [partly] (load-bearing)
Move to GX10 changes binary and a few flags, not the engine design.

Evidence: Same tag has Linux arm64 CUDA assets: llama-b11429-bin-ubuntu-cuda-13.4-arm64.tar.gz (147639003 bytes, sha256 9c76d072276c0faa7fc1b5cbf715b4186dd2e8d7f16acd20b67daab24c82bd22) plus runtime cudart-llama-b11429-bin-ubuntu-cuda-13.4-arm64.tar.gz (552521413 bytes, sha256 ad62e46cdc2e8636fa91e883b9e9ad779516f61cc478ece1c90e5dbc905a7d29); workflow says unpack cudart next to binaries ($ORIGIN rpath). CPU-only: llama-b11429-bin-ubuntu-arm64.tar.gz (13682895 bytes). Earlier research: nobody has reported this archive running on DGX OS; still true as far as I looked.

For the build: Keep platform bits in one table keyed by `${process.platform}-${process.arch}`: archive URL, sha256, extra archives, load-mode flag, memory probe. Everything else (API client, downloader, supervisor, GGUF files) stays same.

Sources: https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b11429, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/.github/workflows/release.yml

## Recommendations
- **llama.cpp build**: Tag b11429 (release v0.6.0). https://github.com/ggml-org/llama.cpp/releases/download/b11429/llama-b11429-bin-macos-arm64.tar.gz , 11971406 bytes, sha256 740288ec6887be94280a5dfa25b5e23a78285cab104519e6c7e218904ee82459. Engine downloads it, checks sha256, unpacks with system tar into <appData>/runtime/, spawns llama-b11429/llama-server. _Why:_ Build behind the named release. Every flag and API shape here was read at this tag. Same tag has the GX10 archive. No install, no compile.
- **Chat server flags (Mac, Phase 2)**: env LLAMA_API_KEY=<random 32 bytes hex>; `llama-server -m <models>/Qwen3.5-4B-Q4_K_M.gguf --alias chat --host 127.0.0.1 --port <free> -c 16384 -np 1 -ngl all --fit off --cache-ram 0 --ctx-checkpoints 4 --reasoning off --no-webui --no-slots --offline --log-file <logs>/chat.log --log-timestamps --log-prefix --log-colors off` _Why:_ All spellings checked in common/arg.cpp at b11429. Explicit -c and -np with --fit off fail loud instead of silent shrink. --cache-ram 0 removes 8192 MiB ceiling and the open cross-chat bug #27148. --offline and 127.0.0.1 back 'no web ever'. --jinja is default on, no flag needed. Load mode left at default (mmap) on Mac.
- **Default chat model**: unsloth/Qwen3.5-4B-GGUF @ e87f176479d0855a907a41277aca2f8ee7a09523, file Qwen3.5-4B-Q4_K_M.gguf, 2740937888 bytes, sha256 00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4. URL https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf . Sampler for document answers: temperature 0.7, top_p 0.8, top_k 20 (card, non-thinking); presence_penalty 0 for the citation call (my inference: penalty fights verbatim copying; test it). _Why:_ Apache-2.0, no gate (live fetch with no token worked). 2.74 GB. Thinking off by default in this GGUF's template. Tools in template. Arch qwen35 is in b11429. No open json_schema bug found for it. Same family runs on GX10 later.
- **Fallback chat model**: mistralai/Ministral-3-8B-Instruct-2512-GGUF @ 0102285ad796bd99af90f58de616092e5630e970, file Ministral-3-8B-Instruct-2512-Q4_K_M.gguf, 5198911904 bytes, sha256 33e7a72cf5e6e2cfc2f2847075acc013d68bba023e35310cef86b5cf8fdca761. Earlier research: card asks temperature under 0.1. _Why:_ Other maker, other template, official GGUF from the maker, Apache-2.0, no gate, no thinking mode at all - so the whole class of thinking-versus-grammar bugs cannot hit it. Bigger model, likely better answers, about half the speed (my estimate from the 4B vs 8B M4 run).
- **Embedding model and server**: Qwen/Qwen3-Embedding-0.6B-GGUF @ 370f27d7550e0def9b39c1f16d3fbaa13aa67728, file Qwen3-Embedding-0.6B-Q8_0.gguf, 639150592 bytes, sha256 06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439. Second server: `llama-server -m <models>/Qwen3-Embedding-0.6B-Q8_0.gguf --alias embed --embeddings --pooling last --host 127.0.0.1 --port <free2> -c 8192 -np 4 -b 2048 -ub 2048 -ngl all --fit off --cache-ram 0 --no-webui --no-slots --offline --log-file <logs>/embed.log`. Query text: `Instruct: Given a question, retrieve passages from the user's documents that answer it\nQuery:<question>`. Document chunks: plain text. Request: POST /v1/embeddings `{"input":["chunk a","chunk b"],"encoding_format":"float"}`. _Why:_ Loads at pinned build, 1024-d, Apache-2.0, no gate, card gives exact llama-server command. 8192 / 4 slots = 2048 tokens per input (source reading, not run).
- **Downloader**: Own module on global fetch (Node 24): .part file + .part.json sidecar, Range resume against the huggingface.co /resolve/<commit>/<file> URL, node:crypto createHash('sha256') stream check against manifest, AbortController for pause and cancel, progress events by bytes. Same module fetches the llama.cpp archive from GitHub (size + sha256 from manifest). _Why:_ Live test passed: 302, 206, AbortError, no token. No new dependency. One code path for Mac and GX10.
- **Chat API use**: POST /v1/chat/completions with stream:true, return_progress:true, stream_options:{include_usage:true}, max_tokens set, chat_template_kwargs:{enable_thinking:false}, Authorization: Bearer <key>. Stop = abort the fetch. Regenerate = same messages minus last answer. Token count before send = POST /v1/chat/completions/input_tokens. Structured calls: response_format {type:'json_schema', json_schema:{schema}} then validate in code, one retry. _Why:_ All read from source and README at b11429. Append-only message list keeps the prompt cache (cache_n in timings shows it).
- **How answers cite**: Two calls. Call 1 (streamed Markdown): system rules short; then passages as numbered blocks `[1] file: <name> | page: <p>` + text; question LAST; rules: answer only from passages, put [n] after each claim, say 'not in the files' if missing. Call 2 (not streamed, same messages + answer + one instruction): response_format json_schema `{citations:[{n: enum of passage numbers actually sent, quote: string maxLength 240}]}`, temperature low, presence_penalty 0. Code: normalise both sides (Unicode NFKC, curly quotes, hyphen line breaks, whitespace, case), require quote as substring of passage n; if not, fuzzy-find nearest span in passage n and swap in the true page text; if none, drop that citation and flag the sentence unverified. UI shows only quotes that passed. _Why:_ Keeps live Markdown streaming. Enum makes a made-up passage number impossible. Call 2 is cheap: prefix is cached. Code check never trusts the model's quote text.
- **Supervisor**: One small class used for both servers: spawn by full path with env key, pipe stdout/stderr to log, poll /health every 250 ms (time-out 120 s), check /props build_info and n_ctx, SIGTERM then SIGKILL after 5 s, servers.json pid registry with sweep at start, OS-chosen ports. Start embedder only while indexing or searching is needed; start chat server on first chat. _Why:_ SIGTERM path and health states confirmed in source. Registry sweep covers engine crash on both macOS and Linux with no extra package.
- **GX10 move (outline)**: Swap archive to llama-b11429-bin-ubuntu-cuda-13.4-arm64.tar.gz + cudart-llama-b11429-bin-ubuntu-cuda-13.4-arm64.tar.gz (unpacked into same folder). Add load-mode test (`-lm dio` vs `none`). Engine listens on LAN; llama-server stays on 127.0.0.1 there. Run engine under systemd. Memory probe reads MemAvailable. Bigger chat model from manifest. Rest unchanged. _Why:_ Same tag, same flags, same API, same GGUF files, same downloader.

## Risks
- Gatekeeper: binaries are ad-hoc signed, not notarized. If macOS 26.6.2 marks or blocks files fetched by the app, nothing runs. Expected fine, NOT tested. Test first.
- Citation quality with a 4B model is unknown. A quote can match the page and still not support the claim; code check cannot see that. Needs a real test set from owner's files.
- Speed unknown on this Mac. Nearest measured figure is another model on an M4: about 300-400 tok/s read. Big passage packs mean 10-30 s before first word. Fanless Air may slow under long load (my inference).
- One slot and --cache-ram 0: every chat switch re-reads that chat's whole prompt. Long chats feel slow to reopen. Turning the RAM cache on brings back open bug #27148 (wrong chat restored).
- Structured output breaks per template: #30256 open on this exact build for Gemma 4. A new model can fail the same way. Each model needs an install self-test (thinking off honoured, json_schema returns content).
- Qwen card sampler has presence_penalty 1.5; may hurt verbatim quotes. Unmeasured.
- Qwen3-Embedding GGUF may need `<|endoftext|>` at end of each input; server adds EOS only if the GGUF says so. Not checked. Wrong = weaker search, silently.
- Embedding model swap later (for example EmbeddingGemma 2 after a llama.cpp bump) forces full re-index of all files.
- Engine crash leaves llama-server holding 3-5 GB; without the pid sweep a second copy loads. On GX10 same fault costs tens of GB.
- Hugging Face or GitHub file can be moved or deleted by its owner. Pinned commit + sha256 detect it but cannot fix it. Keep downloaded files; never auto-delete.
- API key in argv would show in process list; use env LLAMA_API_KEY. /health stays open without key by design.
- Prebuilt CUDA arm64 archive still untested on DGX OS (earlier research). Phase 3 may need a source build with sudo.
- llama.cpp moves fast: flags and defaults changed within days before. Any bump of the pinned tag needs the flag list and API shapes re-read.
- Context overflow is a hard HTTP 400, no auto-shift. Long chat plus passages will hit 16384 unless engine counts tokens and trims.

## Open questions
- Real test: after Node downloads and tar unpacks the archive on this Mac, does `xattr -p com.apple.quarantine` show nothing and does `llama-server --version` run - from dev Node and from the packaged Electron app?
- Real test: Qwen3.5-4B-Q4_K_M on this M5 Air - read tok/s and write tok/s at 4k, 8k, 16k context (bundled llama-bench), RSS of the server, and speed after 10 minutes of load.
- Real test: does Qwen3.5-4B with thinking off return clean JSON for the citation schema 20 of 20 times, and what share of its quotes match the cited page on 30 questions over owner's own files?
- Real test: same 30 questions on Ministral-3-8B-Instruct Q4_K_M. Is the answer quality worth half the speed?
- Real test: Qwen3-Embedding-0.6B via llama-server - is EOS added by the server (--verbose-prompt shows last token), and does appending `<|endoftext|>` change search results?
- Real test: abort mid-answer and mid-prompt-read; how many ms until the slot is free?
- Real test: does --log-file also keep stdout output, or must the engine pick one?
- Owner: is 10-25 s wait before first word acceptable when many passages are attached, or should the app send fewer passages to answer sooner?
- Owner: what languages are the personal files in? Decides embedding instruction text and whether a multilingual check is needed.
- Owner: may the app download about 3.4 GB (chat 2.74 GB + embedder 0.64 GB + runtime 12 MB) on first run without asking, or must it ask first?
- Owner: should the chat model unload after idle time to save battery and memory (costs a few seconds on next question)?
- GX10: which DGX OS, kernel and CUDA are installed, and does llama-b11429-bin-ubuntu-cuda-13.4-arm64 start there?

## Independent re-check (overrides the above)

- **R1a** [confirmed] 
- **R1b** [partly] Listing right. Still not run (read-only job). Me pull whole archive to memory: 11971406 bytes, sha256 740288ec6887be94280a5dfa25b5e23a78285cab104519e6c7e218904ee82459, match. Exact unpacked sum: 31762278 bytes. Mach-O read by me: llama-server minos 13.3.0, sdk 26.5.0, LC_RPATH @loader_path, all llama libs @rpath. Extra: also loads system /usr/lib/librdma.dylib. Archive holds more tools than listed (llama-cli, llama-completion, libllama-*-impl.dylib). Version symlinks are real tar symlinks: unpack tool must keep them.
- **R1c** [refuted] 
- **R1d** [partly, disagrees] Half now measured on this Mac, half still guess. Measured (read-only xattr): two things Node fetched before carry only com.apple.provenance, NO com.apple.quarantine: ui/node_modules/electron/dist/Electron.app (fetched at npm ci) and ~/Library/Caches/ms-playwright/chromium-1248/chrome-mac-arm64/Google Chrome for Testing.app. Packaged app release/GX10 Council-darwin-arm64/GX10 Council.app: no LSFileQuarantineEnabled key, signature adhoc flags 0x20002, no entitlements, and it runs on macOS 26.6.2. So adhoc + no quarantine mark does run here. Still NOT tested: the llama archive itself, fetch from inside the packaged app, system tar unpack. Keep first-test step as written.
- **R2a** [confirmed] 
- **R2b** [refuted] All listed defaults match source. One detail: common.h says n_parallel = 1, but common/arg.cpp line 1406 sets params.n_parallel = -1 for server, then server.cpp lines 168-172 make it 4 slots with kv_unified = true. Port 9931 at b11552 confirmed by me. Fix flag `--ctx-checkpoints 4` is risky for Qwen3.5: see objections.
- **R3a** [confirmed] 
- **R3b** [partly] Templates read by me, same result. Qwen card line 712: 'Qwen3.5 models operate in thinking mode by default'; Unsloth doc: 'For Qwen3.5 0.8B, 2B, 4B and 9B, reasoning is disabled by default'. Extra: arg.cpp shows `--reasoning off` sets default template kwarg enable_thinking = false, so flag and per-request kwarg do same thing. Template text came from HF API field, not from the Q4_K_M file itself: after load, read GET /props chat_template to be sure.
- **R3c** [refuted] Issue real, open, 1 comment, no fix yet. Small fix to count: the 15 of 15 'length' runs used response_format or json_schema; only 2 of those 15 had enable_thinking false. The 3 of 3 short-prompt result with thinking off is right. Tested on E2B, Linux CUDA only.
- **R3d** [refuted] No measured run found by me too. M4 numbers match the page exact. Web search gives only willitrunai estimates, and they clash (35 tok/s and 32.6 tok/s for same M4 Air). Extra doubt on the planning figure: benchmark model was Qwen3 (arch qwen3); pick is Qwen3.5 (arch qwen35, hybrid in llama.cpp). Different arch, so speed may differ more than guessed. Source is third-party site, not primary.
- **R4a** [confirmed] Pick, commit, file, bytes, sha256, card command, query form all match. One detail wrong or unproven: EmbeddingGemma 2 context. HF API gguf.context_length for ggml-org/embeddinggemma-2-GGUF says 262144, not 8,192; card gives no number. Treat 8,192 as unverified. Me read the Qwen GGUF header by Range request: qwen3.pooling_type = 3 (last), qwen3.embedding_length = 1024, qwen3.context_length = 32768, tokenizer.ggml.add_eos_token = true. So `--pooling last` is belt and braces, and no hand-added <|endoftext|> needed (header reading, not run). Card code says `Query:{query}` no space; TEI example on same card has a space. Pick one, store it with index.
- **R4b** [confirmed] Exact limit from source: with pooling last, input errors when n_tokens >= slot n_ctx. So `-c 8192 -np 4` = max 2047 tokens per input, end token included. Not run.
- **R5a** [confirmed] 
- **R5b** [partly] 
- **R5c** [confirmed] One thing to state plain: only /health and /v1/health skip the key (server-http.cpp get_public_endpoints). GET /props and the token count route need Authorization: Bearer <key>.
- **R5d** [confirmed] Source nesting right: response_format.json_schema.schema. Trap not flagged: README at same tag (line 1344) shows `{"type": "json_schema", "schema": {...}}`. Per source that form reads no schema and falls back to 'any object', with NO error. Wrong nesting fails silent. Test must prove the schema bites (send schema with an enum, assert reply obeys).
- **R6a** [confirmed] Re-run by me, no token: 302, x-linked-size 2740937888, x-linked-etag = sha256, then 206 with content-range bytes 2740937872-2740937887/2740937888; CDN etag = xetHash 1d203c21..., not sha256. Extra: GitHub release asset also answers Range with 206 (content-range bytes 11971400-11971405/11971406), so one resume path serves both hosts.
- **R6b** [refuted] Now checked at the published 2.17.6 files, not only main: src/lib/download-file-to-cache-dir.ts pipes to `${blobPath}.incomplete`, then rename; console.debug; no Range, no hash check. npm view by me: @huggingface/hub 2.17.6, MIT, node >=18, unpackedSize 3156257, deps @huggingface/tasks ^0.21.58 and @huggingface/xetchunk-wasm ^0.2.0.
- **R7** [partly] Signal handling and router stdin trick both seen in source by me (server.cpp lines 510-515 and 32; server-models.cpp lines 1744, 1836-1853). Memory still a guess, nobody measured. Nothing wrong found.
- **R8** [unverified] Evidence weaker than told. arXiv 2609.15964: the 69.0% is claude-haiku-4.5, the 37.1% is claude-opus-5 (98.0% of claims quoted, 37.1% fully backed). Both are cloud models, not 4B local ones. arXiv 2510.20303 is about missing citations (CITECONTROL, CITENTION), not verbatim quotes. So no source at all speaks for a 4B GGUF. Own test set is the only proof.
- **R9** [partly] Asset names, sizes, sha256 all match. Two fixes. (1) cudart archive has its own top folder cudart-llama-b11429-bin-ubuntu-cuda-13.4-arm64/ with 3 files (libcudart.so.13, libcublas.so.13, libcublasLt.so.13). Plain unpack does NOT land next to binaries: use `tar -xzf <cudart> --strip-components=1 -C <folder>/llama-b11429`. (2) 'Later' is wrong now: BUILD_STATUS.md newest entry says Phase 2 ships to the GX10. Linux arm64 CUDA archive, never reported running on DGX OS, is now on the Phase 2 path. Build facts: container nvidia/cuda:13.4.1-devel-ubuntu24.04, gcc-14, -DGGML_BACKEND_DL=ON, -DGGML_NATIVE=OFF, default CUDA arch list.

### Objections to recommendations
- Scope clash. /Users/lucasta/projects/gx10-council/docs/BUILD_STATUS.md newest owner entry (2026-10-10, 'Phase 2 scope change'): no file attach, no search, no citations in Phase 2; Electron app runs ON the GX10, built for Linux arm64 on this Mac. So embedding server, cite scheme, Library are not Phase 2 work now. And the GX10 archive pair (147639003 + 552521413 bytes, never reported running on DGX OS) moves from 'outline' to must-work. This task text says the old scope. Lead must settle which holds before plan.
- `--ctx-checkpoints 4` with Qwen3.5-4B. src/llama-arch.cpp at b11429 lists LLM_ARCH_QWEN35 in llm_arch_is_hybrid. Hybrid model cannot cut its memory back part-way; server rolls back only through context checkpoints. server-context.cpp create_checkpoint: when list is near full, checkpoints closer than checkpoint_min_step (8192 tokens) to an older one get erased. With limit 4 and a 16384 context, regenerate, edit, or next turn may fall to 'forcing full prompt re-processing' (source reading, NOT run). Safer: leave default 32, or test first: log timings.cache_n on turn 2, on regenerate, and on the turn after a second call. Fallback Ministral (arch mistral3) is not in the hybrid list.
- Two-call citation plan on one slot. Call 2 writes extra tokens into the only slot. Next user turn must roll back past them. On a hybrid model that needs a live checkpoint (see above). Claim 'Call 2 is cheap: prefix is cached' is not proven for Qwen3.5. Measure cache_n before trusting.
- Install self-test too thin. Bug #30256 shows thinking leaks only when response_format json_schema is set. Self-test must send a json_schema request (not plain chat) and assert reasoning_content empty, finish_reason 'stop', and schema obeyed. Also guards the README nesting trap.
- Sampler. Qwen card line 837 for non-thinking general use says presence_penalty=1.5. Pick uses 0 for the cite call: own guess, fine to test, but say it is off-card. llama-server will not apply card values by itself: send every sampler field in each request.
- 'No web ever' versus first-run downloads. Pick fetches 11971406 bytes from GitHub and 2740937888 bytes from Hugging Face. Repo rule in CLAUDE.md: 'Nothing leaves this machine: no CDN, no outside requests'. Needs owner yes in plain words, a clear one-time setup screen, and a no-internet path: import a file from disk, checked by same sha256. On the GX10 same question again.
- Electron 44. Spawn and fetch must live in main process or a helper process, never the page (repo rule: page gets no Node). Use global fetch only; Electron net.fetch does not exist under plain Node on the GX10. Stop servers on Electron before-quit; a force-quit leaves a 3-5 GB orphan until next start sweep (size is estimate).
- Long silent requests. Node fetch (undici) has default 300 s header and body time-outs. Server ping every 30 s covers streams once headers are out. A non-stream call (the citation call) sends nothing until done. Fine on this Mac with max_tokens set; on GX10 with big models set own time-out on purpose (inference, not run).
- Pin is good, but b11429 is flagged prerelease on GitHub and the engine depends on that one URL forever. Old tags b4000, b6000, b9000, b10929 still answer today, so no pruning seen. Still: keep own copy of the archive beside the models.
- Speed plan rests on a Qwen3 run on an M4 mini. Pick is Qwen3.5 (other arch) on a fanless M5 Air. Do not size passage caps from it. Run bundled llama-bench on this Mac first.

### Missed by the first pass
- Qwen3.5 is a hybrid arch in llama.cpp (LLM_ARCH_QWEN35 in llm_arch_is_hybrid, src/llama-arch.cpp at b11429). Changes prompt-cache behaviour: rollback only by checkpoints. Touches regenerate, edit, chat switch, two-call cite.
- README at b11429 shows a json_schema form the source does not read (`{"type":"json_schema","schema":{...}}`). Wrong nesting gives 'any object', no error. Right form: response_format.json_schema.schema (server-common.cpp lines 1299-1318).
- Embedding GGUF header read direct: qwen3.pooling_type = 3, tokenizer.ggml.add_eos_token = true, qwen3.embedding_length = 1024, qwen3.context_length = 32768. Known worry 'must add <|endoftext|> by hand' does not apply to this file (header reading).
- Real proof on this Mac for the quarantine question: Electron.app from npm ci and Playwright Chromium, both fetched by Node, have com.apple.provenance only, no com.apple.quarantine. Packaged app is adhoc signed (flags 0x20002), no LSFileQuarantineEnabled, no entitlements.
- cudart archive unpacks to its own folder name; needs --strip-components=1 into the llama-b11429 folder. Plain unpack leaves llama-server without libcudart.so.13.
- GitHub release assets support Range (206 seen). One resume downloader covers the 12 MB Mac archive and the 148 MB + 553 MB GX10 archives.
- Only /health and /v1/health skip the API key. /props, /v1/models, token count all need it.
- unsloth/Qwen3.5-4B-GGUF also holds mmproj-F16.gguf (672423616 bytes); model card type is image-text-to-text. Same llama-server could read images later with --mmproj, maybe sparing a separate OCR engine. Quality for scans not checked.
- Archive also ships unified `llama` binary (README: `llama serve`) beside llama-server, and llama-bench, llama-tokenize, llama-fit-params. Pin protects if llama-server name is dropped later.
- Server default slot count comes from arg.cpp (n_parallel = -1 for server), not common.h (= 1). Anyone reading only common.h gets it wrong.
- release/ already holds 'GX10 Council-linux-arm64' and 'GX10-Council-linux-arm64.tar.gz': the Linux arm64 Electron build exists, which backs the newer 'runs on the GX10' reading.
- arXiv 2609.15964 numbers are for cloud models (claude-haiku-4.5 69.0%, claude-opus-5 37.1%). No source found for any 4B local model on quote citing.
