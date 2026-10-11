# Research: frontend

Read-only research on 2026-10-10. Nothing was run on the GX10. The re-check section overrides the findings where they differ.

## Summary
Read-only research; nothing was installed, written or changed. Versions come from `npm view` and PyPI on 2026-10-10; behaviour claims come from docs, published package files or the skill files on disk. Two things are my own calculations rather than measurements: the Table View geometry and the colour-contrast ratios. I could not view the plan's wireframes (no PDF renderer on this Mac; I extracted the text only), so sidebar width, avatar size and seat spacing are assumptions.

Main findings:

1. **The pinned stack is still current.** All 22 pins match npm `latest` except TypeScript (latest 7.0.2; the 6.0.3 pin is deliberate). Additions: motion 14.1.0, vite-plugin-singlefile 2.3.3. @floating-ui/react is not needed.
2. **Motion is not needed for Phase 1.** The 250 ms fade in, 1.5 s fade out and in-place crossfade are plain CSS transitions on always-mounted bubbles. Motion's `reducedMotion="user"` keeps opacity fades, so on its own it does not meet the plan's "simply appear and disappear" rule.
3. **Table View layout should be a pure function, not a measuring pass.** Every rule depends only on seat count and stage size. jsdom does no layout, so only a pure function can be unit-tested.
4. **Seven seats at 1024 px fit, but the text does not.** In my model a non-overlapping layout always exists, with bubbles about 140-170 px wide (roughly 40-50 characters over two lines). A two-sentence summary will be cut off at 6-7 seats. This needs an owner decision.
5. **Light-theme seat heads fail contrast.** No single label colour reaches 4.5:1 on all seven seat colours, and white on the clay accent is 3.84:1.
6. **One self-contained HTML is feasible with Vite alone.** vite-plugin-singlefile 2.3.3 handles Vite 8 explicitly in its published source (not run here). The skill's Parcel plus html-inline route is a second bundler and does not document font inlining.
7. **frontend-design lists the plan's look as an AI default, then says the brief wins.** Its process, quality floor and writing guidance apply; its palette and type advice must be overridden by the plan.
8. **Python Playwright cannot reuse the Node browsers today.** PyPI has 1.63.0 (chromium 1243); @playwright/test 1.64.0 uses chromium 1248. One toolchain (Node) should own the browsers.
9. **The marketplace is registered but no plugin is installed.** `claude plugin install example-skills@anthropic-agent-skills` exists and works from the shell; in VS Code the command is `/plugins`. Reading SKILL.md by path is sound and is what I did.

## Claims

### F1a [partly]
Motion (formerly Framer Motion) is a current, MIT-licensed package that works with React 19.3 and covers enter and exit fades, an in-place crossfade and reduced motion.

Evidence: npm: `motion` 14.1.0 (published 2026-10-09; 14.0.0 on 2026-10-02), MIT, peers `react ^18.0.0 || ^19.0.0`, import from `motion/react`; not run against React 19.3 here. AnimatePresence gives `exit` on keyed direct children with `mode` "sync" | "wait" | "popLayout", and a `transition` can sit inside any animation target. `<MotionConfig reducedMotion="user">` disables transform and layout animations but preserves opacity, and the docs give sizes of 34kb for `motion`, or 4.6kb for `m` with LazyMotion plus 15kb (`domAnimation`) or 25kb (`domMax`).

For the build: When Motion is added, pin motion@14.1.0 exactly. For bubbles the pattern would be `<AnimatePresence initial={false}>` with a keyed `motion.p`, `animate={{opacity:1, transition:{duration:0.25, ease:"easeOut"}}}` and `exit={{opacity:0, transition:{duration:1.5}}}`. Use `useReducedMotion()` to set both durations to 0, because MotionConfig alone leaves opacity fades running.

Sources: https://registry.npmjs.org/motion, https://motion.dev/docs/react-animate-presence, https://motion.dev/docs/react-transitions, https://motion.dev/docs/react-accessibility, https://motion.dev/docs/react-reduce-bundle-size, https://motion.dev/docs/react-installation, https://raw.githubusercontent.com/motiondivision/motion/main/CHANGELOG.md

### F1b [refuted]
The bubble fades need the Motion library, including in the Phase 1 static mocks.

Evidence: A 250 ms fade in and 1.5 s fade out on an element that stays mounted needs only `transition` on opacity and visibility, which every browser supports. `@starting-style` (Chrome 117, Safari 17.5, Firefox 129) and `transition-behavior: allow-discrete` (Chrome 117, Safari 17.4, Firefox 129) matter only when the element is unmounted or `display:none`, and MDN's data lists transitioning `display` as unsupported in Firefox. Playwright's `toHaveScreenshot` defaults to `animations: "disabled"`, which fast-forwards CSS transitions, CSS animations and Web Animations.

For the build: Phase 1: keep one bubble element per seat mounted and switch a `data-state` attribute. Hidden state: `opacity:0; visibility:hidden; transition: opacity 1.5s ease-out, visibility 0s linear 1.5s`. Shown state: `opacity:1; visibility:visible; transition: opacity 250ms ease-out`. Crossfade by stacking two text layers in one grid cell. Under `prefers-reduced-motion: reduce` set `transition: none`. Add Motion later, where layout animation earns it (the stage folding into a card, seats spooling up).

Sources: https://raw.githubusercontent.com/mdn/browser-compat-data/main/css/at-rules/starting-style.json, https://raw.githubusercontent.com/mdn/browser-compat-data/main/css/properties/transition-behavior.json, https://playwright.dev/docs/api/class-pageassertions

### F2a [partly] (load-bearing)
Keeping bubbles from overlapping needs a layout pass that measures each bubble in the DOM (ResizeObserver and getBoundingClientRect), or a positioning library.

Evidence: The plan's rules (width no more than the seat gap, end seats pushed outward, rise instead of touch, two-line clamp) depend only on seat count and stage size, so they can be computed without measuring text. jsdom's README says it does not do layout and returns zeros for layout properties, so measuring code cannot be unit-tested in Vitest with jsdom. Floating UI's `detectOverflow` checks a floating element only against a clipping boundary, and CSS anchor positioning (Chrome 125, Firefox 147, Safari 26) applies to elements that generate a principal box; neither handles one bubble colliding with another.

