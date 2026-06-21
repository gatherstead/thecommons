# Redis + Celery — Handoff

How async tasks and scheduled jobs run on The Commons. Read this before adding a
background task, a scheduled job, or touching the worker/beat services.

## Why this exists

Before this, background work ran two ways: the bespoke broadcast Playwright worker
(polls Postgres directly) and external cron hitting HTTP endpoints
(`/api/cron/ingest`). There was no general task queue. Redis + Celery gives any
Django app a place to define async tasks (`@shared_task`) and DB-backed schedules,
so we can move the OS-cron jobs (`ingest_events`, `send_weekly_digest`) onto Celery
beat in later tickets.

## Architecture

- **One self-hosted Redis** on the VM (single Oracle Cloud box, 6 GB RAM). Bound to
  `127.0.0.1`, password-protected, `maxmemory 512mb` / `allkeys-lru`.
  - **DB 0** — Celery broker **and** result backend (`REDIS_URL`).
  - **DB 1** — Django cache for hot read endpoints (`REDIS_CACHE_URL`). Wired in
    ticket 14.4 — see "Read-endpoint cache" below.
- **Celery worker** and **Celery beat** run as separate systemd services on the VM,
  mirroring the gunicorn/nextjs pattern (run as `ubuntu`, `Restart=on-failure`).
  Exactly one beat process.
- **Scheduling** uses `django-celery-beat` (`DatabaseScheduler`): schedules live in
  Postgres and are editable in the django-unfold admin — not in code.

## Where things live

| Thing | Path |
|-------|------|
| Celery app bootstrap | `backendServer/backend/celery.py` |
| App load (`celery_app` import) | `backendServer/backend/__init__.py` |
| Config (`CELERY_*`, `REDIS_URL`) | `backendServer/backend/settings/base.py` |
| Worker service template | `deploy/celery.service` |
| Beat service template | `deploy/celerybeat.service` |
| Env var | `REDIS_URL` in `.env` (`.env.example` documents it) |

`backend/celery.py` sets `DJANGO_SETTINGS_MODULE=backend.settings` (the settings
package dispatches dev/prod on `DJANGO_ENV`), reads config with the `CELERY_`
namespace, and calls `autodiscover_tasks()`.

## Conventions

- **Tasks** go in each app's `tasks.py` as `@shared_task` functions.
  `autodiscover_tasks()` finds them automatically — no registration needed.
- **Enqueue** with `my_task.delay(...)` or `.apply_async(...)`.
- **Schedules** are **seeded by a data migration** (one `CrontabSchedule` +
  `PeriodicTask` per job), then live in Postgres and are read live by the
  `DatabaseScheduler`. See "Beat schedules" below. (Earlier tickets used the admin
  directly; the migration approach keeps the canonical schedule version-controlled.)
- **Result backend** is Redis DB 0; `.get()` works for the ping smoke test but
  prefer fire-and-forget for real tasks.

## Beat schedules

Periodic jobs are seeded by data migrations so the canonical schedule deploys with
the code and reproduces on a fresh DB. Current entries:

| Task | Path | Schedule (seeded by) |
|------|------|----------------------|
| Ingestion pipeline | `ingestion.tasks.run_ingestion_pipeline` | 04:00 daily, `America/New_York` (`ingestion/migrations/0007_seed_ingest_beat.py`) |
| Weekly digest fan-out | `events.tasks.fan_out_weekly_digest` | Sundays 18:00, `America/New_York` (`events/migrations/0015_seed_digest_beat.py`) |

The `CrontabSchedule.timezone` is set to `America/New_York` (not UTC) so beat tracks
US-Eastern DST exactly like the OS cron these replaced.

**Changing a schedule:** the migration only *seeds* the row on first apply — it does
**not** re-assert on every deploy. To change a time, day, enable/disable, or trigger a
one-off run, edit the entry live in the django-unfold admin under **Periodic Tasks**
(and its **Crontab**); changes take effect on the next beat tick, no deploy needed.
Editing the migration only affects DBs that haven't applied it yet, so for a permanent
change you'd update *both* the admin (live) and the migration (future fresh installs).

## Read-endpoint cache (DB 1)

The three hottest unauthenticated GETs are cached in Redis DB 1 to cut Neon round
trips: `getAll` (`/events/`), `getTowns`, `getCategories` (`events/views.py`).

- **Backend:** Django 6 stdlib `django.core.cache.backends.redis.RedisCache` (uses
  redis-py, already a dep — no `django-redis`). Configured as `CACHES['default']`
  in `settings/base.py` at `REDIS_CACHE_URL`.
