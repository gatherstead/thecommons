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
- `backendServer/vercel.json`, `build.sh`, `main.py` are legacy dead files — ignore them.
- Run `python manage.py migrate` after model changes — but never for `neon_auth` mirrors (`managed = False`).
- Async work runs on Redis + Celery (DB 0 = broker/results, DB 1 = cache); the `broadcast` worker is separate (its own DB queue, not Celery). Keep `broadcast/` isolated — `routing.py` must not import from `events`, and never use the ORM inside `sync_playwright`.
- Frontend type-checks with `pnpm build`. Backend tests run under the test settings: `DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test` (Postgres test DB; `--tag=fast` for the no-DB tier, `--tag=db` for the DB tier). See [`backendServer/AGENTS.md`](backendServer/AGENTS.md#testing).
