from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.downtowncarync import DowntowncarynScraper

FIXTURE = Path(__file__).parent / "fixtures" / "downtowncarync.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31, mid-afternoon UTC). The fixture keeps
# two back-dated (2026-07-03) events and one same-day (2026-07-31, 7pm ET,
# still future relative to this "now") plus one clearly-future (2026-08-02)
# event to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31, 12, 0))


@tag("fast")
class DowntowncarynExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture -- no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.downtowncarync.timezone.now")
    def test_extracts_future_events_from_month_grid(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = DowntowncarynScraper().extract(self.html)

        # Fixture carries 5 events: 2 back-dated to July 3, 1 later today
        # (July 31, 7pm), and 2 in the future (Aug 2).
        self.assertEqual(len(events), 2)
        titles = [e.title for e in events]
        self.assertNotIn("July 3rd Celebration", titles)
        self.assertNotIn(
            "Cary Town Band presents America’s 250th Anniversary Patriotic Celebration",
            titles,
        )

        dance = next(e for e in events if e.title == "Discover Dance: DISHOOM")
        self.assertEqual(dance.start.isoformat(), "2026-07-31T19:00:00-04:00")
        self.assertIsNotNone(dance.start.tzinfo)
        self.assertEqual(dance.end.isoformat(), "2026-07-31T22:30:00-04:00")
        self.assertEqual(
            dance.source_url, "https://downtowncarync.org/event/discover-dance-dishoom-2/"
        )
        self.assertEqual(dance.source_uid, dance.source_url)
        self.assertEqual(dance.location, "")
        self.assertIn("DISHOOM returns to Downtown Cary Park", dance.description)

        artists = next(e for e in events if e.title == "Meet the Artists: Fine Arts League of Cary")
        self.assertEqual(artists.start.isoformat(), "2026-08-02T14:00:00-04:00")

    @mock.patch("ingestion.scraping.scrapers.downtowncarync.timezone.now")
    def test_titles_are_html_unescaped(self, mock_now):
        # Use a "now" before all fixture events so the back-dated (but
        # entity-escaped) title survives the past-event filter.
        mock_now.return_value = timezone.make_aware(datetime(2000, 1, 1))
        events = DowntowncarynScraper().extract(self.html)

        band = next(e for e in events if "Cary Town Band" in e.title)
        self.assertEqual(
            band.title,
            "Cary Town Band presents America’s 250th Anniversary Patriotic Celebration",
        )
        self.assertNotIn("&#8217;", band.description)
        self.assertIn("America’s Semi-Quincentennial", band.description)

    def test_no_matching_articles_yields_no_events(self):
        self.assertEqual(DowntowncarynScraper().extract("<html><body>nope</body></html>"), [])
