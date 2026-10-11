// Turns a short, readable script of a debate into the full numbered event list.
// Sample data only: every question, file and answer here is invented.
import {
  type Citation,
  type DebateEvent,
  type DebateEventBody,
  type FileRef,
  type Ms,
  needed,
  type Seat,
} from "../lib/events";

/** minutes and seconds on the debate clock, as ms */
export const c = (m: number, s = 0): Ms => Math.round((m * 60 + s) * 1000);

export interface TurnSpec {
  seat: string;
  round: number;
  kind: "research" | "position" | "reply" | "answer" | "dissent";
  to?: "all" | string[];
  /** debate clock */
  start: Ms;
  end: Ms;
  /** for turns written after the clock has stopped: ms added to real time, clock stays at `start` */
  afterStop?: { start: Ms; end: Ms };
  text: string;
  cites?: { file: string; page: number; quote?: string }[];
  /** bubble lines: debate clock and text (55 characters or fewer) */
  says?: { at: Ms; text: string }[];
  /** leave the turn open (never ends) - used only by the "several talking" stress fixture */
  open?: boolean;
}

export interface TallySpec {
  clock: Ms;
  round: number;
  basis?: "round-vote" | "closing" | "live";
  groups: { answerId: string; statement: string; seats: string[] }[];
}

export interface Script {
  id: string;
  question: string;
  files: FileRef[];
  seats: { shortName: string; modelName: string }[];
  limitMs: Ms;
  /** real ms after sending when each model is ready; the clock starts when the last one is */
  readyAt: Record<string, Ms>;
  failed?: { seat: string; at: Ms; reason: string };
  pauses?: { clock: Ms; forMs: Ms }[];
  phases: { clock: Ms; phase: "research" | "debate" | "vote" | "writing" | "released"; afterStop?: Ms }[];
  rounds: { clock: Ms; round: number }[];
  turns: TurnSpec[];
  tallies: TallySpec[];
  notes?: { text: string; queued: Ms; queuedRound: number; delivered?: Ms }[];
  release?: {
    clock: Ms;
    afterStop: Ms;
    outcome: "agreed" | "no-consensus" | "stopped";
    tallyRound: number;
    rounds: number;
    answerSeat: string;
    dissentSeats: string[];
  };
}

export interface Fixture {
  id: string;
  events: DebateEvent[];
  seats: Seat[];
  /** real time (ms since sending) for a moment on the debate clock */
  at: (clock: Ms) => Ms;
  /** real time of the last event */
  endAt: Ms;
  clockStartAt: Ms;
}

