import logging

from django.core.management.base import BaseCommand

from events.models import Town
from ingestion.models import StagedEvent

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Reopen StagedEvents that were skipped for having no matching Town "
        "(status=skipped_no_town) whose town slug now resolves to a real Town row. "
        "Run this once after adding coverage for a new town (a new Town row, or an "
        "alias fix) — publish_all_approved no longer retries skipped rows on its "
        "own, so a coverage change is inert until this command flips them back to "
        "'approved' for the next publish run to pick up."
    )

    def handle(self, *args, **options):
        candidates = list(StagedEvent.objects.filter(status="skipped_no_town"))
        reopened = 0

        for staged in candidates:
            town_slug = staged.town.lower().replace(" ", "-") if staged.town else None
            if not town_slug or not Town.objects.filter(slug=town_slug).exists():
                continue
            staged.status = "approved"
            staged.save(update_fields=["status"])
            reopened += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Reopened {reopened} of {len(candidates)} skipped_no_town rows "
                "now matching a Town."
            )
        )
