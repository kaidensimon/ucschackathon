// The review bar's Play button. One small store outside React, so the bar (mounted once at
// the top of the app) and the screen (which reads the debate through useDebate) share the
// same clock. When `at` is null the screen shows the moment named in its route.
import type { Ms } from "../lib/events";

export interface PlayerState {
  /** ms since the question was sent, or null to follow the route */
  at: Ms | null;
  playing: boolean;
  speed: number;
}

let state: PlayerState = { at: null, playing: false, speed: 1 };
const listeners = new Set<() => void>();
let frame: number | null = null;
let last = 0;
let endAt = 0;

function set(next: Partial<PlayerState>) {
  state = { ...state, ...next };
  for (const l of listeners) l();
}

function tick(now: number) {
  if (!state.playing) return;
  const next = (state.at ?? 0) + (now - last) * state.speed;
  last = now;
  if (next >= endAt) {
    set({ at: endAt, playing: false });
    frame = null;
    return;
  }
  set({ at: next });
  frame = requestAnimationFrame(tick);
}

export const player = {
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  get: () => state,
  /** start playing from `from` up to `end` (both ms since the question was sent) */
  play(from: Ms, end: Ms, speed = 1) {
    endAt = end;
    last = performance.now();
    set({ at: from >= end ? 0 : from, playing: true, speed });
    if (frame === null) frame = requestAnimationFrame(tick);
  },
  pause() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    set({ playing: false });
  },
  seek(at: Ms) {
    set({ at });
  },
  /** back to the moment named in the route */
  reset() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    set({ at: null, playing: false, speed: 1 });
  },
};
