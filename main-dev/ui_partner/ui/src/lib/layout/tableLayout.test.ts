// FROZEN: written by the lead before the code. Do not edit; report if a case looks wrong
// (2026-10-11, lead: the cap on bubbles at seven seats is gone. Lucas found the seven-seat
// bubbles "messed up"; they now fan outward and every seat may have one.)
// (if a case truly cannot be satisfied, report the exact case instead of bending the code).
import { describe, expect, it } from "vitest";
import { figureRect, placeBubbles, type Rect, type TableLayout, tableLayout } from "./tableLayout";

// stage sizes: the 1440 x 830 window, and the 1024 x 768 window with the icon rail
const STAGES: [number, number][] = [
  [1040, 558],
  [912, 560],
];
const GAP = 4; // clear space required between any two boxes

const overlaps = (a: Rect, b: Rect, gap = 0) =>
  a.x < b.x + b.w + gap && b.x < a.x + a.w + gap && a.y < b.y + b.h + gap && b.y < a.y + a.h + gap;

function subsets(n: number, max: number): number[][] {
  const out: number[][] = [];
  for (let mask = 1; mask < 1 << n; mask++) {
    const set: number[] = [];
    for (let i = 0; i < n; i++) if (mask & (1 << i)) set.push(i);
    if (set.length <= max) out.push(set);
  }
  return out;
}

describe("seat positions", () => {
  it("matches the reference numbers used by the look studies (1040 x 558)", () => {
    const five = tableLayout(5, 1040, 558);
    expect(five).toMatchObject({ n: 5, cx: 520, flatY: 520, headD: 72, r: 263, bubbleMaxWidth: 280, maxBubbles: 5 });
    // the table stops short of the end seats' bodies: ring radius - half a body - 8
    expect(five.tableR).toBe(Math.floor(263 - 0.7 * 72 - 8));
    expect(five.tableR).toBe(204);
    expect(five.bodyW).toBeCloseTo(100.8, 5);
    expect(five.bodyH).toBeCloseTo(50.4, 5);
    const seven = tableLayout(7, 1040, 558);
    expect(seven).toMatchObject({ n: 7, headD: 64, r: 277, bubbleMaxWidth: 240, maxBubbles: 7 });
    expect(seven.tableR).toBe(224);
    // seat i of N sits at 180 x (i - 0.5) / N degrees from the left end of the flat edge
    const angles = five.seats.map((s) => (Math.atan2(five.flatY - s.y, five.cx - s.x) * 180) / Math.PI);
    for (const [i, deg] of [18, 54, 90, 126, 162].entries()) expect(angles[i]).toBeCloseTo(deg, 1);
    expect(five.seats[2]?.x).toBeCloseTo(520, 1);
    expect(five.seats[2]?.y).toBeCloseTo(520 - 263, 1);
  });

  it("uses smaller heads and bubbles on the narrow stage, and lets every seat have a bubble", () => {
    expect(tableLayout(5, 912, 560)).toMatchObject({ headD: 64, bubbleMaxWidth: 216, maxBubbles: 5 });
    expect(tableLayout(6, 912, 560)).toMatchObject({ headD: 56, bubbleMaxWidth: 200, maxBubbles: 6 });
    expect(tableLayout(7, 912, 560)).toMatchObject({ headD: 56, bubbleMaxWidth: 200, maxBubbles: 7 });
    expect(tableLayout(6, 1040, 558)).toMatchObject({ headD: 64, bubbleMaxWidth: 240, maxBubbles: 6 });
    expect(tableLayout(3, 1040, 558)).toMatchObject({ headD: 72, bubbleMaxWidth: 280, maxBubbles: 3 });
  });

  for (const [w, h] of STAGES) {
    for (let n = 3; n <= 7; n++) {
      it(`${n} seats in ${w} x ${h}: mirror-symmetric, inside the stage, figures apart`, () => {
        const L = tableLayout(n, w, h);
        expect(L.seats).toHaveLength(n);
        for (let i = 0; i < n; i++) {
          const a = L.seats[i];
          const b = L.seats[n - 1 - i];
          if (!a || !b) throw new Error("missing seat");
          expect(a.x + b.x).toBeCloseTo(2 * L.cx, 1);
          expect(a.y).toBeCloseTo(b.y, 1);
          const f = figureRect(L, i);
          expect(f.w).toBeCloseTo(L.bodyW, 5);
          expect(f.h).toBeCloseTo(L.headD + 2 + L.bodyH, 5);
          expect(f.x).toBeCloseTo(a.x - L.bodyW / 2, 5);
          expect(f.y + f.h).toBeCloseTo(a.y, 5);
          expect(f.x).toBeGreaterThanOrEqual(0);
          expect(f.x + f.w).toBeLessThanOrEqual(w);
          expect(f.y).toBeGreaterThanOrEqual(0);
          expect(f.y + f.h).toBeLessThanOrEqual(h);
        }
        for (let i = 1; i < n; i++) expect(overlaps(figureRect(L, i - 1), figureRect(L, i))).toBe(false);
      });
    }
  }
});

