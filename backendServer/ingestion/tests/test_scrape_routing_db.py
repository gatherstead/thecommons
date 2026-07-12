"""Migration 0012 seeds the scrape beat schedule; CELERY_TASK_ROUTES pins the
scrape task to its own queue so headless Chromium never lands on the default
worker shared with digests/ingestion."""

from django.conf import settings
from django.test import TestCase, tag
from django_celery_beat.models import PeriodicTask


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
