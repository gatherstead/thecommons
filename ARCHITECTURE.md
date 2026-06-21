# Architecture

Deep-dive reference for The Commons. For the repo map start at [AGENTS.md](AGENTS.md); for deployment, [DEPLOY.md](DEPLOY.md) is the source of truth. If anything here contradicts the code, **trust the code** and flag the drift.

## Overview

The Commons is a monorepo with four deployable pieces:

| Piece | Path | What it is |
|-------|------|------------|
| Backend | `backendServer/` | Django 6 + DRF — public API, LLM ingestion pipeline, broadcast subsystem, Celery async |
| Main frontend | `theCommonsWeb/` | Next.js 16 (App Router) + Better Auth — public site + auth provider |
| Broadcast SPA | `broadcastWeb/` | Vite + React operator console for the broadcast feature |
| Extension | `broadcastExtension/` | Chrome MV3 extension for manual-review broadcast handoff (dormant) |

Data lives in Postgres on Neon (`public` schema owned by Django, `neon_auth` schema owned by Better Auth). Async work runs on self-hosted Redis + Celery. Everything is served from one Oracle Cloud VM behind nginx.

---

## Data Models

**Key files:** `events/models.py`, `ingestion/models.py`, `broadcast/models.py`

### `events` app — `public` schema (managed)

| Model | Key fields | Relationships |
|-------|-----------|---------------|
| `Tag` | `name` (unique) | M2M from users/businesses/events |
| `Town` | `slug` (unique), `name` | FK target of `Event.town` |
| `Category` | `slug` (unique), `display_name` | M2M with `Event` |
| `UserProfile` | `uuid`, `user_type` (LOCAL/BUSINESS/VENUE), `primary_city`, `address`, `email_preference` (WEEKLY/MONTHLY/NEVER) | OneToOne→`BetterAuthUser` (`db_constraint=False`); M2M→`Tag` |
| `BusinessProfile` | `uuid`, `business_name`, `description`, `contact_email/phone`, `is_published`, timestamps | OneToOne→`BetterAuthUser`; M2M→`Tag`; M2M→`Town` (`service_area`) |
| `NewsletterSubscriber` | `email` (unique), `frequency`, `is_active`, `subscribed_at` | — |
| `Event` | `uuid` (PK), `title`, `date` (indexed), `venue`, `description`, `price`, `photo`, `link`, `is_verified`, `source_name` | FK→`Town` (SET_NULL); M2M→`Tag`, `Category`; FK→`BetterAuthUser` (`created_by`) |

### Better Auth mirrors — `neon_auth` schema (`managed = False`)

Better Auth (Next.js) owns these tables; Django maps them **read-only** for joins. **Never create migrations for them.** Models: `BetterAuthUser`, `BetterAuthSession`, `BetterAuthAccount`, `BetterAuthVerification`, `BetterAuthJwks`.

- The `db_table` values use a double-quote trick (e.g. `'neon_auth"."user'`) so Django emits a valid cross-schema reference `FROM "neon_auth"."user"`.
- `BetterAuthUser` hardcodes `is_authenticated=True` / `is_anonymous=False` so DRF permission classes treat it as a real user.
- FKs into these mirrors use `db_constraint=False` (no DB-level FK against unmanaged tables).

### `ingestion` app — `public` schema (managed)

| Model | Key fields | Relationships |
|-------|-----------|---------------|
| `EventSource` | `name`, `source_type` (ics/scraper/email), `url`, `active`, `last_polled`, `poll_interval_hours` | reverse `raw_events` |
| `RawEvent` | raw title/description/location, raw start/end, `source_url`, `source_uid`, `processed` | FK→`EventSource`; `unique_together=(source, source_uid)` |
| `StagedEvent` | LLM fields (title, description, location, town, datetimes, tags JSON, category, price, link), `status` (pending/approved/rejected/duplicate), `safety_score/notes`, `reviewer_notes` | OneToOne→`RawEvent`; self-FK `duplicate_of`; FK→`events.Event` (`published_event`); FK→`BetterAuthUser` (`submitted_by`) |

### `broadcast` app — `public` schema (managed)

