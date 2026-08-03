import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from ingestion.models import RawEvent, StagedEvent

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Delete past RawEvents and StagedEvents, preserving approved-but-unpublished ones. "
        "`published` rows (permanent dedupe anchors — see ingestion/deduplicator.py) are "
        "kept until their event date has passed, then reaped here like any other past row."
    )

    def handle(self, *args, **options):
        now = timezone.now()

        # 1. Delete past staged events — but keep approved ones not yet
        #    published to the Events table. `published` rows are NOT excluded:
        #    they're the deduplicator's matching corpus, but only need to
        #    survive until their event date passes, at which point they can
        #    no longer collide with a new submission's time window.
        staged_qs = StagedEvent.objects.filter(start_datetime__lt=now).exclude(
            status="approved", published_event__isnull=True
        )
        staged_deleted, _ = staged_qs.delete()

        # 2. Delete past raw events — but keep those still backing
        #    an approved+unpublished staged event
        raw_qs = RawEvent.objects.filter(raw_start_datetime__lt=now).exclude(
            staged__status="approved", staged__published_event__isnull=True
        )
        raw_deleted, _ = raw_qs.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Cleanup: removed {staged_deleted} staged events and {raw_deleted} raw events.\n"
            )
        )
