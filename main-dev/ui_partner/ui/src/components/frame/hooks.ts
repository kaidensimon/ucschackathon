// Small hooks the frame shares: theme, window width, and view state kept in the URL.
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { useSearchParams } from "react-router";

export type Theme = "warm" | "light" | "dark";

/** The themes in the order the choosers show them, with the word for each. Warm is the one a new owner sees. */
export const THEMES = [
  { value: "warm", label: "Warm" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
] as const;

/** What <html data-theme> holds, as a theme. Anything else is Warm. */
export function themeOf(value: string | null | undefined): Theme {
  return value === "light" || value === "dark" ? value : "warm";
}

export function currentTheme(): Theme {
  if (typeof document === "undefined") return "warm";
  return themeOf(document.documentElement.getAttribute("data-theme"));
}

// Every part of the app that shows the theme reads this one store, so the sidebar's word and
// the Settings switch can never disagree.
const themeListeners = new Set<() => void>();
function subscribeTheme(listener: () => void) {
  themeListeners.add(listener);
  return () => themeListeners.delete(listener);
}

/** The theme lives on <html data-theme>; index.html sets it before first paint. */
export function useTheme(): [Theme, (next: Theme) => void] {
  const theme = useSyncExternalStore(subscribeTheme, currentTheme, () => "warm" as Theme);
  const set = useCallback((next: Theme) => {
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("theme", next);
    } catch {
      // storage can be switched off; the theme still changes for this sitting
    }
    for (const l of themeListeners) l();
  }, []);
  return [theme, set];
}

/** True while the window matches the query. Without matchMedia (tests) it answers `fallback`. */
export function useMediaQuery(query: string, fallback = true): boolean {
  const can = typeof matchMedia === "function";
  const [matches, setMatches] = useState(() => (can ? matchMedia(query).matches : fallback));
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const m = matchMedia(query);
    const on = () => setMatches(m.matches);
    on();
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [query]);
  return matches;
}

/** Below this window width the sidebar is a 64 px icon rail. */
export const WIDE_QUERY = "(min-width: 1100px)";

/** Read and write one piece of view state in the URL. `null` removes it. */
export function useUrlState(): [URLSearchParams, (changes: Record<string, string | null>) => void] {
  const [search, setSearch] = useSearchParams();
  const change = useCallback(
    (changes: Record<string, string | null>) => {
      setSearch(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const [key, value] of Object.entries(changes)) {
            if (value === null) next.delete(key);
            else next.set(key, value);
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSearch],
  );
  return [search, change];
}
