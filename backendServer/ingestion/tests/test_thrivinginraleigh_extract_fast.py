from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.thrivinginraleigh import ThrivinginraleighScraper

FIXTURE = Path(__file__).parent / "fixtures" / "thrivinginraleigh.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one real
# past event ("Pottery Painting", Jun 17 2026) to exercise the past-event
# filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class ThrivinginraleighExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture -- no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.thrivinginraleigh.timezone.now")
    def test_extracts_future_events_only(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = ThrivinginraleighScraper().extract(self.html)

        # Fixture carries 4 events: 3 upcoming, 1 real past event that the
        # filter must drop.
        self.assertEqual(len(events), 3)
        self.assertNotIn("Pottery Painting", [e.title for e in events])

    @mock.patch("ingestion.scraping.scrapers.thrivinginraleigh.timezone.now")
    def test_multiday_event_uses_gcal_dates_range(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = ThrivinginraleighScraper().extract(self.html)

        lazy_daze = next(e for e in events if e.title.startswith("Lazy Daze"))
        # No localized start/end <time> elements exist for this multi-day
        # event; start/end must come from the Google Calendar `dates=` range.
        self.assertEqual(lazy_daze.start.isoformat(), "2026-08-22T13:00:00+00:00")
        self.assertEqual(lazy_daze.end.isoformat(), "2026-08-23T21:00:00+00:00")
        self.assertIsNotNone(lazy_daze.start.tzinfo)
        self.assertEqual(
            lazy_daze.location,
            "Cary Town Hall Campus, 327 South Academy Street Cary, NC, 27511 United States",
        )
        self.assertEqual(
            lazy_daze.source_url,
            "https://www.thrivinginraleigh.com/events/lazy-daze-arts-and-crafts-festival-2025",
        )
        self.assertEqual(lazy_daze.source_uid, "/events/lazy-daze-arts-and-crafts-festival-2025")

    @mock.patch("ingestion.scraping.scrapers.thrivinginraleigh.timezone.now")
    def test_single_day_event_fields(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = ThrivinginraleighScraper().extract(self.html)

        carnival = next(e for e in events if "CaribMask" in e.title)
        self.assertEqual(carnival.start.isoformat(), "2026-08-15T16:00:00+00:00")
        self.assertEqual(carnival.end.isoformat(), "2026-08-15T17:00:00+00:00")
        self.assertIn("RDACA", carnival.description)
        self.assertNotIn("<p>", carnival.description)

    @mock.patch("ingestion.scraping.scrapers.thrivinginraleigh.timezone.now")
    def test_address_deduplicated_when_map_link_repeats_venue_name(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = ThrivinginraleighScraper().extract(self.html)

        live_after_5 = next(e for e in events if e.title.strip() == "Live After 5")
        # The maps.google.com link for this event is just "?q=Moore Square" --
        # identical to the venue text -- so location must not repeat itself.
        self.assertEqual(live_after_5.location, "Moore Square")

    def test_no_events_yields_no_events(self):
        self.assertEqual(ThrivinginraleighScraper().extract("<html><body>nope</body></html>"), [])
