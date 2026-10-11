# Judges' findings for direction A

## judge:distinct
Scores (1-5): distinctiveness 4, calm and readable 4, function 4, feasibility 5

### Must fix
- Vote marks vanish on most heads as written. 'Solid ink disc, check cut out' and 'hollow disc with ink ring and ink cross' put ink on the head: ink on oxblood is 1.10:1, on slate 1.15, on navy 1.36, on olive 1.70 (dark theme has the same problem with pale ink on pale heads). Fix in one line: draw the check in the on-ink colour and fill the hollow disc with the surface colour, as the other two directions already do.
- Sizes contradict each other. Radius is 34% of a stage capped at 760 px, which is 258 px at most: the stated 340 px maximum cannot be reached, the flat side is 517 px and not 'the same width' as the 760 px message box, and the 'under 260' rule means heads are always 48 px, never 56. Pick one: let the stage reach about 1000 px, or state radius up to 258 and a message box wider than the table.
- Seat numbers must not read as speaking order. Keep the number on the chair body; drop it from the top-bar chips and Chat View column heads, or show it there only when two seats share a name.
- The study shows only the best case (one lamp). Add one small panel with all five lamps lit and five bubbles: 'one light in the room' is the identity, and the back end may run seats together.
- Lamp pools are 110 px across. With seven seats at the 240 px minimum radius neighbouring lamps are 93 px apart (109 px with six), so two neighbours speaking merge into one glow. Size the pool by the seat gap, as bubbles already are.
- The speaker is marked on the table, not on the agent. Put the direction's own fallback in the study as a second panel: an ink ring round the speaking head, with a 3 px page-colour gap (ink touching oxblood or slate is about 1.1:1). Include a seven-seat panel so lamp-to-seat matching is tested at its hardest.
- Light theme is heavy: five of seven seats sit at L* 17 to 32, the table is L* 24 and text ink is L* 14; the slate seat is 4.7 units from the text colour. Show seven seats in light in the study; if it reads as dark blobs round a dark table, lift oxblood, slate and navy to about L* 30 and recompute.
- Correct one figure: the 'usual five seats' smallest distance of 9.2 light and 9.4 dark leaves out tritanopia. I get 7.1 light (navy against petrol) and 8.6 dark.

### Generic-look tells found
- Numbered markers (skill: only when the content is a sequence). Seat numbers appear as '(1)Qwen (2)Llama (3)Phi' chips in the top bar and as numbered black discs heading Chat View columns. Seats are places, not steps, and 1 to 5 reads as speaking order, which the back end has not settled. The number on the chair body is justified (it separates two seats running one model); the numbering in the chrome is the tell.
- Cluster 1, partial and confined to the table: lettering on the walnut is #F5EFE6, 0.59 OKLab units from the skill's cream #F4F1EA (about 2 is just noticeable), next to an amber light and a serif title face. The page is not cream and no colour is within 7 units of #D97757 or #C4694D, so it is a warm island, not the cream look.
- Type skeleton unchanged from the PDF's starting look: a serif for titles only, a sans for everything read, at the PDF's sizes (24, 16, 15, 14, 13, 12). Besley and Atkinson Hyperlegible Next are not default picks; the structure is the starting one.
- Dark theme: page #1C201F is 0.92 units from the PDF's dark #1F1E1B. The dark room is the starting dark with a table in it.
- Cluster 5, inherited from the PDF: Chat View #111111 and #0E0E0E are the 'tinted near-black standing in for black' on the skill's list. Invisible in practice, shared by record; no action.
- Checked and clear: clay accent, cream page, near-black with one acid accent, broadsheet rules, card kit and soft shadows, gradient washes (the lamp pool is the only gradient and it is the speaker mark), ALL-CAPS labels, eyebrows, middle dots, monospace labels (ui-monospace for code blocks only), arrows on buttons, single-word headline accents, more than one staged motion moment.

### Keep
- The lamp on the table as the only light, with the rule that amber appears only where something is live. It is one idea, spent in one place, as the skill asks.
- The walnut half-circle as the only dark mass in a pale, lineless, shadowless room. Nobody's default for an AI chat app.
- 'Show counts, not mechanisms': the clearest handling of the three open back-end questions of any direction.
- Besley with Atkinson Hyperlegible Next, chosen for a stated reason (I, l, 1 and O, 0 in model names at 12 px). The only direction whose fonts are not shared with another.
- Solid and hollow ballots with no colour, so the same marks carry into black-and-white Chat View. Disagreement is never red.
- Radius by material (paper 4, controls 8, furniture round), no shadows, one outline token at 3:1 or better.
- Error copy with real numbers and two next actions ('It needs 9 GB and the GX10 has 6 GB free'), and the empty-chat line 'What should the council settle?'
- The study brief's rule to stop rather than substitute fonts. The other two briefs should copy it.
- Honest limits stated in the spec itself (lamp is 1.51:1 on the page, so it is drawn only on walnut; rim required in dark).

