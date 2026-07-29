# Deployment Runbook — The Commons

This is the single source of truth for deploying The Commons to the production VM.
Follow **Part 1** top-to-bottom for the **first deploy** of the new
Redis/Celery/broadcast/CI infrastructure (the VM does not have it yet). After that,
deploys are automatic — see **Part 2**. **Part 3** is reference (services, env vars,
nginx, firewall, troubleshooting).

---

## Facts you need first

| Thing | Value |
|-------|-------|
| Provider / OS | Oracle Cloud (OCI), Ubuntu 24.04, ARM64 (aarch64), 1 OCPU / 6 GB |
| VM IP | `129.80.229.41` |
| SSH | `ssh -i oraclevps.key ubuntu@129.80.229.41` (key is in repo root — **never commit it**) |
| Repo path on VM | `/home/ubuntu/thecommons` |
| Deploy user | `ubuntu` (all services run as `ubuntu`) |
| Python | **`uv`** at `/snap/bin/uv` — never `pip` — but **only for one-shot commands** (`uv sync`, `manage.py migrate`, etc.); long-lived systemd units exec `.venv/bin/<binary>` directly, never `uv run` (see §4) |
| Node | **`pnpm`** — never `npm install` (it breaks peer-dependency pinning) |
| DNS / TLS | Cloudflare, proxied (orange cloud), SSL mode **Full (strict)**; origin cert at `/etc/ssl/cloudflare/thecommons.town.{pem,key}` |

> **What changed since `main`:** this release adds Redis, a Celery worker + beat
> scheduler, the broadcast worker (Playwright), a healthcheck, and a CI/CD
> auto-deploy. The ingestion and weekly-digest jobs **moved off OS cron** onto
> `django-celery-beat` (a DB-backed scheduler seeded by migrations). If you followed
> any older notes that set up `crontab`/`logrotate`/`/var/log/thecommons` for those
> two jobs, that approach is **dead** — Part 1 §9 retires it.

---

# Part 1 — First deploy (manual, one time)

Do these in order. The CI auto-deploy in Part 2 **cannot** succeed until this is
done, because it restarts `celery`/`celerybeat`/`broadcast-worker`/`scrape-worker`,
which don't exist on the box yet.

## 1. Pull the new code onto the VM

```bash
ssh -i oraclevps.key ubuntu@129.80.229.41
cd /home/ubuntu/thecommons
git fetch origin
git checkout testing+ci && git pull origin testing+ci
```

> You provision from the `testing+ci` branch now. In §10 you'll switch the VM to
> `main` so CI's `git pull` tracks the right branch going forward.

## 2. Provision Redis (one time)

```bash
sudo apt update && sudo apt install -y redis-server
openssl rand -hex 32                       # copy the output — this is <REDIS_PASS>
sudo nano /etc/redis/redis.conf            # set the four lines below
```

In `/etc/redis/redis.conf` set:

```
bind 127.0.0.1 -::1
requirepass <REDIS_PASS>
maxmemory 512mb
maxmemory-policy allkeys-lru
```

```bash
sudo systemctl enable --now redis-server && sudo systemctl restart redis-server
redis-cli -a '<REDIS_PASS>' PING           # → PONG
```

One Redis instance, two logical DBs: **DB 0** = Celery broker + results, **DB 1** =
read-endpoint cache. The password lives **only** in `backendServer/.env`, never in git.

## 3. Backend — env, deps, migrate, static

Edit `backendServer/.env` and add the Redis URLs (note the **leading `:`** and no
username). Full env reference is in Part 3.

```
REDIS_URL=redis://:<REDIS_PASS>@127.0.0.1:6379/0
REDIS_CACHE_URL=redis://:<REDIS_PASS>@127.0.0.1:6379/1
INGEST_SHARD_COUNT=3        # optional — spreads source polling across 3 days; set 1 or omit to poll all daily
```

**`INGEST_SHARD_COUNT=3` is a deliberate prod setting — keep it at 3.** `_resolve_env_shard`
(`backendServer/ingestion/tasks.py:22-39`) polls only the sources where
`id % INGEST_SHARD_COUNT == day_of_year % INGEST_SHARD_COUNT`, so with a shard count
of 3 any given source is actually polled roughly every **72 hours**, not the 24h its
own `poll_interval_hours` implies — sharding is disabled (all sources polled daily)
only when the var is unset, fails to parse as an int, or is `<= 1`. Two consequences
to keep in mind:

- A source that fails transiently gets **1/3 as many chances** to recover before the
  next poll compared to unsharded daily polling.
- Monitoring/alerting thresholds must be shard-aware — a source that looks "3 days
  stale" is expected and healthy under this setting, not a symptom of an outage. (A
  companion ticket is making the ingestion monitor account for this.)

```bash
cd /home/ubuntu/thecommons/backendServer
/snap/bin/uv sync
/snap/bin/uv run python manage.py migrate            # also seeds the beat schedules
/snap/bin/uv run python manage.py collectstatic --noinput
```

The `migrate` step runs `ingestion/migrations/0007_seed_ingest_beat.py` (ingest,
04:00 ET daily) and `events/migrations/0015_seed_digest_beat.py` (digest, Sun
18:00 ET), which create the scheduled tasks in the database.

## 4. Celery worker + beat services (one time)

**The `uv` rule for this project has two cases — don't collapse them:**

- **One-shot commands** (`uv sync`, `uv run python manage.py migrate`, `playwright
  install`, etc.) — always go through `/snap/bin/uv`. That part of the Facts table
  above is unchanged.
- **Long-lived systemd units** (`celery`, `celerybeat`, `scrape-worker`,
  `broadcast-worker`) — **never** `uv run`. They exec the venv binary directly,
  `/home/ubuntu/thecommons/backendServer/.venv/bin/celery …`, the same pattern
  `gunicorn` has always used (`.venv/bin/gunicorn`). This is not a style preference:
  snap-packaged `uv run` spawns its child process inside a transient
  `snap.astral-uv.uv-*.scope` under `user@1001.service` — the *user* manager, not the
  unit's own cgroup. With `Linger=no`, systemd-logind tears down that user slice the
  moment the deploying SSH session ends, and the child (celery/beat) receives SIGTERM
  and performs a clean warm shutdown — **`status=0/SUCCESS`**, which
  `Restart=on-failure` correctly declines to restart. That is exactly how the async
  stack died silently on 2026-07-21 12:46 UTC and stayed down for 8 days while the
  site looked healthy: every `uv run`-based unit died within a minute of the deploy
  session ending; `gunicorn` (execs its venv binary) and `nextjs` (`/usr/bin/npm`)
  never went through snap and stayed up 68 days straight. See
  `docs/prod-incident-2026-07-21-scheduler-outage.md` for the full forensics.

Two complementary mitigations are now in place, not alternatives — keep both:

1. **`.venv/bin/celery` in `ExecStart`** (all four unit files) removes the mechanism
   entirely — the process never lands in a user-manager slice, so there's nothing for
   a lost SSH session to tear down.
2. **`Restart=always`** (all four units) + **linger enabled for `ubuntu`** are
   defense-in-depth, in case a unit is ever reverted to `uv run` or linger is somehow
   turned back off:
   ```bash
   sudo loginctl enable-linger ubuntu
   loginctl show-user ubuntu --property=Linger    # must print Linger=yes
   ```

```bash
cd /home/ubuntu/thecommons
sudo cp deploy/celery.service deploy/celerybeat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now celery celerybeat
sudo systemctl status celery celerybeat              # both active (running)
sudo journalctl -u celery -n 30                      # should show "celery@... ready" + broker connected
```

Run **exactly one** beat process. The worker drains Redis DB 0; beat uses
`django-celery-beat`'s DatabaseScheduler, so schedules are editable later in the
Django admin.

**The real acceptance test is a full SSH login→logout cycle, not `systemctl
is-active` right after `enable --now`.** A unit that was just started by your current
session is active regardless of whether the underlying bug is fixed — that's the
exact false-positive that let this incident go unnoticed for 8 days. Log out
completely and reconnect fresh before you trust the result:

```bash
exit                                                  # close the SSH session completely
ssh -i oraclevps.key ubuntu@129.80.229.41 'systemctl is-active celery celerybeat scrape-worker broadcast-worker'
# all four must print "active" from a session that did NOT start them
```

Confirm every queue has a consumer. A queue with depth but no consumer is
silent — jobs enqueue and are never dispatched:

