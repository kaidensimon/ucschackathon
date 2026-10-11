import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { EngineProvider } from "../../engine/EngineProvider";
import { FakeEngine, type FakeOptions } from "../../engine/fake";
import { SettingsBody } from "./SettingsPage";

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-theme");
});

function show(options: FakeOptions = {}) {
  const engine = new FakeEngine({ wordMs: 0, ...options });
  const user = userEvent.setup();
  render(
    <EngineProvider engine={engine}>
      <SettingsBody />
    </EngineProvider>,
  );
  return { engine, user };
}

const part = (name: string) => screen.getByRole("region", { name });
const longest = () => screen.findByRole("spinbutton", { name: "Longest answer" }) as Promise<HTMLInputElement>;

describe("Settings", () => {
  it("has four parts under one title", () => {
    show();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Settings");
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "Theme",
      "Model",
      "Answers",
      "About",
    ]);
    expect(part("About").textContent).toContain("Syndicate");
    expect(part("About").textContent).toContain("Phase 2 preview");
    expect(part("About").textContent).toContain("Sample data. Nothing leaves this computer.");
  });

  it("Model: names the model and says ready, and says this build talks to none", async () => {
    show();
    await waitFor(() => expect(part("Model").querySelector("[data-part=model-status]")).not.toBeNull());
    const status = part("Model").querySelector("[data-part=model-status]") as HTMLElement;
    expect(status.getAttribute("data-state")).toBe("ready");
    expect(status.textContent).toBe("stand-in-modelready");
    expect(part("Model").textContent).toContain("This build shows the screens only. It does not talk to a model yet.");
    // read only: nothing here pretends to connect
    expect(within(part("Model")).queryByRole("textbox")).toBeNull();
    expect(within(part("Model")).queryByRole("button")).toBeNull();
  });

  it("Model: says so when no model is answering", async () => {
    show({ modelState: "unreachable" });
    await waitFor(() => expect(part("Model").querySelector("[data-part=model-status]")).not.toBeNull());
    const status = part("Model").querySelector("[data-part=model-status]") as HTMLElement;
    expect(status.getAttribute("data-state")).toBe("unreachable");
    expect(status.textContent).toBe("No model is answering");
    // a mark as well as the words
    expect(status.querySelector("svg")).not.toBeNull();
  });

  it("Answers: saves the number and the instructions", async () => {
    const { engine, user } = show();
    const box = await longest();
    await waitFor(() => expect(box.value).toBe("1024"));
    await user.clear(box);
    await user.type(box, "2048");
    const text = screen.getByRole("textbox", { name: "Instructions for the model" });
    await user.clear(text);
    await user.type(text, "Answer in one line.");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Saved"));
    const saved = await engine.getSettings();
    expect(saved.maxAnswerTokens).toBe(2048);
    expect(saved.systemPrompt).toBe("Answer in one line.");
    expect(box.value).toBe("2048");
    expect(part("Answers").textContent).toContain("Kept until the app closes in this build.");
  });

  it("Answers: a number out of range is not saved, and the line says what is allowed", async () => {
    const { engine, user } = show();
    const box = await longest();
    await waitFor(() => expect(box.value).toBe("1024"));
    await user.clear(box);
    await user.type(box, "12{Enter}");
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe("Longest answer must be a whole number from 64 to 8192."),
    );
    expect(box.getAttribute("aria-invalid")).toBe("true");
    expect((await engine.getSettings()).maxAnswerTokens).toBe(1024);
    // typing again takes the mark away
    await user.type(box, "8");
    expect(box.getAttribute("aria-invalid")).toBeNull();
  });

  it("Theme: the switch sets the theme on the page, and follows a change made elsewhere", async () => {
    const { user } = show();
    const group = screen.getByRole("radiogroup", { name: "Theme" });
    // a new owner starts on Warm
    expect(
      within(group)
        .getAllByRole("radio")
        .map((r) => r.textContent),
    ).toEqual(["Warm", "Light", "Dark"]);
    expect(within(group).getByRole("radio", { name: "Warm" }).getAttribute("aria-checked")).toBe("true");
    await user.click(within(group).getByRole("radio", { name: "Dark" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    await waitFor(() =>
      expect(within(group).getByRole("radio", { name: "Dark" }).getAttribute("aria-checked")).toBe("true"),
    );
    // a change made to the page from outside (a saved choice read at start-up) shows here too
    document.documentElement.setAttribute("data-theme", "light");
    await waitFor(() =>
      expect(within(group).getByRole("radio", { name: "Light" }).getAttribute("aria-checked")).toBe("true"),
    );
  });
});
