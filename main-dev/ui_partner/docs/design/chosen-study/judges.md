# Judges' findings for direction C

## judge:distinct
Scores (1-5): distinctiveness 3, calm and readable 4, function 3, feasibility 4

### Must fix
- The page is the PDF's cream to the eye, so 'No cream' is not true on screen. Either take a real step (pure white #FFFFFF is 4.2 units from the cream and lifts the two tightest seats, ochre to 5.43 and slate to 5.35; small hue nudges I tried stay under 2 units), or keep the value and delete the claim.
- Same two font families as record, and the same Literata 17/28 answer. Use the direction's own stated fallback now: answers in Archivo 16/26. Voices becomes the one-family direction (the skill allows one), the width axis becomes its type identity, and the overlap with record and with Claude's own serif replies goes.
- Top bar shows 'o o o o o 5 seated': five coloured dots with no names. That is colour as the only signal, and it breaks the direction's own rule that below a 24 px body the name is written beside the figure. Write the names, or drop the mini figures from the top bar.
- Cut the 'addressing' and 'reading files' postures from Phase 1. They need two per-seat signals the back end has not promised, and they spread small movements round the table all debate long. Keep the speaking lean. Choose one staged moment (start or agreement), not both.
- Status pill: gaps instead of pipes, as the other two do.
- Bubbles: drop the shadow and draw the edge in the 'line' token (3.55:1) instead of the 1.29:1 hairline; collapse five radii to three.
- Table: stop listing the cloth as an identity colour (the 3.55:1 edge line is what the eye sees). Do not deepen it to a visible green: a green half-round table with figures on the curve is a card table, which is why the room direction refused baize.
- Chat View: remove the hairline column separators and go back to the PDF's #111111, #0E0E0E, #F2F2F2. They already have equal red, green and blue, so the test still works and Chat View stays the same in all three studies.
- Study brief: delete the option to load fonts from the Fontsource CDN. It breaks the no-network rule. Embed or stop.
- Radius and stage height are defined in terms of each other (R depends on stage height minus 190; stage height is R plus 190). State the available height independently.
- The fit rule's 'unit test' cannot run in jsdom, which does not measure text. It has to be a browser check, and the author's width figures for condensed names are scaled estimates, not measurements.

