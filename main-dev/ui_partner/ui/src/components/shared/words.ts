// Words and numbers every screen writes the same way (docs/design/direction.md, "Wording").
import type { Ms } from "../../lib/events";

/** The one line a control shows when it does nothing in the mock. */
export const NOT_YET = "Not in this mock yet";

/** 190000 -> "3:10". Rounds up, so a countdown never shows 0:00 while time is left. */
export function minSec(ms: Ms): string {
  const s = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** "4 of 5" */
export function ofSeats(agree: number, seats: number): string {
  return `${agree} of ${seats}`;
}

/** Weights the look uses that Tailwind has no class for (Archivo is a variable face). */
export const wght = {
  bubble: { fontWeight: 450 },
  pill: { fontWeight: 550 },
  title: { fontWeight: 620 },
  name: { fontWeight: 650 },
} as const;
