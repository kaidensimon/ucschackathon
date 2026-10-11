// The side sheet for one council member: who it is, what it is doing, everything it has said
// in this debate (newest last) and the pages it has cited. A Radix Dialog on the right:
// Esc closes it and focus goes back to that seat at the table.
import { Dialog } from "radix-ui";
import { type ElementType, useId, useRef } from "react";
import type { DebateView, FileRef, SeatView, TurnView } from "../../lib/events";
import { Button } from "../shared/Button";
import { Chip } from "../shared/Chip";
import { SeatFigure } from "../shared/SeatFigure";
import { VoteMark } from "../shared/VoteMark";
import { minSec, wght } from "../shared/words";
import { capital, listOf, seatState, seatVote } from "./seatWords";

const pagesOf = (pages: number[]) => `${pages.length === 1 ? "page" : "pages"} ${listOf(pages.map(String))}`;

/** Where in the debate a turn was said: "Round 2", or what kind of turn it was. */
function turnPlace(turn: TurnView): string {
  if (turn.kind === "research") return "Reading your files";
  if (turn.kind === "answer") return "The answer";
  if (turn.kind === "dissent") return "Disagreed with the answer";
  return `Round ${turn.round}`;
}

/** "to all" or "to Qwen": only for turns spoken in a round. */
function turnTo(turn: TurnView, seats: SeatView[]): string {
  if (turn.kind !== "position" && turn.kind !== "reply") return "";
  if (turn.to === "all") return "to all";
  const names = turn.to.map((id) => seats.find((s) => s.id === id)?.shortName).filter((name) => name !== undefined);
  return names.length > 0 ? `to ${listOf(names)}` : "to all";
}

/** Each file the seat cited, with its pages in order. Files in the order the owner attached them. */
function filesRead(turns: TurnView[], files: FileRef[]): { file: FileRef; pages: number[] }[] {
  const pages = new Map<string, Set<number>>();
  for (const turn of turns) {
    for (const cite of turn.citations) {
      if (cite.kind !== "file") continue;
      const set = pages.get(cite.fileId) ?? new Set<number>();
      if (cite.page !== undefined) set.add(cite.page);
      pages.set(cite.fileId, set);
    }
  }
  return files
    .filter((file) => pages.has(file.id))
    .map((file) => ({ file, pages: [...(pages.get(file.id) ?? [])].sort((a, b) => a - b) }));
}

/**
 * What the sheet shows, without the dialog round it (the gallery shows this part alone).
 * `Title` and `Description` are the dialog's own parts when it is inside one.
 */
