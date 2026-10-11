# Council API: integration guide for a separate UI

For a developer building a TypeScript UI against the Council backend. Written from `main-dev/council/api/*`,
`council/core/event_types.py`, `schemas.py`, `schemas_v15.py` and `ui/src/{types,api,store}.ts`. Where docs and code
disagree, the code wins. Section 11 lists known rough edges. All paths are under `main-dev/`; run commands from there.

## 1. Start the backend

```
python -m council.api.server
```

Binds `127.0.0.1`, port `8765` or the `COUNCIL_PORT` environment variable. Needs only fastapi, uvicorn, pydantic, httpx.
SQLite file `<home>/db/council.db`; runs and events survive a restart. `<home>` is `COUNCIL_HOME` or `main-dev/`.
CORS allows any `localhost` / `127.0.0.1` origin (any port) plus `null` and `file://`. No auth.
Check: `curl http://127.0.0.1:8765/health` gives `{"ok":true,"mock":true,"driver":"mock"}`.

### Mock or real: config/council.toml decides
`python -m council.api.server` builds `RunController.build_from_config()`, which reads `[gateway] mock`:

- `mock = true` (the file as shipped): `build_mock()`. No GPU, no model server. `driver` in `/health` is `"mock"`.
- `mock = false`: the real stack. The model host driver comes from `[host] driver` and is echoed as `driver` in
  `/health`. `llamacpp` is the box setting (`tools/box/make_config.py` writes it unless `COUNCIL_DRIVER=ollama`): one
  `llama-server` process per model, loading the GGUF file that Ollama downloaded. Ollama is only the downloader
  there. `ollama` is the fallback: Ollama serves the models at `[ollama] base_url` (default
  `http://127.0.0.1:11434`). Any other value (the shipped `llama_router`) builds the router driver. No model is
  started until a run needs it. Steering vectors (`steer.applied`) and per-model context only work with `llamacpp`.

Edit the toml and restart to switch. `GET /health` tells the UI which stack it is talking to.

## 2. Conventions

JSON in and out; times are float epoch seconds; snake_case. Errors are `{"detail": "..."}`: `404` not found,
`409` wrong state, `422` body does not validate. Types live in `ui/src/types.ts`.

## 3. Endpoints

