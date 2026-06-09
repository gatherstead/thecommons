# The Commons — Agent Map

Local community events aggregator for small NC towns (Chapel Hill / Carrboro). Django REST API backend + Next.js frontend, deployed on a single Oracle Cloud VM. Database is managed Postgres on Neon.

## Repo Map

```
thecommons/
├── backendServer/                # Django 6 + DRF + Postgres (Neon) + Gemini ingestion pipeline
│   ├── backend/                  #   Project config: settings, urls, jwt_auth, permissions
│   ├── events/                   #   Events, towns, tags, categories, profiles, businesses, digests
│   ├── ingestion/                #   Pipeline: sources → raw → staged → published
│   ├── templates/email/          #   HTML email templates
│   └── AGENTS.md                 #   ← Backend local map
├── theCommonsWeb/                # Next.js 16 (App Router) + React 19 + TypeScript + Tailwind v4
│   └── src/
│       ├── app/                  #   Pages + API routes (App Router)
│       ├── components/           #   React components (auth/, events/, layout/, ui/)
│       ├── hooks/                #   useAuth, useEvents, useMessageStack, useToggleSet
│       ├── lib/                  #   Better Auth config, Drizzle schema, DB pool, lazy-auth plugin
│       ├── models/               #   TypeScript types (events, auth, business)
│       ├── services/             #   API clients (event, profile, business)
│       └── AGENTS.md             #   ← Frontend local map (one level up, in theCommonsWeb/)
├── docs/                         # Deep-dive guides (see docs/index.md)
│   ├── index.md                  #   Documentation catalog
│   ├── ingestion-pipeline.md     #   Pipeline walkthrough
│   ├── admin-backend.md          #   Admin UI guide
│   └── safety-scoring.md         #   Safety scorer details
├── AGENTS.md                     # ← You are here
├── CLAUDE.md                     # Claude Code entry point (points here)
├── ARCHITECTURE.md               # System design: models, endpoints, auth bridge
├── CODING_STYLE.md               # Design philosophy + conventions
└── DEPLOY.md                     # Production VM setup, nginx, systemd, deploy commands
```

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 16 (App Router + Turbopack), React 19, TypeScript, Tailwind CSS v4 |
| Backend | Python 3.13, Django 6, Django REST Framework |
| Database | PostgreSQL on Neon (psycopg3 from Django; pg/Drizzle from Next.js) |
| LLM | Google Gemini (event standardization in ingestion pipeline) |
| Auth | Better Auth (lives in Next.js); Django verifies JWTs via JWKS |
| Email | Brevo (transactional + weekly/monthly digests) |
| Admin | django-unfold |
| Deploy | Single Oracle Cloud VM (Ubuntu 24.04, ARM64) — nginx → gunicorn + Next.js |

## Quick Start

```bash
# Backend
cd backendServer && uv sync && python manage.py migrate && python manage.py runserver

# Frontend
cd theCommonsWeb && npm install && npm run dev
```

Run both for end-to-end auth (Django validates JWTs against the frontend's JWKS endpoint).

## Where to Find Things

| Concern | Key files | Deep dive |
|---------|-----------|-----------|
| Auth bridge | `backend/jwt_auth.py`, `backend/permissions.py`, `src/lib/auth.ts`, `src/lib/lazy-auth-plugin.ts` | [ARCHITECTURE.md §Authentication](ARCHITECTURE.md#authentication) |
| Lazy accounts | `src/lib/lazy-auth-plugin.ts`, `src/app/api/auth/set-password/route.ts`, `src/hooks/useAuth.tsx` | [ARCHITECTURE.md §Authentication](ARCHITECTURE.md#authentication) |
| Ingestion pipeline | `ingestion/services.py`, `ingestion/standardizer.py`, `ingestion/importers/`, `ingestion/safety_scorer.py` | [docs/ingestion-pipeline.md](docs/ingestion-pipeline.md) |
| Email digests | `events/email_service.py`, `events/management/commands/send_weekly_digest.py` | [ARCHITECTURE.md §Email Digests](ARCHITECTURE.md#email-digests) |
| Data models | `events/models.py`, `ingestion/models.py` | [ARCHITECTURE.md §Data Models](ARCHITECTURE.md#data-models) |
| API endpoints | `backend/urls.py`, `events/urls.py` | [ARCHITECTURE.md §API Endpoints](ARCHITECTURE.md#api-endpoints) |
| Design system | `src/app/globals.css`, `src/components/ui/` | [CODING_STYLE.md](CODING_STYLE.md) |
| Deployment | systemd services, nginx, env vars on VM | [DEPLOY.md](DEPLOY.md) |
| Admin UI | `events/admin.py`, `ingestion/admin.py` | [docs/admin-backend.md](docs/admin-backend.md) |
| Safety scoring | `ingestion/safety_scorer.py` | [docs/safety-scoring.md](docs/safety-scoring.md) |

## Guardrails

- **Never migrate `neon_auth` tables.** Better Auth (Next.js) owns them. Django mirrors are `managed = False`.
- **`Town` and `Category` are SQL tables** — don't hardcode. Pipeline skips events with unknown town slugs.
- **Auth lives in Next.js**, not Django. Don't add Django login/signup views.
- **Never commit `.env` files** — update `.env.example` instead.
- **Newspaper aesthetic** — serif fonts, cream/ink, column rules. No gradients, shadows, or pill buttons. See [CODING_STYLE.md](CODING_STYLE.md).
- **Events API excludes past by default** — use `?include_past=true` for all events.
- **Google sign-in is disabled** — commented out in `auth.ts`, `AuthFlow.tsx`, `google-popup/`. Revisit later.
- **Legacy Vercel files** — `backendServer/vercel.json`, `build.sh`, `main.py` are dead artifacts. Ignore them.

## Database Ownership

| Schema | Owner | Django access |
|--------|-------|---------------|
| `public` | Django migrations | Full read/write |
| `neon_auth` | Better Auth (Next.js) | Read-only mirrors (`managed = False`) — never migrate |

## Ingestion Pipeline

```
EventSource (URL/feed)
    ↓  importers/ (ICS, scraper)
RawEvent  ←  deduplicator.py
    ↓  standardizer.py (Gemini LLM)  +  safety_scorer.py
StagedEvent  ←  admin reviews in django-unfold
    ↓  services.publish_all_approved()
Event (published, public)
```

Triggered via `POST /api/cron/ingest` (requires `CRON_SECRET`) or `python manage.py ingest_events`.

## Documentation Index

| Doc | Purpose |
|-----|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Models, endpoints, auth bridge, deployment details |
| [CODING_STYLE.md](CODING_STYLE.md) | Design tokens, component conventions, backend conventions |
| [DEPLOY.md](DEPLOY.md) | VM setup, nginx, systemd, env vars, deploy commands |
| [docs/index.md](docs/index.md) | Catalog of deep-dive guides |
| [backendServer/AGENTS.md](backendServer/AGENTS.md) | Backend directory map |
| [theCommonsWeb/AGENTS.md](theCommonsWeb/AGENTS.md) | Frontend directory map |
