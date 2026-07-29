"""Guards the beat-freshness logic in `manage.py healthcheck`.

Motivating bug (2026-07-21 -> 2026-07-29 scheduler outage): `scrape-sources-daily`
had no entry in DEFAULT_STALENESS_HOURS, so a task that had *never run* in its
entire life reported OK/WARN forever instead of failing the healthcheck. Two
fixes are pinned down here:

1. scrape-sources-daily has a staleness window, same as the other daily task.
2. A seeded task with NO configured window no longer silently passes at any
   age — it reports WARN with an explicit "add it" message, not OK.
3. Staleness for a *configured* task is now FAIL, not WARN, so a dead schedule
   trips deploy/healthcheck.sh's non-zero exit.
"""

import unittest
from datetime import timedelta
from types import SimpleNamespace

from django.test import TestCase, tag
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from events.management.commands.healthcheck import (
    DEFAULT_STALENESS_HOURS,
    FAIL,
    OK,
    WARN,
    Command,
)


def _fake_task(name: str, last_run_at):
    return SimpleNamespace(name=name, last_run_at=last_run_at)


@tag("fast")
class TaskFreshnessUnitTests(unittest.TestCase):
    """Exercise _task_freshness directly against fake task objects — no DB."""

    def setUp(self):
        self.cmd = Command()
        self.now = timezone.now()

    def test_scrape_sources_daily_has_a_configured_window(self):
        # The exact defect: this key was missing entirely.
        self.assertIn("scrape-sources-daily", DEFAULT_STALENESS_HOURS)
        self.assertEqual(DEFAULT_STALENESS_HOURS["scrape-sources-daily"], 25)

    def test_broadcast_orphan_recovery_has_a_configured_window(self):
        # Found by the first real healthcheck run on prod (2026-07-29): the task
        # is seeded by broadcast/0009 but had no window, so it reported WARN
        # "no staleness window configured" — the exact ride-along case the
        # DEFAULT_STALENESS_HOURS comment warns about. Schedule is `0 */6 * * *`.
        self.assertEqual(DEFAULT_STALENESS_HOURS["broadcast-orphan-recovery"], 7)

    def test_orphan_recovery_one_missed_interval_still_ok(self):
        # 6h schedule + 1h grace: a run that merely landed late must not FAIL.
        task = _fake_task("broadcast-orphan-recovery", self.now - timedelta(hours=6, minutes=30))
        status, _, _ = self.cmd._task_freshness(task, "beat:broadcast-orphan-recovery", self.now)
        self.assertEqual(status, OK)

    def test_orphan_recovery_two_missed_intervals_fails(self):
        task = _fake_task("broadcast-orphan-recovery", self.now - timedelta(hours=13))
        status, _, detail = self.cmd._task_freshness(
            task, "beat:broadcast-orphan-recovery", self.now
        )
        self.assertEqual(status, FAIL)
        self.assertIn("STALE", detail)

    def test_configured_task_never_run_fails(self):
        task = _fake_task("scrape-sources-daily", None)
        status, _, detail = self.cmd._task_freshness(task, "beat:scrape-sources-daily", self.now)
        self.assertEqual(status, FAIL)
        self.assertIn("never run", detail)

    def test_configured_task_within_window_is_ok(self):
        task = _fake_task("ingest-events-daily", self.now - timedelta(hours=5))
        status, _, _ = self.cmd._task_freshness(task, "beat:ingest-events-daily", self.now)
        self.assertEqual(status, OK)

    def test_configured_task_stale_fails_not_warns(self):
        task = _fake_task("ingest-events-daily", self.now - timedelta(hours=30))
        status, _, detail = self.cmd._task_freshness(task, "beat:ingest-events-daily", self.now)
        self.assertEqual(status, FAIL)
        self.assertIn("STALE", detail)

    def test_unlisted_task_does_not_silently_pass(self):
        # A task with no entry in DEFAULT_STALENESS_HOURS at all — e.g. the
        # next task someone adds to the schedule and forgets to configure.
        task = _fake_task("some-new-task-nobody-configured", self.now - timedelta(days=400))
        status, _, detail = self.cmd._task_freshness(task, "beat:some-new-task", self.now)
        self.assertNotEqual(status, OK)
        self.assertEqual(status, WARN)
        self.assertIn("DEFAULT_STALENESS_HOURS", detail)

    def test_unlisted_task_recently_run_also_does_not_pass(self):
        # Recency must not mask the missing-window gap either.
        task = _fake_task("some-new-task-nobody-configured", self.now)
        status, _, _ = self.cmd._task_freshness(task, "beat:some-new-task", self.now)
        self.assertNotEqual(status, OK)


@tag("db")
class PeriodicTaskHealthcheckDbTests(TestCase):
    """End-to-end against real PeriodicTask rows, including the migration-seeded
    scrape-sources-daily task."""

    def setUp(self):
        self.cmd = Command()

    def test_scrape_sources_daily_seeded_and_never_run_fails(self):
        # Matches prod as found: seeded by ingestion migration 0012, enabled,
        # last_run_at NULL because beat never survived to fire it.
        pt = PeriodicTask.objects.get(name="scrape-sources-daily")
        self.assertTrue(pt.enabled)
        self.assertIsNone(pt.last_run_at)

        results = self.cmd._check_periodic_tasks()
        matches = [r for r in results if r[1] == "beat:scrape-sources-daily"]
        self.assertEqual(len(matches), 1)
        status, _, detail = matches[0]
        self.assertEqual(status, FAIL)
        self.assertIn("never run", detail)

    def test_missing_seeded_task_fails(self):
        PeriodicTask.objects.filter(name="scrape-sources-daily").delete()
        results = self.cmd._check_periodic_tasks()
        matches = [r for r in results if r[1] == "beat:scrape-sources-daily"]
        self.assertEqual(len(matches), 1)
        status, _, detail = matches[0]
        self.assertEqual(status, FAIL)
        self.assertIn("missing", detail)

    def test_stale_but_previously_run_task_fails_the_whole_check(self):
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="0", hour="4", day_of_week="*", day_of_month="*", month_of_year="*"
        )
        pt, _ = PeriodicTask.objects.update_or_create(
            name="scrape-sources-daily",
            defaults={
                "task": "ingestion.tasks.scrape_all_sources_task",
                "crontab": schedule,
                "enabled": True,
                "last_run_at": timezone.now() - timedelta(hours=200),
            },
        )
        results = self.cmd._check_periodic_tasks()
        matches = [r for r in results if r[1] == "beat:scrape-sources-daily"]
        status, _, detail = matches[0]
        self.assertEqual(status, FAIL)
        self.assertIn("STALE", detail)
