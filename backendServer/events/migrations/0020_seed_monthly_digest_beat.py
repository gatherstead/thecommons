"""Seed the django-celery-beat schedule for the monthly digest fan-out.

Mirrors 0015_seed_digest_beat.py's weekly schedule — 1st of the month, 18:00
ET. The timezone is set on the CrontabSchedule so beat tracks US Eastern DST
exactly as intended.

This is a one-time seed — schedules live in Postgres and are edited live in
the django admin (Periodic Tasks). See docs/redis-celery-handoff.md.
"""
from django.db import migrations

TASK_NAME = "monthly-digest-first"
TASK_PATH = "events.tasks.fan_out_monthly_digest"


def create_schedule(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="18",
        day_of_week="*",
        day_of_month="1",
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
        ("events", "0019_newslettersubscriber_manage_token"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_schedule, remove_schedule),
    ]
