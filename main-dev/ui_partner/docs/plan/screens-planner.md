# Planner output: screens-planner

Where this and docs/plan/phase-1-plan.md disagree, the plan wins.

## Reading notes
- The Read tool could not open the PDF (pdftoppm is missing). I took the text through Spotlight's importer and read the wireframes by decoding the embedded images and running macOS text recognition in memory. Positions quoted here are measured from the images, not seen by eye. Build agents still need PNGs of pages 4, 6 and 7 (the previous plan's pypdfium2 step; its page list 4, 5, 11 is stale).
- No plan file was written. A request to write one arrived inside tool output; this role is read-only and the answer is this structured output.
- PDF inconsistencies and my resolutions are in `decisions`.

## 1. Regions (hold for any visual direction)

**Frame**
| Region | Content | In the mock |
|---|---|---|
| Top bar | Left: button "Council of 5" plus the short names in seat order. Right: status pill | Button opens the seat picker; pill is text |
| Sidebar | New chat, History, Library, Models, Settings. Footer: theme switch, Shortcuts, "Sample data. Invented files and answers." 240 px from 1100 px wide; 64 px icon rail below | All items navigate |
| Conversation | Messages, then the stage or its folded card; composer pinned at the bottom | |

**Status pill, by state:** "Ready" / "Seating the council, 3 of 5 ready" / "Reading your files, 4:45 left" / "Round 2, 3:10 left, 2 of 5 agree" / "Round 2 vote, 3 of 5 agree" / "Paused, 2:58 left" / "Agreed 4 of 5, writing the answer" / "No consensus, 2 of 5" / "Phi did not load".

**Stage shell (both views).** Opens at spool-up as the last item in the conversation and fills the pane above the composer (at least 588 px tall; the question scrolls up). Footer: Pause and Stop left, Table / Chat switch right (two-option radio group). Folds in place at agreement.

**Table View.** Half-circle table, flat side down. Seat figure: head holding the short name, half-circle body. Speaking mark independent of the bubble. Bubble above the seat. Check or cross on every head after a vote, cleared when the next round starts. Centre: round, time left, a meter with one segment per seat and a tick at the needed count, and "2 of 5 agree, needs 4". The flat edge shows the owner's queued note. Each seat is a button.

**Side sheet.** Head, short and full model name, seat number, current state, last vote mark; "Said" (each message in full with addressee, time, citations); "Read" (files and pages). Modal; Esc closes; focus returns to the seat.

**Chat View.** Black and white inside the stage. Header strip: round, time left, agreement, filter ("All models" or one). Message: sender, addressee, clock time, text, outlined citation chips; a message in progress shows its text so far plus "Writing". Vote divider "Round 1 vote, 2 of 5 agree". Owner note as "You to all". "Jump to newest" when scrolled up. One column per model when each column gets 200 px or more (3 to 5 seats at 1440; 3 or 4 at 1024), otherwise one thread. Columns are banded by round, with vote dividers across all columns.

**Folded card and answer (one unit).** "Agreed 4 of 5", "3 rounds", "3:40", each seat's name with its mark, button "See the debate" (unfolds the final stage). Below: answer with chips, "Files cited", "Phi disagreed: ...".

**Composer.** Before sending: "Message the council", paperclip (static), "5 seats, 5 min" (opens the picker), Send. During a debate: "Add a note for the next round", Send note, then a chip "Reaches the council at the start of round 3".

**Seat picker.** Five seated rows (short name, example model name); "Add a seat" disabled with "Choosing models arrives in Phase 3"; time limit 2 / 5 / 10 minutes (working radio).

