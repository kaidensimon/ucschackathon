# Planner output: build-planner

Where this and docs/plan/phase-1-plan.md disagree, the plan wins.

## Verified today (read-only)

- The Read tool cannot open the PDF on this Mac (`pdftoppm` is missing). I extracted the text of all 16 pages, but saw the wireframe pictures (pages 4, 6, 7, 8, 13) only as coarse character renderings: structure confirmed, fine detail not. Sub-agents would hit the same wall, so WP 1.0 renders those pages to PNG and saves the text.
- No Playwright browser is installed. Python Playwright's newest release is 1.63.0; the pinned Node package is 1.64.0.
- `with_server.py` needs only Python's standard library. It stops only the shell it started, never reads the server's output, and treats anything already on the port as ready.

## 1. Work packages

| WP | What | Who | Needs | Done when |
|---|---|---|---|---|
| 1.0 | Repo; pinned install (previous stack table, `motion` 14.1.0, the font packages the three directions name, each confirmed with `npm view`); Chromium and WebKit; PDF pages as PNG and text in `docs/plan/`; scripts `look`, `look:file`, `contrast`, `font-face`; `CLAUDE.md`; `docs/BUILD_STATUS.md` | lead | none | clean `npm ci`; `look:file` screenshots a placeholder with an embedded font and 0 outside requests; `contrast` reproduces the known PDF-palette figures (white on clay 3.84, border 1.2) |
| 1.1 | Direction: three studies, a screenshots-only check, the picker page | workflow D, lead | 1.0 | three complete study folders; `contrast` exit 0 for each; picker opens by double-click with the network off |
| 1.2 | Everything that does not depend on the look | lead, workflow F | 1.0; runs beside 1.1 | `gate` green on a placeholder using real constructs; layout and timing tests green |
| Stop | Lucas picks | Lucas | 1.1 | his words in `BUILD_STATUS.md`; `docs/design/direction.md` and `docs/design/chosen-study/` committed |
| 1.3 | `tokens.css`, fonts (unused candidates removed), theme script, enforced contrast test, token guard, gallery token page | lead | pick, 1.2 | contrast green in both themes, all seven seat names in heads included; fonts proven loaded in the built app |
| 1.4 | App frame and primitives; `docs/design/recipes.md` | one agent | 1.3 | frame states pass at 1440 and 1024, both themes; lead compares with the chosen study and commits a restore point |
| 1.5 | Table View, Chat View, conversation and answer; review, fix, verify | workflow A | 1.4 | `gate` green; every must-show line ticked against a screenshot; each confirmed finding fixed or listed with severity |
| 1.6 | Gate package | lead | 1.5 | `gate` green with it in place |

Safe before the pick (WP 1.2), so the wait costs nothing:
- Lead: the check harness; `lib/types.ts`; the sample debate as an event log where "speaking" is a set of seats, a summary names no author and a vote is groups of seats with no stated matching method, so the mocks hold under all three back-end unknowns; `story.test.ts` (votes needed 3, 4, 4, 5, 6 for 3 to 7 seats); the `/review` state list; lazy route stubs; `phase-1-spec.md`; layout and timing tests, written first and frozen.
- Workflow F: seat positions for 3 to 7 seats, the bubble layout pass, the bubble timeline.
- `fixtures/study-content.json` (one question, five seat names, bubbles, the answer), so the studies differ only in look.

## 2. Showing the studies and recording the pick

- One file: `~/projects/gx10-council/Choose a look.html`, opened for him by the lead. No server; fonts are embedded.
- For A, B and C: a plain name, two sentences, light and dark screenshots side by side. Clicking opens the live study (theme switch; Play shows one bubble fade).
- Under the title: "Studies, not finished screens. Judge mood, colour and type."
- He answers in chat:
  1. Which do you want to live with: A, B, C, a blend (say which parts), or none?
  2. Does its dark version look as good as its light one?
  3. What one thing bothers you in it?
- Recorded verbatim and dated in `BUILD_STATUS.md`; the chosen folder is copied to `docs/design/chosen-study/` and its plan becomes `direction.md`. A blend or "none" gets one more study and a yes or no, once. Later changes wait for G1.

## 3. How each skill is used

**frontend-design**

| Agent | Reads SKILL.md | Returns |
|---|---|---|
| Three study builders | all | the seven items below |
| Screenshots-only reviewer (D) | calibration list | which default look each study resembles; whether two studies look alike |
| Lead, WP 1.3 | all | `direction.md`, tokens |
| Frame and screen builders | principles, restraint, writing | self-critique from their screenshots; the one thing removed; every string they wrote |
| Design critic | all | review against the five defaults and three type tells; wording review |
| F agents, function critic, first-time viewer, fixer, verifier | no | |

