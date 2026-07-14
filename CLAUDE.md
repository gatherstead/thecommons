# The Commons — Claude Code Context

[![CI](https://github.com/gatherstead/thecommons/actions/workflows/ci.yml/badge.svg)](https://github.com/gatherstead/thecommons/actions/workflows/ci.yml)

Read these files before any task — they are the system of record:

1. [`AGENTS.md`](AGENTS.md) — Repository map, tech stack, cross-cutting concerns, guardrails
2. [`ARCHITECTURE.md`](ARCHITECTURE.md) — Models, endpoints, auth bridge, deployment
3. [`CODING_STYLE.md`](CODING_STYLE.md) — Design philosophy + frontend/backend conventions

For deployment: [`DEPLOY.md`](DEPLOY.md)
For backend orientation: [`backendServer/AGENTS.md`](backendServer/AGENTS.md)
For frontend orientation: [`theCommonsWeb/AGENTS.md`](theCommonsWeb/AGENTS.md)
For the broadcast subsystem: [`docs/broadcast.md`](docs/broadcast.md) (source of truth) + [`broadcastWeb/AGENTS.md`](broadcastWeb/AGENTS.md)
For deep-dive guides: [`docs/index.md`](docs/index.md)

## Quick Start

```bash
# Backend
cd backendServer && uv sync && python manage.py migrate && python manage.py runserver

# Frontend (pnpm-managed — npm install will fail on the symlinked store)
cd theCommonsWeb && pnpm install && pnpm dev
```

## Claude-Specific Notes

- If a doc contradicts the code, **trust the code** and flag the doc drift.
- In task recaps, include the **ticket name** if given (10.2, T12, etc.).
- Run `python manage.py migrate` after model changes — but never for `neon_auth` mirrors (`managed = False`).
- Async work runs on Redis + Celery (DB 0 = broker/results, DB 1 = cache); broadcast dispatch now runs on Celery too, via a dedicated `broadcast` queue drained by a single `-c 1` worker (on-demand `transaction.on_commit(process_broadcast_queue.delay)`, not a poll loop). Keep `broadcast/` isolated — `routing.py` must not import from `events`, and never use the ORM inside `sync_playwright`.
- Frontend type-checks with `pnpm build`. Backend tests run under the test settings: `DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test` (Postgres test DB; `--tag=fast` for the no-DB tier, `--tag=db` for the DB tier). See [`backendServer/AGENTS.md`](backendServer/AGENTS.md#testing).

## Notion sync (keep the Kanban board in step)

Never edit the Notion board directly. Instead, whenever board state changes in a session,
write it to the **outbox** — the Claude desktop app applies it to Notion later. See
[`notion-sync/README.md`](notion-sync/README.md).

Append a change block to `notion-sync/OUTBOX.md → Pending changes` (and update
`notion-sync/STATE.md`) when you:

- **Plan a suite via `/write-tickets`** (tickets written, no code built) → **ask first.**
  Present the tickets, and only after the user approves, append a `NEW SUITE` block: the
  suite card body (Why / Outcomes / QA, a few bullets each) plus one full ticket per
  subpage, in the **`Open`** column. Take the suite number from `STATE.md`'s
  `Next suite number`, then increment it and add the suite to the ledger.
- **Orchestrate/build a whole suite** (e.g. `/orchestrate`, or you just implemented its
  tickets) → append a `MOVE SUITE` block placing the **whole suite** in **`Needs QA`**
  (plus `MOVE TICKET` blocks as individual tickets land). If the suite isn't on the board
  yet, create it (`NEW SUITE`) first, then move it. Update the ledger.
- **Move a single ticket** — its status changes (Open → In Progress → Needs QA →
  Staged for Prod → In Prod) → append a `MOVE TICKET` block, and a `MOVE SUITE` block if
  the suite's overall column should change too. Update the ledger.
- **Change a ticket's scope or a suite summary** → append an `UPDATE` block.

Use the change formats defined in the OUTBOX preamble. If a change doesn't map to a real
suite in the ledger yet, create the suite first. Don't gate a coding task on this — record
the change and keep working.
