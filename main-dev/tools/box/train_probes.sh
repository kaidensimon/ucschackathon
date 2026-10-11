#!/usr/bin/env bash
# Train the truth probe of each council model on the GX10 box, one after another.
# Runs from ~/council/main-dev with COUNCIL_HOME=~/council/box and the venv at ~/council/venv.
#
#   bash ~/council/main-dev/tools/box/train_probes.sh              all 11 default models
#   bash ~/council/main-dev/tools/box/train_probes.sh qwen3-14b    only the ids given
#
# No set -e: one failing model does not stop the loop. Logs go to ~/council/logs.
set -u

BOX="$HOME/council"
REPO="$BOX/main-dev"
PY="$BOX/venv/bin/python"
OLLAMA="http://127.0.0.1:11435"
ACTDUMP="$BOX/tap-build/actdump"
LOGS="$BOX/logs"

# Registry ids from tools/box/make_registry.py (not Ollama tags). llama32-vision is purged,
# and gemma4-12b-q4 is not in the eleven.
DEFAULT_MODELS="gpt-oss-20b qwen35-9b phi4-14b ministral3-14b granite41-8b qwen3-14b deepseek-r1-14b phi4-reasoning mistral-small32 falcon3-10b gemma4-12b"

if [ ! -x "$ACTDUMP" ]; then
  echo "refused: no executable actdump at $ACTDUMP (build tap-build first)" >&2
  exit 1
fi
if [ ! -x "$PY" ]; then
  echo "refused: venv python missing at $PY" >&2
  exit 1
fi
cd "$REPO" || { echo "refused: no repo at $REPO" >&2; exit 1; }
mkdir -p "$LOGS"
export COUNCIL_HOME="$BOX/box"

if [ "$#" -gt 0 ]; then MODELS="$*"; else MODELS="$DEFAULT_MODELS"; fi

# Free the memory: unload every model the council Ollama holds (keep_alive 0).
unload_all() {
  local names name
  names=$(curl -s --max-time 10 "$OLLAMA/api/ps" 2>/dev/null \
    | "$PY" -c 'import sys,json; [print(m.get("name") or m.get("model")) for m in json.load(sys.stdin).get("models",[])]' 2>/dev/null)
  if [ -z "$names" ]; then
    echo "unload: nothing loaded on $OLLAMA (or no answer)"
    return
  fi
  while IFS= read -r name; do
    [ -z "$name" ] && continue
    echo "unload: $name"
    curl -s --max-time 120 "$OLLAMA/api/generate" -d "{\"model\":\"$name\",\"keep_alive\":0}" >/dev/null
  done <<< "$names"
}

echo "train_probes start $(date '+%Y-%m-%d %H:%M:%S')"
echo "models: $MODELS"
unload_all

SUMMARY=()
FAILS=0
for id in $MODELS; do
  log="$LOGS/probe_$id.log"
  t0=$(date +%s)
  echo "== $id  $(date '+%H:%M:%S')"
  "$PY" -m council.probe.train_cli --source llamacpp --model "$id" 2>&1 | tee "$log"
  rc=${PIPESTATUS[0]}
  secs=$(( $(date +%s) - t0 ))
  verdict=$(grep -h 'verdict:' "$log" | tail -n 1)
  if [ -z "$verdict" ]; then verdict=$(grep -h '^error:' "$log" | tail -n 1); fi
  if [ -z "$verdict" ]; then verdict="no verdict line"; fi
  [ "$rc" -ne 0 ] && FAILS=$((FAILS + 1))
  SUMMARY+=("$(printf '%-18s rc=%s %6ss  %s' "$id" "$rc" "$secs" "$verdict")")
done

echo
echo "== summary $(date '+%Y-%m-%d %H:%M:%S')"
printf '%s\n' "${SUMMARY[@]}" | tee "$LOGS/probe_summary.txt"
echo "failed: $FAILS of $(echo $MODELS | wc -w)"
[ "$FAILS" -eq 0 ]
