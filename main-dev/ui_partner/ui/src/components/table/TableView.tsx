// Table View: the council at its half-circle table (spec, screen rule 7).
// Every position comes from tableLayout / figureRect / placeBubbles; nothing is worked out here.
// It draws `view` and keeps no debate state: who speaks, each vote mark and each bubble's
// strength are read from the view at every render.
import { type KeyboardEvent, useMemo, useReducer, useRef, useState } from "react";
import { type DebateView, needed, type SeatView } from "../../lib/events";
import { figureRect, placeBubbles, type TableLayout, tableLayout } from "../../lib/layout/tableLayout";
import type { LiveBubble } from "../../lib/timeline/bubble";
import { Meter } from "../shared/Meter";
import { makerOf } from "../shared/makers";
import { figureScale, markCentre, SeatFigure } from "../shared/SeatFigure";
import { VoteMark } from "../shared/VoteMark";
import { minSec, ofSeats, wght } from "../shared/words";
import { Bubble, BubbleProbe, bubbleSize, needsProbe, RING_ROOM, TAIL_ROOM, tailAt } from "./Bubble";
import { seatLabel } from "./seatWords";

/** a vote mark at the table, its page-colour gap included: full size, and at least this on a small head */
const MARK = 26;
const MARK_MIN = 14;
/**
 * A short window leaves a small table. Its words must stay on the cloth and off its edges, so
 * below these radii the caption under the pips goes first, then the pips, then everything.
 */
const SMALL_TABLE = 124;
const SMALLER_TABLE = 96;
const TINY_TABLE = 64;
/** rough width of one character in the table's two lines of words (14 px semibold, 20 px), and the air kept each side */
const WHERE_CHAR = 7;
const TIME_CHAR = 9.4;
const CLOTH_AIR = 8;

/** The words in the middle of the table: where the debate is, and how much time is left. */
function middleWords(view: DebateView): { where: string; time: string | null } {
  const left = `${minSec(view.leftMs)} left`;
  if (view.answer) {
    const { rounds, elapsedMs } = view.answer;
    return { where: `${rounds} ${rounds === 1 ? "round" : "rounds"}, ${minSec(elapsedMs)}`, time: null };
  }
  switch (view.phase) {
    case "idle":
      return { where: "Waiting for a question", time: null };
    case "spooling": {
      const ready = view.seats.filter((s) => s.status === "ready").length;
      return { where: "Seating the council", time: `${ofSeats(ready, view.seats.length)} ready` };
    }
    case "writing":
    case "released":
      return { where: "Writing the answer", time: null };
  }
  if (view.paused) return { where: view.round > 0 ? `Paused in round ${view.round}` : "Paused", time: left };
  if (view.phase === "research") return { where: "Reading your files", time: left };
  if (view.phase === "vote") return { where: `Round ${view.round} vote`, time: left };
  return { where: `Round ${view.round}`, time: left };
}

