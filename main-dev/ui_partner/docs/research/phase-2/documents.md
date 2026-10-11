# Phase 2 research: documents

Read-only research on 2026-10-10. The re-check section overrides the findings where they differ. Written in the agents' short style.

## Summary
Read-only. Nothing installed, nothing written. Versions from `npm view` 2026-10-10. Three things measured on this Mac (in-memory only): node:sqlite FTS5 queries, brute-force vector speed, Electron-as-Node probe. All else from registry, package source, official docs. No PDF, OCR or docx was actually run: speeds and quality are NOT measured.

Stack pick, all prebuilt or pure JS/WASM for darwin-arm64 and linux-arm64, no compile on install:
- PDF text + render: `pdfjs-dist@6.4.299` legacy build + `@napi-rs/canvas@1.0.10`
- OCR: `tesseract.js@7.0.0` (WASM) + `@tesseract.js-data/eng@1.0.0` local file
- Images: `sharp@0.35.5`; HEIC: `heic-decode@2.1.0`
- Word: `mammoth@1.13.0`. Sheets: `read-excel-file@9.3.12`. CSV: `papaparse@5.7.0`
- Sniff: `file-type@22.1.1`. Zip pre-scan: `yauzl@3.4.0`. Encoding: `TextDecoder` fatal, then `chardet@2.2.0`
- Search: FTS5 in built-in `node:sqlite` (works in Node 24.19 and Electron 44.7.0) + vectors + RRF k=60
- Quote check: normalise, exact, then `approx-string-match`

Three sharp findings:
1. pdf.js thinks it is in a browser inside an Electron `utilityProcess` (source line checks `process.type`). Engine must run as plain Node or `ELECTRON_RUN_AS_NODE` child. Measured: there `process.type` is undefined, pdf.js Node path is on.
2. Raw question text breaks FTS5 (`?`, `'`, `-`, bare `AND` all error, measured). Every term must be double-quoted and joined with OR.
3. `sharp` prebuilt does NOT read iPhone HEIC. Need WASM decoder.

Not settled: OCR seconds per page, OCR quality on phone photos, pdf.js memory on big files, glibc on the GX10.

## Claims

### R1a [confirmed] (load-bearing)
pdfjs-dist legacy build gives PDF text per page in Node 24, offline, no browser.

Evidence: `pdfjs-dist` 6.4.299 (2026-10-03), Apache-2.0, engines `>=22.13.0 || >=24`, monthly releases. Official Node examples import `pdfjs-dist/legacy/build/pdf.mjs` and loop `getPage(i)` / `getTextContent()` / `cleanup()`. In Node the source sets worker disabled (fake worker, same thread) and reads cmaps, fonts, wasm from disk with `fs`; package ships `/cmaps` 1.17 MB, `/standard_fonts` 0.8 MB, `/wasm` 1.5 MB. Not run here.

For the build: Use `pdfjs-dist@6.4.299`, import `pdfjs-dist/legacy/build/pdf.mjs`. Call `getDocument({ url: <file path>, cMapUrl, cMapPacked: true, standardFontDataUrl, wasmUrl, verbosity: 0 })` with the three dirs resolved from `node_modules/pdfjs-dist/`. No worker setup needed. Store one row per page: 1-based page number + exact text.

Sources: https://registry.npmjs.org/pdfjs-dist, https://raw.githubusercontent.com/mozilla/pdf.js/master/examples/node/getinfo.mjs, https://unpkg.com/pdfjs-dist@6.4.299/legacy/build/pdf.mjs, https://unpkg.com/pdfjs-dist@6.4.299/?meta, https://github.com/mozilla/pdf.js/releases

### R1b [refuted] (load-bearing)
pdf.js Node mode works wherever the engine runs inside Electron.

Evidence: Source: `isNodeJS = ... && !(process.versions.electron && process.type && process.type !== "browser")`. Electron docs list `process.type` = `utility` for utilityProcess, so pdf.js takes browser path there. Measured here: Electron 44.7.0 with `ELECTRON_RUN_AS_NODE=1` gives `process.type` undefined, check is true, Node 24.21.0.

For the build: Run engine as plain Node process (Phase 3) or `child_process.fork` / `ELECTRON_RUN_AS_NODE` child (Phase 2). NOT `utilityProcess`, NOT renderer. Keep Electron fuse `runAsNode` enabled (default) or fork throws. Test worker_threads under Electron main before using them for pdf.js.

Sources: https://unpkg.com/pdfjs-dist@6.4.299/legacy/build/pdf.mjs, https://raw.githubusercontent.com/electron/electron/main/docs/api/process.md, https://raw.githubusercontent.com/electron/electron/main/docs/tutorial/fuses.md

### R1c [partly]
pdf-parse, unpdf or mupdf would be as good a pick as pdfjs-dist.

Evidence: `unpdf` 1.8.1 (MIT) is a wrapper; its bundled PDF.js is v5.6.205, older than 6.4.299. `pdf-parse` 2.4.5 last published 2025-10-29, pins `pdfjs-dist` 5.4.296 and `@napi-rs/canvas` 0.1.80. `mupdf` 1.28.1 is `AGPL-3.0-or-later`. `officeparser` 8.1.1 does all formats in one but has one maintainer, 3 releases in 3 weeks, 31 MB, pins `pdfjs-dist` 6.2.108.

For the build: Use pdfjs-dist direct. One less layer, newest engine, Apache-2.0.

Sources: https://raw.githubusercontent.com/unjs/unpdf/main/README.md, https://registry.npmjs.org/pdf-parse, https://registry.npmjs.org/mupdf, https://unpkg.com/officeparser@8.1.1/README.md

### R1d [confirmed] (load-bearing)
A PDF page can be drawn to an image in Node with pdfjs + @napi-rs/canvas, prebuilt on both platforms.

Evidence: `@napi-rs/canvas` 1.0.11 (2026-10-10; 1.0.10 is 2026-10-01), MIT, has `@napi-rs/canvas-darwin-arm64` (28.1 MB) and `@napi-rs/canvas-linux-arm64-gnu` (29.5 MB, glibc). `pdfjs-dist` lists it as optionalDependency `^1.0.10` and its `NodeCanvasFactory` requires it. Official example `pdf2png.mjs` uses `pdfDocument.canvasFactory` then `canvas.toBuffer("image/png")`. Not run here.

For the build: Pin `@napi-rs/canvas@1.0.10` (9 days old, 1.0.11 is hours old). Render scanned pages at scale about 3 to 4.17 (216 to 300 dpi; 300 dpi Letter = 2550x3300 px, about 34 MB RGBA, my sum), PNG buffer to OCR. Min glibc of the linux build not found: test on GX10.

