from pathlib import Path

from django.test import SimpleTestCase, tag

from ingestion.scraping.scrapers.visitpittsboro import VisitpittsboroScraper

FIXTURE = Path(__file__).parent / "fixtures" / "visitpittsboro_month.html"


@tag("fast")
class VisitpittsboroExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture — no DB, no mocks, no browser."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_extracts_future_events_from_json_ld(self):
        events = VisitpittsboroScraper().extract(self.html)

        # All 3 fixture events are future-dated relative to "now" at fixture-build
        # time (2026-07-12, 07-17, 07-19 vs. a 2026-07-11 build date); none should
        # be dropped by the past-event filter.
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
