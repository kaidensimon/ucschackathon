# Phase 1 spec: what gets built, where, and how it is checked

Short talk. Exact things exact. Where this and `phase-1-plan.md` disagree, the plan wins.

## What this is
Mock screens of GX10 Council, in look C (`docs/design/direction.md`), inside an Electron app. No model, no network, no storage. Every screen shows one invented debate at one moment.

## How data reaches a screen (do not invent another way)
- `ui/src/hooks/useDebate.ts` → `useDebate()` gives `{ view, fixture, at, scene, reducedMotion, playing, play, pause, seek }`.
- `view` is a `DebateView` (`ui/src/lib/events.ts`; read its comments). It comes from `viewAt(events, at)`. Screens only draw `view`. No screen keeps its own copy of debate state. No timers for bubbles: bubble strength is `seat.bubble.opacity` from `view` (so Pause holds it).
- Route: `#/chat/<fixture>?scene=<moment>&view=table|chat&sheet=<seatId>&help=1&open=1`. Fixtures: `lease`, `lease-3`, `lease-7`, `lease-7-busy`, `lease-timeup`, `lease-failed`. Moments: `ui/src/review/moments.ts`. View state lives in the URL (`useSearchParams`), nothing else.
- Table geometry: `tableLayout(n, width, height)`, `figureRect`, `placeBubbles` in `ui/src/lib/layout/tableLayout.ts`. Pure. Use them; do not re-derive positions.
- Scene list: `ui/src/review/states.ts`. Each scene names what must be on screen by `data-part` selectors. Your parts MUST carry those attributes exactly.

## Three things the engine has not decided (screens must be true either way)
1. One seat speaks at a time, or several. → `view.speaking` is a list. Draw a mark per speaking seat.
2. Who writes bubble lines. → never show an author for a bubble.
3. How "answers match" is decided. → show counts only. The agreement number changes only when `view.tally` changes.

## Folders and owners
```
ui/src/
  app/App.tsx                 routes                         LEAD (frozen)
  hooks/                      useDebate                       LEAD (frozen)
  lib/ fixtures/ review/ styles/                              LEAD (frozen)
  components/shared/          Button, IconButton, Switch, Chip, SeatFigure, VoteMark, Meter, Tooltip, Notice   FRAME builder
  components/frame/           AppFrame, TopBar, Sidebar, StatusPill, LaterPage, ShortcutsSheet                  FRAME builder
  components/stage/           Stage (shell)                   FRAME builder
  components/composer/        Composer                        FRAME builder
  screens/ChatScreen.tsx      puts it together                FRAME builder
  gallery/                    Gallery shell                   FRAME builder
  components/table/           TableView, Bubble, SeatSheet    TABLE builder
  components/chatview/        ChatView                        CHAT VIEW builder
  components/conversation/    Question, Answer, FoldedCard, SeatPicker   CONVERSATION builder
```
Each folder may hold `*.test.tsx` and `*.gallery.tsx` beside its components. Write only your folders.

## Contracts between folders (props are fixed; insides are yours)
```ts
// components/table/TableView.tsx
export function TableView(p: { view: DebateView; width: number; height: number; onOpenSeat: (seatId: string) => void }): JSX.Element
// components/table/SeatSheet.tsx   (side sheet for one agent; Radix Dialog; Esc closes; focus returns to the seat)
export function SeatSheet(p: { view: DebateView; seatId: string | null; onClose: () => void }): JSX.Element
// components/chatview/ChatView.tsx
export function ChatView(p: { view: DebateView; width: number; filterSeatId: string | null; onFilter: (seatId: string | null) => void }): JSX.Element
// components/conversation/Question.tsx   (the owner's question with its file chips and time limit)
export function Question(p: { question: string; files: FileRef[]; limitMs: number }): JSX.Element
// components/conversation/FoldedCard.tsx (the folded stage, joined to the answer: vote, rounds, time, each seat's mark, "See the debate")
export function FoldedCard(p: { view: DebateView; open: boolean; onToggle: () => void }): JSX.Element
// components/conversation/Answer.tsx     (answer text as Markdown, citation chips, "Files cited", dissent lines)
export function Answer(p: { view: DebateView }): JSX.Element
// components/conversation/SeatPicker.tsx (five seated rows, "Add a seat" disabled, time limit 2 / 5 / 10)
export function SeatPicker(p: { seats: Seat[]; limitMs: number; open: boolean; onOpenChange: (open: boolean) => void; readOnly: boolean }): JSX.Element
```
The FRAME builder creates each of these files as a small stub (right props, a labelled empty box) so `ChatScreen` compiles. The three screen builders then replace the stubs in their own folders.

