# syntax=docker/dockerfile:1
#
# Multi-stage build producing two images from one Django source tree + venv:
#   - `app`        — gunicorn / celery worker (default queue) / celerybeat.
#                    No Chromium.
#   - `playwright` — `FROM app` + bundled Chromium, for the broadcast and
#                    scrape Celery workers (both drive headless Chromium).
#
# Build context is backendServer/ (not the repo root):
#   docker build -f backendServer/Dockerfile --target app        backendServer
#   docker build -f backendServer/Dockerfile --target playwright backendServer
#
# Target platform: Oracle Ubuntu 24.04 on ARM64 (prod VM). python:3.13-slim
# is multi-arch, so no --platform pin is needed even though local dev is
# Apple Silicon.

########################################################################
# Stage: builder
#
# Resolves the locked dependency set (uv.lock) into a venv at /app/.venv
# and installs the project into it. Kept separate from `app` so build-only
# tooling (the uv binary, compilers, -dev headers) never ships at runtime.
########################################################################
FROM python:3.13-slim AS builder

# Recommended way to get `uv` into a Dockerfile per Astral's docs — copies
# the static binary from their distroless image rather than curl | sh.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# No compilers/headers here on purpose. Every dependency in pyproject.toml
# that would otherwise need to build from sdist — psycopg[binary], lxml,
# Pillow — publishes prebuilt manylinux aarch64 wheels, so `uv sync` never
# invokes a compiler on this platform. Installing build-essential + libpq-dev
# "just in case" cost ~250 MB and made this the slowest, most fragile layer
# in the build (it was also the layer that reliably tripped apt Hash Sum
# mismatches behind a proxy). If a future dependency genuinely lacks an
# aarch64 wheel, `uv sync` below will fail loudly with a compiler error —
# that's the signal to add the toolchain back, deliberately and with a note.

# Copy only the dependency manifests first so this (slow) layer caches
# across source-only changes.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
# --frozen: fail the build if uv.lock is stale rather than silently
# re-resolving. --no-install-project: dependencies only — project source
# isn't copied in yet, so there's nothing to install as a package.
RUN uv sync --frozen --no-install-project --no-dev

# Now bring in the full source (respecting .dockerignore: no .venv, no
# .env, no caches) and install the project itself into the same venv.
COPY . .
RUN uv sync --frozen --no-dev

########################################################################
# Stage: app
#
# Runtime image for gunicorn, the default celery worker, and celerybeat.
# venv + source only — no compilers, no Chromium.
########################################################################
FROM python:3.13-slim AS app

WORKDIR /app

# apt hardening, applied to every apt invocation in this file via
# /etc/apt/apt.conf.d/. Retries covers transient mirror failures; disabling
# HTTP pipelining is the standard mitigation for "Hash Sum mismatch" errors,
# which is how a proxy that mangles large or pipelined responses reports
# itself. Docker Desktop ships such a proxy on by default
# (http.docker.internal:3128), and without this the Playwright stage's
# `--with-deps` — a large multi-package fetch — fails intermittently on a
# different package each run, which reads like package corruption rather
# than a network problem.
RUN printf 'Acquire::Retries "3";\nAcquire::http::Pipeline-Depth "0";\n' \
    > /etc/apt/apt.conf.d/99-robust

# libpq5 is the runtime (not -dev) Postgres client lib psycopg needs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user (contract requirement). --home-dir /app rather than
# a separate /home/app: WORKDIR is already /app, and it makes $HOME sane for
# anything (e.g. playwright, in the child stage) that defaults to
# $HOME/.cache.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --home-dir /app --no-create-home \
       --shell /usr/sbin/nologin app

# Pull in the venv + installed project from the builder stage, owned by the
# runtime user up front so later steps (collectstatic, playwright's browser
# download in the child stage) don't need a root-owned-file cleanup pass.
COPY --from=builder --chown=app:app /app /app