| Model | Key fields | Relationships |
|-------|-----------|---------------|
| `BroadcastSubmission` | `uuid` (PK), `client_label`, denormalized event fields (title, datetimes, venue/address, locality JSON, categories JSON, urls, price, organizer, contacts), `status` (queued/running/done/failed/canceled), timestamps | reverse `targets` |
| `BroadcastTarget` | `uuid` (PK), `site_key`, `status` (pending/in_progress/succeeded/failed/needs_manual/skipped), `attempts`, `external_url`, `error`, `screenshot_path`, `dry_run`, timestamps | FK→`BroadcastSubmission`; `UniqueConstraint(submission, site_key)` |

### Database ownership

| Schema | Owner | Django access |
|--------|-------|---------------|
| `public` | Django migrations | Full read/write |
| `neon_auth` | Better Auth (Next.js) | Read-only mirrors (`managed = False`) — never migrate |

---

## API Endpoints

**Key files:** `backend/urls.py`, `events/urls.py`, `broadcast/urls.py`

Notes that apply throughout:
- **`APPEND_SLASH=False`** — trailing slashes are matched exactly as written below.
- **No global DRF config.** Each view sets its own `@authentication_classes` / `@permission_classes` (house pattern).
- Auth column: `—` = public, `user` = Better Auth JWT, `API key` = `THE_COMMONS_API_KEY`, `code` = `X-Broadcast-Access-Code`.

### Root (`backend/urls.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/cron/ingest` | `CRON_SECRET` | Queue the ingestion pipeline (Celery) |
| POST | `/api/events/publish-approved` | API key | Queue bulk publish of approved staged events |
| GET/PATCH | `/auth/me` | user | Read / update own profile |
| POST | `/auth/subscribe` | — | Newsletter signup |
| GET/POST | `/businesses` | user | Browse published businesses / create a listing |
| GET | `/businesses/me` | user | Own business listing |
| GET/PATCH/DELETE | `/businesses/<uuid>` | user | Business listing CRUD |
| GET/POST | `/admin/docs/...` | staff | Pipeline/admin docs pages + publish-approved button |
| — | `/admin/` | staff | Django admin (django-unfold) |

### Events (`/events/`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/events/` | — | Paginated published events (window/after/before/category filters, Redis-cached) |
| GET | `/events/towns/` | — | Town list (cached) |
| GET | `/events/categories/` | — | Category list (cached) |
| GET | `/events/me/profile` | user | Own profile summary (includes derived `has_password`) |
| GET | `/events/me/events` | user | Own staged + published events |
| GET/PATCH/DELETE | `/events/staged/<int>` | user | Manage own staged submission |
| GET/DELETE | `/events/<uuid>` | user (delete) | Event detail / owner delete |
| POST | `/events/create` | user or API key | Submit an event → `StagedEvent` |

### Broadcast (`/broadcast/`, all gated by `X-Broadcast-Access-Code`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/broadcast/preview` | Compute eligible/excluded target sites for an event |
| POST | `/broadcast/submit` | Create submission + targets, enqueue |
| GET | `/broadcast/jobs/<uuid>` | Job status + per-target detail |
| POST | `/broadcast/jobs/<uuid>/retry` | Re-queue selected targets |
| POST | `/broadcast/jobs/<uuid>/submit-real` | Promote dry-run targets to real |
| POST | `/broadcast/jobs/<uuid>/cancel` | Cancel job, skip pending |
| GET | `/broadcast/jobs/<uuid>/screenshots/<site_key>` | Serve gated screenshot PNG |
| GET | `/broadcast/jobs/<uuid>/manual/<site_key>` | Recipe JSON for a `needs_manual` target |
| GET | `/broadcast/mock-form` | Dev-only (`DEBUG`) mock submission form |

> Login/signup/logout are handled by Better Auth in **Next.js** at `/api/auth/*` (including lazy `POST /api/auth/enter` and `POST /api/auth/set-password`).

---

## Authentication

**Key files:** `backend/jwt_auth.py`, `backend/permissions.py`, `src/lib/auth.ts`, `src/lib/lazy-auth-plugin.ts`, `src/hooks/useAuth.tsx`, `src/app/api/auth/set-password/route.ts`

