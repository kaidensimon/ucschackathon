import clsx from "clsx";
import type { ButtonHTMLAttributes, ReactNode, Ref } from "react";
import { Tooltip } from "./Tooltip";

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> {
  /** what the button does: read aloud, and shown as its tooltip */
  label: string;
  children: ReactNode;
  tooltipSide?: "top" | "right" | "bottom" | "left";
  ref?: Ref<HTMLButtonElement>;
}

/** A square button that shows only an icon. Its label is never optional. */
export function IconButton({
  label,
  children,
  tooltipSide = "top",
  className,
  type = "button",
  ...rest
}: IconButtonProps) {
  return (
    <Tooltip label={label} side={tooltipSide}>
      <button
        type={type}
        aria-label={label}
        className={clsx(
          "grid size-9 shrink-0 cursor-pointer place-items-center rounded-control text-ink transition-colors duration-(--quick) hover:bg-hover",
          "disabled:cursor-default disabled:text-muted disabled:hover:bg-transparent",
          className,
        )}
        {...rest}
      >
        {children}
      </button>
    </Tooltip>
  );
}
