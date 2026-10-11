import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { carried, Sidebar } from "../../components/frame/Sidebar";
import type { ChatSummary } from "../../engine/client";
import { EngineProvider } from "../../engine/EngineProvider";
import { FakeEngine, type FakeOptions } from "../../engine/fake";
import { groupChats, groupOf, messagesWords, plainWords, whenWords } from "./groups";
import { HistoryList } from "./HistoryList";
import { safeFilename } from "./saveFile";

// The stand-in's clock is set to 18:00 on the computer's own calendar, so the sample chats
// (30 minutes, 26 hours and 6 days old) fall on today, yesterday and earlier in any time zone.
const NOW = new Date(2026, 9, 10, 18, 0, 0);

beforeAll(() => {
  // what the menu and the dialogs ask of a browser that jsdom does not have
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  Element.prototype.scrollIntoView ??= () => {};
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => {};
  Element.prototype.releasePointerCapture ??= () => {};
});

afterEach(cleanup);

function Where() {
  const { pathname, search } = useLocation();
  return <p data-testid="where">{pathname + search}</p>;
}

function show(options: FakeOptions = {}, at = "/history") {
  const engine = new FakeEngine({ now: NOW.toISOString(), wordMs: 0, ...options });
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={[at]}>
      <EngineProvider engine={engine}>
        <HistoryList now={NOW} />
        <Where />
      </EngineProvider>
    </MemoryRouter>,
  );
  return { engine, user };
}

const group = (name: string) => screen.getByRole("region", { name });
const titlesUnder = (name: string) =>
  within(group(name))
    .getAllByRole("link")
    .map((a) => a.textContent);
const headings = () => screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);

async function openMenu(user: ReturnType<typeof userEvent.setup>, title: string) {
  await user.click(await screen.findByRole("button", { name: `More for ${title}` }));
  return screen.findByRole("menu");
}

describe("History groups", () => {
  it("puts each chat under one plain heading, and the pinned chat only under Pinned", async () => {
    show();
    await screen.findByRole("region", { name: "Pinned" });
    expect(headings()).toEqual(["Pinned", "Yesterday", "Earlier"]);
    expect(titlesUnder("Pinned")).toEqual(["Ending the lease early"]);
    expect(titlesUnder("Yesterday")).toEqual(["Packing list for a week away"]);
    expect(titlesUnder("Earlier")).toEqual(["Explain compound interest"]);
  });

  it("a row: the title is the link to the chat, with one line of preview and the time", async () => {
    show({}, "/history?fast=1");
    const link = await screen.findByRole("link", { name: "Ending the lease early" });
    expect(link.getAttribute("href")).toMatch(/^\/chat\/c\d+\?fast=1$/);
    const row = link.closest("[data-part=history-row]") as HTMLElement;
    expect(row.querySelector("[data-part=history-preview]")?.textContent).toContain("Keep it short:");
    expect(row.querySelector("time")?.textContent).toBe("Today 17:30");
    // what can be done with the chat sits beside the link, never inside it
    expect(link.querySelector("button")).toBeNull();
    expect(within(row).getByRole("button", { name: "More for Ending the lease early" })).toBeTruthy();
  });

  it("sorts by the calendar day, not by hours", () => {
    const chat = (pinned: boolean, at: Date) => ({ pinned, updatedAt: at.toISOString() });
    expect(groupOf(chat(false, new Date(2026, 9, 10, 0, 5)), NOW)).toBe("Today");
    expect(groupOf(chat(false, new Date(2026, 9, 9, 23, 55)), NOW)).toBe("Yesterday");
    expect(groupOf(chat(false, new Date(2026, 9, 8, 23, 55)), NOW)).toBe("Earlier");
    expect(groupOf(chat(true, new Date(2026, 9, 1, 12, 0)), NOW)).toBe("Pinned");
  });

  it("keeps the headings in order and the newest chat first", () => {
    const chat = (id: string, pinned: boolean, at: Date): ChatSummary => ({
      id,
      title: id,
      pinned,
      createdAt: at.toISOString(),
      updatedAt: at.toISOString(),
      messageCount: 2,
      preview: "",
      match: null,
    });
    const groups = groupChats(
      [
        chat("old", false, new Date(2026, 8, 1, 9, 0)),
        chat("morning", false, new Date(2026, 9, 10, 8, 0)),
        chat("noon", false, new Date(2026, 9, 10, 12, 0)),
        chat("kept", true, new Date(2026, 9, 2, 9, 0)),
      ],
      NOW,
    );
    expect(groups.map((g) => [g.name, g.chats.map((c) => c.id)])).toEqual([
      ["Pinned", ["kept"]],
      ["Today", ["noon", "morning"]],
      ["Earlier", ["old"]],
    ]);
  });

  it("writes the time in plain words", () => {
    const at = (d: Date) => d.toISOString();
    expect(whenWords(at(new Date(2026, 9, 10, 9, 5)), NOW)).toBe("Today 09:05");
    expect(whenWords(at(new Date(2026, 9, 10, 9, 5)), NOW, "Today")).toBe("09:05");
    expect(whenWords(at(new Date(2026, 9, 9, 16, 0)), NOW)).toBe("Yesterday 16:00");
    expect(whenWords(at(new Date(2026, 9, 9, 16, 0)), NOW, "Yesterday")).toBe("16:00");
    expect(whenWords(at(new Date(2026, 9, 4, 16, 0)), NOW, "Earlier")).toBe("4 Oct");
    expect(whenWords(at(new Date(2025, 11, 31, 16, 0)), NOW)).toBe("31 Dec 2025");
  });

  it("small words", () => {
    expect(plainWords("- Warm coat - **Two** `jumpers`")).toBe("Warm coat - Two jumpers");
    expect(messagesWords(1)).toBe("1 message");
    expect(messagesWords(4)).toBe("4 messages");
    expect(safeFilename("Rent: now/later?.md")).toBe("Rent- now-later-.md");
  });
});

