# Build status

## Where we are
Phase 2, UI only: real-looking chat, history and settings screens on stand-in data, shipped to the GX10 as an Electron app for viewing. (Below is the Phase 1 record.)
Phase 1, second sitting. Lucas picked look C. Tokens done (1.3). Next: 1.4 app frame and shared pieces (one agent), then 1.5 the screens (workflow A), then 1.6 the review package and stop G1.

## Lucas's decisions (dated, in his words where quoted)
- 2026-10-10. "plan this using the plugin as reference with some of the work". The plugin = Anthropic skills; lean on frontend-design and webapp-testing ("Design + testing").
- 2026-10-10. The look: "Let the skill redesign".
- 2026-10-10. Shape: "Same shape, Council version" (detailed Phase 1, road map after, stop after Phase 1).
- 2026-10-10. Fourth study of the PDF's original look: "No, three is enough".
- 2026-10-10. Usage: "No ceiling, report at stops".
- 2026-10-10. Talk with sub-agents in "Stone Age talk. So that, it consumes less tokens and it finishes the task faster."
- 2026-10-10. Plan approved. Not yet answered: whether he prefers one stop ("you pick").
- 2026-10-10 (during WP 1.1). "Make this compatible with Electron.js and it is completely completed in electron". Read as: the finished product is an Electron desktop app; the optional Tauri wrapper is dropped; both stops open in Electron. The browser question is no longer needed. Open for the Phase 2 plan: where the engine lives (Electron on the Mac talking to the GX10, or on the GX10 itself; Python gateway or Node inside Electron).

- 2026-10-10, stop G0. "lets go with C." Look C, Cut-Out Council. He did not answer the two follow-ups (does dark look as good as light; the one thing that bothers him), so nothing was changed in the direction; both are asked again at G1.

- 2026-10-10, during WP 1.5. "stop the agents from running, send me the app as is". The three reviewers were stopped part-way (no findings kept). No fixer or verifier ran. The app was packaged and handed over as built.

- 2026-10-10. "lets work on phase 2". Phase 1's review questions were not answered; the mocks are treated as accepted for now.
- 2026-10-10, Phase 2 decisions. Engine: "All in Electron, no Python". Storage: "On the GX10". First model: "A small model on this Mac". Documents: "Personal files only".

- 2026-10-10, Phase 2 scope change. "this is just a test, we'll ship it to the gx10 so we can see it on the monitor from there. dont worry about the files or word citations for now". Read as: Phase 2 is a real chat with one model plus saved history, no file attachments, no search, no citations yet; the Electron app runs ON the GX10 and is viewed on its monitor (so app and engine are on one machine, built for Linux arm64 on this Mac and shipped over).

- 2026-10-10, Phase 2. "make sure no backend work is being done, remove any backend work. this is purely UI". The engine folder started that evening was deleted; the app shell no longer starts or forwards to anything. Phase 2 is the chat and history SCREENS on in-memory stand-in data. No engine, no model, no network. The earlier engine decisions (Node-only, storage on the GX10, a model on this Mac) are parked for a later phase.

- 2026-10-11. "can we have it so when we minimize the window, the council pfps also minimize alongside it?" Read as: when the window is made smaller, the council's figures get smaller with it (a window minimised to the Dock shows nothing). Done in `tableLayout`: the heads shrink a pixel at a time (72 down to 20) with the table, and names, speaking rings and vote marks follow. The full-size look (1040 x 558 stage and larger) is unchanged. The window may now be made as small as 800 x 600 (was 1024 x 700). On a small table a bubble that has no clear spot over its own seat is left out; nothing is drawn over a figure.
- 2026-10-11. "Can you amke the heads of each be the logo of the company instead of just a name?" Done at the table: each head shows its maker's logo as a one-colour cut-out (Phi Microsoft, Llama Meta, Qwen Alibaba, Gemma Google, Mistral Mistral AI, Granite IBM, Hermes Nous Research) and the name moved to the body. This changes look C's rule "the name lettered large inside its head" on his say. Logo shapes are copied into `ui/src/components/shared/makers.ts` from the open icon set Lobe Icons (`@lobehub/icons-static-svg` 1.95.1, MIT); the logos are their owners' trademarks, used only to say whose model a seat is. A model whose maker is not known keeps its name in the head. Small figures (top bar, Chat View, side sheet) carry no logo. Not asked, so not done: full-colour logos.
- 2026-10-11. "make a warmer theme and delete the theme chooser at the top left". A third theme, Warm (cream paper, brown ink, linen table), added to `ui/src/styles/tokens.css` and made the one a new owner sees first; Light and Dark stay. The Theme switch in the review bar (top left of a sample scene opened from the review page) is deleted. (Superseded by the next entry for the sidebar.) Read of his words is the lead's: he may have meant Warm to replace Light; ask if he says more.
- 2026-10-11. "pill inside of settings". Read as: the theme is chosen in one place, the Warm / Light / Dark pill on the Settings page. The sidebar's Theme button was removed as well.
- 2026-10-11. "make the gx10 council be a slider that goes from 2-6 at the top left". Done on the sample debate screens: after the "Council of N" button at the top left there is a slider from 2 to 6; moving it seats a council of that size (sample debates `lease-2`, `lease-3`, `lease-4`, `lease`, `lease-6`; the two, four and six seat ones are new). His PDF says 3 to 7 seats; 2 to 6 is his newer word, for the slider. Not asked, so unchanged: the seven-seat review scenes, the review bar's own Seats buttons, and the pages that have no council (chat, History, Settings).
- 2026-10-11. "Can we put settings at the bottom left below shortcuts?" Done in the sidebar: Settings left the top list (now New chat, History, Library, Models, Sample debate) and sits at the bottom left, right under Shortcuts, in the wide sidebar and in the icon rail. (The sidebar line in `docs/plan/phase-1-spec.md` is the Phase 1 record and is not kept up to date.)
- 2026-10-11. "the chat bubbles get messed up with 7 agents." Seen by the lead on the seven-seat scenes: bubbles hung over the wrong seat, sat glued together, the two sides were uneven, and some speakers had none. Changed in `tableLayout` for close tables (six or seven seats, or a shrunk council): bubbles fan outward, each on its own side of the line halfway to the next seat inward; the top seat's stays straight above it; a tail lands on its own head; the cap of four bubbles at seven seats is gone; the member speaking first always gets one. Full-size tables of two to five seats are placed exactly as before. Still imperfect, and said to Lucas: with five talking at once in a window about 1100 wide or less, not every speaker gets a bubble and the two sides can differ by one.
- 2026-10-11. "Here is the linux box. asus@100.103.186.3 ... make a folder inside of desktop just named UI and it's just move everything into UI via FTP." FTP (port 21) is closed on that box, so the copy goes by SFTP over the SSH login he gave. `~/Desktop/UI` gets the project's source and the ready-to-run GX10 app.

