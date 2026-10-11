// Who sits at the table, and how long they may debate. A side sheet, like the other sheets:
// Esc closes it and focus goes back to where it was.
// Phase 1 shows the sample council only. Choosing models arrives in Phase 3, so the seats
// are listed, not edited; the time limit can be tried but changes nothing in the sample.
import { Dialog, RadioGroup } from "radix-ui";
import { useId, useState } from "react";
import { useEngineLive } from "../../engine/EngineProvider";
import type { Seat, SeatView } from "../../lib/events";
import { SeatSlider, useSeatChoice } from "../../screens/chat/ChatTopBar";
import { Button } from "../shared/Button";
import { Notice, useNotYet } from "../shared/Notice";
import { SeatFigure } from "../shared/SeatFigure";
import { seatFullName, seatLabel } from "../shared/seatName";
import { NOT_YET, wght } from "../shared/words";

const LIMITS = [2, 5, 10].map((min) => ({ value: String(min * 60000), label: `${min} min` }));

const seated = (seat: Seat): SeatView => ({ ...seat, status: "ready", activity: "idle", mark: null, bubble: null });

function TimeLimit({ limitMs, readOnly }: { limitMs: number; readOnly: boolean }) {
  // lives only while the sheet is open: the sample debate keeps the limit it was recorded with
  const [picked, setPicked] = useState<string | null>(null);
  const [notYet, poke] = useNotYet();
  const labelId = useId();
  return (
    <div className="flex flex-col items-start gap-2">
      <p id={labelId} className="font-medium text-ink text-label">
        Time limit
      </p>
      <RadioGroup.Root
        aria-labelledby={labelId}
        orientation="horizontal"
        value={picked ?? String(limitMs)}
        onValueChange={(next) => {
          setPicked(next);
          poke();
        }}
        disabled={readOnly}
        className="inline-flex rounded-full border border-line p-0.75 data-disabled:border-dashed"
      >
        {LIMITS.map((limit) => (
          <RadioGroup.Item
            key={limit.value}
            value={limit.value}
            // locked: the chosen limit keeps a shape of its own (an ink edge), not only a tint
            className="h-7 cursor-pointer rounded-full border border-transparent px-3.5 font-medium text-ink text-label transition-colors duration-(--quick) data-[state=unchecked]:hover:bg-hover data-[state=checked]:border-accent data-[state=checked]:bg-accent data-[state=checked]:text-on-accent data-disabled:cursor-default data-disabled:text-muted data-disabled:data-[state=unchecked]:hover:bg-transparent data-disabled:data-[state=checked]:bg-transparent data-disabled:data-[state=checked]:text-ink"
          >
            {limit.label}
          </RadioGroup.Item>
        ))}
      </RadioGroup.Root>
      {notYet ? <Notice>{NOT_YET}</Notice> : null}
    </div>
  );
}

export const ROUTER_PICKS = "The router picks the models when you ask";

/** Seats nobody sits in yet: no model, no maker. The router fills them when a question is asked. */
function blankSeats(count: number): Seat[] {
  return Array.from({ length: count }, (_, i): Seat => ({
    id: `seat-${i + 1}`,
    index: i,
    shortName: `Seat ${i + 1}`,
    modelName: "",
  }));
}

/**
 * What the sheet holds under its title: the seats, the way to add one, the time limit.
 * With the real engine only the NUMBER of seats is the owner's; which models sit there is the
 * router's. `ran`: the seats given are the real ones of a debate (otherwise they are blank).
 */
export function SeatPickerBody({
  seats,
  limitMs,
  readOnly,
  ran = true,
}: {
  seats: Seat[];
  limitMs: number;
  readOnly: boolean;
  ran?: boolean;
}) {
  const engineLive = useEngineLive();
  const [chosen, choose] = useSeatChoice();
  const blank = engineLive && (!ran || seats.length === 0);
  const shown = blank ? blankSeats(chosen) : seats;
  return (
    <>
      {engineLive ? (
        <div className="mt-4 flex flex-col items-start gap-2">
          <SeatSlider seats={chosen} onSeats={choose} disabled={readOnly} />
          <p className="text-meta text-muted">{ROUTER_PICKS}</p>
        </div>
      ) : null}
      <ol aria-label="Seats" className="mt-4 flex flex-col">
        {shown.map((seat) => (
          <li key={seat.id} className="flex items-center gap-3 border-hairline border-b py-2.5">
            <SeatFigure seat={seated(seat)} index={seat.index} headD={22} size="small" />
            <div className="min-w-0 flex-1">
              <p className="font-medium text-ink text-label">{blank ? seat.shortName : seatLabel(seat)}</p>
              {blank ? null : (
                <p className="truncate text-meta text-muted">{engineLive ? seatFullName(seat) : seat.modelName}</p>
              )}
            </div>
            <p className="shrink-0 text-meta text-muted">Seat {seat.index + 1}</p>
          </li>
        ))}
      </ol>

      {engineLive ? null : (
        <div className="mt-4 flex flex-col items-start gap-2">
          <Button size="small" disabled>
            Add a seat
          </Button>
          <p className="text-meta text-muted">Choosing models arrives in Phase 3</p>
        </div>
      )}

      <div className="mt-7">
        <TimeLimit limitMs={limitMs} readOnly={readOnly} />
      </div>
    </>
  );
}

export function SeatPicker(p: {
  seats: Seat[];
  limitMs: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  readOnly: boolean;
  /** with the real engine: the seats are those of a debate that ran (default: blank seats) */
  ran?: boolean;
}) {
  return (
    <Dialog.Root open={p.open} onOpenChange={p.onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-page/70" />
        <Dialog.Content
          data-part="seat-picker"
          data-read-only={p.readOnly}
          // only a running debate has something to say under the title
          {...(p.readOnly ? {} : { "aria-describedby": undefined })}
          className="fixed inset-y-0 right-0 z-50 flex w-90 max-w-full flex-col overflow-y-auto border-line border-l bg-surface p-6 text-ink"
        >
          <div className="flex items-center justify-between gap-4">
            <Dialog.Title style={wght.name} className="text-heading">
              Seat the council
            </Dialog.Title>
            <Dialog.Close asChild>
              <Button size="small">Close</Button>
            </Dialog.Close>
          </div>
          {p.readOnly ? (
            <Dialog.Description className="mt-3 text-label text-muted">The council is in session</Dialog.Description>
          ) : null}

          <SeatPickerBody seats={p.seats} limitMs={p.limitMs} readOnly={p.readOnly} ran={p.ran ?? false} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
