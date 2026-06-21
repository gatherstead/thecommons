# The Commons — Project Context (Consolidated)

> **Purpose:** Self-contained context dump for use in Claude.ai projects, planning sessions outside the repo, or onboarding. Generated from `AGENTS.md`, `ARCHITECTURE.md`, `CODING_STYLE.md`, `DEPLOY.md`, `docs/`, and the sub-project `AGENTS.md` files. **The in-repo docs are canonical** — if this file drifts, trust them. Regenerate this file from them rather than hand-editing.

---

## 1. What This Is

The Commons is a local community events aggregator for small NC towns (Chapel Hill / Carrboro / Pittsboro). A monorepo with a Django REST API backend, a Next.js frontend, a separate broadcast subsystem (event syndication to third-party calendars), and a dormant browser extension. Deployed on a single Oracle Cloud VM; database is managed Postgres on Neon.

The product look-and-feel is intentionally a **digital newspaper** — old-timey Craigslist crossed with a small-town broadsheet. Serif fonts (Georgia), cream/ink palette, column rules, density over whitespace. No gradients, no rounded pill buttons, no startup vibes.

```
thecommons/
├── backendServer/      # Django 6 + DRF + Postgres + Gemini ingestion + broadcast + Celery
├── theCommonsWeb/      # Next.js 16 (App Router) + React 19 + Better Auth (main site)
├── broadcastWeb/       # Vite + React operator SPA for broadcast
├── broadcastExtension/ # Chrome MV3 extension (manual broadcast review, dormant)
└── docs/               # Deep-dive guides
```

---

## 2. Tech Stack

| Layer | Tech |
|-------|------|
| Frontend (main) | Next.js 16 (App Router + Turbopack), React 19, TypeScript, Tailwind v4, TanStack Query v5 |
| Frontend (broadcast) | Vite 7 + React 19 SPA |
| Backend | Python 3.13, Django 6, Django REST Framework, `uv` |
| Database | PostgreSQL on Neon (psycopg from Django; pg/Drizzle from Next.js) |
| Async | Self-hosted Redis + Celery + django-celery-beat |
| Broadcast | Playwright (Chromium) via a DB-queue worker |
| LLM | Google Gemini (event standardization + safety scoring) |
| Auth | Better Auth (lives in Next.js); Django verifies JWTs via JWKS |
| Email | Brevo (transactional + weekly/monthly digests) |
| Admin | django-unfold |
| Testing | Django test runner (`fast`/`db` tags); Vitest (`fast`/`db` projects) |
| Deploy | Single Oracle Cloud VM (Ubuntu 24.04, ARM64) — nginx → gunicorn + Next.js; GitHub Actions CI/CD |

---

## 3. Repository Map

```
backendServer/
├── backend/        # Config: settings/{base,dev,prod,test}, urls, celery, jwt_auth, permissions, test_runner
├── events/         # Public app: Event/Town/Tag/Category/UserProfile/Business/Newsletter + neon_auth mirrors;
│                   #   cache.py, signals.py, tasks.py (Celery digests), email_service.py (Brevo)
├── ingestion/      # Pipeline: EventSource/RawEvent/StagedEvent; importers/, standardizer, deduplicator,
│                   #   safety_scorer, services, tasks
├── broadcast/      # Syndication: models, routing, schema, services, worker, runner, adapters/, access
└── templates/      # admin docs pages + email digests
theCommonsWeb/src/  # app/ (App Router) · components/ · hooks/ · lib/ (Better Auth, Drizzle, queryClient) ·
                    #   models/ · services/ (Django clients)
broadcastWeb/src/   # App.tsx · components/ · hooks/useExtension · services/broadcastApi · lib/persist · models/
docs/               # broadcast, ingestion-pipeline, safety-scoring, admin-backend, redis-celery-handoff, dev-db-isolation
```

> **Legacy dead files (ignore):** `backendServer/vercel.json`, `build.sh`, `main.py` (leftover from a previous Vercel deploy).

---

## 4. Data Models

