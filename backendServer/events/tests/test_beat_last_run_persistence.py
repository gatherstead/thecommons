"""Regression test for ticket 36.4.

Root cause (confirmed on prod, see docs/ingestion-monitoring.md): django_celery_beat's
DatabaseScheduler keeps PeriodicTask.last_run_at / total_run_count in memory and only
writes them to Postgres on a sync. With CELERY_BEAT_SYNC_EVERY unset (default 0),
Scheduler.should_sync() only has the 3-minute time-based trigger left
(celery/beat.py Scheduler.sync_every = 180), so a task that fires again within that
window of the previous sync leaves its just-made last_run_at update sitting in memory
— for up to CELERY_BEAT_MAX_LOOP_INTERVAL (6h here) until beat's next sync opportunity,
or until process shutdown flushes it via `finally: self.sync()`.

This test drives a real django_celery_beat.schedulers.DatabaseScheduler end to end:
seed a PeriodicTask + CrontabSchedule, build a scheduler whose in-memory schedule
contains only that one entry (bypassing DatabaseScheduler.setup_schedule()'s full-table
scan, which would otherwise also pull in every other seeded PeriodicTask row in this
shared test DB), send it through Scheduler.apply_async with the underlying task stubbed
so nothing touches Redis, then assert the DB row itself (a fresh .get(), not the
in-memory entry) advanced last_run_at/total_run_count — with no shutdown/close call.
Without CELERY_BEAT_SYNC_EVERY = 1, should_sync() is False on a steady-state send and
the DB row is untouched; with it, sync_every_tasks=1 forces should_sync() True after
one send and the row is updated immediately.
"""

import time
from datetime import timedelta
from unittest.mock import patch

from celery import current_app
from django.test import TestCase, tag
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from django_celery_beat.schedulers import DatabaseScheduler, ModelEntry

TASK_NAME = "test-beat-last-run-persistence"


