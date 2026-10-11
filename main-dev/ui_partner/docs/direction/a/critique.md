# Look A — critique, written from the screenshots

Shots read: `shots/study-light.png`, `shots/study-dark.png`, `shots/study-light-grey.png`, `shots/study-dark-grey.png`, `shots/study-1x-light@1x.png`, `shots/study-1x-dark@1x.png`, per-panel `shots/crop-*.png`, enlarged `shots/zoom-*.png`. Two rounds of look, fix, look.

## Fixed after looking
1. "Time limit 5:00" broke onto three lines beside file chips. Now one line.
2. Panel 4: small head beside Phi's note was black (colour rule did not reach it). Now seat colour.
3. Panels 1, 2: Gemma's and Llama's bubbles sat 12 px from Qwen's ring; looked like Qwen's. Moved out 18 px each.
4. Panels 1, 2: one-line bubbles 280 px wide beside two-line ones. Long text now two even lines; bubbles similar size.
5. Panel 4: vote marks on small heads 14 px, cross hard to read at ordinary sharpness. Now 16 px.
6. Before first shot, by sums: vote mark at upper right of seat 1 head landed on seat 2 body (seven seats). Marks moved to outer upper side.

## Removed (one accessory)
- **Send button** in message box. Box now plain field. Corner had four controls; now three, quieter.
- Also not built: boxes round top bar names, tiny table picture in folded card.

## Still weak
1. **Light theme heavy.** Olive, navy, oxblood = three dark figures on left of dark table. In `study-light-grey.png` seats and table are near one dark grey; names and numbers carry identity. Oxblood `#580D03` reads close to walnut `#4A3628`. "Table is only dark mass" not true once seats sit down. Lift tested: costs colour-vision distance (see review.md). Not applied.
2. **Seven seats crowd.** Seat 1 head 1.5 px from seat 2 body; same on right. Frozen sizes. Two dark shapes nearly touch.
3. **Notch in table** at the two end seats (page-colour gap cut into walnut and rim). Clean, but owner may read it as flaw. Cause: frozen sizes put body corner inside table.
4. **Lamp far from head.** Top seat: lamp about 160 px below head. Ring on head does the work at a glance; lamp is mood. Fine with one speaker (panel 1). With five (panel 2) five rings + five pools: busy, least calm panel.
5. **Fading bubble** at half strength: text about 3:1. Passing state, fixed by brief, but pale in light theme.
6. **Amber focus band** weak in light (1.51:1 on page). Ink ring does the work. Band earns keep only in dark.
7. **Besley hardly seen.** App name 17 px, card heading 20 px. Title face is small part of what owner looks at all day.
8. **Panel 4 has no table, no lamp.** Look's identity absent in the state owner reads most. What remains: plaster, paper, ink, seat colours, Besley heading.
9. **Empty band** between question and top bubble (about 60 px). From frozen stage height. Calm, but table sits low.
10. **Dark slate** `#D3D7E1` near dark ink `#E9ECE7` (1.21:1). Seat 7 in dark reads close to text colour.
11. **Vote marks flip between themes.** Light: check = dark solid disc, cross = pale disc. Dark: check = pale solid disc, cross = dark disc with pale edge. Shape (check, cross) holds; "dark = agrees" does not. Follows correction 2 as written.

## Good, keep
- Dark theme: walnut lifted, oak rim clear, lamps glow. Stronger of the two themes.
- One speaker (panel 1): ring + lit lamp + pool read at once. Quiet lamps as hollow rings.
- Table on message box: owner sits at flat side.
- Vote marks clear on every seat colour, both themes, and in grey.
- Bubbles: none overlap; page checks itself on load (console error, so `look:file` exit 1, if a bubble overlaps or passes 2 lines).

## Fix round
Small fixes after review. No colour, font or wording change. Shots re-made: `shots/study-*.png`, `shots/study-1x-*@1x.png`, `shots/crop-*.png`, `shots/zoom-p1-*.png`, `shots/zoom-p3-*.png`.

1. **Table smaller** (shared file). Radius five seats 221 -> 204, seven seats 233 -> 224. End-seat body corner now 11.6 px (five) and 9.6 px (seven) clear of table. No body touches table.
2. **Notch gone.** Page-colour band painted over table removed; table is plain half-circle again, rim unbroken. 8 px rule kept as a check: page logs console error (so `look:file` exit 1) if any body is under 8 px from table. See `shots/zoom-p1-left-light@1x.png`, `shots/zoom-p3-end-seat-light@1x.png`. "Still weak" point 3 above no longer true.
3. **Table flat edge shows whole.** Message box moved down 8 px (top y 520 -> 528). 8 px of page between flat edge and box, no overlap. Pause / Stop / switch row moved down 8 px too (702 -> 710) so its 14 px distance under box holds; 36 px left under row. Page checks the 8 px on load.
4. **Top bar** reads each panel's own `topBarLeft`. Panel 3: "Council of 7". Panels 1, 2, 4: "Council of 5".
5. **Hermes bubble, panel 3.** Left edge x 682 -> 716. Was 10 px from Gemma's head, at head height: looked like Gemma's. Now 44 px from Gemma's head, 41 px from her vote mark; whole bubble sits over Hermes and out to the right. Tail over Hermes head centre, 21 px from bubble's left end. 12 px above Hermes head, 9 px above his vote mark. Check tightened: bubble must be 4 px clear of every figure (head, body, ring, vote mark), all panels. See `shots/zoom-p3-right-light@1x.png`, `shots/crop-p3-seven-after-vote-dark@1x.png`.

Kept: `#seats27` / `#seats30` comparison (`shots/zoom-p3-seats27-light@1x.png`, `shots/zoom-p3-seats30-light@1x.png`), Play bubble, focus on Granite, all else.

Left stale, not re-made: `shots/play-check-*.png`, `shots/webkit-check-light@1x.png` (old table size). Old text now out of date: review.md points 2 and 10, plan.md layout sentence, direction.md "flat side rests on the message box" (table now 8 px above box, by reviewer's rule).

Cost of fix 3: "Table on message box" (Good, keep, above) weaker. Table now floats 8 px over box instead of resting on it. Question for owner if he wants the docked look back.