### `events` app — `public` schema (managed)
- **`Tag`** — `name` (unique).
- **`Town`** — `slug` + `name`. SQL-backed; do not hardcode.
- **`Category`** — `slug` + `display_name`; distinct from `Tag`. SQL-backed; do not hardcode.
- **`Event`** — UUID PK · title · town (FK, SET_NULL) · date (indexed) · venue · description · price · photo · link · `tags`/`categories` (M2M) · `is_verified` · `source_name` · `created_by` (FK → `BetterAuthUser`).
- **`UserProfile`** — OneToOne → `BetterAuthUser` · `user_type` (LOCAL/BUSINESS/VENUE) · `primary_city` · `address` · `email_preference` (WEEKLY/MONTHLY/NEVER) · `tags` (M2M). Created automatically via a Better Auth `databaseHook`.
- **`BusinessProfile`** — OneToOne → `BetterAuthUser` · `business_name` · `description` · `tags` (M2M) · `service_area` (M2M Town) · contacts · `is_published`.
- **`NewsletterSubscriber`** — `email` · `frequency` · `is_active` · `subscribed_at`.

### Better Auth mirrors — `neon_auth` schema, `managed = False`
`BetterAuthUser`, `BetterAuthSession`, `BetterAuthAccount`, `BetterAuthVerification`, `BetterAuthJwks`. Django maps them read-only via the cross-schema `db_table` trick (`'neon_auth"."user'`); FKs use `db_constraint=False`. **Never migrate them.**

### `ingestion` app
- **`EventSource`** — `source_type ∈ {ics, scraper, email}`, polled URL.
- **`RawEvent`** — scraped event pre-LLM; unique on (source, source_uid).
- **`StagedEvent`** — LLM-standardized, awaiting review; status ∈ {pending, approved, rejected, duplicate}; `safety_score`; links to `published_event`.

### `broadcast` app
- **`BroadcastSubmission`** — denormalized event copy; status ∈ {queued, running, done, failed, canceled}.
- **`BroadcastTarget`** — per-site; status ∈ {pending, in_progress, succeeded, failed, needs_manual, skipped}; `dry_run`, `screenshot_path`, `external_url`.

### Database ownership

| Schema | Owner | Django access |
|--------|-------|---------------|
| `public` | Django migrations | Full read/write |
| `neon_auth` | Better Auth (Next.js) | Read-only mirrors (`managed = False`) — never migrate |

---

## 5. API Endpoints (Django)

