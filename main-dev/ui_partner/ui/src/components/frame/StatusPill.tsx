// The one-line state of the debate, at the right end of the top bar.
// Parts are set apart by space: no pipes, no dots (direction.md, "Wording").
// It is not a live region: the time changes every second. LiveRegion does the announcing.
import { CircleAlert } from "lucide-react";
import type { DebateView } from "../../lib/events";
import { CheckGlyph } from "../shared/Glyph";
import { minSec, ofSeats, wght } from "../shared/words";

export interface PillWords {
  tone: "plain" | "agreed" | "error";
  parts: string[];
}

export function pillWords(view: DebateView): PillWords {
  const plain = (...parts: string[]): PillWords => ({ tone: "plain", parts });
  const { tally, answer, round } = view;
  const count = tally ? ofSeats(tally.agree, tally.seats) : "";
  const left = `${minSec(view.leftMs)} left`;

  if (answer) {
    const backed = ofSeats(answer.agree, answer.seats);
    if (answer.outcome === "agreed") return { tone: "agreed", parts: [`Agreed ${backed}`] };
    if (answer.outcome === "no-consensus") return plain(`No consensus, ${backed}`);
    return plain("Stopped");
  }
  const failed = view.seats.find((s) => s.status === "failed");
  if (failed) return { tone: "error", parts: [`${failed.shortName} did not load`] };

  switch (view.phase) {
    case "idle":
      return plain("Waiting for a question");
    case "spooling": {
      const ready = view.seats.filter((s) => s.status === "ready").length;
      return plain(`Seating the council, ${ofSeats(ready, view.seats.length)} ready`);
    }
    case "writing":
      if (!tally) return plain("Writing the answer");
      if (tally.reached) return { tone: "agreed", parts: [`Agreed ${count}, writing the answer`] };
      return plain(`No consensus, ${count}, writing the answer`);
    case "released":
      return plain("Answer released");
  }
  if (view.paused) return plain(round > 0 ? `Paused in round ${round}` : "Paused");
  if (view.phase === "research") return plain("Reading your files", left);
  if (view.phase === "vote") {
    return tally && tally.round === round
      ? plain(`Round ${round} vote`, `${count} agree`)
      : plain(`Round ${round} vote`, left);
  }
  return plain(`Round ${round}`, left, tally ? `${count} agree` : "No vote yet");
}

export function StatusPill({ view }: { view: DebateView }) {
  const { tone, parts } = pillWords(view);
  return (
    <p
      data-part="status-pill"
      data-tone={tone}
      style={wght.pill}
      className="inline-flex h-7.5 shrink-0 items-center gap-4.5 whitespace-nowrap rounded-full border border-line px-3.5 text-bubble text-ink"
    >
      {parts.map((part, i) => {
        // the agreed colour never stands alone: it comes with the check and the word
        const agreed = i === 0 && tone === "agreed" && part.startsWith("Agreed");
        return (
          <span key={part} className="inline-flex items-center">
            {i === 0 && tone === "error" ? (
              <CircleAlert size={14} aria-hidden="true" className="mr-1.5 text-error" />
            ) : null}
            {agreed ? (
              <span className="inline-flex items-center gap-1.5 text-agreed">
                <CheckGlyph size={14} />
                Agreed
              </span>
            ) : null}
            <span className="whitespace-pre">{agreed ? part.slice("Agreed".length) : part}</span>
            {i < parts.length - 1 ? <span className="sr-only"> </span> : null}
          </span>
        );
      })}
    </p>
  );
}
