# The Commons — Agent Context

The Commons is a local community events aggregator for small NC towns (initially Chapel Hill / Carrboro). It has a Django REST API backend and a React SPA frontend, both deployed to Vercel.

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full system design and [`CODING_STYLE.md`](./CODING_STYLE.md) for design philosophy and conventions.

---

## Repo Layout

```
thecommons/
├── backendServer/   # Django 6 + DRF + PostgreSQL + Gemini ingestion pipeline
├── theCommonsWeb/   # React 19 + TypeScript + Vite + Tailwind v4
├── docs/            # Human-readable docs (admin guide, pipeline guide)
├── ARCHITECTURE.md
└── CODING_STYLE.md
```

## Quick-start Commands

```bash
# Backend
cd backendServer && uv sync && python manage.py runserver

# Frontend
cd theCommonsWeb && npm install && npm run dev
```

## Tech Stack at a Glance

| Layer | Tech |
|-------|------|
| Frontend | React 19, TypeScript, Vite 7, Tailwind CSS v4 |
| Backend | Python 3.13, Django 6, Django REST Framework |
| Database | PostgreSQL (psycopg3) |
| LLM | Google Gemini (event standardization in ingestion pipeline) |
| Admin | django-unfold |
| Deploy | Vercel (both frontend and backend independently) |

## Key Workflows

- **Ingestion pipeline**: `POST /api/cron/ingest` → scrapes EventSources → creates RawEvents → Gemini standardizes into StagedEvents → admin reviews in `/admin/` → `publish_all_approved()` promotes to Events
- **Submitting events**: `POST /events/create` (public API, no auth required)
- **Publishing approved staged events**: Admin "Publish Approved" page or `POST /api/events/publish-approved`

## Things to Know

- `Town` is a SQL table — don't add towns as hardcoded strings. If a new town is needed, add a row to the `Town` model first.
- The ingestion pipeline skips staged events whose `town` slug doesn't match any `Town` record.
- Both sub-projects have their own `.env` files. See `.env.example` in each directory for required vars.
- The frontend design is a **newspaper aesthetic** — serif fonts, cream/ink palette, column rules. Don't introduce gradients, shadows, or rounded pill buttons. See `CODING_STYLE.md`.

## Working in This Repo

- Run `python manage.py migrate` after any model changes before running the server.
- Backend tests live in `{app}/tests.py`. Run with `python manage.py test`.
- Frontend type-checks with `npm run build` (runs `tsc -b` before Vite).
- Never commit `.env` files — use `.env.example` to document new variables.
