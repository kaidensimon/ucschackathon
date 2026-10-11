# Look B, Fair Copy — plan

Stone Age talk. Exact things exact.

## Subject, audience, job
- Subject: how a meeting is put on record. Rough minutes first, clean final copy last.
- Audience: one man, Lucas. Law background. Home network. Not engineer.
- Job of study: let Lucas judge this look beside A and C. Same words, seats, sizes. Only look differs.

## Colours (named, per theme)
| Name | Light | Dark | Use |
|---|---|---|---|
| page (steno pad) | `#E5ECE4` | `#141A23` | app ground, stage |
| surface (sheet) | `#F5F8F4` | `#1D232E` | answer sheet, bubbles, table top, message box, pill |
| ink (registrar blue-black) | `#1A2435` | `#E2E8E1` | text, names, filled tally strokes, vote marks, focus, Send |
| outline | `#717E76` | `#78818C` | edges that must be seen: bubble, table, hollow strokes, buttons |
| mark (copying pencil violet) | `#67298C` | `#CDA4EC` | live only: speaker ring, active side of switch |
| agreed (auditor green) | `#136239` | `#7BCC98` | ruled-off tally, heading "Agreed 4 of 5" |

Helpers: sunk `#DBE2D9` / `#272E3A` (sidebar), rule `#B5C2B7` / `#3A404B` (margin line, sheet edge; decoration), muted `#515963` / `#9AA8A8`, mark-wash `#ECDFF7` / `#3F2C4C`, error `#A12628` / `#F28881` (not drawn in study), on-ink `#F5F8F4` / `#141A23` (Send label; new, see changed values). Seven seat colours + seven tints: `tokens.json`.

## Typefaces and roles
- `'Literata Variable'` (opsz.css, opsz-italic.css) = the record. Question, answer, bubbles (italic 14/20, 450), dissent (italic), headings.
- `'Archivo Variable'` (wdth.css) = the form. Labels, buttons, names in heads, timer, counts, margin notes, captions. Tabular numbers. Name too wide for head: letters narrow (100, 88, 75), size stays.
- No third face. No mono. No capitals for labels.

## Layout
One sentence: page on a pad; narrow left margin column holds who and what; text column holds what was said; stage is a plate with no box; all left-anchored, ragged right; only table-top stack is centred.

```
+--------------------------------------------------------------------------------+
| Council of 5                                    ( //|| Round 2, 3:10 left, .. ) |  48
+-----------+--------------------------------------------------------------------+
| New chat  |        You | Can I end my apartment lease early ...                 |
| History   | Time limit | [Lease 2025.pdf, 14 pages] [..] [..]                   |
| Library   |   (line stops here)                                                 |
| Models    |                      [ slip ]                                       |
| Settings  |             [ slip ]   (O)   [ slip ]        stage 1040 x 558       |
|           |                (O)    _.---._    (O)         no box, page tone      |
|           |            (O)      /  Round 2 \      (O)                           |
|           |                    |  ////  ___ |                                   |
|           |                    +------------+   flat side y = 520               |
| Theme     |  [Pause] [Stop]                                    [Table | Chat]   |
| Shortcuts |  [ Add a note for the next round            Send ]                  |
+-----------+--------------------------------------------------------------------+
  240          56 | margin 136 | 24 | text 590
```
Panel 4: same frame. Hollow docket slip (tally, "Agreed 4 of 5", seat marks, See the debate), then one filled sheet (answer, files, dissent).

## Principles
1. Two voices, never swapped: Literata = said. Archivo = form.
2. Margin holds meta. No label above content.
3. Hollow = not settled. Filled = settled. (tally strokes, cross vs check, docket vs answer sheet)
4. Violet = live. Green = agreed. Nothing else gets them.
5. One ruled line in conversation column (margin line). Other edges only where needed.
6. No shadow, no gradient, no glow, no capitals, no dots between meta.

## The one bold element
The tally. One slanted stroke per seat. Filled = agrees. Hollow = not yet. Underline under number needed. At agreement: green, second line ruled under. Same mark in pill (tiny), table top (big), docket margin (green).
