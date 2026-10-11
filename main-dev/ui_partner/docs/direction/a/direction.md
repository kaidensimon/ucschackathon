# Direction A: The Lit Table

> A pale, quiet room with one dark wooden half-round table, where a small warm lamp comes on in front of whichever model is speaking.

This is the design lead's written direction (frontend-design skill process). Read `corrections.md` beside it: corrections win.

## Grounding
Subject: one person presiding over a small council that argues and then answers. Audience: the owner alone, reading on his Macs. Job: let him follow the debate at a glance and trust the released answer.

What is borrowed from real deliberation rooms, and why:
- The horseshoe table seen from the chair. In a chamber the presiding seat faces the open side of the horseshoe. The brief's half-circle with its flat side toward the viewer is that view, so the owner's message box is docked to the flat edge: he sits at the table.
- The light at the seat. Delegate microphones and desk lamps show who is speaking by a light at that seat, not by a pointer. Every seat gets a small lamp on the table: hollow when quiet, solid and glowing when speaking. Any number can be lit, so the mock is truthful whether seats speak one at a time or together.
- Wooden table, leather chairs. The table top is flat walnut with an oak rim. The seven seat colours are upholstery leathers: olive, navy, oxblood, violet, petrol, mauve, slate.
- Numbered seats and nameplates. Name in the head, seat number on the chair back. The PDF allows one model in two seats, so the number is sometimes the only thing that tells two seats apart.
- Ballots. Athenian jurors voted with bronze discs that were solid or hollow. Votes here are solid check discs and hollow cross discs, with no colour, so they work unchanged in black-and-white Chat View.
- Plaster walls by day, the same room in the evening. The page is cool plaster, not paper. Dark theme is the room after dark, where the lamps do more work.
- Lettering. Besley is a revival of Robert Besley's 1845 Clarendon, the sturdy slab of notices and reference-book headings. Atkinson Hyperlegible Next was drawn by the Braille Institute so similar characters cannot be confused (I, l, 1, O, 0), which is what a nameplate needs and what model names are full of.

Refused as costume: green baize, wood grain, brass ornament, gavels, scales, columns, courtroom wording.

## Palette

| Token | Light | Dark | Role |
|---|---|---|---|
| page (plaster) | `#E9ECE8` | `#1C201F` | IDENTITY. App background. Cool grey-green, deliberately not cream. |
| surface (paper) | `#F9FAF7` | `#262B29` | Cards, bubbles, message box, the answer. Also the lettering colour on seats in light theme. |
| sunken | `#DDE2DC` | `#303634` | Sidebar, top bar, hover and selected rows. Separation by tone, not by lines. |
| outline | `#717A75` | `#808B86` | The only line colour. Inputs, bubbles, cards you can click. 3:1 or better on page, surface and sunken. |
| ink | `#1D2427` | `#E9ECE7` | IDENTITY. Text, the main button fill, vote marks, the inner focus ring. |
| on-ink | `#F9FAF7` | `#1C201F` | Label on the main button. |
| muted | `#55605C` | `#A5AEA9` | Meta, placeholders, times. |
| table (walnut) | `#4A3628` | `#5A4130` | IDENTITY. The table top and nothing else. |
| table-rim (oak) | `#B58A55` | `#C49C66` | IDENTITY. 3 px rim stroked inside the curved edge. Required in dark, where walnut alone is 1.75:1 against the page. |
| on-table | `#F5EFE6` | `#F6F0E6` | Round, time, meter caption and meter discs on the table. |
| on-table-muted | `#D9CAB5` | `#DDCEB9` | Secondary text on the table and unlit lamp rings. |
| lamp | `#F4B740` | `#F6C356` | IDENTITY, the bold one. Lit seat lamp and its pool of light, the in-session dot, the outer band of the focus ring. Never on buttons, links or headings. In light theme it is 1.51:1 against the page, so it is only drawn on walnut or with an ink keyline. |
| agreed | `#2A6A43` | `#8CCB9C` | Only once the needed number of seats agree: the answer heading mark and the status pill. |
| agreed-on-table | `#9AD3A8` | `#A6DBB2` | Meter discs and caption on the table once the needed number is reached. |
| error | `#A52A1A` | `#FF8B73` | A model that failed to load or answer. Never used for disagreement. |
| seat-lettering | `#F9FAF7` | `#1C201F` | Name in the head, seat number on the body, keyline round vote marks. |
| chat-view-bg | `#FFFFFF` | `#0E0E0E` | Chat View sheet. PDF value, kept. |
| chat-view-ink | `#111111` | `#F2F2F2` | Chat View text and solid vote discs. PDF value, kept. |
| chat-view-grey | `#5E5E5E` | `#A6A6A6` | Chat View names, addressed-to and times. |
| chat-view-rule | `#767676` | `#8A8A8A` | Chat View vote divider and citation chip outline. |

