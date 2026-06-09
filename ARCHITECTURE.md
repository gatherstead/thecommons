# Architecture

## Overview

The Commons is a local community events aggregator for small towns in North Carolina (initially Chapel Hill / Carrboro area). It is a monorepo with two sub-projects:

```
thecommons/
├── backendServer/   # Django 6 REST API + admin + ingestion pipeline
└── theCommonsWeb/   # Next.js 16 (App Router) + React 19 — public site + Better Auth
```

Both run on a single Oracle Cloud VM behind nginx; see [Deployment](#deployment). The database is managed Postgres on **Neon**, shared by both sub-projects: Django reads/writes the application tables, and Better Auth (in Next.js) owns the auth tables in a separate `neon_auth` schema.

---

## Backend (`backendServer/`)

**Stack:** Python 3.13 · Django 6 · Django REST Framework · PostgreSQL on Neon (psycopg3) · Google Gemini (LLM) · django-unfold (admin UI) · Brevo (email)

### Django Apps

| App | Responsibility |
|-----|---------------|
| `events` | Published events, tags, towns, categories, user profiles, newsletter, profile/me endpoints, email digests |
| `ingestion` | Ingestion pipeline: event sources, raw events, staged events, LLM standardization, safety scoring, admin review workflow |

### Data Models

#### `events` app — application data
- **`Town`** — `slug` + `name` (e.g. `carrboro` / `Carrboro`).
- **`Tag`** — unique string labels.
- **`Category`** — `slug` + `display_name`; distinct from `Tag`.
- **`Event`** — UUID PK · title · town (FK, nullable) · date (indexed) · venue · description · price · photo · `tags` (M2M) · `categories` (M2M) · link · `is_verified` · `source_name` · `created_by` (FK → `BetterAuthUser`, null for pipeline-ingested events).
- **`UserProfile`** — OneToOne with **`BetterAuthUser`** (not Django's `auth.User`) · `user_type` (LOCAL/BUSINESS/VENUE) · `primary_city` · `address` · `email_preference` (WEEKLY/MONTHLY/NEVER) · `tags` (M2M). Created automatically when Better Auth creates a user (see [Authentication](#authentication)).
- **`BusinessProfile`** — OneToOne with **`BetterAuthUser`** · UUID · `business_name` · `description` · `tags` (M2M Tag) · `service_area` (M2M Town) · `contact_email` · `contact_phone` · `is_published` · timestamps.
- **`NewsletterSubscriber`** — `email` · `frequency` (WEEKLY/MONTHLY) · `is_active` · `subscribed_at`. For non-account digest subscribers.

#### Better Auth mirror models — `neon_auth` schema, **`managed = False`**
Better Auth (Next.js) owns these tables; Django maps them read-only for joins and lookups. **Never create migrations for them.**
- **`BetterAuthUser`** (`neon_auth.user`) — UUID id · name · email · `user_type` · timestamps. Sets `is_authenticated = True` so DRF permission classes accept it as the request user.
- **`BetterAuthSession`**, **`BetterAuthAccount`**, **`BetterAuthVerification`**, **`BetterAuthJwks`** — the rest of the Better Auth table set.

> The `db_table` values use a deliberate double-quote trick (e.g. `'neon_auth"."user'`) so Django emits a valid cross-schema reference `FROM "neon_auth"."user"`.

#### `ingestion` app
- **`EventSource`** — URL we poll on a schedule; source_type ∈ {ics, scraper, email}.
- **`RawEvent`** — event as scraped, before LLM processing; unique on (source, source_uid).
- **`StagedEvent`** — LLM-standardized version awaiting admin review; status ∈ {pending, approved, rejected, duplicate}.

### Authentication

**Key files:** `backend/jwt_auth.py`, `backend/permissions.py`, `src/lib/auth.ts`, `src/lib/lazy-auth-plugin.ts`, `src/hooks/useAuth.tsx`, `src/app/api/auth/set-password/route.ts`

Auth is owned by **Better Auth running inside Next.js** — there are no Django login/signup endpoints. Django only *verifies* tokens Better Auth issues.

**The bridge (`backend/jwt_auth.py` + `backend/permissions.py`):**

- The browser authenticates with Better Auth and holds a session cookie. To call Django, the frontend fetches a short-lived **JWT** from `/api/auth/token` (Better Auth `jwt()` plugin) and sends it as `Authorization: Bearer <jwt>`.
- `BearerTokenAuthentication` accepts either:
  1. a **Better Auth JWT**, verified statelessly against the frontend's JWKS endpoint (`BETTER_AUTH_JWKS_URL`). The `sub` claim is resolved to a `BetterAuthUser`. The JWKS client is cached in-process (10-min TTL) with a stale-grace window so a brief Next.js outage doesn't cascade into Django auth.
  2. the shared **`THE_COMMONS_API_KEY`** (no user attached) — for app-level calls like event creation.
- Permissions: `HasCommonsAPIKey` (key only), `HasCommonsAPIKeyOrUser` (authenticated user *or* shared key), plus DRF's `IsAuthenticated` for user-only endpoints.

**User creation side effect:** `src/lib/auth.ts` defines a `databaseHooks.user.create.after` that inserts a matching `events_userprofile` row when Better Auth creates a user, so every account has a Django profile.

**Lazy (passwordless) accounts.** Signup is email-first and password-optional. A custom Better Auth plugin (`src/lib/lazy-auth-plugin.ts`, registered in `auth.ts`) exposes `POST /api/auth/enter`:

- New email → creates a Better Auth user (no credential account) and a session via the internal adapter, returns `{ isNew: true }`. The `databaseHook` still fires, so the Django profile is created.
- Existing passwordless email → issues a fresh session, returns `{ isNew: false, requiresPassword: false }`.
- Existing email that *has set a password* → returns `{ requiresPassword: true }` (no session); the frontend then collects the password and uses the normal `signIn.email` flow.

A user can secure their account later via `POST /api/auth/set-password` (`src/app/api/auth/set-password/route.ts`), which calls Better Auth's `auth.api.setPassword` to link a `credential` account. There's no email verification for MVP — anyone can claim any unclaimed email (see the ticket's risk notes).

**`has_password` is derived, not stored.** Django computes it from the `BetterAuthAccount` mirror (`provider_id='credential'` with a non-null password) and returns it on `/auth/me` and `/events/me/profile`. The frontend uses it to drive security nudges (a banner when an account has no password; a red dot for incomplete business/venue profiles). No new column or migration.

### Ingestion Pipeline

**Key files:** `ingestion/services.py`, `ingestion/standardizer.py`, `ingestion/safety_scorer.py`, `ingestion/deduplicator.py`, `ingestion/importers/ics_importer.py`

```
EventSource (URL/feed)
    ↓  importers (ICS, scraper)
RawEvent  ←  deduplicator.py
    ↓  standardizer.py (Gemini LLM)  +  safety_scorer.py
StagedEvent  ←  admin reviews in django-unfold
    ↓  services.publish_all_approved()
Event (canonical, public)
```

Triggered via `POST /api/cron/ingest` (requires `CRON_SECRET` header) or the `python manage.py ingest_events` command. Publishing approved events is done from the admin UI or via `POST /api/events/publish-approved`. `safety_scorer.py` flags low-quality/unsafe events against `SAFETY_SCORE_THRESHOLD`.

### API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/events/` | — | List published events (excludes past by default; `?after=`, `?before=`, `?include_past=true`) |
| GET | `/events/towns/` | — | List all towns |
| GET | `/events/categories/` | — | List all categories |
| GET | `/events/{uuid}` | — | Single event detail |
| DELETE | `/events/{uuid}` | user | Delete a published event you own |
| POST | `/events/create` | user **or** API key | Submit a new event |
| GET | `/events/me/profile` | user | Current user's profile (auth bootstrap); includes derived `has_password` |
| GET | `/events/me/events` | user | Events submitted by the current user |
| GET/PATCH/DELETE | `/events/staged/{id}` | user | Manage one of your staged submissions |
| GET/PATCH | `/auth/me` | user | Read / update the current user's profile (response includes derived `has_password`) |
| POST | `/auth/subscribe` | — | Subscribe an email to the newsletter |
| GET/POST | `/businesses` | user | List all published businesses / create a business profile |
| GET | `/businesses/me` | user | Current user's business profile |
| GET/PATCH/DELETE | `/businesses/{uuid}` | user | Read / update / delete a business profile |
| POST | `/api/cron/ingest` | `CRON_SECRET` | Trigger ingestion pipeline (scheduled) |
| POST | `/api/events/publish-approved` | API key | Publish all approved staged events |

> Login/signup/logout are handled by Better Auth in Next.js at `/api/auth/*` — including the lazy `POST /api/auth/enter` and `POST /api/auth/set-password` (see [Authentication](#authentication)).

Admin lives at `/admin/` (django-unfold). Pipeline and admin docs render as Django template pages under `/admin/docs/`. (Login/signup/logout are handled by Better Auth in Next.js at `/api/auth/*`, not here.)

### Email Digests

`events/email_service.py` wraps **Brevo** transactional email. Management commands:
- `send_weekly_digest` — personalized per WEEKLY subscriber (their town + tag interests). HTML from `templates/email/weekly_digest.html`.
- `send_digest --frequency WEEKLY|MONTHLY` — batch digest.
- `send_test_digest --email <addr>` — render + send one test digest.

These are scheduled via cron on the VM (see [Deployment](#deployment)).

### Other Management Commands

- `delete_user` — delete a user and cascade associated data.
- `ingest_events` — run the full ingestion pipeline (also triggered via cron endpoint).
- `cleanup_old_events` — remove expired events.

### Environment Variables (`backendServer/.env`)

```
DATABASE_URL=                # Neon Postgres connection string
DJANGO_SECRET_KEY=
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=        # comma-separated
CORS_EXTRA_ORIGINS=          # comma-separated, appended to defaults
CSRF_TRUSTED_ORIGINS=        # comma-separated, HTTPS origins for admin/POST
GEMINI_API_KEY=
CRON_SECRET=
THE_COMMONS_API_KEY=
SAFETY_SCORE_THRESHOLD=0.3
# Better Auth bridge — Django verifies JWTs issued by Next.js
BETTER_AUTH_JWKS_URL=        # e.g. http://localhost:3000/api/auth/jwks (prod: the frontend origin)
BETTER_AUTH_ISSUER=
BETTER_AUTH_AUDIENCE=
# Brevo (email digests)
BREVO_API_KEY=
DIGEST_FROM_EMAIL=digest@thecommons.town
SITE_URL=https://thecommons.town
```

### Running Locally

```bash
cd backendServer
uv sync
python manage.py migrate
python manage.py runserver       # http://localhost:8000
```

For end-to-end auth, also run the frontend so `BETTER_AUTH_JWKS_URL` resolves.

---

## Frontend (`theCommonsWeb/`)

**Stack:** Next.js 16 (App Router + Turbopack) · React 19 · TypeScript · Tailwind CSS v4 · Better Auth (`better-auth` + Drizzle + `pg`)

### Key Source Directories

```
src/
├── app/
│   ├── layout.tsx            # Root layout (server component): AuthProvider, Header, Footer
│   ├── page.tsx              # Home (client): feed/calendar views, modals
│   ├── about/page.tsx        # About (server component, SEO metadata)
│   ├── dashboard/page.tsx    # Manage your submitted events (client)
│   ├── profile/page.tsx      # View/edit your profile + Security (set-password) section (client)
│   ├── auth/page.tsx         # Lazy signup/login flow: user type → preferences → email (client)
│   ├── auth/google-popup/    # Google OAuth popup flow (page + complete page) — DISABLED, revisit later
│   ├── api/auth/[...all]/route.ts      # Better Auth request handler — also serves /api/auth/enter (nodejs)
│   ├── api/auth/set-password/route.ts  # Secure a passwordless account (auth.api.setPassword)
│   └── globals.css           # Design tokens, utility classes, skeleton animation
├── components/
│   ├── auth/      # SecuritySection (set-password form on the profile page)
│   ├── events/    # EventFeed, CalendarView, EventRow, AddEventModal, EditEventModal, EventDetailModal
│   ├── layout/    # Header, HeaderAuthNav, AccountBanner (no-password nudge), Footer, Sidebar, TopBar,
│   │              # MiniCalendar, PageLayout, TagsBar, SectionSelector, TimeWindowSelector
│   └── ui/        # Shared primitives (Badge, Button, Input, Modal, Select, Textarea, Link)
├── hooks/
│   ├── useEvents.ts      # Main data hook: fetch events, filter state, past-event loading
│   ├── useAuth.tsx       # Auth context: Better Auth session + Django profile + JWT; enter/login/setPassword, hasPassword
│   ├── useToggleSet.ts   # Generic multi-select toggle state
│   └── useClickOutside.ts
├── lib/
│   ├── auth.ts             # betterAuth() server config (Drizzle adapter, email+password; Google commented out; jwt + lazyAuth + nextCookies)
│   ├── lazy-auth-plugin.ts # Custom plugin: POST /api/auth/enter (email-first passwordless login/signup)
│   ├── auth-client.ts      # createAuthClient() — signIn/signUp/signOut/useSession/getSession
│   ├── auth-schema.ts      # Drizzle schema for the neon_auth tables
│   └── db.ts               # Drizzle + pg Pool (DATABASE_URL)
├── models/
│   ├── eventsModels.ts   # FrontendEvent, BackendEvent, EventPayload, TownOption, CategoryOption, …
│   ├── authModels.ts     # AuthUser (with hasPassword), UserType, LoginPayload, EnterPayload, EnterResult
│   └── businessModels.ts # Business-related types
├── services/
│   ├── eventService.ts   # getEvents, getTowns, getCategories, getMyEvents, create/update/delete event(s)
│   ├── profileService.ts # getProfile / updateProfile (via /auth/me)
│   ├── businessService.ts # Business profile API client
│   └── eventCache.ts     # Client-side event caching
├── constants/tags.ts
└── data/mockEvents.ts
```

### App Layout

Two view modes — **feed** (chronological list) and **calendar** — switchable in the sidebar. Filter state (tags, towns, selected date, time window) is owned by the `useEvents` hook on the home page. Auth state is provided by `AuthProvider` in the root layout.

**Routing** (App Router):
- `/` — feed/calendar view (client)
- `/about` — about page (server component, SEO metadata)
- `/auth` — lazy signup/login flow (client)
- `/auth/login` — direct login (client)
- `/auth/signup` — direct signup (client)
- `/dashboard` — your submitted events (client)
- `/post` — submit new event, auth-gated (client)
- `/profile` — view/edit profile (client)
- `/events/[uuid]` — single event detail (client)
- `/api/auth/[...all]` — Better Auth handler
- `/api/auth/set-password` — secure a passwordless account

**Event loading:** the feed requests future events by default; calendar requests all including past. A "See Past Events" control triggers a secondary fetch with `?include_past=true`.

### Authentication (frontend)

Better Auth is configured in `src/lib/auth.ts` (server) and consumed via `src/lib/auth-client.ts` (React). The `AuthProvider` (`useAuth.tsx`):
1. reads the Better Auth session (`getSession`),
2. fetches a JWT from `/api/auth/token`,
3. calls Django `/events/me/profile` with that JWT to hydrate the profile,
4. exposes `login`, `signup`, `logout`, and `refreshSession`.

Email+password is enabled. **Google sign-in is temporarily disabled** — commented out in `src/lib/auth.ts` (provider config), `src/app/auth/AuthFlow.tsx` (button + popup handler), and `src/app/auth/google-popup/` (the popup invokes nothing now). It returned `invalid_code` and bypassed user-type selection during signup; revisit later (likely needs a post-OAuth "choose account type" step). The session lives in a Better Auth cookie — **tokens are fetched on demand, not persisted in `localStorage`.**

### Environment Variables (`theCommonsWeb/.env.local`)

```
NEXT_PUBLIC_API_BASE_URL=          # Django base URL, e.g. http://127.0.0.1:8000
NEXT_PUBLIC_THE_COMMONS_API_KEY=   # shared API key (fallback for event creation)
DATABASE_URL=                      # Neon Postgres (Better Auth owns neon_auth schema)
BETTER_AUTH_SECRET=
BETTER_AUTH_URL=http://localhost:3000
NEXT_PUBLIC_BETTER_AUTH_URL=http://localhost:3000
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

### Running Locally

```bash
cd theCommonsWeb
npm install
npm run dev      # http://localhost:3000 (Turbopack)
```

---

## Deployment

Both sub-projects run on a **single Oracle Cloud VM**:

- **Host:** Ubuntu 24.04 · 1 OCPU ARM64 (aarch64) · 6 GB RAM
- **nginx** — reverse proxy and TLS termination. TLS via **Cloudflare** origin certs (Full strict mode). Routes `thecommons.town` → Next.js, `api.thecommons.town` → Django, `www.thecommons.town` → 301 redirect to bare domain.
- **Django** — served by **gunicorn** via unix socket (`unix:/run/gunicorn/gunicorn.sock`).
- **Next.js** — `next start` on `127.0.0.1:3000`.
- **Database** — managed Postgres on **Neon** (external; unchanged from before). Both apps connect over the network.
- **Scheduled jobs** — cron on the VM: daily ingestion (`POST /api/cron/ingest` with `CRON_SECRET`, or `manage.py ingest_events`) and the email digests (`manage.py send_weekly_digest`).

Production frontend domain: `https://thecommons.town`. Django API: `https://api.thecommons.town`. The backend's `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` and `BETTER_AUTH_JWKS_URL` are set to the production hostnames via env on the box (not committed). For full deployment details, see [`DEPLOY.md`](DEPLOY.md).

> Legacy: `backendServer/vercel.json`, `build.sh`, and `main.py` are dead artifacts from the previous Vercel deployment — ignore them.
