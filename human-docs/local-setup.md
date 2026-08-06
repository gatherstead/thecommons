# Local Setup

> **Last updated:** 2026-08-05, commit `087f5e6`, branch `suite-49-11-category-pipeline`

## Overview

This is the clone-to-running-system guide for The Commons. It assumes general web-dev skill
and zero context on this codebase, and it takes you as far as: the Django API answering
requests, the public Next.js site rendering events from your own database, background jobs
actually executing, and — optionally — the broadcast operator SPA and its Playwright worker.

**Environment variables are deliberately not in this doc.** Every service reads a `.env` file
that is gitignored; the real values are handed to you out of band (ask whoever onboarded you).
What this guide tells you is *which file goes where* and which single variable will stop you
dead if it's missing. Each `.env.example` in the repo is the authoritative list of keys.

Three toolchains are involved and none of them are interchangeable: **`uv`** for the Python
backend, **`pnpm`** (never npm) for both frontends, and **Docker Compose** as an optional
whole-stack alternative. Postgres is *not* something you install — it lives on Neon in every
environment including local dev, so "set up the database" means "get a connection string and
run migrations", never "start a server".

Roughly 20 minutes if the credentials are already in hand. Read §1 before you start; the rest
is sequential.

**If you're in VS Code, skip most of the manual terminal-juggling below.** The **"Start Dev
Environment"** task in `.vscode/tasks.json` (Cmd/Ctrl+Shift+P → "Tasks: Run Task" → *Start Dev
Environment*) opens one dedicated terminal each for the frontend, `broadcastWeb`, Redis, and
the backend (running `runserver`, not the Celery workers from §6), plus a terminal for the prod
VM (`ssh.sh`) and a spare shell — all in parallel with one command. Pair it with **"Teardown Dev
Environment"** (`teardown.sh`) to kill everything at once when you're done. §7 covers the other
shortcut, the fully containerized alternative.

---

## 1. Prerequisites

| Tool | Version | Why, and how |
|---|---|---|
| **Python** | 3.13+ | `requires-python = ">=3.13"` in `backendServer/pyproject.toml`. You don't need to install it yourself — `uv` will fetch a matching interpreter. |
| **uv** | recent | The only supported Python package manager here. `brew install uv`, or see astral.sh. Every backend command in this repo is `uv run …`. |
| **Node** | 22.13+ | CI pins Node 22; pnpm 11 refuses to run below 22.13. |
| **pnpm** | 11.x | CI pins `pnpm@11.1.1`. `corepack enable` or `npm i -g pnpm@11`. |
| **Redis** | 7.x | Needed to *run* the app, not to test it. `brew install redis && brew services start redis`, or `apt install redis-server`. Or let Docker provide it — §7. |
| **Docker** | recent | Optional. Only if you want the whole-stack path in §7 or the containerized broadcast worker. |
| **Postgres server** | — | **Not needed.** The database is Neon-hosted in every environment. You may want `psql` as a client, nothing more. |

You do not need a Postgres install, an nginx install, or a Chromium install (Playwright fetches
its own — §6).

---

## 2. Clone and place the env files

```bash
git clone <repo-url> thecommons && cd thecommons
```

Four env files, four different names — the naming is not arbitrary and getting it wrong fails
quietly rather than loudly:

| File | Consumed by | Template | Note |
|---|---|---|---|
| `backendServer/.env` | Django, Celery, all management commands | `backendServer/.env.example` | Plain `.env`. |
| `theCommonsWeb/.env.local` | Next.js (public site) | `theCommonsWeb/.env.example` | **`.env.local`, not `.env`.** Next gives `.env.local` precedence; a stale `.env` in an old checkout will silently lose to it and leave you debugging the wrong file. |
| `broadcastWeb/.env` | Vite (broadcast SPA) | `broadcastWeb/.env.example` | Plain `.env` — this one's a Vite app, so `VITE_*` keys. Only needed for §5. |
| `.env` at the repo root | Docker Compose build args only | — | Only needed for the Docker path (§7), and only for real builds; every build arg has a placeholder default. |

Copy each example to its real name and fill in the values you were given. Two things worth
knowing before you do:

- **`DATABASE_URL` is the one hard requirement.** `backend/settings/dev.py` raises a
  `RuntimeError` at import time if it's unset — before Django loads anything else, so the error
  you get is not a helpful one if you skip this. Everything else in `backendServer/.env.example`
  (Gemini, Brevo, the JWKS URL, `CRON_SECRET`, `THE_COMMONS_API_KEY`) either has a dev fallback
  or only matters for a feature you may not be touching.
- **Point `DATABASE_URL` at your own Neon dev branch, not prod, and not a branch someone else is
  using.** The setup is in [`docs/dev-db-isolation.md`](../docs/dev-db-isolation.md). The backend
  and `theCommonsWeb` share *one* database — Better Auth (Next.js) owns the `neon_auth` schema,
  Django owns `public` — so both files point at the same branch.

> **Never commit a `.env`.** If you add a key, add it to the matching `.env.example` instead.

---

## 3. Backend — Django API