Base: `http://127.0.0.1:8765`.

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/health` | none | `{ok: true, mock: boolean, driver: string}` |
| POST | `/runs` | `RunRequest` | `{run_id: string}` |
| GET | `/runs` | none | array of run rows from the store, newest first |
| GET | `/runs/{id}` | none | `RunSnapshot` |
| GET | `/runs/{id}/events?since=N` | none | SSE stream (section 4) |
| POST | `/runs/{id}/delegate` | none | `{ok: true}` |
| POST | `/runs/{id}/input` | `UserInput` | `{ok: true}` |
| PATCH | `/runs/{id}/plan` | partial or full `Plan` | `{ok: true, plan: Plan, issues: []}` |
| POST | `/runs/{id}/cancel` | none | `{ok: boolean}` |
| GET | `/router/preview?task=..&mode=..` | none | `LineupRecord` |
| GET | `/models` | none | `ModelEntry[]` each with a `live` object |
| POST | `/models/{id}/load` | none | `{ok: true, model_id}` |
| POST | `/models/{id}/unload` | none | `{ok: true, model_id}` |
| GET | `/chronicle` | none | `ChronicleEntry[]` |
| PATCH | `/chronicle/{entry_id}` | partial `ChronicleEntry` | the updated entry |
| DELETE | `/chronicle/{entry_id}` | none | `{ok: true}` |
| GET | `/telemetry` | none | `TelemetrySnapshot` |
| POST | `/bench/runs` | optional `BenchRunRequest` | `{bench_id: string}` |
| GET | `/bench/runs/{bench_id}` | none | bench status object |
| GET | `/corrections?project=` | none | `Correction[]` |
| GET | `/probes` | none | `Probe[]` (without `weights`) |
| POST | `/probes/{model_id}/train` | none | the trained `Probe` (without `weights`) |
| GET | `/chronicle/export?project=` | none | Markdown text (`text/markdown`) |
| GET | `/config` | none | the loaded `Config` as JSON |
| GET | `/runs/{id}/summary` | none | flat run summary (section 3a) |
| GET | `/runs/{id}/ui-events` | none | the run as the partner UI's `DebateEvent` stream (SSE, no `event:` names) |
| GET | `/lies/{run_id}` | none | `LieReport` plus `caveat` (404 if the run has none) |
| GET | `/lies/{run_id}/text` | none | the same report as plain text (`text/plain`) |
| GET | `/probes/cards` | none | `ProbeCard[]`, one per model |
| POST | `/probes/train_all` | none | train every model, returns `ProbeCard[]` |
| POST | `/probes/cards/{model_id}/train` | none | train one model, returns its `ProbeCard` |
| PATCH | `/probes/cards/{model_id}` | `{active: boolean}` | the updated `ProbeCard` (422 for any other body, 404 unknown model) |
| GET | `/system/models` | none | model cards (section 3a) |
| GET | `/system/memory` | none | `{meminfo, plan}` (section 3a) |
| GET | `/system/specdec` | none | `DraftPair[]` |
| GET | `/system/measured` | none | `{model_id: MeasuredModel}` from the on-box check |
| GET | `/steer` | none | `SteerCard[]`, `[]` while there are none |

### Request bodies
`RunRequest` (POST /runs), only `task` required: `task: string`, `workspace?: string|null`,
`mode?: "quick"|"standard"|"deep"` (default standard), `deliverable?: "answer"|"plan"|"build"|null` (null: the
Profiler decides), `lineup_override?: string[]|null` (model ids), `options?: object`.

Known `options` keys (read by the controller and pipeline):

- `demo: true` replays a scripted run instead of the pipeline. Also `seed` (int).
- `auto_delegate: true` skip the delegate click.
- `auto_input: true` do not pause for user questions (pipeline path).
- `bench: true` marks a bench run (tribunal is skipped unless `[tribunal] in_bench`).
- `k: int` council size, the number of seats. The UI offers 2 to 6. A value outside 2..6 is ignored unless the mode's
  own `k_options` lists it (`deep` also lists 7); an ignored value means the mode default (quick 3, standard and deep
  6). The memory plan can seat fewer than asked: it drops the lowest scored seats when they do not fit, never below 2
  (see `memory.planned`, section 6). The seat count that really sits is `router.lineup_selected.k` and the number of
  `seat.assigned` events. CLI: `--k 2..6`.
- `effort: "light"|"normal"|"heavy"|"fixed"` sets how much the council deliberates. Unset (CLI `--effort auto`): the
  pipeline plans the level from task difficulty and measured seat speed (standard mode, `[chamber] adaptive = true`).
  `light`, `normal` and `heavy` force that level. `fixed` uses the mode's own rounds and deadline. A positive
  `deadline_s` option beats the planned deadline.

`BenchRunRequest` (POST /bench/runs), all optional: `tasks_path` (default: the bundled sample tasks), `modes: string[]`,
`split` (`"test"` default), `limit`, `models: string[]` (empty: the whole registry). Only one bench runs at a time
(`409` otherwise). Status fields: `bench_id, state, mode, model_id, done, total, correct, modes, summary, results_path,
out_dir, error, started_at, finished_at, request`. `404` for an unknown bench id.

`UserInput` (POST /runs/{id}/input): `{request_id: string, choice?: string|null, text?: string|null}`.
`request_id` must equal the one in the open `user.input_requested` event, else `409`.

`PATCH /runs/{id}/plan`: the body is any set of top-level `Plan` fields. The server lays it over the current plan
(`dict.update`, so a `tasks` array replaces the whole list), re-lints it (`Foreman.apply_user_edit`), stores it with a
new version and emits `plan.drafted` (with `version` and `task_count`). Success: `200 {ok: true, plan, issues: []}`.
`404` unknown run. `409` unless the run is in `AWAITING_DELEGATION` (or has no plan). `422` when the body is not a
valid plan or lint errors remain; nothing is stored. The 422 body is `{ok: false, detail, issues: [{code, task_id,
message}]}`.

### Curl examples
```bash
B=http://127.0.0.1:8765
curl $B/health
curl -X POST $B/runs -H "Content-Type: application/json"   -d '{"task":"SQLite or Postgres for a small app?","mode":"quick","deliverable":"answer"}'   # {"run_id":"run_..."}
curl $B/runs
curl $B/runs/RUN_ID
curl -N "$B/runs/RUN_ID/events?since=0"
curl -X POST $B/runs/RUN_ID/delegate
curl -X POST $B/runs/RUN_ID/input -H "Content-Type: application/json" -d '{"request_id":"ask_...","choice":"proceed"}'
curl -X PATCH $B/runs/RUN_ID/plan -H "Content-Type: application/json" -d '{"tasks":[...]}'
curl -X POST $B/runs/RUN_ID/cancel
curl "$B/router/preview?task=write%20a%20parser&mode=standard"
curl $B/models; curl -X POST $B/models/MODEL_ID/load; curl -X POST $B/models/MODEL_ID/unload
curl $B/chronicle
curl -X PATCH $B/chronicle/ENTRY_ID -H "Content-Type: application/json" -d '{"status":"retracted"}'
curl -X DELETE $B/chronicle/ENTRY_ID
curl $B/telemetry
curl -X POST $B/bench/runs -H "Content-Type: application/json" -d '{"limit":5}'
```

### Endpoint notes
- `GET /runs/{id}` folds the stored events into a `RunSnapshot` on each call (fields: `state, prev_state, task,
  workspace, mode, deliverable, profile, lineup, round, options, cruxes, evidence, tally, decision, plan,
  task_statuses, work_report, pending_input, counters, error, last_seq, created_at, updated_at, finished_at,
  tribunal, corrections, claim_scores`). Use `last_seq` as `since`.
- `cancel` returns `{ok:false}` if the run had already ended. After a server restart, `delegate` and `input` on a
  run that was mid-flight return `409 "... not active in this process"`.
- `GET /models` rows are the registry entry (including `ollama_tag`, `ollama_options` and `speculative`, see below)
  plus `live: {resident, ...host status row}`. `load` returns `409` with the
  host error if the model does not fit. `GET /telemetry` returns the last tick while a run is active, else a fresh sample.

## 3a. The 1.5 routes in detail

Types are in `council/core/schemas_v15.py`. Every score reads 0 = likely false, 1 = likely true. `null` means that
signal was missing.

### Lie detector: `/lies/...` and `/probes/...`

`GET /lies/{run_id}` returns a `LieReport` plus `caveat` (a sentence to show next to the scores):

```
{run_id, seats: SeatHonesty[], flags: LieFlag[], probe_models: string[], note: string, caveat: string}
SeatHonesty: {seat_no, model_id, claims, flagged, watched, mean_probe|null, mean_gap|null, level}
LieFlag:     {run_id, seat_no, model_id, claim_id, text, probe_score|null, behaviour_score|null, track_record|null,
              stated_confidence|null, bluff_gap|null, level, reasons: string[]}
