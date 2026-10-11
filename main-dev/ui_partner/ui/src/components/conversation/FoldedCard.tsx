// The stage, folded away once an answer is out. It sits straight above the answer and the two
// read as one unit: the vote is said here, once, and the answer below does not repeat it.
//   heading  the outcome and the count        "Agreed 4 of 5"
//   meta     how long it took                 "3 rounds, 3:40"
//   line-up  every seat with the mark of the vote the answer rests on
import { useId } from "react";
import type { DebateView, SeatView } from "../../lib/events";
import { Button } from "../shared/Button";
import { CheckGlyph } from "../shared/Glyph";
import { MakerMark } from "../shared/MakerMark";
import { seatFullName, seatLabel } from "../shared/seatName";
import { figureBox, SeatFigure } from "../shared/SeatFigure";
import { VoteMark } from "../shared/VoteMark";
import { minSec, ofSeats, wght } from "../shared/words";

type Mark = "agrees" | "differs";

const HEAD = 22;
const MARK = 16;
/** the maker's mark in a 22 px head: the same share of the head as at the table */
const LOGO = 12;
const WIDER = { ...wght.name, fontStretch: "106%" } as const;

const roundsWord = (n: number) => `${n} ${n === 1 ? "round" : "rounds"}`;

/**
 * A seat's mark in the line-up. Marks on the seats are wiped when a new round starts, so when
 * time runs out mid-round they are read back from the vote the answer's count comes from.
 */
function markOf(seat: SeatView, view: DebateView): Mark | null {
  if (seat.mark) return seat.mark;
  const { tally, answer } = view;
  if (!tally || !answer || tally.agree !== answer.agree || tally.seats !== answer.seats) return null;
  const group = tally.groups.find((g) => g.seatIds.includes(seat.id));
  if (!group) return null;
  return group.answerId === tally.leading ? "agrees" : "differs";
}

export function FoldedCard(p: { view: DebateView; open: boolean; onToggle: () => void }) {
  const { view } = p;
  const headingId = useId();
  const answer = view.answer;
  if (!answer) return null;

  const backed = ofSeats(answer.agree, answer.seats);
  const box = figureBox(HEAD);
  const timeUp = answer.outcome === "no-consensus";

  return (
    <section
      data-part="folded-card"
      data-outcome={answer.outcome}
      aria-labelledby={headingId}
      className="rounded-card border border-line bg-surface p-5"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 id={headingId} style={WIDER} className="flex items-center gap-2 text-heading text-ink">
            {answer.outcome === "agreed" ? (
              <>
                {/* the agreed colour never stands alone: it comes with the check and the word */}
                <CheckGlyph size={18} className="shrink-0 text-agreed" />
                <span>
                  <span className="text-agreed">Agreed</span> {backed}
                </span>
              </>
            ) : (
              `${timeUp ? "No consensus" : "Stopped"}, ${backed} backed this answer`
            )}
          </h2>
          <p className="mt-0.5 flex flex-wrap gap-x-3 text-bubble text-muted">
            {timeUp ? (
              <>
                {/* the clock is not said twice: when time ran out is how long it took */}
                <span>Time ran out at {minSec(answer.elapsedMs)}</span>
                <span>{roundsWord(answer.rounds)}</span>
              </>
            ) : (
              <span>
                {roundsWord(answer.rounds)}, {minSec(answer.elapsedMs)}
              </span>
            )}
          </p>
        </div>
        <Button aria-expanded={p.open} onClick={p.onToggle}>
          {p.open ? "Hide the debate" : "See the debate"}
        </Button>
      </div>

      <ul aria-label="How each seat voted" className="mt-4 flex flex-wrap gap-x-5.5 gap-y-3">
        {view.seats.map((seat) => {
          const mark = markOf(seat, view);
          return (
            // the name comes first for a reader; on screen it sits beneath its figure
            <li
              key={seat.id}
              className="flex w-11 flex-col-reverse items-center gap-0.5 font-medium text-ink text-meta"
            >
              <span title={seatFullName(seat)} className="whitespace-nowrap">
                {seatLabel(seat)}
              </span>
              <span className="relative mt-1.25 block">
                <SeatFigure seat={seat} index={seat.index} headD={HEAD} size="small" />
                {/* a small figure's head is drawn empty: the maker's mark goes on it here */}
                <MakerMark
                  seat={seat}
                  size={LOGO}
                  className={`absolute ${seat.status === "ready" ? "text-on-seat" : "text-muted"}`}
                  style={{ left: box.headCx - LOGO / 2, top: box.headCy - LOGO / 2 }}
                />
                {mark ? (
                  <span className="absolute block" style={{ left: box.markCx - MARK / 2, top: box.markCy - MARK / 2 }}>
                    <VoteMark mark={mark} size={MARK} />
                  </span>
                ) : null}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
