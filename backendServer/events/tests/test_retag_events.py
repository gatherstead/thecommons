"""Suite 47.3 — retag_events management command + the 0025 data migration.

retag_events backfills weekends/evenings/daytime tags (computed from
Event.date via events.tagging.day_part_tags) onto events that predate the
publish-time computation, and strips both the current and legacy
'-only' day-part slugs first. Migration 0025 deletes the retired Tag rows
outright (lgbtq-friendly, speaks-spanish, and the three orphaned '-only'
slugs).
"""

import importlib
from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo

from django.apps import apps as global_apps
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, tag

from events import cache as events_cache
from events.models import Event, Tag

from .factories import make_event, make_town

migration_0025 = importlib.import_module("events.migrations.0025_delete_retired_tags")

_ET = ZoneInfo("America/New_York")


def _run_retag(dry_run=False):
    out = StringIO()
    call_command("retag_events", dry_run=dry_run, stdout=out)
    return out.getvalue()


@tag("db")
class RetagEventsCommandTests(TestCase):
    def setUp(self):
        cache.clear()
        self.town = make_town()

    def test_computes_exact_tag_set_from_event_date(self):
        # Saturday 9am ET -> daytime + weekends. Seed with a stale LLM-guessed
        # tag plus a legacy '-only' slug, both of which should be dropped.
        sat_9am = datetime(2026, 8, 8, 9, 0, tzinfo=_ET)
        event = make_event("Sat morning", town=self.town, date=sat_9am)
        stale, _ = Tag.objects.get_or_create(name="evenings")
        legacy, _ = Tag.objects.get_or_create(name="weekends-only")
        event.tags.set([stale, legacy])

        _run_retag()

        event.refresh_from_db()
        self.assertEqual({t.name for t in event.tags.all()}, {"daytime", "weekends"})

    def test_non_day_part_tags_are_preserved(self):
        # The easiest thing to accidentally wipe with a naive .set() call.
        sat_9am = datetime(2026, 8, 8, 9, 0, tzinfo=_ET)
        event = make_event("Sat morning with extras", town=self.town, date=sat_9am)
        free, _ = Tag.objects.get_or_create(name="free")
        nature, _ = Tag.objects.get_or_create(name="nature")
        event.tags.set([free, nature])

        _run_retag()

        event.refresh_from_db()
        self.assertEqual(
            {t.name for t in event.tags.all()}, {"daytime", "weekends", "free", "nature"}
        )

    def test_dry_run_writes_nothing(self):
        sat_9am = datetime(2026, 8, 8, 9, 0, tzinfo=_ET)
        event = make_event("Sat morning", town=self.town, date=sat_9am)
        legacy, _ = Tag.objects.get_or_create(name="daytime-only")
        event.tags.set([legacy])

        output = _run_retag(dry_run=True)

        event.refresh_from_db()
        self.assertEqual({t.name for t in event.tags.all()}, {"daytime-only"})
        self.assertIn("Would change 1", output)
        self.assertIn("no tags were written", output)

    def test_second_run_is_idempotent_and_reports_zero_changed(self):
        sat_9am = datetime(2026, 8, 8, 9, 0, tzinfo=_ET)
        make_event("Sat morning", town=self.town, date=sat_9am)
        weekday_evening = datetime(2026, 8, 10, 19, 0, tzinfo=_ET)  # Monday 7pm
        make_event("Weekday evening", town=self.town, date=weekday_evening)

        first_output = _run_retag()
        second_output = _run_retag()

        self.assertIn("Changed 2", first_output)
        self.assertIn("Changed 0", second_output)

    def test_legacy_only_slugs_are_gone_from_every_event_after_run(self):
        sat_9am = datetime(2026, 8, 8, 9, 0, tzinfo=_ET)
        weekday_evening = datetime(2026, 8, 10, 19, 0, tzinfo=_ET)
        e1 = make_event("A", town=self.town, date=sat_9am)
        e2 = make_event("B", town=self.town, date=weekday_evening)
        e1.tags.set([Tag.objects.get_or_create(name="weekends-only")[0]])
        e2.tags.set([Tag.objects.get_or_create(name="evenings-only")[0]])

        _run_retag()

        legacy_names = {"weekends-only", "evenings-only", "daytime-only"}
        for event in Event.objects.prefetch_related("tags").all():
            self.assertFalse({t.name for t in event.tags.all()} & legacy_names)

    def test_reports_scanned_added_and_collapsed_counts(self):
        sat_9am = datetime(2026, 8, 8, 9, 0, tzinfo=_ET)
        event = make_event("Sat morning", town=self.town, date=sat_9am)
        legacy, _ = Tag.objects.get_or_create(name="weekends-only")
        event.tags.set([legacy])

        output = _run_retag()

        self.assertIn("Scanned 1 event(s)", output)
        self.assertIn("Changed 1", output)
        self.assertIn("Day-part tags added: 2", output)  # daytime + weekends
        self.assertIn("Legacy '-only' slugs collapsed: 1", output)

    def test_real_run_invalidates_events_cache(self):
        sat_9am = datetime(2026, 8, 8, 9, 0, tzinfo=_ET)
        make_event("Sat morning", town=self.town, date=sat_9am)

        before = cache.get(events_cache.EVENTS_LIST_VERSION_KEY)
        _run_retag()
        after = cache.get(events_cache.EVENTS_LIST_VERSION_KEY)

        self.assertIsNotNone(after)
        if before is not None:
            self.assertGreater(after, before)


@tag("db")
class DeleteRetiredTagsMigrationTests(TestCase):
    """Exercises 0025's RunPython function directly, matching the pattern in
    test_town_backfill.py — the migration is already applied in the test DB,
    so this proves the function itself is correct and idempotent rather than
    depending on prod-only rows.
    """

    def test_deletes_retired_tag_rows(self):
        for name in [
            "lgbtq-friendly",
            "speaks-spanish",
            "weekends-only",
            "evenings-only",
            "daytime-only",
        ]:
            Tag.objects.get_or_create(name=name)

        migration_0025.delete_retired_tags(global_apps, None)

        remaining = set(
            Tag.objects.filter(
                name__in=[
                    "lgbtq-friendly",
                    "speaks-spanish",
                    "weekends-only",
                    "evenings-only",
                    "daytime-only",
                ]
            ).values_list("name", flat=True)
        )
        self.assertEqual(remaining, set())

    def test_linked_events_survive_with_other_tags_intact(self):
        town = make_town()
        event = make_event("Linked event", town=town)
        retired = Tag.objects.get_or_create(name="lgbtq-friendly")[0]
        keeper = Tag.objects.get_or_create(name="free")[0]
        event.tags.set([retired, keeper])

        migration_0025.delete_retired_tags(global_apps, None)

        event.refresh_from_db()
        self.assertEqual({t.name for t in event.tags.all()}, {"free"})

    def test_idempotent_on_second_run(self):
        migration_0025.delete_retired_tags(global_apps, None)
        migration_0025.delete_retired_tags(global_apps, None)  # should not raise
        self.assertEqual(Tag.objects.filter(name__in=migration_0025.RETIRED_TAG_NAMES).count(), 0)
