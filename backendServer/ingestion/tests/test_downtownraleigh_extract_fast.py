from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.downtownraleigh import DowntownraleighScraper

FIXTURE = Path(__file__).parent / "fixtures" / "downtownraleigh.html"

# Fixed "now" the fixture's events were built to be future-dated against (real
# data confirmed live 2026-07-31); the fixture also carries one back-dated
# "Jan 1" row (same header year, earlier month) to exercise the past-event
# filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class DowntownraleighExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture -- no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.downtownraleigh.timezone.now")
    def test_extracts_future_events_grouped_by_day(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = DowntownraleighScraper().extract(self.html)

        # Fixture carries 7 events: 1 back-dated (Jan 1) that the filter must
        # drop, 3 on Jul 31, 3 on Aug 1. The "Ongoing" bucket has no day/month
        # anchor and is skipped entirely regardless of date.
        self.assertEqual(len(events), 6)
        self.assertNotIn("Past Event (back-dated for filter test)", [e.title for e in events])
        self.assertNotIn(
            "Staying Alive Special Exhibition", [e.title for e in events]
        )

    @mock.patch("ingestion.scraping.scrapers.downtownraleigh.timezone.now")
    def test_time_range_parses_start_hour(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = DowntownraleighScraper().extract(self.html)

        karaoke = next(e for e in events if e.title == "Crank Karaoke @ Crank Arm Brewing")
        self.assertEqual(karaoke.start.isoformat(), "2026-07-31T20:00:00-04:00")
        self.assertIsNotNone(karaoke.start.tzinfo)
        self.assertIsNone(karaoke.end)
        self.assertEqual(karaoke.location, "Crank Arm Brewing, Raleigh, NC")
        self.assertEqual(
            karaoke.source_url,
            "https://downtownraleigh.org/do/crank-karaoke--crank-arm-brewing",
        )
        self.assertEqual(
            karaoke.source_uid, "/do/crank-karaoke--crank-arm-brewing#2026-07-31"
        )

    @mock.patch("ingestion.scraping.scrapers.downtownraleigh.timezone.now")
    def test_range_without_leading_meridiem_uses_trailing_one(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = DowntownraleighScraper().extract(self.html)

        reset = next(e for e in events if e.title == "Friday Reset for the Weekend")
        # "1-3pm" -> starts at 1pm, not 3pm.
        self.assertEqual(reset.start.hour, 13)

    @mock.patch("ingestion.scraping.scrapers.downtownraleigh.timezone.now")
    def test_single_time_token_uppercase(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = DowntownraleighScraper().extract(self.html)

        golf = next(e for e in events if e.title == "National Disc Golf Day")
        self.assertEqual(golf.start.hour, 11)

    @mock.patch("ingestion.scraping.scrapers.downtownraleigh.timezone.now")
    def test_no_time_text_defaults_to_midnight(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = DowntownraleighScraper().extract(self.html)

        cozy = next(e for e in events if e.title.startswith("Cozy Saturday"))
        self.assertEqual((cozy.start.hour, cozy.start.minute), (0, 0))
        self.assertEqual(cozy.location, "Haymaker, Raleigh, NC")

    def test_no_rows_yields_no_events(self):
        self.assertEqual(DowntownraleighScraper().extract("<html><body>nope</body></html>"), [])
