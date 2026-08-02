from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.morrisvillechamber import MorrisvillechamberScraper

FIXTURE = Path(__file__).parent / "fixtures" / "morrisvillechamber.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# back-dated 2020 event to exercise the past-event filter, and one event
# whose title the chamber marked *CANCELLED* to exercise that filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class MorrisvillechamberExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture — no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.morrisvillechamber.timezone.now")
    def test_extracts_future_uncancelled_events(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = MorrisvillechamberScraper().extract(self.html)

        # Fixture carries 5 events: 3 plain future events, 1 future event
        # marked *CANCELLED* (dropped), 1 back-dated to 2020 (dropped).
        self.assertEqual(len(events), 3)
        titles = [e.title for e in events]
        self.assertNotIn("*CANCELLED* Cregger Showroom Ribbon-Cutting After Hours Social", titles)
        self.assertFalse(any("back-dated for filter test" in t for t in titles))

    @mock.patch("ingestion.scraping.scrapers.morrisvillechamber.timezone.now")
    def test_in_person_event_fields(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = MorrisvillechamberScraper().extract(self.html)

        pizza = next(e for e in events if e.title.startswith("Bambino's Pizza"))
        self.assertEqual(pizza.start.isoformat(), "2026-08-04T20:00:00+00:00")
        self.assertIsNotNone(pizza.start.tzinfo)
        self.assertEqual(pizza.end.isoformat(), "2026-08-04T21:00:00+00:00")
        self.assertEqual(
            pizza.source_url,
            "https://morrisvillechamber.org/event-detail?e=EXCq5cP0tOLp7S7CEjtAWg2",
        )
        self.assertEqual(pizza.source_uid, "EXCq5cP0tOLp7S7CEjtAWg2")
        self.assertEqual(pizza.location, "4129 Davis Drive, Morrisville, NC, 27560")
        self.assertIn("Grand Opening and Ribbon Cutting", pizza.description)

    @mock.patch("ingestion.scraping.scrapers.morrisvillechamber.timezone.now")
    def test_online_event_has_no_street_address(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = MorrisvillechamberScraper().extract(self.html)

        virtual = next(e for e in events if "Virtual" in e.title)
        self.assertEqual(virtual.location, "Online")

    def test_invalid_json_yields_no_events(self):
        self.assertEqual(MorrisvillechamberScraper().extract("not json"), [])

    def test_no_events_key_yields_no_events(self):
        self.assertEqual(MorrisvillechamberScraper().extract('{"data": {}}'), [])