Auth is owned by **Better Auth running inside Next.js** — there are no Django login/signup endpoints. Django only *verifies* tokens.

### The bridge
- Browser authenticates with Better Auth and holds a session cookie.
- To call Django, the frontend fetches a short-lived **JWT** from `/api/auth/token` (Better Auth `jwt()` plugin) and sends it as `Authorization: Bearer <jwt>`.
- `BearerTokenAuthentication` accepts either:
  1. a **Better Auth JWT** verified statelessly against the frontend's JWKS endpoint (`BETTER_AUTH_JWKS_URL`); `sub` resolves to a `BetterAuthUser`. The JWKS client is cached in-process with a TTL and **stale-grace** fallback so brief Next.js outages don't cascade.
  2. the shared **`THE_COMMONS_API_KEY`** (no user attached) — for app-level calls like event creation.
- Permission classes live in `backend/permissions.py` and are applied per-view alongside DRF's `IsAuthenticated`.

### User-creation side effect
`src/lib/auth.ts` defines `databaseHooks.user.create.after`, which inserts a matching `public.events_userprofile` row whenever Better Auth creates a user — so every account has a Django profile.

### Lazy (passwordless) accounts
Signup is email-first, password-optional. The custom plugin `src/lib/lazy-auth-plugin.ts` exposes `POST /api/auth/enter`:
- New email → creates a Better Auth user (no credential) + session; the `databaseHook` fires.
- Existing passwordless email → fresh session.
- Existing email with a password → returns `requiresPassword: true` (no session); frontend collects the password and uses normal `signIn.email`.

Users secure the account later via `POST /api/auth/set-password` (links a `credential` account). **No email verification for MVP.**

### `has_password` is derived
Django computes it from the `BetterAuthAccount` mirror (`provider_id='credential'` with a non-null password) and returns it on `/auth/me` and `/events/me/profile`. No column, no migration.

### Google sign-in — DISABLED
Commented out in `src/lib/auth.ts`, `src/app/auth/AuthFlow.tsx`, and `src/app/auth/google-popup/`. Revisit later (needs a post-OAuth account-type step).

---

## Ingestion Pipeline

**Key files:** `ingestion/tasks.py`, `ingestion/importers/ics_importer.py`, `ingestion/standardizer.py`, `ingestion/deduplicator.py`, `ingestion/safety_scorer.py`, `ingestion/services.py`

Orchestrated by `ingestion.tasks.run_ingestion_pipeline` (Celery, daily 04:00 ET) and mirrored by the `ingest_events` command. Each step is error-isolated; the task retries the whole pipeline (up to 3×) if any step raises, since steps are idempotent.

```
1. cleanup_old_events          delete past Raw/Staged (keep approved-unpublished)
2. poll_all_ics_sources        fetch ICS feeds → RawEvent (shardable)
3. standardize_all_unprocessed Gemini → StagedEvent (pending); marks Raw processed
4. dedup_all_pending           thefuzz title/location/time match → mark duplicate
5. score_all_unscored          Gemini content-safety score 0.0–1.0
6. auto_publish_safe_events    score ≤ threshold → approved; rest held for manual review
   publish_all_approved()      atomically create Event rows, link, delete StagedEvents
```

Manual entrypoints: `POST /api/cron/ingest` (`CRON_SECRET`) queues the pipeline; `POST /api/events/publish-approved` (API key) and the admin docs page queue `publish_all_approved_task`. Public/auth users submit via `POST /events/create`, which creates a pending `StagedEvent` directly (skipping poll/standardize). Unknown `Town` slugs cause an event to be skipped at publish time. Threshold is `SAFETY_SCORE_THRESHOLD` (default 0.3). See [docs/ingestion-pipeline.md](docs/ingestion-pipeline.md) and [docs/safety-scoring.md](docs/safety-scoring.md).

---

## Broadcast

**Key files:** `broadcast/services.py`, `broadcast/worker.py`, `broadcast/runner.py`, `broadcast/routing.py`, `broadcast/adapters/`

The broadcast subsystem pushes a single event out to multiple third-party community calendars via headless Playwright form-filling. It is deliberately **isolated** from `events/` (its `routing.py` must not import from `events`) and does **not** use Celery — it runs its own DB-backed queue worker.