For the build: Write a pure `layoutTable({seats, width, height})` that returns seat points and one reserved bubble slot per seat (x, y, maxWidth, alignment, tier). Use a single ResizeObserver on the stage for width and height. Bubbles are absolutely positioned HTML with `width: max-content`, `max-width` from the slot, a two-line `-webkit-line-clamp`, anchored at the bottom so they grow upward. Give the SVG a viewBox equal to the stage's pixel size so SVG and HTML share coordinates.

Sources: /Users/lucasta/Downloads/GX10 Cluster UI Plan.pdf, https://raw.githubusercontent.com/jsdom/jsdom/main/README.md, https://floating-ui.com/docs/detectOverflow, https://developer.mozilla.org/en-US/docs/Web/CSS/anchor-name, https://raw.githubusercontent.com/mdn/browser-compat-data/main/css/properties/anchor-name.json, https://raw.githubusercontent.com/mdn/browser-compat-data/main/css/properties/position-area.json

### F2b [partly] (load-bearing)
With 7 seats in a 1024 px wide window, all of the plan's bubble rules can hold at once, including a one- or two-sentence summary inside a two-line clamp.

Evidence: This is an estimate from my own geometry model, not a measurement. Assumptions: 240 px sidebar and 24 px padding (736 px stage), 60 by 74 px avatars, 13 px text at about 6 px per character. A non-overlapping layout exists for 3 to 7 seats, but at 7 seats bubbles are about 141 px wide with no rising and 169 px with one rise, roughly 40-50 characters over two lines; with the sidebar collapsed (976 px stage) they are about 190-255 px, 57-78 characters. At 5 seats the figure is about 267-297 px (82-92 characters).

For the build: Treat maximum bubble width as an output of the layout function, and tie summary length to seat count on the server (for example about 8 words at 6-7 seats and about 14 words at 3-5), with the full text in the agent's side sheet. Include a 7-seat, 1024 px, longest-text scene in the Phase 1 mocks so the owner sees the worst case before the summariser prompt is written.

Sources: /Users/lucasta/Downloads/GX10 Cluster UI Plan.pdf

### F3 [partly] (load-bearing)
The Table View scene as specified (11 px names inside seat-coloured heads, full name on hover, a glow for the speaker) is accessible without changes.

Evidence: Contrast computed from the plan's tokens with the WCAG formula: in the light theme the text colour #2B2A27 gives 3.25-5.54:1 across the seven seat colours and white gives 2.59-4.41:1, so no single label colour meets 4.5:1 on all seats; sage (2.83:1) and amber (2.30:1) are under 3:1 against #F5F1EA; white on the clay accent is 3.84:1. The dark theme passes with dark labels (5.55-8.41:1). Radix Tooltip "opens when the trigger is focused or hovered" and closes on Escape, and MDN says `role="timer"` has an implicit `aria-live` of `off`.

For the build: Make each seat an HTML `<button>` in seat order (left to right) that opens the side sheet, with an accessible name such as "Full model name, seat 3, speaking, agrees". Show the full name with Radix Tooltip on hover and focus. Mark the speaker with the glow plus a non-colour cue (thicker ring and the word in the label) and votes with check and cross icons. Announce through one visually hidden `role="status"` region, limited to speaker changes, vote results and the final outcome; never put bubble text or the ticking timer in a live region. Add a token contrast unit test alongside axe.

Sources: /Users/lucasta/Downloads/GX10 Cluster UI Plan.pdf, https://www.w3.org/TR/WCAG22/, https://www.radix-ui.com/primitives/docs/components/tooltip, https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles/timer_role

### F4a [confirmed]
Chat View can show one column per model on a wide screen and a single thread on a narrow one from the same markup, using container queries or grid.

Evidence: Container queries are supported from Chrome 105, Firefox 110 and Safari 16, and Tailwind 4 ships `@container` with variants such as `@min-[475px]:`. Keeping the DOM in time order and giving each message its seat's column and its own row keeps time readable down the page; that part is design reasoning, not a sourced fact. At 15 px text, seven columns need roughly 240 px each, about 1,750 px of container width (estimate).

For the build: Render one list in sequence order. Narrow: one column. Wide: `grid-template-columns: repeat(var(--seats), minmax(0, 1fr))`, each message with `grid-column` set to its seat and `grid-row` set to its sequence index, and vote dividers spanning `1 / -1`. Switch to columns only when the container is at least seats times about 240 px, so 6-7 seats stay a single thread on a laptop. Use one scroll container and sticky column headers showing model names.

Sources: https://raw.githubusercontent.com/mdn/browser-compat-data/main/css/at-rules/container.json, https://tailwindcss.com/docs/responsive-design, /Users/lucasta/Downloads/GX10 Cluster UI Plan.pdf

### F4b [refuted]
Following the newest message until the reader scrolls up can be left to the browser's CSS scroll anchoring.

Evidence: MDN's compatibility data lists `overflow-anchor` from Chrome 56 and Firefox 66 but Safari only from 27, which was released on 2026-09-14. Which Safari version the owner's Macs run is unknown.

For the build: Do it in script: a `following` flag that is true while a bottom sentinel is visible (IntersectionObserver) or the distance from the bottom is under about 48 px. While following, set `scrollTop = scrollHeight` after each batched update, with no smooth scrolling during streaming. A user scroll upward clears the flag and shows a "Jump to newest" button.

Sources: https://raw.githubusercontent.com/mdn/browser-compat-data/main/css/properties/overflow-anchor.json, https://raw.githubusercontent.com/mdn/browser-compat-data/main/browsers/safari.json

### F4c [unverified]
Long debates need list virtualisation in Chat View.

Evidence: No measurement exists. Debates are capped at 2, 5 or 10 minutes, so message count is bounded by the GX10's throughput; my estimate is tens to low hundreds of messages, which plain DOM handles. Earlier research recommended memoised finished messages and `content-visibility: auto`, adding virtua 0.53.3 or TanStack Virtual only if jank is measured.

For the build: No virtualiser in Phases 1-5. Memoise completed messages and batch streamed text to one state write per animation frame. Re-check with a real 10-minute, 7-seat debate recorded on the GX10 before Phase 7 replay.

Sources: earlier research: research:frontend D5d, /Users/lucasta/Downloads/GX10 Cluster UI Plan.pdf

