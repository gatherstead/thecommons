from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag
from django.utils import timezone

from ingestion.scraping.scrapers.patchpittsboro import PatchpittsboroScraper

FIXTURE = Path(__file__).parent / "fixtures" / "patchpittsboro.html"

# Fixed "now" the fixture's events were built to be future-dated against
# (real data confirmed live 2026-07-31); the fixture also carries one
# synthetic back-dated event to exercise the past-event filter.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 31))


@tag("fast")
class PatchpittsboroExtractTests(SimpleTestCase):
    """Pure `extract()` against a saved real fixture -- no DB, no browser, no network.

    Pittsboro's calendar carries only `patchAmFreeEvent` nodes (no
    Patch-authored `event` nodes at all), so this exercises the aggregator
    node shape: date + separate 12-hour time string, no body/description,
    `externalUrl` as the source link.
    """

    def setUp(self):
        self.html = FIXTURE.read_text(encoding="utf-8")

    @mock.patch("ingestion.scraping.scrapers.patch.timezone.now")
    def test_extracts_future_events_from_next_data(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = PatchpittsboroScraper().extract(self.html)

        # Fixture carries 4 events across day buckets: 3 future, 1 back-dated
        # to 2020 that the past-event filter must drop.
        self.assertEqual(len(events), 3)
        self.assertNotIn("Past Event (back-dated for filter test)", [e.title for e in events])

        okra = next(e for e in events if "Okra Jamboree" in e.title)
        self.assertEqual(okra.start.isoformat(), "2026-08-02T12:00:00-04:00")
        self.assertIsNotNone(okra.start.tzinfo)
        self.assertIsNone(okra.end)
        self.assertEqual(okra.source_uid, "10837944")
        self.assertEqual(
            okra.source_url,
            "https://thetriangleweekender.com/event/third-annual-okra-jamboree/",
        )
        # `patchAmAddressStr` already reads "Venue, Street, City"; the region
        # gets appended since it isn't part of that string.
        self.assertEqual(okra.location, "The Plant, 220 Lorax Ln, Pittsboro, NC")
        # No body/summary field exists on this node shape.
        self.assertEqual(okra.description, "")

    @mock.patch("ingestion.scraping.scrapers.patch.timezone.now")
    def test_titles_are_html_unescaped(self, mock_now):
        mock_now.return_value = _FIXTURE_BUILD_TIME
        events = PatchpittsboroScraper().extract(self.html)

        dance = next(e for e in events if "Inclusive Dance" in e.title)
        self.assertEqual(
            dance.title, "ALL-Together! Friends Group – Inclusive Dance and Activities"
        )
        self.assertEqual(dance.start.isoformat(), "2026-08-06T11:00:00-04:00")

    def test_no_next_data_yields_no_events(self):
        self.assertEqual(PatchpittsboroScraper().extract("<html><body>nope</body></html>"), [])
