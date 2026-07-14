"""Seed the django-celery-beat schedule for broadcast orphan recovery.

Crash-safety net: if the broadcast worker dies mid-submission, some rows can get
stranded in a non-terminal state. This periodic task runs every 6 hours (on the
hour, UTC) to sweep those up and recover them. UTC is used since this is internal
crash-recovery, not user-facing timing.

This is a one-time seed — schedules live in Postgres and are edited live in the
django admin (Periodic Tasks). See docs/redis-celery-handoff.md.
"""
from django.db import migrations

TASK_NAME = "broadcast-orphan-recovery"
TASK_PATH = "broadcast.tasks.recover_broadcast_orphans"


def create_schedule(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="*/6",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="UTC",
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
        ("broadcast", "0008_accesscode_code"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_schedule, remove_schedule),
    ]