## Phase 2 (UI only) status, 2026-10-11
- 2026-10-11, last of the night, after Settings moved and the bubble fan: `gate` exit 0 (395 unit tests; 133 browser checks; Electron window clean). Reviews: Settings move 2 agents 219,407 tokens (no faults); bubble fan 2 agents 486,679 tokens (two serious findings, both fixed: an end seat could lose its bubble, a side bubble could be pushed off its own seat at full size).
- 2026-10-11, after the council slider: `gate` exit 0 (387 unit tests; 133 browser checks = 33 scenes in three themes plus 6 slider tests; Electron window clean). One review round of two agents (485,227 tokens); confirmed findings fixed. Left as they are, for Lucas to say: a model's colour follows its seat number, so it changes as the slider moves; the two and four seat sample debates have silent stretches when played, where the missing members spoke in the main story; in a narrow window the top bar shows fewer names because the slider takes room.
- 2026-10-11 (later the same night), after the shrink, logo and warm-theme work: `gate` exit 0 (344 unit tests; 115 browser checks = 30 scenes in light, dark and warm; Electron window 0 console errors, 0 outside requests, no Node access). Packaged Mac app opened through `look:app --packaged`, clean. Two review rounds of three agents each ran on this work (first 514,301 tokens, second 606,102); every confirmed finding was fixed except these, left as they are: with seven seats at the smallest window some logos (Alibaba, Nous) are hard to make out and long names are set narrower than short ones; a bubble may sit partly over a neighbour who is also speaking; the top bar hides whole names that do not fit.
- Built: chat screen (`#/chat/new`, `#/chat/<id>`), History (`#/history`), Settings (`#/settings`), all on the in-memory stand-in. The sample debate moved to `#/sample/...` and is linked from the sidebar and `#/review`.
- Lead checks at hand-over: `check` exit 0 (252 unit tests), 77 browser checks over 29 scenes in both themes, packaged Mac app opened through `look:app --packaged` (0 console errors, 0 outside requests, no Node access from the page).
- Not done: no critique, fix or verify round on the new screens. The Linux arm64 package has never been started on a GX10.
- Packages: `release/GX10 Council-darwin-arm64/GX10 Council.app`, `release/GX10 Council.zip`, `release/GX10-Council-linux-arm64.tar.gz` (start with `./start.sh`).
- Usage: Phase 2 research 8 runs 844,411 tokens; ship research 2 runs 246,768; UI builders 2 runs 172,898 (the history builder ran twice because of a pause; the first, stopped run is not counted).

