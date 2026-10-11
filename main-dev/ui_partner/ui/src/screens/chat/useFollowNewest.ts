// Keeps the newest words in sight while the reader is at the end of the messages, and leaves
// the page alone once they have scrolled up (then `away` offers the way back).
// The same behaviour as the debate's Chat View. Scroll position only: no timers.
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

/** the reader counts as "at the newest message" within this many px of the end */
const NEAR_END = 24;

export function useFollowNewest() {
  const scroller = useRef<HTMLElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const atEnd = useRef(true);
  const [away, setAway] = useState(false);

  const onScroll = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    atEnd.current = el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_END;
    setAway(!atEnd.current);
  }, []);

  const toNewest = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    atEnd.current = true;
    setAway(false);
    // the button is about to go: keep the keyboard where it was working
    el.focus({ preventScroll: true });
  }, []);

  // after every draw: new words push the end down, so follow it
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && atEnd.current) el.scrollTop = el.scrollHeight;
  });

  // and when the size changes with no new draw (the font arriving, the window resized)
  useEffect(() => {
    const el = scroller.current;
    const inner = content.current;
    if (!el || !inner || typeof ResizeObserver === "undefined") return;
    const watch = new ResizeObserver(() => {
      if (atEnd.current) el.scrollTop = el.scrollHeight;
    });
    watch.observe(el);
    watch.observe(inner);
    return () => watch.disconnect();
  }, []);

  return { scroller, content, away, onScroll, toNewest };
}