Shared pieces the screen builders import from `components/shared/` (FRAME builder builds them, with gallery entries):
```ts
SeatFigure(p: { seat: SeatView; index: number; headD: number; speaking?: boolean; focused?: boolean; size?: "table" | "small" | "tiny"; variant?: "colour" | "ink" })
  // colour = solid seat colour (app); ink = outline drawing with no colour (Chat View column heads)
  // draws head + body + cut + name. Renders data-part="seat-name" on the name.
VoteMark(p: { mark: "agrees" | "differs"; size: number; variant?: "colour" | "ink" })      // data-part="vote-mark"
Meter(p: { agree: number; seats: number; needed: number; reached: boolean; size?: "table" | "pill" })  // pips, mark after the needed pip; data-part="meter" data-reached
Chip(p: { kind: "file" | "citation"; label: string; detail?: string })                     // data-part="file-chip" | "citation-chip"
Button, IconButton, Switch (two-option radio group), Tooltip (Radix, delay 300), Notice
```

## `data-part` names the checks look for (exact)
| Part | Attributes | Who |
|---|---|---|
| `stage` | `data-paused="true|false"`, `data-view="table|chat"` | frame |
| `composer` | | frame |
| `status-pill` | | frame |
| `note` | `data-state="queued|delivered"` | frame (queued chip at composer and at table flat edge is TABLE's; delivered note in Chat View is CHAT VIEW's "You to all") |
| `failed-notice` | | frame |
| `shortcuts-sheet`, `later-page` | | frame |
| `seat` | on the seat's `<button>`: `data-status`, `data-activity`, `data-speaking="true|false"`, `aria-label` with name, state and vote in words | table |
| `seat-name` | visible name text inside the seat | shared SeatFigure |
| `bubble` | `data-fading="true"` while opacity is between 0 and 1 | table |
| `meter` | `data-reached` | shared Meter |
| `vote-mark` | | shared VoteMark |
| `seat-sheet` | | table |
| `chat-view` | `data-layout="thread|columns"` | chat view |
| `chat-column`, `vote-divider`, `citation-chip` | | chat view |
| `question`, `file-chip`, `seat-picker` | | conversation |
| `folded-card`, `answer` (`data-outcome`), `dissent` | | conversation |
| `gallery-entry` | attribute `data-gallery-entry="<name>"` | gallery shell wraps each entry |

