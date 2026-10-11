# Run the app on the box

## Who talks to whom
Browser or Electron window -> http://127.0.0.1:8765/ui/... (council API, FastAPI)
-> council (router, chamber, works, chronicle) -> one llama-server per model.
The UI itself is static files served on http://127.0.0.1:4173 (vite preview).
If the backend does not answer, the UI falls back to the mock engine as before.

## Start
    bash ~/council/main-dev/tools/box/run_app.sh          # backend + UI
    bash ~/council/main-dev/tools/box/run_app.sh --no-ui  # backend only
    bash ~/council/main-dev/tools/box/run_app.sh stop     # kill both
Build the UI alone (type check + vite build): `bash tools/box/build_ui.sh`.
Then open http://127.0.0.1:4173. For a window at the box screen:
    cd ~/council/main-dev/ui_partner/ui
    GX10_DEV_URL=http://127.0.0.1:4173 env -u ELECTRON_RUN_AS_NODE npx electron .

## Force the mock
Open http://127.0.0.1:4173/?mock  (FakeEngine, no backend needed).

## View from another computer
    ssh -L 4173:127.0.0.1:4173 -L 8765:127.0.0.1:8765 asus@<box>
Then open http://127.0.0.1:4173 on your own machine.

## Logs
- ~/council/logs/api.log  backend
- ~/council/logs/ui.log   vite preview
- COUNCIL_HOME=~/council/box  run data and state
node_modules for the UI are symlinked from ~/Desktop/UI/ui/node_modules (not copied).
