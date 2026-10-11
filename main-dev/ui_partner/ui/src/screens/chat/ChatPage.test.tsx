import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EngineProvider } from "../../engine/EngineProvider";
import { FakeEngine, type FakeOptions } from "../../engine/fake";
import { ChatPage } from "./ChatPage";
import { SEATS_DEFAULT, seatsOf } from "./ChatTopBar";
import { speedWords } from "./Conversation";
import { waitingView } from "./LiveStage";

afterEach(() => {
  cleanup();
  Reflect.deleteProperty(navigator, "clipboard");
});

const CANNED_START = "Here is a short answer from the stand-in model.";
const CANNED_END = "That is all.";

function Address() {
  const { pathname, search } = useLocation();
  return <output data-testid="address">{pathname + search}</output>;
}

const LEASE = "Ending the lease early";
const PACKING = "Packing list for a week away";
const INTEREST = "Explain compound interest";

/** `route` may name a sample chat by its title: "/chat/{Packing list for a week away}" */
async function open(route: string, options: FakeOptions = {}) {
  const engine = new FakeEngine({ wordMs: 0, ...options });
  const chats = await engine.listChats();
  const at = route.replace(/\{(.+)\}/, (_, title: string) => chats.find((c) => c.title === title)?.id ?? "");
  const view = render(
    <EngineProvider engine={engine}>
      <MemoryRouter initialEntries={[at]}>
        <Routes>
          <Route path="/chat/new" element={<ChatPage />} />
          <Route path="/chat/:id" element={<ChatPage />} />
        </Routes>
        <Address />
      </MemoryRouter>
    </EngineProvider>,
  );
  const all = (part: string) => [...view.container.querySelectorAll<HTMLElement>(`[data-part=${part}]`)];
  return { engine, all, at, ...view };
}

const box = () => screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Message the model" });
const address = () => screen.getByTestId("address").textContent ?? "";
/** the id of the chat the address is at */
const here = () =>
  address()
    .replace(/^\/chat\//, "")
    .replace(/\?.*$/, "");
/** the address follows a moment after the new chat is on screen */
const arrived = () => waitFor(() => expect(address()).toMatch(/^\/chat\/c\d+/));
const words = (el: Element | undefined | null) => el?.textContent?.replace(/\s+/g, " ").trim() ?? "";

function ask(text: string) {
  fireEvent.change(box(), { target: { value: text } });
  fireEvent.keyDown(box(), { key: "Enter" });
}

function stubClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
}

describe("new chat", () => {
  it("starts empty: the line, the box, and Ask waiting for words", async () => {
    const { all } = await open("/chat/new");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("What do you want to ask?");
    expect(words(all("chat-top-bar")[0])).toContain("New chat");
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Ask" }).disabled).toBe(true);
    fireEvent.change(box(), { target: { value: "  " } });
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Ask" }).disabled).toBe(true);
    fireEvent.change(box(), { target: { value: "Hello" } });
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Ask" }).disabled).toBe(false);
    await waitFor(() => expect(words(all("model-pill")[0])).toBe("Model ready, stand-in-model"));
  });

  it("Ask makes a chat, goes to it with the address options kept, and shows the answer", async () => {
    const { engine, all } = await open("/chat/new?fast=1");
    ask("Why is the sky blue?");
    await waitFor(() => expect(all("answer")).toHaveLength(1));
    await arrived();
    expect(address()).toMatch(/^\/chat\/c\d+\?fast=1$/);
    expect(words(all("owner-message")[0])).toBe("You asked: Why is the sky blue?");
    expect(all("answer")[0]?.getAttribute("data-status")).toBe("complete");
    expect(words(all("answer")[0])).toContain(CANNED_START);
    expect(words(all("answer")[0])).toContain(CANNED_END);
    expect(words(all("answer-meta")[0])).toContain("stand-in-model");
    expect(words(all("answer-meta")[0])).toContain("41.5 tokens a second");
    // the chat's first words became its title, and the box is empty again
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Why is the sky blue?");
    expect(box().value).toBe("");
    const chats = await engine.listChats();
    expect(chats).toHaveLength(4);
    expect((await engine.getChat(here())).messages.map((m) => m.role)).toEqual(["user", "assistant"]);
  });

  it("a second question goes to the same chat, not to another new one", async () => {
    const { engine, all } = await open("/chat/new");
    ask("One");
    await waitFor(() => expect(all("answer")).toHaveLength(1));
    ask("Two");
    await waitFor(() => expect(all("answer")).toHaveLength(2));
    expect(all("owner-message").map(words)).toEqual(["You asked: One", "You asked: Two"]);
    await arrived();
    expect(await engine.listChats()).toHaveLength(4);
    expect((await engine.getChat(here())).messages).toHaveLength(4);
  });

  it("Shift and Enter starts a new line and sends nothing", async () => {
    const { engine } = await open("/chat/new");
    fireEvent.change(box(), { target: { value: "One" } });
    fireEvent.keyDown(box(), { key: "Enter", shiftKey: true });
    expect(address()).toBe("/chat/new");
    expect(await engine.listChats()).toHaveLength(3);
  });

  it("the Ask button sends too", async () => {
    const { all } = await open("/chat/new");
    fireEvent.change(box(), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(all("answer")).toHaveLength(1));
    expect(document.activeElement).toBe(box());
  });

  it("the / key goes to the message box", async () => {
    await open("/chat/new");
    expect(document.activeElement).not.toBe(box());
    fireEvent.keyDown(document.body, { key: "/" });
    expect(document.activeElement).toBe(box());
  });
});

