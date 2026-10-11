// The owner's question: plain words at the right of the centre column, no box.
// Under it the files that went with it, and the time the council was given.
import type { FileRef } from "../../lib/events";
import { Chip } from "../shared/Chip";
import { minSec } from "../shared/words";

const pages = (n: number | undefined) => (n === undefined ? undefined : `${n} ${n === 1 ? "page" : "pages"}`);

export function Question(p: { question: string; files: FileRef[]; limitMs: number }) {
  return (
    <div data-part="question" className="text-right">
      <h1 className="font-medium text-body text-ink">{p.question}</h1>
      {p.files.length > 0 ? (
        <ul aria-label="Attached files" className="mt-2.5 flex flex-wrap justify-end gap-2">
          {p.files.map((f) => (
            <li key={f.id} className="flex">
              <Chip kind="file" label={f.name} detail={pages(f.pages)} />
            </li>
          ))}
        </ul>
      ) : null}
      {p.limitMs > 0 ? <p className="mt-2 text-meta text-muted">Time limit {minSec(p.limitMs)}</p> : null}
    </div>
  );
}
