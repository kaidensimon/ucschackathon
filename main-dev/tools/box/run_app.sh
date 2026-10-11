#!/usr/bin/env bash
# Start the council backend (8765) and the UI (4173). Usage: run_app.sh [--no-ui] | stop
#
# The source folder (main-dev) is only read. Everything that is made while running lives beside it:
#   ~/council/venv          Python packages          ~/council/node_modules  UI packages
#   ~/council/box           config, database, probes ~/council/ui-dist       built UI page
#   ~/council/logs          logs                     ~/council/pycache       Python byte code
# the folder that holds main-dev (found from where this script is, so the folder can be moved or renamed)
BASE="${COUNCIL_BASE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
SRC="$BASE/main-dev"
UI="$SRC/ui_partner/ui"
BIN="$BASE/node_modules/.bin"
LOGS="$BASE/logs"
API="http://127.0.0.1:8765"
mkdir -p "$LOGS"

listening() { curl -s -o /dev/null --max-time 2 "$1"; }

if [ "$1" = "stop" ]; then
  pkill -f "[c]ouncil.api.server" && echo "backend stopped" || echo "backend not running"
  pkill -f "[v]ite preview" && echo "ui stopped" || echo "ui not running"
  exit 0
fi

# ---- backend ----
if listening "$API/ui/health"; then
  echo "backend already up"
else
  cd "$SRC" || { echo "no $SRC"; exit 1; }
  # shellcheck disable=SC1091
  source "$BASE/venv/bin/activate"
  export COUNCIL_HOME="$BASE/box"
  export PYTHONPYCACHEPREFIX="$BASE/pycache"
  # The trained lie-detector probes ship with the source (probes/). A fresh machine starts from them.
  if [ -d "$SRC/probes" ] && [ ! -d "$COUNCIL_HOME/probes" ]; then
    mkdir -p "$COUNCIL_HOME" && cp -r "$SRC/probes" "$COUNCIL_HOME/probes" && echo "probes copied from the source folder"
  fi
  nohup python -m council.api.server > "$LOGS/api.log" 2>&1 &
  echo "backend starting, log $LOGS/api.log"
  ok=0
  for _ in $(seq 1 60); do
    if listening "$API/ui/health"; then ok=1; break; fi
    sleep 1
  done
  if [ "$ok" = 1 ]; then
    echo "health:"; curl -s "$API/ui/health"; echo
  else
    echo "backend did NOT answer in 60 s. see $LOGS/api.log"; tail -20 "$LOGS/api.log"
  fi
fi

[ "$1" = "--no-ui" ] && exit 0

# ---- ui ----
[ -d "$BASE/ui-dist" ] || bash "$SRC/tools/box/build_ui.sh"
cd "$UI" || exit 1
export GX10_VITE_CACHE="$BASE/vite-cache"
if listening "http://127.0.0.1:4173/"; then
  echo "ui already up"
else
  nohup "$BIN/vite" preview --outDir "$BASE/ui-dist" --host 127.0.0.1 --port 4173 > "$LOGS/ui.log" 2>&1 &
  sleep 3
  echo "ui log $LOGS/ui.log"
fi
echo "open http://127.0.0.1:4173"
echo "mock only: open http://127.0.0.1:4173/?mock"
echo "app window (at the box screen): cd $UI && GX10_DEV_URL=http://127.0.0.1:4173 env -u ELECTRON_RUN_AS_NODE $BIN/electron --no-sandbox ."