`APPEND_SLASH=False` (slashes exact); no global DRF config (per-view auth/permissions). Auth: `—` public · `user` Better Auth JWT · `key` `THE_COMMONS_API_KEY` · `code` `X-Broadcast-Access-Code`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/events/` | — | Published events (window/category filters, Redis-cached) |
| GET | `/events/towns/` · `/events/categories/` | — | Towns / categories |
| GET | `/events/me/profile` · `/events/me/events` | user | Own profile / events |
| GET/PATCH/DELETE | `/events/staged/<int>` | user | Manage own staged submission |
| GET/DELETE | `/events/<uuid>` | user (delete) | Event detail / owner delete |
| POST | `/events/create` | user or key | Submit an event → StagedEvent |
| GET/PATCH | `/auth/me` | user | Read / update profile |
| POST | `/auth/subscribe` | — | Newsletter signup |
| GET/POST | `/businesses` · `/businesses/me` · `/businesses/<uuid>` | user | Business listing CRUD |
| GET | `/api/cron/ingest` | CRON_SECRET | Queue ingestion pipeline |
| POST | `/api/events/publish-approved` | key | Queue bulk publish |
| POST/GET | `/broadcast/...` | code | Preview/submit/jobs/screenshots/manual (see §10) |

> Login/signup/logout are handled by Better Auth in **Next.js** at `/api/auth/*` (incl. lazy `/api/auth/enter` and `/api/auth/set-password`). Django admin at `/admin/` (django-unfold).

---

## 6. Authentication — Better Auth ↔ Django Bridge

**Key files:** `backend/jwt_auth.py`, `backend/permissions.py`, `src/lib/auth.ts`, `src/lib/lazy-auth-plugin.ts`, `src/hooks/useAuth.tsx`, `src/app/api/auth/set-password/route.ts`

Auth is owned by **Better Auth inside Next.js** — no Django login/signup endpoints. Django only *verifies* tokens.

- Browser holds a Better Auth session cookie; to call Django it fetches a short-lived **JWT** from `/api/auth/token` and sends `Authorization: Bearer <jwt>`.
- `BearerTokenAuthentication` accepts either a **Better Auth JWT** (verified statelessly against the frontend JWKS, in-process cache with TTL + stale-grace; `sub` → `BetterAuthUser`) **or** the shared **`THE_COMMONS_API_KEY`** (no user).
- `databaseHooks.user.create.after` inserts a matching `events_userprofile` on user creation.
- **Lazy passwordless accounts:** email-first signup via `POST /api/auth/enter`; users secure the account later via `POST /api/auth/set-password`. No email verification for MVP.
- **`has_password`** is derived from the `BetterAuthAccount` mirror — no column, no migration.
- **Google sign-in is DISABLED** (commented out in `auth.ts`, `AuthFlow.tsx`, `google-popup/`).

---

## 7. Ingestion Pipeline

**Key files:** `ingestion/tasks.py`, `importers/ics_importer.py`, `standardizer.py`, `deduplicator.py`, `safety_scorer.py`, `services.py`

```
cleanup_old_events → poll_all_ics_sources → standardize (Gemini) → dedup (thefuzz)
  → safety score (Gemini) → auto_publish_safe_events / publish_all_approved()
EventSource → RawEvent → StagedEvent → Event (published)
```

Runs daily via Celery beat (04:00 ET) or `POST /api/cron/ingest` (`CRON_SECRET`) / `manage.py ingest_events`. Public/auth users submit via `POST /events/create` (creates a pending StagedEvent directly). Unknown `Town` slugs are skipped at publish. Threshold `SAFETY_SCORE_THRESHOLD` (default 0.3). See `docs/ingestion-pipeline.md`, `docs/safety-scoring.md`.

---

## 8. Async — Redis + Celery

**Key files:** `backend/celery.py`, `events/tasks.py`, `ingestion/tasks.py`, `events/cache.py`, `events/signals.py`

- One Redis instance: **DB 0** = Celery broker + results (`REDIS_URL`), **DB 1** = Django cache (`REDIS_CACHE_URL`).
- Celery autodiscovers tasks; `django_celery_beat` `DatabaseScheduler` holds schedules in Postgres, seeded by migrations: weekly digest (Sun 18:00 ET), ingest (04:00 ET).
- Tasks: `events.tasks` (`ping`, `send_one_digest`, `fan_out_weekly_digest`), `ingestion.tasks` (`run_ingestion_pipeline`, `publish_all_approved_task`).
- Read-endpoint cache (`events/cache.py`) is version-keyed; `events/signals.py` invalidates on Event/Town/Category writes.
- The **broadcast worker is NOT Celery** — it has its own Postgres queue.

See `docs/redis-celery-handoff.md`.

### Email digests
`events/email_service.py` wraps **Brevo**; digest HTML in `templates/email/`. Commands: `send_digest`, `send_test_digest --email`, `send_weekly_digest`.

---

## 9. Frontend Architecture (theCommonsWeb)

Next.js 16 App Router; root layout wraps `QueryProvider → AuthProvider → MessageStackProvider`.

### Routes

| Path | File | Type | Purpose |
|------|------|------|---------|
| `/` | `app/page.tsx` | client | Feed + calendar |
| `/about` | `app/about/page.tsx` | server | About (SEO) |
| `/post` | `app/post/page.tsx` | client | Submit event (auth-gated) |
| `/profile` | `app/profile/page.tsx` | client | Profile + digest prefs + security |
| `/dashboard` | `app/dashboard/page.tsx` | client | Manage events + business listing |
| `/auth[/login\|/signup]` | `app/auth/` | server → client `AuthFlow` | Login / signup |
| `/events/[uuid]` | `app/events/[uuid]/page.tsx` | server | Event detail (OpenGraph) |
| `/api/auth/[...all]` · `/api/auth/set-password` | `app/api/auth/` | route | Better Auth handler / set-password |

### Data layer
TanStack Query (`lib/queryClient.ts`: `staleTime/gcTime: Infinity`, `retry: 1`), provided by `QueryProvider`. Keys: `['towns']`, `['categories']`, `['profile', token]`, `['events', …]`, `['myEvents', token]`, `['myBusiness', token]`. Services (`src/services/`) call Django over `fetch` at `NEXT_PUBLIC_API_BASE_URL`; `fetchWithRetry` covers Neon cold-starts. Auth combined in `useAuth` (session + JWT + profile); no `middleware.ts` (client-side route guards).

---

## 10. Broadcast (event syndication)

**Source of truth: `docs/broadcast.md`.** Pushes one event to multiple third-party calendars via headless Playwright. Isolated from `events/` (`routing.py` must not import events); not Celery (own Postgres queue, `SELECT FOR UPDATE SKIP LOCKED`); no ORM inside `sync_playwright`.

Flow: access code → `POST /preview` (`CanonicalEvent` + `routing.eligible_targets`) → `POST /submit` (Submission + Targets, dry-run first) → `run_broadcast_worker` claims job → `runner.py` drives one Chromium per target → adapters fill/submit. Captcha sites end `needs_manual` and use the recipe layer + dormant Chrome extension for human handoff.

Models: `BroadcastSubmission` / `BroadcastTarget`. 10 Tier-1 adapters + mock (`adapters/__init__.py`). Access via `X-Broadcast-Access-Code` (`access.py`, `BROADCAST_ACCESS_CODES`). Commands: `run_broadcast_worker`, `broadcast_dry_run`, `capture_broadcast_form`, `check_recipes`, `scaffold_adapter`. Dev autospawns a one-shot worker (`BROADCAST_AUTOSPAWN_WORKER`); prod uses the systemd `broadcast-worker`.

---

## 11. Coding Style & Conventions

(See `CODING_STYLE.md` for the authoritative version.)

- **Look:** ink on newsprint; Georgia serif everywhere (no network fonts); column rules/thick borders instead of cards/shadows; density over whitespace.
- **Frontend tokens** (`src/app/globals.css`): never hardcode hex — use CSS custom properties (`--color-bg #f4f1eb`, `--color-text #1a1a1a`, `--color-accent #8b0000`, Georgia `--font-*`). Utilities: `.rule-thick`, `.rule-double`, `.drop-cap`, `.skeleton-block`.
- **Frontend components:** TypeScript; `{ComponentName}Props`; `src/components/{category}/`; Tailwind for layout, CSS vars for color; data via `useEvents`; auth via `useAuth` (never call `authClient`/manage JWTs in components); API → `FrontendEvent` mapping in services; `'use client'` for interactive components; `NEXT_PUBLIC_` for browser env.
- **Backend:** domain-scoped apps (don't bleed pipeline logic into events; keep broadcast isolated); thin views, logic in `services.py`; `transaction.atomic()` across models; migrations required except `neon_auth` mirrors; auth delegated (no `auth.User`); `Town`/`Category` are canonical SQL authorities.
- **General:** descriptive names over what-comments; why-only comments; no dead code; keep `.env.example` current.

---

## 12. Testing & CI

- **Backend:** `DJANGO_SETTINGS_MODULE=backend.settings.test` (Postgres, never SQLite); `NeonAuthTestRunner` builds the `neon_auth` schema. Tiers via `@tag`: `fast` (no-DB, `*_fast.py`) / `db` (`*_db.py`). `test.py` strips `-pooler` for Neon's direct endpoint. Run `uv run python manage.py test [--tag=fast|--tag=db]`.
- **Frontend:** Vitest, projects `fast` (node) / `db` (jsdom). `pnpm test:fast|test:db`; `pnpm build` is the type-check gate.
- **CI** (`.github/workflows/ci.yml`): push/PR to `main`; jobs `backend` (Postgres 16, uv/Py 3.13, fast then db), `frontend-commons`, `frontend-broadcast` (pnpm 11.1.1, Node 22, build + tests), gated `deploy` (push-to-main only → SSH to Oracle VM).
- **Known gaps:** many `broadcast/tests/` files + `ingestion/tests/test_pipeline.py` carry no `@tag` → never run in CI; no lint step (eslint config commented out; no ruff/mypy/prettier); pnpm/Node pinned only in CI.

---

## 13. Deployment (Production VM)

(See `DEPLOY.md` — source of truth.)

- **Host:** Oracle Cloud, Ubuntu 24.04 ARM64, 1 OCPU / 6 GB, IP `129.80.229.41`. Repo at `/home/ubuntu/thecommons`, user `ubuntu`. Python via `uv` (snap, never pip); Node via `pnpm` (never npm).
- **DNS/TLS:** Cloudflare proxied, Full (strict); origin cert covers `*.thecommons.town`.
- **Domains:** `thecommons.town` → Next.js (:3000); `api.thecommons.town` → gunicorn socket; `broadcast.thecommons.town` → static broadcast SPA.
- **systemd services:** `gunicorn`, `nextjs`, `redis-server`, `celery`, `celerybeat`, `broadcast-worker`. DB is managed Postgres on Neon (external).
- **CI/CD:** every push to `main` runs CI; on success the gated `deploy` job SSHes in → `git pull` → `uv sync` → `migrate` (unguarded) → `collectstatic` → build both frontends → restart the five services. Scheduled jobs are `django-celery-beat` (DB-backed), not OS cron.

---

## 14. Environment Variables

### `backendServer/.env`
```
DATABASE_URL=                 # Neon Postgres
DJANGO_SECRET_KEY=
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,api.thecommons.town
CORS_EXTRA_ORIGINS=https://thecommons.town
CSRF_TRUSTED_ORIGINS=https://api.thecommons.town,https://thecommons.town
REDIS_URL=                    # DB 0 — Celery broker + results
REDIS_CACHE_URL=              # DB 1 — Django cache
GEMINI_API_KEY=
CRON_SECRET=
THE_COMMONS_API_KEY=
SAFETY_SCORE_THRESHOLD=0.3    # optional
INGEST_SHARD_COUNT=           # optional
BETTER_AUTH_JWKS_URL=         # prod: https://thecommons.town/api/auth/jwks
BETTER_AUTH_ISSUER=           # prod: https://thecommons.town
BETTER_AUTH_AUDIENCE=
BREVO_API_KEY=
DIGEST_FROM_EMAIL=digest@thecommons.town
SITE_URL=https://thecommons.town
BROADCAST_ACCESS_CODES=       # label:code,...
BROADCAST_AUTOSPAWN_WORKER=   # true in dev, false in prod
# plus BROADCAST_HEADLESS / _DRY_RUN_DEFAULT / _MAX_CONCURRENCY / _SCREENSHOT_DIR /
#      _DOWNLOAD_DIR / _TIMEOUT_MS / _ENABLE_MOCK
```

### `theCommonsWeb/.env.local`
```
NEXT_PUBLIC_API_BASE_URL=          # e.g. http://127.0.0.1:8000 (prod: https://api.thecommons.town)
NEXT_PUBLIC_THE_COMMONS_API_KEY=   # fallback for event creation
NEXT_PUBLIC_BETTER_AUTH_URL=
DATABASE_URL=                      # same Neon string (Better Auth owns neon_auth)
BETTER_AUTH_SECRET=
BETTER_AUTH_URL=                   # prod: https://thecommons.town
```

### `broadcastWeb/.env`
```
VITE_BROADCAST_API_BASE_URL=       # Django API
VITE_BROADCAST_EXTENSION_ID=       # enables the manual-review button
```

---

## 15. Quick Start (Local) + Dev Mode

```bash
# Backend (needs Redis for Celery)
cd backendServer && uv sync && python manage.py migrate && python manage.py runserver
uv run celery -A backend worker -l info   # + beat / run_broadcast_worker as needed

# Main frontend (pnpm only)
cd theCommonsWeb && pnpm install && pnpm dev

# Broadcast SPA (optional)
cd broadcastWeb && pnpm install && pnpm dev
```

- Backend tests: `DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test`
- Frontend type-check: `pnpm build`

**Dev mode:** there is no single dev-mode flag or auth bypass. It's `settings/dev.py` vs `prod.py` (`DJANGO_SETTINGS_MODULE`) + `BROADCAST_AUTOSPAWN_WORKER` (true in dev) + `DEBUG`-gated mock form + `BROADCAST_ENABLE_MOCK`. Frontend dev-only behavior is just React Query Devtools and `pg` pool HMR caching.

---

## 16. Guardrails (Cross-Cutting Rules)

- **Never migrate `neon_auth` tables.** Better Auth owns them (`managed = False`).
- **`Town` and `Category` are SQL tables** — don't hardcode; pipeline skips unknown town slugs.
- **Auth lives in Next.js**, not Django. No Django login/signup views or `auth.User`.
- **`broadcast/` is isolated** — `routing.py` must not import `events`; **no ORM inside `sync_playwright`**.
- **Redis layout fixed:** DB 0 broker/results, DB 1 cache.
- **pnpm only** (pinned 11) — `npm install` breaks the symlinked store.
- **Events API excludes past by default.**
- **Google sign-in disabled** — revisit later.
- **Never commit `.env`** — update `.env.example`.
- **Newspaper aesthetic** — serif, cream/ink, column rules; no gradients/shadows/pills.
- **Legacy Vercel files** (`vercel.json`, `build.sh`, `main.py`) are dead.
- **If a doc contradicts the code, trust the code** and flag the drift.

---

## 17. Where to Find Deeper Detail

Deep-dive guides in `docs/`: `broadcast.md` (broadcast source of truth), `ingestion-pipeline.md`, `safety-scoring.md`, `admin-backend.md`, `redis-celery-handoff.md`, `dev-db-isolation.md`. Per-directory maps: `backendServer/AGENTS.md`, `theCommonsWeb/AGENTS.md`, `broadcastWeb/AGENTS.md`, `broadcastExtension/README.md`.
