# Setting up Council on a new machine

This is the path from an empty Linux machine to the app answering a question. It was written from
the one machine the project ran on (an ASUS Ascent GX10, NVIDIA GB10, 121 GiB of memory shared by
CPU and GPU, Ubuntu 24.04 on aarch64). **It has not been run from scratch on a second machine**, so
expect to adjust a path or two.

## What you need

| Thing | Version used | Why |
|---|---|---|
| Linux with an NVIDIA GPU and CUDA | CUDA 13.0 | every model runs on the GPU |
| Memory | about 15 GiB per seated model | 3 seats need about 50 GiB, 6 seats about 100 GiB |
| Disk | about 90 GB | the eight recommended model files (less if you use your own) |
| Python | 3.12 | the backend |
| Node.js | 24 | building the UI |
| Ollama | 0.40.2 | **downloading** the models only |
| llama.cpp | commit `b97ebdc` (2026-05-01), built with CUDA | **serving** the models, and reading their internals |
| cmake and a C++17 compiler | | building the activation tool |

## Layout

The scripts expect this layout. The source folder is only read; everything made while running sits
beside it. Set `COUNCIL_BASE` to use a folder other than `~/council`.

```
~/council/
  main-dev/        this repository
  venv/            Python packages
  node_modules/    UI packages
  ui-dist/         the built UI page
  box/             config, database, trained probes in use
  tap-build/       the compiled activation tool
  logs/
~/llama.cpp/       llama.cpp source and its build/
```

## Steps

1. **Put the repository at `~/council/main-dev`.**

2. **Have some models in Ollama.** Council works with whatever chat models Ollama has downloaded:
   it seats 2 to 6 of them per question and the router picks which. At least 2 are needed. See
   "Models" below. To get the eight we recommend (about 82 GB):
   ```
   bash ~/council/main-dev/tools/box/pull_models.sh
   ```
   Models you already pulled with `ollama pull` are found without doing anything.

3. **Build llama.cpp** with CUDA in `~/llama.cpp`, so that `~/llama.cpp/build/bin/llama-server`
   exists. Follow llama.cpp's own build instructions.

4. **Build the activation tool** (the lie detector reads model internals with it):
   ```
   mkdir -p ~/council/tap-build && cd ~/council/tap-build
   cmake ~/council/main-dev/tap -DGGML_CUDA=ON
   cmake --build . --target actdump -j8
   ```

5. **Python packages** (four, pinned in `requirements.txt`):
   ```
   python3 -m venv ~/council/venv
   ~/council/venv/bin/pip install -r ~/council/main-dev/requirements.txt
   ```

6. **Write the machine's config and model list:**
   ```
   cd ~/council/main-dev
   COUNCIL_DRIVER=llamacpp COUNCIL_PROTOCOL=open python3 tools/box/make_config.py
   COUNCIL_DRIVER=llamacpp python3 tools/box/make_registry.py
   ```
   `make_registry.py` reads Ollama's store, writes one entry per model it finds and prints what it
   found, what it will not seat and why. Run it again after you pull or remove a model.
   `COUNCIL_ONLY_RECOMMENDED=1` keeps only the eight recommended models.
   Optional: `python3 tools/box/llamacpp_check.py` loads each model once under llama.cpp and
   records which ones work; `make_registry.py` then does not seat any that do not.

7. **Start the app** (the first start installs the UI's pinned packages and builds the page):
   ```
   bash tools/box/run_app.sh
   ```
   Then open `http://127.0.0.1:4173`. `bash tools/box/run_app.sh stop` stops it.

## Models

Council works with whatever chat models Ollama has downloaded: it seats 2 to 6 of them per question
and the router picks which. These eight are the ones we recommend and tuned for on the ASUS machine;
when they are installed the router prefers them:

`gpt-oss:20b`, `qwen3.5:9b-q8_0`, `qwen3:14b`, `phi4:14b`, `granite4.1:8b-q8_0`, `deepseek-r1:14b`,
`falcon3:10b-instruct-q8_0`, `gemma4:12b-it-q8_0`.

Each model belongs to its maker and comes under that maker's licence.

To see what Council finds on a machine, and what it can seat:

```
python -m council.cli models
```

It reads Ollama's store (`$OLLAMA_MODELS`, else `/usr/share/ollama/.ollama/models`, else
`~/.ollama/models`) and falls back to `ollama list`. Ollama does not have to be running.

How a model that is not one of the eight is treated: its maker, size and thinking style are guessed
from its name; its memory need is estimated from its file size (file size x 1.25 + 1.5 GiB); its
speed is unknown; and its starting skill scores are set a little lower (0.52 against 0.60 or more),
which is the whole of the preference for the eight. The scores then move with the results of real
runs like any other model's.

Limits:

- Only models plain llama.cpp can load. Vision models packed the Ollama way, embedding models and
  Ollama cloud models are skipped automatically; Mistral Small 3.2, Ministral 3 and Phi-4 Reasoning are known not to run and
  are listed but not seated.
- Models other than the eight have **not** been tested by us. The guesses above can be wrong.
- The lie-detector probes exist only for the eight (train more with `tools/box/train_probes.sh`).
- A model must fit in memory next to the others. One that is larger than the machine's memory is
  not seated.
- At most two models of one maker sit in the same council, so six seats need models from at least
  three makers. With fewer, the council is smaller.

## The lie-detector probes

`probes/` holds one trained probe per model. They were trained on these exact model files, so they
are only valid for the same Ollama tags. `run_app.sh` copies them into `~/council/box/probes` on a
fresh machine. To train them again on your own machine (about 3 minutes per model):

```
bash tools/box/train_probes.sh
```

## Checking it works

- `python -m unittest discover -s tests` from `main-dev` runs the backend tests. They use canned
  replies and need no GPU.
- `curl http://127.0.0.1:8765/ui/health` should answer with a name like `"Council (8 models)"`.
- `python3 tools/box/watch_run.py` prints the newest debate: every message, note and vote.

## Known limits

- See "Limits" under "Models" for what applies to models other than the recommended eight.
- The app window is started with Electron's sandbox off (`--no-sandbox`).
- Each lie-detector reading loads a second copy of that member's model, which makes it slow.
