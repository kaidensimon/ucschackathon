// The sample debates the top bar's slider reaches (2 to 6 seats): each tells a story that fits
// its own council, and every named moment shows what its name says.
import { describe, expect, it } from "vitest";
import { needed } from "../lib/events";
import { viewAt } from "../lib/timeline/viewAt";
import { momentAt, momentNames } from "../review/moments";
import { bySeats, COUNCIL_MAX, COUNCIL_MIN, fixtures } from "./lease";

const EVERYONE = ["Phi", "Llama", "Granite", "Qwen", "Gemma", "Hermes", "Mistral"];

describe("one sample debate for each council size", () => {
  it("covers every size from the smallest to the largest", () => {
    for (let n = COUNCIL_MIN; n <= COUNCIL_MAX; n++) {
      const fx = fixtures[bySeats[n] ?? ""];
      expect(fx?.seats.length, `${n} seats`).toBe(n);
    }
  });

  const votes: Record<number, [agree: number, reached: boolean][]> = {
    2: [
      [1, false],
      [2, true],
    ],
    3: [
      [2, false],
      [3, true],
    ],
    4: [
      [2, false],
      [3, false],
      [4, true],
    ],
    5: [
      [2, false],
      [3, false],
      [4, true],
    ],
    6: [
      [3, false],
      [4, false],
      [5, true],
    ],
  };

  for (let n = COUNCIL_MIN; n <= COUNCIL_MAX; n++) {
    const id = bySeats[n] ?? "";
    const fx = fixtures[id];
    if (!fx) throw new Error(`no debate for ${n} seats`);
    const seated = fx.seats.map((s) => s.shortName);
    const absent = EVERYONE.filter((name) => !seated.includes(name));

    describe(`${n} seats (${id})`, () => {
      it("votes as its story says, and agrees only when enough seats do", () => {
        const tallies = fx.events.filter((e) => e.type === "tally.posted");
        expect(tallies.map((t) => (t.type === "tally.posted" ? [t.agree, t.reached] : []))).toEqual(votes[n]);
        for (const t of tallies) {
          if (t.type !== "tally.posted") continue;
          expect(t.seats).toBe(n);
          expect(t.needed).toBe(needed(n));
          expect(t.reached).toBe(t.agree >= needed(n));
        }
        const released = fx.events.find((e) => e.type === "answer.released");
        expect(released && released.type === "answer.released" ? released.outcome : "").toBe("agreed");
      });

      it("never has two seats talking at once", () => {
        let open = 0;
        for (const e of fx.events) {
          if (e.type === "turn.started") open++;
          if (e.type === "turn.ended") open--;
          expect(open).toBeLessThanOrEqual(1);
        }
      });

      it("never names a member who is not at this table", () => {
        const said: string[] = [];
        for (const e of fx.events) {
          if (e.type === "turn.ended") said.push(e.text);
          if (e.type === "summary.posted") said.push(e.text);
        }
        expect(said.length).toBeGreaterThan(0);
        for (const text of said) for (const name of absent) expect(text, `"${name}" in: ${text}`).not.toContain(name);
      });

      it("every named moment shows what its name says", () => {
        const at = (scene: string) => momentAt(id, scene);
        const view = (scene: string) => {
          const t = at(scene);
          if (t === undefined) throw new Error(`${id} has no moment "${scene}"`);
          return viewAt(fx.events, t);
        };
        // every debate has these
        expect(view("spooling").phase).toBe("spooling");
        expect(view("researching").phase).toBe("research");
        const debating = view("debating");
        expect(debating.phase).toBe("debate");
        expect(debating.speaking.length).toBe(1);
        const vote = view("vote");
        expect(vote.phase).toBe("vote");
        expect(vote.tally).not.toBeNull();
        expect(vote.seats.filter((s) => s.mark !== null)).toHaveLength(n);
        expect(vote.answer).toBeUndefined();
        const agreed = view("agreed");
        expect(agreed.tally?.reached).toBe(true);
        expect(agreed.phase).toBe("writing");
        expect(view("released").answer).toBeDefined();
        // a debate either has these moments and they are true, or it says it has not
        if (at("paused") !== undefined) expect(view("paused").paused).toBe(true);
        if (at("owner-note") !== undefined) {
          const waiting = view("owner-note");
          expect(waiting.notes.some((note) => note.state === "queued")).toBe(true);
          expect(waiting.speaking.length, "somebody is speaking while the note waits").toBe(1);
        }
        if (at("note-delivered") !== undefined)
          expect(view("note-delivered").notes.some((note) => note.state === "delivered")).toBe(true);
        // and no moment lands past the end by accident (only "released" shows the answer)
        for (const scene of momentNames) {
          const t = at(scene);
          if (t === undefined || scene === "released" || scene === "asking") continue;
          expect(viewAt(fx.events, t).answer, `${id} ${scene}`).toBeUndefined();
        }
      });
    });
  }
});
