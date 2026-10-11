# Syndicate

**High-quality AI answers without paying for a frontier model, and without your data ever leaving the building.**

Syndicate runs a group of small and medium open models on one local machine, the **ASUS Ascent GX10**. Instead of
trusting a single model, it has several models from different labs answer the same question and debate until they
agree, and a lie detector checks their claims so hallucinations are caught before they reach the answer. Built for
the GX10 hackathon.

## The problem

- **Frontier models are expensive.** Many people and teams want high-quality AI output but cannot afford the
  continuous cost of a big frontier model.
- **Many cannot use the cloud at all.** Companies with sensitive data are often legally barred from letting it leave
  their own network, so even enterprise zero-data-retention (ZDR) contracts are not an option.
- **One local model is not enough.** A single small or medium model running locally has blind spots on specific kinds
  of tasks, and sometimes reasons its way to a wrong answer.

## Our answer

- **A council instead of one model.** Several small and medium models from different labs, each with different
  strengths and weaknesses, answer the same question on their own, then debate it until they agree. One model's gap
  or faulty reasoning gets caught by the others.
- **A lie detector against hallucinations.** Every claim in every answer gets a truth score, built from how the model
  behaves (hedging, how consistent its answers are), its track record, and, once trained for that model, a probe that
  reads the model's internal activations. Claims that look false are flagged to the council before it decides.
- **Fully local and private.** Everything runs on one machine; its 121 GiB of memory holds several models at once.
  No cloud, no per-token bill, nothing leaves the building, so the council can afford to think hard about every
  question.

The benchmark (`council.cli bench` and `compare`) checks the claim honestly: the council against each member
answering alone, against the biggest single model, and against simpler setups such as a plain vote with no debate.
See `docs/ARCHITECTURE.md` section 1.3.

## How a run works

1. **Profile.** The task is described: what kind of task, how hard, what it needs.
2. **Convene.** A router picks 2 to 6 models (the "seats") whose strengths fit this task, and loads them.
3. **Blind drafts.** Every seat answers alone.
4. **Lie check.** The lie detector scores each claim in the drafts and flags the ones that look false. A seat whose
   answer stands out from the rest can be cross-examined.
5. **Debate.** Seats review each other's drafts with names removed, test claims that can be checked (run the code,
   compute the number), and vote.
6. **Decision.** The council agrees when 80% of the seats back the same answer. If time runs out first, a majority
   wins, or a chair model decides, or the council asks you. The losing view is always kept as a minority report.
7. **Delegate** (build tasks). The plan becomes small jobs that worker models do in parallel. Each result is checked
   by structure, then by the task's own test commands, then by a model if nothing else can check it.
8. **Review.** The council looks at the work and accepts it, asks for fixes, or replans. Accepted work is copied into
   your folder.
9. **Remember.** A small panel decides what the run taught it and writes that to the Chronicle, with evidence.
   Nothing is remembered just because you said it once.

Every step emits events. The app, the command line and the benchmark all watch the same event stream.

## Quick start

All commands run from `main-dev/`.

### Try it without a GPU (mock mode)

`config/council.toml` ships with `[gateway] mock = true`: scripted answers, no model server needed.

```
python -m unittest discover -s tests                        # the test suite (standard-library unittest)
python -m council.cli demo                                  # replay a scripted run
python -m council.cli run "Is 0.1 + 0.2 == 0.3 in Python?"  # a question through the full engine
python -m council.api.server                                # API on http://127.0.0.1:8765
curl http://127.0.0.1:8765/health                           # {"ok":true,"mock":true,"driver":"mock"}
```

### Run it for real on the box

First time only (see `docs/BOX.md` section 1):

```
mkdir -p ~/council/logs
bash ~/council/main-dev/tools/box/start_council_ollama.sh   # the council's own Ollama, port 11435
cd ~/council/main-dev
python3 tools/box/make_config.py                             # writes ~/council/box/config/council.toml (real mode)
python3 tools/box/make_registry.py                           # writes ~/council/box/config/models.json
```

Every day:

```
bash ~/council/main-dev/tools/box/start_council_ollama.sh
cd ~/council/main-dev && export COUNCIL_HOME=~/council/box
~/council/venv/bin/python -m council.cli run "your question" --mode standard --k 4
~/council/venv/bin/python -m council.cli build "add a CLI flag" --workspace ~/myproject
```

### The app (backend and window)

```
bash ~/council/main-dev/tools/box/run_app.sh          # backend on :8765 and the UI on :4173
bash ~/council/main-dev/tools/box/run_app.sh --no-ui  # backend only
bash ~/council/main-dev/tools/box/run_app.sh stop     # stop both
```

Open http://127.0.0.1:4173 (add `?mock` to use the built-in stand-in instead of the backend). From another computer:
`ssh -L 4173:127.0.0.1:4173 -L 8765:127.0.0.1:8765 asus@<box>`, then open the same address locally. Details in
`docs/RUN_APP.md`.

## Command line

`python -m council.cli <command>`:

| Command | What it does |
|---|---|
| `run "<task>"` | Ask the council a question. `--mode quick\|standard\|deep`, `--k 2..6` seats. |
| `build "<task>" --workspace DIR` | Plan, delegate, check and write a deliverable into `DIR`. `--auto-delegate` skips the plan pause. |
| `demo` | Replay the scripted demo run. |
| `bench` | Run the benchmark and print a markdown report (`--modes`, `--split`, `--limit`, `--fast`). |
| `compare --solo FILE --council DIR` | Compare the council with each model answering alone. |
| `summary`, `lies` | Plain-text summary, or the lie-detector report, of a stored run. |
| `cards`, `memory` | One card per registered model; the memory plan for the largest models. |
| `probe`, `train-probe --model ID` | Onboarding checks for a model; train its truth probe. |
| `steer --project DIR --model ID --rule "..."` | Train a steering vector that nudges a model toward a project rule. |
| `chronicle export` | Print what the council remembers, as markdown. |
| `models pull-list` | Print one `ollama pull` line per registered model. |

