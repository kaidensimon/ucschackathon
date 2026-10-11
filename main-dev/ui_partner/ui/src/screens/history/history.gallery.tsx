import { useMemo, useState } from "react";
import { Button } from "../../components/shared/Button";
import type { ChatSummary } from "../../engine/client";
import { EngineProvider } from "../../engine/EngineProvider";
import { FakeEngine } from "../../engine/fake";
import type { GalleryEntry } from "../../gallery/entry";
import { DeleteDialog } from "./dialogs";
import { HistoryList } from "./HistoryList";

// the stand-in's own clock: the sample chats are 30 minutes, 26 hours and 6 days older
const NOW = "2026-10-10T18:00:00.000Z";

/** The list without its frame, on a stand-in of its own, so one entry cannot change another. */
function Sample({ empty = false, query }: { empty?: boolean; query?: string }) {
  const engine = useMemo(() => new FakeEngine({ wordMs: 0, empty, now: NOW }), [empty]);
  return (
    <div className="h-120 rounded-control border border-hairline">
      <EngineProvider engine={engine}>
        <HistoryList initialQuery={query} now={new Date(NOW)} />
      </EngineProvider>
    </div>
  );
}

const SAMPLE_CHAT: ChatSummary = {
  id: "sample",
  title: "Ending the lease early",
  pinned: true,
  createdAt: NOW,
  updatedAt: NOW,
  messageCount: 4,
  preview: "",
  match: null,
};

function DeleteDemo() {
  const [chat, setChat] = useState<ChatSummary | null>(null);
  const [said, setSaid] = useState("Nothing is deleted here.");
  return (
    <div className="flex flex-wrap items-center gap-4">
      <Button id="show-delete-dialog" onClick={() => setChat(SAMPLE_CHAT)}>
        Show the dialog
      </Button>
      <span className="text-meta text-muted">{said}</span>
      <DeleteDialog
        chat={chat}
        onDelete={() => setSaid("Pressed Delete chat.")}
        onClose={() => setChat(null)}
        onClosed={() => document.getElementById("show-delete-dialog")?.focus()}
      />
    </div>
  );
}

export const entries: GalleryEntry[] = [
  {
    name: "History, list",
    note: "Each chat under one plain heading. The title is the link; the menu beside it renames, pins, exports and deletes.",
    wide: true,
    render: () => <Sample />,
  },
  {
    name: "History, search with no hits",
    note: "The line names what was searched for.",
    render: () => <Sample query="zebra" />,
  },
  {
    name: "History, no chats",
    note: "An empty list says so and offers the way to start.",
    render: () => <Sample empty />,
  },
  {
    name: "History, delete dialog",
    note: "Asks first. Focus starts on Keep it; Esc keeps too.",
    render: () => <DeleteDemo />,
  },
];
