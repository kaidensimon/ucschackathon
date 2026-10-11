#!/bin/bash
# Starts the GX10 Council app that sits in this folder.
# Double-click it (choose "Run in Terminal"), or in a terminal:  ./"Start GX10 Council.sh"
cd "$(dirname "$0")/release/GX10 Council-linux-arm64" || exit 1
exec ./start.sh "$@"
