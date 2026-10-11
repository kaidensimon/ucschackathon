// CONTRACT (tests in viewAt.test.ts and fixtures/story.test.ts are frozen). Built by the timeline builder.
import type {
  AnswerView,
  BubbleView,
  DebateEvent,
  DebateView,
  Id,
  Ms,
  NoteView,
  Phase,
  SeatStatus,
  SeatView,
  TallyView,
  TurnView,
} from "../events";
import { BUBBLE, bubbleOpacity } from "./bubble";

type Created = Extract<DebateEvent, { type: "debate.created" }>;
type Released = Extract<DebateEvent, { type: "answer.released" }>;
type Mark = "agrees" | "differs";

/** One bubble line, with the debate clock at which it was posted. */
interface Summary {
  summaryId: Id;
  text: string;
  clock: Ms;
}

/** The debate clock only moves in these phases: not while seating, not once the answer is being written. */
const CLOCK_RUNS_IN: readonly string[] = ["research", "debate", "vote"] satisfies Phase[];

const IDLE: DebateView = {
  phase: "idle",
  paused: false,
  round: 0,
  clock: 0,
  leftMs: 0,
  limitMs: 0,
  question: "",
  files: [],
  seats: [],
  speaking: [],
  tally: null,
  turns: [],
  notes: [],
};

/**
 * What the screen shows `at` ms after the question was sent. Pure: no clock, no randomness,
 * same answer every time. Every mock scene is "the debate at time T" through this one function.
 */
export function viewAt(events: DebateEvent[], at: Ms, opts?: { reducedMotion?: boolean }): DebateView {
  const reducedMotion = opts?.reducedMotion === true;

  let created: Created | null = null;
  let released: Released | null = null;
  let phase: Phase | "idle" = "idle";
  let paused = false;
  let round = 0;
  let tally: TallyView | null = null;
  // true once a vote has reached agreement: the clock stops there for good
  let agreed = false;
  // clock and real time of the last event used; the view clock is worked out from these
  let lastClock: Ms = 0;
  let lastAt: Ms = 0;

  const status = new Map<Id, SeatStatus>();
  const marks = new Map<Id, Mark>();
  const turns: TurnView[] = [];
  const turnById = new Map<Id, TurnView>();
  const notes: NoteView[] = [];
  const tallies: TallyView[] = [];
  // per seat: its newest bubble line and the one before it
  const summaries = new Map<Id, { newest: Summary; earlier: Summary | null }>();

  for (const e of events) {
    if (e.at > at) continue; // has not happened yet
    lastClock = e.clock;
    lastAt = e.at;

    switch (e.type) {
      case "debate.created":
        created = e;
        break;
      case "seat.status":
        status.set(e.seatId, e.status);
        break;
      case "phase.changed":
        phase = e.phase;
        break;
      case "clock.paused":
        paused = true;
        break;
      case "clock.resumed":
        paused = false;
        break;
      case "round.started":
        round = e.round;
        marks.clear(); // vote marks last only until the next round starts
        break;
      case "turn.started": {
        const turn: TurnView = {
          turnId: e.turnId,
          seatId: e.seatId,
          round: e.round,
          kind: e.kind,
          to: e.to,
          clock: e.clock,
          text: "",
          done: false,
          citations: [],
        };
        turns.push(turn);
        turnById.set(e.turnId, turn);
        break;
      }
      case "turn.delta": {
        const turn = turnById.get(e.turnId);
        // a late piece never changes a turn that has already ended
        if (turn && !turn.done) turn.text += e.text;
        break;
      }
      case "turn.ended": {
        const turn = turnById.get(e.turnId);
        if (turn) {
          turn.text = e.text;
          turn.done = true;
          turn.citations = e.citations;
        }
        break;
      }
      case "summary.posted": {
        const before = summaries.get(e.seatId);
        summaries.set(e.seatId, {
          newest: { summaryId: e.summaryId, text: e.text, clock: e.clock },
          earlier: before ? before.newest : null,
        });
        break;
      }
      case "tally.posted": {
        tally = {
          round: e.round,
          basis: e.basis,
          groups: e.groups,
          leading: e.leading,
          agree: e.agree,
          seats: e.seats,
          needed: e.needed,
          reached: e.reached,
        };
        tallies.push(tally);
        if (e.reached) agreed = true;
        marks.clear();
        for (const group of e.groups) {
          const mark: Mark = group.answerId === e.leading ? "agrees" : "differs";
          for (const seatId of group.seatIds) marks.set(seatId, mark);
        }
        break;
      }
      case "note.queued":
        notes.push({ noteId: e.noteId, text: e.text, state: "queued", round: e.round });
        break;
      case "note.delivered": {
        const note = notes.find((n) => n.noteId === e.noteId);
        if (note) {
          note.state = "delivered";
          note.round = e.round;
        } else {
          notes.push({ noteId: e.noteId, text: e.text, state: "delivered", round: e.round });
        }
        break;
      }
      case "answer.released":
        released = e;
        break;
    }
  }

  if (!created) return { ...IDLE, files: [], seats: [], speaking: [], turns: [], notes: [] };

  // The debate clock: the last event's clock, plus the real time since then while the clock is running.
  const limitMs = created.limitMs;
  const running = CLOCK_RUNS_IN.includes(phase) && !paused && !agreed;
  const clock = running ? Math.min(limitMs, lastClock + (at - lastAt)) : lastClock;

  // Open turns decide what each seat is doing. A seat's latest open turn wins.
  const activity = new Map<Id, SeatView["activity"]>();
  const talking = new Set<Id>();
  for (const turn of turns) {
    if (turn.done) continue;
    if (turn.kind === "research") activity.set(turn.seatId, "researching");
    else if (turn.kind === "answer" || turn.kind === "dissent") activity.set(turn.seatId, "writing");
    else {
      activity.set(turn.seatId, "speaking");
      talking.add(turn.seatId);
    }
  }

  const seats: SeatView[] = [...created.seats]
    .sort((a, b) => a.index - b.index)
    .map((seat) => ({
      ...seat,
      status: status.get(seat.id) ?? "loading",
      activity: activity.get(seat.id) ?? "idle",
      mark: marks.get(seat.id) ?? null,
      bubble: bubbleFor(summaries.get(seat.id), clock, reducedMotion),
    }));

  const view: DebateView = {
    phase,
    paused,
    round,
    clock,
    leftMs: Math.max(0, limitMs - clock),
    limitMs,
    question: created.question,
    files: created.files,
    seats,
    speaking: seats.filter((s) => talking.has(s.id)).map((s) => s.id),
    tally,
    turns,
    notes,
  };
  if (released) view.answer = answerFor(released, tallies, seats.length);
  return view;
}

