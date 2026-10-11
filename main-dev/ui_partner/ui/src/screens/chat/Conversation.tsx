// One chat, in order: the owner's words at the right with no box, each answer at the left as
// Markdown. Under a finished answer one quiet line: the model, its speed, Copy, and on the
// newest answer Write again. It draws what it is given; it keeps no copy of the chat.
import { CircleAlert, Square } from "lucide-react";
import { type ButtonHTMLAttributes, memo, useCallback, useEffect, useRef, useState } from "react";
import remend from "remend";
import { AnswerText } from "../../components/conversation/AnswerText";
import { Button } from "../../components/shared/Button";
import { Notice } from "../../components/shared/Notice";
import type { Message } from "../../engine/client";
import type { LiveAnswer } from "./useLiveAnswer";

export const WRITING = "Writing";
export const STOPPED = "Stopped";
export const COULD_NOT_COPY = "Could not copy. Select the words and copy them yourself.";
/** when a failed answer comes with no words of its own */
export const NO_ANSWER = "The model did not answer. Check that it is running, then try again.";

/** 41.5 -> "41.5 tokens a second" */
export function speedWords(tokensPerSecond: number): string {
  const n = Math.round(tokensPerSecond * 10) / 10;
  return `${n} ${n === 1 ? "token" : "tokens"} a second`;
}

function MetaButton({ className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={`inline-flex h-6.5 cursor-pointer items-center rounded-control px-2 font-medium text-ink text-meta transition-colors duration-(--quick) hover:bg-hover disabled:cursor-default disabled:text-muted disabled:hover:bg-transparent ${className ?? ""}`}
      {...rest}
    />
  );
}

/** Copy to the clipboard: "copied" for 2 s after it worked, "refused" for a while after it did not. */
function useCopy(text: string): ["idle" | "copied" | "refused", () => void] {
  const [state, setState] = useState<"idle" | "copied" | "refused">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const here = useRef(true);
  useEffect(() => {
    here.current = true;
    return () => {
      here.current = false;
      if (timer.current !== null) clearTimeout(timer.current);
    };
  }, []);
  const copy = useCallback(async () => {
    let next: "copied" | "refused" = "copied";
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      next = "refused";
    }
    if (!here.current) return;
    setState(next);
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), next === "copied" ? 2000 : 6000);
  }, [text]);
  return [state, copy];
}

function OwnerMessage({ text }: { text: string }) {
  return (
    <li data-part="owner-message" className="mt-10 flex justify-end first:mt-0">
      <span className="sr-only">You asked: </span>
      {/* the block sits at the right; a long message still reads from its left edge */}
      <p className="max-w-136 whitespace-pre-wrap break-words font-medium text-body text-ink">{text}</p>
    </li>
  );
}

const AnswerMessage = memo(function AnswerMessage({
  message,
  liveText,
  newest,
  busy,
  onWriteAgain,
}: {
  message: Message;
  /** the words so far while this answer is being written, else null */
  liveText: string | null;
  newest: boolean;
  /** a press is still on its way: Write again and Try again wait */
  busy: boolean;
  onWriteAgain: () => void;
}) {
  const [copyState, copy] = useCopy(message.text);
  const writing = message.status === "writing";
  // a half-written **bold** or `code` is closed for the moment, so the words do not jump about
  const text = writing ? remend(liveText ?? message.text, { links: false }) : message.text;
  const has = text.trim() !== "";

  return (
    <li data-part="answer" data-status={message.status} className="mt-6 first:mt-0">
      <span className="sr-only">Answer: </span>
      {has ? <AnswerText text={text} /> : null}

      {/* the same place and height as the line that takes over when the answer is done: nothing jumps */}
      {writing ? (
        <p data-part="answer-writing" className={`flex h-6.5 items-center text-meta text-muted ${has ? "mt-2" : ""}`}>
          {WRITING}
        </p>
      ) : null}

      {message.status === "failed" ? (
        <div
          data-part="answer-failed"
          role="alert"
          className={`flex items-center gap-4 rounded-card border border-line bg-surface py-3 pr-3 pl-4 ${has ? "mt-4" : ""}`}
        >
          <CircleAlert size={18} aria-hidden="true" className="shrink-0 text-error" />
          <p className="min-w-0 flex-1 text-ink text-label">{message.error ?? NO_ANSWER}</p>
          {newest ? (
            <Button variant="ink" onClick={onWriteAgain} disabled={busy}>
              Try again
            </Button>
          ) : null}
        </div>
      ) : null}

      {message.status === "complete" || message.status === "stopped" ? (
        <div
          data-part="answer-meta"
          className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-meta text-muted ${has ? "mt-2" : ""}`}
        >
          {message.status === "stopped" ? (
            <span className="inline-flex items-center gap-1.5 font-medium text-ink">
              <Square size={9} fill="currentColor" aria-hidden="true" />
              {STOPPED}
            </span>
          ) : null}
          {message.model ? <span>{message.model}</span> : null}
          {message.tokensPerSecond !== null ? <span>{speedWords(message.tokensPerSecond)}</span> : null}
          <span className="-mx-2 flex items-center">
            {has ? <MetaButton onClick={copy}>{copyState === "copied" ? "Copied" : "Copy"}</MetaButton> : null}
            {newest ? (
              <MetaButton onClick={onWriteAgain} disabled={busy}>
                Write again
              </MetaButton>
            ) : null}
          </span>
          {copyState === "refused" ? <Notice tone="error">{COULD_NOT_COPY}</Notice> : null}
          <span aria-live="polite" className="sr-only">
            {copyState === "copied" ? "Copied" : ""}
          </span>
        </div>
      ) : null}
    </li>
  );
});

export function Conversation({
  messages,
  live = null,
  busy = false,
  onWriteAgain,
}: {
  messages: Message[];
  /** the answer being written, when one is */
  live?: LiveAnswer | null;
  busy?: boolean;
  /** write the newest answer again (also "Try again" on a failed one) */
  onWriteAgain: () => void;
}) {
  const last = messages.length - 1;
  return (
    <ol data-part="conversation" className="flex flex-col">
      {messages.map((m, i) =>
        m.role === "user" ? (
          <OwnerMessage key={m.id} text={m.text} />
        ) : (
          <AnswerMessage
            key={m.id}
            message={m}
            liveText={m.status === "writing" ? (live && live.runId === m.runId ? live.text : m.text) : null}
            newest={i === last}
            busy={busy}
            onWriteAgain={onWriteAgain}
          />
        ),
      )}
    </ol>
  );
}
