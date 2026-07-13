from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import TestCase, tag
from django.utils import timezone

from ingestion.importers.scraper_importer import fetch_scraper_source
from ingestion.models import EventSource, RawEvent

FIXTURE = Path(__file__).parent / "fixtures" / "visitpittsboro_month.html"

# Fixed "now" the fixture's 3 events (07-12, 07-17, 07-19) were built to be
# future-dated against — see test_scraper_extract_fast.py for the same fix.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 11))


@tag("db")
class ScraperImporterTests(TestCase):
    def setUp(self):
        self.source = EventSource.objects.create(
            name="VisitPittsboro",
            source_type="scraper",
            url="https://visitpittsboro.com/events/month/",
            scraper_key="visitpittsboro",
        )
        self.html = FIXTURE.read_text(encoding="utf-8")
        self.enterContext(
            mock.patch(
                "ingestion.scraping.scrapers.visitpittsboro.timezone.now",
                return_value=_FIXTURE_BUILD_TIME,
            )
        )

    def _patched_render(self):
        return mock.patch(
            "ingestion.importers.scraper_importer.render_page", return_value=self.html
        )

    def test_parses_page_into_raw_events(self):
        with self._patched_render() as render:
            created = fetch_scraper_source(self.source)
        render.assert_called_once_with(self.source.url)
        self.assertEqual(len(created), 3)

        titles = set(RawEvent.objects.values_list("raw_title", flat=True))
        self.assertEqual(
            titles,
            {
                "Loose Watercolor Floral Postcards",
                "Live Music: Too Much Fun! at City Tap",
                "The City Tap’s 18th Birthday Party",
            },
        )

        postcards = RawEvent.objects.get(raw_title="Loose Watercolor Floral Postcards")
        self.assertEqual(
            postcards.source_url,
            "https://visitpittsboro.com/event/loose-watercolor-floral-postcards/",
        )
        self.assertEqual(postcards.source_uid, postcards.source_url)

        self.source.refresh_from_db()
        self.assertIsNotNone(self.source.last_polled)

    def test_rerun_dedupes_on_source_uid(self):
        with self._patched_render():
            fetch_scraper_source(self.source)
        with self._patched_render():
            created_again = fetch_scraper_source(self.source)

        self.assertEqual(created_again, [])
        self.assertEqual(RawEvent.objects.count(), 3)
