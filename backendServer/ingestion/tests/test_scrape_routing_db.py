"""Migration 0012 seeds the scrape beat schedule; CELERY_TASK_ROUTES pins the
scrape task to its own queue so headless Chromium never lands on the default
worker shared with digests/ingestion."""

from unittest import mock

from celery.exceptions import Retry
from django.conf import settings
from django.test import TestCase, override_settings, tag
from django_celery_beat.models import PeriodicTask

from ingestion.tasks import scrape_all_sources_task


@tag("db")
class ScrapeBeatScheduleTests(TestCase):
    def test_scrape_beat_seeded_by_migration(self):
        task = PeriodicTask.objects.get(name="scrape-sources-daily")
        self.assertEqual(task.task, "ingestion.tasks.scrape_all_sources_task")
        self.assertTrue(task.enabled)
        self.assertEqual(task.crontab.hour, "3")
        self.assertEqual(task.crontab.minute, "30")
        self.assertEqual(str(task.crontab.timezone), "America/New_York")


@tag("db")
class ScrapeTaskRoutingTests(TestCase):
    def test_scrape_task_routed_to_scrape_queue(self):
        self.assertEqual(
            settings.CELERY_TASK_ROUTES["ingestion.tasks.scrape_all_sources_task"]["queue"],
            "scrape",
        )


@tag("db")
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class ScrapeTaskRetryTests(TestCase):
    def test_failing_poll_retries_task(self):
        with mock.patch(
            "ingestion.tasks.poll_all_scraper_sources",
            side_effect=RuntimeError("connection reset"),
        ) as poll:
            # In eager mode self.retry() raises Retry rather than re-executing
            # inline; this confirms a transient failure is retried rather than
            # silently dropping the day's poll (previously this task had no
            # retry configuration at all).
            with self.assertRaises(Retry):
                scrape_all_sources_task.delay()

        self.assertEqual(poll.call_count, 1)
