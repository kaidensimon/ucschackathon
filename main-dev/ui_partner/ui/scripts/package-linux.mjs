// npm run package:linux
// Builds the GX10 Council app for the GX10 (Linux, arm64) into ../release/.
// The app holds only the Electron shell and the built screens (ui/dist). It is built on the
// Mac and copied to the GX10; start it there with the start.sh written beside it.
import { chmodSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { packager } from "@electron/packager";

const ui = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const keep = [/^\/dist($|\/)/, /^\/electron($|\/)/, /^\/package\.json$/];
const paths = await packager({
  dir: ui,
  out: path.resolve(ui, "..", "release"),
  name: "GX10 Council",
  platform: "linux",
  arch: "arm64",
  overwrite: true,
  prune: false,
  executableName: "gx10-council",
  // keep only the shell and the built screens; everything else in ui/ stays out of the app
  ignore: (p) => p !== "" && !keep.some((re) => re.test(p)),
});
// A start script and a short note travel inside the folder, so the GX10 needs nothing else.
const START = `#!/bin/bash
# Starts GX10 Council. Run from a terminal:  ./start.sh
# A log is written to ~/gx10-council.log
cd "$(dirname "$0")" || exit 1
LOG="$HOME/gx10-council.log"
unset ELECTRON_RUN_AS_NODE
./gx10-council "$@" 2>&1 | tee "$LOG"
if grep -qi "sandbox" "$LOG"; then
  echo
  echo "------------------------------------------------------------------"
  echo "The app did not start because of this system's sandbox setting."
  echo "Pick ONE of these, then run ./start.sh again:"
  echo
  echo "  1) The quick test (no password). Fine for this build: it shows only"
  echo "     its own screens and never uses the network."
  echo "       ./start.sh --no-sandbox"
  echo
  echo "  2) The proper fix (asks for your password; redo after each new copy):"
  echo "       sudo chown root:root chrome-sandbox && sudo chmod 4755 chrome-sandbox"
  echo "------------------------------------------------------------------"
fi
`;
const NOTE = `GX10 Council, UI-only test build for the GX10 (Linux, arm64)

1. Open a terminal in this folder.
2. Run:    ./start.sh
3. A window titled "GX10 Council" opens on a new chat.

What you are looking at: screens only. The chat answers with a canned stand-in
reply, nothing is saved when the app closes, and nothing uses the network.
"Sample debate" in the sidebar opens the council screens.

If it does not start, the terminal says what to do. The most likely cause is this
system's sandbox setting; start.sh prints two ways round it.

If something else goes wrong, send back the file  ~/gx10-council.log
and the output of:
    ldd ./gx10-council | grep "not found"
    cat /etc/os-release | head -3
    echo $XDG_SESSION_TYPE
`;
for (const dir of paths) {
  writeFileSync(path.join(dir, "start.sh"), START);
  chmodSync(path.join(dir, "start.sh"), 0o755);
  writeFileSync(path.join(dir, "READ ME FIRST.txt"), NOTE);
}
console.log(`packaged: ${paths.join(", ")}`);