## Seats
Four signals, in this order of importance. (1) The model's short name inside the head. (2) The seat number on the body, and the same number wherever the seat appears: top bar chips, Chat View column heads, the side sheet. It is the only signal that survives when one model fills two seats. (3) Fixed place: seat 1 is the left end of the curve, numbers run clockwise. (4) Colour: in light theme a deep leather colour with paper-coloured lettering; in dark theme a pale version with dark lettering. Head and body are solid seat colour; no tints, no outlines.

Computed, not guessed. Every name is 5.0:1 or better on its seat (light 5.00 to 13.60, dark 5.31 to 11.42). Every figure is 4.39:1 or better against the page. Smallest distance between any two seats under simulated colour-vision deficiency (Machado 2009 matrices, OKLab distance x100; about 2 is just noticeable): light theme 9.8 normal, 8.9 protanopia, 9.0 deuteranopia, 6.9 tritanopia; dark theme 7.9, 6.8, 6.6, 7.1. With the usual five seats the smallest combined distance is 9.2 light and 9.4 dark. For comparison, the PDF's starting seats score 1.6 under deuteranopia (sage and rose merge). Each seat is also kept 10 or more away from the error and agreed colours and 14 or more from the lamp, so no seat looks failed, agreed or lit. A seat changes from deep to pale between themes, so identity across themes is the number and name, not the hue.

| Seat | Light | Dark |
|---|---|---|
| 1 Olive | `#4A4A04` | `#859D52` |
| 2 Navy | `#1E3572` | `#AEC9FD` |
| 3 Oxblood | `#580D03` | `#E7B2BB` |
| 4 Violet | `#685DA3` | `#A8A1EB` |
| 5 Petrol | `#005366` | `#24A5AB` |
| 6 Mauve | `#8A616C` | `#CC7B8D` |
| 7 Slate | `#262E3A` | `#D3D7E1` |

## Typefaces

| Role | Family | Package | Why |
|---|---|---|---|
| Titles only. Page, panel, sheet and dialog titles 24/30, weight 500. The answer's vote heading 20/26, weight 500. App name in the top bar 17/24, weight 600. Sentence case, letter-spacing -0.01em, tabular figures on. Never used for names, labels, running text or list rows. | Besley | `@fontsource-variable/besley` 5.3.0 (OFL-1.1) | A Clarendon: sturdy, low-contrast, friendly without being soft. It keeps the owner's wish for a serif on titles but is unmistakably not Fraunces and not a newspaper serif. Checked today: the package exists on npm; variable weight 400 to 900, upright and italic (Fontsource API); the shipped latin file carries the tnum feature. It is wide and dark, which is why weight drops from the PDF's 600 to 500 and why it is kept to short titles. |
| Everything read or pressed. Chat text and answers 16/26, weight 400 (bold 650), column 600 px at most, about 75 characters. Bubble text 13/18, weight 450, two lines. Names in heads 12/12, weight 650, mixed case, 7 characters at most (11 px and 6 characters in 48 px heads on a narrow stage). Seat number on the body 13/13, weight 700. Chat View messages 15/23, weight 400. Labels and buttons 14/20, weight 550. Small meta 12/16, weight 400, muted. Numbers in the same face with tabular figures: table timer 22/26 weight 600, status pill 13/20 weight 550, counts 13 weight 400. | Atkinson Hyperlegible Next | `@fontsource-variable/atkinson-hyperlegible-next` 5.3.0 (OFL-1.1) | Drawn so I, l, 1 and O, 0 cannot be confused, which matters for model names at 12 px inside a circle, and it is calm at 16 px for long answers. Checked today: the package exists on npm; variable weight 200 to 800, upright and italic. I read the shipped font file: digits are proportional by default (widths 407 to 648 per 1000) but the tnum feature is present, so every changing number must set font-variant-numeric: tabular-nums. That removes the need for JetBrains Mono, so there is no third family. Measured widths: 'Qwen' at 12 px weight 600 is 31 px, and a 56 px head has about 46 px of usable width. Code blocks in answers use the Mac's own fixed-width face through ui-monospace (nothing bundled, works offline); if code should be bundled too, the matching @fontsource-variable/atkinson-hyperlegible-mono 5.3.0 (OFL-1.1) exists. |

## Layout
**Concept: you have the chair.** During a debate the table's flat side rests on the top edge of your message box, so the council faces you and what you type goes onto the table.

**Alignment.** All text is left-aligned. The conversation column and the stage share one centre axis in the main area. Only the contents of the middle of the table are centred, on that same axis.

**Fixed frame, kept.** Slim top bar, sidebar (New chat, History, Library, Models, Settings), conversation fills the rest, Table / Chat switch bottom right, stage folds into a card above the answer.