### F5 [partly] (load-bearing)
The Phase 1 mocks can be driven by a recorded debate (a fixture event log plus a small player) and still give deterministic screenshot tests.

Evidence: Playwright's `page.clock` overrides Date, setTimeout, setInterval, requestAnimationFrame and performance, with `install`, `pauseAt`, `fastForward` and `runFor`; `toHaveScreenshot` fast-forwards finite CSS transitions and animations by default. That makes settled states repeatable but not mid-fade frames, and Vitest's fake timers cover the player's unit tests. Hard-to-reach states (load error, 7 seats with long text, no consensus) still need their own fixtures.

For the build: Define a versioned `DebateEvent` union with `seq` and `t` (milliseconds on the debate clock, pauses excluded), a pure `reduce(state, event)` and a `view(state, nowMs)` selector that derives bubble visibility from `nowMs - summary.t` instead of component timers. The player offers play, pause and `seek(seq)` with an injected clock. Screenshot tests open named scenes, each a `{fixture, seq, nowMs}` bookmark, with no playback, reduced motion on and fonts awaited. Import fixtures as modules, because a file:// page cannot fetch them.

Sources: https://playwright.dev/docs/clock, https://playwright.dev/docs/api/class-pageassertions, https://vitest.dev/guide/mocking/timers, /Users/lucasta/Downloads/GX10 Cluster UI Plan.pdf

### F6 [confirmed] (load-bearing)
The pinned stack is still current and mutually compatible, and the additions fit it.

Evidence: `npm view` on 2026-10-10 returns the pinned version as `latest` for 21 of 22 packages; TypeScript's latest is 7.0.2 and the deliberate 6.0.3 pin exists. Peer ranges line up: @vitejs/plugin-react 6.1.2 needs vite ^8, @tailwindcss/vite 4.3.3 accepts vite ^5.2 to ^8, vitest 5.0.3 accepts vite ^6.4 to ^8, react-router 8.4.0 needs react >=19.2.7 and node >=22.22, jsdom 30.1.2 needs node ^24.15. Additions: motion 14.1.0 (react ^18 || ^19), @floating-ui/react 0.27.20 (react >=17), vite-plugin-singlefile 2.3.3 (vite ^5.4.21 || ^6 || ^7 || ^8, node >18).

For the build: Keep every pin, exact, with a committed lockfile. Add vite-plugin-singlefile@2.3.3 as a dev dependency in Phase 1. Add motion@14.1.0 only when first used. Do not add @floating-ui/react: radix-ui 1.7.0 already brings @floating-ui/react-dom through @radix-ui/react-popper 1.3.8 for Tooltip and Popover.

Sources: https://registry.npmjs.org/motion, https://registry.npmjs.org/@floating-ui/react, https://registry.npmjs.org/vite-plugin-singlefile, https://registry.npmjs.org/@vitejs/plugin-react, https://registry.npmjs.org/vitest, https://registry.npmjs.org/react-router, https://registry.npmjs.org/jsdom, earlier research: research:frontend D1a, D9a

### F7a [partly] (load-bearing)
vite-plugin-singlefile works with Vite 8 and produces one HTML file, fonts inlined, that opens from a double-click.

Evidence: Confirmed from the published 2.3.3 source, not run: it sets `build.assetsInlineLimit = () => true`, `cssCodeSplit = false`, `base = "./"` and, when Vite's major is 8 or higher, `output.codeSplitting = false`. Its README says public-folder files are not inlined and that History API routing does not work. The Fontsource CSS for the three fonts references 16 woff2 subset files totalling 385 KB, about 514 KB once base64-encoded (latin only: 136 KB, about 182 KB).

For the build: Add a separate `vite.mock.config.ts` (or `--mode mock`) that adds `viteSingleFile()`, so the normal GX10 build keeps code splitting. Use HashRouter in both builds, bundle fixtures by import, and keep nothing in `public/`. Expect roughly 1-1.6 MB for the file (estimate). Verify with a Playwright test that opens the file through `file://` and asserts zero network requests.

Sources: https://cdn.jsdelivr.net/npm/vite-plugin-singlefile@2.3.3/dist/esm/index.js, https://raw.githubusercontent.com/richardtallent/vite-plugin-singlefile/main/README.md, https://vite.dev/config/build-options, https://data.jsdelivr.com/v1/package/npm/@fontsource-variable/fraunces@5.3.0/flat, https://data.jsdelivr.com/v1/package/npm/@fontsource-variable/source-sans-3@5.3.0/flat, https://data.jsdelivr.com/v1/package/npm/@fontsource-variable/jetbrains-mono@5.3.0/flat

### F7b [refuted]
The Parcel plus html-inline route in web-artifacts-builder is an equivalent way to produce the single file.

Evidence: `bundle-artifact.sh` installs parcel, @parcel/config-default, parcel-resolver-tspaths and html-inline with pnpm and builds `index.html` with Parcel, a second bundler that would not run the app's `@tailwindcss/vite` plugin. html-inline 1.2.0 (registry record last modified 2022-11-08) documents inlining only stylesheets, script tags and images; fonts referenced from CSS are not mentioned. Not run.

For the build: Do not use the skill's bundling script. Use Vite for both the served build and the single-file mock so the CSS and font pipeline is identical.

Sources: /Users/lucasta/.claude/plugins/marketplaces/anthropic-agent-skills/skills/web-artifacts-builder/scripts/bundle-artifact.sh, https://registry.npmjs.org/html-inline, https://registry.npmjs.org/parcel

### F8a [partly]
frontend-design's instructions apply when building a pre-specified app interface, not only a landing page.

Evidence: Applicable parts of SKILL.md: ground the design in the subject, write a compact token plan, review that plan against the brief before building, watch CSS specificity, "Spend your boldness in one place", the quality floor ("responsive down to mobile, visible keyboard focus, reduced motion respected, visually accessible"), critique from screenshots, and the whole writing section. The hero paragraph and the invitation to take aesthetic risk assume a brief that leaves the look open.

For the build: Use the skill in Phase 1 for the axes the plan leaves free: how the table and avatars are drawn, the agreement meter, the status pill, empty and error states, and all interface copy. Run its plan, review, build, screenshot-critique loop, with Table View as the one bold element and everything else quiet.

