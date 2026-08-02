from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.morrisvilleevents import MorrisvilleeventsScraper

FIXTURE = Path(__file__).parent / "fixtures" / "morrisvilleevents.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# back-dated 2020 event to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class MorrisvilleeventsExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture — no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.morrisvilleevents.timezone.now")
    def test_extracts_future_events_and_drops_past(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = MorrisvilleeventsScraper().extract(self.html)

        # Fixture carries 5 events: 4 future, 1 back-dated to 2020 that the
        # past-event filter must drop.
        self.assertEqual(len(events), 4)
        self.assertNotIn("Founders Day (back-dated for filter test)", [e.title for e in events])

    @mock.patch("ingestion.scraping.scrapers.morrisvilleevents.timezone.now")
    def test_event_fields(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = MorrisvilleeventsScraper().extract(self.html)

        psac = next(e for e in events if e.title == "Public Safety Advisory Committee Meeting")
        self.assertEqual(
            psac.start.isoformat(),
            datetime(2026, 8, 4, tzinfo=psac.start.tzinfo).isoformat(),
        )
        self.assertIsNotNone(psac.start.tzinfo)
        self.assertIsNone(psac.end)
        self.assertEqual(
            psac.source_url,
            "https://www.morrisvillenc.gov/Events-directory/"
            "Public-Safety-Advisory-Committee-Meeting",
        )
        self.assertEqual(psac.source_uid, psac.source_url)
        self.assertIn(
            "health, safety, and welfare",
            psac.description,
        )
        self.assertEqual(psac.location, "Fire Station No. 1, 200 Town Hall Drive, 27560")

    @mock.patch("ingestion.scraping.scrapers.morrisvilleevents.timezone.now")
    def test_address_trailing_comma_stripped_when_no_zip(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = MorrisvilleeventsScraper().extract(self.html)

        music = next(e for e in events if e.title == "Music in the Park")
        # Fixture's address has no zip: "Indian Creek Trailhead,&nbsp;101 Town
        # Hall Drive,&nbsp;&nbsp;" -- trailing comma/whitespace must be trimmed.
        self.assertEqual(music.location, "Indian Creek Trailhead, 101 Town Hall Drive")

    def test_no_items_yields_no_events(self):
        self.assertEqual(MorrisvilleeventsScraper().extract("<html><body>nope</body></html>"), [])
