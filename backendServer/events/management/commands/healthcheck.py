"""App-level health probes for the VM healthcheck.

Run by `deploy/healthcheck.sh` (which adds the system-level checks and the
colors), but usable on its own:

    uv run python manage.py healthcheck            # STATUS|name|detail lines
    uv run python manage.py healthcheck --json     # machine-readable JSON

Checks: settings sanity (`--require-prod`), Postgres `SELECT 1`, Redis broker
ping (DB 0), Django cache round-trip (DB 1), a Celery worker `control.ping`, and
every django-celery-beat PeriodicTask (enabled + last-run freshness). Exits
non-zero if any *critical* check fails so it can feed monitoring — staleness is
one of those: a schedule that stopped firing IS an outage, not a warning.

Freshness for a crontab-backed task is judged by deriving the *expected* next
fire time from the crontab itself (via `crontab.remaining_estimate`), not by a
hand-tuned staleness window — a window necessarily exceeds the task's own
period, so it always has a blind spot at least one period wide (a missed
weekly send would ride along for ~8 days). Instead we ask the schedule "what
was the next fire time after last_run_at?" and FAIL as soon as that time has
passed (past a grace allowance — see crontab_grace_seconds() below), so a
missed occurrence surfaces within hours, not days.
DEFAULT_STALENESS_HOURS is kept for two narrower roles: (1) the must-exist set
— a seeded task missing from the schedule entirely is a FAIL — and (2) a
fallback window for interval-backed or schedule-less PeriodicTask rows, where
there is no crontab to derive an expected fire time from.

`PeriodicTask.last_run_at` is not written the instant a task fires: beat's
`DatabaseScheduler` keeps it in memory and only persists it on a sync. That
sync is now forced after every single task send by `CELERY_BEAT_SYNC_EVERY = 1`
(see backend/settings/base.py), so last_run_at lags reality by roughly one
task execution, not by `CELERY_BEAT_MAX_LOOP_INTERVAL` (hours). If
`CELERY_BEAT_SYNC_EVERY` is ever unset/disabled, the old worst case comes
back, so `crontab_grace_seconds()` re-widens automatically rather than
silently staying tight. A naive "is remaining negative" check would misreport
a healthy-but-unsynced task as MISSED, so `crontab_grace_seconds()` absorbs
that plausible persistence lag before declaring MISSED; see
`_crontab_freshness` for the WARN/FAIL split within that grace window.
"""

import json
import os
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

OK, WARN, FAIL = "OK", "WARN", "FAIL"

# Hosts that prove nothing about public reachability — if ALLOWED_HOSTS contains
# only these, the app is on dev settings and will 400 every real request.
LOCALHOST_ONLY = {"localhost", "127.0.0.1", "[::1]"}

# Tasks that must exist in the schedule (a missing entry is a FAIL — see
# _check_periodic_tasks, guarding the 2026-07-21 scheduler outage), and the
# fallback staleness window (hours) used only when a task has no crontab to
# derive an expected-fire time from (interval schedule, or no schedule at
# all). Crontab-backed tasks are judged against their own expected fire time
# instead — see _task_freshness.
DEFAULT_STALENESS_HOURS = {
    "ingest-events-daily": 25,
    "scrape-sources-daily": 25,
    "weekly-digest-sunday": 24 * 8,  # ~8 days
    "broadcast-orphan-recovery": 7,
}

# Fallback bound (seconds) on how long beat's DatabaseScheduler may leave a
# fresh last_run_at unpersisted, used only if CELERY_BEAT_MAX_LOOP_INTERVAL is
# unset — matches the value that setting currently carries in
# backend/settings/base.py, so an unset value degrades to today's known prod
# behavior rather than to an arbitrary guess.
_DEFAULT_BEAT_LOOP_INTERVAL_SECONDS = 6 * 60 * 60

