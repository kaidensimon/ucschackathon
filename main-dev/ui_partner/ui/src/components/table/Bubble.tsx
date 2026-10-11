// A bubble: one short line about what a seat just said, over its head (direction rule 6:
// it fades in, stays and fades out with the debate clock, never by a timer of its own).
// Two lines at most. An edge in `line`, no shadow, and a small tail down to its own seat.
// How strong it shows is `bubble.opacity`, straight from the view, so Pause holds it.
// A live debate's bubble may carry a small word on its top edge ("thinking...", "truth 0.94")
// and may be dimmed while its seat works on the next message; neither changes its size.
import { useLayoutEffect, useRef } from "react";
import type { LiveBubble } from "../../lib/timeline/bubble";
import { wght } from "../shared/words";

/** side padding and edge, both sides together */
const PAD_X = 26;
/** whole height with one line of text, and with two */
const ONE_LINE = 40;
const TWO_LINES = 58;
/**
 * Room kept under a bubble for its tail. With the 8 px the layout keeps above a figure, a bubble
 * sits 12 px over its head, as in the study. A speaking seat's ring stands 7 px proud of the
 * head, so its bubble sits that much higher.
 */
export const TAIL_ROOM = 4;
export const RING_ROOM = 7;
/** the tail stays this far inside the bubble's corners */
const TAIL_INSET = 14;
/** rough width of one character at 13 px, Archivo at width 96: used until the browser has measured */
const CHAR = 6.4;
const FACE = '450 13px "Archivo Variable"';

const TYPE = { ...wght.bubble, fontStretch: "96%" } as const;
/** how strong the words of a note are while its seat is thinking about the next one */
const DIM = 0.55;
/** the small word sits across the top edge, this far above the bubble's top and in from its right corner */
const TAG_UP = 8;
const TAG_IN = 8;

export interface BubbleSize {
  w: number;
  h: number;
  lines: 1 | 2;
}

/** A size worked out from the letter count alone. */
export function estimateBubble(text: string, maxWidth: number): BubbleSize {
  const width = text.length * CHAR;
  if (width + PAD_X <= maxWidth) return { w: Math.ceil(width) + PAD_X, h: ONE_LINE, lines: 1 };
  // two balanced lines, with room for a word that will not split
  return { w: Math.min(maxWidth, Math.ceil(width / 2) + 24 + PAD_X), h: TWO_LINES, lines: 2 };
}

/** sizes measured in the browser, by widest allowed width and text; `final` once Archivo was in */
const measured = new Map<string, { size: BubbleSize; final: boolean }>();
const keyOf = (text: string, maxWidth: number) => `${maxWidth}|${text}`;

/** The measured size if the browser has one, else the estimate. */
export function bubbleSize(text: string, maxWidth: number): BubbleSize {
  return measured.get(keyOf(text, maxWidth))?.size ?? estimateBubble(text, maxWidth);
}

/** True while a text still needs a `BubbleProbe` on the page. */
export function needsProbe(text: string, maxWidth: number): boolean {
  return measured.get(keyOf(text, maxWidth))?.final !== true;
}

/** How the text really wraps inside `el`: line count and widest line. Null where layout cannot be read (tests). */
function readLines(el: HTMLElement): { lines: number; widest: number } | null {
  if (typeof document.createRange !== "function") return null;
  const range = document.createRange();
  range.selectNodeContents(el);
  if (typeof range.getClientRects !== "function") return null;
  const rows = new Map<number, { left: number; right: number }>();
  for (const rect of range.getClientRects()) {
    if (rect.width <= 0) continue;
    const top = Math.round(rect.top);
    const row = rows.get(top);
    if (row) {
      row.left = Math.min(row.left, rect.left);
      row.right = Math.max(row.right, rect.right);
    } else rows.set(top, { left: rect.left, right: rect.right });
  }
  if (rows.size === 0) return null;
  let widest = 0;
  for (const row of rows.values()) widest = Math.max(widest, row.right - row.left);
  return { lines: rows.size, widest };
}

/**
 * Sets one bubble text out of sight at the widest allowed width and reads how it wraps, so the
 * bubble can be drawn tight round its words. Calls `onMeasured` when the size it found is new.
 */
