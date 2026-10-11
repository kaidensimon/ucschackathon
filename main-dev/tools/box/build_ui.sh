#!/usr/bin/env bash
# Build the UI on the box. Run: bash tools/box/build_ui.sh
#
# Nothing is written inside the source folder. Installed packages and build output live beside it:
#   ~/council/node_modules   the UI's packages (Node finds them by walking up from the source)
#   ~/council/ui-dist        the built page
#   ~/council/vite-cache     Vite's cache
# the folder that holds main-dev (found from where this script is, so the folder can be moved or renamed)
BASE="${COUNCIL_BASE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
UI="$BASE/main-dev/ui_partner/ui"
BIN="$BASE/node_modules/.bin"
cd "$UI" || { echo "no $UI"; exit 1; }

if [ ! -x "$BIN/vite" ]; then
  echo "== installing the UI's pinned packages into $BASE/node_modules =="
  cp package.json package-lock.json "$BASE/" || exit 1
  (cd "$BASE" && npm ci --no-audit --no-fund) || { echo "npm ci FAILED"; exit 1; }
fi

export GX10_VITE_CACHE="$BASE/vite-cache"
echo "== tsc --noEmit (first 40 error lines) =="
"$BIN/tsc" --noEmit 2>&1 | head -40
echo "== vite build =="
"$BIN/vite" build --outDir "$BASE/ui-dist" --emptyOutDir || { echo "vite build FAILED"; exit 1; }
echo "built page is at: $BASE/ui-dist"
