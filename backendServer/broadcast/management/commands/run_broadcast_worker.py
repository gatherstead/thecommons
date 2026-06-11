from django.core.management.base import BaseCommand

from broadcast.worker import run_forever, run_once


class Command(BaseCommand):
    help = "Run the broadcast worker loop (claims queued submissions, drives Playwright)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once", action="store_true",
            help="Process at most one queued submission, then exit (for tests/dev).",
        )

    def handle(self, *args, **options):
        if options["once"]:
            processed = run_once()
            self.stdout.write("processed one submission" if processed else "queue empty")
            return
        run_forever()
