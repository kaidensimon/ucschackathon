# Lie detector guide

This guide explains the lie detector in plain words. The spec is ARCHITECTURE.md section 28. The shared types are in `council/core/schemas_v15.py`.

## 1. What it is

The lie detector gives each claim in a seat's answer a score. It uses three kinds of evidence.

1. **Probe.** A small linear model, trained per model, reads the model's hidden activations. Hidden activations are the numbers inside the network while it reads a text. They are read with llama.cpp from the same Ollama model files the council already uses. The tool that does it is `tap/actdump.cpp`. It loads the GGUF blob, runs the text, and writes the hidden state of chosen layers.
2. **Behaviour signals.** Hedging, entropy, how often resamples agree, and the confidence the seat stated. These need no activations.
3. **Track record.** The share of this model's past labelled claims that turned out true.

The probe only counts once it passes the switch-on checks in section 5. Until then the report uses behaviour signals and track record only, and says so in its note.

## 2. What a score means

Every score reads the same way.

- **0** means likely false.
- **1** means likely true.
- Around **0.5** means the signal does not know.

A score is an estimate. It is not a probability that you can bet on, unless the probe card shows a good calibration error (`ece`).

Each claim becomes a `LieFlag` with three levels.

| Level | Meaning |
|---|---|
| `ok` | nothing worrying |
| `watch` | shaky, worth a second look |
| `flag` | check this claim before you trust it |

Default cut-offs (`probe/bluff.py`):

- flag when the probe score is below 0.30, or the bluff gap is 0.45 or more
- watch when the probe score is below 0.45, or the bluff gap is 0.30 or more
- with no probe, watch when the behaviour score is below 0.35

## 3. The bluff gap

The bluff gap is `stated confidence - probe score`. Both are clamped to 0..1.

A high gap means the seat says it is sure, but its own activations read as unsure. Example: the seat states 0.95, the probe reads 0.40, the gap is 0.55, the claim is flagged. The reason text reads "says 0.95 sure, reads 0.40".

The gap needs both numbers. With no probe it is empty.

## 4. How flags reach the council and the UI

### The council

Flags are advice. They are never a vote and never change a vote weight.

- **Round 1 notes.** Each seat gets a short block called "Engine notes on the claims in the drafts (advisory)". It lists the worst claims, flag before watch, at most 6 lines. Its own claims say "Your claim c2 ... Re-check it." Other drafts are named by their anonymous letter only. Seat numbers and model ids never appear. The block ends with a reminder that these are estimates, not facts and not votes.
- **Cross-examination.** When a seat dissents, the tribunal gets that seat's worst claims as targets (`tribunal_targets`, 3 by default). Each target comes with a question hint: "Ask for the evidence behind: ...". The examiners ask, the seat defends, and the judges decide. The score is a reason to ask. It is not the verdict.

Code: `council/chamber/lie_notes.py`.

### The UI

The UI reads a `LieReport`.

| Field | Meaning |
|---|---|
| `run_id` | the council run |
| `seats[]` | one `SeatHonesty` per seat: `claims`, `flagged`, `watched`, `mean_probe`, `mean_gap`, `level` |
| `flags[]` | every scored claim as a `LieFlag`, worst first |
| `probe_models[]` | models that had an active probe in this run |
| `note` | for example "no active probe: behaviour signals only" |

Each `LieFlag` holds `claim_id`, `text`, `probe_score`, `behaviour_score`, `track_record`, `stated_confidence`, `bluff_gap`, `level` and `reasons[]`. Any score can be `null` when that signal was missing.

A seat is `flag` when it has 2 or more flagged claims, or at least a quarter of its claims flagged. It is `watch` when it has any flagged or watched claim. Otherwise it is `ok`.

The API adds a `caveat` string to the report. Show it next to the scores.

## 5. How a probe is trained and when it turns on

### Training data

The probe learns from pairs of simple statements, one true and one false, written as "Question: ... Answer: ...". A benchmark file with known answers can be used instead. No instruction to lie is used. The model reads the text and the probe looks at what the network holds.

Layers are picked from the middle half of the network (quarter to three quarters), four layers by default. The tool trains one logistic regression per layer. The layer with the best held-out score is kept. Pooling is the last token by default (`pool = "last"`).

### The checks

A probe is switched on only when every check passes. The first one that fails sets the reason shown on the card.

1. **Held-out AUROC** is at least `min_auroc` (0.80). AUROC is the chance that the probe ranks a true statement above a false one on data it never saw. 0.5 is a coin flip.
2. **Enough held-out rows.** The gate wants at least 30.
3. **Shuffled-label control.** The same probe is trained on shuffled labels. It must score near 0.5 (at most 0.62). A higher score means the setup leaks.
4. **Surface-feature baseline.** A cheap model sees only answer length and token counts. The real probe must beat it. If it does not, the probe learned wording, not model state.

