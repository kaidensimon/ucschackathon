# Look B, Fair Copy — fixed function checklist

Stone Age talk. Where to see = panel id in `study.html` (also in `shots/study-light.png`, `shots/study-dark.png`).

- [x] 1. Calm, readable, roomy. Not control panel. Light AND dark designed.
  See: every panel, both themes. No shadow, glow, gradient. Dark is blue slate `#141A23` with paper-colour ink `#E2E8E1`, own lilac `#CDA4EC`.
- [x] 2. Body text ≥ 4.5:1.
  See: `contrast-pairs.json`. Ink on page 12.95 / 14.03, on surface 14.56 / 12.66. Muted lowest 5.37. Contrast exit 0, 138 pairs.
- [x] 3. Half-circle table, flat side to viewer. Head = full circle, short name inside. Body = half circle. Seat colour on figure. Colour never only signal.
  See: `p1-one-speaker`, `p3-seven-after-vote`. Flat side at y = 520. Seat colour = 3 px ring on head and body + pattern lines. Other signals: name, place, pattern. Grey shots still tell seats apart.
- [x] 4. Speaker marked ON figure: ring round head.
  See: `p1-one-speaker` (Qwen), `p2-all-speaking` (all five). Violet second ring, 3 px, 4 px gap. Nothing else is violet on the stage.
- [x] 5. After vote: check or cross on every head. Check = solid dark disc, pale check. Cross = pale disc, dark outline, dark cross. Never red.
  See: `p3-seven-after-vote` (7 heads: 4 checks, 3 crosses), `p4-released` docket (Phi cross, four checks). All ink. 2 px halo round each disc.
- [x] 6. Table middle: round, time left, meter, caption.
  See: `p1-one-speaker`: "Round 2", "3:10 left", tally 2 filled of 5 with line under 4, "2 of 5 agree, needs 4". `p3-seven-after-vote`: "Round 1 vote", "3:36 left", 4 of 7, line under 6.
- [x] 7. Bubble above own seat, 2 lines max, no overlap.
  See: `p2-all-speaking` (five bubbles), `p3-seven-after-vote` (Hermes pushed right, clear of Gemma). Layout pass counts overlaps into `data-slip-overlaps` on `<body>` (0) and logs an error if any; look exit 0.
- [x] 8. Keyboard focus on seat = outline round WHOLE figure.
  See: `p3-seven-after-vote`, Granite: 2 px ink rounded box round head, body and vote mark. Real Tab key does the same on every seat. Not violet.
- [x] 9. Fonts embedded. No network.
  See: look report: FONTS LOADED Literata Variable (normal, italic), Archivo Variable. OUTSIDE REQUESTS 0. No fallback families in CSS.

Also asked:
- [x] Play button on panel 1 ("Play one bubble"): Mistral bubble in 250 ms, stays 8 s, out 1.5 s. Reduced motion: appears, disappears. Click tested both ways, exit 0.
- [x] Panel 1 twice: patterns on, patterns off. Shots at scale 2 and scale 1.
- [x] Dark: one bubble slanted and upright side by side (`bubble-compare`).
- [x] Theme switch top right. Default light.
