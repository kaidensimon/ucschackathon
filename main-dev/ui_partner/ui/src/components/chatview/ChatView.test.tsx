import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { sampleView } from "../../gallery/entry";
import type { DebateView } from "../../lib/events";
import { ChatView } from "./ChatView";
import { bandsOf, layoutFor, researchWords, stripWords } from "./chatModel";

afterEach(cleanup);

function show(view: DebateView, width: number, filterSeatId: string | null = null) {
  const onFilter = vi.fn();
  const { container } = render(<ChatView view={view} width={width} filterSeatId={filterSeatId} onFilter={onFilter} />);
  const root = container.querySelector("[data-part=chat-view]") as HTMLElement;
  const all = (selector: string) => [...root.querySelectorAll<HTMLElement>(selector)];
  return { root, all, onFilter };
}

const debating = () => sampleView("lease", "debating");
const released = () => sampleView("lease", "released");

describe("ChatView layout", () => {
  it("five seats at 1040 px: one column per seat, in seat order", () => {
    const { root, all } = show(debating(), 1040);
    expect(root.getAttribute("data-layout")).toBe("columns");
    expect(all("[data-part=chat-column]").map((c) => c.getAttribute("data-seat"))).toEqual([
      "s1",
      "s2",
      "s3",
      "s4",
      "s5",
    ]);
  });

  it("five seats at 760 px: one thread", () => {
    const { root, all } = show(debating(), 760);
    expect(root.getAttribute("data-layout")).toBe("thread");
    expect(all("[data-part=chat-column]")).toHaveLength(0);
  });

  it("seven seats at 1040 px: one thread, because a column would get less than 200 px", () => {
    const { root } = show(sampleView("lease-7", "debating"), 1040);
    expect(root.getAttribute("data-layout")).toBe("thread");
  });

  it("columns start at exactly 200 px a seat", () => {
    expect(layoutFor(1000, 5)).toBe("columns");
    expect(layoutFor(999, 5)).toBe("thread");
    expect(layoutFor(1400, 7)).toBe("columns");
    expect(layoutFor(1040, 0)).toBe("thread");
  });

  it("columns show no filter; the thread does", () => {
    expect(show(debating(), 1040).all("select")).toHaveLength(0);
    expect(show(debating(), 760).all("select")).toHaveLength(1);
  });
});

describe("ChatView messages", () => {
  it("shows every message once the answer is released, in both layouts", () => {
    const view = released();
    const messages = view.turns.filter((t) => t.kind !== "research").length;
    const reading = view.turns.filter((t) => t.kind === "research").length;
    expect(messages).toBe(18);
    for (const width of [760, 1040]) {
      const { all } = show(view, width);
      expect(all("[data-part=message]")).toHaveLength(messages);
      expect(all("[data-part=research-line]")).toHaveLength(reading);
      cleanup();
    }
  });

  it("says who a message is for, by name", () => {
    const { all } = show(debating(), 760);
    const texts = all("[data-part=message]").map((m) => m.textContent ?? "");
    expect(texts.some((t) => t.startsWith("Llamato Qwen1:31"))).toBe(true);
    expect(texts.some((t) => t.startsWith("Qwento all0:32"))).toBe(true);
  });

  it("every message carries its maker's mark before the name; in columns the head carries it", () => {
    const thread = show(debating(), 760);
    const messages = thread.all("[data-part=message]");
    expect(messages.length).toBeGreaterThan(0);
    for (const m of messages) expect(m.querySelectorAll("[data-part=maker-mark]")).toHaveLength(1);
    const llama = messages.find((m) => m.textContent?.startsWith("Llamato Qwen1:31"));
    expect(llama?.querySelector("[data-part=maker-mark]")?.getAttribute("data-maker")).toBe("Meta");
    cleanup();
    const columns = show(debating(), 1040);
    expect(columns.all("[data-part=message] [data-part=maker-mark]")).toHaveLength(0);
    expect(
      columns.all("[data-part=chat-column]").map((c) => c.querySelectorAll("[data-part=maker-mark]").length),
    ).toEqual([1, 1, 1, 1, 1]);
  });

  it("an open turn shows its words so far, then Writing, and no chips yet", () => {
    const view = debating();
    const open = view.turns.filter((t) => !t.done);
    expect(open).toHaveLength(1);
    const { all } = show(view, 760);
    const writing = all("[data-part=message][data-state=writing]");
    expect(writing).toHaveLength(1);
    expect(writing[0]?.getAttribute("data-seat")).toBe(open[0]?.seatId);
    expect(writing[0]?.textContent).toContain(open[0]?.text);
    expect(writing[0]?.textContent?.endsWith("Writing")).toBe(true);
    expect(writing[0]?.querySelector("[data-part=citation-chip]")).toBeNull();
  });

  it("a finished message carries its citations as chips, named from the files", () => {
    const { all } = show(debating(), 760);
    const first = all("[data-part=message]")[0];
    expect(first?.querySelector("[data-part=citation-chip]")?.textContent).toBe("Renewal letter 2026.pdf, p.\u00a01");
  });

  it("a reading turn is one short line", () => {
    const view = debating();
    const { all } = show(view, 760);
    expect(all("[data-part=research-line]").map((l) => l.textContent)).toEqual([
      "Phi read Lease 2025.pdf, page 9",
      "Llama read Lease 2025.pdf, pages 2 and 9",
      "Qwen read Renewal letter 2026.pdf, page 1 and Lease 2025.pdf, page 9",
      "Gemma read Renewal letter 2026.pdf, page 1 and House rules.docx, page 4",
      "Mistral read Lease 2025.pdf, page 9 and Renewal letter 2026.pdf, page 1",
    ]);
    const reading = sampleView("lease", "researching");
    const open = reading.turns.find((t) => !t.done);
    expect(open && researchWords(open, "Qwen", reading.files)).toBe("Qwen is reading your files");
  });

  it("a closing dissent says it disagreed", () => {
    const { all } = show(released(), 760);
    const dissent = all("[data-part=message][data-kind=dissent]");
    expect(dissent).toHaveLength(1);
    expect(dissent[0]?.textContent?.startsWith("Phidisagreed3:40")).toBe(true);
  });
});

