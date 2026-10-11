import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { sampleView } from "../../gallery/entry";
import type { DebateView } from "../../lib/events";
import { figureRect, tableLayout } from "../../lib/layout/tableLayout";
import { TableView } from "./TableView";

afterEach(cleanup);

const W = 1040;
const H = 558;

function table(view: DebateView, width = W, height = H) {
  const onOpenSeat = vi.fn();
  const utils = render(<TableView view={view} width={width} height={height} onOpenSeat={onOpenSeat} />);
  const all = <T extends Element = HTMLElement>(selector: string) => [...utils.container.querySelectorAll<T>(selector)];
  return { ...utils, onOpenSeat, all, seats: () => all<HTMLButtonElement>("[data-part=seat]") };
}

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}
const styleBox = (el: HTMLElement): Box => ({
  x: Number.parseFloat(el.style.left),
  y: Number.parseFloat(el.style.top),
  w: Number.parseFloat(el.style.width),
  h: Number.parseFloat(el.style.height),
});
const touch = (a: Box, b: Box) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

describe("TableView", () => {
  it("seats five, each one button that says its name, state and last vote", () => {
    const t = table(sampleView("lease", "debating"));
    // round 2 has started, so the marks of the round 1 vote are gone
    expect(t.seats().map((s) => s.getAttribute("aria-label"))).toEqual([
      "Phi, listening",
      "Llama, listening",
      "Qwen, speaking",
      "Gemma, listening",
      "Mistral, listening",
    ]);
    expect(t.seats().every((s) => s.tagName === "BUTTON" && s.classList.contains("group"))).toBe(true);
    expect(t.all("[data-part=seat-name]").map((el) => el.textContent)).toEqual([
      "Phi",
      "Llama",
      "Qwen",
      "Gemma",
      "Mistral",
    ]);
  });

  it("puts each seat where the layout says", () => {
    const t = table(sampleView("lease", "debating"));
    const layout = tableLayout(5, W, H);
    t.seats().forEach((seat, i) => {
      const rect = figureRect(layout, i);
      expect(styleBox(seat)).toEqual(rect);
    });
  });

  it("marks exactly one speaking seat while one speaks", () => {
    const t = table(sampleView("lease", "debating"));
    expect(t.all("[data-part=seat][data-speaking=true]")).toHaveLength(1);
    expect(t.all("[data-ring=speaking]")).toHaveLength(1);
    expect(t.all("[data-part=seat][data-speaking=true]")[0]?.getAttribute("data-seat-id")).toBe("s3");
  });

  it("marks every speaking seat when several speak", () => {
    const view = sampleView("lease", "debating");
    const t = table({ ...view, speaking: view.seats.map((s) => s.id) });
    expect(t.all("[data-part=seat][data-speaking=true]")).toHaveLength(5);
    expect(t.all("[data-ring=speaking]")).toHaveLength(5);
  });

  it("shows three bubbles while debating, the oldest one fading", () => {
    const view = sampleView("lease", "debating");
    const t = table(view);
    const bubbles = t.all("[data-part=bubble]");
    expect(bubbles).toHaveLength(3);
    // the speaker first, then the others left to right
    expect(bubbles.map((b) => b.getAttribute("data-fading"))).toEqual(["false", "true", "false"]);
    const fading = bubbles[1];
    expect(Number(fading?.style.opacity)).toBeGreaterThan(0);
    expect(Number(fading?.style.opacity)).toBeLessThan(1);
    // bubbles are not controls and are not read twice: the seat carries the words
    expect(bubbles.every((b) => b.getAttribute("aria-hidden") === "true")).toBe(true);
    const qwen = view.seats[2];
    expect(t.seats()[2]?.getAttribute("aria-description")).toBe(qwen?.bubble?.text);
  });

  it("draws both lines while one bubble line replaces another", () => {
    const view = sampleView("lease", "debating");
    const seats = view.seats.map((s, i) =>
      i === 2
        ? {
            ...s,
            bubble: {
              summaryId: "new",
              text: "The new line.",
              opacity: 0.4,
              prev: { summaryId: "old", text: "The old line.", opacity: 0.6 },
            },
          }
        : { ...s, bubble: null },
    );
    const t = table({ ...view, seats });
    const bubble = t.all("[data-part=bubble]");
    expect(bubble).toHaveLength(1);
    expect(bubble[0]?.textContent).toBe("The new line.The old line.");
    expect(Number(bubble[0]?.style.opacity)).toBe(1);
  });

  it("draws a live bubble's small word, and dims a note its seat is thinking past", () => {
    const view = sampleView("lease", "debating");
    const live = [
      { summaryId: "a", text: "An old note.", opacity: 1, dim: true, tag: { text: "thinking..." }, newer: 1 },
      { summaryId: "b", text: "A doubtful note.", opacity: 1, tag: { text: "truth 0.31", flag: true }, newer: 3 },
      { summaryId: "c", text: "A sound note.", opacity: 1, tag: { text: "truth 0.94" }, newer: 2 },
    ];
    const seats = view.seats.map((s, i) => ({ ...s, bubble: live[i] ?? null }));
    const t = table({ ...view, seats, speaking: [] });
    // the newest words first
    const bubbles = t.all("[data-part=bubble]");
    expect(bubbles.map((b) => b.querySelector("[data-part=bubble-text]")?.textContent)).toEqual([
      "A doubtful note.",
      "A sound note.",
      "An old note.",
    ]);
    expect(bubbles.map((b) => b.querySelector("[data-part=bubble-tag]")?.textContent)).toEqual([
      "truth 0.31",
      "truth 0.94",
      "thinking...",
    ]);
    expect(bubbles.map((b) => b.querySelector("[data-part=bubble-tag]")?.getAttribute("data-flag"))).toEqual([
      "true",
      null,
      null,
    ]);
    expect(bubbles.map((b) => b.getAttribute("data-dim"))).toEqual([null, null, "true"]);
    expect(Number(bubbles[2]?.querySelector<HTMLElement>("[data-part=bubble-text]")?.style.opacity)).toBeLessThan(1);
    // the samples' bubbles have no small word
    cleanup();
    expect(table(view).all("[data-part=bubble-tag]")).toHaveLength(0);
  });

  it("shows one vote mark per seat just after a vote", () => {
    const t = table(sampleView("lease", "vote"));
    expect(t.all("[data-part=vote-mark]")).toHaveLength(5);
    expect(t.all("[data-part=seat] [data-part=vote-mark]")).toHaveLength(5);
    const labels = t.seats().map((s) => s.getAttribute("aria-label") ?? "");
    expect(labels.filter((l) => l.endsWith(", agreed at the last vote"))).toHaveLength(3);
    expect(labels.filter((l) => l.endsWith(", disagreed at the last vote"))).toHaveLength(2);
    expect(labels[2]).toMatch(/^Qwen, \w+, agreed at the last vote$/);
  });

  it("hangs the mark on the head's outer side", () => {
    const t = table(sampleView("lease", "vote"));
    const offsets = t.seats().map((seat) => {
      const mark = seat.querySelector<HTMLElement>("[data-part=vote-mark]")?.parentElement;
      return Number.parseFloat(mark?.style.left ?? "0") + 13 - Number.parseFloat(seat.style.width) / 2;
    });
    // left of the middle: mark left of the head's centre; middle and right: right of it
    expect(offsets.map((o) => Math.sign(o))).toEqual([-1, -1, 1, 1, 1]);
  });

  it("seats seven", () => {
    const t = table(sampleView("lease-7", "vote"));
    expect(t.seats()).toHaveLength(7);
    expect(t.all("[data-part=vote-mark]")).toHaveLength(7);
    // seven seats: 64 px heads, each with its maker's logo, and the names on the bodies at 15 px
    expect(t.all("[data-part=seat-logo]")).toHaveLength(7);
    expect(t.all("[data-part=seat-name]").every((el) => el.getAttribute("font-size") === "15")).toBe(true);
  });

  it("seats three", () => {
    const t = table(sampleView("lease-3", "debating"));
    expect(t.seats()).toHaveLength(3);
  });

  it("is one Tab stop; Left and Right move between seats; Enter opens the seat", () => {
    const t = table(sampleView("lease", "debating"));
    const seats = t.seats();
    expect(seats.map((s) => s.tabIndex)).toEqual([0, -1, -1, -1, -1]);
    seats[0]?.focus();
    fireEvent.keyDown(seats[0] as HTMLElement, { key: "ArrowRight" });
    expect(document.activeElement).toBe(seats[1]);
    expect(t.seats().map((s) => s.tabIndex)).toEqual([-1, 0, -1, -1, -1]);
    fireEvent.keyDown(seats[1] as HTMLElement, { key: "End" });
    expect(document.activeElement).toBe(seats[4]);
    fireEvent.keyDown(seats[4] as HTMLElement, { key: "ArrowRight" });
    expect(document.activeElement).toBe(seats[4]); // no way past the last seat
    fireEvent.keyDown(seats[4] as HTMLElement, { key: "ArrowLeft" });
    expect(document.activeElement).toBe(seats[3]);
    // Enter and Space press a button: the browser turns them into a click
    fireEvent.click(seats[3] as HTMLElement);
    expect(t.onOpenSeat).toHaveBeenCalledWith("s4");
  });

  it.each([
    [1040, 558],
    [1040, 620],
    [900, 470],
    [976, 470],
  ])("keeps bubbles off each other and off every figure with several talking (%i x %i)", (width, height) => {
    const view = sampleView("lease-7-busy", "debating");
    const t = table(view, width, height);
    const bubbles = t.all("[data-part=bubble]").map(styleBox);
    expect(bubbles.length).toBeGreaterThanOrEqual(3);
    const layout = tableLayout(7, width, height);
    expect(bubbles.length).toBeLessThanOrEqual(layout.maxBubbles);
    const figures = view.seats.map((_, i) => figureRect(layout, i));
    bubbles.forEach((a, i) => {
      // the tail hangs 6 px under the box: it must stay clear too
      const withTail = { ...a, h: a.h + 6 };
      expect(a.x).toBeGreaterThanOrEqual(0);
      expect(a.x + a.w).toBeLessThanOrEqual(width);
      expect(a.y).toBeGreaterThanOrEqual(0);
      for (const b of bubbles.slice(i + 1)) expect(touch(withTail, b) || touch(a, { ...b, h: b.h + 6 })).toBe(false);
      for (const f of figures) expect(touch(withTail, f)).toBe(false);
    });
  });

  it("says what a seat that is loading or did not load is doing", () => {
    const spooling = table(sampleView("lease", "spooling"));
    expect(spooling.all("[data-part=seat][data-status=ready]")).toHaveLength(3);
    expect(spooling.all("[data-part=seat][data-status=loading]")[0]?.getAttribute("aria-label")).toMatch(/, loading$/);
    cleanup();
    const failed = table(sampleView("lease-failed", "failed"));
    expect(failed.all("[data-part=seat][data-status=failed]")[0]?.getAttribute("aria-label")).toBe("Phi, did not load");
  });

  it("writes the middle of the table", () => {
    const middle = (fixture: string, scene: string) => {
      cleanup();
      return table(sampleView(fixture, scene)).container.querySelector("[data-part=table-middle]");
    };
    const debating = middle("lease", "debating");
    expect(debating?.textContent).toBe("Round 23:10 left2 of 5 agree, needs 4");
    expect(debating?.querySelectorAll("[data-part=meter]")).toHaveLength(1);
    expect(middle("lease", "researching")?.textContent).toMatch(
      /^Reading your files\d:\d\d leftNo vote yet, needs 4 of 5$/,
    );
    expect(middle("lease", "spooling")?.textContent).toBe("Seating the council3 of 5 ready");
    expect(middle("lease", "paused")?.textContent).toMatch(/^Paused in round 2/);
    expect(middle("lease", "agreed")?.querySelector("[data-part=meter][data-reached=true]")).not.toBeNull();
  });

  it("shows the owner's waiting note at the flat edge, and not as the composer's note", () => {
    const t = table(sampleView("lease", "owner-note"));
    expect(t.all("[data-part=table-note]").map((el) => el.textContent)).toEqual(["Your note waits for round 3"]);
    expect(t.all("[data-part=note]")).toHaveLength(0);
  });

  it("draws the table with its curved and its flat edge", () => {
    const t = table(sampleView("lease", "debating"));
    const layout = tableLayout(5, W, H);
    const edge = t.container.querySelector("[data-table=edge]");
    expect(edge?.getAttribute("d")).toBe(
      `M${layout.cx - layout.tableR} ${layout.flatY}A${layout.tableR} ${layout.tableR} 0 0 1 ${layout.cx + layout.tableR} ${layout.flatY}Z`,
    );
    expect(edge?.getAttribute("class")).toContain("stroke-line");
    expect(t.container.querySelector("[data-table=cloth]")?.getAttribute("class")).toContain("fill-table");
  });
});
