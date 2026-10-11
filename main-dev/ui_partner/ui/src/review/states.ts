// The one list of scenes. It drives the review page AND the final check, so the two can
// never disagree. A scene is "the sample debate at a moment", reached by its route.
// `built` is switched to true by the lead when the screen exists; the final check runs every
// check on built scenes and fails if a check finds none of the thing it tests.

export interface Scene {
  id: string;
  /** plain title shown to Lucas on the review page */
  title: string;
  /** hash route, without the leading # */
  route: string;
  /** extra window sizes to check, besides 1440 x 830 */
  alsoAt?: { width: number; height: number }[];
  /** use only this size (for scenes that exist only on a narrow window) */
  onlyAt?: { width: number; height: number };
  built: boolean;
  /** what must be on screen: a CSS selector and how many of it */
  mustShow: { selector: string; count?: number; atLeast?: number }[];
  /** a scene that shows Chat View: its panel must have no colour */
  chatView?: boolean;
  /** a scene that shows the table: also saved as a grey screenshot */
  table?: boolean;
}

const NARROW = { width: 1024, height: 768 };
const TIGHT = { width: 1100, height: 768 };
// The sample debate (Phase 1 mock screens) lives under /sample. Real chats live under /chat.
const chat = (fixture: string, q: string) => `/sample/${fixture}?${q}`;

export const scenes: Scene[] = [
  {
    id: "placeholder",
    title: "Setup placeholder",
    route: "/placeholder",
    built: true,
    mustShow: [{ selector: "[data-testid=placeholder]", count: 1 }],
  },
  {
    id: "gallery",
    title: "Every component",
    route: "/gallery",
    built: true,
    mustShow: [{ selector: "[data-gallery-entry]", atLeast: 10 }],
  },
  {
    id: "chat-new",
    title: "A new chat",
    route: "/sample/new",
    built: true,
    mustShow: [{ selector: "[data-part=composer]", count: 1 }],
  },
  {
    id: "chat-asking",
    title: "Asking, with the seat picker open",
    route: chat("lease", "scene=asking"),
    built: true,
    mustShow: [
      { selector: "[data-part=seat-picker]", count: 1 },
      { selector: "[data-part=file-chip]", count: 3 },
    ],
  },
  {
    id: "spooling",
    title: "Seating the council (3 of 5 ready)",
    route: chat("lease", "scene=spooling"),
    built: true,
    table: true,
    mustShow: [
      { selector: "[data-part=seat]", count: 5 },
      { selector: "[data-part=seat][data-status=ready]", count: 3 },
    ],
  },
  {
    id: "researching",
    title: "Reading your files",
    route: chat("lease", "scene=researching"),
    built: true,
    table: true,
    mustShow: [{ selector: "[data-part=seat][data-activity=researching]", count: 1 }],
  },
  {
    id: "debating-table",
    title: "Debating, Table View",
    route: chat("lease", "scene=debating"),
    alsoAt: [NARROW],
    built: true,
    table: true,
    mustShow: [
      { selector: "[data-part=seat]", count: 5 },
      { selector: "[data-part=seat][data-speaking=true]", count: 1 },
      { selector: "[data-part=bubble]", count: 3 },
      { selector: "[data-part=meter]", count: 1 },
    ],
  },
  {
    id: "debating-thread",
    title: "Debating, Chat View as one thread",
    route: chat("lease", "scene=debating&view=chat"),
    onlyAt: NARROW,
    built: true,
    chatView: true,
    mustShow: [
      { selector: "[data-part=chat-view][data-layout=thread]", count: 1 },
      { selector: "[data-part=vote-divider]", atLeast: 1 },
    ],
  },
  {
    id: "debating-columns",
    title: "Debating, Chat View as columns",
    route: chat("lease", "scene=debating&view=chat"),
    built: true,
    chatView: true,
    mustShow: [
      { selector: "[data-part=chat-view][data-layout=columns]", count: 1 },
      { selector: "[data-part=chat-column]", count: 5 },
    ],
  },
  {
    id: "seat-sheet",
    title: "An agent's side sheet",
    route: chat("lease", "scene=debating&sheet=s4"),
    built: true,
    mustShow: [{ selector: "[data-part=seat-sheet]", count: 1 }],
  },
  {
    id: "vote",
    title: "Just after a vote (3 of 5, needs 4)",
    route: chat("lease", "scene=vote"),
    built: true,
    table: true,
    mustShow: [{ selector: "[data-part=vote-mark]", count: 5 }],
  },
  {
    id: "paused",
    title: "Paused",
    route: chat("lease", "scene=paused"),
    built: true,
    table: true,
    mustShow: [{ selector: "[data-part=stage][data-paused=true]", count: 1 }],
  },
  {
    id: "owner-note",
    title: "Your note, waiting for the next round",
    route: chat("lease", "scene=owner-note"),
    built: true,
    table: true,
    mustShow: [{ selector: "[data-part=note][data-state=queued]", count: 1 }],
  },
  {
    id: "note-delivered",
    title: "Your note, delivered",
    route: chat("lease", "scene=note-delivered&view=chat"),
    onlyAt: NARROW,
    built: true,
    chatView: true,
    mustShow: [{ selector: "[data-part=note][data-state=delivered]", count: 1 }],
  },
  {
    id: "agreed",
    title: "Agreed, writing the answer",
    route: chat("lease", "scene=agreed"),
    built: true,
    table: true,
    mustShow: [{ selector: "[data-part=meter][data-reached=true]", count: 1 }],
  },
  {
    id: "released",
    title: "The answer",
    route: chat("lease", "scene=released"),
    alsoAt: [NARROW],
    built: true,
    mustShow: [
      { selector: "[data-part=answer]", count: 1 },
      { selector: "[data-part=folded-card]", count: 1 },
      { selector: "[data-part=dissent]", count: 1 },
    ],
  },
  {
    id: "released-open",
    title: "The answer, with the debate reopened",
    route: chat("lease", "scene=released&open=1"),
    built: true,
    table: true,
    mustShow: [
      { selector: "[data-part=stage]", count: 1 },
      { selector: "[data-part=answer]", count: 1 },
    ],
  },
  {
    id: "no-consensus",
    title: "Time ran out: no consensus",
    route: chat("lease-timeup", "scene=released"),
    built: true,
    mustShow: [
      { selector: "[data-part=answer][data-outcome=no-consensus]", count: 1 },
      { selector: "[data-part=dissent]", count: 3 },
    ],
  },
  {
    id: "model-failed",
    title: "A model failed to load",
    route: chat("lease-failed", "scene=failed"),
    built: true,
    table: true,
    mustShow: [
      { selector: "[data-part=seat][data-status=failed]", count: 1 },
      { selector: "[data-part=failed-notice]", count: 1 },
    ],
  },
  {
    id: "table-2",
    title: "Two seats",
    route: chat("lease-2", "scene=debating"),
    built: true,
    table: true,
    mustShow: [
      { selector: "[data-part=seat]", count: 2 },
      { selector: "[data-part=council-slider]", count: 1 },
    ],
  },
  {
    id: "table-4",
    title: "Four seats",
    route: chat("lease-4", "scene=vote"),
    built: true,
    table: true,
    mustShow: [
      { selector: "[data-part=seat]", count: 4 },
      { selector: "[data-part=vote-mark]", count: 4 },
    ],
  },
  {
    id: "table-6",
    title: "Six seats",
    route: chat("lease-6", "scene=debating"),
    alsoAt: [NARROW],
    built: true,
    table: true,
    mustShow: [
      { selector: "[data-part=seat]", count: 6 },
      { selector: "[data-part=bubble]", atLeast: 1 },
    ],
  },
  {
    id: "table-3",
    title: "Three seats",
    route: chat("lease-3", "scene=debating"),
    built: true,
    table: true,
    mustShow: [{ selector: "[data-part=seat]", count: 3 }],
  },
  {
    id: "table-7",
    title: "Seven seats",
    route: chat("lease-7", "scene=vote"),
    alsoAt: [NARROW, TIGHT],
    built: true,
    table: true,
    mustShow: [
      { selector: "[data-part=seat]", count: 7 },
      { selector: "[data-part=vote-mark]", count: 7 },
    ],
  },
  {
    id: "table-7-busy",
    title: "Seven seats, several talking at once",
    route: chat("lease-7-busy", "scene=debating"),
    alsoAt: [NARROW, TIGHT],
    built: true,
    table: true,
    mustShow: [
      { selector: "[data-part=seat]", count: 7 },
      { selector: "[data-part=bubble]", atLeast: 3 },
    ],
  },
  {
    id: "shortcuts",
    title: "The shortcuts sheet",
    route: chat("lease", "scene=debating&help=1"),
    built: true,
    mustShow: [{ selector: "[data-part=shortcuts-sheet]", count: 1 }],
  },
  {
    id: "later-page",
    title: "A screen that arrives later",
    route: "/later/history",
    built: true,
    mustShow: [{ selector: "[data-part=later-page]", count: 1 }],
  },
];

