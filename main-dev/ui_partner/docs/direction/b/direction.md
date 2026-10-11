# Direction B: Fair Copy

> The debate is written down in front of you like minutes being taken, and the agreed answer arrives as the clean final copy.

This is the design lead's written direction (frontend-design skill process). Read `corrections.md` beside it: corrections win.

## Grounding
Subject: how a deliberation is put on record. Every choice below comes from that world, not from "AI app".

| In the world of the record | What it becomes here |
|---|---|
| Rough minutes, then the fair copy (the clean final version written out afterwards) | The debate is the rough state: tinted pad, hollow marks, short notes. The answer is the fair copy: the one white sheet, inked and ruled off. |
| The stenographer's pad: green-tinted "eye-ease" paper, used because long sessions on it tire the eye less | Page colour #E5ECE4. Calm comes from the subject, not from cream. |
| Registrar's blue-black ink, the ink of official registers | Text colour #1A2435. Dark theme inverts the pair: carbon-paper blue-black page, paper-coloured ink. |
| The copying pencil: indelible, violet, used to mark ballots and duplicate records | The single accent #67298C, reserved for what is live or pressable. |
| Tally marks on a tally sheet | The agreement meter: one stroke per seat. |
| The double rule a bookkeeper draws under a final total; the auditor's green tick | "Agreed": the tally is ruled off with a second line and turns green. |
| Side-notes in statutes and reports: a few words beside each section saying what it does | The bubbles: small italic note slips with a leader line, written as a minute-taker's note. |
| The dissenting opinion printed after a judgment | The one-line dissent notes under the answer. |
| The docket: the one-line label on the outside of a folded record | The folded debate card above the answer. |
| Times printed in the margin of a parliamentary record | Chat View times, and all "who and when", live in a margin column. |
| A printed form versus what is entered on it | Two typefaces with a strict split: Archivo for the form, Literata for the record. |
| Engravers' hatching, the print convention for showing different colours in black ink | Each seat has a hatch as well as a colour, so seats survive colour-blindness and the black-and-white Chat View. |

Hint used: the owner's background is legal (Founder Context in /Users/lucasta/.claude/CLAUDE.md), so dissents, dockets and ruled-off totals are native conventions for him rather than decoration.

How the PDF was read: the Read tool could not render PDF pages on this Mac (pdftoppm is missing), so I extracted the text with macOS PDFKit and read the labels and their positions inside the wireframes on pages 4, 6, 7, 8 and 13 with in-memory text recognition. I did not see the wireframes as pictures.

## Palette

| Token | Light | Dark | Role |
|---|---|---|---|
| page | `#E5ECE4` | `#141A23` | IDENTITY 1 of 5. App background and the debate stage. Light: steno-pad green-grey. Dark: carbon-paper blue-black (a chosen slate, not a fake black). |
| surface | `#F5F8F4` | `#1D232E` | IDENTITY 2 of 5. Anything written and settled: the answer sheet, note slips, the table top, message box, status pill. |
| sunk | `#DBE2D9` | `#272E3A` | Sidebar block, hover and pressed rows. Derived from page. |
| rule | `#B5C2B7` | `#3A404B` | Decorative only: the one margin line and slip edges. About 1.5:1 by design; nothing depends on seeing it. |
| outline | `#717E76` | `#78818C` | Edges that must be seen: message box, table edge, hollow tally strokes, leader lines, chips. 3:1 or better everywhere it is used. |
| ink | `#1A2435` | `#E2E8E1` | IDENTITY 3 of 5. All primary text, names in heads, filled tally strokes, check and cross marks. Light: registrar's blue-black. Dark: the light theme's paper colour. |
| muted | `#515963` | `#9AA8A8` | Margin column meta, times, placeholders, helper lines. |
| mark | `#67298C` | `#CDA4EC` | IDENTITY 4 of 5. The accent: copying-pencil violet. Only for what is live or pressable: Send, focus ring, active side of the Table / Chat switch, the speaker's ring, links, the writing caret. Always flat: no gradient, no glow. |
| mark-wash | `#ECDFF7` | `#3F2C4C` | Fill of the active switch segment and selected rows. |
| on-mark | `#FFFFFF` | `#141A23` | Label on the Send button. |
| agreed | `#136239` | `#7BCC98` | IDENTITY 5 of 5. Auditor's green. Only the ruled-off tally and the word Agreed. Dark enough to be used as text. |
| error | `#A12628` | `#F28881` | A model that failed to load or answer. Never used for a dissenting vote. |
| cv-paper | `#FFFFFF` | `#0E0E0E` | Chat View sheet. PDF values kept. |
| cv-ink | `#111111` | `#F2F2F2` | Chat View text, its tally strokes, hatch chips and the focus ring inside the sheet. PDF values kept. |
| cv-grey | `#5C5C5C` | `#A3A3A3` | Chat View names and times. |
| cv-outline | `#767676` | `#8A8A8A` | Chat View citation chip outlines. |
| cv-rule | `#D4D4D4` | `#333333` | Chat View vote divider line and sheet edge. Decorative. |

## Seats
Four signals per seat, colour last. (1) Position: seats are numbered left to right and never move. (2) Name: the short name sits in the head in ink, not in the seat colour. (3) Hatch: the half-circle body carries one of seven patterns (plain, vertical lines, dots, rising diagonal, horizontal lines, falling diagonal, grid) drawn in 1.5 px lines at 6 px pitch. (4) Colour: used only for the 2 px ring and the hatch lines, never as a solid fill and nowhere outside the figures. Head and body fill is a pale tint: the seat colour mixed 14% (light) or 16% (dark) into surface; the tint values are in each row. How the colours were chosen: a search over seven hue families (none near the violet accent, the agreed green or the error red) that maximised the smallest distance between any two seats under simulated protanopia, deuteranopia and tritanopia (Machado 2009 matrices, distance in OKLab), with every ring held at 3:1 or better against the page and against its own tint. Measured smallest distance between any two of the seven: light theme normal 0.106, protan 0.064, deutan 0.063, tritan 0.062; dark theme normal 0.092, protan 0.085, deutan 0.063, tritan 0.058. My first hand-picked set measured 0.024 at worst, so separation is about 2.5 times better, but colour alone will still not let every viewer tell seven seats apart; that is the job of the hatch, the name and the position. The seat order puts the most separable colours first, so councils of 3, 4 and 5 use the strongest subset (weakest pair among the first five: 0.064 under any simulation, 0.106 in normal vision). Colour belongs to the seat, not the model, so one model filling two seats still gets two looks. In Chat View the hatch appears as a 12 px black chip beside each column heading: no colour, same seat.