# `WORKDIR /app` above created /app itself as root, and `COPY --chown` only
# sets ownership on the entries it copies — never on a pre-existing
# destination directory. So /app stays root-owned unless we say otherwise,
# and collectstatic (below, running as `app`) then fails with EACCES trying
# to create STATIC_ROOT at /app/staticfiles_build/.
RUN chown app:app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/app

USER app

# collectstatic needs Django settings to import cleanly, but prod.py hard-
# crashes at import time without DJANGO_SECRET_KEY / DJANGO_ALLOWED_HOSTS /
# DATABASE_URL (deliberately — see prod.py), and this image never bakes in
# a real .env (config comes from compose's env_file at container start).
# So this runs under dev settings (DJANGO_ENV unset -> dev.py) with a
# throwaway DATABASE_URL just to satisfy dev.py's urlparse() call at import;
# collectstatic itself never touches the database. STATIC_ROOT
# (backend/settings/base.py) is identical across dev/prod, so the output
# lands in the right place regardless of which settings module produced it.
RUN DATABASE_URL=postgresql://collectstatic:collectstatic@localhost:5432/collectstatic \
    python manage.py collectstatic --noinput

EXPOSE 8000

# Default command: gunicorn bound to TCP 0.0.0.0:8000 (replaces the old
# nginx-unix-socket setup at /run/gunicorn/gunicorn.sock), 3 sync workers,
# backend.wsgi. Exec-form CMD so gunicorn runs as PID 1 and receives signals
# directly.
#
# Compose overrides this CMD for the other two services that reuse this
# image (same command the systemd units ran, minus the systemd-specific
# bits — see note below):
#   celery worker (default queue): celery -A backend worker -n commons-default@%h -l info --concurrency=2
#   celery beat:                   celery -A backend beat -l info
#
# Note on `.venv/bin/celery` vs `uv run celery`: the old systemd units exec
# the venv binary directly instead of going through `uv run`, to dodge a
# snap-packaged-uv bug where the child process landed in a systemd user
# slice that a logout could tear down (an 8-day silent prod outage on
# 2026-07-21 — see deploy/celery.service and
# docs/prod-incident-2026-07-21-scheduler-outage.md). That mechanism can't
# happen in a container — no snap, no logind, no user slice — so it's
# obsolete here. Still worth exec'ing the venv binary directly (it's on
# PATH via the ENV above) rather than `uv run`: it's the same correct
# behavior for PID-1 signal handling, just without the systemd-specific
# justification.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "backend.wsgi:application"]

########################################################################
# Stage: playwright
#
# `FROM app` + bundled Chromium + its system libs, for the two Playwright
# Celery workers:
#   broadcast worker: celery -A backend worker -Q broadcast -n commons-broadcast@%h -c 1 -l info
#   scrape worker:    celery -A backend worker -Q scrape -n commons-scrape@%h -c 1 -l info
# (-c 1 is mandatory for the broadcast worker — recover_orphans() assumes a
# single worker — and the scrape worker follows the same pattern; compose
# sets these commands, not this Dockerfile.)
########################################################################
FROM app AS playwright

USER root

# uv is only needed transiently to invoke `playwright install` against the
# exact pinned version in uv.lock; not required at runtime, so it's added
# here rather than in `app`.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Explicit browsers path rather than relying on the default
# ~/.cache/ms-playwright: guarantees the browser lands somewhere the
# non-root `app` user can read (and, since we install as root below, we
# chown it explicitly afterward rather than relying on $HOME semantics).
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.playwright-browsers

# `uv run playwright install --with-deps chromium`:
#   - `uv run` resolves the playwright *package* version already pinned in
#     uv.lock, so the browser build downloaded here matches it exactly.
#   - `--with-deps` also apt-installs the system libraries Chromium needs
#     (requires root, hence USER root above).
#   - Never the branded "chrome" channel — unsupported on arm64, which is
#     the actual prod target.
# Chromium is baked into the image here (build time), not downloaded at
# container start.
RUN uv run playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && chown -R app:app "$PLAYWRIGHT_BROWSERS_PATH"

USER app
