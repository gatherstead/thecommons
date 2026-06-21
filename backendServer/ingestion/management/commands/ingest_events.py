import logging
import os
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from ingestion.importers.ics_importer import poll_all_ics_sources
from ingestion.standardizer import standardize_all_unprocessed
from ingestion.deduplicator import dedup_all_pending
from ingestion.safety_scorer import score_all_unscored
from ingestion.services import auto_publish_safe_events

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run the full event ingestion pipeline: poll sources → standardize → dedup'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-cleanup', action='store_true',
            help='Skip deletion of past events'
        )
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
        parser.add_argument(
            '--skip-safety', action='store_true',
            help='Skip safety scoring'
        )
        parser.add_argument(
            '--skip-autopublish', action='store_true',
            help='Skip auto-publishing safe events'
        )
        parser.add_argument(
            '--shard', type=str, default=None,
            help=(
                'Shard the source poll as N/M (e.g. 0/3). Only sources where '
                'id %% M == N are polled. If omitted and INGEST_SHARD_COUNT is set '
                'in the env, N is auto-computed as (day_of_year %% M).'
            ),
        )

    def _resolve_shard(self, shard_arg):
        """Parse --shard or fall back to INGEST_SHARD_COUNT env var. Returns (n, m) or None."""
        if shard_arg:
            try:
                n_str, m_str = shard_arg.split('/')
                n, m = int(n_str), int(m_str)
            except ValueError:
                raise CommandError(f"--shard must look like N/M (got {shard_arg!r})")
            if m <= 0 or n < 0 or n >= m:
                raise CommandError(f"--shard N/M requires 0 <= N < M and M > 0 (got {n}/{m})")
            return (n, m)

        m_env = os.environ.get('INGEST_SHARD_COUNT')
        if m_env:
            try:
                m = int(m_env)
            except ValueError:
                raise CommandError(f"INGEST_SHARD_COUNT must be an integer (got {m_env!r})")
            if m <= 1:
                return None  # 1 (or less) disables sharding — poll everything.
            n = date.today().timetuple().tm_yday % m
            return (n, m)

        return None

    def handle(self, *args, **options):
        self.stdout.write("Starting event ingestion pipeline...\n")

        # Step 0: Clean up past events
        if not options['skip_cleanup']:
            self.stdout.write("Step 0: Cleaning up past events...")
            try:
                from django.core.management import call_command
                call_command('cleanup_old_events')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  → Error: {e}\n"))
        else:
            self.stdout.write("Step 0: Skipped (--skip-cleanup)\n")

        # Step 1: Poll ICS feeds
        if not options['skip_poll']:
            shard = self._resolve_shard(options.get('shard'))
            shard_msg = f" (shard {shard[0]}/{shard[1]})" if shard else ""
            self.stdout.write(f"Step 1: Polling ICS sources{shard_msg}...")
            try:
                new_count = poll_all_ics_sources(shard=shard)
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

        # Step 4: Safety scoring
        if not options['skip_safety']:
            self.stdout.write("Step 4: Safety scoring with Gemini...")
            try:
                scored_count = score_all_unscored()
                self.stdout.write(self.style.SUCCESS(f"  → {scored_count} events scored\n"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  → Error: {e}\n"))
        else:
            self.stdout.write("Step 4: Skipped (--skip-safety)\n")

        # Step 5: Auto-publish safe events
        if not options['skip_autopublish']:
            self.stdout.write("Step 5: Auto-publishing safe events...")
            try:
                result = auto_publish_safe_events()
                self.stdout.write(self.style.SUCCESS(
                    f"  → {result['auto_approved']} auto-published, "
                    f"{result['held_for_review']} held for review\n"
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  → Error: {e}\n"))
        else:
            self.stdout.write("Step 5: Skipped (--skip-autopublish)\n")

        self.stdout.write(self.style.SUCCESS(
            "\nPipeline complete. Check Django Admin for events held for review.\n"
        ))
