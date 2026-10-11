#!/bin/bash
# Real build test on the box: empty folder in, working package out. Log: /tmp/buildtest.log
# Waits for the full test sequence to finish first, so the two do not share the GPU.
while pgrep -f "[f]ull_test.sh|/tmp/[f]ull.sh" > /dev/null; do sleep 20; done
cd ~/council/main-dev; export COUNCIL_HOME=~/council/box; PY=~/council/venv/bin/python
echo "##### BUILD TEST $(date +%T)"
rm -rf /tmp/ws6 && mkdir /tmp/ws6
timeout 5400 $PY -m council.cli build "Create a small Python package named textstats with a function word_count(text) returning a dict of lowercase word frequencies and a function top_n(text, n) returning the n most common words, plus unittest tests in a tests folder." --workspace /tmp/ws6 --auto-delegate > /tmp/s6.log 2>&1
echo "exit $?"
$PY tools/box/summarize_run.py
echo "--- files"; find /tmp/ws6 -type f | head -30
(cd /tmp/ws6 && $PY -m unittest discover -s tests 2>&1 | tail -4)
echo "##### BUILD TEST DONE $(date +%T)"
