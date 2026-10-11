import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { VoteMark } from "./VoteMark";

afterEach(cleanup);

describe("VoteMark", () => {
  it("agrees: a filled disc with a check, named in words", () => {
    const { getByRole } = render(<VoteMark mark="agrees" size={26} />);
    const mark = getByRole("img");
    expect(mark.getAttribute("data-part")).toBe("vote-mark");
    expect(mark.getAttribute("aria-label")).toBe("agrees");
    expect(mark.querySelector(".fill-accent")).not.toBeNull();
  });

  it("disagrees: an outlined disc with a cross, and never the error colour", () => {
    const { getByRole } = render(<VoteMark mark="differs" size={26} />);
    const mark = getByRole("img");
    expect(mark.getAttribute("aria-label")).toBe("disagrees");
    expect(mark.querySelector(".stroke-accent")).not.toBeNull();
    expect(mark.outerHTML).not.toContain("error");
  });

  it("is as large as asked", () => {
    const { getByRole } = render(<VoteMark mark="agrees" size={16} />);
    expect(getByRole("img").getAttribute("width")).toBe("16");
  });

  it("ink: only Chat View greys", () => {
    const { getByRole } = render(<VoteMark mark="differs" size={26} variant="ink" />);
    const classes = [...getByRole("img").querySelectorAll("[class]")].map((el) => el.getAttribute("class")).join(" ");
    expect(classes).toContain("cv-ink");
    expect(classes).not.toMatch(/accent|page|seat/);
  });
});
