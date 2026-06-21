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
| Python | **`uv`** at `/snap/bin/uv` — never `pip` |
| Node | **`pnpm`** — never `npm install` (it breaks peer-dependency pinning) |
| DNS / TLS | Cloudflare, proxied (orange cloud), SSL mode **Full (strict)**; origin cert at `/etc/ssl/cloudflare/thecommons.town.{pem,key}` |

> **What changed since `main`:** this release adds Redis, a Celery worker + beat
> scheduler, the broadcast worker (Playwright), a healthcheck, and a CI/CD
> auto-deploy. The ingestion and weekly-digest jobs **moved off OS cron** onto
> `django-celery-beat` (a DB-backed scheduler seeded by migrations). If you followed
> any older notes that set up `crontab`/`logrotate`/`/var/log/thecommons` for those
> two jobs, that approach is **dead** — Part 1 §8 retires it.

---

# Part 1 — First deploy (manual, one time)

Do these in order. The CI auto-deploy in Part 2 **cannot** succeed until this is
done, because it restarts `celery`/`celerybeat`/`broadcast-worker`, which don't
exist on the box yet.

## 1. Pull the new code onto the VM

```bash
ssh -i oraclevps.key ubuntu@129.80.229.41
cd /home/ubuntu/thecommons
git fetch origin
git checkout testing+ci && git pull origin testing+ci
```

> You provision from the `testing+ci` branch now. In §9 you'll switch the VM to
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

## 5. Broadcast feature (one time)

The broadcast feature adds a third subdomain, a Playwright worker, and a static SPA.
Do all seven in order.

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
6. **Worker service:**
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

## 6. Frontend builds + restart

```bash
cd /home/ubuntu/thecommons/theCommonsWeb
pnpm install && pnpm run build
sudo systemctl restart nextjs

cd ../broadcastWeb
pnpm install && pnpm run build           # static → dist/, served directly by nginx (no service)

sudo systemctl restart gunicorn
```

## 7. Verify

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

## 8. Retire the old OS cron (only if it exists)

Beat now owns the ingest + digest schedules. If the box still has the old cron
lines, remove them so the jobs don't run twice:

```bash
crontab -l                 # look for ingest_events / send_weekly_digest lines
crontab -e                 # delete those two lines if present
```

`healthcheck.sh` also flags leftover cron lines for these jobs.

## 9. Switch the VM to `main` and enable CI/CD

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

**Sudoers drop-in (VM)** — passwordless restart for exactly the five units:

```bash
sudo visudo -f /etc/sudoers.d/deploy-restart
```

