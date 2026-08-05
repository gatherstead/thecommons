"""Ticket 49.11c — backfill categories onto existing published events.

The ingestion pipeline never populated `Event.categories` until 49.11a wired
`infer_categories` into the standardization path, so every event published
before that fix has no categories at all — 816 events in prod, of which only
527 have a surviving `StagedEvent` to work backward from. This command
classifies the other way: it reads the published `Event` row directly
(title + description), asks Gemini for up to 2 canonical category slugs via
`ingestion.standardizer.infer_categories`, and attaches the matching
`Category` rows. `infer_categories` never raises — a failed/unparseable
Gemini response comes back as `[]`, which this command counts as "left
uncategorized" and moves on, rather than aborting the batch.

Lives in `ingestion/management/commands/`, not `events/`, because it needs
`ingestion.standardizer` (Gemini) and this repo's isolation contract runs
one direction only: `ingestion` may import from `events`, never the reverse.
`retag_events.py` (events/management/commands/) is the style precedent for
this command's shape (chunked iteration, --dry-run, summary line, cache
invalidation) but could not itself do this backfill without violating that
contract.

Re-runnable, not a migration, and NOT run by deploy — deploy only runs
`manage.py migrate`, never a backfill (see suite 47's `retag_events`, which
needed the same manual step). After deploy, a prod operator must invoke this
command by hand. It targets only events with zero categories, so a second
run costs nothing: already-categorized events are excluded from the
queryset, and a real run following a real run reports 0 categorized. Unlike
`ingest_events`, this command does not shard — prod's `INGEST_SHARD_COUNT`
is not relevant here; a single invocation walks every uncategorized event.
"""

from django.core.management.base import BaseCommand

from events import cache as events_cache
from events.models import Category, Event
from ingestion.standardizer import infer_categories


class Command(BaseCommand):
    help = (
        "Infer and attach categories for published events that have none, via "
        "Gemini. Re-runnable; --dry-run previews without writing. Not run by "
        "deploy — must be invoked manually in prod after the deploy."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Classify at most N events (for trialing before the full run).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]

        scanned = 0
        categorized = 0
        uncategorized = 0

        queryset = Event.objects.filter(categories__isnull=True).order_by("pk")
        if limit is not None:
            queryset = queryset[:limit]
        queryset = queryset.iterator(chunk_size=500)

        for event in queryset:
            scanned += 1

            slugs = infer_categories(event.title, event.description)
            if not slugs:
                uncategorized += 1
                continue

            categorized += 1

            if not dry_run:
                categories = Category.objects.filter(slug__in=slugs)
                event.categories.set(categories)

        verb = "Would categorize" if dry_run else "Categorized"
        self.stdout.write(
            f"Scanned {scanned} event(s). {verb} {categorized}. "
            f"Left uncategorized (no categories inferred): {uncategorized}."
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run only — no categories were written."))
            return

        events_cache.invalidate_events_list()
        self.stdout.write(self.style.SUCCESS("Events cache invalidated."))
