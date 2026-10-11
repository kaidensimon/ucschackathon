// The real engine: the Python council's API, reached over HTTP on this machine.
// Same shapes as the in-memory stand-in (fake.ts), so the screens do not change.
// EngineProvider only switches to this one when the council answers; otherwise the
// stand-in stays in charge.
import type { DebateEvent } from "../lib/events";
import {
  type Chat,
  type ChatSummary,
  type ChatUpdate,
  type EngineClient,
  EngineError,
  type ExportedChat,
  type Health,
  type RunEvent,
  type RunStarted,
  type Settings,
  type SettingsUpdate,
} from "./client";

const DEFAULT_URL = "http://127.0.0.1:8765";

/** Where the council's API lives: set by the window, then by the build, then the default. */
export function engineUrl(): string {
  const fromWindow =
    typeof window === "undefined" ? undefined : (window as unknown as { COUNCIL_ENGINE_URL?: string }).COUNCIL_ENGINE_URL;
  const fromBuild = import.meta.env.VITE_ENGINE_URL as string | undefined;
  return (fromWindow ?? fromBuild ?? DEFAULT_URL).replace(/\/+$/, "");
}

function unreachable(address: string): EngineError {
  return new EngineError(0, "unreachable", `The council engine is not answering at ${address}.`);
}

function isAbort(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** Turns a non-2xx answer into an EngineError with the plain words the backend sent. */
async function failure(response: Response): Promise<EngineError> {
  let code = "engine";
  let message = `The council engine answered with an error (${response.status}).`;
  try {
    const body = (await response.json()) as { code?: unknown; message?: unknown } | null;
    if (body && typeof body.code === "string") code = body.code;
    if (body && typeof body.message === "string") message = body.message;
  } catch {
    // no JSON body: keep the plain words above
  }
  return new EngineError(response.status, code, message);
}

async function open(baseUrl: string, path: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(baseUrl + path, init);
  } catch (error) {
    if (isAbort(error)) throw error;
    throw unreachable(baseUrl);
  }
  if (!response.ok) throw await failure(response);
  return response;
}

/**
 * Reads a text/event-stream: one JSON object per "data:" line. Calls onEvent for each.
 * Resolves when `isLast` says so, when the stream ends, or when `signal` aborts.
 */
async function readEvents<T>(
  baseUrl: string,
  path: string,
  onEvent: (event: T) => void,
  isLast: (event: T) => boolean,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) return;
  let response: Response;
  try {
    response = await open(baseUrl, path, { headers: { Accept: "text/event-stream" }, signal });
  } catch (error) {
    if (isAbort(error) || signal?.aborted) return;
    throw error;
  }
  const body = response.body;
  if (!body) return;
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const stop = () => {
    reader.cancel().catch(() => {});
  };
  signal?.addEventListener("abort", stop, { once: true });
  let buffer = "";
  try {
    for (;;) {
      if (signal?.aborted) return;
      const { done, value } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split(/\r?\n/);
      // the last piece may be half a line: keep it for the next chunk
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data:")) continue; // ":" comments, "id:", "event:", blank lines
        const text = line.slice(5).trim();
        if (!text) continue;
        let event: T;
        try {
          event = JSON.parse(text) as T;
        } catch {
          continue;
        }
        if (signal?.aborted) return;
        onEvent(event);
        if (isLast(event)) return;
      }
    }
  } catch (error) {
    if (isAbort(error) || signal?.aborted) return;
    throw unreachable(baseUrl);
  } finally {
    signal?.removeEventListener("abort", stop);
    stop();
  }
}

