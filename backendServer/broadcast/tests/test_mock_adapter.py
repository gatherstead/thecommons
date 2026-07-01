"""End-to-end adapter integration: runs the mock adapter through the real
runner pipeline (Playwright + Chromium) against the local static form.
Skipped automatically when the Playwright browser is not installed.
"""
import shutil
import tempfile
import unittest
from datetime import datetime, timezone as dt_timezone

from django.test import TestCase, override_settings, tag

from broadcast.adapters._mock import MockSiteAdapter
from broadcast.adapters.base import RunContext
from broadcast.schema import CanonicalEvent


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return bool(p.chromium.executable_path) and \
                shutil.os.path.exists(p.chromium.executable_path)
    except Exception:
        return False


CHROMIUM = _chromium_available()


def make_event():
    return CanonicalEvent(
        title="International Dance Night @ The Plant",
        description="Live international music and social dancing.",
        start_datetime=datetime(2026, 7, 10, 19, 0, tzinfo=dt_timezone.utc),
        end_datetime=datetime(2026, 7, 10, 22, 0, tzinfo=dt_timezone.utc),
        venue_name="The Plant",
        address_line1="220 Lorax Ln",
        city="Pittsboro",
        zip="27312",
        locality="pittsboro",
        categories=["music", "community", "nightlife"],
        event_url="https://www.theplantnc.com/events/international-dance-night",
        price="Free",
        is_free=True,
        organizer_name="The Plant",
        contact_email="events@theplantnc.com",
    )


@tag("db")
@unittest.skipUnless(CHROMIUM, "Playwright Chromium not installed")
class MockAdapterEndToEndTest(TestCase):
    def _run(self, dry_run: bool):
        from playwright.sync_api import sync_playwright

        adapter = MockSiteAdapter()
        with tempfile.TemporaryDirectory() as shots, tempfile.TemporaryDirectory() as downloads:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_context().new_page()
                    ctx = RunContext(
                        dry_run=dry_run, screenshot_dir=shots,
                        download_dir=downloads, submission_id="test",
                    )
                    result = adapter.fill_and_submit(page, make_event(), ctx)
                    self.assertTrue(shutil.os.path.exists(result.screenshot_path))
                finally:
                    browser.close()
        return result

    def test_dry_run_fills_but_never_submits(self):
        result = self._run(dry_run=True)
        self.assertEqual(result.status, "succeeded")
        self.assertIn("[DRY RUN]", result.error)
        self.assertEqual(result.external_url, "")

    def test_real_run_submits_and_confirms(self):
        result = self._run(dry_run=False)
        self.assertEqual(result.status, "succeeded")
        self.assertIn("#submitted", result.external_url)


@tag("db")
@unittest.skipUnless(CHROMIUM, "Playwright Chromium not installed")
class WorkerPipelineTest(TestCase):
    """Full path: submission row → worker claim → runner → target row updated."""

    def test_worker_processes_queued_submission(self):
        import os
        from unittest import mock

        from broadcast.models import BroadcastSubmission, BroadcastTarget
        from broadcast.worker import run_once

        with tempfile.TemporaryDirectory() as shots, tempfile.TemporaryDirectory() as dl:
            submission = BroadcastSubmission.objects.create(
                client_label="test",
                title="T", description="D",
                start_datetime=datetime(2026, 7, 10, 19, 0, tzinfo=dt_timezone.utc),
                venue_name="V", address_line1="1 Main St", city="Pittsboro",
                zip="27312", locality="pittsboro", categories=["music"],
            )
            BroadcastTarget.objects.create(
                submission=submission, site_key="mock_site", dry_run=True
            )
            with mock.patch.dict(os.environ, {"BROADCAST_ENABLE_MOCK": "1"}), \
                 override_settings(BROADCAST_SCREENSHOT_DIR=shots, BROADCAST_DOWNLOAD_DIR=dl):
                self.assertTrue(run_once())

            submission.refresh_from_db()
            target = submission.targets.get()
            self.assertEqual(
                submission.status, "done",
                f"target status={target.status!r} error={target.error!r}",
            )
            self.assertEqual(target.status, "succeeded")
            self.assertEqual(target.attempts, 1)
            self.assertIn("[DRY RUN]", target.error)
