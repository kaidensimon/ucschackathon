# Direction C: Cut-Out Council

> Seven flat, one-colour cut-out figures, each with its model's name lettered large inside its head, sit around a pale green-cloth table, and everything else in the app is plain dark ink on chalk so the council is the only colour you ever see.

This is the design lead's written direction (frontend-design skill process). Read `corrections.md` beside it: corrections win.

## Grounding
Six things from this product's own world drive the choices.

1. A vote is a head count. Picture statistics (Isotype, Neurath and Arntz, 1920s) count people with small one-colour figures instead of bars. So the figures and a row of pips do the counting; there is no progress bar.
2. Game pieces and turned wooden dolls. A piece is told apart by one flat colour and one painted mark, never by a face. So each figure is a single colour with one cut in its body and no eyes or mouth.
3. The green cloth. Council and card tables are covered in green baize (the old Board of Green Cloth; in German a decision is made 'at the green table'). So the table is the one tinted surface in the app, and nothing else is.
4. Name placards. At a council table you know who is speaking by the name in front of them. So the name is the face: it is lettered to fill the head, larger for short names.
5. Model names are short and odd (Qwen, Phi, Llama, Mistral), with look-alike letters and very different lengths. So the lettering face is a sturdy grotesque with a width axis that can fit each name to the same circle.
6. Two phrases in the PDF itself. 'In one voice': the debate is set in a sans, the released answer in a book serif, so the type changes when the council speaks as one. 'Flat side toward you': the message box is joined to the flat side, so it is your place at the table.

Checked today: both font packages exist on npm at 5.3.0 under OFL-1.1; the Fontsource registry lists Archivo's width axis as 62 to 125 and weight 100 to 900, and Literata's optical-size axis as 7 to 72; Archivo's feature table contains tabular figures (tnum).

## Palette

| Token | Light | Dark | Role |
|---|---|---|---|
| page | `#F1F2EE` | `#151B18` | IDENTITY (chalk). App background and the stage. Also the colour of every name and every cut inside a figure: they are the page showing through. |
| surface | `#FBFBF9` | `#1C2420` | Bubbles, message box, folded debate card, sheets, menus. |
| table | `#DEE5DD` | `#213029` | IDENTITY (green cloth). Fill of the half-circle table and nothing else. |
| hover | `#E6E9E3` | `#242D28` | Row hover and pressed states. Only text and muted text sit on it. |
| border | `#D3D8D1` | `#2D3832` | Decorative hairlines only (1.29:1 light, 1.43:1 dark). Never the only cue for anything. |
| line | `#77827B` | `#74817A` | Edges that carry meaning: the table's curved edge, text-field outlines, empty meter pips. At least 3:1 on page, surface and table. |
| text | `#17201C` | `#E6EBE7` | IDENTITY (ink). Primary text everywhere outside Chat View. |
| muted | `#535E58` | `#9CA9A2` | Meta, times, placeholders. |
| accent | `#1D2A24` | `#E6EBE7` | Deliberately ink, not a hue. Ask button, active side of the Table / Chat switch, focus ring, vote badges, filled meter pips. |
| accent-hover | `#2C3B33` | `#FFFFFF` | Hover on the ink button. |
| on-accent | `#F1F2EE` | `#151B18` | Label on the ink button; the check inside a solid vote badge. |
| agreed | `#1A6B42` | `#74C998` | Meter pips and the words '4 of 5 agree' once the bar is reached. Always with a check and the word, never figure-shaped. |
| error | `#A32A1C` | `#F0897A` | Badge and message for a model that failed to load or answer. Always with an icon and words. |
| seat-1 to seat-7 | `see seats` | `see seats` | IDENTITY as a set. The only hues in the app. seat-1 teal, seat-2 indigo and seat-3 ochre sit in every council (three is the minimum), so with page, table and text they are the six values that carry the identity. |
| chat-paper | `#FFFFFF` | `#101010` | Chat View sheet. Every Chat View value has equal red, green and blue, so 'no colour' can be checked by a test. |
| chat-text | `#161616` | `#EDEDED` | Chat View message text and names inside the ink figures. |
| chat-grey | `#5E5E5E` | `#A6A6A6` | Chat View 'to Llama', times, filter labels. |
| chat-rule | `#8C8C8C` | `#6E6E6E` | Chat View vote divider, chip outlines, figure outlines (3:1 or better). |
| chat-faint | `#DCDCDC` | `#2A2A2A` | Chat View column separators (decorative). |

## Seats
Four signals, so colour is never alone: (1) colour; (2) a cut in the body, one per seat, fixed to the seat not the model; (3) position at the table; (4) the model's short name lettered in the head. The cut matters because the PDF allows one model in two seats: two heads may then carry the same name.

One colour per figure. Head and body are the seat colour; the name and the cut are the page colour (knocked out). So one rule covers text and graphics: every seat colour must reach 4.5:1 against the page. Light theme uses deep colours, dark theme pale ones. All fourteen pass (see contrast).

Cuts (4 px at a 60 px head): seat 1 plain; seat 2 band (one horizontal cut); seat 3 collar (a V from the shoulders); seat 4 sash (one diagonal); seat 5 placket (one vertical at centre); seat 6 yoke (an arc following the top curve, 9 px inside it); seat 7 braces (two verticals). Below a 24 px body the cut is dropped and the name is written beside the figure instead.

