# Handoff — Suite 42 (Dockerize the stack), 2026-08-02

Paste the block below to a fresh Claude Code instance. Everything it needs is inline;
it does not need to read this preamble.

---

## PROMPT FOR NEXT INSTANCE

You are picking up **suite 42 — Dockerize the stack** on `The Commons`
(`/Users/ErenYeager/Desktop/hw/thecommons`, branch `all-things-ingestion`).
Read `CLAUDE.md`, `AGENTS.md`, and `DEPLOY.md` first — DEPLOY.md was just rewritten
and is the system of record for everything below.

### Read this before you touch anything

**⚠️ There is a live landmine. Do not merge this branch to `main` yet.**

`.github/workflows/ci.yml:171` runs the `deploy` job on every push to `main`. That job
was rewritten in suite 42 to build images and run `docker compose -f docker-compose.yml
up -d` over SSH — **but the production VM has no Docker installed.** The first merge to
`main` will fail the deploy, and the VM's current systemd-based stack will keep running
the old code with no indication anything was attempted. The branch is currently 3 commits
ahead of `main` with all of suite 42 uncommitted, so nothing has fired yet.

Sequence matters: **VM prep must land before the merge**, or the merge must be gated.

### What suite 42 already did (all verified, none of it committed)

The stack is containerized and was proven end-to-end on a local machine against the Neon
dev branch. Postgres is deliberately NOT containerized.

New files:
- `backendServer/Dockerfile` — multi-stage: `app` (gunicorn/celery/celerybeat, 492 MB, no
  Chromium) and `playwright` (`FROM app` + bundled Chromium 148, 1.97 GB) for the
  broadcast and scrape workers.
- `Dockerfile.frontend` — shared: `commons-runtime` (Next.js standalone, port 3000,
  284 MB) and `broadcast-build` (build-only, SPA at `/app/dist`, 387 MB).
  `theCommonsWeb` and `broadcastWeb` are SEPARATE pnpm workspaces with separate lockfiles.
- `deploy/nginx/Dockerfile` + `deploy/nginx/thecommons.conf` — nginx as sole ingress,
  baking in collectstatic output and the broadcast SPA via Buildx named build contexts.
- `docker-compose.yml` — replaces all seven systemd units.
- `docker-compose.override.yml` — local dev only (plain HTTP, no cert, `DJANGO_ENV=dev`,
  repo-relative mounts under `.local-dev/`).
- `.dockerignore`, `backendServer/.dockerignore`.
- `docs/adr/0001-containerization.md` — the architecture decisions and rationale.

Modified: `.github/workflows/ci.yml` (deploy job), `DEPLOY.md` (full rewrite),
`deploy/healthcheck.{sh,service,timer}` (systemd → container checks),
`theCommonsWeb/next.config.ts` (added `output: 'standalone'`), `.gitignore`,
`notion-sync/{OUTBOX.md,STATE.md}`.

**Verified locally:** all 8 long-running services up; apex / `/events/` / `/admin/login/`
/ baked static / media / broadcast SPA incl. deep-link fallback all 200 through nginx;
3 distinct Celery nodes each draining only its own queue; Chromium launches in both
Playwright workers; Redis DB 0 (broker) + DB 1 (cache) both exercised; `docker compose
down` clean.

### Rules that will bite you

1. **Every prod compose command needs `-f docker-compose.yml` explicitly.** A bare
   `docker compose` auto-loads `docker-compose.override.yml`, which is local-dev-only —
   you would deploy plain-HTTP, cert-less, `DJANGO_ENV=dev` config to production.
2. `-c 1` on the broadcast worker is mandatory, not tuning — `recover_orphans()` assumes
   a single worker. Exactly one `celerybeat`.
3. Compose does **not** auto-recreate a container when inline `configs:` content changes.
   Use `--force-recreate`.
4. Docker Desktop's proxy (`http.docker.internal:3128`) corrupts large apt fetches with
   `Hash Sum mismatch` on a different package each run. `backendServer/Dockerfile`
   mitigates it via `/etc/apt/apt.conf.d/99-robust`.
5. `.dockerignore` patterns need an explicit `**/` to match inside subdirectories on this
   BuildKit — stricter than `.gitignore`. A bare `*.pem` does NOT exclude
   `broadcastWeb/commons-broadcast.pem`.
6. The tree is dirty with three overlapping suites (41 backend refactor, 42 docker,
   43 human docs). **Do not `git add -A`** — a blanket commit sweeps unrelated in-flight
   work. Commit suite 42's files explicitly by path.

### Next steps, in order

**1. Decide the merge-safety strategy (blocking, do this first).**
Either complete VM prep before merging, or temporarily gate the deploy job. Do not leave
`main` armed against a Docker-less VM. This is a judgement call — surface the options
rather than picking silently.