export function SeatSheetBody({
  view,
  seat,
  onClose,
  Title = "h2",
  Description = "p",
}: {
  view: DebateView;
  seat: SeatView;
  onClose?: () => void;
  Title?: ElementType;
  Description?: ElementType;
}) {
  const turns = view.turns.filter((turn) => turn.seatId === seat.id);
  const read = filesRead(turns, view.files);
  const fileName = (id: string) => view.files.find((f) => f.id === id)?.name;
  const vote = seatVote(seat);
  const saidId = useId();
  const readId = useId();
  return (
    <>
      <header className="flex shrink-0 flex-col gap-3 border-hairline border-b px-6 pt-6 pb-4">
        <div className="flex items-start gap-3">
          <span className="mt-0.5">
            <SeatFigure seat={seat} index={seat.index} headD={22} size="small" />
          </span>
          <div className="min-w-0 flex-1">
            <Title style={wght.name} className="text-heading">
              {seat.shortName}
            </Title>
            <Description className="text-label text-muted">{seat.modelName}</Description>
          </div>
          {onClose ? (
            <Button size="small" onClick={onClose}>
              Close
            </Button>
          ) : null}
        </div>
        <p className="flex flex-wrap items-center gap-x-4.5 gap-y-1 text-label">
          <span className="text-muted">Seat {seat.index + 1}</span>
          <span data-part="seat-state" className="font-medium">
            {capital(seatState(seat, view))}
          </span>
          {seat.mark && vote ? (
            <span className="inline-flex items-center gap-1.5">
              <span aria-hidden="true" className="flex">
                <VoteMark mark={seat.mark} size={18} />
              </span>
              {capital(vote)}
            </span>
          ) : null}
        </p>
      </header>

      <section
        aria-label="What this seat said and read"
        // biome-ignore lint/a11y/noNoninteractiveTabindex: a scrolling area must be reachable so the keyboard can scroll it
        tabIndex={0}
        className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-6 pt-4 pb-6"
      >
        <section aria-labelledby={saidId} className="flex flex-col">
          <h3 id={saidId} className="font-semibold text-label">
            Said
          </h3>
          {turns.length === 0 ? (
            <p className="mt-1 text-label text-muted">Nothing yet.</p>
          ) : (
            <ol className="flex flex-col">
              {turns.map((turn) => {
                const to = turnTo(turn, view.seats);
                const cites = turn.citations.filter((cite) => cite.kind === "file");
                return (
                  <li
                    key={turn.turnId}
                    data-part="sheet-turn"
                    className="flex flex-col gap-1.5 border-hairline border-b py-3 last:border-b-0 last:pb-0"
                  >
                    <p className="flex items-baseline gap-3 text-meta text-muted">
                      <span className="font-medium text-ink">{turnPlace(turn)}</span>
                      {to ? <span>{to}</span> : null}
                      <span className="ml-auto">{minSec(turn.clock)}</span>
                    </p>
                    <p className="whitespace-pre-line text-chat">
                      {turn.text}
                      {turn.done ? null : <span className="text-muted">{turn.text ? " " : ""}Writing</span>}
                    </p>
                    {cites.length > 0 ? (
                      <ul aria-label="Cited" className="flex flex-wrap gap-2 pt-0.5">
                        {cites.map((cite) => {
                          const name = fileName(cite.fileId);
                          if (!name) return null;
                          return (
                            <li key={`${cite.fileId}:${cite.page ?? ""}`} className="flex">
                              <Chip
                                kind="citation"
                                label={name}
                                detail={cite.page === undefined ? undefined : `page ${cite.page}`}
                              />
                            </li>
                          );
                        })}
                      </ul>
                    ) : null}
                  </li>
                );
              })}
            </ol>
          )}
        </section>

        {read.length > 0 ? (
          <section aria-labelledby={readId} className="flex flex-col gap-1">
            <h3 id={readId} className="font-semibold text-label">
              Read
            </h3>
            <ul className="flex flex-col">
              {read.map(({ file, pages }) => (
                <li key={file.id} className="py-1 text-label">
                  {file.name}
                  {pages.length > 0 ? <span className="text-muted">, {pagesOf(pages)}</span> : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </section>
    </>
  );
}

export function SeatSheet(p: { view: DebateView; seatId: string | null; onClose: () => void }) {
  const seat = p.seatId === null ? undefined : p.view.seats.find((s) => s.id === p.seatId);
  // remembered for the moment after closing, when focus goes back to this seat
  const lastSeatId = useRef<string | null>(null);
  if (seat) lastSeatId.current = seat.id;
  return (
    <Dialog.Root
      open={seat !== undefined}
      onOpenChange={(open) => {
        if (!open) p.onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-page/70" />
        <Dialog.Content
          data-part="seat-sheet"
          onCloseAutoFocus={(event) => {
            // back to the seat at the table, however the sheet was opened (click, Enter or the 1 to 7 keys)
            for (const el of document.querySelectorAll<HTMLElement>('[data-part="seat"]')) {
              if (el.dataset.seatId !== lastSeatId.current) continue;
              event.preventDefault();
              el.focus();
              return;
            }
          }}
          className="fixed inset-y-0 right-0 z-50 flex w-110 max-w-full flex-col border-line border-l bg-surface text-ink"
        >
          {seat ? (
            <SeatSheetBody
              view={p.view}
              seat={seat}
              onClose={p.onClose}
              Title={Dialog.Title}
              Description={Dialog.Description}
            />
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
