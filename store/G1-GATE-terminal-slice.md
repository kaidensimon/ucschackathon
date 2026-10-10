# Gate G1 - The terminal slice

Run this after round 06. First time the three tracks meet: A1's engine sends expert calls through A2's network code to A2's satellites, reading weights with A3's reader. One machine, tiny model, terminals only.

Who runs it: A1's human, the other two watching. About 20 minutes.

## Before you start

| Check | How |
|---|---|
| Rounds 01 to 06 are pushed by all three | PUSHED entries in `AGENT_CHAT.md` |
| Your clone is current | pull as `AGENTS.md` says |
| Every check passes | `python -B -m checks.run_all` ends with every file `PASS` (allow a few minutes) |
| The tiny model exists | `python -B -m ecc make-tiny` prints its folder |

A failing check is fixed by its owner before the gate goes on. The file name says whose it is: `check_common_`, `check_engine_` A1 (except `check_engine_stats`, `check_engine_chat`: A2); `check_net_`, `check_migrate_` A2; the rest A3.

## Part A - one machine

Three terminals in the repo folder, environment active.

| # | Terminal | Command | What you must see |
|---|---|---|---|
| 1 | one | `python -B -m ecc satellite --host 127.0.0.1 --port 7701 --name sat-a --device cpu --no-cache` | `satellite sat-a <id>-7701 listening on 127.0.0.1:7701 device=cpu dtype=float32 budget=... GiB` |
| 2 | two | the same with `--port 7702 --name sat-b` | the same for `sat-b`, and a different node id (it ends in `-7702`) |
| 3 | three | `python -B -m ecc inspect <tiny model folder>` | 4 layers, 16 experts, top 4, shared expert yes |
| 4 | three | `python -B -m ecc chat --place local --wire-dtype float32 --check` | `max logit difference:` below 0.0001; exit code 0 |
| 5 | three | `python -B -m ecc chat --place disk --wire-dtype float32 --check` | the same |
| 6 | three | `python -B -m ecc chat --peer 127.0.0.1:7701 --peer 127.0.0.1:7702 --place remote --wire-dtype float32 --check` | difference below 0.0001 and the line `calls local=0 remote=<above 0> disk=0`. This step proves the idea: every routed expert was computed in another process. `disk` above 0 means the network path failed and the disk fallback hid it |
| 7 | three | the same with `--place split` | difference below 0.0001, `remote` above 0, `disk=0` |
| 8 | three | the same with `--place split --wire-dtype float16` | difference below 0.05 (16-bit activations lose a little; expected), `disk=0` |
| 9 | three | `python -B -m ecc chat --peer 127.0.0.1:7701 --peer 127.0.0.1:7702 --place split --prompt "hello" --max-new-tokens 30` | 30 tokens of nonsense text (random weights), then `tokens=30 ... remote=<above 0> ...`. If it says the model has no tokenizer: `python -B -m ecc make-tiny --tokenizer-from <draft model folder>` and repeat |
| 10 | three, then two | step 9 again with `--max-new-tokens 200`; while it prints, stop `sat-b` with Ctrl+C | the text keeps coming; a warning says the node is unavailable and its experts are now read from disk |
| 11 | one, two, three | restart both satellites with `--dtype bfloat16` added, then step 9 with `--device cpu --dtype bfloat16` added | text appears, no error. This is the only test of 16-bit computation before the real model |

## Part B - two machines (10 minutes)

| # | Where | Command | What you must see |
|---|---|---|---|
| 1 | a helper laptop, on the cluster link | `python -B -m ecc satellite --device cpu --no-cache` | the ready line; allow Python through the firewall if asked (Windows: both private and public networks) |
| 2 | A1's machine | `python -B -m ecc chat --peer <helper address>:7700 --place remote --wire-dtype float32 --check` | difference below 0.0001, `disk=0` |

If step 2 times out, the laptops cannot reach each other: firewall on the helper, Wi-Fi client isolation, or the wrong address. Sort this out now, not at G2.

## If a step fails

| Step | First suspect | Owner |
|---|---|---|
| A1, A2 | satellite mode or its flags | A2 |
| A3 | model map | A3 |
| A4 | the MoE block or the dispatcher's local path | A1 |
| A5 | the dispatcher's disk path, or the expert reader | A1, then A3 |
| A6, A7 | run `python -B -m checks.check_net_client`: passes means the fault is in chat's placement or loading (A2, `chat.py`) or the dispatcher's remote path (A1); fails means the client (A2) | A2 or A1 |
| A8 | above 0.05: 16-bit is applied somewhere other than the wire | A1 |
| A9 | generation service (A1) or chat mode (A2) | A1 or A2 |
| A10 | dispatcher failure handling (A1) or the client not raising `NodeUnavailable` (A2) | A1 or A2 |
| A11 | a missing dtype conversion in expert math, the block, or the satellite store | A1, then A2 |

The owner's human starts a new chat with the repair prompt from `00-START-HERE.md`, naming this file and the step.

## When every step passes

A1's agent posts a GOOD entry with the commit hash and the numbers from steps A6 and A8. Go on to round 07.
