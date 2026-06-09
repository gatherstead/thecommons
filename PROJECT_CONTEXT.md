# The Commons — Project Context (Consolidated)

> **Purpose:** Self-contained context dump for use in Claude.ai projects, planning sessions outside the repo, or onboarding. Generated from `AGENTS.md`, `ARCHITECTURE.md`, `CODING_STYLE.md`, `DEPLOY.md`, and the sub-project `AGENTS.md` files. **The in-repo docs are canonical** — if this file drifts, trust them. Regenerate this file from them rather than hand-editing.

---

## 1. What This Is

The Commons is a local community events aggregator for small NC towns (initially Chapel Hill / Carrboro). It's a monorepo with a Django REST API backend and a Next.js frontend, deployed on a single Oracle Cloud VM. The database is managed Postgres on Neon.

The product look-and-feel is intentionally a **digital newspaper** — old-timey Craigslist crossed with a small-town broadsheet. Serif fonts (Georgia), cream/ink palette, column rules, density over whitespace. No gradients, no rounded pill buttons, no startup vibes.

```
thecommons/
├── backendServer/      # Django 6 + DRF + Postgres + Gemini ingestion
├── theCommonsWeb/      # Next.js 16 (App Router) + React 19 + Better Auth
└── docs/               # Deep-dive guides
```

---

## 2. Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 16 (App Router + Turbopack), React 19, TypeScript, Tailwind CSS v4 |
| Backend | Python 3.13, Django 6, Django REST Framework, `uv` |
| Database | PostgreSQL on Neon (psycopg3 from Django; pg/Drizzle from Next.js) |
| LLM | Google Gemini (event standardization in ingestion pipeline) |
| Auth | Better Auth (lives in Next.js); Django verifies JWTs via JWKS |
| Email | Brevo (transactional + weekly/monthly digests) |
| Admin | django-unfold |
| Deploy | Single Oracle Cloud VM (Ubuntu 24.04, ARM64) — nginx → gunicorn + Next.js |

---

## 3. Repository Map

```
thecommons/
├── backendServer/                # Django 6 + DRF + Postgres + Gemini
│   ├── backend/                  #   Project config
│   │   ├── settings.py           #     DB, CORS, CSRF, installed apps, pagination
│   │   ├── urls.py               #     Root URL conf
│   │   ├── jwt_auth.py           #     BearerTokenAuthentication — verifies Better Auth JWTs via JWKS
│   │   ├── permissions.py        #     HasCommonsAPIKey, HasCommonsAPIKeyOrUser
│   │   └── wsgi.py
│   ├── events/                   #   Public data app
│   │   ├── models.py             #     Event, Town, Tag, Category, UserProfile, BusinessProfile,
│   │   │                         #     NewsletterSubscriber + BetterAuth mirrors (managed=False)
│   │   ├── views.py              #     DRF views
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   ├── admin.py              #     django-unfold registration
│   │   ├── email_service.py      #     Brevo wrapper
│   │   └── management/commands/  #     send_weekly_digest, send_digest, send_test_digest, delete_user
│   ├── ingestion/                #   Pipeline app
│   │   ├── models.py             #     EventSource, RawEvent, StagedEvent
│   │   ├── views.py              #     cron_ingest, publish_approved_events
│   │   ├── services.py           #     publish_all_approved(), orchestration
│   │   ├── importers/            #     ICS importer (scraper planned)
│   │   ├── deduplicator.py       #     Dedup raw events
│   │   ├── standardizer.py       #     Gemini LLM standardization
│   │   ├── safety_scorer.py      #     Flag unsafe/low-quality
│   │   ├── admin.py              #     Staged-event review workflow
│   │   └── management/commands/  #     ingest_events, cleanup_old_events
│   └── templates/email/          #   HTML email templates
├── theCommonsWeb/                # Next.js 16 + React 19 + TypeScript
│   └── src/
│       ├── app/                  #   App Router pages + API routes
│       ├── components/           #   auth/, events/, layout/, ui/
│       ├── hooks/                #   useAuth, useEvents, useMessageStack, useToggleSet
│       ├── lib/                  #   Better Auth config, Drizzle schema, DB pool, lazy-auth plugin
│       ├── models/               #   TypeScript types
│       ├── services/             #   API clients
│       └── constants/
├── docs/                         # Deep-dive guides
│   ├── index.md
│   ├── ingestion-pipeline.md
│   ├── admin-backend.md
│   └── safety-scoring.md
├── AGENTS.md                     # Repo map (canonical)
├── ARCHITECTURE.md               # System design (canonical)
├── CODING_STYLE.md               # Design philosophy + conventions (canonical)
├── DEPLOY.md                     # VM setup (canonical)
├── CLAUDE.md                     # Claude Code entry point
└── PROJECT_CONTEXT.md            # This file — consolidated dump for external use
```