```bash
cd /home/ubuntu/thecommons/backendServer
uv run celery -A backend inspect active_queues | grep -o "'name': '[a-z]*'"   # expect celery, scrape, broadcast
```

## 5. Broadcast feature (one time)

The broadcast feature adds a third subdomain, a Playwright worker, and a static SPA.
Do all seven in order.

> **Local dev note:** `BROADCAST_AUTOSPAWN_WORKER` no longer exists — Suite 25 moved
> broadcast dispatch onto on-demand Celery (`transaction.on_commit(process_broadcast_queue.delay)`),
> so there's nothing to autospawn. To drain broadcast jobs locally, either run
> `celery -A backend worker -Q broadcast -c 1 -l info` alongside `runserver`, or set
> `CELERY_TASK_ALWAYS_EAGER=True` (as `settings/test.py` does) to execute tasks
> synchronously with no worker at all. See [`docs/broadcast.md`](docs/broadcast.md).

1. **TLS (do this first).** The existing origin cert covers only `thecommons.town`
   and `api.thecommons.town`. In the Cloudflare dashboard, reissue an origin cert
   for `thecommons.town, *.thecommons.town`, replace
   `/etc/ssl/cloudflare/thecommons.town.{pem,key}`, then:
   ```bash
   sudo nginx -t && sudo systemctl reload nginx
   ```
   Skipping this makes the subdomain fail with a Cloudflare 526 error.
2. **DNS.** Cloudflare → add an **A record** `broadcast` → `129.80.229.41`, proxied
   (orange cloud). An A record, not a CNAME.
3. **Playwright Chromium** (bundled only — arm64 has no branded Chrome):
   ```bash
   cd /home/ubuntu/thecommons/backendServer
   /snap/bin/uv run playwright install chromium
   /snap/bin/uv run playwright install-deps chromium     # apt system libs (uses sudo)
   ```
4. **Artifact dirs:**
   ```bash
   mkdir -p /home/ubuntu/broadcast/{screenshots,downloads}
   ```
5. **Env.** Add the `BROADCAST_*` block from `backendServer/.env.example` to
   `backendServer/.env`, and append `https://broadcast.thecommons.town` to both
   `CORS_EXTRA_ORIGINS` and `CSRF_TRUSTED_ORIGINS`.
6. **Worker service.** Broadcast dispatch is on-demand Celery, not a poll loop:
   the app calls `transaction.on_commit(process_broadcast_queue.delay)` on
   submit/retry, routed to a dedicated `broadcast` Celery queue
   (`CELERY_TASK_ROUTES` in `backend/settings/base.py`). `deploy/broadcast-worker.service`
   runs `celery -A backend worker -Q broadcast -c 1 -l info` — **`-c 1` is
   mandatory, not a tuning default**: `recover_orphans()` assumes any `running`
   submission at startup is orphaned, so a second concurrent worker could race
   a live queue-drain. A `broadcast-orphan-recovery` beat task (seeded by
   migration `0009_seed_orphan_recovery_beat.py`) sweeps orphaned submissions
   every 6 hours as a crash-recovery net; normal stalled-target recovery is
   client-driven from the SPA (`POST /broadcast/jobs/<id>/retry-stuck`) and
   doesn't involve this worker restarting.
   ```bash
   cd /home/ubuntu/thecommons
   sudo cp deploy/broadcast-worker.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now broadcast-worker
   ```
7. **nginx.** Add the server block from `deploy/nginx-broadcast.conf.snippet` into
   the **existing** `/etc/nginx/sites-available/thecommons` (one file, many `server`
   blocks — do not create a new sites-available file), then:
   ```bash
   sudo nginx -t && sudo systemctl reload nginx
   ```

## 6. Scrape worker (one time)

