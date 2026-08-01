from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.patchraleigh import PatchraleighScraper

FIXTURE = Path(__file__).parent / "fixtures" / "patchraleigh.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# synthetic back-dated event to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class PatchraleighExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture -- no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.patch.timezone.now")
    def test_extracts_future_events_from_next_data(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = PatchraleighScraper().extract(self.html)

        # Fixture carries 4 events across day buckets: 3 future, 1 back-dated
        # to 2020 that the past-event filter must drop.
        self.assertEqual(len(events), 3)
        self.assertNotIn("Past Event (back-dated for filter test)", [e.title for e in events])

        concert = next(e for e in events if e.title.startswith("Beer Garden Concert Series"))
        self.assertEqual(concert.start.isoformat(), "2026-07-31T22:00:00+00:00")
        self.assertIsNotNone(concert.start.tzinfo)
        self.assertIsNone(concert.end)
        self.assertEqual(concert.source_uid, "c65e76f8-3165-4bab-a398-76a4c6d8fbe6")
        self.assertEqual(
            concert.source_url,
            "https://patch.com/north-carolina/raleigh/calendar/event/20260731/"
            "c65e76f8-3165-4bab-a398-76a4c6d8fbe6/"
            "beer-garden-concert-series-friday-night-edition-with-the-hourglass-kids",
        )
        self.assertEqual(concert.location, "The Glass Jug Beer Lab - RTP, 5410 NC-55, Durham, NC")
        self.assertNotIn("<p>", concert.description)
        self.assertNotIn("<strong>", concert.description)

    @mock.patch("ingestion.scraping.scrapers.patch.timezone.now")
    def test_address_with_only_a_name_field_falls_back_gracefully(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = PatchraleighScraper().extract(self.html)

        soap = next(e for e in events if "Soap Making" in e.title)
        # streetAddress/city/region are all empty on this real record; only
        # the concatenated `name` field carries the full address (with the
        # site's real non-breaking spaces between segments, preserved as-is).
        self.assertEqual(
            soap.location,
            "The Glass Jug Downtown\xa0545 Foster Street, Suite 10\xa0Durham, NC 27701",
        )

    def test_no_next_data_yields_no_events(self):
        self.assertEqual(PatchraleighScraper().extract("<html><body>nope</body></html>"), [])
