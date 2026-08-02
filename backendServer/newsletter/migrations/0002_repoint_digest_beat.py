"""Repoint the beat PeriodicTask rows seeded by events/migrations/0015 and
events/migrations/0020 to the digest engine's new home in newsletter/tasks.py
(ticket 41.8).

The historical seed migrations (events 0015_seed_digest_beat,
0020_seed_monthly_digest_beat) are left untouched — they created the rows
with task="events.tasks.fan_out_weekly_digest" / "...fan_out_monthly_digest".
This migration only UPDATEs the `task` dotted-path on those existing rows so
django-celery-beat's DatabaseScheduler dispatches to the tasks' new Celery
names (newsletter.tasks.fan_out_weekly_digest / fan_out_monthly_digest,
auto-derived from the module @shared_task now lives in). Fully reversible.
"""
from django.db import migrations

WEEKLY_OLD = "events.tasks.fan_out_weekly_digest"
WEEKLY_NEW = "newsletter.tasks.fan_out_weekly_digest"
MONTHLY_OLD = "events.tasks.fan_out_monthly_digest"
MONTHLY_NEW = "newsletter.tasks.fan_out_monthly_digest"


def repoint_forward(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(task=WEEKLY_OLD).update(task=WEEKLY_NEW)
    PeriodicTask.objects.filter(task=MONTHLY_OLD).update(task=MONTHLY_NEW)


def repoint_reverse(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(task=WEEKLY_NEW).update(task=WEEKLY_OLD)
    PeriodicTask.objects.filter(task=MONTHLY_NEW).update(task=MONTHLY_OLD)


class Migration(migrations.Migration):

    dependencies = [
        ("newsletter", "0001_initial"),
        ("events", "0020_seed_monthly_digest_beat"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(repoint_forward, repoint_reverse),
    ]
