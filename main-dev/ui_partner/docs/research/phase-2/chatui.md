# Phase 2 research: chatui

Read-only research on 2026-10-10. The re-check section overrides the findings where they differ. Written in the agents' short style.

## Summary
Chat UI plan, short. Keep what Phase 1 has: react-markdown 10.1.0 + remark-gfm 4.0.1 + AnswerText in look C. Add 4 direct deps only: remend@1.4.0, rehype-highlight@7.0.2, eventsource-parser@4.1.1, @tanstack/react-query@5.104.1. No Streamdown (its classes fight the tokens). No Shiki (about 10x heavier). No msw. No virtual list yet. Stream = fetch + SSE, Stop = abort + explicit stop call. Files go renderer -> engine direct, never through main. BIG CATCH found: app as built cannot reach any engine. main.cjs cancels all non-file requests and denies all permissions; Chromium Local Network Access needs `local-network` / `loopback-network` granted (Electron 43 break reported by another app; NOT tested on 44.7.0). Same deny-all likely kills the Copy button. Do a 1-hour spike before any UI work. Second catch: no login + open CORS = any web page on home network can read the files; use a pairing key. Measured here (Node, this Mac): react-markdown full re-parse 2.3 ms at 2,524 chars, 7.2 ms at 10,096, 25.3 ms at 40,384. Rule 'never change package.json' must be lifted for Phase 2 deps.

## Claims

### R1a [partly] (load-bearing)
react-markdown 10 re-parse on every token is too slow for long answers.

Evidence: Measured here in Node 24 on this Mac (renderToStaticMarkup, react-markdown 10.1.0 + remark-gfm 4.0.1 from ui/node_modules): 2.27 ms at 2,524 chars, 7.23 ms at 10,096, 25.25 ms at 40,384. Stream of 10,096 chars with re-parse every 8 tokens: 316 parses, 842 ms total. DOM commit in Chromium NOT measured, so real cost is higher; normal answers fit a 16 ms frame, very long ones do not.

For the build: Batch tokens: one state write per animation frame. React.memo every finished message so only the live one re-parses. Adaptive brake: if last parse took over 8 ms, update at most every 100 ms. Add block memo only if a Chromium test with a 40,000-char answer shows jank.

Sources: /Users/lucasta/projects/gx10-council/ui/package.json, /Users/lucasta/projects/gx10-council/ui/src/components/conversation/AnswerText.tsx, https://registry.npmjs.org/react-markdown

### R1b [refuted] (load-bearing)
Streamdown drops into this codebase clean.

