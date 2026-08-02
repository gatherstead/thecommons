from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.chathamchamber import ChathamchamberScraper

FIXTURE = Path(__file__).parent / "fixtures" / "chathamchamber.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# card whose dates were edited to 2020 to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class ChathamchamberExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture -- no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.chathamchamber.timezone.now")
    def test_extracts_future_and_ongoing_events_from_microdata(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = ChathamchamberScraper().extract(self.html)

        # Fixture carries 5 cards: 4 real (one an ongoing series whose
        # startDate is already past but endDate is future) + 1 back-dated
        # to 2020 that the past-event filter must drop.
        self.assertEqual(len(events), 4)
        self.assertNotIn("Past Event (back-dated for filter test)", [e.title for e in events])

        film_series = next(e for e in events if e.title.startswith("Goldston America 250"))
        self.assertEqual(film_series.start.isoformat(), "2026-01-17T16:00:00-05:00")
        self.assertEqual(film_series.end.isoformat(), "2026-12-22T18:00:00-05:00")
        self.assertIsNotNone(film_series.start.tzinfo)
        self.assertEqual(
            film_series.source_url,
            "https://business.chathamchambernc.org/chatham-community-events/"
            "Details/goldston-america-250-film-series-1591589",
        )
        self.assertEqual(film_series.source_uid, film_series.source_url)

        walking_tour = next(e for e in events if e.title.startswith("Historical Walking Tour"))
        self.assertEqual(walking_tour.start.isoformat(), "2026-08-09T13:00:00-04:00")
        self.assertEqual(walking_tour.end.isoformat(), "2026-08-09T14:30:00-04:00")
        self.assertEqual(walking_tour.description, "")

    @mock.patch("ingestion.scraping.scrapers.chathamchamber.timezone.now")
    def test_description_is_html_unescaped_when_present(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = ChathamchamberScraper().extract(self.html)

        race_amity = next(e for e in events if e.title == "Race Amity Day")
        self.assertIn("Mindful Musical Walk", race_amity.description)
        self.assertNotIn("<p", race_amity.description)

    @mock.patch("ingestion.scraping.scrapers.chathamchamber.timezone.now")
    def test_titles_are_html_unescaped(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = ChathamchamberScraper().extract(self.html)

        drone_show = next(e for e in events if "Drone Light Show" in e.title)
        self.assertEqual(
            drone_show.title, "Brightspeed's Merry + Bright Christmas Drone Light Show"
        )

    def test_no_event_cards_yields_no_events(self):
        self.assertEqual(ChathamchamberScraper().extract("<html><body>nope</body></html>"), [])
