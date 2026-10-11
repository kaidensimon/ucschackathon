// FROZEN: written by the lead before the code. Do not edit; report if a case looks wrong.
import { describe, expect, it } from "vitest";
import { c } from "../../fixtures/build";
import { lease, lease7Busy, leaseFailed, leaseTimeUp } from "../../fixtures/lease";
import type { DebateView } from "../events";
import { viewAt } from "./viewAt";

const id = (view: DebateView, name: string) => view.seats.find((s) => s.shortName === name)?.id ?? "?";
const seatOf = (view: DebateView, name: string) => {
  const s = view.seats.find((x) => x.shortName === name);
  if (!s) throw new Error(`no seat ${name}`);
  return s;
};
const at = (m: number, s = 0) => lease.at(c(m, s));

describe("viewAt on the main sample", () => {
  it("before anything: idle", () => {
    const v = viewAt(lease.events, -1);
    expect(v.phase).toBe("idle");
    expect(v.seats).toEqual([]);
    expect(v.turns).toEqual([]);
  });

  it("seating: three of five ready at 10 s, clock not started", () => {
    const v = viewAt(lease.events, 10000);
    expect(v.phase).toBe("spooling");
    expect(v.clock).toBe(0);
    expect(v.leftMs).toBe(300000);
    expect(v.seats.map((s) => s.shortName)).toEqual(["Phi", "Llama", "Qwen", "Gemma", "Mistral"]);
    expect(v.seats.filter((s) => s.status === "ready").map((s) => s.shortName)).toEqual(["Phi", "Llama", "Gemma"]);
    expect(v.seats.filter((s) => s.status === "loading").map((s) => s.shortName)).toEqual(["Qwen", "Mistral"]);
    expect(v.speaking).toEqual([]);
    expect(v.tally).toBeNull();
  });

  it("reading files at 0:15: Qwen is researching, nobody is 'speaking'", () => {
    const v = viewAt(lease.events, at(0, 15));
    expect(v.phase).toBe("research");
    expect(v.round).toBe(0);
    expect(v.clock).toBe(15000);
    expect(seatOf(v, "Qwen").activity).toBe("researching");
    expect(seatOf(v, "Phi").activity).toBe("idle");
    expect(v.speaking).toEqual([]);
    expect(seatOf(v, "Qwen").bubble?.text).toBe("Reading Renewal letter 2026.pdf, page 1");
  });

  it("after the round 1 vote: marks on every head, 2 of 5, needs 4", () => {
    const v = viewAt(lease.events, at(1, 26));
    expect(v.phase).toBe("vote");
    expect(v.tally).toMatchObject({ round: 1, agree: 2, seats: 5, needed: 4, reached: false, leading: "A" });
    expect(v.seats.map((s) => s.mark)).toEqual(["differs", "differs", "agrees", "agrees", "differs"]);
  });

  it("the canonical moment, 1:50: 3:10 left, Qwen speaking, bubbles full, full, half", () => {
    const v = viewAt(lease.events, at(1, 50));
    expect(v.phase).toBe("debate");
    expect(v.round).toBe(2);
    expect(v.paused).toBe(false);
    expect(v.clock).toBe(110000);
    expect(v.leftMs).toBe(190000);
    expect(v.speaking).toEqual([id(v, "Qwen")]);
    expect(seatOf(v, "Qwen").activity).toBe("speaking");
    // the agreement number only changes at a vote
    expect(v.tally).toMatchObject({ round: 1, agree: 2, needed: 4 });
    // marks clear when the next round starts
    expect(v.seats.every((s) => s.mark === null)).toBe(true);
    expect(seatOf(v, "Qwen").bubble).toMatchObject({
      text: "Tells Mistral the fee is one month at the new rent.",
      opacity: 1,
    });
    expect(seatOf(v, "Gemma").bubble).toMatchObject({
      text: "Cites the renewal letter, page 1: fee is one month.",
      opacity: 1,
    });
    expect(seatOf(v, "Llama").bubble?.text).toBe("Holds that a letter cannot change the lease.");
    expect(seatOf(v, "Llama").bubble?.opacity).toBeCloseTo(0.5, 5);
    expect(seatOf(v, "Phi").bubble).toBeNull();
    expect(seatOf(v, "Mistral").bubble).toBeNull();
    // Qwen's turn is open: text so far is the start of the full text
    const turn = v.turns.find((t) => t.seatId === id(v, "Qwen") && !t.done);
    expect(turn).toBeDefined();
    expect(turn?.to).toEqual([id(v, "Mistral")]);
    expect(turn?.text.length).toBeGreaterThan(0);
    expect("Mistral, you are right that the new rent applies".startsWith(turn?.text.slice(0, 20) ?? "x")).toBe(true);
  });

  it("a replacement bubble crossfades in place", () => {
    const v = viewAt(lease.events, at(1, 41) + 100);
    const b = seatOf(v, "Llama").bubble;
    expect(b?.text).toBe("Holds that a letter cannot change the lease.");
    expect(b?.opacity).toBeCloseTo(0.4, 5);
    expect(b?.prev?.text).toBe("Answers Qwen: the lease still stands as written.");
    expect(b?.prev?.opacity).toBeCloseTo(0.6, 5);
    const later = viewAt(lease.events, at(1, 41) + 300);
    expect(seatOf(later, "Llama").bubble?.prev).toBeUndefined();
  });

  it("pause holds the clock, the bubbles and the open turn", () => {
    const a = viewAt(lease.events, lease.at(c(2, 2)) + 2000);
    const b = viewAt(lease.events, lease.at(c(2, 2)) + 14000);
    expect(a.paused).toBe(true);
    expect(b.paused).toBe(true);
    expect(a.clock).toBe(122000);
    expect(b.clock).toBe(122000);
    expect(b.seats.map((s) => s.bubble)).toEqual(a.seats.map((s) => s.bubble));
    expect(b.turns).toEqual(a.turns);
    const after = viewAt(lease.events, lease.at(c(2, 2)) + 15000 + 1000);
    expect(after.paused).toBe(false);
    expect(after.clock).toBe(123000);
  });

  it("the owner's note is queued in round 2 and delivered at the start of round 3", () => {
    const q = viewAt(lease.events, at(2, 16));
    expect(q.notes).toEqual([
      { noteId: "n1", text: "I want to be out by the end of February.", state: "queued", round: 2 },
    ]);
    const d = viewAt(lease.events, at(2, 50));
    expect(d.notes[0]).toMatchObject({ state: "delivered", round: 3 });
    expect(d.round).toBe(3);
  });

  it("agreed at 3:40: the clock stops and Qwen writes", () => {
    const v = viewAt(lease.events, at(3, 40) + 3000);
    expect(v.phase).toBe("writing");
    expect(v.clock).toBe(220000);
    expect(v.leftMs).toBe(80000);
    expect(v.tally).toMatchObject({ round: 3, agree: 4, seats: 5, needed: 4, reached: true });
    expect(seatOf(v, "Qwen").activity).toBe("writing");
    expect(v.speaking).toEqual([]);
    expect(v.seats.map((s) => s.mark)).toEqual(["differs", "agrees", "agrees", "agrees", "agrees"]);
    expect(v.answer).toBeUndefined();
  });

  it("released: the answer, one dissent, marks still on the heads", () => {
    const v = viewAt(lease.events, lease.endAt);
    expect(v.phase).toBe("released");
    expect(v.answer).toMatchObject({ outcome: "agreed", agree: 4, seats: 5, rounds: 3, elapsedMs: 220000 });
    const answer = v.turns.find((t) => t.turnId === v.answer?.turnId);
    expect(answer?.done).toBe(true);
    expect(answer?.text.startsWith("Yes. You can end the lease early")).toBe(true);
    expect(v.answer?.dissentTurnIds).toHaveLength(1);
    const dissent = v.turns.find((t) => t.turnId === v.answer?.dissentTurnIds[0]);
    expect(dissent?.seatId).toBe(id(v, "Phi"));
    expect(v.seats.map((s) => s.mark)).toEqual(["differs", "agrees", "agrees", "agrees", "agrees"]);
    expect(v.turns.every((t) => t.done)).toBe(true);
    expect(v.speaking).toEqual([]);
  });

  it("is pure, and far in the future equals the end", () => {
    const t = at(1, 50);
    expect(viewAt(lease.events, t)).toEqual(viewAt(lease.events, t));
    expect(viewAt(lease.events, lease.endAt + 3600000)).toEqual(viewAt(lease.events, lease.endAt));
  });

  it("turns are listed in the order they started, with text growing and never shrinking", () => {
    let lastLen = 0;
    for (let s = 48; s <= 58; s += 1) {
      const v = viewAt(lease.events, at(1, s) + 500);
      const turn = v.turns.find((x) => x.seatId === id(v, "Qwen") && x.round === 2);
      const len = turn?.text.length ?? 0;
      expect(len).toBeGreaterThanOrEqual(lastLen);
      lastLen = len;
    }
    const v = viewAt(lease.events, lease.endAt);
    const clocks = v.turns.map((t) => t.clock);
    expect([...clocks].sort((a, b) => a - b)).toEqual(clocks);
  });

  it("with reduced motion a bubble is shown or gone, never in between", () => {
    for (let s = 30; s <= 220; s += 3) {
      const v = viewAt(lease.events, lease.at(s * 1000), { reducedMotion: true });
      for (const seat of v.seats) {
        if (seat.bubble) {
          expect(seat.bubble.opacity).toBe(1);
          expect(seat.bubble.prev).toBeUndefined();
        }
      }
    }
    const v = viewAt(lease.events, at(1, 50), { reducedMotion: true });
    expect(seatOf(v, "Llama").bubble).toBeNull();
    expect(seatOf(v, "Qwen").bubble?.opacity).toBe(1);
  });
});

describe("viewAt on the variants", () => {
  it("several seats may talk at once", () => {
    const v = viewAt(lease7Busy.events, lease7Busy.at(c(1, 50)));
    expect(v.speaking).toHaveLength(5);
    expect(v.seats.filter((s) => s.bubble && s.bubble.opacity === 1)).toHaveLength(5);
  });

  it("time runs out: no consensus on the last completed vote", () => {
    const v = viewAt(leaseTimeUp.events, leaseTimeUp.endAt);
    expect(v.limitMs).toBe(120000);
    expect(v.clock).toBe(120000);
    expect(v.leftMs).toBe(0);
    expect(v.answer).toMatchObject({ outcome: "no-consensus", agree: 2, seats: 5, rounds: 2 });
    expect(v.answer?.dissentTurnIds).toHaveLength(3);
  });

  it("a model that fails to load is marked failed with its reason kept in the events", () => {
    const v = viewAt(leaseFailed.events, 7000);
    expect(v.seats.find((s) => s.shortName === "Phi")?.status).toBe("failed");
    expect(v.phase).toBe("spooling");
  });
});
