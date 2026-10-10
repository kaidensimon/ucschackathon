# Gate G4 - Freeze and rehearsal

Run this at the Freeze time written in `AGENTS.md`, whatever state the build is in. From here on the agents fix the demo path and add nothing (`AGENTS.md` section 10). The point of this gate is to find out, with hours to spare, what the judges will actually see.

Who runs it: all three humans, at the demo machine, on the link you will use on stage. Time: one hour.

## Part A - set up from scratch

A demo that works only on the laptop it was built on is not finished. `AGENTS.md` section 10 asks for this once before Freeze; if it has not been done, do it now.

| # | Do | What you must see |
|---|---|---|
| 1 | On the demo machine, make a fresh clone in a new folder | |
| 2 | Follow Install in `AGENTS.md` exactly, nothing else | no errors |
| 3 | `python -B -m checks.run_all` | every file `PASS` |
| 4 | Anything you had to do that Install does not say | fix Install or the code, in the repo, now |

## Part B - the demo, twice

Close everything the demo does not need on all laptops, above all the local coding models: they hold many gigabytes of RAM that the cluster needs. Plug every laptop into power and switch off sleep.

Run the demo path from `AGENTS.md` from a cold start (every satellite and the master stopped), with a stopwatch, exactly as you will on stage. Then stop everything and do it again.

| Step of the demo path | Time, run 1 | Time, run 2 | Worked? |
|---|---|---|---|
| 1. Satellites and master start, the page lists every machine | | | |
| 2. Model loaded, the memory bars show it does not fit in the master | | | |
| 3. Placement, one refused move, Launch finishes | | | |
| 4. A prompt streams an answer; cells light up; stats move | | | |
| 5. Experts turn master-coloured; round trips per token fall; tokens per second rise | | | |

Write the times into the chat (a NOTE to all). The second launch should be much faster than the first because the satellites kept their experts on disk; if the first launch takes minutes, do it before you walk on stage and present from a launched cluster.

## Part C - what to say when something is slow

Have the numbers ready; judges ask.

| Question | Where the answer comes from |
|---|---|
| How big is the model and how much RAM does each laptop have? | `python -B -m ecc inspect <model folder>` and the node cards |
| How many network round trips per token, before and after migration? | the stats panel, first and last minute |
| How fast is it? | tokens per second at the start and after two minutes |
| What happens if a laptop disappears? | only if `R12-A1` is in and you rehearsed it: unplug one, generation continues |
| Why not just read experts from the master's disk? | a disk read of one expert costs about as much as a round trip on a slow link, and the operating system cannot keep 25 GB of experts in a 16 GB machine's file cache; the cluster's RAM can |

## Part D - decide the fallbacks now

| If this happens on stage | Do this |
|---|---|
| A satellite will not connect | run with the satellites that do; unplaced experts stay on disk and the model still answers, slowly |
| The venue network blocks the laptops from seeing each other | use the cable or switch you brought; if there is none, a phone hotspot that all laptops join |
| The real model will not launch | show the same path with the tiny model (text is nonsense; say so) and the real model's memory bars |
| Nothing connects at all | if `R13-A3` is in: `python -B -m ecc mock-ui --replay <the recording from rehearsal>` replays your best rehearsal run in the real page |
| `main` broke after the rehearsal | the newest GOOD commit, in a fresh clone (`AGENTS.md` section 10) |

Record a rehearsal now if `R13-A3` is in: set the environment variable `ECC_RECORD` to a file path before starting the master, run the demo once, keep the file.

## When this gate is done

1. Post a GOOD entry with the commit hash of the rehearsed build.
2. List in one NOTE to humans every step that failed or was slow, in the order it would embarrass you. Those, and nothing else, are the work between now and the Deadline.
3. Thirty minutes before the Deadline the demo machine stops pulling (`AGENTS.md` section 10).