Flow: access code → `preview` (build a `CanonicalEvent`, match adapters via `routing.eligible_targets`) → `submit` (create `BroadcastSubmission` + `BroadcastTarget`s) → `run_broadcast_worker` claims the job (`SELECT FOR UPDATE SKIP LOCKED`) → `runner.py` drives one Chromium session per target (no ORM inside `sync_playwright`) → per-site adapters fill and submit.

**[docs/broadcast.md](docs/broadcast.md) is the single source of truth** for models, adapters, access codes, env vars, commands, and the manual-review handoff.

---

## Async: Redis + Celery

**Key files:** `backend/celery.py`, `backend/__init__.py`, `events/tasks.py`, `ingestion/tasks.py`, `events/cache.py`, `events/signals.py`

- **One Redis instance, two logical DBs:** DB 0 = Celery broker **and** result backend (`REDIS_URL`); DB 1 = Django cache (`RedisCache`, `REDIS_CACHE_URL`).
- **Celery** app is built in `backend/celery.py`, loaded eagerly via `backend/__init__.py`, and autodiscovers tasks. `CELERY_TIMEZONE = UTC` (beat entries carry their own tz).
- **Beat** uses `django_celery_beat`'s `DatabaseScheduler` — schedules live in Postgres and are editable in admin. Seeded by migrations:
  - `weekly-digest-sunday` → `events.tasks.fan_out_weekly_digest`, Sun 18:00 America/New_York (`events/migrations/0015_seed_digest_beat.py`).
  - `ingest-events-daily` → `ingestion.tasks.run_ingestion_pipeline`, 04:00 America/New_York (`ingestion/migrations/0007_seed_ingest_beat.py`).
- **Tasks:** `events.tasks` (`ping`, `send_one_digest`, `fan_out_weekly_digest`), `ingestion.tasks` (`run_ingestion_pipeline`, `publish_all_approved_task`).
- **Read-endpoint cache:** `events/cache.py` is a version-keyed Redis cache for the hot list endpoints; `events/signals.py` bumps the version on `Event`/`Town`/`Category` writes to invalidate.

See [docs/redis-celery-handoff.md](docs/redis-celery-handoff.md).

### Email digests
`events/email_service.py` wraps **Brevo** transactional email and builds digest HTML from `templates/email/`. `fan_out_weekly_digest` queues one `send_one_digest` per WEEKLY `UserProfile`. Management commands (`send_digest`, `send_test_digest`, `send_weekly_digest`) cover synchronous/test sends.

---

## Frontend Architecture

**Key files:** `src/app/layout.tsx`, `src/lib/queryClient.ts`, `src/components/providers/QueryProvider.tsx`, `src/hooks/useEvents.ts`, `src/services/`

The main site is **Next.js 16 App Router**. Root layout (`src/app/layout.tsx`) wraps `QueryProvider → AuthProvider → MessageStackProvider`.

### Routes

| Path | File | Type | Purpose |
|------|------|------|---------|
| `/` | `app/page.tsx` | client | Home: event feed + calendar, filters, detail modal |
| `/about` | `app/about/page.tsx` | server | Static about page (SEO metadata) |
| `/post` | `app/post/page.tsx` | client | Submit an event (auth-gated) |
| `/profile` | `app/profile/page.tsx` | client | Edit profile, digest prefs, security section |
| `/dashboard` | `app/dashboard/page.tsx` | client | Manage submitted events + business listing |
| `/auth` | `app/auth/page.tsx` | server | Redirects to `/auth/signup` |
| `/auth/login` | `app/auth/login/page.tsx` | server shell → client `AuthFlow` | Login |
| `/auth/signup` | `app/auth/signup/page.tsx` | server shell → client `AuthFlow` | Signup |
| `/auth/google-popup[/complete]` | `app/auth/google-popup/` | client | DISABLED Google OAuth popup |
| `/events/[uuid]` | `app/events/[uuid]/page.tsx` | server (async) | Event detail (`generateMetadata` + OpenGraph) |
| `/api/auth/[...all]` | `app/api/auth/[...all]/route.ts` | route | Better Auth handler |
| `/api/auth/set-password` | `app/api/auth/set-password/route.ts` | route | Set password on a passwordless account |