## Screen rules (from the plan's "Differences" list; do not "correct" back to the PDF)
1. Frame: top bar 48 px (left: button `Council of 5` + short names in seat order, each with a tiny figure and its name; right: status pill). Sidebar 240 px: New chat, History, Library, Models, Settings; footer: Theme switch, Shortcuts, `Sample data. Invented files and answers.` Below 1100 px wide the sidebar is a 64 px icon rail (icons from `lucide-react`, each with `aria-label` and tooltip).
2. Conversation column: owner's question, then the stage (last item, fills the space above the composer while live, at least 558 px tall when the window allows), composer pinned at the bottom.
3. Stage footer: `Pause` (becomes `Resume` when `view.paused`) and `Stop` at left; Table / Chat switch at right end. Switch appears from spool-up and goes when the stage folds. `Stop` shows `Not in this mock yet`.
4. When `view.answer` exists the stage folds into `FoldedCard` + `Answer` (one unit: vote shown once). `open=1` reopens the stage at its final state above the answer.
5. A failed seat (`status === "failed"`): `failed-notice` says what went wrong (reason from the `seat.status` event in `fixture.events`) and offers `Try again`, `Continue with 4`, `Stop` (all `Not in this mock yet`).
6. Composer: before sending `Message the council` + paperclip + `5 seats, 5 min` (opens SeatPicker) + `Ask`. During a debate `Add a note for the next round` + `Add to next round`; a queued note shows as a chip `Reaches the council at the start of round 3` (`data-part="note" data-state="queued"`).
7. Table View: half-circle table (fill `table`, curved edge and flat edge in `line`), figures from `tableLayout`. Each seat is ONE button (arrow keys move between seats, Enter opens the sheet). Bubble above its seat from `placeBubbles`; two lines at most (line clamp); edge `line`; no shadow; tail to its own seat. Vote marks at the head's upper outer side. Table middle: round, time left, Meter, caption. Queued owner note shown at the flat edge.
8. Chat View: everything inside `[data-part=chat-view]` is black, white and grey (`cv-*` tokens only, including focus rings, and the ink variant of SeatFigure and VoteMark). Solid `cv-paper` background. Header strip: round, time left, agreement, filter (`All models` or one). Message: sender, `to all` or `to Qwen`, clock time, text, outlined citation chips; a message in progress shows its text so far plus `Writing`. Vote divider across the thread. Owner note as `You to all`. `Jump to newest` when scrolled up. Columns only when each gets 200 px or more (`width / seats >= 200`), else one thread; columns are banded by round with dividers across all columns.
9. Keyboard, outside text fields: `?` shortcuts sheet, `/` focus message box, `T` and `C` switch view, Space pause or resume (mock: toggles a `Not in this mock yet` notice is fine), `1`-`7` open that seat's sheet, Esc closes. Enter sends, Shift+Enter new line. No shortcut fires while typing in a field.
10. Accessibility: every control reachable by Tab once, visible focus ring. A seat's `aria-label` says name, state and last vote ("Qwen, speaking, agreed at the last vote"). One polite live region announces round changes, vote results and the final outcome only (not every speaker). Colour is never the only signal.
11. Sidebar items History, Library, Models, Settings go to `#/later/<name>`: one page, one sentence on what will be there and in which phase (History 2, Library 2, Models 3, Settings 2).
12. `council.md` chips and the learning review card are NOT built (gallery shows one chip specimen marked `Arrives with Phase 6`).

## Checks you run
```
npm --prefix <repo>/ui run slice -- src/components/<your folder>     types + your tests (must match at least one test)
npm --prefix <repo>/ui run look -- --port <yours> --agent <you> --route "#/chat/lease?scene=debating"
npm --prefix <repo>/ui run token-guard
npm --prefix <repo>/ui run lint
```
Look at your screenshots (light and dark) beside `docs/design/chosen-study/shots/study-1x-light@1x.png` and `study-1x-dark@1x.png`. Fix. Look again. Use `--width 1024 --height 768` too.
Only the lead and the verifier run `gate` and `look:app` (they write `dist/`).

## Rules
- TypeScript strict. React 19 function components. Tailwind token classes only. Radix primitives from `radix-ui` for dialog, tooltip, toggle group. Icons from `lucide-react`. Markdown with `react-markdown` + `remark-gfm`. No new packages.
- Electron: the page has no Node access. Do not import `fs`, `path`, `electron` or use `process` in `src/`. `window.gx10?.shell` may be read; nothing else.
- No network. No CDN. No `<img>` from the web.
- No install, no `npx`, no git writes, no killing processes, no Python scripts. Only `npm --prefix <repo>/ui run <script>`.
- Frozen for you: everything not in your folders. Need a change there? Work round it and report it.
- Talk to the lead in Stone Age talk. Code, comments and on-screen words stay normal and exact.
