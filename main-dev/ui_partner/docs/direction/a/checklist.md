# Look A — fixed function checklist

| # | Item | Done | Where to see |
|---|---|---|---|
| 1 | Calm, readable, roomy. Not control panel. Light AND dark both designed. | yes, one doubt | `shots/study-light.png`, `shots/study-dark.png`. Doubt: light theme heavy with dark seats (critique.md, point 1). Panel 2 busiest. |
| 2 | Body text >= 4.5:1. | yes | `contrast-pairs.json`: 142 pairs, 0 below, exit 0. Lowest text pair: muted on sunken 4.97 (light). |
| 3 | Half-circle table, flat side to viewer. Head = full circle, short name inside. Body = half circle. Seat colour on figure. Colour never only signal. | yes | Panels 1 to 3. Name in head, seat number on body, fixed place. Grey shots: `shots/study-light-grey.png`, `shots/study-dark-grey.png`. |
| 4 | Speaker marked ON the figure (ring round head = speaking, always). | yes | Panel 1: Qwen. Panel 2: all five. Ink ring, 3 px page gap. Lamp on table lit as well. `shots/zoom-p1-top-light@1x.png`. |
| 5 | After vote: check or cross on every head. Check = solid dark disc, pale check. Cross = pale disc, dark outline, dark cross. Never red. | yes, note | Panel 3, all seven heads; panel 4 small heads. `shots/zoom-p3-left-light@1x.png`. Note: in dark theme ink is pale, so check disc is pale with dark check (correction 2 as written). |
| 6 | Table middle: round, time left, meter, caption like "2 of 5 agree, needs 4". | yes | Panels 1 to 3. One disc per seat, notch after number needed. |
| 7 | Bubble: above own seat, 2 lines max, no overlap with bubble or figure. | yes | Panel 1 (three, third at half strength), panel 2 (five), panel 3 (one). Page checks on load; any overlap = console error = `look:file` exit 1. Exit was 0. |
| 8 | Keyboard focus on seat = outline round WHOLE figure. One focused seat in panel 3. | yes | Panel 3: Granite. Rounded rectangle, ink ring with page gap, amber outer band. Tab to any seat shows same. |
| 9 | Fonts embedded. No network. | yes | `look:file`: FONTS LOADED "Besley Variable 400 900 normal", "Atkinson Hyperlegible Next Variable 200 800 normal". OUTSIDE REQUESTS 0. |

Also asked:
- Theme switch top right, default light: yes.
- Play on panel 1: one bubble (Phi) fades in 250 ms, stays 3 s, fades out 1.5 s. Reduced motion: appears, disappears. `shots/play-check-light@1x.png`.
- Stage footer: Pause, Stop left; Table / Chat right, Table active: yes.
- Chat View: not drawn.