**What I do inside it.**
- Top bar (48 px, sunken tone): app name, then the seated council as numbered nameplate chips (a 16 px seat-colour disc holding the seat number, then the short name), then the status pill at the right.
- Sidebar (232 px, sunken tone, no dividing line): New chat is the one ink button. Theme and Shortcuts at the foot.
- Conversation: reading column 600 px. Stage up to 760 px wide. Message box 760 px, the same width as the table's flat side.
- No shadows and no decorative lines anywhere. Tone separates areas; the outline token is used only where a boundary must be seen.
- Corners by material: paper things (bubbles, cards, chips) 4 px; controls 8 px; furniture (table, heads, bodies, lamps, vote discs) truly round; the status pill fully round.
- Spacing on the 8 px grid: 8, 16, 24, 32, 48.

| Part | Size |
|---|---|
| Table radius | 34% of stage width, 240 to 340 px |
| Stage height | radius + 190 px (figures 100, two bubble rows 90) |
| Head / body | 56 px circle / 76 x 38 px half-disc (48 and 64 x 32 when the radius is under 260) |
| Below 1100 px wide | sidebar becomes a slide-over, chips show discs only, Chat View becomes one thread |

**1. Main screen during a debate (1440 wide)**

```
+------------------------------------------------------------------------------------------------+
| Council   (1)Qwen (2)Llama (3)Phi (4)Gemma (5)Mistral      ( * Round 2   3:12 left   3 of 5 agree ) |
+------------+-----------------------------------------------------------------------------------+
| [New chat] |                                                                                   |
|            |        You                                                                        |
| History    |        Should we renew the Harbour Street lease, and for how long?                |
| Library    |        [lease-2024.pdf, 14 pages]  [rent-review.xlsx]                             |
| Models     |                                                                                   |
| Settings   |                      .-----------------------------.                              |
|            |                      | Renew for three years, with |                              |
|            |                      | a break clause at 18 months.|                              |
|            |                      '--------------v--------------'                              |
|            |               (Llama)            ( Phi )            (Gemma)                       |
|            |                [ 2 ]             [  3  ]             [ 4 ]                        |
|            |                          .-===================-.                                  |
|            |      (Qwen)           .-'   o      (*)      o   '-.           (Mistral)           |
|            |       [ 1 ]         .'                             '.           [ 5 ]             |
|            |                    /  o          Round 2          o  \                            |
|            |                   |             3:12 left             |                           |
|            |                   |    @ @ @ o | o   3 of 5 agree, needs 4                        |
|            |                   +-----------------------------------+                           |
|            |                   | Add to the debate.   [Pause] [Stop] [Send] |                  |
|            |                   +-----------------------------------+                           |
| Light Dark |                                                                                   |
| Shortcuts  |                                                              [ Table | Chat ]     |
+------------+-----------------------------------------------------------------------------------+
```

**2. Table View, five seats, round 2, after the round 1 vote**

```
                                .------------------------------.
                                | Renew for three years, with  |
                                | a break clause at 18 months. |
                                '--------------v---------------'
            . - - - - - - - - - .          .-------.
            : The rent review    :         (  Phi   )v          (bubble 2 is fading out)
            : caps rises at 4%.  :          '-------'
            ' - - - - v - - - - '           [   3   ]
                 .-------.          ___.---=========---.___          .-------.
                ( Llama   )v     .-'          (*)          '-.      ( Gemma   )x
                 '-------'     .'       lit lamp and pool     '.     '-------'
                 [   2   ]    /    o                       o    \    [   4   ]
                             /                                   \
      .-------.             |               Round 2               |             .-------.
     (  Qwen   )v           |              3:12 left              |            ( Mistral )x
      '-------'             |  o          @ @ @ o | o          o  |             '-------'
      [   1   ]             |        3 of 5 agree, needs 4        |             [   5   ]
                            +=====================================+
                            |  your message box, on the flat side |

 (name) head in solid seat colour     [n] body carrying the seat number
 v solid check disc    x hollow cross disc    o unlit lamp ring    (*) lit lamp with its pool
 @ solid meter disc    | notch at the number needed    === oak rim, curved edge only
```

**Scenes the Phase 1 mocks need so they stay truthful under the open back-end questions:** one seat speaking; two seats speaking at once (two lamps, two bubbles, no overlap); just after a vote; one seat that failed to load; three seats and seven seats; the folded card with the released answer; No consensus.

**Where this would live (nothing exists yet):** /Users/lucasta/projects/gx10-council/ui/src/styles/tokens.css (every value above), /Users/lucasta/projects/gx10-council/ui/src/components/table/ (table, figure, lamp, vote mark, bubble layout pass), /Users/lucasta/projects/gx10-council/ui/src/components/chatview/, /Users/lucasta/projects/gx10-council/ui/src/app/AppFrame.tsx. References read: /Users/lucasta/Downloads/GX10 Cluster UI Plan.pdf, /Users/lucasta/.claude/plugins/marketplaces/anthropic-agent-skills/skills/frontend-design/SKILL.md, /Users/lucasta/.claude/plans/distributed-puzzling-zephyr.md.

## The one bold element
The lit table. One solid walnut half-circle in an otherwise pale, lineless room, and a small amber lamp that comes on, with a soft pool of light on the wood, in front of whichever seat is speaking. It is the only dark mass, the only warm colour and the only glow in the app. Everything around it stays quiet: no accent colour on controls (the main button is ink), no shadows, no decorative lines, no second glow.

