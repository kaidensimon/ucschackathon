// CONTRACT (tests in tableLayout.test.ts are frozen). Built by the layout builder.
// Pure geometry: no DOM, no clock, no randomness. Same input, same output.

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface TableLayout {
  /** number of seats, 2 to 7 */
  n: number;
  width: number;
  height: number;
  /** centre of the table's flat edge */
  cx: number;
  flatY: number;
  /** radius of the ring the figures sit on, and of the table itself */
  r: number;
  tableR: number;
  /** head diameter; the body is 1.4 x headD wide and 0.7 x headD tall, 2 px under the head */
  headD: number;
  bodyW: number;
  bodyH: number;
  /** middle of each body's flat bottom edge, left to right */
  seats: { x: number; y: number }[];
  bubbleMaxWidth: number;
  /**
   * How far sideways a bubble's middle may sit from its own seat's middle. The full-size council
   * allows a whole bubble width; a shrunk one allows less, so a bubble never ends up beside
   * somebody else's seat. A bubble with no spot that near goes without.
   */
  bubbleReach: number;
  /** how many bubbles may show at once */
  maxBubbles: number;
}

/** space under the flat edge of the table */
const FLOOR = 38;
/** stages at least this wide get the larger heads and bubbles */
const WIDE = 1000;
/** gap between head and body */
const NECK = 2;
/** room kept above the top figure for bubbles: at full size, and the least a two-line bubble needs */
const HEADROOM = 132;
export const HEADROOM_MIN = 80;
/** however small the stage, heads stay at least this big */
const HEAD_MIN = 20;
/** clear space kept between neighbours once the figures have shrunk */
const NEIGHBOUR_GAP = 4;
const TIE = 1e-6;
/** the ring's radius is never less than this many heads (the full-size council has 3.6 or more) */
const RING_HEADS = 3;
/** clear space between a bubble and its own figure's top */
const OWN_GAP = 8;
/** clear space between a bubble and any figure or other bubble */
const GAP = 4;
/** on a shrunk council the bubbles are large beside the figures, and keep more air so two never read as one */
const BUBBLE_GAP = 8;
/** ...and per later try with fewer seats, so a crowded table costs little while the window is dragged */
const RETRY_BUDGET = 300;
/** a bubble's tail stays this far inside its corners (Bubble.tsx draws it so), and is this wide each side of its tip */
const TAIL_INSET = 14;
const TAIL_HALF = 6;
/** most spots tried per call before giving up on a clean fit (keeps the search short) */
const SEARCH_BUDGET = 5000;

/** Where the seats go for one head size: the ring's radius and the seats on it. */
function ring(n: number, width: number, flatY: number, headD: number, headroom: number) {
  const bodyW = 1.4 * headD;
  const figureH = headD + NECK + 0.7 * headD;
  const cx = width / 2;
  // the ring must leave half a body plus 8 px at each side, and bubble room above the top figure
  const r = Math.max(0, Math.floor(Math.min(width / 2 - bodyW / 2 - 8, flatY - figureH - headroom)));
  const seats: { x: number; y: number }[] = [];
  for (let i = 1; i <= n; i++) {
    const angle = (Math.PI * (i - 0.5)) / n; // from the left end of the flat edge
    seats.push({ x: cx - r * Math.cos(angle), y: flatY - r * Math.sin(angle) });
  }
  // stops short of the end seats' bodies, so no figure overlaps the table
  return { r, tableR: Math.floor(r - 0.7 * headD - 8), seats, bodyW, figureH };
}

/**
 * True when the council keeps its proportions (the ring at least `RING_HEADS` heads in radius, so
 * big figures never crowd round a tiny table) and neighbours' boxes are `gap` apart.
 */
function roomy(at: ReturnType<typeof ring>, headD: number, gap: number): boolean {
  if (at.r < RING_HEADS * headD) return false;
  for (let i = 1; i < at.seats.length; i++) {
    const a = at.seats[i - 1];
    const b = at.seats[i];
    if (!a || !b) return false;
    // (a hair of slack: with five seats the neighbours' height difference is exactly r / 2)
    if (Math.abs(a.x - b.x) < at.bodyW + gap - TIE && Math.abs(a.y - b.y) < at.figureH + gap - TIE) return false;
  }
  return true;
}

/**
 * Seat positions and sizes for `n` seats in a stage `width` x `height`. Pure.
 * A roomy stage gets the full-size council. A smaller one gets the same council scaled down:
 * the heads shrink a pixel at a time, and the bubble room with them, until neighbours are clear
 * of each other again. So the figures follow the window instead of crowding.
 */
