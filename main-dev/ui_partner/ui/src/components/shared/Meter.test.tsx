import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Meter } from "./Meter";

afterEach(cleanup);

const meter = (c: HTMLElement) => c.querySelector("[data-part=meter]") as HTMLElement;

describe("Meter", () => {
  it("draws one pip per seat, filled for each seat that agrees", () => {
    const { container } = render(<Meter agree={2} seats={5} needed={4} reached={false} />);
    expect(container.querySelectorAll("[data-pip=on]")).toHaveLength(2);
    expect(container.querySelectorAll("[data-pip=off]")).toHaveLength(3);
  });

  it("puts the mark straight after the pip that reaches the number needed", () => {
    const { container } = render(<Meter agree={4} seats={7} needed={6} reached={false} />);
    const order = [...container.querySelectorAll("[data-pip]")].map((el) => el.getAttribute("data-pip"));
    expect(order).toEqual(["on", "on", "on", "on", "off", "off", "needed", "off"]);
  });

  it("says the count and what is needed", () => {
    const { container, getByRole } = render(<Meter agree={2} seats={5} needed={4} reached={false} />);
    expect(getByRole("img").getAttribute("aria-label")).toBe("2 of 5 agree, needs 4");
    expect(meter(container).getAttribute("data-reached")).toBe("false");
    expect(meter(container).textContent).toBe("");
  });

  it("reached: marked, with the word as well as the colour", () => {
    const { container, getByRole } = render(<Meter agree={4} seats={5} needed={4} reached={true} />);
    expect(meter(container).getAttribute("data-reached")).toBe("true");
    expect(meter(container).textContent).toBe("Agreed");
    expect(getByRole("img").getAttribute("aria-label")).toBe("Agreed 4 of 5");
  });

  it("three seats need all three: the mark stands after the last pip", () => {
    const { container } = render(<Meter agree={1} seats={3} needed={3} reached={false} size="pill" />);
    const order = [...container.querySelectorAll("[data-pip]")].map((el) => el.getAttribute("data-pip"));
    expect(order).toEqual(["on", "off", "off", "needed"]);
  });
});