Colour-vision check, computed: Machado 2009 simulation at full severity, difference as OKLab distance x100 (about 2 is just noticeable). Lowest for ANY pair of the seven: light 11.7 normal, 8.2 protan (teal vs slate, seats 1 and 5), 9.0 deutan (teal vs claret), 9.6 tritan (slate vs violet); dark 12.1 normal, 11.4 protan, 11.4 deutan, 11.4 tritan. Lowest for NEIGHBOURS in seat order: 12.7 light, 11.7 dark. Seat order was chosen by trying all 5,040 orders for the best worst-case neighbour pair across both themes. Lightness also steps: L* 34, 19, 45, 22, 45, 32, 35 in light and 87, 65, 87, 57, 73, 72, 59 in dark, so neighbours differ even in greyscale.

Hues were chosen to stay clear of the table's green; agreed green and error red are never drawn as figures.

| Seat | Light | Dark |
|---|---|---|
| 1 Teal, plain body | `#005960` | `#A1E8E5` |
| 2 Indigo, band | `#23246E` | `#789AFF` |
| 3 Ochre, collar | `#8C6205` | `#FAD786` |
| 4 Claret, sash | `#641530` | `#DE6365` |
| 5 Slate, placket | `#656B78` | `#ABB6B5` |
| 6 Rust, yoke | `#8A2C06` | `#F49A5B` |
| 7 Violet, braces | `#6C379B` | `#9D85B2` |

## Typefaces

