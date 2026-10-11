// The chat screen, at one moment of the sample debate. It puts the pieces together and owns
// nothing but the keyboard: what is shown comes from useDebate() (the debate) and from the URL
// (?view= ?sheet= ?help= ?open= ?picker= ?filter=).
import { useMemo, useRef } from "react";
import { useNavigate } from "react-router";
import { ChatView } from "../components/chatview/ChatView";
import { Composer } from "../components/composer/Composer";
import { Answer } from "../components/conversation/Answer";
import { FoldedCard } from "../components/conversation/FoldedCard";
import { Question } from "../components/conversation/Question";
import { SeatPicker } from "../components/conversation/SeatPicker";
import { AppFrame } from "../components/frame/AppFrame";
import { useUrlState } from "../components/frame/hooks";
import { LiveRegion } from "../components/frame/LiveRegion";
import { StatusPill } from "../components/frame/StatusPill";
import { TopBar } from "../components/frame/TopBar";
import { useShortcuts } from "../components/frame/useShortcuts";
import { useNotYet } from "../components/shared/Notice";
import { seatLabel } from "../components/shared/seatName";
import { wght } from "../components/shared/words";
import { Stage, type StageMode, type StageSize } from "../components/stage/Stage";
import { SeatSheet } from "../components/table/SeatSheet";
import { TableView } from "../components/table/TableView";
import { useEngineLive } from "../engine/EngineProvider";
import { bySeats, COUNCIL_MAX, COUNCIL_MIN, fixtures } from "../fixtures/lease";
import { useDebate } from "../hooks/useDebate";
import type { DebateEvent, SeatView } from "../lib/events";
import { viewAt } from "../lib/timeline/viewAt";
import { momentAt } from "../review/moments";
import { useSeatChoice } from "./chat/ChatTopBar";

type Created = Extract<DebateEvent, { type: "debate.created" }>;
type SeatStatusEvent = Extract<DebateEvent, { type: "seat.status" }>;

