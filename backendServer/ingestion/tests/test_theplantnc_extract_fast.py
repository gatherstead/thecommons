from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.theplantnc import TheplantncScraper

FIXTURE = Path(__file__).parent / "fixtures" / "theplantnc.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-13); the fixture also carries one
# 2020-dated event to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 13))


@tag("fast")
class TheplantncExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture — no DB, no mocks, no browser."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.theplantnc.timezone.now")
    def test_extracts_future_events_deduped_across_widgets(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = TheplantncScraper().extract(self.html)

        # Fixture has 4 event entries across two widget components: one id
        # duplicated in both (dedupe -> 1), one distinct future event, and
        # one 2020-dated event that must be dropped by the past-event filter.
        self.assertEqual(len(events), 2)

        tween = next(
            e for e in events if e.title == "Tween Tuesdays: Animal Collages @ Roam Paint Press"
        )
        self.assertEqual(tween.location, "The Plant")
        self.assertEqual(
            tween.source_url,
            "https://www.theplantnc.com/event-details/tween-tuesdays-animal-collages-roam-paint-press-2026-07-14-11-00",
        )
        self.assertTrue(tween.start.tzinfo is not None)
        self.assertEqual(tween.start.isoformat(), "2026-07-14T15:00:00+00:00")
        self.assertEqual(tween.source_uid, "113be0b5-da7d-4c0c-9eb6-27bb21368d3c")

        tomato = next(e for e in events if e.title == "Chatham Tomato Festival")
        self.assertIn("tomatoes", tomato.description)
        self.assertEqual(tomato.end.isoformat(), "2026-08-09T22:00:00+00:00")

        self.assertNotIn("Member Mixer", [e.title for e in events])
