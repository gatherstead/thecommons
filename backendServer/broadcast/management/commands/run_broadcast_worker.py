from django.core.management.base import BaseCommand

from broadcast.worker import run_once


class Command(BaseCommand):
    help = (
        "Debug helper: manually drain one queued broadcast submission. "
        "Production dispatch runs via the Celery `broadcast` queue, not this command."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process at most one queued submission, then exit (default behavior).",
        )

    def handle(self, *args, **options):
        processed = run_once()
        self.stdout.write("processed one submission" if processed else "queue empty")
