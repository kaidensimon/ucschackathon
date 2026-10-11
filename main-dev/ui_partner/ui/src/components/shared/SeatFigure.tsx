// One council member, cut from one colour (direction rules 2 to 4).
//   head  = circle, diameter D
//   body  = half circle 1.4 D wide and 0.7 D tall, 2 px under the head
//   logo  = the mark of the company that makes the seat's model, cut out of the head (makers.ts)
//   name  = seatLabel (seatName.ts), lettered across the body, fitted by Archivo's width axis
//           (62 to 125); its size follows the figure, a name of 8 letters or more is a little
//           smaller, and only in a very small figure is it shrunk further so it stays inside
// A seat whose maker this build does not know keeps the earlier drawing: the name lettered across
// the head, and a cut (one line through the body, fixed to the seat's place at the table).
// The drawing box equals tableLayout's figureRect, so a figure can be placed by that box.
// Speaking ring, focus frame and marks draw outside the box (the svg does not clip).
import clsx from "clsx";
import { useId, useLayoutEffect, useRef, useState } from "react";
import type { SeatView } from "../../lib/events";
import { makerOf } from "./makers";
import { seatLabel } from "./seatName";

const FILL = ["fill-seat-1", "fill-seat-2", "fill-seat-3", "fill-seat-4", "fill-seat-5", "fill-seat-6", "fill-seat-7"];
const STRETCH_MIN = 62;
const STRETCH_MAX = 125;
/** the name spans this share of the head; on the body (under a logo) it has a whole head's width */
const NAME_FIT = 0.78;
const BODY_NAME_FIT = 1;
/** a logo's 24 x 24 grid is drawn this share of the head wide, which keeps its corners inside the circle */
const LOGO_FIT = 0.56;
/** the pale plate under a picture logo, as a share of the head */
const PLATE_FIT = 0.84;

/** the face the names are set in (size does not matter for loading) */
const NAME_FACE = '650 19px "Archivo Variable"';

const n1 = (v: number) => Number(v.toFixed(1));

/** The figure's box and the points other parts hang marks on. All in px from the box's top left. */
export function figureBox(headD: number) {
  const bodyR = 0.7 * headD;
  const headR = headD / 2;
  const neck = headD < 20 ? 1 : 2;
  return {
    width: 2 * bodyR,
    height: headD + neck + bodyR,
    headCx: bodyR,
    headCy: headR,
    headR,
    bodyR,
    /** centre of a vote mark: the head's upper outer side */
    markCx: bodyR + headR * Math.SQRT1_2,
    markCy: headR - headR * Math.SQRT1_2,
  };
}

/** One name size per council, following the head: 19 px in a 72 head, 17 in 64, 15 in 56. */
export function nameSize(headD: number): number {
  return Math.max(9, Math.round(headD * 0.265));
}

/** The name's size when it is lettered across the body, under a logo: 17 px under a 72 head, 15 under 64, 13 under 56. */
export function bodyNameSize(headD: number): number {
  return Math.max(9, Math.round(headD * 0.235));
}

/**
 * A long name ("DeepSeek", 8 letters or more) is lettered a little smaller, so it need not be
 * squeezed as narrow to fit: 7/8 of the size at 8 letters, and never under 80%.
 */
export function longNameScale(name: string): number {
  return name.length >= 8 ? Math.max(0.8, 7 / name.length) : 1;
}

/**
 * How big the parts drawn on a figure are (speaking ring, vote mark, error mark): full size down
 * to a 56 head, then smaller with the head, and never under half.
 */
export function figureScale(headD: number): number {
  return Math.max(0.5, Math.min(1, headD / 56));
}

/**
 * Where a mark sits on a figure at the table (px from the box's top left, for a seat right of the
 * middle): on the head's upper outer side. On a small head, and on any head that carries a logo
 * (`onRim`), it moves out to the rim, so the mark does not cover what is in the head.
 */
export function markCentre(headD: number, onRim = false): { x: number; y: number } {
  const headR = headD / 2;
  const out = headR * Math.SQRT1_2 * (headD >= 56 && !onRim ? 1 : 1.3);
  return { x: 0.7 * headD + out, y: headR - out };
}

/** The word under a head that is loading or did not load needs a body this wide; below it the outline and mark say it. */
const WORD_MIN_HEAD = 48;

