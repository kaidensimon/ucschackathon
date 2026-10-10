# 01 - Overview

Read this at the start of every session, after `AGENTS.md`. It is the map. The numbered contract files (`03` to `07`) hold the exact interfaces; your task file tells you which of them to read.

## What we are building

**Expert Cache Cluster** (package name `ecc`): an app that runs one Mixture-of-Experts (MoE) language model that is too big for the RAM of any single laptop, by keeping most of its expert weights in the RAM of other laptops on the same network.

- A MoE model is a normal transformer in which each layer's feed-forward part is replaced by many small feed-forward networks called **experts**. For every token, a small **router** picks a few experts (the top `k`) out of many (`E` per layer), runs only those, and adds their weighted outputs. Most of the model's weights are experts, but only a few experts are used for any one token.
- One machine, the **master**, runs everything that is not a routed expert: tokenizer, embeddings, attention, norms, routers, shared experts, output head, key-value cache, sampling. We call that part the **backbone**.
- The other machines, **satellites**, hold expert weights in RAM and do one thing: given an expert and a batch of activations, return that expert's output. They know nothing about the text.
- The master keeps the experts it uses most in its own RAM (the **expert cache**). Experts that turn out to be hot are loaded into that cache while the session runs (**migration**), so remote calls become rarer and the model speeds up.

## The path of one token

1. The master runs layer 1's attention, then the router, which names `k` experts for this token.
2. For each named expert the **dispatcher** looks up where it lives: in the master's RAM (compute here), on a satellite (send the activations there), or only on the master's disk (load it, then compute here).
3. All calls for one satellite in one layer travel in one request. Different satellites are called at the same time. The answers come back and the master adds them up.
4. The same happens in every layer, then the output head picks the next token.

So a token costs at most one network round trip per layer per satellite, and none at all for a layer whose chosen experts are all in the master's RAM.

## Stack

- Python 3.11, 3.12 or 3.13. PyTorch 2.14 and Hugging Face `transformers` 5.17 run the backbone. Every package version is pinned in `requirements.txt`; never change, add or upgrade one yourself. What you remember about these libraries may be from an older version: where a task file states a fact about a library, trust the task file.
- The network layer is plain blocking TCP sockets and threads from the standard library. No asyncio in `ecc/net/` or `ecc/engine/`.
- The UI is a web page served by the master (FastAPI), written in plain HTML, CSS and JavaScript modules. No npm, no build step, no CDN links.
- One program, several modes: `python -B -m ecc <mode>`. Always pass `-B` so Python writes no cache folders into the repo.

## Repo layout and owners

| Path | Owner | What lives there |
|---|---|---|
| `requirements.txt`, `README.md`, `ecc/__init__.py`, `ecc/__main__.py`, `ecc/app.py` | A1 | skeleton, mode dispatcher, the real app facade |
| `ecc/common/` | A1 | shared types, settings, errors, logging, dtype table, expert math |
| `ecc/engine/` | A1, except the two files in the next row | tiny test model, reference oracle, MoE block, dispatcher, expert cache, generation, launcher |
| `ecc/engine/stats.py`, `ecc/engine/chat.py` | A2 | engine counters; the terminal chat mode |
| `ecc/net/` | A2 | wire protocol, satellite, client, weight push, node registry, discovery |
| `ecc/migrate/` | A2 | the migrator that moves hot experts into the master's RAM |
| `ecc/modelfile/` | A3 | safetensors index, model map, expert reader |
| `ecc/placement/` | A3 | memory math, placement checker, auto-placer |
| `ecc/api/` | A3 | facade interface, mock facade, HTTP and event server |
| `ecc/ui/` | A3 | the web page |
| `checks/run_all.py` | A1 | runs every check |
| `checks/check_engine_*.py`, `checks/check_common_*.py` | A1, except the two in the next row | A1's checks |
| `checks/check_net_*.py`, `checks/check_migrate_*.py`, `checks/check_engine_stats.py`, `checks/check_engine_chat.py` | A2 | A2's checks |
| `checks/check_modelfile_*.py`, `checks/check_placement_*.py`, `checks/check_api_*.py`, `checks/check_ui_*.py` | A3 | A3's checks |
| `store/` | humans | these plan files. Agents read them and never edit them |

A1 is the root owner: every path not listed is A1's.

## Words used in every file

| Word | Meaning |
|---|---|
| expert | one routed feed-forward network: three weight matrices. The smallest unit that is placed, moved or called. Never split |
| expert key | the pair (layer, expert), both counted from 0 |
| backbone | every tensor that is not part of a routed expert. Always on the master |
| shared expert | an extra feed-forward network some models run for every token. It is backbone |
| router | the small linear layer that scores the experts for a token. It is backbone |
| placement | for every expert key, the node that holds it in RAM at launch, or "disk" |
| disk | the expert is in nobody's RAM; the master reads it from the model file when it is needed |
| node | a machine in the cluster: the master or a satellite |
| dispatcher | the master-side object that sends each expert call to the right place |
| model hash | 16 hex characters that identify a model file set |
| tiny model | a small random-weight model we generate ourselves. Its text is nonsense; it exists so every check runs in seconds |
| reference | the same model run by plain `transformers` with no cluster code. Our output must match it |
| facade | the one Python object through which the HTTP server talks to the app |

## The one test that matters

For the same input, the logits produced through our code path must equal the logits of the reference, whatever the placement: all local, all remote, or mixed. With 32-bit floats on the wire the largest absolute difference must be below 1e-4. Every engine and network task ends by showing this still holds.

## Modes

| Command | What it does | Owner |
|---|---|---|
| `python -B -m ecc make-tiny` | creates the tiny model in the data folder | A1 |
| `python -B -m ecc inspect <model folder>` | prints the model map | A3 |
| `python -B -m ecc satellite` | runs a satellite | A2 |
| `python -B -m ecc chat` | terminal chat on the master, no UI | A2 |
| `python -B -m ecc master` | the full app with the UI | A1 |
| `python -B -m ecc mock-ui` | the UI on simulated data, no model | A3 |
| `python -B -m checks.run_all` | runs every check. This is the project's Check | A1 |

## Where files go on a machine

Nothing large and nothing generated goes into the repo. The data folder is `~/.ecc` (the environment variable `ECC_HOME` overrides it): `models/tiny/` for the tiny model, `cache/` for a satellite's saved experts, `node_id` for this machine's id. Real model folders live wherever the human downloaded them. The Python virtual environment is also outside the repo.

## Out of scope for this hackathon

GGUF files, quantised weights, 8-bit activations, QUIC, more than one master, more than one chat at a time, training, authentication, encryption. If a task seems to need one of these, it does not: re-read the task.