level:       "ok" | "watch" | "flag"
```

`flags` holds every scored claim, worst first. `note` says things like "no active probe: behaviour signals only".
`404` when the run has no report (lie detector off, round 0 not done, or an unknown run). The same report also comes
as the `lie.report` event. `GET /lies/{run_id}/text` is the same report as plain terminal text.

A flag is advice, never a vote. Show it as "check this claim". `docs/LIE_DETECTOR.md` has the cut-offs and limits.

`ProbeCard`: `{model_id, version, source ("mock"|"ollama_embed"|"llamacpp"), layers[], auroc|null, accuracy|null,
control_auroc|null, baseline_auroc|null, ece|null, n_train, n_test, trained_at, active, reason}`. `active` is true only
when the probe passed every switch-on check; `reason` says which check failed otherwise. Model ids may contain `/` and
`:`; the routes accept them. `POST /probes/train_all` and `POST /probes/cards/{id}/train` can take a long time (they
read activations through llama.cpp), so call them with a long client timeout. The older `GET /probes` and
`POST /probes/{id}/train` are the 1.0 routes.

### Steering vectors: `GET /steer`

A list of `SteerCard`: `{project, model_id, version, layers[], scale|null, examples, fraction, active, reason,
trained_at, path}`. `scale` is the strength the search chose, `null` when none passed the sanity check (then `active`
is false and `reason` says why). `fraction` is the vector size as a share of the hidden-state size. There is no
route to train or switch a vector by hand: a vector is trained after a run that recorded a correction
(`steer.trained`), and applied when the model is next seated in that project (`steer.applied`).

### Machine status: `/system/...`

A provider failure on one route gives `503 {"detail": "<what> failed: <error>"}` for that route only.

- `GET /system/models`: one card per registry model, resident ones first: `{id, display, lab, lineage, params_b,
  quant, roles[], status, ollama_tag, resident, memory_gib|null, tps|null, json_ok|null, think_ok|null, runs, wins,
  chaired, win_rate, probe: {active, auroc, version}|null}`. `memory_gib` and `tps` come from the on-box check file
  first, then the registry.
- `GET /system/memory`: `{meminfo: {total_gib, available_gib, used_gib, swap_used_gib}, plan: MemoryPlan}`. The plan
  here is for the models resident now. The plan of one run is in its `memory.planned` event.
  `MemoryPlan`: `{fits, budget_gib, total_gib, per_model{id: gib}, num_ctx{id: tokens}, roles{role: id},
  shared_roles[], dropped[], notes[]}`.
- `GET /system/specdec`: `DraftPair[]`: `{target_id, draft_id, family, size_ratio, verified, speedup|null, note}`.
  A pair is only a proposal until `verified` is true (measured on the box). Speculative decoding needs the
  `llamacpp` driver.
- `GET /system/measured`: `{model_id: MeasuredModel}`, `MeasuredModel`: `{model_id, tag, ok, reported_gib|null,
  ram_gib|null, tps|null, json_ok|null, think_ok|null, error}`. Empty until `tools/box/check_models.py` has run.

### Run summary: `GET /runs/{id}/summary`

The stored events of the run folded into one flat dict. Every key is always present. Keys: `run_id, started, ended,
wall_s, state, lineup[{seat_no, model_id, lens}], effort|null, rounds[], agreement_trend[], decision{outcome,
option_id, agreement, rounds_run, confidence, final_text}, extended, tribunal|null, plan{tasks, titles[]},
tasks{passed, failed, blocked, skipped}, reviews[], final_say|null, integration{ok, files_written},
memory{candidates, committed}, failures[], tokens{in, out}, calls`. `404` for an unknown run.

---

## 4. The event stream

`GET /runs/{id}/events` is Server-Sent Events (`text/event-stream`, `Cache-Control: no-cache`).

### Framing

Each event is one frame:

```
id: 42
event: turn.completed
data: {"type":"turn.completed","seq":42,"ts":1760000000.12,"run_id":"run_...","payload":{...}}