| Seat | Light | Dark |
|---|---|---|
| Seat 1: Blue, plain body (no hatch). Head tint light #D3E2E7, dark #2C394C | `#015B94` | `#7CAAE9` |
| Seat 2: Ochre, vertical lines. Head tint light #E9E7D2, dark #3F3E3A | `#A27C01` | `#F1CA78` |
| Seat 3: Sepia, dots. Head tint light #DEDDD7, dark #323237 | `#513A26` | `#9F7F64` |
| Seat 4: Teal, rising diagonal lines. Head tint light #D8E9E5, dark #2E414B | `#238C8C` | `#89DFE3` |
| Seat 5: Olive, horizontal lines. Head tint light #E2E4D8, dark #343936 | `#6C6B2A` | `#AAAE62` |
| Seat 6: Rose, falling diagonal lines. Head tint light #ECE2E1, dark #3D3944 | `#B25C69` | `#E6ABB8` |
| Seat 7: Graphite, grid. Head tint light #DFE2DF, dark #303640 | `#555A60` | `#959AA0` |

## Typefaces

| Role | Family | Package | Why |
|---|---|---|---|
| Family 1, the record: everything you read (your questions, answers, model messages, note slips, titles) | Literata, variable, with an optical-size axis and a true italic. CSS family name 'Literata Variable' | `@fontsource-variable/literata` 5.3.0 (OFL-1.1) | Drawn for long reading on screens, so it stays sturdy at 14 to 17 px in both themes, and its optical-size axis gives finer shapes at title size without a second display face. The italic is distinct enough to carry the note slips and dissent lines on its own. Checked today: the package exists at 5.3.0 and ships opsz.css and opsz-italic.css (weights 200 to 900); the bundled Latin file has lining figures by default and a tabular-figure feature. Imports: '@fontsource-variable/literata/opsz.css' and '@fontsource-variable/literata/opsz-italic.css'. Fallback: Iowan Old Style, Charter, Georgia, serif. This inverts the PDF: there the serif was for titles and a sans for reading. |
| Family 2, the form: everything you operate or count (labels, buttons, names in heads, times, timer, votes) | Archivo, variable, with a width axis from 62% to 125%. CSS family name 'Archivo Variable' | `@fontsource-variable/archivo` 5.3.0 (OFL-1.1) | A plain, sturdy grotesque of the kind printed forms and ballot papers are set in, clearly unlike Literata. The width axis does real work: a model name is fitted into its head by narrowing the letters, not by shrinking them. Checked today: the package exists at 5.3.0 and ships wdth.css (weights 100 to 900, widths 62 to 125); the bundled Latin file has a tabular-figure feature, so the timer does not jitter. Import: '@fontsource-variable/archivo/wdth.css' (no italic needed). Fallback: Helvetica Neue, Arial, system-ui, sans-serif. |
| Scale: page, sheet and dialog titles | Literata 26 px, line height 32 px, weight 550, letter-spacing -0.01em, sentence case, optical size automatic | `@fontsource-variable/literata` 5.3.0 (OFL-1.1) | One title size. The answer heading ('Agreed, 4 of 5') is 22 px, line height 28 px, weight 600. |
| Scale: chat text and answers | Literata 17 px, line height 28 px (1.65), weight 400; bold 650 | `@fontsource-variable/literata` 5.3.0 (OFL-1.1) | Serif body gets one more pixel and more leading than the PDF's 16 px / 1.6 sans. Measure capped at 70 characters; measured 8.4 px per character, so the text column is about 590 px. |
| Scale: bubble text (note slips) | Literata Italic 14 px, line height 20 px, weight 450, two lines then an ellipsis | `@fontsource-variable/literata` 5.3.0 (OFL-1.1) | Measured 6.1 px per character, so a 220 px slip holds about 60 characters over two lines. |
| Scale: names in heads | Archivo 12 px, line height 12 px, weight 600, width stepped 100, then 88, then 75 until the name is 46 px or less | `@fontsource-variable/archivo` 5.3.0 (OFL-1.1) | Measured at width 100: Phi 18 px, Qwen 32, Llama 34, Mistral 38, Gemma 44, DeepSeek 57 (about 46 at width 75). So every name of eight characters or fewer fits a 60 px head at 12 px. Full name in a tooltip on hover and focus. |
| Scale: Chat View messages | Literata 15 px, line height 24 px, weight 400. Sender line: Archivo 13 px, line height 16 px, weight 600 | `@fontsource-variable/literata` 5.3.0 (OFL-1.1) | PDF size kept. Measured 7.4 px per character: a 200 px column holds about 27 characters, which sets the rule for when columns are allowed. |
| Scale: labels and buttons | Archivo 14 px, line height 20 px, weight 500, width 100, sentence case, never uppercase | `@fontsource-variable/archivo` 5.3.0 (OFL-1.1) | PDF size and weight kept. |
| Scale: small meta (times, rounds, the margin column) | Archivo 12 px, line height 16 px, weight 450, muted colour, tabular figures | `@fontsource-variable/archivo` 5.3.0 (OFL-1.1) | PDF size kept. |
| Scale: numbers (timer, votes, counts) | Archivo 14 px, line height 20 px, weight 500, font-variant-numeric: tabular-nums. Timer on the table top: 20 px, line height 24 px, weight 500 | `@fontsource-variable/archivo` 5.3.0 (OFL-1.1) | No third family and no monospace: the form face has tabular figures. This replaces JetBrains Mono. |

## Layout
## Concept

The conversation is a page on a pad. A left margin column holds who, when and the vote. A text column holds only what was said. The stage is a full-width plate set into that page. The right third stays empty so an agent's sheet can dock there without covering the text.

## The fixed frame, and what happens inside it

