# The Commons — Claude Code Context

The Commons is a local community events aggregator for small NC towns (initially Chapel Hill / Carrboro). It has a Django REST API backend and a Next.js frontend, deployed together on a single Oracle Cloud VM (nginx → gunicorn + Next.js, TLS via Certbot). The database is managed Postgres on Neon.

## Before you start any task

Read these three files first so we share the same mental model of the system. They override any assumptions from training data — the stack has changed (Better Auth, Oracle deploy), so don't rely on memory.

1. **This file** — workflows, conventions, and gotchas.
2. [`ARCHITECTURE.md`](./ARCHITECTURE.md) — system design, data models, endpoints, auth bridge, deploy topology.
3. [`CODING_STYLE.md`](./CODING_STYLE.md) — design philosophy and frontend/backend conventions.

Skim all three before writing or changing code. If something you read contradicts the code, trust the code and flag the doc drift.

---

## Repo Layout

```
thecommons/
├── backendServer/   # Django 6 + DRF + Postgres (Neon) + Gemini ingestion pipeline
├── theCommonsWeb/   # Next.js 16 (App Router) + React 19 + TypeScript + Tailwind v4 + Better Auth
├── docs/            # Human-readable docs (admin guide, pipeline guide)
├── AGENTS.md        # Same context, vendor-neutral (for non-Claude agent tools)
├── ARCHITECTURE.md
└── CODING_STYLE.md
```

## Quick-start Commands

```bash
# Backend
cd backendServer && uv sync && python manage.py migrate && python manage.py runserver

# Frontend
cd theCommonsWeb && npm install && npm run dev
```

The frontend owns auth, so it needs `DATABASE_URL` (Neon) and Better Auth env vars to run — see `theCommonsWeb/.env.example`. The backend validates Better Auth JWTs against the frontend's JWKS endpoint, so for end-to-end auth in dev, run both servers.

## Tech Stack at a Glance

| Layer | Tech |
|-------|------|
| Frontend | Next.js 16 (App Router + Turbopack), React 19, TypeScript, Tailwind CSS v4 |
| Backend | Python 3.13, Django 6, Django REST Framework |
| Database | PostgreSQL on **Neon** (psycopg3 from Django; `pg`/Drizzle from Next.js) |
| LLM | Google Gemini (event standardization in ingestion pipeline) |
| Auth | **Better Auth** (lives in Next.js); Django verifies issued JWTs via JWKS |
| Email | Brevo (transactional + weekly/monthly digests) |
| Admin | django-unfold |
| Deploy | Single **Oracle Cloud** VM (Ubuntu 24.04, ARM64) — nginx → gunicorn (:8000) + Next.js (:3000) |

## Key Workflows

- **Auth**: Better Auth runs inside Next.js (`src/lib/auth.ts`), owns the user/session/account tables in Neon's `neon_auth` schema, and supports email+password. (**Google sign-in is temporarily disabled** — commented out in `src/lib/auth.ts`, `src/app/auth/AuthFlow.tsx`, and `src/app/auth/google-popup/`; it returned `invalid_code` and bypassed user-type selection. Revisit later.) The browser holds a Better Auth session cookie; for calls to Django the frontend fetches a short-lived JWT from `/api/auth/token` and sends it as `Authorization: Bearer <jwt>`. Django verifies that JWT statelessly against the frontend's JWKS endpoint (`backend/jwt_auth.py`). Creating a Better Auth user also inserts a Django `UserProfile` row via a `databaseHook`.
- **Lazy account creation**: signup is email-first and password-optional. The `/auth` page (`src/app/auth/page.tsx`) walks user type → preferences → email, then calls `POST /api/auth/enter` (custom plugin `src/lib/lazy-auth-plugin.ts`). A new email gets a passwordless account + session on the spot; an email that has already set a password is prompted for it. Users can secure an account later via `POST /api/auth/set-password`. `has_password` is **derived** server-side from the `BetterAuthAccount` mirror (not stored) and drives UI nudges (`AccountBanner`, profile `SecuritySection`). There is no `AuthModal` anymore — all auth flows through `/auth`.
- **Ingestion pipeline**: `POST /api/cron/ingest` → scrapes EventSources → creates RawEvents → Gemini standardizes into StagedEvents → admin reviews in `/admin/` → `publish_all_approved()` promotes to Events.
- **Submitting events**: `POST /events/create` (requires auth — a user JWT or the shared API key via `HasCommonsAPIKeyOrUser`).
- **Publishing approved staged events**: Admin "Publish Approved" page or `POST /api/events/publish-approved`.
- **Email digests**: `python manage.py send_weekly_digest` sends each subscriber a personalized digest (their town + tag interests) via Brevo. Scheduled by cron on the VM.

## Things to Know

- **Don't migrate the `neon_auth` tables.** Better Auth (Next.js) owns those tables. Django mirrors them as `managed = False` models (`BetterAuthUser`, `BetterAuthSession`, etc.) purely for reads/joins. `UserProfile` is a OneToOne to `BetterAuthUser`, not Django's `auth.User`.
- Auth signup/login/logout endpoints live in **Next.js** (`/api/auth/*`, including the lazy `enter` and `set-password` routes), not Django. Django only exposes profile (`/auth/me`, `/events/me/profile`) and newsletter subscribe (`/auth/subscribe`), and computes `has_password` for the profile responses.
- `Town` is a SQL table — don't add towns as hardcoded strings. If a new town is needed, add a row to the `Town` model first. The ingestion pipeline skips staged events whose `town` slug doesn't match any `Town` record.
- `Category` is also a SQL table (separate from `Tag`); events carry both `tags` and `categories` M2M.
- Both sub-projects have their own env files. See `.env.example` in each directory. The frontend uses the `NEXT_PUBLIC_` prefix for browser-exposed variables (Next.js convention); secrets like `DATABASE_URL`, `BETTER_AUTH_SECRET`, and `GOOGLE_CLIENT_SECRET` must stay server-side.
- The frontend design is a **newspaper aesthetic** — serif fonts, cream/ink palette, column rules. Don't introduce gradients, shadows, or rounded pill buttons. See `CODING_STYLE.md`.
- The events API defaults to excluding past events. Use `?include_past=true` to get everything, or `?after=`/`?before=` for date ranges. `Event.date` is indexed.
- Most frontend components are `'use client'`. The root layout (`app/layout.tsx`) and the About page leverage server components for SEO metadata.
- In the recap, try to list the ticket name if given (10.2, T12, etc.) in addition to the rest of the recap

## Working in This Repo

- Run `python manage.py migrate` after any model change before running the server — but never generate migrations for the `neon_auth` mirror models (`managed = False`).
- Backend tests live in `{app}/tests.py`. Run with `python manage.py test`.
- Frontend type-checks with `npm run build` (`next build` includes TypeScript checks).
- Never commit `.env` / `.env.local` files — document new variables in the matching `.env.example`.
