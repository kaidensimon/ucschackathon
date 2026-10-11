// What a seat is doing and how it last voted, in words. The table's seat buttons say them
// aloud; the side sheet shows them. One wording for both, so they can never disagree.
import type { DebateView, SeatView } from "../../lib/events";

/** The seat's state in lower-case words: "speaking", "loading", "did not load" ... */
export function seatState(seat: SeatView, view: DebateView): string {
  if (seat.status === "failed") return "did not load";
  if (seat.status === "loading") return "loading";
  if (seat.status === "dropped") return "left out of this debate";
  if (view.speaking.includes(seat.id) || seat.activity === "speaking") return "speaking";
  if (seat.activity === "researching") return "reading your files";
  if (seat.activity === "writing") return "writing";
  if (view.answer) return "finished";
  if (view.phase === "spooling") return "ready";
  if (view.phase === "vote" || view.phase === "writing") return "waiting";
  return "listening";
}

/** The seat's last vote in words, or "" when it has no mark. */
export function seatVote(seat: SeatView): string {
  if (seat.mark === "agrees") return "agreed at the last vote";
  if (seat.mark === "differs") return "disagreed at the last vote";
  return "";
}

/** "Qwen, speaking, agreed at the last vote" */
export function seatLabel(seat: SeatView, view: DebateView): string {
  return [seat.shortName, seatState(seat, view), seatVote(seat)].filter(Boolean).join(", ");
}

/** "speaking" -> "Speaking" */
export function capital(words: string): string {
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** ["Qwen"] -> "Qwen"; two -> "Qwen and Llama"; more -> "Qwen, Llama and Phi" */
export function listOf(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}
