# backendServer — Agent Map

Django 6 + DRF backend. Python 3.13, managed by `uv`. Four apps: `events` (public API + digests), `ingestion` (LLM pipeline), `broadcast` (event syndication), `backend` (config + auth bridge + Celery). Database is Postgres on Neon. Async on Redis + Celery; broadcast dispatch is on-demand Celery too, routed to its own single-concurrency `broadcast` queue (mirrors the `scrape` queue) rather than a polling worker. See [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for cross-cutting detail.

## Directory Map

```
backendServer/
├── manage.py
├── backend/                       # Project config
│   ├── settings/                  #   base / dev / prod / test
│   ├── urls.py                    #   Root URLconf (cron, publish, auth/me, businesses, admin)
│   ├── celery.py                  #   Celery app factory + autodiscover
│   ├── jwt_auth.py                #   BearerTokenAuthentication — Better Auth JWKS (TTL + stale-grace)
│   ├── permissions.py             #   DRF auth/permission classes (JWT, API key)
│   └── test_runner.py             #   NeonAuthTestRunner — builds neon_auth schema for tests
├── events/                        # Public app
│   ├── models.py                  #   Event/Town/Tag/Category/UserProfile/BusinessProfile/Newsletter
│   │                              #     + 5 BetterAuth* mirrors (managed=False)
│   ├── views.py / serializers.py / urls.py
│   ├── cache.py                   #   Version-keyed Redis cache for hot read endpoints
│   ├── signals.py                 #   Cache invalidation on Event/Town/Category writes
│   ├── tasks.py                   #   Celery: ping, send_one_digest, fan_out_weekly_digest, fan_out_monthly_digest
│   ├── email_service.py           #   Brevo transactional email + digest builder
│   └── management/commands/       #   devserver, seed_dev, healthcheck, delete_user, send_*digest
├── ingestion/                     # Pipeline app
│   ├── models.py                  #   EventSource, RawEvent, StagedEvent
│   ├── importers/ics_importer.py  #   ICS feed → RawEvent (shardable)
│   ├── standardizer.py            #   Gemini: RawEvent → StagedEvent
│   ├── deduplicator.py            #   Fuzzy dedup (thefuzz)
│   ├── safety_scorer.py           #   Gemini content-safety scoring
│   ├── services.py                #   publish_all_approved, auto_publish_safe_events
│   ├── tasks.py                   #   Celery: run_ingestion_pipeline, publish_all_approved_task
│   ├── views.py                   #   cron_ingest, publish, admin doc pages
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
├── templates/                     # admin docs pages (docs/) + email digests (email/)
└── pyproject.toml / uv.lock
```

## API Endpoints

Auth: `—` public · `user` Better Auth JWT · `key` `THE_COMMONS_API_KEY` · `tier≥N` broadcast tier (Bearer JWT or `X-Broadcast-Access-Code`, resolved by `broadcast/access.py`). `APPEND_SLASH=False` — slashes are exact. No global DRF config; auth/permissions are per-view.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/events/` | — | Published events (window/category filters, cached) |
| GET | `/events/towns/` · `/events/categories/` | — | Town / category lists (cached) |
| GET | `/events/me/profile` · `/events/me/events` | user | Own profile / own events |
| GET/PATCH/DELETE | `/events/staged/<int>` | user | Manage own staged submission |
| GET/DELETE | `/events/<uuid>` | user (delete) | Event detail / owner delete |
| POST | `/events/create` | user or key | Submit event → StagedEvent |
| GET/PATCH | `/auth/me` | user | Read / update profile |
| POST | `/newsletter/subscribe` | — | Newsletter signup (welcome email + manage link) |
| GET/PATCH | `/newsletter/manage` | — (token) | View / change a subscription via `?token=<manage_token>` |
| GET/POST | `/businesses` · `/businesses/me` · `/businesses/<uuid>` | user | Business listing CRUD |
| GET | `/api/cron/ingest` | CRON_SECRET | Queue ingestion pipeline |
| POST | `/api/events/publish-approved` | key | Queue bulk publish |
| GET | `/broadcast/access` | — | Caller's tier + trial metadata (403 for invalid creds) |
| POST | `/broadcast/preview` · `/submit` | tier≥1 | Preview eligible sites / enqueue submission |
| POST | `/broadcast/ai-autofill` | tier≥2 | LLM field extraction from free text |
| POST | `/broadcast/direct-recipe` | tier≥1 | Recipe JSON for a site (no job) |
| GET/POST | `/broadcast/jobs/<uuid>[/retry\|/submit-real\|/cancel]` | tier≥1 | Job status + lifecycle ops |
| GET | `/broadcast/jobs/<uuid>/screenshots/<key>` · `/manual/<key>` | tier≥1 | Screenshot / manual-review recipe |
| GET/POST | `/admin/docs/...` · `/admin/` | staff | Docs pages + django-unfold admin |

## Management Commands

- **events:** `devserver` (auto-port runserver), `seed_dev`, `healthcheck [--json]`, `delete_user --email`, `send_digest`, `send_test_digest --email`, `send_weekly_digest`.
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

`devtools/` (dev-only, `DEBUG`-gated — 404s in prod) hosts the ingestion playground and
the `/devtools/monitor` funnel dashboard + dry-run probe. See
[`../docs/ingestion-monitoring.md`](../docs/ingestion-monitoring.md) for funnel/health
semantics, `SourceRun` statuses, the probe's SSE contract, and the prod read-only setup
(`PROD_DATABASE_URL`).

## Quick Start

```bash
cd backendServer && uv sync && python manage.py migrate && python manage.py runserver
```

`migrate` after model changes — **never** for `neon_auth` mirrors (`managed = False`). Conventions: [`../CODING_STYLE.md`](../CODING_STYLE.md).
