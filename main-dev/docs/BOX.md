# Box runbook: ASUS GX10

Ubuntu 24.04, aarch64, Ollama 0.40.2, 121 GiB RAM. Scripts live in `tools/box/` (see `tools/box/README.md`).

## Facts measured on the box

- Code lives in `~/council/main-dev`. `tools/deploy.sh` copies it from the Windows machine. Code is never edited on the box.
- Box config is in `~/council/box/config`, made by `tools/box/make_config.py` and `tools/box/make_registry.py`. `COUNCIL_HOME=~/council/box`.
- Python env: `~/council/venv`.
- The shared system Ollama (port 11434) keeps only 3 models loaded. The council uses its own second instance on port 11435, started under the user account. It shares the model store `/usr/share/ollama/.ollama/models` and runs with `OLLAMA_MAX_LOADED_MODELS=8`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_KEEP_ALIVE=-1`.
- Real memory use is about 16% above what `ollama ps` reports.
- Models slow to roughly a third of their solo speed when six generate at once.
- Ollama refuses embeddings from chat models.
- The neuron tap is built with cmake in `~/council/tap-build` from `main-dev/tap`, against `~/llama.cpp` (read only). It reads Ollama blobs directly.

## 1. First-time setup

On Windows (from `main-dev`; the box login is `asus@100.103.186.3` unless `COUNCIL_BOX` says otherwise):

```
bash tools/deploy.sh
```

On the box:

```
mkdir -p ~/council/logs
bash ~/council/main-dev/tools/box/start_council_ollama.sh
cd ~/council/main-dev
python3 tools/box/make_config.py
python3 tools/box/make_registry.py
```

`make_registry.py` asks the 11435 Ollama what is installed, so start it first. Models that are not installed are left out of the registry.

Check:

```
export COUNCIL_HOME=~/council/box
~/council/venv/bin/python -m unittest discover -s tests 2>&1 | tail -3
```

The venv at `~/council/venv` must already exist; deploy never touches it. Any install into it needs the vulnerability check from the install policy first.

## 2. Daily loop

1. Edit on Windows. Run the unit tests there (mock mode).
2. Deploy: `bash tools/deploy.sh` (or `bash tools/deploy.sh --test` to also run the unit tests on the box).
3. On the box, make sure the council Ollama is up, then run:

```
bash ~/council/main-dev/tools/box/start_council_ollama.sh
cd ~/council/main-dev && export COUNCIL_HOME=~/council/box
~/council/venv/bin/python -m council.cli run "your question" --mode standard
```

Deploy leaves alone `~/council/box`, `~/council/venv`, and generated data (db, runs, correction datasets, benchmark results). Settings for deploy: `COUNCIL_BOX`, `COUNCIL_BOX_DIR`, `COUNCIL_BOX_PASS` (environment only).

CLI subcommands: `demo`, `run`, `build`, `bench`, `probe`, `train-probe`, `models pull-list`, `chronicle export`. Modes: `quick`, `standard`, `deep`. `build` needs `--workspace DIR` (and `--auto-delegate` to skip the plan pause).

## 3. Every tools/box script

| Script | What it does |
|---|---|
| `start_council_ollama.sh` | Starts the 11435 Ollama detached if it is not answering; log `~/council/logs/ollama-council.log`; prints version and loaded models. `stop` stops it. No sudo. |
| `make_config.py` | Copies the repo `config/council.toml` to `~/council/box/config/`, with mock off, `core_models = ["qwen35-9b"]`, `default_timeout_s = 420`, base URL port 11435, deadlines quick 180 s, standard 900 s, deep 2400 s. Driver comes from `COUNCIL_DRIVER` (see "Driver choice"). Also copies `lenses.json`. Prints the chosen driver. |
| `make_registry.py` | Writes `~/council/box/config/models.json` from a built-in list of known models, keeping those whose tag the 11435 Ollama has. When `~/council/box/model_checks.json` exists, each model gets its measured RAM (`ram_gib`), speed (`tps`), JSON result (`json_ok` becomes `structured_valid_rate` 1.0 or 0.0) and think result (`think_ok` false makes reasoning `none`). A model whose check failed (`ok` false) gets status `quarantined`: kept in the list, never seated. Prints the count, the labs and one note per measured value. |
| `check_models.py` | Loads each council model alone (the eleven in `COUNCIL_TAGS` that are installed), measures size, speed, JSON and think support. Writes `~/council/box/model_checks.json`. `--all` checks every installed model; `--tags a,b` checks exactly those tags. |
| `verify_models.py` | Walks the Ollama manifests, checks every blob of the council's models exists, has the right size and sha256. Prints one line per model, OK or BAD. `--all` checks every model in the store. |
| `full_test.sh` | The long end-to-end sequence (steps 3 to 9, below). |
| `build_test.sh` | Waits for `full_test.sh` to finish, then runs one real build in `/tmp/ws6`. |
| `sizes_test.sh` | Three questions at council sizes 2, 4 and 6 (see 4). |
| `stop_models.sh` | Stops every model server (see "Stopping models"). |
| `summarize_run.py` | Prints the latest run from `~/council/box/db/council.db`: event counts, lineup, failures, decision. |

## Driver choice

The models are served by llama.cpp: one `llama-server` per model, loading the GGUF blob that Ollama downloaded. Ollama is only the downloader. The Ollama driver stays in the code as a fallback. `make_config.py` picks the driver from the environment variable `COUNCIL_DRIVER`:

```
python3 tools/box/make_config.py                       # llamacpp (default)
COUNCIL_DRIVER=ollama python3 tools/box/make_config.py # fallback: Ollama serves the models
```

For `llamacpp` it also sets `[llamacpp]` in the box config: `server_bin` (`~/llama.cpp/build/bin/llama-server`, written as an absolute path), `ctx = 8192`, `ollama_models_dir = "/usr/share/ollama/.ollama/models"`. If a key or the whole section is missing from the repo default, it is added. Any other value of `COUNCIL_DRIVER` stops the script. The script prints `driver: <name>`. Rerun it after switching, then start a run.

## Stopping models

```
bash ~/council/main-dev/tools/box/stop_models.sh
```

Kills leftover council `llama-server` processes (`pkill -f "[l]lama-server.*--port 181"`) and unloads every loaded model from both Ollama instances (ports 11434 and 11435) with `keep_alive` 0. Run it after a crashed or killed run, and before a test that needs the memory. It does not stop the Ollama processes themselves (`start_council_ollama.sh stop` does).

## 4. Running the tests

Unit tests (box or Windows):

```
cd ~/council/main-dev && ~/council/venv/bin/python -m unittest discover -s tests
```

Full test (long; run it in tmux):

```
tmux new -s full
bash ~/council/main-dev/tools/box/full_test.sh 2>&1 | tee /tmp/full.log
```

Steps: easy question, contested question, real build, second run in the same workspace plus chronicle export, benchmark of 12 tasks, API server with live stream. Logs: `/tmp/s3.log`, `/tmp/s4.log`, `/tmp/s6.log`, `/tmp/s7.log`, `/tmp/s8.log`, `/tmp/s9-server.log`, `/tmp/s9-events.log`. The script calls `/tmp/sum.py` to summarize each step; copy it first: `cp ~/council/main-dev/tools/box/summarize_run.py /tmp/sum.py`.

Build test (one real build; log `/tmp/s6.log`, workspace `/tmp/ws6`; it waits if `full_test.sh` is running so the two do not share the GPU):

```
bash ~/council/main-dev/tools/box/build_test.sh
```

Sizes test (three questions, three council sizes; sequential, a failed run does not stop the next):

```
bash ~/council/main-dev/tools/box/sizes_test.sh 2>&1 | tee /tmp/sizes.log
```

| Size | Question |
|---|---|
| 2 | Is 0.1 + 0.2 == 0.3 in Python? Answer yes or no and explain in two sentences. |
| 4 | A startup must choose one: PostgreSQL or MongoDB for a new billing system. Give one recommendation. |
| 6 | Should a team of five rewrite a working 80,000-line Python 2 codebase in Python 3 incrementally or all at once? Give one recommendation. |

Each runs `python -m council.cli run "<q>" --k N --mode standard` with `COUNCIL_HOME=~/council/box`. Output goes to `/tmp/size2.log`, `/tmp/size4.log`, `/tmp/size6.log`, with the `summarize_run.py` summary appended. The script prints exit code and elapsed seconds per run.

Model file check (council models only; reads every model file, slow, mostly disk; add `--all` for every model in the store):

```
~/council/venv/bin/python ~/council/main-dev/tools/box/verify_models.py
```

Run summary after any run: `~/council/venv/bin/python ~/council/main-dev/tools/box/summarize_run.py` (needs `COUNCIL_HOME`-style db at `~/council/box/db`).

## 5. Adding a newly pulled model

Pull in tmux (large downloads). Pull through the council instance so it sees the model:

```
tmux new -s pull
OLLAMA_HOST=127.0.0.1:11435 ollama pull <tag>
```

Then add the tag to the list `L` in `tools/box/make_registry.py` on Windows (id, tag, display, lab, lineage, params, expected RAM, speed, reasoning style, roles, priors), deploy, and rerun on the box:

```
python3 ~/council/main-dev/tools/box/make_registry.py
```

Models not in that list are not registered. Run `verify_models.py` after big pulls. Onboarding probes (`council.cli probe --model ID`) fill in measured values.

## 6. The neuron tap

`tap/actdump.cpp` reads prompts, runs them through a GGUF model, and writes the hidden state of chosen layers. Ollama blobs are plain GGUF files.

Build:

```
mkdir -p ~/council/tap-build && cd ~/council/tap-build
cmake ~/council/main-dev/tap -DGGML_CUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc
cmake --build . --target actdump -j8
```

`~/llama.cpp` is the default source path (`LLAMA_CPP_DIR`) and is not modified.

Smoke test (finds the blob of a model from its manifest, one prompt, one layer):

```
M=/usr/share/ollama/.ollama/models
BLOB=$(python3 -c "import json,sys;m=json.load(open(sys.argv[1]));print([l['digest'] for l in m['layers'] if l['mediaType'].endswith('image.model')][0].replace(':','-'))" $M/manifests/registry.ollama.ai/library/qwen3.5/9b-q8_0)
echo '{"id":"t1","text":"hello"}' | ~/council/tap-build/actdump -m $M/blobs/$BLOB --layers 8 | cut -c1-200
```

(Use any installed model's manifest path: `<library>/<name>/<tag>`.)

Output: one JSON line per input: `id`, `n_tokens` (prompt length), `n_embd` (width of the hidden state), and `layers`: for each requested layer a list of `n_embd` floats, the residual stream after that block, taken at the last token (`--pool mean` averages over tokens). Options: `--layers 8,12,16|all`, `-ngl N` (default 99), `-c CTX` (default 4096), `--info` (model info only). Errors go to stderr: `cannot load model`, `cannot create context`, `bad input line`.

## 7. Troubleshooting

**Model will not load.** Is the council Ollama up? `bash tools/box/start_council_ollama.sh`. Then read `~/council/logs/ollama-council.log`. Check free memory with `free -g` (remember real use is about 16% above `ollama ps`). If numbers say it fits but the load fails, the page cache may look like used memory: `sync; echo 3 | sudo tee /proc/sys/vm/drop_caches` (this one needs sudo, and the architecture doc says retry once). Run `verify_models.py` if the file may be damaged.

**Only N seats chosen.** The router only picks from models in `~/council/box/config/models.json`. Rerun `make_registry.py`; check the printed count. A model that is not pulled into the 11435 store, or whose tag differs, is left out. Also check the `summarize_run.py` lineup line.

**Turns timing out.** Six models generating at once run at about a third of solo speed. Deadlines in the box config are already long (180/900/2400 s); raise `default_timeout_s` or deadlines in `~/council/box/config/council.toml` (edit on the box only for this generated file, or change `make_config.py` on Windows and rerun it). Try `--mode quick` first.

**Memory pressure.** `free -g`, `ollama ps` (add `OLLAMA_HOST=127.0.0.1:11435`), `swapon --show`. Rising swap means trouble: stop the instance (`start_council_ollama.sh stop`) to unload everything, start again. Do not run two long tests at once.

**A stuck run.** Look at the tail of the log in `/tmp/s*.log`, then `~/council/venv/bin/python ~/council/main-dev/tools/box/summarize_run.py`. Then `pgrep -af council.cli`, and `kill <pid>`. If the model server looks hung, stop and restart the 11435 Ollama.

**Embeddings fail.** Ollama refuses embeddings from chat models. That is expected; use an embedding model.

## 8. Remove everything

```
bash ~/council/main-dev/tools/box/start_council_ollama.sh stop
rm -rf ~/council
```

That deletes the code, config, venv, database, logs and the tap build. It does not touch the shared model store or the system Ollama on 11434. `~/llama.cpp` was only read; remove it separately if you want. Temp files: `rm -rf /tmp/ws6 /tmp/s*.log /tmp/full.log /tmp/sum.py`.

## 9. Version 1.5: llama.cpp serving, steering, memory plan (appended 2026-10-11)

Sections 1 to 8 above were written for the Ollama path. In 1.5 the models are served by llama.cpp and Ollama is only the downloader. Status of each part is in `docs/V15.md`. Almost all of it is mock-proven only; the first real run on the box is still to do.

**Serving with llama.cpp.**

- `python3 tools/box/make_config.py` writes `driver = "llamacpp"` by default. `COUNCIL_DRIVER=ollama python3 tools/box/make_config.py` writes the fallback instead. Rerun it after a change, then restart the server.
- With `llamacpp` the council starts one `llama-server` per model, on ports `18100 + n`, using `~/llama.cpp/build/bin/llama-server` and the GGUF blob in the Ollama store (`/usr/share/ollama/.ollama/models`). Ollama downloads the models and `make_registry.py` asks the 11435 instance what is installed, so keep using it for those. It no longer serves the council's chat models. Whether anything else (for example the embedder) still needs it to be up is not checked yet.
- The command line of each child is in `docs/ARCHITECTURE.md` 6.1. Settings are in the `[llamacpp]` block (`ctx`, `parallel`, `base_port`, `extra_args`).
- Memory: llama-server holds one copy of each model. Do not run `actdump`, the steering experiment or the Ollama instance with the same models loaded at the same time as a six-seat run; the memory plan (ARCHITECTURE 29) counts only the council's own servers.
- Child output goes nowhere unless the driver is given a log directory, and the box config does not set one yet. If a model does not start, copy its command line and run it by hand to see the error. A port already in use makes the load fail with "port already in use"; find the old process with `pgrep -af llama-server` and stop it.

**Steering experiment** (the one proven on the box):

```
python3 ~/council/main-dev/tools/box/steer_test.py --tag granite4.1:8b-q8_0
```

It needs `~/council/tap-build/actdump` and `~/llama.cpp/build/bin/llama-server`, and writes `~/council/box/steer_test.json`. Options: `--layers 14-26`, `--scales -1,0.5,1,2`, `--concepts french,terse,camel`, `--port`. It starts and stops a server several times per rule, so it takes a while and uses the memory of one model plus the activation copy. Run it with nothing else loaded.

**Other 1.5 box scripts** (see `tools/box/README.md`): `check_models.py` (size, speed, JSON and think support per model, writes `model_checks.json` that the memory plan reads), `train_probes.sh` (probes for all 11 models, `tools/box/V15_PROBES.md`), `specdec_bench.py` (speculative decoding pairs), `v15_test.sh`.

**Install rule.** Building `llama.cpp`, `actdump` or anything else on the box, and any download, needs the vulnerability and supply-chain check from the global install policy first.
