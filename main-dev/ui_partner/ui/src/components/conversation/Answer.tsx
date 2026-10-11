// The council's one answer, straight under the folded stage card (which says the vote).
//   the answer turn's words, as Markdown
//   "Files cited": each place in the owner's files the answer points at, once
//   one line per seat that did not back it: "Phi disagreed: ..."
import type { DebateView, TurnView } from "../../lib/events";
import { MakerMark } from "../shared/MakerMark";
import { seatFullName, seatLabel } from "../shared/seatName";
import { AnswerText } from "./AnswerText";
import { CitedChips, citedPlaces } from "./Cited";

export function Answer(p: { view: DebateView }) {
  const { view } = p;
  const answer = view.answer;
  // while the answer is still being written there is nothing to show: the stage is still up
  if (!answer) return null;

  const turn = view.turns.find((t) => t.turnId === answer.turnId);
  const places = citedPlaces(turn?.citations ?? [], view.files);
  const dissents = answer.dissentTurnIds
    .map((id) => view.turns.find((t) => t.turnId === id))
    .filter((t): t is TurnView => t !== undefined);

  return (
    <article data-part="answer" data-outcome={answer.outcome} aria-label="Answer">
      {turn ? <AnswerText text={turn.text} /> : null}

      {places.length > 0 ? (
        <div className="mt-5 flex items-start gap-2">
          <p className="flex h-6.5 shrink-0 items-center text-meta text-muted">Files cited</p>
          <CitedChips places={places} label="Files cited" />
        </div>
      ) : null}

      {dissents.length > 0 ? (
        <ul aria-label="Seats that disagreed" className="mt-5 flex flex-col gap-4 border-hairline border-t pt-4">
          {dissents.map((d) => {
            const own = citedPlaces(d.citations, view.files);
            const seat = view.seats.find((s) => s.id === d.seatId);
            const name = seat ? seatLabel(seat) : "A seat";
            return (
              <li key={d.turnId} data-part="dissent">
                <p className="text-ink text-label leading-5.5">
                  {seat ? <MakerMark seat={seat} size={16} className="mr-1.5 align-[-3px]" /> : null}
                  <span title={seat ? seatFullName(seat) : undefined} className="font-medium">
                    {name} disagreed:
                  </span>{" "}
                  {d.text}
                </p>
                {own.length > 0 ? (
                  <CitedChips places={own} label={`Files ${name} cited`} className="mt-1.5 flex flex-wrap gap-2" />
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </article>
  );
}