## Work packages
| WP | Status | Evidence |
|---|---|---|
| 1.0 Setup | done (plus Electron shell: `look:app` opens the built placeholder in Electron 44.7.0, 0 outside requests, no Node access from the page) | `npm ci` clean; `look:file` on the placeholder: fonts embedded, 0 outside requests; `look` twice on port 5311, port free after each; `contrast` reproduces white on clay 3.84 and hairline 1.20 |
| 1.1 Studies | done | Three studies in `docs/direction/{a,b,c}/`, each with all seven returns. Re-run by the lead: `contrast` 142, 138 and 118 pairs, 0 below; `look:file` on each study and on the chooser: 0 console errors, 0 outside requests. One fix round after the screenshot-only review (table radius, a label, one bubble, table edge). |
| 1.2 Look-independent work | done except the player's clock (moved to 1.6) | `check` exit 0: 86 tests pass (story, bubble timing, viewAt, table layout, 80% rule); final check passes on the placeholder scene in both themes, plus the Electron pass; 23 scenes listed as not yet built |
| G0 Lucas picks | done: look C | chosen study copied to `docs/design/chosen-study/`; brief in `docs/design/direction.md` |
| 1.3 Tokens | done | `tokens.css` and `app.css` in look C; unused fonts removed; `contrast.test.ts` enforces text, seat names, edges and colourless Chat View tokens in both themes; `check` exit 0, 94 tests |
| 1.4 Frame | done | 45 files: shared pieces, frame, stage shell, composer, chat screen, gallery, stubs for the three screen builders. Lead re-ran `check`: exit 0, 133 tests. Builder's looks: 0 console errors, 0 outside requests, light and dark, 1440 and 1024. Lead viewed the debating shot: matches the chosen study. |
| 1.5 Screens | built; review round STOPPED by Lucas before it reported, so no critique, fix or verify pass has run | Lead ran the final check after the three builders: `check` exit 0 (212 tests), 61 browser checks pass over 23 scenes (both themes; key scenes at 1024 and 1100), Electron pass clean. One lead fix: the seat sheet's scroll area made keyboard-reachable (accessibility scan). |
| 1.6 Review package | done as is | Review page with 13 questions, review bar with Play, screenshot sheet (`docs/review/phase-1/index.html`, 29 views), `GX10 Council.app` in `release/` (opened and checked through `look:app --packaged`: 0 console errors, 0 outside requests, no Node access from the page), launcher `Open GX10 Council mocks.command` |
| G1 Lucas reviews | OPEN: app handed over 2026-10-10 | |

## Differences from the approved plan
- Electron (Lucas, 2026-10-10): `electron` 44.7.0 and `@electron/packager` 20.3.0 added; `ui/electron/main.cjs` and `preload.cjs`; Vite `base: "./"`; new commands `app`, `app:dev`, `look:app`, `package:mac`. The WebKit test pass is dropped; the final check adds an Electron pass. Electron 44.7.0 carries Chromium 152; the test browser is Chromium 156.
- VS Code's terminal sets `ELECTRON_RUN_AS_NODE`, which makes Electron act as plain Node. Every script that starts Electron removes that variable first.
- `look` starts and stops its own dev server. The skill's `with_server.py` is kept in `ui/scripts/vendor/` for reference but not used: it stops only the shell it started, and the plan allowed this fallback.
- Vite has no `--cacheDir` flag; each agent's cache folder is set through the `GX10_VITE_CACHE` variable read in `vite.config.ts`.

## The three open back-end questions (mocks must be true under either answer)
1. Seats speak one at a time, or several at once.
2. Bubble lines come from a separate small model, or from each agent.
3. How "the answers match" is decided.

## Kept from the earlier (stopped) plan, and what was cut
Cut: the two-agent rehearsal; four builders in sequence to set the look; two of three critique rounds; the two skeptics; the three look switches.
Kept: the owner's pick before any token is written; computed contrast for every palette; a reviewer who sees only screenshots; builder, critic, fixer and verifier as different agents; the lead re-running the final check before each commit; no-overlap tests in pure code and in both browsers; both themes for every scene; restore points.

## Usage log
| Workflow | Agent runs | Sub-agent tokens | Minutes |
|---|---|---|---|
| Planning: research | 10 | 2,179,203 | 33 |
| Planning: design | 7 | 1,214,912 | 38 |
| Planning: audit | 3 | 716,947 | 20 |
| F, layout and timing (first run in Stone Age talk) | 2 | 141,100 | 4 |
| D, three studies and a screenshot-only reviewer | 4 | 798,844 | 27 |
| D, fix round | 3 | 354,667 | 7 |
| WP 1.4, frame builder | 1 | 285,295 | 21 |
| A launch 1, three screen builders | 3 | 700,812 | 18 |
| A launch 2, three reviewers (stopped by Lucas; tokens not reported) | 3 | not reported | about 6 |

## Findings not fixed (studies; for the chosen look these are settled in WP 1.3)
- All looks: a seat's colour belongs to its place, so a model's colour differs between the five-seat and seven-seat panels. Decide in WP 1.3 whether colour should follow the model instead.
- A: light-theme seats are as dark as the table (two lighter variants are in the study; lighter costs colour-vision separation). Dark-theme slate seat is close to the dark ink (1.21:1). The lamp sits far from its head; the ring on the head does the real work. The text face draws a slashed zero.
- B: line patterns make the bodies louder than the tally; ochre and teal rings pass 3:1 with little to spare; bubbles are the hardest to read of the three.
- C: the figure still reads as the stock user icon because the shared body size is fixed at 1.4 x head; rust and violet neighbours come out the same grey; teal and ochre shout in dark.
- Studies' own plan.md / review.md have a few lines that predate the fix round (listed in each critique.md).
