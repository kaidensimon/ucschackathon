// Chat View: the full messages the models send each other. Black, white and grey only:
// every colour in here is a cv-* token, on its own solid sheet.
//   thread   one column in time order (the narrow window, or a large council)
//   columns  one column per seat, banded by round, when each seat gets 200 px or more
// It draws `view` and nothing else: no timers, no copy of the debate.
import clsx from "clsx";
import { ChevronDown, CircleAlert } from "lucide-react";
import { Fragment, type ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { DebateView, SeatView } from "../../lib/events";
import { CheckGlyph } from "../shared/Glyph";
import { MakerMark } from "../shared/MakerMark";
import { seatFullName, seatLabel } from "../shared/seatName";
import { figureBox, SeatFigure } from "../shared/SeatFigure";
import { VoteMark } from "../shared/VoteMark";
import { wght } from "../shared/words";
import { type Band, bandsOf, type Layout, layoutFor, stripWords } from "./chatModel";
import { BandLabel, Message, NoteMessage, ResearchLine, VoteLine } from "./Message";

/** the reader counts as "at the newest message" within this many px of the end */
const NEAR_END = 24;
/** the focus ring in here is ink from the Chat View greys, not the app's accent */
const FOCUS = "focus-visible:outline-cv-ink";

/** the thread's one column: the same 640 px the question keeps, with a margin for a narrow sheet */
const THREAD = "mx-auto w-full max-w-170 px-5";

export function ChatView(p: {
  view: DebateView;
  width: number;
  filterSeatId: string | null;
  onFilter: (seatId: string | null) => void;
}) {
  const { view, width, filterSeatId, onFilter } = p;
  const layout = layoutFor(width, view.seats.length);
  // the filter belongs to the thread: columns already keep each model apart
  const only = layout === "thread" ? (view.seats.find((s) => s.id === filterSeatId) ?? null) : null;
  const bands = useMemo(() => {
    const all = bandsOf(view);
    if (!only) return all;
    return all.map((band) => ({ ...band, notes: [], turns: band.turns.filter((t) => t.seatId === only.id) }));
  }, [view, only]);
  const shown = bands.reduce((n, band) => n + band.turns.length + band.notes.length, 0);
  const follow = useFollowNewest();
  const nothing =
    shown === 0 ? (
      <p className={clsx("pt-4 text-cv-grey text-label", layout === "thread" ? THREAD : "px-4")}>
        {only ? `No messages from ${seatLabel(only)} yet` : "No messages yet"}
      </p>
    ) : null;

  return (
    <section
      data-part="chat-view"
      data-layout={layout}
      className="flex h-full min-h-0 flex-col overflow-hidden rounded-card border border-cv-rule bg-cv-paper text-cv-ink selection:bg-cv-ink selection:text-cv-paper"
    >
      <Strip view={view} layout={layout} only={only} onFilter={onFilter} />
      <div className="relative min-h-0 flex-1">
        <section
          ref={follow.scroller}
          aria-label="Debate messages"
          // biome-ignore lint/a11y/noNoninteractiveTabindex: a scrolling area must be reachable so the keyboard can scroll it
          tabIndex={0}
          onScroll={follow.onScroll}
          // the scrollbar stays grey in both themes
          style={{ scrollbarColor: "var(--cv-rule) transparent", scrollbarWidth: "thin" }}
          // the ring is drawn inside the sheet, and follows its lower corners
          className={clsx("h-full overflow-y-auto rounded-b-card focus-visible:-outline-offset-2", FOCUS)}
        >
          <div ref={follow.content}>
            {layout === "columns" ? (
              <>
                <Columns view={view} bands={bands} />
                {nothing}
              </>
            ) : (
              <>
                {nothing}
                <Thread view={view} bands={bands} />
              </>
            )}
          </div>
        </section>
        {follow.away ? (
          <button
            type="button"
            onClick={follow.toNewest}
            className={clsx(
              "-translate-x-1/2 absolute bottom-4 left-1/2 inline-flex h-7.5 cursor-pointer items-center rounded-control border border-cv-ink bg-cv-ink px-3 font-medium text-cv-paper text-label",
              FOCUS,
            )}
          >
            Jump to newest
          </button>
        ) : null}
      </div>
    </section>
  );
}

/** Round, time left, agreement; at the right, whose messages are shown. */
function Strip({
  view,
  layout,
  only,
  onFilter,
}: {
  view: DebateView;
  layout: Layout;
  only: SeatView | null;
  onFilter: (seatId: string | null) => void;
}) {
  const { mark, parts } = stripWords(view);
  return (
    // over columns the strip and the column heads are one header: the line comes under the heads
    <header className={clsx("shrink-0", layout === "thread" && "border-cv-faint border-b")}>
      <div className={clsx("flex h-11 items-center gap-5", layout === "thread" ? THREAD : "px-4")}>
        <p className="flex min-w-0 items-center gap-5 whitespace-nowrap font-medium text-label">
          {parts.map((part, i) => (
            <span key={part} style={i === 0 ? wght.name : undefined} className="inline-flex items-center gap-1.5">
              {i === 0 && mark === "agreed" ? <CheckGlyph size={14} className="shrink-0" /> : null}
              {i === 0 && mark === "failed" ? <CircleAlert size={14} aria-hidden="true" className="shrink-0" /> : null}
              {part}
            </span>
          ))}
        </p>
        {layout === "thread" ? (
          <label className="relative ml-auto inline-flex shrink-0 items-center gap-2">
            <span className="sr-only">Show messages from</span>
            {/* a list's choices are words only, so the picked model's mark sits beside the list */}
            {only ? <MakerMark seat={only} size={16} variant="ink" /> : null}
            <select
              value={only?.id ?? ""}
              onChange={(e) => onFilter(e.target.value || null)}
              className={clsx(
                "h-7.5 cursor-pointer appearance-none rounded-control border border-cv-rule bg-cv-paper pr-8 pl-3 font-medium text-cv-ink text-label transition-colors duration-(--quick) hover:bg-cv-faint",
                FOCUS,
              )}
            >
              <option value="" className="bg-cv-paper text-cv-ink">
                All models
              </option>
              {view.seats.map((seat) => (
                <option key={seat.id} value={seat.id} title={seatFullName(seat)} className="bg-cv-paper text-cv-ink">
                  {seatLabel(seat)}
                </option>
              ))}
            </select>
            <ChevronDown size={14} aria-hidden="true" className="pointer-events-none absolute right-2.5" />
          </label>
        ) : null}
      </div>
    </header>
  );
}

/** One column, in time order. A vote line closes a round; a rule and "Round 2" open the next. */
function Thread({ view, bands }: { view: DebateView; bands: Band[] }) {
  return (
    <div className={clsx(THREAD, "pt-4 pb-2")}>
      {bands.map((band) => (
        <Fragment key={band.key}>
          {band.label ? <BandLabel label={band.label} round={band.round !== null} /> : null}
          {band.notes.length + band.turns.length > 0 ? (
            <div className="flex flex-col pt-3 pb-5">
              {band.notes.map((note) => (
                <NoteMessage key={note.noteId} note={note} className="mt-5 first:mt-0" />
              ))}
              <Turns turns={band.turns} view={view} />
            </div>
          ) : band.label ? (
            <div className="h-5" />
          ) : null}
          {band.vote ? <VoteLine text={band.vote.text} reached={band.vote.reached} /> : null}
        </Fragment>
      ))}
    </div>
  );
}

/** A run of turns: reading lines sit close together, messages stand apart. */
function Turns({ turns, view, named = true }: { turns: Band["turns"]; view: DebateView; named?: boolean }) {
  return turns.map((turn) =>
    turn.kind === "research" ? (
      <ResearchLine key={turn.turnId} turn={turn} seats={view.seats} files={view.files} className="mt-1 first:mt-0" />
    ) : (
      <Message
        key={turn.turnId}
        turn={turn}
        seats={view.seats}
        files={view.files}
        named={named}
        className="mt-5 first:mt-0"
      />
    ),
  );
}

/**
 * One column per seat, in seat order. The rows of the grid are the bands, shared by every
 * column (each column is a subgrid), so a round starts at the same height all the way across
 * and its heading and vote line run over all the columns.
 */
function Columns({ view, bands }: { view: DebateView; bands: Band[] }) {
  const seats = view.seats;
  // row 1 holds the column heads
  let row = 1;
  const across: { row: number; key: string; node: ReactNode }[] = [];
  const cells: { row: number; band: Band }[] = [];
  for (const band of bands) {
    if (band.label) {
      across.push({
        row: ++row,
        key: `${band.key}-label`,
        // each column names the band itself for a screen reader, which reads column by column
        node: <BandLabel label={band.label} round={band.round !== null} across />,
      });
    }
    if (band.notes.length > 0) {
      across.push({
        row: ++row,
        key: `${band.key}-notes`,
        node: (
          <div className="flex flex-col gap-3 pt-3">
            {band.notes.map((note) => (
              <NoteMessage key={note.noteId} note={note} />
            ))}
          </div>
        ),
      });
    }
    cells.push({ row: ++row, band });
    if (band.vote) {
      across.push({
        row: ++row,
        key: `${band.key}-vote`,
        node: <VoteLine text={band.vote.text} reached={band.vote.reached} />,
      });
    }
  }
  const last = seats.length - 1;

  return (
    <div
      className="grid gap-x-6 px-4 pb-2"
      style={{
        gridTemplateColumns: `repeat(${seats.length}, minmax(0, 1fr))`,
        gridTemplateRows: `repeat(${row}, auto)`,
      }}
    >
      {seats.map((seat, i) => (
        <div
          key={seat.id}
          data-part="chat-column"
          data-seat={seat.id}
          className="grid grid-rows-subgrid"
          style={{ gridColumn: i + 1, gridRow: `1 / span ${row}` }}
        >
          <ColumnHead seat={seat} speaking={view.speaking.includes(seat.id)} first={i === 0} last={i === last} />
          {cells.map(({ row: at, band }) => {
            const mine = band.turns.filter((t) => t.seatId === seat.id);
            if (mine.length === 0) return null;
            return (
              <div key={band.key} style={{ gridRow: at }}>
                {band.label ? <h3 className="sr-only">{band.label}</h3> : null}
                <div className="flex flex-col pt-3 pb-5">
                  {/* the head above already names the sender */}
                  <Turns turns={mine} view={view} named={false} />
                </div>
              </div>
            );
          })}
        </div>
      ))}
      {across.map((item) => (
        <div key={item.key} style={{ gridColumn: "1 / -1", gridRow: item.row }}>
          {item.node}
        </div>
      ))}
    </div>
  );
}

/** A column's head: the seat's figure as an outline, its maker's mark and name, and the model behind it. */
function ColumnHead({
  seat,
  speaking,
  first,
  last,
}: {
  seat: SeatView;
  speaking: boolean;
  first: boolean;
  last: boolean;
}) {
  const box = figureBox(22);
  const under = seat.status === "loading" ? "Loading" : seat.status === "failed" ? "Did not load" : seat.modelName;
  return (
    <div
      // The head stays put while the messages scroll under it. It reaches half way into the
      // gap on each side (and to the sheet's edge at the ends), so nothing shows between heads.
      className={clsx(
        "sticky top-0 z-10 flex items-center gap-2.5 border-cv-faint border-b bg-cv-paper pt-3.5 pb-2.5",
        first ? "-ml-4 pl-4" : "-ml-3 pl-3",
        last ? "-mr-4 pr-4" : "-mr-3 pr-3",
      )}
      style={{ gridRow: 1 }}
    >
      <span className="relative block shrink-0" style={{ width: box.width, height: box.height }}>
        <SeatFigure seat={seat} index={seat.index} headD={22} size="small" variant="ink" speaking={speaking} />
        {seat.mark ? (
          <span className="absolute" style={{ left: box.markCx - 8, top: box.markCy - 8 }}>
            <VoteMark mark={seat.mark} size={16} variant="ink" />
          </span>
        ) : null}
      </span>
      <span className="flex min-w-0 flex-col">
        <span title={seatFullName(seat)} className="flex min-w-0 items-center gap-1.5">
          <MakerMark seat={seat} size={16} variant="ink" />
          <span style={wght.name} className="truncate text-label">
            {seatLabel(seat)}
          </span>
        </span>
        <span className="truncate text-cv-grey text-meta">{under}</span>
      </span>
    </div>
  );
}

/**
 * Keeps the newest message in sight while the reader is at the end of the messages, and
 * leaves the page alone once they have scrolled up (then `away` offers the way back).
 * Scroll position only: no timers.
 */
function useFollowNewest() {
  const scroller = useRef<HTMLElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const atEnd = useRef(true);
  const [away, setAway] = useState(false);

  const onScroll = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    atEnd.current = el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_END;
    setAway(!atEnd.current);
  }, []);

  const toNewest = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    atEnd.current = true;
    setAway(false);
    // the button is about to go: keep the keyboard where it was working
    el.focus({ preventScroll: true });
  }, []);

  // after every draw: new words push the end down, so follow it
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && atEnd.current) el.scrollTop = el.scrollHeight;
  });

  // and when the size changes with no new draw (the font arriving, the window resized)
  useEffect(() => {
    const el = scroller.current;
    const inner = content.current;
    if (!el || !inner || typeof ResizeObserver === "undefined") return;
    const watch = new ResizeObserver(() => {
      if (atEnd.current) el.scrollTop = el.scrollHeight;
    });
    watch.observe(el);
    watch.observe(inner);
    return () => watch.disconnect();
  }, []);

  return { scroller, content, away, onScroll, toNewest };
}
