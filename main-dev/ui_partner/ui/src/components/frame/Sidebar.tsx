// Left column: 240 px with words; under 1100 px of window it becomes a 64 px rail of icons.
import clsx from "clsx";
import { History, Keyboard, type LucideIcon, Settings, SquarePen } from "lucide-react";
import { Link, useLocation } from "react-router";
import { useEngineLive } from "../../engine/EngineProvider";
import { Tooltip } from "../shared/Tooltip";
import { wght } from "../shared/words";
import { useMediaQuery, WIDE_QUERY } from "./hooks";

/** `match`: the item is the current one when the path starts with any of these. */
interface Item {
  label: string;
  to: string;
  icon: LucideIcon;
  match: string[];
}

const ITEMS: Item[] = [
  { label: "New chat", to: "/chat/new", icon: SquarePen, match: ["/chat"] },
  { label: "History", to: "/history", icon: History, match: ["/history"] },
  // the Phase 1 mock screens: the list of them, and each one
];

/** Settings sits apart from the rest: at the bottom left, under Shortcuts (Lucas, 2026-10-11). */
const SETTINGS: Item = { label: "Settings", to: "/settings", icon: Settings, match: ["/settings"] };

const isCurrent = (pathname: string, match: string[]) => match.some((start) => pathname.startsWith(start));

/** The address options that shape the sample data (see EngineProvider). */
const CARRIED = ["fast", "empty", "model"];

/**
 * The part of the address a link takes along: "?fast=1" and the like, or "" when there is none.
 * `search` is the query of the hash route (useLocation().search). Without this a move from one
 * screen to the next would drop the options, and screenshots would not stay steady.
 */
export function carried(search: string): string {
  const from = new URLSearchParams(search);
  const keep = new URLSearchParams();
  for (const key of CARRIED) {
    const value = from.get(key);
    if (value !== null) keep.set(key, value);
  }
  const query = keep.toString();
  return query ? `?${query}` : "";
}

export const SAMPLE_NOTE = "Sample data. Invented files and answers.";
/** shown instead, once the real council engine is answering */
export const LIVE_NOTE = "Live council on this computer";

const row =
  "flex h-9 w-full cursor-pointer items-center justify-between rounded-control px-3 text-left text-label font-medium text-ink transition-colors duration-(--quick) hover:bg-hover aria-[current=page]:bg-hover";
const square =
  "grid size-10 cursor-pointer place-items-center rounded-control text-ink transition-colors duration-(--quick) hover:bg-hover aria-[current=page]:bg-hover";

export function Sidebar({ onShortcuts, wide: wideProp }: { onShortcuts: () => void; wide?: boolean }) {
  const { pathname, search } = useLocation();
  const keep = carried(search);
  const matches = useMediaQuery(WIDE_QUERY);
  const wide = wideProp ?? matches;
  const live = useEngineLive();

  if (!wide) {
    return (
      <nav
        aria-label="Main"
        data-part="sidebar"
        data-rail="true"
        className="flex w-16 shrink-0 flex-col items-center gap-1 border-hairline border-r py-4"
      >
        {ITEMS.map((item) => (
          <Tooltip key={item.to} label={item.label} side="right">
            <Link
              to={{ pathname: item.to, search: keep }}
              aria-label={item.label}
              aria-current={isCurrent(pathname, item.match) ? "page" : undefined}
              className={square}
            >
              <item.icon size={18} aria-hidden="true" />
            </Link>
          </Tooltip>
        ))}
        <div className="mt-auto flex flex-col items-center gap-1">
          <Tooltip label="Shortcuts" side="right">
            <button type="button" onClick={onShortcuts} aria-label="Shortcuts" className={square}>
              <Keyboard size={18} aria-hidden="true" />
            </button>
          </Tooltip>
          <Tooltip label={SETTINGS.label} side="right">
            <Link
              to={{ pathname: SETTINGS.to, search: keep }}
              aria-label={SETTINGS.label}
              aria-current={isCurrent(pathname, SETTINGS.match) ? "page" : undefined}
              className={square}
            >
              <SETTINGS.icon size={18} aria-hidden="true" />
            </Link>
          </Tooltip>
          <p className="mt-2 px-1 text-center text-meta text-muted">
            {live ? (
              <>
                Live council<span className="sr-only"> on this computer</span>
              </>
            ) : (
              <>
                Sample data<span className="sr-only">. Invented files and answers.</span>
              </>
            )}
          </p>
        </div>
      </nav>
    );
  }

  return (
    <nav
      aria-label="Main"
      data-part="sidebar"
      data-rail="false"
      className="flex w-60 shrink-0 flex-col gap-0.5 border-hairline border-r px-3 pt-4 pb-3"
    >
      {ITEMS.map((item) => {
        const current = isCurrent(pathname, item.match);
        return (
          <Link
            key={item.to}
            to={{ pathname: item.to, search: keep }}
            aria-current={current ? "page" : undefined}
            style={current ? wght.name : undefined}
            className={row}
          >
            {item.label}
          </Link>
        );
      })}
      <div className="mt-auto flex flex-col gap-0.5">
        <button type="button" onClick={onShortcuts} className={row}>
          Shortcuts
        </button>
        <Link
          to={{ pathname: SETTINGS.to, search: keep }}
          aria-current={isCurrent(pathname, SETTINGS.match) ? "page" : undefined}
          style={isCurrent(pathname, SETTINGS.match) ? wght.name : undefined}
          className={row}
        >
          {SETTINGS.label}
        </Link>
        <p className={clsx("mx-3 mt-2 mb-1 text-meta text-muted")}>{live ? LIVE_NOTE : SAMPLE_NOTE}</p>
      </div>
    </nav>
  );
}