/** The council's debate for one run, event by event, from its start. Ends after the answer is released. */
export function streamDebate(
  baseUrl: string,
  runId: string,
  onEvent: (e: DebateEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return readEvents<DebateEvent>(
    baseUrl.replace(/\/+$/, ""),
    `/ui/runs/${encodeURIComponent(runId)}/debate`,
    onEvent,
    (e) => (e as { type?: string }).type === "answer.released",
    signal,
  );
}

/** One line of a web search results page: what the "Web search" switch hands to the council. */
export interface WebResult {
  title: string;
  url: string;
  snippet: string;
}

export class HttpEngine implements EngineClient {
  readonly baseUrl: string;

  constructor(baseUrl: string = engineUrl()) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  private async json<T>(path: string, method = "GET", body?: unknown, signal?: AbortSignal): Promise<T> {
    const init: RequestInit = { method, signal, headers: { Accept: "application/json" } };
    if (body !== undefined) {
      init.headers = { Accept: "application/json", "Content-Type": "application/json" };
      init.body = JSON.stringify(body);
    }
    const response = await open(this.baseUrl, path, init);
    try {
      return (await response.json()) as T;
    } catch {
      throw new EngineError(response.status, "engine", "The council engine sent an answer this app could not read.");
    }
  }

  private async empty(path: string, method: string): Promise<void> {
    await open(this.baseUrl, path, { method });
  }

  health(signal?: AbortSignal): Promise<Health> {
    return this.json<Health>("/ui/health", "GET", undefined, signal);
  }

  getSettings(): Promise<Settings> {
    return this.json<Settings>("/ui/settings");
  }

  updateSettings(update: SettingsUpdate): Promise<Settings> {
    return this.json<Settings>("/ui/settings", "PATCH", update);
  }

  listChats(query?: string): Promise<ChatSummary[]> {
    const q = query?.trim();
    return this.json<ChatSummary[]>(q ? `/ui/chats?query=${encodeURIComponent(q)}` : "/ui/chats");
  }

  createChat(title?: string): Promise<Chat> {
    return this.json<Chat>("/ui/chats", "POST", title === undefined ? {} : { title });
  }

  getChat(id: string): Promise<Chat> {
    return this.json<Chat>(`/ui/chats/${encodeURIComponent(id)}`);
  }

  updateChat(id: string, update: ChatUpdate): Promise<Chat> {
    return this.json<Chat>(`/ui/chats/${encodeURIComponent(id)}`, "PATCH", update);
  }

  deleteChat(id: string): Promise<void> {
    return this.empty(`/ui/chats/${encodeURIComponent(id)}`, "DELETE");
  }

  exportChat(id: string, format: "markdown" | "json"): Promise<ExportedChat> {
    return this.json<ExportedChat>(`/ui/chats/${encodeURIComponent(id)}/export?format=${format}`);
  }

  sendMessage(
    chatId: string,
    text: string,
    seats?: number,
    search?: boolean,
    found?: WebResult[],
  ): Promise<RunStarted> {
    const body: { text: string; seats?: number; search?: boolean; searchResults?: WebResult[] } = { text };
    // results the desktop shell already read off a search page: the engine uses them as they are
    if (found && found.length > 0) body.searchResults = found;
    // "Web search" switch: the engine runs one plain web search and hands the results to the council
    if (search === true) body.search = true;
    if (typeof seats === "number" && Number.isFinite(seats)) body.seats = Math.min(6, Math.max(2, Math.round(seats)));
    return this.json<RunStarted>(`/ui/chats/${encodeURIComponent(chatId)}/messages`, "POST", body);
  }

  regenerate(chatId: string): Promise<RunStarted> {
    return this.json<RunStarted>(`/ui/chats/${encodeURIComponent(chatId)}/regenerate`, "POST", {});
  }

  stopRun(runId: string): Promise<void> {
    return this.empty(`/ui/runs/${encodeURIComponent(runId)}/stop`, "POST");
  }

  streamRun(runId: string, onEvent: (event: RunEvent) => void, signal?: AbortSignal): Promise<void> {
    return readEvents<RunEvent>(
      this.baseUrl,
      `/ui/runs/${encodeURIComponent(runId)}/events`,
      onEvent,
      (e) => e.type === "run.done" || e.type === "run.error",
      signal,
    );
  }

  /** The debate of one run (see streamDebate). */
  streamDebate(runId: string, onEvent: (e: DebateEvent) => void, signal?: AbortSignal): Promise<void> {
    return streamDebate(this.baseUrl, runId, onEvent, signal);
  }
}
