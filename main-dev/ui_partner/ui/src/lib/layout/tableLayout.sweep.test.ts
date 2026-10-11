// Every stage size the window can give, not only the handful in the frozen tests: the council
// always fits, never crowds, and only ever gets bigger when the stage does.
import { describe, expect, it } from "vitest";
import { figureRect, HEADROOM_MIN, placeBubbles, type Rect, tableLayout } from "./tableLayout";

const overlaps = (a: Rect, b: Rect) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

// from a stage smaller than the smallest window gives, up to a very large monitor
// (steps of 19 and 17, so odd and even sizes are both met)
const WIDTHS = Array.from({ length: 100 }, (_, i) => 420 + 19 * i); // 420 to 2301
const HEIGHTS = Array.from({ length: 60 }, (_, i) => 260 + 17 * i); // 260 to 1263

describe("the council at every stage size", () => {
  for (let n = 2; n <= 7; n++) {
    it(`${n} seats: fits, stays apart and keeps its proportions`, () => {
      for (const w of WIDTHS) {
        for (const h of HEIGHTS) {
          const L = tableLayout(n, w, h);
          const at = `${n} seats in ${w} x ${h}`;
          expect(L.headD, at).toBeGreaterThanOrEqual(20);
          expect(L.headD, at).toBeLessThanOrEqual(72);
          expect(L.r, at).toBeGreaterThanOrEqual(3 * L.headD);
          expect(L.tableR, at).toBeGreaterThan(0);
          const figures = Array.from({ length: n }, (_, i) => figureRect(L, i));
          // the stage counts on this much clear room above the top figure (Stage.tsx lowers the table by the rest)
          expect(Math.min(...figures.map((f) => f.y)), at).toBeGreaterThanOrEqual(HEADROOM_MIN);
          for (const f of figures) {
            expect(f.x, at).toBeGreaterThanOrEqual(0);
            expect(f.x + f.w, at).toBeLessThanOrEqual(w);
            expect(f.y, at).toBeGreaterThanOrEqual(0);
            expect(f.y + f.h, at).toBeLessThanOrEqual(h);
          }
          for (let i = 0; i < n; i++)
            for (let j = i + 1; j < n; j++) {
              const [a, b] = [figures[i], figures[j]];
              if (!a || !b) throw new Error("missing figure");
              expect(overlaps(a, b), `${at}: figures ${i} and ${j}`).toBe(false);
            }
        }
      }
    });

    it(`${n} seats: a bubble is over its own seat or not shown, and the first speaker is served first`, () => {
      const all = Array.from({ length: n }, (_, i) => i);
      for (const w of WIDTHS.filter((_, i) => i % 4 === 0)) {
        for (const h of HEIGHTS.filter((_, i) => i % 4 === 0)) {
          const L = tableLayout(n, w, h);
          const at = `${n} seats in ${w} x ${h}`;
          expect(L.bubbleReach, at).toBeLessThanOrEqual(L.bubbleMaxWidth);
          const figures = all.map((i) => figureRect(L, i));
          // the bubble as the table draws it: two lines of text, with room for its tail and a speaking ring
          const size = { w: Math.min(L.bubbleMaxWidth, 216), h: 69 };
          // each seat in turn speaks first, the others after it
          for (const first of all) {
            const order = [first, ...all.filter((i) => i !== first)];
            const boxes = placeBubbles(L, order, size);
            expect(boxes, at).toHaveLength(n);
            const placed: Rect[] = [];
            boxes.forEach((box, k) => {
              const own = figures[order[k] ?? -1];
              if (!box || !own) return;
              expect(box.x, at).toBeGreaterThanOrEqual(0);
              expect(box.x + box.w, at).toBeLessThanOrEqual(w);
              expect(box.y, at).toBeGreaterThanOrEqual(0);
              expect(box.y + box.h, at).toBeLessThanOrEqual(own.y);
              expect(Math.abs(box.x + box.w / 2 - (own.x + own.w / 2)), at).toBeLessThanOrEqual(L.bubbleReach);
              for (const f of figures) expect(overlaps(box, f), at).toBe(false);
              for (const other of placed) expect(overlaps(box, other), at).toBe(false);
              placed.push(box);
            });
            // if anybody got a bubble, the first speaker did not go without while a later seat got one...
            // unless the first speaker has no clear spot even on an empty table
            if (boxes[0] === null && boxes.some((b) => b !== null)) {
              expect(placeBubbles(L, [first], size)[0], `${at}: seat ${first} speaks first`).toBeNull();
            }
          }
        }
      }
    });

    it(`${n} seats: two speakers who fit together both get a bubble before any listener does`, () => {
      const all = Array.from({ length: n }, (_, i) => i);
      for (const w of WIDTHS.filter((_, i) => i % 3 === 0)) {
        for (const h of HEIGHTS.filter((_, i) => i % 3 === 0)) {
          const L = tableLayout(n, w, h);
          if (L.maxBubbles < 2) continue;
          const size = { w: Math.min(L.bubbleMaxWidth, 216), h: 69 };
          for (let a = 0; a < n; a++)
            for (let b = a + 1; b < n; b++) {
              const alone = placeBubbles(L, [a, b], size);
              if (alone.some((box) => box === null)) continue; // the two do not fit together at all
              const withOthers = placeBubbles(L, [a, b, ...all.filter((i) => i !== a && i !== b)], size);
              expect(withOthers[0], `${n} seats in ${w} x ${h}: speakers ${a} and ${b}`).not.toBeNull();
              expect(withOthers[1], `${n} seats in ${w} x ${h}: speakers ${a} and ${b}`).not.toBeNull();
            }
        }
      }
    }, 60000);

    it(`${n} seats: a member talking alone always gets a bubble, with its tail on its own head`, () => {
      // every stage the app's window can give and smaller, with the widest two-line bubble and a short one
      for (const w of WIDTHS.filter((x) => x >= 500)) {
        for (const h of HEIGHTS.filter((y) => y >= 300)) {
          const L = tableLayout(n, w, h);
          for (const size of [
            { w: L.bubbleMaxWidth, h: 69 },
            { w: Math.min(L.bubbleMaxWidth, 170), h: 51 },
          ]) {
            for (let seat = 0; seat < n; seat++) {
              const [box] = placeBubbles(L, [seat], size);
              const own = L.seats[seat];
              const at = `${n} seats in ${w} x ${h}, seat ${seat} alone, bubble ${size.w} x ${size.h}`;
              if (!box || !own) throw new Error(`no bubble: ${at}`);
              // The app's stage is never narrower than 688 px (an 800 px window with the icon rail):
              // from there up the tail lands on the speaker's own head. On a narrower stage the
              // bubble still shows, wherever it is clear.
              if (w < 688) continue;
              const tail = Math.max(box.x + 14, Math.min(box.x + box.w - 14, own.x));
              expect(Math.abs(tail - own.x), at).toBeLessThanOrEqual(L.headD / 2);
            }
          }
        }
      }
    });

    it(`${n} seats: a bigger stage never gives smaller heads`, () => {
      for (const w of WIDTHS) {
        let last = 0;
        for (const h of HEIGHTS) {
          const d = tableLayout(n, w, h).headD;
          expect(d, `${n} seats, ${w} wide, growing to ${h} tall`).toBeGreaterThanOrEqual(last);
          last = d;
        }
      }
      for (const h of HEIGHTS) {
        let last = 0;
        for (const w of WIDTHS) {
          const d = tableLayout(n, w, h).headD;
          expect(d, `${n} seats, ${h} tall, growing to ${w} wide`).toBeGreaterThanOrEqual(last);
          last = d;
        }
      }
    });
  }
});