# Extra buffer (seconds) on top of the loop-interval bound, covering scheduler
# jitter and task execution time so we don't FAIL on the tail end of a sync
# that lands a few minutes late. Deliberately small relative to the loop
# interval — this is slack for noise, not a second staleness window. Used
# only in the *wide* (CELERY_BEAT_SYNC_EVERY unset/0) branch below.
CRONTAB_GRACE_BUFFER_SECONDS = 60 * 60

# Buffer (seconds) used in the *tight* branch, when CELERY_BEAT_SYNC_EVERY
# forces a DB flush after every task send. The only slack left to absorb is
# ordinary scheduler wake-up jitter plus the time a task itself takes to run
# before the post-send sync fires — not a multi-hour polling interval. 5
# minutes comfortably covers that for these tasks (digest/ingestion/orphan
# recovery all complete in seconds-to-low-minutes) without reopening a
# window wide enough to swallow a genuine miss.
CRONTAB_GRACE_TIGHT_BUFFER_SECONDS = 5 * 60


def crontab_grace_seconds() -> int:
    """Grace (seconds) allowed between an expected crontab fire time and when
    we declare a task MISSED, absorbing beat's last_run_at persistence lag.

    Evaluated at call time (not a module-level constant) so tests can vary it
    via @override_settings. When CELERY_BEAT_SYNC_EVERY is a positive int,
    beat flushes last_run_at after every task send (see module docstring), so
    the lag collapses to roughly one task execution and only the small jitter
    buffer is needed. If someone later unsets/disables that setting, the lag
    bound reverts to CELERY_BEAT_MAX_LOOP_INTERVAL and the grace automatically
    re-widens to match — that self-protection is the point of deriving this
    from the setting instead of hardcoding a small number.
    """
    sync_every = getattr(settings, "CELERY_BEAT_SYNC_EVERY", 0) or 0
    if isinstance(sync_every, int) and sync_every > 0:
        return CRONTAB_GRACE_TIGHT_BUFFER_SECONDS
    loop_interval = getattr(
        settings, "CELERY_BEAT_MAX_LOOP_INTERVAL", _DEFAULT_BEAT_LOOP_INTERVAL_SECONDS
    )
    return loop_interval + CRONTAB_GRACE_BUFFER_SECONDS


