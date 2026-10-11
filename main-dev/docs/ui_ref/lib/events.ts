// The debate as a numbered list of events. The Phase 1 mocks read a recorded list;
// the Phase 4 engine will emit the same shapes, and Phase 7's replay will reuse them.
// Three things are deliberately NOT assumed here, because the engine has not decided them:
//  - who is speaking is whichever seats have an open turn (none, one or many);
//  - a summary names no author (see `source`);
//  - agreement arrives only as a tally of groups, with no stated matching method.

export type Ms = number;
export type Id = string;

export interface Seat {
  id: Id;
  /** 0-based, left to right along the table */
  index: number;
  /** shown in the head; at most 7 characters */
  shortName: string;
  modelName: string;
  role?: string;
}

export interface FileRef {
  id: Id;
  name: string;
  pages?: number;
  from: "attachment" | "library";
}

export type Citation =
  | { kind: "file"; fileId: Id; page?: number; quote?: string }
  // reserved for Phase 6 (council.md entries such as L7)
  | { kind: "council"; entryId: string };

export type Phase = "spooling" | "research" | "debate" | "vote" | "writing" | "released";
export type TurnKind = "research" | "position" | "reply" | "answer" | "dissent";
export type SeatStatus = "loading" | "ready" | "failed" | "dropped";

export interface TallyGroup {
  answerId: Id;
  statement: string;
  seatIds: Id[];
}

interface Base {
  v: 1;
  seq: number;
  debateId: Id;
  /** ms since the question was sent */
  at: Ms;
  /** debate clock: 0 until reading starts, frozen while paused */
  clock: Ms;
}

export type DebateEventBody =
  | { type: "debate.created"; question: string; files: FileRef[]; seats: Seat[]; limitMs: Ms }
  | { type: "seat.status"; seatId: Id; status: SeatStatus; reason?: string }
  | { type: "phase.changed"; phase: Phase }
  | { type: "clock.paused" }
  | { type: "clock.resumed" }
  | { type: "round.started"; round: number }
  | { type: "turn.started"; turnId: Id; seatId: Id; round: number; kind: TurnKind; to: "all" | Id[] }
  | { type: "turn.delta"; turnId: Id; text: string }
  | { type: "turn.ended"; turnId: Id; text: string; citations: Citation[]; error?: string }
  | {
      type: "summary.posted";
      summaryId: Id;
      seatId: Id;
      turnId?: Id;
      text: string;
      source: "summarizer" | "self" | "engine";
    }
  | {
      type: "tally.posted";
      round: number;
      basis: "round-vote" | "closing" | "live";
      groups: TallyGroup[];
      leading: Id;
      agree: number;
      seats: number;
      needed: number;
      reached: boolean;
    }
  | { type: "note.queued"; noteId: Id; text: string; round: number }
  | { type: "note.delivered"; noteId: Id; text: string; round: number }
  | {
      type: "answer.released";
      outcome: "agreed" | "no-consensus" | "stopped";
      turnId: Id;
      tallyRound: number;
      rounds: number;
      elapsedMs: Ms;
      dissentTurnIds: Id[];
    };

export type DebateEvent = Base & DebateEventBody;

// ---- what a screen shows at one moment (derived by viewAt) ----

export interface BubbleView {
  summaryId: Id;
  text: string;
  /** 0 to 1 */
  opacity: number;
  /** the summary this one is replacing, during its 250 ms fade-in (crossfade in place) */
  prev?: { summaryId: Id; text: string; opacity: number };
}

export interface SeatView extends Seat {
  status: SeatStatus;
  activity: "idle" | "researching" | "speaking" | "writing";
  /** vote mark; cleared when the next round starts */
  mark: "agrees" | "differs" | null;
  bubble: BubbleView | null;
}

export interface TurnView {
  turnId: Id;
  seatId: Id;
  round: number;
  kind: TurnKind;
  to: "all" | Id[];
  /** debate clock when the turn started */
  clock: Ms;
  /** text so far */
  text: string;
  done: boolean;
  citations: Citation[];
}

export interface TallyView {
  round: number;
  basis: "round-vote" | "closing" | "live";
  groups: TallyGroup[];
  leading: Id;
  agree: number;
  seats: number;
  needed: number;
  reached: boolean;
}

export interface NoteView {
  noteId: Id;
  text: string;
  state: "queued" | "delivered";
  round: number;
}

export interface AnswerView {
  outcome: "agreed" | "no-consensus" | "stopped";
  agree: number;
  seats: number;
  rounds: number;
  elapsedMs: Ms;
  turnId: Id;
  dissentTurnIds: Id[];
}

export interface DebateView {
  phase: "idle" | Phase;
  paused: boolean;
  round: number;
  clock: Ms;
  leftMs: Ms;
  limitMs: Ms;
  question: string;
  files: FileRef[];
  seats: SeatView[];
  /** seat ids with an open turn: none, one or many */
  speaking: Id[];
  tally: TallyView | null;
  turns: TurnView[];
  notes: NoteView[];
  answer?: AnswerView;
}

/** Seats that must back the same answer: 80%, rounded up. 3->3, 4->4, 5->4, 6->5, 7->6. */
export function needed(seats: number): number {
  return Math.ceil((4 * seats) / 5);
}
