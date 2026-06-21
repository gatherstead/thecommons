from django.core.management.base import BaseCommand

from events.tasks import fan_out_weekly_digest


class Command(BaseCommand):
    help = "Queue the personalized weekly digest for every WEEKLY subscriber (runs via Celery)."

    def handle(self, *args, **options):
        result = fan_out_weekly_digest.delay()
        self.stdout.write(self.style.SUCCESS(
            f"Queued weekly digest fan-out (task {result.id}). "
            "Subtasks will send per-recipient on the worker."
        ))