Sources: https://registry.npmjs.org/@napi-rs/canvas, https://registry.npmjs.org/@napi-rs/canvas-linux-arm64-gnu, https://raw.githubusercontent.com/mozilla/pdf.js/master/examples/node/pdf2png/pdf2png.mjs

### R1e [partly] (load-bearing)
pdf.js tells you when a page is a scan.

Evidence: No such flag found in pdf.js API typings. `getTextContent()` items give the text; `getOperatorList()` exists to look for image paint ops. Rule below is my design, not from a source.

For the build: Per page: count non-space chars. Under 50 chars, or over 20% junk chars (U+FFFD, control chars): send page to OCR. Mark page row `source = text | ocr`. Tune both numbers on real files.

Sources: https://unpkg.com/pdfjs-dist@6.4.299/types/src/display/api.d.ts

### R1f [unverified]
pdf.js memory on big PDFs is known and safe.

Evidence: No measured figure found. API has what is needed: `url` file path load (Node stream with range reads when file > 2 x `rangeChunkSize`), `page.cleanup()`, `loadingTask.destroy()`, `maxImageSize`, `canvasMaxAreaInBytes`.

For the build: Load by `url` not whole-file buffer. One page at a time, `cleanup()` each. Run in a child process with a kill timer and caps (file size, page count). Measure RAM on a 500-page file early.

Sources: https://unpkg.com/pdfjs-dist@6.4.299/legacy/build/pdf.mjs, https://unpkg.com/pdfjs-dist@6.4.299/types/src/display/api.d.ts

### R2a [confirmed] (load-bearing)
mammoth is current, maintained and gives .docx structure.

Evidence: `mammoth` 1.13.0 (2026-09-26), BSD-2-Clause, pure JS, repo pushed same day. 1.12.2 and 1.12.3 fix prototype pollution and a denial-of-service; NEWS says process untrusted docs "in a separate thread with a timeout". `convertToHtml` maps Word heading styles to h1..h6; `extractRawText` exists; Markdown output is deprecated.

For the build: Use `mammoth@1.13.0` `convertToHtml({buffer})`, walk the HTML with `parse5@8.0.1` (MIT, one dep) to get headings, paragraphs, tables. Do not use `convertToMarkdown`. Run in the extraction child.

Sources: https://registry.npmjs.org/mammoth, https://raw.githubusercontent.com/mwilliamson/mammoth.js/master/NEWS, https://raw.githubusercontent.com/mwilliamson/mammoth.js/master/README.md

### R2b [unverified] (load-bearing)
A .docx can be cited by page number like a PDF.

Evidence: No source opened that settles it. From knowledge of the format (inference): pages are made by Word at layout time, the file stores flowing text. mammoth output has no page info.

For the build: Cite .docx as heading path + paragraph number, e.g. `Lease.docx, "3 Rent > 3.2 Deposit", para 41`. Store text per section as the 'page' unit for quote checks. UI chip shows section, not page. Schema needs a generic `locator` (kind + label), not just an int page.

Sources: https://raw.githubusercontent.com/mwilliamson/mammoth.js/master/README.md

### R2c [partly]
Old .doc files should be supported in Phase 2.

Evidence: `word-extractor` 1.0.4 is the pure-JS reader; last publish 2022-06-29. `file-type` core only reports `cfb` for old Office files. `docx4js` 3.3.0 last publish 2024-09.

For the build: Skip .doc and .xls in Phase 2. Detect `cfb`, show plain message: "Old Word format. Save as .docx or PDF and add again."

Sources: https://registry.npmjs.org/word-extractor, https://unpkg.com/file-type@22.1.1/readme.md, https://registry.npmjs.org/docx4js

### R3a [refuted] (load-bearing)
exceljs is maintained.

Evidence: `exceljs` latest stable 4.4.0 is from 2023-10-19; only a prerelease 2024-12-20 since. GitHub repo last push 2025-01-21, 815 open issues. 21.8 MB, 9 old deps (`unzipper` ^0.10, `archiver` ^5, `uuid` ^8).

For the build: Do not use exceljs.

Sources: https://registry.npmjs.org/exceljs, https://api.github.com/repos/exceljs/exceljs

### R3b [refuted] (load-bearing)
SheetJS `xlsx` on the npm registry is the current version.

Evidence: npm `xlsx` is 0.18.5 from 2022-03-24. Current is 0.20.3, Apache-2.0, zero deps, at `https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz`; SheetJS docs say install from that URL. Git tag v0.20.3 dated 2024-07-18, so no release in 2 years.

For the build: Never `npm install xlsx` from the registry. If SheetJS is ever wanted (for .xls, .ods), vendor the 0.20.3 tarball in the repo. `node-xlsx` 0.24.0 (2024-04) is a wrapper on SheetJS: skip.

Sources: https://registry.npmjs.org/xlsx, https://cdn.sheetjs.com/xlsx-latest/package/package.json, https://docs.sheetjs.com/docs/getting-started/installation/nodejs, https://git.sheetjs.com/sheetjs/sheetjs/tags

### R3c [partly] (load-bearing)
A small maintained read-only xlsx reader plus a csv parser is enough.

Evidence: `read-excel-file` 9.3.12 (2026-10-07), MIT, node >=18, 4 small deps, returns all sheets as `[{ sheet, data: rows[][] }]` with string/number/boolean/Date; only empty rows at sheet END are dropped, so row index maps to sheet row. `papaparse` 5.7.0 (2026-08-24), MIT, no deps. Formula cells, merged cells, big-file memory not checked.

For the build: `read-excel-file@9.3.12` (import `read-excel-file/node`) + `papaparse@5.7.0`. Passage = header row + about 20 to 40 data rows as `Header: value` lines, repeat header each passage. Cite `File.xlsx, sheet "Budget", rows 12-31`. The 'page' unit for quote check = one sheet's row block text. Test one file with formulas and merged cells.

Sources: https://unpkg.com/read-excel-file@9.3.12/README.md, https://registry.npmjs.org/read-excel-file, https://registry.npmjs.org/papaparse

### R4 [partly]
Text and code files need an encoding-detection library.

Evidence: Measured in Node 24.19: `new TextDecoder("utf-8",{fatal:true})` throws `ERR_ENCODING_INVALID_ENCODED_DATA` on bad bytes, strips BOM, and `windows-1252`, `utf-16le`, `shift_jis`, `gbk`, `iso-8859-2`, `macintosh`, `windows-1251` all decode. `chardet` 2.2.0 MIT, no deps, 179 KB; `jschardet` 4.0.0 is 7.4 MB.

