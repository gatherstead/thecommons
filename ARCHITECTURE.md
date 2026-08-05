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

**Key files:** `accounts/models.py`, `events/models.py`, `newsletter/models.py`, `ingestion/models.py`, `broadcast/models.py`

### `accounts` app — identity / auth-bridge

`accounts` owns the Better Auth mirrors and every profile that hangs off a user — a
"business" is modeled as a kind of user profile, not a separate app.

| Model | Key fields | Relationships |
|-------|-----------|---------------|
| `UserProfile` | `uuid`, `user_type` (LOCAL/BUSINESS/VENUE), `primary_city`, `address`, `email_preference` (WEEKLY/MONTHLY/NEVER) | OneToOne→`BetterAuthUser` (`db_constraint=False`); M2M→`events.Tag`. `db_table="events_userprofile"` (unchanged — model moved app, table didn't) |
| `BusinessProfile` | `uuid`, `business_name`, `description`, `contact_email/phone`, `is_published`, timestamps | OneToOne→`BetterAuthUser`; M2M→`events.Tag`; M2M→`events.Town` (`service_area`). `db_table="events_businessprofile"` |

#### Better Auth mirrors — `neon_auth` schema (`managed = False`)

Better Auth (Next.js) owns these tables; Django maps them **read-only** for joins. **Never create migrations for them.** Models: `BetterAuthUser`, `BetterAuthSession`, `BetterAuthAccount`, `BetterAuthVerification`, `BetterAuthJwks` — all in `accounts.models`.

- The `db_table` values use a double-quote trick (e.g. `'neon_auth"."user'`) so Django emits a valid cross-schema reference `FROM "neon_auth"."user"`.
- `BetterAuthUser` hardcodes `is_authenticated=True` / `is_anonymous=False` so DRF permission classes treat it as a real user.
- FKs into these mirrors use `db_constraint=False` (no DB-level FK against unmanaged tables).

### `events` app — `public` schema (managed, slimmed)

`events` now owns only the genuine event/taxonomy models; profile and newsletter models
moved to `accounts`/`newsletter` respectively (state-only migrations — see below).

| Model | Key fields | Relationships |
|-------|-----------|---------------|
| `Tag` | `name` (unique) | M2M from users/businesses/events |
| `Town` | `slug` (unique), `name` | FK target of `Event.town` |
| `Event` | `uuid` (PK), `title`, `date` (indexed), `venue`, `description`, `price`, `photo`, `link`, `is_verified`, `source_name` | FK→`Town` (SET_NULL); M2M→`Tag`; FK→`accounts.BetterAuthUser` (`created_by`) |

### `newsletter` app — `public` schema (managed)

| Model | Key fields | Relationships |
|-------|-----------|---------------|
| `NewsletterSubscriber` | `email` (unique), `frequency`, `is_active`, `manage_token` (UUID, unique — unguessable credential for the manage link), `subscribed_at` | — . `db_table="events_newslettersubscriber"` (unchanged) |

There is a deliberate `accounts ↔ newsletter` coupling, not a boundary bug: `accounts.me`
writes a `NewsletterSubscriber` row (email-preference sync) and
`newsletter._build_recipients` reads `accounts.UserProfile` (tag-filtered digests). Both
directions are intentional and covered by each app's `test_isolation_fast.py` (which forbid
reaching into `ingestion`/`broadcast`, not into each other or `events`). That guard covers
`accounts` and `newsletter` only — `events` has no isolation test and does import
`ingestion.models.StagedEvent` for the user-submission endpoints (see
[`backendServer/AGENTS.md`](backendServer/AGENTS.md)).

### Migration mechanics for the model moves

All three moves (`UserProfile`/`BusinessProfile` → `accounts`, `NewsletterSubscriber` →
`newsletter`) used `migrations.SeparateDatabaseAndState` with `db_table` preserved
(`events_userprofile`, `events_businessprofile`, `events_newslettersubscriber`) — state-only,
zero physical DDL. The `neon_auth.*` mirrors were never migrated (still `managed=False`).
A companion data migration (`newsletter/migrations/0002_repoint_digest_beat.py`) repoints the
existing `django_celery_beat` `PeriodicTask` rows from `events.tasks.fan_out_*_digest` to
`newsletter.tasks.fan_out_*_digest`.