/** The bubble over one head at debate clock `clock`, or null when nothing shows. */
function bubbleFor(
  lines: { newest: Summary; earlier: Summary | null } | undefined,
  clock: Ms,
  reducedMotion: boolean,
): BubbleView | null {
  if (!lines) return null;
  const { newest, earlier } = lines;
  const age = clock - newest.clock;
  const opacity = bubbleOpacity(age, { reducedMotion });
  const bubble: BubbleView = { summaryId: newest.summaryId, text: newest.text, opacity };

  // Crossfade in place: while the new line fades in, the line it replaces fades out under it.
  if (earlier && !reducedMotion && age >= 0 && age < BUBBLE.fadeInMs) {
    const prevOpacity = bubbleOpacity(clock - earlier.clock) * (1 - opacity);
    // Kept even at the very first instant (new line at 0), so the old line does not blink off.
    if (prevOpacity > 0) {
      return { ...bubble, prev: { summaryId: earlier.summaryId, text: earlier.text, opacity: prevOpacity } };
    }
  }
  return opacity > 0 ? bubble : null;
}

/** The released answer. Its agreement count comes from the vote the release points at. */
function answerFor(released: Released, tallies: TallyView[], seatCount: number): AnswerView {
  // the latest tally of that round, in case a round was counted more than once
  const counted = tallies.findLast((t) => t.round === released.tallyRound);
  return {
    outcome: released.outcome,
    // no such vote in the events (stopped before any vote): nobody is counted as agreeing
    agree: counted ? counted.agree : 0,
    seats: counted ? counted.seats : seatCount,
    rounds: released.rounds,
    elapsedMs: released.elapsedMs,
    turnId: released.turnId,
    dissentTurnIds: released.dissentTurnIds,
  };
}