@tag("db")
class BeatLastRunPersistenceTests(TestCase):
    """Drives a real DatabaseScheduler.apply_async() and inspects the DB row."""

    def setUp(self):
        self.crontab = CrontabSchedule.objects.create(
            minute="*",
            hour="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            timezone="UTC",
        )
        # last_run_at far in the past — not load-bearing for these assertions (we
        # drive apply_async()/reserve() directly rather than relying on is_due()),
        # but keeps the row realistic.
        self.periodic_task = PeriodicTask.objects.create(
            name=TASK_NAME,
            task="events.tasks.fan_out_weekly_digest",
            crontab=self.crontab,
            enabled=True,
            last_run_at=timezone.now() - timedelta(days=1),
            total_run_count=0,
        )

    def _build_scheduler_with_single_entry(self):
        """A DatabaseScheduler whose in-memory schedule holds only our one
        PeriodicTask — avoids all_as_schedule()'s full-table scan over every
        other PeriodicTask seeded by migrations in this shared test DB. Sets
        scheduler.data/_schedule directly rather than going through the
        `schedule` property getter, which would otherwise trigger exactly that
        full re-sync (DatabaseScheduler.sync() writes dirty entries out of
        self._schedule specifically, so both must point at the same dict)."""
        scheduler = DatabaseScheduler(current_app, lazy=True)
        entry = ModelEntry(self.periodic_task, app=current_app)
        scheduler.data = {TASK_NAME: entry}
        scheduler._schedule = scheduler.data
        return scheduler

    def _send_one(self, scheduler):
        """Send the one entry through the real apply_async(), with the task
        lookup and actual dispatch stubbed so nothing touches Redis/the broker.

        DatabaseScheduler.sync() opens with close_old_connections() (see
        django_celery_beat/schedulers.py), which is harmless for a real beat
        process but fatal under Django's TestCase: that wraps the test in an
        atomic block on a single connection, and closing it mid-transaction
        breaks every later ORM call with "the connection is closed". Patched
        to a no-op here so the test can still run inside TestCase's atomic
        wrapper; this doesn't touch what's under test (should_sync()/sync()'s
        own dirty-entry save logic), only the connection-recycling housekeeping
        that a real long-running beat process needs and a single test
        transaction does not.
        """
        entry = scheduler.data[TASK_NAME]
        with patch("django_celery_beat.schedulers.close_old_connections"):
            with patch.object(scheduler, "send_task") as mock_send_task:
                with patch.object(current_app.tasks, "get", return_value=None):
                    scheduler.apply_async(entry, advance=True)
                mock_send_task.assert_called_once()

    def test_last_run_at_not_persisted_without_sync(self):
        """Pin the failure mode itself: should_sync() is False after a send that
        isn't the scheduler's first (i.e. reproduces the pre-fix config, where
        sync_every_tasks is unset and only the 180s time-based trigger remains)."""
        scheduler = self._build_scheduler_with_single_entry()
        scheduler.sync_every_tasks = None  # pre-fix: CELERY_BEAT_SYNC_EVERY unset

        # Simulate "not the first send since beat started" — _last_sync already
        # set and recent — which is the steady-state a long-running beat process
        # is in almost all the time.
        scheduler._last_sync = time.monotonic()
        scheduler._tasks_since_sync = 0

        self._send_one(scheduler)

        self.assertFalse(
            scheduler.should_sync(),
            "should_sync() must be False here to reproduce the bug: with "
            "sync_every_tasks unset, a task fired well within the 180s "
            "time-based sync window has no other trigger to flush "
            "last_run_at to Postgres.",
        )

        # And, correspondingly, the DB row itself must NOT have advanced.
        unchanged = PeriodicTask.objects.get(name=TASK_NAME)
        self.assertEqual(
            unchanged.total_run_count,
            0,
            "Without a sync, last_run_at/total_run_count must still be sitting "
            "in memory only — this is exactly the prod lag ticket 36.4 fixes.",
        )

    def test_last_run_at_persisted_immediately_with_current_settings(self):
        """With the actual project settings (CELERY_BEAT_SYNC_EVERY = 1), a single
        apply_async() call must flush last_run_at/total_run_count to Postgres
        without any explicit sync()/close()/shutdown."""
        self.assertEqual(
            current_app.conf.beat_sync_every,
            1,
            "This test asserts the fix is live; if beat_sync_every isn't 1, "
            "CELERY_BEAT_SYNC_EVERY regressed in settings.",
        )

        scheduler = self._build_scheduler_with_single_entry()
        # sync_every_tasks is read from app.conf.beat_sync_every at __init__ time
        # (celery/beat.py Scheduler.__init__), so it's already 1 here — assert it
        # explicitly so a future config regression fails loudly at this line.
        self.assertEqual(scheduler.sync_every_tasks, 1)

        # Same steady-state simulation as the failing test above, so this test
        # differs from it only in sync_every_tasks — isolating the fix.
        scheduler._last_sync = time.monotonic()
        scheduler._tasks_since_sync = 0

        before = PeriodicTask.objects.get(name=TASK_NAME)
        self.assertEqual(before.total_run_count, 0)

        self._send_one(scheduler)

        # apply_async()'s own `finally` clause already called _do_sync() (since
        # should_sync() was True mid-send) and _do_sync() resets the counter —
        # so _tasks_since_sync == 0 here is itself evidence a sync just ran,
        # not evidence that none is needed. The DB assertion below is the real
        # proof: the row must reflect the send with no explicit sync() call
        # from this test.
        self.assertEqual(
            scheduler._tasks_since_sync,
            0,
            "sync_every_tasks=1 should have forced should_sync() True and "
            "reset the counter via _do_sync() within apply_async() itself.",
        )

        after = PeriodicTask.objects.get(name=TASK_NAME)
        self.assertEqual(
            after.total_run_count,
            1,
            "last_run_at/total_run_count should be persisted to Postgres "
            "right after the send, with no explicit sync()/shutdown call.",
        )
        self.assertGreater(after.last_run_at, before.last_run_at)
