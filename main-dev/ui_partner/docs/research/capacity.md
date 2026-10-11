# Research: capacity

Read-only research on 2026-10-10. Nothing was run on the GX10. The re-check section overrides the findings where they differ.

## Summary
A 5-minute debate on one GX10 is realistic only for councils of "fast" models with thinking off; it is not realistic for councils of dense 24-32B models or for models left in their default thinking mode. All round and load times below are my estimates built from measured single-model GB10 speeds; nobody has published a measurement of several llama-server processes sharing one GB10.

**Speed (measured on DGX Spark, llama.cpp).** Generation is limited by the 273 GB/s memory bus, so what matters is bytes read per token, not parameter count.
- MoE models with 3-4B active parameters: 49-90 tok/s (Qwen3.6-35B-A3B 62-65, gpt-oss-20b 83, Gemma-4-26B-A4B about 50, gpt-oss-120b 59).
- Dense 8-14B at Q4_K_M: 26-44 tok/s.
- Dense 27-32B at Q4_K_M: 10.7-11.9 tok/s (about 18 with an MTP draft model).
- Dense 70B: about 5 tok/s (one unre-measured Ollama figure).
- Prompt reading: 750-4,500 tok/s depending on model.

**Models.** Current mid-size picks with GGUF builds exist from Alibaba, Google, OpenAI, Mistral, IBM, NVIDIA and Z.ai. "Llama" and "Phi" are stale: Meta's newest open chat weights are Llama 4 (April 2025) and Llama 3.3 70B; Microsoft's is Phi-4 (December 2024, 16,384-token context). Qwen 3.6/3.8, Granite 4.2 and Gemma 4 think unless told not to (confirmed for Qwen and Granite on their cards; for Gemma 4 it follows from llama.cpp's default).

**Memory (computed, about 121 GiB usable).**
| Council | 16k per seat | 32k per seat |
|---|---|---|
| 5 seats (60 GiB weights) | 96 GiB, fits | 102 GiB, fits |
| 7 seats (73 GiB weights) | 118 GiB, tight | 126 GiB, does not fit |
Totals include 2 GiB per seat, 18 GiB fixed (OS, embedder, summariser, 8 GiB safety margin). Average weights per seat should stay under about 17 GiB for 5 seats and 11 GiB for 7.

**Time (estimate, one speaker at a time, thinking off, 330 tokens per turn).**
| Council type | Round, 3 / 5 / 7 seats | Rounds in 5 min |
|---|---|---|
| Fast (MoE or small) | 21 / 35 / 50 s | 13 / 7 / 5 |
| Mixed MoE + 8-14B dense | 30 / 50 / 70 s | 9 / 5 / 3 |
| Dense 27-32B | 95 / 160 / 225 s | 2 / 1 / 0 |
- The 2-minute preset only suits 3 fast seats (about 4 rounds).
- Default thinking multiplies generated tokens by 2.5-3.6x.
- Cold load of a whole council is about 0.5-2 minutes and should not count against the timer.

**Other picks.** Use a dedicated 2-3B summariser on the GPU, rate-limited (Ministral-3-3B measured at 92 tok/s); no CPU-only GB10 speeds were found. Keep Qwen3-Embedding-0.6B. Disk is not a constraint: a 12-model library is roughly 170-300 GB against 1, 2 or 4 TB.

## Claims

### C1a [partly] (load-bearing)
llama.cpp on a GB10 generates fast enough with 20-35B models for a live multi-agent debate.

Evidence: True for MoE models. llama.cpp's own DGX Spark bench (build 7941, pp2048/tg32): gpt-oss-20b MXFP4 4,506/83.4 tok/s, Qwen3-Coder-30B-A3B Q8_0 2,987/61.1, GLM-4.7-Flash Q8_0 2,364/48.7. Community runs: Qwen3.6-35B-A3B MXFP4 2,289/62.6 and UD-Q4_K_M 65.4 tok/s; Qwen3-30B-A3B Q4_K_M 2,541-3,287/89-91; Gemma-4-26B-A4B Q4_K_M 49.6 tok/s via Ollama (F16 only 26.8).

For the build: Build the default councils from MoE models with 3-4B active parameters. Store a measured speed (prompt and generation tok/s) per installed model and show it in the seat picker.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/benches/dgx-spark/dgx-spark.md, https://github.com/nabe2030/dense-27b-31b-dgx-spark, https://llama-cpp-ex.hexdocs.pm/dgx-spark.html, https://raw.githubusercontent.com/DandinPower/llama.cpp_bench/main/dgx_spark/report.md, https://raw.githubusercontent.com/sergioamsilva/dgx-spark-field-notes/main/benchmarks/RESULTS.md

### C1b [refuted] (load-bearing)
Dense mid-size models (24-32B) at Q4_K_M are about as fast as other mid-size models.

Evidence: Measured on DGX Spark, llama.cpp b8922 (pp512/tg128): Qwen3.5-27B Q4_K_M 821/11.94 tok/s, Qwen3.6-27B Q4_K_M 823/11.85, Gemma-4-31B Q4_K_M 746/10.65; a separate report has Qwen3-32B Q4_K_M at 762/10.7. An MTP draft raised Qwen3.6-27B from 11.59 to 18.65 tok/s (1.61x), and a user measured Qwen3.8-27B Q4_K_M with MTP at 18.08 tok/s; MTP gave MoE models no gain.

For the build: Mark dense 24-32B models as "slow" in the seat picker (about 30 s per turn). If one is seated, load its MTP companion file with `--spec-type draft-mtp`. Never default to an all-dense council.

Sources: https://github.com/nabe2030/dense-27b-31b-dgx-spark, https://raw.githubusercontent.com/DandinPower/llama.cpp_bench/main/dgx_spark/report.md, https://llama-cpp-ex.hexdocs.pm/dgx-spark.html, https://github.com/ggml-org/llama.cpp/discussions/27080

### C1c [confirmed]
Small (about 4B) and 8-14B models are fast on the GB10.

Evidence: Q4_K_M on DGX Spark (prompt/generation tok/s at 512 context): Qwen3-1.7B 11,947/161, Ministral-3-3B 6,961/91.9, Qwen3-8B 3,167/43.7, Ministral-3-8B 3,020/41.7, Ministral-3-14B 1,853/26.4. llama.cpp's own file adds Gemma-3-4b QAT Q4_0 at 5,949/81.1 and Qwen2.5-Coder-7B Q8_0 at 2,250/29.4.

For the build: Use 8-14B dense models at Q4_K_M to fill seats 5-7 where memory is tight. Prefer Q4 over Q8_0: the 7B model at Q8_0 is slower than 8B models at Q4_K_M.

Sources: https://raw.githubusercontent.com/DandinPower/llama.cpp_bench/main/dgx_spark/report.md, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/benches/dgx-spark/dgx-spark.md

### C1d [partly]
70B and 120B class models are usable as seats.

Evidence: gpt-oss-120b MXFP4 (59 GiB, MoE) measures 2,444/58.7 tok/s in llama.cpp's own file. For a dense 70B the only figure found is about 5 tok/s for llama3.3:70b under Ollama, marked by its author as not re-measured; scaling the 27B results by file size gives about 4.7 tok/s (my inference). No llama-bench result for a dense 70B on GB10 was found.

For the build: Do not offer Llama 3.3 70B as a timed-debate seat (about 70 s per 330-token turn). gpt-oss-120b is fast enough but takes half the memory, so it suits a 3-seat council only.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/benches/dgx-spark/dgx-spark.md, https://raw.githubusercontent.com/sergioamsilva/dgx-spark-field-notes/main/benchmarks/RESULTS.md

### C1e [refuted] (load-bearing)
Speeds stay constant as a seat's context fills.

Evidence: llama.cpp's DGX Spark file shows Qwen3-Coder-30B-A3B Q8_0 generation falling from 61.1 tok/s at depth 0 to 48.0 at 8k, 40.2 at 16k and 30.2 at 32k, with prompt reading falling from 2,987 to 1,348 tok/s. GLM-4.7-Flash prompt reading falls from 2,364 to 567 tok/s at 32k; gpt-oss-20b is milder (83.4 to 61.7 tok/s generation).

For the build: Default to 16k context per seat and keep debate prompts short (retrieved passages, not whole files). Derate speed estimates by 15-35% for later rounds.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/benches/dgx-spark/dgx-spark.md

### C2a [partly]
The wireframe's example makers (Qwen, Llama, Gemma, Phi, Mistral) each have a current good mid-size open-weight chat model.

Evidence: Hugging Face org listings show current releases for Qwen (Qwen3.8-27B, 2026-08-05; Qwen3.6-35B-A3B, 2026-04-15), Gemma 4 (March-May 2026) and Mistral (Ministral 3 2512 family). Meta's newest open chat weights are Llama 4 (April 2025) and Llama 3.3 70B (2024-11-26); Microsoft's newest general Phi chat model is phi-4 (2024-12-11), and no Phi-5 exists on the Hub. Quality rankings between models were not verified from any primary source.

For the build: Keep seat names data-driven, not hardcoded to these five. Offer OpenAI gpt-oss, IBM Granite and NVIDIA Nemotron as the more current alternatives to the Llama and Phi seats.

Sources: https://huggingface.co/api/models?author=Qwen&sort=createdAt&direction=-1, https://huggingface.co/api/models?author=google&sort=createdAt&direction=-1, https://huggingface.co/api/models?author=meta-llama&sort=createdAt&direction=-1, https://huggingface.co/api/models?author=microsoft&search=phi&sort=createdAt&direction=-1

### C2b [confirmed] (load-bearing)
Qwen3.6-35B-A3B is a suitable Qwen seat.

Evidence: 35.95B parameters (MoE, 256 experts, 8 used), Apache-2.0, trained context 262,144. unsloth GGUF: UD-Q4_K_M 22.13 GB, MXFP4_MOE 21.71 GB, Q8_0 36.90 GB; the chat template has a tools section. It thinks by default and measures 62.6-65.4 tok/s on DGX Spark.

For the build: Default Qwen seat: `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`, with thinking disabled per request. Its KV cache is tiny (about 0.31 GiB at 16k) because only 10 of 40 layers use full attention.

Sources: https://huggingface.co/Qwen/Qwen3.6-35B-A3B, https://huggingface.co/api/models/unsloth/Qwen3.6-35B-A3B-GGUF/tree/main?recursive=true, https://github.com/nabe2030/dense-27b-31b-dgx-spark, https://llama-cpp-ex.hexdocs.pm/dgx-spark.html

### C2c [partly]
Qwen3.8-27B, the newest Qwen mid-size model, is a good seat.

Evidence: 27.78B parameters, dense, Apache-2.0, context 262,144; GGUF sizes are 16.46 GB (unsloth UD-Q4_K_M), 18.97 GB (ggml-org Q4_K_M) and 28.6-29.05 GB (Q8_0). Its card says thinking is on by default with `reasoning_effort` defaulting to xhigh. Reported GB10 speed is about 15-18 tok/s even with MTP, and plain dense 27B runs at about 12 tok/s.

For the build: Offer it as an optional "slow, strong" seat with its MTP file (`mtp-Qwen3.8-27B-Q4_0.gguf`, 1.68 GB) and thinking off. Do not put it in the default council.

Sources: https://huggingface.co/Qwen/Qwen3.8-27B, https://huggingface.co/api/models/ggml-org/Qwen3.8-27B-GGUF/tree/main?recursive=true, https://huggingface.co/api/models/unsloth/Qwen3.8-27B-GGUF/tree/main?recursive=true, https://github.com/ggml-org/llama.cpp/discussions/27080

### C2d [confirmed] (load-bearing)
Gemma 4 provides suitable Google seats.

Evidence: All Apache-2.0 with tools in the chat template and configurable thinking. gemma-4-26B-A4B-it: 25.8B MoE, context 262,144, UD-Q4_K_M 16.95 GB, Q8_0 26.86 GB, about 50 tok/s. gemma-4-31B-it: 31.3B dense, Q4_K_M 18.32 GB, 10.65 tok/s. gemma-4-12B-it: 11.96B dense, Q4_K_M 7.12 GB, Q8_0 about 13 GB, speed not measured on GB10.

For the build: Default Google seat: `gemma-4-26B-A4B-it-UD-Q4_K_M.gguf`. Skip the `mmproj` files (0.8-2.3 GB each) since the council reads extracted text. Send only final content, not thoughts, back in history, as the card requires.

Sources: https://huggingface.co/google/gemma-4-26B-A4B-it, https://huggingface.co/api/models/unsloth/gemma-4-26B-A4B-it-GGUF/tree/main?recursive=true, https://huggingface.co/api/models/unsloth/gemma-4-12b-it-GGUF?expand[]=gguf, https://github.com/nabe2030/dense-27b-31b-dgx-spark, https://raw.githubusercontent.com/sergioamsilva/dgx-spark-field-notes/main/benchmarks/RESULTS.md

### C2e [confirmed]
gpt-oss-20b is a suitable OpenAI seat.

Evidence: 20.9B parameters (MoE, 4 of 32 experts), Apache-2.0, context 131,072; ggml-org `gpt-oss-20b-MXFP4.gguf` is 12.11 GB, unsloth Q4_K_M 11.62 GB and Q8_0 12.11 GB. llama.cpp lists GPT-OSS (Harmony) as a native tool-call format, and measured speed is 4,506/83.4 tok/s. It always reasons; whether llama.cpp's `reasoning_effort: none` fully suppresses that for this template was not verified.

For the build: Seat it with `--reasoning-effort low` plus a reasoning token budget, and test what `reasoning_effort: none` actually does on the pinned build.

Sources: https://huggingface.co/openai/gpt-oss-20b, https://huggingface.co/api/models/ggml-org/gpt-oss-20b-GGUF/tree/main?recursive=true, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/docs/function-calling.md, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/benches/dgx-spark/dgx-spark.md

### C2f [confirmed]
Mistral has a suitable mid-size seat with a GGUF build.

Evidence: Ministral-3-14B-Instruct-2512: 13.9B dense, Apache-2.0, context 262,144, official GGUF Q4_K_M 8.24 GB and Q8_0 14.36 GB, tools in template, no thinking mode, 1,853/26.4 tok/s measured. Mistral-Small-3.2-24B and Magistral-Small-2509 are 24.0B, Apache-2.0, Q4_K_M 14.33 GB, Q8_0 25.06 GB; the official Magistral GGUF has no embedded chat template and a 40,960 context. Mistral Small 4 and Medium 3.5 are 119-128B.

For the build: Default Mistral seat: the official `Ministral-3-14B-Instruct-2512-Q4_K_M.gguf`. Its card asks for temperature below 0.1, so sampling settings must be per model.

Sources: https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512, https://huggingface.co/api/models/mistralai/Ministral-3-14B-Instruct-2512-GGUF/tree/main?recursive=true, https://huggingface.co/api/models/mistralai/Magistral-Small-2509-GGUF?expand[]=gguf, https://raw.githubusercontent.com/DandinPower/llama.cpp_bench/main/dgx_spark/report.md

### C2g [partly]
IBM Granite 4.2 is a usable extra maker.

Evidence: granite-4.2-30b (29.3B dense, Q4_K_M 17.72 GB, Q8_0 31.11 GB) and granite-4.2-8b (8.8B, Q4_K_M 5.35 GB, Q8_0 9.35 GB) are Apache-2.0 with official GGUFs (2026-08-12), context 131,072 and tools in the template. The card says thinking is the default mode and requires temperature 1.0. No GB10 speed was found; by size I estimate about 11 tok/s for the 30b and about 40 tok/s for the 8b.

For the build: Use granite-4.2-8b Q4_K_M as a small fast seat with thinking off; treat the 30b as a slow dense seat. Measure both on the GX10 before listing a speed.

Sources: https://huggingface.co/ibm-granite/granite-4.2-30b, https://huggingface.co/api/models/ibm-granite/granite-4.2-30b-GGUF/tree/main?recursive=true, https://huggingface.co/api/models/ibm-granite/granite-4.2-8b-GGUF/tree/main?recursive=true

### C2h [partly] (load-bearing)
Phi-4 can fill the Phi seat like any other model.

Evidence: microsoft/phi-4 is 14.66B dense, MIT, with a GGUF context_length of 16,384; Q4_K_M is 9.05 GB (bartowski) and Q8_0 15.58 GB. Its 462-character chat template has no tools section and it has no thinking mode. No GB10 speed was found; by size I estimate about 24 tok/s.

For the build: Cap this seat at 16,384 tokens whatever the council setting, and read each model's `context_length` from the GGUF. Phi-4 cannot join a 32k council at full context.

Sources: https://huggingface.co/microsoft/phi-4, https://huggingface.co/api/models/microsoft/phi-4-gguf?expand[]=gguf, https://huggingface.co/api/models/bartowski/phi-4-GGUF/tree/main?recursive=true

### C2i [refuted]
There is a current, fast Llama model for the Llama seat.

Evidence: Llama 3.3 70B (Q4_K_M 42.52 GB, Q8_0 74.98 GB, llama3.3 licence) runs at about 5 tok/s; Llama 4 Scout is 108.6B with a 65.36 GB Q4_K_M under a custom llama4 licence. The practical option is Llama 3.1 8B Instruct from July 2024 (Q4_K_M 4.92 GB, Q8_0 8.54 GB, context 131,072, native tool format in llama.cpp, no thinking). Meta's own repos are gated.

For the build: If the owner wants a Llama seat, use Llama 3.1 8B Q4_K_M and say plainly it is a 2024 model. Otherwise fill that seat with gpt-oss-20b or Nemotron.

Sources: https://huggingface.co/api/models/bartowski/Llama-3.3-70B-Instruct-GGUF/tree/main?recursive=true, https://huggingface.co/api/models/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/tree/main?recursive=true, https://huggingface.co/api/models/unsloth/Llama-4-Scout-17B-16E-Instruct-GGUF/tree/main?recursive=true, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/docs/function-calling.md

### C2j [partly]
NVIDIA and Z.ai offer further 30B-class MoE seats.

Evidence: NVIDIA-Nemotron-3.5-Lightning-30B-A3B (31.6B, hybrid Mamba/attention MoE with 6 attention layers; ggml-org GGUF Q4_0 18.90 GB, Q8_0 33.59 GB) carries an "other" licence and has no GB10 llama.cpp speed I could find. GLM-4.7-Flash (31.2B MoE, MIT, context 202,752, Q4_K_M 18.31 GB, Q8_0 31.84 GB) measures 2,364/48.7 tok/s at Q8_0. The newer GLM-5.3-Flash is 321B and DeepSeek-V4.1-Flash 763B.

For the build: Offer both as optional seats. Read the Nemotron licence before making it a default, and benchmark it on the GX10 first. GLM-4.7-Flash's prompt reading degrades badly with depth, so keep it at 16k.

Sources: https://huggingface.co/api/models/ggml-org/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF/tree/main?recursive=true, https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-Base-BF16/resolve/main/config.json, https://huggingface.co/api/models/unsloth/GLM-4.7-Flash-GGUF/tree/main?recursive=true, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/benches/dgx-spark/dgx-spark.md

### C2k [partly] (load-bearing)
Every council model supports tool calling in llama.cpp, so agents can search files through tools.

Evidence: llama.cpp's function-calling doc says tool calls work for all models under `--jinja`, natively for a listed set (Llama 3.x, Hermes/Qwen 2.5, Mistral Nemo, GPT-OSS Harmony) and through a less efficient Generic handler otherwise. The GGUF chat templates of the 2026 candidates contain a tools section, except phi-4 and the official Magistral GGUF. Which handler each 2026 model gets was not verified.

For the build: Do not make research depend on native tool calls. Have the engine ask each seat for search queries as schema-constrained JSON (`response_format` / `json_schema`), run the search itself and append the passages. Use the same mechanism for the one-sentence answer.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/docs/function-calling.md, https://huggingface.co/api/models/microsoft/phi-4-gguf?expand[]=gguf, https://huggingface.co/api/models/mistralai/Magistral-Small-2509-GGUF?expand[]=gguf

### C3a [confirmed] (load-bearing)
A 5-seat council of mid-size models fits in about 121 GiB at 16k and at 32k context per seat.

Evidence: Computed, not measured. Seats: Qwen3.6-35B-A3B 20.61 GiB, Gemma-4-26B-A4B 15.78, gpt-oss-20b 11.28, Ministral-3-14B 7.67, Granite-4.2-8b 4.98 = 60.3 GiB of weights. f16 KV is 7.3 GiB at 16k or 13.9 GiB at 32k; adding 2 GiB per seat and 18 GiB fixed gives 95.6 GiB at 16k and 102.2 GiB at 32k.

For the build: The memory meter should compute, per seat, file size + KV from GGUF metadata + a 2 GiB allowance, plus 18 GiB fixed (6 OS and gateway, 1.5 embedder, 2.5 summariser, 8 safety). Calibrate the allowance from real /proc/meminfo readings on first load.

Sources: earlier research: research:llama-rpc A10a (KV bytes = attention layers x n_ctx x kv_heads x head_dim x 4 at f16), earlier research: research:hardware-telemetry B1a (about 121 GiB usable), https://huggingface.co/Qwen/Qwen3.6-35B-A3B/resolve/main/config.json, https://huggingface.co/google/gemma-4-26B-A4B-it/resolve/main/config.json, https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512/resolve/main/config.json, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/src/llama-model.cpp

### C3b [partly] (load-bearing)
A 7-seat council of mid-size models fits at 16k and at 32k context per seat.

Evidence: Computed. Adding Llama-3.1-8B (4.58 GiB) and Phi-4 (8.43 GiB) to the 5-seat set gives 73.3 GiB of weights; with 12.4 GiB KV at 16k the total is 117.7 GiB, which fits with about 3 GiB spare beyond the safety margin. At 32k KV is 21.0 GiB and the total 126.4 GiB, which does not fit. Seven 30B-class models (17-21 GiB each) do not fit at any context.

For the build: For 6-7 seats, force 16k context and make the picker suggest 8-14B models for the extra seats. Block Start when the meter exceeds MemAvailable minus the margin rather than letting llama-server try.

Sources: earlier research: research:llama-rpc A10a, https://huggingface.co/microsoft/phi-4/resolve/main/config.json, https://huggingface.co/unsloth/Meta-Llama-3.1-8B-Instruct/resolve/main/config.json, https://huggingface.co/api/models/bartowski/phi-4-GGUF/tree/main?recursive=true

### C3c [partly] (load-bearing)
Memory is what limits model size per seat.

Evidence: Memory allows average weights of about 30 GiB per seat for 3 seats, 17 GiB for 5 and 11 GiB for 7 at 16k (computed from 103 GiB left after fixed costs). Speed binds sooner: dense models above about 14B fall to 10-15 tok/s, while MoE models up to 36B at Q4 (15-21 GiB) stay at 50-65 tok/s.

For the build: Largest sensible seat: an MoE of up to about 36B total with 3-4B active at Q4 (about 21 GiB), or a dense model up to about 14B at Q4_K_M (about 8.5 GiB). Show both a memory meter and a time estimate in the seat picker.

Sources: https://raw.githubusercontent.com/DandinPower/llama.cpp_bench/main/dgx_spark/report.md, https://github.com/nabe2030/dense-27b-31b-dgx-spark

### C3d [refuted] (load-bearing)
Weights plus KV cache is the whole memory cost of a llama-server seat.

Evidence: The server README gives `--cache-ram` a default of 8192 MiB of host-RAM prompt cache per server and `--ctx-checkpoints` a default of 32 per slot; seven servers could claim tens of GiB on top of the model. A field report says loading with mmap leaves about 100 GB of page cache behind, and the GB10 runbook shows over-commit ends in a global OOM kill that took down avahi-daemon. Per-process CUDA overhead on GB10 was not found in any source.

For the build: Launch every seat with `--cache-ram 0`, a low `--ctx-checkpoints` (start at 4), explicit `-c` and `-np 1`, `--fit off`, and a non-mmap load mode. Watch /proc/meminfo and /proc/pressure/memory during spool-up and abort before the kernel does.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md, https://raw.githubusercontent.com/sergioamsilva/dgx-spark-field-notes/main/docs/loading-performance.md, https://llama-cpp-ex.hexdocs.pm/dgx-spark.html

### C4a [partly] (load-bearing)
A debate round with seats sharing one GPU takes well under a minute.

Evidence: Estimate, assuming one speaker at a time, thinking off, 330 generated tokens per turn, append-only cached prompts and 0.8-2k new prompt tokens per turn. Fast seats (55 tok/s) take about 7 s per turn, so 21/35/50 s for 3/5/7 seats; mixed MoE plus 8-14B dense about 30/50/70 s; dense 27-32B (11 tok/s) about 95/160/225 s. Round 1 is about 40% longer because each seat reads roughly 6k tokens.

For the build: Cap each turn with `max_tokens` (about 350-450). Fold the one-sentence current answer into the end of each turn instead of a second request. Compute a per-council round estimate from stored per-model speeds and show it before Start.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/benches/dgx-spark/dgx-spark.md, https://raw.githubusercontent.com/DandinPower/llama.cpp_bench/main/dgx_spark/report.md, https://github.com/nabe2030/dense-27b-31b-dgx-spark

### C4b [partly] (load-bearing)
The 5-minute default (with 2 and 10 minute presets) gives a council enough rounds to converge.

Evidence: Estimate, with 15-20 s reserved for the final write-up. In 5 minutes a fast council gets about 13/7/5 rounds for 3/5/7 seats, a mixed council 9/5/3, and a dense 27-32B council 2/1/0. In 2 minutes: fast 4/2/1, mixed 3/1/1, dense 0. In 10 minutes: fast 27/16/11, mixed 19/11/7, dense 5/3/2. How many rounds a council needs to reach 80% is unknown.

For the build: Keep 5 minutes as the default for fast and mixed councils up to 5 seats. Grey out or warn on the 2-minute preset above 3 seats and on any preset where the estimate is under 2 rounds. Stop debating at limit minus a write-up reserve.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/benches/dgx-spark/dgx-spark.md, https://raw.githubusercontent.com/sergioamsilva/dgx-spark-field-notes/main/docs/reasoning-models.md

### C4c [refuted] (load-bearing)
Spool-up is quick enough to count inside the debate timer.

Evidence: Measured GB10 load rates span 0.6-2.9 GB/s: gpt-oss-120b (59 GiB) took 1 min 44 s by default, 49 s with a unified-memory setting and 22 s on kernel 6.17.1; another runbook measured 63.4 GB in 64.8 s. At those rates a 65 GB 5-seat council loads cold in roughly 22-108 s and a 79 GB 7-seat council in 27-131 s (estimate, before per-process start-up). A field report says the Spark's mmap path is slow and `--no-mmap` loads 1.5-2x faster.

For the build: Start the timer when the first seat begins its first turn, not at Ask. Show spool-up as its own stage with per-seat progress. Keep the last council's servers running between debates so repeat debates start warm.

Sources: https://github.com/ggml-org/llama.cpp/discussions/16578, https://llama-cpp-ex.hexdocs.pm/dgx-spark.html, https://raw.githubusercontent.com/sergioamsilva/dgx-spark-field-notes/main/docs/loading-performance.md

### C4d [unverified] (load-bearing)
Seats can generate at the same time on the shared GPU without losing total throughput.

Evidence: No measurement of several llama-server processes generating concurrently on a GB10 was found. Batching gains are documented only inside one process (Qwen3-Coder-30B-A3B aggregate 58 tok/s at 1 stream, 70 at 2, 98 at 4), and generation is bound by the shared 273 GB/s memory bus.

For the build: Design the engine for one speaker at a time, which also matches the Table View's single glowing speaker. Make the scheduler's concurrency a setting and test 2 concurrent seats on the GX10 before considering parallel turns.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/benches/dgx-spark/dgx-spark.md, https://raw.githubusercontent.com/DandinPower/llama.cpp_bench/main/dgx_spark/report.md

### C5a [partly] (load-bearing)
A small fast model (4B or under) can write the bubble lines every few seconds.

Evidence: Speed is confirmed on GPU: Ministral-3-3B Q4_K_M (2.15 GB, Apache-2.0, no thinking mode) measures 6,961 tok/s reading and 91.9 tok/s writing on DGX Spark, so a 300-token read plus 35-token line takes about 0.45 s. Qwen3-1.7B measures 161 tok/s; Qwen3.5-2B is 1.28 GB at Q4_K_M and Gemma-4-E2B Q4_K_M ran at 53 tok/s under Ollama. Summary quality at this size was not tested by any source I opened.

For the build: Run one dedicated summariser server and call it only for the seat that is speaking, at most once every 4-5 s, with `max_tokens` about 40 and thinking off. One call per 4 s costs roughly 10% of GPU time (estimate). Fall back to the last complete sentence when a call is late.

Sources: https://raw.githubusercontent.com/DandinPower/llama.cpp_bench/main/dgx_spark/report.md, https://huggingface.co/api/models/mistralai/Ministral-3-3B-Instruct-2512-GGUF/tree/main?recursive=true, https://huggingface.co/api/models/unsloth/Qwen3.5-2B-GGUF/tree/main?recursive=true, https://ai-muninn.com/en/blog/dgx-spark-gemma4-complete-guide

### C5b [unverified]
Running the summariser on the CPU cores keeps it from competing with the debating models.

Evidence: No CPU-only tok/s for any model on a GB10 was found; the nearest datum is a runbook line that zero GPU layers costs 57% of decode, model unnamed. CPU and GPU share the same memory bus, so a CPU summariser still takes bandwidth from GPU decoding (my inference). The same runbook reports that `GGML_NATIVE` on GCC 13.3 silently builds the CPU backend without dotprod, i8mm or SVE kernels.

For the build: Default the summariser to the GPU and make the device a config switch (`-ngl 0 -t 4` pinned to performance cores 5-9 or 15-19). A/B both on the GX10 by measuring the speaking seat's tok/s with summaries on and off.

Sources: https://llama-cpp-ex.hexdocs.pm/dgx-spark.html, https://learn.arm.com/learning-paths/laptops-and-desktops/dgx_spark_llamacpp/3_gb10_llamacpp_cpu/

### C5c [refuted] (load-bearing)
Each agent summarising itself is a workable alternative to a separate small model.

Evidence: My inference from measured figures: a seat cannot summarise while it is generating without a second slot, which adds a second KV cache and slows the main stream (Qwen3-Coder-30B-A3B drops from 58 tok/s alone to about 35 tok/s per stream at 2 streams). A dense seat at 11 tok/s would need over 3 s per 35-token line, and thinking models would reason first.

For the build: Keep the separate small model. The one free form of self-summary is the one-sentence current answer each agent already writes at the end of its turn: show that as the turn's final bubble.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/benches/dgx-spark/dgx-spark.md, https://github.com/nabe2030/dense-27b-31b-dgx-spark

### C6a [partly]
Qwen3-Embedding-0.6B is still the best small embedding GGUF.

Evidence: The one new contender is google/embeddinggemma-2 (2026-09-14, Apache-2.0, 768 dimensions, 8,192 context, Q8_0 GGUF 310 MB published 2026-10-06), whose card reports an MTEB Multilingual v2 mean of 61.36. Qwen's card reports 64.33 for Qwen3-Embedding-0.6B on MTEB Multilingual; the two figures come from different cards and possibly different benchmark versions. jina-embeddings-v5-text-small is CC-BY-NC-4.0; Nemotron-3-Embed was not evaluated.

For the build: Keep `Qwen3-Embedding-0.6B-Q8_0.gguf` (639 MB): longer context, 16 months of llama.cpp support, and no sign of a better small model. Store model id and dimension in the index so a later switch forces a clean re-index.

Sources: https://huggingface.co/google/embeddinggemma-2, https://huggingface.co/api/models/ggml-org/embeddinggemma-2-GGUF/tree/main, https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/raw/main/README.md, earlier research: verify:documents-models E4

### C6b [partly]
The embedding model can run on CPU alongside a debate.

Evidence: llama-server can run it with no GPU layers, but no CPU embedding speed on GB10 was found, and the CPU build pitfall in C5b applies. A debate needs only one short query embedding per search, which is negligible on the GPU too (my estimate). Earlier research noted the server defaults to the model's 32,768 context and reports of high memory use at that setting.

For the build: Run the embedder on the GPU with `-c 2048 -ub 2048 -np 1` (about 1.5 GiB all in) and pause bulk indexing while a debate is running. Keep a CPU option only as a fallback.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md, https://llama-cpp-ex.hexdocs.pm/dgx-spark.html, earlier research: verify:documents-models (recommendation objections)

### C7a [refuted] (load-bearing)
Thinking models cost little extra time in a timed debate.

Evidence: Measured on a DGX Spark with Qwen3.6-35B-A3B: a two-sentence answer took 239 tokens by default and 67 with thinking off, about 60% of tokens were hidden reasoning, and a 20-task set took 369 s against 52 s. Qwen3.6, Qwen3.8 (effort xhigh) and Granite 4.2 think by default per their cards. A token cap sized for a non-thinking model produced empty answers, and `/no_think` made Qwen3.6 reason until the limit.

For the build: Turn thinking off for debate turns by default. Budget 2.5-3.6x the generated tokens for any seat allowed to think. Never rely on `/no_think` in the prompt.

Sources: https://raw.githubusercontent.com/sergioamsilva/dgx-spark-field-notes/main/docs/reasoning-models.md, https://huggingface.co/Qwen/Qwen3.8-27B, https://huggingface.co/ibm-granite/granite-4.2-30b

### C7b [confirmed] (load-bearing)
llama.cpp can cap hidden reasoning per model and per request.

Evidence: The server README lists `--reasoning [on|off|auto]`, `--reasoning-effort LEVEL`, `--reasoning-budget N` (-1 unrestricted, 0 immediate end, N>0 token budget) and `--reasoning-budget-message`. Server source reads per-request `reasoning_budget_tokens` (alias `thinking_budget_tokens`), treats `reasoning_effort: "none"` as thinking off, and honours `chat_template_kwargs.enable_thinking`. These are from master (b11552, 2026-10-10); the GX10's installed build is unknown.

For the build: Send `reasoning_effort: "none"` (or `chat_template_kwargs: {"enable_thinking": false}`) per request. For a "think briefly" seat send `reasoning_budget_tokens: 256` and raise `max_tokens` by the same amount. Read `reasoning_content` separately and keep it out of the history sent to other seats.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/server-common.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/common/arg.cpp

### C8 [confirmed]
The GX10's storage has room for a library of 7 to 12 models.

Evidence: ASUS lists one M.2 slot with 1 TB or 2 TB (PCIe 4.0) or 4 TB (PCIe 5.0); ServeTheHome says it is a 2242 slot and user-replaceable with effort. The 7-seat example is 78.7 GB; twelve Q4-class models averaging 14 GB are about 170 GB, or about 300 GB with gpt-oss-120b (63 GB) and a few Q8_0 copies, plus under 3 GB for summariser and embedder. Which capacity the owner has, and how full it is, is unknown.

For the build: No external storage is needed. Have the downloader check free space before each download, refuse below about 10% free, and show library size on the Models screen. Skip `mmproj`, BF16 and duplicate quantisations.

Sources: https://www.asus.com/networking-iot-servers/desktop-ai-supercomputer/ultra-small-ai-supercomputers/asus-ascent-gx10/techspec, https://www.servethehome.com/asus-ascent-gx10-review-a-new-nvidia-gb10-solution/2

## Recommendations
- **Default 5-seat council**: Qwen3.6-35B-A3B UD-Q4_K_M (22.13 GB), gemma-4-26B-A4B-it UD-Q4_K_M (16.95 GB), gpt-oss-20b MXFP4 (12.11 GB), Ministral-3-14B-Instruct-2512 Q4_K_M (8.24 GB), granite-4.2-8b Q4_K_M (5.35 GB), each at 16k context. _Why:_ Five makers, all Apache-2.0, 60 GiB of weights and about 96 GiB all in. Three seats are measured at 50-83 tok/s and one at 26 tok/s on a DGX Spark; the Granite seat's about 40 tok/s is my estimate. That puts a round at roughly 40-50 s.
- **Seats 6 and 7**: Add Llama 3.1 8B Instruct Q4_K_M (4.92 GB) and phi-4 Q4_K_M (9.05 GB, capped at 16,384 context) if the owner wants the Llama and Phi names; otherwise add GLM-4.7-Flash Q4_K_M or Nemotron-3.5-Lightning-30B-A3B Q4_0 only in place of, not on top of, a large seat. Force 16k context at 6-7 seats. _Why:_ The 7-seat set totals about 118 GiB at 16k and 126 GiB at 32k against 121 GiB usable. Seven 30B-class models do not fit at all.
- **Quantisation**: Q4-class files for every seat (UD-Q4_K_M, Q4_K_M, or MXFP4 for MoE models). _Why:_ Generation on the GB10 is bound by bytes read per token, so Q4 is both smaller and faster: Qwen3-30B-A3B measures 85-91 tok/s at Q4_K_M against 61-62 at Q8_0.
- **Per-seat llama-server flags**: `llama-server -m <file> --host 127.0.0.1 --port <p> -c 16384 -np 1 -ngl all -fa on --jinja -lm dio --fit off --cache-ram 0 --ctx-checkpoints 4 --reasoning off`. Check each spelling against `llama-server --help` on the pinned build; older builds use `--no-mmap` instead of `-lm`. _Why:_ Explicit context and one slot make memory predictable. `--cache-ram 0` removes an 8 GiB-per-server default. A non-mmap load avoids the Spark's slow mmap path and a second copy of the weights in page cache. `--fit off` makes a misfit fail loudly instead of silently shrinking context.
- **Turn scheduling and prompt shape**: One seat generates at a time. Each seat's conversation is append-only with `cache_prompt: true`. Each turn is capped by `max_tokens` and ends with the one-sentence current answer in a fixed, schema-constrained form. _Why:_ Cross-process concurrency on a GB10 is unmeasured and generation is bus-bound, so parallel turns are unlikely to help. Qwen 3.5/3.6/3.8 (hybrid memory) and Gemma 4 (sliding-window cache) cannot cheaply rewind, so any edit to earlier prompt text forces a full re-read.
- **Thinking policy**: Off by default for every seat via per-request `reasoning_effort: "none"` or `chat_template_kwargs: {"enable_thinking": false}`. Optional per-seat "think briefly" = `reasoning_budget_tokens: 256` with `max_tokens` raised to match. At model install, run one probe prompt and record whether the model honours the switch. _Why:_ Default thinking measured 3.6x the tokens and 7x the time on a Spark, which would cut a 5-seat council from about 7 rounds to 2-3 in 5 minutes.
- **Bubble summariser**: A dedicated llama-server with Ministral-3-3B-Instruct-2512 Q4_K_M (official GGUF, 2.15 GB) on the GPU, `-c 4096 -np 1`. Summarise only the speaking seat, at most every 4-5 s, about 40 output tokens, cancelling a stale call when new text arrives. Keep the device switchable to CPU. _Why:_ It is the only small candidate with a measured GB10 speed and no thinking mode to manage (6,961 tok/s read, 91.9 tok/s write, about 0.45 s per bubble). No CPU-only GB10 speed exists to justify a CPU default, and CPU decoding shares the same memory bus.
- **Embedding model**: Keep `Qwen3-Embedding-0.6B-Q8_0.gguf` on its own llama-server, on the GPU, with `--embedding --pooling last -c 2048 -ub 2048 -np 1`. Pause bulk indexing during debates. _Why:_ Nothing found beats it at this size; EmbeddingGemma 2 reports a lower multilingual score on its own card and its GGUF is four days old. A small explicit context avoids the 32k default's memory cost.
- **What the timer measures**: The timer starts when the first seat starts its first turn and stops debating at the limit minus a write-up reserve (about 20 s for fast councils, more when the writer is slow). Spool-up is a separate, untimed stage. Keep the last council's servers alive between debates. _Why:_ A cold council load is an estimated 0.5-2 minutes, which is 10-40% of the default and potentially all of the 2-minute preset. The plan already lists Spool up as its own step.
- **Seat-aware time estimate**: Store measured prompt and generation tok/s per installed model (from the `timings` object llama-server returns) and show "about N rounds in M minutes" next to the memory meter. Warn when N is under 2. _Why:_ Round time varies about 5x between a fast and a dense council of the same size, so a fixed 2/5/10 preset means very different things per council.
- **Dense 27B seats, if the owner wants one**: Load the model's MTP companion as a draft: `--spec-type draft-mtp` with the `mtp-*.gguf` file as the draft model (the maintainer's example adds `--spec-default`). _Why:_ Measured 1.61x on Qwen3.6-27B Q4_K_M (11.59 to 18.65 tok/s) for about 1.3-1.7 GB more memory.
- **Research and answer extraction mechanism**: Engine-driven retrieval: ask each seat for search queries and for its one-sentence answer as JSON constrained by `response_format` / `json_schema`, rather than native tool calls. _Why:_ Grammar-constrained JSON works the same for every GGUF. Native tool-call handling differs per template, and phi-4's template has no tools section.
- **Per-model settings registry**: One record per installed model: file, `context_length`, KV parameters, sampling preset from the model card, thinking capability and off-switch, speed class, optional MTP file. _Why:_ Cards disagree sharply: Ministral asks for temperature under 0.1, Granite 4.2 requires 1.0, Qwen uses different presets for thinking and non-thinking; context limits range from 16,384 (phi-4) to 262,144.
- **First test on the real GX10, before phase 3**: A one-off benchmark script that (1) cold-loads the 5-seat council with mmap, with `-lm dio`, and in parallel versus one at a time; (2) records MemAvailable after each load; (3) measures one seat's tok/s alone, with a second seat generating, and with the summariser on GPU versus CPU; (4) checks each model's thinking switch. _Why:_ Every time and memory figure here that involves more than one process is an estimate; these four measurements replace them.

