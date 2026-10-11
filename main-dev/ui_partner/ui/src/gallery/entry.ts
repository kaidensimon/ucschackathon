// How a component shows itself in the gallery (#/gallery).
// Put a file named `<Something>.gallery.tsx` beside the component and export `entries`:
//
//   export const entries: GalleryEntry[] = [
//     { name: "Bubble", note: "two lines at most", render: () => <Bubble ... /> },
//   ];
//
// The gallery finds every such file by itself and wraps each entry in a box that carries
// data-gallery-entry="<name>". Names must be unique.
import type { ReactNode } from "react";
import { fixtures } from "../fixtures/lease";
import type { DebateView, SeatView } from "../lib/events";
import { viewAt } from "../lib/timeline/viewAt";
import { momentAt } from "../review/moments";

export interface GalleryEntry {
  name: string;
  /** one plain line under the name */
  note?: string;
  /** span the whole row (for wide pieces) */
  wide?: boolean;
  render: () => ReactNode;
}

/** The sample debate at a named moment, for gallery entries and tests. */
export function sampleView(fixtureId: string, scene: string): DebateView {
  const fixture = fixtures[fixtureId];
  const at = momentAt(fixtureId, scene);
  if (!fixture || at === undefined) throw new Error(`no sample ${fixtureId} at ${scene}`);
  return viewAt(fixture.events, at);
}

/** `n` seated, ready members of the seven-seat sample council. */
export function sampleSeats(n = 7): SeatView[] {
  return (fixtures["lease-7"]?.seats ?? [])
    .slice(0, n)
    .map((s) => ({ ...s, status: "ready", activity: "idle", mark: null, bubble: null }));
}
