# Notion Sync — State

**This file is the source of truth for suite numbering. It persists — never delete it.**
Claude Code reads `Next suite number` before minting a new suite, then bumps it.
The ledger mirrors what *should* be on the Notion board so the desktop app can reconcile.

---

**Next suite number:** `36`

## Suite ledger

One row per suite = one card on the board. `Column` is the suite card's board column;
per-ticket status lives on each ticket subpage (see OUTBOX preamble).

| Suite | Title | Column | Tickets | Last synced |
|-------|-------|--------|---------|-------------|
| 17 | Fable code-review infrastructure | Needs QA | 17.1–17.4 | _(pending)_ |
| 18 | DB-backed broadcast access codes (centralized auth) | Needs QA | R1–R8 (18.1–18.8; R7 Open) | _(pending)_ |
| 19 | Sales codes | Needs QA | 19.1–19.6 | _(pending)_ |
| 20 | Scraper ingestion pipeline (visitpittsboro) | Needs QA | 20.1–20.5 | _(pending)_ |
| 21 | SEO hub pages | Needs QA | 21.1–21.3 | _(pending)_ |
| 22 | Code-quality hardening (lint / types / CI) | Needs QA | T0–T7, T12 | _(pending)_ |
| 23 | Dev tooling / slash-commands | Needs QA | 23.1–23.6 | _(pending)_ |
| 24 | Notion sync (outbox → Kanban) | Needs QA | 24.1–24.2 | _(pending)_ |
| 25 | Broadcast dispatch on Celery (kill the 3s Neon poll) | Needs QA | 25.1–25.9 | _(pending)_ |
| 29 | Standalone auth portal (auth.thecommons.town) | Needs QA | 29.1–29.7 | _(pending)_ |
| 30 | Broadcast auth + access-code debugging (JWT bridge, sign-in 401, tier-0, request reduction, hard reset) | Needs QA | 30.1–30.8 | _(pending)_ |
| 31 | Broadcast client-feedback fixes (organizer/contact fields, AI autofill, TW tags + image uploads, ABC11 identity + date/time) | In Prod | 31.1–31.11 | _(pending)_ |
| 32 | Ingestion observability devtool (run history, live probe, funnel metrics, health flags) | In Prod | 32.1–32.8 | _(pending)_ |
| 33 | Ingestion monitor diagnostics correctness (health levels, zero legibility, GRANT detection) | In Prod | 33.1–33.5 | _(pending)_ |
| 34 | Ingestion pipeline resilience (dedupe corpus, standardizer fallback, direct-submission delivery) | In Prod | 34.1–34.5 | _(pending)_ |
| 35 | Prod scheduler outage (snap-uv user-slice teardown) + monitor correctness | In Prod | 35.1–35.11, 35.13, 35.14 (35.12 merged into 35.8) | _(pending)_ |

<!--
Columns (left→right): Idea · Open · In Progress · Needs QA · Staged for Prod · In Prod
When a suite is created here it starts in `Open` (or `Idea` if it's just a sketch).
Update a suite's Column as its tickets progress; the desktop app moves the card to match.
`Last synced` = date the desktop app last pushed this suite to Notion (it fills this in / you do).
-->
