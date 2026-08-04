"""Suite 47.3 — recompute day-part tags for every existing event.

`events/tagging.py` (day_part_tags) makes `weekends`/`evenings`/`daytime`
pure functions of `Event.date`, computed at publish time. That only covers
events published from here on — every event already in the DB still carries
whatever the standardizer LLM guessed (or nothing at all), some of it under
the retired `weekends-only`/`evenings-only`/`daytime-only` slugs. This
command backfills all of them: for every event it drops the current and
legacy day-part slugs, then adds back `day_part_tags(event.date)`. Any other
tags on the event (e.g. `free`, `nature`) are left untouched.

Re-runnable, not a migration — `--dry-run` previews the same summary without
writing anything, and a second real run reports 0 changed (idempotent).

Run order in prod: run this command BEFORE `manage.py migrate`. A separate
data migration deletes the orphaned `weekends-only`/`evenings-only`/
`daytime-only` Tag rows outright (plus the retired `lgbtq-friendly` and
`speaks-spanish` tags). If migrate runs first, those `-only` Tag rows are
gone before this command can count them as "collapsed" — harmless, since
tags are recomputed straight from `event.date` either way, but the reported
collapsed-legacy-slug count would read 0 instead of the real number.
"""

from django.core.management.base import BaseCommand

from events import cache as events_cache
from events.models import Event, Tag
from events.tagging import DAY_PART_TAGS, day_part_tags

LEGACY_DAY_PART_SLUGS = frozenset({"weekends-only", "evenings-only", "daytime-only"})
STALE_DAY_PART_SLUGS = DAY_PART_TAGS | LEGACY_DAY_PART_SLUGS


class Command(BaseCommand):
    help = (
        "Recompute weekends/evenings/daytime tags for every existing event "
        "from Event.date, dropping any stale current or legacy '-only' "
        "day-part slugs first. Re-runnable; --dry-run previews without "
        "writing. Run before `migrate` in prod — see module docstring."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        scanned = 0
        changed = 0
        tags_added = 0
        legacy_collapsed = 0

        queryset = Event.objects.all().prefetch_related("tags").iterator(chunk_size=500)

        for event in queryset:
            scanned += 1

            current_names = {t.name for t in event.tags.all()}
            new_day_part = day_part_tags(event.date)
            kept = current_names - STALE_DAY_PART_SLUGS
            desired_names = kept | new_day_part

            if desired_names == current_names:
                continue

            changed += 1
            tags_added += len(new_day_part - current_names)
            legacy_collapsed += len(current_names & LEGACY_DAY_PART_SLUGS)

            if not dry_run:
                tag_objs = [Tag.objects.get_or_create(name=n)[0] for n in sorted(desired_names)]
                event.tags.set(tag_objs)

        verb = "Would change" if dry_run else "Changed"
        self.stdout.write(
            f"Scanned {scanned} event(s). {verb} {changed}. "
            f"Day-part tags added: {tags_added}. Legacy '-only' slugs collapsed: "
            f"{legacy_collapsed}."
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run only — no tags were written."))
            return

        events_cache.invalidate_events_list()
        self.stdout.write(self.style.SUCCESS("Events cache invalidated."))