## Table View
**Table.** One SVG. A half-disc in flat walnut, flat side down and resting on the message box. A 3 px oak rim is stroked inside the curved edge only. No texture, no gradient, no shadow. In light theme the walnut itself separates from the page (9.53:1). In dark theme walnut is only 1.75:1 against the page, so the rim (6.50:1) is the boundary and is required.

**Seats.** For N seats, seat i sits at angle 180 - (i - 0.5) x 180 / N degrees (five seats: 162, 126, 90, 54, 18). Figure centre is 44 px outside the rim. Figures are always upright and never touch the table: an 8 px gap of page colour stays between body and rim, because the dark seats (oxblood, slate, olive) are close to walnut.

**Figures.** Head: 56 px circle in solid seat colour, short name centred, 12 px weight 650, mixed case. Body: 76 x 38 px half-disc in the same colour, 3 px below the head, carrying the seat number at 13 px weight 700. Full model name in a tooltip. Click or Enter opens the side sheet.

**Speaker mark: the lamp.** Each seat has a lamp on the table, 30 px inside the rim on the seat's own angle. Quiet: a 10 px hollow ring in on-table-muted. Speaking: a 12 px solid amber disc with a pool of light, a radial fade from 45% amber to nothing, 110 px across, clipped to the table. Lit lamp against walnut is 6.32:1 light, 5.75:1 dark. Signals other than colour: hollow becomes solid, the pool, the bubble above the seat, and 'speaking' in the accessible name. Several lamps can be lit at once. There is no ring or glow on the head; that was cut so the table holds the only light.

**Vote marks.** After each vote an 18 px disc sits at the upper right of every head, with a 2 px keyline in the seat-lettering colour, until the next round starts. With the leading answer: solid ink disc, check cut out. Not with it: hollow disc with ink ring and ink cross. No green, no red.

**Failed seat.** Dashed outline figure with no fill, name in muted text, an error mark at the upper right, and the plain sentence in the conversation.

**Bubbles.** HTML, placed by a layout pass. Paper surface, 1 px outline, 4 px corners, 8 x 12 px padding, 13/18 text, two lines then an ellipsis. Width is the smaller of 240 px and the seat gap minus 16 px. A small tail points at the head, 10 px above it. End seats push theirs outward; a bubble that would touch a neighbour rises above it. No credit line on the bubble, since who writes summaries is undecided.

**Middle of the table.** Centred on the table's axis, starting 28 px above the flat side, top to bottom: 'Round 2' (14 px, on-table-muted); '3:12 left' (22 px weight 600, tabular); the meter; '3 of 5 agree, needs 4' (14 px weight 550). The meter is a row of N discs, 12 px each: solid for seats backing the leading answer, sorted first, hollow rings for the rest, and a 2 x 20 px notch after the number needed. Before the first vote: all hollow, 'No vote yet, 4 of 5 needed'. When the needed number is reached, discs and caption switch to agreed-on-table and the caption reads '4 of 5 agree'. The timer is kept at 22 px on purpose: the meter is the main thing, not a big number.

## Chat View
**The written record of the same room.** A sheet in pure white with #111111 text (dark: #0E0E0E with #F2F2F2) set inside the stage; the app frame around it keeps its plaster tone. No walnut, no lamp, no seat colours.

**Wide stage (1100 px or more):** one column per seat in seat order, 24 px gutters and no vertical rules. Each column is headed by a 22 px solid black disc with the seat number in white, the short name at 14 px weight 650, and the full model name in grey at 12 px. Messages sit on a shared time grid, so reading across shows the order. **Narrow:** one thread, each message headed by the same disc and name.

**Message.** Meta line in grey: name, 'to all' or 'to Llama', and the time into the debate right-aligned in tabular figures. Text 15/23. Citations as outlined chips with 4 px corners, such as 'lease-2024.pdf, p. 12' or 'council.md L7'. A message being written has a 2 px black bar at its left and the grey word 'writing'.

**Votes.** A thin grey rule across the sheet with centred text, 'Round 1 vote: 2 of 5 agree, needs 4'. Under it each column head shows that seat's mark, the same solid check disc or hollow cross disc as on the table. In the single thread the line below reads 'Agreed: Qwen, Phi. Not yet: Llama, Gemma, Mistral.'

**Also kept from the PDF:** a filter for one model, and the view follows the newest message until you scroll up.

**Why it still feels like the same app.** Same two typefaces and sizes, same seat numbers, same vote discs (they were designed without colour for this reason), same 4 px paper corners, same frame, top bar and switch around it, and the same folded card and answer afterwards. To avoid the newspaper look, the only rule on the sheet is the vote divider; columns are separated by space.

