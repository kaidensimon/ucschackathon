import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MakerMark } from "./MakerMark";

afterEach(cleanup);

const mark = (c: HTMLElement) => c.querySelector("[data-part=maker-mark]") as HTMLElement;

describe("MakerMark", () => {
  it("draws the maker's mark at the asked size, hidden from a screen reader, with the company as its tooltip", () => {
    const { container } = render(<MakerMark seat={{ shortName: "Phi", modelName: "Phi-4 14B" }} size={18} />);
    const el = mark(container);
    expect(el.getAttribute("aria-hidden")).toBe("true");
    expect(el.getAttribute("title")).toBe("Microsoft");
    expect(el.getAttribute("data-maker")).toBe("Microsoft");
    const svg = el.querySelector("svg");
    expect(svg?.getAttribute("width")).toBe("18");
    expect(svg?.getAttribute("height")).toBe("18");
    expect(svg?.getAttribute("viewBox")).toBe("0 0 24 24");
    expect(el.querySelectorAll("path")).toHaveLength(4);
    expect(el.querySelector("g")?.getAttribute("fill-rule")).toBe("evenodd");
    // it adds no words beside the name
    expect(el.textContent).toBe("");
  });

  it("is 16 px unless told otherwise", () => {
    const { container } = render(<MakerMark seat={{ shortName: "Gemma", modelName: "Gemma 4 12B" }} />);
    expect(mark(container).querySelector("svg")?.getAttribute("width")).toBe("16");
    expect(mark(container).getAttribute("title")).toBe("Google");
  });

  it("a picture mark stays dark on a pale plate", () => {
    const { container } = render(<MakerMark seat={{ shortName: "Hermes", modelName: "Hermes example model" }} />);
    const el = mark(container);
    expect(el.querySelector("circle")?.getAttribute("class")).toBe("fill-plate");
    expect(el.querySelector("g")?.getAttribute("class")).toBe("fill-on-plate");
  });

  it("in the Chat View greys a picture mark has no plate: one colour only", () => {
    const { container } = render(
      <MakerMark seat={{ shortName: "Hermes", modelName: "Hermes example model" }} variant="ink" />,
    );
    const el = mark(container);
    expect(el.querySelector("circle")).toBeNull();
    expect(el.querySelector("g")?.getAttribute("class")).toBe("fill-current");
  });

  it("no maker known: a ring with the first letter of the name, and no tooltip", () => {
    const { container } = render(<MakerMark seat={{ shortName: "orca", modelName: "Orca example model" }} />);
    const el = mark(container);
    expect(el.getAttribute("title")).toBeNull();
    expect(el.getAttribute("data-maker")).toBeNull();
    expect(el.querySelectorAll("path")).toHaveLength(0);
    expect(el.querySelectorAll("circle")).toHaveLength(1);
    expect(el.querySelector("text")?.textContent).toBe("O");
  });
});
