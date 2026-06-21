"""Seed the django-celery-beat schedule for the daily ingestion pipeline.

Replaces the OS-cron entry `0 4 * * *` (TZ=America/New_York). The timezone is set
on the CrontabSchedule so beat tracks US Eastern DST exactly as the old cron did.

This is a one-time seed — schedules live in Postgres and are edited live in the
django admin (Periodic Tasks). See docs/redis-celery-handoff.md.
"""
from django.db import migrations

TASK_NAME = "ingest-events-daily"
TASK_PATH = "ingestion.tasks.run_ingestion_pipeline"


def create_schedule(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="4",
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
        ("ingestion", "0006_stagedevent_category"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_schedule, remove_schedule),
    ]
