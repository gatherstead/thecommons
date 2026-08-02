from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.carychamber import CarychamberScraper

FIXTURE = Path(__file__).parent / "fixtures" / "carychamber.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# back-dated 2020 event to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31, 12, 0, 0))


@tag("fast")
class CarychamberExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture — no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.carychamber.timezone.now")
    def test_extracts_future_events_and_drops_past(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = CarychamberScraper().extract(self.html)

        # Fixture carries 5 events: 4 future, 1 back-dated to 2020 that the
        # past-event filter must drop.
        self.assertEqual(len(events), 4)
        self.assertNotIn("Past Event (back-dated for filter test)", [e.title for e in events])

    @mock.patch("ingestion.scraping.scrapers.carychamber.timezone.now")
    def test_start_and_end_built_from_date_plus_free_text_time(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = CarychamberScraper().extract(self.html)

        ambassador = next(e for e in events if e.title == "Ambassador Information Session")
        # "12:00 Noon" is the site's own non-standard time string for noon.
        self.assertEqual(ambassador.start.hour, 12)
        self.assertEqual(ambassador.start.minute, 0)
        self.assertEqual(ambassador.start.day, 5)
        self.assertIsNotNone(ambassador.start.tzinfo)
        self.assertEqual(ambassador.end.hour, 13)
        self.assertEqual(ambassador.source_uid, "6241")
        self.assertEqual(
            ambassador.source_url,
            "https://web.carychamber.com/events/eventdetail.aspx?eventid=6241",
        )

    @mock.patch("ingestion.scraping.scrapers.carychamber.timezone.now")
    def test_description_is_html_unescaped_and_stripped(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = CarychamberScraper().extract(self.html)

        golf = next(e for e in events if e.title == "Education Golf Tournament")
        self.assertNotIn("<p>", golf.description)
        self.assertNotIn("&nbsp;", golf.description)
        self.assertIn("beautiful day on the course", golf.description)

    @mock.patch("ingestion.scraping.scrapers.carychamber.timezone.now")
    def test_titles_are_html_unescaped(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = CarychamberScraper().extract(self.html)

        golf_academy = next(e for e in events if "Golf Academy" in e.title)
        self.assertEqual(golf_academy.title, "Ladies Lunch & Learn Golf Academy")

    def test_no_events_yields_empty_list(self):
        self.assertEqual(CarychamberScraper().extract('<?xml version="1.0"?><WCData></WCData>'), [])

    def test_malformed_xml_yields_empty_list(self):
        self.assertEqual(CarychamberScraper().extract("<html><body>nope"), [])
