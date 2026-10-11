# tools/box

Scripts for the ASUS GX10. Full runbook: `docs/BOX.md`. Code is edited on the Windows machine and copied over by `tools/deploy.sh`; never edit on the box.

| File | Runs on | What it does |
|---|---|---|
| `start_council_ollama.sh` | box | Starts the council's own Ollama on port 11435 (`stop` stops it). |
| `make_config.py` | box | Writes `~/council/box/config/council.toml` (real mode, longer deadlines, Ollama port 11435). Driver from `COUNCIL_DRIVER`: `llamacpp` (default) or `ollama`. |
| `make_registry.py` | box | Writes `~/council/box/config/models.json` from the models the 11435 Ollama has installed. Fills RAM, speed, JSON and think results from `model_checks.json`; a model whose check failed is `quarantined`. |
| `verify_models.py` | box | Checks size and sha256 of the files of the council's models in the Ollama store. `--all` checks every model. |
| `full_test.sh` | box | Long end-to-end sequence: questions, build, memory, benchmark, API. Log: `/tmp/s*.log`. |
| `build_test.sh` | box | One real build into an empty folder. Log: `/tmp/s6.log`. |
| `summarize_run.py` | box | Prints a short summary of the latest run from the database. |
| `check_models.py` | box | Loads each council model alone (the eleven in `COUNCIL_TAGS`), measures size, speed, JSON and think support; writes `~/council/box/model_checks.json`. `--all` checks every installed model. |
| `specdec_test.py` | box | Tokens per second with draft_num_predict 0, 4, 8 for one model. |
| `sizes_test.sh` | box | Three questions at council sizes 2, 4, 6 (`--k N --mode standard`). Logs: `/tmp/size2.log`, `/tmp/size4.log`, `/tmp/size6.log`; prints elapsed seconds per run. |
| `stop_models.sh` | box | Kills leftover council `llama-server` processes (ports 181xx) and unloads every model from both Ollama instances (11434, 11435). |
| `failure_drill.sh` | box | Unloads a seated model mid-run, then SIGTERMs a run; prints PASS/FAIL per drill. |

Quick start: `bash tools/box/start_council_ollama.sh`
