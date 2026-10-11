// The debate of one run, as it happens. Only used with the real (HTTP) engine: the events come
// from GET /ui/runs/{runId}/debate and go through the same viewAt() the recorded samples use.
// If the stream cannot be opened the list stays empty and the screen shows what it always did.
import { useEffect, useMemo, useState } from "react";
import type { DebateEvent, DebateView, Id, Ms, SeatView } from "../lib/events";
import { BUBBLE, type LiveBubble } from "../lib/timeline/bubble";
import { viewAt } from "../lib/timeline/viewAt";
import { engineUrl, streamDebate } from "./http";

const FLUSH_MS = 100;
/** how often the live clock moves between events, once no note is fading in */
const TICK_MS = 250;
export const THINKING = "thinking...";

/** "truth 0.94": the lie-detector reading, as the small word on a note */
export function truthWords(score: number): string {
  return `truth ${score.toFixed(2)}`;
}

/** Where the backend is. Same rule as http.ts. */
export function engineBaseUrl(): string {
  return engineUrl();
}

/** What the backend sends: the UI's events plus a few of its own (lie.posted, seat.thinking, ...). */
export interface WireEvent {
  type: string;
  seq: number;
  at: number;
  clock: number;
  [key: string]: unknown;
}

const KNOWN: ReadonlySet<string> = new Set([
  "debate.created",
  "seat.status",
  "phase.changed",
  "clock.paused",
  "clock.resumed",
  "round.started",
  "turn.started",
  "turn.delta",
  "turn.ended",
  "summary.posted",
  "tally.posted",
  "note.queued",
  "note.delivered",
  "answer.released",
]);

export interface LiveDebate {
  /** every event so far, in seq order (unknown types included) */
  events: WireEvent[];
  /** the stream is open and the answer has not been released */
  live: boolean;
}

export function useLiveDebate(runId: string | null): LiveDebate {
  const [state, setState] = useState<{ runId: string; events: WireEvent[]; open: boolean } | null>(null);

  useEffect(() => {
    if (!runId) {
      setState(null);
      return;
    }
    const leave = new AbortController();
    let all: WireEvent[] = [];
    let waiting: WireEvent[] = [];
    let open = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    setState({ runId, events: all, open });

    const flush = () => {
      timer = null;
      if (leave.signal.aborted) return;
      if (waiting.length > 0) {
        const lastSeq = all.at(-1)?.seq ?? -1;
        const inOrder = waiting.every((e, i) => e.seq > (i === 0 ? lastSeq : (waiting[i - 1]?.seq ?? lastSeq)));
        all = [...all, ...waiting];
        if (!inOrder) all.sort((a, b) => a.seq - b.seq);
        waiting = [];
      }
      setState({ runId, events: all, open });
    };
    const soon = () => {
      if (timer === null) timer = setTimeout(flush, FLUSH_MS);
    };
    const onEvent = (event: DebateEvent) => {
      if (leave.signal.aborted) return;
      waiting.push(event as unknown as WireEvent);
      soon();
    };
    const closed = () => {
      open = false;
      soon();
    };
    streamDebate(engineBaseUrl(), runId, onEvent, leave.signal).then(closed, closed);

    return () => {
      leave.abort();
      if (timer !== null) clearTimeout(timer);
    };
  }, [runId]);

  return useMemo(() => {
    if (!state || state.runId !== runId) return { events: [], live: false };
    const released = state.events.some((e) => e.type === "answer.released");
    return { events: state.events, live: state.open && !released };
  }, [state, runId]);
}

/**
 * Real time (ms since the question) for a live view. The backend's clock only moves when an
 * event arrives, so between events it is carried on by this machine's clock: the newest event's
 * time plus the time since it got here. Every frame while a new note fades in, then four times a
 * second. A debate that is over stands a moment after its last event, with every note fully in.
 */
