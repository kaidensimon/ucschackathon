// The debate behind an answer, in the same Stage the sample uses. Only there with the real
// council engine; with the stand-in it draws nothing.
//   - while the answer is being written: the debate as it happens;
//   - after it: the finished debate of the newest answer, to read (it is fetched again, and
//     replays, when the chat is opened later), until the next question is sent;
//   - before the debate has its seats: the council that was asked for, as empty seats.
import { useMemo, useState } from "react";
import { ChatView } from "../../components/chatview/ChatView";
import { Button } from "../../components/shared/Button";
import { Stage, type StageMode } from "../../components/stage/Stage";
import { TableView } from "../../components/table/TableView";
import { liveViewOf, useLiveClock, useLiveDebate } from "../../engine/useLiveDebate";
import type { DebateView, SeatView } from "../../lib/events";

const nothing = () => {};

export const HIDE_DEBATE = "Hide the debate";
export const SHOW_DEBATE = "Show the debate";

/**
 * A table of `count` seats nobody has been given yet: the council the owner asked for.
 * `seating`: the question has been sent and the models are being chosen and loaded.
 */
export function waitingView(count: number, seating: boolean): DebateView {
  const seats: SeatView[] = Array.from({ length: Math.max(0, Math.round(count)) }, (_, i): SeatView => ({
    id: `seat-${i + 1}`,
    index: i,
    shortName: `Seat ${i + 1}`,
    modelName: "Chosen when you ask",
    status: seating ? "loading" : "ready",
    activity: "idle",
    mark: null,
    bubble: null,
  }));
  return {
    phase: seating ? "spooling" : "idle",
    paused: false,
    round: 0,
    clock: 0,
    leftMs: 0,
    limitMs: 0,
    question: "",
    files: [],
    seats,
    speaking: [],
    tally: null,
    turns: [],
    notes: [],
  };
}

export function LiveStage({
  runId,
  running = runId !== null,
  seats = 0,
  waiting = null,
}: {
  /** the run whose debate is shown: the one being written, or the newest finished one */
  runId: string | null;
  /** the run is still going; false for a finished debate, which can be folded away */
  running?: boolean;
  /** the council size the owner chose: what is drawn until the debate has seats of its own */
  seats?: number;
  /** what to draw without a debate: "idle" before a question, "seating" just after one, null for nothing */
  waiting?: "idle" | "seating" | null;
}) {
  const debate = useLiveDebate(runId);
  // real time, carried on between events while the run is live: notes fade in and the clock runs
  const at = useLiveClock(debate.events, debate.live);
  const real = useMemo(() => liveViewOf(debate.events, at), [debate.events, at]);
  const empty = useMemo(
    () => (waiting && seats > 0 ? waitingView(seats, waiting === "seating") : null),
    [waiting, seats],
  );
  const [mode, setMode] = useState<StageMode>("table");
  const [filter, setFilter] = useState<string | null>(null);
  // a finished debate can be folded away, so the answer has the whole page
  const [hidden, setHidden] = useState<string | null>(null);

  const view = real ?? empty;
  if (!view) return null;
  const finished = real !== null && !running;
  if (finished && hidden === runId) {
    return (
      <div data-part="live-stage" data-state="hidden" className="flex shrink-0 justify-center px-6 pt-2">
        <Button size="small" onClick={() => setHidden(null)}>
          {SHOW_DEBATE}
        </Button>
      </div>
    );
  }
  // seats nobody sits in yet have nothing to say: the table only
  const shown: StageMode = real ? mode : "table";
  return (
    <div
      data-part="live-stage"
      data-state={real ? (finished ? "finished" : "live") : "waiting"}
      data-seats={view.seats.length}
      className="flex min-h-0 flex-[2] flex-col px-6 pt-2"
    >
      {finished ? (
        <div className="mx-auto flex w-full max-w-260 shrink-0 justify-end">
          <Button size="small" onClick={() => setHidden(runId)}>
            {HIDE_DEBATE}
          </Button>
        </div>
      ) : null}
      {/* live={false}: Pause and Stop are not wired here; the message box has Stop */}
      <Stage
        view={view}
        mode={shown}
        onMode={real ? setMode : nothing}
        live={false}
        onDead={nothing}
        className="mx-auto w-full max-w-260 flex-1"
      >
        {(size) =>
          shown === "chat" ? (
            <ChatView view={view} width={size.width} filterSeatId={filter} onFilter={setFilter} />
          ) : (
            <TableView view={view} width={size.width} height={size.height} onOpenSeat={nothing} />
          )
        }
      </Stage>
    </div>
  );
}
