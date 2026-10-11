// The shapes of the data the chat screens show: chats, messages, an answer being written.
// Phase 2 is UI only: there is no engine and no model. An in-memory stand-in (fake.ts)
// supplies these shapes. A real engine, built in a later phase, would supply the same ones,
// so the screens would not need to change.

export type Id = string;
/** ISO 8601 time, e.g. 2026-10-10T21:04:11.000Z */
export type IsoTime = string;

// ---- model server (llama.cpp's llama-server) ----

export type ModelState =
  /** the engine reached the server and it answered ready */
  | "ready"
  /** the server answered but is still loading its model */
  | "loading"
  /** nothing answered at the address */
  | "unreachable"
  /** something answered, but not like llama-server (wrong address, wrong key) */
  | "refused";

export interface ModelStatus {
  state: ModelState;
  /** where the engine looks for llama-server, e.g. http://127.0.0.1:8080 */
  address: string;
  /** model name as the server reports it, when known */
  name: string | null;
  /** context size in tokens, when the server reports it */
  contextTokens: number | null;
  /** plain words for the owner when state is not "ready" */
  detail: string | null;
  checkedAt: IsoTime;
}

export interface Health {
  ok: true;
  engineVersion: string;
  model: ModelStatus;
}

export interface Settings {
  /** address of llama-server */
  modelAddress: string;
  /** true when a key for llama-server is stored (the key itself is never sent back) */
  hasModelKey: boolean;
  /** instructions given to the model before every chat */
  systemPrompt: string;
  /** most tokens the model may write in one answer */
  maxAnswerTokens: number;
}
export interface SettingsUpdate {
  modelAddress?: string;
  /** empty string clears the key */
  modelKey?: string;
  systemPrompt?: string;
  maxAnswerTokens?: number;
}

// ---- chats ----

export type MessageRole = "user" | "assistant";
export type MessageStatus =
  /** the answer is still being written (a run is open) */
  | "writing"
  | "complete"
  /** the owner pressed Stop; the text so far is kept */
  | "stopped"
  /** the model server failed; `error` says what happened */
  | "failed";

export interface Message {
  id: Id;
  chatId: Id;
  role: MessageRole;
  text: string;
  status: MessageStatus;
  createdAt: IsoTime;
  /** assistant messages: model name, speed and counts once known */
  model: string | null;
  tokensPerSecond: number | null;
  answerTokens: number | null;
  /** plain words when status is "failed" */
  error: string | null;
  /** assistant messages: the open run, while status is "writing" */
  runId: Id | null;
}

export interface ChatSummary {
  id: Id;
  title: string;
  pinned: boolean;
  createdAt: IsoTime;
  updatedAt: IsoTime;
  messageCount: number;
  /** first words of the newest message, for the History list */
  preview: string;
  /** set only for search results: a short passage with the match, plain text */
  match: string | null;
}

export interface Chat extends Omit<ChatSummary, "match" | "preview"> {
  messages: Message[];
}

export interface ChatUpdate {
  title?: string;
  pinned?: boolean;
}

// ---- asking and answering ----

export interface SendMessage {
  text: string;
}
export interface RunStarted {
  runId: Id;
  userMessage: Message | null;
  assistantMessage: Message;
  chat: ChatSummary;
}

// The events of one answer being written, in order.
export type RunEvent =
  | { type: "run.started"; runId: Id; messageId: Id; seq: number }
  /** what the model server is doing before the first word arrives */
  | { type: "run.status"; runId: Id; seq: number; status: "waiting" | "reading"; progress: number | null }
  /** more text; append it */
  | { type: "delta"; runId: Id; seq: number; text: string }
  /** the run ended; `message` is the saved assistant message */
  | { type: "run.done"; runId: Id; seq: number; message: Message }
  | { type: "run.error"; runId: Id; seq: number; message: Message };

export const DEFAULTS = {
  modelAddress: "http://127.0.0.1:8080",
  maxAnswerTokens: 1024,
  systemPrompt:
    "You are a careful assistant running on the owner's own computer. Answer plainly and briefly. If you are not sure, say so.",
} as const;
