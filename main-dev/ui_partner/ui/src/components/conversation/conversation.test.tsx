import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fixtures } from "../../fixtures/lease";
import { sampleView } from "../../gallery/entry";
import type { DebateView } from "../../lib/events";
import { Answer } from "./Answer";
import { citedPlaces } from "./Cited";
import { FoldedCard } from "./FoldedCard";
import { Question } from "./Question";
import { SeatPicker } from "./SeatPicker";

afterEach(cleanup);

const agreed = sampleView("lease", "released");
const timeUp = sampleView("lease-timeup", "released");
const seats = fixtures.lease?.seats ?? [];

const part = (c: HTMLElement, name: string) => c.querySelector(`[data-part=${name}]`) as HTMLElement;
const parts = (c: HTMLElement, name: string) => [...c.querySelectorAll<HTMLElement>(`[data-part=${name}]`)];
const words = (el: Element | null) => el?.textContent?.replace(/\s+/g, " ").trim();

describe("Question", () => {
  it("shows the question, its three files and the time limit", () => {
    const { container } = render(<Question question={agreed.question} files={agreed.files} limitMs={agreed.limitMs} />);
    const q = part(container, "question");
    expect(within(q).getByRole("heading").textContent).toBe(
      "Can I end my apartment lease early, and what would it cost me?",
    );
    expect(parts(q, "file-chip").map(words)).toEqual([
      "Lease 2025.pdf, 14 pages",
      "Renewal letter 2026.pdf, 2 pages",
      "House rules.docx, 6 pages",
    ]);
    expect(q.textContent).toContain("Time limit 5:00");
  });

  it("writes one page as one page, and no count when a file has none", () => {
    const { container } = render(
      <Question
        question="Q"
        files={[
          { id: "a", name: "Note.pdf", pages: 1, from: "attachment" },
          { id: "b", name: "Sheet.csv", from: "library" },
        ]}
        limitMs={120000}
      />,
    );
    expect(parts(container, "file-chip").map(words)).toEqual(["Note.pdf, 1 page", "Sheet.csv"]);
    expect(container.textContent).toContain("Time limit 2:00");
  });
});