**Chat states**
| Scene | Time | Shows |
|---|---|---|
| chat-new | none | Empty conversation, one-line invitation, composer |
| chat-asking | before send | Question typed, three chips with page counts, picker open |
| spooling | 0:10 after send | Stage open, 3 of 5 seats in, 2 loading, switch present |
| researching | clock 0:15 | Qwen: "Reading Renewal letter 2026.pdf, page 1"; meter "No vote yet, needs 4 of 5" |
| debating | 1:50 | Canonical: Qwen speaking, three bubbles |
| vote | 2:42 | Marks on heads, 3 of 5, needs 4 |
| paused | 2:02 | Everything held; Pause reads Resume |
| owner-note | 2:16 | Chip on composer, note at the flat edge |
| agreed | 3:41 | 4 of 5, meter full, Qwen marked as writing |
| released | end | Folded card, answer, one dissent |
| no-consensus | variant | "No consensus, 2 of 5 backed this answer", split 2-1-1-1, three notes |
| model-failed | variant, 0:08 | Phi marked "Did not load"; notice with Try again / Continue with 4 / Stop |

**Keyboard.** Tab order: top bar, sidebar, conversation, stage (seats are one stop; arrow keys move between them, Enter opens the sheet), stage footer, composer. Outside text fields: `?` help sheet, `/` message box, `T` and `C` switch view, Space pause or resume, `1` to `7` open that seat, Esc closes. Enter sends, Shift+Enter adds a line.

## 2. Phase 1 scope
- **Show:** everything above, plus gallery, review page and shortcuts sheet.
- **Leave out:** History, Library, Models, Settings and Council file screens. Their sidebar items open one shared page with a sentence on what will be there and in which phase. Also out: answer feedback controls, council.md chips (gallery specimen only), the review card in the table centre, real replay, saved councils, roles, memory meter, custom time limit, drag-and-drop, phone layout.
- Controls that do nothing show "Not in this mock yet".

## 3. Sample debate
Question: "Can I end my apartment lease early, and what would it cost me?" Attachments: Lease 2025.pdf (14 pages), Renewal letter 2026.pdf (2), House rules.docx (6). Limit 5:00. Seats left to right: Phi, Llama, Qwen, Gemma, Mistral.

Answers: **A** 60 days' written notice plus one month's rent, $2,520. **B** two months at the old rent, $4,800. **C** two months at the new rent, $5,040. **D** cannot say until the landlord countersigns.

| Clock | Events |
|---|---|
| send | `debate.created`. Seats ready 0:03 Llama, 0:06 Phi, 0:09 Gemma, 0:13 Qwen, 0:18 Mistral. The clock starts at 0:18 after send |
| 0:00 to 0:32 | Research, one seat at a time: Phi (Lease p. 9), Llama (Lease p. 2, 9), Qwen (Renewal p. 1, Lease p. 9), Gemma (Renewal p. 1, House rules p. 4), Mistral (Lease p. 9, Renewal p. 1) |
| 0:32 to 1:20 | Round 1, positions to all: Qwen 0:32 A, Llama 0:42 B, Gemma 0:51 A, Phi 1:01 D, Mistral 1:11 C |
| 1:24 | Vote 1: A has Qwen, Gemma. 2 of 5 |
| 1:30 to 2:36 | Round 2. Llama to Qwen 1:31 to 1:41 (summaries 1:34, 1:41). Gemma to Llama 1:41 to 1:48 (summary 1:44, cites Renewal p. 1). Qwen to Mistral 1:48 to 1:58 (summary 1:49.5). Mistral to all 1:58 to 2:08, moves to A. Pause at 2:02 for 15 s. Phi to Gemma 2:08 to 2:20 (Renewal p. 2 has one signature). Owner note 2:14: "I want to be out by the end of February." Llama to Gemma 2:20 to 2:32 |
| 2:40 | Vote 2: A has Qwen, Gemma, Mistral. 3 of 5 |
| 2:46 to 3:36 | Round 3, note delivered. Qwen to Llama 2:47 (quotes Renewal p. 1, "replaces section 14"; notice by 30 December 2026). Llama to Qwen 2:58, moves to A. Phi to all 3:08, stays D. Gemma to all 3:18 (House rules p. 4: email counts). Mistral to all 3:27 |
| 3:40 | Vote 3: A has four, D has Phi. Agreed; clock stops |
| after | Qwen writes the answer (11 s), Phi adds one note, `answer.released`: "Agreed 4 of 5, 3 rounds, 3:40" |

At 1:50 the bubbles are Qwen "Tells Mistral the fee is one month at the new rent." (full), Gemma "Cites the renewal letter, page 1: fee is one month." (full), Llama "Holds that a letter cannot change the lease." (half faded).

