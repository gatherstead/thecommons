from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.patchdurham import PatchdurhamScraper

FIXTURE = Path(__file__).parent / "fixtures" / "patchdurham.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# back-dated 2020 event to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class PatchdurhamExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture — no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.patchdurham.timezone.now")
    def test_extracts_future_events_from_next_data(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = PatchdurhamScraper().extract(self.html)

        # Fixture carries 4 events across day buckets: 3 future, 1 back-dated
        # to 2020 that the past-event filter must drop.
        self.assertEqual(len(events), 3)
        self.assertNotIn("Past Event (back-dated for filter test)", [e.title for e in events])

        concert = next(e for e in events if e.title.startswith("Beer Garden Concert Series"))
        self.assertEqual(concert.start.isoformat(), "2026-07-31T22:00:00+00:00")
        self.assertIsNotNone(concert.start.tzinfo)
        self.assertIsNone(concert.end)
        self.assertEqual(concert.source_uid, "20fdd37c-7c6b-4b89-9d06-e09553ee9838")
        self.assertEqual(
            concert.source_url,
            "https://patch.com/north-carolina/durham-nc/calendar/event/20260731/"
            "20fdd37c-7c6b-4b89-9d06-e09553ee9838/"
            "beer-garden-concert-series-friday-night-edition-with-the-hourglass-kids",
        )
        # Venue name plus street address, so the standardizer can infer the town.
        self.assertEqual(concert.location, "The Glass Jug Beer Lab - RTP, 5410 NC-55, Durham, NC")
        # `body` is HTML on the wire; the extractor stores plain text.
        self.assertNotIn("<p>", concert.description)
        self.assertNotIn("<strong>", concert.description)
        self.assertIn("Glass Jug RTP", concert.description)

    @mock.patch("ingestion.scraping.scrapers.patchdurham.timezone.now")
    def test_titles_are_html_unescaped(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = PatchdurhamScraper().extract(self.html)

        soap = next(e for e in events if "Soap Making" in e.title)
        self.assertEqual(soap.title, "Sip & Create: Soap Making Workshop")

    def test_no_next_data_yields_no_events(self):
        self.assertEqual(PatchdurhamScraper().extract("<html><body>nope</body></html>"), [])
