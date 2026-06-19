"""Guards the beat schedule seeded by migrations (events 0015, ingestion 0007).
A future migration silently dropping or disabling a schedule should fail here."""
from django.test import TestCase, tag
from django_celery_beat.models import PeriodicTask


@tag('db')
class BeatScheduleSeedTests(TestCase):
    def test_weekly_digest_schedule_seeded(self):
        pt = PeriodicTask.objects.get(name='weekly-digest-sunday')
        self.assertEqual(pt.task, 'events.tasks.fan_out_weekly_digest')
        self.assertTrue(pt.enabled)
        self.assertEqual(pt.crontab.minute, '0')
        self.assertEqual(pt.crontab.hour, '18')
        self.assertEqual(pt.crontab.day_of_week, '0')
        self.assertEqual(str(pt.crontab.timezone), 'America/New_York')

    def test_daily_ingest_schedule_seeded(self):
        pt = PeriodicTask.objects.get(name='ingest-events-daily')
        self.assertEqual(pt.task, 'ingestion.tasks.run_ingestion_pipeline')
        self.assertTrue(pt.enabled)
        self.assertEqual(pt.crontab.hour, '4')
        self.assertEqual(pt.crontab.day_of_week, '*')
        self.assertEqual(str(pt.crontab.timezone), 'America/New_York')
