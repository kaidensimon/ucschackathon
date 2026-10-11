#!/bin/bash
cd ~/council/main-dev; export COUNCIL_HOME=~/council/box; PY=~/council/venv/bin/python
step(){ echo; echo "##### $1 $(date +%T)"; }
step "STEP 3 easy question"
timeout 1500 $PY -m council.cli run "A bat and a ball cost 1.10 dollars in total. The bat costs 1.00 dollar more than the ball. How much does the ball cost? Explain briefly." --mode standard > /tmp/s3.log 2>&1; echo "exit $?"; $PY tools/box/summarize_run.py
step "STEP 4 contested question"
timeout 2400 $PY -m council.cli run "A startup with 3 engineers must ship an internal analytics dashboard in 6 weeks. Should they build it on a single Postgres database with materialized views, or adopt a dedicated columnar warehouse (ClickHouse)? Pick one and justify it. Data volume: 40 million events per day, 20 internal users." --mode standard > /tmp/s4.log 2>&1; echo "exit $?"; $PY tools/box/summarize_run.py
step "STEP 6 real build"
rm -rf /tmp/ws6 && mkdir /tmp/ws6
timeout 3600 $PY -m council.cli build "Create a small Python package named textstats with a function word_count(text) returning a dict of lowercase word frequencies and a function top_n(text, n) returning the n most common words, plus unittest tests in a tests folder." --workspace /tmp/ws6 --auto-delegate > /tmp/s6.log 2>&1; echo "exit $?"; $PY tools/box/summarize_run.py; echo "--- files"; find /tmp/ws6 -type f | head -20; (cd /tmp/ws6 && $PY -m unittest discover -s tests 2>&1 | tail -4)
step "STEP 7 second run in same workspace (memory and corrections recall)"
timeout 1500 $PY -m council.cli run "For the textstats package, should word_count treat hyphenated words as one word or two? Decide." --mode standard > /tmp/s7.log 2>&1; echo "exit $?"; $PY tools/box/summarize_run.py; $PY -m council.cli chronicle export 2>&1 | head -30
step "STEP 8 benchmark, 12 test tasks"
timeout 5400 $PY -m council.cli bench --tasks bench/tasks/sample.jsonl --modes "solo:*,council_vote_only,council" --limit 12 > /tmp/s8.log 2>&1; echo "exit $?"; tail -25 /tmp/s8.log | cut -c1-260
step "STEP 9 API server and live stream"
COUNCIL_PORT=8765 nohup $PY -m council.api.server > /tmp/s9-server.log 2>&1 &
SP=$!; sleep 6; curl -s -m 5 http://127.0.0.1:8765/health; echo
RID=$(curl -s -m 20 -X POST http://127.0.0.1:8765/runs -H 'content-type: application/json' -d '{"task":"Is 91 a prime number? Answer yes or no with one line of reasoning.","workspace":"/tmp","mode":"quick","deliverable":"answer"}' | $PY -c "import sys,json;print(json.load(sys.stdin).get('run_id',''))"); echo "run $RID"
timeout 600 curl -s -N "http://127.0.0.1:8765/runs/$RID/events" > /tmp/s9-events.log; echo "stream lines $(wc -l < /tmp/s9-events.log); deltas $(grep -c 'event: turn.delta' /tmp/s9-events.log); completed $(grep -c 'event: run.completed' /tmp/s9-events.log); failed $(grep -c 'event: run.failed' /tmp/s9-events.log)"
curl -s -m 10 http://127.0.0.1:8765/runs/$RID | $PY -c "import sys,json;d=json.load(sys.stdin);print('snapshot state',d.get('state'),'| decision',(d.get('decision') or {}).get('final_text','')[:160])"
curl -s -m 10 http://127.0.0.1:8765/models | $PY -c "import sys,json;d=json.load(sys.stdin);print('models endpoint:',len(d))"
kill $SP
step "ALL DONE"; free -g | sed -n 2p
