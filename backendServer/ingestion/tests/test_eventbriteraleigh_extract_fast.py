from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.eventbriteraleigh import EventbriteraleighScraper

FIXTURE = Path(__file__).parent / "fixtures" / "eventbriteraleigh.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# back-dated 2020 event to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class EventbriteraleighExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture — no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.eventbriteraleigh.timezone.now")
    def test_extracts_future_local_events_from_server_data(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = EventbriteraleighScraper().extract(self.html)

        # Fixture carries 5 events: 3 future local, 1 online (dropped), 1
        # back-dated to 2020 (dropped by the past-event filter).
        self.assertEqual(len(events), 3)
        titles = [e.title for e in events]
        self.assertNotIn(
            "LITERACY. NOW. A National Parent-Led Conference to End the Literacy Crisis", titles
        )
        self.assertNotIn(
            "250 aka Finesse2tymes takes over CLUB LOVE (back-dated for filter test)", titles
        )

        club = next(e for e in events if e.title == "250 aka Finesse2tymes takes over CLUB LOVE")
        self.assertEqual(club.start.isoformat(), "2026-07-31T22:00:00-04:00")
        self.assertIsNotNone(club.start.tzinfo)
        self.assertEqual(club.end.isoformat(), "2026-08-01T02:00:00-04:00")
        self.assertEqual(club.source_uid, "1995343344657")
        self.assertEqual(
            club.source_url,
            "https://www.eventbrite.com/e/250-aka-finesse2tymes-takes-over-club-love-tickets-1995343344657",
        )
        # Venue name plus street address, so the standardizer can infer the town.
        self.assertEqual(club.location, "4400 Craftsman Dr, 4400 Craftsman Drive, Raleigh, NC")
        self.assertIn("free for everybody", club.description)

    @mock.patch("ingestion.scraping.scrapers.eventbriteraleigh.timezone.now")
    def test_online_events_are_dropped(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = EventbriteraleighScraper().extract(self.html)

        self.assertTrue(all("LITERACY" not in e.title for e in events))

    def test_no_server_data_yields_no_events(self):
        self.assertEqual(EventbriteraleighScraper().extract("<html><body>nope</body></html>"), [])

    def test_malformed_server_data_yields_no_events(self):
        html = "<script>window.__SERVER_DATA__ = {not valid json;</script>"
        self.assertEqual(EventbriteraleighScraper().extract(html), [])
