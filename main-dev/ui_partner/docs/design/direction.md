# The look: C, "Cut-Out Council" (the brief)

Lucas, 2026-10-10: "lets go with C." This is now the brief. Nobody redesigns. A complaint about the look is a question for Lucas, not a fix.

Short talk below. Exact things exact.

## See it
- Reference study: `docs/design/chosen-study/study.html`. Shots: `docs/design/chosen-study/shots/study-1x-light@1x.png`, `study-1x-dark@1x.png`. The app must look like these.
- Full written direction: `docs/design/chosen-study/direction.md`, `corrections.md` (corrections win), `plan.md`, `critique.md` (read its "Fix round").
- Colours, corners, type sizes: `ui/src/styles/tokens.css` + `ui/src/styles/app.css`. Only source. Use Tailwind token classes (`bg-page`, `text-ink`, `border-line`, `bg-seat-3`, `rounded-control`, `text-bubble` ...). Raw hex or bracket values fail the token guard.

## Six rules
1. Colour belongs to the council. Every hue on screen is a seat. Controls are ink (`accent`). Only other colour: `agreed` green and `error` red, always with a mark and a word.
2. Name is the face. No eyes, no mouth. Name lettered across the head in `on-seat` (page showing through), fitted by Archivo width (62 to 125), never shrunk. One name size per council.
3. One colour per figure. Head and body solid seat colour. One cut per seat body, in page colour, fixed to the seat (seat 1 plain, 2 band, 3 collar V, 4 sash, 5 placket, 6 yoke, 7 braces).
4. Every state has a shape and a word. Ink ring round head with page-colour gap = speaking. Solid ink disc with page-colour check = agrees. Page-filled disc, ink outline, ink cross = disagrees. Never red. Rounded rectangle round whole figure = keyboard focus. Dashed outline = model not ready.
5. Fills are rare: figures, table cloth, ink buttons. Everything else is a `line` edge on paper. No shadows. No gradients. No uppercase. Three corner sizes: `rounded-control` (8), `rounded-card` (14), `rounded-full`.
6. Nothing loops. Motion marks a change: controls 160 ms; bubbles follow the debate clock (fade in 250 ms, stay 8 s, fade out 1.5 s); one staged moment only (stage folds at agreement). Reduced motion: nothing animates.

## Type (one family: Archivo Variable)
- Names in heads: weight 650, one size per council (19 px in 72 head, 17 px in 64 head, 15 px in 56 head), `font-stretch` chosen per name so it spans about 0.78 of the head. Measure in the browser.
- Title 24/30 weight 620. Answer heading 20/26 weight 650. Body and answer 16/26. Chat View 15/24. Labels and buttons 14/20 weight 500. Bubbles 13/18 weight 450. Meta 12/16 `muted`.
- Numbers: tabular figures (set on `html`). No mono face except code blocks (`font-mono`).

## Wording (frontend-design skill, writing section)
Plain verbs. Sentence case. Digits. No exclamation marks, no arrows, no middle dots, no all-caps. One word per thing, same everywhere: seat, round, vote, agree, answer.
- Status pill, parts set apart by space: `Round 2   3:10 left   2 of 5 agree`. Others: `Seating the council, 3 of 5 ready`. `Reading your files   4:45 left`. `Paused in round 2`. `Agreed 4 of 5, writing the answer`. `Agreed 4 of 5`. `No consensus, 2 of 5`. `Phi did not load`.
- Table middle: `Round 2`, `3:10 left`, pips, `2 of 5 agree, needs 4`. Before first vote: `No vote yet, needs 4 of 5`.
- Vote divider (Chat View): `Round 1 vote: 2 of 5 agree, needs 4`.
- Answer: heading `Agreed 4 of 5`, under it `3 rounds, 3:40`. No consensus: `No consensus, 2 of 5 backed this answer`, under it `Time ran out at 2:00`.
- Dissent: `Phi disagreed: <its line>`.
- Buttons say what they do: `Ask` (new chat), `Add to next round` (during debate), then notice `Reaches the council at the start of round 3`. `Pause` / `Resume`. `Stop`. `See the debate`. `Try again`, `Continue with 4`, `Stop`.
- Empty chat: `What should the council settle?`
- Dead control in mock: one quiet line `Not in this mock yet`.
- Sidebar footer: `Sample data. Invented files and answers.`
- Errors say what happened and what to do. No apology.

## Known weak spots (Lucas sees them at G1; do not "fix" by redesign)
- Figure is close to the stock user icon. Keep head large, name filling it, cut visible.
- Light: indigo and claret near-black at small sizes. Dark: teal and ochre bright.
- No accent hue: outside the table it is ink on white. That is the look.
