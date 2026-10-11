# Look A — review against the skill

Short talk. Exact things exact.

## Generic looks (skill list): absent or deliberate
| Tell | Verdict | Where / why |
|---|---|---|
| 1. Cream page + serif display + terracotta accent | absent | Page `#E9ECE8` cool plaster. No terracotta. Lettering on walnut `#F5EFE6` is near cream: deliberate, on table only (direction). |
| 2. Near-black + one acid accent | absent | Dark page `#1C201F` lifted green-grey. Amber is lamp light on walnut, not accent on controls. |
| 3. Broadsheet: hairlines, zero radius, dense columns | absent | No rules at all. Corners by material: 4, 8, round. |
| 4. Card kit: same rounded cards, same grey shadow, gradient wash | absent, one thing to watch | No shadows. Only gradient = lamp pool (speaker mark). Panel 4 has two paper blocks stacked (card outlined because clickable; answer no outline). Two, not a grid. |
| 5a. ALL-CAPS eyebrow above headings | absent | Sentence case everywhere. |
| 5b. Middle dots between facts | absent | Commas: "Round 2, 3:10 left, 2 of 5 agree". |
| 5c. "WORD — fragment" labels | absent | |
| 5d. Tinted near-black for black | deliberate | Ink `#1D2427` is the direction's identity ink. Not swapped. |
| 5e. Monospace for small data | absent | Tabular figures in text face. |
| 5f. Arrow on buttons | absent | |
| Type: one word in headline accented | absent | |
| Type: all-caps labels | absent | |
| Type: needless label above content | deliberate, small | "You" above question (says who speaks). "Files cited" comes from shared content; set inline, not above. Panel captions: brief asks for them. |
| Numbered markers | deliberate | Seat number on chair body only (seats are places; two seats may run one model). Removed from top bar (correction 6). |
| Big number + small label hero | deliberate, small | Timer 22 px. Meter is main thing. |
| Scattered motion | absent | One Play bubble. Nothing else moves. |
| Serif titles over sans body (same skeleton as PDF) | deliberate | Kept by correction 11. Judges flagged; reported, not changed. |
| Glow on speaker | deliberate | Lamp pool is the bold element. Moved from head to table. |

## Plan revised before build (what changed, why)
1. Send button planned inside message box. Cut. Box + Pause + Stop + switch was four controls in one corner: control panel feel.
2. Top bar chips planned as boxed chips. Now disc + name, no box. Fewer boxes; top bar stays quiet.
3. Selected "Table" planned as ink fill. Now paper key with ink edge on sunken track. "New chat" stays the one ink button.
4. Folded card planned with tiny table picture. Cut: decoration, carried no fact. Card shows small heads with same vote marks instead.

## Revisions to how the study is DRAWN (reason each)
1. **Vote mark place.** Direction: upper right of every head. Drawn: upper OUTER side (left seats upper left, right and middle seats upper right). Reason: in `layouts.seven` seat 1 head top (347.6) sits 1.5 px under seat 2 body (347.3). Mark at upper right of seat 1 lands on seat 2 body.
2. **Gap cut into table at end seats.** Frozen sizes put end-seat body corner 5.8 px INSIDE table (five seats: corner x 320.3, table edge x 314.5 at y 438.7) and 0.6 px outside (seven). Correction 9 wants 8 px page colour between body and rim. Drawn: 8 px page-colour band round every figure, painted over table. Shows as small notch at the two end seats.
3. **Bubble gap.** 12 px measured from speaking ring when seat speaks (= 18 px from head circle), 12 px from head when quiet. Reason: ring is 6 px outside head; bubble tail touched ring.
4. **Bubble width.** Text that fits 232 px stays one line. Longer text: two lines, box as narrow as words allow. Reason: first shot had 280 px one-line bubbles next to two-line ones; ragged.
5. **Side bubbles pushed out** (five seats: right edge 448, left edge 592; was 466 and 574). Reason: sat 12 px from speaker's ring; read as speaker's bubble.
6. **Top bubble rises** 8 px above neighbours' bubbles (brief rule). Makes an arch, as in owner's drawing.
7. **Speaking ring** 3 px ink, 3 px page gap (correction 3), plus 2 px page colour between ring and own body, because head-to-body gap is only 2 px.
8. **Small parts scaled with frozen head sizes** (direction wrote them for 56 px head): name 15 px in 72 px head, 13 px in 64 px head (was 12); seat number 14 and 13 (was 13); vote mark 20 px disc (was 18).
9. **Lamp pool** diameter 0.8 x distance to next lamp (correction 5): 94.4 px at five seats, 72.3 px at seven (was fixed 110).
10. **Message box** 760 wide, table flat side 442 (correction 1 allows). Table rests on box top edge.
11. **Top bar name** "Council of 7" on panel 3 (shared content says "Council of 5"; seven are seated).

## Colour test (corrections 7 and 8). Tool: `colour-check.html` (L*, contrast, Machado 2009, OKLab x100)
- Check of tool: reproduces direction's own figures (light 9.8 / 8.9 / 9.0 / 6.9; dark 7.9 / 6.8 / 6.6 / 7.1).
- **Correction 7, done.** Slate light `#262E3A` -> `#485D7E`. L* 18.7 -> 39.1. Name on it 6.38:1. Figure vs page 5.61:1. Vs ink 2.36:1 (was 1.15). OKLab distance to ink 22.6 (was 4.7).
  Cost: closest seat pair at seven seats now 5.5 (petrol vs slate, protanopia). As written 6.9, but slate was ink.
- **Correction 8, tested, NOT applied. Needs lead / owner.** Panel 3 light looked at: left three seats (olive, navy, oxblood) heavy; oxblood close to walnut in tone. Names readable, seats distinct in normal vision. Not merged blobs. Lift computed anyway:

| Set | Navy | Oxblood | Worst pair, five seats | Worst pair, seven seats |
|---|---|---|---|---|
| Study (as written) | `#1E3572` L* 23.8 | `#580D03` L* 17.3 | 7.1 (navy-petrol, tritanopia) | 5.5 |
| `#seats27` | `#283D75` L* 26.9 | `#642C33` L* 26.0 | 5.0 (navy-petrol, tritanopia); 5.6 (olive-oxblood, deuteranopia) | 5.0 |
| `#seats30` | `#294385` L* 29.9 | `#723339` L* 30.0 | 2.6 (navy-petrol, tritanopia); 4.7 (olive-oxblood, deuteranopia) | 2.6 |

  Why it falls: olive (L* 30.3) and petrol (L* 32.1) already sit at L* 30. Lift puts five seats at one lightness; then only hue separates them, and colour-vision loss removes hue. Oxblood kept at its own hue (32) and lifted to L* 28 (`#75291C`): worst pair 1.1. That is why the lifted oxblood above is turned toward wine (hue 14 to 16). About 2 = just noticeable.
  See both lifts: open `study.html#seats27` or `study.html#seats30` (light theme). Shots: `shots/zoom-p3-written-light@1x.png`, `shots/zoom-p3-seats27-light@1x.png`, `shots/zoom-p3-seats30-light@1x.png`.
- Dark slate `#D3D7E1` vs dark ink `#E9ECE7`: 1.21:1. Same fault as light slate. Correction names only the light value. Not changed. Reported.
