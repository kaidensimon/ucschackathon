// The agreement meter: one pip per seat, filled for each seat that backs the leading answer,
// and a small upright mark after the pip that reaches the number needed.
// Reached: the pips turn the agreed colour, with a check and the word (never colour alone).
import clsx from "clsx";
import { CheckGlyph } from "./Glyph";
import { ofSeats } from "./words";

const SIZES = {
  table: { pip: 12, gap: 8, barH: 16, check: 16 },
  pill: { pip: 8, gap: 5, barH: 11, check: 13 },
} as const;
const BAR = 2;

export function Meter({
  agree,
  seats,
  needed,
  reached,
  size = "table",
}: {
  agree: number;
  seats: number;
  needed: number;
  reached: boolean;
  size?: "table" | "pill";
}) {
  const s = SIZES[size];
  const width = seats * s.pip + (seats - 1) * s.gap + s.gap + BAR;
  const cy = s.barH / 2;
  const shapes = [];
  let x = 0;
  for (let i = 1; i <= seats; i++) {
    const on = i <= agree;
    shapes.push(
      <circle
        key={`pip-${i}`}
        data-pip={on ? "on" : "off"}
        cx={x + s.pip / 2}
        cy={cy}
        r={on ? s.pip / 2 : s.pip / 2 - 0.75}
        strokeWidth={on ? 0 : 1.5}
        className={on ? (reached ? "fill-agreed" : "fill-accent") : "fill-none stroke-line"}
      />,
    );
    x += s.pip + s.gap;
    if (i === needed) {
      shapes.push(
        <rect
          key="needed"
          data-pip="needed"
          x={x}
          y={0}
          width={BAR}
          height={s.barH}
          className={reached ? "fill-agreed" : "fill-accent"}
        />,
      );
      x += BAR + s.gap;
    }
  }
  const words = reached ? `Agreed ${ofSeats(agree, seats)}` : `${ofSeats(agree, seats)} agree, needs ${needed}`;
  return (
    <span data-part="meter" data-reached={String(reached)} className="inline-flex items-center gap-2 align-middle">
      {reached ? <CheckGlyph size={s.check} className="shrink-0 text-agreed" /> : null}
      <svg
        width={width}
        height={s.barH}
        viewBox={`0 0 ${width} ${s.barH}`}
        role="img"
        aria-label={words}
        className="block shrink-0"
      >
        {shapes}
      </svg>
      {reached ? (
        <span
          aria-hidden="true"
          className={clsx("font-semibold text-agreed", size === "table" ? "text-label" : "text-meta")}
        >
          Agreed
        </span>
      ) : null}
    </span>
  );
}