For the build: Order: BOM check; strict UTF-8 decode; on throw `chardet@2.2.0` `detect()` then `TextDecoder(thatName)`; last resort `windows-1252`. NUL byte in first 8 KB = binary, refuse. Cap text files at 5 MB (my pick). Code = plain text with a fixed extension list (ts, tsx, js, jsx, mjs, cjs, py, rb, go, rs, java, kt, swift, c, h, cpp, cs, php, sh, sql, html, css, json, yaml, yml, toml, xml, ini, md); cite by line range.

Sources: https://unpkg.com/chardet@2.2.0/README.md, https://registry.npmjs.org/jschardet

### R5a [confirmed] (load-bearing)
tesseract.js runs OCR offline in Node on both platforms once eng.traineddata is local.

Evidence: `tesseract.js` 7.0.0 (2025-12-15), Apache-2.0, pure WASM core `tesseract.js-core` 7.0.0 (45 MB unpacked; its `latest` tag still says 6.1.2 but 7.0.0 is what 7.0.0 depends on). Node worker is a `worker_threads` Worker. Source: with no `langPath` it downloads from `https://cdn.jsdelivr.net/npm/@tesseract.js-data/${lang}/4.0.0_best_int`; in Node a non-URL `langPath` is read from disk. npm package `@tesseract.js-data/eng@1.0.0` holds `4.0.0_best_int/eng.traineddata.gz` (2,952,873 bytes). v6 notes: fixed memory leak, fixed Electron main process.

For the build: `createWorker('eng', 1, { langPath: <abs dir of node_modules/@tesseract.js-data/eng/4.0.0_best_int>, gzip: true, cacheMethod: 'none' })`. Without `cacheMethod` it writes `./eng.traineddata` into the working dir. One long-lived worker, reuse it. Input must be an encoded image buffer (png/jpg), not raw pixels. Docs say default page mode is single block: set `tessedit_pageseg_mode` to `PSM.AUTO` for full pages and test. Add a test that fails if any network call happens.

Sources: https://unpkg.com/tesseract.js@7.0.0/src/worker-script/index.js, https://unpkg.com/tesseract.js@7.0.0/src/worker-script/node/getCore.js, https://raw.githubusercontent.com/naptha/tesseract.js/master/docs/local-installation.md, https://registry.npmjs.org/@tesseract.js-data/eng, https://github.com/naptha/tesseract.js/releases

### R5b [unverified] (load-bearing)
OCR speed per page on Apple silicon is published for tesseract.js.

Evidence: None found. Only: v7 release note says runtimes "~15-35%" lower than v6. Docs say no handwriting support.

For the build: Treat OCR as a slow background job with per-page progress and a page cap. Measure seconds per page on this Mac in week one, on 5 real scans and 5 phone photos. My guess only (not measured): a few seconds per page.

Sources: https://github.com/naptha/tesseract.js/releases/tag/v7.0.0, https://raw.githubusercontent.com/naptha/tesseract.js/master/docs/faq.md

### R5c [partly]
onnxruntime-node with PaddleOCR models is an equally simple OCR path.

Evidence: `onnxruntime-node` 1.30.0 (MIT) does ship `bin/napi-v6/darwin/arm64` and `linux/arm64` binaries, but is 301 MB unpacked (all platforms in one package) and has a `postinstall` script. PaddleOCR repo is Apache-2.0. `@gutenye/ocr-models` 1.4.2 carries PP-OCRv4 det 4.7 MB + rec 10.8 MB; wrappers (`@gutenye/ocr-node` 1.4.9, `ppu-paddle-ocr` 6.6.1) add more deps. Accuracy versus Tesseract on photos: no primary figure found.

For the build: Not for Phase 2. Keep OCR behind one function `ocrImage(buffer) -> { text, confidence }` so the engine can be swapped.

Sources: https://unpkg.com/onnxruntime-node@1.30.0/?meta, https://unpkg.com/onnxruntime-node@1.30.0/script/install.js, https://api.github.com/repos/PaddlePaddle/PaddleOCR/license, https://registry.npmjs.org/@gutenye/ocr-node

### R5d [partly]
A small vision model through llama.cpp can do the OCR instead.

Evidence: llama.cpp `docs/multimodal.md` says llama-server takes images on `/chat/completions` and names OCR models with their PRs: PaddleOCR-VL, GLM-OCR, Deepseek-OCR, Dots.OCR, HunyuanOCR. Quality, speed and exact GGUF files not checked. `scribe.js-ocr` 0.16.1 is AGPL-3.0, 46 MB.

For the build: Good Phase 3 upgrade for phone photos on the GX10: no new library, same llama-server. Danger: a vision model can invent fluent text, and the quote check then 'verifies' against invented text. If used, label those pages `source = ocr-model`.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/docs/multimodal.md, https://registry.npmjs.org/scribe.js-ocr

### R6 [partly] (load-bearing)
sharp decodes png, jpg and iPhone heic on both platforms from prebuilt binaries.

Evidence: `sharp` 0.35.5 (2026-09-27), Apache-2.0, node >=20.9.0, prebuilt `@img/sharp-darwin-arm64` and `@img/sharp-linux-arm64` (glibc >= 2.28) plus libvips 1.3.4 (18.2 MB, LGPL-3.0-or-later). Prebuilt formats: JPEG, PNG, WebP, AVIF, TIFF, GIF, SVG. Docs: HEIC with `hevc` "requires the use of a globally-installed libvips compiled with support for libheif, libde265 and x265". `heic-decode` 2.1.0 (ISC) uses `libheif-js` 1.23.5 (WASM, LGPL-3.0, 9 MB).

For the build: png/jpg/webp/tiff: `sharp(buf, { autoOrient: true, limitInputPixels: <default 268402689> })`, resize long side to at most about 3000 px, grayscale, PNG out, to OCR. HEIC: `heic-decode@2.1.0` to raw RGBA, then `sharp(raw, { raw: {width,height,channels:4} })`. Packaged Electron: unpack `sharp` and `@img` from asar (sharp docs).

Sources: https://sharp.pixelplumbing.com/install, https://raw.githubusercontent.com/lovell/sharp/main/docs/src/content/docs/api-output.md, https://registry.npmjs.org/sharp, https://registry.npmjs.org/heic-decode, https://registry.npmjs.org/libheif-js

### R7 [partly] (load-bearing)
There is a sourced best passage size and overlap for retrieval.