export function BubbleProbe({
  text,
  maxWidth,
  onMeasured,
}: {
  text: string;
  maxWidth: number;
  onMeasured: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    let live = true;
    const take = (final: boolean) => {
      if (!live) return;
      const got = readLines(el);
      if (!got) return;
      const lines = got.lines > 1 ? 2 : 1;
      const size: BubbleSize = {
        // more than two lines: the widest bubble, cut at the second line
        w: got.lines > 2 ? maxWidth : Math.min(maxWidth, Math.ceil(got.widest) + 1 + PAD_X),
        h: lines === 2 ? TWO_LINES : ONE_LINE,
        lines,
      };
      const key = keyOf(text, maxWidth);
      const before = measured.get(key)?.size ?? estimateBubble(text, maxWidth);
      measured.set(key, { size, final });
      if (before.w !== size.w || before.h !== size.h || final) onMeasured();
    };
    // Archivo loads when first used, so a first reading may be of the fallback face: it is
    // taken again once the real face is in
    const fonts = typeof document !== "undefined" ? document.fonts : undefined;
    const ready = !fonts || fonts.check(FACE);
    take(ready);
    if (fonts && !ready)
      fonts
        .load(FACE)
        .then(() => take(true))
        .catch(() => {});
    return () => {
      live = false;
    };
  }, [text, maxWidth, onMeasured]);
  return (
    <div
      ref={ref}
      aria-hidden="true"
      className="pointer-events-none invisible absolute top-0 left-0 text-balance text-bubble"
      style={{ ...TYPE, width: maxWidth - PAD_X }}
    >
      {text}
    </div>
  );
}

/** Where the tail leaves the bubble: under the seat's head, kept clear of the corners. */
export function tailAt(seatX: number, left: number, width: number): number {
  return Math.max(TAIL_INSET, Math.min(width - TAIL_INSET, seatX - left));
}

export function Bubble({
  bubble,
  left,
  top,
  size,
  tail,
}: {
  bubble: LiveBubble;
  /** px from the stage's top left */
  left: number;
  top: number;
  size: BubbleSize;
  /** px from the bubble's left edge to the middle of its tail */
  tail: number;
}) {
  const prev = bubble.prev;
  // while a new line replaces an old one the box stays; the two texts trade places inside it
  const strength = Math.min(1, bubble.opacity + (prev?.opacity ?? 0));
  const share = (opacity: number) => (strength > 0 ? opacity / strength : 0);
  const clamp = size.lines === 1 ? "line-clamp-1" : "line-clamp-2";
  const words = bubble.dim ? DIM : 1;
  const tag = bubble.tag;
  return (
    <div
      data-part="bubble"
      data-fading={String(strength > 0 && strength < 1)}
      data-dim={bubble.dim ? "true" : undefined}
      aria-hidden="true"
      className="pointer-events-none absolute rounded-control border border-line bg-surface px-3 py-2.5 text-bubble text-ink"
      style={{ ...TYPE, left, top, width: size.w, height: size.h, opacity: strength }}
    >
      <span
        data-part="bubble-text"
        className={`block text-balance ${clamp}`}
        style={prev || bubble.dim ? { opacity: (prev ? share(bubble.opacity) : 1) * words } : undefined}
      >
        {bubble.text}
      </span>
      {prev ? (
        <span
          className={`absolute inset-x-3 top-2.5 text-balance ${clamp}`}
          style={{ opacity: share(prev.opacity) * words }}
        >
          {prev.text}
        </span>
      ) : null}
      {tag ? (
        <span
          data-part="bubble-tag"
          data-flag={tag.flag ? "true" : undefined}
          className={`absolute whitespace-nowrap rounded-control border bg-surface px-1.5 text-meta ${
            tag.flag ? "border-error font-semibold text-error" : "border-line text-muted"
          }`}
          style={{ top: -TAG_UP - 1, right: TAG_IN }}
        >
          {tag.text}
        </span>
      ) : null}
      <span
        data-tail=""
        className="absolute size-2.75 rotate-45 border-line border-r border-b bg-surface"
        style={{ left: tail - 6.5, bottom: -6.5 }}
      />
    </div>
  );
}