// Phase 2: the chat, history and settings screens, on in-memory stand-in data (?fast=1 makes
// answers arrive at once, so screenshots are steady).
scenes.push(
  {
    id: "real-chat-new",
    title: "A new chat",
    route: "/chat/new?fast=1",
    built: true,
    mustShow: [{ selector: "[data-part=message-box]", count: 1 }],
  },
  {
    id: "real-chat",
    title: "A chat with two answers",
    route: "/chat/c1?fast=1",
    alsoAt: [NARROW],
    built: true,
    mustShow: [
      { selector: "[data-part=owner-message]", count: 2 },
      { selector: "[data-part=answer]", count: 2 },
      { selector: "[data-part=model-pill]", count: 1 },
    ],
  },
  {
    id: "real-chat-no-model",
    title: "A chat when no model is answering",
    route: "/chat/c1?model=unreachable",
    built: true,
    mustShow: [{ selector: "[data-part=model-pill]", count: 1 }],
  },
  {
    id: "history",
    title: "History",
    route: "/history?fast=1",
    alsoAt: [NARROW],
    built: true,
    mustShow: [{ selector: "[data-part=history-row]", atLeast: 3 }],
  },
  {
    id: "history-empty",
    title: "History with no chats yet",
    route: "/history?empty=1",
    built: true,
    mustShow: [{ selector: "[data-part=history-empty]", count: 1 }],
  },
  {
    id: "settings",
    title: "Settings",
    route: "/settings",
    built: true,
    mustShow: [{ selector: "[data-part=settings]", count: 1 }],
  },
);

export const WINDOW = { width: 1440, height: 830 };
export const themes = ["light", "dark", "warm"] as const;
