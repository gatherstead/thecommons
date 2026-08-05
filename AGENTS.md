# The Commons — Agent Map

Local community events aggregator for small NC towns (Chapel Hill / Carrboro / Pittsboro). A Django REST API backend ingests events via an LLM pipeline; a Next.js frontend serves a digital-newspaper UI; a separate "broadcast" subsystem syndicates events out to third-party community calendars. Everything runs on a single Oracle Cloud VM with Postgres on Neon.

## Repo Map

```
thecommons/
├── backendServer/                # Django 6 + DRF — API, ingestion pipeline, broadcast, async
│   ├── backend/                  #   Project config: settings/ (base/dev/prod/test), urls, celery,
│   │                             #     jwt_auth (Better Auth JWKS), permissions, test_runner
│   ├── accounts/                 #   Identity/auth-bridge app: neon_auth mirrors (BetterAuth*),
│   │                             #     UserProfile + BusinessProfile, /auth/me, /businesses
│   ├── events/                   #   Public app: Event/Town/Tag + genuine event views
│   ├── newsletter/                #   NewsletterSubscriber, subscribe/manage views, digest engine
│   │                              #     (email_service, tasks, templates, digest commands)
│   ├── ingestion/                #   Pipeline: EventSource → RawEvent → StagedEvent → published Event
│   ├── broadcast/                #   Event syndication: Playwright adapters, DB-queue worker, routing
│   ├── templates/                #   HTML for admin docs pages + email digests
│   └── AGENTS.md                 #   ← Backend local map
├── theCommonsWeb/                # Next.js 16 (App Router) + React 19 + Better Auth — main site
│   ├── src/app/                  #   Pages + API routes (App Router)
│   ├── src/components/           #   auth/, events/, layout/, ui/, providers/
│   ├── src/hooks/                #   useAuth, useEvents, useTowns, useMessageStack, …
│   ├── src/lib/                  #   Better Auth config, Drizzle schema, DB pool, queryClient
│   ├── src/services/             #   Django API clients (event, profile, business)
│   └── AGENTS.md                 #   ← Frontend local map
├── broadcastWeb/                 # Vite + React 19 operator SPA for the broadcast console
│   └── AGENTS.md                 #   ← broadcastWeb local map
├── broadcastExtension/           # Chrome MV3 extension for manual-review broadcast handoff (dormant)
├── deploy/                       # systemd units + nginx snippets + healthcheck.sh (see DEPLOY.md)
├── docs/                         # Deep-dive guides (see docs/index.md)
├── AGENTS.md                     # ← You are here
├── CLAUDE.md                     # Claude Code entry point (points here)
├── ARCHITECTURE.md               # System design: models, endpoints, auth, async, deployment
├── CODING_STYLE.md               # Design philosophy + frontend/backend conventions
├── DEPLOY.md                     # Production VM setup — nginx, systemd, deploy (source of truth)
└── PROJECT_CONTEXT.md            # Generated consolidated dump for external/Claude.ai use
```

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend (main) | Next.js 16 (App Router + Turbopack), React 19, TypeScript, Tailwind CSS v4, TanStack Query v5 |
| Frontend (broadcast) | Vite 7 + React 19 SPA (`broadcastWeb/`) |
| Backend | Python 3.13, Django 6, Django REST Framework, managed with `uv` |
| Database | PostgreSQL on Neon (psycopg from Django; pg/Drizzle from Next.js) |
| Async | Self-hosted Redis + Celery + django-celery-beat (DB-backed schedules) |
| Broadcast | Playwright (Chromium) form-filling via a DB-queue worker |
| LLM | Google Gemini (event standardization + safety scoring) |
| Auth | Better Auth (lives in Next.js); Django verifies JWTs via JWKS |
| Email | Brevo (transactional + weekly/monthly digests) |
| Admin | django-unfold |
| Testing | Django test runner (`fast`/`db` tags); Vitest (`fast`/`db` projects) |
| Deploy | Single Oracle Cloud VM (Ubuntu 24.04, ARM64) — nginx → gunicorn + Next.js; GitHub Actions CI/CD |

## Quick Start

```bash
# Backend (needs a running Redis for Celery; pipeline/digests run async)
cd backendServer && uv sync && python manage.py migrate && python manage.py runserver

# Main frontend (pnpm-managed — npm install breaks the symlinked store)
cd theCommonsWeb && pnpm install && pnpm dev

# Broadcast operator SPA (optional)
cd broadcastWeb && pnpm install && pnpm dev
```

