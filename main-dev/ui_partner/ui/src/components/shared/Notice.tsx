import clsx from "clsx";
import { CircleAlert } from "lucide-react";
import { type HTMLAttributes, useCallback, useEffect, useRef, useState } from "react";

/**
 * One quiet line that answers something the owner just did.
 * tone "error" adds the error mark; the words still say what happened.
 */
export function Notice({
  tone = "quiet",
  className,
  children,
  ...rest
}: { tone?: "quiet" | "error" } & HTMLAttributes<HTMLOutputElement>) {
  return (
    <output
      className={clsx("flex items-center gap-1.5 text-meta", tone === "error" ? "text-ink" : "text-muted", className)}
      {...rest}
    >
      {tone === "error" ? <CircleAlert size={14} aria-hidden="true" className="shrink-0 text-error" /> : null}
      {children}
    </output>
  );
}

/** For controls that do nothing in the mock: `poke()` shows the "Not in this mock yet" line for a few seconds. */
export function useNotYet(ms = 4000): [shown: boolean, poke: () => void] {
  const [shown, setShown] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current);
    },
    [],
  );
  const poke = useCallback(() => {
    setShown(true);
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = setTimeout(() => setShown(false), ms);
  }, [ms]);
  return [shown, poke];
}
