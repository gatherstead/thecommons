"""Tests for the Celery task wrappers around the broadcast worker.

Tasks are called directly (not via .delay()) since the test suite has no live
Redis broker. run_submission's _run_target is stubbed the same way
test_runner.py does it, so process_broadcast_queue drains real submissions to
a terminal state without launching Playwright/Chromium.
"""

from datetime import UTC, datetime
from unittest import mock

from django.test import TestCase, tag

from broadcast.adapters.base import TargetResult
from broadcast.models import BroadcastSubmission, BroadcastTarget
from broadcast.tasks import process_broadcast_queue, recover_broadcast_orphans


def make_submission(status="queued"):
    return BroadcastSubmission.objects.create(
        client_label="test",
        title="T",
        description="D",
        start_datetime=datetime(2026, 7, 10, 19, 0, tzinfo=UTC),
        venue_name="V",
        address_line1="1 Main St",
        city="Pittsboro",
        zip="27312",
        locality="pittsboro",
        categories=["music"],
        status=status,
    )


@tag("db")
class ProcessBroadcastQueueTests(TestCase):
    def test_drains_all_queued_submissions(self):
        first = make_submission()
        BroadcastTarget.objects.create(submission=first, site_key="mock_site")
        second = make_submission()
        BroadcastTarget.objects.create(submission=second, site_key="mock_site")

        with mock.patch(
            "broadcast.runner._run_target",
            return_value=TargetResult(status="succeeded", external_url="https://x/1"),
        ):
            processed = process_broadcast_queue()

        self.assertEqual(processed, 2)
        self.assertEqual(BroadcastSubmission.objects.filter(status="queued").count(), 0)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, "done")
        self.assertEqual(second.status, "done")

    def test_empty_queue_processes_nothing(self):
        self.assertEqual(process_broadcast_queue(), 0)


@tag("db")
class RecoverBroadcastOrphansTests(TestCase):
    def test_requeues_stranded_running_submission(self):
        orphan = make_submission(status="running")
        BroadcastTarget.objects.create(
            submission=orphan, site_key="mock_site", status="in_progress", attempts=1
        )

        count = recover_broadcast_orphans()

        self.assertEqual(count, 1)
        orphan.refresh_from_db()
        self.assertEqual(orphan.status, "queued")
        self.assertEqual(orphan.targets.get(site_key="mock_site").status, "pending")