After the pick the skill's own rule applies: the brief wins. `direction.md` is the brief, and nobody redesigns.

Seven items per study; the lead rejects a return missing any:
1. `plan.md`: subject, audience, job; 4 to 6 named colours per theme; typefaces with roles and package names; layout sentence, ASCII wireframe, alignment; principles; the one bold element.
2. `review.md`: each default look and type tell marked absent or deliberate; at least one revision with its reason.
3. `contrast.txt`: text 4.5:1 or better, graphics 3:1, seven seat names, both themes.
4. `study.html`, self-contained, and `tokens.json`.
5. Screenshots: light, dark, grey.
6. `critique.md`, written from those screenshots: what was fixed, what was removed, what is still weak.
7. The fixed-function checklist, ticked.

**webapp-testing: one toolchain, Node Playwright**

- Why: 1.63.0 against 1.64.0 means a second browser download, and agents judging screenshots from a different browser build than the gate.
- Taken from the skill: its decision tree (static file: `look:file` on a `file://` address, no server; app: `look` with the server helper), look first then act, wait for load before inspecting, console capture, headless, always close.
- `with_server.py` and its Apache licence are copied to `ui/scripts/vendor/`. `look` refuses a busy port, then calls it with `exec node node_modules/vite/bin/vite.js --port N --strictPort --logLevel warn` (path confirmed in WP 1.0). It prints screenshot paths, the page's buttons, links and inputs, console errors and outside requests; `--press` and `--click` give the acting pass.
- The gate uses `@playwright/test`'s own `webServer` on 4310.
- Builders, fixer and verifier read the skill with one note: use `npm run look`; write no Python; screenshots go to `ui/.looks/<agent>/`, never `/tmp`.

## 4. Workflows

| Workflow | Stages | Agents |
|---|---|---|
| D | Three study builders in parallel (plan, review, build, screenshot, self-critique, one revision), then one screenshots-only reviewer. The lead runs `contrast` and builds the picker. A failed study is rerun fresh (budget 2). | 4 |
| F | Layout builder and timeline builder in parallel, against the lead's frozen tests | 2 |
| WP 1.4 | One frame builder, then the lead's check | 1 |
| A | Three builders in parallel (Table View; Chat View; conversation, answer and folded card), then three reviewers in parallel (design critic; function, keyboard, motion and truthfulness; first-time viewer with screenshots only), then one fixer, then one verifier | 8 |

About 15 agent runs (20 at worst) against about 26 before.

Every brief contains: role and single output; the product in three sentences; absolute paths to the spec, `direction.md`, chosen-study screenshots, `recipes.md` and `toolchain.md`; which SKILL.md to read; write list and frozen list; exact commands, port and screenshot folder; the nine fixed-function items, the three unknowns and the "do not correct" list; must-show lines; done-when as commands with expected exit codes; a fixed return shape (files, exit codes, screenshots, frozen-change requests, anything unfinished); the stop rule (report; never install, kill or use git).

