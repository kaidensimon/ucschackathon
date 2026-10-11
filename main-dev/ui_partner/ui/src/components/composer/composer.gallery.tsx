import { fixtures } from "../../fixtures/lease";
import { type GalleryEntry, sampleView } from "../../gallery/entry";
import { Composer } from "./Composer";

const created = fixtures.lease?.events.find((e) => e.type === "debate.created");
const question = created?.type === "debate.created" ? created.question : "";
const files = created?.type === "debate.created" ? created.files : [];
const queued = sampleView("lease", "owner-note").notes.find((n) => n.state === "queued");

const box = "max-w-160 pb-6";

export const entries: GalleryEntry[] = [
  {
    name: "Composer, before sending",
    note: "Enter sends, Shift and Enter starts a new line.",
    render: () => (
      <div className={box}>
        <Composer mode="ask" seats={5} limitMs={300000} onOpenPicker={() => {}} />
      </div>
    ),
  },
  {
    name: "Composer, question typed",
    note: "Attached files sit above the words.",
    render: () => (
      <div className={box}>
        <Composer mode="ask" seats={5} limitMs={300000} onOpenPicker={() => {}} draft={question} files={files} />
      </div>
    ),
  },
  {
    name: "Composer, during a debate",
    render: () => (
      <div className={box}>
        <Composer mode="note" seats={5} limitMs={300000} onOpenPicker={() => {}} />
      </div>
    ),
  },
  {
    name: "Composer, note waiting",
    note: "The line under the box says when the note reaches the council.",
    render: () => (
      <div className={box}>
        <Composer mode="note" seats={5} limitMs={300000} onOpenPicker={() => {}} queued={queued} />
      </div>
    ),
  },
];
