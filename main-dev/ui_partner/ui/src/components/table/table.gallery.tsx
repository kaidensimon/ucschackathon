import { useReducer } from "react";
import { type GalleryEntry, sampleView } from "../../gallery/entry";
import type { BubbleView, DebateView } from "../../lib/events";
import { Bubble, BubbleProbe, bubbleSize, needsProbe } from "./Bubble";
import { SeatSheetBody } from "./SeatSheet";
import { TableView } from "./TableView";

/** The study's stage. The table is drawn at a fixed size here; the row scrolls sideways if it must. */
const W = 1040;
const H = 558;
/** the widest bubble at a table of five */
const MAX = 280;

function Table({ view }: { view: DebateView }) {
  return (
    <div className="overflow-x-auto">
      <div className="relative" style={{ width: W, height: H }}>
        <TableView view={view} width={W} height={H} onOpenSeat={() => {}} />
      </div>
    </div>
  );
}

/** The stress case the engine has not ruled out: every seat with an open turn and a line showing. */
function everyoneSpeaking(): DebateView {
  const view = sampleView("lease", "debating");
  const lines = [
    "Says the landlord never signed the letter.",
    "Holds that a letter cannot change the lease.",
    "Tells Mistral the fee is one month at the new rent.",
    "Cites the renewal letter, page 1: fee is one month.",
    "Now agrees: one month, not two.",
  ];
  return {
    ...view,
    speaking: view.seats.map((s) => s.id),
    seats: view.seats.map((s, i) => ({
      ...s,
      activity: "speaking",
      bubble: { summaryId: `all-${i}`, text: lines[i] ?? "", opacity: 1 },
    })),
  };
}

function BubbleStage({ bubble, word }: { bubble: BubbleView; word: string }) {
  // measured as at the table, so the specimen is as tight round its words as the real one
  const [, measuredAgain] = useReducer((count: number) => count + 1, 0);
  const size = bubbleSize(bubble.text, MAX);
  return (
    <figure className="flex flex-col gap-3">
      <div className="relative" style={{ width: size.w, height: size.h + 8 }}>
        <Bubble bubble={bubble} left={0} top={0} size={size} tail={size.w / 2} />
        {needsProbe(bubble.text, MAX) ? (
          <BubbleProbe text={bubble.text} maxWidth={MAX} onMeasured={measuredAgain} />
        ) : null}
      </div>
      <figcaption className="text-meta text-muted">{word}</figcaption>
    </figure>
  );
}

const LINE = "Cites the renewal letter, page 1: fee is one month.";

export const entries: GalleryEntry[] = [
  {
    name: "Table, 5 seats",
    note: "Mid-debate, one seat speaking. Each seat is one button: Left and Right move, Enter opens its sheet.",
    wide: true,
    render: () => <Table view={sampleView("lease", "debating")} />,
  },
  {
    name: "Table, 3 seats",
    wide: true,
    render: () => <Table view={sampleView("lease-3", "debating")} />,
  },
  {
    name: "Table, 7 seats",
    note: "Smaller heads, one name size for the whole council.",
    wide: true,
    render: () => <Table view={sampleView("lease-7", "vote")} />,
  },
  {
    name: "Table, every seat speaking",
    note: "A ring per speaking seat. No bubble touches another bubble or a figure.",
    wide: true,
    render: () => <Table view={everyoneSpeaking()} />,
  },
  {
    name: "Table, just after a vote",
    note: "A mark on each head's outer side: check agrees, cross disagrees.",
    wide: true,
    render: () => <Table view={sampleView("lease", "vote")} />,
  },
  {
    name: "Table, seats still loading",
    note: "A seat that is not ready is a dashed outline with the word.",
    wide: true,
    render: () => <Table view={sampleView("lease", "spooling")} />,
  },
  {
    name: "Bubble",
    note: "It follows the debate clock: in over 250 ms, stays 8 s, out over 1.5 s. Two lines at most.",
    render: () => (
      <div className="flex flex-wrap items-start gap-8">
        <BubbleStage bubble={{ summaryId: "full", text: LINE, opacity: 1 }} word="Showing" />
        <BubbleStage bubble={{ summaryId: "half", text: LINE, opacity: 0.5 }} word="Half way out" />
        <BubbleStage
          bubble={{ summaryId: "short", text: "Now agrees: one month, not two.", opacity: 1 }}
          word="One line"
        />
      </div>
    ),
  },
  {
    name: "Seat sheet",
    note: "Opens from a seat, at the right edge of the window. Esc closes it.",
    render: () => {
      const view = sampleView("lease", "debating");
      const seat = view.seats[3];
      if (!seat) return null;
      return (
        <div className="flex h-140 w-110 max-w-full flex-col border border-line bg-surface text-ink">
          <SeatSheetBody view={view} seat={seat} />
        </div>
      );
    },
  },
];
