// CONTRACT (tests in bubble.test.ts are frozen). Built by the timeline builder.
import type { BubbleView, Ms } from "../events";

/** A small word on a live bubble's edge: "thinking..." or a lie-detector reading. */
export interface BubbleTag {
  text: string;
  /** the reading is a warning: drawn in the error colour */
  flag?: boolean;
}

/**
 * A bubble of a debate that is happening now. A plain BubbleView with three optional extras,
 * so everything that draws a BubbleView draws this too.
 */
export interface LiveBubble extends BubbleView {
  /** the seat is working on its next message: the old note stays, drawn weaker */
  dim?: boolean;
  tag?: BubbleTag;
  /** real time (ms) its words were posted: when not all bubbles fit, the newest get the room */
  newer?: Ms;
}

/**
 * How strongly a live note shows, `ageMs` of REAL time after it was posted: it fades in over
 * 250 ms and then stays. A live note has no time limit; the seat's next note replaces it.
 */
export function liveOpacity(ageMs: Ms, opts?: { reducedMotion?: boolean }): number {
  if (!(ageMs >= 0)) return 0;
  if (opts?.reducedMotion || ageMs >= BUBBLE.fadeInMs) return 1;
  return ageMs / BUBBLE.fadeInMs;
}

/** The fixed bubble timings from the product plan. */
export const BUBBLE = { fadeInMs: 250, holdMs: 8000, fadeOutMs: 1500 } as const;

/**
 * How strongly a bubble shows, 0 to 1, `ageMs` after its summary was posted
 * (measured on the debate clock, so a pause holds it).
 * Normal: 0 -> 1 over the first 250 ms, 1 until 8250, 1 -> 0 until 9750, then 0.
 * Reduced motion: 1 from 0 to 8250 inclusive, otherwise 0. Never a value in between.
 */
export function bubbleOpacity(ageMs: Ms, opts?: { reducedMotion?: boolean }): number {
  const holdEnd = BUBBLE.fadeInMs + BUBBLE.holdMs; // 8250
  const gone = holdEnd + BUBBLE.fadeOutMs; // 9750

  if (opts?.reducedMotion) return ageMs >= 0 && ageMs <= holdEnd ? 1 : 0;

  // `!(ageMs > 0)` also catches NaN, so a bad age shows nothing
  if (!(ageMs > 0) || ageMs >= gone) return 0;
  if (ageMs < BUBBLE.fadeInMs) return ageMs / BUBBLE.fadeInMs;
  if (ageMs <= holdEnd) return 1;
  return (gone - ageMs) / BUBBLE.fadeOutMs;
}