describe("History search", () => {
  it("narrows the list as you type, and shows the passage that matches", async () => {
    const { user } = show();
    await screen.findByRole("region", { name: "Pinned" });
    await user.type(screen.getByRole("searchbox", { name: "Search your chats" }), "jumpers");
    await waitFor(() => expect(headings()).toEqual(["Yesterday"]));
    expect(titlesUnder("Yesterday")).toEqual(["Packing list for a week away"]);
    expect(group("Yesterday").querySelector("mark")?.textContent).toBe("jumpers");
  });

  it("says so when no chat matches, and Clear brings the list back", async () => {
    const { user } = show();
    await screen.findByRole("region", { name: "Pinned" });
    await user.type(screen.getByRole("searchbox"), "zebra");
    const line = await screen.findByText(/No chat mentions/);
    expect(line.textContent).toBe("No chat mentions zebra.");
    expect(screen.queryAllByRole("heading", { level: 2 })).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Clear the search" }));
    await waitFor(() => expect(headings()).toEqual(["Pinned", "Yesterday", "Earlier"]));
    expect(screen.queryByText(/No chat mentions/)).toBeNull();
  });
});

describe("History row actions", () => {
  it("rename: Enter saves the new name", async () => {
    const { user, engine } = show();
    const menu = await openMenu(user, "Packing list for a week away");
    await user.click(within(menu).getByRole("menuitem", { name: "Rename" }));
    const dialog = await screen.findByRole("dialog", { name: "Rename this chat" });
    const box = within(dialog).getByRole("textbox", { name: "Name" });
    expect((box as HTMLInputElement).value).toBe("Packing list for a week away");
    await user.clear(box);
    await user.type(box, "Cold city packing{Enter}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(await screen.findByRole("link", { name: "Cold city packing" })).toBeTruthy();
    await waitFor(async () => expect((await engine.listChats()).map((c) => c.title)).toContain("Cold city packing"));
  });

  it("rename: Esc cancels and the name stays", async () => {
    const { user, engine } = show();
    const menu = await openMenu(user, "Packing list for a week away");
    await user.click(within(menu).getByRole("menuitem", { name: "Rename" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox"), " changed{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("link", { name: "Packing list for a week away" })).toBeTruthy();
    expect((await engine.listChats()).map((c) => c.title)).toContain("Packing list for a week away");
  });

  it("pin and unpin move the chat between Pinned and its day", async () => {
    const { user, engine } = show();
    let menu = await openMenu(user, "Ending the lease early");
    await user.click(within(menu).getByRole("menuitem", { name: "Unpin" }));
    await waitFor(() => expect(headings()).toEqual(["Today", "Yesterday", "Earlier"]));
    expect(titlesUnder("Today")).toEqual(["Ending the lease early"]);

    menu = await openMenu(user, "Explain compound interest");
    await user.click(within(menu).getByRole("menuitem", { name: "Pin" }));
    await waitFor(() => expect(headings()).toEqual(["Pinned", "Today", "Yesterday"]));
    expect(titlesUnder("Pinned")).toEqual(["Explain compound interest"]);
    await waitFor(async () =>
      expect((await engine.listChats()).filter((c) => c.pinned).map((c) => c.title)).toEqual([
        "Explain compound interest",
      ]),
    );
  });

  it("delete asks first: Keep it keeps, Delete chat deletes", async () => {
    const { user, engine } = show();
    let menu = await openMenu(user, "Ending the lease early");
    await user.click(within(menu).getByRole("menuitem", { name: "Delete" }));
    let dialog = await screen.findByRole("alertdialog", { name: "Delete this chat?" });
    expect(dialog.textContent).toContain(
      "Ending the lease early and its 4 messages will be gone. This cannot be undone.",
    );
    await user.click(within(dialog).getByRole("button", { name: "Keep it" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(await engine.listChats()).toHaveLength(3);

    menu = await openMenu(user, "Ending the lease early");
    await user.click(within(menu).getByRole("menuitem", { name: "Delete" }));
    dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete chat" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Ending the lease early" })).toBeNull());
    expect(headings()).toEqual(["Yesterday", "Earlier"]);
    expect(screen.getByRole("status").textContent).toBe("Deleted Ending the lease early");
    expect(await engine.listChats()).toHaveLength(2);
  });

  it("export saves a file through the browser and says its name", async () => {
    const made = vi.fn((_blob: Blob) => "blob:chat");
    Object.assign(URL, { createObjectURL: made, revokeObjectURL: vi.fn() });
    const pressed = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      expect(this.download).toBe("Packing list for a week away.md");
    });
    const { user } = show();
    // by keyboard: down to Export, right into its menu, Enter on the first way to save
    await openMenu(user, "Packing list for a week away");
    await user.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}");
    expect(document.activeElement?.textContent).toBe("Export");
    await user.keyboard("{ArrowRight}");
    await waitFor(() => expect(document.activeElement?.textContent).toBe("As Markdown"));
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Saved Packing list for a week away.md"));
    expect(pressed).toHaveBeenCalledOnce();
    expect(made.mock.calls[0]?.[0].type).toContain("text/markdown");
  });

  it("keeps the keyboard in a sensible place", async () => {
    const { user } = show();
    const more = (title: string) => screen.getByRole("button", { name: `More for ${title}` });

    // Esc in the rename dialog: back on the row's menu button
    (await screen.findByRole("button", { name: "More for Packing list for a week away" })).focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Rename"));
    await user.keyboard("{Enter}");
    const box = await screen.findByRole("textbox", { name: "Name" });
    await waitFor(() => expect(document.activeElement).toBe(box));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(document.activeElement).toBe(more("Packing list for a week away")));

    // pin: the row is drawn anew under Pinned, and its menu button has the keyboard again
    await user.keyboard("{Enter}");
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Rename"));
    await user.keyboard("{ArrowDown}");
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Pin"));
    await user.keyboard("{Enter}");
    await waitFor(() => expect(titlesUnder("Pinned")).toContain("Packing list for a week away"));
    await waitFor(() => expect(document.activeElement).toBe(more("Packing list for a week away")));

    // delete: the row is gone, so the keyboard goes to the title
    await user.keyboard("{Enter}");
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Rename"));
    await user.keyboard("{End}");
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Delete"));
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("alertdialog");
    // the safe choice has focus first
    await waitFor(() => expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Keep it" })));
    await user.keyboard("{Tab}{Enter}");
    await waitFor(() => expect(screen.queryByRole("link", { name: "Packing list for a week away" })).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("heading", { level: 1 })));
  });

  it("says what happened when the engine refuses", async () => {
    const { user, engine } = show();
    const menu = await openMenu(user, "Packing list for a week away");
    vi.spyOn(engine, "updateChat").mockRejectedValue(new Error("down"));
    await user.click(within(menu).getByRole("menuitem", { name: "Pin" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("The chat was not pinned. Try again."));
    // the list goes back to how it was
    await waitFor(() => expect(titlesUnder("Yesterday")).toEqual(["Packing list for a week away"]));
  });
});

describe("History with no chats", () => {
  it("says so and offers a new chat", async () => {
    const { user } = show({ empty: true }, "/history?empty=1");
    expect(await screen.findByText("No chats yet.")).toBeTruthy();
    expect(screen.queryByRole("searchbox")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Start a new chat" }));
    expect(screen.getByTestId("where").textContent).toBe("/chat/new?empty=1");
  });
});

describe("Sidebar links", () => {
  const links = () =>
    Object.fromEntries(screen.getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")]));

  it("lead to the built screens", () => {
    render(
      <MemoryRouter initialEntries={["/history"]}>
        <Sidebar wide onShortcuts={() => {}} />
      </MemoryRouter>,
    );
    expect(links()).toEqual({
      "New chat": "/chat/new",
      History: "/history",
      Settings: "/settings",
    });
    expect(screen.getByRole("link", { current: "page" }).textContent).toBe("History");
  });

  for (const wide of [true, false]) {
    it(`${wide ? "wide" : "icon rail"}: Settings sits at the bottom, right under Shortcuts and above the sample note`, async () => {
      const user = userEvent.setup();
      render(
        <MemoryRouter initialEntries={["/settings"]}>
          <Sidebar wide={wide} onShortcuts={() => {}} />
        </MemoryRouter>,
      );
      const nav = screen.getByRole("navigation", { name: "Main" });
      const name = (el: Element) => el.getAttribute("aria-label") ?? el.textContent ?? "";
      const controls = [...nav.querySelectorAll("a, button")];
      expect(controls.map(name)).toEqual([
        "New chat",
        "History",
        "Shortcuts",
        "Settings",
      ]);
      // Shortcuts is a button, Settings a link, and the sample note comes after both
      const [shortcuts, settings] = controls.slice(-2);
      expect(shortcuts?.tagName).toBe("BUTTON");
      expect(settings?.tagName).toBe("A");
      expect(settings?.getAttribute("href")).toBe("/settings");
      expect(settings?.getAttribute("aria-current")).toBe("page");
      const note = nav.querySelector("p");
      expect(note?.textContent).toContain("Sample data");
      expect(
        settings && note ? settings.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING : 0,
      ).toBeTruthy();
      // the keyboard walks them in the same order, once each
      const walked: string[] = [];
      for (let i = 0; i < controls.length; i++) {
        await user.tab();
        walked.push(document.activeElement ? name(document.activeElement) : "");
      }
      expect(walked).toEqual(controls.map(name));
    });
  }

  it("carry the sample-data options along, and nothing else", () => {
    render(
      <MemoryRouter initialEntries={["/sample/lease?fast=1&help=1&model=unreachable"]}>
        <Sidebar wide onShortcuts={() => {}} />
      </MemoryRouter>,
    );
    expect(links().Settings).toBe("/settings?fast=1&model=unreachable");
    // Library, Models and Sample debate were taken out of the sidebar (2026-10-11): no link is current here
    expect(screen.queryByRole("link", { current: "page" })).toBeNull();
    expect(carried("?q=lease&empty=1")).toBe("?empty=1");
    expect(carried("")).toBe("");
  });
});
