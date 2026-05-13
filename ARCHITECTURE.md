# Architecture

## Overview

The Commons is a local community events aggregator for small towns in North Carolina (initially Chapel Hill / Carrboro area). It has two sub-projects inside a monorepo:

```
thecommons/
├── backendServer/   # Django 6 REST API + admin + ingestion pipeline
└── theCommonsWeb/   # React 19 SPA (the public-facing site)
```

---

## Backend (`backendServer/`)

**Stack:** Python 3.13 · Django 6 · Django REST Framework · PostgreSQL (psycopg3) · Google Gemini (LLM) · django-unfold (admin UI) · Deployed on Vercel

### Django Apps

| App | Responsibility |
|-----|---------------|
| `events` | Published events, tags, towns, user profiles — the canonical public data |
| `ingestion` | Ingestion pipeline: event sources, raw events, staged events, LLM processing, admin review workflow |

### Data Models

#### `events` app
- **`Town`** — slug + display name (e.g. `carrboro` / `Carrboro`)
- **`Tag`** — lowercase string labels
- **`Event`** — UUID PK · title · town (FK) · date · venue · description · price · photo · tags (M2M) · link
- **`UserProfile`** — OneToOne with Django `User` · user_type (LOCAL/BUSINESS/VENUE) · primary_city · email_preference · tags (M2M)

#### `ingestion` app
- **`EventSource`** — URL we poll on a schedule; source_type ∈ {ics, scraper, email}
- **`RawEvent`** — event as scraped, before any LLM processing; unique on (source, source_uid)
- **`StagedEvent`** — LLM-standardized version awaiting admin review; status ∈ {pending, approved, rejected, duplicate}

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
| GET | `/events/` | List all published events |
| GET | `/events/towns/` | List all towns |
| GET | `/events/{uuid}` | Single event detail |
| POST | `/events/create` | Submit a new event |
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

**Stack:** React 19 · TypeScript · Vite 7 · Tailwind CSS v4

### Key Source Directories

```
src/
├── components/
│   ├── events/    # EventFeed, CalendarView, AddEventModal, EventDetailModal
│   ├── filters/   # Tag/town filter controls
│   ├── layout/    # Header, Footer, Sidebar, TopBar
│   └── ui/        # Shared primitives
├── hooks/         # useEvents (main data hook)
├── models/        # TypeScript interfaces (FrontendEvent, etc.)
├── services/      # eventService.ts (API calls)
└── constants/
```

### App Layout

The app has two view modes — **feed** (chronological list) and **calendar** — switchable in the sidebar. Layout is a 6-column grid: 4 columns for the main content, 2 for the sidebar.

Navigation context flows through `App.tsx` via the `useEvents` hook which owns filter state (tags, towns, selected date).

### Environment Variables (`theCommonsWeb/.env`)

```
VITE_API_URL=    # backend base URL, e.g. http://localhost:8000
```

### Running Locally

```bash
cd theCommonsWeb
npm install
npm run dev      # http://localhost:5173
```

---

## Deployment

Both sub-projects deploy to **Vercel** independently (each has its own `vercel.json`). The backend is a WSGI app served via Vercel's Python runtime. The frontend is a static Vite build.

Production domain: `https://www.thecommons.town`
