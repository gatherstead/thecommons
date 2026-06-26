#!/usr/bin/env bash
#
# The Commons — VM health check.
#
# A single, scannable report of the box's health: RAM/disk, every systemd unit,
# and (via the Django `healthcheck` command) Redis, Postgres, the Celery worker,
# and the beat schedule. Run it on the VM:
#
#     bash deploy/healthcheck.sh
#     bash deploy/healthcheck.sh --no-color | tee health.log
#
# System-level checks (RAM/disk/systemd/cron) are done here in bash; app-level
# checks are delegated to `manage.py healthcheck`, whose STATUS|name|detail lines
# are colorized below. Exits non-zero if any critical check fails so it can feed
# monitoring later.
#
# Tunables (env vars, with defaults):
#   RAM_WARN=80  RAM_FAIL=95     # % memory used
#   DISK_WARN=80 DISK_FAIL=95    # % of / used
#   UV_BIN=uv                    # path to uv (VM: /snap/bin/uv)
#   CELERY_TIMEOUT=1.0           # seconds to wait for a worker ping
set -uo pipefail

# ── config ───────────────────────────────────────────────────────────────────
RAM_WARN="${RAM_WARN:-80}"
RAM_FAIL="${RAM_FAIL:-95}"
DISK_WARN="${DISK_WARN:-80}"
DISK_FAIL="${DISK_FAIL:-95}"
UV_BIN="${UV_BIN:-uv}"
CELERY_TIMEOUT="${CELERY_TIMEOUT:-1.0}"

SERVICES=(redis-server celery celerybeat gunicorn nextjs broadcast-worker)
LEGACY_CRON='manage.py (ingest_events|send_weekly_digest)'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND="$REPO_ROOT/backendServer"

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

# ── systemd units ────────────────────────────────────────────────────────────
section "Services"
if command -v systemctl >/dev/null 2>&1; then
    for svc in "${SERVICES[@]}"; do
        state="$(systemctl is-active "$svc" 2>/dev/null || true)"
        if [ "$state" = active ]; then
            report OK "$svc" "active"
        else
            report FAIL "$svc" "${state:-unknown}"
        fi
    done
else
    report WARN "systemd" "systemctl not available (not a VM?)"
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

# ── app-level checks (Django command) ────────────────────────────────────────
section "Application"
app_out=""
if [ -d "$BACKEND" ]; then
    # Mirror the systemd units: run from the backend dir with .env loaded.
    pushd "$BACKEND" >/dev/null
    if [ -f .env ]; then set -a; . ./.env; set +a; fi
    # --require-prod: this script only runs on the VM, so assert production-safe
    # settings (DEBUG off, public ALLOWED_HOSTS) and fail loud if dev.py leaked in.
    app_out="$("$UV_BIN" run python manage.py healthcheck --require-prod --celery-timeout "$CELERY_TIMEOUT" 2>/dev/null || true)"
    popd >/dev/null
else
    report FAIL "app-checks" "backendServer not found at $BACKEND"
fi

if [ -n "$app_out" ]; then
    while IFS='|' read -r status name detail; do
        [ -z "$status" ] && continue
        report "$status" "$name" "$detail"
    done <<< "$app_out"
elif [ -d "$BACKEND" ]; then
    report FAIL "app-checks" "manage.py healthcheck produced no output (uv/Django error?)"
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
