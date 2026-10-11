// A seat's vote, as a shape (direction rule 4). Never red.
//   agrees  = solid ink disc, page-colour check
//   differs = page-filled disc, ink outline, ink cross
// Both sit on a page-colour gap so the mark reads on top of a head.

const n1 = (v: number) => Number(v.toFixed(1));

export function VoteMark({
  mark,
  size,
  variant = "colour",
}: {
  mark: "agrees" | "differs";
  /** the whole mark in px, gap included (26 at the table, 16 in a line-up) */
  size: number;
  /** ink = Chat View greys only */
  variant?: "colour" | "ink";
}) {
  const ink = variant === "ink";
  const k = size / 26;
  const c = size / 2;
  const gap = ink ? "fill-cv-paper" : "fill-page";
  const cross = 3.7 * k;
  return (
    <svg
      data-part="vote-mark"
      data-mark={mark}
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={mark === "agrees" ? "agrees" : "disagrees"}
      className="block shrink-0"
    >
      <circle cx={c} cy={c} r={n1(13 * k)} className={gap} />
      {mark === "agrees" ? (
        <>
          <circle cx={c} cy={c} r={n1(11 * k)} className={ink ? "fill-cv-ink" : "fill-accent"} />
          <path
            d={`M${n1(c - 4.8 * k)} ${n1(c + 0.4 * k)}l${n1(3.3 * k)} ${n1(3.3 * k)}l${n1(6 * k)} ${n1(-7 * k)}`}
            fill="none"
            strokeWidth={n1(Math.max(1.6, 2.4 * k))}
            strokeLinecap="round"
            strokeLinejoin="round"
            className={ink ? "stroke-cv-paper" : "stroke-on-accent"}
          />
        </>
      ) : (
        <>
          <circle
            cx={c}
            cy={c}
            r={n1(10 * k)}
            strokeWidth={n1(Math.max(1.5, 2 * k))}
            className={ink ? "fill-cv-paper stroke-cv-ink" : "fill-page stroke-accent"}
          />
          <path
            d={`M${n1(c - cross)} ${n1(c - cross)}L${n1(c + cross)} ${n1(c + cross)}M${n1(c + cross)} ${n1(c - cross)}L${n1(c - cross)} ${n1(c + cross)}`}
            fill="none"
            strokeWidth={n1(Math.max(1.5, 2.2 * k))}
            strokeLinecap="round"
            className={ink ? "stroke-cv-ink" : "stroke-accent"}
          />
        </>
      )}
    </svg>
  );
}