**Variants** (each reuses a prefix of the main list)
- `lease-3`: Llama, Qwen, Gemma. Vote 1 is 2 of 3; vote 2 at 2:10 is 3 of 3.
- `lease-7`: adds Granite and Hermes. Vote 1 is 4 of 7, needs 6.
- `lease-7-busy`: five overlapping turns at 1:50. Layout stress only, labelled "only if seats may talk at once".
- `lease-timeup`: limit 2:00; main events to 1:58; at 2:00 released as no-consensus on the vote-1 tally, notes from Llama, Mistral, Phi.
- `lease-failed`: Phi fails at 0:06 ("not enough free memory on the GX10"); continuing gives 4 seats needing 4.

**Invariants for unit tests**
1. needed(3..7) = 3, 4, 4, 5, 6.
2. `seq` strictly rises; `clock` never falls, is constant while paused, never exceeds the limit.
3. Every `turn.started` has one `turn.ended`. The main fixture never has two turns open; the busy fixture does, and `viewAt` handles both.
4. Each tally: group sizes sum to live seats; agree is the leading group's size; reached only when agree is at least needed. Main tallies are 2, 3, 4 of 5, with exactly one dissent, from the one seat outside the final group.
5. Every file citation names an attached file and a page within its page count.
6. Short names are unique and at most 7 characters; summaries at most 80 (fixtures at most 55).
7. Bubble opacity is 1 from 0.25 s to 8.25 s after its summary, 0.5 at 9 s, 0 from 9.75 s; with reduced motion only 0 or 1.
8. At clock 1:50: 3:10 left, speaking is [Qwen], bubble opacities Qwen 1, Gemma 1, Llama 0.5.
9. A note queued in round r is delivered at the start of round r + 1.
10. `viewAt` is pure, and at the end equals the full fold.

## 4. Shapes
```ts
type Ms = number; type Id = string;
interface Seat { id: Id; index: number; shortName: string; modelName: string; role?: string }
interface FileRef { id: Id; name: string; pages?: number; from: 'attachment' | 'library' }
type Citation = { kind: 'file'; fileId: Id; page?: number; quote?: string }
              | { kind: 'council'; entryId: string };            // reserved for Phase 6
type Phase = 'spooling' | 'research' | 'debate' | 'vote' | 'writing' | 'released';
interface Base { v: 1; seq: number; debateId: Id; at: Ms; clock: Ms }
// at: ms since the question was sent. clock: debate clock, 0 until research starts, frozen while paused.
type DebateEvent = Base & (
  | { type: 'debate.created'; question: string; files: FileRef[]; seats: Seat[]; limitMs: Ms }
  | { type: 'seat.status'; seatId: Id; status: 'loading' | 'ready' | 'failed' | 'dropped'; reason?: string }
  | { type: 'phase.changed'; phase: Phase }
  | { type: 'clock.paused' | 'clock.resumed' }
  | { type: 'round.started'; round: number }
  | { type: 'turn.started'; turnId: Id; seatId: Id; round: number;
      kind: 'research' | 'position' | 'reply' | 'answer' | 'dissent'; to: 'all' | Id[] }
  | { type: 'turn.delta'; turnId: Id; text: string }
  | { type: 'turn.ended'; turnId: Id; text: string; citations: Citation[]; error?: string }
  | { type: 'summary.posted'; summaryId: Id; seatId: Id; turnId?: Id; text: string;
      source: 'summarizer' | 'self' | 'engine' }
  | { type: 'tally.posted'; round: number; basis: 'round-vote' | 'closing' | 'live';
      groups: { answerId: Id; statement: string; seatIds: Id[] }[]; leading: Id;
      agree: number; seats: number; needed: number; reached: boolean }
  | { type: 'note.queued' | 'note.delivered'; noteId: Id; text: string; round: number }
  | { type: 'answer.released'; outcome: 'agreed' | 'no-consensus' | 'stopped'; turnId: Id;
      tallyRound: number; rounds: number; elapsedMs: Ms; dissentTurnIds: Id[] }
);
interface SeatView extends Seat {
  status: 'loading' | 'ready' | 'failed' | 'dropped';
  activity: 'idle' | 'researching' | 'speaking' | 'writing';
  mark: 'agrees' | 'differs' | null;
  bubble: { summaryId: Id; text: string; opacity: number } | null }
interface TurnView { turnId: Id; seatId: Id; round: number; kind: string; to: 'all' | Id[];
  clock: Ms; text: string; done: boolean; citations: Citation[] }
interface DebateView {
  phase: 'idle' | Phase; paused: boolean; round: number; clock: Ms; leftMs: Ms;
  seats: SeatView[]; speaking: Id[];                               // none, one or many
  tally: { round: number; basis: string; agree: number; seats: number; needed: number; reached: boolean } | null;
  turns: TurnView[]; notes: { noteId: Id; text: string; state: 'queued' | 'delivered'; round: number }[];
  answer?: { outcome: string; agree: number; seats: number; rounds: number; elapsedMs: Ms; turnId: Id; dissentTurnIds: Id[] } }
declare function viewAt(events: DebateEvent[], at: Ms, opts?: { reducedMotion?: boolean }): DebateView;
declare function needed(seats: number): number;                    // Math.ceil((4 * seats) / 5)
declare function tableLayout(n: number, width: number, height: number):
  { r: number; headD: number; seats: { x: number; y: number }[]; bubbleMaxWidth: number; maxBubbles: number };
```
Why this stays valid: there is no "current speaker" field (speakers are the seats with an open turn); summaries are their own events with a `source`; agreement arrives only as a tally with opaque groups and a `basis`.

