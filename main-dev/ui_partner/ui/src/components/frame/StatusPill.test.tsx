import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { fixtures } from "../../fixtures/lease";
import { viewAt } from "../../lib/timeline/viewAt";
import { momentAt } from "../../review/moments";
import { announcement } from "./LiveRegion";
import { StatusPill } from "./StatusPill";
import { shortcutFor } from "./useShortcuts";

afterEach(cleanup);

const at = (fixtureId: string, scene: string) => {
  const fixture = fixtures[fixtureId];
  const when = momentAt(fixtureId, scene);
  if (!fixture || when === undefined) throw new Error(`no ${fixtureId} ${scene}`);
  return viewAt(fixture.events, when);
};
const words = (fixtureId: string, scene: string) => {
  const { container } = render(<StatusPill view={at(fixtureId, scene)} />);
  const pill = container.querySelector("[data-part=status-pill]");
  const text = pill?.textContent?.replace(/\s+/g, " ").trim();
  cleanup();
  return { text, tone: pill?.getAttribute("data-tone") };
};

describe("StatusPill words", () => {
  it.each([
    ["lease", "asking", "Waiting for a question", "plain"],
    ["lease", "spooling", "Seating the council, 3 of 5 ready", "plain"],
    ["lease", "researching", "Reading your files 4:45 left", "plain"],
    ["lease", "debating", "Round 2 3:10 left 2 of 5 agree", "plain"],
    ["lease", "vote", "Round 2 vote 3 of 5 agree", "plain"],
    ["lease", "paused", "Paused in round 2", "plain"],
    ["lease", "agreed", "Agreed 4 of 5, writing the answer", "agreed"],
    ["lease", "released", "Agreed 4 of 5", "agreed"],
    ["lease-timeup", "released", "No consensus, 2 of 5", "plain"],
    ["lease-failed", "failed", "Phi did not load", "error"],
    ["lease-7", "vote", "Round 1 vote 4 of 7 agree", "plain"],
  ])("%s at %s: %s", (fixtureId, scene, text, tone) => {
    expect(words(fixtureId, scene)).toEqual({ text, tone });
  });

  it("before the first vote it says so", () => {
    const fixture = fixtures.lease;
    if (!fixture) throw new Error("no lease");
    const view = viewAt(fixture.events, fixture.at(40000));
    const { container } = render(<StatusPill view={view} />);
    expect(container.textContent?.replace(/\s+/g, " ").trim()).toBe("Round 1 4:20 left No vote yet");
  });

  it("is not a live region (the time changes every second)", () => {
    const { container } = render(<StatusPill view={at("lease", "debating")} />);
    expect(container.querySelector("[aria-live], [role=status], output")).toBeNull();
  });
});

describe("what the live region says", () => {
  it("nothing on opening a screen, nothing when only the clock moved", () => {
    expect(announcement(null, at("lease", "debating"))).toBeNull();
    const fixture = fixtures.lease;
    if (!fixture) throw new Error("no lease");
    const a = viewAt(fixture.events, fixture.at(100000));
    const b = viewAt(fixture.events, fixture.at(101000));
    expect(announcement(a, b)).toBeNull();
  });

  it("a vote, agreement, and the outcome", () => {
    expect(announcement(at("lease", "debating"), at("lease", "vote"))).toBe("Round 2 vote: 3 of 5 agree, needs 4.");
    expect(announcement(at("lease", "vote"), at("lease", "agreed"))).toBe("Agreed 4 of 5.");
    expect(announcement(at("lease", "agreed"), at("lease", "released"))).toBe("Agreed 4 of 5. The answer is ready.");
    expect(announcement(at("lease-timeup", "debating"), at("lease-timeup", "released"))).toBe(
      "No consensus, 2 of 5 backed this answer.",
    );
  });

  it("a new round", () => {
    const fixture = fixtures.lease;
    if (!fixture) throw new Error("no lease");
    const before = viewAt(fixture.events, fixture.at(85000));
    const after = viewAt(fixture.events, fixture.at(91000));
    expect(announcement(before, after)).toBe("Round 2.");
  });
});

describe("shortcuts", () => {
  const input = document.createElement("textarea");
  const button = document.createElement("button");

  it("maps the keys", () => {
    expect(shortcutFor({ key: "?" })).toEqual({ kind: "help" });
    expect(shortcutFor({ key: "/" })).toEqual({ kind: "message" });
    expect(shortcutFor({ key: "t" })).toEqual({ kind: "view", view: "table" });
    expect(shortcutFor({ key: "C" })).toEqual({ kind: "view", view: "chat" });
    expect(shortcutFor({ key: " " })).toEqual({ kind: "pause" });
    expect(shortcutFor({ key: "3" })).toEqual({ kind: "seat", index: 2 });
    expect(shortcutFor({ key: "8" })).toBeNull();
    expect(shortcutFor({ key: "Escape" })).toEqual({ kind: "close" });
  });

  it("never fires while typing, except Esc", () => {
    for (const key of ["?", "/", "t", "c", " ", "1"]) expect(shortcutFor({ key, target: input })).toBeNull();
    expect(shortcutFor({ key: "Escape", target: input })).toEqual({ kind: "close" });
  });

  it("leaves Space to a focused button, and Cmd or Ctrl combinations to the system", () => {
    expect(shortcutFor({ key: " ", target: button })).toBeNull();
    expect(shortcutFor({ key: "t", target: button })).toEqual({ kind: "view", view: "table" });
    expect(shortcutFor({ key: "c", metaKey: true })).toBeNull();
    expect(shortcutFor({ key: "t", ctrlKey: true })).toBeNull();
  });
});
