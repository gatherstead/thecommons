from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.chapelhillnc import ChapelhillncScraper

_LOCAL_TZ = ZoneInfo("America/New_York")

FIXTURE = Path(__file__).parent / "fixtures" / "chapelhillnc.html"

# Fixed "now" the fixture's events (July 2-29, 2026) were built to be
# future-dated against -- real data confirmed live on the site 2026-07-31,
# captured from a month-grid render whose events had already mostly passed
# by that date, so "now" is pinned to the start of that same month instead.
# The fixture also carries one back-dated 2020 event to exercise the
# past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 1))


@tag("fast")
class ChapelhillncExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture -- no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.chapelhillnc.timezone.now")
    def test_extracts_future_events_from_calendar_grid(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = ChapelhillncScraper().extract(self.html)

        # Fixture carries 6 day cells: 1 back-dated to 2020 (dropped by the
        # past-event filter) and 5 real future events.
        self.assertEqual(len(events), 5)
        self.assertNotIn("Past Event (back-dated for filter test)", [e.title for e in events])

        drone_show = next(e for e in events if e.title == "Chapel Hill July 4th Drone Show")
        self.assertEqual(drone_show.start, datetime(2026, 7, 4, tzinfo=_LOCAL_TZ))
        self.assertIsNotNone(drone_show.start.tzinfo)
        self.assertEqual(drone_show.source_uid, "62ab25af-7708-4f73-80c3-53ad722a6312:2026-07-04")
        # The DOM carries no start time, location, description, or permalink --
        # only day-level dates and a stable item id -- so these stay blank
        # rather than being invented.
        self.assertEqual(drone_show.location, "")
        self.assertEqual(drone_show.description, "")
        self.assertEqual(drone_show.source_url, "")

    @mock.patch("ingestion.scraping.scrapers.chapelhillnc.timezone.now")
    def test_recurring_series_gets_per_occurrence_uid(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = ChapelhillncScraper().extract(self.html)

        food_distribution = next(e for e in events if e.title == "Food Distribution")
        # Same `data-item-id` as the site's other "Food Distribution" occurrence
        # would reuse, disambiguated by date so each occurrence is unique.
        self.assertEqual(
            food_distribution.source_uid, "a5ff3873-c5e9-4f09-9449-47ca0db32b15:2026-07-08"
        )

    def test_no_calendar_cells_yields_no_events(self):
        self.assertEqual(ChapelhillncScraper().extract("<html><body>nope</body></html>"), [])