describe("a saved chat", () => {
  it("shows its messages in order, the newest answer with Write again", async () => {
    const { all } = await open(`/chat/{${LEASE}}`);
    await waitFor(() => expect(all("answer")).toHaveLength(2));
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Ending the lease early");
    expect(all("owner-message").map(words)).toEqual([
      "You asked: Can I end my apartment lease early, and what would it cost me?",
      "You asked: What should the notice say?",
    ]);
    expect(within(all("answer")[0] as HTMLElement).queryByRole("button", { name: "Write again" })).toBeNull();
    expect(within(all("answer")[0] as HTMLElement).getByRole("button", { name: "Copy" })).toBeTruthy();
    expect(within(all("answer")[1] as HTMLElement).getByRole("button", { name: "Write again" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Messages" }).getAttribute("tabindex")).toBe("0");
  });

  it("a follow-up is added under the chat", async () => {
    const { all, at } = await open(`/chat/{${INTEREST}}`);
    await waitFor(() => expect(all("answer")).toHaveLength(1));
    ask("And simple interest?");
    await waitFor(() => expect(all("answer")).toHaveLength(2));
    expect(address()).toBe(at);
    expect(words(all("owner-message")[1])).toBe("You asked: And simple interest?");
    expect(words(all("answer")[1])).toContain(CANNED_START);
    // Write again has moved to the newest answer
    expect(within(all("answer")[0] as HTMLElement).queryByRole("button", { name: "Write again" })).toBeNull();
  });

  it("Write again replaces the newest answer", async () => {
    const { all, engine } = await open(`/chat/{${PACKING}}`);
    await waitFor(() => expect(words(all("answer")[0])).toContain("Warm coat"));
    fireEvent.click(screen.getByRole("button", { name: "Write again" }));
    await waitFor(() => expect(words(all("answer")[0])).toContain(CANNED_START));
    expect(all("answer")).toHaveLength(1);
    expect(words(all("answer")[0])).not.toContain("Warm coat");
    expect(all("owner-message")).toHaveLength(1);
    expect((await engine.getChat(here())).messages).toHaveLength(2);
  });

  it("Copy puts the answer on the clipboard and says Copied", async () => {
    const writeText = vi.fn(async (_text: string) => {});
    stubClipboard(writeText);
    const { all } = await open(`/chat/{${INTEREST}}`);
    await waitFor(() => expect(all("answer")).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await screen.findByRole("button", { name: "Copied" });
    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText.mock.calls[0]?.[0]).toMatch(/^Compound interest is interest paid on both/);
  });

  it("a refused copy says so in words", async () => {
    stubClipboard(() => Promise.reject(new Error("no")));
    const { all } = await open(`/chat/{${INTEREST}}`);
    await waitFor(() => expect(all("answer")).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(words(all("answer-meta")[0])).toContain("Could not copy"));
    expect(screen.getByRole("button", { name: "Copy" })).toBeTruthy();
  });
});

describe("while an answer is being written", () => {
  it("the words grow, the button is Stop, and Stop keeps the words and marks them Stopped", async () => {
    const { all, engine } = await open("/chat/new", { wordMs: 50 });
    ask("Tell me something");
    await waitFor(() => expect(all("answer")[0]?.getAttribute("data-status")).toBe("writing"));
    expect(words(all("answer-writing")[0])).toBe("Writing");
    expect(screen.queryByRole("button", { name: "Ask" })).toBeNull();
    await waitFor(() => expect(words(all("answer")[0])).toContain("Here is"));
    // Enter does not send a second question on top of the first
    fireEvent.change(box(), { target: { value: "Another" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(all("owner-message")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(all("answer")[0]?.getAttribute("data-status")).toBe("stopped"));
    const answer = words(all("answer")[0]);
    expect(answer).toContain("Here is");
    expect(answer).not.toContain(CANNED_END);
    expect(words(all("answer-meta")[0])).toContain("Stopped");
    expect(all("answer-writing")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Ask" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Write again" })).toBeTruthy();
    expect(words(all("chat-live-region")[0])).toBe("Stopped");
    await arrived();
    const saved = (await engine.getChat(here())).messages[1];
    expect(saved?.status).toBe("stopped");
    expect(box().value).toBe("Another");
  });

  it("half-written bold is closed, so no stray stars show", async () => {
    const { all } = await open("/chat/new", { wordMs: 20 });
    ask("Tell me something");
    await waitFor(() => expect(words(all("answer")[0])).toContain("bold"), { timeout: 3000 });
    expect(words(all("answer")[0])).not.toContain("**");
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(all("answer")[0]?.getAttribute("data-status")).toBe("stopped"));
  });
});

describe("when no model answers", () => {
  it("the pill says so, and asking shows the failed answer with Try again", async () => {
    const { all } = await open("/chat/new?model=unreachable", { modelState: "unreachable" });
    await waitFor(() => expect(words(all("model-pill")[0])).toBe("No model is answering"));
    ask("Anyone there?");
    await waitFor(() => expect(all("answer")[0]?.getAttribute("data-status")).toBe("failed"));
    await arrived();
    expect(address()).toMatch(/^\/chat\/c\d+\?model=unreachable$/);
    expect(words(screen.getByRole("alert"))).toContain(
      "The model server did not answer. Check that llama-server is running, then try again.",
    );
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
    expect(all("answer-meta")).toHaveLength(0);
    // trying again asks the engine again; the model is still away
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() =>
      expect(screen.getByRole<HTMLButtonElement>("button", { name: "Try again" }).disabled).toBe(false),
    );
    expect(all("answer")).toHaveLength(1);
    expect(all("answer")[0]?.getAttribute("data-status")).toBe("failed");
  });
});

describe("a chat that is gone", () => {
  it("says so and offers a new chat", async () => {
    const { all } = await open("/chat/nope?fast=1");
    await screen.findByRole("heading", { level: 1, name: "That chat does not exist any more." });
    expect(screen.queryByRole("textbox")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Start a new chat" }));
    await screen.findByRole("heading", { level: 1, name: "What do you want to ask?" });
    expect(address()).toBe("/chat/new?fast=1");
    expect(all("message-box")).toHaveLength(1);
  });
});

describe("speedWords", () => {
  it("writes the speed in plain words", () => {
    expect(speedWords(41.5)).toBe("41.5 tokens a second");
    expect(speedWords(41.46)).toBe("41.5 tokens a second");
    expect(speedWords(1)).toBe("1 token a second");
    expect(speedWords(12)).toBe("12 tokens a second");
  });
});

describe("the council's size", () => {
  it("is 2 to 6 seats, and nothing else counts as a choice", () => {
    expect(SEATS_DEFAULT).toBe(3);
    expect(seatsOf("4")).toBe(4);
    expect(seatsOf(2)).toBe(2);
    expect(seatsOf(6)).toBe(6);
    expect(seatsOf(null)).toBeNull();
    expect(seatsOf("")).toBeNull();
    expect(seatsOf("1")).toBeNull();
    expect(seatsOf("7")).toBeNull();
    expect(seatsOf("many")).toBeNull();
  });

  it("the table that waits has that many empty seats", () => {
    const idle = waitingView(3, false);
    expect(idle.phase).toBe("idle");
    expect(idle.seats.map((s) => s.shortName)).toEqual(["Seat 1", "Seat 2", "Seat 3"]);
    expect(idle.seats.every((s) => s.status === "ready")).toBe(true);
    const seating = waitingView(5, true);
    expect(seating.phase).toBe("spooling");
    expect(seating.seats).toHaveLength(5);
    expect(seating.seats.every((s) => s.status === "loading")).toBe(true);
    // blank: no model behind a seat
    expect(idle.seats.every((s) => !/gpt|deepseek|qwen|phi|gemma/i.test(s.modelName))).toBe(true);
  });

  it("the stand-in shows no slider and no table", async () => {
    const { all } = await open("/chat/new");
    expect(all("council-slider")).toHaveLength(0);
    expect(all("live-stage")).toHaveLength(0);
    expect(all("router-hint")).toHaveLength(0);
  });
});
