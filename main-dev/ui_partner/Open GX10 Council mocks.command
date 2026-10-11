#!/bin/zsh
# Double-click to open the GX10 Council mock screens (an Electron app).
cd "$(dirname "$0")"
unset ELECTRON_RUN_AS_NODE
APP="release/GX10 Council-darwin-arm64/GX10 Council.app"
if [ -d "$APP" ]; then
  open "$APP"
else
  # no packaged app yet: run the built screens through Electron directly
  exec ui/node_modules/.bin/electron ui
fi
