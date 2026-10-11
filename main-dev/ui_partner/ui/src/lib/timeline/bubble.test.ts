// FROZEN: written by the lead before the code. Do not edit; report if a case looks wrong.
import { describe, expect, it } from "vitest";
import { BUBBLE, bubbleOpacity } from "./bubble";

describe("bubble timing", () => {
  it("keeps the plan's numbers", () => {
    expect(BUBBLE).toEqual({ fadeInMs: 250, holdMs: 8000, fadeOutMs: 1500 });
  });
  it("fades in over 250 ms, holds 8 s, fades out over 1.5 s", () => {
    expect(bubbleOpacity(-1)).toBe(0);
    expect(bubbleOpacity(0)).toBe(0);
    expect(bubbleOpacity(125)).toBeCloseTo(0.5, 5);
    expect(bubbleOpacity(250)).toBe(1);
    expect(bubbleOpacity(4000)).toBe(1);
    expect(bubbleOpacity(8250)).toBe(1);
    expect(bubbleOpacity(9000)).toBeCloseTo(0.5, 5);
    expect(bubbleOpacity(9750)).toBe(0);
    expect(bubbleOpacity(60000)).toBe(0);
  });
  it("never leaves 0..1 and never rises again after the hold", () => {
    let last = 1;
    for (let age = 8250; age <= 10000; age += 50) {
      const o = bubbleOpacity(age);
      expect(o).toBeGreaterThanOrEqual(0);
      expect(o).toBeLessThanOrEqual(1);
      expect(o).toBeLessThanOrEqual(last);
      last = o;
    }
  });
  it("with reduced motion is only shown or gone", () => {
    for (let age = -500; age <= 11000; age += 125) {
      const o = bubbleOpacity(age, { reducedMotion: true });
      expect([0, 1]).toContain(o);
    }
    expect(bubbleOpacity(0, { reducedMotion: true })).toBe(1);
    expect(bubbleOpacity(8250, { reducedMotion: true })).toBe(1);
    expect(bubbleOpacity(8251, { reducedMotion: true })).toBe(0);
    expect(bubbleOpacity(-1, { reducedMotion: true })).toBe(0);
  });
});
