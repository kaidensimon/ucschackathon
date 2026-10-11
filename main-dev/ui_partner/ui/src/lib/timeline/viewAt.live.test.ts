// viewAt's `live` option: notes stay. Off by default, so the recorded samples are untouched.
import { describe, expect, it } from "vitest";
import { c } from "../../fixtures/build";
import { lease } from "../../fixtures/lease";
import { liveOpacity } from "./bubble";
import { viewAt } from "./viewAt";

describe("viewAt, live", () => {
  it("changes nothing unless asked", () => {
    for (const [m, s] of [[0, 10], [0, 50], [1, 50], [3, 20], [4, 50]] as const) {
      const at = lease.at(c(m, s));
      expect(viewAt(lease.events, at, { live: false })).toEqual(viewAt(lease.events, at));
    }
  });

  it("keeps every seat's newest note, however old", () => {
    // long after the last note of the sample
    const at = lease.events.reduce((last, e) => Math.max(last, e.at), 0) + 60000;
    const notes = new Map<string, string>();
    for (const e of lease.events) if (e.type === "summary.posted") notes.set(e.seatId, e.text);
    const recorded = viewAt(lease.events, at);
    const live = viewAt(lease.events, at, { live: true });
    expect(notes.size).toBeGreaterThan(0);
    for (const seat of live.seats) {
      const text = notes.get(seat.id);
      if (text === undefined) expect(seat.bubble).toBeNull();
      else expect(seat.bubble).toMatchObject({ text, opacity: 1 });
    }
    // everything else is the same view
    expect({ ...live, seats: [] }).toEqual({ ...recorded, seats: [] });
  });

  it("fades a live note in over 250 ms of real time and then holds it", () => {
    expect(liveOpacity(-1)).toBe(0);
    expect(liveOpacity(0)).toBe(0);
    expect(liveOpacity(125)).toBe(0.5);
    expect(liveOpacity(250)).toBe(1);
    expect(liveOpacity(3600000)).toBe(1);
    expect(liveOpacity(0, { reducedMotion: true })).toBe(1);
    expect(liveOpacity(Number.NaN)).toBe(0);
  });
});