| Role | Family | Package | Why |
|---|---|---|---|
| Everything spoken or operated. Page, sheet and dialog titles 24/30, weight 620, width 112%. Answer heading ('Agreed 4 of 5') 20/26, weight 650, width 106%. Chat text, your messages: 16/25, weight 400. Bubble text 13/18, weight 450, width 96%, two lines at most. Names in heads: fitted, 11 to 17 px, weight 650, width 72 to 110%, line height 1. Chat View messages 15/23, weight 400; sender name 13/600; 'to Llama' and time 12/400. Labels and buttons 14/20, weight 500. Small meta 12/16, weight 400, muted. Numbers (timer, votes, counts) 13 to 15 px, weight 550, tabular lining figures; no separate numbers font. | Archivo (variable: weight and width) | `@fontsource-variable/archivo` 5.3.0 (OFL-1.1) | Its width axis (62 to 125, confirmed on the Fontsource registry; import the package's wdth.css) lets every name fill the same circle: short names set large, long names condensed instead of shrunk or cut off. Measured at weight 600: Phi 1.51 em, Qwen 2.69, Llama 2.80, Mistral 3.12, Granite 3.42, Gemma 3.63, DeepSeek 4.77. In a 60 px head (target width 47 px) that gives about Phi 17 px, Qwen 17, Llama 16, Mistral 14, Gemma 13 at 98%, DeepSeek 13 at 72%; a 50 px head still holds 11 px. Fit rule: largest size from 17 down that fits at 100% width; at 13 px and below condense as far as 72% before shrinking further; never under 11 px; otherwise the name is too long. Use CSS font-stretch, not raw variation settings. It is a matter-of-fact grotesque, which keeps round friendly figures from turning cute. Its tabular figures (tnum, confirmed in the font's feature table) replace the PDF's monospace for numbers. |
| The released answer only (and a single model's reply in Phase 2). Chat text, council answers: 17/28 (line height 1.65), weight 400, bold 650, true italics, optical size automatic, measure 640 px at most (about 78 characters). Tables inside an answer switch to Archivo 14/20 with tabular figures. Code blocks use the Mac's own monospace (ui-monospace, SF Mono, Menlo) at 14/22, so no third family is bundled. | Literata (variable: weight and optical size) | `@fontsource-variable/literata` 5.3.0 (OFL-1.1) | Sans is talk, serif is the answer: the typeface changes at the moment the council speaks in one voice, which the owner can see without being told. Literata was drawn for reading books on screens: low contrast, sturdy, warm, and nothing like the high-contrast display serif of the PDF's starting look. It carries no titles. Import the package's opsz.css and opsz-italic.css (optical size 7 to 72, weight 200 to 900, confirmed on the Fontsource registry). |

## Layout
## Concept

One centred axis, 640 px wide. The table's diameter, the message box and the answer's text column are the same width on the same centre line. The table's flat side rests on the top edge of the message box, so the message box is your place at the table. The fixed frame (slim top bar, sidebar, conversation) is kept as briefed; inside it there are no cards and no panels except bubbles, the message box and the folded debate card.

Alignment: answer text left-aligned in the 640 column; your messages right-aligned in it; the middle of the table is the only centred text in the app; top bar has title left, seated council and status pill right.

## Sizes

| Thing | Value |
|---|---|
| Top bar | 48 px high: app name, chat title, row of mini figures with '5 seated', status pill |
| Sidebar | 232 px: New chat, History, Library, Models, Settings; footer has theme switch and Shortcuts. Becomes a 56 px rail under 1100 px |
| Axis column | 640 px (table diameter, message box, answer measure) |
| Table radius R | 320; rule: clamp(220, the smaller of (stage width - 300) / 2 and (stage height - 190), 320) |
| Stage height | R + 190, pinned above the message box; the chat scrolls above it |
| Head diameter D | 64 (3 or 4 seats), 60 (5), 54 (6), 50 (7) |
| Body | half-circle of radius 0.75 D; head overlaps it by 0.14 D with a 3 px page-colour gap |
| Seat angles | evenly spaced along the curve between 180 - t and t degrees; t = 40, 28, 18, 15, 12 for 3, 4, 5, 6, 7 seats |
| Seat placement | figure stays upright; slide it out along its seat's radius until only 6 px of the body is hidden behind the table edge |
| Bubble | 200 to 248 px wide, never wider than the gap to the neighbour, two lines |
| Radius by role | bubble 10, message box and folded card 14, buttons 8, chips 6, pill and switch fully round |
| Shadow | one, on floating things only (bubbles, menus, sheets): 0 1px 2px, ink at 8% |
| Spacing | 8 px grid |

## 1. Main screen during a debate (1440 x 900)

```
+--------------------------------------------------------------------------------------------------+
| GX10 Council   March invoice total      o o o o o  5 seated   ( Round 2 | 3:12 left | 3 of 5 agree ) |
+------------+-------------------------------------------------------------------------------------+
| New chat   |                                                +------------------------------+     |
| History    |                                                | Which total is right for the |     |
| Library    |                                                | March invoice?               |     |
| Models     |                                                | [invoice-march.pdf, 3 pages] |     |
| Settings   |                                                +------------------------------+     |
|            |                          +------------------------+                                 |
|            |                          | The March invoice is   |                                 |
|            |                          | the newest. Total 4,180|                                 |
|            |                          +-----------v------------+                                 |
|            |                  (Llama)         ((Gemma))         (Mistral)                        |
|            |                             . - - - - - - - .                                       |
|            |            (Qwen)       .'       Round 2       '.        (Phi)                      |
|            |                        :        3:12 left        :                                  |
|            |                       :         * * * o | o        :                                |
|            |                       :   3 of 5 agree, needs 4    :                                |
|            |                       +============================+                                |
|            |                       | Add something for the next |                                |
| Light/Dark |                       | round          Pause  Stop |                                |
| Shortcuts  |                       +----------------------------+               [ Table | Chat ] |
+------------+-------------------------------------------------------------------------------------+
   232 px                      one axis, 640 px: table = message box = answer
```

## 2. Table View, five seats (stage only)

```
                               +-----------------------------+
                               | The March invoice is the    |
                               | newest. The total is 4,180. |
                               +--------------v--------------+
        + - - - - - - - - - +
        : The 2023 rate no  :            (( Gemma ))        speaking: ring and halo in its own
        : longer applies.   :           (____VV____)        colour, leans in 4 px. Cut: collar
        + - - - - v - - - - +     (fading, 40%)
              ( Llama )            . - - - - - - - - - .            ( Mistral )
             (___====___)      . '                       ' .        (____//____)
               band          .'            Round 2          '.         sash
                            :             3:12 left           :
     ( Qwen )              :                                   :              ( Phi )
    (__________)           :           *  *  *  o | o          :            (____||____)
       plain               :       3 of 5 agree, needs 4       :              placket
                           +===================================+   flat side has no line of its
                           | Add something for the next round  |   own: it rests on the message box
                           |                      Pause   Stop |
                           +-----------------------------------+
                                                                          [ Table | Chat ]
```

`*` filled pip (agrees), `o` empty pip, `|` the mark after pip 4 ('needs 4'). After a vote each head carries a small badge at its upper right: solid with a check, or hollow with a cross.

When the council agrees, the table sinks into the message box and the stage becomes one card above the answer: five small figures in a row with their badges and names beneath, 'Agreed 4 of 5', rounds, time, 'Replay the debate'. The answer follows in Literata on the same 640 axis.

Under 1100 px: sidebar rail, R 240, bubbles 180 px. Phone layout stays in Phase 7.

## Files this direction adds in Phase 1 (none exist yet)

- /Users/lucasta/projects/gx10-council/ui/src/styles/tokens.css
- /Users/lucasta/projects/gx10-council/ui/src/components/Figure.tsx
- /Users/lucasta/projects/gx10-council/ui/src/lib/fitName.ts
- /Users/lucasta/projects/gx10-council/ui/src/components/CouncilTable.tsx
- /Users/lucasta/projects/gx10-council/ui/src/lib/contrast.test.ts

## The one bold element
The figures. Seven one-colour cut-outs with the name lettered to fill the head and one cut in the body are the only colour, the only illustration and the only recurring shape in the app. They appear at four sizes: seated at the table (head 50 to 64 px), as a row in the top bar (head 14 px), as the line-up on the folded debate card above each answer (head 22 px), and as ink line drawings heading the Chat View columns. Everything else (page, type, controls, bubbles, table) is kept plain so they can carry it.

## Table View
Stage: page colour, no frame, pinned above the message box, height R + 190.

Table: an SVG half-disc, flat side down, diameter 640 (R 320, shrinking to 220), filled with the table token. A 1.5 px line-token stroke on the curve only. The flat side has no stroke and sits on the message box, which is the same width.

Figures: SVG, one flat seat colour each, no outline, no gradient, no shadow, no face. Head is a circle of diameter D holding the fitted name in the page colour. Body is a half-circle of radius 0.75 D under it, overlapped by the head by 0.14 D with a 3 px page-colour gap, carrying that seat's cut in the page colour. The table is drawn on top and hides the lowest 6 px of each body, so the figures sit behind it. All figures stay upright.

Posture, as fixed offsets: listening, head centred; speaking, the whole figure moves 4 px toward the table centre and the head rises 2 px; addressing one model by name, the head shifts 3 px toward that seat; reading files, the head drops 3 px. Never more than 5 px, never rotated.

Speaker mark: a 2 px ring in the speaker's own seat colour, 5 px outside the head, over a soft halo of the same colour at 22% (the PDF's soft glow, minus the clay), plus the lean-in and its bubble. It is drawn per figure, so it is equally true if seats speak one at a time or several at once.

