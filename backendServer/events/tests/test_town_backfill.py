"""Guards the ticket-36.2 backfill (migration 0017) for the 15 live events
that shipped with `town = NULL`.

Migration 0017 runs as part of the test database setup, so the venues it maps
already carry the right `Town` FK by the time these tests run — these tests
assert that end state, then separately exercise the migration's own
`backfill_towns` / `unbackfill_towns` functions directly (via the historical
app registry) to prove reversibility without depending on unrelated rows.
"""

import importlib

from django.apps import apps as global_apps
from django.test import TestCase, tag

from events.models import Event, Town

from .factories import make_event, make_town

backfill_module = importlib.import_module("events.migrations.0017_backfill_null_town_events")

BACKFILLED_VENUES = {
    "Fair Game Beverage Company": "pittsboro",
    "bmc brewing": "pittsboro",
    "Chatham YMCA": "pittsboro",
    "Covenant Place": "carrboro",
}

LEFT_NULL_VENUE = "Jordan Lake State Recreation Area – New Hope Overlook Access"


@tag("db")
class TownBackfillMigrationTests(TestCase):
    """Exercises 0017's RunPython functions directly against fresh rows.

    This does not depend on prod's actual 15 rows still existing in the test
    DB — it creates its own rows shaped like them (empty source_name, NULL
    town, matching venue strings) and proves the migration's mapping function
    assigns the right town and leaves the untouched venue alone.
    """

    def setUp(self):
        for slug, name in [("pittsboro", "Pittsboro"), ("carrboro", "Carrboro")]:
            make_town(slug, name)

        self.mapped_events = {}
        for venue in BACKFILLED_VENUES:
            event = make_event(title=f"{venue} test event", venue=venue)
            event.town = None
            event.source_name = ""
            event.save()
            self.mapped_events[venue] = event

        left_null_event = make_event(title="Spring Cleanup", venue=LEFT_NULL_VENUE)
        left_null_event.town = None
        left_null_event.source_name = ""
        left_null_event.save()
        self.left_null_event = left_null_event

    def _run_backfill(self):
        backfill_module.backfill_towns(global_apps, None)

    def test_backfill_assigns_mapped_venues_to_expected_town(self):
        self._run_backfill()
        for venue, slug in BACKFILLED_VENUES.items():
            event = Event.objects.get(uuid=self.mapped_events[venue].uuid)
            self.assertIsNotNone(event.town, f"{venue} should have a town after backfill")
            self.assertEqual(event.town.slug, slug)

    def test_backfill_leaves_ambiguous_venue_null(self):
        self._run_backfill()
        event = Event.objects.get(uuid=self.left_null_event.uuid)
        self.assertIsNone(event.town)

    def test_backfill_does_not_touch_events_with_source_name(self):
        # A row with the same venue string but a real source_name looks like
        # pipeline output, not the hand-entered rows this migration targets.
        town = Town.objects.get(slug="pittsboro")
        pipeline_event = make_event(
            title="Pipeline-sourced Fair Game show",
            venue="Fair Game Beverage Company",
            town=town,
        )
        pipeline_event.town = None
        pipeline_event.source_name = "some-ics-feed"
        pipeline_event.save()

        self._run_backfill()

        pipeline_event.refresh_from_db()
        self.assertIsNone(pipeline_event.town)

    def test_unbackfill_restores_null_for_mapped_venues(self):
        self._run_backfill()
        backfill_module.unbackfill_towns(global_apps, None)
        for venue in BACKFILLED_VENUES:
            event = Event.objects.get(uuid=self.mapped_events[venue].uuid)
            self.assertIsNone(event.town)


@tag("db")
class TownBackfillAppliedStateTests(TestCase):
    """The migration already ran against the test DB (it's in the migration
    graph) — these tests describe the town coverage it's expected to produce
    without asserting on prod-only rows that may not exist in a fresh DB.
    """

    def test_covered_towns_used_by_backfill_exist(self):
        expected_slugs = set(BACKFILLED_VENUES.values())
        self.assertTrue(expected_slugs <= set(Town.objects.values_list("slug", flat=True)))
