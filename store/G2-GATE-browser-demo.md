# Gate G2 - The demo path in the browser

Run this after round 09. Part A proves the whole demo path on one machine with the tiny model. Part B repeats it across the real laptops, still with the tiny model, so that network problems show up before the big model is involved.

Who runs it: A3's human drives the browser, A1's and A2's humans watch the terminals. Time: 30 to 45 minutes.

## Before you start

| Check | How |
|---|---|
| Rounds 07 to 09 are pushed | PUSHED entries in `AGENT_CHAT.md` |
| Every check passes on every machine | `python -B -m checks.run_all` |
| The page works on simulated data | `python -B -m ecc mock-ui`, open the address it prints |

## Part A - one machine

| # | Where | Do | What you must see |
|---|---|---|---|
| 1 | terminal one | `python -B -m ecc satellite --host 127.0.0.1 --port 7701 --name sat-a --device cpu --budget-gb 2` | the ready line |
| 2 | terminal two | `python -B -m ecc satellite --host 127.0.0.1 --port 7702 --name sat-b --device cpu --budget-gb 0.751` | the ready line. The odd budget is on purpose: after the satellite's fixed overhead it leaves room for only about 14 of the tiny model's experts, so the page has something to refuse |
| 3 | terminal three | `python -B -m ecc master --model <tiny model folder> --peer 127.0.0.1:7701 --peer 127.0.0.1:7702 --device cpu --budget-gb 4` | the browser opens the page |
| 4 | page | look at the node cards | three cards (this machine first, then sat-a, sat-b) and a Disk card; each satellite shows link type `loopback`, a round-trip time, and a memory bar |
| 5 | page | look at the grid | 4 rows of 16 cells, all in the Disk colour; the header shows the model name and phase `model_loaded` |
| 6 | page | (only once round 10's `R10-A3a` and `R10-A3b` are in) click the layer number of row 1, then "Assign selection here" on sat-a | row 1 turns sat-a's colour; sat-a's memory bar grows |
| 7 | page | (same condition) press "Select all", then "Assign selection here" on sat-b | the move is refused: the card shakes, a message says by how much sat-b is over its budget, the grid does not change |
| 8 | page | press Auto-place | the grid shows three colours: the master holds about a third of the experts, sat-b about 14, sat-a the rest |
| 9 | page | press Launch | progress on each card runs to done; the phase becomes `ready` |
| 10 | page | type a prompt, Send | text streams in (nonsense: the tiny model is random); cells flash as experts are used; the stats panel shows tokens per second and round trips per token |
| 11 | page | press Stop during a long answer | the answer stops; the phase returns to `ready` |
| 12 | terminals one and two, then three | stop both satellites and the master, start all three again as in steps 1 to 3, Auto-place, Launch | the launch finishes with almost no bytes sent on the satellite cards: each satellite found the experts in its own disk cache. (With the tiny model the time saved is too small to see; with the real model this is the difference between minutes and seconds.) |

## Part B - across the laptops

Use the cluster link you will use on stage (cable or switch), not the venue Wi-Fi.

| # | Where | Do | What you must see |
|---|---|---|---|
| 1 | every laptop | pull, activate the environment, `python -B -m checks.run_all` | all `PASS` |
| 2 | each helper laptop | `python -B -m ecc satellite` | the ready line. Note the address of the cluster link on that laptop (the operating system's network settings show it) |
| 3 | each helper laptop | if the operating system asks whether Python may accept network connections, allow it for private networks | |
| 4 | master laptop | `python -B -m ecc master --model <tiny model folder> --peer <address 1>:7700 --peer <address 2>:7700` | the page lists both satellites as online with a round-trip time. Over a cable or switch expect under 2 ms; over Wi-Fi 3 to 20 ms |
| 5 | page | Auto-place, Launch, send a prompt | the same as Part A steps 8 to 10 |
| 6 | page | read the stats | write down tokens per second and round trips per token: these are the tiny-model baseline across machines |

## If a step fails

| Symptom | First suspect | Owner |
|---|---|---|
| A satellite never appears, or `connection refused` | the satellite is not running, or the port is wrong | human |
| A satellite never appears, or a timeout | firewall on the helper laptop, client isolation on the Wi-Fi, or the wrong address (use the cluster link's address) | human |
| Page does not load | `ecc/api/server.py` or the `master` mode | A3, then A1 |
| Cards or grid wrong while `mock-ui` looks right | the real State differs from the contract: compare `GET /api/state` with `07-CONTRACT-APP-API.md` section 4 | A1 |
| Cards or grid wrong in `mock-ui` too | the page | A3 |
| Refusal does not happen | `check_placement` in the planner, or the page not calling `/api/placement/check` first | A3 |
| Launch hangs or ends in `error` | read the message on the page; push problems are A2's, loading problems A1's | A2 or A1 |
| No tokens | generation or event forwarding | A1 |
| Part A step 12 is not faster | the satellite disk cache | A2 |

## When both parts pass

1. Post a GOOD entry with the commit hash and the Part B numbers.
2. Decide now which laptop is the demo machine and which link you will use, and write both into `AGENTS.md` (root owner).
3. Go on to round 10. The big model's download must be complete by now.
