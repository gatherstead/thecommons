# Deployment Runbook — The Commons

This is the single source of truth for deploying The Commons to the production VM.
The stack is **containerized** (Docker Compose) — this replaces the old systemd-unit
runbook. Follow **Part 1** top-to-bottom for the **one-time VM prep** that gates the
first automated container deploy (the VM does not have Docker on it yet). After that,
deploys are automatic — see **Part 2**. **Part 3** is reference (services, env vars,
nginx, firewall, troubleshooting).

> ⚠️ **Every prod Compose command in this document passes `-f docker-compose.yml`
> explicitly, and so must you.** A bare `docker compose` (no `-f`) auto-loads
> `docker-compose.override.yml` from the same directory — that file is **local-dev
> only** (plain HTTP nginx with no cert, repo-relative bind-mount paths, `DJANGO_ENV=dev`).
> Running it against the VM would deploy the dev config to prod: no TLS, wrong
> hostnames, wrong Redis auth. If you ever type `docker compose` without `-f
> docker-compose.yml` on the VM, stop and re-type it.

---

## Facts you need first

| Thing | Value |
|-------|-------|
| Provider / OS | Oracle Cloud (OCI), Ubuntu 24.04, ARM64 (aarch64), 1 OCPU / 6 GB |
| VM IP | `129.80.229.41` |
| SSH | `ssh -i oraclevps.key ubuntu@129.80.229.41` (key is in repo root — **never commit it**) |
| Repo path on VM | `/home/ubuntu/thecommons` |
| Deploy user | `ubuntu` (member of the `docker` group; every container runs as `ubuntu`'s Docker daemon, unprivileged) |
| Container runtime | Docker Engine + the `docker compose` v2 plugin (arm64). **No `sudo` in the deploy path** — group membership is enough. |
| Python / Node on the VM | **Not used directly anymore.** `uv` and `pnpm` still matter for local dev and CI (they build the images), but the VM never runs `uv sync`, `manage.py migrate` bare, or `pnpm build` outside a container — see Part 2. |
| DNS / TLS | Cloudflare, proxied (orange cloud), SSL mode **Full (strict)**; origin cert at `/etc/ssl/cloudflare/thecommons.town.{pem,key}`, bind-mounted read-only into the `nginx` container |

> **What changed since the last runbook:** the seven systemd units (`gunicorn`,
> `nextjs`, `redis-server`, `celery`, `celerybeat`, `broadcast-worker`,
> `scrape-worker`) plus the hand-edited nginx config are replaced by
> [`docker-compose.yml`](docker-compose.yml) — one file describing the whole
> service graph, built and run with `docker compose`. `git pull` + `uv sync` +
> `pnpm build` + `sudo systemctl restart …` is gone from the deploy path entirely;
> CI now runs `docker compose -f docker-compose.yml build` and
> `docker compose -f docker-compose.yml up -d`. See
> [`docs/adr/0001-containerization.md`](docs/adr/0001-containerization.md) for the
> full rationale behind each decision (nginx-in-a-container, Redis-in-a-container,
> Postgres staying external on Neon, what's baked vs. volumed).

---

# Part 1 — One-time VM prep (blocking)

**This gates the first automated container deploy.** The `deploy` job in
[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs `docker compose -f
docker-compose.yml build` and `up -d` on every push to `main` — that fails
immediately if the VM doesn't have Docker, the `ubuntu` user can't run it without
`sudo`, or the bind-mount directories/env files it depends on don't exist. Do all
eleven steps in order before the first push to `main` after this cutover.

> ⚠️ **If you check a feature branch out on the VM to rehearse this before
> merging, expect an immediate 500 on `api.thecommons.town`.** The systemd
> gunicorn is still running and imports Python modules lazily *from the working
> tree*, so a `git checkout` swaps files underneath a process whose settings are
> already loaded in memory. A branch carrying an app-layout change (the suite-41
> `accounts`/`newsletter` extraction is the live example) then produces
> `RuntimeError: Model class accounts.models.BetterAuthUser doesn't declare an
> explicit app_label and isn't in an application in INSTALLED_APPS` — new file,
> old `INSTALLED_APPS`. `sudo systemctl restart gunicorn` immediately after the
> checkout reloads both consistently and clears it. Restart the Celery units too
> if the branch moved any task modules. None of this applies once the stack is
> containerized: an image is a snapshot, so a checkout can't change code out from
> under a running container.

## 1. Install Docker Engine + the Compose v2 plugin (arm64)

```bash
ssh -i oraclevps.key ubuntu@129.80.229.41
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

`dpkg --print-architecture` resolves to `arm64` automatically on this VM — no
manual platform pin needed; every image in this stack (`python:3.13-slim`,
`node:22-slim`, `redis:7-alpine`, `nginx:1.27-alpine`, `postgres:18-alpine`) ships
a maintained arm64 build (`docs/adr/0001-containerization.md` §Base images).

Verify:

```bash
docker --version
docker compose version        # the `compose` SUBCOMMAND must work — that's the plugin, not the old standalone `docker-compose` binary.
                              # Don't assert a specific major here; what matters is that `docker compose` (space, not hyphen)
                              # resolves at all. Verified installed on this VM: Docker 29.7.1 / Compose v5.3.1.
```

## 2. Add `ubuntu` to the `docker` group — and prove it non-interactively

```bash
sudo usermod -aG docker ubuntu
```

**Group membership only applies to sessions started *after* this command runs.**
The SSH session you just ran `usermod` in still has the old group list — testing
`docker ps` in that same session (or papering over it with `newgrp docker`) proves
nothing about how CI will actually connect. CI's `appleboy/ssh-action` opens a
brand-new non-interactive SSH connection on every run (`ssh host 'command'`, not an
interactive login shell), so that's exactly what you must test:

```bash
exit                                          # close the current SSH session completely
ssh -i oraclevps.key ubuntu@129.80.229.41 'id -nG; docker version --format "{{.Server.Version}}"'
```

`id -nG` must list `docker`, and the second command must print a server version
with **no `sudo` and no permission-denied error** on the Docker socket. If it
fails, the group add didn't take (check `getent group docker`) or the session
really is stale — reconnect fresh and retry.

## 3. Create the persistent host directories (bind mounts)

```bash
mkdir -p /home/ubuntu/broadcast/{media,screenshots,downloads} /home/ubuntu/backups
```

These back real state that must survive a container restart — client-uploaded
event images, Playwright debug artifacts, and pre-migrate `pg_dump`s
(`docs/adr/0001-containerization.md` §Decision 4). `docker-compose.yml` bind-mounts
them at the identical absolute path inside the `backend`, `broadcast-worker`,
`scrape-worker`, `migrate`, and `nginx` containers.

They must be **writable by uid 1000** — the image's non-root `app` user
(`backendServer/Dockerfile`: `useradd --uid 1000 --gid app …`) — **and** by the
host's `ubuntu` user, which is what the deploy pipeline runs as.

> ⚠️ **On this VM `ubuntu` is uid 1001, not 1000.** The Oracle Ubuntu image ships
> an `opc` user that already holds uid 1000 (`getent passwd 1000 1001` to see it).
> So a plain `sudo chown -R 1000:1000` — the obvious reading of "writable by uid
> 1000" — hands these directories to `opc` and locks `ubuntu` *out* of them. That
> silently breaks the backup-pruning step in Part 2 §4
> (`ls -1t /home/ubuntu/backups/… | xargs rm`, which runs as `ubuntu`), while the
> containers themselves stay perfectly happy — a failure that only shows up as
> backups quietly accumulating forever. Don't assume; check.

Give the container the ownership and the host user the group, with setgid so
newly created files keep inheriting that group:

```bash
getent passwd 1000 1001                       # confirm who actually holds each uid
sudo chown -R 1000:1001 /home/ubuntu/broadcast /home/ubuntu/backups
sudo chmod -R 2775      /home/ubuntu/broadcast /home/ubuntu/backups
```

That leaves uid 1000 (the container's `app` user) as **owner**, and gid 1001
(`ubuntu`) as a **group** with write — so both sides can write the same trees. Use
numeric ids rather than names: the container's `app` user is fixed at uid 1000
regardless of what the host calls that uid. Verify both directions before moving
on:

```bash
touch /home/ubuntu/broadcast/media/.wtest && rm /home/ubuntu/broadcast/media/.wtest   # host `ubuntu`
docker run --rm -u 1000:1000 -v /home/ubuntu/broadcast/media:/m alpine \
  sh -c 'touch /m/.ctest && rm /m/.ctest'                                             # container uid 1000
```

## 4. Confirm the Cloudflare origin cert is in place

```bash
ls -l /etc/ssl/cloudflare/thecommons.town.pem /etc/ssl/cloudflare/thecommons.town.key
```

The `nginx` container bind-mounts `/etc/ssl/cloudflare` read-only
(`docker-compose.yml`'s `nginx.volumes`) — it is **never** baked into the image
(a rebuild-and-repush on every cert rotation, and the private key ending up in a
pullable image layer, are exactly what a bind mount avoids —
`docs/adr/0001-containerization.md` §Decision 1). If this cert isn't already on the
box from the earlier broadcast-subdomain rollout, reissue a
`thecommons.town, *.thecommons.town` origin cert in the Cloudflare dashboard and
place it here before continuing — `nginx` refuses to boot with `listen 443 ssl`
blocks pointing at missing files.

## 5. Confirm the three runtime env files exist on the box

```bash
ls -l /home/ubuntu/thecommons/backendServer/.env \
      /home/ubuntu/thecommons/theCommonsWeb/.env.local \
      /home/ubuntu/thecommons/broadcastWeb/.env
```

These are consumed two different ways, and it matters which:

- **`env_file:`** in `docker-compose.yml` (all Django/Celery services, plus
  `nextjs`) loads them into the container's runtime environment when it starts.
- **Build args** (`nextjs` and `broadcast-spa-build`'s `NEXT_PUBLIC_*`/`VITE_*`
  values) get baked into the compiled JS at *build* time via Compose variable
  interpolation, which only reads the shell environment or a `.env` file next to
  `docker-compose.yml` — it **cannot** read `theCommonsWeb/.env.local` or
  `broadcastWeb/.env` directly. Part 2 covers how the deploy pipeline bridges this
  (`source` the real files, re-export under the `NEXTJS_BUILD_*`/`BROADCAST_BUILD_*`
  names the build args read).

If any of the three files is missing, create it from its `.env.example` and fill
in real values before proceeding — every other step assumes they're already
correct except step 6, which calls out the one change that's mandatory.

> ⚠️ **Quote any value containing `&`, a space, or `#`.** The build path
> (`set -a; . theCommonsWeb/.env.local`) is **shell sourcing, not a dotenv
> parser** — it does not reject a malformed line, it *mis-parses* it. A bare
> Neon URL is the live example, because its query string contains `&`:
>
> ```
> DATABASE_URL=postgres://…?sslmode=require&channel_binding=require     # BROKEN
> DATABASE_URL='postgres://…?sslmode=require&channel_binding=require'   # correct
> ```
>
> The shell reads `VAR=x & y=z` as "assign `x` in a **background subshell**,
> then assign `y`", so `DATABASE_URL` never reaches the calling shell. Compose's
> `env_file:` parses the same file correctly, so the running containers look
> fine — only the *build args* are wrong, and compose's `${VAR:-placeholder}`
> defaults turn that into a build that succeeds with placeholder config baked
> in. `backendServer/.env` already quotes its `DATABASE_URL`;
> `theCommonsWeb/.env.local` did not, which is what surfaced this.
>
> Audit all three files at once — this compares each key's literal value against
> what sourcing actually yields, and prints no secrets:
>
> ```bash
> cd /home/ubuntu/thecommons
> for f in backendServer/.env theCommonsWeb/.env.local broadcastWeb/.env; do
>   echo "=== $f ==="
>   awk '/^[A-Za-z_][A-Za-z0-9_]*=/ {k=substr($0,1,index($0,"=")-1); v=substr($0,index($0,"=")+1);
>        if ((substr(v,1,1)=="\"" && substr(v,length(v),1)=="\"") || (substr(v,1,1)=="'"'"'" && substr(v,length(v),1)=="'"'"'")) v=substr(v,2,length(v)-2);
>        print k"\t"length(v)}' "$f" > /tmp/lit
>   ( set -a; . "$f" >/dev/null 2>&1; set +a
>     while IFS=$'\t' read -r k n; do eval "cur=\${$k-__UNSET__}"
>       [ "$cur" = "__UNSET__" ] && { echo "  $k BROKEN (unset after sourcing)"; continue; }
>       [ "${#cur}" = "$n" ] || echo "  $k TRUNCATED ($n -> ${#cur})"
>     done < /tmp/lit )
> done
> ```
>
> The `deploy` job also fails loudly now if any required build arg comes out
> empty (`.github/workflows/ci.yml`), but fix the file rather than relying on
> that backstop.

## 6. ⚠️ Blocking: point `backendServer/.env` at the container Redis, not localhost

**This is the step this whole suite exists to get right — treat it as a release
blocker, not a nit.** `backendServer/.env` almost certainly still has:

```
REDIS_URL=redis://:<REDIS_PASS>@127.0.0.1:6379/0
REDIS_CACHE_URL=redis://:<REDIS_PASS>@127.0.0.1:6379/1
```

Inside a container, `127.0.0.1`/`localhost` is *that container itself* — Redis now
runs in its own container reachable only by its Compose service name. Leaving
these as-is does **not** error at startup: Celery just silently connects to
nothing and no task ever runs, while gunicorn, nginx, and everything synchronous
stays green. That is the exact shape of the 2026-07-21 outage (async stack dead,
everything else looked healthy) — see §Historical incident below. Fix it:

```
REDIS_URL=redis://:<REDIS_PASS>@redis:6379/0
REDIS_CACHE_URL=redis://:<REDIS_PASS>@redis:6379/1
```

The `<REDIS_PASS>` embedded in both URLs must match a `REDIS_PASSWORD` entry
you add to the same file — the `redis` container reads `REDIS_PASSWORD` directly
(`docker-compose.yml`'s `redis.command`) and starts `--requirepass` with it; Django
and Celery never read `REDIS_PASSWORD` itself, only the URLs above, which already
carry the password in their `:<password>@` segment. If it isn't already present:

```
REDIS_PASSWORD=<REDIS_PASS>            # same value embedded in the two URLs above
```

While you're in this file, confirm two more things `prod.py` hard-requires —
missing either crashes every container on boot, not just Celery:

- **`DJANGO_ALLOWED_HOSTS`** is set (`backend/settings/prod.py:16` does
  `os.environ["DJANGO_ALLOWED_HOSTS"]` — a hard `KeyError`, not a default, if it's
  absent). Expected value: `localhost,127.0.0.1,api.thecommons.town`.
  `docker-compose.override.yml` (local dev only) sets `DJANGO_ENV=dev` specifically
  to dodge this same crash on a laptop that has no reason to set this var — that
  workaround does not apply on the VM.
- **`DJANGO_ENV=prod`** is set. `docker-compose.yml` also sets it via
  `environment: DJANGO_ENV: prod` on every backend/Celery service, so this is
  belt-and-suspenders — but a stray unset/wrong value in `.env` that later
  overrides it (env_file loads before `environment:` in Compose precedence,
  so `environment:` wins) is not worth relying on. Confirm it's `prod` in the file
  too.

`manage.py healthcheck` pings Redis DB 0 and round-trips DB 1, so the hourly
watchdog (Part 3 §Health check) will eventually catch a missed edit here — but the
point of calling this out as its own step is to not discover it that way.

> ⚠️ **This edit breaks the still-running host stack the moment you save it.**
> Steps 7–9 haven't happened yet, so the *systemd* gunicorn/celery are still
> serving production out of this same `.env` — and on the host there is no such
> hostname as `redis`, so every cached read starts throwing
> `redis.exceptions.ConnectionError: Error -3 connecting to redis:6379.
> Temporary failure in name resolution` and `api.thecommons.town/events/` 500s.
> The step reads like inert preparation; it isn't. Bridge it before you edit, so
> the host stack keeps resolving `redis` to the local `redis-server` until the
> containers take over:
>
> ```bash
> grep -q '^127.0.0.1[[:space:]]\+redis\b' /etc/hosts || echo '127.0.0.1 redis' | sudo tee -a /etc/hosts
> sudo systemctl restart gunicorn celery celerybeat broadcast-worker scrape-worker
> ```
>
> Containers are unaffected either way — they resolve `redis` through Docker's
> embedded DNS inside their own namespace and never consult the host's
> `/etc/hosts`. **Remove the line once step 9 has retired the host units**
> (`sudo sed -i '/^127\.0\.0\.1[[:space:]]\+redis$/d' /etc/hosts`); leaving it
> behind is harmless but will mislead whoever debugs this box next.

## 7. First manual bring-up — everything except `nginx`

Bring the non-ingress services up by hand once, before CI ever touches the box,
so you can see them start clean without racing the host-nginx cutover in the next
step:

```bash
cd /home/ubuntu/thecommons
docker compose -f docker-compose.yml up -d --build redis migrate backend celery celerybeat broadcast-worker scrape-worker nextjs
docker compose -f docker-compose.yml ps
```

`migrate` is a one-shot container (`restart: "no"`) — it applies migrations
(seeding the `django_celery_beat` schedule tables in the process) and exits 0;
`docker compose ps` will show it `Exited (0)`, which is correct, not a failure.
Every other service listed should show `running`. Then run the full report:

```bash
bash deploy/healthcheck.sh
```

Expect `redis`, `backend`, `celery`, `celerybeat`, `broadcast-worker`, and
`scrape-worker` all `✓`, plus the app-level Redis/Postgres/Celery-ping/beat-schedule
checks from `manage.py healthcheck` running *inside* the `backend` container.
`nextjs` and `nginx` will `✗` here — `nginx` hasn't been started yet (next step),
and that's expected at this point.

## 8. Cutover: stop the host nginx, start the container nginx

**This is the one step in the whole suite where a mistake produces an immediate,
visible outage** (`docs/adr/0001-containerization.md` §Decision 1) — two processes
cannot bind ports 80/443 at once, so the container nginx cannot come up cleanly
until the host one is out of the way.

```bash
sudo systemctl disable --now nginx
docker compose -f docker-compose.yml up -d --build nginx
docker compose -f docker-compose.yml ps
```

Verify all three domains from outside the box:

```bash
curl -I https://thecommons.town/
curl -I https://api.thecommons.town/events/
curl -I https://broadcast.thecommons.town/
```

If `broadcast.thecommons.town` 526s, the origin cert doesn't cover the wildcard —
back to step 4. If any of the three hangs, it's the iptables
REJECT-before-ACCEPT gotcha — see Part 3 §Firewall (unchanged by containerization:
the container nginx still binds the host's 80/443 the same way the old one did).

## 9. Retire the old systemd units and the sudoers drop-in

Now that the containers own gunicorn, Next.js, and all four Celery roles, the old
units would only cause confusion (or a port clash) if left enabled:

```bash
sudo systemctl disable --now celery celerybeat broadcast-worker scrape-worker gunicorn nextjs
sudo rm -f /etc/systemd/system/{celery,celerybeat,broadcast-worker,scrape-worker,gunicorn,nextjs}.service
sudo systemctl daemon-reload
sudo rm -f /etc/sudoers.d/deploy-restart
```

Leave `redis-server` alone if it's still `apt`-installed from before — stop and
disable it too, since the `redis` container now owns port 6379:

```bash
sudo systemctl disable --now redis-server 2>/dev/null || true
```

`healthcheck.service`/`healthcheck.timer` are **not** part of this retirement —
they were rewritten to check containers (`docker compose ps` / `docker inspect`)
rather than `systemctl is-active`, and still run as a host-level systemd timer on
purpose (Part 3 §Health check explains why). Leave them installed, or install them
now if this is the first time — see that section.

## 10. Confirm the GitHub Actions secrets

The deploy job only needs the four secrets it already had — nothing new, since
Docker commands run unprivileged via the `docker` group instead of the old
`systemctl`-restart sudoers allowlist:

| Secret | Value |
|--------|-------|
| `ORACLE_SSH_KEY` | Full PEM **private** key for the deploy key (incl. BEGIN/END lines) |
| `ORACLE_HOST` | `129.80.229.41` (raw IP — Cloudflare won't proxy port 22) |
| `ORACLE_USER` | `ubuntu` |
| `ORACLE_KNOWN_HOSTS` | Output of `ssh-keyscan 129.80.229.41` (all key types — `.github/workflows/ci.yml`'s fingerprint step needs ECDSA/RSA/ED25519 all present, since `appleboy/ssh-action`'s Go SSH client negotiates ECDSA first) |

Confirm the deploy key still authenticates and the non-interactive Docker check
from step 2 still passes through it specifically (not just `oraclevps.key`):

```bash
ssh -i ~/.ssh/thecommons_deploy ubuntu@129.80.229.41 'id -nG; docker version --format "{{.Server.Version}}"'
```

## 11. Trigger and verify the first automated deploy

The `deploy` job runs only on **push to `main`**, gated on `backend`,
`frontend-commons`, and `frontend-broadcast` all passing.

- Push to `main` (or re-run the Action). Watch **Actions → CI**: three green test
  jobs → `deploy` starts.
- The `deploy` log should show, in order: `git pull`, `docker compose … build` (all
  services), the broadcast-bundle origin grep check, the guarded-migrate check,
  `docker compose … up -d`, the running-services assertion, then a separate
  post-deploy smoke-test job (three domain checks, the rate-limit regression probe,
  the auth-bridge probes). See Part 2 for what each of those actually does.
- Confirm the VM is on the pushed commit and every long-running service is up:
  ```bash
  ssh -i ~/.ssh/thecommons_deploy ubuntu@129.80.229.41 \
    'cd /home/ubuntu/thecommons && git log -1 --oneline && docker compose -f docker-compose.yml ps'
  ```

> **Budget 30–60 min for the first automated run.** It usually trips on something
> environmental — a bind-mount permission gap, a stale `.env`, `--frozen-lockfile`
> drift in `uv.lock`/`pnpm-lock.yaml`. Read the failing step's log
> (`docker compose -f docker-compose.yml logs <service>` on the VM reproduces most
> failures locally), fix it, push again.

---

# Part 2 — Ongoing deploys (automatic)

Once Part 1 is done, **every push to `main`** runs CI
(`.github/workflows/ci.yml`) and, after `backend`, `frontend-commons`, and
`frontend-broadcast` all pass, a gated `deploy` job SSHes into the VM and runs the
full container build-and-release sequence, followed by a separate post-deploy
smoke test. A failing test on `main` blocks the deploy entirely — nothing below
runs until all three test jobs are green.

**On the VM, in order:**

1. **`git pull origin main`** (after discarding any stray tracked
   `tsconfig.tsbuildinfo` that could block the fast-forward — a leftover from a
   pre-Docker deploy).
2. **Build every image**, arm64-native, no registry needed — the VM builds what it
   runs:
   ```bash
   (
     set -a
     . theCommonsWeb/.env.local
     . broadcastWeb/.env
     set +a
     export NEXTJS_BUILD_DATABASE_URL="$DATABASE_URL"
     export NEXTJS_BUILD_BETTER_AUTH_SECRET="$BETTER_AUTH_SECRET"
     export NEXTJS_BUILD_BETTER_AUTH_URL="$BETTER_AUTH_URL"
     export NEXTJS_BUILD_NEXT_PUBLIC_BETTER_AUTH_URL="$NEXT_PUBLIC_BETTER_AUTH_URL"
     export NEXTJS_BUILD_NEXT_PUBLIC_API_BASE_URL="$NEXT_PUBLIC_API_BASE_URL"
     export NEXTJS_BUILD_NEXT_PUBLIC_THE_COMMONS_API_KEY="$NEXT_PUBLIC_THE_COMMONS_API_KEY"
     export BROADCAST_BUILD_VITE_BROADCAST_API_BASE_URL="$VITE_BROADCAST_API_BASE_URL"
     export BROADCAST_BUILD_VITE_BETTER_AUTH_URL="$VITE_BETTER_AUTH_URL"
     export BROADCAST_BUILD_VITE_BROADCAST_EXTENSION_ID="$VITE_BROADCAST_EXTENSION_ID"
     docker compose -f docker-compose.yml build
   )
   ```
   This re-export is required because Compose's `${VAR:-default}` interpolation
   only reads the shell env or a root-level `.env` — it cannot read
   `theCommonsWeb/.env.local`/`broadcastWeb/.env` directly (see `docker-compose.yml`'s
   header comment). Skipping it silently ships the safe *placeholder* build-arg
   defaults instead of real config — a build that "succeeds" but is wrong.
3. **Guard against exactly that**: grep the built `broadcast-spa-build` bundle for
   a real `thecommons.town` API origin. A malformed `VITE_BROADCAST_API_BASE_URL`
   builds fine and misroutes every API call silently — this catches it before the
   image goes live:
   ```bash
   docker compose -f docker-compose.yml run --rm -T --no-deps --entrypoint sh broadcast-spa-build \
     -c 'grep -rq "https\?://[a-zA-Z0-9.-]*thecommons\.town" /app/dist/assets/*.js'
   ```
4. **Guarded migrate.** `migrate --check` exits non-zero only when unapplied
   migrations exist, and applies nothing itself — so prod only ever writes schema
   when there's real work, and never without a fresh dump first:
   ```bash
   docker compose -f docker-compose.yml run --rm -T --no-deps migrate python manage.py migrate --check
   ```
   If that fails (migrations pending): take a `pg_dump` via a throwaway
   `postgres:18-alpine` container (the VM has no host-installed Postgres client —
   see the doc-drift correction below), keep the 5 newest, then apply:
   ```bash
   mkdir -p /home/ubuntu/backups
   (
     set -a; . backendServer/.env; set +a
     docker run --rm \
       -e DATABASE_URL \
       -v /home/ubuntu/backups:/backups \
       postgres:18-alpine \
       sh -c 'set -o pipefail; pg_dump "$DATABASE_URL" | gzip > "/backups/pre-migrate-$(date +%Y%m%d-%H%M%S).sql.gz"'
   )
   ls -1t /home/ubuntu/backups/pre-migrate-*.sql.gz | tail -n +6 | xargs -r rm -f --
   docker compose -f docker-compose.yml run --rm -T --no-deps migrate python manage.py migrate --noinput
   ```
   `postgres:18-alpine` is pinned deliberately — `pg_dump` can dump a server
   *older* than itself but refuses one *newer*, so the newest client image stays
   safe regardless of what Postgres version Neon runs, with no version-matching
   exercise to redo on every Neon upgrade. This dump is belt-and-suspenders; Neon
   PITR/branching is the real restore mechanism.

   `collectstatic` and both frontend builds are **not** separate deploy steps
   anymore — `collectstatic` runs at image build time (baked into
   `/app/staticfiles_build/static`, then `COPY --from=`'d into the `nginx` image),
   and both `pnpm build`s happened inside step 2 above. There is no host-side
   `node_modules` or static directory left to manage.
5. **Recreate every service from the images just built** — no `sudo`, no
   `systemctl restart`:
   ```bash
   docker compose -f docker-compose.yml up -d
   ```
6. **Health assertion.** `migrate` and `broadcast-spa-build` are one-shot
   (`restart: "no"`) and correctly exit 0, so they're excluded from the
   "still running" check; every long-running service must be:
   ```bash
   docker compose -f docker-compose.yml ps
   running_services=$(docker compose -f docker-compose.yml ps --status running --services)
   for svc in redis backend celery celerybeat broadcast-worker scrape-worker nextjs nginx; do
     printf '%s\n' "$running_services" | grep -qx "$svc" || { echo "$svc not running"; exit 1; }
   done
   ```
7. **Post-deploy smoke test** (separate SSH step, so a deploy that "succeeded" but
   serves garbage still fails CI): the three domains return 200, the broadcast
   rate-limit path returns 403 (not 500 — regression-checks the old
   Unix-socket-`REMOTE_ADDR` bug now that gunicorn is on TCP), `/auth/me` 401/403s
   on no/garbage credentials (never 500), and a real `THE_COMMONS_API_KEY` against
   `/events/create` gets past auth to a 400 body-validation error. See the
   `deploy`/`Post-deploy smoke test` steps in `.github/workflows/ci.yml` for the
   literal script.

### Manual fallback (CI down, or a hand hotfix)

```bash
cd /home/ubuntu/thecommons && git pull origin main

docker compose -f docker-compose.yml build                                       # rebuild whatever changed
docker compose -f docker-compose.yml run --rm --no-deps migrate python manage.py migrate --noinput   # if models changed
docker compose -f docker-compose.yml up -d                                       # recreate from the new images
docker compose -f docker-compose.yml ps
```

To restart a single service without touching the rest (e.g. picked up a `.env`
change with no code change):

```bash
docker compose -f docker-compose.yml up -d --no-deps <service>
```

If you only edited nginx's config (`deploy/nginx/thecommons.conf`), the change
needs a rebuild — it's baked into the image at build time, not bind-mounted, in
prod:

```bash
docker compose -f docker-compose.yml build nginx
docker compose -f docker-compose.yml up -d --no-deps nginx
```

---

# Part 3 — Reference

## Compose services

| Service | What it is | Image / build target | Command | Notes |
|---------|-----------|----------------------|---------|-------|
| `redis` | Celery broker + results (DB 0) + read-endpoint cache (DB 1) | `redis:7-alpine` | `redis-server --requirepass … --appendonly yes` | Named volume `redis-data`; password from `REDIS_PASSWORD` in `backendServer/.env` |
| `migrate` | One-shot: `manage.py migrate --noinput`, seeds `django_celery_beat` schedules | `backendServer/Dockerfile` target `app` | `python manage.py migrate --noinput` | `restart: "no"`; exits 0 by design — not a long-running service |
| `backend` | Django / gunicorn | `backendServer/Dockerfile` target `app` | `gunicorn --bind 0.0.0.0:8000 --workers 3 backend.wsgi:application` | TCP `:8000`, internal only (`expose`, not `ports`) — no more unix socket |
| `celery` | Default async worker (digest emails, etc. — everything not routed to `broadcast`/`scrape`) | same `app` image | `celery -A backend worker -n commons-default@%h -l info --concurrency=2` | `mem_limit: 1g` |
| `celerybeat` | Scheduler | same `app` image | `celery -A backend beat -l info` | DatabaseScheduler; **exactly one** process — do not scale this service |
| `broadcast-worker` | Playwright form-filler, drains the `broadcast` queue | `backendServer/Dockerfile` target `playwright` | `celery -A backend worker -Q broadcast -n commons-broadcast@%h -c 1 -l info` | `mem_limit: 2g`; **`-c 1` is mandatory**, not tuning — `recover_orphans()` assumes a single worker |
| `scrape-worker` | Ingestion scraper (headless Chromium), drains the `scrape` queue | `backendServer/Dockerfile` target `playwright` | `celery -A backend worker -Q scrape -n commons-scrape@%h -c 1 -l info` | `mem_limit: 2g`; keeps Chromium memory off the default worker |
| `nextjs` | theCommonsWeb (Next.js) | `Dockerfile.frontend` target `commons-runtime` | `node server.js` | Port 3000, internal only |
| `broadcast-spa-build` | Build-only: produces the compiled broadcastWeb SPA for `nginx` to `COPY --from=` | `Dockerfile.frontend` target `broadcast-build` | `true` (no-op) | `restart: "no"`; never actually runs as a service — exists so `docker compose up` doesn't crash-loop on a stray start |
| `nginx` | Single ingress for all three subdomains | `deploy/nginx/Dockerfile` | (stock `nginx:1.27-alpine` entrypoint) | **Only** service publishing host ports (`80:80`, `443:443`); bakes in both `backend`'s `collectstatic` output and `broadcast-spa-build`'s `dist/` via Buildx named contexts |

All images build for **arm64**, matching the VM
(`docs/adr/0001-containerization.md` §Base images). Every long-running service's
`CMD`/`command` execs the real binary directly (no wrapper shell) so the
container's PID 1 receives `SIGTERM` on `docker stop`/`down` and shuts down
cleanly — the one piece of the old systemd `ExecStart=.venv/bin/celery …`
convention worth keeping, for an unrelated reason to why it existed originally
(see §Historical incident).

The three Celery **workers** pass `-n commons-{default,scrape,broadcast}@%h`.
Without it they'd all default to `celery@<hostname>`, and duplicate nodenames make
`celery -A backend inspect|control` ambiguous (`DuplicateNodenameWarning`, and a
`revoke` can misroute). Verify all three are distinct:

```bash
docker compose -f docker-compose.yml exec backend celery -A backend inspect ping
# expect three distinct nodes: commons-default@, commons-scrape@, commons-broadcast@
```

**Logs and status — the container replacements for `journalctl`/`systemctl`:**

```bash
docker compose -f docker-compose.yml ps                       # replaces `systemctl status <unit>`
docker compose -f docker-compose.yml logs <service>            # replaces `journalctl -u <unit> -n 50`
docker compose -f docker-compose.yml logs -f <service>         # add -f to follow, same as journalctl -f
docker compose -f docker-compose.yml restart <service>         # replaces `systemctl restart <unit>`
```

Logging is plain `json-file` with rotation (`max-size: 10m`, `max-file: 3` — the
`x-logging` anchor at the top of `docker-compose.yml`), since there's no
`journald` inside a container.

## Health check

Unchanged interface, container-aware internals. One command still prints a
scannable report of the whole box:

```bash
cd /home/ubuntu/thecommons
bash deploy/healthcheck.sh
bash deploy/healthcheck.sh --no-color | tee /tmp/health.log
```

It checks (✓/!/✗): RAM/disk vs. thresholds; `docker compose ps`/`docker inspect`
liveness (running vs. restarting vs. exited, health status, restart count) for
every long-running service in the table above (`migrate` and
`broadcast-spa-build` are deliberately excluded — both are one-shot and exiting 0
is correct, not a failure); leftover legacy OS-cron lines; and, via
`docker compose exec -T backend python manage.py healthcheck`, Postgres
`SELECT 1`, Redis broker ping (DB 0), Django cache round-trip (DB 1), a Celery
worker `control.ping`, and each seeded `PeriodicTask`'s freshness (daily within
~25h, weekly within ~8d). A stale or never-run beat schedule is a **`FAIL`**, not a
`WARN` — that's precisely the bug class that let the 2026-07-21 outage run silent
for weeks (§Historical incident below). Exits non-zero on any critical failure.

Tunables (env vars): `RAM_WARN`/`RAM_FAIL` (80/95), `DISK_WARN`/`DISK_FAIL`
(80/95), `CELERY_TIMEOUT` (1.0s), `RESTART_WARN` (3 — a container that's
auto-restarted this many times trips a `WARN` as a possible crash-loop),
`COMPOSE_FILE` (default `docker-compose.yml` — override only for local testing,
never on the VM). The Django command also runs standalone inside the container:

```bash
docker compose -f docker-compose.yml exec backend python manage.py healthcheck [--json]
```

### Scheduled health check (host systemd timer)

Deliberately still a **host** systemd timer, not a Compose `healthcheck:` block or
a Celery beat task — both of those go silent in exactly the "everything is down"
case this exists to catch (a container health check only watches its own
container; beat watching itself is circular). A host-level timer fires even if
every container in `docker-compose.yml`, including `nginx`, is down.

1. Copy the unit files and enable the **timer**, not the service:
   ```bash
   sudo cp deploy/healthcheck.service deploy/healthcheck.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now healthcheck.timer
   ```
   `User=ubuntu` in `healthcheck.service` needs `ubuntu` in the `docker` group
   (Part 1 §2) — the timer shells out to `docker compose ps`/`exec`, not `sudo`.
2. Verify it's scheduled: `systemctl list-timers healthcheck.timer` — expect a
   `NEXT`/`LEFT` time within the hour, `LAST`/`PASSED` populated after the first run.
3. Check the most recent run:
   ```bash
   systemctl status healthcheck.service
   journalctl -u healthcheck.service -n 50 --no-pager
   ```
   (This one still goes through `journalctl` — the timer/service pair itself is a
   host systemd unit, not a container; only the app stack it inspects moved.)
4. `systemctl --failed` shows failed runs across all timers.

> **Expect an immediate FAIL on first install** if `scrape-sources-daily` has
> never run (`last_run_at` is NULL) — the never-run rule fires until beat
> completes one cycle. That's the outage this check exists to surface; don't
> silence it, let beat run.

> **No push notification is wired up yet** — `systemctl --failed` and the journal
> are the only read paths until an `OnFailure=` target/email/Slack hook is built.

## Local development (`docker-compose.override.yml`)

Plain `docker compose up --build` (no `-f`) auto-loads
`docker-compose.override.yml` alongside `docker-compose.yml` — Compose's default
two-file merge. It swaps the baked Cloudflare-cert `nginx` config for an
HTTP-only one using `*.localhost` hostnames (no `/etc/hosts` edits needed, per RFC
6761), remaps every bind-mounted host path from `/home/ubuntu/...` to
`./.local-dev/...`, and points `REDIS_URL`/`REDIS_CACHE_URL` at the `redis`
Compose service instead of `localhost` (same cutover fix as Part 1 §6, just
pre-applied for dev). See that file's header comment for the full explanation of
why it exists as a separate file rather than a second tracked nginx config.

> **Gotcha, discovered during verification:** Compose does **not** auto-recreate a
> container when the *content* of an inline `configs:` entry changes (the local
> `nginx_dev_conf` block in `docker-compose.override.yml` is defined this way). If
> you edit that inline config and run a plain `docker compose up -d`, `nginx`
> silently keeps running with the old config. Force it:
> ```bash
> docker compose up -d --force-recreate nginx
> ```

## Environment variables

### `backendServer/.env`

```
DATABASE_URL=                          # Neon Postgres connection string
DJANGO_SECRET_KEY=
DJANGO_ENV=prod                        # selects settings/prod.py — also set redundantly via compose's `environment:` on every backend/Celery service
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,api.thecommons.town
CORS_EXTRA_ORIGINS=https://thecommons.town,https://broadcast.thecommons.town
CSRF_TRUSTED_ORIGINS=https://api.thecommons.town,https://thecommons.town,https://broadcast.thecommons.town
GEMINI_API_KEY=
CRON_SECRET=
THE_COMMONS_API_KEY=
SAFETY_SCORE_THRESHOLD=0.3             # optional
INGEST_SHARD_COUNT=3                   # optional, deliberate prod setting — see note below
INGEST_SCRAPER_HEADLESS=true           # optional — default true
INGEST_SCRAPER_TIMEOUT_MS=30000        # optional — default 30000
INGEST_SCRAPER_USER_AGENT=Mozilla/5.0 (compatible; TheCommons/1.0)  # optional — default shown
BETTER_AUTH_JWKS_URL=https://auth.thecommons.town/api/auth/jwks
BETTER_AUTH_ISSUER=https://auth.thecommons.town
BETTER_AUTH_AUDIENCE=
BREVO_API_KEY=
DIGEST_FROM_EMAIL=digest@thecommons.town
SITE_URL=https://thecommons.town
REDIS_PASSWORD=<REDIS_PASS>                                        # container-only knob — must match the password embedded below
REDIS_URL=redis://:<REDIS_PASS>@redis:6379/0                       # Celery broker + results (DB 0) — `redis`, NOT 127.0.0.1 (Part 1 §6)
REDIS_CACHE_URL=redis://:<REDIS_PASS>@redis:6379/1                 # read-endpoint cache (DB 1)
# Broadcast (see backendServer/.env.example for the full annotated block)
BROADCAST_HEADLESS=true
BROADCAST_DRY_RUN_DEFAULT=false
BROADCAST_MAX_CONCURRENCY=1
BROADCAST_SCREENSHOT_DIR=/home/ubuntu/broadcast/screenshots
BROADCAST_DOWNLOAD_DIR=/home/ubuntu/broadcast/downloads
BROADCAST_TIMEOUT_MS=30000
MEDIA_ROOT=/home/ubuntu/broadcast/media    # client-uploaded event images — bind-mounted into `backend`/`nginx` at this identical path
```

**`INGEST_SHARD_COUNT=3` is a deliberate prod setting — keep it at 3.**
`_resolve_env_shard` (`backendServer/ingestion/tasks.py:22-39`) polls only the
sources where `id % INGEST_SHARD_COUNT == day_of_year % INGEST_SHARD_COUNT`, so
with a shard count of 3 any given source is actually polled roughly every **72
hours**, not the 24h its own `poll_interval_hours` implies — sharding is disabled
(all sources polled daily) only when the var is unset, fails to parse as an int,
or is `<= 1`. Two consequences: a source that fails transiently gets 1/3 as many
chances to recover before the next poll compared to unsharded daily polling, and
monitoring thresholds must be shard-aware — a source that looks "3 days stale" is
expected and healthy under this setting, not a symptom of an outage.

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

Loaded into the running `nextjs` container via `env_file:`, **and** its
`NEXT_PUBLIC_*`/`DATABASE_URL`/`BETTER_AUTH_*` values get baked into the compiled
JS at image build time via the `NEXTJS_BUILD_*`-prefixed build args (Part 2 step
2) — two different mechanisms consuming the same file, at two different times.

### `broadcastWeb/.env`

```
VITE_BROADCAST_API_BASE_URL=https://api.thecommons.town
VITE_BROADCAST_EXTENSION_ID=           # Chrome extension ID for extension autofill
VITE_BETTER_AUTH_URL=https://auth.thecommons.town
```

`broadcastWeb` has no running container of its own — this file only matters at
**build** time (`broadcast-spa-build`'s `VITE_*` build args, Part 2 step 2). Vite
inlines these into the compiled bundle; there is no runtime env to load them into.

## nginx

- Config: [`deploy/nginx/thecommons.conf`](deploy/nginx/thecommons.conf), baked
  into the `nginx` image at `/etc/nginx/conf.d/thecommons.conf` by
  [`deploy/nginx/Dockerfile`](deploy/nginx/Dockerfile) — **not** a bind mount in
  prod, so an edit requires a rebuild (`docker compose -f docker-compose.yml build
  nginx && docker compose -f docker-compose.yml up -d --no-deps nginx`), not
  `nginx -t && systemctl reload nginx`. One file, multiple `server` blocks — the
  repo's long-standing convention, preserved rather than restructured.
- Routes: `thecommons.town` → `proxy_pass http://backend:8000` was the old
  wording; today it's `thecommons.town` → `http://nextjs:3000` (Next.js);
  `api.thecommons.town` → `http://backend:8000` (Django/gunicorn, **TCP now, not
  a unix socket** — see the correction below); `www` → 301 to apex; HTTP → 301 to
  HTTPS; `api.thecommons.town/static/` → the baked `collectstatic` output at
  `/usr/share/nginx/html/static` (`COPY --from=` the `backend` image's
  `/app/staticfiles_build/static`, matching `STATIC_ROOT` in
  `backendServer/backend/settings/base.py:91`); `api.thecommons.town/media/` →
  `/var/www/media` (bind-mounted `MEDIA_ROOT`, read-only from nginx's side —
  **never** served by Django/gunicorn in prod); `broadcast.thecommons.town` → the
  baked SPA at `/usr/share/nginx/html/broadcast` (`COPY --from=`
  `broadcast-spa-build`'s `/app/dist`).
- All `proxy_pass` targets resolve through a `resolver 127.0.0.11 …` directive
  (Docker's embedded DNS) via an nginx variable rather than a literal hostname —
  a literal `proxy_pass http://nextjs:3000` makes nginx resolve once at boot and
  **refuse to start** if that service isn't up yet; resolving through a variable
  defers the lookup to request time, so one crashed upstream degrades to a 502 on
  just that hostname instead of taking the whole ingress down.
- `MEDIA_ROOT` (`/home/ubuntu/broadcast/media`) must exist and be uid-1000-writable
  before the first upload — covered in Part 1 §3. **Uploaded images are kept
  indefinitely — no pruning job exists**, at roughly 1–3 MB/event against the VPS
  block volume; negligible for now, but a prune command could be added later
  without a migration.

```bash
docker compose -f docker-compose.yml build nginx
docker compose -f docker-compose.yml up -d --no-deps nginx
```

## Firewall

Unchanged by containerization — the container `nginx` binds the host's 80/443
exactly like the systemd one did, so both layers still apply:

1. **Oracle VCN Security List** (OCI console) — ingress on 22, 80, 443.
2. **iptables on the VM** — Oracle Ubuntu images ship a catch-all `REJECT` in
   INPUT. The 80/443 ACCEPT rules must sit **above** it:
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
| nginx 502 Bad Gateway | `backend` or `nextjs` container down/unhealthy | `docker compose -f docker-compose.yml ps`; `docker compose -f docker-compose.yml logs backend nextjs` |
| broadcast subdomain → Cloudflare 526 | origin cert doesn't cover `*.thecommons.town`, or the cert bind mount is missing/wrong path | reissue cert (Part 1 §4); confirm `nginx`'s `volumes:` in `docker-compose.yml` |
| Django `DisallowedHost` | `DJANGO_ALLOWED_HOSTS` missing from `backendServer/.env` — `prod.py:16` hard-crashes without it | `docker compose -f docker-compose.yml logs backend`; fix `.env`, `docker compose -f docker-compose.yml up -d --no-deps backend` |
| 400 on `/events/` from browser | `NEXT_PUBLIC_API_BASE_URL` wrong at **build** time — a runtime `.env.local` edit alone does nothing, since Next inlined the old value already | fix `theCommonsWeb/.env.local`, then `docker compose -f docker-compose.yml build nextjs && docker compose -f docker-compose.yml up -d --no-deps nextjs` |
| Django admin has no CSS | `collectstatic` output stale or missing in the `backend` image, or nginx's `/static/` alias path wrong | rebuild `backend` and `nginx`: `docker compose -f docker-compose.yml build backend nginx && docker compose -f docker-compose.yml up -d --no-deps backend nginx` |
| Celery worker won't start / no broker | `REDIS_URL` still points at `127.0.0.1`/`localhost` instead of `redis`, wrong password, or the `redis` container is down | `docker compose -f docker-compose.yml logs redis celery`; re-check Part 1 §6 |
| Scheduled job ran twice | leftover OS cron alongside beat | `crontab -l` (should be empty of `ingest_events`/`send_weekly_digest` lines — Part 1 §9) |
| Edited `docker-compose.override.yml`'s inline nginx config locally, but the container is still serving the old one | Compose doesn't auto-recreate on inline `configs:` content changes | `docker compose up -d --force-recreate nginx` |

## Historical incident: 2026-07-21 scheduler outage (containers close this gap)

Kept for context, not as a template to reproduce. All four Celery systemd units
used to exec `/snap/bin/uv run celery …`. Snap-packaged `uv run` spawned its child
process inside a transient `snap.astral-uv.uv-*.scope` under `user@1001.service` —
the *user* session manager, not the unit's own cgroup. With linger off,
`systemd-logind` tore that user slice down the moment the deploying SSH session
ended, and every `uv run`-based unit died within a minute of each deploy,
silently, with `status=0/SUCCESS` — a clean exit that `Restart=on-failure`
correctly declined to restart. That took the entire async stack down for 8 days
starting 2026-07-21 while `gunicorn` and `nextjs` (which never went through snap)
stayed up the whole time. Full forensics:
[`docs/prod-incident-2026-07-21-scheduler-outage.md`](docs/prod-incident-2026-07-21-scheduler-outage.md).

The mitigation at the time was two-layered: exec the venv binary directly
(`.venv/bin/celery`, removing the snap-scope mechanism entirely) plus
`Restart=always` + `loginctl enable-linger ubuntu` as defense-in-depth.

**Containers remove this failure mode by construction** — there is no snap, no
`logind`, no per-user systemd slice inside a container's PID namespace for a lost
SSH session to tear down. **Do not cargo-cult the `uv run` avoidance, the linger
setting, or `Restart=always`-as-a-workaround forward into the Compose/Dockerfile
setup** — none of them are solving a live problem there. The one piece that *is*
still worth keeping, for an unrelated reason, is exec'ing binaries directly rather
than through a wrapper shell (`CMD ["gunicorn", …]` / `command: ["celery", …]`,
not a shell script) — so the container's PID 1 is the real process and receives
`SIGTERM` directly on `docker stop`/`down` for a clean shutdown. Same shape,
different justification.

What still matters from this incident either way: a stale/dead beat schedule is a
`FAIL` in `deploy/healthcheck.sh`, not a `WARN` (§Health check above) — that
distinction is what would have caught this outage in hours instead of weeks, and
it has nothing to do with systemd vs. containers.

## Deep-dive references

- [`docs/adr/0001-containerization.md`](docs/adr/0001-containerization.md) — the
  four containerization decisions (nginx-in-a-container, Redis-in-a-container,
  Postgres staying external, baked-vs-volumed artifacts) and their rationale
- [`docs/redis-celery-handoff.md`](docs/redis-celery-handoff.md) — Redis/Celery internals, task conventions, beat schedules
- [`docs/broadcast.md`](docs/broadcast.md) — broadcast subsystem: routing, adapters, worker, recipe layer, extension, SPA wiring
- [`docs/dev-db-isolation.md`](docs/dev-db-isolation.md) — Neon dev branch setup for local development
- [`docs/ingestion-pipeline.md`](docs/ingestion-pipeline.md) — scrape → stage → publish flow
- [`docs/runbook-auth-cutover.md`](docs/runbook-auth-cutover.md) — Auth-origin cutover (auth.thecommons.town subdomain, .thecommons.town cookie domain, forced re-login)