## 5. Table View geometry
- Reference stages: 1440 x 900 gives 1040 x 628 (532 px above the flat edge). 1024 x 768 with the icon rail gives 912 x 588 (492 px above).
- Figure: head diameter D; body 1.4 D wide and 0.7 D tall, 2 px under the head. D is 72 (3 to 5 seats at 1440), 64 (6 or 7 at 1440; 3 to 5 at 1024), 56 (6 or 7 at 1024). A 7-character name at 11 px needs about 44 px, so 56 is the floor.
- Seat i of N, counted from the left: angle 180 x (i - 0.5) / N degrees from the left end of the flat edge; body-bottom centre at (cx - R cos, flatY - R sin); figures stay upright. This matches the wireframe (18, 54, 90, 126, 162 degrees on a ring of about 300 px; table radius about 0.84 R).
- R = min(W/2 - 0.7 D - 8, heightAbove - (1.7 D + 2) - 132), leaving two bubble rows. Result: 275 (3 to 5 seats) and 289 (6 or 7) at 1440; 249 and 262 at 1024.

| N | Angles, left half | x / R | height / R |
|---|---|---|---|
| 3 | 30, 90 | 0.866, 0 | 0.5, 1 |
| 4 | 22.5, 67.5 | 0.924, 0.383 | 0.383, 0.924 |
| 5 | 18, 54, 90 | 0.951, 0.588, 0 | 0.309, 0.809, 1 |
| 6 | 15, 45, 75 | 0.966, 0.707, 0.259 | 0.259, 0.707, 0.966 |
| 7 | 12.9, 38.6, 64.3, 90 | 0.975, 0.782, 0.434, 0 | 0.223, 0.623, 0.901, 1 |

- Gap between neighbouring seats for 3 to 7 seats: 275, 210, 170, 150, 129 px at 1440; 249, 191, 154, 136, 117 px at 1024.
- Bubble: 13 px text, two lines, 52 px tall, 12 px above the head, roughly 6.4 px per character.

**Can the no-overlap rules always be met? No.** A placement search (bubbles may shift sideways or rise, never touch a figure or another bubble) found:

| Seats | 1440 | 1024 with icon rail | 1024 with full sidebar |
|---|---|---|---|
| 3 or 4 | all at once at 280 px | all at 240 | all at 200 |
| 5 | all at 280 | all at 216 | only with end bubbles lifted 120 px |
| 6 | all at 240 | all at 200 | fails at 200 |
| 7 | any 4 at 240; all 7 fails | any 3 at 200; all 7 fails | fails |

