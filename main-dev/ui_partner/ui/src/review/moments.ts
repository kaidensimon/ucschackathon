// Named moments in the sample debates. A scene is "fixture + moment"; the route
// #/sample/<fixture>?scene=<moment> shows the debate at that instant.
import { c, type Fixture } from "../fixtures/build";
import { fixtures } from "../fixtures/lease";
import type { Ms } from "../lib/events";

type MomentFn = (fx: Fixture) => Ms;

const common: Record<string, MomentFn> = {
  // before the question is sent: nothing has happened yet
  asking: () => -1,
  spooling: () => 10000,
  researching: (fx) => fx.at(c(0, 15)),
  debating: (fx) => fx.at(c(1, 50)),
  vote: (fx) => fx.at(c(2, 42)),
  paused: (fx) => fx.at(c(2, 2)) + 2000,
  "owner-note": (fx) => fx.at(c(2, 16)),
  "note-delivered": (fx) => fx.at(c(2, 50)),
  agreed: (fx) => fx.at(c(3, 40)) + 3000,
  released: (fx) => fx.endAt,
};

// The two and three seat debates are short: two rounds, agreed at 2:10, no pause and no note
// from the owner. Their vote and agreement come earlier, and three moments they do not have.
const short: Record<string, MomentFn | null> = {
  debating: (fx) => fx.at(c(1, 45)),
  vote: (fx) => fx.at(c(1, 26)),
  agreed: (fx) => fx.at(c(2, 10)) + 3000,
  paused: null,
  "owner-note": null,
  "note-delivered": null,
};

/** A debate's own time for a moment, where it differs from the main story's. null: it has no such moment. */
const perFixture: Record<string, Record<string, MomentFn | null>> = {
  "lease-2": short,
  "lease-3": short,
  // four seats: Phi's turns are gone, so the note is shown waiting while Llama speaks instead
  "lease-4": { "owner-note": (fx) => fx.at(c(2, 23)) },
  // six seats: Granite speaks after the other five, so later moments come 13 s after the main story's
  "lease-6": {
    debating: (fx) => fx.at(c(2, 3)),
    vote: (fx) => fx.at(c(2, 55)),
    paused: (fx) => fx.at(c(2, 15)) + 2000,
    "owner-note": (fx) => fx.at(c(2, 29)),
    "note-delivered": (fx) => fx.at(c(3, 3)),
    agreed: (fx) => fx.at(c(3, 53)) + 3000,
  },
  "lease-7": { vote: (fx) => fx.at(c(1, 52)), debating: (fx) => fx.at(c(2, 3)) },
  "lease-7-busy": { debating: (fx) => fx.at(c(1, 50)) },
  "lease-failed": { failed: () => 7000 },
};

/** Real time (ms since the question was sent) of a named moment, or undefined if unknown. */
export function momentAt(fixtureId: string, scene: string): Ms | undefined {
  const fx = fixtures[fixtureId];
  if (!fx) return undefined;
  const own = perFixture[fixtureId]?.[scene];
  if (own === null) return undefined;
  const fn = own ?? common[scene];
  return fn ? fn(fx) : undefined;
}

export const momentNames = Object.keys(common);
