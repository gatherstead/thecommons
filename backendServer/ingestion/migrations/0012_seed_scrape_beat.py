"""Seed the django-celery-beat schedule for the daily scraper poll.

Runs 30 minutes before `ingest-events-daily` (0007_seed_ingest_beat.py) so
scraped RawEvents land before the standardize step. Routed to the dedicated
`scrape` queue via CELERY_TASK_ROUTES (backend/settings/base.py) so headless
Chromium never shares the default worker with digests/ingestion.

This is a one-time seed — schedules live in Postgres and are edited live in the
django admin (Periodic Tasks). See docs/redis-celery-handoff.md.
"""
from django.db import migrations

TASK_NAME = "scrape-sources-daily"
TASK_PATH = "ingestion.tasks.scrape_all_sources_task"


def create_schedule(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute="30",
        hour="3",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="America/New_York",
    )
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={
            "task": TASK_PATH,
            "crontab": crontab,
            "enabled": True,
        },
    )


def remove_schedule(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0011_eventsource_scraper_key"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_schedule, remove_schedule),
    ]