export function tableLayout(n: number, width: number, height: number): TableLayout {
  const wide = width >= WIDE;
  const crowded = n >= 6;
  const full = crowded ? (wide ? 64 : 56) : wide ? 72 : 64;
  const flatY = height - FLOOR;

  // the largest head that fits; at full size neighbours may come as close as touching (the
  // studies' seven-seat table does), once shrunk they keep a little air
  let headD = full;
  let at = ring(n, width, flatY, headD, HEADROOM);
  if (!roomy(at, headD, 0)) {
    for (headD = full - 1; headD >= HEAD_MIN; headD--) {
      at = ring(n, width, flatY, headD, Math.max(HEADROOM_MIN, Math.round((HEADROOM * headD) / full)));
      if (roomy(at, headD, NEIGHBOUR_GAP)) break;
    }
    if (headD < HEAD_MIN) {
      // a stage too small even for the smallest heads: give up bubble room before anything else
      headD = HEAD_MIN;
      for (let headroom = HEADROOM_MIN - 8; headroom >= 0; headroom -= 8) {
        at = ring(n, width, flatY, headD, headroom);
        if (roomy(at, headD, NEIGHBOUR_GAP)) break;
      }
    }
  }

  const bubbleFull = crowded ? (wide ? 240 : 200) : wide ? 280 : 216;
  // a bubble never takes more than half a small stage
  const bubbleMaxWidth = Math.min(bubbleFull, Math.max(120, Math.floor(width / 2)));
  return {
    n,
    width,
    height,
    cx: width / 2,
    flatY,
    r: at.r,
    tableR: at.tableR,
    headD,
    bodyW: at.bodyW,
    bodyH: 0.7 * headD,
    seats: at.seats,
    bubbleMaxWidth,
    bubbleReach: Math.max(Math.round((bubbleMaxWidth * headD) / full), Math.ceil(bubbleMaxWidth / 2)),
    // every seat may have one: a bubble that has no clear spot is left out when they are placed
    maxBubbles: n,
  };
}

/** The box round one whole figure (head and body). */
export function figureRect(layout: TableLayout, seat: number): Rect {
  const s = layout.seats[seat];
  if (!s) throw new RangeError(`no seat ${seat}`);
  const h = layout.headD + NECK + layout.bodyH;
  return { x: s.x - layout.bodyW / 2, y: s.y - h, w: layout.bodyW, h };
}

/** True when the two boxes are closer than `gap` on both axes. */
function overlaps(a: Rect, b: Rect, gap: number): boolean {
  return a.x < b.x + b.w + gap && b.x < a.x + a.w + gap && a.y < b.y + b.h + gap && b.y < a.y + a.h + gap;
}

/**
 * Every allowed spot for one seat's bubble, best first.
 * Only "snapped" spots are tried: the ideal one (centred, just above the own figure), the stage
 * edges, and flush against each obstacle. The best free spot is always one of these.
 * Best = least (rise above the ideal height + sideways shift from the own figure's centre).
 */
function spots(
  layout: TableLayout,
  seat: number,
  size: { w: number; h: number },
  figures: Rect[],
  placed: Rect[],
  /** drop the close-table rules (own side, tail on own head, not too high): any clear spot within reach */
  anywhere = false,
): Rect[] {
  const own = figures[seat];
  if (!own) return [];
  const mid = own.x + own.w / 2;
  const baseY = Math.floor(own.y - OWN_GAP - size.h); // lowest allowed top edge
  // Where the seats sit close together (six or seven of them, or a shrunk council) a bubble must
  // also sit where its tail (which stays TAIL_INSET inside the bubble's corners) can still land
  // on its own head, a little inside the rim. A bubble with no such spot goes without.
  const shrunk = layout.bubbleReach < layout.bubbleMaxWidth;
  const close = !anywhere && (shrunk || layout.n >= 6);
  const middle = (layout.n - 1) / 2;
  // The seat at the top of a close table has neighbours on both sides: its bubble stays straight
  // above it (never over either of them), and may sit as high as the stage allows, where nothing
  // else is. If that leaves it no room it goes without.
  const top = close && seat === middle;
  const reach = top
    ? layout.headD / 2
    : close
      ? Math.min(layout.bubbleReach, Math.max(0, size.w / 2 - TAIL_INSET) + layout.headD / 2 - TAIL_HALF)
      : layout.bubbleReach;
  const xs = [
    Math.round(mid - size.w / 2),
    0,
    layout.width - size.w,
    Math.ceil(mid - reach - size.w / 2),
    Math.floor(mid + reach - size.w / 2),
  ];
  // Where seats sit close together (six or seven of them, or a shrunk council) the bubbles fan
  // out: each stays on its own side of the line halfway to the next seat towards the middle, so
  // it never hangs over that seat's head and reads as its words. Left of the middle bubbles lean
  // left, right of it they lean right, and the two sides mirror each other.
  const inward = seat < middle ? figures[seat + 1] : seat > middle ? figures[seat - 1] : undefined;
  const fan = inward !== undefined && close;
  const leansLeft = seat < middle;
  // (half the gap two bubbles keep, each side of the line; and a bubble wider than the room
  // between the stage's edge and the line, as at an end seat, reaches across only as far as it must)
  const air = (shrunk ? BUBBLE_GAP : GAP) / 2;
  const line = inward ? (mid + inward.x + inward.w / 2) / 2 : 0;
  const bound = leansLeft ? Math.max(line - air, size.w) : Math.min(line + air, layout.width - size.w);
  if (fan) xs.push(leansLeft ? Math.floor(bound - size.w) : Math.ceil(bound));
  // ...and may not float far above its own head, where its tail would end nearer a neighbour
  const topY = shrunk && !top && !anywhere ? Math.max(0, baseY - layout.headD) : 0;
  const ys = [baseY, topY];
  const obstacles = [
    ...figures.map((box) => ({ box, gap: GAP })),
    ...placed.map((box) => ({ box, gap: shrunk ? BUBBLE_GAP : GAP })),
  ];
  for (const { box: o, gap } of obstacles) {
    xs.push(Math.floor(o.x - gap - size.w), Math.ceil(o.x + o.w + gap)); // left of it, right of it
    ys.push(Math.floor(o.y - gap - size.h), Math.ceil(o.y + o.h + gap)); // above it, below it
  }

  const found: { box: Rect; cost: number }[] = [];
  for (const y of ys) {
    if (y < topY || y > baseY) continue;
    for (const x of xs) {
      if (x < 0 || x + size.w > layout.width) continue;
      const shift = Math.abs(x + size.w / 2 - mid);
      if (shift > reach) continue;
      if (fan && (leansLeft ? x + size.w > bound : x < bound)) continue;
      const box = { x, y, w: size.w, h: size.h };
      if (obstacles.some((o) => overlaps(box, o.box, o.gap))) continue;
      found.push({ box, cost: baseY - y + shift });
    }
  }
  // cheapest first; ties: lower on the stage, then further left (fixed order keeps it deterministic).
  // In a fan a seat right of the middle takes the spot further right, so the two sides mirror.
  const outward = fan && !leansLeft ? -1 : 1;
  found.sort((a, b) => a.cost - b.cost || b.box.y - a.box.y || outward * (a.box.x - b.box.x));
  return found
    .map((f) => f.box)
    .filter((b, i, all) => {
      const prev = all[i - 1];
      return !prev || prev.x !== b.x || prev.y !== b.y; // drop repeats
    });
}