```

- `id` is the event `seq`. `event` is the type string (so browsers need `addEventListener(type, ...)` per type;
  plain `onmessage` does not fire for named events). `data` is the full envelope as compact JSON.
- Envelope: `{type: string, seq: number, ts: number, run_id: string, payload: object}`.
- Idle keepalive: the comment line `: ping` after 15 s with nothing to send. Ignore it.
- `seq` is strictly increasing per database (not per run), so within one run it is increasing with gaps.

### Resume
The server replays stored events with `seq` above the cursor, then polls (50 ms) for new ones. Cursor = the larger of
`?since=N` and the `Last-Event-ID` header; non-numeric counts as 0. To resume, reconnect with `since=<highest seq
applied>`; `since=0` (full replay) is safe. A finished run replays all stored events, then closes.

### Terminal events and close
`run.completed`, `run.failed` and `run.cancelled` are terminal. The server sends the terminal event, then ends
the response. The client must treat a normal close after a terminal event as the end, and not reconnect
(`api.ts` closes on terminal types). The stream also ends, once idle, when this process no longer drives the run (for example after a restart): stored
events are replayed, then it closes.

### Ephemeral delta events
`turn.delta`, `turn.reasoning_delta`, `chair.delta`, `task.delta` (any type ending in `.delta` or `_delta`) are never
stored, but the SSE route delivers them live: after replaying stored events it forwards everything the event bus
publishes for the run. They carry the last stored `seq` of the run, so they repeat a `seq`. Never de-duplicate them by
`seq` (`store.ts` does not). They are not replayed after a reconnect; a client that joins late sees only deltas from
that moment. The finished text is always in `turn.completed.content`, `decision.final` and `task.attempt_completed`.

`telemetry.tick` is not ephemeral in the Python code: it is stored and replayed, about one per second per live
(non-demo) run.

## 5. Run states

`RunState`: `INTAKE, PROFILING, CONVENING, DELIBERATING, DECIDED, EXAMINING, PLANNING, AWAITING_DELEGATION,
EXECUTING, REVIEWING, INTEGRATING, REFLECTING, DONE, AWAITING_USER, CANCELLED, FAILED`.
Terminal: `DONE, FAILED, CANCELLED`.

Every change is a `run.state_changed` event `{from_state, to_state, reason, round, review_cycle?, phase_ms}`, with these
exceptions: the first state comes with `run.created`, and failure and cancel arrive as `run.failed` / `run.cancelled`
(state in their payload `state` field) with no state_changed.

```
INTAKE -> PROFILING -> CONVENING -> DELIBERATING -> DECIDED
DECIDED -> EXAMINING           only if the tribunal runs (a dissenting seat exists, tribunal enabled)
DECIDED/EXAMINING -> DONE      deliverable "answer", or the user said "stop" after a contested tribunal
DECIDED/EXAMINING -> PLANNING  deliverable "plan" or "build"
PLANNING -> AWAITING_DELEGATION        plan ready; waits for POST /delegate (unless auto_delegate)
AWAITING_DELEGATION -> EXECUTING
EXECUTING -> REVIEWING
REVIEWING -> INTEGRATING       verdict accept
REVIEWING -> EXECUTING         verdict fix (up to [review] max_cycles fix cycles)
REVIEWING -> DELIBERATING      verdict replan (once); then PLANNING -> EXECUTING -> REVIEWING again
REVIEWING -> AWAITING_USER     otherwise: "accept it as it is, or discard it?"
INTEGRATING -> REFLECTING -> DONE
(rejected work) REVIEWING -> REFLECTING -> DONE, nothing written
any non-terminal -> AWAITING_USER -> back to the state it left   (council asks the user; see below)
any non-terminal -> CANCELLED  (POST /cancel)
any non-terminal -> FAILED     (exception; run.failed carries error and detail)
```

AWAITING_USER: the controller emits `run.state_changed` to AWAITING_USER, then `user.input_requested`
(`from_state` says where it will return). After `POST /input` it emits `user.input_received` and a state_changed
back to `resume_state`. The open question is also in `RunSnapshot.pending_input`.

Valid actions: delegate only in AWAITING_DELEGATION (else 409); input only while a question is open (else 409);
PATCH plan only in AWAITING_DELEGATION (else 409); cancel in any non-terminal state (else `{ok:false}`).

## 6. Event types

Envelope fields (`seq`, `ts`, `run_id`) are not repeated below. All payload fields are optional on the wire
except the ids shown in bold (`call_id`, `task_id`, `model_id`). Unknown keys are ignored. Nested objects
(`Plan`, `Decision`, `LineupRecord`, `CheckResult` and so on) are typed in `ui/src/types.ts`.

### Run

| Type | Fires when | Payload fields |
|---|---|---|
| `run.created` | POST /runs accepted | task, workspace, mode, deliverable, lineup_override, options, state, created_at |
| `run.state_changed` | any state change | from_state (null first time), to_state, reason, round, review_cycle, phase_ms |
| `run.completed` | terminal, success | state, outcome, final_text, decision, counters, files_written, finished_at |
| `run.failed` | terminal, exception | state, from_state, error, detail, counters, finished_at |
| `run.cancelled` | terminal, user cancel | state, from_state, reason, counters, finished_at |

### Setup and router

| Type | Fires when | Payload fields |
|---|---|---|
| `brief.ready` | workspace summarised | workspace, summary, file_count, languages, key_files, tree, cached, ms |
| `recall.ready` | chronicle entries recalled | entries, count, record_block, ms |
| `profile.ready` | task profiled | profile, model_id, ms |
| `router.candidates_scored` | models scored | candidates[{model_id, display, lab, q, eligible, reason}], lineups_considered, top, tier, k |
| `router.lineup_selected` | lineup chosen | lineup, models[ModelInfo], chair_model_id, wildcard_seat_no, score, mode, k, labs, overridden |

### Models (host)

| Type | Fires when | Payload fields |
|---|---|---|
| `model.loading` | load starts | **model_id**, display, lab, footprint_gib, serve_profile, mem_available_gib, reason, expected_load_s |
| `model.loaded` | load done | **model_id**, display, lab, footprint_gib, serve_profile, mem_available_gib, load_ms, ctx, parallel, endpoint |
| `model.unloaded` | unloaded | **model_id**, display, lab, footprint_gib, serve_profile, mem_available_gib, reason, freed_gib |
| `model.evicted` | evicted for room | same as unloaded, plus for_model_id |
| `model.failed` | load or serve failed | **model_id**, display, lab, footprint_gib, serve_profile, mem_available_gib, error, stage ("load"/"health"/"serve"), replaced_by |

### Deliberation

| Type | Fires when | Payload fields |
|---|---|---|
| `seat.assigned` | a model takes a seat | seat_no, model_id, display, lab, lens, is_wildcard, is_chair, q, label, replaces_model_id |
| `round.started` | a round opens | round, purpose, seats[], deadline_s, focus_crux_ids, is_review |
| `turn.started` | a model call begins | **call_id**, purpose, model_id, seat_no (null for non-seat calls), round, reasoning, max_output_tokens, attempt |
| `turn.delta` | answer token chunk (ephemeral) | **call_id**, seat_no, text |
| `turn.reasoning_delta` | reasoning chunk (ephemeral) | **call_id**, seat_no, text |
| `turn.completed` | call finished, valid | **call_id**, seat_no, round, purpose, model_id, tokens, tokens_in, tokens_out, tokens_reasoning, tps, ms, parsed, content, finish_reason, attempts, cached |
| `turn.invalid` | output failed validation | **call_id**, seat_no, round, purpose, model_id, error, attempts, will_retry, content_tail |
| `turn.timeout` | call timed out | **call_id**, seat_no, round, purpose, model_id, timeout_s, ms, will_retry |
| `options.clustered` | answers grouped into options | round, options[], tally, agreement, leading_option_id |
| `cruxes.extracted` | disagreements found | round, cruxes[] |
| `evidence.requested` | a check is requested | round, check_id, kind, spec, settles, crux_id, requested_by[] |
| `evidence.result` | a check finished | round, check_id, result, crux_id, crux_resolved |
| `ballot.cast` | a seat voted | seat_no, round, ballot, model_id, call_id, changed |
| `round.completed` | a round closes | round, options, tally, agreement, leading_option_id, valid_turns, failed_seats, converged, ms |
| `effort.planned` | once, after the lineup, before round 0 (standard mode, adaptive on, `effort` not "fixed") | level ("light"/"normal"/"heavy"), rounds[], deadline_s, reasoning, max_extra_rounds, difficulty ("easy"/"medium"/"hard"), rationale |
| `round.extended` | a close vote with no planned round left gets one more re-ballot (comes after `round.completed`, before the `consensus.failed` with next_step "round") | round (the added round), agreement, extra_used, extra_max, reason |

### Decision

| Type | Fires when | Payload fields |
|---|---|---|
| `consensus.reached` | agreement over threshold | round, option_id, agreement, threshold, tally, outcome, early |
| `consensus.failed` | no agreement yet | round, agreement, threshold, tally, leading_option_id, open_cruxes, reason, next_step ("round"/"majority"/"chair"/"user"/"deadlock") |
| `chair.started` | the Chair begins writing | call_id, model_id, seat_no, reason |
| `chair.delta` | Chair text chunk (ephemeral) | call_id, seat_no, text |
| `ratify.result` | seats vote on the Chair text | ratified, votes_for, votes_against, votes{seat_no text: bool}, objections, option_id |
| `decision.final` | decision made (re-emitted if the tribunal vindicates the outlier) | decision, options, ms |

### User

| Type | Fires when | Payload fields |
|---|---|---|
| `user.input_requested` | council asks the user | flat `UserQuestion`: question, options[], request_id, crux_id, context; plus from_state, source |
| `user.input_received` | POST /input accepted | request_id, choice, text, resume_state |

### Plan

| Type | Fires when | Payload fields |
|---|---|---|
| `plan.drafted` | plan written, or PATCH /plan | plan, version, task_count, model_id, call_id |
| `plan.linted` | lint ran | ok, version, errors, warnings, task_count, will_retry |
| `plan.reviewed` | cross-check done | ok, version, reviewer_seat_no, reviewer_model_id, issues, changes |
| `plan.ready` | plan final (again after a user edit) | plan, version, task_count, micro_count, senior_count, edited_by_user |

### Work

| Type | Fires when | Payload fields |
|---|---|---|
| `delegation.started` | workers released | task_count, task_ids, workers[ModelInfo], max_parallel, cycle, plan_version |
| `task.queued` | task queued | **task_id**, title, attempt, model_id, tier, status, kind, deps, write_set, cycle |
| `task.started` | attempt starts | **task_id**, title, attempt, model_id, tier, status, call_id, max_attempts, temperature |
| `task.delta` | worker token chunk (ephemeral) | **task_id**, attempt, call_id, text |
| `task.attempt_completed` | attempt ended | **task_id**, title, attempt, model_id, tier, status, ok, record, blocked, failing_check, error_tail, files_changed, tokens_in, tokens_out, tps, ms, will_retry |
| `check.started` | a check runs | task_id (null for global), attempt, check_id, check, level |
| `check.result` | a check finished | result, task_id, attempt, check_id, level, ok |
| `task.passed` | task done | **task_id**, title, attempt, model_id, tier, status, attempts, checks, failing_check, error_tail, reason, files_changed, ms |
| `task.failed` | task gave up | same as task.passed |
| `task.blocked` | task blocked | same as task.passed |
| `task.skipped` | dependency failed | same as task.passed, plus blocked_by[] |
| `task.escalated` | moved to a stronger worker | **task_id**, title, attempt, model_id, tier, status, to ("senior"/"council"), from_tier, to_tier, from_model_id, to_model_id, failing_check, reason |
| `integration.result` | staged checks or copy into workspace | ok, stage ("checks"/"copy"), checks, files_written, diff_stats, error |

### Review

| Type | Fires when | Payload fields |
|---|---|---|
| `review.started` | review cycle opens | cycle, report, seats[], max_cycles |
| `review.ballot` | a seat voted on the work | seat_no, model_id, cycle, ballot, call_id |
| `review.debate` | the first vote was split and the seats voted again after reading each other's ballots | cycle, tally_before, tally_after (each `{verdict: votes}`) |
| `review.final_say` | no agreement in time, so one randomly picked seat decided from the record | cycle, seat_no, model_id, verdict, reason |
| `review.verdict` | vote closed | verdict ("accept"/"fix"/"replan"/"ask_user"), tally, fixes, cycle, reason, next_state |

Review notes:

- Second-round ballots (after `review.debate`) are ordinary `review.ballot` events. They have no phase field; tell
  them apart by `call_id`, which contains `:rvd<cycle>:`. The final-say call id contains `:rvf<cycle>:`.
- `review.verdict.reason` is filled. Before a random-seat final say, `next_state` is `REVIEWING`.
- With `final_say = "random_seat"` the user is still asked when the council votes `ask_user` in an attended run (no
  `auto_input`, no `auto_delegate`). With `"user"` the user is always asked at the end ("accept" integrates, anything
  else discards).
- `review.started.report` and `RunSnapshot.work_report` are a `WorkReport`. Fields added with the review rework:
  - `final_checks: CheckResult[]`: every check re-run on the files as they are now. This is what reviewers judge.
  - `files: {path: string}`: current file contents, clipped.
  - `summary.superseded: number`: failed tasks whose files a later passed task rewrote. They are history, not
    current faults.
  - `tasks[].superseded_by: string|null`: id of the later passed task that rewrote all files of this task.
  - `CheckResult.invalid: boolean`: the check itself is broken (for example a test command that ran zero tests). It
    says nothing about the work. Show it as "bad check", not as a failure. `ui/src/types.ts` does not declare these
    yet.

### Chronicle (memory)

| Type | Fires when | Payload fields |
|---|---|---|
| `memory.candidate` | lesson proposed | candidate, index, total |
| `memory.verdict` | panel judged a candidate | candidate_id, seat_no, model_id, verdict |
| `memory.committed` | entry written | entry, candidate_id, action, superseded_id, merged_into_id |
| `memory.contested` | entry contested | entry_id, entry, candidate_id, reason |
| `memory.retracted` | entry retracted | entry_id, entry, reason, by ("panel"/"user"/"aging") |

### Telemetry

| Type | Fires when | Payload fields |
|---|---|---|
| `telemetry.tick` | about every `[telemetry] tick_s` (1 s) per live run | flat `TelemetrySnapshot` (ts, resident, cloud_equiv_usd, ... see types.ts) |

### Tribunal, corrections (new)

| Type | Fires when | Payload fields |
|---|---|---|
| `tribunal.started` | cross-examination of a dissenting seat begins (state EXAMINING) | outlier_seat, outlier_model_id, distance, option_id, outlier_option_id, examiners[], judges[], questions |
| `tribunal.question` | an examiner asks | seat_no, model_id, index, question, outlier_seat, call_id |
| `tribunal.answer` | the outlier answers | seat_no, model_id, index, answer, call_id |
| `tribunal.verdict` | a judge rules | seat_no, model_id, verdict, call_id |
| `tribunal.outcome` | tribunal ends | outcome, seat_no, model_id, contested_after_review, correction_eligible, reason, ms |
| `correction.recorded` | outlier conceded or failed, training example saved | correction, seat_no, model_id, project, dataset_size |

### Probe and bench

| Type | Fires when | Payload fields |
|---|---|---|
| `probe.scores` | claim reliability scored for a seat | seat_no, model_id, round, scores[], probe_status, shown_to_council |
| `probe.trained` | a probe was trained | probe, model_id, validated, layers_tried, auroc_by_layer, top_dims, ms |
| `bench.started` | a bench run starts | request, bench_id, modes, models, tasks, total |
| `bench.progress` | one unit done | bench_id, mode, model_id, done, total, correct, result |
| `bench.completed` | bench ends | bench_id, summary[], results_path, ms, error |

Bench events use the bench id as their `run_id`, so they are not part of a normal run stream.

### Lie detector, steering, memory plan (1.5)

| Type | Fires when | Payload fields |
|---|---|---|
| `memory.planned` | once per run, after the router picks a lineup and before any model loads | plan (a `MemoryPlan`: fits, budget_gib, total_gib, per_model, num_ctx, roles, shared_roles, dropped, notes) |
| `steer.applied` | a seated model was started with a steering vector (llamacpp driver only), before `seat.assigned` | project, model_id, scale, layers[], source (the vector file) |
| `steer.trained` | a steering vector was trained after a run that recorded a correction, before `run.completed` | project, model_id, examples, scale (null: no strength passed the sanity check), active, reason |
| `lie.report` | after round 0, when `[lie] enabled` | report (a `LieReport`, section 3a), flagged (count), watched (count) |

Notes:

- `memory.planned.plan.dropped` lists the models that did not fit and `notes` says in plain sentences what the plan
  changed: seats dropped (lowest scored first, never below 2), work roles moved to seated models, a note that the
  total memory is what the host budget sees (mock mode) and that Ollama gives one context to every model. Show the
  notes. The `router.lineup_selected` that follows already has the smaller `k`.
- `steer.applied` is not emitted in mock mode: the mock driver cannot steer. `steer.trained` can appear with
  `active: false`; that is a normal result, not an error.
- `lie.report` is not emitted when `[lie]` is off. With `[probe]` off and `[lie]` on, only this event is made
  (behaviour signals, no probe). `probe.scores` still carries the per-seat claim scores of the 1.0 probe.
- The open council protocol events (`msg.started`, `msg.delta`, `msg.thinking`, `msg.ended`, `msg.card`, `msg.lie`,
  `table.tally`) are in `event_types.py`; this guide does not describe them.

## 7. Typical event order

Interleaving is not strict: `model.*`, `telemetry.tick` and `turn.*` events can appear between any two lines below.

### Answer run (`deliverable: "answer"`)

```
run.created
run.state_changed  INTAKE
run.state_changed  PROFILING
brief.ready, profile.ready, recall.ready
run.state_changed  CONVENING
memory.planned                                   (1.5: before the router events)
router.candidates_scored, router.lineup_selected
model.loading / model.loaded (per model), [steer.applied], seat.assigned (per seat)
effort.planned                                  (standard mode with adaptive effort)
run.state_changed  DELIBERATING
round.started (0, blind drafts)
  turn.started, turn.delta*, turn.completed (per seat)   [turn.invalid / turn.timeout on trouble]
  options.clustered