```bash
cd backendServer
uv sync
uv run python manage.py migrate
uv run python manage.py runserver     # http://127.0.0.1:8000
```

`uv sync` creates `.venv` and installs from `uv.lock`. Skip `--frozen` locally — that flag is
CI-only and fails rather than updating the lockfile when `pyproject.toml` has drifted.

`runserver` expects a **reachable Redis** at whatever `REDIS_URL` / `REDIS_CACHE_URL` resolve to
(the examples default to `localhost:6379`, DB 0 and DB 1 respectively — that split is fixed:
DB 0 is the Celery broker/results, DB 1 is the Django cache; don't mix them). Confirm with
`redis-cli ping` → `PONG` before blaming Django.

Two conveniences worth knowing:

```bash
uv run python manage.py devserver     # runserver, but auto-increments past a busy port
uv run python manage.py seed_dev      # Towns, Tags, Categories, sample Events, scraper sources
```

`seed_dev` is what turns an empty migrated database into something the frontend can render.
It refuses to run when `DEBUG` is off unless you pass `--force` — which is a guardrail against
seeding prod, so if you find yourself reaching for `--force`, stop and check which database
you're pointed at.

For the Django admin at `/admin/`, create a Django superuser the ordinary way
(`uv run python manage.py createsuperuser`). Note this is **staff access to the admin only** —
it has nothing to do with application user accounts, which live in Better Auth on the Next.js
side. See [`auth.md`](auth.md) for why those are two separate worlds.

Under `DEBUG`, the dev-only `devtools` app also mounts at `/devtools/` — an ingestion playground
and a source monitor. See [`ingestion.md`](ingestion.md) and
[`docs/ingestion-monitoring.md`](../docs/ingestion-monitoring.md).

---

## 4. Frontend — theCommonsWeb (the public site)

```bash
cd theCommonsWeb
pnpm install
pnpm dev            # http://localhost:3000
```

**pnpm only.** `npm install` breaks here — the store is symlinked in a way plain npm doesn't
handle, and peer pinning depends on pnpm's resolution. If you've already run `npm install` by
reflex, delete `node_modules` and `package-lock.json` and start over with pnpm.

`pnpm dev` runs Next 16 with Turbopack. It needs `.env.local` in place (§2) — `DATABASE_URL`
(same Neon branch as the backend) and `BETTER_AUTH_SECRET` at minimum, because Better Auth
initializes against Postgres at startup.

Run this **together with** the backend if you're touching anything authenticated: Django
verifies JWTs against the frontend's JWKS endpoint, so signed-in API calls simply don't work
with only one half of the pair running.

Type-checking is `pnpm build` (there is no separate `typecheck` script). Lint is `pnpm lint`.

---

## 5. Frontend — broadcastWeb (optional operator SPA)

```bash
cd broadcastWeb
pnpm install
pnpm dev            # http://localhost:5173
```

Skip this unless you're working on syndication. The public site and its tests don't depend on
it. Its `.env` holds `VITE_*` keys pointing at the backend and auth origins.

The **Chrome extension** (`broadcastExtension/`) pairs with this SPA for manual-review autofill
and is loaded, not built: `chrome://extensions` → Developer mode → *Load unpacked* →
`broadcastExtension/`. Its manifest already allows `externally_connectable` from
`localhost:5173`, so a locally-served SPA can talk to it. The sharp edge: the extension only
autofills hosts listed in `manifest.json`'s `host_permissions` — a calendar host that isn't
there produces a **silent no-fill**, not an error. Full picture in [`broadcast.md`](broadcast.md).

---

## 6. Background jobs and Playwright

Nothing processes a queued task unless you run a worker. `runserver` alone will happily enqueue
digests, ingestion runs, and broadcast submissions that then sit there forever.

```bash
cd backendServer
uv run celery -A backend worker -l info                     # default queue
uv run celery -A backend beat -l info                       # scheduler (DB-backed schedules)
uv run celery -A backend worker -Q scrape -c 1 -l info      # scrape queue
uv run celery -A backend worker -Q broadcast -c 1 -l info   # broadcast queue
```

You rarely need all four locally — start the default worker, and add the specific queue you're
working on. **`-c 1` on the broadcast worker is load-bearing, not tuning:** orphan recovery
assumes exactly one worker, and a second would race a live queue drain. Queue topology and beat
scheduling are in [`async-jobs.md`](async-jobs.md).

The two `-c 1` queues drive a real headless Chromium, so install it once:

```bash
uv run playwright install chromium
uv run playwright install-deps chromium     # Linux only — system libs, uses sudo
```

The absolute rule when touching that code: **no Django ORM inside `sync_playwright`.** Fetch
everything into plain objects first, then drive the browser.

A shortcut for tests and quick loops: setting `CELERY_TASK_ALWAYS_EAGER=True` executes tasks
synchronously in-process with no worker at all (this is what the test settings do).

Once things are running, one command tells you whether the whole async stack is actually alive:

```bash
uv run python manage.py healthcheck      # Postgres, Redis DB 0 + DB 1, worker ping, beat freshness
```

---

## 7. Alternative: the whole stack in Docker

If you'd rather not install Redis or juggle five terminals, the repo's Compose files run the
entire stack locally, nginx included:

```bash
docker compose up --build       # http://localhost
```

Plain `docker compose up` auto-loads `docker-compose.override.yml`, which is what makes this
work on a dev machine: it swaps the TLS nginx config for an HTTP-only one (the production
config hard-requires a Cloudflare origin cert you don't have, and nginx refuses to start
without it), remaps the VM's `/home/ubuntu/...` bind mounts to repo-relative `.local-dev/`
directories, sets `DJANGO_ENV=dev`, and repoints `REDIS_URL`/`REDIS_CACHE_URL` at the `redis`
service.

Local hostnames, no `/etc/hosts` edits required (`*.localhost` resolves to 127.0.0.1 per
RFC 6761):

| URL | Serves |
|---|---|
| `http://localhost` | The Next.js public site |
| `http://api.localhost` | Django, plus `/static/` and `/media/` |
| `http://broadcast.localhost` | The compiled broadcast SPA |

You still need `backendServer/.env` and `theCommonsWeb/.env.local` in place — the containers
read them via `env_file:`. Postgres is *still* Neon; it is not in the compose stack in any
environment.

Two traps: the **production** invocation always names the file explicitly
(`docker compose -f docker-compose.yml up -d --build`) precisely so the VM never picks up the
override — don't drop that flag when following a deploy runbook. And build args for the two
frontend bundles come from your *shell* or a root `.env`, never from
`theCommonsWeb/.env.local`, so a "real" build needs
`set -a; source theCommonsWeb/.env.local; source broadcastWeb/.env; set +a` first. Background in
[`containerization.md`](containerization.md).

---

## 8. Verify the install

Run these in order — the ordering matters for the reason in §9.

```bash
cd backendServer
DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test --tag=fast
DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test --tag=db

cd ../theCommonsWeb
pnpm test:fast
pnpm test:db
pnpm build          # type-check

cd ../broadcastWeb   # only if you set it up
pnpm test:fast
```

Green across the board means a working backend, a working frontend, and a working test loop.
Backend tests always run under `backend.settings.test` — never the dev or prod settings — and
they do **not** need Redis. Full detail on tiers, tags, and the test runner lives in
[`testing.md`](testing.md).

Optionally, install the git hooks (ruff check, ruff format, mypy, eslint):

```bash
pre-commit install
```

---

## 9. Sharp edges

The ones that cost people an afternoon, in rough order of likelihood:

- **Concurrent `--tag=db` runs silently lie.** The Neon test database is shared infrastructure.
  Two terminals — or two agents — running DB tests against the same branch race to create and
  drop the same literal database, and the failure mode is a **false green**, not a crash. Run DB
  suites serially, with `--noinput` and `pipefail`. [`testing.md`](testing.md) §4.
- **`npm install` in either frontend.** Breaks the symlinked store. pnpm 11 only.
- **`.env` vs `.env.local` in theCommonsWeb.** Next prefers `.env.local`; a leftover `.env` loses
  silently and you'll edit the wrong file for twenty minutes.
- **Redis DB 0 vs DB 1 are not interchangeable.** 0 is broker + results, 1 is the Django cache.
  Pointing both at the same DB appears to work until cache flushes start eating task state.
- **Inside a container, `localhost` is the container.** If you hand-roll a compose setup and
  leave `REDIS_URL=redis://localhost:6379/0`, Celery connects to nothing and no task ever runs —
  no error, just silence. The override file handles this for you; hand edits don't.
- **`DJANGO_ENV` unset means dev settings.** Harmless locally, an outage in prod
  (`DisallowedHost` 400s that present as "the site has no events"). Never copy a prod `.env`
  fragment into a local file without checking this key.
- **`events.Event`'s primary key is `uuid`, not `id`.** `Count("id")` or `values("id")` on
  `Event` raises `FieldError`. Use `Count("pk")`.
- **Never migrate `neon_auth`.** Better Auth owns those tables; the Django models are
  `managed = False` mirrors. `manage.py migrate` after a model change is right for everything
  else.
- **Some ingestion sources are blocked from some networks.** A source that 403s for you may be
  WAF behaviour, not broken code. [`ingestion.md`](ingestion.md) covers the classification traps.

---

## 10. Where to go next

| You want to… | Read |
|---|---|
| Understand what you just installed | [`overview.md`](overview.md) |
| Understand sign-in and the JWT bridge | [`auth.md`](auth.md) |
| Add or debug an event source | [`ingestion.md`](ingestion.md) |
| Know the models | [`data-model.md`](data-model.md) |
| Run and write tests properly | [`testing.md`](testing.md) |
| Add a background job | [`async-jobs.md`](async-jobs.md) |
| Match the newspaper aesthetic | [`design-system.md`](design-system.md) |
| Deploy | [`deploy-ops.md`](deploy-ops.md), then [`DEPLOY.md`](../DEPLOY.md) |

Every command above was checked against the repo's actual scripts, settings modules, and
management commands at the commit in the header. Where this doc and the code disagree, the code
wins — and please fix the doc.
