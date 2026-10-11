#!/bin/zsh
# Double-click to open the look chooser in an Electron window.
cd "$(dirname "$0")"
unset ELECTRON_RUN_AS_NODE
exec ui/node_modules/.bin/electron ui/electron/open-file.cjs "$PWD/Choose a look.html"
