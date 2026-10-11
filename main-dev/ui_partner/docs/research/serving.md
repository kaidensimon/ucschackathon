# Research: serving

Read-only research on 2026-10-10. Nothing was run on the GX10. The re-check section overrides the findings where they differ.

## Summary
Read-only research against llama.cpp source at tag b11429 (release v0.6.0, 2026-10-05) and master (nightly b11552, 2026-10-10), plus NVIDIA docs and DGX Spark forum reports. Nothing was run on the GX10. The plan PDF could not be opened here (pdftoppm missing), so plan wording comes from the task brief.

**Decisions this supports**
- **Per-seat processes, not the router, for v1.** The router does keep several models loaded at once (default cap 4, each a child process with its own flags). But its children are ordinary llama-server processes, so it saves no memory or GPU time. It also carries open bugs on cancel propagation (#29707), port selection (#29815) and scheduling (#28774, #28829).
- **Seats should generate one at a time.** I found no measurement of two different models generating concurrently on a GB10. The nearest evidence is two vLLM servers under CUDA MPS: about 9% more total output, with time per token rising from 156 ms to 290 ms.
- **Same-model seats can share one server.** `-np 2` plus `id_slot` per request gives separate prompt caches with the weights loaded once (source reading, not run). Context is divided: each slot gets `-c` / N.
- **Model choice sets the debate length.** Reported GB10 speeds are 60-90 tok/s for 20-35B mixture-of-experts models and 8-12 tok/s for dense 27-32B models. My estimate: only the former fit several rounds with 5-7 seats in 5 minutes.

**What changes the plan**
- **No generic tool-call fallback exists at b11429**, although the README still says so. A model whose template lacks tool support silently returns plain text. The gateway needs its own fallback.
- **Structured votes need validation and retry.** `response_format` json_schema works and supports enums, but template-specific failures keep appearing (Gemma 4, #30256, open).
- **Standalone servers expose no load progress**, only `/health` 503 then 200. Progress events go only to a router parent.
- **Defaults are wrong for this machine.** Each server defaults to an 8192 MiB host prompt cache and `--fit on`. Use `--cache-ram 0`, `--fit off`, and explicit `-c`, `-np`, `-ngl all`.
- **Flags moved.** `--no-mmap` and `--mlock` are gone (`--load-mode` replaces them). The default port is 8080 at b11429 and 9931 on master.

**Memory**
Weights are counted once. A Spark with a 94 GB model showed used 94Gi and buff/cache 27Gi; dropping caches left used at 93Gi. The meter should use MemAvailable, per-process figures, and `llama-fit-params --fit-print on` before launch.

**Not verified**
- Whether the prebuilt `ubuntu-cuda-13.4-arm64` archive runs on DGX OS.
- Whether CUDA MPS is supported on GB10.
- Per-process overhead on GB10.
- Issue #27918 beyond its single report (open, stale, no replies).

## Claims

### S1a [confirmed]
Router mode can keep several models loaded at the same time, each as its own child process with its own context size and flags.

Evidence: At b11429 the router spawns one llama-server child per model on 127.0.0.1 with a free port and proxies requests by the `model` field. `--models-max` defaults to 4 (0 = unlimited). `--models-preset` INI sections take any CLI flag per model, with precedence router command line > model section > `[*]`.

For the build: The plan's 'conflicting' note is settled: simultaneous models are supported. If the router is ever used, set `--models-max 0` (7 seats + summariser + embedder = 9 processes), `--no-models-autoload`, one preset section per seat, and keep model-specific flags off the router command line because children inherit them.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/README.md, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-models.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/common.h

### S1b [partly]
Router eviction is predictable enough to hold a fixed council in memory.

Evidence: At the cap, the router unloads the least-recently-used model that is idle (no requests in flight, ready or sleeping, not wanted by a queued request). Busy models are never evicted; if none is idle the request queues, or a direct load fails with "model limit reached, try again later". An evicted model loses its KV cache (feature request #28998 is open).

For the build: With `--models-max 0` nothing is evicted. With the default of 4, a 5-7 seat council would thrash: every fifth model evicts another and its prompt cache. Do not rely on router eviction for seat management.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-models.cpp, https://github.com/ggml-org/llama.cpp/issues/28998

### S1c [partly]
Router mode is mature enough to be the first version's model manager.

Evidence: About 20 issues and PRs with 'router' in the title are open on 2026-10-10. They include #29707 (open PR: a client disconnect was not fully propagated to the child, so it kept generating), #28829 (hard deadlock with --models-max 1), #28774 (cold-start race), #29815 (port race), #28837 (API key not forwarded to children) and #29073 (no per-child environment variables). #23704 (one model, several presets, loaded once) is still a feature request.

For the build: Skip the router in v1. Its one unique benefit is load progress over `GET /models/sse` (`progress.value`); revisit it after v1 if that matters.

Sources: https://github.com/ggml-org/llama.cpp/pull/29707, https://github.com/ggml-org/llama.cpp/issues/28829, https://github.com/ggml-org/llama.cpp/issues/28774, https://github.com/ggml-org/llama.cpp/issues/29815, https://github.com/ggml-org/llama.cpp/pull/28837, https://github.com/ggml-org/llama.cpp/issues/23704

### S2a [partly] (load-bearing)
Three to seven llama-server processes can share the single GB10 GPU with no special setup.

Evidence: DGX Spark owners report running one llama-server per model on separate ports (`-ngl 999 --no-mmap`), and a NIM plus llama-server pair on one box. I found no report of 3-7 llama.cpp processes on a GB10 and no measured per-process overhead. One issue shows a healthy llama-server holding about 2.1 GiB of host memory beside an 86.7 GB model on the GPU.

For the build: Per-seat processes are workable. Budget 1-2 GiB of overhead per process (my estimate) until measured. Make the first GX10 test: load 7 small models, record the MemAvailable drop per process, then generate with 1, 2 and 3 at once.

Sources: https://forums.developer.nvidia.com/t/can-i-use-ollama-or-vllm-on-the-gb10-to-run-multiple-llm-models-simultaneously/352903, https://forums.developer.nvidia.com/t/guide-gemma-4-31b-on-dgx-spark-via-nemoclaw-dual-model-setup-guide/366162, https://github.com/ggml-org/llama.cpp/issues/28933

### S2b [unverified]
CUDA MPS is available on DGX Spark to make GPU sharing between processes efficient.

Evidence: One forum user started `nvidia-cuda-mps-control -d` on a GB10 (after `sudo nvidia-smi -i 0 -c EXCLUSIVE_PROCESS`) and ran two vLLM servers: total output rose from 570 to 621 tok/s while mean time per token went from 156 ms to 290 ms. A separate thread asking whether MPS is officially supported on GB10 has no answer from NVIDIA, and the DGX Spark known-issues page does not mention MPS.

For the build: Do not depend on MPS. It needs sudo, is not confirmed as supported, and the one test shows little gain. Assume default sharing, where processes take turns on the GPU.

Sources: https://forums.developer.nvidia.com/t/serving-multiple-small-llms-on-dgx-spark-with-cuda-mps/376724, https://forums.developer.nvidia.com/t/mps-support-and-telemetry-on-grace-blackwell-gb10-with-unified-memory/363137, https://docs.nvidia.com/dgx/dgx-spark/known-issues.html

### S2c [partly]
llama.cpp issue #27918 (loads above 32 GB hang on unified memory; workaround GGML_CUDA_NO_VMM) blocks large models on the GX10.

Evidence: The issue is open, labelled stale, has no replies and was last updated 2026-09-28; it is one report with a 104 GB model, and the 32 GB constant is still in master. But llama.cpp's own DGX Spark benchmark loaded gpt-oss-120b (59.02 GiB, fully offloaded), so loads above 32 GB do not hang in general. I did not find which build options that benchmark used.

For the build: Council seats will mostly be under 32 GB each, so the exposure is the single large model in phase 2. Add a load watchdog (time out by file size, kill, report), because the failure is a hang. Keep a source build with `-DGGML_CUDA_NO_VMM=ON` as the fallback (a CMake option, per earlier research).

Sources: https://github.com/ggml-org/llama.cpp/issues/27918, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/benches/dgx-spark/dgx-spark.md, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/ggml/src/ggml-cuda/ggml-cuda.cu

### S2d [confirmed] (load-bearing)
The first version should run one gateway-supervised llama-server process per seated model (the plan's pick) and not the router.

Evidence: Router children are separate llama-server processes anyway, so the router saves no memory and no GPU time. It adds the open bugs listed under S1c, strips the API key from children and cannot set per-child environment variables. Killing a process is also the most reliable way to return its memory (my inference).

For the build: Build a Python supervisor in the gateway: one process per distinct model (not per seat), with fixed ports, explicit flags, its own log file and a PID for memory accounting. Hide it behind an interface (start, stop, health, chat stream) so a router backend could be swapped in later.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-models.cpp, https://github.com/ggml-org/llama.cpp/pull/29707, https://github.com/ggml-org/llama.cpp/issues/29073

### S3a [unverified] (load-bearing)
Several different models can generate at the same moment on the one GPU at useful speed.

Evidence: I found no measurement of two or more different-model processes generating at once on a GB10 or a comparable single GPU. The nearest is the MPS test in S2b (about 9% more total, 86% slower per token). A forum regular puts the Spark's memory bandwidth 'below 273GB/s', which caps decode speed however work is scheduled.

For the build: Seats in a round generate one at a time. Implement the round as a speaker queue with a concurrency setting that defaults to 1 (the summariser and embedder are extra). Raise it only after measuring on the GX10. This also matches the Table View, where one speaker glows.

Sources: https://forums.developer.nvidia.com/t/serving-multiple-small-llms-on-dgx-spark-with-cuda-mps/376724, https://forums.developer.nvidia.com/t/help-on-llama-cpp-command-line-arguments-and-compilation-settings-performance-testing-included/357012

### S3b [confirmed] (load-bearing)
Parallel slots inside one server (-np with continuous batching) raise total throughput, and the context is divided between slots.

Evidence: llama.cpp's DGX Spark benchmark for gpt-oss-120b shows 57.1 tok/s for 1 stream, 73.3 total for 2, 98.5 for 4 and 159.2 for 8 (512-token prompts), so each stream slows to 36.6, 24.6 and 19.9 tok/s. In source, explicit `-np N` without `--kv-unified` gives each slot `-c` / N (padded to 256). With `-np` unset the server makes 4 slots sharing one pool, and `--kv-unified-per-slot N` caps each.

For the build: Only seats that share a model can gain from parallel generation. Always pass `-np` explicitly: `-np 1` for a single-seat server, and `-np K -c K x per-seat-context` for K seats on one model. Never rely on the default of 4 slots.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/benches/dgx-spark/dgx-spark.md, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/src/llama-context.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server.cpp

### S4 [confirmed] (load-bearing)
One llama-server with two or more slots can serve two seats with different system prompts and separate prompt caches, so the weights load once.

Evidence: Source reading, not run: `id_slot` is read from the request body for every completion task, and the OpenAI-compatible chat route copies unknown fields through. Each slot is its own KV sequence with its own cached tokens; a busy slot defers the task. Two open bugs touch this setup: #27148 (the host-RAM prompt cache can restore an unrelated conversation into a slot under concurrent load with -np 2) and #28917 (Gemma 4 26B loses end-of-turn under concurrent decode on GB10, seen through Ollama).

For the build: For K seats on one model: start one server with `-np K -c K x ctx --cache-ram 0`, send `id_slot` = that seat's fixed index and `cache_prompt: true` on every request, and keep their turns sequential by default. The seat-to-(server, slot) map lives in the gateway.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-context.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-common.cpp, https://github.com/ggml-org/llama.cpp/issues/27148, https://github.com/ggml-org/llama.cpp/issues/28917

### S5a [partly] (load-bearing)
With cache_prompt, each debate round only processes the new tokens.

Evidence: `cache_prompt` defaults to true and the server reuses the longest common token prefix between the slot's cache and the new prompt. Models with sliding-window or recurrent memory cannot roll back partway and depend on context checkpoints (default 32 per slot, made at user-message boundaries, 8192-token minimum spacing); without a usable one the log says "forcing full prompt re-processing". If the template drops earlier reasoning from history, I expect reuse to stop at the start of the previous assistant turn (my inference from the prefix rule).

For the build: Keep each seat's transcript append-only: system prompt, council.md and tool definitions first and unchanged for the whole debate, then question, evidence and rounds. Append the owner's mid-debate message at the end. Pin `id_slot`, and log `timings.cache_n` against `prompt_n` on every call so a full re-read is visible. Context shift is off by default, so an overflowing request errors; size `-c` for the whole debate.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-context.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/README.md, https://github.com/ggml-org/llama.cpp/issues/24714

### S5b [confirmed]
Slot save and restore can carry a seat's cache across a server restart.

Evidence: With `--slot-save-path PATH`, `POST /slots/{id_slot}?action=save`, `restore` or `erase` (body `filename`) writes or reads the slot's KV state, and context checkpoints are appended to the file. Without it, the cache is lost when the process stops or sleeps.

For the build: Not needed for v1. Pause should hold between turns, with servers left running. Consider slot save only if 'resume a debate after restart' becomes a feature.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/README.md, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/server-context.cpp

### S6a [partly] (load-bearing)
response_format with json_schema on /v1/chat/completions reliably forces a structured vote.

Evidence: The server accepts `response_format: {"type":"json_schema","json_schema":{"schema":{...}}}`, `{"type":"json_object","schema":{...}}` or top-level `json_schema` / `grammar`, and turns the schema into a sampling grammar of optional reasoning then schema-shaped JSON; enums are supported. Template-specific failures keep appearing: #30256 is open (Gemma 4 still opens a thought channel with thinking off and can run to max_tokens with empty content), and #29652, #29613 and #20345 were closed only between June and October 2026.

For the build: Make the end-of-round vote a separate short request with a small schema (for example `answer` as a one-sentence string plus `agrees_with` as an enum of seat ids or 'none'), a `max_tokens` cap and thinking off. Validate with Pydantic, retry once, then fall back to lenient parsing and mark the seat 'no vote'. Run a per-model self-test when a model is added and store the result.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-common.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/chat-auto-parser-generator.cpp, https://github.com/ggml-org/llama.cpp/issues/30256, https://github.com/ggml-org/llama.cpp/issues/20345, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/grammars/README.md

### S6b [confirmed] (load-bearing)
Reasoning models can be made to answer without thinking, or with capped thinking, and their thoughts arrive separately from the answer.

Evidence: At b11429 the server flags are `-rea/--reasoning [on|off|auto]`, `--reasoning-format {none,deepseek,deepseek-legacy}` (default auto; deepseek puts thoughts in `message.reasoning_content`), `--reasoning-budget N` (-1 unlimited, 0 end immediately) and `--chat-template-kwargs`. Per request: `chat_template_kwargs: {"enable_thinking": false}`, `reasoning_effort: "none"`, `reasoning_budget_tokens`, and `reasoning_control: true` with `POST /v1/chat/completions/control` `{id, action: "reasoning_end"}`.

For the build: Stream `delta.reasoning_content` and `delta.content` as separate WebSocket fields; bubbles and Chat View use content, and the seat can show a 'thinking' state. Give debate turns a per-request `reasoning_budget_tokens` so one seat cannot spend the time limit thinking, and turn thinking off for the vote. Whether 'off' holds is per template, so include it in the self-test.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/arg.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-common.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/README.md

### S7a [confirmed]
Tool calling in llama-server requires the --jinja flag.

Evidence: The requirement is real but `--jinja` is now on by default (`--jinja, --no-jinja`, default enabled at b11429). With it off, a request carrying `tools` fails with "tools param requires --jinja flag".

For the build: Pass `--jinja` explicitly so behaviour does not depend on the build's default. The gateway runs the tools itself; do not enable llama-server's own `--tools` (it includes exec_shell_command and write_file) or its MCP support.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/README.md, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-common.cpp

### S7b [partly] (load-bearing)
OpenAI-style tools work today for the Qwen, Llama, Gemma, Mistral, Phi and gpt-oss families.

Evidence: The template list tested at b11429 covers Llama 3.1/3.2/3.3, Qwen (Hermes-style and Qwen3-Coder), Mistral Nemo, Small 3.2, Devstral and Ministral, gpt-oss (dedicated handler), Nemotron 3 Nano and Granite 4. Gemma 2 is listed as 'No tool support', Gemma 4 has a dedicated handler with an open streaming bug (#29655), and Phi is not in the list. Open tool bugs include #30118 (Qwen3.6 calls leak into content), #20837 (Qwen3.5 9B calls inside thinking), #29248 (Ministral-3), #27217 (`tool_choice: required` not enforced), #27733 (a stray trailing think tag makes a finished generation fail) and #27966 (streamed parallel calls reuse an id).

For the build: Treat tool support as a per-model capability, not a family promise. Read `chat_template_caps` from `GET /props` at seat start and run a canned tool-call self-test. Send one tool call at a time (`parallel_tool_calls: false`), keep the KV cache at f16 or q8_0 (the docs warn q4_0 degrades tool calling), and retry once on a 500 parse error.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/docs/autoparser.md, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/chat.cpp, https://github.com/ggml-org/llama.cpp/issues/30118, https://github.com/ggml-org/llama.cpp/issues/27217, https://github.com/ggml-org/llama.cpp/issues/27733, https://github.com/ggml-org/llama.cpp/issues/29655

### S7c [refuted] (load-bearing)
When a model's template has no tool support, llama-server falls back to a generic tool-call format.

Evidence: The README and docs/function-calling.md still say so, but at b11429 there is no generic chat format in common/chat.h. The parser generator only builds a tool parser when the template analysis found a tool format and the template supports tool calls; otherwise the output is treated as plain content and the `tools` array is not parsed.

For the build: The gateway must own the fallback. Simplest for v1: the gateway searches the files with the owner's question and gives every seat the same cited evidence pack (file and page). Follow-up searches go through native tools where the self-test passes, and elsewhere through a json_schema action reply (`search`, `read` or `answer`).

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/chat.h, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/chat-auto-parser-generator.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/README.md

### S8a [partly] (load-bearing)
A supervisor can tell when each server is ready and show load progress.

Evidence: `GET /health` needs no API key and returns 503 `{"error":{"code":503,"message":"Loading model","type":"unavailable_error"}}` while loading, then 200 `{"status":"ok"}`. Load progress is only reported to a router parent (the state callback is set only when the process is a router child); a standalone server exposes none.

For the build: Poll `/health` every 250-500 ms, treat connection-refused as 'starting', and watch for process exit. For 'spool up', show per-seat state with elapsed time; a progress bar would have to be estimated (for example bytes read from `/proc/<pid>/io` against file size, untested). After ready, read `/props` for `build_info`, `chat_template_caps` and `total_slots`.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/README.md, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/server.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/server-context.cpp

### S8b [confirmed] (load-bearing)
Binding, authentication, stopping, cancelling and logging can all be controlled by the supervisor.

Evidence: The default bind is 127.0.0.1. The default port is 8080 at b11429 but 9931 on master. `--api-key` or env `LLAMA_API_KEY` protects everything except `/health`. SIGINT and SIGTERM trigger a clean shutdown and a second signal exits at once. Closing the streaming connection cancels the task. Logging flags are `--log-file`, `--log-timestamps`, `--log-prefix` and `-lv N`.

For the build: Always pass `--host 127.0.0.1 --port <n>` from a fixed gateway-owned range. Stop with one SIGTERM, wait about 10 s, then SIGKILL. Stop and Pause cancel by closing the httpx stream. Write one log file per server and surface the last lines on a crash. An API key is optional on loopback; if used, pass it by environment so it is not in the process list.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/common.h, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/common/common.h, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/server.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/server-queue.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/README.md

### S8c [partly] (load-bearing)
Models load from the NVMe drive quickly enough that 'spool up' is a short step.

Evidence: Reports for gpt-oss-120b (59-63 GB) on a Spark: 1 min 44 s with default settings on DGX OS, 64.8 s in a third-party runbook, and about 22 s on a 6.17 kernel. That is roughly 0.6 to 2.9 GB/s.

For the build: My estimate: a council totalling 60-100 GB takes roughly 0.5 to 3 minutes to load cold, which is comparable to the 2-minute preset. Start the debate timer after spool-up, keep the last council loaded between debates, load one model at a time, and only restart the servers whose model or settings changed.

Sources: https://github.com/ggml-org/llama.cpp/discussions/16578, https://llama-cpp-ex.hexdocs.pm/dgx-spark.html

### S9a [refuted] (load-bearing)
On unified memory a loaded model's weights are held twice (page cache plus the CUDA copy), so the meter should count them twice.

Evidence: A Spark with a 94 GB model loaded showed used 94Gi, buff/cache 27Gi, available 27Gi; after dropping caches, used 93Gi, buff/cache 1.0Gi, available 28Gi. The weights are counted once and the file cache is reclaimable. At b11429 the CUDA backend reports no mmap support on integrated GPUs, so `--load-mode auto` becomes `none` on the GX10; llama.cpp's own Spark benchmarks ran with mmap off and direct I/O on. NVIDIA documents a manual cache flush (`sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'`) as a debugging workaround.

For the build: The meter's total is MemTotal minus MemAvailable. Per seat, count weights + KV cache at the chosen context + compute buffers + host memory of the process; nvidia-smi's process table does list per-process GPU memory on GB10. `--no-mmap` and `--mlock` no longer exist: use `--load-mode dio` (or `none`) and skip mlock. Set `--cache-ram 0`, since the default 8192 MiB host prompt cache per server comes out of the same pool.

Sources: https://frankdenneman.ai/posts/2026-03-23-understanding-unified-memory-dgx-spark-nemoclaw-nemotron/, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/ggml/src/ggml-cuda/ggml-cuda.cu, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/benches/dgx-spark/dgx-spark.md, https://docs.nvidia.com/dgx/dgx-spark/known-issues.html

### S9b [confirmed] (load-bearing)
llama-fit-params can size a model for the memory meter without RPC.

Evidence: Source reading, not run: with `--fit-print on` the tool prints estimated MiB per device (model, context, compute) for the given `-m`, `-c` and `-ngl` without fitting; without it, it prints fitted `-c ... -ngl ...` arguments. On unified-memory CUDA devices llama.cpp takes free memory from MemAvailable in /proc/meminfo. Earlier research found the binary in the release archives.

For the build: On the GX10 the gateway runs `llama-fit-params -m <gguf> -c <ctx> -np <slots> -ngl all --fit-print on` for each candidate seat and caches the result by file, context, slots and KV type. Run it when no debate is active, since it initialises CUDA. Confirm the exact output format on the real build before writing the parser.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/fit-params/fit-params.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/arg.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/ggml/src/ggml-cuda/ggml-cuda.cu

### S10a [confirmed]
There is a clear current llama.cpp build to pin for the GX10.

Evidence: The newest nightly tag on 2026-10-10 is b11552 (19:52 UTC). `releases/latest` is v0.6.0 (2026-10-05), whose only asset `nightly-tag.txt` contains `b11429`, built from commit d812350493. Several nightlies ship per day and defaults move between them (the default port changed between b11429 and master).

For the build: Pin b11429 (v0.6.0) on the GX10 and on the dev Mac (`llama-b11429-bin-macos-arm64.tar.gz`). Everything in this report was checked against that tag. Upgrade deliberately and re-run the per-model self-tests.

Sources: https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=8, https://github.com/ggml-org/llama.cpp/releases/tag/v0.6.0, https://github.com/ggml-org/llama.cpp/releases/tag/b11429

### S10b [unverified]
The prebuilt ubuntu-cuda arm64 archive is known to run on DGX OS.

Evidence: `llama-<tag>-bin-ubuntu-cuda-13.4-arm64.tar.gz` (about 148 MB) and its `cudart-` companion (about 553 MB) exist for b11429 and b11552, built in nvidia/cuda:13.4.1-devel-ubuntu24.04 with the default GPU architecture list. NVIDIA's CUDA notes give driver >= 580 for the whole 13.x family and DGX OS ships a 580 driver, so it should load (my inference). I found no report of anyone running it on a Spark or GX10.

For the build: Try the prebuilt archive first; it needs no sudo. Unpack the cudart archive into the same folder (`--strip-components=1`, per earlier research). If it fails, build b11429 from source with NVIDIA's playbook flags. Either way, run a smoke test: load one model, generate, check the log shows the CUDA device.

Sources: https://github.com/ggml-org/llama.cpp/releases/tag/b11552, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/.github/workflows/release.yml, https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html

### S10c [confirmed] (load-bearing)
The gateway can read the version of the llama.cpp build already installed.

Evidence: `llama-server --version` prints `version: <semver> (build <n>, commit <hash>)` and `built with <compiler> for <target>` to stderr, then exits 0; an issue quotes `version: 0.6.0-dev (build 11429, commit d812350493)`. A running server returns `build_info` as `b<build>-<commit>` from `GET /props`.

For the build: At gateway start, run `llama-server --version`, parse the build number from stderr and refuse to start seats below 11429 with a clear message. Also grep `llama-server --help` for `--load-mode`, so an older build with `--no-mmap` gets a clear error rather than a failed launch.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/build-info.cpp.in, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/build-info.h, https://github.com/ggml-org/llama.cpp/issues/30256, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/README.md

## Recommendations
- **How models are run for a council**: One gateway-supervised llama-server process per distinct seated model (plus one for the bubble summariser and one for embeddings), started and stopped by a Python supervisor inside the FastAPI gateway. No router mode in v1. _Why:_ Router children are ordinary llama-server processes, so the router saves nothing. Direct processes give exact flags, a PID for memory accounting, per-process logs and cancel-by-disconnect that works today. This is the plan's own pick.
- **llama.cpp version**: Pin tag b11429 (release v0.6.0, commit d812350493) on the GX10 and the dev Mac. The gateway checks it with `llama-server --version` and `/props.build_info`. _Why:_ It is the build behind the latest release, and every flag and behaviour in this report was checked against it. Nightlies ship several times a day and change defaults (port 8080 became 9931 within five days).
- **Seat server command line**: `llama-server -m <gguf> --alias <id> --host 127.0.0.1 --port <fixed> -c <per-seat ctx x slots> -np <slots> -ngl all --fit off --load-mode dio --cache-ram 0 --jinja --reasoning-format deepseek --no-webui --offline --log-file <path> --log-timestamps --log-prefix`. Start with a per-seat context of 16384 and KV cache at f16. _Why:_ Explicit `-c`, `-np`, `-ngl` with `--fit off` makes a too-big council fail loudly; the default `--fit on` can quietly shrink context or move layers to the CPU. `--cache-ram 0` removes an 8192 MiB-per-server host cache that shares the same memory pool and has an open cross-conversation bug (#27148). `--offline` backs the 'never the web' promise.
- **Do seats generate in parallel or in turn**: In turn: one seat generates at a time, through a speaker queue in the debate engine with a concurrency setting fixed at 1 for v1. End-of-round votes also run one after another. _Why:_ Different models cannot be batched together, there is no evidence that concurrent generation on a GB10 gains more than a few percent, and each stream gets slower. One speaker at a time also matches the Table View.
- **One model filling several seats**: One server per model with `-np K -c K x ctx`; each seat sends its fixed `id_slot` and `cache_prompt: true`. The gateway keeps a seat-to-(server, slot) map. _Why:_ Weights load once and each seat keeps its own prompt cache; confirmed in source. The context is split evenly, so `-c` must be multiplied by the number of seats.
- **Prompt layout for cache reuse across rounds**: Per seat, an append-only message list: fixed system prompt + council.md + tool definitions first, then the question and evidence, then one appended block per round. Never rewrite earlier messages. Log `timings.cache_n` and `prompt_n` for every call. _Why:_ The cache is a plain longest-common-prefix match, so any change near the top forces a full re-read. Logging makes regressions visible per model.
- **Forcing the structured vote**: A separate short request per seat with `response_format: {"type":"json_schema","json_schema":{"schema":...}}`, a small schema using an enum for 'agrees with', thinking off (`chat_template_kwargs: {"enable_thinking": false}`), a `max_tokens` cap, Pydantic validation, one retry, then a lenient-parse fallback. _Why:_ Grammar-constrained output works for most templates, and an enum makes 'which answers match' a comparison of ids. The retry and fallback cover the template-specific bugs that keep appearing.
- **How agents research the owner's files**: The gateway runs the file search itself and gives every seat the same cited evidence pack at the start. Follow-up searches go through native tool calls only for models that pass a start-up self-test, and through a json_schema action reply for the rest. _Why:_ There is no generic tool fallback at b11429, tool support differs per template with many open bugs, and N separate tool loops would eat the time limit. A shared pack also gives uniform file-and-page citations.
- **Memory meter and admission check**: Before launch: sum per-seat estimates from `llama-fit-params --fit-print on` plus a per-process allowance, and compare with MemAvailable minus a reserve (start at 10 GiB). After launch: show MemTotal minus MemAvailable, and per seat the MemAvailable drop measured at load. _Why:_ llama.cpp itself uses MemAvailable on this chip, weights are counted once, and over-commit on unified memory ends in swap or the OOM killer and not a clean error. The 10 GiB reserve is my starting figure; one forum regular advises staying under about 115 GB.
- **Timer and spool-up**: Start the debate timer when all seats report ready. Keep the last council's servers running between debates and restart only those whose model or settings changed. Load models one at a time. _Why:_ Cold loads run at roughly 0.6-2.9 GB/s by owner reports, so a large council could take longer to load than the 2-minute preset. Sequential loads keep each admission check honest.
- **First hardware milestone**: Before phase 3, run a one-hour GX10 smoke test: prebuilt b11429 loads and uses CUDA; load time for one model with `dio` and with `none`; MemAvailable drop per process; tok/s with 1, 2 and 3 different models generating at once; `cache_n` across three appended rounds; vote and tool self-tests per candidate model. _Why:_ Every unverified item in this report is cheap to measure on the real box and each one changes a default.

## Risks
- Debate length against model speed: reported GB10 generation is about 60-90 tok/s for 20-35B mixture-of-experts models but 8-12 tok/s for dense 27-32B models. With turns in sequence, my estimate is that a 5-7 seat council of dense 30B-class models gets only one or two rounds in 5 minutes. The seat picker should show each model's measured speed.
- Memory over-commit has no clean failure on unified memory. Reports show the OOM killer taking system services, swap thrash and outright hangs. Hidden per-server costs add up: the default 8192 MiB host prompt cache, context checkpoints (up to 32 per slot) and KV cache that scales with context.
- Structured output and tool calling break per template. Open today: Gemma 4 ignoring thinking-off under json_schema (#30256), `tool_choice: required` not enforced (#27217), a finished generation turned into an error by a stray think tag (#27733), Qwen3.6 tool calls leaking into content (#30118). Each new model needs a self-test before it can hold a seat.
- Prompt cache misses can make every round re-read the whole transcript, most likely on models with sliding-window or recurrent memory, or when anything near the top of the prompt changes. With 5-7 seats this multiplies.
- A stuck load looks like a slow load. Issue #27918 describes a hang, not an error, and a standalone server reports no load progress. Without a watchdog the 'spool up' screen could sit forever.
- llama.cpp moves fast and its docs lag: `--no-mmap` and `--mlock` were removed, the default port changed within five days, and the README still promises a generic tool fallback that is gone. An unpinned or mismatched build on the GX10 will break launches.
- Open GB10-specific issues exist for particular model architectures: an abort at 262144 context (#27871), Gemma 4 losing end-of-turn under concurrent decode (#28917), and others visible in the issue list for qwen4exp and DeepSeek-V4-Flash (titles only, not opened). Model choice needs checking against the tracker.
- The bubble summariser is a second generator on the same GPU while a seat speaks. Its requests every few seconds will slow the speaker by an unmeasured amount.
- Sustained GPU load raises the thermal risk found in earlier research (hard power-offs reported on a GX10). Any move to parallel generation makes this worse.
- On GB10, llama.cpp sets CUDA to busy-wait, so each generating process holds a CPU core at 100%. That is harmless one at a time but adds up if concurrency is raised, and nine processes each defaulting to a full thread pool may contend (untested).
- The prebuilt CUDA arm64 archive is untested on DGX OS. The source-build fallback needs sudo for apt packages, which the app cannot do itself.
- Polling `/metrics` every second is reported to stall a server during prompt processing (#29104, open, Windows report). Prefer the stream's `timings` object and `/slots`.

## Open questions
- Which llama.cpp build is on the GX10 now (`llama-server --version`), how was it built, and does the owner have sudo there for a rebuild, a cache flush or apt packages?
- Which models and quantisations does the owner want as seats? This sets memory, load time and how many rounds fit in the time limit.
- GX10 test: tokens per second with 1, 2 and 3 different-model servers generating at once, compared with each alone.
- GX10 test: how much MemAvailable drops per loaded idle server beyond its weights, and does `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` work on this chip?
- GX10 test: does the prebuilt `llama-b11429-bin-ubuntu-cuda-13.4-arm64` archive (with its cudart companion) load and offload to the GPU on the installed driver?
- GX10 test: load seconds per model with `--load-mode dio` against `none`, and whether a second load is faster from the file cache.
- Per candidate model: does the vote self-test pass with thinking off, does the tool-call self-test pass, and does `cache_n` stay high across three appended rounds?
- Does a request carrying both the unchanged `tools` array and `response_format` keep the prompt cache and return clean JSON on each chosen template?
- Owner decision: should the time limit start after the models have loaded (recommended), and should the last council stay loaded between debates?
- Owner decision: may two seats that share one model speak at the same time later on, or is one speaker at a time a fixed rule of the Table View?
- Should the bubble summariser run on the GPU or on a few CPU cores to stay out of the speaker's way? Needs a speed test with the chosen small model.
- Does a model above 32 GB load on this GX10 with the installed build, or does it hang as in #27918? Only relevant if a single seat or the phase-2 chat model is that large.

## Independent re-check (overrides the above)

- **S1b** [partly] 
- **S1c** [partly] #28829 is still open, but its reporter wrote on 2026-09-13 that it is fixed in b10936 and no longer reproducible, so it is not a live bug at b11429. A title search today returns 22 open issues and PRs with 'router'; the other cited items are open as described.
- **S2a** [partly] The 2.1 GiB figure in #28933 is host RSS at load on an unsloth fork build. The same reporter later measured 5.1 to 12.8 GiB of host RSS per llama-server after 21-44 hours, with three llama-server processes resident on one Spark, so 1-2 GiB per process is not a safe budget. Stronger precedent the original missed: NVIDIA's multi-agent-chatbot playbook runs three llama.cpp server containers plus one TensorRT-LLM server on one Spark without MPS, using about 120 of 128 GB. Still no report of 5-7 processes.
- **S2b** [unverified] The figures are in the post, but 621 tok/s is the sum of two vLLM servers (310.23 + 310.44 tok/s output, Qwen3.5-4B, 100 concurrent requests each) against one server at 569.96 tok/s. There is no two-server run without MPS, so the test says nothing about MPS versus default sharing. NVIDIA's MPS documentation names neither GB10 nor DGX Spark.
- **S2c** [partly] The issue's root cause is doubtful. In source the 32 GiB constant (`1ull << 35`) sizes `ggml_cuda_pool_vmm`, the pool returned by `new_pool_for_device`, and ggerganov's Spark log shows `NVIDIA GB10 ... VMM: yes` with the 59.02 GiB gpt-oss-120b loading. `GGML_CUDA_NO_VMM` is only a CMake option (`-DGGML_CUDA_NO_VMM=ON`, default OFF); b11429 reads no environment variable of that name, although the issue writes it like one.
- **S2d** [confirmed] 
- **S3a** [unverified] No measurement exists in the sources I opened. The '86% slower per token' figure comes from vLLM serving 100 concurrent requests per server, so it cannot be scaled to single-stream llama.cpp seats. The 'below 273GB/s' quote is real (forum user eugr, tagged Spark Expert).
- **S3b** [confirmed] The numbers match (57.14, 73.27, 98.51, 159.18 tok/s) but come from `llama-batched-bench`, not llama-server `-np`: build 7941, kernel 6.11, February 2026, 512-token prompts and only 32 generated tokens per stream. Treat them as an upper bound for same-model seats. The server's `-np` default is -1 (auto), which becomes 4 slots with `kv_unified = true`.
- **S4** [confirmed] Confirmed by source reading and by two third-party production reports, not run on a GB10. One condition is mandatory at b11429: `--cache-ram 0`. PR #30295 (merged 2026-10-10, first in b11552) fixes a bug where a request pinned by `id_slot` to a busy slot still ran the RAM prompt-cache update and loaded another prompt into the generating slot; at b11429 that path is only closed when the RAM cache is off. A 2026-10-10 comment on #27148 reports 0 crossings in 60 concurrent pairs with `--cache-ram 0`.
- **S5a** [partly] 
- **S6a** [partly] #20345 was closed on 2026-03-10, the day it was opened (its last comment is 2026-06-02), not between June and October; #29613 closed 2026-09-29 and #29652 closed 2026-10-03. #30256 was reported on build 11429 itself, the pinned build, and gives a workaround: sending GBNF in the `grammar` field produced no reasoning in 3 of 3 runs where `json_schema` did.
- **S6b** [confirmed] Flags and fields are exact. Two details: the per-request budget is also accepted as `thinking_budget_tokens`, and the budget and `reasoning_control` are only applied when the template exposes thinking end tags, so they silently do nothing for other templates.
- **S7b** [partly] 
- **S7c** [refuted] Right for templates with no tool support: chat.h at b11429 lists only CONTENT_ONLY, PEG_SIMPLE, PEG_NATIVE, PEG_GEMMA4 and PEG_MINIMAX_M3. One nuance: for a template that supports tool calls but does not describe tools, chat.cpp still applies a fallback and logs 'Template supports tool calls but does not natively describe tools. The fallback behaviour used may produce bad results'.
- **S8a** [partly] 
- **S8b** [confirmed] 
- **S8c** [partly] The low end of the range is obsolete. 1 min 44 s was October 2025 on kernel 6.11 with mmap; the same thread reports, for the 59.02 GiB gpt-oss-120b without mmap, 27 s on DGX OS kernel 6.14, 22 s on 6.17, and 15 s after `echo 8192 > /sys/block/nvme0n1/queue/read_ahead_kb` (needs sudo). That is about 2.2 to 3.9 GiB/s; 64.8 s is a third-party runbook figure for a 63.4 GB file on kernel 6.17. The GX10's own kernel and drive are unmeasured.
- **S9a** [refuted] The `free -h` numbers are exact, but they were measured with Ollama (nemotron-3-super:120b), not llama-server; nvidia-smi listed that process at 89709 MiB. PR #26081 states that with mmap on an integrated GPU the model is in RAM twice temporarily during loading, which is why `--load-mode auto` now avoids mmap when a device reports no mmap support (CUDA does so for `prop.integrated` devices). So the double count is a load-time effect of mmap only.
- **S9b** [confirmed] Source reading, not run. The output format is fixed in common/fit.cpp: one stdout line per device, `<device name> <model MiB> <context MiB> <compute MiB>`, then a final line `Host <model> <context> <compute>`. `-np` is accepted by this tool, and `-ngl all` is a valid value at b11429.
- **S10b** [unverified] Still no report of the Linux archive on a Spark or GX10. Two things raise the odds: NVIDIA's own playbook Dockerfile builds the same style of portable binary (`-DGGML_NATIVE=OFF -DGGML_BACKEND_DL=ON -DCMAKE_CUDA_ARCHITECTURES=121`, but on CUDA 13.0.1), and the official Windows arm64 CUDA 13.4 archive runs on GB10-class hardware with `ARCHS = ...,1210`. That Windows report (#28112) also describes an intermittent start-up crash in about 3 of 10 launches.
- **S10c** [confirmed] Correct for b11429, but the installed build is unknown and older builds print a different line: at b7941 the source is `fprintf(stderr, "version: %d (%s)\n", LLAMA_BUILD_NUMBER, LLAMA_COMMIT)`, for example `version: 7941 (11fb327bf)`. The gateway's parser must accept both formats.

### Objections to recommendations
- Pinning b11429 with multi-seat servers: b11429 lacks PR #30295 (merged 2026-10-10, first in b11552). At b11429 a request pinned to a busy slot can have another prompt loaded into the slot that is still generating, unless the RAM prompt cache is off. Make `--cache-ram 0` a hard rule the supervisor enforces for every server, not a tuning choice (https://github.com/ggml-org/llama.cpp/pull/30295, https://github.com/ggml-org/llama.cpp/issues/27148).
- Structured vote: the recommended request (`response_format` json_schema plus `enable_thinking: false`) is the exact combination that fails for Gemma 4 on build 11429 in #30256, where long prompts ran to `max_tokens` with empty content. Add a GBNF `grammar` fallback before lenient parsing. That fallback conflicts with 'keep the tools array identical': chat.cpp throws 'Cannot specify grammar with tools' unless `tool_choice` is "none" (https://github.com/ggml-org/llama.cpp/issues/30256, https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/chat.cpp).
- Memory meter: a 1-2 GiB per-process allowance and a one-time MemAvailable drop at load under-count. Host memory per llama-server grew to 5.1-12.8 GiB over 21-44 hours in #28933 (a fork build), and context checkpoints (default 32 per slot) accumulate in host memory for sliding-window and hybrid models. Poll per-PID RSS during use and recycle a server above a threshold; 'keep the last council running between debates' makes this worse (https://github.com/ggml-org/llama.cpp/issues/28933).
- Over-commit on unified memory is not a clean failure. A third-party Spark runbook shows the global OOM killer taking out `avahi-daemon`, which made the box unreachable by name; a non-programmer owner cannot diagnose that. Keep the admission check strict and the reserve at 10 GiB or more; forum user eugr advises staying under about 115 GB (https://llama-cpp-ex.hexdocs.pm/dgx-spark.md, https://forums.developer.nvidia.com/t/help-on-llama-cpp-command-line-arguments-and-compilation-settings-performance-testing-included/357012).
- 'One seat generates at a time' is never true on the GPU, because the bubble summariser must run while a seat is speaking, and separate processes take turns on the one GPU. Nobody has measured the cost on a GB10. Add 'speaker plus summariser' to the smoke test, and test a CPU-only summariser (`-ngl 0`) as the alternative; my inference, unmeasured.
- Per-seat context of 16384: council.md (about 2,000 tokens), the evidence pack and every other seat's messages are appended each round, so 5-7 seats can overflow within a few rounds. Overflow is an error ('request (N tokens) exceeds the available context size'), and context shift is off. The gateway needs a per-round token budget and a deliberate compaction step that accepts one full re-read (https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-context.cpp).
- Supervisor inside the FastAPI gateway: if the gateway crashes or restarts, its llama-server children keep tens of GB, and the next start would load a second copy and exhaust memory. Plan a PID and port registry on disk, a sweep for stale servers at start-up, and a systemd service so the owner never has to clean up by hand; my inference from standard Linux practice.
- Install path for a non-programmer: the prebuilt archive is unverified on DGX OS and the source build needs sudo for apt packages plus a 5-10 minute compile (NVIDIA playbook, earlier research). Ship both as one scripted installer with the smoke test built in, and have the supervisor retry a failed server start once, given the intermittent start-up crash reported for the Windows arm64 prebuilt on GB10-class hardware (https://github.com/ggml-org/llama.cpp/issues/28112).
- Page cache between sequential loads: NVIDIA's playbook tells users to run `sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'` when memory problems appear within capacity, which the gateway cannot do without sudo. `--load-mode dio` should avoid filling the cache (my inference), but the third-party runbook measured direct I/O costing 3-4%, so compare `dio` and `none` in the smoke test as the original suggests (https://raw.githubusercontent.com/NVIDIA/dgx-spark-playbooks/main/nvidia/multi-agent-chatbot/README.md).

### Missed by the first pass
- Load progress without the router (undocumented, source reading at b11429, not run): a directly launched llama-server that has `LLAMA_SERVER_ROUTER_PORT` set in its environment behaves as a router child. It writes state lines with load progress (`stages`, `current`, `value` 0-1) to stdout and exits when its stdin reaches end-of-file, which would also give 'die with the gateway'. It is an internal protocol that may change between builds, so treat it as an experiment (https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/server-models.cpp).
- `return_progress: true` on a streaming request adds `prompt_progress` with `total`, `cache`, `processed` and `time_ms`. That gives the UI a real 'reading' state per seat and shows cache reuse per call before the final `timings` arrive (https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/tools/server/README.md).
- Slot save and restore (S5) is not dependable: #26676 (open, three independent reports) says `POST /slots/{id}?action=restore` reports success but the next request re-reads everything (`cache_n=0`). Do not build Pause, resume-after-restart or replay on it (https://github.com/ggml-org/llama.cpp/issues/26676).
- nvidia-smi does list per-process GPU memory on GB10: NVIDIA's known-issues page says so and a Spark capture shows a process at 89709 MiB. That is a per-seat GPU figure to pair with per-PID host RSS; whether the `--query-compute-apps` form works on GB10 is unverified (https://docs.nvidia.com/dgx/dgx-spark/known-issues.html, https://frankdenneman.ai/posts/2026-03-23-understanding-unified-memory-dgx-spark-nemoclaw-nemotron/).
- The closest official precedent for this design is NVIDIA's multi-agent-chatbot playbook: gpt-oss-120b, deepseek-coder 6.7B and Qwen3-Embedding-4B as three llama.cpp servers plus a TensorRT-LLM server on one Spark, about 120 of 128 GB, no MPS. It is worth reading before phase 3 (https://raw.githubusercontent.com/NVIDIA/dgx-spark-playbooks/main/nvidia/multi-agent-chatbot/assets/docker-compose-models.yml).
- Load speed depends on the kernel: the same owner measured 68 s on 6.11, 27 s on 6.14 and 22 s on 6.17 for the same model. Earlier research found DGX OS 7.5.0 ships 6.17 but partner systems can lag, so the gateway should record `uname -r` and the smoke test should time a cold load (https://github.com/ggml-org/llama.cpp/discussions/16578).
- `--sleep-idle-seconds N` exists at b11429 (default -1, off). It is an alternative to killing servers between debates: an idle server releases its model and reloads on the next request. Untested here; the KV cache is lost on sleep (https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/common/arg.cpp).
- PR #27624 (open) fixes a related slot bug: a slot picked by least-recently-used fallback can keep the previous request's prompt tokens, checkpoints and KV state. Always sending a fixed `id_slot` avoids that path, which is one more reason never to send a seat request without it (https://github.com/ggml-org/llama.cpp/pull/27624).
- Each CUDA process reserves 32 GiB of GPU virtual address space the first time its VMM pool is used (`cuMemAddressReserve` with `CUDA_POOL_VMM_MAX_SIZE`). Whether seven such reservations coexist on a GB10 is untested; the 'load 7 small models' smoke test is where it would show, and a build with `-DGGML_CUDA_NO_VMM=ON` is the fallback (https://raw.githubusercontent.com/ggml-org/llama.cpp/b11429/ggml/src/ggml-cuda/ggml-cuda.cu).
