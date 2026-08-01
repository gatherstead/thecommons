from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.eventbritepittsboro import EventbritepittsboroScraper

FIXTURE = Path(__file__).parent / "fixtures" / "eventbritepittsboro.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# back-dated 2020 event to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class EventbritepittsboroExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture — no DB, no browser, no network.

    Delegates to the shared `extract_eventbrite_events` helper tested more
    thoroughly in `test_eventbriteraleigh_extract_fast.py`; this test just
    confirms the Pittsboro-specific fixture wires through correctly.
    """

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.eventbriteraleigh.timezone.now")
    def test_extracts_future_local_events(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = EventbritepittsboroScraper().extract(self.html)

        # Fixture carries 5 events: 3 future local, 1 online (dropped), 1
        # back-dated to 2020 (dropped by the past-event filter).
        self.assertEqual(len(events), 3)

        trivia = next(e for e in events if e.title == "Doherty's Pub Trivia w/ Patrick W")
        self.assertEqual(trivia.start.isoformat(), "2026-08-04T19:00:00-04:00")
        self.assertIsNotNone(trivia.start.tzinfo)
        self.assertEqual(trivia.source_uid, "1989861724985")
        self.assertEqual(
            trivia.location,
            "Doherty's Irish Pub & Restaurant, 56 Sanford Road, Pittsboro, NC",
        )
        self.assertIn("Pittsboro, NC", trivia.description)

    def test_no_server_data_yields_no_events(self):
        self.assertEqual(EventbritepittsboroScraper().extract("<html><body>nope</body></html>"), [])