```
ubuntu ALL=(root) NOPASSWD: /usr/bin/systemctl restart gunicorn, \
                            /usr/bin/systemctl restart nextjs, \
                            /usr/bin/systemctl restart celery, \
                            /usr/bin/systemctl restart celerybeat, \
                            /usr/bin/systemctl restart broadcast-worker
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
the full sequence: `git pull` → `uv sync` → `migrate` → `collectstatic` → both
frontend `pnpm install`/`build` → restart `gunicorn nextjs celery celerybeat
broadcast-worker`. A failing test on `main` blocks the deploy.

> ⚠️ The workflow runs `migrate` **unguarded** — a destructive migration applies
> automatically. There's no "review migrations first" gate yet.

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
`celery`, `celerybeat`, `gunicorn`, `nextjs`, `broadcast-worker`; leftover OS-cron
lines; and via `manage.py healthcheck` — Postgres `SELECT 1`, Redis broker ping
(DB 0), Django cache round-trip (DB 1), a Celery worker `control.ping`, and each
seeded `PeriodicTask` (enabled + last-run freshness: daily within ~25h, weekly
within ~8d). It exits non-zero on any critical failure. Tunables:
`RAM_WARN`/`RAM_FAIL` (80/95), `DISK_WARN`/`DISK_FAIL` (80/95), `CELERY_TIMEOUT`
(1.0s), `UV_BIN` (default `uv`; the VM has it at `/snap/bin/uv`). The Django command
also runs standalone: `/snap/bin/uv run python manage.py healthcheck [--json]`.

## Services

| Service | What it is | File | Notes |
|---------|-----------|------|-------|
| `gunicorn` | Django backend | `/etc/systemd/system/gunicorn.service` | `unix:/run/gunicorn/gunicorn.sock`, 3 sync workers; `RuntimeDirectory=gunicorn` creates `/run/gunicorn/` |
| `nextjs` | Next.js frontend | `/etc/systemd/system/nextjs.service` | Port 3000, `npm run start` from `theCommonsWeb/` |
| `redis-server` | Celery broker + cache | `/etc/redis/redis.conf` | localhost-bound, password-protected, 512 MB allkeys-lru |
| `celery` | Async task worker | `deploy/celery.service` | `/snap/bin/uv run celery -A backend worker`, concurrency 2, drains Redis DB 0 |
| `celerybeat` | Scheduler | `deploy/celerybeat.service` | DatabaseScheduler; **exactly one** process |
| `broadcast-worker` | Playwright form-filler | `deploy/broadcast-worker.service` | `run_broadcast_worker`, MemoryMax 2G |

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
BETTER_AUTH_JWKS_URL=https://thecommons.town/api/auth/jwks
BETTER_AUTH_ISSUER=https://thecommons.town
BETTER_AUTH_AUDIENCE=
BREVO_API_KEY=
DIGEST_FROM_EMAIL=digest@thecommons.town
SITE_URL=https://thecommons.town
REDIS_URL=redis://:<REDIS_PASS>@127.0.0.1:6379/0          # Celery broker + results (DB 0)
REDIS_CACHE_URL=redis://:<REDIS_PASS>@127.0.0.1:6379/1    # read-endpoint cache (DB 1)
# Broadcast (see backendServer/.env.example for the full annotated block)
BROADCAST_ACCESS_CODES=
BROADCAST_HEADLESS=true
BROADCAST_DRY_RUN_DEFAULT=false
BROADCAST_MAX_CONCURRENCY=1
BROADCAST_SCREENSHOT_DIR=/home/ubuntu/broadcast/screenshots
BROADCAST_DOWNLOAD_DIR=/home/ubuntu/broadcast/downloads
BROADCAST_TIMEOUT_MS=30000
```

### `theCommonsWeb/.env.local`

```
NEXT_PUBLIC_API_BASE_URL=https://api.thecommons.town
NEXT_PUBLIC_THE_COMMONS_API_KEY=
DATABASE_URL=                          # same Neon connection string
BETTER_AUTH_SECRET=
BETTER_AUTH_URL=https://thecommons.town
NEXT_PUBLIC_BETTER_AUTH_URL=https://thecommons.town
```

## nginx

- Config: `/etc/nginx/sites-available/thecommons` (symlinked into `sites-enabled/`) —
  one file, multiple `server` blocks.
- Routes: `thecommons.town` → `localhost:3000` (Next.js); `api.thecommons.town` →
  `unix:/run/gunicorn/gunicorn.sock` (Django); `www` → 301 to apex; HTTP → 301 to
  HTTPS; `api.thecommons.town/static/` → `backendServer/staticfiles/`;
  `broadcast.thecommons.town` → the block from `deploy/nginx-broadcast.conf.snippet`.

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
| Scheduled job ran twice | leftover OS cron alongside beat | `crontab -l` (Part 1 §8) |

## Deep-dive references

- `docs/redis-celery-handoff.md` — Redis/Celery internals, task conventions, beat schedules
- `docs/broadcast-handoff.md` — broadcast recipe layer, extension, SPA wiring
- `docs/dev-db-isolation.md` — Neon dev branch setup for local development
- `docs/ingestion-pipeline.md` — scrape → stage → publish flow