describe("FoldedCard", () => {
  it("agreed: the count, the rounds and the time, and every seat's mark", () => {
    const { container } = render(<FoldedCard view={agreed} open={false} onToggle={() => {}} />);
    const card = part(container, "folded-card");
    expect(words(within(card).getByRole("heading"))).toBe("Agreed 4 of 5");
    expect(card.textContent).toContain("3 rounds, 3:40");
    expect(card.textContent).not.toContain("Time ran out");
    const marks = parts(card, "vote-mark");
    expect(marks).toHaveLength(5);
    expect(marks.map((m) => m.getAttribute("data-mark"))).toEqual(["differs", "agrees", "agrees", "agrees", "agrees"]);
    expect(within(card).getAllByRole("listitem").map(words)).toEqual(["Phi", "Llama", "Qwen", "Gemma", "Mistral"]);
  });

  it("agreed: the agreed colour comes with the check and the word", () => {
    const { container } = render(<FoldedCard view={agreed} open={false} onToggle={() => {}} />);
    const green = [...container.querySelectorAll(".text-agreed")];
    expect(green.map((el) => el.tagName.toLowerCase())).toEqual(["svg", "span"]);
    expect(green[1]?.textContent).toBe("Agreed");
  });

  it("no consensus: who backed the answer, when time ran out, and the marks of the last vote", () => {
    const { container } = render(<FoldedCard view={timeUp} open={false} onToggle={() => {}} />);
    const card = part(container, "folded-card");
    expect(words(within(card).getByRole("heading"))).toBe("No consensus, 2 of 5 backed this answer");
    expect(card.textContent).toContain("Time ran out at 2:00");
    expect(card.textContent).toContain("2 rounds");
    expect(container.querySelector(".text-agreed")).toBeNull();
    const marks = parts(card, "vote-mark").map((m) => m.getAttribute("data-mark"));
    expect(marks).toHaveLength(5);
    expect(marks.filter((m) => m === "agrees")).toHaveLength(2);
  });

  it("stopped: says so, with the count", () => {
    const answer = agreed.answer;
    if (!answer) throw new Error("the sample has no answer");
    const stopped: DebateView = { ...agreed, answer: { ...answer, outcome: "stopped", agree: 3, rounds: 1 } };
    const { container } = render(<FoldedCard view={stopped} open={false} onToggle={() => {}} />);
    expect(words(within(part(container, "folded-card")).getByRole("heading"))).toBe(
      "Stopped, 3 of 5 backed this answer",
    );
    expect(container.textContent).toContain("1 round, 3:40");
  });

  it("the button opens and hides the debate", () => {
    const onToggle = vi.fn();
    const { rerender } = render(<FoldedCard view={agreed} open={false} onToggle={onToggle} />);
    const closed = screen.getByRole("button", { name: "See the debate" });
    expect(closed.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(closed);
    expect(onToggle).toHaveBeenCalledTimes(1);
    rerender(<FoldedCard view={agreed} open={true} onToggle={onToggle} />);
    expect(screen.getByRole("button", { name: "Hide the debate" }).getAttribute("aria-expanded")).toBe("true");
  });

  it("draws nothing before there is an answer", () => {
    const { container } = render(<FoldedCard view={sampleView("lease", "agreed")} open={false} onToggle={() => {}} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("Answer", () => {
  it("agreed: the text, three files cited, one seat that disagreed", () => {
    const { container } = render(<Answer view={agreed} />);
    const answer = part(container, "answer");
    expect(answer.getAttribute("data-outcome")).toBe("agreed");
    const paragraphs = [...part(answer, "answer-text").querySelectorAll("p")].map(words);
    expect(paragraphs).toEqual([
      "Yes. You can end the lease early by giving 60 days' written notice and paying one month's rent at the new rate, $2,520.",
      "To be out by the end of February, send the notice by 30 December 2026. An email counts as written notice.",
    ]);
    const cited = within(answer).getByRole("list", { name: "Files cited" });
    expect(parts(cited, "citation-chip").map(words)).toEqual([
      "Renewal letter 2026.pdf, page 1",
      "Lease 2025.pdf, page 9",
      "House rules.docx, page 4",
    ]);
    const dissents = parts(answer, "dissent");
    expect(dissents).toHaveLength(1);
    expect(words(dissents[0]?.querySelector("p") ?? null)).toBe(
      "Phi disagreed: The renewal letter has one signature (page 2), so the old terms may still apply.",
    );
    expect(parts(dissents[0] as HTMLElement, "citation-chip").map(words)).toEqual(["Renewal letter 2026.pdf, page 2"]);
  });

  it("no consensus: marked so, with three seats that disagreed, in seat order of the release", () => {
    const { container } = render(<Answer view={timeUp} />);
    const answer = part(container, "answer");
    expect(answer.getAttribute("data-outcome")).toBe("no-consensus");
    const lines = parts(answer, "dissent").map((d) => words(d.querySelector("p")));
    expect(lines).toHaveLength(3);
    expect(lines.map((l) => l?.split(":")[0])).toEqual(["Llama disagreed", "Mistral disagreed", "Phi disagreed"]);
  });

  it("draws nothing while the answer is still being written", () => {
    const writing = sampleView("lease", "agreed");
    expect(writing.phase).toBe("writing");
    const { container } = render(<Answer view={writing} />);
    expect(container.innerHTML).toBe("");
  });

  it("draws Markdown: a table, a list, and a code block in the mono face with a Copy button", () => {
    const text =
      "## Costs\n\n| Step | Cost |\n| --- | --- |\n| Notice | $0 |\n\n- one\n- two\n\n```text\nline one\n```\n";
    const view: DebateView = {
      ...agreed,
      turns: agreed.turns.map((t) => (t.turnId === agreed.answer?.turnId ? { ...t, text } : t)),
    };
    const { container } = render(<Answer view={view} />);
    expect(within(container).getByRole("heading", { name: "Costs" })).not.toBeNull();
    expect(within(container).getByRole("table").querySelectorAll("td")).toHaveLength(2);
    expect(within(part(container, "answer-text")).getAllByRole("listitem")).toHaveLength(2);
    const pre = container.querySelector("pre");
    expect(pre?.className).toContain("font-mono");
    expect(pre?.textContent).toContain("line one");
    fireEvent.click(within(container).getByRole("button", { name: "Copy" }));
    expect(within(container).getByText("Not in this mock yet")).not.toBeNull();
  });

  it("a link in an answer is words only: nothing leaves the machine", () => {
    const view: DebateView = {
      ...agreed,
      turns: agreed.turns.map((t) =>
        t.turnId === agreed.answer?.turnId ? { ...t, text: "See [the rules](https://example.com/rules)." } : t,
      ),
    };
    const { container } = render(<Answer view={view} />);
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toContain("See the rules.");
  });
});

describe("citedPlaces", () => {
  it("lists each file and page once, and skips files the owner did not attach", () => {
    const places = citedPlaces(
      [
        { kind: "file", fileId: "f1", page: 9 },
        { kind: "file", fileId: "f1", page: 9, quote: "again" },
        { kind: "file", fileId: "f1" },
        { kind: "file", fileId: "nope", page: 1 },
        { kind: "council", entryId: "L7" },
      ],
      agreed.files,
    );
    expect(places.map((p) => [p.label, p.detail])).toEqual([
      ["Lease 2025.pdf", "page 9"],
      ["Lease 2025.pdf", undefined],
    ]);
  });
});

describe("SeatPicker", () => {
  const picker = () => document.querySelector("[data-part=seat-picker]") as HTMLElement;

  it("lists the five seats in order, with the model behind each", () => {
    render(<SeatPicker seats={seats} limitMs={300000} open onOpenChange={() => {}} readOnly={false} />);
    expect(screen.getByRole("dialog", { name: "Seat the council" })).toBe(picker());
    const rows = within(within(picker()).getByRole("list", { name: "Seats" })).getAllByRole("listitem");
    expect(rows.map(words)).toEqual([
      "PhiPhi example modelSeat 1",
      "LlamaLlama example modelSeat 2",
      "QwenQwen example modelSeat 3",
      "GemmaGemma example modelSeat 4",
      "MistralMistral example modelSeat 5",
    ]);
    const add = within(picker()).getByRole("button", { name: "Add a seat" }) as HTMLButtonElement;
    expect(add.disabled).toBe(true);
    expect(picker().textContent).toContain("Choosing models arrives in Phase 3");
    expect(picker().textContent).not.toContain("The council is in session");
  });

  it("the time limit shows the debate's limit and can be changed", () => {
    render(<SeatPicker seats={seats} limitMs={300000} open onOpenChange={() => {}} readOnly={false} />);
    const group = within(picker()).getByRole("radiogroup", { name: "Time limit" });
    const radios = within(group).getAllByRole("radio");
    expect(radios.map((r) => r.textContent)).toEqual(["2 min", "5 min", "10 min"]);
    expect(radios.map((r) => r.getAttribute("aria-checked"))).toEqual(["false", "true", "false"]);
    fireEvent.click(radios[2] as HTMLElement);
    expect(radios.map((r) => r.getAttribute("aria-checked"))).toEqual(["false", "false", "true"]);
    expect(within(picker()).getByText("Not in this mock yet")).not.toBeNull();
  });

  it("reflects a two-minute debate", () => {
    render(<SeatPicker seats={seats} limitMs={timeUp.limitMs} open onOpenChange={() => {}} readOnly={false} />);
    expect(within(picker()).getByRole("radio", { name: "2 min" }).getAttribute("aria-checked")).toBe("true");
  });

  it("read only while the council is in session", () => {
    render(<SeatPicker seats={seats} limitMs={300000} open onOpenChange={() => {}} readOnly />);
    expect(picker().textContent).toContain("The council is in session");
    const radios = within(picker()).getAllByRole("radio") as HTMLButtonElement[];
    expect(radios.every((r) => r.disabled)).toBe(true);
    fireEvent.click(radios[0] as HTMLElement);
    expect(radios.map((r) => r.getAttribute("aria-checked"))).toEqual(["false", "true", "false"]);
  });

  it("Close and Esc ask to close; closed, it draws nothing", () => {
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <SeatPicker seats={seats} limitMs={300000} open onOpenChange={onOpenChange} readOnly={false} />,
    );
    fireEvent.click(within(picker()).getByRole("button", { name: "Close" }));
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
    fireEvent.keyDown(picker(), { key: "Escape" });
    expect(onOpenChange).toHaveBeenCalledTimes(2);
    rerender(<SeatPicker seats={seats} limitMs={300000} open={false} onOpenChange={onOpenChange} readOnly={false} />);
    expect(picker()).toBeNull();
  });
});
