from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.triangleonthecheap import TriangleonthecheapScraper

FIXTURE = Path(__file__).parent / "fixtures" / "triangleonthecheap.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# back-dated (Jan 1, 2026) day bucket -- a copy of a real event with only
# its header date and title edited -- to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class TriangleonthecheapExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture -- no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.triangleonthecheap.timezone.now")
    def test_extracts_future_events_grouped_by_day_header(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = TriangleonthecheapScraper().extract(self.html)

        # Fixture carries 8 events: 5 under "Today" + 2 under "Tomorrow" (7
        # future) and 1 back-dated to Jan 1 that the filter must drop.
        self.assertEqual(len(events), 7)
        self.assertNotIn("Past Event (back-dated for filter test)", [e.title for e in events])

    @mock.patch("ingestion.scraping.scrapers.triangleonthecheap.timezone.now")
    def test_time_range_parses_start_hour_with_explicit_meridiem(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = TriangleonthecheapScraper().extract(self.html)

        tasting = next(e for e in events if e.title.startswith("Tasting at Ten"))
        self.assertEqual(tasting.start.isoformat(), "2026-07-31T10:00:00-04:00")
        self.assertIsNotNone(tasting.start.tzinfo)
        self.assertEqual(
            tasting.location, "Counter Culture Coffee Headquarters and Training Center, Durham"
        )
        self.assertEqual(
            tasting.source_url,
            "https://triangleonthecheap.com/tasting-ten-free-tasting-tour-counter-culture-coffee-hq/",
        )

    @mock.patch("ingestion.scraping.scrapers.triangleonthecheap.timezone.now")
    def test_all_day_defaults_to_midnight(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = TriangleonthecheapScraper().extract(self.html)

        baskin = next(e for e in events if e.title.startswith("Baskin Robbins"))
        self.assertEqual((baskin.start.hour, baskin.start.minute), (0, 0))
        self.assertEqual(baskin.location, "Baskin-Robbins, multiple locations")

    @mock.patch("ingestion.scraping.scrapers.triangleonthecheap.timezone.now")
    def test_duplicate_permalink_stays_unique_per_title_same_day(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = TriangleonthecheapScraper().extract(self.html)

        hillsborough = [
            e
            for e in events
            if e.source_url == "https://triangleonthecheap.com/hillsborough-last-fridays-art-walk/"
        ]
        # Three distinct listings share one permalink on the same date --
        # source_uid must disambiguate all three.
        self.assertEqual(len(hillsborough), 3)
        self.assertEqual(len({e.source_uid for e in hillsborough}), 3)

        live_on_lawn = next(
            e for e in hillsborough if e.title == "Hillsborough Arts Council's Live on the Lawn"
        )
        # 2-segment meta ("time | price", no venue segment) -> no location.
        self.assertEqual(live_on_lawn.location, "")

    def test_no_day_headers_yields_no_events(self):
        self.assertEqual(TriangleonthecheapScraper().extract("<html><body>nope</body></html>"), [])
