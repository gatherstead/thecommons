# Notion Sync — State

**This file is the source of truth for suite numbering. It persists — never delete it.**
Claude Code reads `Next suite number` before minting a new suite, then bumps it.
The ledger mirrors what *should* be on the Notion board so the desktop app can reconcile.

---

**Next suite number:** `17`

## Suite ledger

One row per suite = one card on the board. `Column` is the suite card's board column;
per-ticket status lives on each ticket subpage (see OUTBOX preamble).

| Suite | Title | Column | Tickets | Last synced |
|-------|-------|--------|---------|-------------|
| _(none yet)_ | | | | |

<!--
Columns (left→right): Idea · Open · In Progress · Needs QA · Staged for Prod · In Prod
When a suite is created here it starts in `Open` (or `Idea` if it's just a sketch).
Update a suite's Column as its tickets progress; the desktop app moves the card to match.
`Last synced` = date the desktop app last pushed this suite to Notion (it fills this in / you do).
-->
