# Study brief (shared by looks A, B, C)

Talk short. Stone Age talk. Exact things stay exact (paths, hex, numbers, commands, words on screen).

## Job
Draw ONE look as ONE self-contained HTML study. Owner Lucas compares three studies and picks. Same words, same seats, same sizes in all three. Only look differs.

## Read first (in order)
1. `docs/skills/frontend-design/SKILL.md` — all of it. Follow its process.
2. `docs/direction/<your letter>/direction.md` — your look, as written.
3. `docs/direction/<your letter>/corrections.md` — BINDING. Corrections beat direction.md.
4. `docs/direction/<your letter>/judges.md` — why corrections exist.
5. `docs/direction/study-content.json` — words, seats, sizes, four panels. Do not change words or numbers.
6. `docs/plan/wireframes/page-04-main-screen.png`, `page-06-table-view.png` — owner's own drawings (structure only; their blue and pastel colours are drawing notes).

Ignore the "study brief" section at the end of direction.md. This file replaces it.

## You may change / may not change
- MAY: how the study is drawn (spacing, sizes of small parts, line weights, bubble shape) to make the direction work on screen.
- MAY NOT: the direction's written colours, typefaces, bold element. Think one is wrong? Report it. Do not swap it.
- MAY NOT: words, numbers, seat order, sizes in `study-content.json`.

## What to build
Folder: `docs/direction/<letter>/`. Write only there.

`study.src.html` → run embed script → `study.html`. One file, no outside requests, no CDN, no fallback fonts.
- Fonts: put ONE tag in head: `<style data-fonts="@fontsource-variable/<pkg>/<file>.css ..."></style>`. Then `npm --prefix ui run embed-fonts -- docs/direction/<letter>/study.src.html`. Script fills the tag. Never print, read or paste font data. Script errors → stop and report. No substitute font.
- CSS families after embed: `'Besley Variable'`, `'Atkinson Hyperlegible Next Variable'`, `'Literata Variable'`, `'Archivo Variable'`. Files that exist: archivo `wght.css wdth.css` (+`-italic`), literata `wght.css opsz.css` (+`-italic`), besley `wght.css wght-italic.css`, atkinson-hyperlegible-next `wght.css wght-italic.css`.
- Theme: `data-theme="light|dark"` on `<html>`. Small theme switch top right of page. Default light. Tokens as CSS variables under `:root` and `[data-theme=dark]`.
- Page = four panels stacked, each a 1440 × 830 app window (top bar 48, sidebar 240, rest conversation), 48 px apart, short plain caption above each. Page width 1440.
  1. `p1-one-speaker` — Table View mid-debate, Qwen speaking, three bubbles (third at half strength).
  2. `p2-all-speaking` — all five speaking, five bubbles, none overlapping.
  3. `p3-seven-after-vote` — seven seats, vote marks on every head.
  4. `p4-released` — folded stage card + answer in chat.
- Stage: 1040 × 558 box in the conversation. Table flat side down at y = 520. Seat points and sizes from JSON (`layouts.five`, `layouts.seven`). Figures upright: head circle D, body half-circle 1.4 D wide × 0.7 D tall, 2 px under head. SVG for table and figures. HTML for bubbles.
- Stage footer: Pause, Stop left. Table / Chat switch right (Table active).
- Play button on panel 1: one bubble fades in 250 ms, stays, fades out 1.5 s. With `prefers-reduced-motion`: appears, disappears. Nothing else moves.
- Chat View not in study (black and white in every look).
- `tokens.json`: your tokens, both themes: `{ "light": {name: hex}, "dark": {...} }`.
- `contrast-pairs.json` for `npm --prefix ui run contrast -- <file>`: every text pair (min 4.5) and graphic pair (min 3), both themes. MUST include: body text on page and on surface; muted text; each of 7 seat names on its head; each seat figure against page; vote marks on every seat colour; speaker mark; bubble edge; table edge; focus ring; label on main button; agreed and error colours as text.

## Fixed function (tick each in `checklist.md`)
1. Calm, readable, roomy. Not control panel. Light AND dark both designed.
2. Body text ≥ 4.5:1.
3. Half-circle table, flat side to viewer. Head = full circle with short name inside. Body = half circle. Seat colour on figure. Colour never only signal.
4. Speaker marked ON the figure (ring round head = speaking, always).
5. After vote: check or cross on every head. Check = solid dark disc, pale check. Cross = pale disc, dark outline, dark cross. Never red.
6. Table middle: round, time left, meter, caption like "2 of 5 agree, needs 4".
7. Bubble: above own seat, 2 lines max, no overlap with bubble or figure.
8. Keyboard focus on seat = outline round WHOLE figure (not head ring). Show one focused seat in panel 3.
9. Fonts embedded. No network.

## Look at own work (webapp-testing method: look first, then fix)
`npm --prefix ui run look:file -- docs/direction/<letter>/study.html --out docs/direction/<letter>/shots --full --grey`
Gives light, dark, grey PNG + console errors + outside requests. Exit must be 0. Read the PNGs. Fix. Look again. One revision round at least (skill: critique from screenshot, remove one thing).
B only, also: `--scale 1 --name study-1x` (ordinary screen sharpness).

## Return (all seven; missing one = rejected)
1. `plan.md` — subject, audience, job; 4–6 named colours per theme; typefaces + roles; layout sentence + ASCII; principles; the one bold element.
2. `review.md` — each generic look and type tell from skill: absent or deliberate. At least one revision to how study is DRAWN, with reason.
3. `contrast-pairs.json` + exit code of contrast command (must be 0).
4. `study.src.html`, `study.html`, `tokens.json`.
5. Shots in `shots/`: light, dark, grey (full page).
6. `critique.md` — written FROM the screenshots: what fixed, what removed, what still weak.
7. `checklist.md` — nine fixed items ticked, each with where to see it.

## Rules
- Run only `npm --prefix ui run <script>`. No install. No `npx`. No git writes. No killing processes. No Python scripts.
- Write only inside `docs/direction/<letter>/`.
- Need something frozen changed? Work round it, report it.
- Final reply: Stone Age talk. List files, exit codes, shot paths, anything unfinished, anything you think is wrong in the direction.
