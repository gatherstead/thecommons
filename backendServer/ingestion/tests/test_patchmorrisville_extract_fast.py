from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.patchmorrisville import PatchmorrisvilleScraper

FIXTURE = Path(__file__).parent / "fixtures" / "patchmorrisville.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# synthetic back-dated event to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class PatchmorrisvilleExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture -- no DB, no browser, no network.

    Like Pittsboro, Morrisville's calendar carries only `patchAmFreeEvent`
    nodes -- fetched from https://patch.com/north-carolina/morrisville-nc/calendar,
    not the assigned section-landing URL (which has no `allEvents` at all).
    """

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.patch.timezone.now")
    def test_extracts_future_events_from_next_data(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = PatchmorrisvilleScraper().extract(self.html)

        # Fixture carries 4 events across day buckets: 3 future, 1 back-dated
        # to 2020 that the past-event filter must drop.
        self.assertEqual(len(events), 3)
        self.assertNotIn("Past Event (back-dated for filter test)", [e.title for e in events])

        rock_climb = next(e for e in events if "Homeschool Rock Climb" in e.title)
        self.assertEqual(rock_climb.start.isoformat(), "2026-08-27T10:00:00-04:00")
        self.assertIsNotNone(rock_climb.start.tzinfo)
        self.assertIsNone(rock_climb.end)
        self.assertEqual(rock_climb.source_uid, "10717592")
        self.assertEqual(
            rock_climb.source_url,
            "https://raleighfamilyadventure.com/event/homeschool-rock-climb-at-trc-morrisville/2026-08-27/",
        )
        self.assertEqual(
            rock_climb.location,
            "Triangle Rock Club - Morrisville, 102 Pheasant Wood Ct, Morrisville, NC",
        )
        self.assertEqual(rock_climb.description, "")

    @mock.patch("ingestion.scraping.scrapers.patch.timezone.now")
    def test_evening_event_parses_pm_time(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = PatchmorrisvilleScraper().extract(self.html)

        parents_night = next(e for e in events if "Parents" in e.title)
        self.assertEqual(parents_night.start.isoformat(), "2026-08-21T18:00:00-04:00")

    def test_no_next_data_yields_no_events(self):
        self.assertEqual(PatchmorrisvilleScraper().extract("<html><body>nope</body></html>"), [])
