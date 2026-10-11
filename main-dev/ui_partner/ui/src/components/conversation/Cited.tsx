// The places in the owner's files that a turn points at, as chips: "Lease 2025.pdf, page 9".
import type { Citation, FileRef } from "../../lib/events";
import { Chip } from "../shared/Chip";

export interface CitedPlace {
  key: string;
  label: string;
  detail?: string;
}

/**
 * One entry per file and page, in the order first cited. A citation of a file that is not
 * among the debate's files is left out: a chip never shows a name the owner did not attach.
 */
export function citedPlaces(citations: Citation[], files: FileRef[]): CitedPlace[] {
  const places: CitedPlace[] = [];
  const seen = new Set<string>();
  for (const c of citations) {
    if (c.kind !== "file") continue; // council.md entries arrive with Phase 6
    const key = `${c.fileId}:${c.page ?? ""}`;
    const file = files.find((f) => f.id === c.fileId);
    if (!file || seen.has(key)) continue;
    seen.add(key);
    places.push({ key, label: file.name, detail: c.page === undefined ? undefined : `page ${c.page}` });
  }
  return places;
}

export function CitedChips({ places, label, className }: { places: CitedPlace[]; label: string; className?: string }) {
  return (
    <ul aria-label={label} className={className ?? "flex min-w-0 flex-wrap gap-2"}>
      {places.map((place) => (
        <li key={place.key} className="flex">
          <Chip kind="citation" label={place.label} detail={place.detail} />
        </li>
      ))}
    </ul>
  );
}
