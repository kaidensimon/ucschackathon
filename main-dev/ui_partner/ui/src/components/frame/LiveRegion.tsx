// The one polite live region. It speaks three things only: a new round, a vote result,
// and the final outcome. Never each speaker, never the clock.
import { useEffect, useRef, useState } from "react";
import type { DebateView } from "../../lib/events";
import { ofSeats } from "../shared/words";

/** What to say when the debate moves from `prev` to `next`, or null when nothing worth saying changed. */
export function announcement(prev: DebateView | null, next: DebateView): string | null {
  if (!prev) return null; // opening a screen is not news
  if (next.answer && !prev.answer) {
    const backed = ofSeats(next.answer.agree, next.answer.seats);
    if (next.answer.outcome === "agreed") return `Agreed ${backed}. The answer is ready.`;
    if (next.answer.outcome === "no-consensus") return `No consensus, ${backed} backed this answer.`;
    return "Stopped.";
  }
  const t = next.tally;
  if (t && (prev.tally?.round !== t.round || prev.tally.agree !== t.agree)) {
    const count = ofSeats(t.agree, t.seats);
    return t.reached ? `Agreed ${count}.` : `Round ${t.round} vote: ${count} agree, needs ${t.needed}.`;
  }
  if (next.round !== prev.round && next.round > 0) return `Round ${next.round}.`;
  return null;
}

export function LiveRegion({ view }: { view: DebateView }) {
  const prev = useRef<DebateView | null>(null);
  const [said, setSaid] = useState("");
  useEffect(() => {
    const words = announcement(prev.current, view);
    prev.current = view;
    if (words) setSaid(words);
  }, [view]);
  return (
    <div data-part="live-region" aria-live="polite" aria-atomic="true" className="sr-only">
      {said}
    </div>
  );
}
