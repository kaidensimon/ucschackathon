// FROZEN (lead). The council shrinks with the window: when the stage gets small, the figures,
// the table and the bubbles scale down together instead of crowding. Do not edit; report if
// a case looks wrong or cannot be met.
import { describe, expect, it } from "vitest";
import { figureRect, placeBubbles, type Rect, tableLayout } from "./tableLayout";

const overlaps = (a: Rect, b: Rect, gap = 0) =>
  a.x < b.x + b.w + gap && b.x < a.x + a.w + gap && a.y < b.y + b.h + gap && b.y < a.y + a.h + gap;

// stage sizes from a roomy window down to a very small one
const SMALL: [number, number][] = [
  [820, 470],
  [700, 400],
  [600, 340],
  [500, 300],
  [420, 260],
];

describe("the council shrinks with the window", () => {
  it("keeps today's sizes on a roomy stage", () => {
    expect(tableLayout(5, 1040, 558).headD).toBe(72);
    expect(tableLayout(7, 1040, 558).headD).toBe(64);
    expect(tableLayout(5, 912, 560).headD).toBe(64);
  });

  for (let n = 3; n <= 7; n++) {
    it(`${n} seats: heads get smaller as the stage does, never larger, never below 20 px`, () => {
      let last = Number.POSITIVE_INFINITY;
      for (const [w, h] of [[1040, 558] as [number, number], ...SMALL]) {
        const L = tableLayout(n, w, h);
        expect(L.headD, `${w}x${h}`).toBeLessThanOrEqual(last);
        expect(L.headD, `${w}x${h}`).toBeGreaterThanOrEqual(20);
        expect(Number.isInteger(L.headD), `${w}x${h} whole pixels`).toBe(true);
        expect(L.bodyW).toBeCloseTo(1.4 * L.headD, 5);
        expect(L.bodyH).toBeCloseTo(0.7 * L.headD, 5);
        last = L.headD;
      }
      // on the smallest stage the heads really have shrunk
      expect(tableLayout(n, 420, 260).headD).toBeLessThan(tableLayout(n, 1040, 558).headD);
    });

    for (const [w, h] of SMALL) {
      it(`${n} seats in ${w} x ${h}: figures stay apart, inside the stage, clear of the table`, () => {
        const L = tableLayout(n, w, h);
        expect(L.r).toBeGreaterThan(0);
        expect(L.tableR).toBeGreaterThan(0);
        const figures = Array.from({ length: n }, (_, i) => figureRect(L, i));
        figures.forEach((f, i) => {
          expect(f.x, `figure ${i} left`).toBeGreaterThanOrEqual(0);
          expect(f.x + f.w, `figure ${i} right`).toBeLessThanOrEqual(w);
          expect(f.y, `figure ${i} top`).toBeGreaterThanOrEqual(0);
          expect(f.y + f.h, `figure ${i} bottom`).toBeLessThanOrEqual(h);
        });
        // neighbours never touch: at least 4 px between their boxes
        for (let i = 1; i < n; i++) {
          const [a, b] = [figures[i - 1], figures[i]];
          if (!a || !b) throw new Error("missing figure");
          expect(overlaps(a, b, 4), `figures ${i - 1} and ${i}`).toBe(false);
        }
        // every seat's body stays outside the table: its centre is at least half a body beyond the table's edge
        for (const s of L.seats) {
          const d = Math.hypot(s.x - L.cx, s.y - L.flatY);
          expect(d - L.tableR, "body clear of table").toBeGreaterThanOrEqual(0.7 * L.headD);
        }
        // the table is still a table: wider than one figure
        expect(2 * L.tableR).toBeGreaterThanOrEqual(L.bodyW);
        // a bubble is never asked to be wider than the stage allows
        expect(L.bubbleMaxWidth).toBeLessThanOrEqual(Math.max(120, w / 2));
      });

      it(`${n} seats in ${w} x ${h}: a bubble that is placed never overlaps; one that cannot fit is left out`, () => {
        const L = tableLayout(n, w, h);
        const figures = Array.from({ length: n }, (_, i) => figureRect(L, i));
        const size = { w: Math.min(L.bubbleMaxWidth, 180), h: 30 };
        const all = Array.from({ length: n }, (_, i) => i);
        const boxes = placeBubbles(L, all, size);
        expect(boxes).toHaveLength(n);
        const placed: Rect[] = [];
        for (const box of boxes) {
          if (!box) continue; // left out: the speaker's ring still marks the seat
          expect(box.x).toBeGreaterThanOrEqual(0);
          expect(box.x + box.w).toBeLessThanOrEqual(w);
          expect(box.y).toBeGreaterThanOrEqual(0);
          for (const f of figures) expect(overlaps(box, f, 2)).toBe(false);
          for (const other of placed) expect(overlaps(box, other, 2)).toBe(false);
          placed.push(box);
        }
      });
    }
  }
});
