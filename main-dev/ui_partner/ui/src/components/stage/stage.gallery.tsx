import { useState } from "react";
import { type GalleryEntry, sampleView } from "../../gallery/entry";
import type { DebateView } from "../../lib/events";
import { ChatView } from "../chatview/ChatView";
import { useNotYet } from "../shared/Notice";
import { TableView } from "../table/TableView";
import { FailedNotice } from "./FailedNotice";
import { Stage, type StageMode } from "./Stage";

function Demo({ view, live = true, failed = false }: { view: DebateView; live?: boolean; failed?: boolean }) {
  const [mode, setMode] = useState<StageMode>("table");
  const [notYet, poke] = useNotYet();
  return (
    <Stage
      view={view}
      mode={mode}
      onMode={setMode}
      live={live}
      notYet={notYet}
      onDead={poke}
      failure={
        failed ? { name: "Phi", reason: "Not enough free memory on the GX10. It needs 9 GB and 6 GB is free." } : null
      }
      className="h-120"
    >
      {(size) =>
        mode === "chat" ? (
          <ChatView view={view} width={size.width} filterSeatId={null} onFilter={() => {}} />
        ) : (
          <TableView view={view} width={size.width} height={size.height} onOpenSeat={() => {}} />
        )
      }
    </Stage>
  );
}

export const entries: GalleryEntry[] = [
  {
    name: "Stage, open",
    note: "The shell: it measures its body and owns the footer. Pause and Stop do nothing in the mock.",
    wide: true,
    render: () => <Demo view={sampleView("lease", "debating")} />,
  },
  {
    name: "Stage, paused",
    note: "Pause becomes Resume.",
    wide: true,
    render: () => <Demo view={sampleView("lease", "paused")} />,
  },
  {
    name: "Stage, a model failed",
    note: "The notice says what happened and offers what to do. Pause and Stop leave the footer.",
    wide: true,
    render: () => <Demo view={sampleView("lease-failed", "failed")} failed />,
  },
  {
    name: "Stage, reopened after the answer",
    note: "Folded is no stage at all: the folded card stands in its place. Reopened, only the switch is left.",
    wide: true,
    render: () => <Demo view={sampleView("lease", "released")} live={false} />,
  },
  {
    name: "FailedNotice",
    render: () => (
      <FailedNotice
        name="Phi"
        reason="Not enough free memory on the GX10. It needs 9 GB and 6 GB is free."
        others={4}
        onDead={() => {}}
      />
    ),
    wide: true,
  },
];
