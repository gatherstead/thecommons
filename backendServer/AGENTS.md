# backendServer — Agent Map

Django 6 + DRF backend. Python 3.13, managed by `uv`.

## Directory Map

```
backendServer/
├── backend/                          # Django project config
│   ├── settings.py                   # DB, CORS, CSRF, installed apps, pagination, logging
│   ├── urls.py                       # Root URL conf — mounts events/, auth/, businesses, cron, admin
│   ├── jwt_auth.py                   # BearerTokenAuthentication — verifies Better Auth JWTs via JWKS
│   ├── permissions.py                # HasCommonsAPIKey, HasCommonsAPIKeyOrUser
│   └── wsgi.py
├── events/                           # Public data app
│   ├── models.py                     # Event, Town, Tag, Category, UserProfile, BusinessProfile,
│   │                                 #   NewsletterSubscriber + BetterAuth mirrors (managed=False)
│   ├── views.py                      # DRF views: events CRUD, profile, businesses, subscribe
│   ├── serializers.py                # DRF serializers
│   ├── urls.py                       # /events/* routes
│   ├── admin.py                      # django-unfold admin registration
│   ├── email_service.py              # Brevo transactional email wrapper
│   ├── tests.py
│   └── management/commands/
│       ├── send_weekly_digest.py     # Personalized weekly digest (per subscriber town + tags)
│       ├── send_digest.py            # Batch digest (--frequency WEEKLY|MONTHLY)
│       ├── send_test_digest.py       # Render + send one test digest (--email)
│       └── delete_user.py            # Delete a user and cascade
├── ingestion/                        # Pipeline app
│   ├── models.py                     # EventSource, RawEvent, StagedEvent
│   ├── views.py                      # cron_ingest, publish_approved_events, admin doc pages
│   ├── services.py                   # publish_all_approved(), pipeline orchestration
│   ├── importers/
│   │   └── ics_importer.py           # ICS feed importer
│   ├── deduplicator.py               # Dedup raw events by (source, source_uid)
│   ├── standardizer.py               # Gemini LLM standardization
│   ├── safety_scorer.py              # Flag unsafe/low-quality events
│   ├── admin.py                      # Staged event review workflow in admin
│   └── management/commands/
│       ├── ingest_events.py          # Run full ingestion pipeline
│       └── cleanup_old_events.py     # Remove expired events
├── templates/email/                  # HTML email templates (weekly_digest.html, digest.html)
├── .env.example                      # Required env vars — see this file for the full list
├── pyproject.toml                    # uv project config + dependencies
├── manage.py
├── vercel.json                       # LEGACY — dead file from previous Vercel deployment
├── build.sh                          # LEGACY — dead file from previous Vercel deployment
└── main.py                           # LEGACY — dead file from previous Vercel deployment
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/events/` | — | List published events (excludes past by default; `?after=`, `?before=`, `?include_past=true`, `?category=`) |
| GET | `/events/towns/` | — | List all towns |
| GET | `/events/categories/` | — | List all categories |
| GET | `/events/{uuid}` | — | Single event detail |
| DELETE | `/events/{uuid}` | user | Delete an event you own |
| POST | `/events/create` | user or API key | Submit a new event |
| GET | `/events/me/profile` | user | Current user's profile (includes derived `has_password`) |
| GET | `/events/me/events` | user | Events submitted by the current user |
| GET/PATCH/DELETE | `/events/staged/{id}` | user | Manage one of your staged submissions |
| GET/PATCH | `/auth/me` | user | Read / update the current user's profile |
| POST | `/auth/subscribe` | — | Subscribe an email to the newsletter |
| GET/POST | `/businesses` | user | List all published businesses / create a business profile |
| GET | `/businesses/me` | user | Current user's business profile |
| GET/PATCH/DELETE | `/businesses/{uuid}` | user | Read / update / delete a business profile |
| POST | `/api/cron/ingest` | CRON_SECRET | Trigger ingestion pipeline |
| POST | `/api/events/publish-approved` | API key | Publish all approved staged events |

Auth signup/login/logout are handled by Better Auth in Next.js at `/api/auth/*`, not Django.

## Quick Start

```bash
cd backendServer && uv sync && python manage.py migrate && python manage.py runserver
```

For end-to-end auth, also run the frontend so the JWKS endpoint resolves.

### Redis + Celery (async tasks)

Background tasks run on Celery, brokered by Redis (`REDIS_URL` in `.env`). Install
a local Redis once:

- **macOS:** `brew install redis && brew services start redis`
- **Ubuntu:** `sudo apt install redis-server`

To run async tasks locally, start a worker alongside `runserver`:

```bash
uv run celery -A backend worker -l info
```

Scheduled jobs use `django-celery-beat` (DB-backed, editable in the admin) driven
by a separate `celery -A backend beat` process. See
[`docs/redis-celery-handoff.md`](../docs/redis-celery-handoff.md) for the full
setup and prod ops.

## Testing

Always run the suite under the dedicated test settings:

```bash
DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test
```

`backend/settings/test.py` inherits `dev.py` (so it parses `DATABASE_URL` and
uses **Postgres** — a locked decision, not SQLite). Django auto-creates a
throwaway `test_<dbname>`. It also forces local-memory cache, eager Celery (no
Redis/worker needed), a fast password hasher, and stubbed external-service keys.

The `neon_auth.*` mirrors are `managed = False`, so the normal test-DB setup
skips them. `backend/test_runner.py` (`NeonAuthTestRunner`, wired via
`TEST_RUNNER`) creates the `neon_auth` schema and `user` table once, centrally —
no test class should re-create it.

Shared helpers live in `events/tests/factories.py` (`make_user`, `make_town`,
`make_event` — plain functions, no `factory_boy`).

### Tiers

Tests are tagged so you can run a subset:

| Tag | Meaning | Command |
|-----|---------|---------|
| `fast` | Pure logic, **no DB** — plain `unittest.TestCase` | `... manage.py test --tag=fast` |
| `db`   | Needs the Postgres test DB | `... manage.py test --tag=db` |

`--tag=fast` skips DB setup entirely (Django reports "Skipping setup of unused
database(s)"), so it's the quick inner-loop check.

> Neon note: `settings/test.py` rewrites the DB host to Neon's **direct**
> endpoint (strips `-pooler`). The pooler (PgBouncer) can't `DROP DATABASE`, so
> teardown otherwise fails with "database is being accessed by other users".
