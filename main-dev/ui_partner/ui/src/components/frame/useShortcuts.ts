// Keyboard shortcuts for the whole window. None fires while the owner is typing in a field,
// and none fires with Cmd, Ctrl or Alt held (those belong to the system).
import { useEffect, useRef } from "react";

export type Shortcut =
  | { kind: "help" }
  | { kind: "message" }
  | { kind: "view"; view: "table" | "chat" }
  | { kind: "pause" }
  | { kind: "seat"; index: number }
  | { kind: "close" };

interface KeyLike {
  key: string;
  metaKey?: boolean;
  ctrlKey?: boolean;
  altKey?: boolean;
  target?: EventTarget | null;
}

function isTyping(target: EventTarget | null | undefined): boolean {
  if (!target || !(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

/** Space on a focused control presses that control; it must not also pause. */
function isControl(target: EventTarget | null | undefined): boolean {
  if (!target || !(target instanceof HTMLElement)) return false;
  return target.closest("button, a, [role=radio], [role=button], [role=slider], summary") !== null;
}

function isSlider(target: EventTarget | null | undefined): boolean {
  return target instanceof HTMLElement && target.closest("[role=slider]") !== null;
}

/** Which shortcut a key press means, or null. Pure, so it is tested without a window. */
export function shortcutFor(e: KeyLike): Shortcut | null {
  if (e.metaKey || e.ctrlKey || e.altKey) return null;
  if (e.key === "Escape") return { kind: "close" };
  if (isTyping(e.target)) return null;
  if (e.key === "?") return { kind: "help" };
  if (e.key === "/") return { kind: "message" };
  if (e.key === "t" || e.key === "T") return { kind: "view", view: "table" };
  if (e.key === "c" || e.key === "C") return { kind: "view", view: "chat" };
  if (e.key === " ") return isControl(e.target) ? null : { kind: "pause" };
  // on a slider a digit is not a seat (and would take the keyboard away from it)
  if (/^[1-7]$/.test(e.key) && !isSlider(e.target)) return { kind: "seat", index: Number(e.key) - 1 };
  return null;
}

/** Calls `on` for each shortcut pressed. Return true from `on` when the key was used (stops the browser's own action). */
export function useShortcuts(on: (shortcut: Shortcut) => boolean) {
  const handler = useRef(on);
  handler.current = on;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const shortcut = shortcutFor(e);
      if (shortcut && handler.current(shortcut) && shortcut.kind !== "close") e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