Cut: the two-agent rehearsal (D is the rehearsal); four sequential reference builders (the picked study is the reference); two of three critique rounds; both skeptics (replaced by the "do not correct" list, the fixer's right to decline with a reason, and the verifier listing what was declined); per-folder fixers; the look switches; Python Playwright; the hardware test sheet.

Not cut: the pick before tokens; computed contrast for every palette; the skill's process evidence; a screenshots-only reviewer; builder, critic, fixer and verifier as different agents; the lead re-running `gate` before each commit; no-overlap tests in pure code and both browsers; both themes for every state; restore points.

## 5. Shared working tree

The previous rules stand (see the reused list). Changes:
- D agents write only `docs/direction/<a|b|c>/`.
- Only the lead edits `direction.md`, `chosen-study/`, `src/styles`, `src/lib/layout`, `ui/checks`. A complaint about the direction itself is reported as an owner question, not fixed.
- Ports: 5311 frame builder, then Table View; 5312 Chat View; 5313 conversation; 5314 fixer; 4310 built preview. Each port has its own Vite cache folder.
- Only the verifier and the lead run `gate`, because it writes `dist/`.
- Rollback is by folder: the lead restores a failed agent's write list and reruns it fresh.

## 6. Checks

```
check      tsc --noEmit && biome check . && token guard && vitest run
slice      one agent's files only; fails if it matched no tests
look       one state on the agent's port: screenshots, page outline, console errors
look:file  the same for a static file
contrast   every pair with its ratio; exit 1 below threshold
gate       check && vite build && playwright test    (built app, 127.0.0.1:4310)
```

Playwright runs from the `/review` state list, about 12 states fixed in the spec.
- Screenshots: every state in light and dark at 1440; table, Chat View and answer at 1024; Chat View and 7 seats at 760; WebKit on four key states. About 48 images, for eyes: nothing is pixel-compared in Phase 1, and the gate asserts the count.
- Accessibility: axe per state and theme, nothing serious or critical. Seat-name contrast is also a unit test over token pairs.
- Chat View has no colour: every computed text, background and border colour inside it has equal red, green and blue.
- Colour is never the only signal: each head has visible name text; speaker and vote are in the accessible name; a grey screenshot per table state.
- Keyboard: Tab reaches every control once, each with a visible ring; `?` opens the sheet and Esc returns focus; arrows move the Table / Chat switch; a letter typed in the message box triggers no shortcut.
- Motion: with reduced motion, `document.getAnimations()` is empty in the playing state and bubble opacity is 1 or absent; without it, the durations read 250 and 1500 ms.
- Offline: any request to another origin fails the run. Each chosen family has a loaded face and measures differently from the fallback.
- The gate fails on any console error, skipped test, or fewer states than expected.

Deterministic tests:
- Layout, pure function: 3 to 7 seats, all 243 speaker subsets, 4 stage widths, 3 bubble sizes. No two bubbles intersect, none touches a head, all stay in the stage, each is no wider than the seat gap and nearest its own seat.
- Layout, both browsers: real rectangles in 3-, 5- and 7-seat states with the longest text; no intersection; two lines at most.
- Timeline, fake timers: 0, 250, 8250, 9000, 9750 ms; a replacement crossfades in place; reduced motion gives only shown or gone. Static states pass a fixed time into the same function, so "one bubble fading out" is repeatable.

Judging the look: reviewers read each screenshot beside the chosen study and answer a fixed yes or no rubric citing file and region (five default looks, type tells, calm or control panel, grey test, two-line bubbles, wording rules). "Looks fine" is rejected. The lead reads the full final set.

## 7. Gate G1

- Open: double-click `Open GX10 Council mocks.command` (starts the built app, opens `/review`). `docs/review/phase-1/index.html` shows the screenshots with nothing running.
- Questions:
  1. Calm and readable, or control panel?
  2. Still the look you picked?
  3. Table View: can you tell at a glance who is speaking, who agreed and how close they are?
  4. Are names in heads readable with 3, 5 and 7 seats?
  5. Bubbles: are two lines enough, and is the fade speed right (press Play)?
  6. One speaker at a time and several at once are both mocked, because the back end has not decided. Does either look wrong?
  7. Chat View and the answer card, including "No consensus": right, or change what?
  8. Does dark read as well as light?
  9. Go on to Phase 2?
- Review bar on screens opened from `/review`: theme, seats 3 to 7, one or several speakers, Play. Left out of screenshots and scans.
- He answers by number in chat. Recorded dated; each change is a small work package; approved screenshots become the Phase 2 baseline.

`docs/BUILD_STATUS.md`: where we are; Lucas's decisions (dated, verbatim); work packages (status, commit, evidence); open questions; the three back-end unknowns and how the mocks stay true; findings not fixed; differences from the PDF; how to open and resume; run log.

Repo `CLAUDE.md`: what this is and what Phase 1 is; the owner reads plain language; `~/.claude/CLAUDE.md` and `~/Downloads/CLAUDE.md` describe other projects (only "Founder Context" applies); commands; repo map; agent rules, frozen paths, ports; design source of truth; the two skill paths and who reads which; toolchain notes; truthfulness rules; where status lives.

## 8. Time (estimates, not measurements)

WP 1.0: 35-50 min. 1.1 beside 1.2: 60-90 min. Pick: his time; a blend adds 20-30 min. 1.3: 45-60 min. 1.4: 50-70 min. 1.5: 1.75-2.25 h. 1.6: 30-45 min.

About 5.5 to 7.5 hours of machine time in two sittings split at the pick, against 7 to 10 before. Roughly 30% is one-time setup and checks that later phases reuse, 15% studies, 40% building screens, 15% review, fix and verify. Expect one or two feedback rounds of 30 to 60 minutes after G1. Usage cannot be predicted. Failure modes and their prevention are in the risks field.

### Critical Files for Implementation
- /Users/lucasta/Downloads/GX10 Cluster UI Plan.pdf
- /Users/lucasta/.claude/plans/distributed-puzzling-zephyr.md
- /Users/lucasta/.claude/plugins/marketplaces/anthropic-agent-skills/skills/frontend-design/SKILL.md
- /Users/lucasta/.claude/plugins/marketplaces/anthropic-agent-skills/skills/webapp-testing/SKILL.md
- /Users/lucasta/.claude/plugins/marketplaces/anthropic-agent-skills/skills/webapp-testing/scripts/with_server.py

## Decisions
- **One browser-test toolchain or two** One: Node Playwright (@playwright/test 1.64.0) for the gate and for agents' ad-hoc looks. No Python Playwright. _Why:_ Checked today: Python Playwright's newest release on PyPI is 1.63.0, the pinned Node package is 1.64.0, and no test browser is installed yet. Mixing them means a second set of browser downloads and agents approving screenshots from a different browser build than the gate uses. It would also break the rule that only WP 1.0 downloads anything.
- **How the webapp-testing skill is honoured without Python Playwright** Its method becomes two npm scripts: `look:file` (static file on a file:// address, no server) and `look` (app, look first, then act). Its helper `with_server.py` is copied into the repo with its Apache licence and used for ad-hoc looks; the gate uses Playwright's own `webServer`. _Why:_ The helper needs only Python's standard library and ran here today. Reading its 106 lines showed three weaknesses, each closed cheaply: it stops only the shell it started (so the server command starts with `exec node`), it never reads server output (quiet log level, short runs), and it accepts any process already on the port as ready (`--strictPort` plus a busy-port refusal). Copying it protects the build from a marketplace update. Fallback if WP 1.0's start-and-stop-twice proof fails: `look` starts Vite in-process instead.
- **When Lucas chooses the look** After three rendered studies and before any token, component or mock is built. Look-independent work (repo, checks, data shapes, sample debate, seat geometry, bubble layout, bubble timeline) runs beside the studies. _Why:_ Tokens and about 30 components built in the wrong direction would be thrown away. The parallel work means his thinking time costs no machine time.
- **What a study is and how it is shown** One self-contained HTML file per direction with embedded fonts, identical content, shown through one double-click page `Choose a look.html` with light and dark screenshots side by side and three plain questions answered in chat. _Why:_ He is non-technical: one thing to open, no server to start. Identical content and geometry mean he compares looks only. Embedded fonts avoid browser limits on fonts loaded from disk and prove the offline rule early.
- **Rehearsal run** Cut as a separate step. Workflow D is the rehearsal. _Why:_ D's agents write only their own folders and run the same npm commands, so a permissions or exit-code problem shows up there at the lowest stakes.
- **Reference slice** One frame builder followed by a lead check and restore point, then three screen builders in parallel. The owner-picked study is the visual reference. _Why:_ The previous plan used four sequential builders so one hand could set the look. The picked study now does that job, with his approval behind it.
- **Critique rounds** One round of three reviewers (design critic with the skill, function and accessibility critic, first-time viewer who sees only screenshots), one fixer, one verifier. No skeptics. One extra fixer and verifier pair is allowed if a high-severity finding stays open. _Why:_ Three rounds and two skeptics were most of the previous plan's weight. The skeptics' job (stopping fixers from undoing deliberate choices) is covered by a 'do not correct' list in every brief, the fixer's right to decline with a reason, and the verifier reporting what was declined.
- **Who reads frontend-design/SKILL.md** Study builders, the screenshots-only reviewer in D (calibration list only), the lead for tokens, the frame and screen builders (principles, restraint and writing sections), the design critic. Not the fixer, verifier, function critic, first-time viewer or the two logic builders. _Why:_ The skill tells its reader to make bold choices; after the pick that would invite redesign. The first-time viewer must stay naive to stand in for Lucas.
- **Proof that the skill's process was followed** Seven returned items per study: plan, review against the five default looks, computed contrast, the study, three screenshots, a critique written from those screenshots, the fixed-function checklist. The lead rejects a return missing any. _Why:_ The skill's value is its plan, review and self-critique steps. Files and exit codes can be checked mechanically; a claim of having followed it cannot.
- **How bubble timing and layout are made testable** Both are pure functions: positions from seats, sizes and stage; bubble state from the event log and a time. Static mock states pass a fixed time. The lead writes the tests first and freezes them; other agents write the code. _Why:_ Fades run by an animation library may not obey a test clock (unverified), and screenshots of a moving fade are not repeatable. A fixed time makes 'one bubble fading out' the same on every run, and tests written by a different hand cannot be bent to fit the code.
- **Pixel comparison of screenshots** None in Phase 1. Screenshots are produced for eyes; the gate only asserts that the expected number exists. Baselines start from the screenshots Lucas approves at G1. _Why:_ There is no approved look to compare against yet, and pixel comparisons would fail on every deliberate change during the build.
- **WebKit pass** Kept on four key states and on the browser layout test. _Why:_ The reason changed: the app is now opened in a browser, and Safari is installed on this Mac beside Chrome. Text measures differently in the two engines, which matters for the two-line and no-overlap rules.
- **The previous plan's three look switches** Dropped. _Why:_ They existed to let Lucas flip between the PDF's values and versions that pass contrast. The new palette is computed to pass before he sees it.

## Risks
- Sleep: this Mac is still set to sleep after 1 idle minute (confirmed today; it was on mains at 70%). Prevention: confirm mains power and hold sleep off with a temporary `caffeinate` at the start of each sitting. Closing the lid stops the run and loses at most the current work package.
- I planned without seeing the wireframes as pictures: the Read tool cannot open the PDF here, so I worked from the full text and coarse character renderings. Prevention: WP 1.0 renders the five wireframe pages to PNG; the lead reads them and corrects `phase-1-spec.md` before any builder starts.
- Leftover dev servers: `with_server.py` stops only the shell it launched, so a server can survive and hold its port. Not yet tested on this Mac. Prevention: start the server with `exec node`, use `--strictPort`, have `look` refuse a busy port, and have the lead check ports 4310 and 5311-5314 between stages and stop leftovers by process ID only. WP 1.0 proves it by starting and stopping a server twice on one port; if that fails, `look` starts Vite in-process instead.
- `with_server.py` never reads the server's output, so a chatty server can stall once its output buffer fills. Prevention: quiet log level and short-lived looks only; the long gate run uses Playwright's own server handling.
- Ports 5000 and 7000 are held by macOS Control Center on this Mac (confirmed today). Prevention: only 4310 and 5311-5314 are used.
- Several agents in one folder: Vite servers sharing one cache folder, one agent's half-written file breaking type checks for the others, two builds writing `dist/` at once. Prevention: a separate Vite cache folder per port, `slice` for an agent's own files, lazy route stubs, and only the verifier and the lead run `gate`.
- Playwright's WebKit on macOS 26.6.2 is unverified, and it is not Safari itself. Prevention: if it will not launch, the gate runs on Chromium only, the gap is written in `docs/BUILD_STATUS.md`, and Lucas is asked to open the mocks once in Safari.
- The three studies come out alike, or drift to the looks the skill lists as defaults. Prevention: the three directions are fixed in writing first, a reviewer who sees only the six screenshots checks for look-alikes and the five defaults, and a failed study is rerun fresh (budget of two reruns).
- Agents judge small spacing and colour differences poorly. Prevention: everything measurable is measured (contrast, overlap, line count, colourless Chat View, focus rings), rubric answers must cite a file and region, and Lucas's eye decides composition. Expect one or two feedback rounds after G1.
- One critique round instead of three can let findings through. Prevention: the verifier lists every unfixed and declined finding; one extra fixer and verifier pair runs if a high-severity one is open; the rest are shown to Lucas at the gate with their severity.
- New major versions (Vite 8, Vitest 5, TypeScript 6, Tailwind 4, Motion 14): agents may write older patterns from memory. Prevention: the lead writes and freezes all configuration, and `docs/research/toolchain.md` holds import lines verified from the installed packages.
- Sub-agents blocked by permission prompts. Prevention: workflow D is the first and lowest-stakes run; if its agents cannot run the npm scripts, the lead stops and asks Lucas to allow this project's npm scripts before anything larger starts.
- Claude usage for about 15 agent runs cannot be predicted. Prevention: workflows stop cleanly at stage ends; a ceiling is an owner question.
- Git commits on this Mac carry the placeholder address you@example.com (confirmed today). Harmless while nothing is pushed.
- The time figures are estimates, not measurements. The two largest unknowns are how long the three parallel screen builders take and how many findings the single review round returns.

## Questions for the owner
- This plan adds one short stop about two hours in: you open one page and pick the look from three studies (about five minutes of your time). You asked for a single stop at the end of Phase 1. Is the extra stop fine, or should I pick the look myself and show you only the finished mocks?
- Do you want a usage ceiling at which the agent workflows stop cleanly? I cannot predict how much Claude usage about 15 agent runs will consume.
- Should the picker page also show your PDF's original look (warm paper, Fraunces titles, clay accent) as a fourth study for comparison? It costs one more agent run of roughly 20 to 30 minutes (an estimate). My default is no, and 'none of these' stays an allowed answer.
