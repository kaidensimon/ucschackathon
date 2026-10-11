// The mark of the company that makes a seat's model, small, to sit beside the seat's name
// (the head of a figure at the table carries the same mark, large: SeatFigure.tsx).
//   known maker    its one-colour mark from makers.ts, in the colour of the words around it
//   picture mark   stays dark on a pale plate, as on a head (never in the Chat View greys)
//   no maker       a ring with the first letter of the name
// It is for the eye only: the name beside it says who it is. The tooltip names the company.
import clsx from "clsx";
import type { CSSProperties } from "react";
import { makerOf } from "./makers";

/** a picture mark's 24 x 24 grid, as a share of its plate (SeatFigure: 0.62 of the head on a 0.84 plate) */
const ON_PLATE = 0.74;

export function MakerMark({
  seat,
  size = 16,
  variant = "colour",
  className,
  style,
}: {
  seat: { shortName: string; modelName: string };
  /** px, both ways */
  size?: number;
  /** ink = inside Chat View: one colour only, so a picture mark gets no plate */
  variant?: "colour" | "ink";
  className?: string;
  /** to place it on a figure's head */
  style?: CSSProperties;
}) {
  const maker = makerOf(seat);
  const plated = maker?.picture === true && variant !== "ink";
  const letter = (seat.shortName.trim() || seat.modelName.trim()).charAt(0).toUpperCase();
  const inset = plated ? (24 * (1 - ON_PLATE)) / 2 : 0;
  return (
    <span
      data-part="maker-mark"
      data-maker={maker?.company}
      title={maker?.company}
      aria-hidden="true"
      className={clsx("inline-flex shrink-0", className)}
      style={style}
    >
      <svg width={size} height={size} viewBox="0 0 24 24" className="block" focusable="false">
        {maker ? (
          <>
            {plated ? <circle cx={12} cy={12} r={12} className="fill-plate" /> : null}
            <g
              transform={plated ? `translate(${inset} ${inset}) scale(${ON_PLATE})` : undefined}
              fillRule="evenodd"
              clipRule="evenodd"
              className={plated ? "fill-on-plate" : "fill-current"}
            >
              {maker.paths.map((d) => (
                <path key={d} d={d} />
              ))}
            </g>
          </>
        ) : (
          <>
            <circle cx={12} cy={12} r={10.75} fill="none" strokeWidth={1.5} className="stroke-current" />
            <text
              x={12}
              y={16.6}
              fontSize={13}
              textAnchor="middle"
              style={{ fontWeight: 650 }}
              className="fill-current"
            >
              {letter}
            </text>
          </>
        )}
      </svg>
    </span>
  );
}