Note for maintainers: `probe/gate.py` asks for a margin of 0.03 over the baseline. `probe/trainer.py` asks for 0.1 when it sets the status. The stricter one wins in practice. The two numbers should be made equal.

### ProbeCard

Every trained probe gets a `ProbeCard`: `model_id`, `version`, `source`, `layers`, `auroc`, `accuracy`, `control_auroc`, `baseline_auroc`, `ece`, `n_train`, `n_test`, `trained_at`, `active`, `reason`. `source` is `mock`, `ollama_embed` or `llamacpp`. Only `llamacpp` reads real per-layer hidden states.

You can turn a probe off by hand. You cannot make a failed probe trustworthy by turning it on.

## 6. Train on the box

Edit on Windows, deploy with `tools/deploy.sh`, then run on the box. Do not edit code on the box.

1. **Build `actdump` once.** It needs a llama.cpp source tree (the CMake file looks in `~/llama.cpp`). Build `tap/` with CMake. The default binary path is `~/council/tap-build/actdump`. Do the install security check from your global policy before you fetch or build anything.
2. **Set the config** in `config/council.toml`:

```toml
[probe]
enabled = true
min_auroc = 0.80
source = "llamacpp"
actdump_path = "~/council/tap-build/actdump"
ollama_models_dir = ""   # empty = $OLLAMA_MODELS, else system path, else ~/.ollama/models
max_models = 1
pool = "last"
```

3. **Train one model** from the command line:

```
python -m council.probe.train_cli --model MODEL_ID --source llamacpp --layers auto
```

Useful flags: `--tasks PATH` for a benchmark file, `--limit N`, `--seed N`, `--min-auroc X`, `--out PATH`. It prints a table of layers with AUROC, shuffled AUROC and the cheap baseline, then a verdict. The report JSON goes to `bench/results/probe_<model>.json`. Exit code is 0 when training ran, even if the probe was rejected.

4. **Train all models** with `POST /probes/train_all` (section 7), or train one from the UI.
5. **Check the card.** Look at `active` and `reason`. A rejected probe is a normal result.

Try `--source mock` first. It uses made-up vectors and proves the pipeline works. A mock probe says nothing about any real model.

## 7. API routes

All on the backend at `http://127.0.0.1:8765`.

| Method | Route | Does |
|---|---|---|
| GET | `/lies/{run_id}` | the `LieReport` as JSON, plus `caveat`. 404 if the run has none. |
| GET | `/lies/{run_id}/text` | the same report as plain terminal text |
| GET | `/probes/cards` | list of `ProbeCard`, one per model |
| POST | `/probes/train_all` | train every model, return the cards |
| POST | `/probes/cards/{model_id}/train` | train one model, return its card |
| PATCH | `/probes/cards/{model_id}` | body `{"active": true}` or `false`. Switch a probe on or off. 422 for any other body, 404 for an unknown model. |

Model ids may contain `/` and `:`. The routes accept them.

The older `GET /probes` and `POST /probes/{model_id}/train` routes are the 1.0 ones. See API.md.

Events: `probe.scores` after round 0, `probe.trained` after training.

## 8. Limits

Read this part. Do not skip it.

- **Narrow training.** The probe is trained on simple true/false statements. A long plan, an opinion, a piece of code or a maths proof is far from that. The probe may do poorly there. Held-out AUROC on simple statements does not carry over.
- **What it detects.** It detects "the model represents this as false". That is a pattern in the activations. It is not intent. A model can hold a false belief and state it honestly. A model can also state something it does not believe, and the probe may miss that.
- **It can be wrong.** Expect false alarms and misses. Even a probe at 0.85 AUROC is wrong on a real share of claims.
- **A flag is a reason to check.** It is not a verdict. Look at the claim.
- **Never a vote.** Scores do not change vote weights, ever. They only add notes and cross-examination targets.
- **Per model.** A probe fits one model. A new model, a new quantisation or a new version needs a new probe.
- **Wording shifts.** Different phrasing of the same claim can move the score.
- **Memory cost.** Reading activations loads a second copy of the model through llama.cpp, next to the copy Ollama holds. It costs one extra model copy in memory while it reads (`max_models = 1` keeps it to one). Plan the memory budget for this. The copy is released after scoring.
- **Mock is not real.** With `source = "mock"` or `ollama_embed` the numbers are not hidden-state probes. Treat mock results as plumbing tests only.
- **No probe is a normal state.** If no model has an active probe, the report falls back to behaviour signals and says so.
