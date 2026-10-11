// The pieces a thread or a column is made of: one full message, one reading line, the
// owner's note, and the two lines that mark a round. Black, white and grey only.
import clsx from "clsx";
import { PenLine } from "lucide-react";
import type { FileRef, NoteView, TurnView } from "../../lib/events";
import { Chip } from "../shared/Chip";
import { CheckGlyph } from "../shared/Glyph";
import { MakerMark } from "../shared/MakerMark";
import { seatFullName, seatLabel } from "../shared/seatName";
import { minSec, wght } from "../shared/words";
import { citationWords, type Named, researchWords, toWords } from "./chatModel";

/**
 * One message, in full. While its turn is open it shows the text so far, then "Writing";
 * the citation chips arrive when the turn ends.
 */
export function Message({
  turn,
  seats,
  files,
  named = true,
  className,
}: {
  turn: TurnView;
  /** every seat, to name the sender and who the message is for */
  seats: Named[];
  files: FileRef[];
  /** false under a column head that already shows the sender: the name is then only read aloud */
  named?: boolean;
  className?: string;
}) {
  const seat = seats.find((s) => s.id === turn.seatId);
  const sender = seat ? seatLabel(seat) : "A seat";
  const writing = !turn.done;
  return (
    <article
      data-part="message"
      data-kind={turn.kind}
      data-seat={turn.seatId}
      data-state={writing ? "writing" : "done"}
      className={className}
    >
      <p className="flex items-baseline gap-2">
        {/* the maker's mark says at a glance whose model is talking; the name beside it is what is read */}
        {named && seat ? <MakerMark seat={seat} size={16} variant="ink" className="-mr-0.5 self-center" /> : null}
        <span
          style={wght.name}
          title={seat ? seatFullName(seat) : undefined}
          className={named ? "text-label" : "sr-only"}
        >
          {sender}
        </span>
        <span className="text-cv-grey text-meta">{toWords(turn, seats)}</span>
        <span className="ml-auto pl-2 text-cv-grey text-meta">{minSec(turn.clock)}</span>
      </p>
      {turn.text ? <p className="mt-1 max-w-140 whitespace-pre-line text-chat">{turn.text}</p> : null}
      {writing ? (
        <p className="mt-1.5 flex items-center gap-1.5 text-cv-grey text-meta">
          <PenLine size={12} aria-hidden="true" className="shrink-0" />
          Writing
        </p>
      ) : turn.citations.length > 0 ? (
        // a long file name wraps inside its chip, so a chip is never wider than a narrow column
        <p className="mt-2 flex flex-wrap gap-1.5 *:inline-block *:h-auto *:max-w-full *:whitespace-normal *:py-1">
          {turn.citations.map((citation, i) => {
            const words = citationWords(citation, files);
            return (
              <Chip
                // biome-ignore lint/suspicious/noArrayIndexKey: a turn's citations never reorder
                key={i}
                kind="citation"
                variant="ink"
                label={words.label}
                detail={words.detail}
              />
            );
          })}
        </p>
      ) : null}
    </article>
  );
}

/** A reading turn, as one short grey line. */
export function ResearchLine({
  turn,
  seats,
  files,
  className,
}: {
  turn: TurnView;
  seats: Named[];
  files: FileRef[];
  className?: string;
}) {
  const seat = seats.find((s) => s.id === turn.seatId);
  const name = seat ? seatLabel(seat) : "A seat";
  return (
    <p
      data-part="research-line"
      data-seat={turn.seatId}
      data-state={turn.done ? "done" : "reading"}
      className={clsx("text-cv-grey text-label", className)}
    >
      {researchWords(turn, name, files)}
    </p>
  );
}

/** The owner's note, once it has reached the council: a message from "You", set in a line box. */
export function NoteMessage({ note, className }: { note: NoteView; className?: string }) {
  return (
    <article
      data-part="note"
      data-state="delivered"
      className={clsx("rounded-control border border-cv-rule px-3.5 py-2.5", className)}
    >
      <p className="flex items-baseline gap-2">
        <span style={wght.name} className="text-label">
          You
        </span>
        <span className="text-cv-grey text-meta">to all</span>
      </p>
      <p className="mt-1 whitespace-pre-line text-chat">{note.text}</p>
    </article>
  );
}

/**
 * Opens a band: a rule across, then "Round 2". `round` makes it one of the vote dividers.
 * `across`: it runs over the columns for the eye only; each column carries the heading itself.
 */
export function BandLabel({ label, round, across = false }: { label: string; round: boolean; across?: boolean }) {
  const parts = {
    "data-part": round ? "vote-divider" : "band-label",
    "data-kind": round ? "round" : undefined,
    style: wght.name,
    className: "border-cv-rule border-t pt-3 text-label",
  };
  return across ? (
    <p {...parts} aria-hidden="true">
      {label}
    </p>
  ) : (
    <h3 {...parts}>{label}</h3>
  );
}

/** Closes a round: "Round 1 vote: 2 of 5 agree, needs 4". Agreement is said with a check, never a colour. */
export function VoteLine({ text, reached }: { text: string; reached: boolean }) {
  return (
    <p
      data-part="vote-divider"
      data-kind="vote"
      data-reached={String(reached)}
      className="flex items-center gap-1.5 pb-3 font-medium text-label"
    >
      {reached ? <CheckGlyph size={14} className="shrink-0" /> : null}
      {text}
    </p>
  );
}
