# Look A, The Lit Table — plan

Short talk. Exact things exact.

## Subject, audience, job
- Subject: one person chairs small council of local AI models. They argue, then give one answer.
- Audience: owner Lucas, alone, on his Macs.
- Job: see at a glance who speaks and how many agree. Trust the released answer.

## Colours (named; all from direction.md + corrections.md)
Light
| Name | Hex | Job |
|---|---|---|
| plaster (page) | `#E9ECE8` | room. Cool grey-green, not cream |
| paper (surface) | `#F9FAF7` | bubbles, card, answer, message box |
| ink | `#1D2427` | text, main button, vote marks, speaker ring, focus ring |
| walnut (table) | `#4A3628` | table top only |
| oak (table-rim) | `#B58A55` | 3 px rim, curved edge only |
| lamp | `#F4B740` | lit lamp + pool on walnut, in-session dot, outer focus band |

Dark
| Name | Hex | Job |
|---|---|---|
| plaster (page) | `#1C201F` | room after dark |
| paper (surface) | `#262B29` | bubbles, card, answer, message box |
| ink | `#E9ECE7` | text, main button, vote marks, speaker ring, focus ring |
| walnut (table) | `#5A4130` | table top only |
| oak (table-rim) | `#C49C66` | the table edge in dark (walnut alone 1.75:1) |
| lamp | `#F6C356` | lit lamp + pool, in-session dot, outer focus band |

Rest (sunken, outline, muted, on-table, agreed, error, seven seats): `tokens.json`.

## Typefaces
- `'Besley Variable'` — titles only. App name 17/24 weight 600. Card heading 20/26 weight 500. Study title 24/30 weight 500. letter-spacing -0.01em.
- `'Atkinson Hyperlegible Next Variable'` — all else. Answer 16/26 weight 400. Labels, buttons 14/20 weight 550. Bubbles 13/18 weight 450. Meta 12/16 muted. Names in heads weight 650. Seat numbers weight 700. Timer 22 weight 600. Tabular figures on every number.
- No third face. No monospace.

## Layout
One sentence: you have the chair — table's flat side rests on your message box, council faces you, all text left-aligned, only the middle of the table centred.

```
+--------------------------------------------------------------------------+
| Council of 5   o Phi o Llama o Qwen o Gemma o Mistral     ( * Round 2 …) |  48, sunken
+----------+---------------------------------------------------------------+
| [New chat]|        You                                                   |
| History  |        Can I end my apartment lease early …                   |
| Library  |        [file] [file] [file]  Time limit 5:00                  |
| Models   |                    .-- bubble --.                             |
| Settings |          .-bubble-.    (Qwen)     .-bubble-.                  |
|          |            (Llama)      [3]        (Gemma)                    |
|          |             [2]    .-=========-.     [4]                      |
|          |      (Phi)       .'  o  (*)  o  '.       (Mistral)            |
|          |       [1]       /     Round 2     \         [5]               |
|          |                |  o   3:10 left  o |                          |
|          |                |   @ @ o o | o     |                          |
|          |          +-----+-------------------+-----+                    |
|          |          | Add a note for the next round |   message box      |
| Theme    |          +-------------------------------+                    |
| Shortcuts|  [Pause] [Stop]                          [ Table | Chat ]     |
+----------+---------------------------------------------------------------+
 240 sunken           conversation 1200; stage 1040 x 558 centred
```
Released panel: question, folded card (paper, outlined), answer (paper, no outline), message box at foot. One 600 px column.

## Principles
1. One light in room. Amber only where something is live. Never button, link, text.
2. Wood for table only. Rest: plaster, paper, ink.
3. Corners say what thing is: paper 4 px, controls 8 px, furniture round. No shadows.
4. Space before lines. Line only for edge that must be seen (outline token, 3:1 or better).
5. Seat = name, number, place first. Colour last. Every state has shape: lamp hollow or solid, ring round head, vote solid check or hollow cross.
6. Show counts, not how.

## The one bold element
The lit table. One walnut half-circle in pale room without lines. Small amber lamp with soft pool on the wood in front of each speaking seat. Only warm colour, only glow. Speaker also has ink ring round head (correction 3) so mark is on the figure too.
