# Look C, Cut-Out Council — plan

Short talk. Exact things exact. Corrections beat direction.md.

## Subject, audience, job
- Subject: GX10 Council. 3 to 7 local models sit at half-circle table, debate one question, release one agreed answer.
- Audience: one owner, Lucas. Home network. Not technical. Looks at it for long debates.
- Job of this study: show look C on four fixed screens so Lucas can compare with A and B. Same words, seats, sizes. Only look differs.

## Colours (named; full set in `tokens.json`)

Light
| Name | Hex | Job |
|---|---|---|
| Paper | `#FFFFFF` | page. Also every name and every cut inside a figure (page shows through) |
| Ink | `#17201C` text, `#1D2A24` controls | all words, all buttons, focus, vote marks |
| Edge | `#77827B` | every line that means something: bubble, table curve, message box, empty pips |
| Cloth | `#DEE5DD` | table fill only. Kept pale on purpose |
| Seat 1 teal | `#005960` | first of seven seat colours. Seats are the only hue |
| Seat 3 ochre | `#8C6205` | lightest seat colour that still holds its name |

Dark
| Name | Hex | Job |
|---|---|---|
| Night | `#151B18` | page, names and cuts |
| Lifted | `#1C2420` | bubbles, message box, folded card |
| Pale ink | `#E6EBE7` | text, buttons, focus, vote marks |
| Edge | `#74817A` | same job as light |
| Cloth | `#213029` | table fill only |
| Seat 1 teal | `#A1E8E5` | seats go pale in dark |

Other tokens: muted `#535E58` / `#9CA9A2`; hairline `#D3D8D1` / `#2D3832` (decoration only); agreed `#1A6B42` / `#74C998`; error `#A32A1C` / `#F0897A`; seats 2 to 7 as direction.md table.

## Typeface
One family: Archivo Variable (weight 100 to 900, width 62 to 125). Package file `@fontsource-variable/archivo/wdth.css`.
- Names in heads: weight 650, one size per council (19 px in a 72 head, 17 px in a 64 head), width axis fits each name to 0.78 of the head. Short name goes wide, long name goes narrow. Never shrunk. Measured in the browser: widths 74% to 125%.
- Study title 24/30, weight 620, width 112.
- Answer heading 20/26, weight 650, width 106.
- Answer and question 16/26 and 16/25, weight 400.
- Bubble 13/18, weight 450, width 96, two lines at most.
- Labels and buttons 14/20, weight 500. Meta 12/16 muted.
- Numbers: tabular lining figures, weight 550. No mono face.

## Layout
One centre line. Table, message box, folded card, answer all sit on it. Message box is 640 wide and its top edge is the table's flat side: owner's place at the table. Text left-aligned in the 640 column; owner's question right-aligned in it; table middle is the only centred text.

```
+----------------------------------------------------------------------------------+
| Council of 5            o Phi o Llama o Qwen o Gemma o Mistral  ( Round 2  3:10 left  2 of 5 agree ) |  48
+----------+-----------------------------------------------------------------------+
| New chat |                                   +-------------------------------+   |
| History  |                                   | question + three file chips   |   |
| Library  |                                   +-------------------------------+   |
| Models   |                          +---------------+                            |
| Settings |          +-----------+   | speaker line  |   +-----------+            |
|          |          | fading    |   +-------v-------+   | line      |            |
|          |          +------v----+      ((Qwen))         +----v------+            |
|          |               (Llama)        (__V__)            (Gemma)               |
|          |                           . - - - - - .                               |
|          |        (Phi)           .'    Round 2    '.          (Mistral)         |
|          |                       :     3:10 left     :                           |
|          |                       :    * * o o | o    :                           |
| Theme    |                       : 2 of 5 agree, needs 4                         |
| Shortcuts| [Pause][Stop]   +=====+===================+=====+       [Table|Chat]  |
| note     |                 | Add a note...   [Add to next round] |               |
+----------+-----------------+--------------------------------------+--------------+
   240                     stage 1040 x 558, flat side at y 520
```

## Principles
1. Colour belongs to the council. Every hue is a seat. Controls are ink. Only other colour: agreed green, error red, always with a mark and a word.
2. Name is the face. No eyes, no mouth. Lettering fitted by width.
3. One colour per figure. Name and cut are the page showing through.
4. Every state has a shape and a word: ring = speaking, solid disc with check = agrees, hollow disc with cross = disagrees, rounded rectangle = keyboard focus.
5. Fills are rare: figures, cloth, ink buttons. Everything else is a line on paper.
6. Nothing loops. One bubble fades when Play is pressed. Nothing else moves.

## The one bold element
The figures. Seven flat one-colour cut-outs, name lettered across the head by the width axis, one cut in each body. Same shape at three sizes in the study: at the table (head 72 and 64), in the top bar (head 14, name beside), in the folded card line-up (head 22, name beneath). All else kept plain so they carry it.

## Choices left to builder by corrections (reported)
- Surface light = `#FFFFFF` (no step). Cards read by the `#77827B` edge (3.99:1), not by a tint. Dark surface stays `#1C2420`.
- Corners: three sizes only. 8 (buttons, chips, bubbles, focus), 14 (message box, folded card, question), fully round (pill, switches, vote discs).
- Meter: pips kept (one per seat, mark after the pip that reaches the bar). Small figures as counters tried on paper, dropped: too fussy at 12 px.
- Name size: one per council.
