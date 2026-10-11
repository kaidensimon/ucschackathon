import { type GalleryEntry, sampleSeats, sampleView } from "../../gallery/entry";
import type { DebateView } from "../../lib/events";
import { LATER } from "./LaterPage";
import { announcement } from "./LiveRegion";
import { ShortcutsList } from "./ShortcutsSheet";
import { Sidebar } from "./Sidebar";
import { StatusPill } from "./StatusPill";
import { TopBar } from "./TopBar";

const caption = "text-meta text-muted";

const PILLS: { when: string; view: () => DebateView }[] = [
  { when: "Before a question", view: () => sampleView("lease", "asking") },
  { when: "Models loading", view: () => sampleView("lease", "spooling") },
  { when: "A model failed", view: () => sampleView("lease-failed", "failed") },
  { when: "Research", view: () => sampleView("lease", "researching") },
  { when: "Debate", view: () => sampleView("lease", "debating") },
  { when: "Just after a vote", view: () => sampleView("lease", "vote") },
  { when: "Paused", view: () => sampleView("lease", "paused") },
  { when: "Agreed, answer being written", view: () => sampleView("lease", "agreed") },
  { when: "Answer released", view: () => sampleView("lease", "released") },
  { when: "Time ran out", view: () => sampleView("lease-timeup", "released") },
];

const SPOKEN: [string, string, string, string][] = [
  ["A new round", "lease", "vote", "note-delivered"],
  ["A vote", "lease", "debating", "vote"],
  ["Agreement", "lease", "vote", "agreed"],
  ["The answer", "lease", "agreed", "released"],
];

export const entries: GalleryEntry[] = [
  {
    name: "StatusPill",
    note: "Parts set apart by space. Agreed and failed carry a mark as well as the word.",
    render: () => (
      <dl className="grid grid-cols-2 items-center gap-x-6 gap-y-3">
        {PILLS.map((p) => (
          <div key={p.when} className="contents">
            <dt className={caption}>{p.when}</dt>
            <dd>
              <StatusPill view={p.view()} />
            </dd>
          </div>
        ))}
      </dl>
    ),
  },
  {
    name: "ShortcutsSheet",
    note: "The list inside the sheet. Open the sheet itself with ? on any screen.",
    render: () => <ShortcutsList />,
  },
  {
    name: "TopBar",
    note: "Who is seated, in seat order, then the state of the debate.",
    wide: true,
    render: () => (
      <div className="flex flex-col gap-4">
        <div className="rounded-control border border-hairline">
          <TopBar
            seats={sampleView("lease", "debating").seats}
            pill={<StatusPill view={sampleView("lease", "debating")} />}
          />
        </div>
        <div className="rounded-control border border-hairline">
          <TopBar seats={sampleSeats(7)} pill={<StatusPill view={sampleView("lease-7", "vote")} />} />
        </div>
        <div className="rounded-control border border-hairline">
          <TopBar
            seats={sampleView("lease", "spooling").seats}
            pill={<StatusPill view={sampleView("lease", "spooling")} />}
          />
        </div>
      </div>
    ),
  },
  {
    name: "Sidebar",
    note: "240 px with words; a 64 px rail of icons when the window is under 1100 px wide.",
    render: () => (
      <div className="flex h-96 gap-8">
        <div className="flex rounded-control border border-hairline">
          <Sidebar wide onShortcuts={() => {}} />
        </div>
        <div className="flex rounded-control border border-hairline">
          <Sidebar wide={false} onShortcuts={() => {}} />
        </div>
      </div>
    ),
  },
  {
    name: "LaterPage",
    note: "What each sidebar item says until it is built.",
    render: () => (
      <dl className="flex flex-col gap-3">
        {Object.values(LATER).map((page) => (
          <div key={page.title}>
            <dt className="font-semibold text-ink text-label">{page.title}</dt>
            <dd className="text-label text-muted">{page.line}</dd>
          </div>
        ))}
      </dl>
    ),
  },
  {
    name: "Live region",
    note: "What a screen reader hears. Rounds, votes and the outcome only.",
    render: () => (
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3">
        {SPOKEN.map(([when, fixture, from, to]) => (
          <div key={when} className="contents">
            <dt className={caption}>{when}</dt>
            <dd className="text-ink text-label">{announcement(sampleView(fixture, from), sampleView(fixture, to))}</dd>
          </div>
        ))}
      </dl>
    ),
  },
];
