// Gives every screen its data. Phase 2 is UI only: the data comes from the in-memory
// stand-in (fake.ts). The address can shape it, for screenshots and for looking at states:
//   ?fast=1               answers arrive at once (steady screenshots)
//   ?empty=1              no chats yet
//   ?model=unreachable    show what the screens say when no model answers
//   ?mock                 stay on the stand-in even when the council engine answers
// The stand-in is always the start. Once, at start, the council engine (http.ts) is asked
// whether it is there; if it answers within 1.5 s the screens switch to it. If not, nothing
// changes.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";
import type { EngineClient, ModelState } from "./client";
import { FakeEngine } from "./fake";
import { HttpEngine } from "./http";

const EngineContext = createContext<EngineClient | null>(null);
/** true when the screens talk to the real council engine, false on the stand-in */
const EngineLiveContext = createContext(false);

const PROBE_MS = 1500;

/** "?mock" in the address (before or after the "#") keeps the stand-in. */
function mockForced(): boolean {
  if (typeof location === "undefined") return false;
  const inHash = new URLSearchParams(location.hash.split("?")[1] ?? "");
  const inSearch = new URLSearchParams(location.search);
  return inHash.has("mock") || inSearch.has("mock");
}

function fromAddress(): EngineClient {
  // hash routes: the query sits after the "#/path?"
  const query = typeof location === "undefined" ? "" : (location.hash.split("?")[1] ?? "");
  const p = new URLSearchParams(query);
  return new FakeEngine({
    wordMs: p.get("fast") === "1" ? 0 : 30,
    empty: p.get("empty") === "1",
    modelState: (p.get("model") as ModelState | null) ?? "ready",
  });
}

export function EngineProvider({ engine, children }: { engine?: EngineClient; children: ReactNode }) {
  const standIn = useMemo(() => engine ?? fromAddress(), [engine]);
  const [real, setReal] = useState<EngineClient | null>(null);
  const queries = useMemo(
    () =>
      new QueryClient({
        defaultOptions: {
          // the data is in memory: "offline" must never pause a request
          queries: { networkMode: "always", retry: 1, staleTime: 2000, refetchOnWindowFocus: false },
          mutations: { networkMode: "always" },
        },
      }),
    [],
  );
  useEffect(() => {
    // an engine handed in (tests, galleries) or "?mock" is never replaced
    if (engine || mockForced() || typeof fetch === "undefined") return;
    let left = false;
    const http = new HttpEngine();
    const probe = new AbortController();
    const timer = setTimeout(() => probe.abort(), PROBE_MS);
    http
      .health(probe.signal)
      .then((health) => {
        if (left || !health || health.ok !== true) return;
        setReal(http);
      })
      .catch(() => {
        // not there: the stand-in stays
      })
      .finally(() => clearTimeout(timer));
    return () => {
      left = true;
      clearTimeout(timer);
      probe.abort();
    };
  }, [engine]);
  useEffect(() => {
    // what the stand-in answered is no longer true: ask the real engine again
    if (real) void queries.invalidateQueries();
  }, [real, queries]);
  const value = engine ?? real ?? standIn;
  const live = !engine && real !== null;
  return (
    <QueryClientProvider client={queries}>
      <EngineLiveContext.Provider value={live}>
        <EngineContext.Provider value={value}>{children}</EngineContext.Provider>
      </EngineLiveContext.Provider>
    </QueryClientProvider>
  );
}

export function useEngine(): EngineClient {
  const engine = useContext(EngineContext);
  if (!engine) throw new Error("useEngine needs an EngineProvider above it");
  return engine;
}

/** true when the real council engine is answering; false while the stand-in supplies the data */
export function useEngineLive(): boolean {
  return useContext(EngineLiveContext);
}
