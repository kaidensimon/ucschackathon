# 08 - Rounds

48 task files in 13 rounds, plus four gates. One task file = one fresh chat. A cell with two files (`a` then `b`) is two short chats for the same agent.

## How it runs

1. One file per round: `ROUND-01.md` to `ROUND-13.md`. Each holds the parts for Agent 1, Agent 2 and Agent 3. The table below shows which tasks are inside each file.
2. Push one round file. Each human tells their agent: `You are Agent <n>. Read store/ROUND-<NN>.md and do the Agent <n> part.`
3. A task is done when the agent's log has a PUSHED entry starting `DONE <task id>`. A round is done when all three parts are done and `python -B -m checks.run_all` passes.
4. Then push the next round file.

## The table

| Round | A1: engine and app | A2: network, satellite, migrator | A3: model file, placement, API, page |
|---|---|---|---|
| 01 | `R01-A1a-skeleton`, `R01-A1b-common-types` | `R01-A2-wire-frames` | `R01-A3-tensor-index` |
| 02 | `R02-A1-tiny-model-and-expert-math` | `R02-A2-messages` | `R02-A3-model-map-and-reader` |
| 03 | `R03-A1-reference-and-cache` | `R03-A2a-satellite-store`, `R03-A2b-engine-stats` | `R03-A3-budget-and-planner` |
| 04 | `R04-A1-moe-block-and-install` | `R04-A2-satellite-server` | `R04-A3a-facade-events-conformance`, `R04-A3b-mock-facade` |
| 05 | `R05-A1a-dispatcher-local`, `R05-A1b-dispatcher-remote` | `R05-A2-client-and-cluster` | `R05-A3-http-server` |
| 06 | `R06-A1-generation-service` | `R06-A2a-node-registry`, `R06-A2b-chat-mode` | `R06-A3a-page-shell`, `R06-A3b-node-cards` |
| | **Gate G1**: one model, two satellites, in the terminal | | |
| 07 | `R07-A1-backbone-only-loading` | `R07-A2-weight-push` | `R07-A3-expert-grid` |
| 08 | `R08-A1a-app-state-and-nodes`, `R08-A1b-app-placement-and-master-mode` | `R08-A2-migrator` | `R08-A3-launch-and-chat` |
| 09 | `R09-A1a-app-launch`, `R09-A1b-app-generate-and-stats` | `R09-A2-satellite-disk-cache` | `R09-A3-stats-heat-migration` |
| | **Gate G2**: the demo path in the browser, tiny model, then across the laptops | | |
| 10 | `R10-A1-migration-wiring` | `R10-A2-mdns-discovery` | `R10-A3a-selection`, `R10-A3b-assign-and-refuse` |
| | **Gate G3**: the real model across the laptops | | |
| 11 | `R11-A1-speculative-decoding` | `R11-A2-link-type-and-addresses` | `R11-A3-dialogs-and-settings` |
| 12 | `R12-A1-node-loss-and-rejoin` | `R12-A2-robustness-and-bench` | `R12-A3-big-grid-and-polish` |
| 13 | `R13-A1-speed-pass` | `R13-A2-doctor` | `R13-A3-record-and-replay` |
| | **Gate G4**: freeze and rehearsal | | |

A1 has the longest path. A2 has two tasks that sit in A1's folder to take load off A1: `R03-A2b` (`ecc/engine/stats.py`) and `R06-A2b` (`ecc/engine/chat.py`).

## Cross-track needs

Each task file's "Needs" row is the full list. The ones that cross tracks:

| Task | Needs from another track |
|---|---|
| `R01-A2`, `R01-A3` | `R01-A1a` (same round: write the code, run the check after the pull that brings it) |
| `R02-A2`, `R02-A3`, `R03-A3`, `R03-A2b` | `R01-A1b` |
| `R03-A2a` | `R02-A1` (expert math) |
| `R05-A1a` | `R03-A2b` (stats), `R02-A3` (expert reader) |
| `R05-A1b` | `R02-A2` (message item type) |
| `R06-A2b` | `R06-A1` (generation), `R05-A1b` (dispatcher) |
| `R07-A1` | `R01-A3` (tensor index) |
| `R07-A2` | `R02-A3` (expert reader) |
| `R08-A1a` | `R06-A2a` (registry), `R04-A3a` (facade, events) |
| `R08-A1b` | `R03-A3` (planner), `R05-A3` (server) |
| `R08-A2` | `R05-A1a` (dispatcher), `R03-A1` (cache) |
| `R09-A1a` | `R07-A2` (push) |
| `R10-A1` | `R08-A2` (migrator) |
| `R12-A1` | `R09-A2` (disk cache), `R10-A2` (discovery, optional) |

## A clock for 20 hours

| By hour | The team should be here |
|---|---|
| 1 | downloads running, `R01-A1a` pushed, everyone installed |
| 7 | rounds 01 to 06 done, gate G1 passed |
| 9 | if G1 has not passed: from here do only rounds 01 to 09 and `R10-A1` |
| 11 | rounds 07 to 09 done, gate G2 passed |
| 13 | round 10 done, gate G3: the real model answers across laptops |
| 16 | rounds 11 and 12 |
| 17 | Freeze. Only fixes to the demo path after this |
| 18 | gate G4: two full rehearsals |
| 20 | Deadline |

From G3 on a laptop is either coding or running the cluster, never both: the local coding model and the real model do not fit in RAM together.

## If you are behind

Cut from the bottom upward.

1. Rounds 01 to 09 and `R10-A1`: the demo path including migration. Never cut. `R09-A2` (disk cache) stays too: it makes every relaunch take seconds.
2. `R11-A1` speculative decoding.
3. `R10-A3a`, `R10-A3b` select and assign: without them placement is Auto-place only; skip the refused move in the demo.
4. `R11-A3` dialogs: without it the model and peers come from the command line (`master --model ... --peer ...`).
5. `R12-A1` node loss: without it, do not unplug anything on stage.
6. `R13-A3` record and replay: the safety net if the cluster fails on stage.
7. `R12-A3` polish, `R12-A2` bench, `R13-A1` speed pass.
8. `R10-A2` mDNS, `R11-A2` link type: without them peers are added by address and the link shows as "unknown".
9. `R13-A2` doctor.