## judge:function
Scores (1-5): distinctiveness 4, calm and readable 4, function 3, feasibility 4

### Must fix
- Vote marks are invisible as written (fixed requirement 3). The cross is ink on a 'hollow' disc and the check is 'cut out' of an ink disc, so both glyphs show the seat colour behind them. Ink against the seat is 1.10:1 (oxblood), 1.15 (slate), 1.36 (navy), 1.70 (olive), 1.82 (petrol) in light, and 1.21 (slate), 1.40 (navy), 1.53 (oxblood) in dark. Fix: give the hollow disc a paper fill and draw the check in the on-ink colour.
- The speaker mark is not on the agent. The lamp sits 30 px inside the rim and the figure 44 px outside it, so the mark is 75 to 95 px from the head it belongs to. Add the ink ring on the speaking head now (the direction's own fallback) so the brief's 'the speaking agent is marked' holds at seven seats.
- The sizes contradict each other. 'Radius is 34% of stage width, 240 to 340' means a stage 706 to 1000 px wide and a flat side 480 to 680 px. The same text says 'stage up to 760' and 'message box 760, the same width as the flat side'. Five seats at radius 340 already need 806 px before any bubble. Pick one set of numbers.
- A fixed 44 px seat offset cannot give the promised 8 px gap. For the top seat the 97 px tall figure ends 4.5 px inside the rim. The offset has to depend on the angle (about 56 px at the top seat). Stage height 'radius + 190' is also about 40 px short of two bubble rows (figure top at radius + 105, each bubble row 64 px).
- Bubble width has no floor. At seven seats on the smallest table the rule gives 110 px, about 34 characters over two lines, not the 'about 150 px' quoted in the risks. Set a floor near 150 px and let bubbles rise in tiers instead.
- Chat View columns (fixed requirement 5). They start at a stage of 1100 px, which the 760 px stage never reaches, and there is no minimum column width: six seats give 163 px and seven give 137 px, about 18 characters a line. Add a rule: columns only when each is 200 px or more, otherwise one thread.
- Chat View is 'set inside the stage', whose height is radius + 190 (530 px at most). Full messages need the whole conversation height. Say so.
- Keyboard (fixed requirement 9) is named but not specified: no tab order for the seats and no keys for Table / Chat. The ink focus ring vanishes on the ink main button and on the slate seat (1.15:1) unless a page-colour gap is specified, and the amber outer band is 1.37 to 1.71:1 in light theme, so it adds nothing there.
- Seat 7 slate (#262E3A) is the ink colour (#1D2427): 1.15:1 apart, OKLab distance 4.7. The seat reads as a button or a vote disc. Move slate lighter or bluer and recompute.
- Five of seven light-theme seats are near-black (L* 17 to 32) and are 1.02 to 1.31:1 against the walnut. They depend entirely on the 8 px page gap and the number. The study must show seven seats in light theme, not only five.
- Study brief: use the same frame size, scenes and font rule as the other two (real fonts embedded, no substitute), so the owner compares directions and not formats.

### Generic-look tells found
- Wood, leather and a desk lamp are boardroom furniture. However flat it is drawn, a brown table with an oak rim sits one step from the 'law firm' costume the direction says it refuses.
- The speaker mark is still a glow (an amber pool of light). It is the stock 'glow on whoever is talking', moved from the head to the table.
- A serif used only for titles over a sans for everything else is the same pattern as the PDF's starting look, with Besley in place of Fraunces.
- Pale grey-green page. All three directions arrived at it, so it is a default of this exercise rather than a choice of this direction (see tooSimilar).
- Seat numbers in coloured discs in three places (top bar, bodies, Chat View column heads). Justified, because seats are real places, but numbered badges are a listed tell and three placements is heavy.

### Keep
- A lamp per seat, any number lit at once: truthful whether seats speak one at a time or together.
- Seat numbers as the identity that survives one model in two seats and a theme change.
- 'Show counts, not mechanisms' and the wording that follows from it. Disagreement is never red; red means a model failed.
- Atkinson Hyperlegible Next for names (I, l, 1, O, 0 cannot be confused) with tabular figures, so no third font.
- Agreement meter as one disc per seat with a notch at the number needed, and the timer kept small on purpose.
- One outline colour at 3:1 or better (3.37 to 4.66 computed), no shadows, no decorative lines.
- Dark theme that is drawn, not flipped, for the table: walnut lifted, oak rim required (6.50:1 against the page where walnut alone is 1.75:1).
- The scene list for the mocks: one speaker, two at once, just after a vote, a failed seat, three and seven seats, the folded card, No consensus.
- Failed-load copy that states the numbers and offers two next steps ('Seat a smaller model', 'Go on with 4 seats').

