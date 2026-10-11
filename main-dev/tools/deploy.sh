#!/usr/bin/env bash
# Copy main-dev from this machine to the GX10. Code is edited here, never on the box.
#
#   tools/deploy.sh            copy the code
#   tools/deploy.sh --test     copy, then run the unit tests on the box
#
# Settings (environment variables):
#   COUNCIL_BOX        user@host of the box        (default asus@100.103.186.3)
#   COUNCIL_BOX_DIR    folder on the box           (default ~/council)
#   COUNCIL_BOX_PASS   password, if key login is not set up (never stored in this file)
#
# Left alone on the box: its config (~/council/box), its Python environment (~/council/venv),
# and anything generated there (db, runs, adapters, benchmark results).
set -euo pipefail
BOX="${COUNCIL_BOX:-asus@100.103.186.3}"
DIR="${COUNCIL_BOX_DIR:-council}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SSH=(ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)
if [ -n "${COUNCIL_BOX_PASS:-}" ]; then
  ASK="$(mktemp)"; trap 'rm -f "$ASK"' EXIT
  printf '#!/bin/sh\nprintf "%%s\n" "$COUNCIL_BOX_PASS"\n' > "$ASK"; chmod +x "$ASK"
  export SSH_ASKPASS="$ASK" SSH_ASKPASS_REQUIRE=force DISPLAY="${DISPLAY:-x}"
  SSH+=(-o PreferredAuthentications=password -o PubkeyAuthentication=no)
fi

cd "$HERE/.."
FILES=$(tar --exclude=node_modules --exclude=__pycache__ --exclude='main-dev/db' --exclude='main-dev/ui' --exclude='main-dev/ui_partner/ui/dist' \
  --exclude='main-dev/runs' --exclude='main-dev/adapters' --exclude='main-dev/bench/bench_*' -cf - main-dev | tar -tf - | grep -vc '/$')
echo "copying $FILES files to $BOX:$DIR/main-dev ..."
tar --exclude=node_modules --exclude=__pycache__ --exclude='main-dev/db' --exclude='main-dev/ui' --exclude='main-dev/ui_partner/ui/dist' \
  --exclude='main-dev/runs' --exclude='main-dev/adapters' --exclude='main-dev/bench/bench_*' -czf - main-dev \
  | "${SSH[@]}" "$BOX" "mkdir -p $DIR && cd $DIR && tar -xzf - && find main-dev -type f -not -path '*/__pycache__/*' | wc -l | xargs echo 'files now on box:'"
echo "done."

if [ "${1:-}" = "--test" ]; then
  echo "running unit tests on the box ..."
  "${SSH[@]}" "$BOX" "cd $DIR/main-dev && ../venv/bin/python -m unittest discover -s tests 2>&1 | tail -3"
fi