/** The seat's cut through its body. Seat 1 is plain. */
function cutPath(seatNo: number, x: number, yb: number, r: number, headD: number): string {
  const rr = r - 0.15 * headD;
  switch (seatNo) {
    case 2: // band
      return `M${n1(x - r)} ${n1(yb - 0.36 * r)}H${n1(x + r)}`;
    case 3: // collar
      return `M${n1(x - 0.78 * r)} ${n1(yb - r)}L${n1(x)} ${n1(yb - 0.4 * r)}L${n1(x + 0.78 * r)} ${n1(yb - r)}`;
    case 4: // sash
      return `M${n1(x - 0.9 * r)} ${n1(yb - r)}L${n1(x + 0.5 * r)} ${n1(yb)}`;
    case 5: // placket
      return `M${n1(x)} ${n1(yb - r)}V${n1(yb)}`;
    case 6: // yoke
      return `M${n1(x - rr)} ${n1(yb)}A${n1(rr)} ${n1(rr)} 0 0 1 ${n1(x + rr)} ${n1(yb)}`;
    case 7: // braces
      return `M${n1(x - 0.36 * r)} ${n1(yb - r)}V${n1(yb)}M${n1(x + 0.36 * r)} ${n1(yb - r)}V${n1(yb)}`;
    default:
      return "";
  }
}

const clampStretch = (v: number) => Math.max(STRETCH_MIN, Math.min(STRETCH_MAX, Math.floor(v)));

/**
 * How a name is set to fit its head: Archivo's width setting, and (only when the narrowest
 * setting is still too wide, in a very small head) how much smaller than `nameSize` it is drawn.
 */
interface NameFit {
  stretch: number;
  shrink: number;
}

/** Before the browser has measured: a fit worked out from the letter count. Errs narrow, so nothing spills. */
function guessFit(name: string, size: number, target: number): NameFit {
  const atFull = Math.max(1, name.length * size * 0.62);
  const stretch = clampStretch((100 * target) / atFull);
  return { stretch, shrink: Math.min(1, target / ((atFull * stretch) / 100)) };
}

/** The widest width setting at which the name still fits `target` px. Null where text cannot be measured. */
function measureFit(el: SVGTextElement, size: number, target: number): NameFit | null {
  if (typeof el.getComputedTextLength !== "function") return null;
  el.style.fontSize = `${size}px`;
  const at = (w: number) => {
    el.style.fontStretch = `${w}%`;
    return el.getComputedTextLength();
  };
  if (!(at(100) > 0)) return null;
  if (at(STRETCH_MAX) <= target) return { stretch: STRETCH_MAX, shrink: 1 };
  const narrowest = at(STRETCH_MIN);
  if (narrowest > target) return { stretch: STRETCH_MIN, shrink: target / narrowest };
  let lo = STRETCH_MIN;
  let hi = STRETCH_MAX;
  for (let i = 0; i < 9; i++) {
    const mid = (lo + hi) / 2;
    if (at(mid) <= target) lo = mid;
    else hi = mid;
  }
  return { stretch: Math.floor(lo), shrink: 1 };
}

/** fits already measured with the real font in, by name, size and head */
const measured = new Map<string, NameFit>();

function useNameFit(name: string, size: number, target: number, enabled: boolean) {
  const ref = useRef<SVGTextElement>(null);
  const key = `${name}@${size}@${target}`;
  const [fit, setFit] = useState(() => ({ key, ...(measured.get(key) ?? guessFit(name, size, target)) }));
  useLayoutEffect(() => {
    const el = ref.current;
    if (!enabled || !el) return;
    let live = true;
    const settle = (final: boolean) => {
      if (!live) return;
      const got = measured.get(key) ?? measureFit(el, size, target);
      if (got === null) return;
      el.style.fontStretch = `${got.stretch}%`;
      el.style.fontSize = `${n1(size * got.shrink)}px`;
      if (final) measured.set(key, got);
      setFit((old) =>
        old.key === key && old.stretch === got.stretch && old.shrink === got.shrink ? old : { key, ...got },
      );
    };
    // Archivo loads only when first used, so the first measure may be of the fallback face:
    // it is kept only if the real face is already in, and taken again once it is
    const fonts = typeof document !== "undefined" ? document.fonts : undefined;
    const ready = !fonts || fonts.check(NAME_FACE);
    settle(ready);
    if (fonts && !ready)
      fonts
        .load(NAME_FACE)
        .then(() => settle(true))
        .catch(() => {});
    return () => {
      live = false;
    };
  }, [enabled, key, size, target]);
  // the head changed size (the window was resized) and the new fit is not measured yet: guess
  const now = fit.key === key ? fit : (measured.get(key) ?? guessFit(name, size, target));
  return { ref, stretch: now.stretch, shrink: now.shrink };
}