Evidence: No single primary source; sizes below are my design. Confirmed: llama-server has `POST /tokenize` (`content`, `add_special`) returning `tokens`, so exact counts are available when a server is up. Earlier research set the embedding server to `-c 2048`.

For the build: Two tables. `pages`: file_id, locator (page no / section / sheet+rows / line range), exact text, source (text|ocr). `passages`: page_id, char_start, char_end, text. Passage target 1,200 chars (about 300 tokens at 4 chars per token, estimate), hard max 1,600, overlap 200, split on paragraph then sentence, NEVER across a page. Use the chars/4 estimate for chunking; use `/tokenize` only for the prompt budget.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md, /Users/lucasta/projects/gx10-council/docs/research/capacity.md

### R8a [refuted] (load-bearing)
A natural question can be passed to FTS5 MATCH as typed.

Evidence: Measured in node:sqlite (Node 24.19.0, SQLite 3.53.3, `ENABLE_FTS5` on; also OK in Electron 44.7.0, SQLite 3.53.4): `what is the deposit?` -> `fts5: syntax error near "?"`; `don't` -> syntax error; `move-in` -> `no such column: in`; bare `AND` -> syntax error. Quoted terms joined by `OR` work; two quoted terms with implicit AND returned 0 rows when the words sat in different passages. SQLite docs: escape `"` by doubling; bm25 k1 1.2, b 0.75, lower is better.

For the build: Query builder: split question on non-letter/digit, lowercase, drop a short stop-word list and 1-char terms, dedupe, cap 16 terms, wrap each as `"term"` (double any `"`), join with ` OR `. Bind as parameter. `ORDER BY rank LIMIT 30`. Table: `fts5(text, file_id UNINDEXED, page_id UNINDEXED, tokenize='porter unicode61 remove_diacritics 2')`. Scope with `AND file_id IN (...)` (measured: works). Wrap in try/catch; on error return no keyword hits, never crash.

Sources: https://www.sqlite.org/fts5.html

### R8b [confirmed]
Reciprocal rank fusion uses k = 60.

Evidence: Cormack, Clarke, Buettcher, SIGIR 2009: score = sum over rankings of 1/(k + r(d)), "where k = 60 was fixed during a pilot investigation"; pilot "indicated that k = 60 was near-optimal, but that the choice was not critical". Text read from the paper PDF.

For the build: Fuse in plain TypeScript: `score += 1 / (60 + rank)` over the keyword list and the vector list (rank from 1). Take 30 from each, keep top 8 after fusion (30 and 8 are my picks; tune).

Sources: http://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf, https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf

### R8c [refuted] (load-bearing)
Vector top-k needs a native SQLite vector extension.

Evidence: Measured here in plain JS: 50,000 vectors x 1024 float32, dot product + sort, 42 ms per query, 205 MB RAM. `sqlite-vec` 0.1.9 (MIT OR Apache) does have prebuilt `sqlite-vec-darwin-arm64` and `sqlite-vec-linux-arm64`, and node:sqlite has `loadExtension`, but it is pre-1.0. Embedding dimension 1024 is assumed, not checked.

For the build: Phase 2: store each embedding as a Float32 BLOB next to its passage, normalise at write, load allowed files' vectors into one Float32Array, brute-force dot product. No extension. Revisit `sqlite-vec` if the Library passes about 200,000 passages. Store model id + dimension with the index.

Sources: https://registry.npmjs.org/sqlite-vec, https://registry.npmjs.org/sqlite-vec-linux-arm64

### R9 [partly] (load-bearing)
A quote can be checked against the cited page with simple exact match.

Evidence: Exact match needs normalising first. Measured: `normalize("NFKC")` turns ligature `ﬁ`/`ﬃ` into `fi`/`ffi` but keeps soft hyphen U+00AD. `fastest-levenshtein` 1.0.16 (2022) only compares two whole strings: wrong tool for find-in-page. `approx-string-match` (MIT) has `search(text, pattern, maxErrors)` -> `{start,end,errors}`; its 2.0.1 was published 2026-10-09 after 2.0.0 on 2021-11-23.

For the build: Normalise both sides the same way: NFKC; lowercase; curly quotes to straight; all dashes to `-`; drop U+00AD; join `-\n` + lowercase letter (line-end hyphen); collapse whitespace to one space. Step 1 `includes` -> `verified`. Step 2 `search(page, quote, floor(quote.length * 0.1))` (0.2 for OCR pages) -> `close`. Step 3 try page-1 and page+1. Else `unverified`: keep the citation, grey chip, label "quote not found on this page". Never delete. Quote min 20 chars, max 300. Pin `approx-string-match@2.0.0` until 2.0.1 diff is read.

Sources: https://unpkg.com/approx-string-match@2.0.1/README.md, https://registry.npmjs.org/approx-string-match, https://registry.npmjs.org/fastest-levenshtein

### R10a [partly] (load-bearing)
file-type identifies every Phase 2 file kind by content.

Evidence: `file-type` 22.1.1 (MIT, node >=22) lists `pdf`, `docx`, `xlsx`, `heic`, `cfb`, `zip`, png, jpg. README: "detecting binary-based file formats, not text-based formats like `.txt`, `.csv`, `.svg`". README also says enforce a size limit and use a worker thread with a timeout for untrusted files.

For the build: `fileTypeFromFile(path)` first. Result undefined -> text path (R4), with extension used only to pick md / csv / code. Result and extension disagree -> trust content, tell the user.

Sources: https://unpkg.com/file-type@22.1.1/readme.md, https://registry.npmjs.org/file-type

### R10b [refuted] (load-bearing)
worker_threads with resourceLimits is enough to contain a bad file.

Evidence: Node docs: worker `resourceLimits` "only affect the JS engine, and no external data, including no `ArrayBuffer`s" and the process may still abort on global out-of-memory. WASM (tesseract, libheif) and native (canvas, sharp) memory sit outside it. `yauzl` 3.4.0 has `validateEntrySizes: true` by default and exposes entry sizes for a pre-scan.

For the build: One extraction CHILD PROCESS (`child_process.fork`), one file at a time, parent kills it on timeout (120 s text, 60 s per OCR page: my picks) and marks the file `failed` with a reason. Before mammoth / read-excel-file: `yauzl` pre-scan, refuse if entries > 10,000, declared total > 500 MB, or ratio > 200 (my picks). Caps: file 100 MB, PDF 2,000 pages, OCR 300 pages per file.