Vote marks: a 22 px badge at the upper right of every head, separated by a 2 px page-colour gap. Agrees: solid ink disc with a page-colour check. Disagrees: hollow disc (page fill, 2 px ink outline) with an ink cross. Same ink for both; shape carries it. They appear together after a vote and stay until the next round starts. A check means 'in the largest group'; nothing on screen claims how matching is decided.

Not ready or failed: dashed 2 px outline in the seat colour, no fill, name in muted text. A failed seat adds an error badge with an exclamation mark and the caption 'Did not load' beneath it.

Bubbles: HTML above the figure. Surface fill, 1 px border, radius 10, the one soft shadow, padding 10 by 12, Archivo 13/18, two lines at most, 200 to 248 px wide and never wider than the gap to the neighbour, an 8 px tail pointing at its own head. No colour and no name: tail and position say whose it is, and the accessible label carries the name. End seats push theirs outward; one that would touch a neighbour's rises above it. Lines state the claim itself (no 'I', no 'argues that'), so they are true whether a small model or the agent wrote them.

Middle of the table, centred: 'Round 2' and '3:12 left' on one line in tabular figures (14/600); below, one 12 px pip per seat, 8 px apart, filled ink for agree and a 1.5 px line outline for not, with a 2 by 16 px ink mark after the pip that reaches the bar; below, the caption '3 of 5 agree, needs 4' (13/18). When the bar is reached the filled pips and caption turn the agreed colour with a check: '4 of 5 agree'.

Keyboard: each figure is a button in seat order; Enter opens that model's side sheet; focus is a 2 px ink rounded rectangle around the whole figure, distinct from the round speaker ring. T and C switch views; ? opens the shortcuts sheet.