### Generic-look tells found
- Cluster 1, two of three parts. The page #F1F2EE measures 0.59 units from the skill's cream #F4F1EA and 0.67 from the PDF's #F5F1EA, at the same lightness (about 2 is just noticeable). On screen it is the starting cream. A serif (Literata) then sets the answer on it. No clay.
- Cluster 4 (card kit), partial. Bubbles are a 10 px rounded surface with a 1 px hairline (1.29:1 on the page, 1.40:1 on the bubble), one soft shadow and a tail; message box and folded card at 14 px; five radii in all. That is the stock tooltip and chat-bubble recipe, and it is the PDF's 'hairline borders and very soft shadows' carried over.
- Cluster 5. The status pill 'Round 2 | 3:12 left | 3 of 5 agree' is the middle-dot meta string with pipes. Chat View near-blacks were changed to #161616 and #101010, still the listed tinted near-black; the stated reason (equal red, green and blue) was already true of the PDF's #111111, #0E0E0E and #F2F2F2.
- Cluster 3, in Chat View only: hairline column separators (#DCDCDC, 1.37:1). The other two separate columns with space.
- The default avatar. A solid colour circle with a light name knocked out is what chat apps draw for a user without a photo. The author's review rejected tinted circles with initials as 'the avatar chip' and landed on the other standard avatar. Fitted lettering and a 4 px cut are all that stand between this and the default, as the author's first risk admits.
- Scattered motion (skill: one orchestrated moment). Two staged moments (table rises at the start, sinks at agreement), plus four posture offsets on every figure, plus ring and halo.
- Pale sage after naming sage as the wellness default: table, hover and border sit at hue 129 to 142, the same grey-green the other two use. The 'green cloth' is 1.14:1 against the page (1.26 dark) and 0.78 units from the room's sidebar grey, so it will not be seen as cloth.
- Checked and clear: clay accent (no accent hue at all; nearest is dark-theme seat 4 #DE6365 at 5.3 units from #D97757, one seat of seven), near-black with acid accent, gradient washes, ALL-CAPS, eyebrows, monospace labels, numbered markers, arrows, single-word headline accents.

### Keep
- The name is the face: lettering fitted to the head with Archivo's width axis, long names condensed rather than shrunk. The one idea here no other direction has.
- 'Colour belongs to the council': every control is ink, so any hue on screen is a seat.
- One cut per seat, fixed to the seat and not the model, as the second signal when one model fills two seats.
- The best measured seat separation of the three (smallest pair 8.2 light and 11.4 dark under simulation, reproduced), a seat order chosen from all 5,040, and lightness steps between neighbours.
- Button naming that follows the skill exactly: 'Ask', then 'Add to next round', then the notice 'Added to round 3'.
- The table drawn over the lowest 6 px of each body, so flat shapes read as seated behind it.
- Seats fill in from dashed to solid in the real load order, not a staged stagger; dashed is reserved for 'not ready'.
- The idea of a test that proves Chat View has no colour (equal red, green and blue).

## judge:function
Scores (1-5): distinctiveness 3, calm and readable 4, function 4, feasibility 4

### Must fix
- The top bar shows the seated council as five 14 px coloured figures beside the words '5 seated'. Colour is the only signal there, against the brief and against the direction's own rule (below a 24 px body the name is written beside the figure). Add the short names.
- The bubble width rule contradicts itself: 200 px minimum, but never wider than the gap to the neighbour. The gap is about 150 px at seven seats and 173 px at six on the largest table, and 146 px at five seats on the smallest. Lower the floor to about 150 px and state the tier rule.
- Chat View is locked to the pinned stage (radius + 190, 510 px at most). A 100-word message in a 220 px column is about 20 lines, 460 px. Let Chat View take the full conversation height.
- Stage height radius + 190 is about 45 px short when one bubble rises above another (figure top at radius + 100, each bubble row about 70).
- The speaker ring is the same colour as the head it surrounds, so at a glance the head only looks slightly larger. The 4 px lean and 22% halo are below what anyone notices. Check at five and seven seats in the study; the fallback is an ink ring.
- Posture states (head turns 3 px toward the model addressed, drops 3 px when reading files) need two back-end signals nobody has confirmed and are too small to see. Leave them out of the Phase 1 mocks.
- Name fitting (11 to 17 px, width 72 to 110%) needs real text measurement in a browser after the fonts load. The unit-test runner (jsdom) cannot measure text, and the direction's own width figures are estimates. Plan a Playwright check, and consider one size per council so heads do not look uneven.
- Light theme: indigo (L* 19) and claret (L* 22) are near-black, and claret is only 5.2 from the text ink under protanopia. Check them at the 14 and 22 px sizes. Dark theme: teal and ochre (L* 87) against claret and violet (L* 57 to 59) will make two seats shout.
- Chat View values were changed from the PDF's (#161616, #EDEDED, #101010) for no functional gain. Keep the equal-red-green-blue test and the PDF's values.
- Two motion set-pieces (the table rises at the start, sinks at agreement) plus posture easing. The skill asks for one. Keep the fold at agreement and make the start a fade.
- Study brief: the font CDN fallback breaks 'no network requests', and the main scene shows no vote marks while the other two do. Use the same scenes, frame size and font rule as the others.

### Generic-look tells found
- The figure is the generic 'user' icon (a circle over a half-circle) in one flat colour: coloured avatar tokens or board-game pawns. The brief fixes the shape, and this direction puts the least between it and the default.
- No accent, ink buttons on off-white, a neutral grotesque: the minimalist-app default. Outside Table View nothing says 'council'.
- Body cuts named collar, sash and braces are clothes, a step toward mascots.
- One soft shadow under floating things and five corner sizes (6, 8, 10, 14, round).
- Thin column separators in Chat View, the hairline-rule habit.
- Sans for talk and serif for the answer uses the same two typefaces as 'record'.

### Keep
- The best colour-blind separation of the three: worst pair 8.2 in light and 11.4 in dark, with lightness stepping between neighbours.
- One rule for text and graphics: every seat colour is 4.5:1 or better against the page (4.75 to 12.64 computed), so the name is the page showing through. Names at 13 to 17 px are the largest of the three.
- Vote badge fully specified: solid ink disc with a page-colour check, page-filled hollow disc with an ink cross, 2 px gap. It works on every seat colour as written.
- Focus as an ink rounded rectangle round the whole figure, distinct from the round speaker ring.
- 'Every Chat View value has equal red, green and blue', a rule a test can check, and the same figure as an ink outline at the column heads.
- Table radius derived from both the width and the height of the stage.
- A body cut fixed to the seat, so one model in two seats still gives two looks.
- 'A check means in the largest group', and bubbles that state the claim itself.
- Button naming that follows through: 'Ask', then 'Add to next round', then the notice 'Added to round 3'.
- Seats that fill in from a dashed outline as each model reports ready, in the real load order.

