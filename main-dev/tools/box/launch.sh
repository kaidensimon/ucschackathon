#!/usr/bin/env bash
# Start Syndicate: the council engine, then the app window. Closing the window stops the engine
# and unloads the models. This is what the desktop shortcut runs.
BASE="${COUNCIL_BASE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
export COUNCIL_BASE="$BASE"
SRC="$BASE/main-dev"
mkdir -p "$BASE/logs"

bash "$SRC/tools/box/run_app.sh" 2>&1 | tee "$BASE/logs/launch.log"

cd "$SRC/ui_partner/ui" || exit 1
GX10_DEV_URL=http://127.0.0.1:4173 env -u ELECTRON_RUN_AS_NODE \
  "$BASE/node_modules/.bin/electron" --no-sandbox . >> "$BASE/logs/electron.log" 2>&1

# the window was closed: stop the engine and free the memory
bash "$SRC/tools/box/run_app.sh" stop >> "$BASE/logs/launch.log" 2>&1
bash "$SRC/tools/box/stop_models.sh" >> "$BASE/logs/launch.log" 2>&1
