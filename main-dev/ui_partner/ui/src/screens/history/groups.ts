// How the History list is sorted under its headings, and how a chat's time is written.
// Days are counted on the computer's own calendar, not in 24-hour steps: a chat from 23:50
// last night is "Yesterday" at 00:10.
import type { ChatSummary } from "../../engine/client";

export type GroupName = "Pinned" | "Today" | "Yesterday" | "Earlier";

export interface ChatGroup {
  name: GroupName;
  chats: ChatSummary[];
}

const ORDER: GroupName[] = ["Pinned", "Today", "Yesterday", "Earlier"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAY = 86400000;

const midnight = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
/** whole calendar days from `then` to `now` (rounded, so a 23 or 25 hour day still counts as one) */
const daysAgo = (then: Date, now: Date) => Math.round((midnight(now) - midnight(then)) / DAY);
const two = (n: number) => String(n).padStart(2, "0");

/** A pinned chat is only ever under Pinned. */
export function groupOf(chat: Pick<ChatSummary, "pinned" | "updatedAt">, now: Date): GroupName {
  if (chat.pinned) return "Pinned";
  const days = daysAgo(new Date(chat.updatedAt), now);
  return days <= 0 ? "Today" : days === 1 ? "Yesterday" : "Earlier";
}

/** The headings that have chats, in their fixed order, each with its newest chat first. */
export function groupChats(chats: ChatSummary[], now: Date): ChatGroup[] {
  const by = new Map<GroupName, ChatSummary[]>();
  for (const chat of chats) {
    const name = groupOf(chat, now);
    by.set(name, [...(by.get(name) ?? []), chat]);
  }
  return ORDER.flatMap((name) => {
    const list = by.get(name);
    return list ? [{ name, chats: [...list].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)) }] : [];
  });
}

/**
 * "Today 18:00", "Yesterday 16:00", "4 Oct", "4 Oct 2025".
 * Under the Today or Yesterday heading the day is already said, so only the time is written.
 */
export function whenWords(iso: string, now: Date, under?: GroupName): string {
  const then = new Date(iso);
  const days = daysAgo(then, now);
  const time = `${two(then.getHours())}:${two(then.getMinutes())}`;
  if (days <= 0) return under === "Today" ? time : `Today ${time}`;
  if (days === 1) return under === "Yesterday" ? time : `Yesterday ${time}`;
  const date = `${then.getDate()} ${MONTHS[then.getMonth()]}`;
  return then.getFullYear() === now.getFullYear() ? date : `${date} ${then.getFullYear()}`;
}

/** A preview is one line of plain words: the marks an answer is written with are left out. */
export function plainWords(text: string): string {
  return text
    .replace(/[*`]/g, "")
    .replace(/^[\s\-#>]+/, "")
    .trim();
}

/** "4 messages", "1 message" */
export function messagesWords(count: number): string {
  return `${count} ${count === 1 ? "message" : "messages"}`;
}
