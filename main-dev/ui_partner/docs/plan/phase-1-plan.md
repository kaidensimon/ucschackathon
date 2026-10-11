# GX10 Council: Phase 1 build plan (pick a look, then design system and mocks), with the road map for Phases 2–7

> **Amendment, 2026-10-10 (after approval): Electron.** Lucas: "Make this compatible with Electron.js and it is completely completed in electron".
> How this is read: the finished product is an Electron desktop app, not a browser tab, and the optional Tauri wrapper is dropped.
> What changes in Phase 1:
> - The React app is built so it runs inside an Electron window as well as in the checks' browser (relative paths, hash routes, no Node access from the page, every outside request refused by the shell).
> - Both stops open in Electron, not Chrome or Safari: the look chooser at G0, and at G1 a real `GX10 Council.app` you double-click. The "which browser" question is no longer needed, and the Safari-like (WebKit) test pass is dropped.
> - The final check also opens the built app in the real Electron shell (`look:app`): the window opens, nothing leaves the machine, and the page has no Node access.
> - Added tools: `electron` 44.7.0 and `@electron/packager` 20.3.0 (pinned). This was a second download step.
> What it leaves open for the Phase 2 plan: where the engine lives. The models run on the GX10; the Electron app can run on the Mac and talk to the GX10 (closest to the PDF), or run on the GX10 itself, and the gateway can stay Python (the PDF's FastAPI and LangGraph) or move into Electron's own Node process. That is Lucas's decision at the Phase 2 plan.

## Context

Lucas attached a new `GX10 Cluster UI Plan.pdf` (16 pages, dated 2026-10-10, in `~/Downloads/`, titled "GX10 Council UI Plan") and asked: "plan this using the plugin as reference with some of the work".

The product changed since the plan written earlier today. The earlier idea (one model split across the GX10 and three Macs) is dropped. The new one is a **council**: 3 to 7 local models, all on the GX10, debate a question in rounds and release one agreed answer when 80% of seats agree or a time limit runs out. They research only Lucas's own files. He watches in Table View (a half-circle table with summary bubbles) or Chat View (the full messages), and a `council.md` file learns lessons after a council vote.

Answers given on 2026-10-10 (this session):
- **"The plugin"** is the Anthropic skills collection added at 4:15 pm (`anthropics/skills`). Use its **frontend-design** skill for the look and wording, and its **webapp-testing** skill for browser checks (its method; its testing program is swapped for the project's own equivalent, explained under "How the two skills are used").
- **The look: "Let the skill redesign."** The PDF's colours and fonts become a starting point only.
- **Shape:** a detailed Phase 1, a road map for Phases 2–7, and a stop for review after Phase 1.
- **Studies:** three looks to choose from; the PDF's original look is not drawn as a fourth.
- **Usage:** no ceiling. At each stop the lead reports how many agent runs and tokens each workflow used.
- **Talk with sub-agents:** short "Stone Age" talk, to save tokens and time.

Carried over from the earlier session's answers: build in phases with multi-agent workflows; llama.cpp already runs on the GX10; the first model is not a concern yet.

**State today.** No GX10 code exists; the earlier plan (`~/.claude/plans/distributed-puzzling-zephyr.md`) was stopped before anything was built. This Mac (the M5 MacBook Air, 24 GB) already has the tools Phase 1 needs: Node, Python, uv and git. `~/.claude/CLAUDE.md` describes a different project (defense compliance); its regulatory rules do not apply here, and its "Founder Context" section does.

**How this plan was made.** All read-only; nothing was built, installed, or run on the GX10.
- Reused: the earlier session's research on the front-end tools, document search and GX10 hardware.
- Research (10 agents): the five areas the Council design adds, each re-checked by a second agent.
- Design (7 agents): three design leads each wrote a rival look following the frontend-design skill, two judges compared them, one planner specified the screens and one planned the build and checks.
- Audit (3 agents): this file checked for unsupported claims, contradictions and readability. Their corrections are in.

## In plain words

**What you get.** A new folder, `~/projects/gx10-council`. First, three sample pages to choose from, one per look (called studies below). Each shows the same four moments of a debate, in light and dark, so the only thing that differs is the look. Then, in the look you pick: fonts, colours, building-block components, light and dark themes, and clickable mock screens of the chat, Table View and Chat View. They run in a browser on this Mac from one invented sample debate. Nothing talks to a model yet.

**Two stops, not one (your call).** You asked for one stop, after Phase 1. I am proposing a second, earlier one, because letting the skill redesign means someone has to choose the new look before everything is built in it, and I think that should be you. About two hours in (an estimate) you open one page and pick from the three studies, about five minutes of your time. I tell you when that first sitting is finished; from then on nothing is running, and the second sitting starts whenever you have picked, the same day or later. If you would rather keep to one stop, say "you pick": I build in look A, which both judges ranked first, and you first see it at the Phase 1 review. The risk is that if you dislike it then, much of the second sitting (roughly 4 to 5 hours) is redone in another look. Further down the two stops are called G0 and G1.

**What you decide.** At the first stop: which look (A, B, C, a blend, or none). At the second: about a dozen short questions on the review page, answered by number in chat; allow half an hour or more (an estimate). Most ask whether a screen looks right. Three settle open points: what happens when time runs out before 80% agree, whether Chat View's columns should depend on the window's width (both open questions in your PDF), and what happens when a model fails to load (new). The last asks whether to go on to Phase 2. Decisions for Phases 3 to 6 are in a table further down and need nothing from you now.

**What it takes.** Roughly 5.5 to 7.5 hours of machine time to reach the review, in two sittings: about 1.5 to 2.5 hours before your pick and about 4 to 5 after it. This is an estimate, not a measurement, and it was worked out when the list of screens was about half its present length, so expect the upper end or more; I give you a revised figure at your pick, once the first steps have been timed. After the review, expect one or two rounds of changes of 30 to 60 minutes each: the phase is done when the mocks look right to you, not when the first build finishes. An agent run is one helper agent doing one job (building a screen, reviewing, fixing). The plan has 15, or about 20 if every planned re-run is used; a stage that fails and is redone, and changes after the review, are on top of that. The earlier plan was 7 to 10 hours and about 24 runs. This consumes Claude usage and I cannot predict how much. You chose no ceiling, so at each stop I report what each batch of agents used.

**What I need from you.**
1. Plug this Mac in and leave the lid open. Closing it stops the run.
2. Approve the permission pop-ups at the start (each asks whether I may run a command). Choosing "always allow" for this project's build commands (they begin with `npm`) should let it run unattended. The first batch of agents is small and tests exactly that; if they are blocked, I stop and ask.

The first build step downloads the app's building blocks and two test browsers from the internet. That is the only step that downloads anything, and apart from those tools' usual download folders nothing is written outside the new project folder.

**Three things to confirm (the first two can wait; the third is best answered before I start).**
1. Your GX10 has 128 GB of memory (taken from ASUS's specification).
2. This is for personal use on your home network with no login, as your PDF says. A ZeroTier installer was downloaded on this Mac today: if the GX10 will be reachable through ZeroTier, every device on that ZeroTier network can open the app. And if defense-customer documents might ever go into it, tell me before Phase 2, because that changes the access design.
3. Which browser will you use for this app: Safari (this Mac's default) or Chrome? The checks run in Chrome, so I open both stops in Chrome unless you say otherwise. If you will use Safari, say so before the build: every scene, not four, is then also run in the Safari-like test browser, I check the three studies there too, and both stops open in Safari.

## The three looks you will choose from

Each was written by a separate design lead following the frontend-design skill: ground the look in the subject, plan it, then check the plan against the skill's list of generic AI looks and revise.

**None of the three keeps your PDF's warm paper.** The skill names that combination (a warm cream page, serif titles, a clay accent) as the most common look of AI-made pages, and your PDF's page colour is one step from its example, so all three designers moved away from it. A keeps the most warmth (a walnut table and an amber lamp).

The table shows each look after the judges' corrections.

| | A. The Lit Table | B. Fair Copy | C. Cut-Out Council |
|---|---|---|---|
| In one sentence | A pale, quiet room with one dark wooden half-round table; a small warm lamp comes on in front of whichever model is speaking. | The debate is written down in front of you like minutes being taken, and the agreed answer arrives as the clean final copy. | Seven flat, one-colour cut-out figures, each with its model's name lettered large inside its head; everything else is plain ink on white, so the council is the only colour you see. |
| Borrowed from | The council chamber: a horseshoe table seen from the chair, a light at the speaker's seat | The record: stenographer's pad, registrar's ink, the copying pencil, tally marks | Game pieces and picture statistics: a vote is a head count |
| Page and ink | Cool plaster `#E9ECE8`, ink `#1D2427` | Steno-pad green-grey `#E5ECE4`, blue-black `#1A2435` | White, ink `#17201C` |
| Colour | Walnut table `#4A3628` with an oak rim; amber `#F4B740` only where something is live. Buttons are ink. | Violet `#67298C` only for what is live (the ring round the speaker, the blinking cursor where text is being written). Buttons are ink. Green only at agreement. | No accent at all. The seven seats are the only colour. |
| Seats | Solid deep "leather" colours with pale lettering, and a seat number on each body | A pale tint with a coloured ring, and a different fine line pattern (hatching, as in an engraving) on each body | Solid colour, the name cut out and sized to fill the head, a different cut in each body |
| Type | Besley (a sturdy, heavy-footed serif of the kind used on old notices) for titles; Atkinson Hyperlegible Next (a sans drawn so that l, I and 1 cannot be confused) for everything else | Literata (a book serif) for everything you read; Archivo (a plain sans) for labels, names and numbers | Archivo only, using its narrow-to-wide range to fit each name to its head |
| The one bold thing | The lit table | The tally: one stroke per seat, underlined at the number needed, ruled off with a second line at agreement | The figures |
| Biggest risk | A wooden table may feel too literal; five dark seats round a dark table may look heavy in the light theme | The least calm: the line patterns, a ruled margin line and the bubbles (drawn as small paper notes) all compete with the tally. Both judges rated it the hardest to build, and the line patterns are untested on an ordinary (non-Retina) monitor. | Nearest to an ordinary chat app: a coloured circle with a name is the standard avatar |

**What the two judges found.** One judged distinctiveness against the skill's lists, the other whether each look works. Both recomputed the designers' contrast figures, which held, and confirmed the fonts on npm. They also found a few colour pairs the designers had not checked; those are corrected below.
- **Ranking.** Both put A first. They split on second place (one B, one C). Neither would show any of the three as first written. One says all three are worth showing once corrected; the other would show B only after its line patterns are proven on an ordinary screen.
- **Too alike as first written.** All three had left cream for nearly the same pale grey-green page, and B and C used the same two typefaces. Corrections: C moves to a white page and to Archivo alone; B keeps its tint, which its subject supplies; A stays, because the walnut table carries it. A and B will still share a similar pale page: pale colours cannot differ much, so they differ by table, figures, type and accent. In dark, the three pages are close to one colour, so the dark studies differ by table and figures only. With the table set aside, A and C also draw their figures alike (solid colour, pale name); the walnut and the lamp separate them.
- **Corrections to A.** Vote marks get a filled disc, because dark marks vanished on the dark seats. The speaking head gets a dark ring as well as the lamp, because the lamp sits on the table, away from the figure. The lamp's pool of light is sized to the gap between seats. Seat numbers stay on the bodies but leave the top bar and Chat View, where they read as speaking order. One seat colour, a dark blue-grey, was nearly the text colour; it changes so it cannot be mistaken for a button. Focus rings get a gap of page colour round them.
- **Corrections to B.** Send becomes an ink button (a white label on purple is the stock AI-product button). Keyboard focus on a seat becomes a dark outline round the whole figure, so it cannot be mistaken for "speaking". Seat rings thicken so the seat colour can be seen. Its study shows the table with and without the line patterns, each at ordinary and at Retina sharpness, and one bubble in upright and in italic type in the dark theme, so you can say which reads better. One thing for you to judge: in B the head is a pale tint with a coloured ring, not a head filled with the seat colour as your PDF describes.
- **Corrections to C.** The top bar writes the names beside its small figures (coloured dots alone made colour the only signal). Bubbles lose their shadow and get a clearly visible edge. The small "leaning toward" and "reading" postures are left out, because they need information from the engine that nobody has confirmed it will supply. One set-piece animation, not two. How each name is sized to fill its head is checked in a real browser, because the designer's widths were estimates. The ring round the speaking head is the same colour as the head, so the study is checked at five and seven seats, and a dark ring is added if the speaker does not stand out.
- **For all three.** Sizes (stage, table, bubbles, Chat View columns) come from the shared screen spec, not from each look. Vote marks are a check on a solid dark disc and a cross on a pale disc with a dark outline. A cross is never red, because disagreeing is not an error. Keyboard focus on a seat is an outline round the whole figure; a ring round the head always means speaking.

## What stays fixed whichever look you pick

These come from your PDF and are treated as function, not look:
1. Calm and readable, generous spacing, smooth fades, light and dark themes. Not a control panel. (Your PDF's "warm low-contrast palette" is not on this list: it is part of the look, which you opened to redesign.)
2. Body text at 4.5:1 contrast or better.
3. Table View: half-circle table, flat side toward you; 3 to 7 agents along the curve; each a full-circle head holding the short name above a half-circle body, in its seat colour; colour never the only signal; the speaker is marked; a check or cross on every head after a vote; the middle shows round, time left and "3 of 5 agree, needs 4".
4. Bubbles: a short summary above whoever is talking, two lines at most, never overlapping; fade in 250 ms, stay about 8 s, fade out about 1.5 s; with reduced motion they appear and disappear.
5. Chat View in black and white only; models told apart by name; one column per model when wide, one thread when narrow.
6. The small Table / Chat switch at the bottom right while the council works.
7. Frame: slim top bar, sidebar (New chat, History, Library, Models, Settings), the stage opens in the conversation and folds into a card above the answer.
8. Open-licence fonts bundled with the app (no internet at run time).
9. Keyboard first: visible focus rings, full tab order, a shortcuts help sheet.

## The two stops (G0 and G1)

**G0, pick a look** (about two hours in, an estimate).
- I open one file for you, `Choose a look.html`, in Google Chrome (already on this Mac), because Chrome is the browser the checks run in. It needs no server and no internet. For each study: a plain name, two sentences, light and dark side by side. Clicking opens the study itself, with a theme switch and a Play button that shows one bubble fade.
- You answer in chat:
  1. Which do you want to live with: A, B, C, a blend (say which parts), or none?
  2. Does its dark version look as good as its light one?
  3. What one thing bothers you in it?
- Each study also names the one or two things only you can judge in it. For example: C's figures have no faces (the name is the face); B's patterned bodies; A's wooden table.
- A blend or "none" gets one more study and a yes or no, once. If the answer is no, the build stops there and we talk; nothing is built in a look you have not accepted. Your answers to questions 2 and 3 go into the chosen direction as written corrections before any colour or font is fixed; they do not get a new study. Later changes wait for G1.

**G1, review the mocks.**
- Open: double-click `Open GX10 Council mocks.command` in the project folder. It opens the review page in Google Chrome and a small Terminal window; leave that window open while you look, and close it when you are done. A sheet of the screenshots (`docs/review/phase-1/index.html`) works with nothing running.
- The review page asks:
  1. Calm and readable, or control panel?
  2. Still the look you picked?
  3. Table View: can you tell at a glance who is speaking, who agreed and how close they are?
  4. Are the names in the heads readable with 3, 5 and 7 seats?
  5. Bubbles: is one short sentence enough, and is the fade speed right (press Play)? Judge the fades, not how fast the debate moves: the sample's pace is the best case.
  6. One speaker at a time and several at once are both shown, because the engine has not been built. Does either look wrong?
  7. After a vote, the check or cross stays on each head until the next round starts, as your PDF says, so during a round the heads are bare while the table still shows the last count. Keep that, or leave the marks up until the next vote?
  8. Chat View and the answer: right, or change what?
  9. When time runs out, the mock releases the best-supported answer marked "No consensus". Keep that, or should the council keep going?
  10. Chat View switches to columns only on a wide window. Is that what you meant by "based on resolution"?
  11. When a model fails to load, the mock stops and asks you (Try again, Continue with 4, Stop). Keep that, or should the council carry on by itself with the seats that loaded?
  12. Does dark read as well as light?
  13. Go on to Phase 2?
- A slim review bar appears on screens opened from the review page: theme, 3, 5 or 7 seats, Play, and at seven seats one or several speakers. It carries one line: "Sample timing. Real speed on your GX10 has not been measured and may be much slower."
- You answer by number in chat. I record your words, dated, in `docs/BUILD_STATUS.md`; each change becomes its own small piece of work.

## What the research changes in your plan

None of this blocks Phase 1. It shapes Phases 2 to 6, and four rows change what the mocks show. Every llama.cpp fact comes from reading its source, documentation and issue tracker, not from running it on your GX10. Speed and time figures are estimates built from published single-model measurements on GX10-class machines; nobody has published a measurement of several models sharing one.

| Your plan says | What the research found | Consequence |
|---|---|---|
| "The engine checks which answers match" | There is no proven automatic way to tell whether free-form sentences agree. Similarity scoring is not dependable for it: it is weak on negation and numbers, and in one published measurement the final answers to a question all scored 0.84 to 0.92 similar. | Phase 4 uses an explicit ballot each round: the distinct positions are listed by one of the models, each seat votes for one (or "none of these") in a fixed format, and code counts. The listing step is the least proven part of the design: a wrong merge would show a false "Agreed". A built-in test set measures how often it gets this right on your models before the badge is switched on. It cannot prove that an agreed answer is correct. **Mocks:** the agreement number changes only at a vote, and the screen never claims how matching is done. |
| A 5-minute default, presets of 2, 5 and 10 | It depends on which models are seated. With fast models a five-seat round is roughly 35 to 50 seconds, so 5 minutes holds perhaps four to six rounds once voting is counted. With heavier models one five-seat round takes about two and a half minutes or more. The 2-minute preset suits only three fast seats. Models that "think" before answering write noticeably more (2.5 to 3.6 times as much in one published figure). | "Thinking" off by default. The seat picker will show "about N rounds in M minutes" beside the memory meter (Phase 3). Loading the models should not count against the timer. The default stays an open question until measured on your GX10. |
| 3 to 7 seats share 128 GB | The machine has about 121 GiB in total (GiB is the unit the machine reports; read it as GB here), and somewhat less is free. Five mid-size seats fit (about 96 to 102 by calculation, which may be low). Seven seats are tight even when the two extra seats are small models (118 to 126 by calculation); seven mid-size models do not fit. Overfilling this machine does not fail cleanly: in one report it dropped off the network. | The memory check before a debate is strict, with a reserve of at least 10 GiB (Phase 3). |
| One llama-server per seated model; router mode "needs a test" | Settled from the source: router mode can keep several models loaded (its default limit is 4), but each is still a separate server process, so it saves nothing, and it has open bugs. Two seats using the same model can share one server, so the model loads once. | Your pick stands. Router mode is skipped. |
| Agents state a position, answer each other by name and revise, in rounds | Published studies (mostly quiz-style questions; none on a set-up like yours) lean one way: much of the gain comes from models answering independently and then voting; extra rounds do not reliably raise accuracy and can raise conformity. | Phase 4 proposes an independent round 1 with a vote straight after, and expects two or three rounds. Your rules (80%, the time limit, answering by name) stay. |
| Bubbles: one or two sentences, two lines, no wider than the gap between seats, never overlapping | These cannot all hold. By calculation, with seven seats the gap is about 129 px in a window 1440 px wide (this Mac's full screen), room for about 32 characters. | **Mocks:** a bubble holds one short sentence, with the full text in the agent's side sheet. The sample lines are 55 characters or fewer so they fit two lines at every seat count; the real limit is set in Phase 5. Width follows the window, not the gap. With three to six seats every speaker's bubble fits. With seven, at most four show at once in a 1440 px window and three in a 1024 px one; the oldest fades when a newer one needs its place. These figures come from a calculated search, not a proof, and the Phase 1 tests check them in a real browser. You judge the seven-seat worst case at the review. |
| A small fast model rewrites the bubble line every few seconds | A fast seat finishes a turn in about 6 seconds (an estimate), shorter than a bubble's 8-second stay, so most turns get one or two lines. The summariser also competes with the speaker for the one graphics chip; the cost is unmeasured. | Decided in Phase 5 after a test. **Mocks:** a bubble never says who wrote its line, and the mark showing who is speaking is there even when no bubble is. |
| (not stated) Whether seats speak one at a time | On one graphics chip, one at a time is the likely answer, but it is unmeasured. | **Mocks:** the main sample has one speaker at a time; one separate, labelled scene shows several at once. |
| LangGraph for the debate engine | No blocker; your pick stands. It covers the wiring (seats, rounds, the 80% check). Pause, Stop, the timer and the event record are plain Python either way. It adds about 29 packages. It has an optional feature that reports activity to its maker's online service; it is off by default, and the build forces it off so nothing can switch it on by accident. | Phase 4 as you planned, with those additions. |
| `council.md` in git; the council debates each entry | Keep the entries as records in the database and write `council.md` from them, because undoing an old entry directly in the file can conflict. Entry numbers such as L7 must never be reused. The review questions miss "is it still true?". | Phase 6. Changes to your design there come to you as decisions first. |
| Every answer cites file and page | Checking that a model's citation really supports its claim is unreliable when a model judges it. Checking that a quoted passage really appears on the cited page is exact. | Citations carry a short quote, and code marks each one verified or unverified (Phases 2 and 4). |
| Motion (formerly Framer Motion) for fades | Not needed for the mocks, and Motion's reduced-motion mode keeps fades, which breaks your "simply appear and disappear" rule. | Not installed in Phase 1. A bubble's strength comes from the debate clock through the timing function, in play and in stills, so Pause holds it; bubbles carry no separate timer. Revisited in Phase 5 for the stage folding into a card. |
| Example seats Qwen, Llama, Gemma, Phi, Mistral | The research proposes a starting council from five makers with current mid-size models: Alibaba (Qwen), Google (Gemma), OpenAI (gpt-oss), Mistral and IBM (Granite), about 65 GB of files in all. Meta's newest open Llama chat models date from April 2025. | The mocks keep your five names, marked as examples. Real seats are chosen in Phase 3. |

**Before Phase 3: a test on the real GX10, about an hour once the test models are on it (an estimate; nothing here has been timed).** It needs someone at a terminal on the GX10. Unless you give me a way to reach the GX10 from this Mac, that is you: I write one script and plain step-by-step instructions, you paste one line and send me back the results file. It needs three model files on the GX10 first; downloading them is extra time. It answers what no published source does: which llama.cpp version is installed; how long models take to load; how much memory each loaded model really takes; how speed changes with one, two and three models generating at once; and whether the bubble summariser is better on the graphics chip or the processor. One part holds the machine at full load for ten minutes. One GX10 owner reported the machine switching itself off under that kind of load until the graphics chip's speed was capped (which made runs about 25% longer), so the script watches the temperature and stops early if it climbs. It does not block Phase 1 or 2.

## Decisions waiting for you, by phase

Your PDF's six open questions and the new ones the research raised. None needs an answer now.

| When | Decision | Where it stands |
|---|---|---|
| G1 | If time runs out, release the best-supported answer marked "No consensus"? | The mock shows your assumption. |
| G1 | Does "based on resolution" mean Chat View adapts to the window width? | The mock assumes yes. |
| G1 | When a model fails to load: ask you, or carry on with the seats that loaded? | The mock shows asking. |
| Phase 3 | The default time limit | Open until measured on your GX10. |
| Phase 3 | Keep the Llama and Phi names seated, or use current models? | Open. |
| Phase 3 | When one model fills two seats, does each head show the model's name or the role you gave it? | Open. A head holds about 7 characters. |
| Phase 4 | Is an explicit ballot an acceptable reading of "the engine checks which answers match"? | Recommended. |
| Phase 4 | Should round 1 be independent, with two or three rounds expected? | Recommended. |
| Phase 4 | Do two seats on the same model count as two votes? | Open. The research advises against it by reasoning (their votes are not independent evidence); no study tested it. |
| Phase 4 | With 3 of 4 or 2 of 3 agreeing, is the label "No consensus" or something like "Majority 3 of 4"? | Open. |
| Phase 4 | On Pause, does text being written stop at once, or may the current turn finish? | Open; needs a test. |
| Phase 5 | Bubble lines from a separate small model, or from each agent? | Open until the GX10 test. |
| Phase 6 | Does an accepted lesson wait for your OK, or go straight in with an undo notice? | Your PDF assumes undo. The research leans toward your OK for lessons at first. |
| Phase 6 | Can the council turn down a preference you state directly? | Your PDF's assumption (no) stands. |

**You can stop reading here.** Everything below is the working reference the agents build from: what Phase 1 includes, how the skills are used, tool versions, the sample debate, build steps, agent rules, checks, risks and the road map for later phases. You do not need it to approve. The first build step copies it into the project folder, where it is kept up to date.

---

## Phase 1 scope

**In.**
- Repo, project notes, build tracker, research notes, the PDF's wireframe pages saved as pictures (sub-agents cannot open the PDF's images on this Mac).
- Three look studies and the page you choose from.
- In the chosen look: design tokens (the named colours, sizes and spacings every screen draws from), bundled fonts, light and dark themes, reduced-motion support, a contrast test, and a gallery page of every component.
- **App frame:** top bar ("Council of 5" with the seat names, status pill), sidebar (five items; theme switch, Shortcuts and a "Sample data" line in the footer), conversation, message box.
- **Chat:** the question with file chips; the stage; Pause and Stop; the message box turning into "Add a note for the next round"; the folded stage card joined to the answer (vote, rounds, time, each seat's mark, files cited, dissent notes); a "No consensus" answer; a seat picker showing five seats and the 2 / 5 / 10 minute choice.
- **Table View** for 3, 5 and 7 seats: figures, speaker mark, bubbles, vote marks, the middle of the table, and the side sheet that opens when you click an agent.
- **Chat View:** one thread and one column per model, citation chips, vote dividers, the filter, "Jump to newest".
- **States:** new chat, asking, seating the council, reading files, debating, a vote, paused, your note queued and delivered, agreed, released, no consensus, a model that failed to load.
- A small **player** in the review bar (play, pause, jump to a moment) so the fades can be judged in motion. This goes beyond the PDF's "static mocks" and costs roughly one extra agent stage (an estimate); Lucas can say still screens are enough. The shortcuts sheet. A review page linking every scene.

**Out (later phases).** Anything real: models, files, storage. History, Library, Models, Settings and the Council file screen (their sidebar items open one page saying what will be there and in which phase). Thumbs and "Remember this", `council.md` chips, the learning review card, true replay, saved councils, roles, the memory meter, a custom time limit, the phone layout.

Controls that do nothing yet show one quiet line, "Not in this mock yet".

## How the two skills are used

Neither skill is installed as a plugin, and neither needs to be: an agent uses one by being told to read its file under `~/.claude/plugins/marketplaces/anthropic-agent-skills/skills/`. Work package 1.0 copies frontend-design and webapp-testing into the repo's `docs/skills/` so the build does not depend on that folder. The copy of webapp-testing gets one note at the top: use `npm run look`, write no Python, and save screenshots inside the repo (its examples write to folders that do not exist on this Mac).

**frontend-design** (the look and the wording)
- Read in full by: the three study builders, the lead when writing tokens, the design critic.
- Read in part (principles, restraint, writing) by: the frame builder and the three screen builders.
- Not read by: the layout and timing builders, the function critic, the first-time viewer, the fixer and the verifier. The skill tells its reader to make bold choices; after the pick that would invite a redesign.
- Proof it was followed. Each study returns seven things, and a return missing any is rejected: the design plan; the review of the drawn study against the skill's generic looks, with at least one revision to how the study is drawn (the direction's written colours, typefaces and bold element are not changed; a builder who thinks one is wrong reports it to me); computed contrast; the study file; light, dark and grey screenshots; a self-critique written from those screenshots; the fixed-function checklist, ticked.
- After the pick the skill's own rule applies: the brief wins. The chosen direction is the brief.

**webapp-testing** (agents looking at their own work)
- Its method is used as written: look first, then act; wait for the page to finish loading before inspecting; capture console errors; headless; always close the browser.
- Its tool is swapped for a twin. The skill drives the test browser from Python. This project already drives the same test browser (Playwright) from JavaScript for its final check, and today the two are one version apart (1.63.0 against 1.64.0). Using both would download a second set of test browsers and let agents approve screenshots from a slightly different browser than the final check uses. So agents follow the skill's method with the project's own copy.
- Read by: the frame builder, the three screen builders, the fixer and the verifier, from the copy in `docs/skills/`.
- The method becomes two commands, `look` (the running app) and `look:file` (a single file). Each prints screenshot paths, the page's buttons and links, console errors and any outside request. The skill's server helper `with_server.py` is copied in with its licence and used by `look`.

Looked at and not used: web-artifacts-builder (its starter installs React 18 and Tailwind 3.4, older than the stack this app should grow on) and theme-factory (ten preset themes for slides).

## Differences from the PDF in Phase 1

Every critic, fixer and verifier brief carries this list, so nobody "corrects" these back.

1. **The look** is whichever direction Lucas picks, not the PDF's palette and fonts.
2. **The switch** sits at the right end of the stage's footer, just above the right end of the message box. The PDF's text says bottom right; its three wireframes draw it in two different places.
3. **The stage** is the last item in the conversation and fills the space above the message box while live. This satisfies both "inside the conversation" (page 4) and "above the message box" (page 10).
4. **Status pill:** state or round, time left, short agreement ("Round 2, 3:10 left, 2 of 5 agree"). "Needs 4" lives in the stage.
5. **The agreement number changes only at a vote.** The sample has three votes (2, then 3, then 4 of 5), so three rounds. The PDF's wireframes show "3 of 5" in round 2 after a round-1 vote of 2 of 5.
6. **One timeline for both views.** At "3:10 left" Qwen is speaking in Table View and in Chat View (the PDF's two wireframes disagree).
7. **Bubbles:** as in the research table above. The PDF's "no wider than the gap between seats" is not used.
8. **The folded stage card and the answer heading are one unit**, so the vote is shown once. Clicking it opens the stage at its final state; true replay is Phase 7.
9. **Pause and Stop** sit at the left end of the stage footer (the PDF names them but draws neither).
10. **The debate clock** starts when reading starts, excludes loading, freezes on Pause and stops at agreement.
11. **A model that fails to load:** the stage says what went wrong and offers Try again, Continue with 4, or Stop. The PDF does not say.
12. **When time runs out,** the answer uses the last completed vote.
13. **Chat View columns** appear only when each gets at least 200 px (3 to 5 seats at 1440 px wide), otherwise one thread. Black and white covers everything inside the Chat View panel, including its focus rings.
14. **`council.md` chips and the review card** are left out; the gallery shows one chip marked "arrives with Phase 6".
15. **Wireframe notes** ("Chats", "You sit here, facing the council", "Council stage", the blue and pastel colours) are drawing notes and are not rendered.
16. **Below 1100 px wide** the sidebar becomes a narrow icon rail, so seven seats still fit.
17. **The sample** is an invented apartment-lease question with three invented files. None of Lucas's real files is read. Its pace is invented too: three rounds in 3:40 is roughly what the research estimates for five fast models, the best case.
18. **Vote marks** clear when the next round starts, as the PDF says (asked at G1).

## Stack

Versions are what the npm registry served on 2026-10-10, re-confirmed today. All are pinned exactly, with the lockfile committed.

| Need | Package and version |
|---|---|
| UI | `react` 19.3.0, `react-dom` 19.3.0, `react-router` 8.4.0 (hash routes) |
| Build | `vite` 8.3.4, `@vitejs/plugin-react` 6.1.2, `typescript` 6.0.3 (version 7 breaks tools this build uses) |
| Styling | `tailwindcss` 4.3.3, `@tailwindcss/vite` 4.3.3, `clsx` 2.1.1 |
| Accessible primitives | `radix-ui` 1.7.0 (dialog, tooltip, dropdown-menu, toggle-group, radio-group, slot) |
| Fonts for the studies | `@fontsource-variable/besley`, `-atkinson-hyperlegible-next`, `-literata`, `-archivo`, all 5.3.0, OFL-1.1. The unused ones are removed after the pick. `-jetbrains-mono` 5.3.0 stays for code blocks only. |
| Icons, Markdown | `lucide-react` 1.55.0, `react-markdown` 10.1.0, `remark-gfm` 4.0.1 |
| Unit tests | `vitest` 5.0.3, `jsdom` 30.1.2, `@testing-library/react` 16.3.3, `/dom` 10.4.2, `/user-event` 14.6.7, `/jest-dom` 7.0.1 |
| Browser tests | `@playwright/test` 1.64.0 (Chromium and WebKit), `@axe-core/playwright` 4.13.0 |
| Lint and format | `@biomejs/biome` 2.5.15 |
| Types | `@types/react` 19.3.0, `@types/react-dom` 19.3.0, `@types/node` 24.19.2 |

- One-off tool: `uv run --with pypdfium2 --with pillow` renders PDF pages 4, 6, 7, 8 and 13 to PNG.
- WP 1.0 is the only step that downloads anything. The two test browsers go to `~/Library/Caches/ms-playwright`; npm and uv keep their usual caches. Nothing else is written outside the repo.

## Sample debate and data

One invented debate drives every screen, so no screen can tell a different story from another.

- **Question:** "Can I end my apartment lease early, and what would it cost me?" with `Lease 2025.pdf` (14 pages), `Renewal letter 2026.pdf` (2) and `House rules.docx` (6). Limit 5:00. Seats left to right: Phi, Llama, Qwen, Gemma, Mistral, as the wireframe draws them.
- **Story:** the council is seated in 18 seconds; each seat reads the files; round 1 ends 2 of 5; a 15-second pause and an owner note in round 2, which ends 3 of 5; round 3 ends 4 of 5 at 3:40 and Qwen writes the answer; Phi dissents in one line. The 18 seconds and the 3:40 are invented for the sample; the research estimates roughly 20 seconds to 2 minutes to load five models from cold.
- **Variants** reuse the same list: three seats, seven seats, seven seats with several talking at once (layout stress only), time running out on the 2-minute preset ("No consensus, 2 of 5"), and Phi failing to load.
- **Shape:** the debate is a numbered list of events (`debate.created`, `seat.status`, `phase.changed`, `round.started`, `turn.started`, `turn.delta`, `turn.ended`, `summary.posted`, `tally.posted`, `note.queued`, `note.delivered`, `clock.paused`, `clock.resumed`, `answer.released`). One small piece of code, `viewAt(events, time)`, turns the list into what the screen shows at that moment, so every scene is "the debate at time T". Phase 4's real engine will emit the same events and Phase 7's replay will reuse them.
- The shapes hold under all three open back-end questions: "speaking" is a set of seats (none, one or many); a summary names no author; a vote is groups of seats with no stated matching method.
- **Tests that pin the story** (`story.test.ts`): votes needed for 3 to 7 seats are 3, 4, 4, 5, 6; the clock never runs backwards and stands still while paused; every turn that starts also ends; the three tallies are 2, 3 and 4 of 5 with exactly one dissent; every citation names an attached file and a page that exists; short names are 7 characters or fewer and sample bubble lines 55 or fewer; at 1:50 there is 3:10 left, Qwen is speaking, and three bubbles are at full, full and half strength.

**Table View geometry** is one function, `tableLayout(seats, width, height)`: seat *i* of *N* sits at angle 180 × (*i* − 0.5) / *N* degrees along the curve (18, 54, 90, 126 and 162 degrees for five, matching the wireframe), and it returns non-overlapping bubble places for whichever seats are talking. Head size steps from 72 to 56 px as seats increase and the window narrows.

**Scenes shown on the review page** (about 23, each in light and dark; the key ones also at 1024 px wide): gallery; new chat; asking; seating; reading; debating in Table View, as one thread and as columns; an agent's side sheet; a vote; paused; note queued; note delivered; agreed; released; released with the stage reopened; no consensus; a model failed; three seats; seven seats; seven seats with several talking; the shortcuts sheet; the "later" page.

## Build steps

| WP | What | Who | Done when |
|---|---|---|---|
| 1.0 | Repo; pinned install; both test browsers; PDF wireframes as PNG and text; the two skills copied in; the commands `look`, `look:file`, `contrast` and a font-embedding script that writes the fonts into the study file itself (a builder writes `study.src.html` with a marker where the fonts go, runs the script and gets `study.html`; builders never print, read or paste the font data); the shared study brief and content file; the repo's `CLAUDE.md`; `docs/BUILD_STATUS.md`; the three direction plans with the judges' corrections, and the research notes, saved under `docs/`; this plan's working reference copied in | me | a clean `npm ci` works; `look:file` screenshots a placeholder with an embedded font and no outside request; `look` starts the dev server, takes a screenshot and stops it, twice in a row on the same port, with the port free after each (if the copied helper leaves a server behind, `look` starts and stops Vite itself and the helper is not used); `contrast` reproduces the known figures for the PDF's palette (white on clay 3.84, hairline border 1.2) |
| 1.1 | Three studies drawn from the corrected directions, a reviewer who sees only the screenshots, and the page Lucas chooses from | workflow D, me | three complete study folders; `contrast` passes for each; the chooser and each study load in `look:file` with every outside request blocked and none attempted |
| 1.2 | Everything that does not depend on the look (runs beside 1.1, so the pick costs no machine time): check harness, the token guard (run against placeholder tokens), event shapes, the sample debate and its tests, the scene list, route stubs, `docs/plan/phase-1-spec.md`, the clock for the player; seat geometry, bubble placement and bubble timing | me, workflow F | the final check (`gate`, under Checks) passes on a placeholder that uses the real constructs; layout and timing tests pass |
| **G0** | **Lucas picks a look** | Lucas | his words recorded in `docs/BUILD_STATUS.md`; the chosen study saved as the reference; a revised time estimate given |
| 1.3 | Tokens (including Chat View's own black, white and grey), fonts (unused candidates removed), theme script, the enforced contrast test, the token guard pointed at the real tokens, the gallery's token page | me | contrast passes in both themes, all seven seat names in heads included; the fonts are proven loaded in the built app |
| 1.4 | App frame and the pieces every screen shares: the stage shell (frame, footer with Pause, Stop and the Table / Chat switch, the "model failed" notice, open and folded states, with empty slots where Table View and Chat View go), the seat figure with its speaker and vote marks, file and citation chips, the agreement count, the message box in both states (ask, and "Add a note for the next round"), the shortcuts sheet and its keys, the "later" page, and the gallery shell, which finds each builder's entries by file name; `docs/design/recipes.md` | one agent | the frame passes its checks at 1440 and 1024 px in both themes; I compare it with the chosen study and save a restore point |
| 1.5 | Table View, Chat View, the conversation and answer; review; fix; verify | workflow A | the final check passes; every must-show line is ticked against a screenshot; each confirmed finding is fixed or listed with its severity |
| 1.6 | Review package: the review page, the review bar and player, the launcher, the screenshot sheet | me | the final check passes with the package in place |
| **G1** | **Lucas reviews the mocks** | Lucas | |

On `main`, one work package is one commit. Nothing is pushed.

**What a study is.** One self-contained HTML file per look, with a theme switch and a Play button that shows one bubble fade. Each panel is drawn for a 1440 by 830 window (this Mac's visible browser area), and the chooser page shows its light and dark screenshots side by side. All three are built from one shared brief and content file that I write in WP 1.0 (`docs/direction/study-brief.md` and `study-content.json`: the lease question, the sample's seat order, the bubble lines, the answer, the four panels, and seat positions and sizes from the layout formula). It replaces the study brief inside each direction file, so only the look differs. The four panels: mid-debate with one speaker; all five speaking; seven seats; the released answer. Chat View is left out because it is black and white in every look. B's study adds its with-and-without-patterns and upright-or-italic comparisons. The real fonts are embedded; if a builder cannot embed one it stops instead of substituting another.

## How the workflows run

A workflow is a batch of agents run together.

| Workflow | Stages | Agents |
|---|---|---|
| D, studies | Three study builders in parallel (plan, review, build, screenshot, self-critique, one revision), then one reviewer who sees only the screenshots, reads only the skill's list of generic looks, and checks for those and for look-alikes other than the two already accepted (A and B's pale page; A and C's solid figures). A study fails only for a missing return item or a failed command, and is rerun fresh, twice at most; if it still fails Lucas is shown two studies and told why. The reviewer's findings do not fail a study: they are shown to Lucas beside it. | 4 |
| F, layout and timing | A layout builder (`tableLayout`) and a timeline builder (`viewAt` and the bubble timing) in parallel, against tests I write first and freeze | 2 |
| WP 1.4 | One frame builder, then my check | 1 |
| A, screens | Three builders in parallel (Table View, bubbles and side sheet; Chat View; question, answer, folded card contents, "No consensus" answer and seat picker). Each fills its own slot in the stage shell from WP 1.4 and writes only its own folder. Then three reviewers in parallel: a design critic with the skill; a function critic for keyboard, motion and truthfulness to this plan; a first-time viewer who sees only screenshots, as Lucas will. Then one fixer, then one verifier. | 8 |

What was cut from the earlier plan, and what was deliberately kept, is recorded in `docs/BUILD_STATUS.md`.

**How I talk with sub-agents (Lucas's instruction, 2026-10-10).** Everything passed between me and sub-agents is written in short "Stone Age" talk to save tokens and time: my briefs, their replies, and their notes while working. Fewer words, same facts. What must stay exact stays exact: file paths, commands, numbers, colour values, code, and any words that end up on a screen or in a document Lucas reads. After this plan is approved I also save this as a standing preference, so later sessions follow it.

**Rules for agents sharing one working tree.**
- Each brief carries a write list. Study builders write only `docs/direction/<a|b|c>/`.
- Frozen for every agent at all times: `package.json`, the lockfile, configs, `scripts`, `src/styles`, the Playwright checks, `src/review`, the chosen-study folder, and every test file I wrote.
- Frozen while agents run in parallel, except the paths on an agent's own write list: `src/lib`, `src/fixtures`, `src/app`, `docs`, and every component finished earlier.
- Write lists for the first two workflows: study builders, `docs/direction/<a|b|c>/`; the layout builder, `src/lib/layout/` (code only, not my tests); the timeline builder, `src/lib/timeline/` (code only). After workflow F both folders are frozen for every agent.
- An agent needing a frozen change works around it and reports the request. A complaint about the direction itself is reported as a question for Lucas, not fixed.
- Agents never install anything, never use `npx`, never write with git, never kill processes by name. They run only `npm --prefix <repo>/ui run <script>`.
- Each builder has its own dev-server port (5311 to 5314) and its own Vite cache folder. Only the verifier and I run the final check, because it writes `dist/`.
- Workflow A runs as three launches: the builders; the reviewers; the fixer and verifier. Between launches I run the final check, which makes the screenshots the reviewers read, and save a restore point on a `wip/` branch. I also save one before and after every other workflow, then squash onto `main`. Rollback is by folder: when an agent fails, only the paths on its own write list are put back from the restore point and only that agent is rerun fresh, never resumed. Work by other agents, or by me, is not touched.
- Critics report and never edit. Verifiers return command exit codes, which I re-run.
- Every brief contains: the role and its single output; the product in three sentences; absolute paths to the spec, the direction, the chosen-study screenshots and the recipes; which skill file to read, if any; the write and frozen lists; exact commands, port and screenshot folder; the nine fixed items, the three open back-end questions and the "Differences" list; the must-show lines; done-when as commands with expected exit codes; a fixed return shape.

## Checks

```
check      tsc --noEmit && biome check . && token guard && vitest run
slice      one agent's files only; fails if it matched no tests
look       one scene on the agent's port: screenshots, page outline, console errors
look:file  the same for a single file
contrast   every colour pair with its ratio; fails below the threshold
gate       (the final check)  check && vite build && playwright test     (the built app on 127.0.0.1:4310)
```

Playwright runs from the same scene list as the review page:
- **Screenshots** of every scene in light and dark at 1440 by 830, Lucas's real window (the one-thread scene at 1024, because five seats get columns at 1440); the key scenes again at 1024 by 768; the seven-seat table scenes also at 1100 wide, where the full sidebar is back and the stage is at its narrowest (the layout tests include that size); a WebKit pass on four key scenes, because Safari measures text differently from Chrome. They are for eyes: nothing is compared pixel by pixel in Phase 1. The screenshots Lucas approves become the baseline for Phase 2.
- **Accessibility** scan per scene and theme, with no serious or critical finding. One exception, set by one named selector: the contrast rule skips a bubble or a seat while it is part-way through a fade, because it is faint on purpose for under two seconds. The same element at full strength is measured in the same scan.
- **Chat View has no colour:** the Chat View panel has its own solid background from separate black, white and grey tokens (written in WP 1.3), so the tinted page cannot show through. Inside it every colour that paints (text, background, border, outline and focus ring, shadow, icon, cursor, underline) has equal red, green and blue. The check fails if a Chat View scene has no Chat View panel.
- **Colour is never the only signal:** each head has visible name text; speaker and vote are in the accessible name; a grey screenshot of each table scene.
- **Keyboard:** Tab reaches every control once, each with a visible ring; `?` opens the shortcuts sheet and Esc returns focus; arrow keys move between seats and across the switch; a letter typed in the message box triggers no shortcut.
- **Motion:** the test sets the player's clock to 0, 250, 8250, 9000 and 9750 ms after a summary and reads the bubble's strength in the browser: none, full, full, half, gone. With reduced motion on it is only full or gone at each of those times, and no other animation is running. While paused, the strength does not change.
- **Offline:** any request to another origin fails the run, and each chosen font is proven loaded.
- The final check fails on any console error, any skipped test, or any check that ran on fewer scenes than the list.
- Each scene in the list is marked built or not yet built, and names what must be on screen (for example: five heads, three bubbles, the Chat View panel). The final check runs every check on built scenes, fails when a check finds none of the thing it tests, and prints how many scenes are not yet built. WP 1.2, 1.3 and 1.4 may pass with scenes not yet built; WP 1.5 and 1.6 pass only when that number is zero. The names the checks look for are fixed in `docs/plan/phase-1-spec.md` before any builder starts.

Tests that need no browser:
- **Layout:** for 3 to 7 seats, every combination of talking seats up to the cap, several stage sizes and bubble sizes: no two bubbles overlap, none touches a figure, all stay inside the stage, each is nearest its own seat. The same is checked on real rectangles in both browsers with the longest sample text.
- **Timing,** with a fake clock, at 0, 250, 8250, 9000 and 9750 ms; a replacement crossfades in place; reduced motion gives only shown or gone. A still scene passes a fixed time into the same function, so "one bubble fading out" looks the same on every run.

Judging the look: reviewers read each screenshot beside the chosen study and answer a fixed yes-or-no list, citing the file and the region. "Looks fine" is rejected. I read the final set myself.

## Risks and operating notes

- **Sleep and power.** This Mac sleeps after one idle minute. At the start of each sitting I confirm mains power and hold sleep off with a temporary `caffeinate` process; no power setting is changed. Closing the lid stops the run and loses at most the current work package.
- **The studies may come out alike,** or drift toward the generic looks the skill lists. The three directions are fixed in writing first, a reviewer who sees only the screenshots checks for look-alikes, and a failed study is rerun.
- **Judging by screenshot.** Agents are weak judges of small spacing and colour differences. Everything measurable is measured; composition needs Lucas's eye.
- **One critique round instead of three** can let findings through. The verifier lists every unfixed and declined finding; one extra fixer and verifier pair runs if a serious one is open; the rest are shown to Lucas with their severity.
- **The wireframes.** Sub-agents could not open the PDF's pictures on this Mac (a system tool is missing), so the planners worked from its text. I saw the wireframes directly in this session. WP 1.0 saves them as PNG and I check the spec against them before any builder starts.
- **New tool versions.** Vite 8, React Router 8, Vitest 5, TypeScript 6 and Tailwind 4 are recent, and agents may write older patterns from memory. I write and freeze all configuration, and `docs/research/toolchain.md` holds import lines verified from the installed packages.
- **Leftover dev servers** can hold a port. `look` refuses a busy port, and I check the ports between stages.
- **Playwright's WebKit** is unverified on this macOS version and is not Safari itself. If it will not start, the final check runs on Chromium only, the gap is recorded, and I ask Lucas to open the mocks once in Safari.
- **Other projects' notes.** `~/.claude/CLAUDE.md` (defense compliance) and `~/Downloads/CLAUDE.md` (a trading project) load into agents working near them. The new repo gets its own `CLAUDE.md` stating its scope, and the PDF is copied into it.
- **Git identity** on this Mac is a placeholder (`you@example.com`). Harmless while nothing is pushed.

## Road map: how Phases 2–7 start

Each phase gets its own plan, Lucas's approval, its batches of agents and a stop for his review.

- **Phase 2, chat, History and documents on one model.** Built and tried on this Mac with a small model first, not on the GX10 as the PDF says (carried over from the earlier plan); it moves to the GX10 in Phase 3. The Python gateway (FastAPI, run with uv) and a prebuilt llama.cpp. SQLite with full-text search plus `sqlite-vec`; `pypdfium2`, `python-docx` and `openpyxl` for extraction; RapidOCR for scans; Qwen3-Embedding-0.6B on its own small server. Citations carry a quote that code checks against the cited page. Text from files is marked as material, not instructions, before a model sees it. This lowers, but does not remove, the chance that a model obeys a line hidden in a file; the published evidence is for other models, so it is tested on the seated ones. Files from the watched Downloads folder keep the one-click inbox.
- **Phase 3, models and seats.** Starts from the GX10 test. One llama-server per distinct model, started and stopped by the gateway, with a record of what is running so a restart never loads a second copy. Two seats on one model share its server. A strict memory check before every debate. Our own resumable downloader (the Hugging Face library no longer resumes). A record per model: whether its "thinking" can be switched off, and its measured speed.
- **Phase 4, debate engine and Chat View.** LangGraph for the wiring; plain Python for Pause, Stop, the timer and the event record; the same events the Phase 1 mocks use. The ballot, with its built-in test set. A scripted stand-in for llama-server so the engine can be built and tested on this Mac.
- **Phase 5, Table View live.** The summariser decision; a fixed character budget for bubble lines; Motion added here if the stage fold needs it.
- **Phase 6, learning.** Entries as database records, `council.md` written from them and committed to git; one-click undo of the newest entry; a separate path for preferences Lucas states directly.
- **Phase 7.** As in the PDF.

## Sources

- This session's research and re-checks (serving, capacity, engine, consensus, front end): `~/.claude/projects/-Users-lucasta/21faaa1b-c410-4e00-89e7-0517e511a8a2/subagents/workflows/wf_4ea7d92f-6d4/journal.jsonl`
- This session's design pass (three directions, two judges, screen spec, build plan): `.../workflows/wf_f5a1a73c-27e/journal.jsonl`
- This session's audit of this file: `.../workflows/wf_e0fbd4c7-d88/journal.jsonl`
- The earlier session's research (front-end tools, documents, GX10 hardware): `~/.claude/projects/-Users-lucasta/fa0881e7-9235-40cb-9884-7b6ee0cccdf6/subagents/workflows/wf_3d1f46d9-326/journal.jsonl`
- The two skills: `~/.claude/plugins/marketplaces/anthropic-agent-skills/skills/frontend-design/SKILL.md` and `.../webapp-testing/SKILL.md`

Work package 1.0 turns these into `docs/research/`, `docs/direction/` and `docs/plan/phase-1-spec.md`. Where a planner's output and this plan disagree, this plan wins.