describe("bubbles never overlap", () => {
  for (const [w, h] of STAGES) {
    for (let n = 3; n <= 7; n++) {
      it(`${n} seats in ${w} x ${h}: every set of talking seats up to the cap`, () => {
        const L: TableLayout = tableLayout(n, w, h);
        const sizes = [
          { w: L.bubbleMaxWidth, h: 52 },
          { w: L.bubbleMaxWidth, h: 30 },
          { w: 160, h: 52 },
        ];
        const figures = Array.from({ length: n }, (_, i) => figureRect(L, i));
        for (const size of sizes) {
          for (const set of subsets(n, L.maxBubbles)) {
            const boxes = placeBubbles(L, set, size);
            expect(boxes).toHaveLength(set.length);
            const placed: Rect[] = [];
            boxes.forEach((box, k) => {
              const seat = set[k] ?? -1;
              const label = `seats ${JSON.stringify(set)} size ${size.w}x${size.h} seat ${seat}`;
              // Six or seven seats: a bubble with no tidy spot (on its own side, tail on its own head)
              // is left out. But a seat talking ALONE always gets its bubble.
              if (!box && n >= 6 && set.length > 1) return;
              if (!box) throw new Error(`no box: ${label}`);
              expect(box.w, label).toBe(size.w);
              expect(box.h, label).toBe(size.h);
              expect(box.x, label).toBeGreaterThanOrEqual(0);
              expect(box.x + box.w, label).toBeLessThanOrEqual(w);
              expect(box.y, label).toBeGreaterThanOrEqual(0);
              // above its own figure, and within reach of it
              const own = figures[seat];
              if (!own) throw new Error("no figure");
              expect(box.y + box.h, label).toBeLessThanOrEqual(own.y - 8);
              const centre = box.x + box.w / 2;
              expect(Math.abs(centre - (own.x + own.w / 2)), label).toBeLessThanOrEqual(L.bubbleMaxWidth);
              for (const f of figures) expect(overlaps(box, f, GAP), label).toBe(false);
              for (const other of placed) expect(overlaps(box, other, GAP), label).toBe(false);
              placed.push(box);
            });
          }
        }
      });
    }
  }

  it("at six and seven seats the bubbles fan out: each stays on its own side, and the sides mirror", () => {
    for (const [w, h] of STAGES) {
      for (const n of [6, 7]) {
        const L = tableLayout(n, w, h);
        const all = Array.from({ length: n }, (_, i) => i);
        const boxes = placeBubbles(L, all, { w: L.bubbleMaxWidth, h: 69 });
        const at = `${n} seats in ${w} x ${h}`;
        // on the wide full-size table every seat gets its bubble, even with all of them talking
        if (w >= 1000)
          expect(
            boxes.every((b) => b !== null),
            at,
          ).toBe(true);
        const middle = (n - 1) / 2;
        boxes.forEach((box, seat) => {
          const own = L.seats[seat];
          if (!box || !own || seat === middle) return;
          const inward = L.seats[seat < middle ? seat + 1 : seat - 1];
          if (!inward) throw new Error("no neighbour");
          // (a bubble wider than the room between the stage's edge and the line, as at an end
          // seat on the narrow stage, reaches across only as far as it must)
          const halfway = (own.x + inward.x) / 2;
          if (seat < middle)
            expect(box.x + box.w, `${at}, seat ${seat} leans left`).toBeLessThanOrEqual(Math.max(halfway, box.w));
          else expect(box.x, `${at}, seat ${seat} leans right`).toBeGreaterThanOrEqual(Math.min(halfway, w - box.w));
          // and its tail can land on its own head
          expect(Math.abs(Math.max(box.x + 14, Math.min(box.x + box.w - 14, own.x)) - own.x)).toBeLessThanOrEqual(
            L.headD / 2,
          );
        });
        // when all of them fit, the left side is the mirror of the right
        // (when they do not, the seats named first are served first, which need not be even)
        if (boxes.some((b) => b === null)) continue;
        for (let i = 0; i < n; i++) {
          const [a, b] = [boxes[i], boxes[n - 1 - i]];
          if (!a || !b) continue;
          expect(Math.abs(a.x + a.w / 2 + (b.x + b.w / 2) - w), `${at}: mirror ${i}`).toBeLessThanOrEqual(2);
          expect(Math.abs(a.y - b.y), `${at}: mirror height ${i}`).toBeLessThanOrEqual(1);
        }
      }
    }
  });

  it("is pure: the same input gives the same boxes", () => {
    const L = tableLayout(5, 1040, 558);
    expect(placeBubbles(L, [2, 3, 1], { w: 280, h: 52 })).toEqual(placeBubbles(L, [2, 3, 1], { w: 280, h: 52 }));
  });
});