### Data layer (TanStack Query)
- `src/lib/queryClient.ts` — `getQueryClient()` returns a per-request client on the server and a browser singleton on the client. Defaults: `staleTime/gcTime: Infinity`, no refetch on focus/reconnect, `retry: 1`.
- `src/components/providers/QueryProvider.tsx` mounts the provider (devtools lazily loaded in development only).
- Query keys: `['towns']`, `['categories']`, `['profile', token]`, `['events','window'|'page'|'month', …]`, `['myEvents', token]`, `['myBusiness', token]`. Mutations + `invalidateQueries` live in `post`/`profile`/`dashboard` pages.
- **Services** (`src/services/`) talk to Django over `fetch` at `NEXT_PUBLIC_API_BASE_URL` (default `http://127.0.0.1:8000`): `eventService` (events CRUD, `BackendEvent`→`FrontendEvent` mapping), `profileService`, `businessService`. `profileService`/`businessService` use `fetchWithRetry` for Neon cold-starts.

### Auth on the frontend
Better Auth (`src/lib/auth.ts`) backed by Drizzle over the `neon_auth` schema (`src/lib/auth-schema.ts`, `src/lib/db.ts`). `useAuth.tsx` combines the Better Auth session, the Django JWT (`/api/auth/token`), and the Django profile. There is **no `middleware.ts`** — route protection is client-side in the pages.

### Design system
Tailwind CSS v4 (zero-config) with design tokens as CSS custom properties in `src/app/globals.css` (newsprint palette, Georgia serif, rule/drop-cap utilities). UI primitives in `src/components/ui/`. Full conventions in [CODING_STYLE.md](CODING_STYLE.md).

### broadcastWeb
A separate Vite + React 19 SPA (`broadcastWeb/`) for the broadcast operator console — plain `fetch` + React state (no TanStack Query), gated by the broadcast access code. See [broadcastWeb/AGENTS.md](broadcastWeb/AGENTS.md) and [docs/broadcast.md](docs/broadcast.md).

---

## Settings & Environment

**Key files:** `backend/settings/{base,dev,prod,test}.py`

