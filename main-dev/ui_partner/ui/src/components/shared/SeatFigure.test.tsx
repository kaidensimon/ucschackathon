import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { sampleSeats } from "../../gallery/entry";
import type { SeatView } from "../../lib/events";
import { figureRect, tableLayout } from "../../lib/layout/tableLayout";
import { figureBox, longNameScale, SeatFigure } from "./SeatFigure";

afterEach(cleanup);

const seats = sampleSeats(7);
const seat = (i: number, change: Partial<SeatView> = {}): SeatView => ({ ...(seats[i] as SeatView), ...change });
/** a seat whose model this build knows no maker for */
const stranger = (change: Partial<SeatView> = {}): SeatView =>
  seat(3, { shortName: "Orca", modelName: "Orca example model", ...change });

describe("SeatFigure", () => {
  it("puts the maker's logo in the head, letters the name across the body and says it aloud", () => {
    const { getByRole, container } = render(<SeatFigure seat={seat(3)} index={3} headD={72} />);
    expect(getByRole("img").getAttribute("aria-label")).toBe("Qwen");
    const logo = container.querySelector("[data-part=seat-logo]");
    expect(logo?.getAttribute("data-maker")).toBe("Alibaba");
    expect(logo?.querySelectorAll("path").length).toBeGreaterThan(0);
    const name = container.querySelector("[data-part=seat-name]");
    expect(name?.textContent).toBe("Qwen");
    expect(name?.getAttribute("font-size")).toBe("17");
    // the name is on the body, below the head
    expect(Number(name?.getAttribute("y"))).toBeGreaterThan(72);
  });

  it("each sample seat has its own maker's logo", () => {
    const makers = seats.map((s, i) => {
      const { container } = render(<SeatFigure seat={s} index={i} headD={64} />);
      return container.querySelector("[data-part=seat-logo]")?.getAttribute("data-maker");
    });
    expect(makers).toEqual(["Microsoft", "Meta", "IBM", "Alibaba", "Google", "Nous Research", "Mistral AI"]);
  });

  it("letters the model's own name, not a short name cut to 7 characters", () => {
    const deepseek = seat(1, { shortName: "DeepSee", modelName: "DeepSeek R1 14B" });
    const { getByRole, container } = render(<SeatFigure seat={deepseek} index={1} headD={72} />);
    expect(container.querySelector("[data-part=seat-logo]")?.getAttribute("data-maker")).toBe("DeepSeek");
    const name = container.querySelector("[data-part=seat-name]");
    expect(name?.textContent).toBe("DeepSeek");
    expect(getByRole("img").getAttribute("aria-label")).toBe("DeepSeek");
    // 8 letters: 7/8 of the 17 px a shorter name gets under a 72 head
    expect(name?.getAttribute("font-size")).toBe("14.9");
  });

  it("names the open-weights GPT model in capitals, under OpenAI's logo", () => {
    const gpt = seat(0, { shortName: "gpt", modelName: "gpt-oss 20B" });
    const { container } = render(<SeatFigure seat={gpt} index={0} headD={64} />);
    expect(container.querySelector("[data-part=seat-logo]")?.getAttribute("data-maker")).toBe("OpenAI");
    expect(container.querySelector("[data-part=seat-name]")?.textContent).toBe("GPT-OSS");
  });

  it("a long name is never lettered under 80% of the usual size", () => {
    expect(longNameScale("Qwen3.5")).toBe(1);
    expect(longNameScale("DeepSeek")).toBe(0.875);
    expect(longNameScale("Llama 3.1")).toBe(0.8);
    expect(longNameScale("Internationale")).toBe(0.8);
  });

  it("a model with no known maker keeps the name in the head", () => {
    const { container } = render(<SeatFigure seat={stranger()} index={3} headD={72} />);
    expect(container.querySelector("[data-part=seat-logo]")).toBeNull();
    const name = container.querySelector("[data-part=seat-name]");
    expect(name?.textContent).toBe("Orca");
    expect(name?.getAttribute("font-size")).toBe("19");
    expect(Number(name?.getAttribute("y"))).toBeLessThan(72);
  });

  it("takes its colour from its place at the table", () => {
    const { container } = render(<SeatFigure seat={seat(3)} index={3} headD={72} />);
    expect(container.querySelectorAll(".fill-seat-4")).toHaveLength(2); // head and body
  });

  it("speaking: a ring, and the word", () => {
    const { getByRole, container } = render(<SeatFigure seat={seat(2)} index={2} headD={72} speaking />);
    expect(container.querySelector("[data-ring=speaking]")).not.toBeNull();
    expect(getByRole("img").getAttribute("aria-label")).toBe("Granite, speaking");
  });

  it("not ready: dashed outline, no fill, and the word", () => {
    const { getByRole, container } = render(<SeatFigure seat={seat(0, { status: "loading" })} index={0} headD={72} />);
    expect(container.querySelector(".fill-seat-1")).toBeNull();
    expect(container.querySelector("[stroke-dasharray]")).not.toBeNull();
    expect(getByRole("img").getAttribute("aria-label")).toBe("Phi, loading");
    // the logo stays, greyed; the name stays on the body
    expect(container.querySelector("[data-part=seat-logo]")?.getAttribute("class")).toContain("fill-muted");
    expect(container.textContent).toBe("Phi");
  });

  it("not ready, no known maker: the word under the head", () => {
    const { container } = render(<SeatFigure seat={stranger({ status: "loading" })} index={0} headD={72} />);
    expect(container.textContent).toContain("Loading");
    const failed = render(<SeatFigure seat={stranger({ status: "failed" })} index={0} headD={72} />);
    expect(failed.container.textContent).toContain("Did not load");
  });

  it("failed: an error mark and the words", () => {
    const { getByRole, container } = render(<SeatFigure seat={seat(0, { status: "failed" })} index={0} headD={72} />);
    expect(container.querySelector("[data-mark=error]")).not.toBeNull();
    expect(getByRole("img").getAttribute("aria-label")).toBe("Phi, did not load");
  });

  it("small and tiny carry no name and stay out of the way of screen readers", () => {
    const { container } = render(<SeatFigure seat={seat(1)} index={1} headD={72} size="tiny" />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
    expect(svg?.getAttribute("width")).toBe("19.6");
    expect(container.querySelector("[data-part=seat-name]")).toBeNull();
  });

  it("ink: no seat colour anywhere", () => {
    const { container } = render(<SeatFigure seat={seat(5)} index={5} headD={64} variant="ink" speaking />);
    const classes = [...container.querySelectorAll("[class]")].map((el) => el.getAttribute("class")).join(" ");
    expect(classes).not.toMatch(/seat-\d|accent|fill-page/);
  });

  it("has the same box as the table layout gives a figure", () => {
    const layout = tableLayout(5, 1040, 558);
    const rect = figureRect(layout, 0);
    const box = figureBox(layout.headD);
    expect(box.width).toBeCloseTo(rect.w);
    expect(box.height).toBeCloseTo(rect.h);
  });
});
