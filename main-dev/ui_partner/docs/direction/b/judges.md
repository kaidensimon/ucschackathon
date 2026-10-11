# Judges' findings for direction B

## judge:distinct
Scores (1-5): distinctiveness 4, calm and readable 3, function 4, feasibility 3

### Must fix
- Too many devices for 'boldness in one place'. Smallest test: in the study show the Table View twice, hatches on and hatches off (the direction's own look switch), so the owner sees whether the tally carries the look alone. Name, position and ring still identify a seat with hatches off.
- Stage height does not fit the table on a laptop. Radius is tied to width only (up to 280 px) while height is clamp(400, 46vh, 500). By my arithmetic (assuming a 12 px gap between head and slip) the top seat's slip needs about 457 px, and 505 px when it rises a tier; this Mac's screen is 2880 x 1864, about 830 px of visible browser height, which gives a 400 px stage. Tie the radius to the available height as the other two do (radius plus about 200).
- Take violet off Send. Make Send an ink button and keep violet for live things only (focus, the speaker's ring, the caret). That breaks the copy of the PDF's accent map and removes the purple button, and it suits the grounding better: a copying pencil marks, it does not make buttons.
- Seat colour is nearly absent. Head tints are 1.04 to 1.13:1 against the page and almost identical to one another; the colour lives in a 2 px ring that is 3.22:1 (ochre) and 3.35:1 (teal) on the page. The brief says the figure is 'in that seat's colour'. Thicken the ring to 3 px (no recompute needed). Raising the tint would push ochre (3.10 on its tint) below 3:1.
- Reword 'one line on the page' to what is meant (one ruled line in the conversation column), so builders and the token guard do not act on a rule the spec itself breaks.
- The study brief allows fallback fonts (Georgia, Helvetica Neue). A study in fallback fonts is not this direction. Use the room rule: embed the real files or stop.
- Bubble text is 14 px italic serif at weight 450, the hardest to read of the three, and thin in dark by the author's own risk list. Show a slip upright and in italic side by side in the dark study; keep italic for the dissent line either way.
- Shares both font families with voices. The fix belongs on the voices side (see there); no change here.

### Generic-look tells found
- Cluster 3 (broadsheet), partial: a ruled margin, 3 px near-square corners on every slip and sheet, a hairline 'rule' token at 1.54:1, times set in a margin column, and a serif reading face. It is a ledger rather than a newspaper and the columns are not dense, but it is the nearest of the three to the editorial default.
- Accent logic copied from the PDF with the hue swapped. The PDF's clay was for 'Send button, focus ring, the speaking glow, the active switch'; violet here is for Send, focus ring, the speaker's ring and the active switch, plus links and the caret. A white label on a saturated purple Send button is also the stock AI-product button, even drawn flat. The violet itself is not the stock one (16 to 20 units from #7C3AED and #8B5CF6).
- Serif reading text on a pale tinted page inside a sidebar chat frame sits beside Claude's own app, the same kind of association the skill warns about for the clay accent. Not one of the five clusters; the author kept it knowingly.
- Boldness in more than one place (skill: one). The tally is named as the bold element, but six hatched bodies, a margin column with its line, leader-line slips and a violet accent all compete with it.
- The principle 'one line on the page' is not true of the spec, which also draws slip edges, the answer sheet edge, leader lines, the table edge, seat rings, hatch lines, tally underlines and the Chat View divider. Lines are this direction's main material.
- Cluster 5, inherited from the PDF: #111111 and #0E0E0E in Chat View. No action.
- One looping motion (the blinking caret). Tied to text arriving, so acceptable, but it is the only loop in any of the three.
- Checked and clear: cream, clay (nearest is seat 6 rose #B25C69 at 6.7 units from #C4694D, a 2 px ring only), near-black with acid accent, card kit and shadows (overlays only), gradients, ALL-CAPS, eyebrows and labels above content (meta goes to the margin), middle dots, monospace, numbered markers (seat numerals were removed), arrows.

### Keep
- The tally: one stroke per seat, an underline under the number needed, a second rule at agreement. The most original meter of the three, it shows a count only, and it works at four sizes and in black.
- Meta in a margin column, so nothing needs a label above it. The cleanest answer to the skill's 'no unnecessary labels above content'.
- Two voices never swapped: Literata for what is recorded, Archivo for the form. Roles are the reverse of the PDF's, which is a real typographic position.
- 'Hollow, then filled' for provisional against settled, and ink (not red) for a dissenting cross.
- Third-person note wording ('Argues the break clause is the real risk.'), true whichever model ends up writing summaries.
- The widest state coverage: loading seat, failed seat, paused, time ran out (underline never ruled off), council-file review placeholder, two seats speaking in the wireframe.
- Chat View honesty: columns only when each can be 200 px, otherwise one thread; simultaneous messages share a row.
- Grounding in real objects (steno pad green, registrar's ink, copying pencil, the docket), and use of the owner's legal background as the skill's memory hint.
- Seat order that puts the most separable colours first, and the look switches proposed for the gate.

## judge:function
Scores (1-5): distinctiveness 4, calm and readable 3, function 3, feasibility 3

### Must fix
- Focus ring and speaker ring are the same mark (fixed requirements 3 and 9). Both are a violet ring round the head: focus 2 px with a 2 px gap, speaking 2.5 px with a 5 px gap. Tabbing to a seat looks like that seat is speaking. Change one, for example focus as an ink rounded rectangle round the whole figure.
- Violet is not clear of the seat colours for red-green colour blindness. Speaker violet against the Blue seat's ring is 3.6 under deuteranopia in light and 1.5 under protanopia in dark (about 2 is just noticeable). The second ring is a shape, so it survives, but the claim 'none near the violet accent' does not hold.
- Seat colour is nearly absent (fixed requirement 3, 'in that seat's colour'). Head tints are 1.04 to 1.13:1 from the page in light and any two tints are 0.5 to 1.3 apart, below noticeable. Colour lives only in a 2 px ring and 1.5 px hatch lines, where ochre and teal are 3.10 and 3.21:1 on their tints and teal against rose is 6.3 under deuteranopia. Raise the tint (20 to 30%) or thicken the ring to 3 px, then recompute.
- Chat View columns never appear with the usual council (fixed requirement 5). Five seats need a 1208 px sheet (5 x 200 + 4 x 32 + 80 padding); the stage stops at 1040. Only three and four seats ever get columns. Let the sheet use the full conversation width, including the reserved right third.
- Stage height does not follow the table. Radius comes from stage width only (280 at a 1040 stage), which needs 452 px for the top figure and one slip and 500 px when a slip rises. The stage is clamp(400, 46vh, 500), so 400 to 414 px in a laptop window 800 to 900 px tall, and the top seat's slip is cut off. Tie the radius to height as well.
- Hatches are unproven at ordinary screen sharpness. Lines of 1.5 px at 6 px pitch on an 80 x 40 body alias on a non-Retina monitor, and the 10 and 12 px chips hold only two lines, so dots, lines and grid look alike. The study must render at device scale 1 and 2, with a tighter pitch for chips.
- Note slips are the most-glanced text in Table View and are set in the hardest style to read, 14 px italic serif. The slip edge is 1.73:1 on its own fill and the fill is 1.12:1 from the page, so a slip has no visible boundary. Use upright text and the outline colour for the edge, or prove it in dark theme.
- Chat View 'sits where the table sat', inside a stage 400 to 500 px tall. Full messages need the whole conversation height.
- Single-key shortcuts (T, C, 1 to 7, ?) must be ignored while the cursor is in the message box. State it.
- Study brief: the fallback to Georgia and Helvetica Neue would not show this direction, which depends on Archivo's width axis and Literata's optical sizes. Require the real fonts, and use the same frame size and scenes as the other two.

### Generic-look tells found
- Paper, ledger and 'minutes' sit next to the broadsheet look the skill lists: a margin rule, 3 px corners and serif text, even with the other rules removed.
- A violet accent on Send, links, focus and the switch. One bright accent on everything pressable is the generic pattern, and violet is the stock 'AI' colour.
- Heads as pale tinted circles with a coloured outline: the avatar chip of every chat app. The 'voices' lead rejected exactly this in its own review.
- Hatch patterns are the chart-legend convention. Seven of them make the table read as a diagram, which leans toward the control-panel feel the brief rules out.
- Italic serif for side notes, the 'literary aside' treatment.
- A blinking caret is the one loop in the app; the other two directions have none.

### Keep
- The tally: one stroke per seat, an underline under the number needed, a second rule at agreement. It shows a count only, so it stays true however matching is decided, and it works in black in Chat View.
- The margin column for who, when and the vote, leaving the text column clean.
- Literata 17/28 for answers: the best long-reading setting of the three.
- 'Hollow, then filled' for provisional against settled.
- Third-person note wording, true whichever model ends up writing summaries.
- A dark theme with its own hue (blue-slate with paper-coloured ink), the most deliberately drawn dark theme of the three. Every ring is 3.46:1 or better on its tint.
- Seat order that puts the most separable colours first (worst pair among the first five: 7.9 light, 10.5 dark under simulation).
- The fullest keyboard specification of the three: T and C, 1 to 7, ?, tab order round the table.
- Columns only when each is 200 px or more, and messages sent at the same moment share a row.
- The extra gate checks: no two slips overlap at 3, 5 and 7 seats; fonts actually loaded; token guard bans gradients and uppercase.