## Chat View
Chat View is the minutes: a sheet of chat-paper replaces the table in the same pinned stage, radius 14. Every value on it has equal red, green and blue (#161616 on #FFFFFF; #EDEDED on #101010; greys #5E5E5E and #A6A6A6), so 'black and white only' is a rule a test can check.

Wide (each column at least 220 px, for example five seats at 1440): one column per model. Each column is headed by the same figure as an ink line drawing: outlined head 44 px with the name inside in chat-text, outlined body with its cut as ink lines. Messages sit in their model's column, each on its own row, so reading downward is still the order they were said. A vote divider runs across all columns.

Narrow, or six and seven seats on a laptop: one thread, 34 em measure. Each message: name 13/600, then 'to Llama' or 'to all' 12 px grey, time into the debate right-aligned in grey tabular figures; text 15/23; file citations as outlined chips, radius 6, 12 px ('invoice-march.pdf p. 2'). Your own step-in messages are right-aligned with no figure.

Vote divider: a thin chat-rule line with centred text, 'Round 2 vote: 3 of 5 agree, needs 4', followed by the same solid and hollow badges, one per model with its name.

Filter: plain text toggles at the top right (All, Qwen, Llama, and so on). The view follows the newest message; scroll up and a 'Jump to newest' button appears.

Why it is still the same app: same Archivo, same figure silhouette and cuts (in ink), same check and cross badges, same radii and spacing, same Table / Chat switch in the same corner. The only thing removed is colour, which is the point: the table shows who, the minutes show what.

## Motion
Library: Motion, as the PDF names it (npm package motion, 14.1.0, MIT, seen on the registry today).

Used:
- Controls: 150 to 200 ms ease-out on press, hover, open and close.
- One orchestrated moment: when a debate starts, the table rises from behind the message box (420 ms ease-out) and each seat fills in from dashed outline to solid (250 ms) when its model reports ready. The order is the real load order, not a staged stagger.
- Posture: lean-in, head turn and head-down ease over 200 ms when the state changes.
- Speaker ring and halo: fade in 200 ms, then hold still.
- Bubbles, fixed by the brief: fade in 250 ms, stay about 8 s, fade out about 1.5 s; a new line from the same model crossfades in place.
- Vote: all badges appear together, 150 ms. Meter pips change over 200 ms.
- Agreement: the table sinks into the message box and the stage folds into its card (400 ms), then the answer fades in (250 ms).
- Table / Chat switch: 200 ms crossfade.

Not used: no loops of any kind (no pulsing status dot, no breathing ring, no bobbing or blinking figures), no hover lift on cards, no entrance animation on pages or list rows, no typing dots at the table.

Reduced motion: every transform and fade is removed. Seats, badges and bubbles simply appear and disappear, the table is simply there, and the ring is static.

## Wording
Plain verbs, sentence case, digits for numbers. The council's vocabulary is five words used the same way everywhere: seat, round, vote, agree, answer. Models are called by their short names. No exclamation marks, no arrows on links, no middle dots between facts (use separate segments or commas), no capitals-only labels, no apologies in errors. A button says what it does: 'Ask' when idle, 'Add to next round' during a debate, and the notice afterwards says 'Added to round 3'.

Six examples:
1. Status pill, three segments with thin dividers: 'Round 2 | 3:12 left | 3 of 5 agree'. Paused: 'Paused in round 2'.
2. Vote divider in Chat View: 'Round 2 vote: 3 of 5 agree, needs 4'.
3. Answer heading, agreed: 'Agreed 4 of 5', with the line under it '3 rounds, 4 min 12 s. Phi disagreed.'
4. Answer heading, no consensus: 'No consensus: 3 of 5', with the line under it 'Time ran out at 5:00. This answer had the most support.'
5. Empty chat: 'Ask a question. Qwen, Llama, Gemma, Mistral and Phi will debate it and send back one answer.' Message box placeholder: 'Ask the council'.
6. A model that failed to load: 'Gemma did not load. The GX10 ran out of memory.' (the second sentence is whatever reason the GX10 reports; this one is an example). Then: 'Start with 4 seats, where all 4 must agree, or change seats.' Buttons: 'Start with 4 seats' and 'Change seats'.

## Review against the skill's generic looks
I worked a look-alike brief first (a group chat with avatars and a progress meter) and compared. Ten things in my first pass were what I would have drawn for any such app. Each was replaced.

1. Figures as pale tinted circles with a coloured outline and small initials. That is the avatar chip of every chat app. Now: one solid colour per figure, the full name knocked out and fitted to the head, a cut in the body, and proportions of a game piece (large head, narrow shoulders), not the user icon.
2. A clay accent and a clay glow on the speaker. That is the first trait on the skill's list. Now: no accent hue at all; controls are ink; the speaker's ring is its own seat colour.
3. A warm paper page, then a sage page. Cream is the listed default; sage is the wellness-app default. Now: chalk #F1F2EE with the green kept very faint, and the only clearly green surface is the table, where the subject puts it.
4. A soft serif for titles. Listed default. Now: no serif titles. The serif is a low-contrast book face used only for the released answer, where it means something.
5. A monospace for timer and counts. Listed tell. Now: Archivo's tabular figures; no numbers font.
6. A humanist sans picked for general friendliness. Now: Archivo, chosen for one job no other candidate did as well: a width axis that fits each name to its head.
7. A progress bar for agreement. A bar implies a percentage; a council of five has five votes. Now: one pip per seat with a mark at the bar to clear.
8. One 12 px radius on everything with the same soft shadow. Listed card-kit tell. Now: radius by role (6, 8, 10, 14, round) and one shadow, on floating things only. The conversation has no cards.
9. Middle dots in the pill and vote divider, an arrow on 'Replay', a small label above the answer. Listed tells. Now: divided segments, commas, a colon; 'Replay the debate'; the heading itself says 'Agreed 4 of 5'.
10. Faces, a gentle idle bob, and a mix of solid and outlined pieces. Faces and bobbing are cute for a week and tiring for a year; outlined pieces read as 'absent'. Now: no faces, no loops, all pieces solid, and dashed outline reserved for 'not ready'.

Also removed in the mirror check: seat colour on bubbles (a coloured edge or name). The tail and position already say whose bubble it is.

## Principles
- Colour belongs to the council. Every hue on screen is a seat, except the agreed and error marks. Controls, focus rings and highlights are ink.
- The name is the face. No eyes, mouths, hats or idle movement. Character comes from fitted lettering, one cut in the body, and posture of 5 px at most.
- One colour per figure. Name and cut are the page showing through, so a seat colour is only allowed if it reaches 4.5:1 against the page in that theme.
- Every state has a shape and a word. Agree is a solid badge with a check, disagree a hollow badge with a cross, not ready a dashed outline, speaking a ring. None relies on colour.
- Sans is talk, serif is the answer. Archivo for everything said, counted or clicked; Literata only for the released answer.
- Motion marks a change, never a state. Nothing loops, nothing pulses, nothing bobs.

## Kept from the PDF
- The frame: slim top bar with the seated council and a status pill (round, time left, agreement); sidebar with New chat, History, Library, Models, Settings; the conversation fills the rest.
- Half-circle table with its flat side toward the viewer; 3 to 7 seats spaced evenly along the curve; each agent a full-circle head holding the short name over a half-circle body in its seat colour; full name on hover.
- A check or cross on every head after each vote, until the next round.
- The middle of the table shows the round, the time left and the meter, with the PDF's wording: '3 of 5 agree, needs 4'.
- Bubble rules: one or two sentences above the talker, two lines at most, never overlapping, end seats push outward; 250 ms in, about 8 s, about 1.5 s out; crossfade in place; reduced motion means appear and disappear.
- Chat View in black and white with greys for names and times; models told apart by name; one column per model when wide, one thread when narrow; vote dividers; outlined citation chips; filter; follows the newest message.
- The small Table / Chat switch at the bottom right while the council works.
- The stage opens in the conversation and folds into a card above the answer; the answer is headed by the vote, rounds and time, with files cited and each dissent in one line.
- Body text at 4.5:1 or better; light and dark themes from the first version; 8 px grid; 150 to 200 ms ease-out on controls; visible focus rings, full tab order, a shortcuts sheet.
- Open-licence variable fonts from Fontsource, bundled with the app; Tailwind driven by tokens, Radix primitives, Motion; SVG table and figures with HTML bubbles.
- Seven seat colours spread around the hue circle, with Agreed and Error as the only other colours.
- Text sizes close to the PDF's: chat 16 to 17, bubbles 13, Chat View 15, labels 14, meta 12, titles 24.

## Changed from the PDF
- Page: warm paper #F5F1EA becomes chalk #F1F2EE (dark #1F1E1B becomes #151B18). No cream.
- Accent: clay #C4694D is removed. The Ask button, focus ring and active switch are ink. There is no accent hue.
- Speaker mark: clay glow becomes a ring and soft halo in the speaker's own seat colour, plus a 4 px lean toward the table.
- Seat colours: seven muted mid-tones become seven deep colours in light and pale ones in dark, each computed to carry its own name at 4.5:1. New hues (teal, indigo, ochre, claret, slate, rust, violet) and a new order chosen for neighbour contrast.
- Each seat gains a cut in its body (plain, band, collar, sash, placket, yoke, braces) so colour is never the only signal even when one model fills two seats.
- Names in heads: fixed 11 px becomes fitted 11 to 17 px using a width axis.
- Fonts: Fraunces, Source Sans 3 and JetBrains Mono become Archivo and Literata. The serif moves from titles to the released answer. Numbers use Archivo's tabular figures; code blocks use the Mac's own monospace.
- Agreement meter: a bar becomes one pip per seat with a mark at the number needed.
- Table: a border-coloured outline becomes a green-cloth fill with an edge at 3:1 or better, and its flat side is joined to the message box.
- Borders: the 1.2:1 hairline is kept only as decoration. A new line token at 3:1 or better draws every edge that carries meaning.
- Radius: 12 and 8 everywhere becomes radius by role (6, 8, 10, 14, round). Shadows only on floating things.
- Wording: the middle dots in the pill and vote divider become segments, commas and a colon. The Send button is labelled 'Ask', then 'Add to next round' during a debate.
- Chat View values: #111111 on #FFFFFF and #F2F2F2 on #0E0E0E become #161616 on #FFFFFF and #EDEDED on #101010, under the rule that every Chat View value has equal red, green and blue.
- Agreed and Error: #5E8C6A and #B5483E become #1A6B42 and #A32A1C (dark #74C998 and #F0897A) so they pass as text and stay clear of the seat colours.
- Motion: the PDF's 150 to 200 ms and bubble timings stay; added is one start-of-debate moment (the table rises from the message box) and a ban on loops.

## Contrast (designer's computed figures)

| Pair | Theme | Ratio | Needed | Pass |
|---|---|---|---|---|
| Text #17201C on page #F1F2EE | light | 14.82 | 4.5 | yes |
| Text on surface #FBFBF9 (bubbles, message box, cards) | light | 16.09 | 4.5 | yes |
| Text on table #DEE5DD (round, time, meter caption) | light | 12.98 | 4.5 | yes |
| Text on hover #E6E9E3 | light | 13.6 | 4.5 | yes |
| Muted text #535E58 on page | light | 6.01 | 4.5 | yes |
| Muted text on surface (placeholder, meta) | light | 6.52 | 4.5 | yes |
| Muted text on table | light | 5.26 | 4.5 | yes |
| Muted text on hover | light | 5.51 | 4.5 | yes |
| Button label #F1F2EE on ink button #1D2A24 (also the check in a solid vote badge) | light | 13.26 | 4.5 | yes |
| Button label on ink button hover #2C3B33 | light | 10.49 | 4.5 | yes |
| Agreed text #1A6B42 on page | light | 5.79 | 4.5 | yes |
| Agreed text on surface | light | 6.28 | 4.5 | yes |
| Agreed text on table | light | 5.07 | 4.5 | yes |
| Error text #A32A1C on page | light | 6.43 | 4.5 | yes |
| Error text on surface | light | 6.98 | 4.5 | yes |
| Chat View text #161616 on paper #FFFFFF | light | 18.1 | 4.5 | yes |
| Chat View grey #5E5E5E (names, times) on paper | light | 6.48 | 4.5 | yes |
| Chat View rule and chip outline #8C8C8C on paper (graphic) | light | 3.36 | 3 | yes |
| Line #77827B on page (table edge, input outline; graphic) | light | 3.55 | 3 | yes |
| Line on surface (graphic) | light | 3.85 | 3 | yes |
| Line on table (empty pips; graphic) | light | 3.11 | 3 | yes |
| Ink marks #1D2A24 on page (vote badge, focus ring, active switch; graphic) | light | 13.26 | 3 | yes |
| Ink marks on table (filled pips, needs mark; graphic) | light | 11.61 | 3 | yes |
| Ink marks on surface (graphic) | light | 14.39 | 3 | yes |
| Agreed pips on table (graphic) | light | 5.07 | 3 | yes |
| Error badge on page (graphic) | light | 6.43 | 3 | yes |
| Seat 1 teal #005960: name in head (page colour on fill), figure and speaker ring against page | light | 7.19 | 4.5 | yes |
| Seat 2 indigo #23246E: name in head, figure and ring against page | light | 12.06 | 4.5 | yes |
| Seat 3 ochre #8C6205: name in head, figure and ring against page | light | 4.83 | 4.5 | yes |
| Seat 4 claret #641530: name in head, figure and ring against page | light | 11.04 | 4.5 | yes |
| Seat 5 slate #656B78: name in head, figure and ring against page | light | 4.75 | 4.5 | yes |
| Seat 6 rust #8A2C06: name in head, figure and ring against page | light | 7.64 | 4.5 | yes |
| Seat 7 violet #6C379B: name in head, figure and ring against page | light | 7.03 | 4.5 | yes |
| Seat 1 teal against table, the weakest background a figure touches (graphic) | light | 6.3 | 3 | yes |
| Seat 2 indigo against table (graphic) | light | 10.56 | 3 | yes |
| Seat 3 ochre against table (graphic) | light | 4.23 | 3 | yes |
| Seat 4 claret against table (graphic) | light | 9.67 | 3 | yes |
| Seat 5 slate against table (graphic) | light | 4.16 | 3 | yes |
| Seat 6 rust against table (graphic) | light | 6.69 | 3 | yes |
| Seat 7 violet against table (graphic) | light | 6.16 | 3 | yes |
| Decorative, no requirement: border #D3D8D1 on page | light | 1.29 | 1 | yes |
| Decorative, no requirement: table fill on page (the table's edge is the 3.55 line above) | light | 1.14 | 1 | yes |
| Text #E6EBE7 on page #151B18 | dark | 14.48 | 4.5 | yes |
| Text on surface #1C2420 (bubbles, message box, cards) | dark | 13.16 | 4.5 | yes |
| Text on table #213029 (round, time, meter caption) | dark | 11.45 | 4.5 | yes |
| Text on hover #242D28 | dark | 11.75 | 4.5 | yes |
| Muted text #9CA9A2 on page | dark | 7.16 | 4.5 | yes |
| Muted text on surface (placeholder, meta) | dark | 6.51 | 4.5 | yes |
| Muted text on table | dark | 5.67 | 4.5 | yes |
| Muted text on hover | dark | 5.81 | 4.5 | yes |
| Button label #151B18 on light ink button #E6EBE7 (also the check in a solid vote badge) | dark | 14.48 | 4.5 | yes |
| Button label on button hover #FFFFFF | dark | 17.47 | 4.5 | yes |
| Agreed text #74C998 on page | dark | 8.78 | 4.5 | yes |
| Agreed text on surface | dark | 7.98 | 4.5 | yes |
| Agreed text on table | dark | 6.94 | 4.5 | yes |
| Error text #F0897A on page | dark | 7.13 | 4.5 | yes |
| Error text on surface | dark | 6.48 | 4.5 | yes |
| Chat View text #EDEDED on paper #101010 | dark | 16.25 | 4.5 | yes |
| Chat View grey #A6A6A6 (names, times) on paper | dark | 7.82 | 4.5 | yes |
| Chat View rule and chip outline #6E6E6E on paper (graphic) | dark | 3.73 | 3 | yes |
| Line #74817A on page (table edge, input outline; graphic) | dark | 4.3 | 3 | yes |
| Line on surface (graphic) | dark | 3.9 | 3 | yes |
| Line on table (empty pips; graphic) | dark | 3.4 | 3 | yes |
| Ink marks #E6EBE7 on page (vote badge, focus ring, active switch; graphic) | dark | 14.48 | 3 | yes |
| Ink marks on table (filled pips, needs mark; graphic) | dark | 11.45 | 3 | yes |
| Ink marks on surface (graphic) | dark | 13.16 | 3 | yes |
| Agreed pips on table (graphic) | dark | 6.94 | 3 | yes |
| Error badge on page (graphic) | dark | 7.13 | 3 | yes |
| Seat 1 teal #A1E8E5: name in head (page colour on fill), figure and speaker ring against page | dark | 12.64 | 4.5 | yes |
| Seat 2 indigo #789AFF: name in head, figure and ring against page | dark | 6.54 | 4.5 | yes |
| Seat 3 ochre #FAD786: name in head, figure and ring against page | dark | 12.59 | 4.5 | yes |
| Seat 4 claret #DE6365: name in head, figure and ring against page | dark | 5.06 | 4.5 | yes |
| Seat 5 slate #ABB6B5: name in head, figure and ring against page | dark | 8.4 | 4.5 | yes |
| Seat 6 rust #F49A5B: name in head, figure and ring against page | dark | 8 | 4.5 | yes |
| Seat 7 violet #9D85B2: name in head, figure and ring against page | dark | 5.35 | 4.5 | yes |
| Seat 1 teal against table, the weakest background a figure touches (graphic) | dark | 10 | 3 | yes |
| Seat 2 indigo against table (graphic) | dark | 5.18 | 3 | yes |
| Seat 3 ochre against table (graphic) | dark | 9.96 | 3 | yes |
| Seat 4 claret against table (graphic) | dark | 4 | 3 | yes |
| Seat 5 slate against table (graphic) | dark | 6.64 | 3 | yes |
| Seat 6 rust against table (graphic) | dark | 6.33 | 3 | yes |
| Seat 7 violet against table (graphic) | dark | 4.23 | 3 | yes |
| Decorative, no requirement: border #2D3832 on page | dark | 1.43 | 1 | yes |
| Decorative, no requirement: table fill on page (the table's edge is the 4.30 line above) | dark | 1.26 | 1 | yes |

## Risks
- The figure is, in outline, the generic 'user' icon. If the proportions drift (smaller head, wider shoulders) or the name shrinks, the whole direction collapses into a default avatar. The geometry and the fit rule need a unit test and a screenshot check.
- In light theme indigo (L* 19) and claret (L* 22) are both very dark and can look near-black at small sizes. The cut and name still separate them, but this is the pair to look at first in the study.
- Ochre (4.83:1) and slate (4.75:1) pass with little to spare in light theme. Any later nudge to the page or those two colours must re-run the contrast test.
- Fitted names give heads different letter sizes (13 to 17 px). With seven seats that could look uneven rather than characterful. Fallback: one size per council, set by its longest name.
- No accent colour may make the app feel austere, or the main action less obvious, to an owner who chose a warm clay look. Fallback: tint the ink button toward the table's green; do not add a new hue.
- Sans for talk and serif for the answer could read as two apps stitched together. Fallback: answers in Archivo 16/26; nothing else changes.
- Chat View is a pure white (or pure black) sheet inside a chalk app; the switch may flash. The 200 ms crossfade softens it, but only a real screen will tell.
- Green is used three ways: the cloth, the agreed mark and, nearby in hue, the teal seat. Agreed always carries a check and the word, but it is the likeliest place for a mixed signal.
- Seven seats on a 13-inch laptop: heads 50 px, names down to 11 px, bubbles about 180 px wide, which holds roughly 60 characters over two lines. Whether summaries can be that short depends on the summariser, which is not yet decided.
- Posture offsets of 2 to 4 px may be too subtle to notice, and anything larger starts to look cute. The 5 px ceiling is a guess until it is seen moving.
- In dark theme ochre and teal (L* 87) are much brighter than claret and violet (L* 57 to 59), so two seats may seem to shout. Watch for it in the dark study.
- Code blocks rely on the Mac's built-in monospace. If the bundling rule is read strictly, add @fontsource-variable/jetbrains-mono 5.3.0 (already verified in the previous plan) for code blocks only.
- The width figures for condensed names are estimates: I measured Archivo at normal width and scaled. The builder must measure in the browser.
- The PDF tool on this Mac could not render pages. I read all 16 pages of text and decoded the three screen wireframes in memory as coarse block pictures, enough for layout but not for the small labels inside them.

## Questions the designer left for Lucas
- The figures have no eyes or mouths in this direction: the model's name is the face. Is that what you want, or were you picturing faces or expressions? It changes the whole direction, so it is worth saying before a study is drawn.
- This direction has no accent colour at all. Buttons and highlights are dark ink, so colour only ever means a council member. Are you content to lose the clay accent completely?
- When one model fills two seats, what should each head say: the role you gave it (such as Skeptic), or the model name with a number (Qwen 1, Qwen 2)? The name is lettered inside the head, so it has to be about 8 characters or fewer.

## Designer's own study brief (SUPERSEDED by docs/direction/study-brief.md)
Build one self-contained HTML file (inline CSS and inline SVG, no script except a theme toggle) showing this direction in light, then in dark, each 1440 px wide. Use this direction's tokens, seat colours, cuts and type scale exactly. Embed Archivo (width and weight axes) and Literata (optical size) as base64 woff2; if you cannot, load them from the Fontsource CDN for the study only and say so in a footer line.

Scene 1, Table View mid-debate: top bar, sidebar, one question, then the stage. Five figures (Qwen, Llama, Gemma, Mistral, Phi in seats 1 to 5) around the cloth table, radius 320, heads 60 px, names fitted. Gemma is speaking: ring, halo, leaned in, bubble at full strength. Llama's bubble is fading at 40%. No vote badges. Table centre: Round 2, 3:12 left, five pips with three filled, the mark after pip 4, '3 of 5 agree, needs 4'. Message box joined to the flat side; Table / Chat switch bottom right.

Beside it, at half size: the same five heads just after a vote, three solid checks and two hollow crosses.

Scene 2, the released answer: the folded card with five small figures and badges, 'Agreed 4 of 5', a 120-word answer in Literata, two file chips, Phi's one-line dissent.

Bubble lines state the claim itself. No faces, gradients, middle dots or capitals-only labels. Screenshot both themes with Playwright as the webapp-testing skill describes (static file), read the images, and fix what differs from this brief before returning.
