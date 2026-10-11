// The slim bar across the top of a chat: its title at the left, and at the right whether a
// model is answering. Same height and edges as the sample screen's bar.
import { CircleAlert } from "lucide-react";
import { Slider } from "radix-ui";
import { type ReactNode, useCallback, useSyncExternalStore } from "react";
import { CheckGlyph } from "../../components/shared/Glyph";
import { wght } from "../../components/shared/words";
import type { ModelStatus } from "../../engine/client";

export const MODEL_READY = "Model ready";
export const MODEL_LOADING = "Model is loading";
export const NO_MODEL = "No model is answering";

/**
 * Whether a model is answering, in words with a mark. `model` is undefined while the app is
 * still asking (nothing is shown), and null when the question itself failed.
 */
export function ModelPill({ model }: { model: ModelStatus | null | undefined }) {
  if (model === undefined) return null;
  const state = model?.state ?? "unreachable";
  const ready = state === "ready";
  return (
    <p
      data-part="model-pill"
      data-state={state}
      style={wght.pill}
      className="inline-flex h-7.5 shrink-0 items-center gap-4.5 whitespace-nowrap rounded-full border border-line px-3.5 text-bubble text-ink"
    >
      <span className="inline-flex items-center gap-1.5">
        {ready ? <CheckGlyph size={14} /> : null}
        {!ready && state !== "loading" ? (
          <CircleAlert size={14} aria-hidden="true" className="shrink-0 text-error" />
        ) : null}
        {ready ? MODEL_READY : state === "loading" ? MODEL_LOADING : NO_MODEL}
      </span>
      {ready && model?.name ? (
        <>
          <span className="sr-only">, </span>
          <span>{model.name}</span>
        </>
      ) : null}
    </p>
  );
}

// ---- how many models sit at the table ----
// One place holds the number: this store (kept in localStorage, so it is still there after a
// restart). The slider in the top bar writes it, the idle table draws it, and every question
// is sent with it. Nothing chosen yet: three seats.

export const SEATS_MIN = 2;
export const SEATS_MAX = 6;
export const SEATS_DEFAULT = 3;
const SEATS_KEY = "council.seats";

/** A council size from anything (a number, "?seats=4", a stored word), or null when it is not one. */
export function seatsOf(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= SEATS_MIN && n <= SEATS_MAX ? Math.round(n) : null;
}

let chosenSeats: number | null = null;
const seatListeners = new Set<() => void>();
function subscribeSeats(listener: () => void) {
  seatListeners.add(listener);
  return () => {
    seatListeners.delete(listener);
  };
}
function readSeats(): number {
  if (chosenSeats === null) {
    let saved: number | null = null;
    try {
      saved = seatsOf(localStorage.getItem(SEATS_KEY));
    } catch {
      // storage can be switched off: the choice then lasts for this sitting
    }
    chosenSeats = saved ?? SEATS_DEFAULT;
  }
  return chosenSeats;
}
/** Sets the council size for every screen that shows it. Anything that is not 2 to 6 is ignored. */
export function chooseSeats(value: unknown): void {
  const next = seatsOf(value);
  if (next === null || next === readSeats()) return;
  chosenSeats = next;
  try {
    localStorage.setItem(SEATS_KEY, String(next));
  } catch {
    // see readSeats
  }
  for (const l of seatListeners) l();
}

/** The council size the owner chose (2 to 6; 3 until they choose), and the way to change it. */
export function useSeatChoice(): [number, (seats: number) => void] {
  const seats = useSyncExternalStore(subscribeSeats, readSeats, () => SEATS_DEFAULT);
  const set = useCallback((next: number) => chooseSeats(next), []);
  return [seats, set];
}

/** "Council of 3" and the slider that changes it: drag, or use the arrow keys. */
export function SeatSlider({
  seats,
  onSeats,
  disabled = false,
}: {
  seats: number;
  onSeats: (seats: number) => void;
  disabled?: boolean;
}) {
  return (
    <div data-part="council-slider" className="flex shrink-0 items-center gap-2 text-meta text-muted">
      <span style={wght.pill} className="mr-1 whitespace-nowrap text-bubble text-ink">
        Council of {seats}
      </span>
      <span aria-hidden="true" className="hidden lg:inline">
        {SEATS_MIN}
      </span>
      <Slider.Root
        min={SEATS_MIN}
        max={SEATS_MAX}
        step={1}
        value={[seats]}
        disabled={disabled}
        onValueChange={([next]) => {
          if (next !== undefined && next !== seats) onSeats(next);
        }}
        className="relative flex h-8 w-16 touch-none select-none items-center data-disabled:opacity-50 lg:w-28"
      >
        <Slider.Track className="relative h-0.5 grow rounded-full bg-line">
          <Slider.Range className="absolute h-full rounded-full bg-accent" />
        </Slider.Track>
        <Slider.Thumb
          aria-label="Seats at the table"
          aria-valuetext={`${seats} seats`}
          className="block size-4 cursor-grab rounded-full bg-accent active:cursor-grabbing"
        />
      </Slider.Root>
      <span aria-hidden="true" className="hidden lg:inline">
        {SEATS_MAX}
      </span>
    </div>
  );
}

export function ChatTopBar({
  title,
  heading = false,
  council,
  pill,
}: {
  title: string;
  /** true when the title names the page (an open chat); the empty chat has its own heading */
  heading?: boolean;
  /** the council's size and its slider (real engine only) */
  council?: ReactNode;
  pill?: ReactNode;
}) {
  const Title = heading ? "h1" : "p";
  return (
    <header
      data-part="chat-top-bar"
      className="flex h-12 shrink-0 items-center gap-6 border-hairline border-b pr-4 pl-6"
    >
      <Title style={wght.title} className="mr-auto min-w-0 truncate text-chat text-ink">
        {title}
      </Title>
      {council}
      {pill}
    </header>
  );
}
