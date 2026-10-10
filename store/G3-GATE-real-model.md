# Gate G3 - The real model across the laptops

Run this after round 10, or as soon as `R07-A1` (loading the model without its experts) is pushed and the download is complete. This is the first time the app does what the pitch says: one model that no single laptop can hold answers a question.

Who runs it: all three humans, on the cluster link you will use on stage. Time: 45 minutes, most of it waiting for weights to move the first time.

## Before you start

| Check | How |
|---|---|
| Gate G2 passed on these laptops with the tiny model | the GOOD entry in `AGENT_CHAT.md` |
| `R07-A1` is pushed and every laptop has pulled | PUSHED entry; `python -B -m checks.run_all` passes everywhere |
| The model folder is complete on the master laptop | `python -B -m ecc inspect <model folder>` prints the numbers in the table below |
| Every laptop is on power, will not sleep, and has everything else closed | above all the local coding models: they hold the RAM this run needs |

What `inspect` must print for `Qwen/Qwen1.5-MoE-A2.7B-Chat`:

| Field | Value |
|---|---|
| arch | `qwen2_moe` |
| layers, experts per layer, top k | 24, 60, 4 |
| hidden size, expert intermediate size | 2048, 1408 |
| shared expert | yes |
| stored dtype | `bfloat16` |
| parameters per expert | 8,650,752 |
| bytes per expert as stored | 17,301,504 (16.5 MiB) |
| experts in total | 1,440 |
| backbone, as stored | 3,717,402,624 bytes (3.46 GiB) |
| all tensors, as stored | 28,631,568,384 bytes (26.67 GiB) |

If a number differs, stop: the model map (A3) or the download is wrong, and nothing after this will be right.

## Choosing the precision on each laptop

Each node computes in one precision, chosen when it starts, and that decides how much RAM an expert costs there.

| The laptop has | Start it with | An expert costs |
|---|---|---|
| an Apple Silicon or NVIDIA GPU that the app uses | nothing extra (it picks 16-bit floats) | 16.5 MiB |
| only a CPU, and 32 GB or more | nothing extra (32-bit floats: fastest) | 33 MiB |
| only a CPU, and 16 GB | `--dtype bfloat16` | 16.5 MiB, a few times slower per expert, which is still small next to a network round trip |

The same flag works on the master. On a 16 GB master without a usable GPU it is not optional: the backbone alone is 6.9 GiB in 32-bit floats.

## Steps

| # | Where | Do | What you must see |
|---|---|---|---|
| 1 | each helper laptop | `python -B -m ecc satellite` (add `--dtype bfloat16` per the table) | the ready line with the device, the precision and the budget |
| 2 | master laptop | `python -B -m ecc master --model <model folder> --peer <address 1>:7700 --peer <address 2>:7700` (add `--dtype bfloat16` per the table) | the page: every node online with a round-trip time |
| 3 | page | read the memory bars before placing anything | the master's bar shows backbone, key-value cache and overhead; write down each node's expert capacity |
| 4 | page | Auto-place | a report that is ok. Note how many experts are on Disk: zero means the whole model is in the cluster's RAM; a few hundred means the cluster is a little too small and those experts will be read from the master's disk when first needed |
| 5 | page | Launch, with a stopwatch | progress on every card. Expect roughly one minute per 6 GB over gigabit Ethernet, faster over Thunderbolt, several times slower over Wi-Fi. The master loads its backbone at the same time |
| 6 | page | set temperature 0, ask: `What is the capital of France? Answer in one word.` | the answer `Paris`. A wrong or garbled answer here means the numbers are wrong somewhere: stop and see the table below |
| 7 | page | ask for a paragraph on any subject | fluent text; cells flash across many layers; the stats show tokens per second and round trips per token (at most 24 times the number of satellites) |
| 8 | page | keep chatting on one subject for two minutes with migration on | cells turn master-coloured; "local fraction" rises; round trips per token fall; tokens per second rise. Write down the first and last values: these are the numbers for the pitch |
| 9 | master laptop | stop the master (Ctrl+C), start it again, Auto-place, Launch | a launch that takes seconds for the satellites, because they kept their experts on disk |

## If a step fails

| Symptom | First suspect | Owner |
|---|---|---|
| The master runs out of memory or the laptop freezes during launch | the full-load path is still in use, or the precision is 32-bit on a small laptop | A1; check the `--dtype` flag first |
| Launch stops with a budget error on a satellite | the page's capacity for that node and the satellite's own accounting disagree: compare the report with the satellite's log | A3 (memory math), then A2 (store accounting) |
| Step 6 gives nonsense while gate G1 still passes on the tiny model | something that differs between the tiny and the real model: the stored precision (bfloat16), the model size, or generation settings. Run `python -B -m ecc chat --model <model folder> --place disk --prompt "What is the capital of France? Answer in one word." --max-new-tokens 8`: if that is right, the fault is on the network path (A2); if it is wrong too, it is in loading or the block (A1) | A1 or A2 |
| Tokens arrive but slower than one every few seconds | look at round trips per token and milliseconds waiting per token on the page; run `python -B -m ecc bench-net --peer <address>:7700` if `R12-A2` is in | the link, then A2 |
| Nothing migrates | the setting is off, or the master's cache budget is zero because its budget is too small: lower the context length or raise the master's budget | humans, then A1 |

## When every step passes

1. Post a GOOD entry with the commit hash and the numbers from steps 5 and 8.
2. From now on, rehearse on the real model. The tiny model is for the agents' checks.
3. If the launch in step 5 took more than five minutes, plan to launch before you go on stage and present from a running cluster.
