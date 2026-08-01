from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.carysistercities import CarysistercitiesScraper

FIXTURE = Path(__file__).parent / "fixtures" / "carysistercities.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# back-dated event (2026-07-25, before "now") to exercise the past-event
# filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31, 12, 0, 0))


@tag("fast")
class CarysistercitiesExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture — no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.carysistercities.timezone.now")
    def test_extracts_future_events_and_drops_past(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = CarysistercitiesScraper().extract(self.html)

        # Fixture carries 4 events: 3 upcoming, 1 back-dated past event that
        # the filter must drop.
        self.assertEqual(len(events), 3)
        self.assertNotIn("CaryLIVE! The Suitcase Junket (Cary)", [e.title for e in events])

    @mock.patch("ingestion.scraping.scrapers.carysistercities.timezone.now")
    def test_google_calendar_dates_param_gives_utc_start_end(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = CarysistercitiesScraper().extract(self.html)

        final_friday = next(e for e in events if e.title == "Final Friday: Meet the Artists (Cary)")
        self.assertEqual(final_friday.start.isoformat(), "2026-07-31T22:00:00+00:00")
        self.assertEqual(final_friday.end.isoformat(), "2026-08-01T00:00:00+00:00")
        self.assertIsNotNone(final_friday.start.tzinfo)
        self.assertEqual(
            final_friday.source_url,
            "https://www.carysistercities.org/events-1/final-friday-meet-the-artists",
        )
        self.assertEqual(final_friday.source_uid, final_friday.source_url)
        self.assertIn("Final Fridays Art Crawl", final_friday.description)
        # `description` is HTML on the wire; the extractor stores plain text.
        self.assertNotIn("<p>", final_friday.description)
        self.assertNotIn("<strong>", final_friday.description)

    @mock.patch("ingestion.scraping.scrapers.carysistercities.timezone.now")
    def test_extracts_address_when_present(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = CarysistercitiesScraper().extract(self.html)

        lazy_daze = next(e for e in events if e.title == "Lazy Daze Beer Garden (CSC)")
        self.assertEqual(lazy_daze.location, "Fred G. Bond Metro Park")
        # The "(map)" link text must not leak into the venue name.
        self.assertNotIn("(map)", lazy_daze.location)

    @mock.patch("ingestion.scraping.scrapers.carysistercities.timezone.now")
    def test_missing_address_yields_empty_location(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = CarysistercitiesScraper().extract(self.html)

        asia_fest = next(e for e in events if e.title == "Asia Fest (CSC)")
        self.assertEqual(asia_fest.location, "")

    def test_no_events_yields_empty_list(self):
        self.assertEqual(CarysistercitiesScraper().extract("<html><body>nope</body></html>"), [])
