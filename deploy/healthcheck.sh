#!/usr/bin/env bash
#
# The Commons — VM health check.
#
# A single, scannable report of the box's health: RAM/disk, every long-running
# compose service (T6/T7 moved the app stack into containers — see
# docker-compose.yml), and (via the Django `healthcheck` command, now run
# *inside* the backend container) Redis, Postgres, the Celery worker, and the
# beat schedule. Run it on the VM:
#
#     bash deploy/healthcheck.sh
#     bash deploy/healthcheck.sh --no-color | tee health.log
#
# System-level checks (RAM/disk/containers/cron) are done here in bash;
# app-level checks are delegated to `manage.py healthcheck`, whose
# STATUS|name|detail lines are colorized below. Exits non-zero if any
# critical check fails so it can feed monitoring — including a stale/never-run
# beat schedule, which is a FAIL, not a WARN (a dead scheduler is an outage,
# not a suggestion).
#
# Tunables (env vars, with defaults):
#   RAM_WARN=80  RAM_FAIL=95      # % memory used
#   DISK_WARN=80 DISK_FAIL=95     # % of / used
#   CELERY_TIMEOUT=1.0            # seconds to wait for a worker ping
#   RESTART_WARN=3                # container RestartCount that trips a WARN
#   COMPOSE_FILE=docker-compose.yml
set -uo pipefail

# ── config ───────────────────────────────────────────────────────────────────
RAM_WARN="${RAM_WARN:-80}"
RAM_FAIL="${RAM_FAIL:-95}"
DISK_WARN="${DISK_WARN:-80}"
DISK_FAIL="${DISK_FAIL:-95}"
CELERY_TIMEOUT="${CELERY_TIMEOUT:-1.0}"
RESTART_WARN="${RESTART_WARN:-3}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

# The long-running services from docker-compose.yml. `migrate` and
# `broadcast-spa-build` are deliberately excluded: both are one-shot/build-only
# (restart: "no", exit 0 by design — see their comments in docker-compose.yml)
# and would misreport as dead services if checked here.
SERVICES=(redis backend celery celerybeat broadcast-worker scrape-worker nextjs nginx)
LEGACY_CRON='manage.py (ingest_events|send_weekly_digest)'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# ── flags ────────────────────────────────────────────────────────────────────
USE_COLOR=auto
for arg in "$@"; do
    case "$arg" in
        --no-color) USE_COLOR=no ;;
        -h|--help)
            grep -E '^#( |$)' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

# Color only when asked-for/auto AND stdout is a TTY AND NO_COLOR is unset.
if [ "$USE_COLOR" = no ] || [ -n "${NO_COLOR:-}" ] || [ ! -t 1 ]; then
    RED= ; GREEN= ; YELLOW= ; BOLD= ; RESET=
else
    RED=$'\033[31m' ; GREEN=$'\033[32m' ; YELLOW=$'\033[33m'
    BOLD=$'\033[1m' ; RESET=$'\033[0m'
fi

WARN_COUNT=0
FAIL_COUNT=0

# report STATUS name detail — print one colored, aligned row and tally it.
report() {
    local status="$1" name="$2" detail="$3" color sym
    case "$status" in
        OK)   color="$GREEN";  sym="✓" ;;
        WARN) color="$YELLOW"; sym="!" ; WARN_COUNT=$((WARN_COUNT + 1)) ;;
        *)    color="$RED";    sym="✗" ; FAIL_COUNT=$((FAIL_COUNT + 1)) ;;
    esac
    printf "%s%s%s %-26s %s\n" "$color" "$sym" "$RESET" "$name" "$detail"
}

section() { printf "\n%s%s%s\n" "$BOLD" "$1" "$RESET"; }

# threshold STATUS for an integer percentage against warn/fail cutoffs.
pct_status() {
    local pct="$1" warn="$2" fail="$3"
    if [ "$pct" -ge "$fail" ]; then echo FAIL
    elif [ "$pct" -ge "$warn" ]; then echo WARN
    else echo OK; fi
}

# ── header ───────────────────────────────────────────────────────────────────
printf "%s%s%s\n" "$BOLD" "The Commons — health check  ·  $(hostname)  ·  $(date '+%Y-%m-%d %H:%M:%S %Z')" "$RESET"

# ── system: RAM / disk ───────────────────────────────────────────────────────
section "System"
if command -v free >/dev/null 2>&1; then
    read -r mem_total mem_used < <(free -m | awk '/^Mem:/ {print $2, $3}')
    if [ "${mem_total:-0}" -gt 0 ]; then
        ram_pct=$(( mem_used * 100 / mem_total ))
        report "$(pct_status "$ram_pct" "$RAM_WARN" "$RAM_FAIL")" "ram" "${ram_pct}% used (${mem_used}M / ${mem_total}M)"
    else
        report WARN "ram" "could not read free -m"
    fi
else
    report WARN "ram" "free not available on this host"
fi

disk_pct="$(df -P / | awk 'NR==2 {gsub("%","",$5); print $5}')"
if [ -n "$disk_pct" ]; then
    report "$(pct_status "$disk_pct" "$DISK_WARN" "$DISK_FAIL")" "disk" "${disk_pct}% of / used"
else
    report WARN "disk" "could not read df -P /"
fi

