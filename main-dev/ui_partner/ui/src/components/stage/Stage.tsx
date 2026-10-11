// The stage: where the debate is watched. This is the shell only. It measures its body and
// hands the size to whatever is shown inside (Table View or Chat View), and it owns the footer:
// Pause or Resume and Stop at the left, the Table / Chat switch at the right end, and a slot
// between them for the message box.
import clsx from "clsx";
import { type ReactNode, useLayoutEffect, useRef, useState } from "react";
import type { DebateView } from "../../lib/events";
import { HEADROOM_MIN } from "../../lib/layout/tableLayout";
import { Button } from "../shared/Button";
import { Notice } from "../shared/Notice";
import { Switch } from "../shared/Switch";
import { NOT_YET } from "../shared/words";
import { FailedNotice } from "./FailedNotice";

export type StageMode = "table" | "chat";
export interface StageSize {
  width: number;
  height: number;
}

const MODES = [
  { value: "table", label: "Table" },
  { value: "chat", label: "Chat" },
] as const;

/** the shortest the stage's body gets; down to this height the table keeps HEADROOM_MIN clear above its top figure */
const STAGE_MIN = 260;
/** clear space kept between the "did not load" notice and the top figure */
const NOTICE_GAP = 8;

/** The size the body is given before it can be measured (and in tests): the study's stage. */
const FALLBACK: StageSize = { width: 1040, height: 558 };

export function Stage({
  view,
  mode,
  onMode,
  live,
  failure = null,
  notYet = false,
  onDead,
  dock,
  className,
  children,
}: {
  view: DebateView;
  mode: StageMode;
  onMode: (mode: StageMode) => void;
  /** the debate is still running: Pause or Resume and Stop are offered */
  live: boolean;
  /** a seat that did not load, and why */
  failure?: { name: string; reason: string } | null;
  /** show the "Not in this mock yet" line */
  notYet?: boolean;
  /** a control that does nothing in the mock was used */
  onDead: () => void;
  /** the message box, between the footer's two ends */
  dock?: ReactNode;
  className?: string;
  /** Table View or Chat View, drawn at the measured size */
  children: (size: StageSize) => ReactNode;
}) {
  const body = useRef<HTMLDivElement>(null);
  const notice = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<StageSize | null>(typeof ResizeObserver === "undefined" ? FALLBACK : null);
  const [noticeH, setNoticeH] = useState(0);
  const failed = failure !== null;
  // biome-ignore lint/correctness/useExhaustiveDependencies: the notice comes and goes with `failed`, and must be watched again
  useLayoutEffect(() => {
    const el = body.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const measure = () => {
      const next = { width: Math.floor(el.clientWidth), height: Math.floor(el.clientHeight) };
      setSize((old) => (old && old.width === next.width && old.height === next.height ? old : next));
      setNoticeH(Math.ceil(notice.current?.offsetHeight ?? 0));
    };
    measure();
    const watch = new ResizeObserver(measure);
    watch.observe(el);
    if (notice.current) watch.observe(notice.current);
    return () => watch.disconnect();
  }, [failed]);

  // The notice lies over the top of the stage, in the room the table keeps for bubbles. In a
  // narrow window it wraps and grows taller than that room, so the table starts that much lower.
  const lower = failed ? Math.max(0, noticeH + NOTICE_GAP - HEADROOM_MIN) : 0;

  const clockRuns = view.phase === "research" || view.phase === "debate" || view.phase === "vote";
  const others = view.seats.filter((s) => s.status !== "failed").length;

  return (
    <section
      data-part="stage"
      data-paused={String(view.paused)}
      data-view={mode}
      aria-label="The debate"
      className={clsx("flex min-h-0 flex-col", className)}
    >
      {/*
        The council shrinks with the stage (tableLayout), so the stage may get this short before
        the page scrolls. What a tall notice takes is added on top, so the table never gets less.
      */}
      <div ref={body} className="relative flex-1" style={{ minHeight: STAGE_MIN + lower }}>
        {size && size.width > 0 && size.height - lower > 0 ? (
          <div className="absolute inset-x-0 bottom-0" style={{ top: lower }}>
            {children(lower > 0 ? { width: size.width, height: size.height - lower } : size)}
          </div>
        ) : null}
        {failure ? (
          <div ref={notice} className="absolute inset-x-0 top-0">
            <FailedNotice name={failure.name} reason={failure.reason} others={others} onDead={onDead} />
          </div>
        ) : null}
      </div>
      <div className="relative flex shrink-0 items-end gap-3">
        {notYet ? <Notice className="absolute bottom-full left-0 mb-2">{NOT_YET}</Notice> : null}
        <div className="mb-2 flex flex-1 basis-0 gap-2">
          {live && !failure ? (
            <>
              <Button onClick={onDead} disabled={!clockRuns}>
                {view.paused ? "Resume" : "Pause"}
              </Button>
              <Button onClick={onDead}>Stop</Button>
            </>
          ) : null}
        </div>
        {dock ? <div className="w-160 min-w-0 shrink">{dock}</div> : null}
        <div className="mb-2 flex flex-1 basis-0 justify-end">
          <Switch label="View" value={mode} options={MODES} onChange={onMode} />
        </div>
      </div>
    </section>
  );
}
