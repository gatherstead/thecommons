from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.visitchapelhill import VisitchapelhillScraper

FIXTURE = Path(__file__).parent / "fixtures" / "visitchapelhill.html"

# Fixed "now" the fixture's 4 events (all Jul 13 or Jul 14, 2026) were built to
# be future-dated against. extract() drops past events using the real clock,
# so the test freezes time instead of relying on wall-clock never catching up
# to the fixture's baked-in dates.
_FIXTURE_BUILD_TIME = timezone.make_aware(
    datetime(2026, 7, 13, 0, 0), timezone=ZoneInfo("America/New_York")
)


@tag("fast")
class VisitchapelhillExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture -- no DB, no mocks, no browser."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.visitchapelhill.timezone.now")
    def test_extracts_events_from_rendered_list(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = VisitchapelhillScraper().extract(self.html)

        self.assertEqual(len(events), 4)

        meditation = next(e for e in events if e.title == "Silent Saturday Meditation")
        self.assertEqual(meditation.location, "Kosala Kadammpa Buddhist Center")
        self.assertEqual(
            meditation.source_url,
            "https://www.visitchapelhill.org/event/silent-saturday-meditation/34606/",
        )
        self.assertTrue(meditation.start.tzinfo is not None)
        self.assertEqual(meditation.start.isoformat(), "2026-07-13T10:00:00-04:00")
        self.assertEqual(meditation.end.isoformat(), "2026-07-13T13:00:00-04:00")
        self.assertEqual(meditation.source_uid, "34606")

        # No <li class="time"> element at all -> defaults to midnight, no end.
        open_mic = next(
            e for e in events if e.title == "Open Mic Night at Steel String Brewery Taproom"
        )
        self.assertEqual(open_mic.start.isoformat(), "2026-07-13T18:00:00-04:00")
        self.assertIsNone(open_mic.end)

        mixology = next(e for e in events if e.title == "Agave Classics | Mixology Class")
        self.assertEqual(mixology.start.isoformat(), "2026-07-14T18:30:00-04:00")
        self.assertEqual(mixology.end.isoformat(), "2026-07-14T20:00:00-04:00")

    @mock.patch("ingestion.scraping.scrapers.visitchapelhill.timezone.now")
    def test_keeps_todays_events_whose_start_time_already_passed(self, mock_now):
        # "now" is late evening on the 13th -- later than every Jul-13 event's
        # start time. The site's own filter is date-based (keeps all of
        # "today"), so our date-only comparison should too, instead of
        # dropping events whose clock time has already elapsed.
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 7, 13, 23, 0), timezone=ZoneInfo("America/New_York")
        )
        events = VisitchapelhillScraper().extract(self.html)

        self.assertEqual(len(events), 4)
