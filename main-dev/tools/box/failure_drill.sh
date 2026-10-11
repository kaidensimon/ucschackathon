#!/usr/bin/env bash
# Failure drills on the box. Needs the council Ollama on 11435 and the real-mode config.
#   drill 1: unload one seated model while round 0 runs; does the run still finish?
#   drill 2: SIGTERM the run process; does the runs table show a terminal or resumable state?
# Prints PASS/FAIL per drill. Run:  bash tools/box/failure_drill.sh
set -u
export COUNCIL_HOME="$HOME/council/box"
PY="$HOME/council/venv/bin/python"
DB="$COUNCIL_HOME/db/council.db"
OLLAMA="http://127.0.0.1:11435"
cd "$HOME/council/main-dev" || { echo "FAIL: no ~/council/main-dev"; exit 1; }
TASK="A bat and a ball cost 1.10 dollars in total. The bat costs 1.00 dollar more than the ball. How much does the ball cost? Explain briefly."

q() { python3 - "$DB" "$@" <<'EOF'
import sqlite3, sys
db, sql = sys.argv[1], sys.argv[2]
args = sys.argv[3:]
try:
    c = sqlite3.connect(db, timeout=10)
    r = c.execute(sql, args).fetchone()
    print("" if r is None or r[0] is None else r[0])
except Exception:
    print("")
EOF
}

latest_run() { q "SELECT id FROM runs ORDER BY created DESC LIMIT 1"; }
run_state()  { q "SELECT state FROM runs WHERE id=?" "$1"; }
has_round0() { q "SELECT count(*) FROM events WHERE run_id=? AND type='round.started'" "$1"; }
terminal_evt() { q "SELECT type FROM events WHERE run_id=? AND type IN ('run.completed','run.failed','run.cancelled') ORDER BY seq DESC LIMIT 1" "$1"; }

start_run() {  # sets RUN_PID and RUN_ID; returns 1 if round 0 never started
  local before; before=$(latest_run)
  nohup "$PY" -m council.cli run "$TASK" --mode standard > "$1" 2>&1 &
  RUN_PID=$!
  RUN_ID=""
  for _ in $(seq 1 180); do
    cur=$(latest_run)
    if [ -n "$cur" ] && [ "$cur" != "$before" ]; then RUN_ID=$cur; fi
    if [ -n "$RUN_ID" ]; then n=$(has_round0 "$RUN_ID"); if [ -n "$n" ] && [ "$n" != "0" ]; then return 0; fi; fi
    kill -0 "$RUN_PID" 2>/dev/null || return 1
    sleep 2
  done
  return 1
}

wait_end() {  # wait up to $2 s for pid $1
  for _ in $(seq 1 "$2"); do kill -0 "$1" 2>/dev/null || return 0; sleep 1; done
  return 1
}

echo "=== drill 1: unload a seated model during round 0"
if ! start_run /tmp/drill1.log; then
  echo "FAIL drill 1: round 0 never started (see /tmp/drill1.log)"; kill "$RUN_PID" 2>/dev/null
else
  # seats hold registry ids; map id -> ollama tag through models.json
  SEAT_ID=$(q "SELECT model_id FROM seats WHERE run_id=? ORDER BY seat_no LIMIT 1" "$RUN_ID")
  MODEL=$(python3 - "$COUNCIL_HOME/config/models.json" "$SEAT_ID" <<'EOF'
import json, sys
for m in json.load(open(sys.argv[1])):
    if m["id"] == sys.argv[2]: print(m["ollama_tag"])
EOF
)
  if [ -z "$MODEL" ]; then echo "FAIL drill 1: could not find a seated model (seat id '$SEAT_ID')"; kill "$RUN_PID" 2>/dev/null
  else
    echo "run $RUN_ID; unloading $MODEL"
    curl -s -m 60 "$OLLAMA/api/generate" -d "{\"model\":\"$MODEL\",\"keep_alive\":0}" > /dev/null
    if wait_end "$RUN_PID" 2400; then
      EVT=$(terminal_evt "$RUN_ID"); ST=$(run_state "$RUN_ID")
      echo "run ended: event=${EVT:-none} state=${ST:-?}"
      if [ "$EVT" = "run.completed" ]; then echo "PASS drill 1: run completed after the unload"
      elif [ -n "$EVT" ]; then echo "PASS drill 1: run ended cleanly with $EVT (handled the failure, did not hang)"
      else echo "FAIL drill 1: process exited with no terminal event"; fi
    else
      echo "FAIL drill 1: run still going after 40 minutes"; kill "$RUN_PID" 2>/dev/null
    fi
  fi
fi

echo "=== drill 2: SIGTERM the run process"
if ! start_run /tmp/drill2.log; then
  echo "FAIL drill 2: round 0 never started (see /tmp/drill2.log)"; kill "$RUN_PID" 2>/dev/null
else
  echo "run $RUN_ID; sending SIGTERM to $RUN_PID"
  kill -TERM "$RUN_PID"
  wait_end "$RUN_PID" 60 || { echo "process ignored SIGTERM; sending KILL"; kill -KILL "$RUN_PID"; }
  sleep 2
  ST=$(run_state "$RUN_ID"); EVT=$(terminal_evt "$RUN_ID")
  echo "runs table: state=${ST:-?} terminal_event=${EVT:-none}"
  case "$ST" in
    DONE|FAILED|CANCELLED|AWAITING_USER) echo "PASS drill 2: state $ST is terminal or resumable" ;;
    *) if [ -n "$EVT" ]; then echo "PASS drill 2: terminal event $EVT recorded"
       else echo "FAIL drill 2: state '${ST:-?}' is neither terminal nor resumable (run left dangling)"; fi ;;
  esac
fi
