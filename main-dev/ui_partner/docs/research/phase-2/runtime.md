# Phase 2 research: runtime

Read-only research on 2026-10-10. The re-check section overrides the findings where they differ. Written in the agents' short style.

## Summary
Engine can be all Node/TS, no compile step. Checked today on this Mac (Node 24.19.0 and the repo's Electron 44.7.0 binary, Node 24.21.0, Chromium 152.0.7977.130).

Big finds:
- node:sqlite works with no flag in both. FTS5 is in. loadExtension is there. Node docs call it "Stability 1.2, Release candidate", not Stable.
- better-sqlite3 13.0.3 is now N-API with prebuilt binaries inside the npm tarball (darwin-arm64, linux-arm64). No rebuild step. Good fallback.
- Plain JS cosine is fast enough: 50,000 x 768 floats = 23.8 ms measured here. sqlite-vec 0.1.9 not needed in Phase 2.
- @hono/node-ws is deprecated. WebSocket now lives in @hono/node-server 2.1.4 (needs ws). SSE over fetch covers Phase 2; no WebSocket needed yet.
- Node type stripping is Stable since v24.12.0. Works in Electron 44.7.0 run-as-node too (tested).
- Electron 44.7.0 protocol.handle relays streamed bodies but gives handler NO abort signal (read in source). Stop must be its own call.

Not proven today (could not create files, so no real Electron main/utilityProcess run): node:sqlite + spawn + fetch inside utilityProcess; app:// origin string; mixed-content rule for app:// page calling LAN http. All need a first-day spike.

Pick: engine = plain Node program, Hono + zod, node:sqlite, JS cosine, SSE. App starts it with utilityProcess.fork; tests and GX10 start it with plain node. Keep ui/ lockfile untouched: no npm workspaces in Phase 2.

## Claims

### R1a [partly] (load-bearing)
node:sqlite is usable in Electron 44 main process and utilityProcess with no flag.

Evidence: Tested on repo binary Electron 44.7.0 in ELECTRON_RUN_AS_NODE mode: require('node:sqlite') works, SQLite 3.53.4, no flag, no warning. Electron PR 47706 fixed 'No such binding: sqlite' (37.2.0) and was backported to 36/37/38. Main process and utilityProcess themselves NOT run today (read-only task); same binary, so inference.

For the build: First-day spike: open node:sqlite inside utilityProcess of Electron 44.7.0, make FTS5 table. If fail, switch to better-sqlite3 13.0.3. Keep all DB calls behind one small module so swap is cheap.

Sources: https://github.com/electron/electron/pull/47706, https://github.com/electron/electron/issues/47671, https://www.electronjs.org/docs/latest/api/utility-process

### R1b [partly] (load-bearing)
node:sqlite is stable in Node 24.

Evidence: Node v24 docs: 'Stability 1.2, Release candidate'; history says v24.15.0 'SQLite is now a release candidate'; no --experimental-sqlite flag since v22.13.0/v23.4.0. Not Stability 2. No ExperimentalWarning seen on 24.19.0 here.

For the build: Use it, but pin Node (24.21.0 on GX10, Electron 44.7.0 on Mac) and wrap it. API is sync: keep queries short; never run long scans while a reply streams.

Sources: https://nodejs.org/docs/latest-v24.x/api/sqlite.html

### R1c [confirmed] (load-bearing)
Node 24's bundled SQLite has FTS5 and can load extensions.

Evidence: Measured here: pragma compile_options lists ENABLE_FTS5 on Node 24.19.0 (SQLite 3.53.3) and Electron 44.7.0 (3.53.4); fts5 table, snippet() and bm25() ran. db.loadExtension is a function; docs: needs constructor option allowExtension: true, else enableLoadExtension cannot turn it on. linux-arm64 build not tested (inference: same Node source).

For the build: Full-text search = FTS5 in node:sqlite. Bind blobs as Uint8Array (Float32Array.buffer wrapped). Re-run the same 10-line probe on the GX10 on day one of Phase 3.

Sources: https://nodejs.org/docs/latest-v24.x/api/sqlite.html

### R1d [refuted]
better-sqlite3 needs a native rebuild for Electron.

Evidence: better-sqlite3 13.0.3 (2026-08-05, MIT, engines node >=22, 27,302,969 bytes unpacked) ships prebuilds/darwin-arm64.node and prebuilds/linux-arm64.node inside the npm tarball; package.json has "gypfile": false. v13.0.0 notes: first version on N-API, prebuild-install removed, binaries 'should theoretically work across different versions of Node.js and Electron'. Not loaded in Electron here.

For the build: Keep as fallback only. Cost if used: a .node file cannot live inside app.asar and cannot be bundled into one JS file; must ship beside the engine.

Sources: https://github.com/WiseLibs/better-sqlite3/releases/tag/v13.0.0, https://unpkg.com/better-sqlite3@13.0.3/package.json, https://unpkg.com/better-sqlite3@13.0.3/?meta

### R2a [confirmed]
sqlite-vec has prebuilt packages for both targets and loads with node:sqlite and better-sqlite3.

Evidence: sqlite-vec 0.1.9 (2026-03-31, 'MIT OR Apache'); optional deps sqlite-vec-darwin-arm64 0.1.9 (vec0.dylib 161,896 bytes) and sqlite-vec-linux-arm64 0.1.9 (vec0.so 156,520 bytes). Its load(db) just calls db.loadExtension(getLoadablePath()); docs show node:sqlite with { allowExtension: true }. README: 'pre-v1, so expect breaking changes'. 0.1.9 is brute force; ANN (rescore, ivf, DiskANN) only in 0.1.10-alpha.1..4 (latest alpha 2026-05-18). Not loaded here (not installed).

For the build: Do not use in Phase 2. If used later: getLoadablePath() uses import.meta.resolve, which breaks in a single-file bundle and inside app.asar; call db.loadExtension(absolute path to vec0.dylib / vec0.so) yourself.

Sources: https://unpkg.com/sqlite-vec@0.1.9/index.mjs, https://unpkg.com/sqlite-vec@0.1.9/package.json, https://unpkg.com/sqlite-vec-linux-arm64@0.1.9/?meta, https://alexgarcia.xyz/sqlite-vec/js.html, https://github.com/asg017/sqlite-vec/releases, https://raw.githubusercontent.com/asg017/sqlite-vec/main/README.md

### R2b [confirmed] (load-bearing)
Plain JS cosine over Float32Array BLOBs is enough for tens of thousands of passages.

Evidence: Measured here (node 24.19.0, Apple M5, synthetic data, dot product + top 20): 20,000 x 384 = 4.8 ms; 50,000 x 384 = 12.1 ms (73 MB); 50,000 x 768 = 23.8 ms (146 MB); 50,000 x 1024 = 31.7 ms (195 MB); 200,000 x 768 = 94.8 ms (586 MB). node:sqlite: insert 50,000 blobs of 3,072 bytes in 47 ms, read all in 29 ms (in-memory DB). sqlite-vec author gives brute-force limit 'probably in the 100's of thousands'. GX10 speed not measured.

For the build: Store each embedding as a BLOB row (little-endian float32, normalised). Load all into one Float32Array at engine start; scan in JS; fuse with FTS5 bm25 in JS. Revisit only past about 200,000 passages.

Sources: https://alexgarcia.xyz/blog/2024/sqlite-vec-stable-release/index.html

### R3a [partly] (load-bearing)
utilityProcess supports node:sqlite, child_process spawn (llama-server) and fetch streaming.

Evidence: Docs: fork starts 'a child process with Node.js and message ports enabled', 'the equivalent of child_process.fork'; no API list given. Same Electron 44.7.0 binary in run-as-node mode passed all three today (sqlite, spawn /bin/echo, fetch reading 3 SSE chunks). utilityProcess itself not run. Limits from docs: fork only after app 'ready'; stdin cannot be piped; stdout/stderr can ('pipe').

For the build: Spike first. Engine must not use process.send, process.parentPort or stdin. It reports its port by printing one JSON line on stdout. Proven fallback: spawn(process.execPath, [engine.mjs], { env: { ...env, ELECTRON_RUN_AS_NODE: '1' } }).

Sources: https://www.electronjs.org/docs/latest/api/utility-process, https://raw.githubusercontent.com/electron/electron/v44.7.0/docs/api/utility-process.md

### R3b [refuted] (load-bearing)
Engine should run inside the Electron main process.

Evidence: node:sqlite is sync and document parsing is heavy: both would freeze the window's main process. Electron security page warns against processing untrusted content in the unsandboxed main process. Fuses doc names utility processes as the route for 'a standalone Node.js process'. Phase 3 needs the same code under plain Node, so a separate process is the shape anyway. (Design judgement, not a measurement.)

For the build: Engine = separate process, plain Node program. Main only: start it, read port, proxy, stop it.

Sources: https://www.electronjs.org/docs/latest/tutorial/security, https://www.electronjs.org/docs/latest/tutorial/fuses

### R4 [partly]
The engine can run headless on the GX10 under plain Node 24 with no sudo, kept alive by a systemd user unit.

Evidence: nodejs.org lists node-v24.21.0-linux-arm64.tar.xz and .tar.gz (unpack to home, no sudo). Upstream systemd policy: org.freedesktop.login1.set-self-linger defaults to 'yes' for all (so `loginctl enable-linger` for self needs no sudo on stock systemd); set-user-linger is auth_admin_keep. DGX OS policy and glibc not checked. ELECTRON_RUN_AS_NODE on GX10 would need the whole Electron linux-arm64 app there: no gain.

For the build: Phase 3 outline: unpack tarball to ~/opt/node; ~/.config/systemd/user/gx10-engine.service with Restart=on-failure; systemctl --user enable --now; loginctl enable-linger (try without sudo; sudo once if 'Access denied'). Phase 2 only has to keep the engine free of Electron imports.

Sources: https://nodejs.org/dist/latest-v24.x/, https://raw.githubusercontent.com/systemd/systemd/main/src/login/org.freedesktop.login1.policy, https://manpages.ubuntu.com/manpages/xenial/man1/loginctl.1.html

### R5a [refuted] (load-bearing)
Hono on Node needs @hono/node-ws for WebSocket.

Evidence: hono.dev: '@hono/node-ws is deprecated'. @hono/node-server 2.1.4 README: `import { serve, upgradeWebSocket } from '@hono/node-server'`, install ws, pass `websocket: { server: new WebSocketServer({ noServer: true }) }`. Caveat in docs: header-changing middleware (CORS) on a WebSocket route can throw 'can't modify immutable headers'.

For the build: Do not install @hono/node-ws 1.3.1. If WebSocket is ever wanted: ws 8.22.0 + built-in upgradeWebSocket.

Sources: https://hono.dev/docs/helpers/websocket, https://unpkg.com/@hono/node-server@2.1.4/README.md

### R5b [partly] (load-bearing)
The engine needs WebSocket to stream tokens.

Evidence: Hono has streamSSE (writeSSE with data/event/id, stream.onAbort). Local test: node:http SSE read chunk by chunk with fetch in Electron 44.7.0's Node. llama-server itself streams SSE (docs/research/serving.md). Electron 44.7.0 protocol.handle can relay a streamed Response but cannot carry WebSocket. Whether Phase 4 debate wants two-way push is a later call; SSE + POST can do it. Judgement, not proof.

For the build: Phase 2: SSE only. A run lives in the engine; events get a rising seq; GET /runs/:id/events?after=<seq> replays then follows. Stop = POST /runs/:id/stop. No ws package in Phase 2.

Sources: https://hono.dev/docs/helpers/streaming, https://raw.githubusercontent.com/electron/electron/v44.7.0/lib/browser/api/protocol.ts

### R5c [confirmed]
Hono is the smallest robust server set versus Fastify or bare node:http.

Evidence: npm today: hono 4.13.13 (MIT, 1,294,526 bytes, 0 deps); @hono/node-server 2.1.4 (MIT, 138,009 bytes, peer hono, node >=20); fastify 5.12.5 (2,953,131 bytes, 15 direct deps incl. pino) + @fastify/websocket 11.3.4; ws 8.22.0 (151,410 bytes, 0 deps). All pure JS. 'Robust' is my judgement.

For the build: hono@4.13.13 + @hono/node-server@2.1.4. Use built-ins: hono/bearer-auth, hono/streaming, hono/body-limit.

Sources: https://www.npmjs.com/package/hono, https://www.npmjs.com/package/@hono/node-server, https://www.npmjs.com/package/fastify, https://www.npmjs.com/package/ws

### R6 [confirmed]
Shared TypeScript types plus zod at the edge is enough; no tRPC or OpenAPI needed.

Evidence: zod 4.6.5 (MIT, 0 deps, 6,140,311 bytes unpacked); @hono/zod-validator 0.9.1 (peers zod ^3.25.0 || ^4.0.0, hono >=4.11.2). Hono RPC (hc<AppType>) is optional sugar with listed costs: same hono version both sides, strict on both tsconfigs, IDE slows with many routes; SSE typing not covered. @trpc/server is 11.19.0: adds a framework on both sides.

For the build: One contract folder: zod schemas for every request body and every SSE event; types by z.infer. Engine validates with zValidator. UI imports the TYPES only (import type), so ui/ needs no new package.

Sources: https://www.npmjs.com/package/zod, https://www.npmjs.com/package/@hono/zod-validator, https://hono.dev/docs/guides/rpc

### R7a [confirmed] (load-bearing)
Electron 44 guidance: custom protocol instead of file://, strict CSP, sandbox, context isolation, checked IPC senders.

Evidence: Security checklist items 3, 4, 7, 17, 18, 19, 20; 'Pages running on file:// have unilateral access to every file on your machine'; CSP best sent as a header. protocol docs give app:// sample with registerSchemesAsPrivileged({standard, secure, supportFetchAPI}) before 'ready' and a path-escape check. Repo today: ui/electron/main.cjs uses win.loadFile (file://) and no CSP anywhere in ui/index.html or main.cjs.

For the build: Phase 2: serve ui/dist from app://gx10/ via protocol.handle; send CSP header from that handler; add 'app:' to isAllowed() in main.cjs (its onBeforeRequest block would cancel it otherwise). Keep sandbox: true, contextIsolation: true.

Sources: https://www.electronjs.org/docs/latest/tutorial/security, https://www.electronjs.org/docs/latest/api/protocol

### R7b [unverified] (load-bearing)
An app:// page can call the engine directly over http with CORS, on localhost now and on the LAN later.

Evidence: No source opened states the Origin header value of a standard custom scheme, nor whether Chromium blocks http://<LAN ip> from a 'secure' custom scheme as mixed content. 127.0.0.1 case is ordinary web behaviour but not run here. Electron source does show handlers see initiatorOrigin and that 'origin: null' is dropped.

For the build: Avoid the question: page calls only its own origin (/api/...). Main forwards to the engine and adds the token. Then no CORS, no mixed content, token never in the page. Spike must prove the forward path streams.

Sources: https://raw.githubusercontent.com/electron/electron/v44.7.0/lib/browser/api/protocol.ts, https://www.electronjs.org/docs/latest/api/protocol

### R7c [partly] (load-bearing)
protocol.handle can proxy a streaming reply and tells the handler when the page aborts.

Evidence: Source v44.7.0 lib/browser/api/protocol.ts: Response.body ReadableStream is relayed (Readable.fromWeb, or native relay for an untouched net.fetch response); upload bodies arrive as a stream with duplex 'half'. But the Request is built with headers, method, referrer, body only: NO signal. Past bug #41872 'ReadableStream is malformed when protocol.handle'd' (closed 2024-04-16). Not run today.

For the build: Never rely on fetch abort for Stop: explicit POST /runs/:id/stop. Engine ends idle streams itself (heartbeat comment line every ~15 s, drop on write failure). If spike shows chunks arrive late or clumped, fall back to direct fetch to http://127.0.0.1:<port> with strict CORS allowlist.

Sources: https://raw.githubusercontent.com/electron/electron/v44.7.0/lib/browser/api/protocol.ts, https://github.com/electron/electron/issues/41872

### R7d [partly] (load-bearing)
No login is safe enough on a home network with bind address, shared token, Host and Origin checks.

Evidence: llama-server precedent in earlier research: default bind 127.0.0.1, --api-key guards all but /health. hono/bearer-auth exists (token or verifyToken). Host/Origin rule against DNS rebinding is standard practice; I opened no Electron or Hono page that prescribes it. Traffic on LAN in Phase 3 is plain http: token and chats readable by anyone on the network path.

For the build: Phase 2: listen 127.0.0.1 only; random 32-byte token made by main each launch, passed by env; every route but /health needs 'Authorization: Bearer'; reject Host not in {127.0.0.1:<port>, localhost:<port>}; reject any request carrying an Origin header not on allowlist; send no CORS headers. Phase 3 adds LAN bind + token file (mode 0600) + owner decision on TLS.

Sources: https://hono.dev/docs/middleware/builtin/bearer-auth, https://www.electronjs.org/docs/latest/tutorial/security

### R8a [confirmed] (load-bearing)
webUtils.getPathForFile gives a dropped file's real path with contextIsolation and sandbox on.

Evidence: Sandbox doc lists modules a sandboxed preload may require from 'electron': contextBridge, crashReporter, ipcRenderer, nativeImage, webFrame, webUtils. web-utils doc: call it in preload, expose through contextBridge; returns '' for a File not on disk; it replaced File.path; docs advise not handing full paths to web content.

For the build: Preload: gx10.attachFiles(files: File[]) -> for each, webUtils.getPathForFile -> ipcRenderer.invoke('attach', paths) -> main checks sender + file, then STREAMS the bytes to the engine (PUT /files). Engine never trusts a client path. Same code path in Phase 3 when engine is remote. Page gets back file ids, not paths.

Sources: https://www.electronjs.org/docs/latest/tutorial/sandbox, https://www.electronjs.org/docs/latest/api/web-utils

### R8b [refuted]
The preload can be an ES module split over files.

Evidence: ESM doc: sandboxed preloads cannot use ESM. Sandbox doc: sandboxed require is a limited polyfill; cannot split preload into several CommonJS files without a bundler; only events, timers, url from Node.

For the build: Keep ui/electron/preload.cjs as ONE hand-written CommonJS file. Each bridge function wraps one ipcRenderer.invoke channel; never expose ipcRenderer itself (checklist item 20). Main checks event.senderFrame origin on every handler (item 17).

Sources: https://www.electronjs.org/docs/latest/tutorial/esm, https://www.electronjs.org/docs/latest/tutorial/sandbox

### R8c [unverified] (load-bearing)
Child processes stop cleanly on quit and after a crash without extra work.

Evidence: Docs: child.kill() 'Terminates the process gracefully. On POSIX, it uses SIGTERM'; 'exit' event gives code. Nothing opened says a utilityProcess dies when main crashes. Earlier research (serving.md) already warns: llama-server children of a dead gateway keep running and hold memory.

For the build: Build it: main on 'before-quit' -> child.kill(), wait for 'exit' up to ~12 s. Engine on SIGTERM -> SIGTERM llama-server, 10 s, SIGKILL, close DB. Engine takes --parent-pid and exits when that pid is gone (poll 2 s). Engine writes llama-server pid + port to a file; on start, sweeps a stale one. Test each path with the fake server.

Sources: https://raw.githubusercontent.com/electron/electron/v44.7.0/docs/api/utility-process.md, https://www.electronjs.org/docs/latest/api/utility-process

### R9a [partly] (load-bearing)
npm workspaces for ui/ + engine/ + shared/ bring no trouble.

Evidence: Not tested. Seen in repo: ui/ has its own package-lock.json and CLAUDE.md forbids changing it; hoisting would break hard-coded paths: ui/playwright.config.ts ('node node_modules/vite/bin/vite.js'), ui/scripts/look.mjs, slice.mjs, embed-fonts.mjs, ui/biome.json, both .command files (ui/node_modules/.bin/electron). ui/scripts/package-mac.mjs packs dir=ui with prune:false and keeps only /dist, /electron, /package.json: no node_modules reaches the app today. Vite 8 / TypeScript 6 project references / Vitest 5 workspace behaviour: no source opened.

For the build: Phase 2: no workspaces. engine/ is its own package with its own lockfile. Contract lives in engine/src/contract/; ui imports it with `import type` (erased, nothing to resolve at run time). Engine ships as ONE bundled file so packager never needs node_modules.

Sources: https://www.npmjs.com/package/@electron/packager, https://github.com/electron/forge/issues/869

### R9b [confirmed] (load-bearing)
Node 24 runs TypeScript directly, stable.

Evidence: Docs v24.21.0: 'Stability: 2 - Stable'; v23.6.0 on by default, v24.3.0 no warning, v24.12.0 stable. Limits: no enum, no runtime namespace, no parameter properties, no import aliases (unless --experimental-transform-types); '.ts' extension mandatory in imports; tsconfig.json ignored, so no paths; `import type` required; no .tsx; refuses .ts under node_modules; no source maps. Measured: process.features.typescript = 'strip' on Node 24.19.0 and on Electron 44.7.0 run-as-node.

For the build: engine/tsconfig.json: noEmit, target esnext, module nodenext, erasableSyntaxOnly, verbatimModuleSyntax, allowImportingTsExtensions (or rewriteRelativeImportExtensions). Dev and tests: `node engine/src/main.ts`, no build. Vitest transforms TS itself and would accept an enum that Node rejects: tsc with erasableSyntaxOnly must be in the check script.

Sources: https://nodejs.org/docs/latest-v24.x/api/typescript.html

### R10a [confirmed]
A scripted fake llama-server in plain Node is enough for engine tests.

Evidence: Local test: node:http server writing 'data: ...\n\n' every 30 ms, read chunk by chunk with fetch. Real server facts to copy are in docs/research/serving.md: GET /health gives 503 {"error":{"code":503,"message":"Loading model","type":"unavailable_error"}} then 200 {"status":"ok"}; SIGTERM = clean stop; stream ends with timings. The fake's fidelity to the real b11429 stream must be checked once against the real binary.

For the build: engine/test/fake-llama-server.mjs, started as a REAL child process through the same supervisor (env GX10_LLAMA_BIN). Modes by flag: slow start (503 for N ms), normal deltas, stall, mid-stream socket destroy, exit code 1 at boot, ignore SIGTERM. Listen on port 0 and print the port. Record one real llama-server stream to a fixture and replay it.

Sources: https://nodejs.org/docs/latest-v24.x/api/http.html

### R10b [confirmed]
Playwright can drive the Electron app with the engine running.

Evidence: Playwright docs: Electron support is 'experimental', Electron v21+, `_electron.launch({ args, executablePath, env, cwd, timeout })`; known issue: launch times out if fuse nodeCliInspect is set to false. Repo already does it: ui/scripts/look-app.mjs imports `_electron` from @playwright/test 1.64.0 and deletes ELECTRON_RUN_AS_NODE from env first. Open bug #8278: native file dialogs emit no filechooser event. No 2026 flake list found.

For the build: E2E: launch app with env GX10_LLAMA_BIN=fake and a temp data dir; wait for an 'engine ready' mark in the page, not a sleep; workers 1; try/finally app.close(); after close assert engine pid and fake pid are gone. Test attach through the preload bridge with a path, not through the native dialog.

Sources: https://playwright.dev/docs/api/class-electron, https://github.com/microsoft/playwright/issues/8278

## Recommendations
- **Database**: node:sqlite (built in; Node 24.21.0 / Electron 44.7.0), FTS5 for full text, WAL mode, new DatabaseSync(path, { timeout: 5000 }). One file db.ts wraps it. _Why:_ Zero install, zero native file, same on Mac and GX10. FTS5 + snippet + bm25 ran here on both runtimes. Wrapper makes swap cheap.
- **Vector search**: Plain JS: embeddings as float32 BLOB rows in SQLite, one in-memory Float32Array, dot-product scan, merge with FTS5 hits in JS (rank fusion). _Why:_ Measured 23.8 ms for 50,000 x 768 on this Mac. No extension to load, sign, or ship per platform.
- **Where engine runs in Phase 2**: Separate process. App: utilityProcess.fork(<resources>/engine.mjs, ['--port','0','--data',dir,'--parent-pid',pid], { stdio: 'pipe', serviceName: 'GX10 Engine', env: { ...process.env, GX10_ENGINE_TOKEN } }) after app ready. Dev, tests, GX10: `node engine/src/main.ts` or `node engine.mjs`. Engine prints one line {"event":"listening","port":N}. _Why:_ Keeps window alive while SQLite and parsing work. Same program runs headless later. Electron docs point to utility processes for this.
- **Day-one spike (before any feature work)**: One throwaway Electron 44.7.0 script that proves, inside utilityProcess: node:sqlite + FTS5; spawn + kill of a child; fetch stream; and in the window: app://gx10 page streaming an SSE reply through protocol.handle with chunks arriving one by one; what happens to the child when main is kill -9'd. _Why:_ These are the unproven joints. Each has a ready fallback, so the spike picks, it does not block.
- **Server**: hono@4.13.13 + @hono/node-server@2.1.4. Token replies by SSE (hono/streaming streamSSE). No WebSocket in Phase 2. _Why:_ Two pure-JS packages, zero transitive deps, typed, built-in bearer auth and body limit. SSE matches llama-server's own stream and passes through protocol.handle and the Vite dev proxy.
- **Stream shape**: POST /chats/:id/messages returns { runId }. GET /runs/:id/events?after=<seq> is the SSE stream (id: seq on every event; heartbeat comment every ~15 s). POST /runs/:id/stop. Regenerate = new run on same message. Engine owns the run and saves tokens as they come. _Why:_ Abort does not reach a protocol.handle handler (44.7.0 source). A dropped link (Phase 3 Wi-Fi) must not lose or kill an answer; the page just re-follows from its last seq.
- **Contract**: zod@4.6.5 + @hono/zod-validator@0.9.1 in engine only. engine/src/contract/*.ts holds schemas for bodies and SSE events and exports z.infer types. ui imports with `import type` through a tsconfig path. _Why:_ One source of truth, checked at the engine edge, no new package in ui/, no codegen step.
- **How the page reaches the engine**: Page is served at app://gx10/ by protocol.handle and calls only relative /api/... . Main forwards /api/* to http://127.0.0.1:<port> with Node's global fetch, adds Authorization: Bearer <token>, returns the Response as is. In Vite dev/preview, server.proxy does the same job. _Why:_ No CORS, no token in the page, no file://, CSP can be connect-src 'self', and the LAN mixed-content question never comes up in Phase 3. UI code never knows an address.
- **Security set, Phase 2**: Engine: listen('127.0.0.1'); bearer token on all but GET /health; Host allowlist; reject unknown Origin; no CORS headers; body limit on uploads. App: registerSchemesAsPrivileged([{ scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true } }]); CSP header `default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'`; keep sandbox, contextIsolation, deny-all permission handler, navigation and new-window blocks already in main.cjs; check senderFrame on each IPC handler. _Why:_ Follows Electron checklist items 3, 4, 7, 13, 14, 17, 18, 20. Token + Host check stop other local pages and DNS rebinding.
- **Repo layout and build**: ui/ untouched. New engine/ (own package.json, own lockfile, "type": "module", exact pins). Contract inside engine/src/contract/. Run TS directly in dev and tests. For the app and the GX10: esbuild@0.28.2 bundles engine/src/main.ts to one engine.mjs (platform node, format esm, target node24); packager copies it with extraResource (outside app.asar). _Why:_ No lockfile churn, no hoisting breakage of 6 hard-coded ui paths, no node_modules inside the app. One file to copy to the GX10.
- **Logging**: No log library. Engine writes JSON lines to stdout. Main pipes child.stdout/stderr to a file under app.getPath('logs') with a size cap. On GX10 the systemd journal keeps it. llama-server gets its own log file; last lines shown on failure. _Why:_ Zero deps; same on both machines.
- **Tests**: vitest 5.0.3 (node environment) in engine/ against the real Hono app + temp SQLite file + fake-llama-server.mjs child. Playwright _electron (already in ui/scripts/look-app.mjs) for 3-5 end-to-end flows. Existing 61 browser checks keep running against vite preview with /api proxied to an engine started with the fake. _Why:_ Engine tests hit the plain-Node path (what the GX10 runs); Electron tests hit the utilityProcess path. Both launch routes stay covered.

## Risks
- utilityProcess path is unproven here (node:sqlite, spawn, fetch stream inside it were only tested in the same binary's run-as-node mode). If the spike fails, launcher switches to spawn(process.execPath) with ELECTRON_RUN_AS_NODE=1 (proven today).
- Orphans: if app or engine dies hard, llama-server keeps running and holds GBs of memory and its port; next start could load a second copy. Needs pid file sweep + --parent-pid watch + tests. No doc opened says utilityProcess dies with a crashed main.
- protocol.handle proxy: streamed bodies are relayed per 44.7.0 source, but handler gets no abort signal, and chunk timing through it was not measured. Tokens could arrive clumped. Fallback is direct fetch with CORS; UI must hide the choice behind one engineFetch function.
- node:sqlite is 'Release candidate' (Stability 1.2) in Node 24, and Mac (Electron's Node 24.21.0) and GX10 (plain Node) may carry different SQLite patch levels (3.53.4 vs 3.53.3 seen today). API or behaviour could shift on a Node/Electron bump. Pin both; wrap in one module.
- Sync SQLite and JS vector scan block the engine's event loop. Fine at 24 ms; a big import (thousands of pages, OCR) in the same process would stall token streaming. Heavy parsing/OCR likely needs a worker thread or child process (other research area).
- Phase 3 LAN traffic is plain http: token, chats and files readable on the home network path. No login makes the token the only lock. Owner must accept or ask for TLS.
- Single-file bundle may not suit document libraries that carry WASM or worker files (PDF, OCR picks from other areas). Those must be marked external and copied beside engine.mjs; packaging plan depends on those picks.
- Two runtimes run the same engine in Phase 2 (system Node 24.19.0 in tests, Electron's Node 24.21.0 in the app). A bug may show in only one. Keep both in the gate.
- Vitest accepts TypeScript that plain Node rejects (enum, parameter properties, imports without .ts). Without tsc erasableSyntaxOnly in the check script, tests pass and the real engine fails to start.
- main.cjs today cancels every request not file:/data:/blob:/devtools:. Moving to app:// without updating isAllowed() gives a blank window. Electron net.fetch from main would also hit that filter; Node's global fetch does not.
- The packaged app is ad hoc signed and unsigned for other Macs. A child binary (llama-server) and any dylib it loads must sit outside app.asar and may meet Gatekeeper quarantine if downloaded by a browser. Not tested.
- Playwright's Electron support is marked experimental; native file dialogs cannot be driven (#8278). Tests must go through the preload bridge.
- Type-only import from engine/ into ui/ means `npm --prefix ui run check` needs engine/ installed first, and ui's tsconfig include must grow. Small, but it touches a file agents were told not to change lightly.

## Open questions
- Owner: in Phase 3, is plain http with a shared token on the home network acceptable, or must traffic be encrypted (adds a certificate step on the GX10)?
- Owner: may Phase 2 agents edit ui/electron/main.cjs, ui/tsconfig.json, ui/vite.config.ts and ui/scripts/package-mac.mjs (needed for app://, type import, dev proxy, extraResource)? ui/package.json and lockfile can stay untouched.
- Owner: when the Mac app quits, should a running answer stop (Phase 2 engine dies with the app) - and in Phase 3 should the GX10 keep working with the app closed?
- Test: inside utilityProcess on Electron 44.7.0 - does node:sqlite open a file DB with FTS5, does spawn + SIGTERM of a child work, does fetch stream chunk by chunk?
- Test: does an SSE reply forwarded through protocol.handle('app') reach the page token by token, and what does the engine see when the page cancels the read?
- Test: when main is kill -9'd, does the utilityProcess exit by itself? Does the --parent-pid watch catch it within 2 s?
- Test: what Origin header does a page on app://gx10 send, and does Chromium 152 block fetch to http://<LAN ip> from it as mixed content? Only matters if the proxy route is dropped.
- Test (Phase 3, GX10): does node-v24.21.0-linux-arm64 run on its DGX OS, does its node:sqlite list ENABLE_FTS5, and does `loginctl enable-linger` work without sudo there?
- Test: real embedding size and passage count. 50,000 x 768 is my assumed ceiling; the embedding model pick (other area) sets the real number and the scan time on the GX10's CPU.
- Test: record one real llama-server stream from the Mac's build (deltas, timings, error on kill) so the fake server copies real bytes, not my memory of the format.

## Independent re-check (overrides the above)

- **R1a** [partly] Me re-run on repo binary, run-as-node: Electron 44.7.0 has Node 24.21.0, SQLite 3.53.4, require('node:sqlite') works, no flag, no warning. PR 47706 merged 2025-07-15; backports 47755 (36-x-y), 47756 (37-x-y), 47757 (38-x-y). Main and utilityProcess still NOT run (read-only). Electron 44.7.0 test files spec/node.spec.ts and spec/api-utility-process.spec.ts have no sqlite test: no upstream proof. Spike stays must.
- **R1b** [partly] 
- **R1c** [confirmed] Me measure more, both runtimes (Node 24.19.0 and Electron 44.7.0 run-as-node): ENABLE_FTS5 on; trigram tokenizer works; no allowExtension -> ERR_INVALID_STATE 'extension loading is not allowed'; with allowExtension: true -> call reaches dlopen (ERR_LOAD_SQLITE_EXTENSION on fake path). No real extension loaded. { timeout: 5000 } accepted (pragma busy_timeout = 5000). linux-arm64 not tested.
- **R1d** [refuted] Original right. Exact: better-sqlite3 13.0.3, "gypfile": false, no install script, one dep node-addon-api ^8.0.0. prebuilds/darwin-arm64.node 1,980,736 bytes; prebuilds/linux-arm64.node 2,066,328 bytes. v13.0.3 note: 'use Ubuntu 22.04-arm' for build (so glibc floor near 2.35: inference). Not loaded in Electron by me either.
- **R2b** [confirmed] Me re-measure, Node 24.19.0, this Mac, synthetic: 50,000 x 768 dot + top 20 = 28.0 ms per scan (original 23.8 ms; same size class). Memory 146 is MiB (153.6 MB). Blog quote real: 'probably in the 100's of thousands depending on your dimensions/quantization techniques'. GX10 speed not measured.
- **R3a** [partly] Doc limits right. New from source: utility entry script is loaded by Node ESM loader (lib/utility/init.ts) and Electron test 'is launches an mjs file' uses stdio 'pipe' -> engine.mjs entry is OK. child.kill() = base::Process::Terminate (SIGTERM), exit code mapped to 0. NOT proven: that a JS process.on('SIGTERM') handler runs inside utilityProcess. No upstream test for sqlite or spawn there. utilityProcess itself not run by me.
- **R3b** [refuted] 
- **R4** [partly] Exact: node-v24.21.0-linux-arm64.tar.xz is 30,843,004 bytes (HTTP 200), released 2026-09-07; check it against SHASUMS256.txt in same folder. Node 24 floor for linux arm64: kernel >= 4.18, glibc >= 2.28 (BUILDING.md). systemd upstream policy: set-self-linger yes/yes/yes, set-user-linger auth_admin_keep. DGX OS own polkit rules and glibc still not read: stays partly.
- **R5a** [refuted] Original right. More: @hono/node-ws 1.3.1 peer wants @hono/node-server ^1.19.11, so it does not fit 2.1.4 at all. npm has no deprecated flag on it; hono docs say it ('@hono/node-ws is deprecated').
- **R5b** [partly] 
- **R7a** [confirmed] Checklist items right (18 = no file://, 7 = CSP, 17 = IPC sender, 20 = no raw Electron API). Add: 44.7.0 also has protocol.registerSource (Experimental: serve folder, no JS handler) but doc says 'A scheme has either a handler or a source', so it cannot share app:// with an /api forwarder: keep protocol.handle. Doc also says 'webRequest listeners apply to these requests': main.cjs isAllowed() must add app:.
- **R7b** [unverified] Direct http call still not proven. Now known: page origin of a standard scheme is a real one (Electron test: initiatorOrigin = 'http-like://page', so app://gx10); same-origin fetch on standard + supportFetchAPI scheme works (Electron test). New risk for direct call: Chromium 152 gives a non-file page with no IP address space kUnknown, treated as public; a call to 127.0.0.1 or LAN then needs permission 'loopback-network' / 'local-network' (listed in Electron 44.7.0 session.md). main.cjs denies every permission -> direct call likely blocked. That last step is inference from source, not run.
- **R7c** [partly, disagrees] Stream relay: yes (source + tests). 'No signal on Request': true. But 'abort does not reach handler' is wrong: when client goes away, native loader calls destroy on the body stream (node_stream_loader.cc ~NodeStreamLoader: 'Destroy the stream if not already ended'); Electron tests 'calls destroy on aborted body stream' and 'lets the client abort mid-body' prove it. So a page abort or reload closes the forwarded upstream body. Gap left: abort before the handler has returned a Response is not seen. Issue 41872 closed 2024-04-22, not 2024-04-16. Not run by me.
- **R7d** [partly] Original right. Add: hono bearerAuth token must match /[A-Za-z0-9._~+/-]+=*/ (hex or base64url is fine). Hono has built-in csrf middleware that checks Origin and Sec-Fetch-Site; no built-in Host check opened: hand-write 5 lines. Electron security page has no Host or rebinding rule (grep: none).
- **R8a** [confirmed] 
- **R8b** [refuted] 
- **R8c** [refuted, disagrees] Claim is false, not just unproven. Node docs: 'On Linux, child processes of child processes will not be terminated when attempting to kill their parent', and children 'may continue running after the parent exits'. So llama-server lives on. Chromium 152 child_thread_impl.cc: on IPC channel error the child calls TerminateCurrentProcessImmediately(0): a utility child dies at once when main dies, with NO JS cleanup (that it applies to Electron's Node utility process is inference; not run). So under utilityProcess the --parent-pid poll never gets to act; it only helps the spawn fallback. Real guard = stale pid-file sweep at next start; before kill, check that pid is really llama-server (pid reuse).
- **R9a** [partly] Repo facts match. Add measured: packaged app has Contents/Resources/app.asar, signature adhoc, TeamIdentifier not set. Vite 8.3.4 types have preview proxy (ui/node_modules/vite/dist/node/index.d.ts:861 'proxy?:'). Workspace behaviour of Vite 8 / TS 6 / Vitest 5 still not tested by anyone.
- **R9b** [confirmed] 

### Objections to recommendations
- CSP pick breaks page now. ui/index.html has inline theme <script>; built ui/dist/index.html keeps it (1 inline <script>, measured). `script-src 'self'` blocks it. Fix: move it to a file, or add its sha256 to script-src. 21 .tsx files use style= so 'unsafe-inline' for style stays needed.
- Stream shape reason is wrong. Page abort DOES reach the forwarder: Electron destroys the response body stream on client loss (node_stream_loader.cc + test 'calls destroy on aborted body stream'). Design still good, but engine must treat a closed SSE link as 'viewer left', never as Stop. Keep POST /runs/:id/stop.
- Direct-fetch fallback likely blocked. Chromium 152 Local Network Access: app:// page counts as public (inference from ip_address_space_util.cc); call to 127.0.0.1 needs 'loopback-network', LAN needs 'local-network'. main.cjs denies all permissions. If fallback is used: allow those two for origin app://gx10 only. Not run.
- Forwarder code traps. (a) Node fetch with a stream body needs duplex: 'half' (measured: TypeError 'RequestInit: duplex option is required when sending a body.'). (b) If agents copy Electron doc sample with net.fetch, repo's webRequest.onBeforeRequest block may cancel it (inference; not run): Node global fetch avoids that. (c) ui/scripts/look-app.mjs counts any failed non file:/data:/blob: request as 'outside': add app:.
- 'ONE bundled engine.mjs, no node_modules' will not hold inside Phase 2. Document parts (PDF, OCR, embeddings) bring worker files, .wasm, trained data; llama-server is a binary. Plan a folder from day one: engine/ = engine.mjs + assets/ + bin/, copied by extraResource (app has app.asar: measured). Inference; exact parts depend on documents research.
- File attach by path through preload + IPC is more code and cannot run in the 61 browser checks (plain Chromium, no preload). Simpler: page does fetch('/api/files', { method: 'PUT', body: file }). protocol.ts reads file-backed upload chunks from disk as a stream; Electron tests 'can receive streaming fetch upload'. One path for Electron, browser tests and Phase 3. Keep webUtils.getPathForFile for later folder features only. Also (estimate, not tested): main reading ~/Documents, ~/Desktop, ~/Downloads by path can raise macOS folder prompts, and ad hoc signing may make grants not stick.
- Phase 3 on Mac: macOS 15+ Local Network privacy (Apple TN3179). App that reaches a LAN box gets a system prompt; helper children count as the app; tools run from Terminal are exempt, so dev works while packaged app can fail. Apple: unsigned and ad hoc code is tracked unreliably, 'sign it with an Apple-issued code-signing identity'. Our app is ad hoc (measured). Owner cost: maybe a paid Apple developer ID. Decide before Phase 3.
- utilityProcess + crash: engine dies at once with no cleanup (Chromium child self-terminate; inference for Electron). llama-server orphan keeps GBs on a 24 GB Mac. --parent-pid poll does nothing in that mode. Guard = pid-file sweep at start (check pid is llama-server first). Also unproven: JS SIGTERM handler inside utilityProcess. Add to spike. Safer clean stop: main sends POST /shutdown (with token), waits, then child.kill().
- Contract import cost. ui `import type` of engine/src/contract/*.ts that import zod: ui tsc must find zod in engine/node_modules, so `npm --prefix ui run check` fails on a fresh checkout until `npm ci` ran in engine/; ui tsconfig needs allowImportingTsExtensions for the '.ts' imports. Inference from TS rules, not run. Cheaper: contract types as plain TS (no zod import); engine zod schemas use `satisfies` against them.
- Random port + random token per launch does not fit dev and tests: Vite server.proxy / preview.proxy and Playwright need a fixed target and must add the Authorization header. Give engine env GX10_ENGINE_PORT and GX10_ENGINE_TOKEN override for dev and tests.
- Sync DB + JS vector scan + parsing in one engine thread: 28 ms scan is fine, but PDF parse, OCR and embedding batches will stall token streaming and heartbeat. Put ingest in a worker_thread (own node:sqlite connection, WAL). First researcher said 'keep queries short' only.
- Three runtimes differ today: Mac Node 24.19.0 (SQLite 3.53.3), Electron 44.7.0 Node 24.21.0 (SQLite 3.53.4), GX10 planned 24.21.0. node:sqlite is Stability 1.2. Tests under plain node run a different SQLite than the app. Move Mac Node to 24.21.0 (official tarball or .pkg, no Homebrew) or accept and note.

### Missed by the first pass
- Electron 37+ rule: utility process only WARNS on unhandled promise rejection; plain Node 24 exits. Same engine acts two ways. Add process.on('unhandledRejection') that logs and exits(1) in engine. Source: https://raw.githubusercontent.com/electron/electron/v44.7.0/docs/breaking-changes.md
- protocol.registerSource (Experimental) in Electron 44.7.0: serves a folder with no JS, but cannot share a scheme with a handler. Not usable with same-origin /api forward. Source: docs/api/protocol.md v44.7.0.
- Chromium Local Network Access permissions exist in Electron 44.7.0: 'local-network', 'loopback-network', 'local-network-access'. Deny-all handler in main.cjs touches them. Source: docs/api/session.md v44.7.0.
- macOS Local Network privacy (TN3179) for Phase 3, and ad hoc signature of current app (codesign: Signature=adhoc, TeamIdentifier=not set). https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy
- utilityProcess macOS options: allowLoadingUnsignedLibraries (needed to load unsigned native libs once app is properly signed: hits better-sqlite3 fallback and any sqlite-vec dylib) and disclaim (child gets own privacy identity). Source: docs/api/utility-process.md v44.7.0.
- Page origin moves from file:// to app://gx10: saved theme in localStorage is lost once; hash routes fine. Trivial, tell owner.
- node:sqlite has backup() (typeof function, measured both runtimes): use for safe copy of chat DB before schema change. Use PRAGMA user_version for migrations. No library needed.
- Node 24.21.0 linux-arm64 floor glibc >= 2.28; better-sqlite3 13.0.3 linux-arm64 built on Ubuntu 22.04-arm. Read `ldd --version` on GX10 day one of Phase 3.
- SSE in page: plan fetch + stream reader, not EventSource (EventSource on a custom scheme not checked by anyone: unverified).
- Spike list should add: SIGTERM handler in utilityProcess; .mjs entry from extraResource path; upload PUT with file body through protocol.handle to engine; CSP header with inline-script hash; what dies when main gets kill -9 (engine and its spawned child, both).
