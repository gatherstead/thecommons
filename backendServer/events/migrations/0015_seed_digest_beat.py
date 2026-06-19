"""Seed the django-celery-beat schedule for the weekly digest fan-out.

Replaces the OS-cron entry `0 18 * * 0` (TZ=America/New_York) — Sunday 18:00 ET.
The timezone is set on the CrontabSchedule so beat tracks US Eastern DST exactly
as the old cron did.

This is a one-time seed — schedules live in Postgres and are edited live in the
django admin (Periodic Tasks). See docs/redis-celery-handoff.md.
"""
from django.db import migrations

TASK_NAME = "weekly-digest-sunday"
TASK_PATH = "events.tasks.fan_out_weekly_digest"


def create_schedule(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="18",
        day_of_week="0",  # Sunday
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
        ("events", "0014_businessprofile"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_schedule, remove_schedule),
    ]
