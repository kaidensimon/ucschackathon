// The slim bar shown above a screen that was opened from the review page (?review=1).
// It is the reviewer's remote control, not part of the product: seat count, Play, and a jump
// to any named moment. (The theme is chosen in Settings, nowhere else.) It is never in the screenshots or the checks.
import { useSyncExternalStore } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { Button } from "../components/shared/Button";
import { Switch } from "../components/shared/Switch";
import { minSec } from "../components/shared/words";
import { fixtures } from "../fixtures/lease";
import { momentAt } from "./moments";
import { player } from "./player";

const MOMENTS: [string, string][] = [
  ["spooling", "Seating the council"],
  ["researching", "Reading your files"],
  ["debating", "Mid-debate"],
  ["vote", "Just after a vote"],
  ["paused", "Paused"],
  ["owner-note", "Your note is waiting"],
  ["agreed", "Agreed, writing"],
  ["released", "The answer"],
];

export function ReviewBar() {
  const location = useLocation();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const state = useSyncExternalStore(player.subscribe, player.get);

  const match = location.pathname.match(/^\/sample\/([a-z0-9-]+)$/);
  const fixtureId = match?.[1] ?? "";
  const fixture = fixtures[fixtureId];
  if (search.get("review") !== "1" || !fixture) return null;

  const scene = search.get("scene") ?? "released";
  const routeAt = momentAt(fixtureId, scene) ?? fixture.endAt;
  const at = state.at ?? routeAt;
  const seats = fixture.seats.length;
  const go = (toFixture: string, toScene: string) => {
    const next = new URLSearchParams(search);
    next.set("scene", toScene);
    next.delete("at");
    navigate({ pathname: `/sample/${toFixture}`, search: `?${next.toString()}` });
  };
  // the clock shown is the debate clock: time since the council was seated, never below zero
  const clock = Math.max(0, at - fixture.clockStartAt);

  return (
    <aside
      data-part="review-bar"
      aria-label="Review controls"
      className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-hover px-4 py-2 text-label text-ink"
    >
      <Link to="/review" className="underline underline-offset-2">
        Back to the review page
      </Link>
      <fieldset className="flex items-center gap-1.5">
        <legend className="sr-only">Seats</legend>
        <span className="text-muted">Seats</span>
        {(
          [
            [3, "lease-3"],
            [5, "lease"],
            [7, "lease-7"],
          ] as const
        ).map(([n, id]) => (
          <Button
            key={id}
            size="small"
            variant={seats === n ? "ink" : "line"}
            aria-pressed={seats === n}
            onClick={() => go(id, n === 7 ? "vote" : "debating")}
          >
            {n}
          </Button>
        ))}
      </fieldset>
      {seats === 7 ? (
        <Switch
          label="Speakers"
          value={fixtureId === "lease-7-busy" ? "several" : "one"}
          options={[
            { value: "one", label: "One speaker" },
            { value: "several", label: "Several at once" },
          ]}
          onChange={(v) => go(v === "several" ? "lease-7-busy" : "lease-7", "debating")}
        />
      ) : null}
      <label className="flex items-center gap-1.5">
        <span className="text-muted">Jump to</span>
        <select
          className="h-7.5 rounded-control border border-line bg-surface px-2 text-label text-ink"
          value={scene}
          onChange={(e) => go(fixtureId, e.target.value)}
        >
          {MOMENTS.filter(([id]) => momentAt(fixtureId, id) !== undefined).map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <div className="flex items-center gap-1.5">
        {state.playing ? (
          <Button size="small" onClick={() => player.pause()}>
            Pause the sample
          </Button>
        ) : (
          <>
            <Button size="small" variant="ink" onClick={() => player.play(at, fixture.endAt, 1)}>
              Play
            </Button>
            <Button size="small" onClick={() => player.play(at, fixture.endAt, 4)}>
              Play 4 times faster
            </Button>
          </>
        )}
        <Button size="small" onClick={() => player.play(0, fixture.endAt, 1)}>
          From the start
        </Button>
        <span className="text-muted" aria-live="off">
          {minSec(clock)} into the debate
        </span>
      </div>
      <p className="basis-full text-meta text-muted">
        Sample timing. Real speed on your GX10 has not been measured and may be much slower.
      </p>
    </aside>
  );
}
