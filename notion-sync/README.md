# notion-sync — keeping the Notion board in step with the code

A one-dev safety net: Claude Code sessions drift (you pivot, make tickets that were
never on the board, ship things that never moved out of "In Progress"). Rather than
stop mid-session to hand-edit Notion, Claude Code writes every board-relevant change to
a plain markdown **outbox**. You hand that file to the **Claude desktop app**, which has
the Notion MCP and does the actual board edits — ideally on a schedule overnight so it
never eats into a working session.

## The three files

| File | Tracked in git? | Who writes it | Lifecycle |
|------|-----------------|---------------|-----------|
| `STATE.md` | yes | Claude Code | **Persistent.** Holds `Next suite number` + a ledger of every suite and its column. Never delete — it's how numbering (`14.x` → `15.x`) stays consistent. |
| `OUTBOX.md` | yes | Claude Code appends | **Disposable queue.** Standing prompt for the desktop app + a "Pending changes" list. You feed it to desktop, then reset the queue to `_(empty)_`. |
| `README.md` | yes | you | This file. |

## The loop

1. **During a session**, whenever Claude Code makes tickets or changes a ticket/suite's
   status, it appends a change block to `OUTBOX.md → Pending changes` and updates
   `STATE.md`. (This is wired via the "Notion sync" note in `CLAUDE.md` and the
   `write-tickets` skill.) It does **not** touch Notion.
2. **On your schedule** (e.g. leave the machine on; have the desktop app run a scheduled
   task in the middle of the night), open the Claude desktop app and give it `OUTBOX.md`.
   The file is self-contained — its top half is the full prompt telling desktop how to
   build cards/subpages via the Notion MCP.
3. **After it applies**, reset the `Pending changes` section back to `_(empty)_`
   (leave the prompt preamble above it intact). `STATE.md` keeps the counter.

## First-time setup

- Open `STATE.md` and set **`Next suite number`** to (your current highest suite + 1).
- In the Notion desktop app, make sure the board has the six columns named in the
  OUTBOX preamble (or tell desktop to create them on the first run).

## Why suites, not tickets, are the cards

A suite (e.g. Suite 14) is one card with a tight Why / Outcomes / QA summary; each ticket
(14.1, 14.2, …) is a subpage carrying the full paste-ready ticket. The card shows the
suite's overall column; each subpage carries its own Status so you can see granular
progress without cluttering the board.
