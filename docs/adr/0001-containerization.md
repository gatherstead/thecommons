# ADR 0001: Containerization of The Commons

## Status

Accepted — 2026-08-01. This ADR records four decisions already made for the
Dockerization suite; later tickets in the suite (Dockerfiles, compose file,
CI changes, `DEPLOY.md` rewrite) build on these without re-litigating them.

## Context

The Commons runs today as a hand-provisioned Oracle Cloud VM (Ubuntu 24.04,
ARM64, 1 OCPU / 6 GB — `DEPLOY.md` §Facts) with seven long-lived processes
wired up as individual systemd units (`gunicorn`, `nextjs`, `redis-server`,
`celery`, `celerybeat`, `broadcast-worker`, `scrape-worker`) plus a hand-edited
nginx config. There is no container tooling anywhere in this repo today — no
Dockerfile, no compose file, not even a stray reference to "docker" in the
docs. Provisioning a second environment (or recovering this one from scratch)
means re-reading all of `DEPLOY.md` Part 1 by hand.

Two incidents make the cost of that gap concrete:

- The 2026-07-21 scheduler outage (`docs/prod-incident-2026-07-21-scheduler-outage.md`):
  all four Celery units execed `/snap/bin/uv run celery …`, and snap's `uv`
  spawns its child inside a transient scope under `user@1001.service` (the
  *user* session manager, not the unit's own cgroup). A post-deploy SSH logout
  tore down `user-1001.slice` and killed the whole async stack with
  `status=0/SUCCESS` — a clean exit `Restart=on-failure` correctly declined to
  restart. `gunicorn` and `nextjs`, which exec their binaries directly, never
  went through snap and stayed up 68 days straight over the same window. The
  fix in `deploy/*.service` today is `ExecStart=.venv/bin/celery …` plus
  `loginctl enable-linger ubuntu` as defense-in-depth.
- The nginx config is one file, `/etc/nginx/sites-available/thecommons`, with
  `server` blocks for all three subdomains hand-appended over several suites
  (`DEPLOY.md` §nginx, `deploy/nginx-broadcast.conf.snippet`). There is no way
  to diff, review, or roll back a change to it short of SSHing in.

This ADR records the four load-bearing decisions for moving this stack into
containers, and the reasoning behind each, so a future engineer sees *why*
rather than re-deriving it from the compose file.

---

## Decision 1 — nginx runs in a container, as the single ingress

**Decision:** nginx moves into a container and becomes the sole entrypoint for
all three subdomains (`thecommons.town`, `api.thecommons.town`,
`broadcast.thecommons.town`), replacing the host-installed nginx.

**Rationale:**

- **Local/prod parity.** Today's nginx config exists only on the VM; nothing
  about routing, TLS termination, or the static/media aliasing is exercised
  locally. Containerizing it means the same image and (mostly) the same
  config file run in both places — the current one-file-many-`server`-blocks
  structure (`DEPLOY.md` §nginx, `deploy/nginx-broadcast.conf.snippet`) is
  preserved, not restructured, since that convention is explicitly called out
  in the repo as deliberate ("do NOT create a separate sites-available file").
- **The Cloudflare origin cert is bind-mounted, never baked in.** TLS
  termination happens with the Cloudflare origin cert at
  `/etc/ssl/cloudflare/thecommons.town.{pem,key}` under Full (strict) mode
  (`DEPLOY.md` §Facts, line 22). This must be a **read-only bind mount**, not
  a `COPY` into an image layer — an image layer would (a) require a rebuild
  and re-push on every cert rotation and (b) risk the private key ending up
  in an image that could be pulled or inspected outside the VM. A bind mount
  keeps the key exactly where it is today, filesystem-permissioned, outside
  the image entirely.

**Consequence — gunicorn moves from a unix socket to TCP.** Today gunicorn
listens on `unix:/run/gunicorn/gunicorn.sock` (`DEPLOY.md` §Services, line
518) with `RuntimeDirectory=gunicorn` creating the socket dir. A unix socket
can't cross a container boundary the way it's used today (nginx and gunicorn
sharing a host filesystem path), so nginx talks to the backend over the
compose network instead: `proxy_pass http://backend:8000;`. This is a strictly
weaker isolation posture than a filesystem-permissioned socket (any container
on the compose network can reach port 8000), but it's the standard pattern
for containerized nginx+app pairs and the compose network is not
host-reachable.

**Cutover risk to flag explicitly:** the host nginx must be **stopped and
disabled** (`sudo systemctl disable --now nginx`) before the container nginx
binds 80/443 — two processes cannot bind the same ports. This is a
first-deploy-only step, but it is the one step in this whole suite where a
mistake produces an immediate, visible outage (container fails to bind, or
host nginx silently keeps serving the old config). The iptables ACCEPT rules
for 80/443 already in place (`DEPLOY.md` §Firewall) are unaffected — they act
on the port, not on which process holds it.

---

## Decision 2 — Redis runs in a container

**Decision:** Redis moves into a container (`redis:7-alpine`), replacing the
`apt install redis-server` + `/etc/redis/redis.conf` setup in `DEPLOY.md`
Part 1 §2.

**Rationale:**

- **Self-contained one-command local bring-up.** Redis is currently the only
  piece of async infrastructure that has no local-dev story at all — `docs/broadcast.md`
  and `DEPLOY.md` both describe it as prod-only apt install. Containerizing
  it means `docker compose up` gives a working broker with no host packages.
- **Clean path to a managed service later.** `redis:7-alpine` in a container
  today, backed by a named volume, ports directly to ElastiCache (or any
  managed Redis) later — swap the connection URL, drop the container. No
  application code changes either way, for the same reason the DB-split
  already requires none (next point).
- **No code changes, because the existing DB-split already lives in env
  vars.** The one-instance/two-logical-DB split — **DB 0 = Celery
  broker + results, DB 1 = Django cache** — is not hardcoded; it falls
  straight out of `REDIS_URL` (`backend/settings/base.py:146`, feeding
  `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND`) and `REDIS_CACHE_URL`
  (`backend/settings/base.py:190-193`, the `CACHES` `LOCATION`). Point both
  env vars at the same containerized Redis with `/0` and `/1` suffixes and
  the split is unchanged.
- **`requirepass` is kept**, sourced from `.env` exactly as today
  (`DEPLOY.md` §2: "The password lives only in `backendServer/.env`, never in
  git") — containerizing Redis is not a reason to relax that.
- **Named volume for persistence**, since Redis here is not purely a cache —
  DB 0 holds in-flight Celery task state and `django-celery-beat`'s schedule
  metadata (the schedule itself is in Postgres via `DatabaseScheduler`, but
  broker state is Redis-resident) — an unpersisted Redis would drop
  in-flight/queued tasks on every container restart.

---

## Decision 3 — Postgres is NOT containerized; it stays on Neon

**Decision:** Postgres is not part of the compose stack. Both prod and local
development continue to point at Neon (external, managed) — prod at the prod
branch, local dev at a Neon dev branch per `docs/dev-db-isolation.md`.

**Rationale:** Neon already gives us managed backups, branching, and
point-in-time recovery — the actual restore mechanism `DEPLOY.md`'s guarded
migrate calls out explicitly ("this dump is belt-and-suspenders; Neon
PITR/branching is the real restore mechanism"). Running a containerized
Postgres alongside a service that's already fully externalized would just be
two sources of truth for the same data, for local dev only, with no benefit
prod can use.

**Consequence — the CI pre-migrate `pg_dump` needs a new home.** The deploy
job's guarded-migrate step (`.github/workflows/ci.yml:230-262`) takes a
`pg_dump` before applying any pending migration and currently depends on a
**host-installed** `postgresql-client` (`DEPLOY.md` line 412: "fails the
deploy if `pg_dump` is missing — one-time VM prep: `sudo apt install -y
postgresql-client`"). Once nginx/Redis/the app tiers are containerized, we
don't want a bare-metal apt package as the one remaining thing keeping the
backup step alive — it becomes a throwaway `postgres:18-alpine` container,
invoked for the duration of the dump and discarded (`docker run --rm
postgres:18-alpine pg_dump "$DATABASE_URL" | gzip > …`).

**Why version 18 specifically, not "latest" or matched-to-Neon:** `pg_dump`
can dump a server *older* than itself, but refuses to dump one *newer* than
itself. Pinning the **newest** available client image is therefore
unconditionally safe regardless of what Postgres major version the Neon
branch is actually running — there's no version-matching exercise to redo
every time Neon upgrades its own server version, and no risk of the dump
silently failing the week Neon ships a major bump ahead of a stale pin.

---

## Decision 4 — build artifacts are baked into images; only real state gets volumes

This is the split most likely to be gotten wrong later, so it's spelled out
explicitly both ways.

### Baked at build time (NOT volumes)

| Artifact | Source | Why baked, not a volume |
|---|---|---|
| Django `collectstatic` output (`staticfiles/`) | `manage.py collectstatic --noinput` (`DEPLOY.md` §3, run on every deploy) | Regenerated from source on every build. A volume here would be strictly **worse** than baking: stale static files from a previous deploy could survive into a new container and be served alongside new code, reintroducing exactly the "admin has no CSS / stale bundle" class of bug `DEPLOY.md`'s troubleshooting table already lists. |
| `broadcastWeb`'s compiled `dist/` | `pnpm run build` (`DEPLOY.md` §7, currently served by nginx directly off the VM filesystem, "static → dist/, served directly by nginx, no service") | Same reasoning — a build artifact, not state. The CI smoke check that greps the built JS for a `thecommons.town` API origin (`ci.yml:274-281`) exists precisely because a stale/misconfigured `dist/` is a real failure mode; a volume would make that class of bug *stickier*, not safer. |

The nginx image's Dockerfile is expected to `COPY --from=` both of these out
of dedicated build stages, so the running nginx container always serves
exactly what was built alongside the code it's serving — never a leftover
from a previous image.

### Volumes (real state that must survive a container restart)

| Path | Env var | What it holds | Why it must be a volume |
|---|---|---|---|
| `/home/ubuntu/broadcast/media` | `MEDIA_ROOT` | Client-uploaded broadcast event images | `DEPLOY.md` (§nginx, line 631) states these are **kept indefinitely with no pruning job** — this is genuine, growing user data, not a cache or a rebuildable artifact. Losing it on a restart would delete client uploads outright. |
| `/home/ubuntu/backups` | — (target of the CI pre-migrate `pg_dump`, `ci.yml:246`) | Pre-migrate `.sql.gz` dumps, newest 5 kept | Call this out explicitly: **if this path were ephemeral, the dump would be written and then discarded the moment the container that wrote it exits**, silently turning the guarded-migrate safety net into a no-op — the deploy would still *look* successful (the dump command exits 0), but there would be nothing to restore from after the fact. This is the one volume in the whole list where getting it wrong fails silently rather than loudly. |
| `/home/ubuntu/broadcast/screenshots`, `/home/ubuntu/broadcast/downloads` | `BROADCAST_SCREENSHOT_DIR`, `BROADCAST_DOWNLOAD_DIR` | Playwright debug artifacts from broadcast form-fill runs | Not user-facing data, but operators reference these when triaging a `needs_manual`/failed broadcast target after the fact (`docs/broadcast.md` §Models) — losing them on every restart would remove the only forensic trail for a failed submission. |
| (unnamed, Redis's data dir) | — | Celery broker state (DB 0), Django cache (DB 1) | Covered under Decision 2 — a named volume so queued/in-flight task state survives a Redis container restart. |

The dividing line, stated once for reuse: **if a path can be fully
regenerated by re-running the build (or re-running `collectstatic`/`pnpm
build`), it's baked. If losing it on restart would destroy something no
rebuild can recreate — user uploads, a backup, a debug trail, cache/broker
state that's actively in flight — it's a volume.**

---

## Base images

All images must have working **arm64** variants — the only deploy target
today is the Oracle Cloud VM, Ubuntu 24.04 **ARM64** (`DEPLOY.md` §Facts,
line 15). This ruled out anything without a maintained arm64 build.

| Component | Image | Notes |
|---|---|---|
| Backend (Django/gunicorn) + Playwright workers (`scrape-worker`, `broadcast-worker`) | `python:3.13-slim` | Matches the `python-version: "3.13"` pinned in CI (`ci.yml:23,82`) and `backendServer/pyproject.toml`. |
| `theCommonsWeb`, `broadcastWeb` | `node:22-slim` | Matches Node 22 pinned in CI (`ci.yml:32,109`) and the `pnpm 11.1.1` requirement (pnpm 11 needs Node ≥22.13, `ci.yml:104`). |
| Redis | `redis:7-alpine` | See Decision 2. |
| nginx | `nginx:1.27-alpine` | See Decision 1. |
| Postgres client (pre-migrate dump sidecar only — not a running service) | `postgres:18-alpine` | See Decision 3; deliberately newer than any Postgres version Neon is expected to run. |

**Chromium is installed into the worker image via `uv run playwright install
--with-deps chromium`, not via a pinned `mcr.microsoft.com/playwright` base
image.** `backendServer/pyproject.toml:31` pins `playwright>=1.60.0`, and
`uv.lock` locks the resolved version exactly (`uv.lock:1006`, `1.60.0`).
Installing the browser build through that same `playwright` package
guarantees the Chromium build matches the library version resolved by
`uv.lock` — that's exactly what `playwright install` does: it fetches the
browser build matching the installed package's version, not a browser
version chosen independently. A pinned Microsoft Playwright base image
instead fixes the Chromium+library pair to whatever version *that image*
shipped with; the moment someone bumps `playwright` in `pyproject.toml`
without also bumping the base image tag (or vice versa), the library and
browser drift out of sync — the exact class of bug Playwright's own docs
warn causes cryptic `Executable doesn't exist` / protocol-mismatch failures.
Installing through the locked library keeps one version number
(`uv.lock`'s) as the single source of truth instead of two that can silently
diverge. This also matches current prod practice (`DEPLOY.md` Part 1 §5.3 /
§6.1: `uv run playwright install chromium` + `install-deps`, bundled Chromium
only — arm64 has no branded "Chrome").

---

## Historical note: why the systemd units exec binaries directly (and why containers make it moot)

Every unit in `deploy/*.service` execs `.venv/bin/celery` directly instead of
going through `uv run`. This looks like an odd style choice until you know
why: snap-packaged `uv run` spawned its child process inside a transient
`snap.astral-uv.uv-*.scope` under `user@1001.service` — the *user* session
manager, not the unit's own cgroup. With linger off, `systemd-logind` tore
that user slice down the moment the deploying SSH session ended, and every
`uv run`-based unit died within a minute of each deploy, silently, with
`status=0/SUCCESS` — a clean exit that `Restart=on-failure` correctly
declined to restart. That's what took the entire async stack down for 8
days starting 2026-07-21 while `gunicorn` and `nextjs` (which never went
through snap) stayed up the whole time (full forensics:
`docs/prod-incident-2026-07-21-scheduler-outage.md`). The current mitigation
is two-layered: exec the venv binary directly (removes the mechanism
entirely) plus `Restart=always` + `loginctl enable-linger ubuntu` as
defense-in-depth in case a unit is ever reverted.

**Containers remove this failure mode by construction** — there is no snap,
no `logind`, no per-user systemd slice inside a container's PID namespace for
a lost SSH session to tear down. The elaborate two-layer mitigation
(exec-direct + linger + `Restart=always`) is a workaround for a systemd/snap
interaction that containers simply don't have, and should **not** be
cargo-culted forward into the compose/Dockerfile setup as if it were still
solving a live problem.

One piece *is* still worth carrying forward, for an unrelated reason: **exec
binaries directly rather than through a wrapper shell**, so the container's
PID 1 is the actual process (`celery`, `gunicorn`, …) and receives `SIGTERM`
directly on `docker stop` / `docker compose down` for a clean shutdown,
rather than a shell that may not forward signals to its child. Same
`ExecStart=` shape as today, different reason.

---

## Doc drift observed while researching this ADR

- `DEPLOY.md` line 412 ("one-time VM prep: `sudo apt install -y
  postgresql-client`") describes the pre-containerization world and will be
  stale once the pre-migrate dump moves into the `postgres:18-alpine`
  sidecar (Decision 3). Not fixed here — `DEPLOY.md` is explicitly out of
  scope for this ticket and owned by a later one in this suite — flagging so
  whoever writes that ticket knows this line needs to go.
- `DEPLOY.md` §Services (line 518) documents gunicorn on
  `unix:/run/gunicorn/gunicorn.sock`. This ADR's Decision 1 changes that to
  TCP (`backend:8000`) once nginx is containerized. This isn't contradictory
  doc drift so much as a documented, deliberate divergence this ADR
  introduces — noting it here so the DEPLOY.md rewrite ticket doesn't miss
  the socket→TCP change as one more thing to update, beyond the nginx
  section itself.
- No contradiction found between the brief and the repo on any of the four
  decisions themselves — `REDIS_URL`/`REDIS_CACHE_URL` really do carry the
  whole DB-split with no code changes needed (verified at
  `backend/settings/base.py:146-193`), `MEDIA_ROOT` really is documented as
  unpruned (`DEPLOY.md` line 631), and `playwright` really is a `uv.lock`-pinned
  dependency rather than a loose one (`pyproject.toml:31`, resolved to exactly
  `1.60.0` in `uv.lock`).