Evidence: streamdown 2.7.0 (Apache-2.0, peers react and react-dom ^18.0.0 || ^19.0.0, 15 deps incl. tailwind-merge, rehype-raw, marked). Its dist/chunk-D32TOXHM.js carries shadcn classes: bg-muted, text-muted-foreground, border-border, bg-background, bg-sidebar, text-primary, bg-red-50, text-red-700, shadow-sm, shadow-lg, rounded-md, bg-black; docs demand `@source "../node_modules/streamdown/dist/*.js";` and shadcn vars (--background, --muted, --border, --primary, --radius). App theme has `--color-*: initial` and its own `muted` = text grey, so `bg-muted` paints text grey as fill, red classes vanish, shadows break rule 5. Good news: no http URL in dist/*.js (scanned), Shiki is NOT in core (plugin @streamdown/code 2.0.0 depends on shiki ^4.4.3 and imports all bundledLanguages).

For the build: Do not add streamdown. Tell build agents so in the plan; they reach for it by habit. Take only its small helper remend@1.4.0.

Sources: https://registry.npmjs.org/streamdown/2.7.0, https://registry.npmjs.org/streamdown/-/streamdown-2.7.0.tgz, https://raw.githubusercontent.com/vercel/streamdown/main/packages/streamdown/README.md, https://streamdown.ai/docs/getting-started, https://registry.npmjs.org/@streamdown/code/-/code-2.0.0.tgz, /Users/lucasta/projects/gx10-council/ui/src/styles/app.css

### R1c [refuted] (load-bearing)
A new incremental parser (marked + own renderer) is needed to stop flicker.

Evidence: Flicker comes from half-written marks (`**bold`, open fence, half link), not from the parser. remend 1.4.0 (Apache-2.0, zero deps, 28,630 bytes unpacked) closes them on the raw string before any parser: remend("This is **bold text") gives "This is **bold text**". AnswerText.tsx already maps every Markdown tag to look C on react-markdown; a new renderer throws that away. Streamdown itself imports `marked` only to split blocks.

For the build: Keep AnswerText. While streaming pass `remend(text)`; when done pass raw text. If block memo is ever needed: marked@18.1.0 (MIT, node >= 20) `Lexer` to cut blocks, one memoised <Markdown> per block. marked's own deps not checked.

Sources: https://raw.githubusercontent.com/vercel/streamdown/main/packages/remend/README.md, https://registry.npmjs.org/remend/1.4.0, /Users/lucasta/projects/gx10-council/ui/src/components/conversation/AnswerText.tsx

### R2a [refuted]
Shiki with a small fixed set is the lightest offline highlighter.

Evidence: File sizes read from npm tarballs, unminified. @shikijs/langs 4.5.0 for 11 langs (javascript 184,866; typescript 190,678; python 77,130; html 61,930; css 56,933; markdown 65,304; shellscript 45,421; sql 24,794; yaml 11,581; json 3,193; diff 2,861) = 724,691 bytes, plus @shikijs/core 50,089, plus oniguruma-to-es (997,453 unpacked) or wasm-inlined.mjs 622,442. highlight.js 11.12.0: lib/core.js 76,324 + same 11 langs 106,729 = about 183 KB. prismjs 1.30.0 is smallest (prism-core.min.js 7,461; langs 449 to 6,143 min) but its glue into react-markdown was not checked. Shiki docs: full bundle 6.4 MB min, web 3.8 MB min; `shiki/core` has no langs, themes or wasm.

For the build: Use highlight.js through rehype-highlight@7.0.2 (MIT; deps lowlight ^3.0.0, hast-util-to-text ^4.0.0, unist-util-visit, vfile). lowlight 3.3.0 pins highlight.js ~11.11.0, so 11.11.x lands, not 11.12.0. It is a sync rehype plugin: one line in AnswerText. Register a fixed language list; unknown language = plain ink. Minified sizes are estimate, not measured.

Sources: https://registry.npmjs.org/@shikijs/langs/-/langs-4.5.0.tgz, https://registry.npmjs.org/@shikijs/core/-/core-4.5.0.tgz, https://registry.npmjs.org/highlight.js/-/highlight.js-11.12.0.tgz, https://registry.npmjs.org/prismjs/-/prismjs-1.30.0.tgz, https://shiki.style/guide/bundles, https://shiki.style/guide/regex-engines, https://shiki.style/guide/theme-colors

### R2b [confirmed]
Monochrome highlighting (weight and greys) is the right call for look C.

Evidence: direction.md rule 1: 'Every hue on screen is a seat... Only other colour: agreed green and error red'. So coloured syntax breaks the brief. highlight.js emits class names (hljs-keyword, hljs-comment, hljs-string), so CSS can use tokens only: ink, `muted`, weight. Catch: only JetBrains Mono wght-normal files are in ui/dist/assets; the package has wght-italic.css but it is not imported, so italics would be faked.

For the build: Write about 10 CSS rules in ui/src/styles: keyword weight 650, comment `muted`, string and number plain ink, rest ink. No italics unless wght-italic.css is imported. Ship no highlight.js theme file. It is a look choice: show Lucas one shot.

Sources: /Users/lucasta/projects/gx10-council/docs/design/direction.md, /Users/lucasta/projects/gx10-council/ui/src/styles/app.css, https://registry.npmjs.org/highlight.js/-/highlight.js-11.12.0.tgz

### R2c [unverified]
The Copy button can call navigator.clipboard.writeText as is.

Evidence: Electron session docs list `clipboard-sanitized-write` as a permission string; main.cjs has `setPermissionRequestHandler((_wc, _permission, callback) => callback(false))`, deny all. Inference: the write is refused. Not run.

For the build: Test Copy in the built Electron app first. If refused: allow only `clipboard-sanitized-write` for the app's own page in the handler. Sandboxed preload cannot require `clipboard`, so the other way is an IPC call to main.

Sources: https://www.electronjs.org/docs/latest/api/session, /Users/lucasta/projects/gx10-council/ui/electron/main.cjs

### R3a [confirmed] (load-bearing)
fetch + ReadableStream + SSE beats WebSocket for one-model chat.

Evidence: eventsource-parser 4.1.1: MIT, no deps, engines node >=22.12, export `eventsource-parser/stream` gives `EventSourceParserStream` for `.pipeThrough(...)`; README: works in 'modern browsers, Node 22.12 and higher'. llama.cpp server README: browser EventSource cannot be used (no POST), so fetch stream is the way. Same parser runs in engine (reading llama-server) and renderer. WebSocket needs a server package in the engine (Node 24 ships a WebSocket client, no server: from memory, not re-checked).

For the build: One POST starts a run and its reply body is the event stream. Every event carries run id and seq. On drop: one GET /runs/:id/events?after=<seq>; if run gone, refetch the chat. Keep WebSocket out until Phase 4 shows a need.

Sources: https://raw.githubusercontent.com/rexxars/eventsource-parser/main/README.md, https://registry.npmjs.org/eventsource-parser, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md

### R3b [partly] (load-bearing)
AbortController in the renderer makes llama-server stop.

Evidence: llama.cpp master: server-http.cpp wires `req.is_connection_closed` into `should_stop`; server-context.cpp has `HTTP_POLLING_SECONDS = 1`, so stop can lag about 1 s plus the current decode batch. But there are two hops: renderer -> engine -> llama-server. Abort only ends hop 1; the engine must see the close and abort its own fetch. Not run end to end.

For the build: Stop = two things: POST /runs/:id/stop (does not lean on socket close) and abort the fetch. Engine holds one AbortController per run, passes its signal to the llama-server fetch, saves partial text with `stopped: true`. Regenerate = new run that replaces the last answer. Test: after Stop, fake llama-server sees its socket close within 2 s.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/server-http.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/server-context.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/server-queue.h, /Users/lucasta/projects/gx10-council/docs/research/engine.md

### R3c [confirmed]
Tokens per second and prompt progress come from llama-server itself.

Evidence: README: `timings_per_token` 'Include prompt processing and text generation speed information in each response' (default false); `timings` has prompt_n, predicted_n, cache_n, predicted_per_second. `return_progress` 'Include prompt processing progress in stream mode' gives prompt_progress {total, cache, processed, time_ms}. Extract, OCR, index and search progress are NOT llama's; engine must emit them.

For the build: Engine sets `timings_per_token: true` and `return_progress: true`, and re-emits own events: run.status (reading-files, searching, thinking, writing), token delta, run.timings, run.done, run.error. UI reuses StatusPill wording 'Reading your files'; tokens per second shown as meta text at most once a second.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md

### R3d [refuted] (load-bearing)
The renderer can simply fetch the engine over HTTP.

Evidence: Confirmed in repo: main.cjs `onBeforeRequest` cancels every URL that is not file:, data:, blob: (or the dev server), and denies every permission. Confirmed in Electron docs: permissions `local-network`, `local-network-access`, `loopback-network` exist for Chromium Local Network Access. Secondary, not merged, NOT tested on 44.7.0: feishin PR #2593 says the Electron 43 bump broke a file:// renderer reaching private addresses until those were granted, while a localhost dev server hid the bug.

For the build: First Phase 2 task = spike in the PACKAGED app (file:// page): streaming fetch to 127.0.0.1 and to a LAN address. Change main.cjs: allow exactly the saved engine origin in isAllowed; grant only `local-network`, `loopback-network`, `local-network-access` for the app's own page in both setPermissionRequestHandler and setPermissionCheckHandler. Engine must answer CORS (page origin is `null`). Fallback if spike fails: custom scheme with protocol.handle + net.fetch in main (stream and abort through it not checked).

Sources: /Users/lucasta/projects/gx10-council/ui/electron/main.cjs, https://www.electronjs.org/docs/latest/api/session, https://github.com/jeffvli/feishin/pull/2593, https://developer.chrome.com/blog/local-network-access

### R4a [partly] (load-bearing)
TanStack Query is worth one dependency over hand-written hooks.

Evidence: @tanstack/react-query 5.104.1: MIT, peer react ^18 || ^19, one dep @tanstack/query-core 5.104.1. Docs give the exact optimistic recipe: onMutate -> cancelQueries -> snapshot -> setQueryData -> rollback in onError -> invalidateQueries in onSettled. That covers rename, pin, delete, search and file status. It does NOT fit the token stream; that is judgement, not a doc fact.

For the build: Query for: chat list, one chat, files, library, settings, engine health. Search box: queryKey ['chats', {q}], keep last result on screen while typing, 150 ms debounce, pass the query `signal` to fetch. Token stream lives in one small store (useSyncExternalStore); on run.done write the final message into the query cache.

Sources: https://registry.npmjs.org/@tanstack/react-query, https://tanstack.com/query/latest/docs/framework/react/guides/optimistic-updates

### R4b [refuted]
Long history lists and long chats need virtualising in Phase 2.

Evidence: Estimate, not measured. @tanstack/react-virtual 3.14.14 exists (MIT, dep @tanstack/virtual-core 3.18.0, headless). But finished messages are memoised so they never re-parse, and the engine can page history 50 rows a time. Earlier research (frontend.md) reached the same call. Virtualising variable-height streaming Markdown adds scroll-anchor bugs.

For the build: No virtualiser in Phase 2. History: useInfiniteQuery, 50 per page, 'Show more'. Chat: memo + CSS `content-visibility: auto` on finished messages. Add @tanstack/react-virtual@3.14.14 only when a test with 1,000 rows or 200 messages shows jank.

Sources: https://registry.npmjs.org/@tanstack/react-virtual, https://tanstack.com/virtual/latest/docs/introduction, /Users/lucasta/projects/gx10-council/docs/research/frontend.md

### R5a [partly] (load-bearing)
The paperclip needs dialog.showOpenDialog from main through preload.

Evidence: Electron dialog is Main-process only, true. But the web-utils docs' own example reads files from an `<input>` in the renderer, so a hidden `<input type="file" multiple>` gives File objects with no IPC. Drop and paste also give File objects in the page. Not run here under sandbox: true.

For the build: Paperclip clicks a hidden file input. Drop zone on the Composer form. Paste handler reads clipboardData.files. All three feed one `addFiles(File[])`. No showOpenDialog, no getPathForFile, no new preload function for attaching. Reject a dropped folder with a per-file error.

Sources: https://www.electronjs.org/docs/latest/api/web-utils, https://www.electronjs.org/docs/latest/api/dialog, https://www.electronjs.org/docs/latest/tutorial/sandbox

### R5b [refuted] (load-bearing)
Upload should go renderer -> preload -> main -> engine.

Evidence: Sandboxed preload may require only contextBridge, crashReporter, ipcRenderer, nativeImage, webFrame, webUtils (+ events, timers, url): no fs. So that route means main reads any path the page names, a wider hole, plus IPC code for progress and errors. The page already holds the File; fetch can send it straight. Both routes need the R3d fix anyway.

For the build: One request per file: POST /files with the File as raw body, name and type in headers or query. No multipart parser in the engine. Engine replies with file id; UI polls GET /files/:id (or listens on SSE) for state: uploading, extracting, OCR, indexing, ready, failed + pages + reason. Chip shows state word then '14 pages'. Send is blocked until every chip is ready or removed.

Sources: https://www.electronjs.org/docs/latest/tutorial/sandbox, https://www.electronjs.org/docs/latest/api/web-utils, /Users/lucasta/projects/gx10-council/ui/electron/preload.cjs

### R6 [confirmed] (load-bearing)
Inline citation markers plus a side sheet can be built from Phase 1 pieces, with shape-and-word marks.

Evidence: Repo: SeatSheet.tsx is a Radix Dialog on the right (Esc closes, focus returns); Chip has kind="citation"; Citation type already has `quote?: string` and `page?: number`; mdast-util-find-and-replace is installed (through remark-gfm, pinned by lockfile only). APG modal rules: focus in on open, Tab trapped, Escape closes, focus back to the opener. Missing: a `verified` field on Citation.

For the build: Marker = real <button> with a number in a `rounded-control` line box, aria-label 'Source 1: Lease 2025.pdf, page 9, quote checked', aria-haspopup="dialog". Sheet shows file, page, page text, quote in <mark> (token fill `hover` + ink underline, no hue). Checked = solid line + check glyph + words 'Quote checked'. Not checked = dashed line + words 'Quote not found on this page' (dashed already means 'not ready' in rule 4). Small remark step turns `[1]` into the marker; unit-test it against react-markdown's URL filter. Chips under the answer stay as now.

Sources: /Users/lucasta/projects/gx10-council/ui/src/components/table/SeatSheet.tsx, /Users/lucasta/projects/gx10-council/ui/src/components/conversation/Cited.tsx, /Users/lucasta/projects/gx10-council/ui/src/lib/events.ts, https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/, /Users/lucasta/projects/gx10-council/docs/design/direction.md

### R7 [confirmed]
History and Library are new screens; frame and atoms are reused.

Evidence: Product plan: 'A searchable list of past chats, grouped by Today, Yesterday and Earlier, that you can rename, pin, delete and export'; Library: 'Drag them in, save an attachment to it... the council searches the Library only when a chat allows it'. Repo: Sidebar links go to /later/history, /later/library, /later/settings, all LaterPage stubs. Reusable: AppFrame, TopBar, Sidebar, Button, IconButton, Chip, Switch, Tooltip, Notice, LiveRegion, useShortcuts, useUrlState, Composer, Question, AnswerText, CitedChips, Radix Dialog pattern from SeatSheet and SeatPicker.

For the build: New pieces: SearchField, ListRow (title, date, pin mark, row menu), GroupHeading (Pinned, Today, Yesterday, Earlier), RowMenu (Radix DropdownMenu: Rename, Pin, Export as Markdown, Export as JSON, Delete), InlineRename, ConfirmDialog (Radix AlertDialog), EmptyState, FileRow (name, pages, size, state, Remove), DropZone, FileStateChip, 'Save to Library' action on a file chip, per-chat Switch 'Search the Library' in Composer, CitationMarker, CitationSheet, EngineBanner (cannot reach engine). New screens: RealChatScreen (one model: no Stage, no SeatPicker), HistoryScreen, LibraryScreen, SettingsScreen. Watched folder and inbox: not in the Phase 2 list; leave out.

Sources: /Users/lucasta/projects/gx10-council/docs/plan/GX10-Council-UI-Plan.txt, /Users/lucasta/projects/gx10-council/ui/src/components/frame/Sidebar.tsx, /Users/lucasta/projects/gx10-council/ui/src/components/frame/LaterPage.tsx

### R8 [partly]
Five settings are enough for Phase 2 (engine address, model status, download progress, storage location, theme).

Evidence: Theme already exists (Sidebar useTheme, localStorage key `theme`). Engine address is forced by R3d (main must know the origin to allow it). Two more fall out of the findings: a connection test and, if the owner agrees, a pairing key. 'Download progress' collides with 'No web access ever': someone must fetch the model file.

For the build: Settings screen, read-mostly: (1) Engine address + 'Check' button + state word (reachable, version). (2) Model: name, state (loading, ready, failed + reason), context size, last tokens per second. (3) Model file: present or progress, only if the engine downloads it. (4) Storage: path on the engine, space used, read-only. (5) Theme: Light, Dark, Match the Mac. (6) Pairing key field, if adopted. Engine address is stored by main (preload function), not localStorage, so main can build its allow-list before the page loads.

Sources: /Users/lucasta/projects/gx10-council/ui/src/components/frame/Sidebar.tsx, /Users/lucasta/projects/gx10-council/ui/electron/main.cjs, /Users/lucasta/projects/gx10-council/docs/BUILD_STATUS.md

### R9a [partly]
msw works both in Node tests and in the Electron renderer.

Evidence: msw 3.0.3: MIT, engines node >=22.12.0, 12 deps (yargs, @inquirer/confirm, tough-cookie, @mswjs/interceptors...), peers optional. Node: `setupServer` from `msw/node`; ReadableStream bodies are documented. Browser mode needs `mockServiceWorker.js` served from the app root over HTTP(S) or localhost; docs say nothing on file://, and the packaged page is file://. Service worker on file:// : not confirmed, likely no (inference).

For the build: Skip msw. Component tests: UI talks to an `EngineClient` interface; tests pass an in-memory `FakeEngine` (scripted events, delays, errors). One fake serves Vitest and the gallery. Zero new test deps.

Sources: https://registry.npmjs.org/msw, https://mswjs.io/docs/integrations/node, https://mswjs.io/docs/integrations/browser, https://mswjs.io/docs/http/mocking-responses/streaming

### R9b [confirmed] (load-bearing)
Playwright can drive the real Electron app end to end against a fake llama-server.

Evidence: Repo: scripts/look-app.mjs already launches the app with `_electron` from @playwright/test 1.64.0 on Electron 44.7.0, and BUILD_STATUS records clean passes, also on the packaged .app. Playwright docs: Electron support is 'experimental'; native dialogs are not intercepted, stub `dialog.showSaveDialog` through `electronApp.evaluate()`. The fake llama-server (Node http: /health, /v1/chat/completions as SSE, records socket close) is own code, not yet written.

For the build: E2E stack per test: fake llama-server (random port) -> real engine (temp data folder) -> Electron app pointed at it by env. Checks: send, stream, Stop (fake sees close within 2 s), regenerate, rename, pin, delete, attach a text file, citation sheet opens, export writes a file (dialog stubbed), engine down shows banner. Keep it a second Playwright project so the 61 checks stay as they are.

Sources: /Users/lucasta/projects/gx10-council/ui/scripts/look-app.mjs, /Users/lucasta/projects/gx10-council/docs/BUILD_STATUS.md, https://playwright.dev/docs/api/class-electron

### R9c [confirmed] (load-bearing)
The Phase 1 mocks and their 61 checks can live beside real chat.

Evidence: Read, not run: checks/gate.spec.ts walks `scenes` from src/review/states.ts; scene routes come from one helper `chat(fixture, q)` -> `/chat/${fixture}?${q}`. App.tsx mounts ReviewBar on every route. The gate aborts any request not to 127.0.0.1:4310, which is right for mocks and wrong for real chat. Scene at states.ts line 251 expects /later/history to be a stub.

For the build: Move mocks to `/sample/:fixture` (change the `chat()` helper, the two routes, useDebate comment). Real chat takes `/chat/new` and `/chat/:id`. ReviewBar and 'Sample data' footer only under /sample, /review, /gallery. Sidebar gets a quiet 'Sample debate' link. Update the later-history, later-library, later-settings scenes when those screens become real. Run `gate` before and after the move: count must stay 61 or the change is explained.

Sources: /Users/lucasta/projects/gx10-council/ui/checks/gate.spec.ts, /Users/lucasta/projects/gx10-council/ui/src/review/states.ts, /Users/lucasta/projects/gx10-council/ui/src/app/App.tsx, /Users/lucasta/projects/gx10-council/ui/src/hooks/useDebate.ts

### R10 [confirmed]
Export = engine builds the text, Electron's save dialog writes it.

Evidence: Electron docs: dialog.showSaveDialog([window, ]options) is Main-process; options defaultPath, filters; resolves {canceled, filePath} (filePath empty when cancelled). Playwright docs show how to stub it in tests. Shapes are design, not fact.

For the build: Engine: GET /chats/:id/export?format=md|json returns text (so headless Phase 3 has export too). Preload gets ONE new function `gx10.saveText({ suggestedName, text })` -> ipcMain.handle -> showSaveDialog -> fs.writeFile; returns {saved, canceled}. Main writes only where the owner pointed; name is cleaned (no slashes, 80 chars). Shapes in recommendations.

Sources: https://www.electronjs.org/docs/latest/api/dialog, https://playwright.dev/docs/api/class-electron

## Recommendations
- **Day-one spike before any UI work**: In the PACKAGED app (file:// page, sandbox on): (1) streaming fetch to http://127.0.0.1:<port> and to a LAN address; (2) AbortController mid-stream; (3) hidden <input type="file"> + drop + paste give File objects; (4) fetch POST with a File body; (5) navigator.clipboard.writeText. Record pass or fail for each. _Why:_ main.cjs now cancels all outside requests and denies all permissions. Electron docs list `local-network`, `loopback-network`, `local-network-access`, `clipboard-sanitized-write`. One outside report says Electron 43 broke file:// -> private address. Nothing is tested on 44.7.0. Whole transport design hangs on this.
- **Streaming Markdown**: Keep react-markdown@10.1.0 + remark-gfm@4.0.1 + existing AnswerText. Add remend@1.4.0 (run on live text only). One state write per animation frame. React.memo on finished messages. Adaptive brake (parse over 8 ms -> update every 100 ms). _Why:_ Measured 7.2 ms per full parse at 10,096 chars, 25.3 ms at 40,384 (Node, this Mac). Look C mapping already exists. One tiny zero-dep add.
- **Code highlighting**: rehype-highlight@7.0.2 (brings lowlight ^3.0.0 and highlight.js ~11.11.x) with a fixed list: javascript, typescript, python, json, bash, xml, css, sql, yaml, markdown, diff. Monochrome CSS by token: keyword weight 650, comment `muted`, rest ink. Copy button = existing Button in CodeBlock, wired for real; label flips to 'Copied' for 2 s. _Why:_ About 183 KB unminified against about 775 KB plus engine for Shiki with the same languages. Sync, one plugin line. Class names let CSS use tokens, so the token guard stays green. Rule 1 of look C bans hue.
- **Stream transport and Stop**: fetch POST -> text/event-stream, parsed with eventsource-parser@4.1.1 `EventSourceParserStream`. Events: run.started, run.status, delta, citations, run.timings, run.done, run.error; each with runId + seq. Stop = POST /runs/:id/stop + abort fetch. Resume = GET /runs/:id/events?after=<seq>, else refetch chat. llama-server asked with `timings_per_token: true`, `return_progress: true`. _Why:_ No server package for WebSocket needed; same parser both ends; llama-server stops on socket close (source checked, 1 s poll).
- **Reaching the engine safely**: Renderer fetches the engine direct. main.cjs: allow exactly the saved engine origin; grant `local-network`, `loopback-network`, `local-network-access` (and `clipboard-sanitized-write` if needed) only when the asking page is the app's own. Engine: CORS for the app, requires `Authorization: Bearer <key>` on every route but /health, checks Host header. Phase 2 on the Mac: engine binds 127.0.0.1, main starts it and hands it a random key, owner types nothing. _Why:_ Page origin is `null` (file://), which any sandboxed frame on any site also sends, so origin checks alone prove nothing. A key is the only real guard for personal files with no login.
- **Server state**: @tanstack/react-query@5.104.1 for lists, one chat, files, library, settings, health, and optimistic rename, pin, delete (onMutate recipe from the docs). Token stream in one small store with useSyncExternalStore. No @tanstack/react-virtual. _Why:_ One dep, well-known to coding agents, removes hand-made cache, cancel and rollback code. Lists are paged by the engine.
- **Attachments path**: Renderer -> engine direct. One POST /files per File with raw body. Sources: hidden file input (paperclip), drop on Composer, paste. Status by poll of GET /files/:id every 500 ms while not ready (React Query refetchInterval). Chip states in words: Uploading, Reading, Reading scan (OCR), Indexing, then '14 pages'; failure = error mark + reason + Remove. _Why:_ With sandbox on, main never opens a path the page names. No multipart parser, no IPC, per-file errors for free.
- **Testing**: `EngineClient` TypeScript interface + in-memory FakeEngine for Vitest component tests. A fake llama-server Node script (http, SSE, records socket close) for engine tests and E2E. Second Playwright project using `_electron` (as scripts/look-app.mjs does) with real engine + fake llama-server; dialogs stubbed via electronApp.evaluate. _Why:_ No new test dep. Tests the true path, CORS and permissions included, which a mock inside the page would skip.
- **Mocks beside real chat**: Move sample scenes to `/sample/:fixture`; real chat owns `/chat/new` and `/chat/:id`; ReviewBar only on /sample, /review, /gallery. Change route helper in ui/src/review/states.ts; run `npm --prefix ui run gate` before and after. _Why:_ All 23 scenes take their route from one list, so the move is small and the 61 checks keep guarding look C.
- **Export shapes and saving**: Markdown: `# <title>`, line 'Exported 2026-10-10 14:05, model <name>', then per turn `## You` / `## Answer` with text, 'Files: a.pdf (14 pages)', footnotes `[^1]: Lease 2025.pdf, page 9. "<quote>" (quote checked)`. JSON: {"format":"gx10-council.chat","version":1,"exportedAt":ISO,"chat":{id,title,createdAt,updatedAt,pinned,model,libraryAllowed},"messages":[{id,role,createdAt,text,stopped,files:[{id,name,pages}],citations:[{n,fileId,fileName,page,quote,verified}],timings:{predictedPerSecond,predictedN}}]}. Built by engine; saved by one preload function `gx10.saveText` -> dialog.showSaveDialog. _Why:_ Version field lets Phase 4 add debate turns without breaking old files. Engine-side build serves headless Phase 3.
- **Dependency rule**: Ask Lucas to lift 'never change package.json or the lockfile' for one approved Phase 2 change: + remend@1.4.0, rehype-highlight@7.0.2, eventsource-parser@4.1.1, @tanstack/react-query@5.104.1, all pinned exact. All pure JS, no install-time compile, same on darwin-arm64 and linux-arm64. _Why:_ CLAUDE.md forbids agents touching package.json; Phase 2 cannot start without it.

## Risks
- Renderer cannot reach the engine as the app stands: main.cjs cancels all outside requests and denies all permissions; Chromium Local Network Access may still block a file:// page after the allow-list is fixed. Break reported on Electron 43 by another app; untested on 44.7.0. Spike first.
- No login + engine on the home network: with open CORS any web page opened on any home device, or a DNS-rebinding trick, could read or delete personal files. Page origin `null` cannot be trusted. Needs a pairing key and Host check (inference from how browsers work, not a tested attack).
- Stop may not stop: two hops. If the engine does not pass the abort on, llama-server keeps burning the GPU. Even when right, llama-server polls stop once a second, and a long prompt read may lag more.
- Copy button likely refused by the deny-all permission handler (`clipboard-sanitized-write`). Inference from docs, not run.
- A small model writes bad or no citation markers. UI must show an answer with zero, wrong-numbered or 'not found' citations without breaking; many 'Quote not found' marks may make the feature look broken.
- Parse cost was measured in Node, not in Chromium with DOM commit and highlighting. A 40,000-char answer may still jank; brake and block-memo fallback are planned but unproven.
- Stream lost on sleep or Wi-Fi drop mid-answer: without seq + resume the UI shows a half answer forever. Needs the refetch path and a test.
- Phase 1 never had its review round; moving mocks to /sample and making History, Library, Settings real will touch scenes the 61 checks count. A silent drop in check count would hide lost coverage.
- Build agents will reach for Streamdown, Shiki or shadcn by habit; each fights the token-only palette. The token guard does not scan node_modules, so it will not catch it. Say 'forbidden' in the plan.
- Pasted images and scans: OCR is slow; if Send is not blocked until files are ready, the model answers without the file and cites nothing.
- JetBrains Mono italic is not bundled; any italic in code is a fake slant. lowlight pins highlight.js ~11.11.0, not 11.12.0; fine, but the lockfile must record it.
- rehype-highlight option names and marked's dependency list were not opened in this pass; read both READMEs before pinning.

## Open questions
- Owner: is a one-time pairing key between the Mac app and the GX10 acceptable under 'No login'? (On the Mac in Phase 2 it is automatic and unseen.)
- Owner: code blocks in ink and grey only, no colour: OK? It follows rule 1 of look C but it is a look choice.
- Owner: after Stop, keep the half answer in the chat (marked 'Stopped') or drop it? After 'Try again', keep the old answer or replace it?
- Owner: if the window closes mid-answer, should the engine finish and save the answer, or stop?
- Owner: 'No web access ever' against 'download progress': who fetches the model file, the engine once from the internet, or Lucas by hand?
- Owner: watched folder and inbox for the Library: Phase 2 or later? (Product plan mentions it; the Phase 2 list does not.)
- Owner: wording for the two citation marks ('Quote checked' / 'Quote not found on this page') and where a failed check shows.
- Owner: Delete a chat: confirm box, or delete with an 'Undo' line? Does deleting a chat delete its attached files too?
- Owner: 'Search the Library' switch per chat: on or off by default?
- Owner: export one chat at a time only, or also 'export all'? Should JSON carry the cited page text or only the quote?
- Test: does a file:// page in packaged Electron 44.7.0 reach 127.0.0.1 and a LAN address once the three network permissions are granted and the origin is allow-listed?
- Test: do hidden file input, drop and paste give usable File objects with sandbox: true, and does fetch stream a 200 MB File body without loading it into memory?
- Test: frame times in Chromium 152 for a 40,000-char answer with code blocks, with and without the brake.
- Test: time from Stop click to the fake llama-server seeing its socket close; and the same against real llama-server during prompt reading.

## Independent re-check (overrides the above)

- **R1a** [partly] Me run again, Node v24.19.0, this Mac, renderToStaticMarkup, react-markdown 10.1.0 + remark-gfm 4.0.1 from ui/node_modules. Other sample text, same shape: 3.02 ms at 2,392 chars; 8.60 ms at 9,568; 38.45 ms at 38,272. Stream 9,568 chars, re-parse every 32 chars: 299 parses, 1,211 ms. Bit slower than first numbers, still linear. DOM commit in Chromium still NOT measured by anyone. Hand-made 'adaptive brake' is own code to get wrong: React 19 useDeferredValue on live text does same job (my judgement, not measured).
- **R1b** [refuted] Facts hold. npm view: streamdown 2.7.0, Apache-2.0, peers react + react-dom ^18.0.0 || ^19.0.0, 15 deps. Me scan dist/chunk-D32TOXHM.js (84,649 bytes): text-muted-foreground x21, bg-muted x20, rounded-md x17, border-border x15, bg-background x15, bg-sidebar x7, shadow-lg x4, text-primary x3, shadow-sm, bg-red-50, bg-red-100, text-red-600/700/800, bg-black. No http URL in dist. No shiki import in core. Small fix: https://streamdown.ai/docs/getting-started shows only the @source line; the shadcn vars demand sits in the package README (line 70: 'built using shadcn/ui's design system and rely on CSS custom properties') and in https://streamdown.ai/docs/styling. @streamdown/code 2.0.0 dist imports bundledLanguages + bundledLanguagesInfo from 'shiki': true.
- **R1c** [refuted] remend 1.4.0 facts hold (Apache-2.0, no dependencies field, 28,630 bytes, ESM only). One trap missed: option `links` is ON by default. README + dist: half link `[text](url` becomes `[text](streamdown:incomplete-link)`, and dist also appends `](streamdown:incomplete-link)` to a lone open `[`. So half-written citation mark `[1` turns into a fake link, then snaps back: flicker right on the markers (read from source, not run). Use `remend(text, { linkMode: "text-only" })` or `{ links: false }` and unit-test with `[1`. Gap filled: marked 18.1.0 has NO dependencies (npm view), MIT, node >= 20.
- **R2a** [refuted] Sizes hold: @shikijs/langs 4.5.0 11 files = 724,691; @shikijs/core dist/index.mjs 50,089; engine-oniguruma wasm-inlined.mjs 622,442; oniguruma-to-es 4.3.6 unpacked 997,453; prism-core.min.js 7,461. highlight.js 11.12.0: core 76,324 + 11 langs = 106,674 by my sum (first said 106,729; 55 bytes, no matter). BIG fix to build note: rehype-highlight 7.0.2 lib/index.js has `import {common, createLowlight} from 'lowlight'` and `const languages = settings.languages || common`. `common` is used at run time, so bundler keeps all 37 common grammars even when a fixed list is passed (inference from source; not built). 37 files in highlight.js 11.11.2 es/languages = 310,681 bytes + core about 76 KB = about 387 KB unminified, not 183 KB. To really get 183 KB (11 langs + core in 11.11.2 = 182,383 bytes): use lowlight@3.3.0 `createLowlight` direct (package has sideEffects: false) with own 11 imports and a ~20-line own rehype step, or highlight inside CodeBlock. lowlight pins highlight.js ~11.11.0: today that lands 11.11.2. Unknown language: plugin does not throw, leaves plain text (source read). Options are `languages`, `detect` (default false), `aliases`, `plainText`, `prefix`, `subset`.
- **R2c** [refuted, disagrees] First said unverified. Source now read, both ends; still NOT run. Chromium 152.0.7977.130 clipboard_promise.cc: writeText asks permission CLIPBOARD_WRITE through `permission_service_->RequestPermission` (line 746); on refusal rejects NotAllowedError 'Write permission denied.' (lines 585, 622). Electron v44.7.0 electron_permission_manager.cc: when a request handler is set, every request goes to it; no special case for clipboard. content_converter.cc maps it to string `clipboard-sanitized-write`. main.cjs handler is `callback(false)`. So Copy fails as is. Fix: in the handler allow only `clipboard-sanitized-write` for the app's own page. Also true and stronger than first said: Electron 44 breaking change REMOVED the `clipboard` module from every renderer, so preload cannot do it; other way is IPC to main. Keep it in the spike.
- **R3a** [confirmed] Holds. eventsource-parser 4.1.1: MIT, no deps, engines node >=22.12, export `./stream`, README line 157 `EventSourceParserStream`. llama.cpp server README line 609: browser `EventSource` cannot be used, no POST. 'From memory' part now checked: on Node v24.19.0 `typeof WebSocket` = function, no server global; nodejs.org page says no built-in WebSocket server, need ws or socket.io (page words are scoped to Node v22).
- **R3b** [partly] Source holds on master today: server-http.cpp lines 685, 736, 757 `req.is_connection_closed`, line 916 `req.should_stop`; server-context.cpp line 40 `constexpr int HTTP_POLLING_SECONDS = 1;`, lines 4935-4942 stream ends on should_stop; server-queue.h line 215 'should_stop function will be called each polling_interval_seconds'. README lines 595, 597: `timings_per_token`, `return_progress` real. Two hops point right. Not run end to end by me either. One hole in the design: plan has both 'socket close stops llama-server' and 'resume after drop'. Pick one rule for a dropped renderer link: run goes on (then engine must buffer events) or run stops (then no resume route needed).
- **R3d** [refuted] Repo part true: main.cjs `onBeforeRequest` cancels all but file:, data:, blob:, devtools:, chrome-extension: and dev host; handler denies every permission. Permission strings `local-network`, `local-network-access`, `loopback-network` are in Electron v44.7.0 session.md lines 981-983. FIX on the cause: Chromium 152.0.7977.130 ip_address_space_util.cc lines 436-438: file URL gets `kLoopback`; `IsLessPublicAddressSpaceLNA` (line 418) treats kLocal and kLoopback as same. So by Chromium source a file:// page calling 127.0.0.1 or 192.168.x.x is NOT a Local Network Access request; the three grants may do nothing (inference from source, not run in Electron). feishin #2430 / PR #2593 (both open, no maintainer word, no net::ERR code, macOS 26.6.2, Electron 43.4.1) says the opposite; its 'file:// not treated as local' line is the reporter's guess. Same symptom fits a second cause: macOS local network privacy (Apple TN3179: macOS 15 on, 'Making an outgoing TCP connection: yes', identity by code signature). Also: with no check handler set, Electron answers permission checks true (electron_permission_manager.cc line 366-371). ui/index.html has no CSP meta, so no connect-src wall. Spike in packaged app stays the only proof.
- **R4a** [partly] npm view: @tanstack/react-query 5.104.1, MIT, peer react ^18 || ^19, one dep @tanstack/query-core 5.104.1 (that one has no deps). Recipe in docs holds; docs code now reads `context.client.cancelQueries(...)` inside onMutate. Missed default that bites THIS app: docs network-mode page: default networkMode is 'online'; with no connection a query sits `paused` 'until you have connection again'. Mac with Wi-Fi off + engine on 127.0.0.1 = lists never load. Set `networkMode: "always"` for queries AND mutations in the QueryClient defaults. Docs also show a lighter way (show `variables` while `isPending`), but rename/pin show in two places (sidebar, History), so the cache way is right.
- **R4b** [refuted] Versions hold: @tanstack/react-virtual 3.14.14, MIT, dep @tanstack/virtual-core 3.18.0. 'No need in Phase 2' is judgement, not measured, by first or by me.
- **R5a** [partly] Holds. Electron v44.7.0 web-utils.md example reads `document.querySelector('input[type=file]').files[0]` in the renderer; dialog is main only. Not run under sandbox by me either. Missed trap in main.cjs: `will-navigate` lets ANY `file:` URL through (isAllowed). A file dropped outside the drop zone makes Chromium navigate the window to that file: app screen gone (inference from code + normal Chromium drop behaviour, not run). Need window-level `dragover` + `drop` preventDefault, and narrow will-navigate to the app's own index.html.
- **R5b** [refuted] Holds. sandbox.md lines 55-58: preload gets only `contextBridge`, `crashReporter`, `ipcRenderer`, `nativeImage`, `webFrame`, `webUtils` + `events`, `timers`, `url`. No fs. Two details to pin: (1) HTTP header values must be Latin-1; a file name with other letters in a header makes fetch throw. Put name in the query with encodeURIComponent. (2) `Authorization` or any custom header makes every call a CORS preflight; preflight carries no key, so engine must answer OPTIONS without the key check. Both from web platform rules, not run here.
- **R6** [confirmed] Repo facts hold: SeatSheet.tsx is Radix Dialog; Chip has kind "file" | "citation"; Citation is `{ kind: "file"; fileId: Id; page?: number; quote?: string }`, no `verified`. APG page: Tab wraps inside, Escape closes, focus back to opener; it says NOTHING on `aria-haspopup` (first note names it; fine to use, just not from APG). mdast-util-find-and-replace 3.0.3 is in package-lock.json only, pulled by remark-gfm: importing a package not named in package.json is brittle; name it in the approved list or hand-walk the tree. Marker flicker: see R1c (remend links).
- **R8** [partly] Holds. Theme: src/components/frame/hooks.ts `useTheme`, `localStorage.setItem("theme", next)`. Sidebar already has links /later/history, /later/library, /later/models, /later/settings. Add one thing: project rules still say 'Nothing leaves this machine: no CDN, no outside requests' (CLAUDE.md) and main.cjs header says the same; engine address on the home network breaks those words. Rule text must change with Lucas's OK before build.
- **R9a** [partly] npm facts hold: msw 3.0.3, MIT, engines node >=22.12.0, 12 deps, peers vite, graphql, typescript all optional. Browser docs: 'Service Workers are meant to be served via HTTPS', localhost HTTP allowed; no word on file:// or Electron. Service worker on file:// still NOT settled by a source I could open. One hint: Electron custom-scheme doc lists `allowServiceWorkers` (default false) as a privilege to grant a scheme. Skip msw stays right.
- **R9b** [confirmed] Holds. look-app.mjs imports `_electron` from @playwright/test and can open the packaged app via `--packaged`. Playwright docs: 'experimental support for Electron automation', v21+, dialogs not intercepted, stub with electronApplication.evaluate(). Two catches: (1) `gate` script runs bare `playwright test`; a second project in playwright.config.ts would run inside gate and share its webServer. Use a separate config file and script; that is a package.json change needing Lucas's OK. (2) Playwright docs: packaged app launch times out if fuse `EnableNodeCliInspectArguments` is set false. package-mac.mjs sets no fuses today; keep it so.
- **R9c** [partly, disagrees] Can live side by side: yes in principle, read not run. But the move as written breaks one scene. states.ts: four scenes use plain routes, not the `chat()` helper: "/placeholder", "/gallery", "/chat/new" (id `chat-new`, must show `[data-part=composer]` count 1), "/later/history". If real chat takes `/chat/new`, scene `chat-new` opens the REAL screen, which calls the engine; gate aborts every request not to http://127.0.0.1:4310 and that fails the check. Move `chat-new` to `/sample/new` too, or make real new-chat draw with no engine call. More files hold the old path than first listed: Sidebar.tsx line 10 (`to: "/chat/new"`, `match: "/chat"`), ReviewBar.tsx line 45 (`pathname: `/chat/${toFixture}``), ChatScreen.tsx, moments.ts, useDebate.ts, App.tsx. Count: states.ts has 24 scene entries by grep; BUILD_STATUS says 61 checks over 23 scenes.

### Objections to recommendations
- Code highlighting pick (rehype-highlight@7.0.2 with fixed list): size claim wrong. Plugin source does `import {common, createLowlight} from 'lowlight'` and falls back to `common`, so all 37 grammars ride along: about 387 KB unminified, not 183 KB (inference from source, not built). Lighter and same look: lowlight@3.3.0 `createLowlight` + own 11 language imports. Then dep list is lowlight (and highlight.js ~11.11.x under it), not rehype-highlight.
- Streaming Markdown pick (remend on live text): default `links` handler rewrites a half `[1` into `[1](streamdown:incomplete-link)`. Citation markers will flicker. Call `remend(text, { linkMode: "text-only" })` or `{ links: false }`. Test with half markers.
- Streaming Markdown pick: 'adaptive brake (parse over 8 ms -> update every 100 ms)' is hand-made timing code for agents to get wrong. React 19 `useDeferredValue` on the live text is built in. Fewer parts for a non-programmer owner. Judgement, not measured.
- Copy button: will fail as built. Chromium 152 asks permission for writeText; Electron 44.7.0 sends it to main.cjs handler which says `callback(false)`. Electron 44 also removed `clipboard` from renderers. Plan must include the handler change (allow `clipboard-sanitized-write` for own page only), not 'if needed'.
- Reaching the engine pick: grant list `local-network`, `loopback-network`, `local-network-access` rests on one outside bug report. Chromium 152 source puts file:// pages in loopback space, so these grants may do nothing, and the real wall on macOS may be Apple's own Local Network prompt (macOS 15+, outgoing TCP to LAN needs owner's Allow; identity by code signature). App is packaged UNSIGNED (package-mac.mjs comment). Apple note warns of odd behaviour without stable identity. Matters in Phase 3 (Mac -> GX10), not for 127.0.0.1 in Phase 2. Spike must include a LAN address from the packaged app.
- Reaching the engine pick: `Authorization: Bearer <key>` on every route makes every call a CORS preflight. Engine must answer OPTIONS with no key, and return `Access-Control-Allow-Headers`. Simpler and safer: main adds the header in `session.webRequest.onBeforeSendHeaders` for the engine origin, so the page never holds the key (Electron API exists; this use not run).
- Reaching the engine pick, Phase 3: key travels in clear over plain http on the home network, and owner said 'No login'. A pairing key is a small login. Needs Lucas's plain yes before it goes in the plan.
- Fallback 'custom scheme with protocol.handle': if that scheme is registered `secure: true` (as Electron docs example does), a direct fetch from the page to http://192.168.x.x becomes mixed content and is blocked; only 127.0.0.1 is exempt. So with a custom scheme ALL engine calls must go through main's net.fetch. Also Electron security list item 18 says prefer custom scheme over file://, and file:// gives origin `null`. Trade-off should be written down, not left as footnote. Mixed-content part is inference from web rules, not run.
- Stream transport pick: 'Resume = GET /runs/:id/events?after=<seq>' forces the engine to keep an event log per run. For one user on one LAN, simpler: on drop, refetch the chat and poll until the run is done. And it clashes with 'socket close stops llama-server': state plainly whether a dropped renderer link stops the run.
- Server state pick: TanStack Query defaults hurt here. `networkMode` default 'online' pauses queries when the Mac has no network, though engine is on 127.0.0.1. Set `networkMode: "always"`. Also set retry on purpose so 'engine down' banner is not held back (default retry count from memory, not re-checked).
- Attachments pick: 'name and type in headers or query'. Header cannot carry non-Latin-1 file names; fetch throws. Use query + encodeURIComponent. And drop outside the Composer navigates the window away because main.cjs `will-navigate` allows any file: URL. Fix both before drag and drop ships.
- Testing pick: 'second Playwright project' inside playwright.config.ts would run under `npm run gate` (bare `playwright test`) and inherit its webServer on 127.0.0.1:4310. Needs own config file + own script. That is a package.json change: add it to the one approved change.
- Mocks pick: 'real chat owns /chat/new' collides with scene `chat-new` (route "/chat/new" in states.ts, not via the helper). Gate aborts all requests not to 127.0.0.1:4310. Move that scene too. Sidebar.tsx and ReviewBar.tsx also hold the old path.
- Dependency rule pick: list is not final. Likely real list: remend@1.4.0, eventsource-parser@4.1.1, @tanstack/react-query@5.104.1, lowlight@3.3.0 (in place of rehype-highlight@7.0.2), plus mdast-util-find-and-replace@3.0.3 if the citation step imports it (today only transitive). All pure JS, no compile, same on darwin-arm64 and linux-arm64 (from package metadata; none has install scripts checked by me).
- Rules clash: CLAUDE.md says 'Nothing leaves this machine: no CDN, no outside requests'; look-app.mjs exits 1 on any failed non-file request; gate.spec.ts aborts all but 127.0.0.1:4310. Real chat to an engine breaks the letter of all three. Ask Lucas to reword the rule ('only the engine address') before agents start.

### Missed by the first pass
- macOS Local Network privacy (Apple TN3179): macOS 15+, outgoing TCP to a LAN address needs the owner's Allow; tracked by code signature and main executable UUID. App is unsigned today. Phase 3 risk; not in first report at all.
- Chromium 152.0.7977.130 source: file: URL = `kLoopback` address space; LNA check treats local and loopback alike. First report built its permission plan without reading this.
- main.cjs `will-navigate` + `isAllowed` let any file: URL through: a stray file drop replaces the app with that file. Same hole lets the page load any local file as image or frame. Tighten when attachments arrive.
- TanStack Query `networkMode` default 'online' = paused queries on an offline Mac.
- rehype-highlight always bundles lowlight `common` (37 grammars).
- remend default `links` handling clashes with `[1]` citation markers; remend also has `htmlTags` (strips half HTML tag) and `katex` (closes `$$`) on by default: choose options on purpose.
- CORS preflight with a key header; non-Latin-1 file names in headers.
- No Content-Security-Policy in ui/index.html or main.cjs (checked: none). Electron security list item 7 asks for one. When engine address arrives, add CSP with `connect-src` = that origin only; it is a second lock beside onBeforeRequest.
- Copy text source: AnswerText CodeBlock keeps React children; after highlighting they are spans, not a string. Copy must read plain text (e.g. the <pre> element's textContent). Small, but agents miss it.
- Monochrome highlight CSS (.hljs-keyword and so on) must live in src/styles/ or use only token vars: token-guard.mjs scans .css under src except src/styles and src/fixtures.
- Streaming screen behaviour not covered: stay pinned to bottom only while owner has not scrolled up; announce to screen reader once at end, not per token (LiveRegion.tsx exists in src/components/frame).
- Safety already in place, worth writing into the plan so no agent undoes it: react-markdown renders no raw HTML by default; AnswerText draws links as words and images as captions, so model text cannot make a network request. Do NOT add rehype-raw.
- Electron 44 removed the `clipboard` module from all renderer processes (breaking-changes.md, 44.0). Any agent habit of `require('electron').clipboard` in preload fails.
- Playwright docs: packaged-app launch needs fuse `EnableNodeCliInspectArguments` not set to false. If fuses get hardened later, E2E on the packaged app breaks.
- eventsource-parser must tolerate llama-server keep-alive lines: server-context.cpp has an `sse_ping_interval` path in the stream loop (seen in source; exact wire form not read). Add one fake-server test with a ping/comment line.
- U7 and U10 had no claims to re-check (History, Library, export shapes). Not verified by me; export shape is design, not fact.