Sources: https://raw.githubusercontent.com/nodejs/node/v24.x/doc/api/worker_threads.md, https://raw.githubusercontent.com/thejoshwolfe/yauzl/master/README.md

### R11 [partly]
Folder watching belongs in Phase 2.

Evidence: Not in the Phase 2 scope list; product plan calls it optional ("let the small Mac app watch a folder such as Downloads", inbox, one click). `chokidar` on npm is 5.0.0 (MIT, ESM-only, node >= 20.19.0, one dep); repo README announces a v6 rewrite (Oct 2026, Node 22+) that is not on npm yet. Node docs: `fs.watch` recursive is supported on macOS (FSEvents).

For the build: Later phase. Outline: watcher lives in Electron main on the Mac (files are on the Mac, engine on the GX10). `chokidar@5.0.0` with `ignoreInitial: true`, `awaitWriteFinish`, depth 0, ignore `.crdownload` / `.download` / dotfiles. New file -> inbox row only; upload on the owner's click. Phase 2 need: make the upload endpoint the single way files enter, so the watcher reuses it.

Sources: /Users/lucasta/projects/gx10-council/docs/plan/GX10-Council-UI-Plan.txt, https://registry.npmjs.org/chokidar, https://raw.githubusercontent.com/paulmillr/chokidar/master/README.md, https://raw.githubusercontent.com/nodejs/node/v24.x/doc/api/fs.md

## Recommendations
- **PDF text per page**: `pdfjs-dist@6.4.299`, import `pdfjs-dist/legacy/build/pdf.mjs`; `getDocument({ url, cMapUrl, cMapPacked: true, standardFontDataUrl, wasmUrl, verbosity: 0 })`; per page `getTextContent()` then `page.cleanup()`; end `loadingTask.destroy()` _Why:_ Official Mozilla build, Apache-2.0, monthly releases, Node path in source, fonts and cmaps inside the package so nothing downloads.
- **Where the engine process runs in Phase 2**: Plain Node-mode child: `child_process.fork` from Electron main (runs with `ELECTRON_RUN_AS_NODE`), same entry file later started by `node` on the GX10. Keep fuse `runAsNode` on. _Why:_ pdf.js turns its Node path off when `process.type` is `utility` or `renderer`. Measured: in Electron-as-Node `process.type` is undefined, Node 24.21.0, node:sqlite + FTS5 work.
- **PDF page to image for OCR**: pdfjs `page.render` on `pdfDocument.canvasFactory` with `@napi-rs/canvas@1.0.10`, scale 3 (about 216 dpi) to start, `canvas.toBuffer("image/png")` _Why:_ Prebuilt for darwin-arm64 and linux-arm64-gnu, MIT, it is what pdfjs itself requires, official example exists.
- **OCR engine**: `tesseract.js@7.0.0` + `@tesseract.js-data/eng@1.0.0`; `createWorker('eng', 1, { langPath: <dir of 4.0.0_best_int>, gzip: true, cacheMethod: 'none' })`; page mode `PSM.AUTO`; one reused worker _Why:_ Pure WASM, same on both platforms, no compile, language file comes from npm so it never downloads at run time. Errors are garbled letters, not invented sentences, which suits quote checking.
- **Expected OCR quality (estimate, not measured)**: Tell the owner: clean flat scans of printed text read well; phone photos with shadow, skew or small print read poorly; handwriting does not work. Show OCR pages with a small 'read by OCR' mark. _Why:_ Tesseract docs say printed text only. No photo accuracy figure found.
- **Image decode and resize**: `sharp@0.35.5` with `autoOrient: true`, resize long side <= 3000 px, grayscale, PNG; HEIC first through `heic-decode@2.1.0` _Why:_ Prebuilt on both platforms; fixes phone photo rotation; default pixel cap guards huge images. sharp prebuilt cannot read HEIC.
- **Word files**: `mammoth@1.13.0` `convertToHtml` + `parse5@8.0.1`; cite by heading path + paragraph number; skip `.doc` _Why:_ Maintained (release 2026-09-26, recent security fixes), pure JS, headings come out as h1..h6.
- **Spreadsheets and CSV**: `read-excel-file@9.3.12` (`read-excel-file/node`) + `papaparse@5.7.0`; passage = header + 20 to 40 rows; cite sheet name + row range _Why:_ Both on the npm registry, MIT, maintained, read-only, small.
- **Text, Markdown, code**: BOM check, `TextDecoder('utf-8', { fatal: true })`, fallback `chardet@2.2.0`, last `windows-1252`; cite by line range; 5 MB cap _Why:_ Built-in covers most files; measured working in Node 24.19.
- **Hybrid search**: Built-in `node:sqlite` FTS5 (`porter unicode61 remove_diacritics 2`), terms each double-quoted joined with OR, top 30; vectors as Float32 BLOBs, brute-force dot product in JS, top 30; RRF `1/(60+rank)`; keep 8. Scope by `file_id IN (chat attachments [+ Library when allowed])` in BOTH legs. _Why:_ No native add-on at all. FTS5 measured present in Node 24.19 and Electron 44.7.0. Brute force measured 42 ms for 50,000 x 1024. k=60 from the RRF paper.
- **Citation quote check**: Same normaliser on quote and page text; exact `includes`; then `approx-string-match@2.0.0` `search()` with 10% errors (20% on OCR pages); then neighbour pages; states `verified` / `close` / `unverified` _Why:_ Finds a quote inside a page with typos allowed in one call. Failing citations stay visible.
- **Safety around untrusted-shaped files**: `file-type@22.1.1` sniff; `yauzl@3.4.0` pre-scan of docx/xlsx; extraction in one forked child process with parent kill timer; caps: 100 MB file, 2,000 PDF pages, 300 OCR pages _Why:_ Node docs say worker limits do not cover ArrayBuffers, so WASM and native memory need a process wall. mammoth and file-type authors both advise a separate thread with timeout.
- **Folder watching**: Not Phase 2. Later: `chokidar@5.0.0` in Electron main on the Mac, inbox rows, upload on click. _Why:_ Not in the Phase 2 scope list; needs the Mac side, while Phase 2 work is the engine.