## The models on the box

From `~/council/box/config/models.json`. A run seats 2 to 6 of them. "Quarantined" means the model failed one of the
box checks (speed, JSON output or reasoning control in `tools/box/check_models.py`) and is not seated.

| Model | Lab | Roles | Status |
|---|---|---|---|
| gemma4:12b-it-q8_0 | Google | seat | active |
| gpt-oss:20b | OpenAI | seat, planner | active |
| qwen3.5:9b-q8_0 | Alibaba | seat, worker, clerk | active |
| phi4:14b | Microsoft | seat | active |
| granite4.1:8b-q8_0 | IBM | seat | active |
| qwen3:14b | Alibaba | seat, senior worker | active |
| deepseek-r1:14b | DeepSeek | seat | active |
| falcon3:10b-instruct-q8_0 | TII | seat | active |
| ministral-3:14b | Mistral | seat | quarantined |
| phi4-reasoning:plus | Microsoft | seat | quarantined |
| mistral-small3.2:24b | Mistral | seat | quarantined |

Ollama downloads the model files. In version 1.5 each model is served by its own `llama.cpp` `llama-server` process
loading that file; the Ollama driver stays as a fallback (`[host] driver` in the config).

## What is in this folder

| Path | What it is |
|---|---|
| `council/core/` | The shared contract (`schemas.py`, `schemas_v15.py`, `event_types.py`), event bus, SQLite store, config. |
| `council/host/` | Starts, stops and supervises model servers; memory budget and memory plan; model probes. |
| `council/gateway/` | The only code that talks to a model: queueing, structured output, reasoning control, cache, mock. |
| `council/router/` | Turns a task into a profile and picks the lineup of seats. |
| `council/chamber/` | The deliberation engine: drafts, clustering, cruxes, votes, consensus, chair, tribunal. |
| `council/works/` | Foreman, workers, inspector, sandbox and staged workspace for build tasks. |
| `council/chronicle/` | Long-term memory: recall, reflection, rules of evidence. |
| `council/probe/` | The lie detector: claim scores from a hidden-state probe, behaviour signals and track record. |
| `council/steer/` | Steering vectors for per-project adaptation. |
| `council/bench/` | Benchmark runner, graders, reports, council-vs-solo comparison. |
| `council/api/` | FastAPI server (REST plus a server-sent event stream) and the run controller. |
| `council/cli.py` | The command line above. |
| `config/` | `council.toml` (all settings), `models.json` (model registry), `lenses.json` (reasoning stances). |
| `tests/` | One `test_<module>.py` per module, standard-library `unittest` only, all in mock mode. |
| `docs/` | Spec, runbooks and guides (below). |
| `tools/box/` | Scripts for the GX10: start, check, test and stop models; run the app. See `tools/box/README.md`. |
| `tools/deploy.sh` | Copies `main-dev/` from the development machine to the box. |
| `tap/` | `actdump.cpp`, the "neuron tap" that reads a model's hidden activations through llama.cpp. |
| `ui_partner/` | The GX10 Council desktop app (React + Electron) that `run_app.sh` serves. |
| `ui/` | The first Electron + React UI, built directly against the API. |
| `bench/`, `runs/`, `db/`, `adapters/` | Generated on the box: benchmark results, run data, the database, steering vectors. |

## Documentation

| Document | Read it for |
|---|---|
| `docs/ARCHITECTURE.md` | The full spec. Where it and the code disagree, the code wins. |
| `docs/V15.md` | What version 1.5 added, and what is proven on the box versus only in mock mode. |
| `docs/BOX.md` | The box runbook: setup, daily loop, tests, adding a model, troubleshooting. |
| `docs/RUN_APP.md` | Starting the backend and the app, and viewing it from another computer. |
| `docs/API.md` | Every API route and event, for anyone building a UI. |
| `docs/LIE_DETECTOR.md` | The lie detector in plain words. |

## Status (2026-10-11, version 1.5)

**Proven on the box:** version 1.0 end to end through Ollama (questions, builds, memory, benchmark, API), and the
steering experiment on Granite 4.1 8B (`tools/box/steer_test.py`).

**Proven in mock mode only** (the code runs and the tests pass, but no real numbers yet): the llama.cpp driver running
a full council, the lie-detector probes, the memory plan, speculative decoding, real runs at every council size, and
the council-versus-solo comparison. `docs/V15.md` lists each one and the box run that will prove it. Until a model's
probe is trained and passes its checks, the lie detector scores claims from behaviour signals and track record only,
and says so in its report (`docs/LIE_DETECTOR.md`).

## Working on the code

- Edit on the development machine and deploy with `bash tools/deploy.sh` (`--test` also runs the tests on the box).
  Do not edit code on the box. Deploy never touches `~/council/box`, `~/council/venv` or generated data.
- Python 3.12. The only third-party packages are `pydantic`, `httpx`, `fastapi` and `uvicorn` (`requirements.txt`).
  Nothing else gets installed without a supply-chain check (`docs/ARCHITECTURE.md` section 3.4).
- Only `council/gateway/` talks to a model, and only `council/host/` starts or stops one.
- `chamber/deliberation.py`, `chamber/consensus.py`, `router/scoring.py`, `works/scheduler.py` and `chronicle/rules.py`
  stay pure: no I/O, no clock, no randomness except an injected seed.
- Every test runs in mock mode with no GPU. Run one module with `python -m unittest tests.test_<module> -v`.
- Coding agents: read `CLAUDE.md` in the parent folder first.
