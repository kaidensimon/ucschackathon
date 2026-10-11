import { Paperclip, X } from "lucide-react";
import { useState } from "react";
import { type GalleryEntry, sampleSeats } from "../../gallery/entry";
import type { SeatView } from "../../lib/events";
import { Button } from "./Button";
import { Chip } from "./Chip";
import { IconButton } from "./IconButton";
import { Meter } from "./Meter";
import { Notice, useNotYet } from "./Notice";
import { figureBox, SeatFigure } from "./SeatFigure";
import { seatFullName } from "./seatName";
import { Switch } from "./Switch";
import { Tooltip } from "./Tooltip";
import { VoteMark } from "./VoteMark";
import { NOT_YET } from "./words";

const row = "flex flex-wrap items-center gap-4";
const caption = "text-meta text-muted";

const seats = sampleSeats(7);
const seat = (i: number, change: Partial<SeatView> = {}): SeatView => ({ ...(seats[i] as SeatView), ...change });

/** the council's eight models as the backend names them; the short names are cut to 7 characters, as a Seat's are */
const council: SeatView[] = [
  "gpt-oss 20B",
  "DeepSeek R1 14B",
  "Qwen3 14B",
  "Qwen3.5 9B",
  "Phi-4 14B",
  "Gemma 4 12B",
  "Granite 4.1 8B",
  "Falcon3 10B",
].map((modelName, i) => seat(i % 7, { id: `council-${i}`, index: i, shortName: modelName.slice(0, 7), modelName }));

function Labelled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <figure className="flex flex-col items-center gap-3">
      {children}
      <figcaption className={caption}>{label}</figcaption>
    </figure>
  );
}

/** A figure with its vote mark at the head's upper outer side, as the table places it. */
function Voted({ index, mark, ink = false }: { index: number; mark: "agrees" | "differs"; ink?: boolean }) {
  const box = figureBox(72);
  return (
    <div className="relative">
      <SeatFigure seat={seat(index, { mark })} index={index} headD={72} variant={ink ? "ink" : "colour"} />
      <div className="absolute" style={{ left: box.markCx - 13, top: box.markCy - 13 }}>
        <VoteMark mark={mark} size={26} variant={ink ? "ink" : "colour"} />
      </div>
    </div>
  );
}

function SwitchDemo() {
  const [view, setView] = useState<"table" | "chat">("table");
  return (
    <Switch
      label="View"
      value={view}
      onChange={setView}
      options={[
        { value: "table", label: "Table" },
        { value: "chat", label: "Chat" },
      ]}
    />
  );
}

function DeadDemo() {
  const [shown, poke] = useNotYet();
  return (
    <div className={row}>
      <Button onClick={poke}>Stop</Button>
      {shown ? <Notice>{NOT_YET}</Notice> : <span className={caption}>Press it: the line shows for 4 seconds.</span>}
    </div>
  );
}