round.completed
  quick mode stops here; standard and deep continue with:
round.started 1 (critique), 2 (ballot), 3 (focused)
  turn.*, cruxes.extracted, evidence.requested / evidence.result, ballot.cast, options.clustered
round.completed
[round.extended, consensus.failed (next_step "round"), round.started 3 ... : repeats up to max_extra_rounds]
consensus.reached | consensus.failed
chair.started, chair.delta*, ratify.result      (when the Chair is needed)
decision.final
[user.input_requested -> user.input_received]   (when the decision needs the user; AWAITING_USER in between)
run.state_changed  DECIDED
[run.state_changed EXAMINING, tribunal.started, tribunal.question, tribunal.answer, tribunal.verdict,
 tribunal.outcome, correction.recorded, decision.final again if the outlier was vindicated]
run.state_changed  DONE
run.completed
```

Probe events (`probe.scores`) appear during deliberation when the probe is on. `lie.report` comes right after
round 0. `steer.trained` can come after the tribunal and reflection, just before `run.completed`.

### Build run (`deliverable: "build"`, or "plan")

Same as above up to DECIDED / EXAMINING, then:

```
run.state_changed  PLANNING
plan.drafted, plan.linted, plan.reviewed, plan.ready
run.state_changed  AWAITING_DELEGATION        <- UI shows plan; optional PATCH /plan; then POST /delegate
[plan.drafted (edited), plan.ready (edited_by_user: true)]
run.state_changed  EXECUTING
delegation.started
task.queued ...
task.started, task.delta*, task.attempt_completed, check.started, check.result   (per task, in parallel)
task.passed | task.failed | task.blocked | task.skipped ; task.escalated on retry with a stronger worker
run.state_changed  REVIEWING
review.started, review.ballot (per seat), [review.debate + a second review.ballot per seat], [review.final_say], review.verdict
  accept -> continue
  fix    -> run.state_changed EXECUTING (fix cycle), then REVIEWING again
  replan -> run.state_changed DELIBERATING, then PLANNING ... as above
  else   -> AWAITING_USER with an accept/discard question