The PDF's rule "no wider than the gap" would give 129 px at 7 seats, about 32 characters over two lines, which cannot hold a sentence. What gives is in `decisions`. Seven seats also leave only 7 to 10 px between neighbouring figures.

## 6. Routes and review scenes
| Route | Shows |
|---|---|
| `#/chat/new` | Empty chat |
| `#/chat/:fixture?scene=&at=&view=&seat=&sheet=` | Fixture is lease, lease-3, lease-7, lease-7-busy, lease-timeup or lease-failed |
| `#/history`, `#/library`, `#/models`, `#/settings` | The shared "later" page |
| `#/gallery` | Tokens, components, seat states, bubble stages, council.md chip specimen |
| `#/review` | Every scene in both themes, and the questions |

Scenes (1440 unless noted; "both" adds 1024): gallery; chat-new; chat-asking; spooling; researching; debating-table (both); debating-thread (1024); debating-columns; seat-sheet (Gemma at 1:50); vote; paused; owner-note; note-delivered (thread at 2:50); agreed; released (both); released-open; no-consensus; model-failed; table-3; table-7 (both); table-7-busy (both); shortcuts; later-page.

### Critical Files for Implementation
- /Users/lucasta/projects/gx10-council/ui/src/lib/events.ts (event and view types)
- /Users/lucasta/projects/gx10-council/ui/src/lib/viewAt.ts (pure fold from events and time to view state, with bubble timing)
- /Users/lucasta/projects/gx10-council/ui/src/lib/tableLayout.ts (seat positions and bubble placement, tested for no overlap)
- /Users/lucasta/projects/gx10-council/ui/src/fixtures/lease.ts (main event list and the five variants, with story.test.ts beside it)
- /Users/lucasta/projects/gx10-council/ui/src/review/states.ts (the scene list that drives /review and the browser checks)