describe("ChatView dividers", () => {
  it("opens each round with its heading and closes the latest vote with its result", () => {
    const { all } = show(debating(), 760);
    expect(all("[data-part=vote-divider]").map((d) => d.textContent)).toEqual([
      "Round 1",
      "Round 1 vote: 2 of 5 agree, needs 4",
      "Round 2",
    ]);
  });

  it("columns carry the same dividers", () => {
    const { all } = show(debating(), 1040);
    expect(
      all("[data-part=vote-divider]")
        .map((d) => d.textContent)
        .sort(),
    ).toEqual(["Round 1", "Round 1 vote: 2 of 5 agree, needs 4", "Round 2"]);
  });

  it("puts the last vote before the answer, and marks agreement without colour", () => {
    const bands = bandsOf(released());
    expect(bands.map((b) => b.key)).toEqual(["reading", "round-1", "round-2", "round-3", "answer"]);
    expect(bands[3]?.vote).toEqual({ text: "Round 3 vote: 4 of 5 agree, needs 4", reached: true });
    const { all } = show(released(), 760);
    expect(all("[data-part=vote-divider][data-reached=true] svg")).toHaveLength(1);
  });

  it("nothing to divide before round 1", () => {
    expect(show(sampleView("lease", "researching"), 760).all("[data-part=vote-divider]")).toHaveLength(0);
  });
});

describe("ChatView owner note", () => {
  it("a delivered note is a message from You, at the start of its round", () => {
    const { all } = show(sampleView("lease", "note-delivered"), 760);
    const notes = all("[data-part=note][data-state=delivered]");
    expect(notes).toHaveLength(1);
    expect(notes[0]?.textContent).toBe("Youto allI want to be out by the end of February.");
    // straight after the "Round 3" heading, before that round's first message
    expect(notes[0]?.parentElement?.previousElementSibling?.textContent).toBe("Round 3");
    expect(notes[0]?.nextElementSibling?.getAttribute("data-part")).toBe("message");
  });

  it("a note still waiting is not drawn here", () => {
    expect(show(sampleView("lease", "owner-note"), 760).all("[data-part=note]")).toHaveLength(0);
  });

  it("in columns the note runs across all of them", () => {
    const { all } = show(sampleView("lease", "note-delivered"), 1040);
    const notes = all("[data-part=note][data-state=delivered]");
    expect(notes).toHaveLength(1);
    expect(notes[0]?.closest("[data-part=chat-column]")).toBeNull();
  });
});

describe("ChatView filter", () => {
  it("shows only that seat's messages, and keeps the dividers", () => {
    const view = released();
    const mine = view.turns.filter((t) => t.seatId === "s3");
    const { all } = show(view, 760, "s3");
    const seats = all("[data-part=message], [data-part=research-line]").map((m) => m.getAttribute("data-seat"));
    expect(seats).toHaveLength(mine.length);
    expect(new Set(seats)).toEqual(new Set(["s3"]));
    expect(all("[data-part=vote-divider]").length).toBeGreaterThanOrEqual(3);
    expect((all("select")[0] as HTMLSelectElement | undefined)?.value).toBe("s3");
  });

  it("hides the owner's note while one model is picked", () => {
    expect(show(sampleView("lease", "note-delivered"), 760, "s1").all("[data-part=note]")).toHaveLength(0);
  });

  it("choosing a model, or all of them, calls onFilter", () => {
    const { all, onFilter } = show(debating(), 760);
    const select = all("select")[0] as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual([
      "All models",
      "Phi",
      "Llama",
      "Qwen",
      "Gemma",
      "Mistral",
    ]);
    fireEvent.change(select, { target: { value: "s4" } });
    expect(onFilter).toHaveBeenLastCalledWith("s4");
    fireEvent.change(select, { target: { value: "" } });
    expect(onFilter).toHaveBeenLastCalledWith(null);
  });

  it("an unknown seat id shows everything", () => {
    const { all } = show(debating(), 760, "nobody");
    expect(new Set(all("[data-part=message]").map((m) => m.getAttribute("data-seat"))).size).toBeGreaterThan(1);
  });
});