Sources: /Users/lucasta/.claude/plugins/marketplaces/anthropic-agent-skills/skills/frontend-design/SKILL.md

### F8b [partly] (load-bearing)
frontend-design's guidance is compatible with the product plan's fixed look.

Evidence: The skill lists as AI-default tells "a warm cream background (near #F4F1EA) with a high-contrast serif display and a terracotta or warm-clay accent", "meta strings joined with middle dots", "tinted near-black (#0B0B0B, #111) standing in for black", "a monospace face for small data labels" and hairline rules, and it prefers one or two type families where the plan has three. It then resolves the conflict itself: "Where the brief pins down a visual direction, follow it exactly — the brief's own words always win, including when it asks for one of these looks. Where it leaves an axis free, don't spend that freedom on one of these defaults."

For the build: Tell every design sub-agent, in its prompt, that the plan pins #F5F1EA, Fraunces titles, clay #C4694D, JetBrains Mono for numbers, middle-dot meta strings, the two radii and black-and-white Chat View, and that these are not to be revised. On free axes, forbid further defaults: all-caps eyebrow labels, an arrow appended to buttons, spaced em-dash labels, gradient washes, identical card grids and fade-and-slide-up entrances.

Sources: /Users/lucasta/.claude/plugins/marketplaces/anthropic-agent-skills/skills/frontend-design/SKILL.md, /Users/lucasta/Downloads/GX10 Cluster UI Plan.pdf

### F8c [refuted] (load-bearing)
web-artifacts-builder's starter is a suitable scaffold for an app that will grow through seven phases.

Evidence: `init-artifact.sh` runs `npm install -g pnpm` if pnpm is missing, scaffolds with `pnpm create vite --template react-ts`, then installs tailwindcss@3.4.1 with postcss, autoprefixer and a `tailwind.config.js`, 26 separate `@radix-ui/react-*` packages, 40+ shadcn/ui components with shadcn's HSL token names, and next-themes, sonner, cmdk, vaul, embla-carousel-react, react-day-picker, react-resizable-panels, date-fns, react-hook-form, zod, class-variance-authority and tailwind-merge. It also writes `baseUrl` path aliases into tsconfig. Each of these contradicts a pinned choice: Tailwind 4.3.3 CSS-first tokens, the unified radix-ui package, npm, and a TypeScript 6/7-clean tsconfig.

For the build: Scaffold by hand with npm and the pinned versions. Do not run `init-artifact.sh` or `bundle-artifact.sh` in the app repository. Take from this skill only the idea of delivering one self-contained HTML file, and its warning against centred layouts, purple gradients, uniform rounded corners and Inter.

Sources: /Users/lucasta/.claude/plugins/marketplaces/anthropic-agent-skills/skills/web-artifacts-builder/scripts/init-artifact.sh, /Users/lucasta/.claude/plugins/marketplaces/anthropic-agent-skills/skills/web-artifacts-builder/SKILL.md, earlier research: research:frontend D1b, D1c

### F8d [refuted] (load-bearing)
Python Playwright run through `uv run --with playwright` can reuse the browser builds that @playwright/test 1.64.0 installs.

Evidence: PyPI's latest `playwright` is 1.63.0 (2026-09-15; its DRIVER_VERSION file reads 1.63.0), whose browsers.json pins chromium 1243, firefox 1543 and webkit 2359, while playwright-core 1.64.0 pins chromium 1248, firefox 1555 and webkit 2370. Both bindings use `~/Library/Caches/ms-playwright` with revision-named folders, and the docs say "Each version of Playwright needs specific versions of browser binaries to operate." That folder does not exist yet on this Mac.

For the build: Let Node own the browsers: `npx playwright install chromium webkit`, with capture and inspection scripts written in TypeScript. Apply webapp-testing's method (look first, then act; screenshots; console capture; the `file://` pattern) rather than its Python, and use Playwright's `webServer` setting instead of `with_server.py` (usage: `--server "<cmd>" --port <n> [--timeout 30] -- <command>`). If Python is wanted anyway, it needs its own `playwright install chromium`, a second download, until 1.64.0 reaches PyPI.

Sources: https://pypi.org/pypi/playwright/json, https://raw.githubusercontent.com/microsoft/playwright-python/v1.63.0/DRIVER_VERSION, https://cdn.jsdelivr.net/npm/playwright-core@1.63.0/browsers.json, https://cdn.jsdelivr.net/npm/playwright-core@1.64.0/browsers.json, https://playwright.dev/docs/browsers, https://playwright.dev/python/docs/browsers, /Users/lucasta/.claude/plugins/marketplaces/anthropic-agent-skills/skills/webapp-testing/SKILL.md

### F9a [confirmed]
There is a `claude plugin install` shell command that installs a marketplace plugin when `/plugin` is not available.