# ── compose services ─────────────────────────────────────────────────────────
# Container-aware replacement for the old `systemctl is-active` loop. Always
# pass -f explicitly and run from REPO_ROOT: a bare `docker compose` (no -f)
# auto-loads docker-compose.override.yml, which swaps in local-dev-only
# config and must never be what a prod healthcheck inspects.
section "Services"
DOCKER_OK=1
if ! command -v docker >/dev/null 2>&1; then
    report WARN "docker" "docker not available (not a VM with the stack deployed?)"
    DOCKER_OK=0
elif ! docker compose version >/dev/null 2>&1; then
    report WARN "docker" "docker compose plugin not available"
    DOCKER_OK=0
fi

BACKEND_UP=0
if [ "$DOCKER_OK" -eq 1 ]; then
    pushd "$REPO_ROOT" >/dev/null
    for svc in "${SERVICES[@]}"; do
        # --all so a stopped/crashed container is still found (a bare `ps -q`
        # only lists running ones, which would collapse "never started" and
        # "exited" into the same unhelpful "no container" report).
        cid="$(docker compose -f "$COMPOSE_FILE" ps --all -q "$svc" 2>/dev/null | head -n1)"
        if [ -z "$cid" ]; then
            report FAIL "$svc" "no container found"
            continue
        fi

        # {{if .State.Health}} guards services with no HEALTHCHECK (only
        # redis defines one) — asking for .State.Health.Status on those
        # would error the template instead of returning empty.
        inspect="$(docker inspect --format \
            '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.RestartCount}}' \
            "$cid" 2>/dev/null || true)"
        status="${inspect%%|*}"
        rest="${inspect#*|}"
        health="${rest%%|*}"
        restarts="${rest#*|}"

        if [ -z "$status" ]; then
            report FAIL "$svc" "docker inspect failed for $cid"
        elif [ "$status" = running ]; then
            [ "$svc" = backend ] && BACKEND_UP=1
            if [ "$health" = unhealthy ]; then
                report FAIL "$svc" "running but unhealthy (restarts=$restarts)"
            elif [ "${restarts:-0}" -ge "$RESTART_WARN" ]; then
                report WARN "$svc" "running, but restarted $restarts times (possible restart-loop)"
            elif [ "$health" != none ]; then
                report OK "$svc" "running, health=$health"
            else
                report OK "$svc" "running"
            fi
        elif [ "$status" = restarting ]; then
            # Caught mid-crash-loop: docker is actively bouncing this
            # container, distinct from a container that's cleanly exited.
            report FAIL "$svc" "restarting (crash-looping, restarts=$restarts)"
        else
            report FAIL "$svc" "$status (restarts=$restarts)"
        fi
    done
    popd >/dev/null
fi

# ── legacy OS cron (must be gone — beat owns these now) ───────────────────────
section "Cron"
if command -v crontab >/dev/null 2>&1; then
    leftover="$(crontab -l 2>/dev/null | grep -E "$LEGACY_CRON" || true)"
    if [ -n "$leftover" ]; then
        report WARN "legacy-cron" "leftover entries would double-run — remove from 'crontab -e'"
    else
        report OK "legacy-cron" "no duplicate ingest/digest entries"
    fi
else
    report OK "legacy-cron" "no crontab on this host"
fi

# ── app-level checks (Django command, now run inside the backend container) ──
# `exec` needs a running container; DOCKER_OK/BACKEND_UP come from the
# Services loop above, so a down stack reports one clear FAIL here instead of
# an ambiguous `docker compose exec` error.
section "Application"
app_out=""
if [ "$DOCKER_OK" -ne 1 ]; then
    report FAIL "app-checks" "docker/compose not available — cannot exec into backend"
elif [ "$BACKEND_UP" -ne 1 ]; then
    report FAIL "app-checks" "backend container is not running — cannot run manage.py healthcheck"
else
    pushd "$REPO_ROOT" >/dev/null
    # -T: no TTY allocation, required for a non-interactive/systemd context.
    app_out="$(docker compose -f "$COMPOSE_FILE" exec -T backend \
        python manage.py healthcheck --require-prod --celery-timeout "$CELERY_TIMEOUT" 2>/dev/null || true)"
    popd >/dev/null
fi

if [ -n "$app_out" ]; then
    while IFS='|' read -r status name detail; do
        [ -z "$status" ] && continue
        report "$status" "$name" "$detail"
    done <<< "$app_out"
elif [ "$DOCKER_OK" -eq 1 ] && [ "$BACKEND_UP" -eq 1 ]; then
    report FAIL "app-checks" "manage.py healthcheck produced no output (container exec error?)"
fi

# ── summary ──────────────────────────────────────────────────────────────────
section "Summary"
if [ "$FAIL_COUNT" -gt 0 ]; then
    report FAIL "result" "$FAIL_COUNT failing, $WARN_COUNT warning"
    # report() bumped FAIL_COUNT for the summary line itself — ignore that.
    exit 1
elif [ "$WARN_COUNT" -gt 0 ]; then
    printf "%s%s%s %-26s %s\n" "$YELLOW" "!" "$RESET" "result" "PASS with $WARN_COUNT warning(s)"
    exit 0
else
    printf "%s%s%s %-26s %s\n" "$GREEN" "✓" "$RESET" "result" "all checks passed"
    exit 0
fi
