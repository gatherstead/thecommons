import json
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.chapelhillarts import ChapelhillartsScraper

FIXTURE = Path(__file__).parent / "fixtures" / "chapelhillarts.html"
_LOCAL_TZ = ZoneInfo("America/New_York")

# Fixed "now" the fixture's events (Jun 25 - Sep 25, 2026) were built to be
# future-dated against -- real data confirmed live via
# GET /wp-json/nmc-feeds/v1/events on 2026-07-31, back-dated here to before
# the earliest of those events since several had already passed by the
# capture date. The fixture also carries one back-dated 2020 event to
# exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 6, 1))


@tag("fast")
class ChapelhillartsExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture -- no DB, no browser, no network."""

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.chapelhillarts.timezone.now")
    def test_extracts_future_events_from_json_feed(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = ChapelhillartsScraper().extract(self.html)

        # Fixture carries 6 items: 1 back-dated to 2020 (dropped by the
        # past-event filter) and 5 real future events.
        self.assertEqual(len(events), 5)
        self.assertNotIn("Past Event (back-dated for filter test)", [e.title for e in events])

        drone_talk = next(e for e in events if e.title == "Visiting Kalamkari Master Artist Talk")
        self.assertEqual(drone_talk.start, datetime(2026, 7, 16, 17, 30, tzinfo=_LOCAL_TZ))
        self.assertIsNotNone(drone_talk.start.tzinfo)
        self.assertEqual(drone_talk.source_uid, "8451")
        self.assertEqual(
            drone_talk.source_url,
            "https://www.chapelhillarts.org/calendar/visiting-kalamkari-master-artist-talk/",
        )
        # The feed's `end` field isn't valid ISO8601, so it's dropped rather
        # than misparsed.
        self.assertIsNone(drone_talk.end)

    def test_no_start_or_title_events_are_skipped(self):
        html = json.dumps(
            [
                {"id": 1, "title": "", "start": "2099-01-01T00:00:00", "url": "x"},
                {"id": 2, "start": "", "title": "No start"},
            ]
        )
        self.assertEqual(ChapelhillartsScraper().extract(html), [])

    def test_malformed_json_yields_no_events(self):
        self.assertEqual(ChapelhillartsScraper().extract("<html><body>nope</body></html>"), [])

    def test_non_list_json_yields_no_events(self):
        self.assertEqual(ChapelhillartsScraper().extract('{"error": "not found"}'), [])
