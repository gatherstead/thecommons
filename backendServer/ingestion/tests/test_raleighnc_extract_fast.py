from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.raleighnc import RaleighncScraper

FIXTURE = Path(__file__).parent / "fixtures" / "raleighnc.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# back-dated (Jan 1, 2026) teaser -- a copy of a real one with only its
# title and `datetime` edited -- to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class RaleighncExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture -- no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.raleighnc.timezone.now")
    def test_extracts_future_events_from_teaser_list(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = RaleighncScraper().extract(self.html)

        # Fixture carries 5 "Upcoming Events" teasers: 4 future, 1 back-dated
        # to Jan 1 that the past-event filter must drop. The "Ongoing Events"
        # sidebar article (no `<time>` at all) must never surface.
        self.assertEqual(len(events), 4)
        self.assertNotIn("Past Event (back-dated for filter test)", [e.title for e in events])
        self.assertNotIn(
            "Continuum: Classical to Contemporary Islamic Art", [e.title for e in events]
        )

    @mock.patch("ingestion.scraping.scrapers.raleighnc.timezone.now")
    def test_event_fields(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = RaleighncScraper().extract(self.html)

        night_out = next(e for e in events if e.title.startswith("National Night Out"))
        self.assertEqual(night_out.start.isoformat(), "2026-08-04T17:30:00-04:00")
        self.assertIsNotNone(night_out.start.tzinfo)
        self.assertIsNone(night_out.end)
        self.assertEqual(
            night_out.source_url,
            "https://raleighnc.gov/engage-city/events/national-night-out-tarboro-road-community-center",
        )
        self.assertEqual(
            night_out.source_uid,
            "/engage-city/events/national-night-out-tarboro-road-community-center",
        )
        self.assertEqual(night_out.location, "Raleigh, NC")
        # No description field exists on this listing; the department/category
        # tags are the only real text available, so they're joined instead.
        self.assertEqual(
            night_out.description, "Community Engagement; Parks, Recreation, and Athletics"
        )

    def test_no_teasers_yields_no_events(self):
        self.assertEqual(RaleighncScraper().extract("<html><body>nope</body></html>"), [])