The ingestion scraper (`ingestion.tasks.scrape_all_sources_task`) renders headless
Chromium and is routed to a dedicated `scrape` Celery queue (`CELERY_TASK_ROUTES` in
`backend/settings/base.py`) so its memory never lands on the default `celery`
worker. `deploy/celery.service`'s `ExecStart` has no `-Q` flag (`celery -A backend
worker -l info --concurrency=2`), so the default worker only drains the `celery`
queue — it will **not** pick up `scrape` tasks. Without this dedicated worker,
scrape tasks queue forever.

1. **Playwright Chromium** (skip if already installed for broadcast — same shared
   cache):
   ```bash
   cd /home/ubuntu/thecommons/backendServer
   /snap/bin/uv run playwright install chromium
   /snap/bin/uv run playwright install-deps chromium     # apt system libs (uses sudo)
   ```
   Bundled Chromium only — **never** a branded "chrome" channel, unsupported on
   arm64. It installs into `/home/ubuntu/.cache/ms-playwright/`, shared with
   `broadcast-worker`, so there's no extra download if that's already in place.
2. **Env.** Add the three `INGEST_SCRAPER_*` vars to `backendServer/.env` if you
   want non-default values (all optional — see Part 3 for defaults).
3. **Worker service:**
   ```bash
   cd /home/ubuntu/thecommons
   sudo cp deploy/scrape-worker.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now scrape-worker
   sudo systemctl status scrape-worker      # active (running)
   ```

> ⚠️ **Operator ordering matters.** From this point on, `.github/workflows/ci.yml`'s
> `deploy` job restarts `scrape-worker` on every push to `main` (see §10/Part 2).
> If you haven't installed and `systemctl enable`d the unit (and run `playwright
> install chromium`) **before** the first deploy that includes this change, CI's
> `sudo -n systemctl restart ... scrape-worker` step will fail and block the
> deploy. Do steps 1–3 above first.

## 7. Frontend builds + restart

```bash
cd /home/ubuntu/thecommons/theCommonsWeb
pnpm install && pnpm run build
sudo systemctl restart nextjs

cd ../broadcastWeb
pnpm install && pnpm run build           # static → dist/, served directly by nginx (no service)

sudo systemctl restart gunicorn
```

## 8. Verify

```bash
cd /home/ubuntu/thecommons
UV_BIN=/snap/bin/uv bash deploy/healthcheck.sh        # everything should be ✓
```

Then smoke-test the two scheduled jobs by hand (they still exist as manual triggers):

```bash
sudo -u ubuntu bash -lc 'cd /home/ubuntu/thecommons/backendServer && /snap/bin/uv run python manage.py ingest_events --shard 0/3 --skip-standardize --skip-dedup --skip-safety --skip-autopublish'
sudo -u ubuntu bash -lc 'cd /home/ubuntu/thecommons/backendServer && /snap/bin/uv run python manage.py send_test_digest --email aryav@unc.edu'
curl -I https://broadcast.thecommons.town/            # expect 200/3xx
```

If the broadcast `curl` hangs, it's the iptables REJECT-before-ACCEPT gotcha — see
Part 3 §Firewall.

## 9. Retire the old OS cron (only if it exists)

Beat now owns the ingest + digest schedules. If the box still has the old cron
lines, remove them so the jobs don't run twice:

```bash
crontab -l                 # look for ingest_events / send_weekly_digest lines
crontab -e                 # delete those two lines if present
```

`healthcheck.sh` also flags leftover cron lines for these jobs.

## 10. Switch the VM to `main` and enable CI/CD

**On your laptop** — merge and push:

```bash
git checkout main && git merge testing+ci && git push origin main
```

**On the VM** — point it at `main` so CI's `git pull` works:

```bash
cd /home/ubuntu/thecommons && git checkout main && git pull
```

**Deploy SSH key (laptop):**

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy@thecommons" -f ~/.ssh/thecommons_deploy -N ""
cat ~/.ssh/thecommons_deploy.pub | ssh -i oraclevps.key ubuntu@129.80.229.41 \
  'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
ssh -i ~/.ssh/thecommons_deploy ubuntu@129.80.229.41 'echo deploy-key-ok'
```

**Sudoers drop-in (VM)** — passwordless restart for exactly the six units:

```bash
sudo visudo -f /etc/sudoers.d/deploy-restart
```

```
ubuntu ALL=(root) NOPASSWD: /usr/bin/systemctl restart gunicorn, \
                            /usr/bin/systemctl restart nextjs, \
                            /usr/bin/systemctl restart celery, \
                            /usr/bin/systemctl restart celerybeat, \
                            /usr/bin/systemctl restart broadcast-worker, \
                            /usr/bin/systemctl restart scrape-worker
```

**GitHub repo secrets** (Settings → Secrets and variables → Actions) — all four:

