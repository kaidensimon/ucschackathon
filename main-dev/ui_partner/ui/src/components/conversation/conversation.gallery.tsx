import { useState } from "react";
import { fixtures } from "../../fixtures/lease";
import { type GalleryEntry, sampleView } from "../../gallery/entry";
import type { DebateView } from "../../lib/events";
import { wght } from "../shared/words";
import { Answer } from "./Answer";
import { FoldedCard } from "./FoldedCard";
import { Question } from "./Question";
import { SeatPickerBody } from "./SeatPicker";

const agreed = sampleView("lease", "released");
const timeUp = sampleView("lease-timeup", "released");
const seats = fixtures.lease?.seats ?? [];

// Sample Markdown, invented like the rest: the same answer, set out with a table, a list and a code block.
const LONG_ANSWER = `## What it costs

| Step | When | Cost |
| --- | --- | ---: |
| Send written notice | By 30 December 2026 | $0 |
| Pay one month's rent at the new rate | With the notice | $2,520 |
| Move out | By 28 February 2027 | $0 |

Before you send it, check two things:

1. The notice gives the date you leave.
2. It goes to the landlord named in the renewal letter.

An email counts as written notice. It can be this short:

\`\`\`text
I am ending my lease early.
My last day is 28 February 2027.
I will pay one month's rent, $2,520, as the renewal letter sets out.
\`\`\`
`;

const withText = (view: DebateView, text: string): DebateView => ({
  ...view,
  turns: view.turns.map((t) => (t.turnId === view.answer?.turnId ? { ...t, text } : t)),
});

const column = "max-w-160";

function CardDemo({ view, startOpen = false }: { view: DebateView; startOpen?: boolean }) {
  const [open, setOpen] = useState(startOpen);
  return (
    <div className={column}>
      <FoldedCard view={view} open={open} onToggle={() => setOpen((o) => !o)} />
    </div>
  );
}

/** The seat picker's sheet, drawn in place (the real one slides over the right edge of the window). */
function PickerDemo({ readOnly }: { readOnly: boolean }) {
  return (
    <div className="flex w-90 flex-col border border-line bg-surface p-6 text-ink">
      <p style={wght.name} className="text-heading">
        Seat the council
      </p>
      {readOnly ? <p className="mt-3 text-label text-muted">The council is in session</p> : null}
      <SeatPickerBody seats={seats} limitMs={agreed.limitMs} readOnly={readOnly} />
    </div>
  );
}

export const entries: GalleryEntry[] = [
  {
    name: "Question",
    note: "The owner's words, with the files and the time limit sent with them.",
    render: () => (
      <div className={column}>
        <Question question={agreed.question} files={agreed.files} limitMs={agreed.limitMs} />
      </div>
    ),
  },
  {
    name: "Folded card, agreed",
    note: "The vote is said here, once. The answer under it does not repeat it.",
    render: () => <CardDemo view={agreed} />,
  },
  {
    name: "Folded card, no consensus",
    note: "Marks come from the last vote taken before time ran out.",
    render: () => <CardDemo view={timeUp} />,
  },
  {
    name: "Folded card, debate open",
    render: () => <CardDemo view={agreed} startOpen />,
  },
  {
    name: "Answer, agreed",
    render: () => (
      <div className={column}>
        <Answer view={agreed} />
      </div>
    ),
  },
  {
    name: "Answer, no consensus",
    note: "One line for each seat that did not back the answer.",
    render: () => (
      <div className={column}>
        <Answer view={timeUp} />
      </div>
    ),
  },
  {
    name: "Answer, table and code block",
    render: () => (
      <div className={column}>
        <Answer view={withText(agreed, LONG_ANSWER)} />
      </div>
    ),
  },
  {
    name: "Seat picker",
    note: "Opens as a sheet at the right edge of the window.",
    render: () => <PickerDemo readOnly={false} />,
  },
  {
    name: "Seat picker, council in session",
    render: () => <PickerDemo readOnly />,
  },
];