run.state_changed  INTEGRATING                 (only when work is accepted)
integration.result
run.state_changed  REFLECTING
memory.candidate, memory.verdict, memory.committed | memory.contested | memory.retracted
run.state_changed  DONE
run.completed      (final_text, files_written, counters)
```

After the dissenting seat defends itself in the tribunal, a plan or build run asks "Proceed with the council's
decision?" (options `proceed` / `stop`) unless `options.auto_input` is set. `stop` ends the run at DONE.

Demo runs (`options.demo: true`) replay a scripted build order and pause before EXECUTING until delegate.

## 8. Reusing `ui/src/types.ts`, `api.ts`, `store.ts` in another React app

Copy the three files into your app as one folder (they import each other with `./types`).

- `types.ts`: types plus the constant `EVENT_TYPES`. `CouncilEvent<T>` narrows `payload` by `type` via `PayloadMap`.
- `store.ts`: pure TypeScript, no React, no fetch, no dependencies. It only imports from `./types`.
  - `initialRunState()`, `initialAppState()`.
  - `reduce(runState, event)`: folds one event into one `RunViewState`. Pure and immutable. Returns the same
    object when nothing changed. Drops a stored event whose `seq <= lastSeq` (safe replay). Never logs or
    de-duplicates `turn.delta`, `turn.reasoning_delta`, `chair.delta`, `task.delta`, `telemetry.tick`
    (`EPHEMERAL_EVENT_TYPES`).
  - `reduceAll(state, events[])`, `reduceApp(appState, event)` (many runs, mirrors memory events into `chronicle`),
    `applySnapshot(state, snapshot)` (first paint or after reconnect).
  - Selectors: `selectActiveSeat`, `selectProgress` (0 to 1), `selectTaskCounts`, `selectResidentGib`, `selectActiveRun`.
  - `createStore(initial)` gives `getState / setState / subscribe`, shaped for `useSyncExternalStore`.
  - Caps: `EVENT_LOG_MAX = 500` log entries, `TELEMETRY_HISTORY_MAX = 120` snapshots.
- `api.ts`: typed `fetch` wrappers (`startRun, getRun, delegate, sendInput, cancelRun, patchPlan, routerPreview,
  listModels, loadModel, unloadModel, listChronicle, patchChronicle, deleteChronicle, getTelemetry, health`) and
  `subscribeEvents(runId, since, onEvent, onError?) -> unsubscribe`. Failures throw `ApiError(status, message)`
  (status 0 = network). `subscribeEvents` uses `EventSource`, registers a listener for every name in `EVENT_TYPES`,
  skips duplicate `seq`, reconnects after 1 s with `?since=<last seq>`, and closes itself on a terminal event.
  - Base URL: `import.meta.env.VITE_API_BASE`, default `http://127.0.0.1:8765`. That is Vite syntax. In another
    bundler, replace that one line.
  - `health()` probes `GET /telemetry`, not `/health`. Use `fetch('/health')` yourself if you want the `mock` flag.