| Part | Spec |
|---|---|
| Top bar | 48 px, page tone, no line under it. Left: the seated council as names in seat order (Archivo 13/500), each with its 10 px hatch chip. Right: status pill (surface, 1 px outline, fully round) holding a mini tally, then Round 2, 3:10 left, 3 of 5 agree, separated by 12 px gaps, not dots. |
| Sidebar | 232 px block in `sunk`, no border. New chat (outline button), History, Library, Models, Settings. Foot: theme switch, Shortcuts. |
| Conversation | Starts 56 px from the sidebar. Margin column 136 px, meta right-aligned in muted Archivo 12. One vertical 1 px `rule` line at the margin's right edge: the only line on the page. 24 px gap, then the text column, at most 70 characters (about 590 px). |
| Alignment | Left-aligned, ragged right. Never justified. Nothing is centred except the stack on the table top, because the table is symmetrical. |
| Your question | Plain text on the page, no bubble. "You" and the time sit in the margin. File chips under it. |
| Stage | Opens between the question and the message box. No box and no shadow: the margin line stops and the figures stand on the page tone. Max width 1040 px, height clamp(400 px, 46vh, 500 px). |
| Message box | Surface, 1 px `outline`, radius 8. Stays live during a debate, with the helper line "The council reads this at the start of the next round." |
| Table / Chat switch | Bottom right of the conversation, on the message-box row. Shown while the council works and when a folded debate is opened. |
| Folded debate | A one-line docket slip above the answer: "Debate record: 3 rounds, 4 min 12 s" and the button Show the debate. |
| Answer | The only sheet in the conversation (surface, radius 3, 1 px `rule` edge), spanning margin and text column. The tally sits in the sheet's margin beside the heading. |
| Agent sheet | Docks in the right third at 380 px when the window is 1280 px or wider; overlays below that. |
| Narrow window (under 900 px) | The margin column folds into one meta line above each entry; notes drop to one tier. The phone layout proper is Phase 7. |
| Shape | 8 px grid. Radius by role: 3 for slips and sheets, 8 for controls, fully round for the pill and heads. No shadows except on overlays (0 8px 28px at 16% ink). No gradients anywhere. |
| Keyboard | Every figure is a button (Enter opens that agent's sheet); tab order runs left to right round the table. Focus ring: 2 px `mark` with a 2 px gap; inside Chat View it is 2 px `cv-ink`. T and C switch views, 1 to 7 open a seat, ? opens the shortcuts sheet. |

## Wireframe 1: main screen during a debate

```
+-----------+---------------------------------------------------------------------------------
| GX10      |  Phi  Llama  Qwen  Gemma  Mistral        ( ///:: Round 2   3:10 left   3 of 5 agree )
| Council   |
|           |          margin |  text column, max 70 characters      :  right third stays
| New chat  |          136 px |  left-aligned, ragged right          :  empty; an agent's
|           |                 |                                      :  sheet docks here
| History   |       You 14:02 |  Should we renew the Harbour Street  :
| Library   |                 |  lease for three years or five?      :
| Models    |                 |  [lease-2024.pdf, 12 p] [rent.xlsx]  :
| Settings  |                 |
|           |   (the margin line stops; the stage is a full-width plate with no box)
|           |
|           |            Table View (wireframe 2)   or   the white Chat View sheet
|           |
|           |
| Dark      |   [ Message the council                          (clip)   Send ]    [ Table | Chat ]
| Shortcuts |     The council reads this at the start of the next round.
+-----------+---------------------------------------------------------------------------------
```

## Wireframe 2: Table View with five seats

```
                                  .-------------------------.
                                  | Argues the break clause |
                                  | is the real risk.       |
                                  '------------+------------'
              .---------------------.          |          .----------------------.
              | Answers Qwen: the   |       (( o ))       | Cites page 4 of      |
              | cap is 3 percent.   |      (( Qwen ))  v  | lease-2024.pdf.      |
              '----------+----------'       (( o ))       '-----------+----------'
                         |                  [. . . .]                 |
                       ( o )                                       (( o ))
                      (Llama)  v           _.-------._            (( Gemma ))  v
                       ( o )           _.-'           '-._         (( o ))
                      [||||||]       .'                   '.       [//////]
                                    /        Round 2        \
    . . . . . . . . .              /        3:10 left        \
    : older note,   :    ( o )    |                           |       ( o )
    : fading out    :...( Phi )  x|        / / /  o o         |     (Mistral)  x
    . . . . . . . . .    ( o )    |        -------.           |       ( o )
                        [      ]  |   3 of 5 agree, needs 4   |      [======]
                                  +---------------------------+
                                    flat side, toward you

   (( )) second ring = speaking     v check, x cross = last vote     [ ] body with the seat's hatch
   / filled stroke = agrees         o hollow stroke = not yet        underline = how many are needed
```

The drawing shows two seats speaking at once on purpose: nothing in the layout assumes one speaker.

## Checks this direction adds to the previous plan's gate

- No two note slips overlap (compare bounding boxes in Playwright) at 3, 5 and 7 seats.
- Hatches are legible at device scale 1 and 2.
- 'Literata Variable' and 'Archivo Variable' are actually loaded.
- Token guard also bans gradients, `text-transform: uppercase`, and shadows outside overlays.
- The contrast test pins every pair in the contrast list, seat by seat.

## Files this direction turns on (none exist yet; repo will be ~/projects/gx10-council)

- /Users/lucasta/projects/gx10-council/ui/src/styles/tokens.css
- /Users/lucasta/projects/gx10-council/ui/src/styles/fonts.css
- /Users/lucasta/projects/gx10-council/ui/src/components/table/Seat.tsx (figure, rings, seven SVG hatch patterns)
- /Users/lucasta/projects/gx10-council/ui/src/components/table/Tally.tsx (used in the pill, the table top, the vote divider and the answer)
- /Users/lucasta/projects/gx10-council/ui/src/lib/contrast.test.ts

Wireframe pages for the builders: in the 16-page PDF the pictures are on pages 4 (main screen), 6 (Table View), 7 (Chat View), 8 (learning flow) and 13 (architecture). The previous plan's page numbers (4, 5, 11) were for the 14-page version.

## The one bold element
The tally. Agreement is never a bar, a percentage or a big number: it is one hand-height stroke per seat, slanted 10 degrees, 6 px wide and 40 px tall on the table top. Strokes for seats that agree are filled in ink; the rest are hollow. A single underline runs under exactly as many strokes as are needed (four of five), so the distance to agreement is the hollow strokes standing on the line. When the council agrees, the strokes and the line turn green and a second line is ruled beneath them, the bookkeeper's mark for a final total. That ruling-off is also the app's one orchestrated moment of motion.

The same mark appears at four sizes and nowhere is it decorated: tiny in the status pill, large on the table top, black in Chat View's vote divider, and in the margin beside the answer heading. Everything else in the app stays quiet so this is the thing he remembers.

## Table View
Drawing style: a seating plan drawn on the pad. Line and tone only: no perspective, no wood, no glow, no shadows.

| Element | How it is drawn |
|---|---|
| Table | SVG half-disc, flat side down (toward you). Fill `surface`, 1.5 px `outline` edge. Radius R = clamp(200 px, 27% of stage width, 280 px). |
| Seat positions | N seats at angles 180 - (i - 0.5) x 180 / N degrees, i = 1 to N from the left, on a circle R + 52 px from the midpoint of the flat edge. All figures stay upright. With five seats this gives the PDF's arrangement: low left, upper left, top, upper right, low right. |
| Head | Circle 60 px across. Fill = the seat's tint. 2 px ring in the seat colour. Short name centred in `ink` (Archivo 12/600, narrowed to fit 46 px). Full model name in a tooltip on hover and focus. |
| Body | Half-disc 80 x 40 px under the head, flat side down, 2 px ring in the seat colour, filled with the seat's tint plus its hatch (1.5 px lines at 6 px pitch; dots of 1.25 px radius on a staggered 6 px grid; seat 1 is plain). |
| Speaker mark | A second ring in `mark`, 2.5 px, 74 px across, leaving a 5 px clear gap round the head. It replaces the PDF's glow: it is measurable (7.7:1 light, 8.4:1 dark), does not move, and works for colour-blind viewers because it is a shape. One ring per speaking seat and nothing shared between seats, so the picture is correct whether seats speak one at a time or several at once. |
| Vote marks | A 22 px disc at the head's upper right: fill `surface`, 1.5 px `ink` edge, a 2 px `ink` check or cross inside. Check = backs the leading answer. Cross = backs another answer. Both in ink. They appear on every head together after a vote. Default: they stay until the next vote replaces them, so the heads always add up to the count on the table (owner question 1). Spoken name: "Qwen, backs the leading answer". |
| Loading seat | Dashed 2 px `outline` ring, no tint, name in muted, the word Loading under the body. Fades in over 250 ms when the model is ready. |
| Failed seat | Dashed 2 px `error` ring, an exclamation disc where the vote mark goes, "Did not load" in `error` under the body. |
| Notes (the bubbles) | HTML slips: fill `surface`, 1 px `rule` edge, radius 3, padding 8 x 10 px, at most 220 px wide, Literata italic 14/20, two lines then an ellipsis. No speech tail: a 1 px `outline` leader line runs from the slip to 4 px short of the head. Worded as a minute-taker's note, third person, no quote marks ("Argues the break clause is the real risk."). That wording is truthful whether a separate small model or the agent itself writes it. |
| No overlap | Each seat owns the sector above it. A slip sits radially outward of its head; the two end seats push theirs out to the side; a slip that would come within 8 px of a neighbour rises one tier (48 px). The layout pass measures after the fonts have loaded. |
| Fading (fixed by the brief) | In over 250 ms, hold about 8 s, out over about 1.5 s. A new note from the same seat crossfades in place. With reduced motion, slips appear and disappear. Slip and leader fade together. |
| Table top | A centred stack: "Round 2" (Archivo 12, muted), "3:10 left" (Archivo 20/500, tabular), the tally, then "3 of 5 agree, needs 4" (Archivo 14/500). |
| Tally | See the bold element. Strokes at 14 px pitch; filled = `ink`; hollow = 1.5 px `outline`; underline 2 px `ink` under the number needed; at agreement everything needed turns `agreed` and a second line is ruled 4 px below. It shows a count only, never which answers matched or how closely, so it stays true however matching ends up being decided. No lines are drawn between agreeing seats for the same reason. |
| Paused, time up | Paused: "Paused at 3:10", strokes unchanged. Time up: "Time ran out"; the single underline stays and is never ruled off. |
| Council file review (Phase 6) | Reserved: a slip replaces the table-top stack. Phase 1 shows it only as a placeholder scene. |

Scenes the Phase 1 mocks should include so the look is tested, not assumed: one seat speaking; three speaking at once; just after a vote; the moment of agreement; three seats; seven seats; one failed seat. Each in light and dark.

## Chat View
Chat View is the typescript of the same meeting: a true white sheet (or true black in dark) laid on the tinted page, with no colour inside it at all. Values are the PDF's: #111111 on #FFFFFF, #F2F2F2 on #0E0E0E.

| Element | How it looks |
|---|---|
| Sheet | `cv-paper`, radius 3, 1 px `cv-rule` edge, padding 32 x 40 px. It sits where the table sat. |
| Head line | "Round 2", "3:10 left", "3 of 5 agree, needs 4" with a black mini tally, set with gaps instead of dots. At the right, the filter "All models". |
| One thread (the default) | A 72 px margin with the time into the debate (Archivo 12, tabular, `cv-grey`, right-aligned). Then the sender line "Qwen to all" or "Llama to Qwen" (Archivo 13/600, `cv-grey`), then the full message in Literata 15/24, `cv-ink`, at most 70 characters wide. |
| Citation chips | 1 px `cv-outline`, radius 4, Archivo 12, for example "notes.pdf, p. 4" or "council.md L7". |
| Vote divider | One thin `cv-rule` line across the thread with a black mini tally and "Round 1 vote: 2 of 5 agree, needs 4" on it. This is the PDF's divider and the only line inside the sheet. |
| One column per model | Used only when every column can be at least 200 px (about 27 characters): five seats need a sheet of about 1100 px, seven need about 1550 px. Otherwise it stays one thread. Column heading: the seat's 12 px hatch chip in black, then the name (Archivo 13/600). Columns are separated by 32 px of space, never by lines. Messages keep their time order down the page, and messages sent at the same moment share a row, so the grid is truthful whether seats speak in turn or together. |
| A model still writing | Its text so far followed by a blinking caret; if nothing has arrived yet, the word Writing in `cv-grey`. |
| Following | The view follows the newest message until you scroll up; then a small outlined button "Jump to newest" appears at the foot of the sheet. |
| Focus | 2 px `cv-ink` ring inside the sheet, so even focus stays black and white. |

Why it is still the same app: the same two typefaces with the same split, the same margin holding the time, the same tally strokes (now black), the same hatch chips (now black), the same radii and spacing, and the same violet Table / Chat switch sitting outside the sheet in the frame. Only the colour has been drained, like a photocopy of the same record. Models are told apart by name; the hatch chip only links a column back to a figure at the table.

## Motion
Where motion is used

| Moment | Motion |
|---|---|
| Note slips (fixed by the brief) | Fade in 250 ms, hold about 8 s, fade out about 1.5 s. Same seat: crossfade in place. Reduced motion: appear and disappear. |
| The one orchestrated moment: agreement | About 700 ms: the last stroke fills (150 ms), the needed strokes and the line turn green (200 ms), the second line is ruled left to right (350 ms). Then the stage folds to the docket slip (height, 320 ms ease-out) and the answer sheet fades in (200 ms). Reduced motion: the final state at once. |
| A seat becoming ready | Opacity only, 250 ms. |
| Speaker's ring | Opacity only, 200 ms in and out. |
| Vote marks | All heads together, 120 ms fade. No stagger. |
| Table / Chat switch | 200 ms crossfade between the views. No slide. |
| Writing caret | The only loop in the app: a text caret blinking once a second at the end of text that is still arriving (Chat View and the answer). Static under reduced motion. |
| Controls | 150 ms ease-out on colour and opacity only. |

Where it is not used

- No pulse or glow on the speaker, the status pill or anything else.
- No slide-up entrances for messages; a new message fades in over 150 ms and does not move.
- No hover lifts, scaling or shadow changes.
- Timer digits swap without animation; tabular figures keep them still.
- Nothing moves between seats (no pointer, spotlight or line to the speaker).
- No page-load sequence.

## Wording
The voice is a careful minute-taker: plain verbs, sentence case, numerals, full stops, no exclamation marks. What is happening is in the present tense; what is finished is in the past. No meeting jargon (no motion, quorum, yea or nay) and no system words. Fragments are never joined with dots or dashes. A button says what it does and the result keeps the same name: Show the debate opens a view headed "The debate".

| Place | Wording |
|---|---|
| 1. Status pill | (mini tally)  Round 2   3:10 left   3 of 5 agree. Other states: "Seating the council, 3 of 5 ready". "Paused at 3:10". "Council of 5 seated". |
| 2. Vote divider | Round 1 vote: 2 of 5 agree, needs 4 |
| 3. Answer heading, agreed | **Agreed, 4 of 5** and under it: 3 rounds, 4 min 12 s. Mistral disagreed. |
| 4. Answer heading, no consensus | **No consensus, 3 of 5** and under it: Time ran out after 5 minutes. This answer had the most support. Phi and Mistral disagreed. |
| 5. Empty chat | **Ask the council a question.** Phi, Llama, Qwen, Gemma and Mistral are seated. They read only your files and give you one answer. Buttons: Change seats. Attach files. |
| 6. A model that failed to load | **Gemma did not load.** The GX10 does not have enough free memory for five seats. Buttons: Start with four seats. Choose a smaller model. Under the first: Four seats must all agree. |

Also used: dissent line "Mistral disagreed: a five-year term saves more than the break clause costs." Docket slip "Debate record: 3 rounds, 4 min 12 s" with Show the debate. Under the message box during a debate: "The council reads this at the start of the next round." On mock-only controls: "Not in this mock yet."

## Review against the skill's generic looks
I wrote a first plan from the angle "the record", then checked it against the skill's five clusters and its three type tells. Eight parts were defaults and were changed.

| # | First draft | Why it was a default | Now |
|---|---|---|---|
| 1 | Legal-pad yellow paper with a red margin line | Warm cream plus red, in costume (cluster 1) | Steno-pad green-grey #E5ECE4, blue-black ink, a quiet grey-green margin line |
| 2 | Rubric red accent | Too near vermilion and terracotta, and it collided with error | Copying-pencil violet, flat only, so it cannot drift into stock AI purple |
| 3 | Typewriter monospace for model messages, with line numbers down the margin | Monospace for data is on the list, and it reads as a terminal, which the brief forbids. The line numbers were not a real sequence anyone cites | Literata for messages. The margin carries only the time into the debate, which the PDF asks for |
| 4 | Feint ruled lines across the page, column rules in Chat View, square corners everywhere | The broadsheet with hairline rules (cluster 3), the exact trap named in my brief | One margin line. Columns separated by 32 px of space. Radius by role: 3, 8, fully round |
| 5 | A giant "3/5" numeral with a small label on the table top | The big number with a small label is the stock hero | Strokes carry the count; the sentence stays label-sized |
| 6 | A rotated rubber stamp reading AGREED | Kitsch, uppercase, decoration with no information | A second ruled line and the word Agreed in sentence case |
| 7 | Closing the tally with the diagonal slash of a five-bar gate | Not a default but a falsehood: with five seats, four strokes and a slash reads as five | The bookkeeper's double rule |
| 8 | Dark theme as near-black with bright violet | Cluster 2 with a different accent | Blue-slate page, paper-coloured ink, soft lilac |

Removed in the "take one thing off" pass: seat numerals in the bodies (name, hatch and position already do it); a box round the stage; uppercase column headings in Chat View; the PDF's middle-dot meta strings; the pulse on the status dot.

Similar-prompt test. For any "AI debate app" I would produce coloured avatar circles, chat bubbles with tails, a progress bar and a glow on the speaker. None of the four survives: figures are ringed and hatched, notes are slips with leader lines, the meter is strokes, the speaker wears a second ring. For any "minutes-themed app" I would produce cream paper, Courier, a red margin and a stamp. Rows 1, 3 and 6 removed those.

What I kept despite the risk: serif reading text. A serif is common in generated designs as a display face over a sans body; here it is the reverse (the serif is the reading face, there is no display face), and it follows from the principle that the record and the form speak in different voices.

## Principles
- Two voices, never swapped. What is recorded (questions, messages, notes, answers, titles) is set in Literata. What is printed on the form (labels, buttons, names in heads, times, numbers) is set in Archivo.
- The margin holds the meta. Who, when, which round and the vote go in the left margin column in muted Archivo. The text column holds only what was said. No labels above content, no eyebrow lines.
- Hollow, then filled. Anything provisional is hollow or dashed (tally strokes not yet won, a seat still loading). Anything settled is filled. Colour never does this job alone.
- One line on the page. The margin line is the only rule. Separate everything else with space and with the step from page tone to surface tone. No boxes inside boxes, no shadows except on overlays, no gradients, no uppercase, no dots or dashes joining fragments of meta, no arrows on links.
- Violet means live or pressable, and only that: Send, focus, the active side of the switch, the speaker's ring, links, the writing caret. Green appears only when the council has agreed. Red appears only when something failed. A cross on a head is ink, because disagreeing is not a fault.
- Counts are strokes. Wherever agreement is shown (pill, table top, vote divider, answer), draw one stroke per seat and say the plain sentence beside it: 3 of 5 agree, needs 4.

## Kept from the PDF
- The frame: slim top bar with the seated council and a status pill (round, time left, agreement); sidebar with New chat, History, Library, Models, Settings; the conversation fills the rest.
- The stage opens inside the conversation and folds into a card above the answer when the council agrees.
- Table View geometry: half-circle table, flat side toward you, 3 to 7 figures evenly along the curved edge, full-circle head holding the short name over a half-circle body, the five-seat arrangement of the wireframe.
- A check or cross on every head after each vote, and the table middle showing round, time left and the PDF's own sentence: 3 of 5 agree, needs 4.
- All bubble rules and timings: two lines at most, never overlapping, each seat owns the space above it, end seats push outward, a touching bubble rises; in 250 ms, hold about 8 s, out about 1.5 s, crossfade in place, plain appear and disappear with reduced motion.
- The third-person style of the wireframe's bubble text (Answers Qwen with a counter. Cites page 4 of your report).
- Chat View in black and white with the PDF's exact values (#111111 on #FFFFFF, #F2F2F2 on #0E0E0E), greys for names and times, sender and addressee, time into the debate, outlined citation chips, a thin vote divider, one column per model on a wide screen and one thread on a narrow one, the All models filter.
- The small Table / Chat switch at the bottom right while the council works.
- Light and dark themes from the first version; body text at 4.5:1 or better; the 8 px grid; 150 to 200 ms ease-out for controls; reduced motion honoured.
- Keyboard first: visible focus rings, full tab order, a shortcuts help sheet.
- Open-licence fonts bundled through Fontsource so the app runs with no internet; tabular figures for the timer and counts.
- Seat colour belongs to the seat, and the name inside the head means colour is never the only signal.
- The words Agreed 4 of 5 and No consensus, the 80% rounding table, and the answer listing its files and its dissents.
- Type sizes where the PDF's were right: labels 14/500, small meta 12, Chat View messages 15.
- The technical picks: SVG table and figures, HTML bubbles placed by a small layout pass, Motion for fades, Tailwind driven by tokens, Radix primitives.

## Changed from the PDF
- Paper: warm cream #F5F1EA becomes cool steno green-grey #E5ECE4; dark #1F1E1B becomes blue-slate #141A23. The mood word changes from warm to cool and clerical.
- Accent: clay #C4694D becomes copying-pencil violet #67298C (dark #CDA4EC), and is restricted to live or pressable things.
- Text: warm near-black #2B2A27 becomes blue-black #1A2435.
- Typefaces: Fraunces, Source Sans 3 and JetBrains Mono become Literata and Archivo. No monospace; numbers use Archivo's tabular figures.
- Roles reversed: the serif is now the reading face and the sans is for labels. The PDF had a sans for reading and a serif for titles.
- Sizes: chat text 16/1.6 becomes 17/28; bubbles 13 become 14 italic; names in heads 11 become 12, fitted by narrowing the letters; titles 24/600 become 26/550.
- Seat colours: seven new values chosen by colour-blindness simulation, in a new order, each with a hatch pattern. Heads are a pale tint with a coloured ring and the name in ink, because a solid fill in the PDF's colours could not carry a name at 4.5:1.
- Speaker mark: the soft clay glow becomes a second ring in violet, which is measurable, still, and a shape.
- Vote marks: check and cross are both drawn in ink. A cross is not red, because a dissent is not an error.
- Agreement meter: tally strokes with an underline at the number needed, ruled off with a second line at agreement, in place of an unspecified meter. Agreed green #5E8C6A becomes #136239 so it can also be text.
- Bubbles: paper slips with a leader line and italic text, with no speech tail.
- Radius and depth: 12 px cards and 8 px inputs with very soft shadows become 3 px slips, 8 px controls, round pills and heads, and no shadows except on overlays.
- Borders: the PDF's hairline (about 1.2:1) is split into a decorative margin line and an outline token at 3:1 or better for every edge that must be seen.
- Meta strings: middle dots (Round 2 · 3:10 left) become gaps, commas and colons.
- Layout inside the frame: the conversation is left-anchored with a real margin column, and the right third is kept clear for the agent's side sheet.
- Status pill: no pulsing dot; it carries a miniature tally.
- Error red #B5483E becomes #A12628 (dark #F28881).

## Contrast (designer's computed figures)

| Pair | Theme | Ratio | Needed | Pass |
|---|---|---|---|---|
| Text (ink #1A2435) on page #E5ECE4 | light | 12.95 | 4.5 | yes |
| Text (ink) on surface #F5F8F4: answer sheet, note slips, table top | light | 14.56 | 4.5 | yes |
| Text (ink) on sunk #DBE2D9: sidebar | light | 11.79 | 4.5 | yes |
| Text (ink) on mark-wash #ECDFF7 | light | 12.22 | 4.5 | yes |
| Muted text #515963 on page: margin meta | light | 5.9 | 4.5 | yes |
| Muted text on surface: placeholder, table-top round label | light | 6.63 | 4.5 | yes |
| Muted text on sunk: sidebar meta | light | 5.37 | 4.5 | yes |
| Accent text (mark #67298C) on page: links | light | 7.68 | 4.5 | yes |
| Accent text (mark) on surface | light | 8.63 | 4.5 | yes |
| Accent text (mark) on mark-wash: active switch label | light | 7.24 | 4.5 | yes |
| Send label (on-mark #FFFFFF) on mark fill | light | 9.24 | 4.5 | yes |
| Agreed text #136239 on surface | light | 6.92 | 4.5 | yes |
| Agreed text on page | light | 6.16 | 4.5 | yes |
| Error text #A12628 on surface | light | 6.95 | 4.5 | yes |
| Error text on page | light | 6.18 | 4.5 | yes |
| Text (ink #E2E8E1) on page #141A23 | dark | 14.03 | 4.5 | yes |
| Text (ink) on surface #1D232E: answer sheet, note slips, table top | dark | 12.66 | 4.5 | yes |
| Text (ink) on sunk #272E3A: sidebar | dark | 10.96 | 4.5 | yes |
| Text (ink) on mark-wash #3F2C4C | dark | 10.06 | 4.5 | yes |
| Muted text #9AA8A8 on page: margin meta | dark | 7.11 | 4.5 | yes |
| Muted text on surface: placeholder, table-top round label | dark | 6.41 | 4.5 | yes |
| Muted text on sunk: sidebar meta | dark | 5.55 | 4.5 | yes |
| Accent text (mark #CDA4EC) on page: links | dark | 8.42 | 4.5 | yes |
| Accent text (mark) on surface | dark | 7.59 | 4.5 | yes |
| Accent text (mark) on mark-wash: active switch label | dark | 6.04 | 4.5 | yes |
| Send label (on-mark #141A23) on mark fill | dark | 8.42 | 4.5 | yes |
| Agreed text #7BCC98 on surface | dark | 8.21 | 4.5 | yes |
| Agreed text on page | dark | 9.1 | 4.5 | yes |
| Error text #F28881 on surface | dark | 6.47 | 4.5 | yes |
| Error text on page | dark | 7.17 | 4.5 | yes |
| Graphic: outline #717E76 on page (message box edge, leader lines) | light | 3.53 | 3 | yes |
| Graphic: outline on surface (table edge, hollow tally strokes) | light | 3.96 | 3 | yes |
| Graphic: outline on sunk | light | 3.21 | 3 | yes |
| Graphic: speaker ring and focus ring (mark) on page | light | 7.68 | 3 | yes |
| Graphic: focus ring (mark) on surface | light | 8.63 | 3 | yes |
| Graphic: filled tally strokes and check or cross (ink) on surface | light | 14.56 | 3 | yes |
| Graphic: ruled-off tally (agreed) on surface | light | 6.92 | 3 | yes |
| Graphic: failed-seat ring (error) on page | light | 6.18 | 3 | yes |
| Graphic: outline #78818C on page (message box edge, leader lines) | dark | 4.42 | 3 | yes |
| Graphic: outline on surface (table edge, hollow tally strokes) | dark | 3.99 | 3 | yes |
| Graphic: outline on sunk | dark | 3.46 | 3 | yes |
| Graphic: speaker ring and focus ring (mark) on page | dark | 8.42 | 3 | yes |
| Graphic: focus ring (mark) on surface | dark | 7.59 | 3 | yes |
| Graphic: filled tally strokes and check or cross (ink) on surface | dark | 12.66 | 3 | yes |
| Graphic: ruled-off tally (agreed) on surface | dark | 8.21 | 3 | yes |
| Graphic: failed-seat ring (error) on page | dark | 7.17 | 3 | yes |
| Seat 1 Blue ring #015B94 on page | light | 5.97 | 3 | yes |
| Seat 1 Blue ring and hatch on its head tint #D3E2E7 | light | 5.4 | 3 | yes |
| Name in head (ink) on Seat 1 tint #D3E2E7 | light | 11.73 | 4.5 | yes |
| Seat 2 Ochre ring #A27C01 on page | light | 3.22 | 3 | yes |
| Seat 2 Ochre ring and hatch on its head tint #E9E7D2 | light | 3.1 | 3 | yes |
| Name in head (ink) on Seat 2 tint #E9E7D2 | light | 12.48 | 4.5 | yes |
| Seat 3 Sepia ring #513A26 on page | light | 8.8 | 3 | yes |
| Seat 3 Sepia ring and hatch on its head tint #DEDDD7 | light | 7.78 | 3 | yes |
| Name in head (ink) on Seat 3 tint #DEDDD7 | light | 11.45 | 4.5 | yes |
| Seat 4 Teal ring #238C8C on page | light | 3.35 | 3 | yes |
| Seat 4 Teal ring and hatch on its head tint #D8E9E5 | light | 3.21 | 3 | yes |
| Name in head (ink) on Seat 4 tint #D8E9E5 | light | 12.4 | 4.5 | yes |
| Seat 5 Olive ring #6C6B2A on page | light | 4.62 | 3 | yes |
| Seat 5 Olive ring and hatch on its head tint #E2E4D8 | light | 4.32 | 3 | yes |
| Name in head (ink) on Seat 5 tint #E2E4D8 | light | 12.11 | 4.5 | yes |
| Seat 6 Rose ring #B25C69 on page | light | 3.77 | 3 | yes |
| Seat 6 Rose ring and hatch on its head tint #ECE2E1 | light | 3.57 | 3 | yes |
| Name in head (ink) on Seat 6 tint #ECE2E1 | light | 12.27 | 4.5 | yes |
| Seat 7 Graphite ring #555A60 on page | light | 5.78 | 3 | yes |
| Seat 7 Graphite ring and hatch on its head tint #DFE2DF | light | 5.33 | 3 | yes |
| Name in head (ink) on Seat 7 tint #DFE2DF | light | 11.93 | 4.5 | yes |
| Seat 1 Blue ring #7CAAE9 on page | dark | 7.31 | 3 | yes |
| Seat 1 Blue ring and hatch on its head tint #2C394C | dark | 4.89 | 3 | yes |
| Name in head (ink) on Seat 1 tint #2C394C | dark | 9.39 | 4.5 | yes |
| Seat 2 Ochre ring #F1CA78 on page | dark | 11.2 | 3 | yes |
| Seat 2 Ochre ring and hatch on its head tint #3F3E3A | dark | 6.86 | 3 | yes |
| Name in head (ink) on Seat 2 tint #3F3E3A | dark | 8.6 | 4.5 | yes |
| Seat 3 Sepia ring #9F7F64 on page | dark | 4.74 | 3 | yes |
| Seat 3 Sepia ring and hatch on its head tint #323237 | dark | 3.46 | 3 | yes |
| Name in head (ink) on Seat 3 tint #323237 | dark | 10.24 | 4.5 | yes |
| Seat 4 Teal ring #89DFE3 on page | dark | 11.42 | 3 | yes |
| Seat 4 Teal ring and hatch on its head tint #2E414B | dark | 6.95 | 3 | yes |
| Name in head (ink) on Seat 4 tint #2E414B | dark | 8.54 | 4.5 | yes |
| Seat 5 Olive ring #AAAE62 on page | dark | 7.44 | 3 | yes |
| Seat 5 Olive ring and hatch on its head tint #343936 | dark | 5.01 | 3 | yes |
| Name in head (ink) on Seat 5 tint #343936 | dark | 9.45 | 4.5 | yes |
| Seat 6 Rose ring #E6ABB8 on page | dark | 9.05 | 3 | yes |
| Seat 6 Rose ring and hatch on its head tint #3D3944 | dark | 5.83 | 3 | yes |
| Name in head (ink) on Seat 6 tint #3D3944 | dark | 9.03 | 4.5 | yes |
| Seat 7 Graphite ring #959AA0 on page | dark | 6.16 | 3 | yes |
| Seat 7 Graphite ring and hatch on its head tint #303640 | dark | 4.29 | 3 | yes |
| Name in head (ink) on Seat 7 tint #303640 | dark | 9.76 | 4.5 | yes |
| Chat View text #111111 on #FFFFFF | light | 18.88 | 4.5 | yes |
| Chat View names and times #5C5C5C on #FFFFFF | light | 6.69 | 4.5 | yes |
| Chat View chip outline #767676 on #FFFFFF | light | 4.54 | 3 | yes |
| Chat View text #F2F2F2 on #0E0E0E | dark | 17.24 | 4.5 | yes |
| Chat View names and times #A3A3A3 on #0E0E0E | dark | 7.65 | 4.5 | yes |
| Chat View chip outline #8A8A8A on #0E0E0E | dark | 5.59 | 3 | yes |
| Decorative, no minimum applies: margin line (rule #B5C2B7) on page. Nothing depends on seeing it | light | 1.54 | 1 | yes |
| Decorative, no minimum applies: surface against page (tone step only; every control edge uses outline instead) | light | 1.12 | 1 | yes |
| Decorative, no minimum applies: margin line (rule #3A404B) on page. Nothing depends on seeing it | dark | 1.68 | 1 | yes |
| Decorative, no minimum applies: surface against page (tone step only; every control edge uses outline instead) | dark | 1.11 | 1 | yes |

## Risks
- The page tint is a taste call and screen-dependent. A faint green can look grey or unwell under Night Shift, True Tone or on an older external monitor, and violet on green will divide opinion. Check on his own Macs at the gate; offer one look switch with the tint halved (about #EAEDE9).
- Hatch patterns can shimmer or fill in on a non-Retina external monitor, and seven hatched bodies could look busy. Test at device scale 1 and 2; the fallback is an 8 px pitch. A second look switch (hatches on or off) lets him judge.
- Two seat colours sit just above the floor in the light theme: ochre 3.10:1 and teal 3.21:1 against their own tints. They are that light on purpose (lightness is what separates them for colour-blind viewers), so any later nudge to the palette can break them. The contrast test must pin them.
- Violet can slide into stock AI purple the moment a builder adds a gradient, a glow or a tinted shadow. The token guard should ban gradients and shadows outside overlays.
- Note length. Two lines above a seat hold about 60 characters with five seats and about 45 with seven. Whoever ends up writing the summaries (a small model or each agent) must be given that budget, or notes will end in an ellipsis every day. See owner question 2.
- Italic serif at 14 px may look thin in the dark theme on some screens. Mitigation: weight 450 to 500 in dark, checked on the device.
- Switching from Table View to Chat View jumps from a tinted page to a pure white (or pure black) sheet. The 200 ms crossfade softens it, but the white sheet is the brightest thing in the app in a dim room.
- The left-anchored page leaves the right third empty on a wide monitor whenever no agent sheet is open. It is deliberate, but it may read as unfinished.
- The ruled-off double line is a bookkeeping convention. If it does not read at a glance, the words (Agreed, 4 of 5) carry the meaning; with seven seats the strokes in the status pill are small.
- Ink-coloured checks and crosses are less glanceable from across a room than green and red. A third look switch can show the green and red version at the gate.
- Model names longer than eight characters will not fit a 60 px head even at the narrowest width. The Models screen (Phase 3) needs a short-name rule.
- At seven seats there are ten hues in play (seven seats, violet, green, red). The calm depends on seat colour staying in thin rings and hatch lines and never becoming a solid fill.
- Process caveat: the PDF's wireframes were read as labels and positions, not seen as pictures, because page rendering is not available on this Mac in read-only mode. Work package 1.0 should render pages 4, 6, 7, 8 and 13 to PNG (the previous plan's pypdfium2 one-off) and a builder should compare them with this direction before building.

## Questions the designer left for Lucas
- Vote marks. The PDF says a check or cross sits on every head 'until the next round'. I would keep them on the heads through the next round, until the next vote replaces them, so the heads always add up to the '3 of 5 agree' shown on the table. Keep them, or clear them when a new round starts?
- Note length. With two lines as the limit, a note above a seat holds about ten words (about 60 characters with five seats, 45 with seven). The PDF says 'one or two sentences'. Are ten-word notes acceptable, with the longer summary available in the agent's side sheet?

## Designer's own study brief (SUPERSEDED by docs/direction/study-brief.md)
Build one self-contained HTML file: inline CSS and inline SVG, no network requests. Render the page twice, stacked: light theme first, dark second, each 1280 px wide, with the exact hex tokens. Each theme shows two frames.

Frame 1, a debate in progress: sidebar block, top bar with five names and the status pill, the question in the text column with "You 14:02" in the margin column and the single vertical margin line, then Table View with five seats, left to right Phi, Llama, Qwen, Gemma, Mistral, using seat colours 1 to 5 and hatches plain, vertical, dots, rising diagonal, horizontal. Qwen and Gemma both wear the violet second ring and a note slip; Llama's slip is steady; Phi's is at 35% opacity. Heads carry three checks and two crosses in ink. Table top: Round 2, 3:10 left, five strokes (three filled, two hollow, underline under four), "3 of 5 agree, needs 4". Message box and Table / Chat switch below.

Frame 2, released: the one-line "Debate record" slip, then the answer sheet headed "Agreed, 4 of 5" with the green ruled-off tally in its margin, three short paragraphs at 17/28, two file chips, one italic dissent line.

Fonts: embed Literata and Archivo as base64 woff2 if the Fontsource files are on disk; otherwise fall back to Georgia and Helvetica Neue and say which. No gradients, shadows, uppercase labels, middle dots or speech tails. Screenshot both themes and confirm no slip overlaps another.
