import logging

from django.core.management.base import BaseCommand

from ingestion.importers.ics_importer import poll_all_ics_sources
from ingestion.standardizer import standardize_all_unprocessed
from ingestion.deduplicator import dedup_all_pending

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run the full event ingestion pipeline: poll sources → standardize → dedup'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-poll', action='store_true',
            help='Skip polling sources (only process existing raw events)'
        )
        parser.add_argument(
            '--skip-standardize', action='store_true',
            help='Skip LLM standardization'
        )
        parser.add_argument(
            '--skip-dedup', action='store_true',
            help='Skip deduplication'
        )

    def handle(self, *args, **options):
        self.stdout.write("Starting event ingestion pipeline...\n")

        # Step 1: Poll ICS feeds
        if not options['skip_poll']:
            self.stdout.write("Step 1: Polling ICS sources...")
            try:
                new_count = poll_all_ics_sources()
                self.stdout.write(self.style.SUCCESS(f"  → {new_count} new raw events\n"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  → Error: {e}\n"))
        else:
            self.stdout.write("Step 1: Skipped (--skip-poll)\n")

        # Step 2: LLM Standardization
        if not options['skip_standardize']:
            self.stdout.write("Step 2: Standardizing with Gemini...")
            try:
                std_count = standardize_all_unprocessed()
                self.stdout.write(self.style.SUCCESS(f"  → {std_count} events standardized\n"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  → Error: {e}\n"))
        else:
            self.stdout.write("Step 2: Skipped (--skip-standardize)\n")

        # Step 3: Deduplication
        if not options['skip_dedup']:
            self.stdout.write("Step 3: Deduplicating...")
            try:
                dupe_count = dedup_all_pending()
                self.stdout.write(self.style.SUCCESS(f"  → {dupe_count} duplicates found\n"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  → Error: {e}\n"))
        else:
            self.stdout.write("Step 3: Skipped (--skip-dedup)\n")

        self.stdout.write(self.style.SUCCESS(
            "\nPipeline complete. Review staged events in Django Admin.\n"
        ))
