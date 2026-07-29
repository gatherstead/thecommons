"""Ticket 32.4: poll_all_ics_sources / poll_all_scraper_sources must each
write exactly one SourceRun row per source per invocation, covering the
success, failure, refusal, and backoff-skip paths -- and a SourceRun write
failure must never abort the poll loop or affect last_polled semantics.
"""

from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import TestCase, tag
from django.utils import timezone

from ingestion.importers.ics_importer import poll_all_ics_sources
from ingestion.importers.scraper_importer import poll_all_scraper_sources
from ingestion.models import EventSource, SourceRun

ICS_FIXTURE = Path(__file__).parent / "fixtures" / "sample.ics"
SCRAPER_FIXTURE = Path(__file__).parent / "fixtures" / "visitpittsboro_month.html"

# Matches test_scraper_importer_db.py: the fixture's events are future-dated
# relative to this fixed "now".
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 11))


@tag("db")
class IcsSourceRunTests(TestCase):
    def setUp(self):
        self.source = EventSource.objects.create(
            name="Test Feed", source_type="ics", url="https://feed.test/cal.ics"
        )
        self.ics_text = ICS_FIXTURE.read_text()

    def _patched_fetch(self):
        resp = mock.Mock()
        resp.text = self.ics_text
        resp.raise_for_status.return_value = None
        return mock.patch("ingestion.importers.ics_importer.requests.get", return_value=resp)

    def test_success_writes_single_ok_run(self):
        with self._patched_fetch():
            total_new = poll_all_ics_sources()

        self.assertEqual(total_new, 2)
        runs = SourceRun.objects.filter(source=self.source)
        self.assertEqual(runs.count(), 1)
        run = runs.get()
        self.assertEqual(run.status, "ok")
        self.assertEqual(run.items_new, 2)
        self.assertIsNotNone(run.finished_at)

    def test_failure_writes_single_failed_run_and_loop_continues(self):
        other = EventSource.objects.create(
            name="Second Feed", source_type="ics", url="https://feed2.test/cal.ics"
        )

        good_resp = mock.Mock()
        good_resp.text = self.ics_text
        good_resp.raise_for_status.return_value = None

        def _get(url, **kwargs):
            if url == self.source.url:
                raise ConnectionError("boom")
            return good_resp

        with mock.patch("ingestion.importers.ics_importer.requests.get", side_effect=_get):
            total_new = poll_all_ics_sources()

        # Only the second (working) source contributed new events.
        self.assertEqual(total_new, 2)

        failed_run = SourceRun.objects.get(source=self.source)
        self.assertEqual(failed_run.status, "failed")
        self.assertEqual(failed_run.error_class, "ConnectionError")
        self.assertIn("boom", failed_run.error_message)
        self.assertNotEqual(failed_run.traceback, "")
        self.assertIsNotNone(failed_run.finished_at)

        ok_run = SourceRun.objects.get(source=other)
        self.assertEqual(ok_run.status, "ok")

    def test_failure_does_not_write_last_polled(self):
        with mock.patch(
            "ingestion.importers.ics_importer.requests.get", side_effect=ConnectionError("boom")
        ):
            poll_all_ics_sources()

        self.source.refresh_from_db()
        self.assertIsNone(self.source.last_polled)

    def test_backoff_branch_writes_skipped_run(self):
        self.source.last_polled = timezone.now()
        self.source.poll_interval_hours = 24
        self.source.save(update_fields=["last_polled", "poll_interval_hours"])

        with self._patched_fetch() as get:
            total_new = poll_all_ics_sources()

        get.assert_not_called()
        self.assertEqual(total_new, 0)
        run = SourceRun.objects.get(source=self.source)
        self.assertEqual(run.status, "skipped")

    def test_source_run_write_failure_does_not_abort_poll(self):
        with (
            self._patched_fetch(),
            mock.patch(
                "ingestion.importers.source_run.SourceRun.objects.create",
                side_effect=Exception("db unavailable"),
            ),
        ):
            total_new = poll_all_ics_sources()

        # Polling itself still ran and returned the right count, even though
        # no SourceRun row could be recorded.
        self.assertEqual(total_new, 2)
        self.assertEqual(SourceRun.objects.filter(source=self.source).count(), 0)
        self.source.refresh_from_db()
        self.assertIsNotNone(self.source.last_polled)


