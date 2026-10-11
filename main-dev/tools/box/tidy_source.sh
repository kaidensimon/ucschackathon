#!/usr/bin/env bash
# Make the source folder hold source only. Run on the box: bash tools/box/tidy_source.sh
#
# Nothing is deleted except Python byte code. Everything else is MOVED out, next to the folder:
#   ui_partner/ui/node_modules -> ~/council/node_modules      (the UI still finds it: Node walks up)
#   ui_partner/ui/dist         -> ~/council/ui-dist
#   db runs adapters bench/bench_* -> ~/council/old-run-data/ (left over from early test runs)
#   ui (the first UI, unused)  -> ~/council/old-ui
# and the trained lie-detector probes are copied IN, to probes/, so the folder is complete.
# the folder that holds main-dev (found from where this script is, so the folder can be moved or renamed)
BASE="${COUNCIL_BASE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
SRC="$BASE/main-dev"
cd "$SRC" || { echo "no $SRC"; exit 1; }

move() {  # move $1 to $2 unless $2 already exists
  [ -e "$1" ] || return 0
  if [ -e "$2" ]; then echo "kept in place (target exists): $1"; else mv "$1" "$2" && echo "moved $1 -> $2"; fi
}

if [ -d ui_partner/ui/node_modules ] && [ ! -L ui_partner/ui/node_modules ]; then
  move ui_partner/ui/node_modules "$BASE/node_modules"
fi
[ -L ui_partner/ui/node_modules ] && rm ui_partner/ui/node_modules && echo "removed stale node_modules link"
if [ -d ui_partner/ui/dist ]; then
  if [ -e "$BASE/ui-dist" ]; then rm -rf ui_partner/ui/dist && echo "removed old build output (a newer one is in $BASE/ui-dist)"
  else move ui_partner/ui/dist "$BASE/ui-dist"; fi
fi

mkdir -p "$BASE/old-run-data"
for d in db runs adapters; do move "$d" "$BASE/old-run-data/$d"; done
for d in bench/bench_*; do [ -e "$d" ] && move "$d" "$BASE/old-run-data/$(basename "$d")"; done
move ui "$BASE/old-ui"

find . -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null
echo "removed Python byte code folders"

if [ -d "$BASE/box/probes" ]; then
  rm -rf probes && cp -r "$BASE/box/probes" probes && echo "copied trained probes into probes/ ($(ls probes | wc -l) models)"
fi

echo
echo "source folder: $SRC"
du -sh . | cut -f1
du -sh ./* | sort -rh | head -12
