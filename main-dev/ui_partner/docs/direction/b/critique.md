# Look B, Fair Copy — critique (written from the shots)

Stone Age talk. Looked at: `shots/study-light.png`, `shots/study-dark.png`, both grey, `shots/study-1x-*@1x.png`, per-panel shots in `shots/work/` (round 1) and `shots/panels/` (round 2), zoom shots `shots/work/z-*`.

## Round 1: what shots showed
- All five panels drew. No bubble on bubble, no bubble on figure (layout pass reports 0; look exit 0).
- Tally reads at once on table top. Filled strokes strong, hollow strokes thin, line under number needed. Good.
- Dots pattern (seat 3) was dense dark stipple. Looked like grid pattern (seat 7) at ordinary sharpness. Bad.
- Up-down and across lines were soft at ordinary sharpness (1.5 px line on half pixel).
- Panel 4: margin line ran on under the answer sheet, through empty page, to nowhere. Also poked out in gap between docket and sheet. Stray mark.
- Patterns + 3 px ring make bodies louder than heads. Patterns-off panel is calmer and tally wins more clearly.

## Fixed (round 2)
1. Dots: now rows 6 px apart, each next row shifted 3 px (still "staggered 6 px grid"). Reads as dots, not mesh. See `shots/work/z-p3-light@1x.png`.
2. Line patterns moved onto whole pixels (line centre 2.75, not 3). Crisper at scale 1. Pitch stays 6 px: at scale 1 all six patterns tell apart (up-down, dots, rising slant, across, falling slant, grid). Did NOT widen to 8 px.
3. Speaker ring drawn 3 px with 4 px gap (direction: 2.5 px, 5 px gap). Body gets small page-colour bite under ring so violet never touches seat colour.
4. Vote discs got 2 px page-colour halo. Ink disc straight on seat ring fails (sepia 1.47:1 light; every seat under 3:1 in dark).

## Removed
- Margin line below the docket in panel 4. Line now stops where the record starts, same rule as panels 1 to 3 (stops at stage).
- Before build: five names with tiny pattern chips in top bar; helper line under message box.

## Still weak
- End seats (Phi, Mistral) in five-seat layout: body corner sits about 6 px over table edge. Comes from shared sizes. Same in all looks.
- Only 5 px between speaker ring and bubble above (shared 12 px gap minus ring). Stem line there is a stub.
- Half-strength bubble: text 3.09:1 in light. It is leaving the screen, but old eyes may lose it early.
- Panel 4: right third empty. Direction wants it (agent sheet docks there). May look unfinished.
- Violet ring next to blue seat ring in dark, all five speaking: hues close. Shape (second ring) carries it; colour does not.
- Bodies with patterns compete with tally. Judges said so. Patterns-off panel shows the other way.
- Docket shows count twice (tally and five named marks). Shared content asks for marks.

## Lucas judges (said plainly, per correction 9)
- Head is pale tint with coloured ring, NOT solid seat colour. Kept as direction wrote it. Solid colour could not carry the name at 4.5:1. Lucas decides if seats feel coloured enough.
- Line patterns on (panel 1) or off (panel 1 again, second window).
- Bubble text slanted (as designed) or upright: strip under the two panel 1 windows, look in dark.

## Not in study
Chat View (brief). Failed seat, loading seat (error red not drawn). Agreement motion. Violet writing cursor (brief: nothing else moves). Full model names on hover.

## Fix round
Small fixes only. No colour, font or wording change. Looked at: `shots/study-1x-light@1x.png`, `shots/study-1x-dark@1x.png`, `shots/panels/p1-one-speaker-*@1x.png`, `shots/panels/p2-all-speaking-*@1x.png`, `shots/panels/p3-seven-after-vote-*@1x.png`.

Changed:
1. Table smaller. `tableRadius` 204 (five seats), 224 (seven seats). Was 221 / 233. No body touches table now. End-seat body corner to table edge: about 11 px (five), about 9 px (seven). Old "Still weak" line about end seats is no longer true.
2. Panel 3 top bar says "Council of 7". Panels 1, 2, 4 say "Council of 5". Was already so in B. Checked in shots, nothing to change.
3. Panel 3, faded Hermes bubble. Was 17 px beside Gemma head. Now up and right of Hermes: left edge 16 px inside Hermes centre, 45 px clear of Gemma. Stem line runs from bubble down to Hermes head.
4. Panel "all five speaking". Phi bubble now 30 px clear of Llama body (was 8). Mistral bubble 30 px clear of Gemma body (was 8). Every bubble now 12 px above its own speaker ring (was 5 px; gap was counted from head, now from ring). No bubble on bubble: 8 px least. All inside stage. Each stem lands inside its own bubble, above its own seat.
5. Same rule in both panel 1 windows, so panels agree: Qwen bubble 7 px higher (clear of its ring). Played Mistral bubble 21 px further right (29 px clear of Gemma body).

How rule works now (layout pass in `study.src.html`):
- Bubble sits 12 px above top of own head. Speaker ring or vote mark there: count from that.
- Other seat's figure in the way: bubble hangs outward from its stem, stem 16 px in from bubble's inner edge. Never closer than 24 px to other figure's box.
- Other bubble in the way: move 8 px clear, no more.
- After placing, page measures every bubble against the drawn shapes (head, ring, vote disc, body) and other bubbles. Under 4 px, outside stage, or not above own seat: console error, so look exit is 1. Now: 0 errors.
- Open `study.html#measure` to list every gap (prints as errors on purpose, so that run exits 1).

Measured (px, to own figure / nearest other figure / nearest bubble):
- Panel 2: Qwen 11.6 / 78.6 / 8. Llama 11.8 / 57.1 / 8. Gemma 11.8 / 58.1 / 8. Phi 12.3 / 29.9 / 93. Mistral 12.3 / 29.9 / 93.
- Panel 3: Hermes 11.9 / 45.2 (Gemma) / none.
- Panel 1: Qwen 11.6 / 85.6 / 8. Gemma 11.8 / 58 / 8. Llama 11.8 / 57 / 8. Played Mistral 12.3 / 29.2 / 93.

Kept: patterns on / off windows, slanted / upright strip, Play button, all else.

Still weak after fix round:
- Phi and Mistral bubbles in "all five speaking" hang mostly outward of their seats (stem near inner end). Rule says end seats push outward. Reads as theirs, but lopsided.
- Hermes bubble is half strength, so its stem is half strength too: 1 px faint line. Points at Hermes, but old eyes may miss it. Bubble place carries it more than the line.
- Old "only 5 px between speaker ring and bubble" line is no longer true: now 12 px.
