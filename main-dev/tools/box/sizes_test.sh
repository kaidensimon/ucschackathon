#!/bin/bash
# Three questions at three council sizes (2, 4, 6). Logs: /tmp/size2.log, /tmp/size4.log, /tmp/size6.log.
# Sequential; a failed run does not stop the next one.
set -u
cd ~/council/main-dev; export COUNCIL_HOME=~/council/box; PY=~/council/venv/bin/python

run_size(){ # k question
  local k="$1" q="$2" log="/tmp/size$1.log" t0 rc
  echo; echo "##### size $k $(date +%T)"; echo "question: $q"
  t0=$(date +%s)
  timeout 2400 $PY -m council.cli run "$q" --k "$k" --mode standard > "$log" 2>&1; rc=$?
  echo "exit $rc, elapsed $(( $(date +%s) - t0 )) s, log $log"
  $PY tools/box/summarize_run.py >> "$log" 2>&1
  tail -n 15 "$log" | cut -c1-300
}

run_size 2 "Is 0.1 + 0.2 == 0.3 in Python? Answer yes or no and explain in two sentences."
run_size 4 "A startup must choose one: PostgreSQL or MongoDB for a new billing system. Give one recommendation."
run_size 6 "Should a team of five rewrite a working 80,000-line Python 2 codebase in Python 3 incrementally or all at once? Give one recommendation."
echo; echo "##### ALL DONE $(date +%T)"