## Risks
- Nothing here was run end to end. pdfjs text, page render, tesseract.js, mammoth, read-excel-file are confirmed from registry, source and docs only. First build step must be a one-file smoke test of each on this Mac.
- OCR quality on phone photos may disappoint (estimate). Then 'OCR for scans and images' is only half met until a better engine (ONNX PaddleOCR or a llama.cpp OCR model) goes in. Keep OCR behind one function.
- OCR speed unknown. A 200-page scanned PDF could take many minutes on the Mac. Needs background queue, progress, page cap, and chat usable before OCR ends.
- Quote check proves the quote is in OUR extracted text, not in the real page. Bad OCR or bad PDF text order gives false 'unverified'; a vision-model OCR could give false 'verified'.
- PDF text order: pdf.js returns items in content-stream order. Two-column pages and tables can come out interleaved, which hurts both search and quote match. Not tested.
- Linux arm64 native parts (`@napi-rs/canvas-linux-arm64-gnu`, `@img/sharp-linux-arm64` needs glibc >= 2.28) are unproven on DGX OS. If one fails in Phase 3, scanned-PDF OCR or image OCR stops there.
- `node_modules` is per platform: the Mac install cannot be copied to the GX10. Phase 3 needs `npm ci` on the GX10 (network once) or a linux-arm64 install bundle.
- Very fresh releases: `@napi-rs/canvas` 1.0.11 (today), `approx-string-match` 2.0.1 (yesterday, after 5 years quiet), `@hyzyla/pdfium` 3.0.0 (today). Pin the older proven version; read the diff before moving.
- tesseract.js default behaviour downloads language data from jsDelivr and writes a cache file into the working directory. One missed option breaks the 'nothing leaves the machine' rule. Guard with a no-network test.
- Zip pre-scan trusts declared sizes. A crafted docx/xlsx can lie; only the child-process kill timer and OS memory stop it. Low odds with personal files.
- `read-excel-file` behaviour on formulas, merged cells, dates and very large sheets not checked. SheetJS 0.20.3 (vendored tarball) is the fallback.
- Brute-force vectors hold all allowed embeddings in RAM (205 MB per 50,000 at 1024 dims). Fine now; wrong shape if the Library grows 10x.

## Open questions
- Owner: which languages are in your files? English only means one 3 MB OCR file. Each extra language is another `@tesseract.js-data/<lang>` package and slower OCR.
- Owner: do you really have phone photos and HEIC images to read, or mostly PDFs? Decides how much OCR quality work is worth it.
- Owner: old `.doc` / `.xls` files: fine to refuse with a 'save as .docx' message?
- Owner: for Word files a citation will say section and paragraph, not page. Acceptable?
- Owner: rough Library size (hundreds of files or tens of thousands)? Decides brute-force vectors versus `sqlite-vec`.
- Test: seconds per page and text quality for tesseract.js 7.0.0 on this Mac, 5 clean scans + 5 phone photos, at render scale 2, 3 and 4.17.
- Test: peak memory of pdfjs on a 500-page text PDF and a 200-page scanned PDF in the child process.
- Test: does pdfjs keep reading order on a two-column PDF and a table-heavy PDF well enough for quote matching?
- Test: do `@napi-rs/canvas@1.0.10`, `sharp@0.35.5`, `tesseract.js@7.0.0` install and run on the GX10 (DGX OS glibc version unknown here)?
- Test: does pdfjs + tesseract.js behave inside `worker_threads` under Electron main, or only in a forked child?
- Test: what did `approx-string-match` 2.0.1 change versus 2.0.0?
- Test: best passage size (1,200 chars is a starting guess) and fuzzy thresholds (10% / 20%) on the owner's real files.

## Independent re-check (overrides the above)

