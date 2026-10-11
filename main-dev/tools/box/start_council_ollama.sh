#!/usr/bin/env bash
# The council's own Ollama on port 11435. Plain bash, no sudo.
#
#   tools/box/start_council_ollama.sh          start it (if not already answering), print version and loaded models
#   tools/box/start_council_ollama.sh stop     stop it
#
# Why a second one: the shared system Ollama (port 11434) keeps only 3 models loaded.
# This one shares its model store and keeps up to 8 loaded, for good.
# Log: ~/council/logs/ollama-council.log
set -u

PORT=11435
URL="http://127.0.0.1:$PORT"
LOGDIR="$HOME/council/logs"
LOG="$LOGDIR/ollama-council.log"

answering() { curl -s -m 3 "$URL/api/version" > /dev/null 2>&1; }

if [ "${1:-}" = "stop" ]; then
  # Match only the instance bound to our port, never the system one on 11434.
  PIDS=$(pgrep -u "$(id -u)" -f "ollama serve" | while read -r p; do
    if tr '\0' '\n' < "/proc/$p/environ" 2>/dev/null | grep -qx "OLLAMA_HOST=127.0.0.1:$PORT"; then echo "$p"; fi
  done)
  if [ -z "$PIDS" ]; then echo "council Ollama is not running"; exit 0; fi
  # shellcheck disable=SC2086
  kill $PIDS
  for _ in 1 2 3 4 5 6 7 8 9 10; do answering || { echo "stopped"; exit 0; }; sleep 1; done
  echo "still answering after 10 s; check: pgrep -af 'ollama serve'"; exit 1
fi

if answering; then
  echo "already answering on $PORT"
else
  mkdir -p "$LOGDIR"
  OLLAMA_HOST="127.0.0.1:$PORT" \
  OLLAMA_MODELS=/usr/share/ollama/.ollama/models \
  OLLAMA_MAX_LOADED_MODELS=8 \
  OLLAMA_NUM_PARALLEL=1 \
  OLLAMA_KEEP_ALIVE=-1 \
  nohup setsid ollama serve >> "$LOG" 2>&1 < /dev/null &
  for _ in $(seq 1 30); do answering && break; sleep 1; done
  answering || { echo "did not start within 30 s; see $LOG"; exit 1; }
  echo "started"
fi

echo "version: $(curl -s -m 5 "$URL/api/version")"
echo "loaded models:"
OLLAMA_HOST="127.0.0.1:$PORT" ollama ps