**2. Do the one-time VM prep — `DEPLOY.md` Part 1, an 11-step numbered checklist.**
Target: Oracle Ubuntu 24.04 **ARM64**, user `ubuntu`, repo at `/home/ubuntu/thecommons`.
Highlights, but follow the doc:
- Install Docker Engine + the compose v2 plugin (arm64).
- Add `ubuntu` to the `docker` group and **verify over a real non-interactive SSH session**
  (`ssh host 'docker ps'`, not an interactive login, and not `newgrp docker` — both paper
  over a broken setup; CI connects non-interactively).
- Create `/home/ubuntu/broadcast/{media,screenshots,downloads}` and `/home/ubuntu/backups`,
  writable by **uid 1000** (the image's non-root `app` user).
- Confirm the Cloudflare origin cert at `/etc/ssl/cloudflare/thecommons.town.{pem,key}`.

**3. Edit prod `backendServer/.env` — two release blockers.**
- `REDIS_URL` / `REDIS_CACHE_URL` currently point at `localhost`/`127.0.0.1`. **Inside a
  container `localhost` is the container itself**, so Celery silently connects to nothing,
  no task ever runs, and every other signal stays green — the same failure shape as the
  2026-07-21 scheduler outage. Must become
  `redis://:<password>@redis:6379/0` and `.../1`.
- Add `REDIS_PASSWORD` (it is NOT in `.env.example` today; the `redis` container reads it
  directly, Django/Celery only read the URLs) — it must match the password in those URLs.
- Confirm `DJANGO_ALLOWED_HOSTS` is set — `backend/settings/prod.py:16` does
  `os.environ["DJANGO_ALLOWED_HOSTS"]`, a hard `KeyError` with no default.
- Confirm `DJANGO_ENV=prod`. If unset the app silently serves dev settings, whose
  localhost-only `ALLOWED_HOSTS` rejects `api.thecommons.town` with a 400.

**4. Host nginx → container nginx cutover.** Keep the host nginx additive until cutover,
then stop/disable it so the container can bind 80/443. Retire the old app systemd units
and the sudoers `systemctl` drop-in.

**5. Run the test suites — NOT done in suite 42.**
- Backend: `cd backendServer && DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test`
  (`--tag=fast` no-DB tier, `--tag=db` DB tier).
- Frontend: `cd theCommonsWeb && pnpm build` — **specifically verify the new
  `output: 'standalone'` doesn't break the host build or CI's `frontend-commons` job.**
  This was only ever exercised inside Docker, never on the host.

**6. First automated container deploy**, then watch `docker compose -f docker-compose.yml
logs` and run `deploy/healthcheck.sh` on the VM.

### Verification gaps — be honest about these, don't assume

- **Nothing was tested on the actual VM.** All verification was local, on Apple Silicon.
- The CI `deploy` job has **never run** — it needs the VM plus repo secrets. It is
  YAML-valid, `actionlint`-clean, and its script is shellcheck-clean at warning level,
  but its runtime behavior is unproven.
- The **Django test suite was not run** during suite 42 (no Python app source changed —
  only `next.config.ts`), so it is untested against the suite-41 refactor in this tree.
- `pnpm build` on the host with `output: 'standalone'` is unverified.
- The broadcast end-to-end submit flow (enqueue → worker drains → Playwright fills a real
  form) was not exercised; only that Chromium launches in both workers.

### Already done, don't redo

- The 6 pending suite-41 migrations were applied to Neon branch `test_neondb_cacheverify`
  with the owner's approval. `migrate --check` is clean there. 5 were
  `SeparateDatabaseAndState` (zero DDL); 1 was a reversible `RunPython` repointing beat
  task paths.
- Suite 42 is queued in `notion-sync/OUTBOX.md` as `Needs QA` (tickets 42.1–42.8) and
  recorded in `notion-sync/STATE.md`. Don't re-add it. Follow `CLAUDE.md`'s Notion rules
  for any new board changes.
- Three DEPLOY.md doc-drift items are already fixed: the static path (`staticfiles_build/
  static`, not `staticfiles/`), the obsolete `apt install postgresql-client`, and the
  gunicorn unix socket (now TCP `backend:8000`).

### Useful context

The six bugs suite 42 found were all invisible to code review and only surfaced by
running things — root-owned `/app` breaking collectstatic, nginx refusing to boot when any
upstream was missing (one dead frontend = total ingress outage), the `REDIS_URL` localhost
trap, the `DJANGO_ALLOWED_HOSTS` KeyError, a `DisallowedHost` 400, and `.dockerignore`
leaking private keys into the build context. **Prefer executing over reading** when
verifying anything here.
