// The slim bar across the top: who is seated (left: the council's size, as a button and a slider;
// then each short name in seat order with its small figure) and the state of the debate (pill,
// right end).
import { Slider } from "radix-ui";
import type { ReactNode } from "react";
import type { SeatView } from "../../lib/events";
import { SeatFigure } from "../shared/SeatFigure";
import { wght } from "../shared/words";

export function TopBar({
  seats,
  onCouncil,
  onSeats,
  sizes = { min: 2, max: 6 },
  pill,
}: {
  /** empty on screens that have no council (the "arrives later" pages) */
  seats: SeatView[];
  /** opens the seat picker */
  onCouncil?: () => void;
  /** the slider was moved to this many seats; without it no slider is shown */
  onSeats?: (seats: number) => void;
  /** the sizes the slider reaches */
  sizes?: { min: number; max: number };
  pill?: ReactNode;
}) {
  // a council outside the usual sizes (the seven-seat review scenes) stretches the slider to itself
  const min = Math.min(sizes.min, seats.length);
  const max = Math.max(sizes.max, seats.length);
  return (
    <header className="flex h-12 shrink-0 items-center gap-6 border-hairline border-b pr-4 pl-6">
      {seats.length > 0 ? (
        <div className="mr-auto flex shrink-0 items-center gap-3">
          <button
            type="button"
            onClick={onCouncil}
            aria-haspopup="dialog"
            style={wght.title}
            className="-ml-2 inline-flex h-8 shrink-0 cursor-pointer items-center rounded-control px-2 text-chat text-ink transition-colors duration-(--quick) hover:bg-hover"
          >
            Council of {seats.length}
          </button>
          {onSeats ? (
            // how many sit at the table: drag, or use the arrow keys
            <div data-part="council-slider" className="flex items-center gap-2 text-meta text-muted">
              <span aria-hidden="true" className="hidden lg:inline">
                {min}
              </span>
              <Slider.Root
                min={min}
                max={max}
                step={1}
                value={[seats.length]}
                onValueChange={([next]) => {
                  if (next !== undefined && next !== seats.length) onSeats(next);
                }}
                className="relative flex h-8 w-16 touch-none select-none items-center lg:w-28"
              >
                <Slider.Track className="relative h-0.5 grow rounded-full bg-line">
                  <Slider.Range className="absolute h-full rounded-full bg-accent" />
                </Slider.Track>
                <Slider.Thumb
                  aria-label="Seats at the table"
                  aria-valuetext={`${seats.length} seats`}
                  className="block size-4 cursor-grab rounded-full bg-accent active:cursor-grabbing"
                />
              </Slider.Root>
              <span aria-hidden="true" className="hidden lg:inline">
                {max}
              </span>
            </div>
          ) : null}
        </div>
      ) : (
        <p style={wght.title} className="mr-auto text-chat text-ink">
          Syndicate
        </p>
      )}
      {seats.length > 0 ? (
        // a name that does not fit wraps to a second row, which is out of sight: never half a name
        <ul aria-label="Seated" className="flex max-h-7 min-w-0 flex-wrap justify-end gap-4 overflow-hidden">
          {seats.map((seat) => (
            <li key={seat.id} className="inline-flex shrink-0 items-center gap-1.5 text-bubble font-medium text-ink">
              <SeatFigure seat={seat} index={seat.index} headD={14} size="tiny" />
              {seat.shortName}
            </li>
          ))}
        </ul>
      ) : null}
      {pill}
    </header>
  );
}
