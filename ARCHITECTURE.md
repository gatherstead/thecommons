# Architecture

## Overview

The Commons is a local community events aggregator for small towns in North Carolina (initially Chapel Hill / Carrboro area). It has two sub-projects inside a monorepo:

```
thecommons/
├── backendServer/   # Django 6 REST API + admin + ingestion pipeline
└── theCommonsWeb/   # Next.js 16 (App Router) + React 19 (the public-facing site)
```

---

## Backend (`backendServer/`)

**Stack:** Python 3.13 · Django 6 · Django REST Framework · PostgreSQL (psycopg3) · Google Gemini (LLM) · django-unfold (admin UI) · Deployed on Vercel

### Django Apps

| App | Responsibility |
|-----|---------------|
| `events` | Published events, tags, towns, user profiles, auth views — the canonical public data |
| `ingestion` | Ingestion pipeline: event sources, raw events, staged events, LLM processing, admin review workflow |

### Data Models

#### `events` app
- **`Town`** — slug + display name (e.g. `carrboro` / `Carrboro`)
- **`Tag`** — lowercase string labels
- **`Event`** — UUID PK · title · town (FK) · date (indexed) · venue · description · price · photo · tags (M2M) · link
- **`UserProfile`** — OneToOne with Django `User` · user_type (LOCAL/BUSINESS/VENUE) · primary_city · email_preference · tags (M2M)

#### `ingestion` app
- **`EventSource`** — URL we poll on a schedule; source_type ∈ {ics, scraper, email}
- **`RawEvent`** — event as scraped, before any LLM processing; unique on (source, source_uid)
- **`StagedEvent`** — LLM-standardized version awaiting admin review; status ∈ {pending, approved, rejected, duplicate}

### Authentication

Auth is handled in `events/auth_views.py` using DRF's `TokenAuthentication` with a `Bearer` scheme:

- `POST /auth/signup` — creates User + UserProfile + Token. Requires email, password; optionally business_name and user_type.
- `POST /auth/login` — authenticates, returns token.
- `POST /auth/logout` — deletes token (requires auth).
- `GET /auth/me` — returns current user profile (requires auth).

The `BearerTokenAuthentication` class (`backend/permissions.py`) accepts either a per-user DRF token or the shared `THE_COMMONS_API_KEY`. The `HasCommonsAPIKeyOrUser` permission allows either form on endpoints like `createEvent`.

### Ingestion Pipeline

```
EventSource (URL/feed)
    ↓  importers (ICS, scraper)
RawEvent  ←  deduplicator.py
    ↓  standardizer.py (Gemini LLM)
StagedEvent  ←  admin reviews in django-unfold
    ↓  services.publish_all_approved()
Event (canonical, public)
```

Triggered via `POST /api/cron/ingest` (requires `CRON_SECRET` header). Publishing approved events is done from the admin UI or via `POST /api/events/publish-approved`.

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/events/` | List published events (excludes past by default; supports `?after=`, `?before=`, `?include_past=true`) |
| GET | `/events/towns/` | List all towns |
| GET | `/events/{uuid}` | Single event detail |
| POST | `/events/create` | Submit a new event (requires auth: user token or API key) |
| POST | `/auth/signup` | Create account |
| POST | `/auth/login` | Log in, receive token |
| POST | `/auth/logout` | Log out, delete token |
| GET | `/auth/me` | Current user profile |
| POST | `/api/cron/ingest` | Trigger ingestion pipeline (cron) |
| POST | `/api/events/publish-approved` | Publish all approved staged events |

Admin lives at `/admin/`. Pipeline and admin docs are rendered as Django template pages under `/admin/docs/`.

### Environment Variables (`backendServer/.env`)

```
DATABASE_URL=        # postgres connection string
DJANGO_SECRET_KEY=
GEMINI_API_KEY=
CRON_SECRET=
THE_COMMONS_API_KEY=
```

### Running Locally

```bash
cd backendServer
uv sync                          # install deps
python manage.py migrate
python manage.py runserver       # http://localhost:8000
```

---

## Frontend (`theCommonsWeb/`)

**Stack:** Next.js 16 (App Router + Turbopack) · React 19 · TypeScript · Tailwind CSS v4

### Key Source Directories

```
src/
├── app/
│   ├── layout.tsx     # Root layout (server component): AuthProvider, Header, Footer
│   ├── page.tsx       # Home page (client component): feed/calendar views, modals
│   ├── about/page.tsx # About page (server component)
│   └── globals.css    # Design tokens, utility classes, skeleton animation
├── components/
│   ├── auth/      # AuthModal (login/signup)
│   ├── events/    # EventFeed, CalendarView, EventRow, AddEventModal, EventDetailModal
│   ├── layout/    # Header, Footer, Sidebar, TopBar, MiniCalendar, PageLayout, TagsBar
│   └── ui/        # Shared primitives (Badge, Button, Input, Modal, Select, Textarea, Link)
├── hooks/
│   ├── useEvents.ts     # Main data hook: fetches events, manages filter state, past-event loading
│   ├── useAuth.tsx       # Auth context provider + hook (login, signup, logout, token management)
│   ├── useToggleSet.ts   # Generic multi-select toggle state
│   └── useClickOutside.ts
├── models/
│   ├── eventsModels.ts  # FrontendEvent, BackendEvent, EventPayload, TownOption
│   └── authModels.ts    # AuthUser, LoginPayload, SignupPayload, AuthResponse
├── services/
│   ├── eventService.ts  # API calls: getEvents, getTowns, createEvent
│   └── authService.ts   # API calls: signup, login, logout, fetchMe, token storage
├── constants/
│   └── tags.ts          # 10 frontend filter tags
└── data/
    └── mockEvents.ts
```

### App Layout

The app has two view modes — **feed** (chronological list) and **calendar** — switchable in the sidebar. Layout is a 6-column grid: 4 columns for the main content, 2 for the sidebar.

Navigation context flows through the home page (`app/page.tsx`) via the `useEvents` hook which owns filter state (tags, towns, selected date). Auth state is provided by `AuthProvider` in the root layout.

**Routing** uses Next.js App Router:
- `/` — feed/calendar view (client component)
- `/about` — about page (server component with SEO metadata)

**Event loading:** The feed requests only future events (next 30 days) by default. Calendar requests all events including past. A "See Past Events" button on the feed triggers a secondary fetch with `?include_past=true`.

**Auth flow:** The `AuthProvider` wraps the entire app. When a non-authenticated user clicks "Post an Event," they see the `AuthModal` (login/signup) first. After authentication, the `AddEventModal` opens automatically.

### Environment Variables (`theCommonsWeb/.env.local`)

```
NEXT_PUBLIC_API_BASE_URL=    # backend base URL, e.g. http://127.0.0.1:8000
NEXT_PUBLIC_THE_COMMONS_API_KEY=   # shared API key (fallback for event creation)
```

### Running Locally

```bash
cd theCommonsWeb
npm install
npm run dev      # http://localhost:3000 (Turbopack)
```

---

## Deployment

Both sub-projects deploy to **Vercel** independently (each has its own `vercel.json`). The backend is a WSGI app served via Vercel's Python runtime. The frontend is a Next.js build.

Production domain: `https://www.thecommons.town`