export interface SeatFigureProps {
  seat: SeatView;
  /** 0-based place at the table: picks the colour and the cut */
  index: number;
  /** head diameter for size "table" (from tableLayout) */
  headD: number;
  speaking?: boolean;
  /**
   * Draw the focus frame round the whole figure. Without it the frame still appears when an
   * ancestor with class `group` has keyboard focus, so a seat button needs no focus state.
   */
  focused?: boolean;
  /** table: head `headD`, name inside. small: head 22. tiny: head 14. Small and tiny carry no name: write it beside. */
  size?: "table" | "small" | "tiny";
  /** colour = solid seat colour. ink = outline drawing in the Chat View greys. */
  variant?: "colour" | "ink";
  /** which upper side of the head the error mark sits on: the one away from the table's middle */
  markSide?: "left" | "right";
}

export function SeatFigure({
  seat,
  index,
  headD,
  speaking = false,
  focused = false,
  size = "table",
  variant = "colour",
  markSide = "right",
}: SeatFigureProps) {
  const D = size === "small" ? 22 : size === "tiny" ? 14 : headD;
  const big = size === "table";
  const ink = variant === "ink";
  const box = figureBox(D);
  const { width: W, height: H, headCx, headCy, headR, bodyR } = box;
  // at the table a known maker's logo takes the head, and the name moves to the body
  const maker = big ? makerOf(seat) : null;
  const markAt = big ? markCentre(D, maker !== null) : { x: box.markCx, y: box.markCy };
  const markCx = markSide === "left" ? W - markAt.x : markAt.x;
  const markCy = markAt.y;
  const place = ((index % 7) + 7) % 7;
  const clipId = useId();

  const loading = seat.status === "loading";
  const failed = seat.status === "failed";
  const solid = seat.status === "ready";
  const outline = ink || !solid;

  const name = seatLabel(seat);
  const nameAt = n1((maker ? bodyNameSize(D) : nameSize(D)) * longNameScale(name));
  const nameRoom = n1((maker ? BODY_NAME_FIT : NAME_FIT) * D);
  const { ref: nameRef, stretch, shrink } = useNameFit(name, nameAt, nameRoom, big);
  const fontSize = n1(nameAt * shrink);
  const logo = (maker?.fit ?? LOGO_FIT) * D;
  // a picture logo keeps its own light and dark; the others are cut out of the head
  const plated = maker?.picture === true && !ink;

  // ring, gap and marks keep their table size down to a 56 head, then shrink with it
  const k = figureScale(D);
  const ringOut = speaking ? 7 * k : 0;
  const markR = 13 * (D >= 56 ? 1 : D >= 20 ? Math.max(0.62, k) : 0.4);
  const top = Math.min(-ringOut, seat.mark || failed ? markCy - markR : 0);

  const shape = ink ? "fill-none stroke-current" : solid ? FILL[place] : "fill-none stroke-line";
  const lineW = outline ? (big ? 1.5 : 1.25) : 0;
  const dash = loading ? (big ? "5 4" : "2.5 2") : undefined;
  const paper = ink ? "fill-cv-paper" : "fill-page";
  const body = `M0 ${n1(H)}A${n1(bodyR)} ${n1(bodyR)} 0 0 1 ${n1(W)} ${n1(H)}Z`;
  const cut = solid && size !== "tiny" && !maker ? cutPath(place + 1, headCx, H, bodyR, D) : "";
  const word = loading ? "Loading" : failed ? "Did not load" : "";
  const label = [name, speaking ? "speaking" : "", word.toLowerCase()].filter(Boolean).join(", ");

  return (
    <svg
      width={n1(W)}
      height={n1(H)}
      viewBox={`0 0 ${n1(W)} ${n1(H)}`}
      data-status={seat.status}
      data-variant={variant}
      className={clsx("block shrink-0 overflow-visible", ink && "text-cv-ink")}
      role={big ? "img" : undefined}
      aria-label={big ? label : undefined}
      aria-hidden={big ? undefined : true}
    >
      <clipPath id={clipId}>
        <path d={body} />
      </clipPath>
      <path d={body} strokeWidth={lineW} strokeDasharray={dash} className={shape} />
      {cut ? (
        <path
          d={cut}
          fill="none"
          clipPath={`url(#${clipId})`}
          strokeWidth={ink ? Math.max(1, n1(D / 36)) : Math.max(1.25, n1(D / 15))}
          className={ink ? "stroke-current" : "stroke-on-seat"}
        />
      ) : null}
      {speaking ? (
        <>
          <circle cx={n1(headCx)} cy={headCy} r={headR + 9 * k} className={paper} />
          <circle
            data-ring="speaking"
            cx={n1(headCx)}
            cy={headCy}
            r={headR + 5.5 * k}
            fill="none"
            strokeWidth={Math.max(1.5, 3 * k)}
            className={ink ? "stroke-current" : "stroke-accent"}
          />
        </>
      ) : null}
      <circle cx={n1(headCx)} cy={headCy} r={headR} strokeWidth={lineW} strokeDasharray={dash} className={shape} />
      {plated ? (
        <circle
          data-part="seat-logo-plate"
          cx={n1(headCx)}
          cy={headCy}
          r={n1((PLATE_FIT * D) / 2)}
          className="fill-plate"
          opacity={solid ? undefined : 0.6}
        />
      ) : null}
      {maker ? (
        <g
          data-part="seat-logo"
          data-maker={maker.company}
          transform={`translate(${n1(headCx - logo / 2)} ${n1(headCy - logo / 2)}) scale(${(logo / 24).toFixed(4)})`}
          fillRule="evenodd"
          clipRule="evenodd"
          className={ink ? "fill-current" : plated ? "fill-on-plate" : solid ? "fill-on-seat" : "fill-muted"}
          opacity={plated && !solid ? 0.6 : undefined}
        >
          {maker.paths.map((d) => (
            <path key={d} d={d} />
          ))}
        </g>
      ) : null}
      {big ? (
        <text
          ref={nameRef}
          data-part="seat-name"
          x={n1(headCx)}
          y={n1(maker ? H - 0.22 * bodyR : headCy + 0.35 * fontSize)}
          fontSize={fontSize}
          textAnchor="middle"
          style={{ fontWeight: 650, fontStretch: `${stretch}%`, fontSize }}
          className={ink ? "fill-current" : solid ? "fill-on-seat" : "fill-ink"}
        >
          {name}
        </text>
      ) : null}
      {big && word && !maker && D >= WORD_MIN_HEAD ? (
        <text
          x={n1(headCx)}
          y={n1(H - 0.24 * bodyR)}
          fontSize={12}
          textAnchor="middle"
          style={{ fontWeight: 500, fontStretch: D < 64 ? "85%" : "100%" }}
          className={ink ? "fill-current" : failed ? "fill-error" : "fill-muted"}
        >
          {word}
        </text>
      ) : null}
      {failed ? (
        <g data-mark="error">
          <circle cx={n1(markCx)} cy={n1(markCy)} r={n1(markR)} className={paper} />
          <circle
            cx={n1(markCx)}
            cy={n1(markCy)}
            r={n1(markR * (11 / 13))}
            className={ink ? "fill-current" : "fill-error"}
          />
          <path
            d={`M${n1(markCx)} ${n1(markCy - markR * 0.42)}V${n1(markCy + markR * 0.08)}`}
            fill="none"
            strokeWidth={n1(markR * 0.18)}
            strokeLinecap="round"
            className={ink ? "stroke-cv-paper" : "stroke-page"}
          />
          <circle cx={n1(markCx)} cy={n1(markCy + markR * 0.42)} r={n1(markR * 0.11)} className={paper} />
        </g>
      ) : null}
      <rect
        data-ring="focus"
        x={-6}
        y={n1(top - 6)}
        width={n1(W + 12)}
        height={n1(H - top + 12)}
        rx={8}
        fill="none"
        strokeWidth={2}
        className={clsx(
          ink ? "stroke-current" : "stroke-accent",
          focused ? "visible" : "invisible group-focus-visible:visible",
        )}
      />
    </svg>
  );
}
