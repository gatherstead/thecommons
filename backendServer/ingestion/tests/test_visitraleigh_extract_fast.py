from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.visitraleigh import VisitraleighScraper

FIXTURE = Path(__file__).parent / "fixtures" / "visitraleigh.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# back-dated 2020 event to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class VisitraleighExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture -- no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.visitraleigh.timezone.now")
    def test_extracts_future_events(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = VisitraleighScraper().extract(self.html)

        # Fixture carries 4 events: 3 future, 1 back-dated to 2020 that the
        # past-event filter must drop.
        self.assertEqual(len(events), 3)
        self.assertNotIn("Past Event (back-dated for filter test)", [e.title for e in events])

    @mock.patch("ingestion.scraping.scrapers.visitraleigh.timezone.now")
    def test_single_date_and_time(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = VisitraleighScraper().extract(self.html)

        rocky = next(e for e in events if e.title == "The Rocky Horror Picture Show")
        self.assertEqual(rocky.start.isoformat(), "2026-07-31T20:30:00-04:00")
        self.assertIsNotNone(rocky.start.tzinfo)
        self.assertIsNone(rocky.end)
        self.assertEqual(rocky.source_uid, "109424")
        self.assertEqual(
            rocky.source_url,
            "https://www.visitraleigh.com/event/the-rocky-horror-picture-show/109424/",
        )
        self.assertEqual(rocky.location, "The Rialto Theatre")

    @mock.patch("ingestion.scraping.scrapers.visitraleigh.timezone.now")
    def test_date_range_with_vary_prefix(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = VisitraleighScraper().extract(self.html)

        andrew = next(e for e in events if e.title == "Andrew Orolfo")
        # "Dates vary between July 31, 2026 - August 1, 2026", first time
        # token "9:15pm" applied to the start date.
        self.assertEqual(andrew.start.isoformat(), "2026-07-31T21:15:00-04:00")
        self.assertEqual(andrew.end.isoformat(), "2026-08-01T00:00:00-04:00")

    @mock.patch("ingestion.scraping.scrapers.visitraleigh.timezone.now")
    def test_date_range_without_vary_prefix(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = VisitraleighScraper().extract(self.html)

        bbb = next(e for e in events if e.title.startswith("Beer, Bourbon"))
        self.assertEqual(bbb.start.isoformat(), "2026-07-31T18:00:00-04:00")
        self.assertEqual(bbb.end.isoformat(), "2026-08-01T00:00:00-04:00")
        self.assertEqual(bbb.location, "Koka Booth Amphitheatre")

    def test_no_recid_items_yields_no_events(self):
        self.assertEqual(VisitraleighScraper().extract("<html><body>nope</body></html>"), [])

    def test_unrendered_template_placeholder_is_skipped(self):
        html = (
            '<div class="eventItem listing-block item" data-recid="{{recId}}">'
            '<h3><a href="/event/x/">{{title}}</a></h3></div>'
        )
        self.assertEqual(VisitraleighScraper().extract(html), [])