def _format_timedelta(delta) -> str:
    """Render a positive timedelta as e.g. '3d13h07m' for detail strings."""
    total_minutes = int(delta.total_seconds() // 60)
    days, rem_minutes = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(rem_minutes, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if days or hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes:02d}m")
    return "".join(parts)


class Command(BaseCommand):
    help = (
        "Probe DB, Redis broker, cache, Celery worker, and beat schedules for the VM healthcheck."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit a JSON array of {status, name, detail} instead of pipe-delimited lines.",
        )
        parser.add_argument(
            "--celery-timeout",
            type=float,
            default=1.0,
            help="Seconds to wait for a Celery worker to answer control.ping (default 1.0).",
        )
        parser.add_argument(
            "--require-prod",
            action="store_true",
            dest="require_prod",
            help="Assert production-safe settings (DEBUG off, public ALLOWED_HOSTS). "
            "Set by deploy/healthcheck.sh; catches dev settings leaking into prod.",
        )

    def handle(self, *args, **options):
        results: list[tuple[str, str, str]] = []
        results.append(self._check_config(options["require_prod"]))
        results.append(self._check_db())
        results.append(self._check_redis_broker())
        results.append(self._check_cache())
        results.append(self._check_celery_worker(options["celery_timeout"]))
        results.extend(self._check_periodic_tasks())

        if options["as_json"]:
            self.stdout.write(
                json.dumps([{"status": s, "name": n, "detail": d} for s, n, d in results])
            )
        else:
            for status, name, detail in results:
                self.stdout.write(f"{status}|{name}|{detail}")

        if any(status == FAIL for status, _, _ in results):
            # SystemExit(1) — non-zero so the bash wrapper / monitoring can react.
            raise SystemExit(1)

    # ── individual probes ────────────────────────────────────────────────────

    def _check_config(self, require_prod: bool) -> tuple[str, str, str]:
        # June 2026 outage: DJANGO_ENV unset -> dev.py -> DEBUG=True and
        # localhost-only ALLOWED_HOSTS -> every request to api.thecommons.town
        # returned DisallowedHost (400). Both signals caught here under --require-prod.
        env = os.environ.get("DJANGO_ENV") or "(unset)"
        hosts = [h for h in settings.ALLOWED_HOSTS if h]
        summary = f"DJANGO_ENV={env}, DEBUG={settings.DEBUG}, ALLOWED_HOSTS={hosts or '[]'}"

        if not require_prod:
            return (OK, "config", summary)

        problems = []
        if settings.DEBUG:
            problems.append("DEBUG=True (dev settings active — set DJANGO_ENV=prod)")
        if not set(hosts) - LOCALHOST_ONLY:
            problems.append("ALLOWED_HOSTS is localhost-only — public host will 400")
        if problems:
            return (FAIL, "config", f"{'; '.join(problems)} [{summary}]")
        return (OK, "config", summary)

    def _check_db(self) -> tuple[str, str, str]:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return (OK, "db", "SELECT 1 ok")
        except Exception as exc:  # noqa: BLE001 — surface any DB error as a failure
            return (FAIL, "db", f"{type(exc).__name__}: {exc}")

    def _check_redis_broker(self) -> tuple[str, str, str]:
        try:
            import redis

            client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
            client.ping()
            return (OK, "redis_broker", "PING ok (DB 0)")
        except Exception as exc:  # noqa: BLE001
            return (FAIL, "redis_broker", f"{type(exc).__name__}: {exc}")

    def _check_cache(self) -> tuple[str, str, str]:
        try:
            token = str(timezone.now().timestamp())
            cache.set("healthcheck:probe", token, 10)
            if cache.get("healthcheck:probe") == token:
                return (OK, "cache", "set/get ok (DB 1)")
            return (FAIL, "cache", "set/get mismatch (DB 1)")
        except Exception as exc:  # noqa: BLE001
            return (FAIL, "cache", f"{type(exc).__name__}: {exc}")

    def _check_celery_worker(self, timeout: float) -> tuple[str, str, str]:
        try:
            from backend.celery import celery_app

            replies = celery_app.control.ping(timeout=timeout) or []
            if replies:
                workers = ", ".join(sorted(k for r in replies for k in r))
                return (OK, "celery_worker", f"{len(replies)} worker(s): {workers}")
            return (FAIL, "celery_worker", "no workers answered control.ping")
        except Exception as exc:  # noqa: BLE001
            return (FAIL, "celery_worker", f"{type(exc).__name__}: {exc}")

    def _check_periodic_tasks(self) -> list[tuple[str, str, str]]:
        try:
            from django_celery_beat.models import PeriodicTask
        except Exception as exc:  # noqa: BLE001
            return [(FAIL, "beat", f"django_celery_beat unavailable: {exc}")]

        out: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        now = timezone.now()

        # Report every scheduled task, skipping beat's internal sentinel row.
        for task in PeriodicTask.objects.exclude(name="celery.backend_cleanup").order_by("name"):
            seen.add(task.name)
            label = f"beat:{task.name}"
            if not task.enabled:
                out.append((FAIL, label, "DISABLED — will not fire"))
                continue
            out.append(self._task_freshness(task, label, now))

        # A seeded task missing entirely is a failure — beat won't schedule it.
        for name in DEFAULT_STALENESS_HOURS:
            if name not in seen:
                out.append((FAIL, f"beat:{name}", "missing — not seeded in the schedule"))

        if not out:
            out.append((WARN, "beat", "no periodic tasks registered"))
        return out

    def _task_freshness(self, task, label: str, now) -> tuple[str, str, str]:
        if task.last_run_at is None:
            return (FAIL, label, "enabled, never run yet")

        crontab = getattr(task, "crontab", None)
        if crontab is not None:
            return self._crontab_freshness(task, label, now, crontab)
        return self._window_freshness(task, label, now)

    def _crontab_freshness(self, task, label: str, now, crontab) -> tuple[str, str, str]:
        # Derive the *expected* next fire after last_run_at from the crontab
        # itself, instead of a hand-tuned window — a window always exceeds the
        # task's own period, so it has a blind spot at least one period wide
        # (a missed weekly send would ride along for ~8 days). Asking the
        # schedule directly means a missed occurrence surfaces within hours.
        schedule = crontab.schedule
        # TzAwareCrontab.remaining_estimate() (inherited unmodified from
        # celery.schedules.crontab) compares last_run_at.hour/.minute/
        # .isoweekday() directly against the crontab's fields — it never
        # converts its inputs into schedule.tz first. In real beat operation
        # that's masked: TzAwareCrontab.is_due() explicitly does
        # `last_run_at.astimezone(self.tz)` before delegating, and its
        # nowfunc() already returns `datetime.now(self.tz)`, so both operands
        # land in local time. Here we call remaining_estimate() directly and
        # pin nowfun to a UTC `now` (from timezone.now()), so without an
        # explicit conversion both operands would be read in UTC — silently
        # treating e.g. "0 4 * * *"/America/New_York as "04:00 UTC" and
        # putting expected_fire ~4-5h off (the zone offset itself, not just
        # DST drift) for every America/New_York crontab, every day. Convert
        # both operands into the schedule's own tz to match what is_due()
        # does, so remaining_estimate() sees the same local wall-clock fields
        # a real beat process would.
        tzinfo = schedule.tz
        local_now = now.astimezone(tzinfo)
        local_last_run_at = task.last_run_at.astimezone(tzinfo)
        schedule.nowfun = lambda: local_now
        remaining = schedule.remaining_estimate(local_last_run_at)
        expected_fire = now + remaining

        if remaining.total_seconds() < 0:
            overdue = -remaining
            # last_run_at can lag real fire time by up to
            # crontab_grace_seconds() (beat's DatabaseScheduler defers the
            # Postgres write — see module docstring), so a task that is
            # merely "overdue" is not yet distinguishable from one that fired
            # on time and just hasn't persisted. Only escalate to FAIL once
            # overdue exceeds that plausible lag; a schedule that stopped
            # firing is an outage (see docstring), so once past grace this
            # must not be softened.
            grace_seconds = crontab_grace_seconds()
            if overdue.total_seconds() <= grace_seconds:
                grace = _format_timedelta(timedelta(seconds=grace_seconds))
                return (
                    WARN,
                    label,
                    f"overdue by {_format_timedelta(overdue)} (expected fire at "
                    f"{expected_fire.isoformat()}) — within {grace} grace for beat's "
                    "last_run_at persistence lag; cannot yet distinguish from a "
                    "genuine miss",
                )
            return (
                FAIL,
                label,
                f"MISSED — expected fire at {expected_fire.isoformat()}, "
                f"overdue by {_format_timedelta(overdue)}",
            )
        return (OK, label, f"next expected fire {expected_fire.isoformat()}")

    def _window_freshness(self, task, label: str, now) -> tuple[str, str, str]:
        # No crontab to derive an expected fire time from (interval schedule,
        # or no schedule at all) — fall back to the hand-tuned window.
        window = DEFAULT_STALENESS_HOURS.get(task.name)
        if window is None:
            # No configured window means we can't judge freshness — that is a
            # gap in DEFAULT_STALENESS_HOURS, not a clean bill of health. Flag
            # it so a newly-seeded task never rides along as a silent OK/WARN
            # until someone remembers to add it above (see scrape-sources-daily).
            return (WARN, label, "no staleness window configured — add to DEFAULT_STALENESS_HOURS")
        age_h = (now - task.last_run_at).total_seconds() / 3600
        stamp = f"last run {age_h:.1f}h ago"
        if age_h > window:
            return (FAIL, label, f"STALE — {stamp} (> {window}h window)")
        return (OK, label, stamp)
