// The in-memory stand-in behind the chat screens: three sample chats and a canned answer that
// arrives word by word. Phase 2 is UI only, so this IS the data; nothing is saved when the
// app closes, and nothing talks to a model.
import type {
  Chat,
  ChatSummary,
  ChatUpdate,
  EngineClient,
  ExportedChat,
  Health,
  Message,
  ModelState,
  RunEvent,
  RunStarted,
  Settings,
  SettingsUpdate,
} from "./client";
import { EngineError } from "./client";

const ANSWER =
  "Here is a short answer from the stand-in model.\n\nIt can write **bold** text, a list:\n\n- first point\n- second point\n\nand a code block:\n\n```js\nconsole.log('hello from the stand-in');\n```\n\nThat is all.";

export interface FakeOptions {
  /** ms between words of an answer; 0 writes the whole answer at once (for screenshots) */
  wordMs?: number;
  modelState?: ModelState;
  /** start with no chats at all */
  empty?: boolean;
  /** a fixed "now", so screenshots and tests do not drift */
  now?: string;
}

interface Run {
  id: string;
  chatId: string;
  messageId: string;
  events: RunEvent[];
  listeners: Set<(e: RunEvent) => void>;
  done: boolean;
  timer: ReturnType<typeof setTimeout> | null;
}

export class FakeEngine implements EngineClient {
  private chats = new Map<string, Chat>();
  private runs = new Map<string, Run>();
  private n = 0;
  private settings: Settings = {
    modelAddress: "http://127.0.0.1:8080",
    hasModelKey: false,
    systemPrompt:
      "You are a careful assistant running on the owner's own computer. Answer plainly and briefly. If you are not sure, say so.",
    maxAnswerTokens: 1024,
  };
  private wordMs: number;
  private modelState: ModelState;
  private clock: number;

  constructor(options: FakeOptions = {}) {
    this.wordMs = options.wordMs ?? 30;
    this.modelState = options.modelState ?? "ready";
    this.clock = Date.parse(options.now ?? "2026-10-10T18:00:00.000Z");
    if (!options.empty) this.seed();
  }

  private id(prefix: string) {
    this.n += 1;
    return `${prefix}${this.n}`;
  }
  private now(offsetMin = 0) {
    return new Date(this.clock + offsetMin * 60000).toISOString();
  }
  private message(
    chatId: string,
    role: Message["role"],
    text: string,
    at: string,
    extra: Partial<Message> = {},
  ): Message {
    return {
      id: this.id("m"),
      chatId,
      role,
      text,
      status: "complete",
      createdAt: at,
      model: role === "assistant" ? "stand-in-model" : null,
      tokensPerSecond: role === "assistant" ? 41.5 : null,
      answerTokens: role === "assistant" ? text.split(/\s+/).length : null,
      error: null,
      runId: null,
      ...extra,
    };
  }
  private seed() {
    const add = (title: string, pinned: boolean, agoMin: number, turns: [string, string][]) => {
      const id = this.id("c");
      const at = this.now(-agoMin);
      const messages: Message[] = [];
      for (const [q, a] of turns) {
        messages.push(this.message(id, "user", q, at));
        messages.push(this.message(id, "assistant", a, at));
      }
      this.chats.set(id, { id, title, pinned, createdAt: at, updatedAt: at, messageCount: messages.length, messages });
    };
    add("Ending the lease early", true, 30, [
      [
        "Can I end my apartment lease early, and what would it cost me?",
        "Most leases allow it with written notice and a fee. I cannot see your lease, so check its early-termination clause for the notice period and the amount.",
      ],
      [
        "What should the notice say?",
        "Keep it short:\n\n1. Your name and the address\n2. The date you will leave\n3. A line saying this is notice under the early-termination clause\n\nSend it in writing and keep a copy.",
      ],
    ]);
    add("Packing list for a week away", false, 60 * 26, [
      [
        "Give me a packing list for a week in a cold city.",
        "- Warm coat\n- Two jumpers\n- Waterproof shoes\n- Gloves, hat, scarf\n- Chargers and an adapter",
      ],
    ]);
    add("Explain compound interest", false, 60 * 24 * 6, [
      [
        "Explain compound interest in two sentences.",
        "Compound interest is interest paid on both the money you put in and the interest it has already earned. Over time that makes the total grow faster and faster.",
      ],
    ]);
  }
  private summary(c: Chat, match: string | null = null): ChatSummary {
    const last = c.messages[c.messages.length - 1];
    return {
      id: c.id,
      title: c.title,
      pinned: c.pinned,
      createdAt: c.createdAt,
      updatedAt: c.updatedAt,
      messageCount: c.messages.length,
      preview: (last?.text ?? "").replace(/\s+/g, " ").slice(0, 120),
      match,
    };
  }
  private chat(id: string): Chat {
    const c = this.chats.get(id);
    if (!c) throw new EngineError(404, "not_found", "That chat does not exist any more.");
    return c;
  }
  private copy<T>(v: T): T {
    return structuredClone(v);
  }