/**
 * Where each talking seat's bubble goes. `seats` are 0-based seat indexes, newest first.
 * Returns one entry per seat in the same order: a box, or null for a seat that gets no bubble
 * (beyond `maxBubbles`, or no clear spot on a small stage).
 * No box overlaps another box or any figure; all stay inside the stage; each sits above its own seat.
 */
export function placeBubbles(layout: TableLayout, seats: number[], size: { w: number; h: number }): (Rect | null)[] {
  const figures = layout.seats.map((_, i) => figureRect(layout, i));
  const result: (Rect | null)[] = seats.map(() => null);

  // The newest `maxBubbles` seats get a bubble. They are placed from the ends of the table inward,
  // so where a bubble goes depends only on WHICH seats talk, not on who spoke last: the low end
  // seats take the free space at the sides, the top seats then rise a little to clear them.
  const middle = (layout.n - 1) / 2;
  const order = seats
    .map((seat, at) => ({ seat, at, own: figures[seat] }))
    .slice(0, layout.maxBubbles)
    .filter((e): e is { seat: number; at: number; own: Rect } => e.own !== undefined)
    .sort((a, b) => Math.abs(b.seat - middle) - Math.abs(a.seat - middle) || a.seat - b.seat || a.at - b.at);

  // Take the best spot for each seat in turn; if a later seat finds no spot, step back and try
  // the earlier seat's next best spot.
  const placed: Rect[] = [];
  let budget = SEARCH_BUDGET;
  const settle = (among: typeof order, k: number): boolean => {
    const entry = among[k];
    if (!entry) return true; // all placed
    for (const box of spots(layout, entry.seat, size, figures, placed)) {
      if (budget-- <= 0) return false;
      placed.push(box);
      if (settle(among, k + 1)) return true;
      placed.pop();
    }
    return false;
  };

  // Not every bubble may fit cleanly (a small stage, or big bubbles). Nothing is ever drawn over
  // a figure or another bubble, so some seats go without; a figure still shows who is speaking.
  // The seats named first (the speakers) come first: as many of them as fit together get their
  // bubbles, then each seat after them takes a clear spot if one is left.
  for (let keep = order.length; keep >= 0; keep--) {
    const first = order.filter((entry) => entry.at < keep);
    placed.length = 0;
    budget = keep === order.length ? SEARCH_BUDGET : RETRY_BUDGET;
    if (!settle(first, 0)) continue;
    first.forEach((entry, k) => {
      result[entry.at] = placed[k] ?? null;
    });
    for (const entry of order.filter((e) => e.at >= keep).sort((a, b) => a.at - b.at)) {
      // The seat named first (the one speaking) never goes without: if the close-table rules
      // leave it no spot, it takes any clear spot within reach, as on a roomy table.
      const box =
        spots(layout, entry.seat, size, figures, placed)[0] ??
        (entry.at === 0 ? spots(layout, entry.seat, size, figures, placed, true)[0] : undefined);
      if (!box) continue;
      placed.push(box);
      result[entry.at] = box;
    }
    break;
  }
  return result;
}