> **Legacy dead files (ignore):** `backendServer/vercel.json`, `backendServer/build.sh`, `backendServer/main.py` are leftover from the previous Vercel deployment.

---

## 4. Data Models

### `events` app — application data
- **`Town`** — `slug` + `name` (e.g. `carrboro` / `Carrboro`). SQL-backed; do not hardcode.
- **`Tag`** — unique string labels.
- **`Category`** — `slug` + `display_name`; distinct from `Tag`. SQL-backed; do not hardcode.
- **`Event`** — UUID PK · title · town (FK, nullable) · date (indexed) · venue · description · price · photo · `tags` (M2M) · `categories` (M2M) · link · `is_verified` · `source_name` · `created_by` (FK → `BetterAuthUser`, null for pipeline-ingested events).
- **`UserProfile`** — OneToOne with **`BetterAuthUser`** (not Django's `auth.User`) · `user_type` (LOCAL/BUSINESS/VENUE) · `primary_city` · `address` · `email_preference` (WEEKLY/MONTHLY/NEVER) · `tags` (M2M). Created automatically when Better Auth creates a user (see §6 Auth).
- **`BusinessProfile`** — OneToOne with **`BetterAuthUser`** · UUID · `business_name` · `description` · `tags` (M2M Tag) · `service_area` (M2M Town) · `contact_email` · `contact_phone` · `is_published` · timestamps.
- **`NewsletterSubscriber`** — `email` · `frequency` (WEEKLY/MONTHLY) · `is_active` · `subscribed_at`. For non-account digest subscribers.

### Better Auth mirrors — `neon_auth` schema, `managed = False`
Better Auth (Next.js) owns these tables; Django maps them read-only for joins. **Never create migrations for them.**
- **`BetterAuthUser`** (`neon_auth.user`) — UUID id · name · email · `user_type` · timestamps. Sets `is_authenticated = True` so DRF permission classes accept it.
- **`BetterAuthSession`**, **`BetterAuthAccount`**, **`BetterAuthVerification`**, **`BetterAuthJwks`** — the rest of the set.

> The `db_table` values use a double-quote trick (e.g. `'neon_auth"."user'`) so Django emits a valid cross-schema reference `FROM "neon_auth"."user"`.

### `ingestion` app
- **`EventSource`** — URL we poll; `source_type ∈ {ics, scraper, email}`.
- **`RawEvent`** — event as scraped, before LLM processing; unique on (source, source_uid).
- **`StagedEvent`** — LLM-standardized version awaiting admin review; status ∈ {pending, approved, rejected, duplicate}.

### Database ownership

| Schema | Owner | Django access |
|--------|-------|---------------|
| `public` | Django migrations | Full read/write |
| `neon_auth` | Better Auth (Next.js) | Read-only mirrors (`managed = False`) — never migrate |

---

## 5. API Endpoints (Django)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/events/` | — | List published events (excludes past by default; `?after=`, `?before=`, `?include_past=true`, `?category=`) |
| GET | `/events/towns/` | — | List all towns |
| GET | `/events/categories/` | — | List all categories |
| GET | `/events/{uuid}` | — | Single event detail |
| DELETE | `/events/{uuid}` | user | Delete a published event you own |
| POST | `/events/create` | user or API key | Submit a new event |
| GET | `/events/me/profile` | user | Current user's profile (includes derived `has_password`) |
| GET | `/events/me/events` | user | Events submitted by current user |
| GET/PATCH/DELETE | `/events/staged/{id}` | user | Manage one of your staged submissions |
| GET/PATCH | `/auth/me` | user | Read / update profile |
| POST | `/auth/subscribe` | — | Subscribe email to newsletter |
| GET/POST | `/businesses` | user | List published businesses / create a business profile |
| GET | `/businesses/me` | user | Current user's business profile |
| GET/PATCH/DELETE | `/businesses/{uuid}` | user | Manage business profile |
| POST | `/api/cron/ingest` | `CRON_SECRET` | Trigger ingestion pipeline |
| POST | `/api/events/publish-approved` | API key | Publish all approved staged events |

> Login/signup/logout are handled by Better Auth in **Next.js** at `/api/auth/*` — including the lazy `POST /api/auth/enter` and `POST /api/auth/set-password`. The Django admin lives at `/admin/` (django-unfold).

---

## 6. Authentication — The Better Auth ↔ Django Bridge

**Key files:** `backendServer/backend/jwt_auth.py`, `backendServer/backend/permissions.py`, `theCommonsWeb/src/lib/auth.ts`, `theCommonsWeb/src/lib/lazy-auth-plugin.ts`, `theCommonsWeb/src/hooks/useAuth.tsx`, `theCommonsWeb/src/app/api/auth/set-password/route.ts`

Auth is owned by **Better Auth running inside Next.js** — there are no Django login/signup endpoints. Django only *verifies* tokens.

### The bridge
- Browser authenticates with Better Auth and holds a session cookie.
- To call Django, frontend fetches a short-lived **JWT** from `/api/auth/token` (Better Auth `jwt()` plugin) and sends it as `Authorization: Bearer <jwt>`.
- `BearerTokenAuthentication` accepts either:
  1. a **Better Auth JWT** verified statelessly against the frontend's JWKS endpoint (`BETTER_AUTH_JWKS_URL`). `sub` is resolved to a `BetterAuthUser`. JWKS client cached in-process (10-min TTL) with stale-grace so brief Next.js outages don't cascade.
  2. the shared **`THE_COMMONS_API_KEY`** (no user attached) — for app-level calls like event creation.
- Permission classes: `HasCommonsAPIKey`, `HasCommonsAPIKeyOrUser`, plus DRF's `IsAuthenticated`.

### User-creation side effect
`src/lib/auth.ts` defines a `databaseHooks.user.create.after` that inserts a matching `events_userprofile` row when Better Auth creates a user, so every account has a Django profile.

### Lazy (passwordless) accounts
Signup is email-first, password-optional. Custom Better Auth plugin (`src/lib/lazy-auth-plugin.ts`) exposes `POST /api/auth/enter`:
- New email → creates Better Auth user (no credential account) and session; returns `{ isNew: true }`. The `databaseHook` still fires.
- Existing passwordless email → fresh session, returns `{ isNew: false, requiresPassword: false }`.
- Existing email with password → returns `{ requiresPassword: true }` (no session); frontend collects password and uses normal `signIn.email`.

Users secure their account later via `POST /api/auth/set-password` (calls Better Auth's `auth.api.setPassword` to link a `credential` account). **No email verification for MVP** — anyone can claim any unclaimed email.

### `has_password` is derived
Django computes it from the `BetterAuthAccount` mirror (`provider_id='credential'` with non-null password) and returns it on `/auth/me` and `/events/me/profile`. Frontend uses it for security nudges (banner for no-password accounts; red dot for incomplete business/venue profiles). **No new column, no migration.**

### Google sign-in — DISABLED
Commented out in `src/lib/auth.ts` (provider config), `src/app/auth/AuthFlow.tsx` (button + popup handler), and `src/app/auth/google-popup/`. Was returning `invalid_code` and bypassed user-type selection during signup. Revisit later (likely needs a post-OAuth "choose account type" step).

---

## 7. Ingestion Pipeline

**Key files:** `ingestion/services.py`, `ingestion/standardizer.py`, `ingestion/safety_scorer.py`, `ingestion/deduplicator.py`, `ingestion/importers/ics_importer.py`

```
EventSource (URL/feed)
    ↓  importers/ (ICS, scraper)
RawEvent  ←  deduplicator.py
    ↓  standardizer.py (Gemini LLM)  +  safety_scorer.py
StagedEvent  ←  admin reviews in django-unfold
    ↓  services.publish_all_approved()
Event (canonical, public)
```

Triggered via `POST /api/cron/ingest` (requires `CRON_SECRET` header) or the `python manage.py ingest_events` command. Publishing approved events is done from the admin UI or via `POST /api/events/publish-approved`. `safety_scorer.py` flags low-quality/unsafe events against `SAFETY_SCORE_THRESHOLD`.

The `Town` slug on a `StagedEvent` must resolve to a row in the `Town` table — unknown slugs cause the event to be skipped during publishing.

---

## 8. Email Digests

`events/email_service.py` wraps **Brevo** transactional email. Management commands:
- `send_weekly_digest` — personalized per WEEKLY subscriber (their town + tag interests). HTML from `templates/email/weekly_digest.html`.
- `send_digest --frequency WEEKLY|MONTHLY` — batch digest.
- `send_test_digest --email <addr>` — render + send one test digest.

Scheduled via cron on the VM (see §11 Deployment).

Other management commands: `delete_user` (cascade delete), `cleanup_old_events` (remove expired).

---

## 9. Frontend Architecture

### Routes (App Router)

| Path | File | Type | Purpose |
|------|------|------|---------|
| `/` | `app/page.tsx` | client | Feed + calendar views |
| `/about` | `app/about/page.tsx` | server | About page (SEO metadata) |
| `/auth` | `app/auth/page.tsx` | client | Lazy signup/login flow: type → preferences → email |
| `/auth/login` | `app/auth/login/page.tsx` | client | Direct login |
| `/auth/signup` | `app/auth/signup/page.tsx` | client | Direct signup |
| `/dashboard` | `app/dashboard/page.tsx` | client | Manage submitted events |
| `/post` | `app/post/page.tsx` | client | Submit new event (auth-gated) |
| `/profile` | `app/profile/page.tsx` | client | View/edit profile + security section |
| `/events/[uuid]` | `app/events/[uuid]/page.tsx` | client | Event detail |
| `/api/auth/[...all]` | `app/api/auth/[...all]/route.ts` | API | Better Auth handler |
| `/api/auth/set-password` | `app/api/auth/set-password/route.ts` | API | Secure passwordless account |

### Layout
Two view modes — **feed** (chronological list) and **calendar** — switchable in the sidebar. Filter state (tags, towns, selected date, time window) is owned by the `useEvents` hook on the home page. Auth state is provided by `AuthProvider` in the root layout.

**Event loading:** feed requests future events by default; calendar requests all including past. A "See Past Events" control triggers a secondary fetch with `?include_past=true`.

### Auth on the frontend
Better Auth configured in `src/lib/auth.ts` (server) and consumed via `src/lib/auth-client.ts` (React). `AuthProvider` (`useAuth.tsx`):
1. Reads Better Auth session (`getSession`)
2. Fetches a JWT from `/api/auth/token`
3. Calls Django `/events/me/profile` with that JWT to hydrate the profile
4. Exposes `login`, `signup`, `logout`, `refreshSession`

Email+password is enabled. Session lives in a Better Auth cookie — **tokens are fetched on demand, not persisted in `localStorage`**.

---

## 10. Coding Style & Conventions

### Design philosophy (the look)
- Ink on newsprint. Dark text on cream background.
- Serif everywhere (Georgia, system-loaded — no network fonts).
- Column rules and thick borders instead of cards and shadows.
- Density over whitespace — newspaper-style packing.

### Frontend CSS tokens — `theCommonsWeb/src/app/globals.css`
**Never hardcode hex values.** Reference these CSS custom properties:

```css
--color-bg:           #f4f1eb   /* newsprint cream */
--color-bg-alt:       #eae6dd   /* slightly darker cream */
--color-text:         #1a1a1a   /* near-black ink */
--color-text-muted:   #555555
--color-link:         #1a1a1a
--color-link-hover:   #8b0000   /* dark red */
--color-border:       #1a1a1a   /* thick rule */
--color-border-light: #c8c3b8   /* hairline */
--color-accent:       #8b0000   /* dark red — active/selected only */

--font-headline:  Georgia, "Times New Roman", Times, serif
--font-body:      Georgia, "Times New Roman", Times, serif
--font-sans:      system-ui, ...  /* UI chrome only */
```

Utility classes: `.rule-thick`, `.rule-double`, `.drop-cap`, `.skeleton-block` (respects `prefers-reduced-motion`).

### Frontend component conventions
- TypeScript everywhere. Props interfaces named `{ComponentName}Props`.
- Components in `src/components/{category}/`.
- Tailwind for layout/spacing; CSS variables for all colors (`var(--color-*)` or `bg-[var(--color-bg)]`).
- No `useState` in pure display components — lift to nearest shared ancestor or hook.
- Main data hook is `useEvents`. Filtering/sorting logic lives there.
- **Auth state lives in `useAuth`.** Don't call `authClient` or manage sessions/JWTs in components.
- Event data flows as `FrontendEvent` (`src/models/eventsModels.ts`). API → `FrontendEvent` mapping in `eventService.ts`, not components. Profile reads/writes via `profileService.ts`.
- Mark interactive components with `'use client'`. Server components preferred for static/SEO pages; use route-level `metadata` exports.
- Browser env vars use `NEXT_PUBLIC_` prefix. Keep `DATABASE_URL`, `BETTER_AUTH_SECRET`, `GOOGLE_CLIENT_SECRET` server-side only.

### Backend Django conventions
- Apps are domain-scoped: `events` = public-facing data, `ingestion` = pipeline internals. Don't bleed pipeline logic into events.
- Serializers in `{app}/serializers.py`; views in `{app}/views.py` stay thin; business logic in `services.py`.
- `transaction.atomic()` for anything touching multiple models.
- New models need a migration — **except** `neon_auth` mirrors (`managed = False`).
- **Auth is delegated.** No Django login/signup/logout views. Don't use `django.contrib.auth.User` for app users. New authed endpoints use `BearerTokenAuthentication` + `HasCommonsAPIKeyOrUser` or `IsAuthenticated`. `UserProfile` is keyed to `BetterAuthUser`.
- Admin registration in `{app}/admin.py`. Use django-unfold decorators for custom display.
- `Town` and `Category` are SQL tables — canonical authorities, don't hardcode.

### General
- No comments explaining *what* — use descriptive names.
- Comments only when *why* is non-obvious (workaround, subtle invariant, known limitation).
- No dead code. Delete it.
- Keep `.env.example` up to date.

---

## 11. Deployment (Production VM)

### Host
- **Provider:** Oracle Cloud Infrastructure
- **OS:** Ubuntu 24.04, ARM64 (aarch64), 1 OCPU, 6 GB RAM
- **IP:** `129.80.229.41`
- **Domain:** `thecommons.town` (frontend), `api.thecommons.town` (Django)

### DNS & TLS
- DNS via **Cloudflare**, proxied (orange cloud).
- TLS mode: **Full (strict)**. Cloudflare-issued origin cert at `/etc/ssl/cloudflare/`.

### Services
- **nginx** — reverse proxy + TLS termination.
  - `thecommons.town` → `http://localhost:3000` (Next.js)
  - `api.thecommons.town` → `unix:/run/gunicorn/gunicorn.sock` (Django)
  - `api.thecommons.town/static/` → `backendServer/staticfiles/` (Django admin CSS)
  - `www.thecommons.town` → 301 to bare domain
  - HTTP (80) → 301 to HTTPS
- **gunicorn** — Django via unix socket, 3 sync workers. `RuntimeDirectory=gunicorn` in service file creates `/run/gunicorn/` owned by `ubuntu`.
- **nextjs** — `next start` on `127.0.0.1:3000`.
- **Database** — managed Postgres on Neon (external).
- **Scheduled jobs** — cron on the VM: daily ingestion (`POST /api/cron/ingest` or `manage.py ingest_events`), email digests (`manage.py send_weekly_digest`).

### Package managers on the VM
- **Python:** `uv` (snap). Never use `pip`. Use `uv sync`, `uv run python manage.py ...`.
- **Node:** `pnpm`. Never `npm install` (breaks peer dep pinning). Use `pnpm install`, `pnpm run build`.

### Deploy commands

**Backend:**
```bash
cd /home/ubuntu/thecommons && git pull
cd backendServer
uv sync                                              # only if pyproject.toml changed
uv run python manage.py migrate                      # only if models changed
uv run python manage.py collectstatic --noinput      # only if static files changed
sudo systemctl restart gunicorn
```

**Frontend:**
```bash
cd /home/ubuntu/thecommons && git pull
cd theCommonsWeb
pnpm install              # only if pnpm-lock.yaml changed
pnpm run build
sudo systemctl restart nextjs
```

### Firewall gotcha
Two layers — both must allow 80/443:
1. **Oracle VCN Security List** (OCI console) — ports 22, 80, 443 ingress.
2. **iptables on the VM** — Oracle Ubuntu ships with a catch-all `REJECT` in INPUT. ACCEPT rules for 80/443 must be **inserted before** that rule (position 5), not appended. Save with `sudo netfilter-persistent save`.

### Troubleshooting cheat-sheet
| Symptom | Likely cause |
|---------|-------------|
| `curl` to IP returns nothing | iptables REJECT before ACCEPT |
| nginx 502 | gunicorn or nextjs down — `systemctl status` |
| Django `DisallowedHost` | `api.thecommons.town` missing from `DJANGO_ALLOWED_HOSTS` |
| 400 on `/events/` from browser | `NEXT_PUBLIC_API_BASE_URL` wrong or build stale |
| gunicorn socket permission denied | Socket outside `RuntimeDirectory` |
| Django admin has no CSS | `collectstatic` not run or nginx `/static/` alias wrong |

---

## 12. Environment Variables

### `backendServer/.env`
```
DATABASE_URL=                # Neon Postgres connection string
DJANGO_SECRET_KEY=
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,api.thecommons.town
CORS_EXTRA_ORIGINS=https://thecommons.town
CSRF_TRUSTED_ORIGINS=https://api.thecommons.town,https://thecommons.town
GEMINI_API_KEY=
CRON_SECRET=
THE_COMMONS_API_KEY=
SAFETY_SCORE_THRESHOLD=0.3
# Better Auth bridge — Django verifies JWTs issued by Next.js
BETTER_AUTH_JWKS_URL=        # prod: https://thecommons.town/api/auth/jwks
BETTER_AUTH_ISSUER=          # prod: https://thecommons.town
BETTER_AUTH_AUDIENCE=
# Brevo (email digests)
BREVO_API_KEY=
DIGEST_FROM_EMAIL=digest@thecommons.town
SITE_URL=https://thecommons.town
```

### `theCommonsWeb/.env.local`
```
NEXT_PUBLIC_API_BASE_URL=          # e.g. http://127.0.0.1:8000  (prod: https://api.thecommons.town)
NEXT_PUBLIC_THE_COMMONS_API_KEY=   # shared API key (fallback for event creation)
DATABASE_URL=                      # Same Neon connection string (Better Auth owns neon_auth schema)
BETTER_AUTH_SECRET=
BETTER_AUTH_URL=http://localhost:3000    # prod: https://thecommons.town
NEXT_PUBLIC_BETTER_AUTH_URL=http://localhost:3000
GOOGLE_CLIENT_ID=                  # currently unused (Google sign-in disabled)
GOOGLE_CLIENT_SECRET=
```

---

## 13. Quick Start (Local)

```bash
# Backend
cd backendServer && uv sync && python manage.py migrate && python manage.py runserver
# Frontend
cd theCommonsWeb && npm install && npm run dev
```

Run both for end-to-end auth — Django validates JWTs against the frontend's JWKS endpoint.

- Backend tests: `python manage.py test`
- Frontend type-check: `npm run build`

---

## 14. Guardrails (Cross-Cutting Rules)

- **Never migrate `neon_auth` tables.** Better Auth owns them. Django mirrors are `managed = False`.
- **`Town` and `Category` are SQL tables** — don't hardcode. Pipeline skips events with unknown town slugs.
- **Auth lives in Next.js**, not Django. Don't add Django login/signup views or use `auth.User`.
- **Never commit `.env`** — update `.env.example` instead.
- **Newspaper aesthetic** — serif fonts, cream/ink, column rules. No gradients, shadows, pill buttons.
- **Events API excludes past by default** — use `?include_past=true` for all.
- **Google sign-in is disabled** — commented out in `auth.ts`, `AuthFlow.tsx`, `google-popup/`. Revisit later.
- **Legacy Vercel files** — `backendServer/vercel.json`, `build.sh`, `main.py` are dead. Ignore.
- **If a doc contradicts the code, trust the code** and flag the drift.

---

## 15. Where to Find Deeper Detail

These deep-dive guides exist in `docs/` and are not inlined here:
- `docs/ingestion-pipeline.md` — end-to-end pipeline walkthrough
- `docs/admin-backend.md` — django-unfold admin UI guide
- `docs/safety-scoring.md` — safety scorer details + threshold tuning
