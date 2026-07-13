from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.visitpittsboro import VisitpittsboroScraper

FIXTURE = Path(__file__).parent / "fixtures" / "visitpittsboro_month.html"

# Fixed "now" the fixture's 3 events (07-12, 07-17, 07-19) were built to be
# future-dated against. `extract()` drops past events using the real clock,
# so the test freezes time instead of relying on wall-clock never catching up
# to the fixture's baked-in dates.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 11))


@tag("fast")
class VisitpittsboroExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture — no DB, no mocks, no browser."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.visitpittsboro.timezone.now")
    def test_extracts_future_events_from_json_ld(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = VisitpittsboroScraper().extract(self.html)

        # All 3 fixture events are future-dated relative to the frozen "now"
        # above; none should be dropped by the past-event filter.
        self.assertEqual(len(events), 3)

        postcards = next(e for e in events if e.title == "Loose Watercolor Floral Postcards")
        self.assertEqual(postcards.location, "Starrlight Mead")
        self.assertEqual(
            postcards.source_url,
            "https://visitpittsboro.com/event/loose-watercolor-floral-postcards/",
        )
        self.assertTrue(postcards.start.tzinfo is not None)
        self.assertEqual(postcards.start.isoformat(), "2026-07-12T14:00:00-04:00")
        self.assertIn("Starrlight Mead", postcards.description)
        self.assertNotIn("<p>", postcards.description)
