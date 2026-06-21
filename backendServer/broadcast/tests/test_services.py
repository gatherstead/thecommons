"""Direct service-level transition tests for the broadcast state machine.
Covers branches the API tests don't already assert."""
from datetime import datetime, timezone as dt_timezone

from django.test import TestCase

from broadcast.models import BroadcastSubmission, BroadcastTarget
from broadcast.services import cancel_submission, retry_targets, submit_real_targets


def make_submission(status="queued"):
    return BroadcastSubmission.objects.create(
        client_label="test",
        title="T", description="D",
        start_datetime=datetime(2026, 7, 10, 19, 0, tzinfo=dt_timezone.utc),
        venue_name="V", address_line1="1 Main St", city="Pittsboro",
        zip="27312", locality=["pittsboro"], categories=["music"],
        status=status,
    )


class CancelSubmissionTests(TestCase):
    def test_cancel_active_skips_pending_targets(self):
        submission = make_submission(status="queued")
        BroadcastTarget.objects.create(submission=submission, site_key="a_site")

        self.assertEqual(cancel_submission(submission), 1)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "canceled")
        self.assertEqual(submission.targets.get(site_key="a_site").status, "skipped")

    def test_cancel_is_noop_on_terminal_status(self):
        for terminal in ("done", "failed", "canceled"):
            with self.subTest(status=terminal):
                submission = make_submission(status=terminal)
                BroadcastTarget.objects.create(submission=submission, site_key="a_site")

                self.assertEqual(cancel_submission(submission), 0)
                submission.refresh_from_db()
                self.assertEqual(submission.status, terminal)
                self.assertEqual(submission.targets.get(site_key="a_site").status, "pending")


class SubmitRealTargetsTests(TestCase):
    def test_only_dry_run_targets_flip_to_real(self):
        submission = make_submission(status="done")
        BroadcastTarget.objects.create(
            submission=submission, site_key="dry_site", status="succeeded", dry_run=True
        )
        BroadcastTarget.objects.create(
            submission=submission, site_key="real_site", status="succeeded", dry_run=False
        )

        updated = submit_real_targets(submission, ["dry_site", "real_site"])

        self.assertEqual(updated, 1)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "queued")
        dry = submission.targets.get(site_key="dry_site")
        self.assertEqual(dry.status, "pending")
        self.assertFalse(dry.dry_run)
        # Already-real target is untouched.
        real = submission.targets.get(site_key="real_site")
        self.assertEqual(real.status, "succeeded")


class RetryTargetsTests(TestCase):
    def test_only_non_pending_targets_reset(self):
        submission = make_submission(status="failed")
        BroadcastTarget.objects.create(
            submission=submission, site_key="failed_site", status="failed", error="x"
        )
        BroadcastTarget.objects.create(
            submission=submission, site_key="pending_site", status="pending"
        )

        updated = retry_targets(submission, ["failed_site", "pending_site"])

        self.assertEqual(updated, 1)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "queued")
        reset = submission.targets.get(site_key="failed_site")
        self.assertEqual(reset.status, "pending")
        self.assertEqual(reset.error, "")
