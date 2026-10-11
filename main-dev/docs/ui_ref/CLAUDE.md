# GX10 Council

A personal app for one person (Lucas) on a home network: 3 to 7 local AI models on an ASUS Ascent GX10 debate a question and release one agreed answer. This repo is that app only.

**Scope warning.** `~/.claude/CLAUDE.md` (defense compliance) and `~/Downloads/CLAUDE.md` (a trading project) describe OTHER projects. Their rules do not apply here. One thing carries over: Lucas is a non-technical founder, so anything he reads is written in plain language.

## Where things are
- `docs/BUILD_STATUS.md` — where we are, Lucas's dated decisions, open findings. Read first.
- `docs/plan/phase-1-plan.md` — the approved Phase 1 plan. It wins over any planner output.
- `docs/plan/GX10-Council-UI-Plan.pdf` / `.txt` — the product spec. `docs/plan/wireframes/*.png` — its drawings (the Read tool cannot open the PDF on this Mac).
- `docs/direction/` — the three candidate looks (a, b, c), the judges' findings, the shared study brief and content.
- `docs/research/` — verified facts for later phases. `docs/skills/` — the two reference skills.
- `ui/` — the app (React 19, Vite 8, TypeScript 6, Tailwind 4), shipped as an **Electron** desktop app (`ui/electron/`). The page never gets Node access; anything it needs from the machine goes through one named function in `ui/electron/preload.cjs`. Versions are pinned exactly; only the lead changes `package.json` or the lockfile. The sample debate (Phase 1 mock screens) lives under `#/sample/...`; real-looking chat lives under `#/chat/...`.

## Current phase
Phase 2 is UI ONLY (Lucas, 2026-10-10: "this is purely UI"). Do not write any backend: no engine, no server, no model calls, no `fetch`, no database. Screens get data from the in-memory stand-in `ui/src/engine/fake.ts` through `useEngine()`.

Phase 1 (done):
Phase 1: pick a look from three studies (stop G0), then design system and mock screens from one invented sample debate (stop G1). Nothing talks to a model. No later phase starts without its own plan and Lucas's approval.

## Commands (run from the repo root)
```
npm --prefix ui run check        # types, lint, token guard, unit tests
npm --prefix ui run look -- --port <5311-5314> --agent <name> --route "<hash route>"
npm --prefix ui run look:file -- <file.html> --out <folder in repo> [--full] [--grey] [--scale 1]
npm --prefix ui run contrast -- <pairs.json>
npm --prefix ui run embed-fonts -- <study.src.html>
npm --prefix ui run gate         # the final check; only the lead and the verifier run it
npm --prefix ui run look:app -- --route "<hash route>"   # the BUILT app in the real Electron window; lead and verifier only
npm --prefix ui run app          # build and open the Electron app
```

## Rules for sub-agents
- Talk between lead and sub-agents is short "Stone Age" talk (Lucas's instruction): briefs, replies, working notes. Exact things stay exact: paths, commands, numbers, colour values, code, and any words Lucas will read or see on screen.
- Write only the paths on your write list. Never install, never `npx`, never write with git, never kill processes by name, never write Python scripts.
- Skills are used by reading `docs/skills/<name>/SKILL.md`. frontend-design: only the agents told to. webapp-testing: its method, through `look` and `look:file`.
- Starting Electron from a script: remove the `ELECTRON_RUN_AS_NODE` variable first (VS Code sets it).
- Screenshots stay inside the repo. Nothing leaves this machine: no CDN, no outside requests.
- A complaint about the chosen look is reported as a question for Lucas, not fixed.
- Commits: one work package, one commit, on `main`. Nothing is pushed.
