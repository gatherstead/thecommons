from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.eventbritemorrisville import EventbritemorrisvilleScraper

FIXTURE = Path(__file__).parent / "fixtures" / "eventbritemorrisville.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# back-dated 2020 event to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class EventbritemorrisvilleExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture — no DB, no browser, no network.

    Delegates to the shared `extract_eventbrite_events` helper tested more
    thoroughly in `test_eventbriteraleigh_extract_fast.py`. This fixture is
    also the receipt for the quality warning in
    `eventbritemorrisville.py`'s docstring: none of the "Popular" bucket
    events on the real Morrisville discovery page (captured 2026-07-31) are
    actually Morrisville-located — extraction still works correctly, it
    just doesn't return Morrisville events.
    """

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.eventbriteraleigh.timezone.now")
    def test_extracts_future_events_none_of_which_are_morrisville(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = EventbritemorrisvilleScraper().extract(self.html)

        # Fixture carries 5 events: 3 future, 1 online (dropped), 1
        # back-dated to 2020 (dropped by the past-event filter).
        self.assertEqual(len(events), 3)
        # Real spillover: the Morrisville discovery page's "Popular" bucket
        # returned only Raleigh-located events on this capture.
        self.assertTrue(all("Raleigh" in e.location for e in events))
        self.assertTrue(all("Morrisville" not in e.location for e in events))

        jersey = next(e for e in events if e.title.startswith("The 4th Annual Jersey Fest"))
        self.assertEqual(jersey.start.isoformat(), "2026-08-01T18:00:00-04:00")
        self.assertEqual(jersey.source_uid, "1992735047169")
        self.assertEqual(
            jersey.location, "The London Bridge Pub, 110 East Hargett Street, Raleigh, NC"
        )

    def test_no_server_data_yields_no_events(self):
        self.assertEqual(
            EventbritemorrisvilleScraper().extract("<html><body>nope</body></html>"), []
        )