- **Event list** (`events/cache.py`): cached per request under a key built from the
  sorted query params, **TTL 60s**. Keys are namespaced by a **version number**
  (`events:list:v{N}:{hash}`) because the stdlib backend has no `delete_pattern`.
- **Towns / categories:** plain keys (`events:towns`, `events:categories`),
  **TTL 1h** — near-static, refreshed only via admin/pipeline.
- **Invalidation** (`events/signals.py`, registered in `EventsConfig.ready()`):
  `Event` post_save/post_delete bumps the list version (`cache.incr`); `Town` /
  `Category` post_save/post_delete clears their own keys. Bulk publishing fires
  per-`Event.objects.create()`, so the version bumps as rows land — acceptable
  given the 60s TTL.
- **Tuning:** bump `EVENTS_LIST_TTL` (currently 60s) toward 5min if Neon load stays
  high. Inspect keys in dev with `redis-cli -n 1 KEYS 'events:*'`.
- **Tests** swap in `LocMemCache` (see `dev.py`'s `'test' in sys.argv` guard), so
  the suite needs no running Redis.

## Testing

The test suite runs under dev settings, where `CELERY_TASK_ALWAYS_EAGER = False`.
Tests that need synchronous execution wrap the call:

```python
from django.test import override_settings

@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_my_task():
    my_task.delay()  # runs inline, exceptions propagate
```

## Local dev

```bash
brew install redis && brew services start redis      # macOS (Ubuntu: apt install redis-server)
redis-cli ping                                       # → PONG

cd backendServer
uv sync
uv run python manage.py migrate                      # django_celery_beat_* tables
printf 'REDIS_URL=redis://localhost:6379/0\nREDIS_CACHE_URL=redis://localhost:6379/1\n' >> .env

# Run a worker alongside runserver
uv run celery -A backend worker -l info
```

## Prod ops (VM)

**Provision Redis:**

```bash
sudo apt update && sudo apt install -y redis-server
openssl rand -hex 32                                 # generate a password
sudo nano /etc/redis/redis.conf                      # bind 127.0.0.1 -::1; requirepass <pass>;
                                                     #   maxmemory 512mb; maxmemory-policy allkeys-lru
sudo systemctl enable --now redis-server
sudo systemctl restart redis-server
redis-cli -a '<password>' PING                       # → PONG
```

**Env (`backendServer/.env`):** the password lives here, never in git.

```
REDIS_URL=redis://:<password>@127.0.0.1:6379/0       # note the leading ':' — no username
REDIS_CACHE_URL=redis://:<password>@127.0.0.1:6379/1  # read-endpoint cache (DB 1)
```

**Celery services:**

```bash
cd /home/ubuntu/thecommons && git pull
cd backendServer && uv sync && uv run python manage.py migrate

cd /home/ubuntu/thecommons
sudo cp deploy/celery.service deploy/celerybeat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now celery celerybeat

sudo systemctl status celery celerybeat
sudo journalctl -u celery -n 20                      # broker connection + registered tasks
```

After deploying task-code or dependency changes:
`sudo systemctl restart celery celerybeat`.

**Verify the whole stack at once:**

```bash
bash deploy/healthcheck.sh        # ✓/!/✗ for RAM, disk, all units, Redis, DB, worker, beat
```

This is the fastest way to confirm beat is actually firing: the Application section
runs `manage.py healthcheck`, which reports each `PeriodicTask`'s `enabled` flag and
`last_run_at` freshness (daily stale after ~25h, weekly after ~8d) and flags any
leftover OS-cron `ingest_events`/`send_weekly_digest` entries that would double-run.
Exits non-zero on any critical failure. Details in [DEPLOY.md](../DEPLOY.md#health-check).

## Next steps

- **Done (14.5/14.6/14.7):** ingestion pipeline (`run_ingestion_pipeline`), weekly
  digest fan-out (`fan_out_weekly_digest` → per-recipient `send_one_digest`), and bulk
  publish (`publish_all_approved_task`) now run on Celery; beat owns their schedules.
  The OS-cron entries for `ingest_events` and `send_weekly_digest` must be removed from
  the VM — see DEPLOY.md.
- Future: split the ingestion pipeline into a per-step Celery chain for finer-grained
  retries (currently the whole pipeline retries on any step failure).
- Consider caching `/businesses` or other read endpoints on DB 1 if they get hot
  (same version-key pattern as the event list).
- Revisit self-hosted vs managed Redis only if we ever go multi-node (losing the VM
  currently means losing the broker).
