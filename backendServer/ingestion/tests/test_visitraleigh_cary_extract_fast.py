from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.visitraleigh_cary import VisitraleighCaryScraper

FIXTURE = Path(__file__).parent / "fixtures" / "visitraleigh_cary.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# back-dated 2020 event to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class VisitraleighCaryExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture -- no DB, no browser, no network.

    Exercises the same `_extract_events` helper as `visitraleigh.py` via the
    Cary-scoped subclass, so this focuses on cases that module's own test
    doesn't cover (the "Recurring ... until <date>" no-start-date case)
    rather than re-testing shared parsing logic end to end.
    """

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.visitraleigh.timezone.now")
    def test_extracts_future_events(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = VisitraleighCaryScraper().extract(self.html)

        # Fixture carries 4 events: 3 future, 1 back-dated to 2020 that the
        # past-event filter must drop.
        self.assertEqual(len(events), 3)
        self.assertNotIn("Past Event (back-dated for filter test)", [e.title for e in events])

    @mock.patch("ingestion.scraping.scrapers.visitraleigh.timezone.now")
    def test_recurring_listing_falls_back_to_until_date(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = VisitraleighCaryScraper().extract(self.html)

        clue = next(e for e in events if e.title == "Clue (High School Edition)")
        # "Recurring weekly on Sunday, Friday, Saturday until August 9, 2026"
        # has only one parseable date, so it becomes `start` with no `end`.
        self.assertEqual(clue.start.isoformat(), "2026-08-09T19:30:00-04:00")
        self.assertIsNone(clue.end)
        self.assertEqual(clue.source_uid, "105919")
        self.assertEqual(clue.location, "Raleigh Little Theatre")

    @mock.patch("ingestion.scraping.scrapers.visitraleigh.timezone.now")
    def test_source_url_and_name(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = VisitraleighCaryScraper().extract(self.html)

        comedy = next(e for e in events if e.title.startswith("Comedy Show"))
        self.assertEqual(
            comedy.source_url,
            "https://www.visitraleigh.com/event/comedy-show%3a-cyrus-steele-%2b-joe-perrow/108510/",
        )
        self.assertEqual(VisitraleighCaryScraper.name, "Visit Raleigh (Cary)")
        self.assertEqual(VisitraleighCaryScraper.key, "visitraleigh_cary")

    def test_no_recid_items_yields_no_events(self):
        self.assertEqual(VisitraleighCaryScraper().extract("<html><body>nope</body></html>"), [])
