import clsx from "clsx";

/**
 * A file the owner attached, or a place in a file that an answer cites.
 * variant "ink" draws it in the Chat View greys only.
 */
export function Chip({
  kind,
  label,
  detail,
  variant = "colour",
}: {
  kind: "file" | "citation";
  label: string;
  /** shown after the label in a quieter voice: "14 pages", "page 9" */
  detail?: string;
  variant?: "colour" | "ink";
}) {
  const ink = variant === "ink";
  return (
    <span
      data-part={kind === "file" ? "file-chip" : "citation-chip"}
      className={clsx(
        "inline-flex h-6.5 items-center whitespace-nowrap rounded-control border px-2.5 text-meta font-medium",
        ink ? "border-cv-rule text-cv-ink" : "border-line text-ink",
      )}
    >
      {label}
      {detail ? <span className={clsx("font-normal", ink ? "text-cv-grey" : "text-muted")}>, {detail}</span> : null}
    </span>
  );
}
