// What the chat screens need from "the thing that holds chats and writes answers".
// Phase 2 is UI only, so the one maker is FakeEngine (fake.ts): an in-memory stand-in with
// sample chats and a canned answer. No engine, no model, no network.
// Screens never reach for data themselves; they use useEngine().
import type { Chat, ChatSummary, ChatUpdate, Health, RunEvent, RunStarted, Settings, SettingsUpdate } from "./contract";

export type * from "./contract";

export interface ExportedChat {
  filename: string;
  mime: string;
  text: string;
}

export interface EngineClient {
  health(): Promise<Health>;
  getSettings(): Promise<Settings>;
  updateSettings(update: SettingsUpdate): Promise<Settings>;
  listChats(query?: string): Promise<ChatSummary[]>;
  createChat(title?: string): Promise<Chat>;
  getChat(id: string): Promise<Chat>;
  updateChat(id: string, update: ChatUpdate): Promise<Chat>;
  deleteChat(id: string): Promise<void>;
  exportChat(id: string, format: "markdown" | "json"): Promise<ExportedChat>;
  /** `seats`: how many council members to seat (2 to 6), when the screen knows; the stand-in ignores it. */
  sendMessage(
    chatId: string,
    text: string,
    seats?: number,
    search?: boolean,
    found?: { title: string; url: string; snippet: string }[],
  ): Promise<RunStarted>;
  regenerate(chatId: string): Promise<RunStarted>;
  stopRun(runId: string): Promise<void>;
  /** Calls onEvent for every event of the run, from its start. Resolves when the run ends or `signal` aborts. */
  streamRun(runId: string, onEvent: (event: RunEvent) => void, signal?: AbortSignal): Promise<void>;
}

/** A failure explained in plain words the screen can show. */
export class EngineError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "EngineError";
    this.code = code;
    this.status = status;
  }
}