## Motion
**Used.**
- Bubbles (fixed by the brief): fade in 250 ms, hold about 8 s, fade out 1.5 s. A new summary from the same seat crossfades in place over 250 ms. With reduced motion they appear and disappear.
- Lamp: lights over 250 ms, goes out over 600 ms, steady while lit.
- Seats at start-up: each figure fades in over 300 ms as its model becomes ready, opacity only.
- Vote marks: all appear together over 200 ms and clear together when the next round starts. Meter discs fill over 200 ms.
- The one orchestrated moment, agreement, about 900 ms in total: marks land, the meter turns to the agreed colour, the lamps go out, the stage folds into its card (height, 320 ms ease-out), the answer fades in over 250 ms.
- Table / Chat switch: 200 ms crossfade. Controls: 150 ms, colour and opacity only.

**Not used.** No pulsing or looping of any kind, no hover lifts, no entrance animation on messages or sections, no shimmer placeholders, no typing dots, no animated timer digits, nothing moving in Chat View except following the newest message.

**Reduced motion.** Every fade becomes an instant change and the fold becomes an instant swap.

**Tools.** Motion for bubble enter and exit and for the fold; plain CSS transitions for the rest.

## Wording
Plain words, sentence case, digits for numbers, no exclamation marks. One word per thing, used everywhere: seat, round, vote, agree, disagree, speaking. 'Speaking', not 'has the floor'; 'Agreed', not 'Consensus reached' or 'Motion carried'. Errors say what happened and what to do next, with no apology. No middle dots between facts, no arrows on buttons, no all-caps labels.

1. Status pill, three parts set apart by space: 'Round 2   3:12 left   3 of 5 agree'. Other states: 'Seating the council, 3 of 5 ready'; 'Paused in round 2, 3:12 left'; 'Agreed, 4 of 5'.
2. Vote divider: 'Round 1 vote: 2 of 5 agree, needs 4'.
3. Answer heading, agreed: 'Agreed, 4 of 5', and under it '3 rounds, 4 min 12 s. Mistral disagreed; its note is below.'
4. Answer heading, no agreement: 'No consensus. 3 of 5 backed this answer', and under it 'Time ran out at 5 min. Gemma and Mistral disagreed; their notes are below.'
5. Empty chat: 'What should the council settle?' and under it 'Five models are seated. They read only your files, debate in rounds, and release one answer when 4 of 5 agree or after 5 minutes.'
6. A model that failed to load (example numbers): 'Gemma did not load. It needs 9 GB and the GX10 has 6 GB free.' Buttons: 'Seat a smaller model' and 'Go on with 4 seats'. Note under them: 'With 4 seats, all 4 must agree.'

Also: message box during a debate, 'Add to the debate. It reaches the council at the start of the next round.' Folded card button: 'Replay the debate'.

## Review against the skill's generic looks
I wrote a first plan, then checked it against the skill's five generic looks and against what I would produce for any 'council' or 'courtroom' prompt. Thirteen things changed.