- **R1a** [confirmed] Claim holds. Not run by me (no install). Exact detail to add, from source 6.4.299: `cMapUrl`, `standardFontDataUrl`, `wasmUrl` must be strings ending in `/` or `getDocument` throws `Invalid factory url: ... must include trailing slash.` In Node they go straight to `fs.readFile(baseUrl + filename)`, so give plain absolute paths, not `file://` strings (inference from that code). `url` may be a plain path (source runs `pathToFileURL`). Node sets worker off and loads `./pdf.worker.mjs` by relative path: do not bundle pdfjs-dist. Measured sizes: `/cmaps` 1,167,747 B, `/standard_fonts` 798,046 B, `/wasm` 1,543,489 B.
- **R1b** [refuted] Original right. Re-measured here: Electron 44.7.0 with `ELECTRON_RUN_AS_NODE=1` -> `process.type` undefined, Node 24.21.0, pdf.js check true, SQLite 3.53.4 with FTS5, `worker_threads` Worker runs. Same check found in pdf.js master `src/shared/util.js`. One add: Electron main (`process.type` = `browser`) also passes the check; only `utility`, `renderer`, `worker`, `service-worker` fail.
- **R1c** [partly] Pick stands. Two small fixes. `pdf-parse` 2.4.5 was published 2025-10-20; 2025-10-29 is the last registry activity (1.1.4 on the `minor` tag). `unpdf` 1.8.1 README says bundle is PDF.js v5.6.205, but its package.json devDependency is `pdfjs-dist` `~6.1.200`: bundle version not settled by me; either is older than 6.4.299. Rest matches: `mupdf` 1.28.1 `AGPL-3.0-or-later`; `officeparser` 8.1.1, 31,076,317 B, one maintainer, pins `pdfjs-dist` 6.2.108, releases 2026-09-16, 2026-09-29, 2026-10-05.
- **R1d** [confirmed] Claim holds. Not run by me. Fix: min glibc IS documented. `@napi-rs/canvas` README: "at least glibc version >= 2.18"; arm64 Linux needs cortex-a57 or newer. 1.0.11 published 2026-10-10T12:46:50Z, 1.0.10 2026-10-01. pdfjs-dist lists it as optionalDependency `^1.0.10`, so npm takes 1.0.11 unless `@napi-rs/canvas` `1.0.10` is an exact direct dependency. Sizes: darwin-arm64 28,058,341 B, linux-arm64-gnu 29,504,205 B. 300 dpi Letter sum (2550x3300x4 = 33.66 MB) is right.
- **R1e** [partly] 
- **R1f** [unverified] Still no measured figure. One fix to the build note: loading by `url` does not cap memory alone. Typings: `disableAutoFetch` default `false` means pdf.js "will automatically keep fetching more data even if it isn't needed", and "It is also necessary to disable streaming". So set `disableAutoFetch: true` and `disableStream: true` if the aim is not to hold the whole file. Range reads start only when size > 2 x 65536 = 131,072 B (source). Effect on RAM not measured.
- **R2a** [confirmed] 
- **R2b** [partly, disagrees] A source does settle it. ISO/IEC 29500 text (Microsoft Learn): `w:lastRenderedPageBreak` "specifies that this position delimited the end of a page when this document was last saved by an application which paginates its content". So Word-saved .docx carry page-break hints. But they are optional, only as fresh as the last save, and mammoth drops them: `lib/docx/body-reader.js` lists `"w:lastRenderedPageBreak": true` under `ignoreElements`. Build note stands: cite heading path + paragraph number. Page from these marks would need own XML read: not for Phase 2.
- **R2c** [partly] Skip .doc stands. Date fix: `word-extractor` 1.0.4 was published 2021-07-26; 2022-06-29 is only the registry `modified` stamp. `docx4js` 3.3.0 is 2024-09-09. file-type README lists `.doc`, `.xls`, `.ppt` as not accepted and lists `cfb`.
- **R3a** [refuted] 
- **R3b** [refuted] Original right. Small add: SheetJS git has commits up to 2026-02-09, so repo not dead, but newest tag is still v0.20.3 (2024-07-18). Tarball answers HTTP 200, 2,409,319 B. Docs say npm registry "is out of date. The latest version on that registry is 0.18.5".
- **R3c** [partly] Pick stands. Gaps now filled from README and source of 9.3.12. Formulas: returns the value the spreadsheet app saved; formula with no saved value or an error becomes empty cell, silently. Strings trimmed by default; `trim: false` keeps them. Source `modules/xlsx/parseSheet.js` pushes `[]` for row gaps, so `data[i]` = sheet row i+1. Values are raw: `Date` objects and plain numbers, not the shown format (0.05, not 5%). Old .xls throws `XLS_FILE_NOT_SUPPORTED`. Deps: `saxen`, `fflate`, `worker-f`, `unzipper-esm`. One maintainer; 9.3.11 and 9.3.12 came 10 minutes apart on 2026-10-07. Merged cells and big-file memory: still not checked.
- **R4** [partly] Order stands, one real bug in it. chardet names do not all work in `TextDecoder`. Measured Node 24.19.0: `UTF-16 LE`, `UTF-16 BE`, `UTF-32 LE`, `UTF-32 BE`, `ISO-2022-KR`, `ISO-2022-CN` throw `ERR_ENCODING_NOT_SUPPORTED`. Map `UTF-16 LE` -> `utf-16le`, `UTF-16 BE` -> `utf-16be`; wrap `new TextDecoder(name)` in try/catch and fall to `windows-1252`. Other 25 chardet names decode. `jschardet` 4.0.0 is 7,451,504 B, licence `0BSD`.
- **R5a** [confirmed] Claim holds, read in source; not run by me. Adds: `gzip` already defaults `true`. `tesseract.js` 7.0.0 has install script `postinstall: opencollective-postinstall || true` and 9 deps (one is `node-fetch` ^2). Node picks `tesseract.js-core/tesseract-core-relaxedsimd-lstm` when the runtime has relaxed SIMD. `tesseract.js-core` 7.0.0 is 45,262,431 B; its `latest` tag is 6.1.2. Repo last push 2026-05-17, no release since 2025-12-15. Default page mode `PSM.SINGLE_BLOCK` confirmed in api.md and faq.md.
- **R5b** [unverified] Still none for tesseract.js. Only near thing found: Phoronix run of native Tesseract 5.5.1 on Apple M4 Pro, 15.10 s for 7 images (about 2.2 s each, my sum). Native C++, not WASM, other images: do not use as the app figure.
- **R5c** [partly] Original right. Exact binary sizes inside the one package: `bin/napi-v6/darwin/arm64` 89,446,696 B, `linux/arm64` 25,530,144 B; whole package 301,068,136 B. `postinstall: node ./script/install`; `--onnxruntime-node-install=skip` exists.
- **R5d** [partly] 
- **R6** [partly] Original right. Adds: install doc now lists prebuilt formats as "JPEG, PNG, Ultra HDR, WebP, AVIF, TIFF, GIF and SVG (input)". `@img/sharp-libvips-linux-arm64` 1.3.4 is 18,336,518 B. `heic-decode` 2.1.0 asks `libheif-js` `^1.19.8`, resolves to 1.23.5 today; neither has an install script.
- **R7** [partly] Sizes are design, as said. `/tokenize` confirmed (`content`, `add_special` default `false`, also `parse_special`, `with_pieces`). Add: earlier research picked `Qwen3-Embedding-0.6B`; its card says context 32k, so the `-c 2048` server cap is the real limit, and 1,600 chars is far under it.
- **R8a** [refuted] Re-measured, same results (Node 24.19.0, SQLite 3.53.3). Two adds. Empty term list gives `fts5: syntax error near ""`: skip the keyword leg when no terms are left. node:sqlite here rejects double-quoted SQL string literals ("should this be a string literal in single-quotes?"): write SQL strings with single quotes. Docs confirm k1 1.2, b 0.75 hard-coded, lower rank is better, `"` escaped by doubling.
- **R8c** [refuted] Re-measured here: 50,000 x 1024 float32, dot product + sort, 40.8 ms per query, RSS 274 MB (original said 42 ms, 205 MB; 205 MB is the array alone). Dimension now checked: Qwen3-Embedding-0.6B card says 1024, user-set 32 to 1024. `sqlite-vec` 0.1.9 prebuilt for both platforms confirmed; alpha 0.1.10-alpha.4 is from 2026-05-18.
- **R9** [partly] Original right. I read the 2.0.1 diff by comparing unpkg files line by line: only comments, a named `Match` type in `index.d.ts`, devDependency `mocha` ^9 -> ^12, CHANGELOG.md dropped. No logic line differs in `build/src/index.js` (line-set compare, not a full audit). So 2.0.0 or 2.0.1 both fine. `fastest-levenshtein` 1.0.16 is 2022-08-02. NFKC re-measured: `ﬁ`/`ﬃ` -> `fi`/`ffi`, U+00AD kept, curly quotes and dashes kept; also `…` -> `...`, `™` -> `TM`, NBSP -> space, so string length changes.
- **R10a** [partly] Original right. One caveat from the README: when `[Content_Types].xml` is out of reach the type is guessed from folder names, so "a non-OOXML archive containing one of those directories is reported as OOXML", and macro or template variants come back as plain `docx` / `xlsx`.
- **R10b** [refuted] 
- **R11** [partly] Original right. Detail: chokidar GitHub master `package.json` already reads `"version": "6.0.0"`, node `>= 22.22`, and README says "The current major is v6 (Oct 2026)"; npm `latest` is still 5.0.0 (2025-11-25), no 6.x on the registry. v6 changelog: "new fs.watch(recursive) backend on macos + windows".