export function useLiveClock(events: WireEvent[], live: boolean): Ms {
  const last = events.at(-1);
  const seq = last ? last.seq : -1;
  const lastAt = last ? last.at : 0;
  const noteAt = useMemo(() => events.findLast((e) => e.type === "summary.posted")?.at ?? null, [events]);
  const [since, setSince] = useState<{ seq: number; ms: number }>({ seq: -1, ms: 0 });

  useEffect(() => {
    if (!live || seq < 0) return;
    const start = performance.now();
    // a note is fading in until this long after the newest event
    const fading = noteAt === null ? 0 : noteAt + BUBBLE.fadeInMs - lastAt;
    const frames = typeof requestAnimationFrame === "function";
    let frame: number | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const step = () => {
      frame = null;
      timer = null;
      const ms = performance.now() - start;
      setSince({ seq, ms });
      if (frames && ms < fading) frame = requestAnimationFrame(step);
      else timer = setTimeout(step, TICK_MS);
    };
    if (frames && fading > 0) frame = requestAnimationFrame(step);
    else timer = setTimeout(step, TICK_MS);
    return () => {
      if (frame !== null) cancelAnimationFrame(frame);
      if (timer !== null) clearTimeout(timer);
    };
  }, [live, seq, lastAt, noteAt]);

  if (!live) return lastAt + BUBBLE.fadeInMs;
  return lastAt + (since.seq === seq ? since.ms : 0);
}

/**
 * A live debate at real time `at` (left out: a moment after its newest event), through viewAt().
 * Null until the debate has been created. In the table every seat keeps its newest note until
 * its next one. Events viewAt does not know are kept out of it; two of them are shown on top:
 *  - a seat that is thinking shows "thinking..." (alone before its first note; after that the
 *    old note stays, weaker, with "thinking..." as a small word on it, until the new note);
 *  - a lie-detector reading is the small word on the note of the message it is about
 *    ("truth 0.94"), and is added under that message in the chat.
 */
export function liveViewOf(events: WireEvent[], at?: Ms): DebateView | null {
  const last = events.at(-1);
  if (!last) return null;
  const now = at ?? last.at + BUBBLE.fadeInMs;
  const known = events.filter((e) => KNOWN.has(e.type)) as unknown as DebateEvent[];
  const view = viewAt(known, now, { live: true });
  if (view.phase === "idle") return null;

  // seat -> when it began thinking; message -> its reading; note -> the message it is about
  const thinking = new Map<Id, Ms>();
  const lies = new Map<Id, { score: number; level: string }>();
  const noteTurn = new Map<Id, Id>();
  for (const e of events) {
    if (e.at > now) break;
    if (e.type === "seat.thinking" && typeof e.seatId === "string") {
      if (e.on === true) thinking.set(e.seatId, e.at);
      else thinking.delete(e.seatId);
    } else if (e.type === "lie.posted" && typeof e.turnId === "string" && typeof e.score === "number") {
      lies.set(e.turnId, { score: e.score, level: typeof e.level === "string" ? e.level : "ok" });
    } else if (e.type === "summary.posted" && typeof e.summaryId === "string" && typeof e.turnId === "string") {
      noteTurn.set(e.summaryId, e.turnId);
    }
  }
  if (view.answer) thinking.clear();
  if (thinking.size === 0 && lies.size === 0) return view;

  const bubbleOf = (seat: SeatView): LiveBubble | null => {
    const note: LiveBubble | null = seat.bubble;
    const since = thinking.get(seat.id);
    if (since !== undefined) {
      if (!note) return { summaryId: `thinking-${seat.id}`, text: THINKING, opacity: 1, newer: since };
      return { ...note, dim: true, tag: { text: THINKING } };
    }
    const reading = note ? lies.get(noteTurn.get(note.summaryId) ?? "") : undefined;
    if (!note || !reading) return note;
    const text = truthWords(reading.score);
    return { ...note, tag: reading.level === "flag" ? { text, flag: true } : { text } };
  };

  return {
    ...view,
    seats: view.seats.map((s) => {
      const bubble = bubbleOf(s);
      return bubble === s.bubble ? s : { ...s, bubble };
    }),
    turns: view.turns.map((t) => {
      const reading = lies.get(t.turnId);
      if (!reading || !t.done) return t;
      return { ...t, text: `${t.text}

[Lie detector: ${reading.level} (${reading.score.toFixed(2)})]` };
    }),
  };
}