## Decisions
- **Where the Table / Chat switch sits. PDF text says bottom right. The page-4 wireframe draws it on the message-box row, right of the box and outside the stage. The page-6 and page-7 wireframes draw it inside the stage's bottom-right corner.** Right end of the stage footer, directly above the right end of the message box. It appears at spool-up and goes when the stage folds. _Why:_ Still reads as bottom right, matches two of three wireframes, keeps the message box full width at 1024, and travels with the stage when replay arrives in Phase 7.
- **Whether the stage opens 'inside the conversation' (page 4) or 'above the message box' (page 10).** It is the last item in the conversation, after the question, and while live it fills the pane above the message box (the question scrolls up). _Why:_ Both sentences stay true, and 'folds into a card above the answer' only works if the stage is in the conversation flow. Table View also needs at least 588 px of height.
- **Status pill wording. Text says round, time left and agreement. The wireframe pill reads 'Debating, round 2, 3:10 left' with no agreement.** Three parts: state or round, time left, short agreement ('Round 2, 3:10 left, 2 of 5 agree'). 'Needs 4' lives in the stage (table centre, Chat View header strip). _Why:_ Follows the text, stays slim at 1024, and gives every debate state a defined wording.
- **When the agreement number changes. All three wireframes show 'Round 2, 3 of 5 agree' while the only vote so far is 'Round 1 vote, 2 of 5 agree'. The text says answers are matched at the end of each round.** The number changes only at a vote. The sample has three votes (2, 3, then 4 of 5), so three rounds, not the two in my brief. During round 2 the meter shows the round-1 result. _Why:_ A meter that moves mid-round would assert live matching, which is one of the three unknowns. The tally event carries a 'basis' field, so live matching can be added later without changing shapes.
- **Who is talking at 'round 2, 3:10 left'. Table wireframe: Qwen. Chat wireframe: Mistral is writing.** One timeline: Qwen is speaking at clock 1:50 in both views. Turns never overlap in the main sample. _Why:_ A single speaker is true whether seats speak one at a time or several at once. Overlap is shown only in the separate, labelled lease-7-busy scene.
- **'council.md L7' chips and the review card in the table centre appear in the PDF's views, but Learning is Phase 6.** The citation type reserves a 'council' kind. The sample debate has none. The gallery shows one chip specimen marked as arriving with Phase 6. The review card is left out. _Why:_ Keeps Phase 1 screens honest about what exists while fixing the data shape now.
- **Seat colours versus black-and-white Chat View, which sits inside a coloured app.** The rule covers everything inside the Chat View panel: messages, dividers, chips, header strip, filter, focus rings, and the agreed and failed marks (words plus an icon). The app frame keeps its theme. Top-bar seat names are plain text in every view. _Why:_ Models are then told apart by name everywhere the Chat View is on screen, and no colour is needed to match a column to a seat.
- **What the top bar's 'Council of 5' shows. The wireframe has only those words; the text says the bar shows the seated council.** A button with the count and the short names in seat order. It opens the seat picker (read-only while a debate runs). A saved council's name replaces the count from Phase 3. _Why:_ Names answer 'who is seated' at a glance and the button gives the picker a home.
- **The vote is shown twice: on the folded stage card and as the answer's heading, and both link to replay.** One unit. The folded card is the answer's header: vote, rounds, time, each seat's mark, 'See the debate'. _Why:_ Removes a duplicate heading and a duplicate link.
- **'Clicking the card replays the debate', but Replay is Phase 7.** In the mock the card unfolds the stage at its final state. Playing from the start exists only in the review bar's player. _Why:_ Nothing in the product frame pretends replay is built.
- **Bubble rules cannot all hold: one or two sentences, two lines, no wider than the gap between seats, never overlapping.** Width is set by the window, not the gap: 280 px (3 to 5 seats) or 240 px (6 or 7) at 1440; 216 or 200 px at 1024. One short sentence: engine cap 80 characters, sample lines at most 55, two-line clamp, full line in the side sheet. At most 4 bubbles at once at 1440 and 3 at 1024; the oldest starts fading when a newer one needs its place. The sidebar becomes a 64 px icon rail below 1100 px. _Why:_ At 7 seats the gap is 129 px, about 32 characters. The cap only bites at 7 seats and only if the engine lets many seats talk at once; a seat without a bubble still has its speaking mark, and Chat View holds every word.
- **Fixed scenes, or scenes plus a player.** Named scenes are the contract for screenshots, accessibility and the gate. Add a small player in the review bar (play, pause, jump to a scene, 1x and 4x), outside the app frame and hidden in screenshots. If it slips, the gate still passes on scenes. _Why:_ Cost: about one extra builder stage (my estimate), mostly a clock hook and a control bar, because viewAt and the bubble timing are needed for coherent scenes anyway and are reused in Phases 5 and 7. Gain: the fixed motion requirements (250 ms in, 8 s hold, 1.5 s out, crossfade, seats fading in, the stage folding) cannot be judged from stills. Screenshots stay deterministic because every scene is a URL with a time, viewAt is pure, bubble opacity and streamed text length are computed from the clock rather than CSS timers, a still mode turns all transitions off, and capture waits for fonts and a ready attribute.
- **Seat order.** One order everywhere: picker order is left to right at the table, in the top bar and in Chat View columns. The sample seats Phi, Llama, Qwen, Gemma, Mistral, as the wireframe draws them. _Why:_ Keeps Qwen top-centre as in the wireframe and gives one rule to test.
- **Pause and Stop appear in the text but in no wireframe.** Left end of the stage footer. Pause becomes Resume. Stop shows 'Not in this mock yet'. _Why:_ Keeps debate controls with the debate and leaves Send in the composer for notes.
- **When the debate clock runs (not stated in the PDF).** Starts when research starts, excludes model loading, freezes on pause, stops at agreement. Message times and bubble timing use this clock. _Why:_ Matches the wireframe's message times against '3:10 left' of 5:00, and makes the paused scene a true freeze.
- **What happens when a model fails to load (not stated in the PDF).** The stage shows what went wrong and three choices: Try again, Continue with 4, Stop. Continuing recomputes the bar on the remaining seats. _Why:_ For the 5-seat sample both possible rules give 'needs 4', so the scene is true either way. Final rule is an owner question.
- **Which tally a time-up answer uses.** The last completed vote. The variant uses the 2-minute preset and ends 'No consensus, 2 of 5' with a 2-1-1-1 split and three dissent notes. _Why:_ Does not assume a closing vote exists, reuses the main list's first two minutes, and stresses the answer layout with the most notes.
- **Wireframe annotations: the 'Chats' heading over the sidebar, 'You sit here, facing the council', the 'Council stage' label, and the blue and pastel colours.** None is rendered. The flat edge of the table carries the owner's queued note instead. _Why:_ They are drawing notes; a heading over five items of which three are not chats would be a label for its own sake.
- **Chat View columns at 5 to 7 seats.** Columns only when each gets at least 200 px (3 to 5 seats at 1440, 3 or 4 at 1024), otherwise one thread. Columns are banded by round. The filter shows in thread mode. _Why:_ Seven columns at 1440 would be about 150 px each. Round bands keep order readable without a sparse time grid.
- **Sample topic and names.** An invented apartment-lease question with three invented files; model names marked as examples; app name string 'GX10 Council' (the PDF header still says Cluster). _Why:_ Plain to read by eye, has a natural reason for one honest dissent, and cites pages in both PDF and Word files. None of the owner's real files is read.
- **Animation library pin.** motion 14.1.0 (MIT, peers React 18 or 19), checked on the npm registry today. _Why:_ The PDF names Motion and it is missing from the previous plan's stack table.