function TableMiddle({ view, layout, lifted }: { view: DebateView; layout: TableLayout; lifted: boolean }) {
  const R = layout.tableR;
  if (R < TINY_TABLE) return null;
  const { where, time } = middleWords(view);
  const seats = view.seats.length;
  const tally = view.tally;
  // while the council is being seated there is no vote to wait for: the pips come with the clock
  const counting = view.phase !== "idle" && view.phase !== "spooling" && R >= SMALLER_TABLE;
  const caption = tally
    ? `${ofSeats(tally.agree, tally.seats)} agree, needs ${tally.needed}`
    : `No vote yet, needs ${ofSeats(needed(seats), seats)}`;
  // centred on the middle of the cloth (0.42 R above the flat edge), a little higher over a note
  const foot = lifted ? 24 : 0;

  // The cloth is a half circle: the higher a line of words sits, the less width it has. A line
  // that would touch the cloth's edge is left out, the longer one ("Paused in round 2") first.
  // The pill in the top bar says the same things, so nothing is lost.
  const middle = 0.42 * R + 0.75 * foot;
  const below = (counting ? 22 : 0) + (counting && R >= SMALL_TABLE ? 24 : 0);
  const onCloth = (lines: { h: number; w: number }[]) => {
    let top = middle + (lines.reduce((sum, line) => sum + line.h, 0) + below) / 2; // px above the flat edge
    for (const line of lines) {
      if (line.w + 2 * CLOTH_AIR > 2 * Math.sqrt(Math.max(0, R * R - top * top))) return false;
      top -= line.h;
    }
    return true;
  };
  const whereLine = { h: 20, w: where.length * WHERE_CHAR };
  const timeLine = time ? { h: 26, w: time.length * TIME_CHAR } : null;
  const showWhere = onCloth(timeLine ? [whereLine, timeLine] : [whereLine]);
  if (!showWhere && !(timeLine && onCloth([timeLine]))) return null;
  return (
    <div
      data-part="table-middle"
      className="absolute flex flex-col items-center justify-center text-center text-ink"
      style={{
        left: layout.cx - R,
        width: 2 * R,
        top: layout.flatY - 0.84 * R - foot / 2,
        height: 0.84 * R - foot / 2,
      }}
    >
      {showWhere ? <p className="whitespace-nowrap font-semibold text-label">{where}</p> : null}
      {time ? (
        <p style={wght.pill} className="whitespace-nowrap text-heading">
          {time}
        </p>
      ) : null}
      {counting ? (
        <>
          <div className="mt-2 flex">
            <Meter
              agree={tally?.agree ?? 0}
              seats={tally?.seats ?? seats}
              needed={tally?.needed ?? needed(seats)}
              reached={tally?.reached ?? false}
              size="table"
            />
          </div>
          {R >= SMALL_TABLE ? (
            <p style={wght.bubble} className="mt-1.5 whitespace-nowrap text-bubble">
              {caption}
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

export function TableView(p: {
  view: DebateView;
  width: number;
  height: number;
  onOpenSeat: (seatId: string) => void;
}) {
  const { view, width, height, onOpenSeat } = p;
  const seats = view.seats;
  const n = seats.length;
  const layout = useMemo(() => tableLayout(n, width, height), [n, width, height]);
  const box = { width: 1.4 * layout.headD };
  // on a small stage the marks shrink with the heads, and move out to the rim so they do not cover the head
  const mark = Math.max(MARK_MIN, Math.round(MARK * figureScale(layout.headD)));

  // one Tab stop for the whole table; Left and Right move between seats
  const [stop, setStop] = useState(0);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const tabStop = Math.min(stop, n - 1);
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const to =
      e.key === "ArrowRight"
        ? Math.min(n - 1, i + 1)
        : e.key === "ArrowLeft"
          ? Math.max(0, i - 1)
          : e.key === "Home"
            ? 0
            : e.key === "End"
              ? n - 1
              : null;
    if (to === null) return;
    e.preventDefault();
    buttons.current[to]?.focus();
  };

  // Bubbles: seats that are speaking first, then the others, each group left to right.
  // In a live debate every seat keeps its note, so not all may fit: there the newest words come
  // first within each group (`newer`; the recorded samples have none, and keep their order).
  // placeBubbles takes one size for all, so every bubble gets a box as big as the biggest
  // (plus room for its tail) and is drawn inside its own box, as near its seat as it can be.
  const [, measuredAgain] = useReducer((count: number) => count + 1, 0);
  const maxW = layout.bubbleMaxWidth;
  const talking = seats
    .map((seat, i) => ({ seat, i, bubble: seat.bubble }))
    .filter((e): e is { seat: SeatView; i: number; bubble: LiveBubble } => {
      const b = e.bubble;
      return b !== null && (b.opacity > 0 || (b.prev?.opacity ?? 0) > 0);
    })
    .sort(
      (a, b) =>
        Number(view.speaking.includes(b.seat.id)) - Number(view.speaking.includes(a.seat.id)) ||
        (b.bubble.newer ?? 0) - (a.bubble.newer ?? 0) ||
        a.i - b.i,
    )
    .map((e) => ({ ...e, size: bubbleSize(e.bubble.text, maxW) }));
  const slot = {
    w: Math.max(0, ...talking.map((e) => e.size.w)),
    h: Math.max(0, ...talking.map((e) => e.size.h)) + TAIL_ROOM + RING_ROOM,
  };
  const order = talking.map((e) => e.i).join(",");
  const slots = useMemo(
    () =>
      placeBubbles(
        layout,
        order === "" ? [] : order.split(",").map(Number),
        // the two numbers are spelled out so the boxes are found again only when one changes
        { w: slot.w, h: slot.h },
      ),
    [layout, order, slot.w, slot.h],
  );

  const queued = view.notes.findLast((note) => note.state === "queued");
  const R = layout.tableR;
  const cloth = R > 0 ? `M${layout.cx - R} ${layout.flatY}A${R} ${R} 0 0 1 ${layout.cx + R} ${layout.flatY}Z` : "";
  const showNote = queued !== undefined && R >= SMALL_TABLE;

  return (
    // biome-ignore lint/a11y/useSemanticElements: a fieldset would bring its own box; this is a plain named group
    <div data-part="table-view" role="group" aria-label="Council table" className="relative h-full w-full">
      {cloth ? (
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          aria-hidden="true"
          className="absolute top-0 left-0 block overflow-visible"
        >
          {/* the cloth, then its edge: the curve and the flat side are one line, and nothing is drawn over it */}
          <path data-table="cloth" d={cloth} className="fill-table" />
          <path data-table="edge" d={cloth} fill="none" strokeWidth={1.5} className="stroke-line" />
        </svg>
      ) : null}

      <TableMiddle view={view} layout={layout} lifted={showNote} />
      {showNote && queued ? (
        <p
          data-part="table-note"
          className="absolute whitespace-nowrap text-center text-meta text-muted"
          style={{ left: layout.cx - R, width: 2 * R, top: layout.flatY - 28 }}
        >
          Your note waits for round {queued.round + 1}
        </p>
      ) : null}

      {seats.map((seat, i) => {
        const rect = figureRect(layout, i);
        const speaking = view.speaking.includes(seat.id);
        // the vote mark sits on the head's upper outer side: left of the middle it goes upper left
        const leftHalf = rect.x + rect.w / 2 < layout.cx - 1;
        const words = seat.bubble && seat.bubble.opacity > 0 ? seat.bubble.text : undefined;
        const markAt = markCentre(layout.headD, makerOf(seat) !== null);
        return (
          <button
            key={seat.id}
            ref={(el) => {
              buttons.current[i] = el;
            }}
            type="button"
            data-part="seat"
            data-seat-id={seat.id}
            data-status={seat.status}
            data-activity={seat.activity}
            data-speaking={String(speaking)}
            aria-label={seatLabel(seat, view)}
            aria-description={words}
            tabIndex={i === tabStop ? 0 : -1}
            onClick={() => onOpenSeat(seat.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
            onFocus={() => setStop(i)}
            className="group absolute cursor-pointer"
            // the figure draws its own focus frame, round the whole figure
            style={{ left: rect.x, top: rect.y, width: rect.w, height: rect.h, outline: "none" }}
          >
            <SeatFigure
              seat={seat}
              index={seat.index}
              headD={layout.headD}
              speaking={speaking}
              markSide={leftHalf ? "left" : "right"}
            />
            {seat.mark ? (
              <span
                className="absolute"
                style={{
                  left: (leftHalf ? box.width - markAt.x : markAt.x) - mark / 2,
                  top: markAt.y - mark / 2,
                }}
              >
                <VoteMark mark={seat.mark} size={mark} />
              </span>
            ) : null}
          </button>
        );
      })}

      {talking.map((e, at) => {
        const room = slots[at];
        const head = layout.seats[e.i];
        if (!room || !head) return null; // beyond the number of bubbles the table has room for
        const left = Math.max(room.x, Math.min(room.x + room.w - e.size.w, Math.round(head.x - e.size.w / 2)));
        // as low in its box as its tail allows; over a speaking ring, that much higher
        const lift = TAIL_ROOM + (view.speaking.includes(e.seat.id) ? RING_ROOM : 0);
        const top = room.y + room.h - lift - e.size.h;
        return (
          <Bubble
            key={e.seat.id}
            bubble={e.bubble}
            left={left}
            top={top}
            size={e.size}
            tail={tailAt(head.x, left, e.size.w)}
          />
        );
      })}

      {[...new Set(talking.map((e) => e.bubble.text))].map((text) =>
        needsProbe(text, maxW) ? (
          <BubbleProbe key={text} text={text} maxWidth={maxW} onMeasured={measuredAgain} />
        ) : null,
      )}
    </div>
  );
}