Settings are split by `DJANGO_SETTINGS_MODULE`:
- `base.py` — shared: installed apps (unfold, corsheaders, DRF, the 3 local apps, `django_celery_beat`), CORS allowlist (+ custom `x-broadcast-access-code` header), `APPEND_SLASH=False`, Celery/Redis config, unfold admin.
- `dev.py` — `DEBUG=True`, parses `DATABASE_URL` (Neon dev branch), console email, `BROADCAST_AUTOSPAWN_WORKER=true` by default.
- `prod.py` — `DEBUG=False`; requires `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL`.
- `test.py` — inherits dev; strips `-pooler` from the DB host (Neon direct endpoint so the test DB can be created/dropped), eager Celery, locmem cache, stubbed external creds. See [§Testing](#testing--ci).

### Backend env vars (`backendServer/.env`)
`DATABASE_URL`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CORS_EXTRA_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `REDIS_URL` (DB 0), `REDIS_CACHE_URL` (DB 1), `GEMINI_API_KEY`, `CRON_SECRET`, `THE_COMMONS_API_KEY`, `SAFETY_SCORE_THRESHOLD` (opt), `INGEST_SHARD_COUNT` (opt), `BETTER_AUTH_JWKS_URL` / `_ISSUER` / `_AUDIENCE`, `BREVO_API_KEY`, `DIGEST_FROM_EMAIL`, `SITE_URL`, and the `BROADCAST_*` family (see [docs/broadcast.md](docs/broadcast.md)). DEPLOY.md is authoritative for production values.

### Frontend env vars (`theCommonsWeb/.env.local`)
`NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_THE_COMMONS_API_KEY`, `NEXT_PUBLIC_BETTER_AUTH_URL` (public); `DATABASE_URL`, `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL` (server-only).

### Dev mode
There is **no single "dev mode" flag or auth bypass.** Auth is never bypassed. Dev-vs-prod behavior is spread across:
- `settings/dev.py` vs `prod.py` (`DJANGO_SETTINGS_MODULE`) — `DEBUG`, console vs Brevo email, required-vs-optional env.
- `BROADCAST_AUTOSPAWN_WORKER` (default true in dev) — `submit`/`retry`/`submit-real` spawn a one-shot worker so forms process without a long-running service; prod uses the systemd worker instead.
- `settings.DEBUG` gates `broadcast.views.mock_form`; `BROADCAST_ENABLE_MOCK` adds the mock adapter to the registry.
- Frontend: only React Query Devtools (dev) and `pg` Pool HMR caching depend on `NODE_ENV`. `src/data/mockEvents.ts` exists but is unused — no mock-data toggle.

---

## Testing & CI

**Key files:** `backend/settings/test.py`, `backend/test_runner.py`, `.github/workflows/ci.yml`, `theCommonsWeb/vitest.config.ts`

### Backend
- Always run under `DJANGO_SETTINGS_MODULE=backend.settings.test` (Postgres, never SQLite). `backend.test_runner.NeonAuthTestRunner` builds the `neon_auth` schema + `user`/`account` mirror tables once (they're `managed=False`); it skips DB setup entirely on fast-only runs.
- **Two tiers** via Django `@tag`: `fast` (no-DB `SimpleTestCase`/unittest, `*_fast.py`) and `db` (Postgres `TestCase`, `*_db.py`). Helpers: `events/tests/factories.py`.
- Commands:
  ```bash
  DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test            # full
  DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test --tag=fast # no-DB tier
  DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test --tag=db   # DB tier
  ```

### Frontend
Both `theCommonsWeb/` and `broadcastWeb/` use **Vitest** with two projects: `fast` (node env, `*.fast.test.*`) and `db` (jsdom, `*.db.test.*`). Run `pnpm test`, `pnpm test:fast`, `pnpm test:db`. `pnpm build` is the type-check gate (`next build` for theCommonsWeb, `tsc -b && vite build` for broadcastWeb).

### CI (`.github/workflows/ci.yml`)
Single `CI` workflow on push/PR to `main`. Four jobs: `backend` (Postgres 16 service, uv/Python 3.13, runs `--tag=fast` then `--tag=db`), `frontend-commons` and `frontend-broadcast` (pnpm 11.1.1, Node 22, `pnpm build` + `test:fast` + `test:db`), and a gated `deploy` job (push-to-`main` only) that SSHes into the Oracle VM and restarts services. See [DEPLOY.md](DEPLOY.md) for the deploy half.

**Known gaps (as of this writing):**
- ~11 backend test files carry no `@tag` (most of `broadcast/tests/`, plus `ingestion/tests/test_pipeline.py`), so neither `--tag=fast` nor `--tag=db` runs them — they **never execute in CI** (only a bare local `manage.py test` runs them).
- No lint step in CI; `theCommonsWeb/eslint.config.js` is fully commented out; there's no ruff/mypy/prettier.
- pnpm (11.1.1) and Node (22) are pinned **only in CI**, not via `packageManager`/`.nvmrc`/`engines`.

---

## Deployment

DEPLOY.md is the source of truth — this is a summary. Production is a **single Oracle Cloud VM** (Ubuntu 24.04, ARM64, 6 GB) behind **nginx** with **Cloudflare** DNS/TLS (Full strict). Postgres is managed on **Neon** (external). systemd services: `gunicorn` (Django via unix socket), `nextjs` (Next.js :3000), `redis-server`, `celery` (worker), `celerybeat` (scheduler), `broadcast-worker` (Playwright). nginx maps `thecommons.town`→Next.js, `api.thecommons.town`→gunicorn, `broadcast.thecommons.town`→the static broadcast SPA.

Deploys are automatic: every push to `main` runs CI, and on success the gated `deploy` job SSHes in to `git pull` → `uv sync` → `migrate` (unguarded) → `collectstatic` → build both frontends → restart the five services. Python uses `uv` (never pip); frontends use `pnpm` (never npm). Full one-time setup, env vars, nginx/systemd files, firewall gotchas, and troubleshooting are in [DEPLOY.md](DEPLOY.md).