### Minimal wiring
```tsx
const store = createStore<RunViewState>(initialRunState());
export async function begin(task: string) {
  const { run_id } = await startRun({ task, mode: 'quick', deliverable: 'answer' });
  const snap = await getRun(run_id);
  store.setState((s) => applySnapshot(s, snap));                   // first paint
  return subscribeEvents(run_id, store.getState().lastSeq,         // returns unsubscribe
    (ev) => store.setState((s) => reduce(s, ev)));
}
export const useRun = () => useSyncExternalStore(store.subscribe, store.getState);
```

Notes:

- `applySnapshot` sets `lastSeq` from `snapshot.last_seq`, so stored events up to it are not replayed into the view.
  Detail that only the stream carries (seat text, rounds, turns) is then missing for events before that point.
  For a full view of a run you open late, skip `applySnapshot` and replay from `since=0`: `subscribeEvents(id, 0, ...)`.
- For several runs use `reduceApp` with an `AppState`; set `activeRunId` yourself.
- `store.ts` has dedicated cases for run, setup, router, model, deliberation, decision, user, plan, work, review,
  memory, telemetry and the newer event families. `RunViewState` fields for those: `tribunal` (`TribunalView`:
  outlier seat and model, questions, answers, verdicts, outcome), `corrections: Correction[]`,
  `claimScores: Record<seat_no, ClaimScore[]>`, `probes: Probe[]`
  (latest per model) and `bench: BenchView | null` (`benchId, status, progress, summary, error`).
  `applySnapshot` fills `tribunal`, `corrections` and `claimScores` from the snapshot fields of the same names.
