# The Commons

Local events aggregator for small NC towns (Chapel Hill / Carrboro / Pittsboro). Events are pulled in automatically, published on a digital-newspaper-style site, and can be pushed back out to other towns' calendars.

> Deep dive: [`ARCHITECTURE.md`](ARCHITECTURE.md), [`AGENTS.md`](AGENTS.md), [`docs/`](docs/index.md).

## Tech stack, and why

**Core**

- **Postgres (Neon)** — managed/serverless, no DB ops; branching gives free isolated dev DB.
- **Django + DRF** — admin UI for reviewing scraped events, and API + ingestion pipeline share one codebase.
- **Next.js (App Router)** — server-rendered pages for SEO, client interactivity where it matters.
- **uv / pnpm** — faster, more reproducible installs than pip/npm.

**Extras**

- **Redis** — significantly improves query times for the clients  by caching serverside
- **Celery** — keeps slow work (LLM calls, scraping, emails) out of the request cycle.
- **TanStack Query** — frontend API caching/refetching, no hand-rolled loading state.
- **Better Auth** — drop-in auth in Next.js, issues JWTs Django verifies statelessly.
- **Google Gemini** — turns messy scraped text into structured events and flags unsafe content.
- **Playwright + Chrome extension** — third-party calendars have no API, only forms; extension autofills, human clicks submit.
- **Brevo** — transactional + digest email, no mail server to run.

## Pieces

One Oracle Cloud VM behind nginx runs all of it:

- **Next.js site** (theCommonsWeb + Better Auth) — public frontend
- **Django API** (backendServer + DRF) — public API, ingestion, broadcast, async
- **Redis + Celery** — job queue + read cache
- **Broadcast subsystem** (Playwright + Chrome extension console) — pushes events to other calendars
- **Postgres (Neon)** — system of record

## How an event gets published

1. Daily poll of each source's ICS calendar feed (or a direct/broadcast submission).
2. **Gemini** standardizes it into title, description, tags, price, town.
3. Fuzzy dedup catches repeats across sources.
4. A safety score auto-publishes clean events; flags the rest for manual review.

More: [`docs/ingestion-pipeline.md`](docs/ingestion-pipeline.md) · [`docs/broadcast.md`](docs/broadcast.md) · [`docs/redis-celery-handoff.md`](docs/redis-celery-handoff.md)

## Local dev

```bash
cd backendServer && uv sync && python manage.py migrate && python manage.py runserver  # needs local Redis
cd theCommonsWeb && pnpm install && pnpm dev
cd broadcastWeb && pnpm install && pnpm dev  # optional
```

See [`AGENTS.md`](AGENTS.md) for the repo map, [`DEPLOY.md`](DEPLOY.md) for production.