Run backend + theCommonsWeb together for end-to-end auth (Django validates JWTs against the frontend's JWKS endpoint). See [`backendServer/AGENTS.md`](backendServer/AGENTS.md) for the Celery worker/beat commands.

## Where to Find Things

| Concern | Key files | Deep dive |
|---------|-----------|-----------|
| Auth bridge | `backend/jwt_auth.py`, `backend/permissions.py`, `accounts/models.py`, `src/lib/auth.ts` | [ARCHITECTURE.md §Authentication](ARCHITECTURE.md#authentication) |
| Data models | `accounts/models.py`, `events/models.py`, `newsletter/models.py`, `ingestion/models.py`, `broadcast/models.py` | [ARCHITECTURE.md §Data Models](ARCHITECTURE.md#data-models) |
| API endpoints | `backend/urls.py` (include()-only), `accounts/urls.py`, `events/urls.py`, `newsletter/urls.py`, `ingestion/urls.py`, `broadcast/urls.py` | [ARCHITECTURE.md §API Endpoints](ARCHITECTURE.md#api-endpoints) |
| Ingestion pipeline | `ingestion/services.py`, `ingestion/standardizer.py`, `ingestion/importers/`, `ingestion/safety_scorer.py` | [docs/ingestion-pipeline.md](docs/ingestion-pipeline.md) |
| Safety scoring | `ingestion/safety_scorer.py` | [docs/safety-scoring.md](docs/safety-scoring.md) |
| Broadcast | `broadcast/services.py`, `broadcast/worker.py`, `broadcast/runner.py`, `broadcast/adapters/` | [docs/broadcast.md](docs/broadcast.md) |
| Redis + Celery | `backend/celery.py`, `newsletter/tasks.py`, `ingestion/tasks.py`, `events/tasks.py`, `events/cache.py` | [docs/redis-celery-handoff.md](docs/redis-celery-handoff.md) |
| Frontend data layer | `src/lib/queryClient.ts`, `src/hooks/useEvents.ts`, `src/services/` | [ARCHITECTURE.md §Frontend](ARCHITECTURE.md#frontend-architecture) |
| Email digests | `newsletter/email_service.py`, `newsletter/tasks.py` (generic transport: `events/email_service.py::send_email`) | [ARCHITECTURE.md §Async](ARCHITECTURE.md#async-redis--celery) |
| Design system | `src/app/globals.css`, `src/components/ui/` | [CODING_STYLE.md](CODING_STYLE.md) |
| Admin UI | `accounts/admin.py`, `events/admin.py`, `newsletter/admin.py`, `ingestion/admin.py` | [docs/admin-backend.md](docs/admin-backend.md) |
| Testing & CI | `backend/settings/test.py`, `.github/workflows/ci.yml`, `vitest.config.ts` | [ARCHITECTURE.md §Testing](ARCHITECTURE.md#testing--ci) |
| Dev DB isolation | Neon dev branch + `settings/dev.py` | [docs/dev-db-isolation.md](docs/dev-db-isolation.md) |
| Deployment | systemd units, nginx, env vars on VM | [DEPLOY.md](DEPLOY.md) |

## Guardrails

- **Never migrate `neon_auth` tables.** Better Auth (Next.js) owns them. Django mirrors are `managed = False`.
- **`Town` is a SQL table** — don't hardcode. Pipeline skips events with unknown town slugs. (Event categories were retired in suite 50; `Tag` is the only event facet vocabulary now.)
- **Auth lives in Next.js**, not Django. Don't add Django login/signup views or use `django.contrib.auth.User` for app users.
- **`broadcast/` and `ingestion/` are isolated from the rest.** No app imports from `ingestion`/`broadcast`; `broadcast/routing.py` must not import from `events` (enforced by tests). `accounts`, `newsletter`, and `events` may read each other where the domain genuinely overlaps — e.g. `accounts.me` writes a `NewsletterSubscriber` row (email-preference sync) and `newsletter._build_recipients` reads `accounts.UserProfile` (tag-filtered digests). Both directions are intentional; don't "fix" the coupling.
- **No Django ORM inside `sync_playwright`** — fetch all data into plain objects first, then drive the browser.
- **Redis layout is fixed:** DB 0 = Celery broker + results, DB 1 = Django cache. Don't mix them.
- **pnpm only for frontends** (pinned to pnpm 11). `npm install` breaks the symlinked store / peer pinning.
- **Events API excludes past by default** — use the time-window params for past events.
- **Google sign-in is disabled** — commented out in `auth.ts`, `AuthFlow.tsx`, `google-popup/`. Revisit later.
- **Never commit `.env`** — update `.env.example` instead.
- **Newspaper aesthetic** — serif fonts, cream/ink, column rules. No gradients, shadows, or pill buttons. See [CODING_STYLE.md](CODING_STYLE.md).

## Database Ownership

| Schema | Owner | Django access |
|--------|-------|---------------|
| `public` | Django migrations | Full read/write |
| `neon_auth` | Better Auth (Next.js) | Read-only mirrors (`managed = False`) — never migrate |

## Ingestion Pipeline

```
EventSource (ICS/feed URL)
    ↓  importers/ics_importer.py        (poll, shardable)
RawEvent
    ↓  standardizer.py (Gemini)         → StagedEvent (pending)
    ↓  deduplicator.py (thefuzz)        → mark duplicates
    ↓  safety_scorer.py (Gemini)        → safety_score
    ↓  services.auto_publish_safe_events / publish_all_approved()
Event (published, public)
```

Runs daily (Celery beat, 04:00 ET) or via `POST /api/cron/ingest` (`CRON_SECRET`) / `python manage.py ingest_events`. See [docs/ingestion-pipeline.md](docs/ingestion-pipeline.md).

## Documentation Index

| Doc | Purpose |
|-----|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Models, endpoints, auth bridge, async, deployment details |
| [CODING_STYLE.md](CODING_STYLE.md) | Design tokens, component conventions, backend conventions |
| [DEPLOY.md](DEPLOY.md) | VM setup, nginx, systemd, env vars, deploy commands (source of truth) |
| [docs/index.md](docs/index.md) | Catalog of deep-dive guides |
| [backendServer/AGENTS.md](backendServer/AGENTS.md) | Backend directory map |
| [theCommonsWeb/AGENTS.md](theCommonsWeb/AGENTS.md) | Main frontend directory map |
| [broadcastWeb/AGENTS.md](broadcastWeb/AGENTS.md) | Broadcast operator SPA map |
| [docs/validated-patterns.md](docs/validated-patterns.md) | Session-confirmed gotchas (confirmed in real sessions, not speculative) |

See @docs/validated-patterns.md for session-confirmed gotchas not covered elsewhere.
