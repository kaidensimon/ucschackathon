// The message box, pinned under the conversation. Two states:
//   ask  (before sending, and after an answer): "Message the council", paperclip, seats and time, Ask
//   note (while the council debates): "Add a note for the next round", Add to next round
// Enter sends, Shift+Enter starts a new line. Sending does nothing in the mock.
import clsx from "clsx";
import { Paperclip } from "lucide-react";
import { type FormEvent, type KeyboardEvent, type Ref, useState } from "react";
import type { FileRef, Ms, NoteView } from "../../lib/events";
import { Button } from "../shared/Button";
import { Chip } from "../shared/Chip";
import { IconButton } from "../shared/IconButton";
import { Notice, useNotYet } from "../shared/Notice";
import { Tooltip } from "../shared/Tooltip";
import { NOT_YET } from "../shared/words";

const pages = (n: number | undefined) => (n === undefined ? undefined : `${n} ${n === 1 ? "page" : "pages"}`);

export function Composer({
  mode,
  seats,
  limitMs,
  onOpenPicker,
  draft = "",
  files = [],
  queued = null,
  inputRef,
}: {
  mode: "ask" | "note";
  /** how many seats the next debate has */
  seats: number;
  limitMs: Ms;
  onOpenPicker: () => void;
  /** words already in the box */
  draft?: string;
  /** files already attached */
  files?: FileRef[];
  /** the owner's note that waits for the next round */
  queued?: NoteView | null;
  inputRef?: Ref<HTMLTextAreaElement>;
}) {
  const [text, setText] = useState(draft);
  const [notYet, poke] = useNotYet();
  const ask = mode === "ask";
  const placeholder = ask ? "Message the council" : "Add a note for the next round";

  const send = () => {
    if (text.trim()) poke();
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    send();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div data-part="composer" data-mode={mode} className="relative w-full">
      <form
        onSubmit={onSubmit}
        className={clsx(
          "flex flex-col gap-2 rounded-card border border-line bg-surface py-1.75 pr-2",
          ask ? "pl-2" : "pl-4.5",
          "has-[textarea:focus-visible]:outline-2 has-[textarea:focus-visible]:outline-accent has-[textarea:focus-visible]:outline-offset-2",
        )}
      >
        {files.length > 0 ? (
          <ul aria-label="Attached files" className="flex flex-wrap gap-2 pt-1 pl-2.5">
            {files.map((f) => (
              <li key={f.id} className="flex">
                <Chip kind="file" label={f.name} detail={pages(f.pages)} />
              </li>
            ))}
          </ul>
        ) : null}
        <div className="flex items-end gap-2">
          {ask ? (
            <IconButton label="Attach files" onClick={poke}>
              <Paperclip size={18} aria-hidden="true" />
            </IconButton>
          ) : null}
          <textarea
            ref={inputRef}
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={placeholder}
            aria-label={placeholder}
            className="field-sizing-content max-h-32 min-h-9 min-w-0 flex-1 resize-none bg-transparent py-1.25 text-body text-ink outline-none placeholder:text-muted"
          />
          {ask ? (
            <Tooltip label="Choose the seats and the time limit">
              <Button size="small" onClick={onOpenPicker} className="mb-0.75">
                {seats} seats, {Math.round(limitMs / 60000)} min
              </Button>
            </Tooltip>
          ) : null}
          <Button type="submit" variant="ink">
            {ask ? "Ask" : "Add to next round"}
          </Button>
        </div>
      </form>
      <div className="absolute top-full left-4.5 mt-1.5 flex gap-4">
        {queued ? (
          <Notice data-part="note" data-state="queued">
            Reaches the council at the start of round {queued.round + 1}
          </Notice>
        ) : null}
        {notYet ? <Notice>{NOT_YET}</Notice> : null}
      </div>
    </div>
  );
}
