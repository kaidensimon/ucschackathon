// The live table: a hand-built event list, as the backend sends it (ui_bridge.py). A seat shows
// "thinking..." until its first note, then keeps its newest note until its next one.
import { describe, expect, it } from "vitest";
import type { DebateView } from "../lib/events";
import type { LiveBubble } from "../lib/timeline/bubble";
import { liveViewOf, THINKING, type WireEvent } from "./useLiveDebate";

let seq = 0;
/** one event `at` ms in; the debate clock runs with real time here */
const ev = (at: number, type: string, body: Record<string, unknown> = {}): WireEvent => {
  seq += 1;
  return { v: 1, seq, debateId: "run-1", at, clock: at, type, ...body };
};
const turn = (at: number, turnId: string, seatId: string, round: number): WireEvent[] => [
  ev(at, "turn.started", { turnId, seatId, round, kind: round === 0 ? "position" : "reply", to: "all" }),
  ev(at, "seat.thinking", { seatId, turnId, on: true }),
];
const note = (at: number, turnId: string, seatId: string, text: string): WireEvent[] => [
  ev(at, "summary.posted", { summaryId: `sum-${turnId}`, seatId, turnId, text, source: "self" }),
  ev(at, "seat.thinking", { seatId, turnId, on: false }),
];

const FIRST = "Canberra, and Mercury.";
const SECOND = "Still Canberra; I now back A1.";
const OTHER = "Canberra. Mercury is closest.";

const events: WireEvent[] = [
  ev(0, "debate.created", {
    question: "Capital of Australia?",
    files: [],
    // no time limit was sent
    limitMs: 0,
    seats: [
      { id: "s0", index: 0, shortName: "GPT-OSS", modelName: "gpt-oss:20b" },
      { id: "s1", index: 1, shortName: "Qwen", modelName: "qwen3.5" },
    ],
  }),
  ev(0, "phase.changed", { phase: "debate" }),
  ev(1000, "round.started", { round: 0 }),
  ...turn(1000, "t0a", "s0", 0),
  ...turn(1000, "t0b", "s1", 0),
  // the whole message is in long before its note
  ev(20000, "turn.ended", { turnId: "t0a", text: "The capital is Canberra.", citations: [] }),
  ...note(30000, "t0a", "s0", FIRST),
  ev(35000, "turn.ended", { turnId: "t0b", text: "Canberra.", citations: [] }),
  ...note(42000, "t0b", "s1", OTHER),
  ev(50000, "round.started", { round: 1 }),
  ...turn(50000, "t1a", "s0", 1),
  ev(60000, "lie.posted", { turnId: "t0b", seatId: "s1", score: 0.897, level: "ok", reasons: [] }),
  ev(80000, "turn.ended", { turnId: "t1a", text: "I back A1.", citations: [] }),
  ...note(90000, "t1a", "s0", SECOND),
  ev(95000, "lie.posted", { turnId: "t1a", seatId: "s0", score: 0.31, level: "flag", reasons: ["hedged"] }),
  ev(100000, "answer.released", {
    outcome: "agreed",
    turnId: "t1a",
    tallyRound: 0,
    rounds: 2,
    elapsedMs: 100000,
    dissentTurnIds: [],
  }),
];

/** the live view at real time `at`, from the events that have arrived by then */
function live(at: number): DebateView {
  const arrived = events.filter((e) => e.at <= at);
  const view = liveViewOf(arrived, at);
  if (!view) throw new Error(`no view at ${at}`);
  return view;
}
const bubble = (view: DebateView, seatId: string): LiveBubble | null =>
  view.seats.find((s) => s.id === seatId)?.bubble ?? null;

describe("liveViewOf: the notes at the table", () => {
  it("shows thinking before a seat's first note", () => {
    const v = live(5000);
    expect(bubble(v, "s0")).toMatchObject({ text: THINKING, opacity: 1 });
    expect(bubble(v, "s1")).toMatchObject({ text: THINKING, opacity: 1 });
    // still thinking after its message ended: the note has not come yet
    expect(bubble(live(25000), "s0")?.text).toBe(THINKING);
  });

  it("runs the clock with no time limit", () => {
    expect(live(5000).clock).toBe(5000);
  });

  it("fades the note in when it arrives", () => {
    expect(bubble(live(30125), "s0")).toMatchObject({ text: FIRST, opacity: 0.5 });
    const full = bubble(live(30250), "s0");
    expect(full).toMatchObject({ text: FIRST, opacity: 1 });
    expect(full?.dim).toBeUndefined();
    expect(full?.tag).toBeUndefined();
    // the other seat has no note yet
    expect(bubble(live(30250), "s1")?.text).toBe(THINKING);
  });

  it("keeps the note long past 10 s, and with nobody speaking", () => {
    for (const at of [41000, 45000, 49999]) {
      expect(bubble(live(at), "s0")).toMatchObject({ text: FIRST, opacity: 1 });
    }
    expect(live(45000).speaking).toEqual([]);
    expect(bubble(live(49999), "s1")).toMatchObject({ text: OTHER, opacity: 1 });
  });

  it("keeps the old note, dimmed and marked thinking, while the seat works on its next message", () => {
    const b = bubble(live(70000), "s0");
    expect(b).toMatchObject({ text: FIRST, opacity: 1, dim: true, tag: { text: THINKING } });
    // 40 s after it was posted
    expect(bubble(live(89999), "s0")?.text).toBe(FIRST);
  });

  it("replaces the note with the seat's next one, crossfading", () => {
    const mid = bubble(live(90100), "s0");
    expect(mid?.text).toBe(SECOND);
    expect(mid?.opacity).toBeCloseTo(0.4);
    expect(mid?.prev?.text).toBe(FIRST);
    expect(mid?.prev?.opacity).toBeCloseTo(0.6);
    const after = bubble(live(90250), "s0");
    expect(after).toMatchObject({ text: SECOND, opacity: 1 });
    expect(after?.prev).toBeUndefined();
    expect(after?.dim).toBeUndefined();
  });

  it("puts the lie-detector reading on the note of the message it is about", () => {
    expect(bubble(live(59999), "s1")?.tag).toBeUndefined();
    expect(bubble(live(60000), "s1")?.tag).toEqual({ text: "truth 0.90" });
    expect(bubble(live(94000), "s0")?.tag).toBeUndefined();
    // only a "flag" reading is drawn as a warning
    expect(bubble(live(95000), "s0")?.tag).toEqual({ text: "truth 0.31", flag: true });
  });

  it("leaves the last notes on the finished table", () => {
    for (const v of [live(100000), live(900000), liveViewOf(events)]) {
      expect(v?.answer?.outcome).toBe("agreed");
      expect(v?.seats.map((s) => s.bubble?.text)).toEqual([SECOND, OTHER]);
      expect(v?.seats.every((s) => s.bubble?.opacity === 1)).toBe(true);
    }
  });

  it("still adds the reading under the message in the chat", () => {
    const text = live(100000).turns.find((t) => t.turnId === "t0b")?.text;
    expect(text).toBe("Canberra.\n\n[Lie detector: ok (0.90)]");
  });

  it("is null before the debate is created", () => {
    expect(liveViewOf([])).toBeNull();
  });
});
