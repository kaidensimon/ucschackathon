#!/bin/bash
# V15 box test: unit tests, council Ollama, contested question, build test, run summary, probe smoke.
# Keeps going after a failing step. Prints PASS / FAIL / SKIP per step and a final count.
# Logs: /tmp/v15_tests.log /tmp/v15_ollama.log /tmp/v15_question.log /tmp/v15_build.log
#       /tmp/v15_summary.log /tmp/v15_probe.log
set -u

cd ~/council/main-dev || { echo "FAIL: ~/council/main-dev missing"; exit 1; }
export COUNCIL_HOME=~/council/box
VENV=~/council/venv
if [ -f "$VENV/bin/activate" ]; then
  . "$VENV/bin/activate"
else
  echo "WARN: $VENV/bin/activate missing, falling back to PATH python"
fi
PY="$VENV/bin/python"
[ -x "$PY" ] || PY=python
WS=/tmp/ws_v15

PASS=0; FAIL=0; SKIP=0
report(){ # $1 step name, $2 PASS|FAIL|SKIP, $3 log path
  case "$2" in
    PASS) PASS=$((PASS+1));;
    SKIP) SKIP=$((SKIP+1));;
    *) FAIL=$((FAIL+1));;
  esac
  echo "$2  $1  (log: $3)"
}

# STEP 1: unit tests
LOG=/tmp/v15_tests.log
echo; echo "##### STEP 1 unit tests $(date +%T)  log: $LOG"
$PY -m unittest discover -s tests > "$LOG" 2>&1; rc=$?
tail -3 "$LOG"
if [ "$rc" -eq 0 ]; then report "step 1 unit tests" PASS "$LOG"; else report "step 1 unit tests (rc $rc)" FAIL "$LOG"; fi

# STEP 2: council Ollama on 11435 answers /api/tags
LOG=/tmp/v15_ollama.log
echo; echo "##### STEP 2 council ollama 11435 $(date +%T)  log: $LOG"
curl -sf -m 10 http://127.0.0.1:11435/api/tags > "$LOG" 2>&1; rc=$?
head -c 300 "$LOG"; echo
if [ "$rc" -eq 0 ] && grep -q '"models"' "$LOG"; then report "step 2 ollama 11435 /api/tags" PASS "$LOG"; else report "step 2 ollama 11435 /api/tags (rc $rc)" FAIL "$LOG"; fi

# STEP 3: contested question, standard mode, 40 minute timeout (same question as full_test.sh STEP 4)
Q="A startup with 3 engineers must ship an internal analytics dashboard in 6 weeks. Should they build it on a single Postgres database with materialized views, or adopt a dedicated columnar warehouse (ClickHouse)? Pick one and justify it. Data volume: 40 million events per day, 20 internal users."
LOG=/tmp/v15_question.log
echo; echo "##### STEP 3 contested question (standard, 40 min) $(date +%T)  log: $LOG"
timeout 2400 $PY -m council.cli run "$Q" --mode standard > "$LOG" 2>&1; rc=$?
echo "exit $rc"
if [ "$rc" -eq 0 ]; then report "step 3 contested question" PASS "$LOG"; else report "step 3 contested question (rc $rc)" FAIL "$LOG"; fi

# STEP 4: build test (reuse build_test.sh, pointed at a fresh /tmp/ws_v15)
LOG=/tmp/v15_build.log
BT=/tmp/v15_build_test.sh
echo; echo "##### STEP 4 build test into $WS $(date +%T)  log: $LOG"
sed "s#/tmp/ws6#$WS#g" tools/box/build_test.sh > "$BT"
bash "$BT" > "$LOG" 2>&1; rc=$?
cat "$LOG"
if [ "$rc" -eq 0 ] && grep -q '^exit 0' "$LOG" && grep -q '^OK' "$LOG"; then
  report "step 4 build test" PASS "$LOG"
else
  report "step 4 build test (rc $rc)" FAIL "$LOG"
fi

# STEP 5: summary of the last run
LOG=/tmp/v15_summary.log
echo; echo "##### STEP 5 run summary $(date +%T)  log: $LOG"
python3 tools/box/summarize_run.py 2>&1 | tee "$LOG"; rc=${PIPESTATUS[0]}
if [ "$rc" -eq 0 ]; then report "step 5 summarize last run" PASS "$LOG"; else report "step 5 summarize last run (rc $rc)" FAIL "$LOG"; fi

# STEP 6: probe smoke test (only if the script exists)
LOG=/tmp/v15_probe.log
echo; echo "##### STEP 6 probe smoke $(date +%T)  log: $LOG"
if [ -f tools/box/probe_smoke.py ]; then
  timeout 1800 python3 tools/box/probe_smoke.py --tag granite4.1:8b-q8_0 > "$LOG" 2>&1; rc=$?
  tail -5 "$LOG"
  if [ "$rc" -eq 0 ]; then report "step 6 probe smoke granite4.1:8b-q8_0" PASS "$LOG"; else report "step 6 probe smoke granite4.1:8b-q8_0 (rc $rc)" FAIL "$LOG"; fi
else
  echo "tools/box/probe_smoke.py not found" > "$LOG"
  report "step 6 probe smoke (script missing)" SKIP "$LOG"
fi

TOTAL=$((PASS+FAIL+SKIP))
echo
echo "##### RESULT: $PASS PASS, $FAIL FAIL, $SKIP SKIP of $TOTAL steps $(date +%T)"
if [ "$FAIL" -eq 0 ]; then exit 0; fi
exit 1
