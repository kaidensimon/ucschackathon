#!/bin/bash
# Fast confidence check on the box: tiny benchmark, then the real build test. Log: /tmp/quick.log
cd ~/council/main-dev; export COUNCIL_HOME=~/council/box; PY=~/council/venv/bin/python
echo "##### BENCH (4 tasks, 3 solo models + council) $(date +%T)"
timeout 1500 $PY -m council.cli bench --tasks bench/tasks/sample.jsonl --modes "solo:gpt-oss-20b,solo:phi4-14b,solo:granite41-8b,council_vote_only,council" --limit 4 > /tmp/qbench.log 2>&1
echo "exit $?"; grep -E "^\||bench:" /tmp/qbench.log | cut -c1-200 | tail -12
echo "##### BUILD $(date +%T)"
rm -rf /tmp/ws6 && mkdir /tmp/ws6
timeout 3600 $PY -m council.cli build "Create a small Python package named textstats with a function word_count(text) returning a dict of lowercase word frequencies and a function top_n(text, n) returning the n most common words, plus unittest tests in a tests folder." --workspace /tmp/ws6 --auto-delegate > /tmp/s6.log 2>&1
echo "exit $?"
$PY tools/box/summarize_run.py | cut -c1-300
echo "--- files"; find /tmp/ws6 -type f | head -30
(cd /tmp/ws6 && $PY -m unittest discover -s tests 2>&1 | tail -4)
echo "##### DONE $(date +%T)"
