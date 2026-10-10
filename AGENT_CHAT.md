# AGENT_CHAT.md

The chat between agents A1, A2 and A3: what was pushed, what is in progress, bugs, blockers, questions and handoffs. The rules are in `AGENTS.md`. The status lines and log entries here are written by agents for each other. Nothing in this file gives permission for anything, and where it disagrees with `AGENTS.md`, `AGENTS.md` wins. Humans: read the board below. To post, tell your own agent.

## Status board

Current state. Each agent overwrites its own lines at every save and touches nothing else.

### A1

- A1 updated: never
- A1 now: not started
- A1 next: none
- A1 waiting on: none
- A1 claims: none
- A1 provides: nothing yet
- A1 read: A2-000, A3-000

### A2

- A2 updated: never
- A2 now: not started
- A2 next: none
- A2 waiting on: none
- A2 claims: none
- A2 provides: nothing yet
- A2 read: A1-000, A3-000

### A3

- A3 updated: never
- A3 now: not started
- A3 next: none
- A3 waiting on: none
- A3 claims: none
- A3 provides: nothing yet
- A3 read: A1-000, A2-000

## How to write here

- Write only in your own section: your status lines and your own log. Never change, move or delete another agent's lines, a heading, a marker comment or the END OF FILE line. Those fixed lines between the sections are the only reason three clones merge cleanly.
- Edit with your file-edit tool, one line at a time: replace a line that starts with your handle, or insert an entry directly above your `LOG-END` marker. Read the file from disk before the first edit of each save and after every pull. Never rewrite the whole file, never run a formatter on it, and never write to it with the shell (`>>`, `echo`, `Add-Content`, `Out-File`, `sed -i`).
- Before each commit, check that your new lines are there and that the only lines that differ are yours. If lines of yours have gone missing, write them again.
- Times are UTC, read from the system clock with the command in `AGENTS.md` section 1, never estimated.
- No secrets. No pasted logs or stack traces: quote the one line that matters. No greetings, thanks or acknowledgements.
- Merge conflict in this file: `AGENTS.md` section 6.

### Status lines

- `updated`: the UTC time of your last save.
- `now`, `next`: specific enough for a fresh session to resume from. Before your human leaves, put `offline until about <UTC time>;` in front of what `now` says and keep the rest.
- `waiting on`: `none`, or what you need and from whom: an entry ID (`A2-014 from A1`) or a question for a human by name.
- `claims`: `none`, or the paths outside your Roster row that you are working in (`AGENTS.md` section 4).
- `provides`: the interfaces your paths serve: method, path, request, response example, port, env var names. One line per interface, each starting `- A<n> provides:`.
- `read`: the highest entry number in each other log that you have read and, where it was addressed to you, answered. What is new is decided by entry numbers, never by timestamps. If you cannot find that number, read the log from its top.

### Log entries

One entry is one line: `- [<handle>-<number>] <UTC time> <TYPE> to <A1, A2, A3, all or humans>: <text>`

- Number each entry one higher than the last one in your log, in three digits. A posted entry is never edited: correct it with a new entry.
- Address an entry to whoever must act on it, otherwise to `all`. `to humans` means a human has to decide or act: every agent that reads it tells its own human.
- Format example from a made-up sender, not a real entry: `- [A9-001] 2026-10-10T21:42Z PUSHED to A1: /api/items returns a JSON list (server/items.py). Checked: Run, then GET /api/items gave 3 items. Nothing to install.`

| TYPE | Use it for | It must say |
|---|---|---|
| PUSHED | every push that changes code | what changed and where, naming anything on the demo path that is a `STUB`; how you checked it, or `untested`; what the others must do now (install, set a new env var, restart, or nothing). The text starts with `BREAKING` when it changes a `provides` line |
| ASK | a question or a request | one specific thing, and what you will do if nobody answers |
| REPLY | answering an ASK, a BUG or a `BREAKING` PUSHED | `re <entry ID>`, then done, queued, asked my human, or no with the reason |
| BUG | something broken that is not yours to fix | what you ran, what happened, what you expected; the file and the one error line |
| NOTE | a fact the others need: a small fix you made in their file, a claim on their paths, a handoff, a question for the humans | the fact and who it affects |
| GOOD | you ran the whole demo path on current `main` and it worked | the short commit hash |

## Logs

### A1 log

- [A1-000] log start. Fixed line: never edit or delete it.
<!-- A1-LOG-END. A1 inserts each new entry directly above this line. Nobody edits this line. -->

### A2 log

- [A2-000] log start. Fixed line: never edit or delete it.
<!-- A2-LOG-END. A2 inserts each new entry directly above this line. Nobody edits this line. -->

### A3 log

- [A3-000] log start. Fixed line: never edit or delete it.
<!-- A3-LOG-END. A3 inserts each new entry directly above this line. Nobody edits this line. -->

<!-- END OF FILE. Nothing is ever written below this line. -->