### Objections to recommendations
- Linux arm64 later: native parts (`sharp` + `@img/*`, `@napi-rs/canvas-*`) come as per-platform optional packages. `node_modules` from the Mac will not run on the GX10; GX10 needs its own `npm ci` (registry reach once, or vendored tarballs). sharp install doc warns a lockfile shared by platforms can miss binaries (npm/cli#4828; issue now closed, updated 2026-10-07; which npm has the fix not checked). Before Phase 3: check the lockfile holds `@img/sharp-linux-arm64`, `@img/sharp-libvips-linux-arm64`, `@napi-rs/canvas-linux-arm64-gnu`.
- Inside Electron 44, packaged app: `ui/scripts/package-mac.mjs` uses a keep-list `ignore` and `prune: false`. Engine files and its `node_modules` must be added to that list or the packaged app has no engine. sharp doc says `sharp` and `@img` must sit outside asar; same care for `@napi-rs/canvas` `.node` file and the tesseract worker file. Simplest: engine folder shipped unpacked. Not tested by anyone yet.
- Do not bundle the engine. pdf.js Node mode loads `./pdf.worker.mjs` by relative path; tesseract.js finds its worker by `__dirname` and its FAQ lists `Cannot find module` under build systems. Run engine as plain files with real `node_modules`.
- `@napi-rs/canvas@1.0.10` pin only holds if it is an exact direct dependency. pdfjs-dist asks `^1.0.10`; alone, npm installs 1.0.11 (17 hours old at check time).
- Fuse `runAsNode` must stay on for `child_process.fork`. Electron docs push the other way ("we recommend that you use Utility Processes"), and pdf.js breaks there. Any later hardening step that flips fuses kills the engine with no clear error. Write this rule in CLAUDE.md.
- Three runtimes: Mac Node 24.19.0 (SQLite 3.53.3), Electron 44.7.0 Node 24.21.0 (SQLite 3.53.4), GX10 Node not yet known. `node:sqlite` is "Stability: 1.2 - Release candidate" in Node 24 docs, not stable. Still the right pick over a native add-on, but run engine tests under plain `node` AND under Electron-as-Node, and install the same Node 24.x on the GX10.
- Citation check, 10% fuzzy (20% on OCR): a changed number passes. `$2,400` vs `$2,900` is one edit in a 60-char quote and would show `close`. Add rule (my design): every digit in the quote must match exactly inside the matched span, else `unverified`.
- Vector leg: "load allowed files' vectors into one Float32Array" per query means reading up to 205 MB of BLOBs each search at 50,000 passages. Keep all vectors in engine RAM once, filter by a file_id mask. RSS measured 274 MB at 50,000 x 1024.
- `yauzl` pre-scan is weaker than it reads: it checks sizes declared in the zip directory, but mammoth (jszip) and read-excel-file (`unzipper-esm` / `fflate`) do their own unzip and do not use yauzl's size check. For "personal files only" it could be dropped: one part less. Keep the forked child + kill timer + file-size cap, and add a memory watch on the child (fork sets no memory cap; not in the original).
- OCR pick, sideways pages: `PSM.AUTO` does not fix rotation. `worker.detect` needs `legacyCore: true, legacyLang: true` (api.md); the legacy file `4.0.0/eng.traineddata.gz` (10,923,060 B) is in the same npm package. sharp `autoOrient` only fixes photos that carry EXIF rotation. Test sideways scans in week one.
- Scan rule "under 50 chars -> OCR" (design, not sourced) misses scans that carry a text header, a stamp, or a poor hidden text layer from the scanner. Tune on real files as said; also look at text length versus page area covered by images.
- `tesseract.js` runs an install script (`opencollective-postinstall || true`). Harmless, but it is a script at install; `npm ci --ignore-scripts` avoids it. Check nothing else in the chosen set needs scripts before using that flag.
- Engine on Linux inside Electron would hit sharp's open glib clash (electron/electron#46323, still open, updated 2026-10-08). Phase 3 plan is plain Node, so fine; do not change that plan lightly.

### Missed by the first pass
- docx pages: Word writes `w:lastRenderedPageBreak` marks (ISO/IEC 29500). mammoth ignores them (source). So approximate Word page numbers are possible later with own XML read. Not needed for Phase 2.
- Embedding model `Qwen3-Embedding-0.6B` is instruction-aware: card shows queries as `Instruct: {task}\nQuery:{query}`, "No need to add instruction for retrieval documents", gain "1% to 5%". Dimension 1024, user-set 32 to 1024. Query builder must add the prefix; passages must not.
- pdf.js already normalises text: `getTextContent` has `disableNormalization` default `false`, and worker source applies `normalize("NFKC")`. Stored 'exact page text' is pdf.js-normalised text. Items carry `hasEOL`; page text must be joined with it or the line-end hyphen rule in the normaliser never fires.
- PDF page number meaning: pdf.js gives physical index; `getPageLabels()` exists for printed labels (i, ii, 1...). Decide once: cite 1-based physical page (what a viewer jumps to), show label too if present.
- Locked PDFs: API has `onPassword`. Plan a plain message ("This PDF needs a password"), not a crash.
- Normaliser changes string length (`…` -> `...`, ligatures, joined hyphens). To highlight the quote on the page, keep an offset map from normalised text back to stored text. Not in the original.
- `node:sqlite` facts measured: FTS5 on in both runtimes; double-quoted SQL strings rejected; empty MATCH string is a syntax error; `loadExtension` exists but needs `allowExtension: true` at open.
- Engine needs its own package folder with own `package.json` and lockfile. CLAUDE.md forbids changing `ui/package.json` and its lockfile, and the GX10 must not need the UI's packages.
- Install size of the document stack on one platform, direct packages only (my sum of registry `unpackedSize`, estimate): pdfjs-dist 34.9 MB + canvas 28.1 + tesseract.js-core 45.3 + tesseract.js 1.4 + eng data 13.9 + sharp and libvips 19.5 + libheif-js 9.0 + mammoth 1.7 + read-excel-file 2.7 + small ones about 1 = about 158 MB.
- Spreadsheet values come raw (`Date` objects, 0.05 not 5%). Turn them to text one fixed way (ISO date, plain number) and run the quote check against that generated row text, or quotes will never match.
- `@napi-rs/canvas` Linux floor found: glibc >= 2.18, cortex-a57 or newer. sharp floor: glibc >= 2.28. GX10 glibc itself not checked by me.
- No published tesseract.js speed for Apple silicon exists in what I found; R5b stays open until measured on this Mac. Node 24 moves to maintenance on 2026-10-20, end of life 2028-04-30 (Node release schedule).