| Secret | Value |
|--------|-------|
| `ORACLE_SSH_KEY` | Full PEM **private** key (`~/.ssh/thecommons_deploy`, incl. BEGIN/END lines) |
| `ORACLE_HOST` | `129.80.229.41` (raw IP — Cloudflare won't proxy port 22) |
| `ORACLE_USER` | `ubuntu` |
| `ORACLE_KNOWN_HOSTS` | The **single** line from `ssh-keyscan -t ed25519 129.80.229.41` |

**Confirm the non-interactive PATH** sees the tools CI will call:

```bash
ssh -i ~/.ssh/thecommons_deploy ubuntu@129.80.229.41 'command -v uv; command -v pnpm; command -v node'
```

If `uv` isn't found, CI uses `/snap/bin/uv` (the workflow already accounts for this).

## 10. Trigger and verify the first automated deploy

The `deploy` job runs only on **push to `main`**, after `backend`,
`frontend-commons`, and `frontend-broadcast` pass.

- Push to `main` (or re-run the Action). Watch **Actions → CI**: three green test
  jobs → `deploy` starts.
- The `deploy` log should show each step: `git pull`, `uv sync`, `migrate`,
  `collectstatic`, both `pnpm` builds, the restart, and `is-active` lines all
  printing `active`.
- Confirm the VM is on the pushed commit:
  ```bash
  ssh -i ~/.ssh/thecommons_deploy ubuntu@129.80.229.41 \
    'cd /home/ubuntu/thecommons && git log -1 --oneline'
  ```

> **Budget 30–60 min for the first automated run.** It usually trips on something
> environmental (a PATH gap, a sudoers path mismatch, `--frozen-lockfile` drift).
> Read the failing step's log, fix on the VM or in the workflow, push again.

---

# Part 2 — Ongoing deploys (automatic)

Once Part 1 is done, **every push to `main`** runs CI (`.github/workflows/ci.yml`)
and, after all three test jobs pass, a gated `deploy` job SSHes into the VM and runs
the full sequence: `git pull` → `uv sync` → guarded `migrate` (below) → `collectstatic`
→ both frontend `pnpm install`/`build` → restart `gunicorn nextjs celery celerybeat
broadcast-worker scrape-worker`, then a post-deploy smoke test: all three domains, `/events/`,
auth probes (`/auth/me` with no/garbage token must 401/403 — never 500 — and the
API-key path must accept the real key), and a broadcast rate-limit regression check.
A failing test on `main` blocks the deploy.

> **Guarded migrate:** the deploy runs `migrate --check` first and skips `migrate`
> entirely when nothing is pending. When migrations *are* pending it logs the plan,
> takes a `pg_dump` to `/home/ubuntu/backups/pre-migrate-<timestamp>.sql.gz` (keeps
> the 5 newest), and only then applies. It **fails the deploy** if `pg_dump` is
> missing — one-time VM prep: `sudo apt install -y postgresql-client`. The dump is
> belt-and-suspenders; Neon PITR/branching is the real restore mechanism.

### Manual fallback (CI down, or a hand hotfix)

```bash
cd /home/ubuntu/thecommons && git pull

# Backend (only the steps that apply)
cd backendServer
/snap/bin/uv sync                                       # if pyproject.toml changed
/snap/bin/uv run python manage.py migrate               # if models changed
/snap/bin/uv run python manage.py collectstatic --noinput   # if static changed
sudo systemctl restart gunicorn
sudo systemctl restart celery celerybeat                # if task code or deps changed

# Frontend
cd ../theCommonsWeb && pnpm install && pnpm run build && sudo systemctl restart nextjs

# Broadcast
cd ../backendServer && sudo systemctl restart broadcast-worker
cd ../broadcastWeb && pnpm install && pnpm run build     # static — no service to restart

# Scrape worker (if scraper/task code changed)
cd ../backendServer && sudo systemctl restart scrape-worker
```

---

# Part 3 — Reference

## Health check

One command prints a scannable report of the whole box — RAM/disk, every systemd
unit, Redis, Postgres, the Celery worker, and whether the beat schedule is firing:

```bash
cd /home/ubuntu/thecommons
UV_BIN=/snap/bin/uv bash deploy/healthcheck.sh
UV_BIN=/snap/bin/uv bash deploy/healthcheck.sh --no-color | tee /tmp/health.log
```

It checks (✓/!/✗): RAM/disk vs thresholds; `systemctl is-active` for `redis-server`,
`celery`, `celerybeat`, `gunicorn`, `nextjs`, `broadcast-worker`, `scrape-worker`; leftover OS-cron
lines; and via `manage.py healthcheck` — Postgres `SELECT 1`, Redis broker ping
(DB 0), Django cache round-trip (DB 1), a Celery worker `control.ping`, and each
seeded `PeriodicTask` (enabled + last-run freshness: daily within ~25h, weekly
within ~8d). A stale or never-run schedule is a **`FAIL`**, not a warning — it was
a warning until the 2026-07-21 outage, which is precisely why a month-dead beat
still exited 0. A seeded task with no window configured in `DEFAULT_STALENESS_HOURS`
reports `WARN` rather than silently passing. It exits non-zero on any critical
failure. Tunables:
`RAM_WARN`/`RAM_FAIL` (80/95), `DISK_WARN`/`DISK_FAIL` (80/95), `CELERY_TIMEOUT`
(1.0s), `UV_BIN` (default `uv`; the VM has it at `/snap/bin/uv`). The Django command
also runs standalone: `/snap/bin/uv run python manage.py healthcheck [--json]`.

### Scheduled health check (systemd timer)

`deploy/healthcheck.sh` catches the failure modes that let the 2026-07-21 scheduler
outage run silent for five weeks — but only if something actually runs it. A systemd
timer does that hourly, independent of Celery beat (beat is one of the things being
checked, so it can't be the thing doing the checking).

1. Copy the unit files and enable the **timer**, not the service:

   ```bash
   sudo cp deploy/healthcheck.service deploy/healthcheck.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now healthcheck.timer
   ```

2. Verify it's scheduled:

   ```bash
   systemctl list-timers healthcheck.timer
   ```

   Expect a `NEXT`/`LEFT` time within the hour, and `LAST`/`PASSED` populated after
   the first run.

3. Check the most recent run:

   ```bash
   systemctl status healthcheck.service
   journalctl -u healthcheck.service -n 50 --no-pager
   ```

   A failing run shows `Active: failed` plus the `deploy/healthcheck.sh` report in
   the journal — look for `✗`/`FAIL` lines, most importantly any `beat:<task-name>`
   entry (stale or never-run schedule, or missing from the schedule entirely).

4. To see failed runs across all timers: `systemctl --failed`.

> **Expect an immediate FAIL on first install.** `scrape-sources-daily` has never run
> on prod (`last_run_at` is NULL), so the never-run rule fires until beat completes
> one. That is the outage this check exists to surface — don't silence it, fix the
> schedule.

> **No push notification is wired up yet.** There is no `OnFailure=` target,
> email, or Slack hook — `systemctl --failed` and the journal are the only read
> paths. Check them as part of routine ops until that's built.

## Services

| Service | What it is | File | Notes |
|---------|-----------|------|-------|
| `gunicorn` | Django backend | `/etc/systemd/system/gunicorn.service` | `unix:/run/gunicorn/gunicorn.sock`, 3 sync workers; `RuntimeDirectory=gunicorn` creates `/run/gunicorn/` |
| `nextjs` | Next.js frontend | `/etc/systemd/system/nextjs.service` | Port 3000, `npm run start` from `theCommonsWeb/` |
| `redis-server` | Celery broker + cache | `/etc/redis/redis.conf` | localhost-bound, password-protected, 512 MB allkeys-lru |
| `celery` | Async task worker | `deploy/celery.service` | `.venv/bin/celery -A backend worker`, concurrency 2, drains Redis DB 0 |
| `celerybeat` | Scheduler | `deploy/celerybeat.service` | `.venv/bin/celery -A backend beat`, DatabaseScheduler; **exactly one** process |
| `broadcast-worker` | Playwright form-filler | `deploy/broadcast-worker.service` | `.venv/bin/celery -A backend worker -Q broadcast -c 1`, MemoryMax 2G, drains the dedicated `broadcast` queue only |
| `scrape-worker` | Ingestion scraper (Playwright) | `deploy/scrape-worker.service` | `.venv/bin/celery -A backend worker -Q scrape -c 1`, MemoryMax 2G, drains the dedicated `scrape` queue only |

All four `ExecStart=` lines exec `/home/ubuntu/thecommons/backendServer/.venv/bin/celery`
directly rather than `uv run celery` — see §4 for why (the 2026-07-21 outage) and the
one-shot vs long-lived `uv` rule in the Facts table above.

The three **workers** also pass `-n commons-{default,scrape,broadcast}@%%h`. Without it
they all default to `celery@<hostname>`, and duplicate nodenames make
`celery -A backend inspect|control` ambiguous — it returns several replies under one
name (`DuplicateNodenameWarning`) and can misroute a revoke. The doubled `%%` is
required: systemd expands a bare `%h` to the *user home directory*, so `%%h` is what
passes a literal `%h` through for celery to expand to the hostname. Verify with:

```bash
cd /home/ubuntu/thecommons/backendServer && .venv/bin/celery -A backend inspect ping
# expect three distinct nodes: commons-default@, commons-scrape@, commons-broadcast@
```

```bash
sudo systemctl status   <unit>
sudo systemctl restart  <unit>
sudo journalctl -u <unit> -n 50         # add -f to follow
```

## Environment variables

### `backendServer/.env`

```
DATABASE_URL=                          # Neon Postgres connection string
DJANGO_SECRET_KEY=
DJANGO_ENV=prod                        # selects settings/prod.py (omit locally → dev)
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,api.thecommons.town
CORS_EXTRA_ORIGINS=https://thecommons.town,https://broadcast.thecommons.town
CSRF_TRUSTED_ORIGINS=https://api.thecommons.town,https://thecommons.town,https://broadcast.thecommons.town
GEMINI_API_KEY=
CRON_SECRET=
THE_COMMONS_API_KEY=
SAFETY_SCORE_THRESHOLD=0.3             # optional
INGEST_SHARD_COUNT=3                   # optional — see §3
INGEST_SCRAPER_HEADLESS=true           # optional — default true
INGEST_SCRAPER_TIMEOUT_MS=30000        # optional — default 30000
INGEST_SCRAPER_USER_AGENT=Mozilla/5.0 (compatible; TheCommons/1.0)  # optional — default shown
BETTER_AUTH_JWKS_URL=https://auth.thecommons.town/api/auth/jwks
BETTER_AUTH_ISSUER=https://auth.thecommons.town
BETTER_AUTH_AUDIENCE=
BREVO_API_KEY=
DIGEST_FROM_EMAIL=digest@thecommons.town
SITE_URL=https://thecommons.town
REDIS_URL=redis://:<REDIS_PASS>@127.0.0.1:6379/0          # Celery broker + results (DB 0)
REDIS_CACHE_URL=redis://:<REDIS_PASS>@127.0.0.1:6379/1    # read-endpoint cache (DB 1)
# Broadcast (see backendServer/.env.example for the full annotated block)
BROADCAST_HEADLESS=true
BROADCAST_DRY_RUN_DEFAULT=false
BROADCAST_MAX_CONCURRENCY=1
BROADCAST_SCREENSHOT_DIR=/home/ubuntu/broadcast/screenshots
BROADCAST_DOWNLOAD_DIR=/home/ubuntu/broadcast/downloads
BROADCAST_TIMEOUT_MS=30000
MEDIA_ROOT=/home/ubuntu/broadcast/media    # client-uploaded event images (T7) — outside the repo checkout so `git pull` never touches it
```

### `theCommonsWeb/.env.local`

```
NEXT_PUBLIC_API_BASE_URL=https://api.thecommons.town
NEXT_PUBLIC_THE_COMMONS_API_KEY=
DATABASE_URL=                          # same Neon connection string
BETTER_AUTH_SECRET=
BETTER_AUTH_URL=https://auth.thecommons.town
NEXT_PUBLIC_BETTER_AUTH_URL=https://auth.thecommons.town
BETTER_AUTH_COOKIE_DOMAIN=.thecommons.town   # enables cross-subdomain sessions (SameSite=None; Secure)
```

### `broadcastWeb/.env`

```
VITE_BROADCAST_API_BASE_URL=https://api.thecommons.town
VITE_BROADCAST_EXTENSION_ID=           # Chrome extension ID for extension autofill
VITE_BETTER_AUTH_URL=https://auth.thecommons.town
```

## nginx

- Config: `/etc/nginx/sites-available/thecommons` (symlinked into `sites-enabled/`) —
  one file, multiple `server` blocks.
- Routes: `thecommons.town` → `localhost:3000` (Next.js); `api.thecommons.town` →
  `unix:/run/gunicorn/gunicorn.sock` (Django); `www` → 301 to apex; HTTP → 301 to
  HTTPS; `api.thecommons.town/static/` → `backendServer/staticfiles/`;
  `api.thecommons.town/media/` → `MEDIA_ROOT` (client-uploaded broadcast event
  images, T7 — served by nginx directly, **never** by Django/gunicorn in prod);
  `broadcast.thecommons.town` → the block from `deploy/nginx-broadcast.conf.snippet`.

  Add a sibling alias to the existing `/static/` block in the `api.thecommons.town`
  server block:

  ```nginx
  location /media/ {
      alias /home/ubuntu/broadcast/media/;
  }
  ```

  `MEDIA_ROOT` (`/home/ubuntu/broadcast/media` by default — see env vars below)
  must exist and be writable by the gunicorn user (`ubuntu`) before the first
  upload: `mkdir -p /home/ubuntu/broadcast/media`. It lives outside the repo
  checkout alongside `BROADCAST_SCREENSHOT_DIR`/`BROADCAST_DOWNLOAD_DIR` so a
  `git pull` during deploy never touches it, and it survives deploys for the
  same reason. **Uploaded images are kept indefinitely — no pruning job exists.**
  `MEDIA_ROOT` grows without bound; at roughly 1–3 MB per event against the VPS
  block volume this is negligible for the foreseeable future, but keep it in
  mind at ops time (a prune command can be added later without a migration).

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## Firewall

Two layers must allow 80/443:

1. **Oracle VCN Security List** (OCI console) — ingress on 22, 80, 443.
2. **iptables on the VM** — Oracle Ubuntu images ship a catch-all `REJECT` in INPUT.
   The 80/443 ACCEPT rules must sit **above** it:
   ```bash
   sudo iptables -L INPUT -n --line-numbers
   sudo iptables -I INPUT 5 -p tcp --dport 443 -m state --state NEW -j ACCEPT
   sudo iptables -I INPUT 5 -p tcp --dport 80  -m state --state NEW -j ACCEPT
   sudo netfilter-persistent save          # persist across reboots
   ```

## Troubleshooting

| Symptom | Likely cause | Check |
|---------|-------------|-------|
| `curl` to IP / subdomain returns nothing | iptables REJECT before ACCEPT | `sudo iptables -L INPUT -n --line-numbers` |
| nginx 502 Bad Gateway | gunicorn or nextjs down | `sudo systemctl status gunicorn nextjs` |
| broadcast subdomain → Cloudflare 526 | origin cert doesn't cover `*.thecommons.town` | reissue cert (Part 1 §5.1) |
| Django `DisallowedHost` | host missing from `ALLOWED_HOSTS` | `DJANGO_ALLOWED_HOSTS` in `.env` |
| 400 on `/events/` from browser | `NEXT_PUBLIC_API_BASE_URL` wrong or stale build | `.env.local`, then `pnpm run build` |
| Django admin has no CSS | `collectstatic` not run / `/static/` alias wrong | `manage.py collectstatic --noinput` |
| Celery worker won't start / no broker | `REDIS_URL` missing/wrong password, or Redis down | `redis-cli -a '<pass>' PING`; `journalctl -u celery -n 50` |
| Scheduled job ran twice | leftover OS cron alongside beat | `crontab -l` (Part 1 §9) |

## Deep-dive references

- `docs/redis-celery-handoff.md` — Redis/Celery internals, task conventions, beat schedules
- `docs/broadcast.md` — broadcast subsystem: routing, adapters, worker, recipe layer, extension, SPA wiring
- `docs/dev-db-isolation.md` — Neon dev branch setup for local development
- `docs/ingestion-pipeline.md` — scrape → stage → publish flow
- `docs/runbook-auth-cutover.md` — Auth-origin cutover (auth.thecommons.town subdomain, .thecommons.town cookie domain, forced re-login)
