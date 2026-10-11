// The window: top bar across, sidebar at the left, the screen in the rest.
// The shortcuts sheet belongs to the frame, so every screen has it (?help=1 in the URL).
import type { ReactNode } from "react";
import { useUrlState } from "./hooks";
import { ShortcutsSheet } from "./ShortcutsSheet";
import { Sidebar } from "./Sidebar";

export function AppFrame({ top, children }: { top: ReactNode; children: ReactNode }) {
  const [search, change] = useUrlState();
  const help = search.get("help") === "1";
  return (
    <div data-part="app-frame" className="flex h-full flex-col overflow-hidden bg-page text-ink">
      {top}
      <div className="flex min-h-0 flex-1">
        <Sidebar onShortcuts={() => change({ help: "1" })} />
        <main className="relative min-w-0 flex-1">{children}</main>
      </div>
      <ShortcutsSheet open={help} onOpenChange={(open) => change({ help: open ? "1" : null })} />
    </div>
  );
}