## Risks
- Seat choice can silently break the timer: a council of dense 24-32B models, or any seat left in default thinking mode, gets 0-2 rounds in 5 minutes instead of 5-13.
- Running out of unified memory is a host-level OOM kill, not a clean llama-server error; a GB10 runbook saw it kill avahi-daemon and make the box unreachable by name. Defaults make this easy: 8192 MiB `--cache-ram` per server, 32 context checkpoints per slot, and page cache left behind by mmap loads.
- Every multi-process number here is an estimate. If two llama-server processes interfere more than simple time-sharing implies, or idle servers cost GPU time, rounds will be slower than stated.
- Prompt-cache misses multiply reading time: Qwen 3.5/3.6/3.8 and Gemma 4 use hybrid or sliding-window memory in llama.cpp, so inserting or rewriting earlier prompt text (for example placing the owner's mid-debate note anywhere but the end) forces a full re-read each turn.
- Cold start of 0.5-2 minutes may be worse on the GX10: the Spark's mmap path is reported slow even on kernel 6.17.1, and partner systems can lag NVIDIA's OS updates.
- Model quirks: phi-4 has a 16,384-token context and no tools section; the official Magistral GGUF has no chat template; Granite and Qwen need different sampling settings per mode; a `max_tokens` cap too small for a thinking model yields an empty answer.
- The CPU backend may be built without Arm dot-product, i8mm and SVE kernels (the GCC 13.3 `GGML_NATIVE` probe fails silently per one runbook), making any CPU fallback for the summariser or embedder much slower than expected.
- Open upstream GB10 bug #27918 (32 GB CUDA VMM cap, hang on larger offloads) could hit any seat over 32 GB such as gpt-oss-120b; the recommended seats are all under 23 GB.
- The 2026 model architectures (qwen35, gemma4, granite, nemotron_h_moe, embeddinggemma-2) need a recent llama.cpp; the GX10's installed build is unknown and may not load them.
- Speed falls as context fills (30B MoE generation halves by 32k depth), so long debates with large retrieved passages slow down round by round.
- Sustained 5-10 minute full-load runs raise thermal risk; earlier research cited a GX10 owner reporting hard power-offs under heat.
- Bubble quality from a 3B model is untested; poor summaries would undercut the Table View even if speed is fine.

## Open questions
- Which SSD capacity does the GX10 have (1, 2 or 4 TB) and how much is free?
- Which llama.cpp build is installed on the GX10, and which DGX OS and kernel version is it running?
- On the real GX10, how long does the 5-seat council take to load cold with mmap, with `-lm dio`, and in parallel versus one at a time?
- What tok/s does one seat get while a second seat, or the summariser, is generating at the same time?
- What is the real per-seat overhead beyond weights and KV (CUDA context, compute buffers, checkpoints), measured from MemAvailable?
- Is the summariser faster for the debate on GPU or on CPU, and does the CPU build include the Arm extension kernels?
- How many rounds does a council typically need to reach 80%? This decides whether 5-7 rounds in 5 minutes is enough and depends on how the engine judges that answers match.
- Does the owner want the Llama and Phi names seated even though those models date from 2024, or prefer current models from OpenAI, IBM and NVIDIA?
- Should any seat be allowed to think briefly, accepting fewer rounds, or should all seats answer directly?
- Does quantising the KV cache actually free memory on the GB10? One runbook says it does not.
- What does `reasoning_effort: "none"` do for gpt-oss-20b on the pinned build?
- What are the real GB10 speeds for the models with no published figure: granite-4.2-8b and 30b, phi-4, gemma-4-12B, Nemotron-3.5-Lightning and Qwen3.5-2B?
- Is the Nemotron 3.5 Lightning licence acceptable to the owner for personal use?
- Are 3B-model bubble lines good enough on real debate text, or is a 4B model needed?

## Independent re-check (overrides the above)

- **C1a** [partly] Every figure is in the cited sources. Two caveats: the Gemma-4-26B-A4B Q4_K_M 49.6 tok/s is an Ollama run with q8_0 KV, a second GB10 Ollama measurement gives 40 tok/s, and no llama-bench result exists for that file; and all figures were taken with one model loaded (the hexdocs runbook saw about 10% loss with about 20 GB of other weights resident).
- **C1b** [refuted] 
- **C1d** [partly] 
- **C1e** [refuted] 
- **C2a** [partly] phi-4 is not Microsoft's newest Phi chat model: Phi-4-mini-instruct (2025-02-19, 3.84B, MIT, GGUF context 131,072, tools in template), Phi-4-reasoning (2025-04-09) and Phi-4-reasoning-vision-15B (2026-01-23) are newer; no Phi-5 exists. Ministral 3 dates from 2025-10-31, and Mistral's newer open weights are 119B or larger.
- **C2b** [confirmed] 
- **C2c** [partly] The 12 tok/s plain figure is measured on Qwen3.5-27B and Qwen3.6-27B, not on Qwen3.8-27B. For 3.8 only the MTP runs are measured: about 15 tok/s (UD-Q4_K_XL, --spec-draft-n-max 2) and 18.08 tok/s (ggml-org Q4_K_M with `-hfd ggml-org/Qwen3.8-27B-GGUF:Q4_0 --spec-default --spec-type draft-mtp`).
- **C2d** [confirmed] Sizes, licence, context and tools are right. Three precisions: the 26B-A4B speed is Ollama only (40 and 49.6 tok/s from two GB10 sources); Gemma 4 does not think unless enabled; and Google publishes an official QAT file, google/gemma-4-26B-A4B-it-qat-q4_0-gguf (14.44 GB), smaller than the 16.95 GB UD-Q4_K_M.
- **C2g** [partly] 
- **C2h** [partly] Details are right. A Phi option without the 16,384 limit exists: Phi-4-mini-instruct (3.84B, MIT, GGUF context 131,072, tools in template, no thinking, Q4_K_M 2.49 GB), though it is a small model.
- **C2i** [refuted] 
- **C2j** [partly] A GB10 llama.cpp figure exists for the predecessor with the same architecture (nemotron_h_moe): Nemotron 3 Nano 30B-A3B Q4_K_XL ran at 13.3-14.7 tok/s generation and 283-371 tok/s prompt reading (build b8399). Expect the Nemotron seat to be slow, not Qwen-MoE fast, until measured.
- **C2k** [partly] The Native/Generic list in function-calling.md is dated. Master builds parsers from each chat template with an autoparser (docs/autoparser.md) plus dedicated handlers such as GPT-OSS, and `--jinja` is now on by default; per-model tool behaviour still needs testing.
- **C3a** [confirmed] 
- **C3b** [partly] Arithmetic is right (117.7 GiB at 16k, 126.4 GiB at 32k). Two additions: a q8_0 KV cache (two GB10 sources report 2-7% speed loss) would bring the 32k case to about 117 GiB (my arithmetic), and a 16k window is too small for 7 seats beyond about 4 rounds.
- **C3c** [partly] 
- **C3d** [refuted] `--cache-ram 8192` is a ceiling that fills as prompts are cached, not memory taken at start. The same field notes say `--no-mmap` costs about +20 GB and the hexdocs runbook says direct I/O costs 3-4%, so the non-mmap advice must be measured on the GX10.
- **C4a** [partly] The arithmetic follows from the stated assumptions. It leaves out the gpt-oss-20b seat's reasoning tokens (that model has no off level), the per-round answer-matching call, the research query step, the summariser's GPU share and any slowdown from 60-75 GiB of other models being resident; treat the round times as 20-40% optimistic (my estimate).
- **C4b** [partly] The round counts ignore the context window. With the original's own assumptions (about 6k starting tokens, 330 tokens per turn) a 16,384 window fills after about 10 rounds at 3 seats, 6 at 5 seats and 4 at 7 seats (my arithmetic), so the 10-minute counts (27/16/11) and the 5-minute counts for 5 and 7 fast seats (7 and 5) are not reachable without history compaction or a larger window.
- **C4c** [refuted] Figures are right. Add that the 22 s result needs `--no-mmap` (with mmap the same 6.17.1 kernel took 1 min 30 s), kernel 6.14 took 27 s against 68 s on 6.11, and NVMe read-ahead 8192 cut no-mmap loading to about 15 s on 6.17.
- **C4d** [unverified] 
- **C5a** [partly] 
- **C5b** [unverified] 
- **C5c** [refuted] 
- **C6a** [partly] Scores, licence, dimensions and dates are as stated. The card says 8,192 context but the GGUF metadata reports context_length 262,144, and the model is 740M parameters in total (270M text plus vision and audio encoders); the text-only Q8_0 file is 0.31 GB.
- **C6b** [partly] 
- **C7a** [refuted] The figures are in the source, but that file does not name the runtime and quotes 101 tok/s raw generation, so it is probably vLLM rather than llama.cpp. Also Gemma 4 does not think unless enabled, while gpt-oss always reasons (levels low, medium and high only).
- **C7b** [confirmed] Flags and request fields are as stated on master (release b11552, 2026-10-10). One gap: the dedicated gpt-oss handler (common/parsers/gpt-oss.cpp) contains no enable_thinking branch, so `reasoning_effort: "none"` probably does not silence gpt-oss; it does set thinking start and end tags, so `reasoning_budget_tokens` is the lever to test for that seat.

### Objections to recommendations
- Thinking policy versus the default council: gpt-oss-20b is a default seat, but OpenAI's card offers only reasoning levels low, medium and high, and llama.cpp's gpt-oss handler has no enable_thinking branch. Put `Reasoning: low` in that seat's system prompt, test `reasoning_budget_tokens` on it, and budget extra tokens for it; the install-time probe must cover this case.
- 16k context per seat conflicts with the round estimates: every round adds about seats x 330 tokens to every seat's prompt, so a 16,384 window fills after about 6 rounds at 5 seats and 4 at 7 seats (my arithmetic from the original's assumptions). Context shift is off by default, so llama-server returns an exceed-context error; the engine needs a history compaction step (which forces a full prompt re-read) or 32k windows, and a phi-4 seat (hard 16,384 limit) fails first.
- "Fold the one-sentence answer into the end of each turn in a schema-constrained form" is not directly possible: `response_format` / `json_schema` constrains the whole reply. Either the whole turn becomes JSON (which complicates live streaming to bubbles and Chat View), or a custom GBNF grammar with a fixed tail line is used, or a second short request is made; the second request costs only about 40 generated tokens because the prefix is cached.
- `--cache-ram 0` with `-np 1` leaves each seat one cached context. Any side request with a different prompt (search-query JSON, learning-review vote, clerk draft, final write-up) overwrites it, and Qwen 3.5/3.6/3.8 and Gemma 4 then re-read the whole debate; keep side calls as continuations of the same conversation or send them elsewhere, and check cache reuse from the `timings` in each response.
- Load mode: sources disagree. llama.cpp's own Spark bench ran with mmap 0 and dio 1, the field notes say `--no-mmap` adds about 20 GB, and the hexdocs runbook says direct I/O costs 3-4%; `-lm` exists only on recent builds and the GX10's build is unknown. Decide by measurement, and note the read-ahead fix (`read_ahead_kb` 8192) needs sudo.
- 7 seats at 16k computes to 117.7 GiB against about 121 GiB of total memory, about 3 GiB of slack, and MemAvailable on a desktop DGX OS is below the total. Over-commit on GB10 ended in a global OOM kill that took avahi-daemon, which to a non-programmer looks like the machine vanishing from the network; treat 7 mid-size seats as not fitting until loads are measured, or use q8_0 KV and smaller extra seats.
- Keeping the last council loaded between debates holds 96-118 GiB permanently, which starves single-model chat, OCR and indexing and forces an unload before any seat change. llama-server has a built-in `--sleep-idle-seconds` that unloads after idle time and reloads on the next request; use that or a gateway idle timeout.
- Speed figures for the seat picker and the default council come from single-model runs. One GB10 runbook measured about 10% loss with 20 GB of unrelated weights resident, and the Gemma 4 26B figure ranges 40-49.6 tok/s under Ollama; the first-test script should measure each seat with the whole council loaded.
- Nemotron-3.5-Lightning as an optional "30B-class MoE seat": its predecessor with the same architecture measured 13-15 tok/s in llama.cpp on a Spark, and the licence is `other` (openmdw-1.1). Do not label it fast before measuring.
- Quantised KV was rejected on one runbook's statement that it frees no memory. A second GB10 report says q8_0 halves the KV cache for under 5% speed loss, while q4_0 collapsed prompt reading from 282.7 to 21.3 tok/s at 64K; so q8_0/q8_0 is a usable fix for 32k windows and q4_0 must never be offered.
- Router mode (the plan's open test) was not assessed. It offers per-model presets (`--models-preset` INI), `/models/load` and `/models/unload`, but `--models-max` defaults to 4 and would evict a seat in any council above 4 models including the summariser and embedder; open issue #28337 (wrong GGUF loaded when files share a subdirectory) affects models with mmproj or mtp companion files.
- Summariser cadence: at 55 tok/s a 330-token turn lasts about 6 s, shorter than the bubble's 8 s dwell, so a fast seat can show at most one or two summaries per turn (my inference). Run the summariser only for turns expected to last longer than about 8 s and use the first or last complete sentence otherwise; separate CUDA processes sharing the GPU is still unmeasured.
- Setup burden for a non-programmer: the recommendations need a pinned llama.cpp source build (apt packages, sudo), a udev rule for NVMe read-ahead (sudo), and possibly a GPU clock cap (sudo). Meta's repos are gated, so a Llama download from meta-llama fails without a Hugging Face token and licence acceptance; all of this belongs in a one-time setup script, not in the app's normal flow.
- Dense seat with MTP: the companion file is passed with `-md` / `--spec-draft-model` (or `-hfd`) plus `--spec-type draft-mtp`, on a recent build only. 18 tok/s still means about 18 s per 330-token turn, and the MTP run lost about 10% when other weights were resident.

### Missed by the first pass
- Thermal risk on the GX10 itself: an ASUS Ascent GX10 owner reproduced hard power-offs under full GPU load held for minutes (second back-to-back 200 s run died, peak 96 C on the ACPI zone while nvidia-smi read lower). The fix was `sudo nvidia-smi -pm 1 && sudo nvidia-smi -lgc 300,2200`, at about 25% longer run time; a 10-minute debate is the same load shape, so log /sys/class/thermal during a full 7-seat test (https://ai-muninn.com/en/blog/gx10-thermal-hard-poweroff).
- Load time depends on the kernel: the same 59 GiB file loaded in 68 s on 6.11, 27 s on 6.14 and 15-22 s on 6.17 with `--no-mmap`. Earlier research found DGX OS 7.5.0 lists kernel 6.17 but partner systems may update later, so read `uname -r` on the GX10 before sizing spool-up.
- Silent partial offload: on GB10 an Ollama load after another process had used memory came back at 16 tok/s instead of 40 because the memory estimator split layers to CPU without warning. The llama-server equivalent is `--fit on`; check the load log for all layers offloaded and surface it per seat.
- Open GB10 issues touching this area: #28917 (Gemma 4 26B loses end-of-sequence under 2 concurrent requests via Ollama, so keep one request at a time on that seat and always set max_tokens) and #27918 (loads over 32 GB hang with the default CUDA VMM pool, workaround GGML_CUDA_NO_VMM; matters only for gpt-oss-120b).
- Answer matching each round has a cost and an owner: deciding which one-sentence answers match needs a judge call or embedding comparison per round, which is not in the time estimates. With the 3B summariser as judge, the quality of that decision drives the 80% rule.
- More small-model candidates for the summariser: granite-4.2-3b (Q4_K_M 2.24 GB, Apache-2.0, thinks by default), Phi-4-mini-instruct (Q4_K_M 2.49 GB, MIT, no thinking) and gemma-3-4b-it-qat Q4_0, which llama.cpp's own Spark bench measured at 5,949 tok/s reading and 81.05 tok/s writing.
- Pick the final writer by speed: the write-up reserve depends on who writes. A 600-token answer takes about 9 s on Qwen3.6-35B-A3B but about 23 s on Ministral-3-14B (26.4 tok/s), so choose the fastest seat in the majority group (my inference).
- Qwen3.6-35B-A3B returns end-of-generation immediately on a raw completion prompt and only works through the chat template, per the hexdocs runbook. Use `/v1/chat/completions` for every seat, never `/completion` with hand-built prompts.
- llama.cpp is not the fastest stack on GB10 for some seats: the same harness measured vLLM at 54.9 tok/s (Gemma-4-26B NVFP4 + MTP) and 60.7 tok/s (gpt-oss-120b) against 49.6 and 42.1 under Ollama. This is context only, since the plan is llama.cpp and vLLM cold starts took about 4 minutes.
- The maintainer's August 2026 example uses `llama serve ...` rather than `llama-server`, which suggests a unified binary name on recent builds. I did not verify this beyond that comment; the launcher should detect the binary name instead of hardcoding it.
- Disk, from verified file sizes: the default 5 seats total 64.8 GB, the 7-seat set plus summariser and embedder 81.5 GB, and a 12-model library with the optional 27-31B models about 175 GB (my sum). Earlier research found the GX10 has one M.2 slot sold at 1, 2 or 4 TB, so 1 TB is enough if partial downloads and duplicate caches are cleaned up.