- `types.ts` `ModelEntry` does not yet declare `ollama_options` or `speculative`; the JSON has them, so extend the
  interface if you read them.

## 9. Model entries and seats

The registry holds 11 models on the box. A run seats 2 to 6 of them: six is the standard and deep default
(`[router] k = 6`, `[chamber.modes.*] k`), quick uses three, and the run option `k` (section 3) overrides it. The
memory plan can seat fewer than `k` when the models do not fit.
The six lenses are in `config/lenses.json`: builder, skeptic, first_principles, risk, user_advocate, specialist. Each
seat is filled by one registry model, with a Chair and a wildcard seat flagged in `seat.assigned`
(`is_chair`, `is_wildcard`) and `router.lineup_selected` (`chair_model_id`, `wildcard_seat_no`).

`GET /models` (and `config/models.json`) entries can carry two extra fields for the Ollama driver:

- `ollama_options: object` (default `{}`): extra Ollama request options passed through untouched, for example
  `{"draft_num_predict": 4}`. The gateway merges, lowest to highest priority: `[ollama] default_draft_num_predict`
  (only for entries with `speculative` not `"none"`; 0 means leave to Ollama), the entry's `ollama_options`, then a
  per-call override used by probes.
- `speculative: "none" | "mtp" | "draft"` (default `"none"`): a label for UI and probes saying the model uses a built-in
  multi-token-prediction head or a Modelfile draft model. It does not switch anything on by itself.

## 10. What is mock in mock mode

`RunController.build_mock()` runs the real pipeline, store, event bus, router, chamber and chronicle. These parts
are replaced:

| Part | Mock behaviour |
|---|---|
| Model host | `MockDriver`: "loads" a model after about 0.4 s. No process, no Ollama, no GPU. `model.*` events are real in shape. |
| Gateway | `MockResponder` (seed 0) answers every model call with generated, schema-valid text after 0.2 to 0.9 s. Answers are canned, not intelligent. Same event types and fields as real. |
| Embedder | `MockEmbedder`. Used for clustering and recall. |
| RAM budget | Fake machine: 121.7 GiB total, 6.4 GiB system. Footprints come from the registry. |
| Telemetry | `FakeSampler`: smooth invented numbers and model names. `cloud_equiv_usd` is derived from real counters. |
| Registry | `config/models.json`, or built-in demo models if that file is empty. |
| Probe | Mock activation source. A probe trained in mock mode is for show. |
| Corrections | Really written to the store and to a dataset file. Nothing is trained from them. |
| Steering | `MockDriver` cannot steer, so a mock run has no `steer.applied`. A steering vector trained in mock mode is made from invented activations and proves only the plumbing. |
| Lie detector | Behaviour signals are real code on canned text; a probe from `source = "mock"` is for show. `lie.report` has the real shape. |
| Memory plan | Real code. The machine total is what the mock host budget sees, not `/proc/meminfo`; a plan note says so. |
| Workspace | Real. A build run with a `workspace` really reads it, runs checks and writes files on integrate. Without one, work goes to a folder under the data home. |

Delegation is manual unless `options.auto_delegate` is true. `options.demo: true` is a scripted replay needing no gateway.

Switch to real as in section 1 (`gateway.mock = false`, `host.driver = "llamacpp"` on the box or `"ollama"` as the fallback, restart). The wire contract is the same.

## 11. Known rough edges (current code)

1. Late joiners miss deltas: they are live only, never replayed (section 4).
2. `telemetry.tick` is stored, so `since=0` replays every tick of a long run.
3. `GET /runs` rows are raw store rows, not a typed contract.
4. `api.ts` has no wrappers for the bench, corrections, probes, chronicle-export or config routes, and
   `health()` probes `/telemetry`, not `/health`.
5. `ui/src/types.ts` `ModelEntry` lacks `ollama_options` and `speculative` (section 9).
6. `api.ts` `patchPlan` returns `unknown`; the real body is `{ok, plan, issues}`.
7. `ui/src/types.ts` has no types for `effort.planned`, `round.extended`, `review.debate`, `review.final_say`, and no
   `final_checks`, `files`, `superseded`, `superseded_by` or `invalid` fields (section 6, Review notes).
8. `ui/src/types.ts` and `api.ts` do not know the 1.5 additions: the routes in section 3a, the events `lie.report`,
   `steer.applied`, `steer.trained`, `memory.planned`, the `msg.*` events, and the run option `k`. Until they do, an
   `EventSource` listener per name is needed (`EVENT_TYPES` has no entry for them) or the events are dropped.
9. Everything new in 1.5 is proven in mock mode only, except the steering experiment (see `docs/V15.md`). The routes and
   events have the right shape; their numbers on the real box are not yet seen.
