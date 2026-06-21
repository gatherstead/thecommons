"""App-level health probes for the VM healthcheck.

Run by `deploy/healthcheck.sh` (which adds the system-level checks and the
colors), but usable on its own:

    uv run python manage.py healthcheck            # STATUS|name|detail lines
    uv run python manage.py healthcheck --json     # machine-readable JSON

Checks: Postgres `SELECT 1`, Redis broker ping (DB 0), Django cache round-trip
(DB 1), a Celery worker `control.ping`, and every django-celery-beat
PeriodicTask (enabled + last-run freshness). Exits non-zero if any *critical*
check fails so it can feed monitoring; staleness is a warning, not a failure.
"""
import json

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

OK, WARN, FAIL = "OK", "WARN", "FAIL"

# Per-task freshness windows (hours). A seeded task whose last_run_at is older
# than this — or that has never run — is flagged WARN. Override on the CLI.
DEFAULT_STALENESS_HOURS = {
    "ingest-events-daily": 25,
    "weekly-digest-sunday": 24 * 8,  # ~8 days
}


class Command(BaseCommand):
    help = "Probe DB, Redis broker, cache, Celery worker, and beat schedules for the VM healthcheck."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json", action="store_true", dest="as_json",
            help="Emit a JSON array of {status, name, detail} instead of pipe-delimited lines.",
        )
        parser.add_argument(
            "--celery-timeout", type=float, default=1.0,
            help="Seconds to wait for a Celery worker to answer control.ping (default 1.0).",
        )

    def handle(self, *args, **options):
        results: list[tuple[str, str, str]] = []
        results.append(self._check_db())
        results.append(self._check_redis_broker())
        results.append(self._check_cache())
        results.append(self._check_celery_worker(options["celery_timeout"]))
        results.extend(self._check_periodic_tasks())

        if options["as_json"]:
            self.stdout.write(json.dumps(
                [{"status": s, "name": n, "detail": d} for s, n, d in results]
            ))
        else:
            for status, name, detail in results:
                self.stdout.write(f"{status}|{name}|{detail}")

        if any(status == FAIL for status, _, _ in results):
            # SystemExit(1) — non-zero so the bash wrapper / monitoring can react.
            raise SystemExit(1)

    # ── individual probes ────────────────────────────────────────────────────

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
            return (WARN, label, "enabled, never run yet")
        age_h = (now - task.last_run_at).total_seconds() / 3600
        window = DEFAULT_STALENESS_HOURS.get(task.name)
        stamp = f"last run {age_h:.1f}h ago"
        if window is not None and age_h > window:
            return (WARN, label, f"STALE — {stamp} (> {window}h window)")
        return (OK, label, stamp)
