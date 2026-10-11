# Look C — critique, written from the screenshots

Short talk. Shots read: `shots/study-light.png`, `shots/study-dark.png`, both grey, `shots/study-1x-*.png`, and per-panel shots in `shots/work/`.

## Speaker ring (correction 9): which one
Built both. Looked at both.
- First: ring in seat colour, 2 px, 5 px out, over 22% halo (as direction.md). Shots kept: `shots/work/ringseat-p1-one-speaker-light@1x.png`, `...-dark@1x.png`, `shots/work/ringseat-p2-all-speaking-*.png`.
  - Seen: head just looks bigger. Halo is a muddy pastel band. Strength changes with seat colour (ochre soft, indigo hard). Tail of bubble touches halo.
- Final: **ink ring with page-colour gap**. 3 px ring in `accent` (`#1D2A24` light, `#E6EBE7` dark), 4 px page gap between head and ring. No halo.
  - Seen (`shots/work/panel-p1-one-speaker-*.png`): Qwen stands out at a glance in both themes. Same strength on all seven colours. In panel 2 all five rings equal.
- Panel 3 has no speaker. Checked there instead: focus rectangle (Granite) and vote marks do not look like a ring. Clear.

## Fixed after looking
1. Ring: seat colour to ink (above).
2. Name size: first build 20 px and 18 px. Browser said Gemma and Hermes needed under 72% width (console error from the study's own check). Dropped to 19 px and 17 px. Now Gemma 75%, Mistral 90%, Llama 103%, Qwen 107%, Phi 125% in the 72 head; Granite 80%, Hermes 75%, Gemma 74% in the 64 head. All measured, not guessed.
3. Line-up badges in the folded card: 12 px was too small to tell check from cross at ordinary sharpness. Now 13.6 px.
4. Theme row in sidebar read "ThemeLightDark" to a screen reader. Given the label "Theme".

## Removed (mirror check, from the shots)
- The halo. Ring alone does the job.
- Before build (see `review.md`): "5 seated" text, attach icon, small Phi figure beside the dissent line, any tint under bubbles.

## What works
- Names across heads carry it. Width axis is visible: Phi wide, Gemma narrow, same height all round the table.
- Vote marks: solid disc with check against hollow disc with cross reads in colour, in grey, in dark. No red needed.
- Grey shots: every seat still told by name and body cut. Figures all clear of page.
- Five bubbles at once: none touch. Machine-checked on load (study logs a console error if a bubble touches another bubble or a figure, leaves the stage, or runs to three lines). Look run: 0 console errors.
- Table on the message box: one base line. No tombstone.
- White page + ink + seven seat colours: calm. Nothing else has colour except the green "Agreed" check and word.

## Still weak
- Figure is still the stock "user" outline. Body width is frozen at 1.4 x head by the shared brief, so correction 15 (narrow shoulders) could not be done. Worst at small sizes: top-bar figures (head 14) and line-up figures (head 22) have no name inside and no cut. They are coloured user icons with a name beside them.
- Phi: at widest (125%) the name is 36 px across a 72 head, others 56 px. Head looks emptier.
- Light theme, small sizes: indigo (Llama) and claret (Gemma) both read near-black in the top bar. Name beside them is what tells them apart.
- Dark theme: teal and ochre are much brighter than claret and violet. Phi and Qwen (Granite in seven) shout a little.
- Grey, light theme: neighbours Hermes (rust) and Mistral (violet) come out the same grey. Names and cuts still differ.
- Speaking lean (4 px in, head 2 px up) is drawn but cannot be seen. Ring does all the work.
- Table middle is small in a big pale table. Left at direction's sizes (14 and 13 px).
- Big empty band between question and stage. True to a pinned stage with a short chat; may look bare.
- Half-strength bubble text is 3.24:1 in light (4.38:1 dark). It is a bubble on its way out, as the brief asks, but it is under 4.5 while it lasts.
- Top bar says "Council of 5" over seven seats in panel 3. Shared content says so; not changed.
- Error colour is in tokens and contrast list only. No failed seat in shared content, so not drawn.

## Fix round
Small fixes only. No colour, font or wording-rule change. Shared file `../study-content.json` re-read. Shots retaken: `shots/study-*.png`, `shots/study-1x-*@1x.png`, `shots/work/panel-*.png`.

1. Table radius: five `tableRadius` 221 to 204, seven 233 to 224 (shared file). End-seat bodies no longer bite the table. Nearest body to table edge: 11.6 px (five), 7.6 px when the seat leans in to speak (panel 2), 9.6 px (seven). Study now logs a console error if any body comes within 2 px of the table. Look run: 0 console errors.
2. Top bar: each panel reads its own `topBarLeft`. Panel 3 says "Council of 7". Panels 1, 2, 4 say "Council of 5". The "Still weak" line about this above is closed.
3. Panel 3, faded Hermes bubble: left edge moved from x 688 to x 716 (stage). Was 12 px from Gemma's vote mark, now 40 px from it and 44 px from Gemma's head. Bubble sits x 716-942, y 181-221, out to the right over Hermes. Tail points down at the middle of Hermes's head, 12 px above it. Machine check (4 px clear of every other figure): passes.
4. Table flat edge (C only): reviewer said the message box hid the table bottom and the table looked chopped. Stage moved up 12 px (`.stage` top 182 to 170). Message-box row did not move (top 702). Flat edge (stage y 520) now ends 12 px above the row. No overlap. Table outline is now closed, so the flat edge has its own line in the edge colour, same 1.5 px as the curve.
   - This replaces "Table on the message box: one base line" under "What works", and item 1 of `review.md` ("table sits on its top edge"). Table is narrower than the box and stands just above it. Still no tombstone.
   - Side effect: empty band between question and stage is 12 px shorter.

Checked by eye in `shots/study-1x-light@1x.png`, `shots/study-1x-dark@1x.png` and `shots/work/panel-p2-all-speaking-*`, `shots/work/panel-p3-seven-after-vote-*`. Contrast: 118 pairs, 0 below threshold.
