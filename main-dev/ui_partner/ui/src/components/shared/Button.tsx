import clsx from "clsx";
import type { ButtonHTMLAttributes, Ref } from "react";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** line = an edge on paper (default); ink = the one filled button of its group */
  variant?: "line" | "ink";
  size?: "normal" | "small";
  ref?: Ref<HTMLButtonElement>;
}

export function Button({ variant = "line", size = "normal", className, type = "button", ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={clsx(
        "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-control border text-label font-medium transition-colors duration-(--quick)",
        size === "small" ? "h-7.5 px-3" : "h-9 px-3.5",
        variant === "ink"
          ? "border-accent bg-accent text-on-accent hover:border-accent-hover hover:bg-accent-hover"
          : "border-line text-ink hover:bg-hover",
        "disabled:cursor-default disabled:border-dashed disabled:border-line disabled:bg-transparent disabled:text-muted",
        className,
      )}
      {...rest}
    />
  );
}
