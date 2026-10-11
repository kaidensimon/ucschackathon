import { useState } from "react";
import { type GalleryEntry, sampleView } from "../../gallery/entry";
import type { DebateView } from "../../lib/events";
import { ChatView } from "./ChatView";
import { Message } from "./Message";

/** Chat View at a fixed size, with a filter that works. */
function Demo({ view, width, filter = null }: { view: DebateView; width: number; filter?: string | null }) {
  const [seatId, setSeatId] = useState<string | null>(filter);
  return (
    <div className="overflow-x-auto">
      <div className="h-120" style={{ width }}>
        <ChatView view={view} width={width} filterSeatId={seatId} onFilter={setSeatId} />
      </div>
    </div>
  );
}

function OpenMessage() {
  const view = sampleView("lease", "debating");
  const open = view.turns.find((t) => !t.done);
  if (!open) return null;
  return (
    <div className="max-w-160 rounded-card border border-cv-rule bg-cv-paper p-5 text-cv-ink">
      <Message turn={open} seats={view.seats} files={view.files} />
    </div>
  );
}

export const entries: GalleryEntry[] = [
  {
    name: "Chat View, one thread",
    note: "The narrow window, or a large council: every message in time order. Black, white and grey only.",
    wide: true,
    render: () => <Demo view={sampleView("lease", "vote")} width={760} />,
  },
  {
    name: "Chat View, columns",
    note: "One column per seat when each gets 200 px or more. A round starts at the same height all the way across.",
    wide: true,
    render: () => <Demo view={sampleView("lease", "debating")} width={1040} />,
  },
  {
    name: "Chat View, one model",
    note: "The filter keeps one model's messages and every divider.",
    wide: true,
    render: () => <Demo view={sampleView("lease", "released")} width={760} filter="s3" />,
  },
  {
    name: "Chat View, message in progress",
    note: "The words so far, then Writing. The citation chips arrive when the turn ends.",
    render: () => <OpenMessage />,
  },
  {
    name: "Chat View, with your note",
    note: "A delivered note is a message from You at the start of its round.",
    wide: true,
    render: () => <Demo view={sampleView("lease", "note-delivered")} width={760} />,
  },
];
