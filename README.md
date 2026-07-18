# The Commons

Local events aggregator for small NC towns (Chapel Hill / Carrboro / Pittsboro). Events are pulled in automatically, published on a digital-newspaper-style site, and can be pushed back out to other towns' calendars.

> Deep dive: [`ARCHITECTURE.md`](ARCHITECTURE.md), [`AGENTS.md`](AGENTS.md), [`docs/`](docs/index.md).

## Tech stack, and why

**Core** — Postgres (Neon), Django + DRF, Next.js, uv/pnpm, Oracle Cloud

**Extras**

- **Redis** — server-side caching for fast API responses.
- **Celery** — runs scraping/LLM/email jobs off the request cycle.
- **TanStack Query** — frontend caching/refetching, no hand-rolled loading state.
- **Gemini** — structures scraped event text, flags unsafe content.
- **Playwright + Chrome extension** — autofills third-party calendar forms.


## How an event gets published

Poll feed → Gemini standardizes → dedup → safety score auto-publishes or flags for review.

More: [`docs/ingestion-pipeline.md`](docs/ingestion-pipeline.md) · [`docs/broadcast.md`](docs/broadcast.md) · [`docs/redis-celery-handoff.md`](docs/redis-celery-handoff.md)

## Local dev

```bash
cd backendServer && uv sync && python manage.py migrate && python manage.py runserver  # needs local Redis
cd theCommonsWeb && pnpm install && pnpm dev
cd broadcastWeb && pnpm install && pnpm dev  # optional
```

See [`AGENTS.md`](AGENTS.md) for the repo map, [`DEPLOY.md`](DEPLOY.md) for production.