@tag("db")
class ScraperSourceRunTests(TestCase):
    def setUp(self):
        self.source = EventSource.objects.create(
            name="VisitPittsboro",
            source_type="scraper",
            url="https://visitpittsboro.com/events/month/",
            scraper_key="visitpittsboro",
        )
        self.html = SCRAPER_FIXTURE.read_text(encoding="utf-8")
        self.enterContext(
            mock.patch(
                "ingestion.scraping.scrapers.visitpittsboro.timezone.now",
                return_value=_FIXTURE_BUILD_TIME,
            )
        )

    def _patched_render(self):
        return mock.patch(
            "ingestion.importers.scraper_importer.render_page", return_value=self.html
        )

    def test_success_writes_single_ok_run(self):
        with self._patched_render():
            total_new = poll_all_scraper_sources()

        self.assertEqual(total_new, 3)
        runs = SourceRun.objects.filter(source=self.source)
        self.assertEqual(runs.count(), 1)
        run = runs.get()
        self.assertEqual(run.status, "ok")
        self.assertEqual(run.items_new, 3)
        self.assertIsNotNone(run.finished_at)

    def test_non_public_url_writes_single_refused_run(self):
        self.source.url = "http://localhost:8000/events"
        self.source.save(update_fields=["url"])

        with self._patched_render() as render:
            total_new = poll_all_scraper_sources()

        render.assert_not_called()
        self.assertEqual(total_new, 0)
        run = SourceRun.objects.get(source=self.source)
        self.assertEqual(run.status, "refused")
        self.assertIn("non_public_url", run.error_message)

    def test_unknown_scraper_key_writes_single_refused_run(self):
        self.source.scraper_key = "does-not-exist"
        self.source.save(update_fields=["scraper_key"])

        with self._patched_render():
            total_new = poll_all_scraper_sources()

        self.assertEqual(total_new, 0)
        run = SourceRun.objects.get(source=self.source)
        self.assertEqual(run.status, "refused")
        self.assertIn("unknown_scraper_key", run.error_message)

    def test_empty_fetch_writes_single_refused_run(self):
        with mock.patch("ingestion.importers.scraper_importer.render_page", return_value=""):
            total_new = poll_all_scraper_sources()

        self.assertEqual(total_new, 0)
        run = SourceRun.objects.get(source=self.source)
        self.assertEqual(run.status, "refused")
        self.assertIn("empty_fetch", run.error_message)

    def test_refusal_does_not_write_last_polled(self):
        with mock.patch("ingestion.importers.scraper_importer.render_page", return_value=""):
            poll_all_scraper_sources()

        self.source.refresh_from_db()
        self.assertIsNone(self.source.last_polled)

    def test_failure_writes_single_failed_run_and_loop_continues(self):
        other = EventSource.objects.create(
            name="Other scraper",
            source_type="scraper",
            url="https://other.example.com/events/",
            scraper_key="visitpittsboro",
        )

        def _render(url, **kwargs):
            if url == self.source.url:
                raise RuntimeError("browser crashed")
            return self.html

        with (
            mock.patch("ingestion.importers.scraper_importer.render_page", side_effect=_render),
            # Only DNS-resolves the fixture's real domain; "other" is a
            # fictitious host used purely to exercise the loop-continues
            # path, so the public-URL guard is bypassed here rather than
            # relying on real DNS resolution in a unit test.
            mock.patch("ingestion.importers.scraper_importer._is_public_url", return_value=True),
        ):
            total_new = poll_all_scraper_sources()

        self.assertEqual(total_new, 3)

        failed_run = SourceRun.objects.get(source=self.source)
        self.assertEqual(failed_run.status, "failed")
        self.assertEqual(failed_run.error_class, "RuntimeError")
        self.assertIn("browser crashed", failed_run.error_message)
        self.assertNotEqual(failed_run.traceback, "")

        ok_run = SourceRun.objects.get(source=other)
        self.assertEqual(ok_run.status, "ok")

    def test_backoff_branch_writes_skipped_run(self):
        self.source.last_polled = timezone.now()
        self.source.poll_interval_hours = 24
        self.source.save(update_fields=["last_polled", "poll_interval_hours"])

        with self._patched_render() as render:
            total_new = poll_all_scraper_sources()

        render.assert_not_called()
        self.assertEqual(total_new, 0)
        run = SourceRun.objects.get(source=self.source)
        self.assertEqual(run.status, "skipped")

    def test_source_run_write_failure_does_not_abort_poll(self):
        with (
            self._patched_render(),
            mock.patch(
                "ingestion.importers.source_run.SourceRun.objects.create",
                side_effect=Exception("db unavailable"),
            ),
        ):
            total_new = poll_all_scraper_sources()

        self.assertEqual(total_new, 3)
        self.assertEqual(SourceRun.objects.filter(source=self.source).count(), 0)
        self.source.refresh_from_db()
        self.assertIsNotNone(self.source.last_polled)
