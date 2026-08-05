# backendServer — Agent Map

Django 6 + DRF backend. Python 3.13, managed by `uv`. Six apps: `accounts` (identity/auth-bridge), `events` (public event API), `newsletter` (subscriptions + digest engine), `ingestion` (LLM pipeline), `broadcast` (event syndication), `backend` (config + Celery, no domain logic). `devtools` is a seventh, dev/test-only app (see below). Database is Postgres on Neon. Async on Redis + Celery; broadcast dispatch is on-demand Celery too, routed to its own single-concurrency `broadcast` queue (mirrors the `scrape` queue) rather than a polling worker. See [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for cross-cutting detail.

**Isolation contract:** no app imports from `broadcast`. Nothing imports from `ingestion` **except `events`**, which owns the user-submission endpoints (`post_event`, `manage_staged_event`, `get_my_events`) and therefore reads and writes `ingestion.models.StagedEvent` directly — a deliberate, long-standing overlap, since a user-submitted event enters the same staging table the pipeline feeds. `accounts`, `newsletter`, and `events` may likewise read each other where the domain genuinely overlaps — e.g. `accounts.me` writes a `NewsletterSubscriber` row (email-preference sync), and `newsletter._build_recipients` reads `accounts.UserProfile` (tag-filtered digests). All of these directions are deliberate. Enforced by `accounts/tests/test_isolation_fast.py` and `newsletter/tests/test_isolation_fast.py` — note `events` has **no** isolation test, so its import surface is unguarded.

## Directory Map

```
backendServer/
├── manage.py
├── backend/                       # Project config — no domain logic, include()-only urlconf
│   ├── settings/                  #   base / dev / prod / test
│   ├── urls.py                    #   Root URLconf — include()s accounts/events/newsletter/ingestion/broadcast.urls
│   │                              #     (+ admin, + DEBUG-gated devtools.urls); no `from <app>.views import ...`
│   ├── celery.py                  #   Celery app factory + autodiscover
│   ├── jwt_auth.py                #   BearerTokenAuthentication — Better Auth JWKS (TTL + stale-grace)
│   ├── permissions.py             #   DRF auth/permission classes (JWT, API key) — imports BetterAuthUser from accounts.models
│   └── test_runner.py             #   NeonAuthTestRunner — builds neon_auth schema for tests
├── accounts/                      # Identity/auth-bridge app
│   ├── models.py                  #   5 BetterAuth* mirrors (managed=False, neon_auth.*) + UserProfile/BusinessProfile
│   │                              #     (both OneToOne→BetterAuthUser; a "business" is a kind of user profile)
│   ├── views.py / serializers.py / urls.py  #   me (/auth/me), businesses, my_business, business_detail (/businesses...)
│   ├── permissions.py             #   Isolation-contract docstring (no permission classes yet)
│   └── tests/test_isolation_fast.py
├── events/                        # Public event app (slimmed)
│   ├── models.py                  #   Tag, Town, Category, Event
│   ├── views.py / serializers.py / urls.py  #   get_all, get_one, get_towns, get_categories, create_event,
│   │                              #     manage_staged_event, get_my_events, get_my_profile
│   ├── cache.py                   #   Version-keyed Redis cache for hot read endpoints
│   ├── signals.py                 #   Cache invalidation on Event/Town/Category writes
│   ├── tasks.py                   #   Celery: ping (digest tasks moved to newsletter/tasks.py)
│   ├── email_service.py           #   Generic Brevo transport (send_email) — used by non-digest commands
│   └── management/commands/       #   devserver, seed_dev, healthcheck, delete_user
├── newsletter/                    # Subscriptions + digest engine
│   ├── models.py                  #   NewsletterSubscriber
│   ├── views.py / urls.py         #   subscribe (/newsletter/subscribe), newsletter_manage (/newsletter/manage)
│   ├── email_service.py           #   _build_recipients, send_digest, digest_window, manage_url_for, send_newsletter_welcome
│   ├── tasks.py                   #   Celery: send_one_digest, fan_out_weekly_digest, fan_out_monthly_digest
│   ├── templates/email/           #   Digest + welcome email templates
│   ├── management/commands/       #   send_digest, send_weekly_digest, send_test_digest
│   └── tests/test_isolation_fast.py
├── ingestion/                     # Pipeline app
│   ├── models.py                  #   EventSource, RawEvent, StagedEvent
│   ├── importers/ics_importer.py  #   ICS feed → RawEvent (shardable)
│   ├── standardizer.py            #   Gemini: RawEvent → StagedEvent
│   ├── deduplicator.py            #   Fuzzy dedup (thefuzz)
│   ├── safety_scorer.py           #   Gemini content-safety scoring
│   ├── services.py                #   publish_all_approved, auto_publish_safe_events
│   ├── tasks.py                   #   Celery: run_ingestion_pipeline, publish_all_approved_task
│   ├── views.py / urls.py         #   cron_ingest, publish_approved_events, direct_submit, pipeline/admin doc pages
│   │                              #     (own urlconf: admin/docs/*, api/cron/ingest, api/events/publish-approved, direct-submit)
│   └── management/commands/       #   ingest_events, cleanup_old_events
├── broadcast/                     # Event syndication (see ../docs/broadcast.md)
│   ├── models.py                  #   BroadcastSubmission, BroadcastTarget, BroadcastAccess, AccessCode, AccessCodeUse
│   ├── schema.py / routing.py     #   CanonicalEvent (ORM-decoupled); tag-based eligibility
│   ├── services.py / worker.py    #   Submission persistence + on-demand Celery dispatch; queue drain (SKIP LOCKED)
│   ├── tasks.py                   #   Celery: process_broadcast_queue, recover_broadcast_orphans (routed to `broadcast` queue)
│   ├── runner.py                  #   sync_playwright runner (no ORM inside)
│   ├── views.py / serializers.py / permissions.py / access.py
│   ├── adapters/                  #   One module per target site (10 Tier-1 + mock) + registry
│   └── management/commands/       #   run_broadcast_worker (--once debug helper), broadcast_dry_run, capture_broadcast_form,
│                                  #     check_recipes, scaffold_adapter, set_broadcast_access,
│                                  #     generate_access_code, list_access_codes, revoke_access_code
├── devtools/                      # Dev-only app (INSTALLED_APPS only under dev/test settings; DEBUG-gated in urls)
│   ├── views/                     #   Package: playground.py, probe.py, monitor.py, _shared.py, __init__.py (re-exports)
│   └── urls.py
├── templates/                     # admin docs pages (docs/) — email digest templates now live in newsletter/templates/email/
└── pyproject.toml / uv.lock
```

## API Endpoints

Auth: `—` public · `user` Better Auth JWT · `key` `THE_COMMONS_API_KEY` · `tier≥N` broadcast tier (Bearer JWT or `X-Broadcast-Access-Code`, resolved by `broadcast/access.py`). `APPEND_SLASH=False` — slashes are exact. No global DRF config; auth/permissions are per-view. `backend/urls.py` is `include()`-only — every route below is owned by the app it's grouped under.

### accounts (`accounts/urls.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET/PATCH | `/auth/me` | user | Read / update own profile |
| GET/POST | `/businesses` · `/businesses/me` · `/businesses/<uuid>` | user | Business listing CRUD |

### events (`events/urls.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/events/` | — | Published events (window/category filters, cached) |
| GET | `/events/towns/` · `/events/categories/` | — | Town / category lists (cached) |
| GET | `/events/me/profile` · `/events/me/events` | user | Own profile / own events |
| GET/PATCH/DELETE | `/events/staged/<int>` | user | Manage own staged submission |
| GET/DELETE | `/events/<uuid>` | user (delete) | Event detail / owner delete |
| POST | `/events/create` | user or key | Submit event → StagedEvent |

### newsletter (`newsletter/urls.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/newsletter/subscribe` | — | Newsletter signup (welcome email + manage link) |
| GET/PATCH | `/newsletter/manage` | — (token) | View / change a subscription via `?token=<manage_token>` |

### ingestion (`ingestion/urls.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/cron/ingest` | CRON_SECRET | Queue ingestion pipeline |
| POST | `/api/events/publish-approved` | key | Queue bulk publish |
| POST | `/api/events/direct-submit` | JWT optional | Direct host event submission (broadcast SPA) |
| GET/POST | `/admin/docs/pipeline-docs/` · `/admin/docs/admin-docs/` · `/admin/docs/publish-approved/` | staff | Pipeline/admin docs pages + publish-approved button |

### broadcast (`broadcast/urls.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/broadcast/access` | — | Caller's tier + trial metadata (403 for invalid creds) |
| POST | `/broadcast/preview` · `/submit` | tier≥1 | Preview eligible sites / enqueue submission |
| POST | `/broadcast/ai-autofill` | tier≥2 | LLM field extraction from free text |
| POST | `/broadcast/direct-recipe` | tier≥1 | Recipe JSON for a site (no job) |
| GET/POST | `/broadcast/jobs/<uuid>[/retry\|/submit-real\|/cancel]` | tier≥1 | Job status + lifecycle ops |
| GET | `/broadcast/jobs/<uuid>/screenshots/<key>` · `/manual/<key>` | tier≥1 | Screenshot / manual-review recipe |

### admin

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET/POST | `/admin/` | staff | django-unfold admin |

## Management Commands

- **events:** `devserver` (auto-port runserver), `seed_dev`, `healthcheck [--json]`, `delete_user --email`.
- **newsletter:** `send_digest`, `send_weekly_digest`, `send_test_digest --email`.
- **ingestion:** `ingest_events` (full pipeline; `--skip-*`, `--shard N/M`), `cleanup_old_events`.
- **broadcast:** `run_broadcast_worker [--once]` (debug helper — drains one submission without Celery, not a service entrypoint), `broadcast_dry_run --site --fixture`, `capture_broadcast_form <site>`, `check_recipes [--live]`, `scaffold_adapter --url --key`, `set_broadcast_access <email> <0|1|2>`, `generate_access_code [--tier] [--label] [--expires] [--uses|--unlimited]`, `list_access_codes`, `revoke_access_code <label|id>`.

## Redis + Celery (local)

One Redis instance: **DB 0** = Celery broker + results (`REDIS_URL`), **DB 1** = Django cache (`REDIS_CACHE_URL`). Beat schedules live in Postgres (`django_celery_beat`, seeded by migrations). Run alongside `runserver`:

```bash
uv run celery -A backend worker -l info              # async tasks (digests, ingestion)
uv run celery -A backend beat -l info                # scheduler
uv run celery -A backend worker -Q broadcast -c 1 -l info   # dedicated broadcast queue (on-demand dispatch)
```

`BROADCAST_AUTOSPAWN_WORKER` no longer exists — broadcast dispatch is on-demand Celery
(`transaction.on_commit(process_broadcast_queue.delay)`, routed to the `broadcast`
queue), so without the worker above running (or `CELERY_TASK_ALWAYS_EAGER=True`, as
`settings/test.py` sets), broadcast jobs enqueue but never drain locally.

See [`../docs/redis-celery-handoff.md`](../docs/redis-celery-handoff.md) and [`../docs/broadcast.md`](../docs/broadcast.md).

## Testing

Always under the test settings (Postgres, never SQLite). `NeonAuthTestRunner` creates the `neon_auth` schema + mirror tables; fast-only runs skip DB setup. Two tiers via `@tag`: `fast` (no-DB, `*_fast.py`) and `db` (`*_db.py`). Helpers in `events/tests/factories.py`. `settings/test.py` strips `-pooler` from the DB host so the throwaway test DB hits Neon's direct endpoint.

```bash
DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test            # full
DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test --tag=fast # no-DB
DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test --tag=db   # DB
```

> Note: all `broadcast/tests/` files are now tagged `fast`/`db` and run in CI (a prior gap where 10 of 12 files carried no `@tag` — including the rate-limit tests — let two prod-only bugs ship undetected). `ingestion/tests/test_pipeline_db.py` (formerly untagged `test_pipeline.py`) is now tagged `db` and runs in CI.

## Devtools

`devtools/` (registered in `INSTALLED_APPS` only under dev/test settings; still `DEBUG`-gated
in urls — 404s in prod either way) hosts the ingestion playground and the `/devtools/monitor`
funnel dashboard + dry-run probe. `devtools/views.py` is a package (`devtools/views/`) split
by concern: `playground.py`, `probe.py`, `monitor.py`, `_shared.py`, with `__init__.py`
re-exporting the view functions `devtools/urls.py` routes to. See
[`../docs/ingestion-monitoring.md`](../docs/ingestion-monitoring.md) for funnel/health
semantics, `SourceRun` statuses, the probe's SSE contract, and the prod read-only setup
(`PROD_DATABASE_URL`).

## Quick Start

```bash
cd backendServer && uv sync && python manage.py migrate && python manage.py runserver
```

`migrate` after model changes — **never** for `neon_auth` mirrors (`managed = False`). Conventions: [`../CODING_STYLE.md`](../CODING_STYLE.md).
