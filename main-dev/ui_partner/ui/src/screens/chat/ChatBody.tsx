// The chat inside the frame: the messages in a 640 px column that scrolls, and the message box
// pinned under it. While the reader is at the end the newest words stay in sight; once they
// scroll up the page is left alone and "Jump to newest" offers the way back.
import type { ReactNode } from "react";
import { Button } from "../../components/shared/Button";
import { wght } from "../../components/shared/words";
import type { Message } from "../../engine/client";
import { Conversation } from "./Conversation";
import { useFollowNewest } from "./useFollowNewest";
import type { LiveAnswer } from "./useLiveAnswer";

export const EMPTY_LINE = "What do you want to ask?";

function MessageScroll({ children }: { children: ReactNode }) {
  const follow = useFollowNewest();
  return (
    <div className="relative min-h-0 flex-1">
      <section
        ref={follow.scroller}
        aria-label="Messages"
        // biome-ignore lint/a11y/noNoninteractiveTabindex: a scrolling area must be reachable so the keyboard can scroll it
        tabIndex={0}
        onScroll={follow.onScroll}
        className="h-full overflow-y-auto px-6 focus-visible:-outline-offset-2"
      >
        <div ref={follow.content} className="mx-auto w-full max-w-160 pt-6 pb-8">
          {children}
        </div>
      </section>
      {follow.away ? (
        <Button
          variant="ink"
          size="small"
          onClick={follow.toNewest}
          className="-translate-x-1/2 absolute bottom-3 left-1/2"
        >
          Jump to newest
        </Button>
      ) : null}
    </div>
  );
}

export function ChatBody({
  chatKey,
  messages,
  live = null,
  busy = false,
  onWriteAgain,
  box,
  stage = null,
}: {
  /** the live debate, between the messages and the message box (real engine only) */
  stage?: ReactNode;
  /** which chat this is: a different chat starts at its own newest message */
  chatKey: string;
  messages: Message[];
  live?: LiveAnswer | null;
  busy?: boolean;
  onWriteAgain: () => void;
  /** the message box */
  box: ReactNode;
}) {
  return (
    <div data-part="chat-body" className="flex h-full flex-col">
      {messages.length === 0 ? (
        <div className="flex min-h-0 flex-1 items-center justify-center px-6 pb-16">
          <h1 style={wght.title} className="text-center text-ink text-title">
            {EMPTY_LINE}
          </h1>
        </div>
      ) : (
        <MessageScroll key={chatKey}>
          <Conversation messages={messages} live={live} busy={busy} onWriteAgain={onWriteAgain} />
        </MessageScroll>
      )}
      {stage}
      <div className="shrink-0 px-6 pt-3 pb-7">
        <div className="mx-auto w-full max-w-160">{box}</div>
      </div>
    </div>
  );
}
