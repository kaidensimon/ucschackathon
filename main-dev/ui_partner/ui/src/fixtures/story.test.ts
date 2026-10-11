// FROZEN: written by the lead. Pins the sample debate so no screen can drift from another.
import { describe, expect, it } from "vitest";
import { needed } from "../lib/events";
import { c } from "./build";
import { fixtures, lease, lease3, lease7 } from "./lease";

describe("every sample debate is well formed", () => {
  for (const [name, fx] of Object.entries(fixtures)) {
    describe(name, () => {
      const events = fx.events;
      it("numbers its events 1, 2, 3 and never goes back in time", () => {
        events.forEach((e, i) => {
          expect(e.seq).toBe(i + 1);
          expect(e.v).toBe(1);
        });
        for (let i = 1; i < events.length; i++) {
          const [a, b] = [events[i - 1], events[i]];
          if (!a || !b) continue;
          expect(b.at).toBeGreaterThanOrEqual(a.at);
          expect(b.clock).toBeGreaterThanOrEqual(a.clock);
        }
      });
      it("never runs the clock past the limit, and holds it while paused", () => {
        const created = events.find((e) => e.type === "debate.created");
        const limit = created && created.type === "debate.created" ? created.limitMs : 0;
        for (const e of events) expect(e.clock).toBeLessThanOrEqual(limit);
        let pausedAt: number | null = null;
        for (const e of events) {
          if (e.type === "clock.paused") pausedAt = e.clock;
          else if (e.type === "clock.resumed") pausedAt = null;
          else if (pausedAt !== null) expect(e.clock).toBe(pausedAt);
        }
      });
      it("ends every turn it starts (except the labelled stress case)", () => {
        const started = events
          .filter((e) => e.type === "turn.started")
          .map((e) => (e.type === "turn.started" ? e.turnId : ""));
        const ended = events
          .filter((e) => e.type === "turn.ended")
          .map((e) => (e.type === "turn.ended" ? e.turnId : ""));
        expect(new Set(started).size).toBe(started.length);
        if (name === "lease-7-busy") expect(started.length - ended.length).toBe(5);
        else expect([...ended].sort()).toEqual([...started].sort());
      });
      it("cites only attached files and pages that exist", () => {
        const created = events.find((e) => e.type === "debate.created");
        const files = created && created.type === "debate.created" ? created.files : [];
        for (const e of events) {
          if (e.type !== "turn.ended") continue;
          for (const cite of e.citations) {
            expect(cite.kind).toBe("file");
            if (cite.kind !== "file") continue;
            const file = files.find((f) => f.id === cite.fileId);
            expect(file).toBeDefined();
            if (cite.page !== undefined) {
              expect(cite.page).toBeGreaterThanOrEqual(1);
              expect(cite.page).toBeLessThanOrEqual(file?.pages ?? 0);
            }
          }
        }
      });
      it("keeps short names to 7 characters and bubble lines to 55", () => {
        for (const s of fx.seats) expect(s.shortName.length).toBeLessThanOrEqual(7);
        expect(new Set(fx.seats.map((s) => s.shortName)).size).toBe(fx.seats.length);
        for (const e of events) if (e.type === "summary.posted") expect(e.text.length).toBeLessThanOrEqual(55);
      });
      it("counts every tally correctly", () => {
        for (const e of events) {
          if (e.type !== "tally.posted") continue;
          const sizes = e.groups.map((g) => g.seatIds.length);
          expect(sizes.reduce((a, b) => a + b, 0)).toBe(e.seats);
          expect(e.agree).toBe(Math.max(...sizes));
          expect(e.needed).toBe(needed(e.seats));
          expect(e.reached).toBe(e.agree >= e.needed);
          const all = e.groups.flatMap((g) => g.seatIds);
          expect(new Set(all).size).toBe(all.length);
        }
      });
    });
  }
});

describe("the main story", () => {
  const tallies = lease.events.filter((e) => e.type === "tally.posted");
  it("has three votes: 2, then 3, then 4 of 5", () => {
    expect(tallies.map((e) => (e.type === "tally.posted" ? [e.agree, e.seats, e.reached] : []))).toEqual([
      [2, 5, false],
      [3, 5, false],
      [4, 5, true],
    ]);
  });
  it("never has two seats talking at once", () => {
    let open = 0;
    for (const e of lease.events) {
      if (e.type === "turn.started") open++;
      if (e.type === "turn.ended") open--;
      expect(open).toBeLessThanOrEqual(1);
    }
  });
  it("seats the council in 18 s and agrees at 3:40 on the clock", () => {
    expect(lease.clockStartAt).toBe(18000);
    const released = lease.events.find((e) => e.type === "answer.released");
    expect(released && released.type === "answer.released" ? released.elapsedMs : 0).toBe(c(3, 40));
    expect(released && released.type === "answer.released" ? released.dissentTurnIds.length : 0).toBe(1);
  });
  it("delivers the owner's note at the start of the round after it was queued", () => {
    const q = lease.events.find((e) => e.type === "note.queued");
    const d = lease.events.find((e) => e.type === "note.delivered");
    const r3 = lease.events.find((e) => e.type === "round.started" && e.round === 3);
    expect(q && q.type === "note.queued" ? q.round : 0).toBe(2);
    expect(d && d.type === "note.delivered" ? d.round : 0).toBe(3);
    expect(d?.clock).toBe(r3?.clock);
  });
  it("has the three-seat and seven-seat variants voting 2 of 3 then 3 of 3, and 4 of 7 needing 6", () => {
    const t3 = lease3.events.filter((e) => e.type === "tally.posted");
    expect(t3.map((e) => (e.type === "tally.posted" ? [e.agree, e.seats, e.needed, e.reached] : []))).toEqual([
      [2, 3, 3, false],
      [3, 3, 3, true],
    ]);
    const t7 = lease7.events.filter((e) => e.type === "tally.posted");
    expect(t7.map((e) => (e.type === "tally.posted" ? [e.agree, e.seats, e.needed, e.reached] : []))).toEqual([
      [4, 7, 6, false],
    ]);
  });
});