/** `fresh` is the empty chat at #/sample/new: no question asked yet. */
export function ChatScreen({ fresh = false }: { fresh?: boolean }) {
  const debate = useDebate();
  const [search, change] = useUrlState();
  const [notYet, poke] = useNotYet();
  const message = useRef<HTMLTextAreaElement>(null);
  const navigate = useNavigate();

  // a new chat has no debate yet: its council is the one the slider last asked for (?seats=)
  const wanted = fresh ? bySeats[Number(search.get("seats"))] : undefined;
  const events = (wanted ? fixtures[wanted] : debate.fixture)?.events;
  const created = useMemo(() => events?.find((e): e is Created => e.type === "debate.created"), [events]);
  const nothingYet = useMemo(() => viewAt([], 0), []);
  const view = fresh || !debate.view ? nothingYet : debate.view;

  const idle = view.phase === "idle";
  const released = view.answer !== undefined;
  const live = !idle && !released;
  const open = search.get("open") === "1";
  const mode: StageMode = search.get("view") === "chat" ? "chat" : "table";
  const sheet = live || open ? search.get("sheet") : null;
  const filter = search.get("filter");
  const help = search.get("help") === "1";
  const asking = idle && !fresh && debate.scene === "asking";
  const picker = search.get("picker") === "1" || (asking && search.get("picker") !== "0");
  const stageShown = live || (released && open);

  // With the real engine the owner chooses only how many sit; the router picks who, so before a
  // debate the seats are blank. With the stand-in the council is the one that would be seated.
  const engineLive = useEngineLive();
  const [chosen, choose] = useSeatChoice();
  const blank = engineLive && view.seats.length === 0;
  const seats: SeatView[] = useMemo(() => {
    if (view.seats.length > 0) return view.seats;
    if (blank) {
      return Array.from(
        { length: chosen },
        (_, i): SeatView => ({
          id: `seat-${i + 1}`,
          index: i,
          shortName: `Seat ${i + 1}`,
          modelName: "",
          status: "ready",
          activity: "idle",
          mark: null,
          bubble: null,
        }),
      );
    }
    return (created?.seats ?? []).map((s) => ({ ...s, status: "ready", activity: "idle", mark: null, bubble: null }));
  }, [view.seats, created, blank, chosen]);
  const limitMs = view.limitMs || created?.limitMs || 0;

  const failedSeat = live ? view.seats.find((s) => s.status === "failed") : undefined;
  const failure = useMemo(() => {
    if (!failedSeat) return null;
    const event = events?.findLast(
      (e): e is SeatStatusEvent => e.type === "seat.status" && e.seatId === failedSeat.id && e.status === "failed",
    );
    return { name: seatLabel(failedSeat), reason: event?.reason ?? "The model could not be started." };
  }, [failedSeat, events]);

  const closePicker = () => change({ picker: asking ? "0" : null });

  useShortcuts((s) => {
    const somethingOpen = help || sheet !== null || picker;
    if (s.kind === "close") {
      if (help) change({ help: null });
      else if (sheet !== null) change({ sheet: null });
      else if (picker) closePicker();
      return somethingOpen;
    }
    if (somethingOpen) return false; // a sheet is open: its own keys only
    switch (s.kind) {
      case "help":
        change({ help: "1" });
        return true;
      case "message":
        message.current?.focus();
        return true;
      case "view":
        if (!stageShown) return false;
        change({ view: s.view });
        return true;
      case "pause":
        if (!live) return false;
        poke();
        return true;
      case "seat": {
        const seat = stageShown ? view.seats[s.index] : undefined;
        if (!seat) return false;
        change({ sheet: seat.id });
        return true;
      }
    }
    return false;
  });

  const composer = (
    <Composer
      // a new moment of the sample is a new box: the draft is not carried over
      key={`${debate.fixtureId}:${fresh ? "new" : (debate.scene ?? "")}`}
      mode={live ? "note" : "ask"}
      seats={seats.length}
      limitMs={limitMs}
      onOpenPicker={() => change({ picker: "1" })}
      draft={asking ? created?.question : ""}
      files={asking ? created?.files : []}
      queued={live ? view.notes.findLast((n) => n.state === "queued") : null}
      inputRef={message}
    />
  );

  const inside = (size: StageSize) =>
    mode === "chat" ? (
      <ChatView
        view={view}
        width={size.width}
        filterSeatId={filter}
        onFilter={(seatId) => change({ filter: seatId })}
      />
    ) : (
      <TableView
        view={view}
        width={size.width}
        height={size.height}
        onOpenSeat={(seatId) => change({ sheet: seatId })}
      />
    );
  const stage = (
    <Stage
      view={view}
      mode={mode}
      onMode={(next) => change({ view: next })}
      live={live}
      failure={failure}
      notYet={notYet}
      onDead={poke}
      dock={live ? composer : undefined}
      className={live ? "mx-auto mt-2 w-full max-w-260 flex-1" : "mx-auto mt-6 h-151.5 w-full max-w-260 shrink-0"}
    >
      {inside}
    </Stage>
  );

  // The slider in the top bar seats a council of another size: the sample debate for that many
  // seats, at the same moment where it has one (mid-debate where it has not).
  const onSeats = (count: number) => {
    if (blank) {
      // blank seats: the size is the one number the owner chooses (it is what a question is sent with)
      choose(count);
      return;
    }
    const id = bySeats[count];
    if (!id) return;
    if (fresh) {
      // a new chat stays a new chat (and keeps what is typed): only its would-be council changes
      change({ seats: String(count) });
      return;
    }
    const next = new URLSearchParams(search);
    const exact = next.has("at");
    for (const gone of ["at", "sheet", "filter", "picker"]) next.delete(gone);
    const scene = next.get("scene");
    // before the question is sent the seat picker would open by itself: keep it shut while sliding
    if (scene === "asking") next.set("picker", "0");
    // a moment the other debate does not have (or an exact instant, which is this debate's own)
    else if (scene ? momentAt(id, scene) === undefined : exact) next.set("scene", "debating");
    const query = next.toString();
    navigate({ pathname: `/sample/${id}`, search: query ? `?${query}` : "" }, { replace: true });
  };

  return (
    <AppFrame
      top={
        <TopBar
          seats={seats}
          onCouncil={() => change({ picker: "1" })}
          onSeats={onSeats}
          sizes={{ min: COUNCIL_MIN, max: COUNCIL_MAX }}
          pill={<StatusPill view={view} />}
        />
      }
    >
      <div data-part="chat-screen" className="flex h-full flex-col">
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-6">
          {idle ? (
            <div className="flex flex-1 items-center justify-center pb-16">
              <h1 style={wght.title} className="text-center text-ink text-title">
                What should the council settle?
              </h1>
            </div>
          ) : (
            <div className="mx-auto w-full max-w-160 shrink-0 pt-6">
              <Question question={view.question} files={view.files} limitMs={view.limitMs} />
            </div>
          )}
          {live ? <div className="flex min-h-0 flex-1 flex-col pb-7">{stage}</div> : null}
          {released ? (
            <>
              <div className="mx-auto mt-7 w-full max-w-160 shrink-0">
                <FoldedCard view={view} open={open} onToggle={() => change({ open: open ? null : "1" })} />
              </div>
              {open ? stage : null}
              <div className="mx-auto mt-7 w-full max-w-160 shrink-0 pb-6">
                <Answer view={view} />
              </div>
            </>
          ) : null}
        </div>
        {live ? null : (
          <div className="shrink-0 px-6 pt-3 pb-7">
            <div className="mx-auto w-full max-w-160">{composer}</div>
          </div>
        )}
      </div>
      <SeatSheet view={view} seatId={sheet} onClose={() => change({ sheet: null })} />
      <SeatPicker
        seats={engineLive ? view.seats : (created?.seats ?? [])}
        ran={engineLive && view.seats.length > 0}
        limitMs={limitMs}
        open={picker}
        onOpenChange={(next) => (next ? change({ picker: "1" }) : closePicker())}
        readOnly={live}
      />
      <LiveRegion view={view} />
    </AppFrame>
  );
}