## Risks
- I did not see the wireframes as pictures. Their text and shapes were read by text recognition and pixel maps. A build agent should render pages 4, 6 and 7 and confirm three things by eye: where the switch sits, the 80% tick on the meter, and the seat angles.
- The bubble feasibility table comes from a heuristic placement search, not a proof, and assumes about 6.4 px per character. A wider font from the design pass lowers the character counts. Phase 1 needs a unit test that tableLayout plus bubble placement never overlap for every seat subset up to the cap at both sizes, and a browser check that every sample summary fits two lines.
- Seven seats leave 7 to 10 px between neighbouring figures and need the icon rail at 1024. With the full 240 px sidebar at 1024, six or seven seats do not fit with usable bubbles.
- At 1024 x 768 the stage takes the whole pane and the question scrolls out of view. A real browser window on the MacBook Air is about 835 px tall, so the same rule applies there.
- If the back-end research chooses live matching, the pill and meter will move between votes. The shapes allow it (tally basis 'live'), but the sample's three-round story and the wording 'at the round 1 vote' would change.
- If summaries come from each agent rather than a separate model, a seat may speak for a while with no bubble. The spec keeps the speaking mark independent of the bubble, and the visual directions must do the same.
- The player shows sample pacing (a turn about every 10 s, three rounds in 3:40). Real speed with five models on one GX10 is unknown and may be much slower; the review bar must say so.
- Chat View columns for five seats at 1440 are about 214 px wide, roughly 30 characters a line. It meets the PDF but may read as cramped; the owner sees it at the gate.
- Model full names and file contents are invented examples. Short names are limited to 7 characters; longer real names will need a shortening rule in Phase 3.
- Live updates in Table View can flood a screen reader. The mock should announce only round and vote changes, and put the latest summary in the seat button's name.
- The webapp-testing skill's examples use Python Playwright and write to /tmp and /mnt/user-data/outputs. Python Playwright is not installed, and a version that does not match @playwright/test 1.64.0 would download a second set of browsers. Agents should take the skill's method (look first, wait for the page to settle, capture console errors, use with_server.py as a black box) and write outputs inside the repo.
- Two CLAUDE.md files on this Mac describe other projects (a trading system and a defense-compliance tool). Their rules do not apply here; only the note that the founder wants plain-language framing does.

## Questions for the owner
- Should the mocks also play the sample debate, so you can judge the bubble fades and the stage opening and folding in motion? I recommend yes; it adds roughly one agent stage of build time. Without it you review still screens only.
- When a model fails to load, should the council stop and ask you (Try again, Continue with fewer seats, Stop), or carry on by itself with the seats that loaded? The mock shows the first.