  async health(): Promise<Health> {
    const ready = this.modelState === "ready";
    return {
      ok: true,
      engineVersion: "0.2.0-fake",
      model: {
        state: this.modelState,
        address: this.settings.modelAddress,
        name: ready ? "stand-in-model" : null,
        contextTokens: ready ? 8192 : null,
        detail: ready ? null : "Nothing answered at this address. Is llama-server running?",
        checkedAt: this.now(),
      },
    };
  }
  async getSettings() {
    return this.copy(this.settings);
  }
  async updateSettings(update: SettingsUpdate) {
    const { modelKey, ...rest } = update;
    this.settings = {
      ...this.settings,
      ...rest,
      hasModelKey: modelKey === undefined ? this.settings.hasModelKey : modelKey !== "",
    };
    return this.copy(this.settings);
  }
  async listChats(query?: string) {
    const q = query?.trim().toLowerCase();
    const all = [...this.chats.values()];
    const hits = q
      ? all.flatMap((c) => {
          const inTitle = c.title.toLowerCase().includes(q);
          const m = c.messages.find((x) => x.text.toLowerCase().includes(q));
          if (!inTitle && !m) return [];
          return [this.summary(c, m ? m.text.replace(/\s+/g, " ").slice(0, 140) : null)];
        })
      : all.map((c) => this.summary(c));
    return hits.sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.updatedAt.localeCompare(a.updatedAt));
  }
  async createChat(title?: string) {
    const id = this.id("c");
    const at = this.now();
    const c: Chat = {
      id,
      title: title?.trim() || "New chat",
      pinned: false,
      createdAt: at,
      updatedAt: at,
      messageCount: 0,
      messages: [],
    };
    this.chats.set(id, c);
    return this.copy(c);
  }
  async getChat(id: string) {
    return this.copy(this.chat(id));
  }
  async updateChat(id: string, update: ChatUpdate) {
    const c = this.chat(id);
    if (update.title !== undefined) c.title = update.title.trim() || c.title;
    if (update.pinned !== undefined) c.pinned = update.pinned;
    return this.copy(c);
  }
  async deleteChat(id: string) {
    this.chat(id);
    this.chats.delete(id);
  }
  async exportChat(id: string, format: "markdown" | "json"): Promise<ExportedChat> {
    const c = this.chat(id);
    if (format === "json") {
      return {
        filename: `${c.title}.json`,
        mime: "application/json",
        text: JSON.stringify({ format: "gx10-council.chat", version: 1, chat: c }, null, 2),
      };
    }
    const body = c.messages.map((m) => `## ${m.role === "user" ? "You" : "Answer"}\n\n${m.text}`).join("\n\n");
    return { filename: `${c.title}.md`, mime: "text/markdown", text: `# ${c.title}\n\n${body}\n` };
  }

  private startRun(c: Chat, assistant: Message): Run {
    const run: Run = {
      id: this.id("r"),
      chatId: c.id,
      messageId: assistant.id,
      events: [],
      listeners: new Set(),
      done: false,
      timer: null,
    };
    assistant.runId = run.id;
    this.runs.set(run.id, run);
    let seq = 0;
    const emit = (e: RunEvent) => {
      run.events.push(e);
      for (const l of run.listeners) l(e);
    };
    const finish = (status: Message["status"], error: string | null = null) => {
      assistant.status = status;
      assistant.error = error;
      assistant.runId = null;
      assistant.tokensPerSecond = 41.5;
      assistant.answerTokens = assistant.text.split(/\s+/).filter(Boolean).length;
      c.updatedAt = this.now();
      run.done = true;
      seq += 1;
      emit({ type: status === "failed" ? "run.error" : "run.done", runId: run.id, seq, message: this.copy(assistant) });
    };
    seq += 1;
    emit({ type: "run.started", runId: run.id, messageId: assistant.id, seq });
    if (this.modelState !== "ready") {
      finish("failed", "The model server did not answer. Check that llama-server is running, then try again.");
      return run;
    }
    const words = ANSWER.match(/\S+\s*/g) ?? [];
    if (this.wordMs === 0) {
      assistant.text = ANSWER;
      seq += 1;
      emit({ type: "delta", runId: run.id, seq, text: ANSWER });
      finish("complete");
      return run;
    }
    let i = 0;
    const step = () => {
      if (run.done) return;
      const word = words[i];
      if (word === undefined) {
        finish("complete");
        return;
      }
      i += 1;
      assistant.text += word;
      seq += 1;
      emit({ type: "delta", runId: run.id, seq, text: word });
      run.timer = setTimeout(step, this.wordMs);
    };
    run.timer = setTimeout(step, this.wordMs);
    (run as Run & { finish?: typeof finish }).finish = finish;
    return run;
  }

  async sendMessage(chatId: string, text: string): Promise<RunStarted> {
    const c = this.chat(chatId);
    if (c.messages.some((m) => m.status === "writing"))
      throw new EngineError(409, "run_open", "The model is still writing. Stop it first, or wait.");
    const at = this.now();
    const user = this.message(chatId, "user", text, at);
    const assistant = this.message(chatId, "assistant", "", at, {
      status: "writing",
      tokensPerSecond: null,
      answerTokens: null,
    });
    c.messages.push(user, assistant);
    if (c.title === "New chat") c.title = text.replace(/\s+/g, " ").slice(0, 60);
    c.messageCount = c.messages.length;
    c.updatedAt = at;
    const run = this.startRun(c, assistant);
    return {
      runId: run.id,
      userMessage: this.copy(user),
      assistantMessage: this.copy(assistant),
      chat: this.summary(c),
    };
  }
  async regenerate(chatId: string): Promise<RunStarted> {
    const c = this.chat(chatId);
    const last = c.messages[c.messages.length - 1];
    if (!last || last.role !== "assistant")
      throw new EngineError(400, "bad_request", "There is no answer to write again.");
    if (last.status === "writing")
      throw new EngineError(409, "run_open", "The model is still writing. Stop it first, or wait.");
    c.messages.pop();
    const assistant = this.message(chatId, "assistant", "", this.now(), {
      status: "writing",
      tokensPerSecond: null,
      answerTokens: null,
    });
    c.messages.push(assistant);
    const run = this.startRun(c, assistant);
    return { runId: run.id, userMessage: null, assistantMessage: this.copy(assistant), chat: this.summary(c) };
  }
  async stopRun(runId: string) {
    const run = this.runs.get(runId) as (Run & { finish?: (s: Message["status"]) => void }) | undefined;
    if (!run || run.done) return;
    if (run.timer) clearTimeout(run.timer);
    run.finish?.("stopped");
  }
  async streamRun(runId: string, onEvent: (event: RunEvent) => void, signal?: AbortSignal) {
    const run = this.runs.get(runId);
    if (!run) throw new EngineError(404, "not_found", "That answer is no longer being written.");
    for (const e of [...run.events]) onEvent(e);
    if (run.done) return;
    await new Promise<void>((resolve) => {
      const listener = (e: RunEvent) => {
        onEvent(e);
        if (e.type === "run.done" || e.type === "run.error") stop();
      };
      const stop = () => {
        run.listeners.delete(listener);
        signal?.removeEventListener("abort", stop);
        resolve();
      };
      run.listeners.add(listener);
      signal?.addEventListener("abort", stop);
    });
  }
}