export const entries: GalleryEntry[] = [
  {
    name: "Button",
    note: "A line edge on paper. One ink button per group. Small is 30 px tall.",
    render: () => (
      <div className={row}>
        <Button>Pause</Button>
        <Button variant="ink">Add to next round</Button>
        <Button size="small">5 seats, 5 min</Button>
        <Button disabled>Add a seat</Button>
      </div>
    ),
  },
  {
    name: "IconButton",
    note: "Always has a spoken label and a tooltip.",
    render: () => (
      <div className={row}>
        <IconButton label="Attach files">
          <Paperclip size={18} aria-hidden="true" />
        </IconButton>
        <IconButton label="Close">
          <X size={18} aria-hidden="true" />
        </IconButton>
        <IconButton label="Attach files" disabled>
          <Paperclip size={18} aria-hidden="true" />
        </IconButton>
      </div>
    ),
  },
  {
    name: "Switch",
    note: "Two options, one always chosen. Arrow keys move, Enter chooses.",
    render: () => <SwitchDemo />,
  },
  {
    name: "Chip",
    note: "A file, a cited page, and the same in Chat View greys.",
    render: () => (
      <div className={row}>
        <Chip kind="file" label="Lease 2025.pdf" detail="14 pages" />
        <Chip kind="citation" label="Renewal letter 2026.pdf" detail="page 1" />
        <span className="rounded-control bg-cv-paper p-2">
          <Chip kind="citation" label="Lease 2025.pdf" detail="page 9" variant="ink" />
        </span>
      </div>
    ),
  },
  {
    name: "Chip, council file",
    note: "Arrives with Phase 6",
    render: () => <Chip kind="citation" label="council.md" detail="L7" />,
  },
  {
    name: "Tooltip",
    note: "Shows 300 ms after the pointer or the keyboard reaches the control.",
    render: () => (
      <Tooltip label="Choose the seats and the time limit">
        <Button size="small">5 seats, 5 min</Button>
      </Tooltip>
    ),
  },
  {
    name: "Notice",
    note: "One quiet line. The error tone adds its mark.",
    render: () => (
      <div className="flex flex-col gap-3">
        <Notice>{NOT_YET}</Notice>
        <Notice>Reaches the council at the start of round 3</Notice>
        <Notice tone="error">Phi did not load</Notice>
        <DeadDemo />
      </div>
    ),
  },
  {
    name: "VoteMark",
    note: "Agrees: solid ink disc with a check. Disagrees: outlined disc with a cross. Never red.",
    render: () => (
      <div className={row}>
        <VoteMark mark="agrees" size={26} />
        <VoteMark mark="differs" size={26} />
        <VoteMark mark="agrees" size={16} />
        <VoteMark mark="differs" size={16} />
        <span className="flex gap-4 rounded-control bg-cv-paper p-2">
          <VoteMark mark="agrees" size={26} variant="ink" />
          <VoteMark mark="differs" size={26} variant="ink" />
        </span>
      </div>
    ),
  },
  {
    name: "Meter",
    note: "One pip per seat. The upright mark stands after the pip that reaches the number needed.",
    render: () => (
      <dl className="grid grid-cols-2 items-center gap-x-6 gap-y-3">
        <dt className={caption}>No vote yet, needs 4 of 5</dt>
        <dd>
          <Meter agree={0} seats={5} needed={4} reached={false} />
        </dd>
        <dt className={caption}>2 of 5 agree, needs 4</dt>
        <dd>
          <Meter agree={2} seats={5} needed={4} reached={false} />
        </dd>
        <dt className={caption}>Agreed 4 of 5</dt>
        <dd>
          <Meter agree={4} seats={5} needed={4} reached={true} />
        </dd>
        <dt className={caption}>3 seats, needs 3</dt>
        <dd>
          <Meter agree={2} seats={3} needed={3} reached={false} />
        </dd>
        <dt className={caption}>4 of 7 agree, needs 6</dt>
        <dd>
          <Meter agree={4} seats={7} needed={6} reached={false} />
        </dd>
        <dt className={caption}>Pill size</dt>
        <dd className="flex items-center gap-6">
          <Meter agree={3} seats={5} needed={4} reached={false} size="pill" />
          <Meter agree={4} seats={5} needed={4} reached={true} size="pill" />
        </dd>
      </dl>
    ),
  },
  {
    name: "SeatFigure, states",
    note: "Every state has a shape and a word.",
    wide: true,
    render: () => (
      <div className="flex flex-wrap items-end gap-x-10 gap-y-8 pt-4">
        <Labelled label="Seated">
          <SeatFigure seat={seat(2)} index={2} headD={72} />
        </Labelled>
        <Labelled label="Speaking">
          <SeatFigure seat={seat(3, { activity: "speaking" })} index={3} headD={72} speaking />
        </Labelled>
        <Labelled label="Keyboard focus">
          <SeatFigure seat={seat(4)} index={4} headD={72} focused />
        </Labelled>
        <Labelled label="Agrees">
          <Voted index={1} mark="agrees" />
        </Labelled>
        <Labelled label="Disagrees">
          <Voted index={0} mark="differs" />
        </Labelled>
        <Labelled label="Not ready">
          <SeatFigure seat={seat(5, { status: "loading" })} index={5} headD={72} />
        </Labelled>
        <Labelled label="Did not load">
          <SeatFigure seat={seat(0, { status: "failed" })} index={0} headD={72} />
        </Labelled>
      </div>
    ),
  },
  {
    name: "SeatFigure, head sizes",
    note: "The maker's logo in the head, the name across the body: 17 px under a 72 head, 15 under 64, 13 under 56. Names are fitted by width, and shrunk only in a very small figure.",
    wide: true,
    render: () => (
      <div className="flex flex-wrap items-end gap-8">
        {[72, 64, 56].map((d) => (
          <Labelled key={d} label={`${d} px head`}>
            <div className="flex items-end gap-4">
              <SeatFigure seat={seat(0)} index={0} headD={d} />
              <SeatFigure seat={seat(6)} index={6} headD={d} />
            </div>
          </Labelled>
        ))}
        <Labelled label="Small and tiny, speaking and not ready">
          <div className="flex items-end gap-4">
            <SeatFigure seat={seat(3)} index={3} headD={22} size="small" speaking />
            <SeatFigure seat={seat(4, { status: "loading" })} index={4} headD={22} size="small" />
            <SeatFigure seat={seat(0, { status: "failed" })} index={0} headD={22} size="small" />
            <SeatFigure seat={seat(1, { status: "loading" })} index={1} headD={14} size="tiny" />
          </div>
        </Labelled>
      </div>
    ),
  },
  {
    name: "SeatFigure, the council's models",
    note: "The eight models on the box, each under its maker's logo, at the three table head sizes. The name is the model's own (seatLabel), and a name of 8 letters or more is lettered a little smaller.",
    wide: true,
    render: () => (
      <div className="flex flex-col gap-8">
        {[72, 64, 56].map((d) => (
          <Labelled key={d} label={`${d} px head`}>
            <div className="flex flex-wrap items-end gap-4">
              {council.map((s) => (
                <span key={s.id} title={seatFullName(s)}>
                  <SeatFigure seat={s} index={s.index} headD={d} />
                </span>
              ))}
            </div>
          </Labelled>
        ))}
      </div>
    ),
  },
  {
    name: "SeatFigure, ink",
    note: "For Chat View: an outline drawing in black, white and grey only.",
    wide: true,
    render: () => (
      <div className="flex flex-wrap items-end gap-8 rounded-control bg-cv-paper p-5 pt-8 text-cv-ink">
        {seats.slice(0, 4).map((s) => (
          <SeatFigure key={s.id} seat={s} index={s.index} headD={64} variant="ink" speaking={s.index === 2} />
        ))}
        <Voted index={4} mark="agrees" ink />
        <SeatFigure seat={seat(5, { status: "loading" })} index={5} headD={64} variant="ink" />
        <div className="flex items-end gap-3">
          {seats.slice(0, 3).map((s) => (
            <SeatFigure key={s.id} seat={s} index={s.index} headD={22} size="small" variant="ink" />
          ))}
        </div>
      </div>
    ),
  },
];