1. Green baize table became flat walnut. A green felt half-circle with players on the curve and the viewer at the flat side is a blackjack table, and green with brass and a serif is the stock answer for anything legal.
2. Brass accent on buttons, links and focus became no general accent. One bright accent on everything is the generic pattern. Buttons are ink; amber is light only, and only where something is live.
3. Serif reading text for answers became sans. On a pale page a serif answer lands next to the cream-and-serif look the skill names first, and next to Claude's own app. The page also moved from cream to cool plaster.
4. Nameplates in spaced capitals became mixed case. All-caps labels are a listed tell, and capitals make 'l' and 'I' harder to tell apart, not easier.
5. A monospace for numbers was dropped. Monospace for small data is a listed tell. I checked that the text face ships tabular figures.
6. Middle dots in the status pill and vote divider became words and spacing.
7. One corner radius everywhere became radius by material: paper 4, controls 8, furniture round.
8. Soft grey shadows under cards became no shadows at all.
9. Hairline rules, including between Chat View columns, became no decorative lines. That is the broadsheet look. The PDF's hairline was also about 1.2:1, too faint to be a real boundary. One outline token at 3:1 or better replaces it.
10. A large timer with a small label in the middle of the table became a 22 px timer with the meter as the main thing. Big number plus small label is the default hero.
11. Courtroom phrases ('has the floor', 'motion carried') became plain words.
12. Removed one accessory, twice: a brass inlay line inside the table edge, and a glow around the speaker's head. The lamp on the table is now the only light.
13. Dark theme is a lifted green-grey (#1C201F), not near-black with a bright accent. Chat View's #0E0E0E stays because the brief fixes it.

Kept on purpose after checking: seat numbers. Numbering is a tell when content is not a sequence, but seats are real fixed places, and a number is the only thing that separates two seats running the same model.

## Principles
- One light in the room. Lamp amber appears only where something is live: a speaking seat, the in-session dot, keyboard focus. Never on buttons, links, headings or decoration, and it never pulses.
- Wood is for the table only. Walnut and oak never appear on cards, bars or buttons. Everything else is plaster, paper and ink.
- Corners say what a thing is. Paper things (bubbles, cards, chips) 4 px; controls 8 px; furniture (table, heads, bodies, lamps, vote discs) truly round. No shadows anywhere.
- Space before lines. No decorative rules. A line is drawn only for a boundary that must be seen (the outline token, 3:1 or better) or for an event (the vote divider).
- A seat is name, number and place first, colour last. Every state has a shape and a word: lamp hollow or solid, vote solid check or hollow cross. Disagreement is never red; red means something failed.
- Show counts, not mechanisms. The screen says who is speaking, how many agree and how many are needed. It never claims how answers are matched or who wrote a summary, and any number of lamps may be lit at once.

## Kept from the PDF
- Frame: slim top bar with the seated council and a status pill, sidebar with New chat, History, Library, Models and Settings, conversation filling the rest
- The stage opens above the message box, folds into a card above the answer when the council agrees, and the card replays the debate
- Half-circle table, flat side toward the viewer, 3 to 7 seats spaced evenly along the curve
- Each agent is a full-circle head holding the short name above a half-circle body, in the seat's colour; full name on hover; clicking opens a side sheet
- A check or cross on every head after each vote, until the next round
- Middle of the table: round, time left and an agreement meter worded '3 of 5 agree, needs 4'
- Bubble rules: two lines at most, no wider than the seat gap, end seats push outward, a bubble that would touch a neighbour rises; 250 ms in, about 8 s, 1.5 s out, crossfade in place, plain appear and disappear with reduced motion
- Chat View: black and white only (#111111 on #FFFFFF, #F2F2F2 on #0E0E0E), greys for names and times, one column per model when wide and one thread when narrow, vote divider, outlined citation chips, a one-model filter, follows the newest message
- Small Table / Chat switch at the bottom right while the council works
- Body text at 4.5:1 or better, colour never the only signal, light and dark from the first version
- 8 px spacing grid, 8 px corners on inputs and buttons, 150 to 200 ms for controls
- Open-licence fonts bundled through Fontsource; keyboard first with visible focus rings, full tab order and a shortcuts sheet
- Sizes for chat text (16), bubbles (13), Chat View (15), labels (14) and meta (12)
- Separate agreed (green) and error (red) status colours
- Tools: React, TypeScript, Vite, Tailwind driven by tokens, Radix, Motion, an SVG table with HTML bubbles placed by a layout pass

## Changed from the PDF
- Page: warm paper #F5F1EA became cool plaster #E9ECE8; dark #1F1E1B became #1C201F
- Accent: clay #C4694D on Send, focus, glow and switch became no general accent. The main button is ink; amber appears only on lit lamps, the in-session dot and the outer focus band
- Speaker mark: a clay glow round the head became a lamp on the table in front of the seat (hollow ring when quiet, solid amber with a pool of light when speaking)
- Table: surface colour with a border edge became solid walnut with an oak rim; text on it is light
- Seat colours: seven mid-tones became seven deep leather colours with light lettering (pale versions with dark lettering in dark theme). Every name is now 5.0:1 or better; with the PDF values five of seven failed. Smallest seat-to-seat distance under deuteranopia rose from 1.6 to 9.0 (light) and 6.6 (dark)
- Seats gain numbers: on the body, in the top bar chips and in Chat View
- Vote marks carry no colour: solid check disc and hollow cross disc. Disagreement is not shown in red
- Agreement meter: a bar with a tick became a row of discs with a notch at the number needed
- Fonts: Fraunces became Besley (titles only, weight 500 instead of 600); Source Sans 3 became Atkinson Hyperlegible Next; JetBrains Mono dropped, numbers use tabular figures in the text face
- Names in heads: 11 px weight 600 became 12 px weight 650, 7 characters at most
- Corners: 12 px on cards became 4 px on paper things; furniture is round; controls stay at 8 px
- Hairline borders and very soft shadows became no shadows and no decorative lines; one outline colour at 3:1 or better where a boundary must be seen
- Middle dots in status and dividers became words: 'Round 1 vote: 2 of 5 agree, needs 4'
- During a debate the message box is docked to the table's flat side and matches its width
- Reading column narrowed to 600 px, about 75 characters
- Status colours recomputed: agreed #5E8C6A became #2A6A43 (dark #8CCB9C); error #B5483E became #A52A1A (dark #FF8B73)

## Contrast (designer's computed figures)

| Pair | Theme | Ratio | Needed | Pass |
|---|---|---|---|---|
| Text on page | light | 13.21 | 4.5 | yes |
| Text on surface (chat text, answers, bubbles, cards, message box) | light | 15.02 | 4.5 | yes |
| Text on hover or selected row | light | 11.98 | 4.5 | yes |
| Muted text on page | light | 5.48 | 4.5 | yes |
| Muted text on surface | light | 6.23 | 4.5 | yes |
| Muted text on hover or selected row | light | 4.97 | 4.5 | yes |
| Round, time and meter caption on the table | light | 9.93 | 4.5 | yes |
| Secondary text on the table | light | 7.06 | 4.5 | yes |
| Agreed caption on the table | light | 6.62 | 4.5 | yes |
| Main button label on its ink fill | light | 15.02 | 4.5 | yes |
| Agreed text on page | light | 5.43 | 4.5 | yes |
| Agreed text on surface | light | 6.18 | 4.5 | yes |
| Error text on page | light | 5.98 | 4.5 | yes |
| Error text on surface | light | 6.8 | 4.5 | yes |
| Chat View text on its background | light | 18.88 | 4.5 | yes |
| Chat View grey (names, times) on its background | light | 6.48 | 4.5 | yes |
| Name and seat number inside seat 1 (Olive) | light | 8.82 | 4.5 | yes |
| Name and seat number inside seat 2 (Navy) | light | 11.09 | 4.5 | yes |
| Name and seat number inside seat 3 (Oxblood) | light | 13.6 | 4.5 | yes |
| Name and seat number inside seat 4 (Violet) | light | 5.44 | 4.5 | yes |
| Name and seat number inside seat 5 (Petrol) | light | 8.25 | 4.5 | yes |
| Name and seat number inside seat 6 (Mauve) | light | 5 | 4.5 | yes |
| Name and seat number inside seat 7 (Slate) | light | 13.06 | 4.5 | yes |
| Seat 1 (Olive) figure against page | light | 7.75 | 3 | yes |
| Seat 2 (Navy) figure against page | light | 9.75 | 3 | yes |
| Seat 3 (Oxblood) figure against page | light | 11.96 | 3 | yes |
| Seat 4 (Violet) figure against page | light | 4.78 | 3 | yes |
| Seat 5 (Petrol) figure against page | light | 7.25 | 3 | yes |
| Seat 6 (Mauve) figure against page | light | 4.39 | 3 | yes |
| Seat 7 (Slate) figure against page | light | 11.48 | 3 | yes |
| Outline (inputs, bubbles, clickable cards) on page | light | 3.71 | 3 | yes |
| Outline on surface | light | 4.22 | 3 | yes |
| Outline on hover or selected row | light | 3.37 | 3 | yes |
| Table against page (walnut fill) | light | 9.53 | 3 | yes |
| Oak rim against the table top | light | 3.63 | 3 | yes |
| Lit lamp against the table top (the speaking mark) | light | 6.32 | 3 | yes |
| Unlit lamp ring against the table top | light | 7.06 | 3 | yes |
| Meter discs against the table top | light | 9.93 | 3 | yes |
| Agreed meter discs against the table top | light | 6.62 | 3 | yes |
| Vote mark and focus ring (ink) against page | light | 13.21 | 3 | yes |
| Focus ring (ink) against surface | light | 15.02 | 3 | yes |
| Chat View divider and citation chip outline | light | 4.54 | 3 | yes |
| Error mark against page | light | 5.98 | 3 | yes |
| In-session dot: ink keyline against lamp fill | light | 8.76 | 3 | yes |
| Text on page | dark | 13.8 | 4.5 | yes |
| Text on surface (chat text, answers, bubbles, cards, message box) | dark | 12.06 | 4.5 | yes |
| Text on hover or selected row | dark | 10.34 | 4.5 | yes |
| Muted text on page | dark | 7.23 | 4.5 | yes |
| Muted text on surface | dark | 6.32 | 4.5 | yes |
| Muted text on hover or selected row | dark | 5.41 | 4.5 | yes |
| Round, time and meter caption on the table | dark | 8.29 | 4.5 | yes |
| Secondary text on the table | dark | 6.09 | 4.5 | yes |
| Agreed caption on the table | dark | 5.99 | 4.5 | yes |
| Main button label on its fill | dark | 13.8 | 4.5 | yes |
| Agreed text on page | dark | 8.73 | 4.5 | yes |
| Agreed text on surface | dark | 7.62 | 4.5 | yes |
| Error text on page | dark | 7.2 | 4.5 | yes |
| Error text on surface | dark | 6.29 | 4.5 | yes |
| Chat View text on its background | dark | 17.24 | 4.5 | yes |
| Chat View grey (names, times) on its background | dark | 7.93 | 4.5 | yes |
| Name inside seat 1 (Olive), and the figure against page | dark | 5.44 | 4.5 | yes |
| Name inside seat 2 (Navy), and the figure against page | dark | 9.85 | 4.5 | yes |
| Name inside seat 3 (Oxblood), and the figure against page | dark | 9 | 4.5 | yes |
| Name inside seat 4 (Violet), and the figure against page | dark | 7.02 | 4.5 | yes |
| Name inside seat 5 (Petrol), and the figure against page | dark | 5.52 | 4.5 | yes |
| Name inside seat 6 (Mauve), and the figure against page | dark | 5.31 | 4.5 | yes |
| Name inside seat 7 (Slate), and the figure against page | dark | 11.42 | 4.5 | yes |
| Outline (inputs, bubbles, clickable cards) on page | dark | 4.66 | 3 | yes |
| Outline on surface | dark | 4.07 | 3 | yes |
| Outline on hover or selected row | dark | 3.49 | 3 | yes |
| Table against page (oak rim, required in dark) | dark | 6.5 | 3 | yes |
| Oak rim against the table top | dark | 3.71 | 3 | yes |
| Lit lamp against the table top (the speaking mark) | dark | 5.75 | 3 | yes |
| Unlit lamp ring against the table top | dark | 6.09 | 3 | yes |
| Meter discs against the table top | dark | 8.29 | 3 | yes |
| Agreed meter discs against the table top | dark | 5.99 | 3 | yes |
| Vote mark and focus ring (ink) against page | dark | 13.8 | 3 | yes |
| Focus ring (ink) against surface | dark | 12.06 | 3 | yes |
| Chat View divider and citation chip outline | dark | 5.59 | 3 | yes |
| Error mark against page | dark | 7.2 | 3 | yes |
| In-session dot: lamp fill against surface | dark | 8.8 | 3 | yes |

## Risks
- Brown is unusual on screens. On a dim or badly calibrated display walnut can look muddy, and the three darkest seats (oxblood, slate, olive) sit close to it in darkness. They depend on the 8 px gap of page colour and the oak rim.
- A wooden table may read as too literal to the owner, however flat it is drawn. This is the direction's whole identity, so if he dislikes it the fallback is another direction, not a tweak.
- The speaker mark is on the table, not on the head. If he cannot find the speaker at a glance in light theme, the fix is an ink ring on the speaking head; amber cannot be used there because it is 1.51:1 against the page.
- If the back end ends up with most seats speaking at once, many lamps and bubbles will be lit together and the one bold element is diluted. The design stays truthful, but less calm.
- Seven seats on a narrow stage: bubbles shrink to about 150 px, roughly 45 characters over two lines. Whatever writes the summaries must keep to that or the text is cut with an ellipsis.
- Dark-theme seats are less far apart with six or seven seats (smallest distance 6.6, mauve against olive under deuteranopia). Numbers and names carry identity there. Seat colours also change character between themes (oxblood becomes pale pink).
- Atkinson Hyperlegible Next has proportional digits by default. Any changing number that forgets the tabular setting will jitter, the countdown most visibly. A check should enforce it.
- Besley is wide and dark. Long titles wrap badly, so it must stay on short titles; History rows and chat titles use the sans.
- Chat View's pure white sheet inside the plaster frame (and #0E0E0E inside #1C201F) may look like a different app pasted in. The brief fixes black and white, so only the surrounding spacing can soften it.
- Docking the table to the message box: when the box grows (several lines, attached files) the table must move up, not be covered. On windows under about 760 px tall the table drops to its 240 px minimum and bubbles have one row.
- Limits of my checks: the PDF image tool is missing on this Mac, so I read the PDF's text in full but saw the three wireframes only as coarse in-memory renderings, enough to confirm positions and parts, not fine detail. The font feature check was run on the static package files; the variable files should be re-checked in the first build step. Colour-vision figures are simulations and need a look by eye in the study.

## Questions the designer left for Lucas
- When one model fills two seats, or when seats get roles in Phase 4 (skeptic, fact-checker), what should the head show: the model's short name both times, told apart by seat number (my assumption), or the role? Role names are longer than the 7 characters a head can hold, so this changes the head design.

## Designer's own study brief (SUPERSEDED by docs/direction/study-brief.md)
Read /Users/lucasta/.claude/plugins/marketplaces/anthropic-agent-skills/skills/frontend-design/SKILL.md first. Build one self-contained HTML file: inline CSS and SVG, a theme toggle, no network requests. Embed Besley and Atkinson Hyperlegible Next as base64 from their Fontsource latin woff2 files; if they are not available, stop and say so rather than substituting.

Show two frames at 1440 x 900, each with the full app frame (top bar with five numbered nameplate chips and the status pill, sidebar, conversation), switchable between light and dark.

Frame A, mid-debate: a question about renewing an office lease. Walnut half-circle table with its flat side on the message box and an oak rim on the curve only. Five figures at 162, 126, 90, 54 and 18 degrees: Qwen 1, Llama 2, Phi 3, Gemma 4, Mistral 5, in seat colours 1 to 5, names in heads, numbers on bodies. Phi's lamp is lit with its pool and a two-line bubble; Llama's bubble is at 40% opacity, fading out. Round 1 vote marks on every head: three solid checks, two hollow crosses. Middle: Round 2, 3:12 left, three solid discs, one hollow, notch, one hollow, '3 of 5 agree, needs 4'. Table / Chat switch bottom right.

Frame B, released: the folded card, then 'Agreed, 4 of 5' and the answer with two citation chips and one disagreement note.

Use only the given token values. No shadows, no decorative lines, no gradient except the lamp pool. Screenshot both themes with Playwright and check each text pair against the contrast table.
