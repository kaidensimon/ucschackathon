# Look C — fixed function checklist

Short talk. Each item: ticked, and where to see it. Shots in `shots/`; one panel each in `shots/work/panel-<id>-<theme>@1x.png`.

1. [x] Calm, readable, roomy. Not control panel. Light AND dark both designed.
   - See: `shots/study-light.png`, `shots/study-dark.png`. Tokens for both in `tokens.json`. Theme switch top right of page.
2. [x] Body text 4.5:1 or better.
   - See: `contrast-pairs.json`, lines "TEXT ...". Lowest body pair: muted on hover 5.51:1 (light), 5.81:1 (dark). Lowest name in a head: seat 5 slate 5.35:1 (light), seat 4 claret 5.06:1 (dark). 118 pairs, 0 below threshold. Command exit 0.
   - One line under 4.5 on purpose: bubble at half strength (3.24:1 light), listed as "PASSING STATE".
3. [x] Half-circle table, flat side to viewer. Head = full circle, short name inside. Body = half circle. Seat colour on figure. Colour never only signal.
   - See: panels 1 to 3. Second signals: name in head, body cut per seat (plain, band, collar, sash, placket, yoke, braces), seat position. Small figures (top bar, folded card) have the name written beside or beneath. Grey shots: `shots/study-light-grey.png`, `shots/study-dark-grey.png`.
4. [x] Speaker marked ON the figure: ring round head = speaking, always.
   - See: panel 1 (Qwen), panel 2 (all five). Ink ring, page-colour gap. Panel 3: no speaker, no ring.
5. [x] After vote: check or cross on every head. Check = solid dark disc, pale check. Cross = pale disc, dark outline, dark cross. Never red.
   - See: panel 3, all seven heads, upper right. Also folded card line-up in panel 4. Dark theme flips with the ink: solid pale disc and dark check; dark disc with pale outline and cross.
6. [x] Table middle: round, time left, meter, caption.
   - See: panels 1 and 2 "Round 2   3:10 left", five pips (2 filled), bar mark after pip 4, "2 of 5 agree, needs 4". Panel 3 "Round 1 vote   3:36 left", seven pips (4 filled), mark after pip 6, "4 of 7 agree, needs 6".
7. [x] Bubble: above own seat, 2 lines max, no overlap with bubble or figure.
   - See: panel 2 (five bubbles). Checked by the study on load; look run shows 0 console errors. Positions (stage px): Phi x 54-306 y 255-295; Llama x 144-412 y 125-165; Qwen x 435-605 y 58-116; Gemma x 628-795 y 107-165; Mistral x 734-945 y 255-295.
8. [x] Keyboard focus on seat = outline round WHOLE figure, not head ring. One focused seat in panel 3.
   - See: panel 3, Granite: ink rounded rectangle round head, body and vote mark. Also live: press Tab in the study, every seat takes the same rectangle.
9. [x] Fonts embedded. No network.
   - See: look run "FONTS LOADED Archivo Variable 100 900 normal", "OUTSIDE REQUESTS 0". One family only. No fallback family named in CSS.

Also asked by brief
- [x] Play button on panel 1: Qwen's bubble goes, fades in 250 ms, stays 8 s, fades out 1.5 s, then the still picture returns. With reduced motion: appears, stays, disappears, no fade. Clicked in a look run both ways: 0 console errors.
- [x] Stage footer: Pause, Stop left; Table / Chat right, Table active. Drawn on the message-box row.
- [x] Four panels, 1440 x 830 each, 48 px apart, caption above each. Page 1440 wide.
