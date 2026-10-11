import { cleanup, render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Switch } from "./Switch";

afterEach(cleanup);

const options = [
  { value: "table", label: "Table" },
  { value: "chat", label: "Chat" },
] as const;

describe("Switch", () => {
  it("shows which side is chosen", () => {
    const { getByRole } = render(<Switch label="View" value="table" options={options} onChange={() => {}} />);
    expect(getByRole("radio", { name: "Table" }).getAttribute("aria-checked")).toBe("true");
    expect(getByRole("radio", { name: "Chat" }).getAttribute("aria-checked")).toBe("false");
    expect(getByRole("radiogroup", { name: "View" })).toBeTruthy();
  });

  it("keyboard: Tab reaches it once, an arrow moves, Enter chooses", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { getByRole } = render(<Switch label="View" value="table" options={options} onChange={onChange} />);
    await user.tab();
    expect(document.activeElement).toBe(getByRole("radio", { name: "Table" }));
    await user.keyboard("{ArrowRight}");
    expect(document.activeElement).toBe(getByRole("radio", { name: "Chat" }));
    await user.keyboard("{Enter}");
    expect(onChange).toHaveBeenCalledExactlyOnceWith("chat");
    await user.tab();
    expect(document.activeElement).toBe(document.body);
  });

  it("pressing the chosen side again leaves it chosen", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { getByRole } = render(<Switch label="View" value="table" options={options} onChange={onChange} />);
    await user.click(getByRole("radio", { name: "Table" }));
    expect(onChange).not.toHaveBeenCalled();
  });
});
