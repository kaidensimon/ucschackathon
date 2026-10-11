// The message box, pinned under the chat. Enter sends, Shift+Enter starts a new line.
// While an answer is being written the button is "Stop". No paperclip: this phase has no files.
import type { FormEvent, KeyboardEvent, ReactNode, Ref } from "react";
import { Button } from "../../components/shared/Button";

export const BOX_LABEL = "Message the model";

/** six lines of 26 px, plus the 5 px above and below the words */
const SIX_LINES = 6 * 26 + 10;

export function MessageBox({
  value,
  onChange,
  onAsk,
  onStop,
  writing = false,
  busy = false,
  notice = null,
  inputRef,
}: {
  value: string;
  onChange: (value: string) => void;
  /** send the words in the box */
  onAsk: () => void;
  onStop: () => void;
  /** an answer is being written: the button stops it */
  writing?: boolean;
  /** the last press is still on its way: nothing can be sent */
  busy?: boolean;
  /** one line under the box (something that did not work) */
  notice?: ReactNode;
  inputRef?: Ref<HTMLTextAreaElement>;
}) {
  const can = value.trim() !== "" && !writing && !busy;
  // the pressed button changes or goes dashed straight away: put the keyboard back in the box
  const toBox = (from: HTMLElement) => from.closest("form")?.querySelector("textarea")?.focus();

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!can) return;
    toBox(e.currentTarget);
    onAsk();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (can) onAsk();
    }
  };

  return (
    <div data-part="message-box" className="relative w-full">
      <form
        onSubmit={onSubmit}
        className="flex items-end gap-2 rounded-card border border-line bg-surface py-1.75 pr-2 pl-4.5 has-[textarea:focus-visible]:outline-2 has-[textarea:focus-visible]:outline-accent has-[textarea:focus-visible]:outline-offset-2"
      >
        <textarea
          ref={inputRef}
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={BOX_LABEL}
          aria-label={BOX_LABEL}
          style={{ maxHeight: SIX_LINES }}
          className="field-sizing-content min-h-9 min-w-0 flex-1 resize-none bg-transparent py-1.25 text-body text-ink outline-none placeholder:text-muted"
        />
        {writing ? (
          <Button
            onClick={(e) => {
              toBox(e.currentTarget);
              onStop();
            }}
          >
            Stop
          </Button>
        ) : (
          <Button type="submit" variant="ink" disabled={!can}>
            Ask
          </Button>
        )}
      </form>
      {notice ? <div className="absolute top-full left-4.5 mt-1.5">{notice}</div> : null}
    </div>
  );
}