### `ingestion` app — `public` schema (managed)

| Model | Key fields | Relationships |
|-------|-----------|---------------|
| `EventSource` | `name`, `source_type` (ics/scraper/email/**direct**), `url`, `active`, `last_polled`, `poll_interval_hours` | reverse `raw_events` |
| `RawEvent` | raw title/description/location, raw start/end, `source_url`, `source_uid`, `processed` | FK→`EventSource`; `unique_together=(source, source_uid)` |
| `StagedEvent` | LLM fields (title, description, location, town, datetimes, tags JSON, price, link), `status` (pending/approved/rejected/duplicate), `safety_score/notes`, `reviewer_notes` | OneToOne→`RawEvent`; self-FK `duplicate_of`; FK→`events.Event` (`published_event`); FK→`accounts.BetterAuthUser` (`submitted_by`) |

### `broadcast` app — `public` schema (managed)

| Model | Key fields | Relationships |
|-------|-----------|---------------|
| `BroadcastSubmission` | `uuid` (PK), `client_label`, denormalized event fields (title, datetimes, venue/address, locality JSON, categories JSON, urls, price, organizer, contacts), `status` (queued/running/done/failed/canceled), timestamps | reverse `targets` |
| `BroadcastTarget` | `uuid` (PK), `site_key`, `status` (pending/in_progress/succeeded/failed/needs_manual/skipped), `attempts`, `external_url`, `error`, `screenshot_path`, `dry_run`, timestamps | FK→`BroadcastSubmission`; `UniqueConstraint(submission, site_key)` |
| `BroadcastAccess` | `email` (unique, lowercased), `tier` (0/1/2, default 0), timestamps | — |
| `AccessCode` | `code_hash` (SHA-256 hex; raw shown once at generation, never stored), `label`, `tier` (default 2), `max_uses` (null=unlimited, default 3), `is_active`, `expires_at`, timestamps | reverse `uses` |
| `AccessCodeUse` | `draft_id`, timestamps | FK→`AccessCode` (`related_name="uses"`); `unique_together(access_code, draft_id)` |

### Database ownership

| Schema | Owner | Django access |
|--------|-------|---------------|
| `public` | Django migrations | Full read/write |
| `neon_auth` | Better Auth (Next.js) | Read-only mirrors (`managed = False`) — never migrate |

---

## API Endpoints

**Key files:** `backend/urls.py`, `accounts/urls.py`, `events/urls.py`, `newsletter/urls.py`, `ingestion/urls.py`, `broadcast/urls.py`

Notes that apply throughout:
- **`APPEND_SLASH=False`** — trailing slashes are matched exactly as written below.
- **No global DRF config.** Each view sets its own `@authentication_classes` / `@permission_classes` (house pattern).
- Auth column: `—` = public, `user` = Better Auth JWT, `API key` = `THE_COMMONS_API_KEY`, `tier≥N` = broadcast tier (Bearer JWT or `X-Broadcast-Access-Code`, resolved by `broadcast/access.py`).
- **`backend/urls.py` is `include()`-only** — it delegates to each app's own urlconf (`accounts.urls`, `events.urls`, `newsletter.urls`, `ingestion.urls`, `broadcast.urls`, plus `admin.site.urls` and, when `DEBUG`, `devtools.urls`). There is no `from <app>.views import ...` in the kernel; the tables below are grouped by the app that actually owns the route.

### accounts (`accounts/urls.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET/PATCH | `/auth/me` | user | Read / update own profile |
| GET/POST | `/businesses` | user | Browse published businesses / create a listing |
| GET | `/businesses/me` | user | Own business listing |
| GET/PATCH/DELETE | `/businesses/<uuid>` | user | Business listing CRUD |

### newsletter (`newsletter/urls.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/newsletter/subscribe` | — | Newsletter signup (`{email, frequency}`); sends a welcome email with a manage link |
| GET/PATCH | `/newsletter/manage` | — (token) | Manage a subscription via `?token=<manage_token>` — GET returns `{email, frequency, is_active}`; PATCH body `{frequency: WEEKLY\|MONTHLY\|NEVER}` (`NEVER` sets `is_active=false`) |

### ingestion (`ingestion/urls.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/cron/ingest` | `CRON_SECRET` | Queue the ingestion pipeline (Celery) |
| POST | `/api/events/publish-approved` | API key | Queue bulk publish of approved staged events |
| POST | `/api/events/direct-submit` | JWT optional (anonymous allowed) | Direct host event submission — fire-and-forget from broadcast SPA; 10/m by IP; invalid token → 401 |
| GET/POST | `/admin/docs/...` | staff | Pipeline/admin docs pages + publish-approved button |

### admin

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| — | `/admin/` | staff | Django admin (django-unfold) |

### Events (`/events/`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/events/` | — | Paginated published events (window/after/before/tag/town filters, Redis-cached) |
| GET | `/events/towns/` | — | Town list (cached) |
| GET | `/events/me/profile` | user | Own profile summary |
| GET | `/events/me/events` | user | Own staged + published events |
| GET/PATCH/DELETE | `/events/staged/<int>` | user | Manage own staged submission |
| GET/DELETE | `/events/<uuid>` | user (delete) | Event detail / owner delete |
| POST | `/events/create` | user or API key | Submit an event → `StagedEvent` |

### Broadcast (`/broadcast/`)

Auth via Bearer JWT or `X-Broadcast-Access-Code` header, resolved to a tier by `broadcast/access.py`. Tier ≥ 1 required for most endpoints; tier ≥ 2 for ai-autofill. See [docs/broadcast.md §Access control](docs/broadcast.md#access-control) for the full tier table.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/broadcast/access` | open | Caller's tier + trial metadata |
| POST | `/broadcast/preview` | tier ≥ 1 | Compute eligible/excluded target sites for an event; meters trial use |
| POST | `/broadcast/ai-autofill` | tier ≥ 2 | LLM-extract event fields from pasted text |
| POST | `/broadcast/direct-recipe` | tier ≥ 1 | Recipe JSON for a site from event data — no job required |
| POST | `/broadcast/submit` | tier ≥ 1 | Create submission + targets, enqueue |
| GET | `/broadcast/jobs/<uuid>` | tier ≥ 1 | Job status + per-target detail |
| POST | `/broadcast/jobs/<uuid>/retry` | tier ≥ 1 | Re-queue selected targets |
| POST | `/broadcast/jobs/<uuid>/submit-real` | tier ≥ 1 | Promote dry-run targets to real |
| POST | `/broadcast/jobs/<uuid>/cancel` | tier ≥ 1 | Cancel job, skip pending |
| GET | `/broadcast/jobs/<uuid>/screenshots/<site_key>` | tier ≥ 1 | Serve gated screenshot PNG |
| GET | `/broadcast/jobs/<uuid>/manual/<site_key>` | tier ≥ 1 | Recipe JSON for a `needs_manual` target |
| GET | `/broadcast/mock-form` | — (`DEBUG` only) | Dev-only mock submission form |

> Login/signup/logout are handled by Better Auth in **Next.js** at `/api/auth/*` (standard `emailAndPassword` sign-up/sign-in, fronted by the portal).

---

## Authentication

**Key files:** `backend/jwt_auth.py`, `backend/permissions.py`, `accounts/models.py`, `src/lib/auth.ts`, `src/lib/redirect-allowlist.ts`, `src/hooks/useAuth.tsx`, `src/app/(portal)/`, `src/components/layout/SiteChrome.tsx`

Auth is owned by **Better Auth running inside Next.js**, fronted by a standalone **portal** — there are no Django login/signup endpoints, and no app renders its own embedded auth form anymore. Django only *verifies* tokens.

### Auth-origin topology

Better Auth — and the portal UI in front of it — is served at **`https://auth.thecommons.town`** (reverse-proxied by nginx on the shared VM; still physically the Next.js app, same `theCommonsWeb` codebase). In dev the portal is unproxied, at `localhost:3000` (same origin as the rest of the app). A **shared cookie domain `.thecommons.town`** (`BETTER_AUTH_COOKIE_DOMAIN=.thecommons.town`, `SameSite=None; Secure`, wired via `crossSubDomainCookies` in `src/lib/auth.ts` — active only when `BETTER_AUTH_COOKIE_DOMAIN` is set) lets one session span the apex app, `auth.`, and `broadcast.thecommons.town`. Every client points its Better Auth client at `BETTER_AUTH_URL` / `VITE_BETTER_AUTH_URL` = `https://auth.thecommons.town`. Django's `BETTER_AUTH_JWKS_URL` also points at this origin. `trustedOrigins` in `src/lib/auth.ts` lists apex, www, broadcast subdomain, localhost:3000, localhost:5173, and any `BETTER_AUTH_TRUSTED_ORIGINS` env additions.

### The portal

The portal is a route group, `src/app/(portal)/`, inside the same Next.js app — not a separate service. Routes: `/signin`, `/join` (create account: email + password + confirm, one step), `/forgot-password`. `PortalShell` (`src/app/(portal)/PortalShell.tsx`) renders standalone split-panel chrome with a SIGN IN / CREATE ACCOUNT tab switcher; a client gate, `src/components/layout/SiteChrome.tsx` (checks `usePathname()` against the portal paths), hides the apex `Header`/`Footer`/banners on those routes so the portal has its own chrome, while every other route is unchanged.

Every service that needs a user to authenticate redirects into the portal with `?redirect_to=<absolute URL>`. `src/lib/redirect-allowlist.ts` exports `resolveRedirect(raw, fallback='/')`, which validates the destination against an allowlist (`thecommons.town`, `*.thecommons.town`, `localhost`/`127.0.0.1` in dev) as an open-redirect guard; the portal completes sign-in with `window.location.href = resolveRedirect(...)` — a full cross-subdomain navigation, not a client-side route change. The apex app's own former embedded flow (`src/app/auth/AuthFlow.tsx`, `src/app/auth/google-popup/`) was removed; `/auth`, `/auth/login`, `/auth/signup` are now thin server-redirect shims that map the old `?redirect=`/`?intent=` params to an absolute `redirect_to` and bounce into the portal. In-app "Sign in"/"Sign up" entry points (Header, sidebar, post gate, digest CTA) navigate straight to the portal. `broadcastWeb` does the same: its former inline `AuthModal` was removed, and its "Sign in / Create account" button does a full navigation to `${VITE_BETTER_AUTH_URL}/signin?redirect_to=<current broadcast URL>` — the shared session brings the user back.

### The bridge
- Browser authenticates with Better Auth and holds a session cookie.
- To call Django, the frontend fetches a short-lived **JWT** from `/api/auth/token` (Better Auth `jwt()` plugin) and sends it as `Authorization: Bearer <jwt>`. JWT payload carries the `email` claim by default (`sub` = user id).
- `BearerTokenAuthentication` accepts either:
  1. a **Better Auth JWT** verified statelessly against the JWKS endpoint (`BETTER_AUTH_JWKS_URL`); `sub` resolves to a `BetterAuthUser` (now in `accounts.models` — `backend/permissions.py` imports it from there, not `events.models`). The JWKS client is cached in-process with a TTL and **stale-grace** fallback so brief Next.js outages don't cascade. In `broadcast/`, `verify_better_auth_jwt` is called directly — no `BetterAuthUser` ORM lookup (isolation preserved).
  2. the shared **`THE_COMMONS_API_KEY`** (no user attached) — for app-level calls like event creation.
- Permission classes live in `backend/permissions.py` and are applied per-view alongside DRF's `IsAuthenticated`.

### User-creation side effect
`src/lib/auth.ts` defines `databaseHooks.user.create.after`, which inserts a matching `public.events_userprofile` row whenever Better Auth creates a user — so every account has a Django profile. The table name is a historical artifact: the `UserProfile` model now lives in `accounts/models.py`, but its `db_table` was pinned to `events_userprofile` by a state-only migration, so the physical table (and this INSERT) is unchanged.

### Account creation is password-required
Signup collects **email + password + confirm** in one step on `/join`, via Better Auth's standard `emailAndPassword` flow (`autoSignIn: true` in `src/lib/auth.ts`) — `signUp.email` creates the Better Auth user + `credential` account and signs the user in immediately; the `databaseHook` fires as usual. There is no passwordless/email-only path and no separate set-password step. **No email verification for MVP.**

### Google sign-in — DISABLED
Commented out in `src/lib/auth.ts`. The client popup flow that used to live at `src/app/auth/google-popup/` was removed along with the rest of the pre-portal embedded auth UI; re-enabling Google sign-in needs a new post-OAuth account-type step built into the portal. Revisit later.

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

Manual entrypoints: `POST /api/cron/ingest` (`CRON_SECRET`) queues the pipeline; `POST /api/events/publish-approved` (API key) and the admin docs page queue `publish_all_approved_task`. Public/auth users submit via `POST /events/create`, which creates a pending `StagedEvent` directly (skipping poll/standardize). **Hosts submit via `POST /api/events/direct-submit`** (Bearer JWT optional; anonymous accepted; invalid token → 401; 10/m by IP) — the broadcast SPA fires this fire-and-forget alongside every preview; it upserts a `RawEvent` keyed by `draft_id` (idempotent re-edits), runs the same standardize/score/publish pipeline, and retains the `StagedEvent` row for the edit chain. Valid JWT → `submitted_by` attributed; no JWT → `submitted_by=None`. Bridge code lives in `ingestion/`; `broadcast/` imports nothing from `ingestion/` (`test_isolation.py` enforces this). Unknown `Town` slugs cause an event to be skipped at publish time. Threshold is `SAFETY_SCORE_THRESHOLD` (default 0.3). See [docs/ingestion-pipeline.md](docs/ingestion-pipeline.md) and [docs/safety-scoring.md](docs/safety-scoring.md).

---

## Broadcast

**Key files:** `broadcast/services.py`, `broadcast/worker.py`, `broadcast/runner.py`, `broadcast/routing.py`, `broadcast/adapters/`

The broadcast subsystem pushes a single event out to multiple third-party community calendars via headless Playwright form-filling. It is deliberately **isolated** from `events/` (its `routing.py` must not import from `events`) and does **not** use Celery — it runs its own DB-backed queue worker.

Flow: tier-based auth (Bearer JWT or access code, resolved by `broadcast/access.py`) → `preview` (build a `CanonicalEvent`, match adapters via `routing.eligible_targets`) → `submit` (create `BroadcastSubmission` + `BroadcastTarget`s) → `run_broadcast_worker` claims the job (`SELECT FOR UPDATE SKIP LOCKED`) → `runner.py` drives one Chromium session per target (no ORM inside `sync_playwright`) → per-site adapters fill and submit.

**[docs/broadcast.md](docs/broadcast.md) is the single source of truth** for models, adapters, access codes, env vars, commands, and the manual-review handoff.

---

## Async: Redis + Celery

**Key files:** `backend/celery.py`, `backend/__init__.py`, `newsletter/tasks.py`, `events/tasks.py`, `ingestion/tasks.py`, `events/cache.py`, `events/signals.py`

- **One Redis instance, two logical DBs:** DB 0 = Celery broker **and** result backend (`REDIS_URL`); DB 1 = Django cache (`RedisCache`, `REDIS_CACHE_URL`).
- **Celery** app is built in `backend/celery.py`, loaded eagerly via `backend/__init__.py`, and autodiscovers tasks. `CELERY_TIMEZONE = UTC` (beat entries carry their own tz).
- **Beat** uses `django_celery_beat`'s `DatabaseScheduler` — schedules live in Postgres and are editable in admin. Seeded by migrations, then repointed by a data migration when the digest engine moved apps:
  - `weekly-digest-sunday` → `newsletter.tasks.fan_out_weekly_digest`, Sun 18:00 America/New_York (seeded by `events/migrations/0015_seed_digest_beat.py`; repointed from `events.tasks.fan_out_weekly_digest` by `newsletter/migrations/0002_repoint_digest_beat.py`).
  - `monthly-digest` → `newsletter.tasks.fan_out_monthly_digest`, 1st of month 18:00 America/New_York (seeded by `events/migrations/0020_seed_monthly_digest_beat.py`; repointed by the same `0002_repoint_digest_beat.py`).
  - `ingest-events-daily` → `ingestion.tasks.run_ingestion_pipeline`, 04:00 America/New_York (`ingestion/migrations/0007_seed_ingest_beat.py`).
- **Tasks:** `newsletter.tasks` (`send_one_digest`, `fan_out_weekly_digest`, `fan_out_monthly_digest`), `events.tasks` (`ping`), `ingestion.tasks` (`run_ingestion_pipeline`, `publish_all_approved_task`).
- **Read-endpoint cache:** `events/cache.py` is a version-keyed Redis cache for the hot list endpoints; `events/signals.py` bumps the version on `Event`/`Town` writes to invalidate.

See [docs/redis-celery-handoff.md](docs/redis-celery-handoff.md).

### Email digests
`newsletter/email_service.py` wraps **Brevo** (via the generic transport, `events/email_service.py::send_email`) and builds digest HTML from `newsletter/templates/email/`. `NewsletterSubscriber` (`newsletter` app) is the single source of truth for both weekly and monthly digests: `_build_recipients(frequency)` resolves the recipient list (deduped by email) from active subscriber rows — anonymous newsletter subscribers get all events, account holders (`accounts.UserProfile.email_preference`) are tag-filtered — and returns `{email, tags, manage_token}` per recipient. This one resolver backs both the Celery path (`newsletter.tasks.fan_out_weekly_digest` / `fan_out_monthly_digest` queue one `send_one_digest` per recipient) and the synchronous `send_digest`/`send_weekly_digest` management commands in `newsletter/management/commands/` (`send_test_digest` sends a one-off test). Every digest email carries a "Manage preferences / Unsubscribe" link built from the recipient's `manage_token` (`/newsletter/manage?token=`). `events/email_service.py::send_email` remains the generic Brevo wrapper used by non-digest commands — it did not move.

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
| `/auth`, `/auth/login`, `/auth/signup` | `app/auth/{page,login/page,signup/page}.tsx` | server redirect shim | Legacy entry points — map old `?redirect=`/`?intent=` to `redirect_to` and bounce into the portal (`/join` or `/signin`) |
| `/signin` | `app/(portal)/signin/page.tsx` | client (`PortalShell` + `SignInForm`) | Portal sign-in |
| `/join` | `app/(portal)/join/page.tsx` | client (`PortalShell` + `JoinForm`) | Portal create-account (email + password + confirm) |
| `/forgot-password` | `app/(portal)/forgot-password/page.tsx` | client | Password reset request |
| `/events/[uuid]` | `app/events/[uuid]/page.tsx` | server (async) | Event detail (`generateMetadata` + OpenGraph) |
| `/api/auth/[...all]` | `app/api/auth/[...all]/route.ts` | route | Better Auth handler |

`/auth/google-popup/` (the disabled Google OAuth popup) was removed along with the rest of the pre-portal embedded auth UI — see [§Authentication](#authentication).

### Data layer (TanStack Query)
- `src/lib/queryClient.ts` — `getQueryClient()` returns a per-request client on the server and a browser singleton on the client. Defaults: `staleTime/gcTime: Infinity`, no refetch on focus/reconnect, `retry: 1`.
- `src/components/providers/QueryProvider.tsx` mounts the provider (devtools lazily loaded in development only).
- Query keys: `['towns']`, `['profile', token]`, `['events','window'|'page'|'month', …]`, `['myEvents', token]`, `['myBusiness', token]`. Mutations + `invalidateQueries` live in `post`/`profile`/`dashboard` pages.
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
- `base.py` — shared: installed apps (unfold, corsheaders, DRF, the 5 local apps — `accounts`, `events`, `newsletter`, `ingestion`, `broadcast`; `devtools` is added by `dev.py` only — `django_celery_beat`), CORS allowlist (+ custom `x-broadcast-access-code` header), `APPEND_SLASH=False`, Celery/Redis config, unfold admin.
- `dev.py` — `DEBUG=True`, parses `DATABASE_URL` (Neon dev branch), console email, `BROADCAST_AUTOSPAWN_WORKER=true` by default.
- `prod.py` — `DEBUG=False`; requires `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL`.
- `test.py` — inherits dev; strips `-pooler` from the DB host (Neon direct endpoint so the test DB can be created/dropped), eager Celery, locmem cache, stubbed external creds. See [§Testing](#testing--ci).

### Backend env vars (`backendServer/.env`)
`DATABASE_URL`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CORS_EXTRA_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `REDIS_URL` (DB 0), `REDIS_CACHE_URL` (DB 1), `GEMINI_API_KEY`, `CRON_SECRET`, `THE_COMMONS_API_KEY`, `SAFETY_SCORE_THRESHOLD` (opt), `INGEST_SHARD_COUNT` (opt), `BETTER_AUTH_JWKS_URL` (points at `https://auth.thecommons.town/api/auth/jwks` in prod) / `_ISSUER` / `_AUDIENCE`, `BREVO_API_KEY`, `DIGEST_FROM_EMAIL`, `SITE_URL`, and the `BROADCAST_*` family (see [docs/broadcast.md](docs/broadcast.md); access codes are now DB-only — no env code list). DEPLOY.md is authoritative for production values.

### Frontend env vars (`theCommonsWeb/.env.local`)
`NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_THE_COMMONS_API_KEY`, `NEXT_PUBLIC_BETTER_AUTH_URL`, `BETTER_AUTH_TRUSTED_ORIGINS` (opt, comma-separated extra origins), `BETTER_AUTH_COOKIE_DOMAIN` (prod: `.thecommons.town` — enables cross-subdomain sessions) (public); `DATABASE_URL`, `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL` (server-only — prod: `https://auth.thecommons.town`).

### Broadcast SPA env vars (`broadcastWeb/.env`)
`VITE_BROADCAST_API_BASE_URL`, `VITE_BROADCAST_EXTENSION_ID`, `VITE_BETTER_AUTH_URL` (prod: `https://auth.thecommons.town`).

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
- (Resolved) Untagged backend test files that never ran in CI: `broadcast/tests/` and `ingestion/tests/test_pipeline.py` (now `test_pipeline_db.py`) all carry `@tag('fast')`/`@tag('db')` and run in CI.
- No lint step in CI; `theCommonsWeb/eslint.config.js` is fully commented out; there's no ruff/mypy/prettier.
- pnpm (11.1.1) and Node (22) are pinned **only in CI**, not via `packageManager`/`.nvmrc`/`engines`.

---

## Deployment

DEPLOY.md is the source of truth — this is a summary. Production is a **single Oracle Cloud VM** (Ubuntu 24.04, ARM64, 6 GB) behind **nginx** with **Cloudflare** DNS/TLS (Full strict). Postgres is managed on **Neon** (external). systemd services: `gunicorn` (Django via unix socket), `nextjs` (Next.js :3000), `redis-server`, `celery` (worker), `celerybeat` (scheduler), `broadcast-worker` (Playwright). nginx maps `thecommons.town`→Next.js, `api.thecommons.town`→gunicorn, `broadcast.thecommons.town`→the static broadcast SPA.

Deploys are automatic: every push to `main` runs CI, and on success the gated `deploy` job SSHes in to `git pull` → `uv sync` → guarded `migrate` (skips when nothing is pending; a pre-migrate `pg_dump` backup precedes any apply) → `collectstatic` → build both frontends → restart the five services, then a post-deploy smoke test (three domains, `/events/`, auth probes, broadcast rate-limit regression). Python uses `uv` (never pip); frontends use `pnpm` (never npm). Full one-time setup, env vars, nginx/systemd files, firewall gotchas, and troubleshooting are in [DEPLOY.md](DEPLOY.md).
