from datetime import datetime, timezone as dt_timezone

from django.test import TestCase, tag

from broadcast.models import BroadcastSubmission, BroadcastTarget
from broadcast.worker import claim_next, recover_orphans


def make_submission(status="queued"):
    return BroadcastSubmission.objects.create(
        client_label="test",
        title="T", description="D",
        start_datetime=datetime(2026, 7, 10, 19, 0, tzinfo=dt_timezone.utc),
        venue_name="V", address_line1="1 Main St", city="Pittsboro",
        zip="27312", locality="pittsboro", categories=["music"],
        status=status,
    )


@tag("db")
class WorkerQueueTest(TestCase):
    def test_claim_oldest_queued_and_mark_running(self):
        first = make_submission()
        make_submission()
        claimed = claim_next()
        self.assertEqual(claimed.id, first.id)
        self.assertEqual(claimed.status, "running")

    def test_claim_empty_queue_returns_none(self):
        make_submission(status="done")
        self.assertIsNone(claim_next())

    def test_recover_orphans_requeues_killed_run(self):
        orphan = make_submission(status="running")
        BroadcastTarget.objects.create(
            submission=orphan, site_key="mock_site", status="in_progress", attempts=1
        )
        BroadcastTarget.objects.create(
            submission=orphan, site_key="explore_pittsboro", status="succeeded"
        )

        self.assertEqual(recover_orphans(), 1)
        orphan.refresh_from_db()
        self.assertEqual(orphan.status, "queued")
        # interrupted target re-queued, finished one untouched, no duplicate rows
        self.assertEqual(orphan.targets.get(site_key="mock_site").status, "pending")
        self.assertEqual(orphan.targets.get(site_key="explore_pittsboro").status, "succeeded")
        self.assertEqual(orphan.targets.count(), 2)
        self.assertEqual(orphan.targets.get(site_key="mock_site").attempts, 1)
