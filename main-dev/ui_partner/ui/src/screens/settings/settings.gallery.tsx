import { useMemo } from "react";
import type { ModelState } from "../../engine/client";
import { EngineProvider } from "../../engine/EngineProvider";
import { FakeEngine } from "../../engine/fake";
import type { GalleryEntry } from "../../gallery/entry";
import { SettingsBody } from "./SettingsPage";

/** The screen without its frame, on a stand-in of its own, so one entry cannot change another. */
function Sample({ model = "ready" }: { model?: ModelState }) {
  const engine = useMemo(() => new FakeEngine({ wordMs: 0, modelState: model }), [model]);
  return (
    <div className="h-150 rounded-control border border-hairline">
      <EngineProvider engine={engine}>
        <SettingsBody />
      </EngineProvider>
    </div>
  );
}

export const entries: GalleryEntry[] = [
  {
    name: "Settings",
    note: "Theme, the model's state (read only), how answers are written, and what this build is.",
    wide: true,
    render: () => <Sample />,
  },
  {
    name: "Settings, no model",
    note: "What the Model part says when nothing answers: a mark and the words.",
    wide: true,
    render: () => <Sample model="unreachable" />,
  },
];
