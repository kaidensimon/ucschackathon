// What Chat View shows, worked out from `view` alone: the layout, the bands of messages
// (reading, one per round, the answer) and the words. Pure, so the tests can read it.
import { type Citation, type DebateView, type FileRef, type NoteView, needed, type TurnView } from "../../lib/events";
import { minSec, ofSeats } from "../shared/words";

export type Layout = "thread" | "columns";

/** A column is drawn only when every seat gets this many px. */
export const COLUMN_MIN = 200;

export function layoutFor(width: number, seats: number): Layout {
  return seats > 0 && width / seats >= COLUMN_MIN ? "columns" : "thread";
}

/** A stretch of the debate: the reading before round 1, one round, or the closing answer. */
export interface Band {
  key: string;
  /** the heading that opens the band; the reading band has none */
  label: string | null;
  /** the round this band is, when it is a round */
  round: number | null;
  /** the owner's notes that reached the council at the start of this round */
  notes: NoteView[];
  turns: TurnView[];
  /** the result of this round's vote, when `view` still knows it */
  vote: { text: string; reached: boolean } | null;
}

/**
 * The messages in time order, cut into bands. `view` holds only the latest tally, so only
 * that round can show its result; every round still opens with its own heading.
 */
export function bandsOf(view: DebateView): Band[] {
  const band = (key: string, label: string | null, round: number | null): Band => ({
    key,
    label,
    round,
    notes: [],
    turns: [],
    vote: null,
  });
  const reading = band("reading", null, null);
  const answer = band("answer", "Answer", null);
  const rounds = new Map<number, Band>();
  const roundBand = (n: number): Band => {
    const round = Math.max(1, n);
    let found = rounds.get(round);
    if (!found) {
      found = band(`round-${round}`, `Round ${round}`, round);
      rounds.set(round, found);
    }
    return found;
  };

  // a round that has started shows its heading even before anyone has spoken in it
  for (let n = 1; n <= view.round; n++) roundBand(n);
  for (const turn of view.turns) {
    if (turn.kind === "answer" || turn.kind === "dissent") answer.turns.push(turn);
    else if (turn.round <= 0) reading.turns.push(turn);
    else roundBand(turn.round).turns.push(turn);
  }
  for (const note of view.notes) {
    if (note.state === "delivered") roundBand(note.round).notes.push(note);
  }
  const tally = view.tally;
  if (tally && tally.basis !== "live") {
    roundBand(tally.round).vote = {
      text: `Round ${tally.round} vote: ${ofSeats(tally.agree, tally.seats)} agree, needs ${tally.needed}`,
      reached: tally.reached,
    };
  }

  return [
    ...(reading.turns.length > 0 ? [reading] : []),
    ...[...rounds.values()].sort((a, b) => (a.round ?? 0) - (b.round ?? 0)),
    ...(answer.turns.length > 0 ? [answer] : []),
  ];
}

const list = (words: string[]): string =>
  words.length <= 1 ? (words[0] ?? "") : `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;

type Named = { id: string; shortName: string };

/** "to all", "to Qwen", "to Qwen and Gemma". A closing dissent says what it is instead. */
export function toWords(turn: TurnView, seats: Named[]): string {
  if (turn.kind === "dissent") return "disagreed";
  if (turn.to === "all") return "to all";
  const names = turn.to.map((id) => seats.find((s) => s.id === id)?.shortName).filter((n) => n !== undefined);
  return names.length > 0 ? `to ${list(names)}` : "to all";
}

/** The words on a citation chip: the file's name, then "p. 9" (kept together when a long name wraps). */
export function citationWords(citation: Citation, files: FileRef[]): { label: string; detail?: string } {
  if (citation.kind === "council") return { label: citation.entryId };
  const label = files.find((f) => f.id === citation.fileId)?.name ?? "A file";
  return citation.page === undefined ? { label } : { label, detail: `p.\u00a0${citation.page}` };
}

/** One short line for a reading turn: "Qwen read Renewal letter 2026.pdf, page 1". */
export function researchWords(turn: TurnView, name: string, files: FileRef[]): string {
  if (!turn.done) return `${name} is reading your files`;
  const pagesByFile = new Map<string, number[]>();
  for (const citation of turn.citations) {
    if (citation.kind !== "file") continue;
    const file = files.find((f) => f.id === citation.fileId)?.name;
    if (!file) continue;
    const pages = pagesByFile.get(file) ?? [];
    if (citation.page !== undefined && !pages.includes(citation.page)) pages.push(citation.page);
    pagesByFile.set(file, pages);
  }
  if (pagesByFile.size === 0) return `${name} read your files`;
  const read = [...pagesByFile].map(([file, pages]) => {
    if (pages.length === 0) return file;
    return `${file}, ${pages.length === 1 ? "page" : "pages"} ${list(pages.map(String))}`;
  });
  return `${name} read ${read.join(" and ")}`;
}

export interface StripWords {
  /** a mark that goes with the first part: agreement and failure are never said by colour */
  mark: "agreed" | "failed" | null;
  parts: string[];
}

/** The header strip: round, time left, agreement. Parts are set apart by space. */
export function stripWords(view: DebateView): StripWords {
  const plain = (...parts: string[]): StripWords => ({ mark: null, parts });
  const { tally, answer, round } = view;
  const count = tally ? ofSeats(tally.agree, tally.seats) : "";
  const left = `${minSec(view.leftMs)} left`;

  if (answer) {
    const backed = ofSeats(answer.agree, answer.seats);
    const took = `${answer.rounds} ${answer.rounds === 1 ? "round" : "rounds"}, ${minSec(answer.elapsedMs)}`;
    if (answer.outcome === "agreed") return { mark: "agreed", parts: [`Agreed ${backed}`, took] };
    if (answer.outcome === "no-consensus") {
      return plain(`No consensus, ${backed}`, `Time ran out at ${minSec(answer.elapsedMs)}`);
    }
    return plain("Stopped", took);
  }
  const failed = view.seats.find((s) => s.status === "failed");
  if (failed) return { mark: "failed", parts: [`${failed.shortName} did not load`] };

  switch (view.phase) {
    case "idle":
      return plain("Waiting for a question");
    case "spooling": {
      const ready = view.seats.filter((s) => s.status === "ready").length;
      return plain(`Seating the council, ${ofSeats(ready, view.seats.length)} ready`);
    }
    case "writing":
      if (!tally) return plain("Writing the answer");
      if (tally.reached) return { mark: "agreed", parts: [`Agreed ${count}, writing the answer`] };
      return plain(`No consensus, ${count}, writing the answer`);
    case "released":
      return plain("Answer released");
    case "research":
      return plain(view.paused ? "Paused" : "Reading your files", left);
  }
  const agreement = tally
    ? `${count} agree, needs ${tally.needed}`
    : `No vote yet, needs ${ofSeats(needed(view.seats.length), view.seats.length)}`;
  return plain(view.paused ? `Paused in round ${round}` : `Round ${round}`, left, agreement);
}
