// The one way a screen gets "the debate right now". It reads the route:
//   #/sample/<fixture>?scene=<moment>   a named moment (see review/moments.ts)
//   #/sample/<fixture>?at=<ms>          an exact instant
// and returns what viewAt says the screen shows. `play` runs the sample forward in real time
// (the review bar's Play button). Everything a scene shows comes from here, so no two
// screens can disagree.
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useParams, useSearchParams } from "react-router";
import type { Fixture } from "../fixtures/build";
import { fixtures } from "../fixtures/lease";
import type { DebateView, Ms } from "../lib/events";
import { viewAt } from "../lib/timeline/viewAt";
import { momentAt } from "../review/moments";
import { player } from "../review/player";

export function useReducedMotion(): boolean {
  const query = "(prefers-reduced-motion: reduce)";
  const [reduced, setReduced] = useState(() => typeof matchMedia === "function" && matchMedia(query).matches);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const m = matchMedia(query);
    const on = () => setReduced(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return reduced;
}

export interface Debate {
  fixtureId: string;
  fixture: Fixture | undefined;
  /** the named moment from the route, if any */
  scene: string | null;
  /** ms since the question was sent */
  at: Ms;
  view: DebateView | null;
  reducedMotion: boolean;
  playing: boolean;
  speed: number;
  play: (speed?: number) => void;
  pause: () => void;
  seek: (at: Ms) => void;
}

export function useDebate(): Debate {
  const { fixture: fixtureParam } = useParams();
  const [search] = useSearchParams();
  const fixtureId = fixtureParam && fixtures[fixtureParam] ? fixtureParam : "lease";
  const fixture = fixtures[fixtureId];
  const scene = search.get("scene");
  const atParam = search.get("at");
  const startAt = useMemo(() => {
    if (atParam !== null && atParam !== "" && Number.isFinite(Number(atParam))) return Number(atParam);
    if (scene) return momentAt(fixtureId, scene) ?? 0;
    return fixture?.endAt ?? 0;
  }, [atParam, scene, fixtureId, fixture]);

  // The review bar's player may override the moment; otherwise the route decides.
  const playerState = useSyncExternalStore(player.subscribe, player.get);
  const reducedMotion = useReducedMotion();
  // biome-ignore lint/correctness/useExhaustiveDependencies: a new route moment must drop any override
  useEffect(() => {
    player.reset();
  }, [startAt, fixtureId]);
  const at = playerState.at ?? startAt;
  const playing = playerState.playing;
  const speed = playerState.speed;

  const view = useMemo(
    () => (fixture ? viewAt(fixture.events, at, { reducedMotion }) : null),
    [fixture, at, reducedMotion],
  );
  const play = useCallback(
    (sp = 1) => {
      if (fixture) player.play(at, fixture.endAt, sp);
    },
    [fixture, at],
  );
  const pause = useCallback(() => player.pause(), []);
  const seek = useCallback((t: Ms) => player.seek(t), []);

  return { fixtureId, fixture, scene, at, view, reducedMotion, playing, speed, play, pause, seek };
}
