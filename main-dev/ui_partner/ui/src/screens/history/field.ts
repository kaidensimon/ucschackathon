// How a box you type in is drawn on the History and Settings screens: a line edge on paper.
// The focus ring comes from the page's own rule (app.css).
export const FIELD =
  "rounded-control border border-line bg-surface px-3 text-body text-ink placeholder:text-muted disabled:border-dashed disabled:text-muted";

/** The card a small dialog sits in, centred on the window. */
export const DIALOG_CARD =
  "fixed top-1/2 left-1/2 z-50 w-100 -translate-x-1/2 -translate-y-1/2 rounded-card border border-line bg-surface p-6 text-ink";
/** never wider than the window less a 16 px margin each side */
export const DIALOG_FIT = { maxWidth: "calc(100vw - 32px)" } as const;

export const DIALOG_OVERLAY = "fixed inset-0 z-40 bg-page/70";