Evidence: The local CLI (2.1.272) lists `claude plugin install|i <plugin>` with `-s, --scope user|project|local`, default user, and the docs say to run it "in your shell to install a plugin without starting a Claude Code session". For VS Code the docs say to type `/plugins` to open Manage plugins. On this Mac `claude plugin marketplace list` already shows `anthropic-agent-skills` (Git, https://github.com/anthropics/skills.git) and `claude plugin list` prints "No plugins installed".

For the build: If the owner wants the skills as real skills: run `claude plugin install example-skills@anthropic-agent-skills` in Terminal, then start a new session or run `/reload-plugins`. That adds 12 skills under the `example-skills:` prefix: algorithmic-art, brand-guidelines, canvas-design, doc-coauthoring, frontend-design, internal-comms, mcp-builder, skill-creator, slack-gif-creator, theme-factory, web-artifacts-builder and webapp-testing. It records `example-skills@anthropic-agent-skills` under `enabledPlugins` in `~/.claude/settings.json`.

Sources: https://code.claude.com/docs/en/discover-plugins, https://code.claude.com/docs/en/vs-code, https://code.claude.com/docs/en/plugins/loading, /Users/lucasta/.claude/plugins/known_marketplaces.json, /Users/lucasta/.claude/plugins/marketplaces/anthropic-agent-skills/.claude-plugin/marketplace.json

### F9b [confirmed] (load-bearing)
Having a sub-agent simply read a skill's SKILL.md by path is a sound alternative to installing the plugin.

Evidence: The docs describe a skill as a SKILL.md whose body loads only when used, and say subagents can invoke project, user and plugin skills through the Skill tool, which covers only installed or enabled ones; built-in agents do not preload skills. In this session the Skill tool listed none of the three skills, and reading them from the marketplace clone worked; none of the three uses `${CLAUDE_SKILL_DIR}`. `anthropic-agent-skills` is an official marketplace name with auto-update on by default, so the clone's contents can change between sessions.

For the build: In each sub-agent prompt, name the absolute SKILL.md path to read first and state that the product plan overrides it where they differ; give script paths in absolute form. For a stable reference across seven phases, copy the three skill folders (Apache-2.0, keep each LICENSE.txt) into the project's `.claude/skills/` from commit dbd4588 (2026-10-09), where they load as ordinary project skills.

Sources: https://code.claude.com/docs/en/skills, https://code.claude.com/docs/en/sub-agents, https://code.claude.com/docs/en/plugins/security, https://code.claude.com/docs/en/plugins/loading, /Users/lucasta/.claude/plugins/marketplaces/anthropic-agent-skills/skills/frontend-design/SKILL.md

## Recommendations
- **Bubble fades and crossfade in Phase 1**: CSS only: one always-mounted bubble per seat with `data-state`, `transition` on opacity and visibility (250 ms in, 1.5 s out), two stacked text layers for the crossfade, and `transition: none` under `prefers-reduced-motion: reduce` _Why:_ It meets every timing in the plan, works in all browsers, and Playwright's default screenshot mode fast-forwards CSS transitions so captures are repeatable. It also satisfies "simply appear and disappear", which Motion's `reducedMotion="user"` does not, because that setting keeps opacity animations.
- **Where Motion is used**: Keep the owner's choice: motion@14.1.0, pinned exactly, added in the phase that first needs layout animation (the stage folding into a card, seats fading in at spool-up); import from `motion/react`; drive reduced motion with `useReducedMotion()` _Why:_ There is no blocker: MIT, peers on React ^18 || ^19. Layout and shared-element moves are where a library saves real work. The package is one day old at 14.1.0 and one week into major 14, so an exact pin matters.
- **Table View layout method**: A pure TypeScript function `layoutTable({seats, width, height})` returning seat positions and one reserved, non-overlapping bubble slot per seat; a single ResizeObserver on the stage; bubbles as HTML with `max-width` from the slot and a two-line `-webkit-line-clamp` _Why:_ All of the plan's rules depend only on seat count and stage size, so no bubble needs measuring. A pure function is the only form Vitest with jsdom can test, since jsdom does no layout.
- **Testing the layout deterministically**: Vitest: for every seat count 3-7 across a list of stage sizes, assert that slots are pairwise disjoint, clear of other avatars and inside the stage. Playwright in Chromium and WebKit: at 1024 by 768 with the longest fixture text, read the real bounding boxes and assert no intersections _Why:_ The unit test proves the rule for all sizes without a browser; the browser test catches font-metric and clamp differences the pure function cannot see.
- **How seats are built**: SVG for the table and avatar shapes, with each seat wrapped in an HTML `<button>` positioned from the layout function, in seat order; Radix Tooltip for the full name; the name as HTML text in the head _Why:_ HTML buttons give keyboard order, a focus ring, an accessible name and a tooltip trigger with no extra work, and HTML text can be truncated and contrast-checked by axe. Radix Tooltip opens on hover and on focus and closes on Escape.
- **Name contrast inside seat heads (light theme)**: Fill the head with the Surface token and give it a seat-colour ring, keep the body in the seat colour, and set the name in the Text token (13.65:1 on Surface); cap short names at about 6 characters _Why:_ With the plan's light seat colours, #2B2A27 reaches only 3.25-5.54:1 and white 2.59-4.41:1, so a filled head cannot carry an 11 px label at 4.5:1 on every seat. This keeps all seven tokens unchanged. It is a design change, so it needs the owner's agreement.
- **Screen-reader announcements in Table View**: One visually hidden `role="status"` region that receives only speaker changes, per-round vote results and the final outcome; the timer as `role="timer"` with announcements at fixed thresholds only; bubbles outside any live region _Why:_ Bubbles are rewritten every few seconds and would flood a screen reader. MDN confirms a timer role is silent by default.
- **Chat View layout**: One DOM list in sequence order inside one scroll container; a CSS grid that is a single column when narrow and one column per seat when the container is at least seats times about 240 px; each message placed by `grid-column` (seat) and `grid-row` (sequence); vote dividers spanning all columns _Why:_ The same markup serves both layouts, time always reads top to bottom, and a single scroll container means one follow-newest state. The width test stops 6-7 seats from producing unreadably narrow columns.
- **Follow the newest message**: A script-driven `following` flag (bottom sentinel with IntersectionObserver, or distance from bottom under about 48 px), instant scroll to bottom after each batched update while following, and a "Jump to newest" button when not _Why:_ CSS scroll anchoring (`overflow-anchor`) reached Safari only in version 27, released 2026-09-14, so it cannot be relied on.
- **What drives the Phase 1 mocks**: A versioned fixture event log (`seq`, `t`, typed events) with a pure reducer and a small player (play, pause, seek to a sequence number), plus named scenes that are bookmarks into a fixture; a few synthetic fixtures for edge cases _Why:_ Table View and Chat View then animate from the same events the engine will emit in Phase 4, and the player becomes Phase 7 replay. Scenes give screenshot tests fixed, settled states, so playback timing never enters a test.
- **Delivering the mocks as one file**: vite-plugin-singlefile@2.3.3 in a separate `vite.mock.config.ts`, HashRouter, fixtures imported as modules, Fontsource CSS imports left as they are, nothing in `public/` _Why:_ The published source handles Vite 8 explicitly and turns on inlining for every referenced asset, so fonts become data URLs through Vite's own pipeline. Keeping it in a separate config leaves the real build untouched.
- **Which toolchain owns the test browsers**: Node: @playwright/test 1.64.0 installs Chromium and WebKit; all capture, inspection and regression scripts are TypeScript; webapp-testing is used for its method only _Why:_ Python Playwright on PyPI is 1.63.0 and expects different browser builds (chromium 1243 against 1248), so a Python script would either fail to find a browser or download a second set.
- **How the three skills are used in the build**: frontend-design: read at the start of Phase 1 design work, with the plan's look declared as pinned. webapp-testing: its look-first, screenshot and console-log method, run through Node Playwright. web-artifacts-builder: the single-file idea only. Sub-agents read each SKILL.md by absolute path; for durability, vendor the three folders into the project's `.claude/skills/` _Why:_ This matches the owner's request to use the plugin as a reference for part of the work, without letting the skills override decisions the plan has already made. Reading by path works today with nothing installed.
- **Summary length for bubbles**: Have the gateway ask the small model for a line sized to the seat count (about 14 words at 3-5 seats, about 8 words at 6-7), and show the full text in the agent's side sheet _Why:_ In my model, bubbles at 6-7 seats in a 1024 px window hold roughly 40-60 characters over two lines, so a two-sentence summary would always be cut off. The word counts are estimates to be tuned against the Phase 1 worst-case scene.

## Risks
- Table View text budget: at 6-7 seats in a 1024 px window, bubbles hold roughly 40-60 characters over two lines (my estimate), so the plan's "one- or two-sentence summary" cannot be shown in full. If this is not decided before the summariser prompt is written, every bubble will end in an ellipsis.
- Contrast in the light theme: 11 px names on seat-coloured heads miss 4.5:1 for most seats with any single label colour, sage and amber are under 3:1 against the background, and white on the clay accent is 3.84:1. axe will flag these in Phase 1, and fixing them touches the owner's fixed look.
- A design sub-agent that loads frontend-design without being told the look is pinned may "revise" it: the skill names warm cream, a high-contrast serif, a clay accent, middle-dot meta strings, #111 and monospace data labels as AI defaults to avoid.
- Running web-artifacts-builder's scripts in the app repository would install pnpm globally, Tailwind 3.4.1, 26 separate Radix packages and a shadcn component kit, and add Parcel as a second bundler, undoing the pinned stack.
- A sub-agent following webapp-testing literally will write Python Playwright; `uv run --with playwright` resolves 1.63.0, which needs browser builds that @playwright/test 1.64.0 does not install, so it fails or triggers a second browser download.
- Several pins are days old: motion 14.1.0 (2026-10-09, major 14 on 2026-10-02), @playwright/test 1.64.0 (2026-10-10), Tailwind 4.3.3 and radix-ui 1.7.0 (2026-10-09). Early patch regressions are possible; rely on exact pins and `npm ci`.
- Skills read from `~/.claude/plugins/marketplaces/anthropic-agent-skills` can change under the build: that marketplace name is in the official tier, where auto-update is on by default, and removing the marketplace deletes the clone.
- Motion's `reducedMotion="user"` leaves opacity fades running, so using it as the only reduced-motion switch would break the plan's rule that bubbles simply appear and disappear.
- The single-file mock has file:// limits: no History API routing, no fetch of local fixtures, and nothing from `public/` is inlined. vite-plugin-singlefile with Vite 8 was verified from source only, not run.
- Screenshot repeatability: Playwright fast-forwards CSS and Web Animations but not script-driven timers; bubble hold times must come from the debate clock or tests will capture different frames. Fonts must be awaited before capture (earlier research).
- Chat View columns: seven readable columns need about 1,750 px. Without a width-per-seat test, a 6-7 seat debate on a laptop gets columns too narrow to read.
- The event schema is designed in Phase 1, before the engine exists in Phase 4. If the engine's real events differ, both views and the fixtures need rework; version the schema and keep the reducer the only consumer.
- CSS features newer than the owner's browsers: anchor positioning needs Safari 26, `overflow-anchor` Safari 27. The recommendations avoid both, but they are easy to reach for by habit.
- `~/.claude/CLAUDE.md` describes an unrelated compliance product and loads into every session on this Mac. Without a project CLAUDE.md in the new repository, build agents may apply its data-handling rules to GX10 Council.

## Open questions
- Within a round, do agents speak one at a time or generate in parallel? This decides how many bubbles are visible at once and therefore how wide each can be.
- What is the smallest window the owner wants Table View to work in, how wide is the sidebar, and may it collapse while a debate is on stage? I assumed 1024 px and a 240 px sidebar.
- At 6-7 seats, should summaries be shortened to about 8 words, allowed a third line, or shown wide only for the current speaker?
- Is a head with a paper-coloured fill and a seat-colour ring acceptable so names reach 4.5:1 in the light theme, or should the seat colours themselves be adjusted? The same question applies to the label colour on the clay Send button.
- How long may a model's short name be, and who writes it (the owner in the seat picker, or a rule)? About 6 characters fit an 11 px label in a 44-48 px head by my estimate.
- Which Safari and Chrome versions do the owner's Macs run? Safari 26 or later widens the CSS that can be used.
- In wide Chat View, does the owner prefer strict time rows (one message per row across the columns, taller) or compact per-round columns (shorter, order within a round shown only by timestamps)?
- Should the three skills be installed as the `example-skills` plugin (auto-updating, 12 skills), copied into the project's `.claude/skills/` (fixed), or only read by path?
- Is the single HTML file the only Phase 1 deliverable, or does the owner also want a served preview and a PNG contact sheet?
- How many messages and how much text does a real 10-minute, 7-seat debate produce on the GX10? Only a run on the device can settle whether Chat View ever needs virtualisation.
- The plan's wireframes were not viewed (text-only extraction). Do seats sit at the very ends of the flat edge or inset from them, and what avatar size do the drawings imply?

## Independent re-check (overrides the above)

- **F1a** [partly] Package facts reproduce: motion 14.1.0 (published 2026-10-09T19:38Z), MIT, optional peers react and react-dom `^18.0.0 || ^19.0.0`, exact dependency on framer-motion 14.1.0; docs give 34kb, 4.6kb, +15kb, +25kb and say reducedMotion="user" keeps opacity. The suggested bubble snippet is incomplete: the `motion.p` needs `initial={{ opacity: 0 }}`, because `<AnimatePresence initial={false}>` only suppresses the first-render animation and an element without `initial` mounts at its `animate` value with no fade. Under the default mode "sync" old and new text are mounted together, so they must share one grid cell or use mode "popLayout". Motion shipped 10 releases between 2026-09-16 and 2026-10-09, so pick the exact pin when it is first added, not today.
- **F1b** [refuted] 
- **F2a** [partly] Cited facts reproduce (jsdom README: no layout, zeros for layout properties; Floating UI `detectOverflow` boundary is `'clippingAncestors' | Element | Array<Element> | Rect`, a containing boundary and not a set of obstacles; anchor-name Chrome 125, Firefox 147, Safari 26). Omitted: the plan's own stack table says the layout pass "Measures each bubble and moves it so none overlap", and "a bubble that would touch a neighbor's rises above it" is conditional on the text. Reserved slots turn rising into a fixed property of seat count and stage size, a behaviour change the owner should approve. "The gap between seats" is also undefined: centre to centre and edge to edge differ by the avatar width.
- **F2b** [partly] Neither the original figures nor mine are measurements. My independent packing model (60x74 px avatars, 52 px two-line bubble, 8 px clearance, 6.1 px per character, free horizontal anchoring) gives an upper bound of 148-172 px (41-49 characters over two lines) for 7 seats in a 736 px stage, 248 px at 6 seats and 320 px at 5. That matches the original 141-169 px; for a 976 px stage mine gives about 280-288 px against the original 190-255 px, because my model does not cap width at the seat gap. Read strictly, "no wider than the gap between seats" is about 110-155 px centre to centre at 7 seats in 736 px, or roughly 30-44 characters. Two short sentences (about 105 characters) need about 340 px, so the plan's "one- or two-sentence" line fits two lines only at 3-5 seats or in a wide window.
- **F3** [partly] Every contrast figure reproduces exactly from the plan's tokens, and the Radix and MDN quotes are accurate. Additions: Radix Tooltip Provider `delayDuration` defaults to 700 (ms), so set it lower for seat names. The proposed Surface-filled head leaves the amber ring at 2.46:1 on #FBF9F5 and 2.30:1 on #F5F1EA. The clay accent #C4694D is within 1.03-1.48:1 of all seven light seat colours (rose 1.03, slate 1.05), and the plan assigns clay to both the focus ring and the speaking glow, so the two states need different shapes and the focus ring needs an offset gap so it sits on the background (3.41:1).
- **F4b** [refuted] 
- **F4c** [unverified] No measurement exists, and the message-count estimate rests on unknown GX10 throughput. One carried-over detail needs care: MDN's data lists `content-visibility` in Safari from 18 but the `auto` value only from Safari 26 (Chrome 85, Firefox 125), so `content-visibility: auto` does nothing on older Safari and must stay an optional speed-up.
- **F5** [partly] Original holds. Precision: the clock page also lists Temporal.Now, requestIdleCallback/cancelIdleCallback and Event.timeStamp, and says `install` "MUST occur before any other clock related calls". `animations: "disabled"` cancels infinite animations to their initial state, so a pulsing speaker glow must be visible in its base style or it vanishes from screenshots. Vitest's `fakeTimers.toFake` default is "everything available globally except nextTick and queueMicrotask". Mid-fade frames could be pinned by pausing transitions through `document.getAnimations()` (Chrome 84, Firefox 75, Safari 14); that is an inference, not run.
- **F6** [confirmed] All 22 versions and the quoted peer ranges reproduce with `npm view` on 2026-10-10 (typescript latest 7.0.2, 6.0.3 pinned on purpose). Gaps in the pin list: @testing-library/react 16.3.3 has a required peer `@testing-library/dom ^10.0.0` (latest 10.4.2), and @types/react 19.3.0, @types/react-dom 19.3.0 and @types/node 24.19.2 are unpinned. vite-plugin-singlefile 2.3.3 also declares an optional peer `rollup ^4.59.0`, which Vite 8.3.4 (rolldown ~1.2.12) does not need. jsdom's full engines range is `^22.22.2 || ^24.15.0 || >=26.0.0`.
- **F7a** [partly] The source reading reproduces; it is still not run. The plugin writes `build.rollupOptions.output.codeSplitting = false`; Vite 8 documents `build.rollupOptions` as a deprecated alias of `build.rolldownOptions`, and Rolldown documents `codeSplitting: false` as equivalent to `inlineDynamicImports: true`. The 385 KB (514 KB base64) font figure is right for Fraunces `opsz.css` or `standard.css` plus the two `index.css` files, 16 files, upright only. Markdown emphasis would be a synthesized italic unless `@fontsource-variable/source-sans-3/wght-italic.css` is added (153 KB raw for all subsets, 28.5 KB latin). react-router 8.4.0 does export `HashRouter` and `createHashRouter`.
- **F7b** [refuted] Stronger evidence than the README: html-inline 1.2.0's index.js (version published 2015-10-02) rewrites only `script[src]`, `img[src]` and `link[href]`, and copies stylesheet text verbatim, so `url()` font references inside CSS remain external files.
- **F8a** [partly] 
- **F8b** [partly] The quotes are exact (SKILL.md lines 19, 39, 43, 45). Two further collisions: the plan's dark-theme accent #D9826A is close to #D97757, which the skill calls "Anthropic's own Claude-interaction accent, so on a user's brief it reads as a tell"; and the bubbles' repeating fade cycle is non-user-triggered motion, which the skill says to use "sparingly and deliberately". Both are pinned by the plan, so the skill's own rule that the brief wins applies.
- **F8c** [refuted] 
- **F8d** [refuted] All figures reproduce (PyPI playwright 1.63.0, 2026-09-15; chromium 1243 vs 1248, firefox 1543 vs 1555, webkit 2359 vs 2370). `DRIVER_VERSION` on playwright-python `main` already reads 1.64.0, so a matching PyPI release is probably close (inference). `uv run --with playwright` is unpinned and follows the newest release, so if Python is ever used, pin `playwright==` to the same minor as @playwright/test.
- **F9b** [confirmed] Holds: this sub-agent's Skill tool listed none of the three skills, reading them by path worked, `claude plugin list` reports "No plugins installed", and the docs list `anthropic-agent-skills` as an official marketplace name with auto-update on by default. Two cautions on the vendoring step. A copy of web-artifacts-builder under `.claude/skills/` becomes a live project skill whose first step is `scripts/init-artifact.sh`, and the docs say subagents "can still discover and invoke project, user, and plugin skills through the Skill tool". The vendored webapp-testing text says "write native Python Playwright scripts", against the Node decision. Vendor frontend-design and an edited webapp-testing; keep web-artifacts-builder outside `.claude/skills/` or add `disable-model-invocation: true`.

### Objections to recommendations
- Summary length sized by seat count on the server: bubble width depends on the browser window, which the gateway cannot see, and the plan says every debate is saved "with each message, summary and vote" for replay, including a phone layout in Phase 7. Sizing by seat count stores a layout assumption in the data. Use one fixed character budget for every debate (my estimate: about 45 characters for the 7-seat, 1024 px case), enforced with the summariser's token cap and a trim at a word boundary, because small models follow word counts poorly. Shorter output also takes less of the GX10's single GPU from the debating models (inference, not measured).
- Chat View grid with `grid-row` = sequence number: each row then holds exactly one message in one column, so a 5-7 column view is mostly empty cells and scrolls further than the single thread (my reasoning, not from a source). Dense columns need rows keyed by round and phase, or per-round sections where each model's column stacks on its own between vote dividers. That makes DOM order differ from strict time order, so "the same markup serves both layouts" may not hold; rendering two structures from one event list, switched on container width, is the simple alternative.
- Surface-filled seat heads with a coloured ring: the plan says the head carries the name "in its seat color", so this changes a pinned look and must go to the owner as a question, with the alternatives shown in the Phase 1 mocks. The amber ring is 2.46:1 on Surface and 2.30:1 on the background, under 3:1.
- Vendoring all three skill folders into the project's `.claude/skills/`: web-artifacts-builder would then be invocable by any agent and tells it to run `init-artifact.sh` (`npm install -g pnpm`, Tailwind 3.4.1, 26 Radix packages), the outcome F8c rejects. For a non-programmer owner an agent quietly running a global install is the worst case. Vendor only frontend-design and an edited webapp-testing.
- Pinning motion@14.1.0 now while adding it in a later phase: the version is one day old and the package released 10 times in the last 24 days. Record the decision as "Motion 14.x, pinned exactly at the version current when first added".
- Reserved bubble slots from a pure function: sound for testing, but it replaces the plan's stated mechanism ("Measures each bubble and moves it so none overlap") and makes rising static. Present it to the owner as a deliberate simplification, and define "gap between seats" in the layout spec before coding.
- One `role="status"` region announcing every speaker change: with up to 7 agents taking turns for up to 10 minutes this still announces every few seconds. Announce rounds, vote results and the final outcome by default and make speaker changes opt-in.
- Node owning the browsers: fine on the Mac, but run screenshot tests there only. Playwright names baselines per browser and platform (`-chromium-darwin`) and says to run "in the same environment where the baseline screenshots were generated", so Mac baselines will not match on Ubuntu aarch64. Installing Playwright's system dependencies on the GX10 also needs sudo. Building `dist/` on the Mac and copying it over would keep Node and browsers off the GX10 entirely.
- Checking only a 1024 px window: it is a useful worst case, but the owner's Macs probably open wider (a 13-inch MacBook Air's default is about 1470 px wide; unverified for the M5 model). Mock both the 1024 px, 7-seat worst case and the owner's real window so the bubble budget is not judged on the worst case alone.