describe("ChatView header strip", () => {
  it("round, time left, agreement and what is needed", () => {
    expect(stripWords(debating()).parts).toEqual(["Round 2", "3:10 left", "2 of 5 agree, needs 4"]);
  });

  it("before the first vote it says what is needed", () => {
    const view = sampleView("lease", "debating");
    expect(stripWords({ ...view, tally: null }).parts[2]).toBe("No vote yet, needs 4 of 5");
  });

  it("the other moments", () => {
    expect(stripWords(sampleView("lease", "spooling")).parts).toEqual(["Seating the council, 3 of 5 ready"]);
    expect(stripWords(sampleView("lease", "researching")).parts).toEqual(["Reading your files", "4:45 left"]);
    expect(stripWords(sampleView("lease", "paused")).parts[0]).toBe("Paused in round 2");
    expect(stripWords(sampleView("lease", "agreed"))).toEqual({
      mark: "agreed",
      parts: ["Agreed 4 of 5, writing the answer"],
    });
    expect(stripWords(released())).toEqual({ mark: "agreed", parts: ["Agreed 4 of 5", "3 rounds, 3:40"] });
    expect(stripWords(sampleView("lease-timeup", "released")).parts).toEqual([
      "No consensus, 2 of 5",
      "Time ran out at 2:00",
    ]);
  });
});

describe("ChatView is black, white and grey", () => {
  // every colour class in the app is `<property>-<token>`; inside Chat View the token must be cv-*
  const COLOUR = /^(?:[a-z-]+:)*(?:text|bg|border|fill|stroke|outline|decoration|ring)-(.+)$/;
  const APP_TOKENS =
    /^(?:page|surface|hover|hairline|line|ink|muted|accent|accent-hover|on-accent|table|agreed|error|on-seat|seat-\d)$/;

  it.each([
    ["columns, debating", "lease", "debating", 1040],
    ["columns, just after a vote", "lease", "vote", 1040],
    ["thread, released", "lease", "released", 760],
    ["thread, note delivered", "lease", "note-delivered", 760],
    ["columns, a seat that did not load", "lease-failed", "failed", 1040],
  ])("%s: no class names an app colour", (_name, fixture, scene, width) => {
    const { root } = show(sampleView(fixture, scene), width);
    const bad: string[] = [];
    for (const el of [root, ...root.querySelectorAll("*")]) {
      for (const cls of (el.getAttribute("class") ?? "").split(/\s+/)) {
        const token = COLOUR.exec(cls)?.[1];
        if (token && APP_TOKENS.test(token)) bad.push(cls);
      }
    }
    expect(bad).toEqual([]);
  });

  it("column heads use the ink figure and the ink vote mark", () => {
    const { all } = show(sampleView("lease", "vote"), 1040);
    expect(all("[data-part=chat-column] svg[data-variant=ink]")).toHaveLength(5);
    expect(all("[data-part=chat-column] [data-part=vote-mark]")).toHaveLength(5);
    expect(all("[data-part=vote-mark] .fill-accent, [data-part=vote-mark] .stroke-accent")).toHaveLength(0);
  });
});

describe("ChatView with nothing to show", () => {
  it("says so under the column heads while the council is being seated", () => {
    const { root, all } = show(sampleView("lease", "spooling"), 1040);
    expect(all("[data-part=chat-column]")).toHaveLength(5);
    expect(all("[data-part=message]")).toHaveLength(0);
    const line = [...root.querySelectorAll("p")].find((p) => p.textContent === "No messages yet");
    const lastColumn = all("[data-part=chat-column]")[4] as HTMLElement;
    expect(line).toBeDefined();
    expect(lastColumn.compareDocumentPosition(line as Node) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("names the model when the filter leaves nothing", () => {
    const { root } = show(sampleView("lease", "researching"), 760, "s5");
    expect(root.textContent).toContain("No messages from Mistral yet");
  });
});

describe("ChatView scrolling", () => {
  it("the messages are one labelled area the keyboard can reach and scroll", () => {
    const { root } = show(debating(), 760);
    const area = root.querySelector("[aria-label='Debate messages']") as HTMLElement;
    expect(area.tabIndex).toBe(0);
    expect(area.contains(root.querySelector("[data-part=message]"))).toBe(true);
  });

  it("offers Jump to newest once the reader has scrolled up, and goes back down", () => {
    const { root } = show(released(), 760);
    const area = root.querySelector("[aria-label='Debate messages']") as HTMLElement;
    expect(root.querySelector("button")).toBeNull();
    // jsdom lays nothing out: give the area a size and scroll it by hand
    Object.defineProperty(area, "scrollHeight", { configurable: true, value: 2000 });
    Object.defineProperty(area, "clientHeight", { configurable: true, value: 500 });
    area.scrollTop = 300;
    fireEvent.scroll(area);
    const jump = root.querySelector("button") as HTMLButtonElement;
    expect(jump.textContent).toBe("Jump to newest");
    fireEvent.click(jump);
    expect(area.scrollTop).toBe(2000);
    expect(root.querySelector("button")).toBeNull();
  });
});