export function build(script: Script): Fixture {
  const seats: Seat[] = script.seats.map((s, index) => ({ id: `s${index + 1}`, index, ...s }));
  const seatId = (name: string): string => {
    const seat = seats.find((s) => s.shortName === name);
    if (!seat) throw new Error(`${script.id}: no seat named ${name}`);
    return seat.id;
  };
  const fileId = (name: string): string => {
    const f = script.files.find((x) => x.name === name);
    if (!f) throw new Error(`${script.id}: no file named ${name}`);
    return f.id;
  };
  const live = seats.filter((s) => s.shortName !== script.failed?.seat);
  const clockStartAt = Math.max(...live.map((s) => script.readyAt[s.shortName] ?? 0));
  const pauses = script.pauses ?? [];
  const at = (clock: Ms): Ms =>
    clockStartAt + clock + pauses.filter((p) => p.clock < clock).reduce((sum, p) => sum + p.forMs, 0);

  const raw: { at: Ms; clock: Ms; body: DebateEventBody }[] = [];
  const push = (atMs: Ms, clock: Ms, body: DebateEventBody) => raw.push({ at: atMs, clock, body });

  push(0, 0, {
    type: "debate.created",
    question: script.question,
    files: script.files,
    seats,
    limitMs: script.limitMs,
  });
  push(0, 0, { type: "phase.changed", phase: "spooling" });
  for (const s of seats) push(0, 0, { type: "seat.status", seatId: s.id, status: "loading" });
  for (const s of seats) {
    if (script.failed?.seat === s.shortName) {
      push(script.failed.at, 0, { type: "seat.status", seatId: s.id, status: "failed", reason: script.failed.reason });
    } else {
      push(script.readyAt[s.shortName] ?? 0, 0, { type: "seat.status", seatId: s.id, status: "ready" });
    }
  }
  for (const p of script.phases) {
    push(at(p.clock) + (p.afterStop ?? 0), p.clock, { type: "phase.changed", phase: p.phase });
  }
  for (const r of script.rounds) push(at(r.clock), r.clock, { type: "round.started", round: r.round });
  for (const p of pauses) {
    push(at(p.clock), p.clock, { type: "clock.paused" });
    push(at(p.clock) + p.forMs, p.clock, { type: "clock.resumed" });
  }

  let turnNo = 0;
  let sayNo = 0;
  const turnIds = new Map<TurnSpec, string>();
  for (const t of script.turns) {
    const turnId = `t${++turnNo}`;
    turnIds.set(t, turnId);
    const sid = seatId(t.seat);
    const to = !t.to || t.to === "all" ? ("all" as const) : t.to.map(seatId);
    const startAt = t.afterStop ? at(t.start) + t.afterStop.start : at(t.start);
    const endAt = t.afterStop ? at(t.start) + t.afterStop.end : at(t.end);
    const clockAt = (realAt: Ms): Ms => {
      if (t.afterStop) return t.start;
      // invert `at`: real time back to the debate clock, standing still inside a pause
      let clock = realAt - clockStartAt;
      for (const p of pauses) {
        const pauseStart = at(p.clock);
        if (realAt >= pauseStart + p.forMs) clock -= p.forMs;
        else if (realAt > pauseStart) clock -= realAt - pauseStart;
      }
      return clock;
    };
    push(startAt, t.start, { type: "turn.started", turnId, seatId: sid, round: t.round, kind: t.kind, to });
    // the text arrives a few words at a time
    const words = t.text.split(" ");
    const steps = Math.max(1, Math.min(words.length, Math.floor((endAt - startAt) / 400)));
    const per = Math.ceil(words.length / steps);
    for (let i = 0; i < steps; i++) {
      const piece = words.slice(i * per, (i + 1) * per).join(" ");
      if (!piece) continue;
      const realAt = Math.round(startAt + ((i + 1) * (endAt - startAt)) / (steps + 1));
      // a pause in the middle of a turn holds the words back until the debate resumes
      const inPause = pauses.find((p) => realAt > at(p.clock) && realAt < at(p.clock) + p.forMs && !t.afterStop);
      const when = inPause ? at(inPause.clock) + inPause.forMs : realAt;
      push(when, clockAt(when), { type: "turn.delta", turnId, text: (i === 0 ? "" : " ") + piece });
    }
    if (!t.open) {
      const citations: Citation[] = (t.cites ?? []).map((x) => ({
        kind: "file",
        fileId: fileId(x.file),
        page: x.page,
        ...(x.quote ? { quote: x.quote } : {}),
      }));
      push(endAt, t.afterStop ? t.start : t.end, { type: "turn.ended", turnId, text: t.text, citations });
    }
    for (const say of t.says ?? []) {
      push(at(say.at), say.at, {
        type: "summary.posted",
        summaryId: `b${++sayNo}`,
        seatId: sid,
        turnId,
        text: say.text,
        source: t.kind === "research" ? "engine" : "summarizer",
      });
    }
  }

  for (const t of script.tallies) {
    const groups = t.groups.map((g) => ({
      answerId: g.answerId,
      statement: g.statement,
      seatIds: g.seats.map(seatId),
    }));
    const leading = [...groups].sort((a, b) => b.seatIds.length - a.seatIds.length)[0];
    if (!leading) throw new Error(`${script.id}: tally with no groups`);
    const total = groups.reduce((n, g) => n + g.seatIds.length, 0);
    push(at(t.clock), t.clock, {
      type: "tally.posted",
      round: t.round,
      basis: t.basis ?? "round-vote",
      groups,
      leading: leading.answerId,
      agree: leading.seatIds.length,
      seats: total,
      needed: needed(total),
      reached: leading.seatIds.length >= needed(total),
    });
  }

  let noteNo = 0;
  for (const n of script.notes ?? []) {
    const noteId = `n${++noteNo}`;
    push(at(n.queued), n.queued, { type: "note.queued", noteId, text: n.text, round: n.queuedRound });
    if (n.delivered !== undefined) {
      push(at(n.delivered), n.delivered, { type: "note.delivered", noteId, text: n.text, round: n.queuedRound + 1 });
    }
  }

  if (script.release) {
    const r = script.release;
    const answer = script.turns.find((t) => t.kind === "answer" && t.seat === r.answerSeat);
    if (!answer) throw new Error(`${script.id}: release without an answer turn`);
    const dissents = script.turns.filter((t) => t.kind === "dissent" && r.dissentSeats.includes(t.seat));
    push(at(r.clock) + r.afterStop, r.clock, {
      type: "answer.released",
      outcome: r.outcome,
      turnId: turnIds.get(answer) ?? "",
      tallyRound: r.tallyRound,
      rounds: r.rounds,
      elapsedMs: r.clock,
      dissentTurnIds: dissents.map((t) => turnIds.get(t) ?? ""),
    });
  }

  // order by real time; events at the same instant keep the order they were written in
  const ordered = raw.map((e, i) => ({ ...e, i })).sort((a, b) => a.at - b.at || a.i - b.i);
  const events: DebateEvent[] = ordered.map((e, i) => ({
    v: 1,
    seq: i + 1,
    debateId: script.id,
    at: e.at,
    clock: e.clock,
    ...e.body,
  }));
  const endAt = events.length ? (events[events.length - 1]?.at ?? 0) : 0;
  return { id: script.id, events, seats, at, endAt, clockStartAt };
}