### Missed by the first pass
- The Read tool cannot open the plan PDF on this Mac: it fails with "pdftoppm is not installed", and Homebrew is absent. I extracted the text through macOS PDFKit (osascript), so the five wireframes were not seen by me and will not be visible to design sub-agents either. Ask the owner to export the wireframe pages as PNG files into the project, or plan a text-only reading.
- Unrelated instructions load into agents: `/Users/lucasta/.claude/CLAUDE.md` (a defence-compliance project: CUI, ITAR, GovCloud rules) loads in every session, and `/Users/lucasta/Downloads/CLAUDE.md` (an AI trading project) loaded when I read the plan from Downloads. Give GX10 Council its own directory and CLAUDE.md that states its scope, and copy the plan into it, so sub-agents do not apply those rules.
- Installing the plugin is possible without the terminal. The VS Code docs say: type `/plugins` (plural) in the prompt box to open Manage plugins, with Plugins and Marketplaces tabs. The shell form also works: `claude plugin install example-skills@anthropic-agent-skills` (CLI 2.1.272 is installed here; default scope user; `--scope project|local`). That plugin's marketplace entry lists 12 skills, 9 of them unrelated to this build.
- The two-line clamp conflicts with "one- or two-sentence" summaries at more than the 7-seat case: by my estimate two short sentences (about 105 characters at 13 px) need a bubble about 340 px wide. Write the summariser brief as a character budget, not a sentence count.
- The plan's Border token is 1.20:1 on the background and 1.28:1 on Surface (dark: 1.41:1). Inputs, the message box and the table edge outlined only with it fall under the 3:1 non-text contrast level. The Agreed token #5E8C6A is 3.43:1 on the background: fine for the meter, not for text such as "Agreed 4 of 5".
- Playwright's `animations: "disabled"` covers "CSS animations, CSS transitions and Web Animations", not script-driven animation. Once Motion is in, screenshots need reduced motion or `MotionGlobalConfig.skipAnimations` (the name is present in the motion-dom 14.1.0 bundle; behaviour not run).
- Pause and the bubbles: bubbles update and vanish on their own (about 8 s), so the Pause control should also hold the bubbles currently shown. Deriving visibility from the debate clock, as F5 proposes, gives this for free; state it as a requirement and add a paused scene to the mocks.
- The stage-folding-into-a-card move was left unchecked. `document.startViewTransition` is in Chrome 111, Firefox 144 and Safari 18 per MDN's data, so it is a no-library candidate to compare with Motion's layout animation in that phase. Not evaluated with React 19.3.
- Browser floor for the owner: the dev Mac runs macOS 26.6.2, so its Safari is at least the 26 line (inference). That covers `@starting-style` (17.5), anchor positioning (26) and `content-visibility: auto` (26), but `overflow-anchor` needs Safari 27 (released 2026-09-14). Playwright 1.64.0's WebKit build reports 27.2, newer than the owner's Safari may be.
- webapp-testing's example scripts write to `/mnt/user-data/outputs/` and `/tmp/`, paths from Claude's hosted sandbox; the first does not exist on macOS. Any script adapted from them needs project-local output paths. `with_server.py --help` output matches the original report.
